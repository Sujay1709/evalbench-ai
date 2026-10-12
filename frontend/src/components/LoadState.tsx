import type { ReactNode } from 'react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import type { ApiState } from '@/hooks/use-api'

export function LoadState<T>({
  state,
  children,
  loadingLabel,
}: {
  state: ApiState<T>
  children: (data: T) => ReactNode
  loadingLabel: string
}) {
  if (state.status === 'loading') {
    return (
      <div role="status" aria-live="polite" className="space-y-3">
        <p className="text-sm text-muted-foreground">{loadingLabel}</p>
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-3/4" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  }
  if (state.status === 'error') {
    const notFound = state.error.status === 404
    return (
      <Alert variant="destructive">
        <AlertTitle>{notFound ? 'Not found' : 'Unable to load evidence'}</AlertTitle>
        <AlertDescription>{state.error.message}</AlertDescription>
      </Alert>
    )
  }
  return <>{children(state.data)}</>
}
