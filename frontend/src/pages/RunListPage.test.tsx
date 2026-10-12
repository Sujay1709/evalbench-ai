import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { RunSummary } from '@/lib/api'
import { listRuns } from '@/lib/api'
import { RunListPage } from '@/pages/RunListPage'

vi.mock('@/lib/api', () => ({
  listRuns: vi.fn(),
}))

const run: RunSummary = {
  id: 'run-12345678-abcd',
  correlation_id: 'corr-1',
  status: 'completed',
  dataset_name: 'automotive_qa',
  dataset_version: 'v1',
  dataset_hash: 'a'.repeat(64),
  dataset_split: 'development',
  prompt_id: 'automotive_qa',
  prompt_version: 'v1',
  provider: 'mock',
  total_examples: 3,
  passed_examples: 3,
  pass_rate: 1,
  mean_score: 1,
  created_at: '2026-10-01T12:00:00+00:00',
  completed_at: '2026-10-01T12:00:01+00:00',
}

function renderList() {
  return render(
    <MemoryRouter basename="/app" initialEntries={['/app/']}>
      <RunListPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.mocked(listRuns).mockReset()
})

afterEach(() => {
  document.body.replaceChildren()
})

describe('RunListPage', () => {
  it('shows an empty state when no runs exist', async () => {
    vi.mocked(listRuns).mockResolvedValue({ runs: [] })

    renderList()

    expect(await screen.findByRole('heading', { name: 'No runs yet' })).toBeInTheDocument()
    expect(screen.getByText(/python -m evalbench.cli run/)).toBeInTheDocument()
  })

  it('links each run by its short identifier', async () => {
    vi.mocked(listRuns).mockResolvedValue({ runs: [run] })

    renderList()

    const link = await screen.findByRole('link', { name: 'run-1234' })
    expect(link).toHaveAttribute('href', '/app/runs/run-12345678-abcd')
    expect(screen.getByText('100%')).toBeInTheDocument()
    expect(screen.getByText('Development')).toBeInTheDocument()
  })

  it('explains a failed request without treating it as empty', async () => {
    vi.mocked(listRuns).mockRejectedValue(Object.assign(new Error('database unavailable'), { status: 500 }))

    const { container } = renderList()
    const view = within(container)

    expect(await view.findByRole('alert')).toHaveTextContent('database unavailable')
    expect(view.queryByRole('heading', { name: 'No runs yet' })).not.toBeInTheDocument()
  })
})
