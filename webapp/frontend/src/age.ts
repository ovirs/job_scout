const AGE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['day', 24 * 60 * 60],
  ['hour', 60 * 60],
  ['minute', 60],
]
const relativeTime = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })

export function age(timestamp: string): string {
  const seconds = (Date.now() - Date.parse(timestamp)) / 1000
  for (const [unit, size] of AGE_UNITS) {
    if (seconds >= size) return relativeTime.format(-Math.floor(seconds / size), unit)
  }
  return 'just now'
}
