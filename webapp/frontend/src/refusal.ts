/** The detail the API gives for a refused request, if it gives one. */
export function refusal(error: unknown): string | null {
  const detail = (error as { detail?: unknown } | null)?.detail
  return typeof detail === 'string' ? detail : null
}
