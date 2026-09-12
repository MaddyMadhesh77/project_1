import { useState } from 'react'
import { Link } from 'react-router-dom'
import { SkeletonTable } from '../components/Skeleton'
import { statusBadgeClass, statusLabel } from '../lib/status'
import { useLogs } from '../lib/queries'

const PAGE_SIZE = 25

// trust_events.decision (Phase 2/7, DESIGN.md 6.5): store | review | reject --
// the actual trust-engine outcome, reused here via the same status palette a
// memory's status pill uses. Colored by decision rather than event_type: a
// "rolled_back" event's own decision can itself be store/review/reject
// (kept/reverted re-score vs. removed), so event_type alone doesn't carry
// enough signal to color correctly.
const DECISION_STATUS: Record<string, string> = {
  store: 'trusted',
  review: 'low_trust',
  reject: 'quarantined',
}

export default function Logs() {
  const [page, setPage] = useState(0)
  const { data, isLoading, isError, isPlaceholderData } = useLogs(PAGE_SIZE, page * PAGE_SIZE)

  const total = data?.total ?? 0
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-neutral-800 dark:text-neutral-100">Logs</h1>
          <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
            Raw <code className="rounded bg-neutral-100 px-1 dark:bg-neutral-800">trust_events</code> feed, newest first.
          </p>
        </div>
        {total > 0 && (
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            {page * PAGE_SIZE + 1}-{Math.min(total, page * PAGE_SIZE + PAGE_SIZE)} of {total}
          </p>
        )}
      </div>

      {isLoading && <SkeletonTable rows={8} cols={5} />}
      {isError && <p className="text-sm text-red-500">Failed to load logs.</p>}

      {data && (
        <div
          className={`overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800 ${
            isPlaceholderData ? 'opacity-60' : ''
          }`}
        >
          <table className="w-full text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
              <tr>
                <th className="px-4 py-2 font-medium">When</th>
                <th className="px-4 py-2 font-medium">Event</th>
                <th className="px-4 py-2 font-medium">Memory</th>
                <th className="px-4 py-2 font-medium">Decision</th>
                <th className="px-4 py-2 font-medium">Trust</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {data.items.map((entry) => (
                <tr key={entry.event_id} className="hover:bg-neutral-50 dark:hover:bg-neutral-900/50">
                  <td className="whitespace-nowrap px-4 py-2 text-neutral-500 dark:text-neutral-400">
                    {new Date(entry.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2 text-neutral-600 dark:text-neutral-400">{statusLabel(entry.event_type)}</td>
                  <td className="px-4 py-2">
                    <Link to={`/admin/memories/${entry.memory_id}`} className="hover:underline">
                      {entry.text}
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusBadgeClass(
                        DECISION_STATUS[entry.decision] ?? '',
                      )}`}
                    >
                      {entry.decision}
                    </span>
                  </td>
                  <td className="px-4 py-2 tabular-nums">{entry.trust_score?.toFixed(1) ?? '—'}</td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-neutral-400">
                    No trust events yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="rounded-md border border-neutral-300 px-3 py-1 text-sm disabled:opacity-40 dark:border-neutral-700"
          >
            Previous
          </button>
          <button
            onClick={() => setPage((p) => Math.min(lastPage, p + 1))}
            disabled={page >= lastPage}
            className="rounded-md border border-neutral-300 px-3 py-1 text-sm disabled:opacity-40 dark:border-neutral-700"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
