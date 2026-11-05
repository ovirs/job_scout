import { useMutation, useQueryClient } from '@tanstack/react-query'
import { age } from './age'
import {
  getJobPostingQueryKey,
  listEvaluationsQueryKey,
  listJobPostingsQueryKey,
  rerunEvaluationMutation,
} from './api/@tanstack/react-query.gen'
import type {
  CheckedFlag,
  DealBreakerVerdictRead,
  EvaluationRead,
  EvidenceMatch,
} from './api/types.gen'
import { Badge, type Tone } from './Badge'
import { type Highlight, type HighlightKind, quoteKey } from './Highlighted'
import { Working } from './Waiting'

type Recommendation = NonNullable<EvaluationRead['recommendation']>

const RECOMMENDATIONS: Record<Recommendation, string> = {
  apply: 'Apply',
  maybe: 'Maybe',
  skip: 'Skip',
}

const RECOMMENDATION_TONES: Record<Recommendation, Tone> = {
  apply: 'good',
  maybe: 'warn',
  skip: 'bad',
}

export function RecommendationBadge({ recommendation }: { recommendation: Recommendation }) {
  return <Badge tone={RECOMMENDATION_TONES[recommendation]}>{RECOMMENDATIONS[recommendation]}</Badge>
}

/** The score out of 10, uncoloured: it only orders postings, the recommendation judges them. */
export function ScoreBadge({ score }: { score: number }) {
  return <Badge>Score {score}/10</Badge>
}

const VERDICTS: Record<DealBreakerVerdictRead['verdict'], string> = {
  clear: 'Clear',
  violated: 'Violated',
  unknown: 'Unknown',
}

const VERDICT_TONES: Record<DealBreakerVerdictRead['verdict'], Tone> = {
  clear: 'good',
  violated: 'bad',
  unknown: 'warn',
}

const STATUSES: Record<EvaluationRead['status'], string> = {
  queued: 'Queued',
  running: 'Evaluating',
  done: 'Done',
  failed: 'Not evaluated',
}

/** Shows one quote in the posting; null while the quotes cannot be placed there. */
export type ShowQuote = ((key: string) => void) | null

/**
 * Every quote of a done Evaluation, with the key that ties it to its place in the panel.
 * Positions are in the posting's text as it was evaluated: an outdated one has none.
 */
export function highlightsOf(evaluation: EvaluationRead): Highlight[] {
  if (evaluation.outdated) return []
  const highlights: Highlight[] = []
  const add = (key: string, kind: HighlightKind, label: string, matches: EvidenceMatch[]) =>
    matches.forEach((match, index) =>
      highlights.push({ key: quoteKey(key, index), kind, label, match }),
    )
  for (const verdict of evaluation.deal_breaker_verdicts) {
    const label = `${VERDICTS[verdict.verdict]}: ${verdict.deal_breaker_text}`
    add(verdictKey(verdict), verdict.verdict, label, verdict.evidence_matches)
  }
  evaluation.red_flags.forEach((flag, index) =>
    add(flagKey('red', index), 'red', `Red flag: ${flag.point}`, flag.evidence_matches),
  )
  evaluation.green_flags.forEach((flag, index) =>
    add(flagKey('green', index), 'green', `Green flag: ${flag.point}`, flag.evidence_matches),
  )
  return highlights
}

/** The current Evaluation among a posting's runs, the latest first: the latest done one. */
export function currentOf(runs: EvaluationRead[]): EvaluationRead | undefined {
  return runs.find((run) => run.status === 'done')
}

const verdictKey = (verdict: DealBreakerVerdictRead) => `verdict${verdict.deal_breaker_id}`
const flagKey = (colour: 'red' | 'green', index: number) => `${colour}${index}`

/**
 * The posting's Evaluation: the state of its latest run with a retry or a re-run, the
 * current (latest done) one in full, and every run as history.
 */
