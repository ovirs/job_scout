import type { EvidenceMatch } from './api/types.gen'

/** What a quote supports, which sets its colour: a Deal Breaker verdict or a flag. */
export type HighlightKind = 'violated' | 'unknown' | 'clear' | 'red' | 'green'

/** One quote of the Evaluation, at the position stored when it was checked. */
export type Highlight = {
  key: string // the same for every place one quote is shown
  kind: HighlightKind
  label: string // what the quote supports, shown on hover
  match: EvidenceMatch
}

// Where quotes overlap, the more serious one gives the colour
const PRECEDENCE: HighlightKind[] = ['violated', 'red', 'unknown', 'green', 'clear']

/**
 * A posting field's text with each quote highlighted at its stored position. Overlapping
 * quotes split the text into segments, each marked with every quote covering it.
 */
export function Highlighted({
  text,
  highlights,
  active,
}: {
  text: string
  highlights: Highlight[]
  active: string | null
}) {
  return segments(text, highlights).map(({ start, end, covering }) => {
    const part = text.slice(start, end)
    if (covering.length === 0) return part
    const kind = PRECEDENCE.find((kind) => covering.some((h) => h.kind === kind))
    const keys = covering.map((h) => h.key)
    return (
      <mark
        key={start}
        className={`${kind}${active !== null && keys.includes(active) ? ' active' : ''}`}
        data-quotes={keys.join(' ')}
        title={covering.map((h) => h.label).join('\n')}
      >
        {part}
      </mark>
    )
  })
}

function segments(text: string, highlights: Highlight[]) {
  const clamp = (at: number) => Math.min(Math.max(at, 0), text.length)
  const cuts = new Set([0, text.length])
  for (const { match } of highlights) {
    cuts.add(clamp(match.start))
    cuts.add(clamp(match.end))
  }
  const sorted = [...cuts].sort((a, b) => a - b)
  return sorted.slice(0, -1).map((start, index) => {
    const end = sorted[index + 1]
    const covering = highlights.filter(({ match }) => match.start < end && match.end > start)
    return { start, end, covering }
  })
}

/** The key of one passage among those a verdict or flag rests on. */
export function quoteKey(quoteOf: string, index: number): string {
  return `${quoteOf}-${index}`
}

/** Scroll to the first place a quote is highlighted. */
export function scrollToQuote(key: string) {
  document
    .querySelector(`mark[data-quotes~="${key}"]`)
    ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
