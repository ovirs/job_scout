// The toolbar's Markdown edits, as pure functions of the text and its selection.

export type Selection = { value: string; start: number; end: number }

/** Replace value[from, to) with insert, then select [select[0], select[1]) in the new text. */
export type Edit = { from: number; to: number; insert: string; select: [number, number] }

export type Format =
  | 'bold'
  | 'italic'
  | 'title'
  | 'heading'
  | 'subheading'
  | 'bullets'
  | 'numbers'
  | 'link'

export function format(kind: Format, selection: Selection): Edit {
  switch (kind) {
    case 'bold':
      return toggleEmphasis(selection, 2)
    case 'italic':
      return toggleEmphasis(selection, 1)
    case 'title':
      return toggleLines(selection, headingLines('# '))
    case 'heading':
      return toggleLines(selection, headingLines('## '))
    case 'subheading':
      return toggleLines(selection, headingLines('### '))
    case 'bullets':
      return toggleLines(selection, listLines(BULLET, () => '- '))
    case 'numbers':
      return toggleLines(selection, listLines(NUMBER, (n) => `${n}. `))
    case 'link':
      return link(selection)
  }
}

/**
 * Wrap the selection in ** (bold, size 2) or * (italic, size 1), or unwrap it when it already is.
 * The asterisks around the selection, or selected at its edges, say which it already is:
 * ** is bold, * italic, *** both.
 */
function toggleEmphasis({ value, start, end }: Selection, size: 1 | 2): Edit {
  // Leave out whitespace selected at the edges, as a double-click on a word often selects
  while (start < end && /\s/.test(value[start])) start++
  while (end > start && /\s/.test(value[end - 1])) end--
  // Asterisks selected with the text count as around it
  const selected = Math.min(
    asterisks(value, start, end, 1),
    asterisks(value, end, start, -1),
    Math.floor((end - start) / 2),
  )
  start += selected
  end -= selected

  const around = Math.min(asterisks(value, start, 0, -1), asterisks(value, end, value.length, 1))
  const applied = size === 2 ? around >= 2 : around === 1 || around >= 3
  if (applied) {
    return {
      from: start - size,
      to: end + size,
      insert: value.slice(start, end),
      select: [start - size, end - size],
    }
  }
  const marker = '*'.repeat(size)
  return {
    from: start,
    to: end,
    insert: marker + value.slice(start, end) + marker,
    select: [start + size, end + size],
  }
}

/** How many asterisks run from position `from` towards `limit`, one step at a time. */
function asterisks(value: string, from: number, limit: number, step: 1 | -1): number {
  let count = 0
  let i = step === 1 ? from : from - 1
  while ((step === 1 ? i < limit : i >= limit) && value[i] === '*') {
    count++
    i += step
  }
  return count
}

/** How a line command reads and rewrites one line. */
type LineRule = {
  has: (line: string) => boolean
  add: (line: string, n: number) => string
  remove: (line: string) => string
}

function headingLines(prefix: string): LineRule {
  const heading = /^#{1,6}\s+/
  return {
    has: (line) => line.startsWith(prefix),
    add: (line) => prefix + line.replace(heading, ''),
    remove: (line) => line.replace(heading, ''),
  }
}

const BULLET = /^(\s*)[-*+]\s+/
const NUMBER = /^(\s*)\d+[.)]\s+/
const ANY_ITEM = /^(\s*)(?:[-*+]|\d+[.)])\s+/

function listLines(marker: RegExp, make: (n: number) => string): LineRule {
  return {
    has: (line) => marker.test(line),
    add: (line, n) => {
      const indent = /^\s*/.exec(line)![0]
      return indent + make(n) + line.replace(ANY_ITEM, '').trimStart()
    },
    remove: (line) => line.replace(ANY_ITEM, '$1'),
  }
}

/**
 * Apply a line command to every line the selection touches, or remove it when every line
 * already has it. Blank lines are left alone unless there is nothing else.
 */
function toggleLines({ value, start, end }: Selection, rule: LineRule): Edit {
  // A selection that ends at the start of a line does not touch that line
  if (end > start && value[end - 1] === '\n') end--
  // lastIndexOf from -1 would still look at position 0
  const from = start === 0 ? 0 : value.lastIndexOf('\n', start - 1) + 1
  const lineEnd = value.indexOf('\n', end)
  const to = lineEnd === -1 ? value.length : lineEnd

  const lines = value.slice(from, to).split('\n')
  const written = lines.some((line) => line.trim() !== '')
  const targets = lines.map((line) => !written || line.trim() !== '')
  const remove = written && lines.every((line, i) => !targets[i] || rule.has(line))

  // Numbers count per indent: a nested list starts again at 1
  const counts: { indent: number; n: number }[] = []
  const insert = lines
    .map((line, i) => {
      if (!targets[i]) return line
      if (remove) return rule.remove(line)
      const indent = /^\s*/.exec(line)![0].length
      while (counts.length && counts[counts.length - 1].indent > indent) counts.pop()
      const level = counts[counts.length - 1]
      if (level?.indent === indent) level.n++
      else counts.push({ indent, n: 1 })
      return rule.add(line, counts[counts.length - 1].n)
    })
    .join('\n')

  const collapsed = start === end && lines.length === 1
  const select: [number, number] = collapsed
    ? [from + insert.length, from + insert.length]
    : [from, from + insert.length]
  return { from, to, insert, select }
}

/** Make the selection a link and select its address, or insert one and select its text. */
function link({ value, start, end }: Selection): Edit {
  const text = value.slice(start, end)
  const address = 'https://'
  if (text) {
    const at = start + text.length + 3
    return { from: start, to: end, insert: `[${text}](${address})`, select: [at, at + address.length] }
  }
  const placeholder = 'link text'
  return {
    from: start,
    to: end,
    insert: `[${placeholder}](${address})`,
    select: [start + 1, start + 1 + placeholder.length],
  }
}
