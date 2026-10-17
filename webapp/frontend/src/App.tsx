import { useQuery } from '@tanstack/react-query'
import { Fragment, type ReactNode, useEffect, useState } from 'react'
import { age } from './age'
import { listJobPostingsOptions } from './api/@tanstack/react-query.gen'
import type { JobPostingRead } from './api/types.gen'
import { ClippingPage, NewClippingForm } from './ClippingPage'
import { DealBreakersPage } from './DealBreakersPage'
import { DOCUMENTS, type DocumentKind, DocumentPage } from './DocumentPage'
import { JobPostingPage } from './JobPostingPage'

const JOB_POSTINGS = {
  hash: '#/',
  label: 'Job Postings',
  page: (
    <>
      <NewClippingForm />
      <JobPostingList />
    </>
  ),
}

const PAGES = [
  JOB_POSTINGS,
  documentPage('career-profile'),
  documentPage('preferences'),
  { hash: '#/deal-breakers', label: 'Deal Breakers', page: <DealBreakersPage /> },
  documentPage('writing-guide'),
]

function documentPage(kind: DocumentKind) {
  return { hash: `#/${kind}`, label: DOCUMENTS[kind].title, page: <DocumentPage kind={kind} /> }
}

/** Pages for one record, reached by link rather than from the navigation. */
const RECORD_PAGES: [RegExp, (id: number) => ReactNode][] = [
  [/^#\/clippings\/(\d+)$/, (id) => <ClippingPage id={id} />],
  [/^#\/job-postings\/(\d+)$/, (id) => <JobPostingPage id={id} />],
]

function recordPage(hash: string): ReactNode | null {
  for (const [pattern, page] of RECORD_PAGES) {
    const match = pattern.exec(hash)
    if (match) return page(Number(match[1]))
  }
  return null
}

export default function App() {
  const hash = useHash()
  const record = recordPage(hash)
  const current = record
    ? { hash, page: record }
    : (PAGES.find((page) => page.hash === hash) ?? JOB_POSTINGS)

  return (
    <main>
      <h1>Job Scout</h1>
      <nav>
        {PAGES.map((page) => (
          <a
            key={page.hash}
            href={page.hash}
            aria-current={page === current ? 'page' : undefined}
          >
            {page.label}
          </a>
        ))}
      </nav>
      {/* Keyed so that moving between pages never carries one page's state into another */}
      <Fragment key={current.hash}>{current.page}</Fragment>
    </main>
  )
}

function useHash(): string {
  const [hash, setHash] = useState(window.location.hash || '#/')
  useEffect(() => {
    const update = () => setHash(window.location.hash || '#/')
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  return hash
}

function evaluationStatusLabel(status: JobPostingRead['evaluation_status']): string {
  switch (status) {
    case 'queued':
      return 'evaluation queued'
    case 'running':
      return 'evaluating'
    case 'done':
      return 'evaluated'
    case 'not_evaluated':
      return 'not evaluated'
    default:
      return 'no evaluation'
  }
}

function JobPostingList() {
  const postings = useQuery({
    ...listJobPostingsOptions(),
    // Poll while the worker has Evaluations still to run
    refetchInterval: (query) =>
      query.state.data?.some(
        (posting) =>
          posting.evaluation_status === 'queued' || posting.evaluation_status === 'running',
      )
        ? 1000
        : false,
  })

  return (
    <section>
      <h2>Job postings</h2>
      {postings.isPending && <p>Loading…</p>}
      {postings.isError && <p role="alert">Could not load the job postings.</p>}
      {postings.data?.length === 0 && <p>No job postings yet.</p>}
      {postings.data && postings.data.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Company</th>
              <th>Location</th>
              <th>Age</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {postings.data.map((posting) => (
              <tr key={posting.id}>
                <td>
                  <a href={`#/job-postings/${posting.id}`}>{posting.title}</a>
                </td>
                <td>{posting.company}</td>
                <td>{posting.location_text}</td>
                <td>{age(posting.created_at)}</td>
                <td>
                  {posting.closed_at
                    ? `closed ${age(posting.closed_at)}`
                    : evaluationStatusLabel(posting.evaluation_status)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
