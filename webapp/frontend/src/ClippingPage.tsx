import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useEffect, useState } from 'react'
import { age } from './age'
import {
  abandonClippingMutation,
  confirmClippingMutation,
  findSimilarJobPostingsOptions,
  getClippingOptions,
  getClippingQueryKey,
  listJobPostingsQueryKey,
  retryClippingMutation,
  submitClippingMutation,
} from './api/@tanstack/react-query.gen'
import type { ClippingConfirm, ClippingRead } from './api/types.gen'
import { Badge } from './Badge'
import { ExtractedFacts, WORKPLACE_TYPES } from './ExtractedFacts'
import { ModelPicker, useRunChoice } from './ModelPicker'
import { refusal } from './refusal'
import { Loading, Working } from './Waiting'

/** The single paste box: submits a Clipping and opens it while the app reads it. */
export function NewClippingForm() {
  const [pastedText, setPastedText] = useState('')
  const [url, setUrl] = useState('')
  const run = useRunChoice('extraction')
  const submit = useMutation({
    ...submitClippingMutation(),
    onSuccess: (clipping) => {
      window.location.hash = `#/clippings/${clipping.id}`
    },
  })

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    submit.mutate({
      body: { pasted_text: pastedText, url: url.trim() || null, model_choice: run.choice },
    })
  }

  return (
    <form onSubmit={send}>
      <h2>Add a job posting</h2>
      <label>
        Paste the whole page showing the posting
        <textarea
          required
          rows={12}
          value={pastedText}
          onChange={(event) => setPastedText(event.target.value)}
        />
      </label>
      <label>
        Link to the posting (optional, kept for reference and never opened by the app)
        <input type="url" value={url} onChange={(event) => setUrl(event.target.value)} />
      </label>
      <ModelPicker run={run} />
      <button
        type="submit"
        disabled={submit.isPending || pastedText.trim() === ''}
        aria-busy={submit.isPending}
      >
        {submit.isPending ? 'Sending…' : 'Read it'}
      </button>
      {submit.isError && (
        <p role="alert">{refusal(submit.error) ?? 'Could not send the pasted text. Try again.'}</p>
      )}
    </form>
  )
}

export function ClippingPage({ id }: { id: number }) {
  const options = getClippingOptions({ path: { clipping_id: id } })
  const clipping = useQuery({
    ...options,
    // Poll while the worker is still reading the pasted text
    refetchInterval: (query) => (readingNow(query.state.data) ? 1000 : false),
  })

  if (clipping.isPending) return <Loading />
  if (clipping.isError) return <p role="alert">Could not load the pasted text.</p>
  return <ClippingStatus clipping={clipping.data} />
}

/** Whether the worker is reading the pasted text now; a stuck reading is not. */
function readingNow(clipping: ClippingRead | undefined) {
  return (clipping?.status === 'queued' || clipping?.status === 'running') && !clipping.stuck
}

function ClippingStatus({ clipping }: { clipping: ClippingRead }) {
  switch (clipping.status) {
    case 'queued':
    case 'running':
      return clipping.stuck ? (
        <ExtractionFailed clipping={clipping} />
      ) : (
        <Working>Reading the pasted text…</Working>
      )
    case 'failed':
      return <ExtractionFailed clipping={clipping} />
    case 'done':
      return <ConfirmForm clipping={clipping} />
    case 'confirmed':
      return (
        <p>
          Saved as a <a href={`#/job-postings/${clipping.job_posting_id}`}>job posting</a>.
        </p>
      )
    case 'abandoned':
      return <p>You abandoned this pasted text; nothing was saved from it.</p>
  }
}

function ExtractionFailed({ clipping }: { clipping: ClippingRead }) {
  const queryClient = useQueryClient()
  // A retry repeats the reading that failed, unless another model is picked
  const run = useRunChoice('extraction', clipping.model_choice)
  const retry = useMutation({
    ...retryClippingMutation(),
    onSuccess: (retried) =>
      queryClient.setQueryData(getClippingQueryKey({ path: { clipping_id: retried.id } }), retried),
  })

  return (
    <section>
      <h2>Could not read the pasted text</h2>
      <p role="alert">
        {clipping.stuck ? 'Reading it got stuck and never finished.' : clipping.failure?.reason}
      </p>
      <ModelPicker run={run} />
      <div className="actions">
        <button
          type="button"
          disabled={retry.isPending}
          aria-busy={retry.isPending}
          onClick={() =>
            retry.mutate({
              path: { clipping_id: clipping.id },
              body: { model_choice: run.choice },
            })
          }
        >
          {retry.isPending ? 'Retrying…' : 'Try again'}
        </button>
      </div>
      {retry.isError && (
        <p role="alert">{refusal(retry.error) ?? 'Could not retry. Try again.'}</p>
      )}
    </section>
  )
}

type Form = {
  title: string
  company: string
  location_text: string
  workplace_type: '' | NonNullable<ClippingConfirm['workplace_type']>
  description: string
}

