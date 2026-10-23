import type { ReactNode } from 'react'

/** A placeholder while data loads: skeleton lines, announced as `label`. */
export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <span className="visually-hidden">{label}</span>
      <span className="skeleton" aria-hidden="true" />
      <span className="skeleton" aria-hidden="true" />
      <span className="skeleton short" aria-hidden="true" />
    </div>
  )
}

/** A longer piece of work under way, such as an LLM step: what it is, over a moving bar. */
export function Working({ children }: { children: ReactNode }) {
  return (
    <p className="working" role="status">
      {children}
    </p>
  )
}
