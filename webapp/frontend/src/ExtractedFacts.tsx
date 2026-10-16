import type { ExtractedFields, SalaryRange, Technology } from './api/types.gen'

const EMPLOYMENT_TYPES: Record<NonNullable<ExtractedFields['employment_type']>, string> = {
  full_time: 'Full-time',
  part_time: 'Part-time',
  contract: 'Contract',
  internship: 'Internship',
  temporary: 'Temporary',
}

export const WORKPLACE_TYPES: Record<NonNullable<ExtractedFields['workplace_type']>, string> = {
  remote: 'Remote',
  hybrid: 'Hybrid',
  onsite: 'On-site',
}

const NOT_STATED = <span className="missing">Not stated</span>

/**
 * The facts the LLM found in a posting, exactly as found: what the posting does not state
 * shows as not stated. The workplace type is left to the envelope, where the user corrects it.
 */
export function ExtractedFacts({ facts }: { facts: ExtractedFields }) {
  return (
    <dl className="facts">
      <dt>Salary</dt>
      <dd>
        {facts.salary_ranges.length === 0
          ? NOT_STATED
          : facts.salary_ranges.map((range, index) => <div key={index}>{salary(range)}</div>)}
      </dd>
      <dt>Seniority</dt>
      <dd>{facts.seniority.length === 0 ? NOT_STATED : facts.seniority.map(capitalise).join(', ')}</dd>
      <dt>Employment type</dt>
      <dd>{facts.employment_type ? EMPLOYMENT_TYPES[facts.employment_type] : NOT_STATED}</dd>
      <dt>Location restriction</dt>
      <dd>{facts.location_restriction ?? NOT_STATED}</dd>
      <dt>Required technologies</dt>
      <dd>
        <Technologies technologies={facts.required_technologies} />
      </dd>
      <dt>Nice-to-have technologies</dt>
      <dd>
        <Technologies technologies={facts.nice_to_have_technologies} />
      </dd>
    </dl>
  )
}

/** Technologies sharing an alternative group are any one of them: "Python or Go or Java". */
function Technologies({ technologies }: { technologies: Technology[] }) {
  if (technologies.length === 0) return NOT_STATED
  const choices: string[][] = []
  const groups = new Map<number, string[]>()
  for (const { name, alternative_group: group } of technologies) {
    if (group === null) {
      choices.push([name])
    } else if (groups.has(group)) {
      groups.get(group)!.push(name)
    } else {
      const choice = [name]
      groups.set(group, choice)
      choices.push(choice)
    }
  }
  return (
    <ul className="technologies">
      {choices.map((names) => (
        <li key={names.join('|')}>{names.join(' or ')}</li>
      ))}
    </ul>
  )
}

const PERIODS: Record<SalaryRange['period'], string> = {
  year: 'a year',
  month: 'a month',
  day: 'a day',
  hour: 'an hour',
}

function salary({ minimum, maximum, currency, period, applies_to }: SalaryRange): string {
  const amount = (value: number) => value.toLocaleString()
  const bounds =
    minimum !== null && maximum !== null
      ? `${amount(minimum)} to ${amount(maximum)}`
      : minimum !== null
        ? `from ${amount(minimum)}`
        : maximum !== null
          ? `up to ${amount(maximum)}`
          : 'an amount not stated'
  return `${bounds} ${currency} ${PERIODS[period]}${applies_to ? ` (${applies_to})` : ''}`
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}
