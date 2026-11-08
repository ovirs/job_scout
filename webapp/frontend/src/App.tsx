import { useQuery } from '@tanstack/react-query'
import { Fragment, type ReactNode, useEffect, useState } from 'react'
import { AddPosting } from './AddPosting'
import { getSetupOptions } from './api/@tanstack/react-query.gen'
import { ApplicationPage, ApplicationsPage } from './ApplicationPage'
import { ClippingPage } from './ClippingPage'
import { DealBreakersPage } from './DealBreakersPage'
import { DOCUMENTS, type DocumentKind, DocumentPage } from './DocumentPage'
import { JobPostingPage } from './JobPostingPage'
import { PostingLists } from './PostingLists'
import { SettingsPage, SetupScreen } from './SettingsPage'
import { Loading } from './Waiting'

type NavPage = { hash: string; label: string; glyph: string; page: ReactNode }

const JOB_POSTINGS: NavPage = {
  hash: '#/',
  label: 'Job Postings',
  glyph: '◎',
  page: <PostingLists />,
}

const APPLICATIONS: NavPage = {
  hash: '#/applications',
  label: 'Applications',
  glyph: '➤',
  page: <ApplicationsPage />,
}

/** The main navigation, grouped by what the pages are about. */
const GROUPS: { label: string; pages: NavPage[] }[] = [
  {
    label: 'Scouting',
    pages: [JOB_POSTINGS, APPLICATIONS],
  },
  {
    label: 'About you',
    pages: [
      documentPage('career-profile', '☰'),
      documentPage('preferences', '♡'),
      { hash: '#/deal-breakers', label: 'Deal Breakers', glyph: '⊘', page: <DealBreakersPage /> },
    ],
  },
  { label: 'Writing', pages: [documentPage('writing-guide', '✎')] },
  {
    label: 'App',
    pages: [{ hash: '#/settings', label: 'Settings', glyph: '⚙', page: <SettingsPage /> }],
  },
]

const PAGES = GROUPS.flatMap((group) => group.pages)

function documentPage(kind: DocumentKind, glyph: string): NavPage {
  return { hash: `#/${kind}`, label: DOCUMENTS[kind].title, glyph, page: <DocumentPage kind={kind} /> }
}

/** Pages for one record, reached by link rather than from the navigation; each lights up the
 * page it belongs to. */
const RECORD_PAGES: [RegExp, NavPage, (id: number) => ReactNode][] = [
  [/^#\/clippings\/(\d+)$/, JOB_POSTINGS, (id) => <ClippingPage id={id} />],
  [/^#\/job-postings\/(\d+)$/, JOB_POSTINGS, (id) => <JobPostingPage id={id} />],
  [/^#\/applications\/(\d+)$/, APPLICATIONS, (id) => <ApplicationPage id={id} />],
]

function recordPage(hash: string): { owner: NavPage; page: ReactNode } | null {
  for (const [pattern, owner, page] of RECORD_PAGES) {
    const match = pattern.exec(hash)
    if (match) return { owner, page: page(Number(match[1])) }
  }
  return null
}

/** Until a Provider is set up, every route shows the setup screen and nothing else. */
export default function App() {
  const setup = useQuery(getSetupOptions())
  if (setup.isPending) return <Loading />
  if (setup.isError) return <p role="alert">Could not reach the app. Reload to try again.</p>
  if (!setup.data.has_provider) return <SetupScreen />
  return <Shell />
}

function Shell() {
  const hash = useHash()
  const record = recordPage(hash)
  const navPage = PAGES.find((page) => page.hash === hash) ?? JOB_POSTINGS
  const current = record
    ? { hash, owner: record.owner, page: record.page }
    : { hash: navPage.hash, owner: navPage, page: navPage.page }

  return (
    <div className="shell">
      <header className="sidebar">
        <a className="brand" href="#/" aria-label="Job Scout">
          <span className="brand-mark" aria-hidden="true">
            ◆
          </span>{' '}
          <span className="brand-text">Job Scout</span>
        </a>
        <nav aria-label="Main">
          {GROUPS.map((group) => (
            <div key={group.label} className="nav-group">
              <div className="nav-group-label">{group.label}</div>
              {group.pages.map((page) => (
                <a
                  key={page.hash}
                  href={page.hash}
                  aria-current={page === current.owner ? 'page' : undefined}
                >
                  <span className="nav-glyph" aria-hidden="true">
                    {page.glyph}
                  </span>
                  {page.label}
                </a>
              ))}
            </div>
          ))}
        </nav>
      </header>
      <main className="content">
        {/* Keyed so that moving between pages never carries one page's state into another */}
        <Fragment key={current.hash}>{current.page}</Fragment>
      </main>
      <AddPosting />
    </div>
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