export function EvaluationPanel({
  postingId,
  runs,
  current,
  showQuote,
}: {
  postingId: number
  runs: EvaluationRead[] // the latest first
  current: EvaluationRead | undefined
  showQuote: ShowQuote
}) {
  const latest = runs.at(0)

  return (
    <section className="evaluation panel">
      <h3>Evaluation</h3>
      <LatestRun postingId={postingId} latest={latest} />
      {current && (
        <>
          {latest !== current && <h4>The current Evaluation, from {age(current.created_at)}</h4>}
          <CurrentEvaluation evaluation={current} showQuote={showQuote} />
        </>
      )}
      {runs.length > 0 && <History runs={runs} />}
    </section>
  )
}

function LatestRun({ postingId, latest }: { postingId: number; latest: EvaluationRead | undefined }) {
  const queryClient = useQueryClient()
  const rerun = useMutation({
    ...rerunEvaluationMutation(),
    onSuccess: async () => {
      const path = { job_posting_id: postingId }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: listEvaluationsQueryKey({ path }) }),
        queryClient.invalidateQueries({ queryKey: getJobPostingQueryKey({ path }) }),
        queryClient.invalidateQueries({ queryKey: listJobPostingsQueryKey() }),
      ])
    },
  })
  const underWay = (latest?.status === 'queued' || latest?.status === 'running') && !latest.stuck
  const label =
    latest === undefined
      ? 'Evaluate'
      : latest.status === 'failed' || latest.stuck
        ? 'Try again'
        : 'Run the Evaluation again'

  return (
    <div>
      {latest === undefined && <p>This posting has not been evaluated yet.</p>}
      {underWay && <Working>Evaluating the posting…</Working>}
      {latest?.stuck && (
        <p role="alert">The Evaluation got stuck and never finished. Try again to replace it.</p>
      )}
      {latest?.status === 'failed' && (
        <>
          <p>
            <strong>Not evaluated.</strong>
          </p>
          <p role="alert">{latest.failure?.reason}</p>
        </>
      )}
      <div className="actions">
        <button
          type="button"
          disabled={rerun.isPending || underWay}
          aria-busy={rerun.isPending}
          onClick={() => rerun.mutate({ path: { job_posting_id: postingId } })}
        >
          {rerun.isPending ? 'Queuing…' : label}
        </button>
        {underWay && (
          <span className="hint">Wait for this Evaluation to finish to run it again.</span>
        )}
      </div>
      {rerun.isError && <p role="alert">Could not start the Evaluation. Try again.</p>}
    </div>
  )
}

