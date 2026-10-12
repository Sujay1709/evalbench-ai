// Mirrors evalbench/api/schemas.py. Extra fields are forbidden there, so a
// schema change must be reflected here and in the API contract tests.

export type RunSummary = {
  id: string
  correlation_id: string
  status: string
  dataset_name: string
  dataset_version: string
  dataset_hash: string
  dataset_split: string
  prompt_id: string
  prompt_version: string
  provider: string
  total_examples: number
  passed_examples: number
  pass_rate: number
  mean_score: number
  created_at: string
  completed_at: string | null
}

export type Efficiency = {
  examples: number
  cache_hits: number
  generated: number
  median_generation_ms: number | null
  p95_generation_ms: number | null
  input_tokens: number | null
  output_tokens: number | null
  estimated_generation_cost_usd: number | null
  estimated_new_response_cost_usd: number | null
  cost_coverage: number
  cost_bases: string[]
}

export type ExampleResult = {
  id: number
  example_id: string
  passed: boolean
  score: number
  input: Record<string, unknown>
  output_text: string
  scorer_details: Record<string, unknown>[]
  cache_hit: boolean
  latency_ms: number
}

export type RunDetail = {
  run: RunSummary
  failure: { category: string | null; message: string | null } | null
  efficiency: Efficiency
  results: ExampleResult[]
}

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    headers: { Accept: 'application/json' },
    signal,
  })
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const message =
      body && typeof body === 'object' && 'error' in body && typeof body.error === 'string'
        ? body.error
        : `Request failed with HTTP ${response.status}`
    throw new ApiError(message, response.status)
  }
  if (body === null) {
    throw new ApiError('The API returned a response that was not JSON', response.status)
  }
  return body as T
}

export const listRuns = (signal?: AbortSignal) =>
  fetchJson<{ runs: RunSummary[] }>('/runs', signal)

export const getRun = (runId: string, signal?: AbortSignal) =>
  fetchJson<RunDetail>(`/runs/${encodeURIComponent(runId)}`, signal)
