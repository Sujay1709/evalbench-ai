import { Link, useParams } from 'react-router'

import { LoadState } from '@/components/LoadState'
import { StatusBadge } from '@/components/StatusBadge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useApi } from '@/hooks/use-api'
import { getRun, type Efficiency, type RunDetail } from '@/lib/api'
import { measured, percent, prettyJson, score, shortHash, titleCase } from '@/lib/format'

function Metric({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-widest text-muted-foreground">{label}</dt>
      <dd className="mt-1 font-mono" title={title}>
        {value}
      </dd>
    </div>
  )
}

function EfficiencyPanel({
  efficiency,
  incomplete,
}: {
  efficiency: Efficiency
  incomplete: boolean
}) {
  const rows = [
    ['Cache hits / results', `${efficiency.cache_hits} / ${efficiency.examples}`],
    ['Generated responses', String(efficiency.generated)],
    ['Median generation latency (ms)', measured(efficiency.median_generation_ms)],
    ['P95 generation latency (ms)', measured(efficiency.p95_generation_ms)],
    [
      'Input / output tokens represented',
      `${measured(efficiency.input_tokens, 0)} / ${measured(efficiency.output_tokens, 0)}`,
    ],
    ['Generation-equivalent estimate (USD)', measured(efficiency.estimated_generation_cost_usd, 6)],
    ['New-response estimate (USD)', measured(efficiency.estimated_new_response_cost_usd, 6)],
    ['Cost coverage', `${efficiency.cost_coverage} / ${efficiency.examples} results`],
  ] as const

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recorded efficiency</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {incomplete ? (
          <p>Partial results only: this run is not completed.</p>
        ) : null}
        <dl className="grid gap-4 sm:grid-cols-2">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="mt-1 font-mono tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
        <details>
          <summary className="cursor-pointer text-sm">Measurement basis</summary>
          <p className="mt-2 text-sm text-muted-foreground">
            Latency includes generated responses only; cached zeros are excluded. P95 uses linear
            quantiles. Small samples are descriptive. These are successful-response estimates, not
            invoices or complete retry costs.
          </p>
          <ul className="mt-2 list-disc pl-5 text-sm">
            {efficiency.cost_bases.length
              ? efficiency.cost_bases.map((basis) => <li key={basis}>{basis}</li>)
              : <li>No pricing basis recorded.</li>}
          </ul>
        </details>
      </CardContent>
    </Card>
  )
}

function RunBody({ detail }: { detail: RunDetail }) {
  const { run, failure, efficiency, results } = detail

  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <Link to="/" className="inline-block text-sm">
          ← All runs
        </Link>
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Evaluation run</p>
        <h1 className="break-all font-mono text-2xl md:text-3xl">{run.id}</h1>
        <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Metric label="Status" value={run.status} />
          <Metric label="Pass rate" value={percent(run.pass_rate)} />
          <Metric label="Mean score" value={score(run.mean_score)} />
          <Metric label="Dataset split" value={titleCase(run.dataset_split)} />
          <Metric label="Dataset hash" value={shortHash(run.dataset_hash)} title={run.dataset_hash} />
          <Metric
            label="Correlation ID"
            value={shortHash(run.correlation_id)}
            title={run.correlation_id}
          />
        </dl>
      </section>

      <EfficiencyPanel efficiency={efficiency} incomplete={run.status !== 'completed'} />

      {failure ? (
        <section className="rounded-xl border border-destructive bg-danger-surface p-5" role="alert">
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Action required</p>
          <h2 className="mt-1 text-xl font-medium">Evaluation did not complete</h2>
          <dl className="mt-4 space-y-3">
            <div>
              <dt className="text-muted-foreground">Error category</dt>
              <dd>{titleCase(failure.category ?? 'unclassified')}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Safe diagnostic</dt>
              <dd>{failure.message ?? 'No diagnostic message was recorded.'}</dd>
            </div>
          </dl>
          <p className="mt-4 text-sm">
            Use correlation ID <code className="font-mono">{run.correlation_id}</code> to locate
            the workflow trace.
          </p>
        </section>
      ) : null}

      <section className="space-y-4">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">
            Per-example evidence
          </p>
          <h2 className="text-2xl font-medium">Results</h2>
        </div>
        {results.length === 0 ? (
          <p className="text-muted-foreground">No example results were persisted for this run.</p>
        ) : (
          results.map((result) => (
            <article
              key={result.id}
              id={`result-${result.id}`}
              className="space-y-4 rounded-xl bg-card p-5 ring-1 ring-border"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-mono text-lg">{result.example_id}</h3>
                <StatusBadge status={result.passed ? 'pass' : 'fail'} />
              </div>
              <dl className="space-y-3">
                <div>
                  <dt className="text-muted-foreground">Input</dt>
                  <dd>
                    <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-sm">
                      {prettyJson(result.input)}
                    </pre>
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Output</dt>
                  <dd>
                    <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-sm">
                      {result.output_text}
                    </pre>
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Score evidence</dt>
                  <dd>
                    <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-sm">
                      {prettyJson(result.scorer_details)}
                    </pre>
                  </dd>
                </div>
              </dl>
              <p className="text-sm text-muted-foreground">
                Score {score(result.score)} · {result.cache_hit ? 'cache hit' : 'generated'} ·{' '}
                {result.latency_ms.toFixed(2)} ms
              </p>
            </article>
          ))
        )}
      </section>
    </div>
  )
}

export function RunDetailPage() {
  const { runId = '' } = useParams()
  const state = useApi((signal) => getRun(runId, signal), runId)

  return (
    <LoadState state={state} loadingLabel="Loading run evidence">
      {(detail) => <RunBody detail={detail} />}
    </LoadState>
  )
}
