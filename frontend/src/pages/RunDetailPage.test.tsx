import { cleanup, render, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getRun, type RunDetail } from '@/lib/api'
import { RunDetailPage } from '@/pages/RunDetailPage'

vi.mock('@/lib/api', () => ({
  getRun: vi.fn(),
}))

const detail: RunDetail = {
  run: {
    id: 'run-detail-1',
    correlation_id: 'corr-detail',
    status: 'completed',
    dataset_name: 'automotive_qa',
    dataset_version: 'v1',
    dataset_hash: 'b'.repeat(64),
    dataset_split: 'holdout',
    prompt_id: 'automotive_qa',
    prompt_version: 'v1',
    provider: 'mock',
    total_examples: 1,
    passed_examples: 1,
    pass_rate: 1,
    mean_score: 1,
    created_at: '2026-10-01T12:00:00+00:00',
    completed_at: '2026-10-01T12:00:01+00:00',
  },
  failure: null,
  efficiency: {
    examples: 1,
    cache_hits: 0,
    generated: 1,
    median_generation_ms: 12.5,
    p95_generation_ms: 12.5,
    input_tokens: 0,
    output_tokens: 0,
    estimated_generation_cost_usd: 0,
    estimated_new_response_cost_usd: 0,
    cost_coverage: 1,
    cost_bases: ['offline mock; no API calls'],
  },
  results: [
    {
      id: 7,
      example_id: 'auto-001',
      passed: true,
      score: 1,
      input: { question: 'What does ICE stand for?' },
      output_text: "<script>alert('unsafe')</script>",
      scorer_details: [{ scorer: 'exact_match', passed: true, score: 1 }],
      cache_hit: false,
      latency_ms: 12.5,
    },
  ],
}

function renderDetail(path = '/app/runs/run-detail-1') {
  return render(
    <MemoryRouter basename="/app" initialEntries={[path]}>
      <Routes>
        <Route path="runs/:runId" element={<RunDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.mocked(getRun).mockReset()
})

afterEach(() => {
  cleanup()
})

describe('RunDetailPage', () => {
  it('renders evidence as text and does not execute model output', async () => {
    vi.mocked(getRun).mockResolvedValue(detail)

    const { container } = renderDetail()
    const view = within(container)

    expect(await view.findByRole('heading', { name: 'run-detail-1' })).toBeInTheDocument()
    expect(view.getByText('Holdout')).toBeInTheDocument()
    expect(view.getByText("<script>alert('unsafe')</script>")).toBeInTheDocument()
    expect(container.querySelector('script')).toBeNull()
    expect(view.getByText('offline mock; no API calls')).toBeInTheDocument()
  })

  it('reports a missing run instead of an empty run', async () => {
    vi.mocked(getRun).mockRejectedValue(
      Object.assign(new Error("Evaluation run 'missing' was not found"), { status: 404 }),
    )

    const view = within(renderDetail('/app/runs/missing').container)

    expect(await view.findByRole('alert')).toHaveTextContent('Not found')
    expect(view.queryByRole('heading', { name: 'Results' })).not.toBeInTheDocument()
  })

  it('surfaces a failed run diagnostic', async () => {
    vi.mocked(getRun).mockResolvedValue({
      ...detail,
      run: { ...detail.run, status: 'failed' },
      failure: { category: 'provider_transient', message: 'provider outage' },
      results: [],
    })

    const view = within(renderDetail().container)

    expect(await view.findByRole('alert')).toHaveTextContent('Evaluation did not complete')
    expect(view.getByText('Provider Transient')).toBeInTheDocument()
    expect(view.getByText('provider outage')).toBeInTheDocument()
  })
})