/** What was found, all editable, beside the postings already stored from the same company. */
function ConfirmForm({ clipping }: { clipping: ClippingRead }) {
  const extraction = clipping.extraction!
  const queryClient = useQueryClient()
  const [form, setForm] = useState<Form>({
    title: extraction.title ?? '',
    company: extraction.company ?? '',
    location_text: extraction.location_text ?? '',
    workplace_type: extraction.extracted_fields.workplace_type ?? '',
    description: extraction.description,
  })
  const similar = useSimilarPostings(form.company, form.title)
  const confirm = useMutation({
    ...confirmClippingMutation(),
    onSuccess: async (posting) => {
      await queryClient.invalidateQueries({ queryKey: listJobPostingsQueryKey() })
      window.location.hash = `#/job-postings/${posting.id}`
    },
  })

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    confirm.mutate({
      path: { clipping_id: clipping.id },
      body: {
        ...form,
        location_text: form.location_text.trim() || null,
        workplace_type: form.workplace_type || null,
      },
    })
  }

  const field = (name: 'title' | 'company' | 'location_text' | 'description') => ({
    name,
    value: form[name],
    onChange: (event: { target: { value: string } }) =>
      setForm({ ...form, [name]: event.target.value }),
  })
  const hasSimilar = (similar.data?.length ?? 0) > 0

  return (
    <div className="confirmation">
      <form className="panel" onSubmit={save}>
        <h2>Check what was found</h2>
        <p>Correct anything that is wrong before saving.</p>
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
          Workplace type
          <select
            name="workplace_type"
            value={form.workplace_type}
            onChange={(event) =>
              setForm({ ...form, workplace_type: event.target.value as Form['workplace_type'] })
            }
          >
            <option value="">Not stated</option>
            {Object.entries(WORKPLACE_TYPES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Description
          {!extraction.description_cut && (
            <span className="hint">
              Could not tell where the description starts and ends, so this is the whole pasted
              text. Trim it to the posting itself.
            </span>
          )}
          <textarea required rows={16} {...field('description')} />
        </label>
        <h3>Facts found in the posting</h3>
        <ExtractedFacts facts={extraction.extracted_fields} />
        <button type="submit" disabled={confirm.isPending} aria-busy={confirm.isPending}>
          {confirm.isPending ? 'Saving…' : hasSimilar ? 'Save anyway' : 'Save'}
        </button>
        {confirm.isError && <p role="alert">Could not save the job posting. Try again.</p>}
      </form>
      <SimilarPostings clippingId={clipping.id} company={form.company} similar={similar} />
    </div>
  )
}

function useSimilarPostings(company: string, title: string) {
  const query = useDebounced({ company: company.trim(), title: title.trim() }, 300)
  return useQuery({
    ...findSimilarJobPostingsOptions({ query }),
    enabled: query.company !== '',
    placeholderData: keepPreviousData,
  })
}

function SimilarPostings({
  clippingId,
  company,
  similar,
}: {
  clippingId: number
  company: string
  similar: ReturnType<typeof useSimilarPostings>
}) {
  const abandon = useMutation({ ...abandonClippingMutation() })

  function openInstead(postingId: number) {
    abandon.mutate(
      { path: { clipping_id: clippingId } },
      {
        onSuccess: () => {
          window.location.hash = `#/job-postings/${postingId}`
        },
      },
    )
  }

  if (company.trim() === '' || !similar.data || similar.data.length === 0) return null
  return (
    <aside className="panel">
      <h3>Already stored from {company.trim()}</h3>
      <p>
        Is this one of them? Open it and nothing is saved from your pasted text, or save yours
        anyway as a separate posting. Saving never merges.
      </p>
      <ul className="rows">
        {similar.data.map((posting) => (
          <li key={posting.id}>
            <a href={`#/job-postings/${posting.id}`} target="_blank" rel="noreferrer">
              {posting.title}
            </a>
            <div className="hint">
              {[posting.company, posting.location_text, `added ${age(posting.created_at)}`]
                .filter(Boolean)
                .join(' · ')}
              {posting.closed_at && <Badge>closed {age(posting.closed_at)}</Badge>}
            </div>
            <button type="button" disabled={abandon.isPending} onClick={() => openInstead(posting.id)}>
              Open this one instead
            </button>
          </li>
        ))}
      </ul>
      {abandon.isError && <p role="alert">Could not abandon the pasted text. Try again.</p>}
    </aside>
  )
}

/** The value once it has stopped changing for a while; compared by content, not identity. */
function useDebounced<T>(value: T, milliseconds: number): T {
  const [debounced, setDebounced] = useState(value)
  // A fresh object every render would restart the timer, so the effect depends on its JSON
  const key = JSON.stringify(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(JSON.parse(key) as T), milliseconds)
    return () => clearTimeout(timer)
  }, [key, milliseconds])
  return debounced
}
