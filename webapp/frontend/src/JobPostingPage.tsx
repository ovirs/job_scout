import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { age } from './age'
import {
  closeJobPostingMutation,
  getJobPostingOptions,
  getJobPostingQueryKey,
  listEvaluationsOptions,
  listJobPostingsQueryKey,
  reopenJobPostingMutation,
} from './api/@tanstack/react-query.gen'
import type { EvaluationRead, EvidenceMatch, JobPostingRead } from './api/types.gen'
import { currentOf, EvaluationPanel, highlightsOf } from './EvaluationPanel'
import { ExtractedFacts, WORKPLACE_TYPES } from './ExtractedFacts'
import { Highlighted, scrollToQuote } from './Highlighted'
import { TriageButtons } from './TriageButtons'

export function JobPostingPage({ id }: { id: number }) {
  const path = { job_posting_id: id }
  const posting = useQuery(getJobPostingOptions({ path }))
  const runs = useQuery({
    ...listEvaluationsOptions({ path }),
    // Poll while the latest Evaluation is under way
    refetchInterval: (query) => {
      const status = query.state.data?.at(0)?.status
      return status === 'queued' || status === 'running' ? 1000 : false
    },
  })

  if (posting.isPending || runs.isPending) return <p>Loading…</p>
  if (posting.isError) return <p role="alert">Could not load the job posting.</p>
  // The posting stays readable when only its Evaluations could not be loaded
  return <JobPostingView posting={posting.data} runs={runs.isError ? null : runs.data} />
}

function JobPostingView({
  posting,
  runs,
}: {
  posting: JobPostingRead
  runs: EvaluationRead[] | null // null when they could not be loaded
}) {
  // The quote last shown from the Evaluation, highlighted more strongly
  const [active, setActive] = useState<string | null>(null)
  const current = runs ? currentOf(runs) : undefined
  const highlights = current ? highlightsOf(current) : []
  const field = (name: EvidenceMatch['field'], text: string) => (
    <Highlighted
      text={text}
      highlights={highlights.filter((h) => h.match.field === name)}
      active={active}
    />
  )
  const showQuote =
    highlights.length > 0
      ? (key: string) => {
          setActive(key)
          scrollToQuote(key)
        }
      : null
  const workplace = posting.workplace_type && WORKPLACE_TYPES[posting.workplace_type]

  return (
    <article>
      <h2>{field('title', posting.title)}</h2>
      <p>
        {field('company', posting.company)}
        {posting.location_text && <> · {field('location_text', posting.location_text)}</>}
        {workplace && ` · ${workplace}`}
      </p>
      <p className="hint">
        Added {age(posting.created_at)}
        {posting.url && (
          <>
            {' · '}
            <a href={posting.url} target="_blank" rel="noreferrer">
              Original posting
            </a>
          </>
        )}
      </p>
      <TriageButtons posting={posting} />
      <CloseOrReopen posting={posting} />
      {posting.extracted_fields && (
        <>
          <h3>Facts</h3>
          <ExtractedFacts facts={posting.extracted_fields} />
        </>
      )}
      {runs ? (
        <EvaluationPanel
          postingId={posting.id}
          runs={runs}
          current={current}
          showQuote={showQuote}
        />
      ) : (
        <p role="alert">Could not load the posting's Evaluations.</p>
      )}
      <h3>Description</h3>
      <div className="description">{field('description', posting.description)}</div>
      {posting.pasted_text !== null && (
        <details>
          <summary>Everything you pasted</summary>
          <div className="description">{posting.pasted_text}</div>
        </details>
      )}
    </article>
  )
}

/** A Manual Entry is closed only by the user, and closing never deletes it. */
function CloseOrReopen({ posting }: { posting: JobPostingRead }) {
  const queryClient = useQueryClient()
  const onSuccess = async (changed: JobPostingRead) => {
    queryClient.setQueryData(getJobPostingQueryKey({ path: { job_posting_id: changed.id } }), changed)
    await queryClient.invalidateQueries({ queryKey: listJobPostingsQueryKey() })
  }
  const close = useMutation({ ...closeJobPostingMutation(), onSuccess })
  const reopen = useMutation({ ...reopenJobPostingMutation(), onSuccess })
  const path = { job_posting_id: posting.id }

  return (
    <div className="actions">
      {posting.closed_at ? (
        <>
          <span className="badge">Closed {age(posting.closed_at)}</span>
          <button type="button" disabled={reopen.isPending} onClick={() => reopen.mutate({ path })}>
            Reopen
          </button>
        </>
      ) : (
        <button type="button" disabled={close.isPending} onClick={() => close.mutate({ path })}>
          Close (the role is filled or the posting is gone)
        </button>
      )}
      {(close.isError || reopen.isError) && <p role="alert">Could not save. Try again.</p>}
    </div>
  )
}
