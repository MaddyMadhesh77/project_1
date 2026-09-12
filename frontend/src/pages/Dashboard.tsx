import { useState } from 'react'
import { Link } from 'react-router-dom'
import { SkeletonStatTiles } from '../components/Skeleton'
import StatTile from '../components/StatTile'
import { useAnalyticsSummary, useResetDemo, useRetrainModel } from '../lib/queries'

function DemoTools() {
  const retrain = useRetrainModel()
  const reset = useResetDemo()
  const [confirming, setConfirming] = useState(false)

  return (
    <section className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
      <h2 className="mb-1 text-sm font-semibold text-neutral-700 dark:text-neutral-200">Demo tools</h2>
      <p className="mb-3 text-xs text-neutral-500 dark:text-neutral-400">
        Manual triggers -- neither runs automatically (bugs.md #10/#11).
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={() => retrain.mutate()}
          disabled={retrain.isPending}
          className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
        >
          {retrain.isPending ? 'Retraining…' : 'Retrain trust model'}
        </button>

        {confirming ? (
          <span className="flex items-center gap-2 text-sm">
            Wipe all memories and reseed the demo chain?
            <button
              onClick={() => {
                reset.mutate()
                setConfirming(false)
              }}
              className="rounded-md bg-[#d03b3b] px-3 py-1.5 text-sm font-medium text-white hover:bg-[#b83232]"
            >
              Confirm reset
            </button>
            <button
              onClick={() => setConfirming(false)}
              className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm dark:border-neutral-700"
            >
              Cancel
            </button>
          </span>
        ) : (
          <button
            onClick={() => setConfirming(true)}
            disabled={reset.isPending}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm disabled:opacity-50 dark:border-neutral-700"
          >
            {reset.isPending ? 'Resetting…' : 'Reset to clean demo state'}
          </button>
        )}
      </div>

      {retrain.isError && <p className="mt-2 text-sm text-red-500">Retrain failed.</p>}
      {retrain.data && (
        <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-300">
          Trained on {retrain.data.n_samples} examples ({retrain.data.n_real_samples} real) -- accuracy{' '}
          {retrain.data.train_accuracy.toFixed(3)}.
        </p>
      )}

      {reset.isError && <p className="mt-2 text-sm text-red-500">Reset failed.</p>}
      {reset.data && (
        <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-300">
          Reset {reset.data.truncated_tables.length} tables and reseeded {reset.data.seeded_lines.length} memories.
        </p>
      )}
    </section>
  )
}

export default function Dashboard() {
  // Real aggregate counts from the backend (services/analytics.py), not
  // derived client-side from a memories page -- a client-side tally would
  // silently under-count once GET /memories is paginated (bugs.md #8).
  const { data: summary, isLoading, isError } = useAnalyticsSummary()

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-xl font-semibold text-neutral-800 dark:text-neutral-100">Dashboard</h1>
        <SkeletonStatTiles />
      </div>
    )
  }
  if (isError || !summary) return <p className="text-sm text-red-500">Failed to load summary.</p>

  const counts = summary.status_counts

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-neutral-800 dark:text-neutral-100">Dashboard</h1>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile label="Total memories" value={summary.total_memories} />
        <StatTile label="Trusted" value={counts.trusted ?? 0} tone="good" />
        <StatTile label="Low trust / review" value={counts.low_trust ?? 0} tone="warning" />
        <StatTile label="Quarantined" value={counts.quarantined ?? 0} tone="critical" />
      </div>

      <p className="text-sm text-neutral-500 dark:text-neutral-400">
        See{' '}
        <Link to="/admin/memories" className="underline">
          Memories
        </Link>{' '}
        for the full list, trust scores, and version history.
      </p>

      <DemoTools />
    </div>
  )
}
