import { type QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { age } from './age'
import {
  deleteApplicationMutation,
  getApplicationOptions,
  getApplicationQueryKey,
  getCoverLetterQueryKey,
  getJobPostingQueryKey,
  listApplicationsOptions,
  listApplicationsQueryKey,
  listJobPostingsQueryKey,
  setApplicationStateMutation,
  startApplicationMutation,
} from './api/@tanstack/react-query.gen'
import type { ApplicationRead, ApplicationStateSet, JobPostingRead } from './api/types.gen'
import { Badge, type Tone } from './Badge'
import { CoverLetter } from './CoverLetter'
import { ApplicationNotes } from './Notes'
import { Loading } from './Waiting'

type State = ApplicationStateSet['state']

/** In the usual progression; the last four are closed. */
export const STATE_LABELS: Record<State, string> = {
  preparing: 'Preparing',
  applied: 'Applied',
  screen_call: 'Screen call',
  interview_loop: 'Interview loop',
  offer: 'Offer',
  accepted: 'Accepted',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
  no_response: 'No response',
}

/** Under way in the accent, then how it ended. */
const STATE_TONES: Record<State, Tone> = {
  preparing: 'accent',
  applied: 'accent',
  screen_call: 'accent',
  interview_loop: 'accent',
  offer: 'good',
  accepted: 'good',
  rejected: 'bad',
  withdrawn: 'neutral',
  no_response: 'neutral',
}

/** An Application's state, as a link to it when `href` is given. */
export function ApplicationStateBadge({
  state,
  href,
  prefix = '',
}: {
  state: State
  href?: string
  prefix?: string
}) {
  return (
    <Badge tone={STATE_TONES[state]} dot href={href}>
      {prefix}
      {STATE_LABELS[state]}
    </Badge>
  )
}

/** Everything that shows an Application, its Cover Letter (locked outside Preparing) or its
 * posting's Triage. */
async function refreshAfterChange(queryClient: QueryClient, application: ApplicationRead) {
  queryClient.setQueryData(
    getApplicationQueryKey({ path: { application_id: application.id } }),
    application,
  )
  await Promise.all([
    queryClient.invalidateQueries({
      queryKey: getJobPostingQueryKey({ path: { job_posting_id: application.job_posting_id } }),
    }),
    queryClient.invalidateQueries({ queryKey: listJobPostingsQueryKey() }),
    queryClient.invalidateQueries({ queryKey: listApplicationsQueryKey() }),
    queryClient.invalidateQueries({
      queryKey: getCoverLetterQueryKey({ path: { application_id: application.id } }),
    }),
  ])
}

/** On a posting: a link to its live Application, or the one deliberate step that starts
 * one (and sets the Triage to Interested). */
export function ApplicationAction({ posting }: { posting: JobPostingRead }) {
  const queryClient = useQueryClient()
  const start = useMutation({
    ...startApplicationMutation(),
    onSuccess: async (started) => {
      await refreshAfterChange(queryClient, started)
      window.location.hash = `#/applications/${started.id}`
    },
  })

  if (posting.application) {
    return (
      <p>
        <a href={`#/applications/${posting.application.id}`}>Your Application</a>{' '}
        <ApplicationStateBadge state={posting.application.state} />
      </p>
    )
  }
  return (
    <div className="actions">
      <button
        type="button"
        disabled={start.isPending}
        aria-busy={start.isPending}
        onClick={() => start.mutate({ path: { job_posting_id: posting.id } })}
      >
        Start application
      </button>
      {start.isError && <p role="alert">Could not start the Application. Try again.</p>}
    </div>
  )
}

export function ApplicationPage({ id }: { id: number }) {
  const application = useQuery(getApplicationOptions({ path: { application_id: id } }))
  if (application.isPending) return <Loading />
  if (application.isError) return <p role="alert">Could not load the Application.</p>
  return <ApplicationView application={application.data} />
}

function ApplicationView({ application }: { application: ApplicationRead }) {
  const queryClient = useQueryClient()
  const setState = useMutation({
    ...setApplicationStateMutation(),
    onSuccess: (moved) => refreshAfterChange(queryClient, moved),
  })
  const remove = useMutation({
    ...deleteApplicationMutation(),
    onSuccess: async () => {
      await refreshAfterChange(queryClient, application)
      queryClient.removeQueries({
        queryKey: getApplicationQueryKey({ path: { application_id: application.id } }),
      })
      window.location.hash = `#/job-postings/${application.job_posting_id}`
    },
  })
  const path = { application_id: application.id }
  const copy = application.posting_copy

  return (
    <article>
      <h2>
        Application: <a href={`#/job-postings/${application.job_posting_id}`}>
          {application.job_posting_title}
        </a>
      </h2>
      <p>
        {application.job_posting_company}
        {application.job_posting_closed_at && (
          <Badge>Posting closed on {application.job_posting_closed_at.slice(0, 10)}</Badge>
        )}
      </p>
      <div className="actions">
        <label className="inline">
          State{' '}
          <select
            value={application.state}
            disabled={setState.isPending}
            onChange={(e) => setState.mutate({ path, body: { state: e.target.value as State } })}
          >
            {(Object.keys(STATE_LABELS) as State[]).map((state) => (
              <option key={state} value={state}>
                {STATE_LABELS[state]}
              </option>
            ))}
          </select>
        </label>
        {application.closed && <Badge>Closed</Badge>}
        {application.state === 'preparing' && (
          <button
            type="button"
            disabled={remove.isPending}
            aria-busy={remove.isPending}
            onClick={() => {
              if (window.confirm(deleteQuestion(application))) {
                remove.mutate({ path })
              }
            }}
          >
            Delete application
          </button>
        )}
      </div>
      {(setState.isError || remove.isError) && <p role="alert">Could not save. Try again.</p>}
      <h3>History</h3>
      <ol className="panel">
        {application.history.map((change, i) => (
          <li key={i}>
            <ApplicationStateBadge state={change.state} />{' '}
            {new Date(change.changed_at).toLocaleString()}
          </li>
        ))}
      </ol>
      <CoverLetter applicationId={application.id} />
      <ApplicationNotes postingId={application.job_posting_id} applicationId={application.id} />
      {copy && (
        <>
          <h3>What you applied to</h3>
          {application.posting_changed_since_copy && (
            <p>
              <Badge tone="warn">The posting has changed since you applied</Badge>
            </p>
          )}
          <p className="hint">
            Copied {age(copy.copied_at)}
            {copy.url && (
              <>
                {' · '}
                <a href={copy.url} target="_blank" rel="noreferrer">
                  Original posting
                </a>
              </>
            )}
          </p>
          <details>
            <summary>
              {copy.title} · {copy.company}
              {copy.location_text && ` · ${copy.location_text}`}
            </summary>
            <div className="description">{copy.description}</div>
          </details>
        </>
      )}
    </article>
  )
}

/** Deletion is allowed whenever the Application is Preparing, even after a move to Applied
 * and back; the app cannot tell a mistaken move from a real application, so the question
 * names that move and lets the user tell. */
function deleteQuestion(application: ApplicationRead): string {
  const lastApplied = application.history.findLast((change) => change.state === 'applied')
  if (!lastApplied) return 'Delete this Application? The posting stays Interested.'
  const date = (timestamp: string) => new Date(timestamp).toLocaleString()
  return (
    `This Application was marked Applied on ${date(lastApplied.changed_at)} and moved back ` +
    `to Preparing on ${date(application.state_changed_at)}. Delete it anyway? ` +
    'The posting stays Interested.'
  )
}

export function ApplicationsPage() {
  return (
    <section>
      <h2>Applications</h2>
      <h3>In flight</h3>
      <ApplicationList closed={false} empty="No Applications in flight." />
      <h3>Closed</h3>
      <ApplicationList closed={true} empty="No closed Applications." />
    </section>
  )
}

/** The live Applications, closed or in flight, by state. */
function ApplicationList({ closed, empty }: { closed: boolean; empty: string }) {
  const query = useQuery(listApplicationsOptions({ query: { closed } }))
  if (query.isPending) return <Loading />
  if (query.isError) return <p role="alert">Could not load the Applications.</p>
  if (query.data.length === 0) return <p>{empty}</p>
  return (
    <ul className="rows">
      {query.data.map((application) => (
        <li key={application.id}>
          <a href={`#/applications/${application.id}`}>{application.job_posting_title}</a> ·{' '}
          {application.job_posting_company} · moved {age(application.state_changed_at)}
          <ApplicationStateBadge state={application.state} />
          {application.job_posting_closed_at && <Badge>Posting closed</Badge>}
        </li>
      ))}
    </ul>
  )
}
