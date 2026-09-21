// Shared status -> badge styling, reused by Memories.tsx and MemoryDetail.tsx.
// Colors are the dataviz skill's fixed status palette (references/palette.md):
// good/warning/critical, applied as tinted-background + full-strength text so
// the pill's own text label is always the primary carrier of meaning.
const STATUS_STYLES: Record<string, string> = {
  trusted: 'bg-[#0ca30c]/10 text-[#0ca30c] dark:bg-[#0ca30c]/15 dark:text-[#2ecc2e]',
  low_trust: 'bg-[#fab219]/15 text-[#8a6110] dark:bg-[#fab219]/20 dark:text-[#fab219]',
  quarantined: 'bg-[#d03b3b]/10 text-[#d03b3b] dark:bg-[#d03b3b]/20 dark:text-[#e66767]',
  rolled_back: 'bg-[#ec835a]/15 text-[#a85226] dark:bg-[#ec835a]/20 dark:text-[#ec835a]',
}

const FALLBACK_STYLE = 'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300'

export function statusBadgeClass(status: string): string {
  return STATUS_STYLES[status] ?? FALLBACK_STYLE
}

export function statusLabel(status: string): string {
  return status.replaceAll('_', ' ')
}
