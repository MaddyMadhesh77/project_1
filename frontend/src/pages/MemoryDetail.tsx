import { Link, useParams } from 'react-router-dom'
import TrustBreakdownBars from '../components/TrustBreakdownBars'
import { useMemory, useMemoryHistory } from '../lib/queries'
import { statusBadgeClass, statusLabel } from '../lib/status'

export default function MemoryDetail() {
  const { memoryId } = useParams<{ memoryId: string }>()
  const { data: memory, isLoading, isError } = useMemory(memoryId)
  const { data: history } = useMemoryHistory(memoryId)

  if (isLoading) return <p className="text-sm text-neutral-400">Loading…</p>
  if (isError || !memory) return <p className="text-sm text-red-500">Memory not found.</p>

  return (
    <div className="space-y-6">
      <div>
        <Link to="/admin/memories" className="text-sm text-neutral-500 hover:underline dark:text-neutral-400">
          &larr; Back to memories
        </Link>
        <div className="mt-1 flex items-center gap-3">
          <h1 className="text-xl font-semibold text-neutral-800 dark:text-neutral-100">{memory.text}</h1>
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusBadgeClass(memory.status)}`}>
            {statusLabel(memory.status)}
          </span>
        </div>
      </div>

      <section className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
        <h2 className="mb-3 text-sm font-semibold text-neutral-700 dark:text-neutral-200">
          Trust breakdown ({memory.trust_score?.toFixed(1) ?? '—'})
        </h2>
        {memory.trust_breakdown ? (
          <TrustBreakdownBars breakdown={memory.trust_breakdown} total={memory.trust_score ?? 0} />
        ) : (
          <p className="text-sm text-neutral-400">No trust breakdown available.</p>
        )}
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
          <h2 className="mb-2 text-sm font-semibold text-neutral-700 dark:text-neutral-200">Content hash</h2>
          <p className="break-all font-mono text-xs text-neutral-500 dark:text-neutral-400">
            {memory.content_hash ?? '—'}
          </p>
        </div>
        <div className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
          <h2 className="mb-2 text-sm font-semibold text-neutral-700 dark:text-neutral-200">Dependencies</h2>
          <p className="text-sm text-neutral-400">None yet -- lands in Phase 4 (dependency graph).</p>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold text-neutral-700 dark:text-neutral-200">Version history</h2>
        <div className="overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
              <tr>
                <th className="px-4 py-2 font-medium">#</th>
                <th className="px-4 py-2 font-medium">Text</th>
                <th className="px-4 py-2 font-medium">Trust</th>
                <th className="px-4 py-2 font-medium">Decision</th>
                <th className="px-4 py-2 font-medium">Active</th>
                <th className="px-4 py-2 font-medium">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {(history ?? []).map((version) => (
                <tr
                  key={version.version_id}
                  className={version.is_active ? 'bg-neutral-50 dark:bg-neutral-900/50' : ''}
                >
                  <td className="px-4 py-2 tabular-nums">{version.version_number}</td>
                  <td className="px-4 py-2">{version.text}</td>
                  <td className="px-4 py-2 tabular-nums">{version.trust_score.toFixed(1)}</td>
                  <td className="px-4 py-2">{version.decision}</td>
                  <td className="px-4 py-2">{version.is_active ? 'current' : ''}</td>
                  <td className="px-4 py-2 text-neutral-500 dark:text-neutral-400">
                    {new Date(version.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
              {(!history || history.length === 0) && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-neutral-400">
                    No versions yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
