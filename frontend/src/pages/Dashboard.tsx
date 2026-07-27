import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import StatTile from '../components/StatTile'
import { useMemories } from '../lib/queries'

const STATUS_BUCKETS = ['trusted', 'low_trust', 'quarantined', 'rolled_back'] as const

export default function Dashboard() {
  const { data: memories, isLoading, isError } = useMemories()

  const counts = useMemo(() => {
    const base: Record<(typeof STATUS_BUCKETS)[number], number> = {
      trusted: 0,
      low_trust: 0,
      quarantined: 0,
      rolled_back: 0,
    }
    for (const memory of memories ?? []) {
      if ((STATUS_BUCKETS as readonly string[]).includes(memory.status)) {
        base[memory.status as (typeof STATUS_BUCKETS)[number]] += 1
      }
    }
    return base
  }, [memories])

  if (isLoading) return <p className="text-sm text-neutral-400">Loading…</p>
  if (isError) return <p className="text-sm text-red-500">Failed to load memories.</p>

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-neutral-800 dark:text-neutral-100">Dashboard</h1>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile label="Total memories" value={memories?.length ?? 0} />
        <StatTile label="Trusted" value={counts.trusted} tone="good" />
        <StatTile label="Low trust / review" value={counts.low_trust} tone="warning" />
        <StatTile label="Quarantined" value={counts.quarantined} tone="critical" />
      </div>

      <p className="text-sm text-neutral-500 dark:text-neutral-400">
        See{' '}
        <Link to="/admin/memories" className="underline">
          Memories
        </Link>{' '}
        for the full list, trust scores, and version history.
      </p>
    </div>
  )
}
