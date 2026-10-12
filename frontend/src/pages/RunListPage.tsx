import { Link } from 'react-router'

import { LoadState } from '@/components/LoadState'
import { StatusBadge } from '@/components/StatusBadge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useApi } from '@/hooks/use-api'
import { listRuns } from '@/lib/api'
import { percent, shortId, timestamp, titleCase } from '@/lib/format'

export function RunListPage() {
  const state = useApi(listRuns, 'runs')

  return (
    <div className="space-y-10">
      <section className="space-y-3">
        <p className="text-xs uppercase tracking-widest text-muted-foreground">
          LLM evaluation and regression testing
        </p>
        <h1 className="max-w-3xl text-4xl font-medium leading-tight md:text-5xl">
          Replace prompt intuition with evidence.
        </h1>
        <p className="max-w-2xl text-muted-foreground">
          EvalBench runs versioned automotive QA cases through reproducible scorers, preserves
          every result, and makes regressions inspectable.
        </p>
      </section>

      <LoadState state={state} loadingLabel="Loading recent evaluation runs">
        {({ runs }) =>
          runs.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border p-8">
              <h2 className="text-xl font-medium">No runs yet</h2>
              <p className="mt-2 text-muted-foreground">
                Run the offline benchmark from the CLI. Results will appear here.
              </p>
              <code className="mt-4 block font-mono text-sm">python -m evalbench.cli run</code>
            </div>
          ) : (
            <section className="space-y-4">
              <div>
                <p className="text-xs uppercase tracking-widest text-muted-foreground">
                  Experiment history
                </p>
                <h2 className="text-2xl font-medium">Recent evaluation runs</h2>
              </div>
              <div className="overflow-x-auto rounded-xl ring-1 ring-border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Run</TableHead>
                      <TableHead>Dataset</TableHead>
                      <TableHead>Split</TableHead>
                      <TableHead>Prompt</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Pass rate</TableHead>
                      <TableHead>Created</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {runs.map((run) => (
                      <TableRow key={run.id}>
                        <TableCell>
                          <Link to={`/runs/${run.id}`} className="font-mono">
                            {shortId(run.id)}
                          </Link>
                        </TableCell>
                        <TableCell>
                          {run.dataset_name} · {run.dataset_version}
                        </TableCell>
                        <TableCell>{titleCase(run.dataset_split)}</TableCell>
                        <TableCell>
                          {run.prompt_id} · {run.prompt_version}
                        </TableCell>
                        <TableCell>
                          <StatusBadge status={run.status} />
                        </TableCell>
                        <TableCell className="font-mono">{percent(run.pass_rate)}</TableCell>
                        <TableCell className="font-mono text-muted-foreground">
                          {timestamp(run.created_at)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </section>
          )
        }
      </LoadState>
    </div>
  )
}
