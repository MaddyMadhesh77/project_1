import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { SkeletonBlock, SkeletonStatTiles } from '../components/Skeleton'
import StatTile from '../components/StatTile'
import type { TrendPoint } from '../lib/api'
import { useAnalyticsSummary } from '../lib/queries'

// Fixed status-role hex (dataviz skill's status palette, references/palette.md)
// -- same mode-invariant values GraphView/status.ts already use, since these
// four series ARE the store/review/reject decision + rollback-event states,
// not arbitrary categorical data (never reuse status color for a plain 4th
// series, but this genuinely is state).
const SERIES = [
  { key: 'store', label: 'Stored', color: '#0ca30c' },
  { key: 'review', label: 'Review', color: '#fab219' },
  { key: 'reject', label: 'Rejected', color: '#d03b3b' },
  { key: 'rollbacks', label: 'Rollbacks', color: '#ec835a' },
] as const

// Chart chrome (grid/axis/ink) DOES need light/dark values -- unlike the
// status colors above, these steps differ per DESIGN.md's dataviz palette
// (references/palette.md "Chart chrome & ink"), and recharts' SVG elements
// take real color props rather than Tailwind dark: classes.
function usePrefersDark(): boolean {
  const [dark, setDark] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches,
  )
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => setDark(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  return dark
}

function formatDay(iso: string): string {
  const d = new Date(`${iso}T00:00:00`)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: readonly { dataKey?: string | number; color?: string; value?: number | string }[]; label?: string }) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div className="rounded-md border border-neutral-200 bg-white px-3 py-2 text-xs shadow-sm dark:border-neutral-700 dark:bg-neutral-900">
      <p className="mb-1 font-medium text-neutral-500 dark:text-neutral-400">{label ? formatDay(label) : ''}</p>
      <div className="space-y-1">
        {payload.map((entry) => {
          const series = SERIES.find((s) => s.key === entry.dataKey)
          return (
            <div key={String(entry.dataKey)} className="flex items-center gap-2">
              <span className="inline-block h-0.5 w-3 shrink-0" style={{ backgroundColor: entry.color }} />
              <span className="text-neutral-500 dark:text-neutral-400">{series?.label ?? String(entry.dataKey)}</span>
              <span className="ml-auto pl-3 font-semibold tabular-nums text-neutral-900 dark:text-neutral-100">
                {entry.value}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function TrendChart({ trend }: { trend: TrendPoint[] }) {
  const dark = usePrefersDark()
  const gridColor = dark ? '#2c2c2a' : '#e1e0d9'
  const axisColor = dark ? '#383835' : '#c3c2b7'
  const tickColor = '#898781'

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1">
        {SERIES.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5 text-xs text-neutral-600 dark:text-neutral-400">
            <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={trend} barCategoryGap="20%" barGap={2} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={gridColor} />
          <XAxis
            dataKey="date"
            tickFormatter={formatDay}
            tick={{ fill: tickColor, fontSize: 11 }}
            axisLine={{ stroke: axisColor }}
            tickLine={false}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fill: tickColor, fontSize: 11 }}
            axisLine={{ stroke: axisColor }}
            tickLine={false}
            width={32}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: dark ? '#ffffff0d' : '#0000000d' }} />
          {SERIES.map((s) => (
            <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color} radius={[4, 4, 0, 0]} maxBarSize={20} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function Analytics() {
  const { data, isLoading, isError } = useAnalyticsSummary()

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-xl font-semibold text-neutral-800 dark:text-neutral-100">Analytics</h1>
        <SkeletonStatTiles />
        <SkeletonBlock className="h-72" />
      </div>
    )
  }
  if (isError || !data) return <p className="text-sm text-red-500">Failed to load analytics.</p>

  const trustedPct = data.total_memories > 0 ? Math.round(((data.status_counts.trusted ?? 0) / data.total_memories) * 100) : 0

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-neutral-800 dark:text-neutral-100">Analytics</h1>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile label="Total memories" value={data.total_memories} />
        <StatTile label="Total versions" value={data.total_versions} />
        <StatTile label="Trusted" value={`${trustedPct}%`} tone="good" />
        <StatTile label="Rollback events" value={data.rollback_count} tone={data.rollback_count > 0 ? 'warning' : 'neutral'} />
      </div>

      <section className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
        <h2 className="mb-1 text-sm font-semibold text-neutral-700 dark:text-neutral-200">
          Trust decisions &amp; rollbacks over time
        </h2>
        <p className="mb-4 text-xs text-neutral-500 dark:text-neutral-400">
          One bar per day per outcome -- versions written with each decision, plus rollback events triggered that day.
        </p>
        {data.trend.length === 0 ? (
          <p className="py-8 text-center text-sm text-neutral-400">No activity yet -- talk to the chat to see a trend.</p>
        ) : (
          <TrendChart trend={data.trend} />
        )}
      </section>

      {data.trend.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold text-neutral-700 dark:text-neutral-200">Daily counts (table view)</h2>
          <div className="overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800">
            <table className="w-full text-left text-sm">
              <thead className="bg-neutral-50 text-xs uppercase text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
                <tr>
                  <th className="px-4 py-2 font-medium">Date</th>
                  {SERIES.map((s) => (
                    <th key={s.key} className="px-4 py-2 font-medium">
                      {s.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                {data.trend.map((point) => (
                  <tr key={point.date}>
                    <td className="px-4 py-2">{formatDay(point.date)}</td>
                    {SERIES.map((s) => (
                      <td key={s.key} className="px-4 py-2 tabular-nums">
                        {point[s.key]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}