function CurrentEvaluation({
  evaluation,
  showQuote,
}: {
  evaluation: EvaluationRead
  showQuote: ShowQuote
}) {
  const violated = evaluation.deal_breaker_verdicts.filter((v) => v.verdict === 'violated')

  return (
    <>
      <p className="badges">
        <RecommendationBadge recommendation={evaluation.recommendation!} />
        <ScoreBadge score={evaluation.score!} />
        {evaluation.outdated && (
          <Badge tone="warn">Outdated: the posting changed since it was evaluated</Badge>
        )}
      </p>
      <p>{evaluation.summary}</p>
      {evaluation.disqualified_but_recommended && (
        <div className="disqualified" role="note">
          <p>
            <strong>Disqualified but recommended.</strong> The LLM recommended{' '}
            {RECOMMENDATIONS[evaluation.llm_recommendation!].toLowerCase()}, but{' '}
            {violated.length === 1 ? 'a Deal Breaker is' : 'Deal Breakers are'} violated, so it
            is stored as skip.
          </p>
          <ul>
            {violated.map((verdict) => (
              <li key={verdict.deal_breaker_id}>
                {verdict.deal_breaker_text}
                <Quotes
                  evidence={verdict.evidence}
                  quoteOf={verdictKey(verdict)}
                  showQuote={showQuote}
                />
              </li>
            ))}
          </ul>
        </div>
      )}
      {evaluation.outdated && (
        <p className="hint">
          Its quotes are not highlighted, since the posting no longer reads as it did.
        </p>
      )}
      {evaluation.to_check.length > 0 && (
        <>
          <h4>To check</h4>
          <ul>
            {evaluation.to_check.map((verdict) => (
              <li key={verdict.deal_breaker_id}>
                {verdict.explanation}{' '}
                <span className="hint">(Deal Breaker: {verdict.deal_breaker_text})</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {evaluation.deal_breaker_verdicts.length > 0 && (
        <>
          <h4>Deal Breakers</h4>
          <ul>
            {evaluation.deal_breaker_verdicts.map((verdict) => (
              <li key={verdict.deal_breaker_id}>
                <Badge tone={VERDICT_TONES[verdict.verdict]} dot>
                  {VERDICTS[verdict.verdict]}
                </Badge>{' '}
                {verdict.deal_breaker_text}
                <div className="hint">{verdict.explanation}</div>
                <Quotes
                  evidence={verdict.evidence}
                  quoteOf={verdictKey(verdict)}
                  showQuote={showQuote}
                />
              </li>
            ))}
          </ul>
        </>
      )}
      <Flags title="Red flags" colour="red" flags={evaluation.red_flags} showQuote={showQuote} />
      <Flags
        title="Green flags"
        colour="green"
        flags={evaluation.green_flags}
        showQuote={showQuote}
      />
    </>
  )
}

function Flags({
  title,
  colour,
  flags,
  showQuote,
}: {
  title: string
  colour: 'red' | 'green'
  flags: CheckedFlag[]
  showQuote: ShowQuote
}) {
  if (flags.length === 0) return null
  return (
    <>
      <h4>
        {title} <Badge tone={colour === 'red' ? 'bad' : 'good'}>{flags.length}</Badge>
      </h4>
      <ul className={`flags ${colour}`}>
        {flags.map((flag, index) => (
          <li key={index}>
            {flag.point}
            <Quotes
              evidence={flag.evidence}
              quoteOf={flagKey(colour, index)}
              showQuote={showQuote}
            />
          </li>
        ))}
      </ul>
    </>
  )
}

/** The posting's words a verdict or flag rests on, each one a way to its highlight. */
function Quotes({
  evidence,
  quoteOf,
  showQuote,
}: {
  evidence: string[]
  quoteOf: string // the verdict or flag the quotes support
  showQuote: ShowQuote
}) {
  if (evidence.length === 0) return null
  return (
    <ul className="quotes">
      {evidence.map((passage, index) => (
        <li key={index}>
          {showQuote ? (
            <button
              type="button"
              className="quote"
              title="Show it in the posting"
              onClick={() => showQuote(quoteKey(quoteOf, index))}
            >
              “{passage}”
            </button>
          ) : (
            <q>{passage}</q>
          )}
        </li>
      ))}
    </ul>
  )
}

/** Every run, the latest first, with what it was made with, so runs can be compared. */
function History({ runs }: { runs: EvaluationRead[] }) {
  const version = (number: number | null) => (number === null ? 'none' : `v${number}`)
  return (
    <details>
      <summary>Evaluation history ({runs.length})</summary>
      <table>
        <thead>
          <tr>
            <th>Run</th>
            <th>Result</th>
            <th>Model</th>
            <th>Prompt</th>
            <th>Career Profile</th>
            <th>Preferences</th>
            <th>Deal Breakers</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <td>{age(run.created_at)}</td>
              <td>
                {run.status === 'done' ? (
                  <span className="badges">
                    <RecommendationBadge recommendation={run.recommendation!} />
                    <ScoreBadge score={run.score!} />
                  </span>
                ) : (
                  STATUSES[run.status]
                )}
                {run.failure && <div className="hint">{run.failure.reason}</div>}
                {run.outdated && <Badge tone="warn">Outdated</Badge>}
              </td>
              <td>{run.model ?? '–'}</td>
              <td>{run.prompt_version ?? '–'}</td>
              {/* Recorded with the posting's text when it ran, which `outdated` is judged by */}
              {run.outdated === null ? (
                <td colSpan={3} className="hint">
                  Not recorded
                </td>
              ) : (
                <>
                  <td>{version(run.career_profile_version_number)}</td>
                  <td>{version(run.preferences_version_number)}</td>
                  <td>{version(run.deal_breaker_set_version_number)}</td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  )
}
