import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { age } from './age'
import { ApplicationStateBadge } from './ApplicationPage'
import {
  listJobPostingsOptions,
  listJobPostingsQueryKey,
  rerunEvaluationMutation,
  rerunUnactedEvaluationsMutation,
} from './api/@tanstack/react-query.gen'
import type { JobPostingRead, ListJobPostingsData } from './api/types.gen'
import { Badge } from './Badge'
import { RecommendationBadge, ScoreBadge } from './EvaluationPanel'
import { TriageButtons } from './TriageButtons'
import { Loading } from './Waiting'

type ListName = NonNullable<NonNullable<ListJobPostingsData['query']>['list']>
type Sort = NonNullable<NonNullable<ListJobPostingsData['query']>['sort']>

/** `sort` is how the list is ordered until the user picks otherwise. */
const LISTS: { name: ListName; label: string; sort: Sort; empty: string }[] = [
  { name: 'inbox', sort: 'score', label: 'Inbox', empty: 'Nothing waiting for your call.' },
  { name: 'skip', sort: 'score', label: 'Skip list', empty: 'Nothing recommended to skip.' },
  { name: 'not-evaluated', sort: 'age', label: 'Not evaluated', empty: 'Every untriaged posting is evaluated.' },
  { name: 'shortlist', sort: 'age', label: 'Shortlist', empty: 'No postings you are interested in.' },
  { name: 'later', sort: 'age', label: 'Later', empty: 'No postings set aside for later.' },
  { name: 'ignored', sort: 'age', label: 'Ignored', empty: 'No ignored postings.' },
]

export function PostingLists() {
  const [list, setList] = useState(LISTS[0])
  const [sort, setSort] = useState<Sort>(LISTS[0].sort)
  const name = list.name
  const postings = useQuery({
    ...listJobPostingsOptions({ query: { list: name, sort } }),
    // Poll while the worker has Evaluations still to run
    refetchInterval: (query) =>
      query.state.data?.some(
        (p) => p.evaluation_status === 'queued' || p.evaluation_status === 'running',
      )
        ? 1000
        : false,
  })

  return (
    <section>
      <h2>Job postings</h2>
      <div className="segmented" role="tablist" aria-label="Lists">
        {LISTS.map((l) => (
          <button
            key={l.name}
            type="button"
            role="tab"
            aria-selected={l.name === name}
            onClick={() => {
              setList(l)
              setSort(l.sort)
            }}
          >
            {l.label}
          </button>
        ))}
      </div>
      <label className="inline">
        Sort by{' '}
        <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
          <option value="score">Score, highest first</option>
          <option value="age">Age, newest first</option>
        </select>
      </label>
      <RerunUnacted />
      {postings.isPending && <Loading />}
      {postings.isError && <p role="alert">Could not load the job postings.</p>}
      {postings.data?.length === 0 && <p>{list.empty}</p>}
      {postings.data && postings.data.length > 0 && (
        <ul className="rows">
          {postings.data.map((posting) => (
            <PostingRow key={posting.id} posting={posting} />
          ))}
        </ul>
      )}
    </section>
  )
}

function PostingRow({ posting }: { posting: JobPostingRead }) {
  const evaluation = posting.evaluation
  return (
    <li>
      <a href={`#/job-postings/${posting.id}`}>{posting.title}</a> · {posting.company} ·{' '}
      {age(posting.created_at)}
      {evaluation && (
        <>
          <ScoreBadge score={evaluation.score} />
          <RecommendationBadge recommendation={evaluation.recommendation} />
        </>
      )}
      {posting.application && (
        <ApplicationStateBadge
          state={posting.application.state}
          href={`#/applications/${posting.application.id}`}
          prefix="Application: "
        />
      )}
      {posting.closed_at && <Badge>Closed on {posting.closed_at.slice(0, 10)}</Badge>}
      {evaluation && (
        <>
          {evaluation.outdated && (
            // An acted-on posting keeps its Evaluation when its text changes; an untriaged
            // one is evaluated again
            <Badge tone="warn">
              {posting.triage ? 'Edited since you triaged it' : 'Edited since evaluated'}
            </Badge>
          )}
          {evaluation.disqualified_but_recommended && (
            <Badge tone="bad" dot>
              Disqualified but recommended:{' '}
              {evaluation.violated_deal_breakers.map((d) => d.deal_breaker_text).join('; ')}
            </Badge>
          )}
          <p className="summary" title={evaluation.summary}>
            {evaluation.summary}
          </p>
        </>
      )}
      {!evaluation && <NotEvaluated posting={posting} />}
      <TriageButtons posting={posting} />
    </li>
  )
}

/** Re-run the Evaluation of every open posting not acted on, after the user inputs change. */
function RerunUnacted() {
  const queryClient = useQueryClient()
  const rerun = useMutation({
    ...rerunUnactedEvaluationsMutation(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: listJobPostingsQueryKey() }),
  })
  const queued = rerun.data?.length
  return (
    <p className="actions">
      <button
        type="button"
        disabled={rerun.isPending}
        aria-busy={rerun.isPending}
        onClick={() => rerun.mutate({})}
      >
        {rerun.isPending ? 'Queuing…' : 'Re-run all I have not acted on'}
      </button>
      <span className="hint">
        {queued === undefined
          ? 'Evaluates every open, untriaged posting again with your current inputs.'
          : queued === 1
            ? 'Queued 1 Evaluation.'
            : `Queued ${queued} Evaluations.`}
      </span>
      {rerun.isError && <span role="alert">Could not queue the Evaluations. Try again.</span>}
    </p>
  )
}

/** Why a posting has no Evaluation yet, with a retry when it failed. */
function NotEvaluated({ posting }: { posting: JobPostingRead }) {
  const queryClient = useQueryClient()
  const rerun = useMutation({
    ...rerunEvaluationMutation(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: listJobPostingsQueryKey() }),
  })
  const status = posting.evaluation_status
  const underWay = status === 'queued' || status === 'running'
  const label =
    status === 'queued' ? 'Evaluation queued' : status === 'running' ? 'Evaluating…' : 'Not evaluated'
  return (
    <p className="hint">
      <Badge tone={underWay ? 'accent' : 'neutral'} busy={underWay}>
        {label}
      </Badge>
      {posting.evaluation_failure && ` ${posting.evaluation_failure.reason}`}
      {status === 'failed' && (
        <>
          {' '}
          <button
            type="button"
            disabled={rerun.isPending}
            aria-busy={rerun.isPending}
            onClick={() => rerun.mutate({ path: { job_posting_id: posting.id } })}
          >
            Try again
          </button>
        </>
      )}
    </p>
  )
}
