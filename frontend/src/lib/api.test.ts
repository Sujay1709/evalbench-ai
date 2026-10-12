import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, getRun, listRuns } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api client', () => {
  it('returns JSON from a successful request', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ runs: [] }),
      }),
    )

    await expect(listRuns()).resolves.toEqual({ runs: [] })
    expect(fetch).toHaveBeenCalledWith('/api/v1/runs', {
      headers: { Accept: 'application/json' },
      signal: undefined,
    })
  })

  it('uses the API error message and status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: "Evaluation run 'missing' was not found" }),
      }),
    )

    await expect(getRun('missing')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      message: "Evaluation run 'missing' was not found",
    } satisfies Partial<ApiError>)
  })
})
