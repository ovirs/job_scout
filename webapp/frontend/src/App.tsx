import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, Fragment, useEffect, useState } from 'react'
import { age } from './age'
import {
  createJobPostingMutation,
  listJobPostingsOptions,
  listJobPostingsQueryKey,
} from './api/@tanstack/react-query.gen'
import { DealBreakersPage } from './DealBreakersPage'
import { DOCUMENTS, type DocumentKind, DocumentPage } from './DocumentPage'

const JOB_POSTINGS = {
  hash: '#/',
  label: 'Job Postings',
  page: (
    <>
      <NewJobPostingForm />
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

export default function App() {
  const hash = useHash()
  const current = PAGES.find((page) => page.hash === hash) ?? JOB_POSTINGS

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

const EMPTY_FORM = { title: '', company: '', location_text: '', description: '' }

function NewJobPostingForm() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState(EMPTY_FORM)
  const save = useMutation({
    ...createJobPostingMutation(),
    onSuccess: () => {
      setForm(EMPTY_FORM)
      return queryClient.invalidateQueries({ queryKey: listJobPostingsQueryKey() })
    },
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    save.mutate({ body: { ...form, location_text: form.location_text.trim() || null } })
  }

  const field = (name: keyof typeof EMPTY_FORM) => ({
    name,
    value: form[name],
    onChange: (event: { target: { value: string } }) =>
      setForm({ ...form, [name]: event.target.value }),
  })

  return (
    <form onSubmit={submit}>
      <h2>New job posting</h2>
      <label>
        Title
        <input required {...field('title')} />
      </label>
      <label>
        Company
        <input required {...field('company')} />
      </label>
      <label>
        Location
        <input {...field('location_text')} />
      </label>
      <label>
        Description
        <textarea required rows={10} {...field('description')} />
      </label>
      <button type="submit" disabled={save.isPending}>
        {save.isPending ? 'Saving…' : 'Save'}
      </button>
      {save.isError && <p role="alert">Could not save the job posting. Try again.</p>}
    </form>
  )
}

function JobPostingList() {
  const postings = useQuery({
    ...listJobPostingsOptions(),
    // Poll while the worker has postings still to process
    refetchInterval: (query) =>
      query.state.data?.some((posting) => posting.processing_status === 'queued') ? 1000 : false,
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
                <td>{posting.title}</td>
                <td>{posting.company}</td>
                <td>{posting.location_text}</td>
                <td>{age(posting.created_at)}</td>
                <td>{posting.processing_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
