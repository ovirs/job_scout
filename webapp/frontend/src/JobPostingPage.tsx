import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { age } from './age'
import {
  closeJobPostingMutation,
  getJobPostingOptions,
  getJobPostingQueryKey,
  listJobPostingsQueryKey,
  reopenJobPostingMutation,
} from './api/@tanstack/react-query.gen'
import type { JobPostingRead } from './api/types.gen'
import { ExtractedFacts, WORKPLACE_TYPES } from './ExtractedFacts'

export function JobPostingPage({ id }: { id: number }) {
  const posting = useQuery(getJobPostingOptions({ path: { job_posting_id: id } }))

  if (posting.isPending) return <p>Loading…</p>
  if (posting.isError) return <p role="alert">Could not load the job posting.</p>
  return <JobPostingView posting={posting.data} />
}

function JobPostingView({ posting }: { posting: JobPostingRead }) {
  const where = [
    posting.location_text,
    posting.workplace_type && WORKPLACE_TYPES[posting.workplace_type],
  ].filter(Boolean)

  return (
    <article>
      <h2>{posting.title}</h2>
      <p>
        {posting.company}
        {where.length > 0 && ` · ${where.join(' · ')}`}
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
      <CloseOrReopen posting={posting} />
      {posting.extracted_fields && (
        <>
          <h3>Facts</h3>
          <ExtractedFacts facts={posting.extracted_fields} />
        </>
      )}
      <h3>Description</h3>
      <div className="description">{posting.description}</div>
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
