import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import {
  addDealBreakerMutation,
  deleteDealBreakerMutation,
  editDealBreakerMutation,
  getCurrentDealBreakersOptions,
  getCurrentDealBreakersQueryKey,
} from './api/@tanstack/react-query.gen'
import type { DealBreakerRead, DealBreakerSetVersionRead } from './api/types.gen'
import { age } from './age'

export function DealBreakersPage() {
  const current = useQuery(getCurrentDealBreakersOptions())
  const dealBreakers = current.data?.deal_breakers ?? []

  return (
    <section>
      <h2>Deal Breakers</h2>
      <p>
        Each one a line you will not cross, in one sentence and in your own words. A Job Posting
        that shows it crosses the line is disqualified; one that is silent on it is not.
      </p>
      {current.isPending && <p>Loading…</p>}
      {current.isError && <p role="alert">Could not load the Deal Breakers.</p>}
      {current.data && (
        <p>
          Version {current.data.number}, saved {age(current.data.created_at)}.
        </p>
      )}
      {current.isSuccess && dealBreakers.length === 0 && <p>No Deal Breakers yet.</p>}
      {dealBreakers.length > 0 && (
        <ol>
          {dealBreakers.map((dealBreaker) => (
            <DealBreakerItem key={dealBreaker.id} dealBreaker={dealBreaker} />
          ))}
        </ol>
      )}
      {current.isSuccess && <AddDealBreakerForm />}
    </section>
  )
}

/** Every change returns the new version of the set, which becomes the current one. */
function useShowNewVersion() {
  const queryClient = useQueryClient()
  return (version: DealBreakerSetVersionRead) =>
    queryClient.setQueryData(getCurrentDealBreakersQueryKey(), version)
}

function DealBreakerItem({ dealBreaker }: { dealBreaker: DealBreakerRead }) {
  const showNewVersion = useShowNewVersion()
  const [editedText, setEditedText] = useState<string | null>(null)
  const edit = useMutation({
    ...editDealBreakerMutation(),
    onSuccess: (version) => {
      setEditedText(null)
      showNewVersion(version)
    },
  })
  const remove = useMutation({ ...deleteDealBreakerMutation(), onSuccess: showNewVersion })
  const path = { deal_breaker_id: dealBreaker.id }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (editedText !== null) edit.mutate({ path, body: { text: editedText } })
  }

  function confirmDelete() {
    if (window.confirm(`Delete this Deal Breaker?\n\n${dealBreaker.text}`)) remove.mutate({ path })
  }

  if (editedText !== null) {
    return (
      <li>
        <form onSubmit={submit}>
          <input
            aria-label="Deal Breaker"
            required
            value={editedText}
            onChange={(event) => setEditedText(event.target.value)}
          />
          <div className="actions">
            <button type="submit" disabled={edit.isPending || editedText.trim() === dealBreaker.text}>
              {edit.isPending ? 'Saving…' : 'Save'}
            </button>
            <button type="button" onClick={() => setEditedText(null)}>
              Cancel
            </button>
          </div>
          {edit.isError && <p role="alert">Could not save. Try again.</p>}
        </form>
      </li>
    )
  }

  return (
    <li>
      {dealBreaker.text}
      <div className="actions">
        <button type="button" onClick={() => setEditedText(dealBreaker.text)}>
          Edit
        </button>
        <button type="button" onClick={confirmDelete} disabled={remove.isPending}>
          Delete
        </button>
      </div>
      {remove.isError && <p role="alert">Could not delete. Try again.</p>}
    </li>
  )
}

function AddDealBreakerForm() {
  const showNewVersion = useShowNewVersion()
  const [text, setText] = useState('')
  const add = useMutation({
    ...addDealBreakerMutation(),
    onSuccess: (version) => {
      setText('')
      showNewVersion(version)
    },
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    add.mutate({ body: { text } })
  }

  return (
    <form onSubmit={submit}>
      <label>
        New Deal Breaker
        <input
          required
          placeholder="Fully remote from Romania"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
      </label>
      <button type="submit" disabled={add.isPending || text.trim() === ''}>
        {add.isPending ? 'Adding…' : 'Add'}
      </button>
      {add.isError && <p role="alert">Could not add the Deal Breaker. Try again.</p>}
    </form>
  )
}
