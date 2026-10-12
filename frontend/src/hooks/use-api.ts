import { useEffect, useRef, useState } from 'react'

export type ApiState<T> =
  | { status: 'loading' }
  | { status: 'error'; error: Error & { status?: number } }
  | { status: 'ready'; data: T }

export function useApi<T>(load: (signal: AbortSignal) => Promise<T>, key: string): ApiState<T> {
  const [state, setState] = useState<ApiState<T>>({ status: 'loading' })
  const loadRef = useRef(load)
  loadRef.current = load

  useEffect(() => {
    const controller = new AbortController()
    setState({ status: 'loading' })
    loadRef
      .current(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ status: 'ready', data })
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) setState({ status: 'error', error })
      })
    return () => controller.abort()
  }, [key])

  return state
}
