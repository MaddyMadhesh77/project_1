// Status-role text colors from the dataviz skill's validated palette
// (references/palette.md) -- reserved for state, never reused as a series color.
const TONE_STYLES = {
  good: 'text-[#0ca30c] dark:text-[#0ca30c]',
  warning: 'text-[#8a6110] dark:text-[#fab219]',
  critical: 'text-[#d03b3b] dark:text-[#e66767]',
  neutral: 'text-neutral-900 dark:text-neutral-100',
} as const

interface StatTileProps {
  label: string
  value: string | number
  tone?: keyof typeof TONE_STYLES
  hint?: string
}

export default function StatTile({ label, value, tone = 'neutral', hint }: StatTileProps) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
      <p className="text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </p>
      <p className={`mt-1 text-3xl font-semibold tabular-nums ${TONE_STYLES[tone]}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-neutral-400 dark:text-neutral-500">{hint}</p>}
    </div>
  )
}
