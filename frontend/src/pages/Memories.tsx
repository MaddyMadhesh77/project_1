import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { SkeletonTable } from '../components/Skeleton'
import { MEMORY_STATUSES } from '../lib/api'
import { useMemories, useSearch } from '../lib/queries'
import { statusBadgeClass, statusLabel } from '../lib/status'

function SemanticSearch() {
  const [input, setInput] = useState('')
  const [query, setQuery] = useState('')
  const { data: hits, isLoading, isError, isFetched } = useSearch(query)

  const submit = () => setQuery(input.trim())

  return (
    <section className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
      <h2 className="mb-1 text-sm font-semibold text-neutral-700 dark:text-neutral-200">Semantic search</h2>
      <p className="mb-3 text-xs text-neutral-500 dark:text-neutral-400">
        Hits the same hybrid retrieval (pgvector + keyword) the chat pipeline uses internally (DESIGN.md §9 flow 5).
      </p>
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          placeholder="e.g. backend frameworks"
          className="flex-1 rounded-md border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
        />
        <button
          onClick={submit}
          disabled={!input.trim()}
          className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
        >
          Search
        </button>
      </div>

      {isLoading && <p className="mt-3 text-sm text-neutral-400">Searching…</p>}
      {isError && <p className="mt-3 text-sm text-red-500">Search failed.</p>}
      {isFetched && hits && (
        <ul className="mt-3 space-y-2">
          {hits.map((hit) => (
            <li key={hit.version_id} className="flex items-center justify-between text-sm">
              <Link to={`/admin/memories/${hit.memory_id}`} className="hover:underline">
                {hit.text}
              </Link>
              <span className="ml-3 shrink-0 tabular-nums text-neutral-500 dark:text-neutral-400">
                similarity {hit.similarity.toFixed(2)}
              </span>
            </li>
          ))}
          {hits.length === 0 && <li className="text-neutral-400">No matches.</li>}
        </ul>
      )}
    </section>
  )
}

const PAGE_SIZE = 25

export default function Memories() {
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(0)
  const { data, isLoading, isError, isPlaceholderData } = useMemories(status || undefined, PAGE_SIZE, page * PAGE_SIZE)

  const total = data?.total ?? 0
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1)

  // If the data shrank under us (e.g. /admin/reset), the current page can sit
  // past the end -- and the pager is hidden once total <= PAGE_SIZE, so there
  // would be no way back. Snap to the last real page.
  useEffect(() => {
    if (data && !isPlaceholderData && page > lastPage) setPage(lastPage)
  }, [data, isPlaceholderData, page, lastPage])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-neutral-800 dark:text-neutral-100">Memories</h1>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value)
            setPage(0)
          }}
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

      <SemanticSearch />

      {isLoading && <SkeletonTable rows={6} cols={4} />}
      {isError && <p className="text-sm text-red-500">Failed to load memories.</p>}

      {data && (
        <div
          className={`overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800 ${
            isPlaceholderData ? 'opacity-60' : ''
          }`}
        >
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
              {data.items.map((memory) => (
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
              {data.items.length === 0 && (
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

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            {page * PAGE_SIZE + 1}-{Math.min(total, page * PAGE_SIZE + PAGE_SIZE)} of {total}
          </p>
          <div className="flex gap-2">
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
        </div>
      )}
    </div>
  )
}
