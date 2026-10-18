import { Fragment, type ReactNode, useEffect, useState } from 'react'
import { ApplicationPage, ApplicationsPage } from './ApplicationPage'
import { ClippingPage, NewClippingForm } from './ClippingPage'
import { DealBreakersPage } from './DealBreakersPage'
import { DOCUMENTS, type DocumentKind, DocumentPage } from './DocumentPage'
import { JobPostingPage } from './JobPostingPage'
import { PostingLists } from './PostingLists'

const JOB_POSTINGS = {
  hash: '#/',
  label: 'Job Postings',
  page: (
    <>
      <NewClippingForm />
      <PostingLists />
    </>
  ),
}

const PAGES = [
  JOB_POSTINGS,
  { hash: '#/applications', label: 'Applications', page: <ApplicationsPage /> },
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
  [/^#\/applications\/(\d+)$/, (id) => <ApplicationPage id={id} />],
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
