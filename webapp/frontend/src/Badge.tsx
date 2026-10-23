import type { ReactNode } from 'react'

/**
 * What a badge says about its subject, which sets its colour: good news, something to watch,
 * bad news, the app's own marker (accent), or plain fact (neutral).
 */
export type Tone = 'neutral' | 'accent' | 'good' | 'warn' | 'bad'

/** A small tinted pill. With `href` it is a link; `dot` leads it with a dot of its colour, and
 * `busy` makes that dot pulse while something is under way. */
export function Badge({
  tone = 'neutral',
  dot = false,
  busy = false,
  href,
  children,
}: {
  tone?: Tone
  dot?: boolean
  busy?: boolean
  href?: string
  children: ReactNode
}) {
  const className = ['badge', tone, (dot || busy) && 'dot', busy && 'busy']
    .filter(Boolean)
    .join(' ')
  return href ? (
    <a className={className} href={href}>
      {children}
    </a>
  ) : (
    <span className={className}>
      {children}
    </span>
  )
}
