import { useState } from 'react'
import { Link } from 'react-router-dom'
import { MEMORY_STATUSES } from '../lib/api'
import { useMemories } from '../lib/queries'
import { statusBadgeClass, statusLabel } from '../lib/status'

export default function Memories() {
  const [status, setStatus] = useState('')
  const { data: memories, isLoading, isError } = useMemories(status || undefined)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-neutral-800 dark:text-neutral-100">Memories</h1>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-md border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
        >
          <option value="">All statuses</option>
          {MEMORY_STATUSES.map((s) => (
            <option key={s} value={s}>
              {statusLabel(s)}
            </option>
          ))}
        </select>
      </div>

      {isLoading && <p className="text-sm text-neutral-400">Loading…</p>}
      {isError && <p className="text-sm text-red-500">Failed to load memories.</p>}

      {memories && (
        <div className="overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
              <tr>
                <th className="px-4 py-2 font-medium">Text</th>
                <th className="px-4 py-2 font-medium">Trust</th>
                <th className="px-4 py-2 font-medium">Versions</th>
                <th className="px-4 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {memories.map((memory) => (
                <tr key={memory.memory_id} className="hover:bg-neutral-50 dark:hover:bg-neutral-900/50">
                  <td className="px-4 py-2">
                    <Link to={`/admin/memories/${memory.memory_id}`} className="hover:underline">
                      {memory.text ?? '(no active version)'}
                    </Link>
                  </td>
                  <td className="px-4 py-2 tabular-nums">{memory.trust_score?.toFixed(1) ?? '—'}</td>
                  <td className="px-4 py-2 tabular-nums">{memory.version_count}</td>
                  <td className="px-4 py-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusBadgeClass(memory.status)}`}
                    >
                      {statusLabel(memory.status)}
                    </span>
                  </td>
                </tr>
              ))}
              {memories.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-neutral-400">
                    No memories yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
