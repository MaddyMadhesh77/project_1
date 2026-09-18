import type { ModelStatus, TrustBreakdown } from '../../lib/api'
import { useModelStatus } from '../../lib/queries'

// Phase 2 rule-scorer keys (always available, cold start / below
// min_training_samples) and Phase 7 SHAP feature-contribution keys (once the
// RandomForest is trained and live) -- score_candidate returns one or the
// other, never a mix, but this map covers both so the bars read the same way
// regardless of which mechanism produced them.
const LABELS: Record<string, string> = {
  // Rule scorer (services/trust_engine.py::_score_rule)
  source: 'Source',
  semantic_similarity: 'Semantic similarity',
  novelty: 'Novelty',
  context: 'Context',
  contradiction: 'Contradiction',
  corroboration: 'Corroboration',
  // RF + SHAP (services/trust_engine.py::_shap_breakdown) -- same underlying
  // §6.4 features, real per-feature contributions toward P(safe) once live.
  similarity: 'Similarity to closest match',
  source_reliability: 'Source reliability',
  memory_age_days: "Contradicted memory's age",
  prior_trust_score: 'Prior trust score',
  corroboration_count: 'Corroboration count',
  conversation_recency: 'Conversation recency',
  has_match: 'Matched an existing memory',
  baseline: 'Model baseline',
}

interface TrustBreakdownBarsProps {
  breakdown: TrustBreakdown
  total: number
}

// Additive breakdown (DESIGN.md 6.5) rendered as a diverging bar per
// component -- positive contributions right of the zero baseline, negative
// ones to the left. Colors are the dataviz skill's validated diverging
// blue/red pair (references/palette.md), never the status palette (that's
// reserved for the trusted/low_trust/quarantined pill).
function scorerLabel(isShap: boolean, status: ModelStatus | undefined): { title: string; detail?: string } {
  if (!isShap) return { title: 'Rule engine' }
  // The badge reflects the model loaded NOW; a SHAP breakdown is only ever
  // produced by an RF that cleared the gate when this version was scored.
  if (status?.mode === 'rf_bootstrap') {
    return {
      title: 'RandomForest + SHAP · bootstrap model',
      detail: `Trained on ${status.n_samples} examples (${status.n_real_samples} real). Real rollback outcomes replace this once ${status.min_training_samples} exist.`,
    }
  }
  if (status?.mode === 'rf_real') {
    return {
      title: 'RandomForest + SHAP',
      detail: `Trained on ${status.n_samples} examples, ${status.n_real_samples} from real rollback outcomes.`,
    }
  }
  return { title: 'RandomForest + SHAP' }
}

export default function TrustBreakdownBars({ breakdown, total }: TrustBreakdownBarsProps) {
  const { data: status } = useModelStatus()
  const entries = Object.entries(breakdown)
  const maxAbs = Math.max(1, ...entries.map(([, value]) => Math.abs(value)))
  // SHAP breakdowns carry a "baseline" key; rule breakdowns never do. SHAP
  // bars sum to the model's own 100*P(safe), not to the stored score, which
  // blends that with the rule engine -- so both numbers are shown.
  const isShap = 'baseline' in breakdown
  const modelScore = Math.round(entries.reduce((sum, [, value]) => sum + value, 0) * 10) / 10
  const scorer = scorerLabel(isShap, status)

  return (
    <div className="space-y-2">
      <div className="mb-1">
        <span className="inline-block rounded-full bg-neutral-100 px-2 py-0.5 text-xs font-medium text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300">
          {scorer.title}
        </span>
        {scorer.detail && <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{scorer.detail}</p>}
      </div>
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
      {isShap && (
        <div className="flex items-center gap-3 border-t border-neutral-200 pt-2 text-sm dark:border-neutral-800">
          <span className="w-40 shrink-0 text-neutral-600 dark:text-neutral-400">Model score (sum of bars)</span>
          <div className="flex-1" />
          <span className="w-16 shrink-0 text-right tabular-nums text-neutral-700 dark:text-neutral-300">{modelScore}</span>
        </div>
      )}
      <div className="flex items-center gap-3 border-t border-neutral-200 pt-2 text-sm dark:border-neutral-800">
        <span className="w-40 shrink-0 font-semibold text-neutral-800 dark:text-neutral-100">
          {isShap ? 'Final score' : 'Total'}
        </span>
        <div className="flex-1" />
        <span className="w-16 shrink-0 text-right tabular-nums font-semibold text-neutral-900 dark:text-neutral-100">
          {total}
        </span>
      </div>
      {isShap && (
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          Final score blends the model score with the rule engine&rsquo;s
          {status ? ` (rule weight ${status.rf_blend_weight})` : ''}.
        </p>
      )}
    </div>
  )
}
