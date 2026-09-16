import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { SkeletonTable } from '../components/Skeleton'
import StatTile from '../components/StatTile'
import { useIntegrityHistory, useVerifyIntegrity } from '../lib/queries'

export default function IntegrityCheck() {
  const { data: history, isLoading, isError } = useIntegrityHistory()
  const verify = useVerifyIntegrity()
  const queryClient = useQueryClient()

  const latest = history?.[0]
  const result = verify.data

  const runVerify = async () => {
    await verify.refetch()
    queryClient.invalidateQueries({ queryKey: ['integrity-history'] })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-neutral-800 dark:text-neutral-100">Integrity check</h1>
        <button
          onClick={runVerify}
          disabled={verify.isFetching}
          className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
        >
          {verify.isFetching ? 'Verifying…' : 'Verify Integrity'}
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile
          label="Latest stored root"
          value={latest ? `${latest.root_hash.slice(0, 10)}…` : '—'}
          hint={latest ? `${latest.leaf_count} active leaves` : 'No writes yet'}
        />
        <StatTile
          label="Root snapshots"
          value={history?.length ?? 0}
          hint="GET /integrity/history"
        />
        {result && (
          <StatTile
            label="Last verify result"
            value={result.tampered ? 'Tampered' : 'Verified'}
            tone={result.tampered ? 'critical' : 'good'}
          />
        )}
      </div>

      {verify.isError && <p className="text-sm text-red-500">Verify request failed.</p>}

      {result && (
        <section
          className={`rounded-lg border p-4 ${
            result.tampered
              ? 'border-[#d03b3b]/40 bg-[#d03b3b]/5 dark:border-[#d03b3b]/40 dark:bg-[#d03b3b]/10'
              : 'border-[#0ca30c]/40 bg-[#0ca30c]/5 dark:border-[#0ca30c]/40 dark:bg-[#0ca30c]/10'
          }`}
        >
          <h2 className="text-sm font-semibold text-neutral-800 dark:text-neutral-100">
            {result.tampered ? 'Database Tampered' : 'Integrity verified'}
          </h2>
          <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-300">
            {result.tampered
              ? 'Recomputed hashes do not match the stored record. See affected versions below.'
              : `Every stored version matches its recorded content hash, and the Merkle root over ${result.leaf_count} active versions matches.`}
          </p>

          {result.row_mismatches.length > 0 && (
            <div className="mt-3">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                Row-level tamper (content_hash mismatch)
              </h3>
              <ul className="space-y-1">
                {result.row_mismatches.map((m) => (
                  <li key={m.version_id} className="text-sm">
                    <Link to={`/admin/memories/${m.memory_id}`} className="font-mono text-xs hover:underline">
                      version {m.version_id}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {result.orphaned_version_ids.length > 0 && (
            <div className="mt-3">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                Missing provenance (cannot be hash-verified)
              </h3>
              <ul className="space-y-1">
                {result.orphaned_version_ids.map((id) => (
                  <li key={id} className="font-mono text-xs">
                    version {id}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {result.root_mismatch && (
            <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
              <div>
                <p className="font-semibold text-neutral-600 dark:text-neutral-300">Expected root</p>
                <p className="break-all font-mono text-neutral-500 dark:text-neutral-400">
                  {result.expected_root ?? '—'}
                </p>
              </div>
              <div>
                <p className="font-semibold text-neutral-600 dark:text-neutral-300">Actual (recomputed) root</p>
                <p className="break-all font-mono text-neutral-500 dark:text-neutral-400">{result.actual_root}</p>
              </div>
            </div>
          )}
        </section>
      )}

      <section>
        <h2 className="mb-3 text-sm font-semibold text-neutral-700 dark:text-neutral-200">Root history</h2>
        {isLoading && <SkeletonTable rows={4} cols={3} />}
        {isError && <p className="text-sm text-red-500">Failed to load root history.</p>}
        {history && (
          <div className="overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800">
            <table className="w-full text-left text-sm">
              <thead className="bg-neutral-50 text-xs uppercase text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
                <tr>
                  <th className="px-4 py-2 font-medium">Root hash</th>
                  <th className="px-4 py-2 font-medium">Leaves</th>
                  <th className="px-4 py-2 font-medium">Computed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                {history.map((snapshot) => (
                  <tr key={snapshot.root_id}>
                    <td className="px-4 py-2 font-mono text-xs">{snapshot.root_hash.slice(0, 20)}…</td>
                    <td className="px-4 py-2 tabular-nums">{snapshot.leaf_count}</td>
                    <td className="px-4 py-2 text-neutral-500 dark:text-neutral-400">
                      {new Date(snapshot.computed_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
                {history.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-4 py-6 text-center text-neutral-400">
                      No root snapshots yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
