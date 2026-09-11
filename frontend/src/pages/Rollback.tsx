import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import StatTile from '../components/StatTile'
import type { RollbackNodeOutcome, RollbackOutcome } from '../lib/api'
import { useInjectPoison, useMemories, useTamperDb, useTriggerRollback } from '../lib/queries'

// Same fixed-role palette as lib/status.ts / GraphView -- kept reuses the
// "trusted" green, reverted the "low_trust" amber, removed the
// "quarantined" red, so the outcome badges read consistently with the rest
// of the dashboard's status vocabulary.
const OUTCOME_STYLES: Record<RollbackOutcome, string> = {
  kept: 'bg-[#0ca30c]/10 text-[#0ca30c] dark:bg-[#0ca30c]/15 dark:text-[#2ecc2e]',
  reverted: 'bg-[#fab219]/15 text-[#8a6110] dark:bg-[#fab219]/20 dark:text-[#fab219]',
  removed: 'bg-[#d03b3b]/10 text-[#d03b3b] dark:bg-[#d03b3b]/20 dark:text-[#e66767]',
}

const OUTCOME_LABELS: Record<RollbackOutcome, string> = {
  kept: 'Kept',
  reverted: 'Reverted',
  removed: 'Removed',
}

function useStagedReveal(count: number, active: boolean) {
  const [revealed, setRevealed] = useState(0)

  useEffect(() => {
    if (!active || count === 0) {
      setRevealed(0)
      return
    }
    setRevealed(0)
    let i = 0
    // `cancelled` (bugs.md #16), not just clearInterval in the cleanup: if a
    // second rollback is triggered while this effect's interval already has
    // a tick queued in the event loop, clearInterval alone can't stop a tick
    // that's already been scheduled before cleanup runs -- it would still
    // fire and setRevealed with this closure's stale `i`/`count`, bleeding
    // the previous run's progress into the new animation. Checking a flag
    // owned by this effect instance inside the callback closes that gap.
    let cancelled = false
    const id = setInterval(() => {
      if (cancelled) return
      i += 1
      setRevealed(i)
      if (i >= count) clearInterval(id)
    }, 450)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [count, active])

  return revealed
}

export default function Rollback() {
  // limit=200 (the backend's max page size, app/api/routes/memories.py) --
  // these selects need the full memory list, not the default paginated
  // page (bugs.md #8), and this app is demo-scale.
  const { data: memoriesPage } = useMemories(undefined, 200)
  const memories = memoriesPage?.items

  // -- Inject poison --
  const [poisonText, setPoisonText] = useState('preference: not Python')
  const [poisonTargetMemoryId, setPoisonTargetMemoryId] = useState('')
  const [poisonScore, setPoisonScore] = useState(95)
  const injectPoison = useInjectPoison()

  // -- Tamper DB --
  const [tamperVersionId, setTamperVersionId] = useState('')
  const tamperDb = useTamperDb()

  // -- Rollback / Recover --
  const [rollbackVersionId, setRollbackVersionId] = useState('')
  const triggerRollback = useTriggerRollback()
  const affected = triggerRollback.data?.affected ?? []
  const revealed = useStagedReveal(affected.length, triggerRollback.isSuccess)
  const animating = triggerRollback.isSuccess && revealed < affected.length

  const versionOptions = (memories ?? []).filter((m) => m.current_version_id)

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold text-neutral-800 dark:text-neutral-100">Attack simulator &amp; recovery</h1>
        <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
          Simulate an attack against the memory store, then use dependency-aware rollback to recover from it
          (DESIGN.md §6.10, §9 flows 2–3).
        </p>
      </div>

      <section className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
        <h2 className="mb-1 text-sm font-semibold text-neutral-700 dark:text-neutral-200">1. Inject poison</h2>
        <p className="mb-3 text-xs text-neutral-500 dark:text-neutral-400">
          Force-writes a memory version bypassing the trust engine entirely -- it lands with{' '}
          <code className="rounded bg-neutral-100 px-1 dark:bg-neutral-800">decision=store</code> at whatever score you
          set below, exactly as if it had slipped past the front-line gate undetected.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block text-neutral-600 dark:text-neutral-400">Stored text (predicate: value)</span>
            <input
              value={poisonText}
              onChange={(e) => setPoisonText(e.target.value)}
              className="w-full rounded-md border border-neutral-300 bg-white px-2 py-1 dark:border-neutral-700 dark:bg-neutral-900"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-neutral-600 dark:text-neutral-400">Target memory (optional -- versions an existing one)</span>
            <select
              value={poisonTargetMemoryId}
              onChange={(e) => setPoisonTargetMemoryId(e.target.value)}
              className="w-full rounded-md border border-neutral-300 bg-white px-2 py-1 dark:border-neutral-700 dark:bg-neutral-900"
            >
              <option value="">New memory</option>
              {(memories ?? []).map((m) => (
                <option key={m.memory_id} value={m.memory_id}>
                  {m.text ?? m.memory_id}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-neutral-600 dark:text-neutral-400">Forced trust score</span>
            <input
              type="number"
              min={0}
              max={100}
              value={poisonScore}
              onChange={(e) => setPoisonScore(Number(e.target.value))}
              className="w-full rounded-md border border-neutral-300 bg-white px-2 py-1 dark:border-neutral-700 dark:bg-neutral-900"
            />
          </label>
        </div>
        <button
          onClick={() =>
            injectPoison.mutate({
              text: poisonText,
              memory_id: poisonTargetMemoryId || undefined,
              forced_trust_score: poisonScore,
            })
          }
          disabled={injectPoison.isPending || !poisonText.trim()}
          className="mt-3 rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
        >
          {injectPoison.isPending ? 'Injecting…' : 'Inject poison'}
        </button>
        {injectPoison.isError && <p className="mt-2 text-sm text-red-500">Injection failed.</p>}
        {injectPoison.data && (
          <p className="mt-3 text-sm text-neutral-600 dark:text-neutral-300">
            Stored as{' '}
            <Link to={`/admin/memories/${injectPoison.data.memory_id}`} className="font-medium hover:underline">
              {injectPoison.data.text}
            </Link>{' '}
            at trust {injectPoison.data.trust_score} ({injectPoison.data.decision}) -- looks completely legitimate in
            the dashboard.
          </p>
        )}
      </section>

      <section className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
        <h2 className="mb-1 text-sm font-semibold text-neutral-700 dark:text-neutral-200">2. Tamper with the database</h2>
        <p className="mb-3 text-xs text-neutral-500 dark:text-neutral-400">
          Directly mutates a row's text via raw SQL, bypassing the API entirely -- simulates a rogue DBA. Check{' '}
          <Link to="/admin/integrity" className="underline">
            Integrity
          </Link>{' '}
          afterward to see it caught.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="mb-1 block text-neutral-600 dark:text-neutral-400">Target memory</span>
            <select
              value={tamperVersionId}
              onChange={(e) => setTamperVersionId(e.target.value)}
              className="w-64 rounded-md border border-neutral-300 bg-white px-2 py-1 dark:border-neutral-700 dark:bg-neutral-900"
            >
              <option value="">Select a memory…</option>
              {versionOptions.map((m) => (
                <option key={m.memory_id} value={m.current_version_id!}>
                  {m.text}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={() => tamperVersionId && tamperDb.mutate({ version_id: tamperVersionId })}
            disabled={tamperDb.isPending || !tamperVersionId}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
          >
            {tamperDb.isPending ? 'Tampering…' : 'Tamper DB'}
          </button>
        </div>
        {tamperDb.isError && <p className="mt-2 text-sm text-red-500">Tamper request failed.</p>}
        {tamperDb.data && (
          <p className="mt-3 text-sm text-neutral-600 dark:text-neutral-300">
            Row mutated in place: <span className="font-mono text-xs">{tamperDb.data.new_text}</span>
          </p>
        )}
      </section>

      <section className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
        <h2 className="mb-1 text-sm font-semibold text-neutral-700 dark:text-neutral-200">3. Rollback / recover</h2>
        <p className="mb-3 text-xs text-neutral-500 dark:text-neutral-400">
          Mark a memory poisoned to walk its dependency graph and recover every descendant (DESIGN.md §6.10): still
          independently corroborated → kept; solely dependent with a prior version → reverted; solely dependent with
          none → removed.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="mb-1 block text-neutral-600 dark:text-neutral-400">Memory to mark poisoned</span>
            <select
              value={rollbackVersionId}
              onChange={(e) => setRollbackVersionId(e.target.value)}
              className="w-64 rounded-md border border-neutral-300 bg-white px-2 py-1 dark:border-neutral-700 dark:bg-neutral-900"
            >
              <option value="">Select a memory…</option>
              {versionOptions.map((m) => (
                <option key={m.memory_id} value={m.current_version_id!}>
                  {m.text}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={() => rollbackVersionId && triggerRollback.mutate({ versionId: rollbackVersionId })}
            disabled={triggerRollback.isPending || animating || !rollbackVersionId}
            className="rounded-md bg-[#d03b3b] px-3 py-1.5 text-sm font-medium text-white hover:bg-[#b83232] disabled:opacity-50"
          >
            {triggerRollback.isPending || animating ? 'Rolling back…' : 'Mark poisoned & recover'}
          </button>
        </div>
        {triggerRollback.isError && <p className="mt-2 text-sm text-red-500">Rollback failed.</p>}

        {triggerRollback.isSuccess && (
          <div className="mt-4 space-y-3">
            <div className="grid gap-3 sm:grid-cols-3">
              <StatTile label="Descendants found" value={Math.max(0, affected.length - 1)} />
              <StatTile
                label="Progress"
                value={animating ? `${revealed}/${affected.length}` : 'Done'}
                tone={animating ? 'warning' : 'good'}
              />
              <StatTile label="New Merkle root" value={`${triggerRollback.data.merkle_root.slice(0, 10)}…`} />
            </div>

            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              {animating
                ? revealed === 0
                  ? 'Finding descendants…'
                  : 'Restoring previous versions…'
                : 'Done -- Merkle root recomputed.'}
            </p>

            <div className="overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800">
              <table className="w-full text-left text-sm">
                <thead className="bg-neutral-50 text-xs uppercase text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
                  <tr>
                    <th className="px-4 py-2 font-medium">Memory</th>
                    <th className="px-4 py-2 font-medium">Outcome</th>
                    <th className="px-4 py-2 font-medium">New trust</th>
                    <th className="px-4 py-2 font-medium">Reason</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                  {affected.slice(0, revealed).map((node: RollbackNodeOutcome, i) => (
                    <tr key={node.version_id} className={i === 0 ? 'bg-neutral-50 dark:bg-neutral-900/50' : ''}>
                      <td className="px-4 py-2">
                        <Link to={`/admin/memories/${node.memory_id}`} className="hover:underline">
                          {node.text}
                        </Link>
                        {i === 0 && (
                          <span className="ml-2 text-xs text-neutral-400" title="the version marked poisoned">
                            (root)
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2">
                        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${OUTCOME_STYLES[node.outcome]}`}>
                          {OUTCOME_LABELS[node.outcome]}
                        </span>
                      </td>
                      <td className="px-4 py-2 tabular-nums">{node.trust_score.toFixed(1)}</td>
                      <td className="px-4 py-2 text-neutral-500 dark:text-neutral-400">{node.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
