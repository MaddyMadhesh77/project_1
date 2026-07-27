import type { TrustBreakdown } from '../../lib/api'

const LABELS: Record<string, string> = {
  source: 'Source',
  semantic_similarity: 'Semantic similarity',
  novelty: 'Novelty',
  context: 'Context',
  contradiction: 'Contradiction',
  corroboration: 'Corroboration',
}

interface TrustBreakdownBarsProps {
  breakdown: TrustBreakdown
  total: number
}

// Additive rule-scorer breakdown (DESIGN.md 6.5) rendered as a diverging bar
// per component -- positive contributions right of the zero baseline, the
// contradiction penalty (if any) to the left. Colors are the dataviz skill's
// validated diverging blue/red pair (references/palette.md), never the
// status palette (that's reserved for the trusted/low_trust/quarantined pill).
export default function TrustBreakdownBars({ breakdown, total }: TrustBreakdownBarsProps) {
  const entries = Object.entries(breakdown)
  const maxAbs = Math.max(1, ...entries.map(([, value]) => Math.abs(value)))

  return (
    <div className="space-y-2">
      {entries.map(([key, value]) => {
        const pct = (Math.abs(value) / maxAbs) * 50
        const positive = value >= 0
        return (
          <div key={key} className="flex items-center gap-3 text-sm">
            <span className="w-40 shrink-0 text-neutral-600 dark:text-neutral-400">
              {LABELS[key] ?? key}
            </span>
            <div className="relative h-3.5 flex-1 rounded-full bg-neutral-100 dark:bg-neutral-800">
              <div className="absolute inset-y-0 left-1/2 w-px bg-neutral-300 dark:bg-neutral-600" />
              <div
                className={`absolute inset-y-0 rounded-full ${
                  positive ? 'bg-[#2a78d6] dark:bg-[#3987e5]' : 'bg-[#e34948] dark:bg-[#e66767]'
                }`}
                style={positive ? { left: '50%', width: `${pct}%` } : { right: '50%', width: `${pct}%` }}
              />
            </div>
            <span
              className={`w-16 shrink-0 text-right tabular-nums font-medium ${
                positive ? 'text-[#1c5cab] dark:text-[#6da7ec]' : 'text-[#d03b3b] dark:text-[#e66767]'
              }`}
            >
              {positive ? '+' : ''}
              {value}
            </span>
          </div>
        )
      })}
      <div className="flex items-center gap-3 border-t border-neutral-200 pt-2 text-sm dark:border-neutral-800">
        <span className="w-40 shrink-0 font-semibold text-neutral-800 dark:text-neutral-100">Total</span>
        <div className="flex-1" />
        <span className="w-16 shrink-0 text-right tabular-nums font-semibold text-neutral-900 dark:text-neutral-100">
          {total}
        </span>
      </div>
    </div>
  )
}
