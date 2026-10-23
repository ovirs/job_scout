import { type UseQueryResult, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import {
  addApplicationNoteMutation,
  addJobPostingNoteMutation,
  deleteNoteMutation,
  listApplicationNotesOptions,
  listApplicationNotesQueryKey,
  listJobPostingNotesOptions,
  listJobPostingNotesQueryKey,
} from './api/@tanstack/react-query.gen'
import type { NoteRead } from './api/types.gen'
import { Badge } from './Badge'
import { Loading } from './Waiting'

/** The Application shows its posting's notes too, so a change to any note refreshes the
 * posting's list and, while it has one, its live Application's. */
function useRefreshNotes(postingId: number, applicationId: number | null) {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({
        queryKey: listJobPostingNotesQueryKey({ path: { job_posting_id: postingId } }),
      }),
      applicationId !== null &&
        queryClient.invalidateQueries({
          queryKey: listApplicationNotesQueryKey({ path: { application_id: applicationId } }),
        }),
    ])
}

/** A posting's own notes, added to the posting. */
export function PostingNotes({
  postingId,
  applicationId,
}: {
  postingId: number
  applicationId: number | null // its live Application, if it has one
}) {
  const refresh = useRefreshNotes(postingId, applicationId)
  const notes = useQuery(listJobPostingNotesOptions({ path: { job_posting_id: postingId } }))
  const add = useMutation({ ...addJobPostingNoteMutation(), onSuccess: refresh })
  return (
    <NoteList
      notes={notes}
      markPostingNotes={false}
      refresh={refresh}
      label="New note on the posting"
      pending={add.isPending}
      failed={add.isError}
      onAdd={(text, done) =>
        add.mutate({ path: { job_posting_id: postingId }, body: { text } }, { onSuccess: done })
      }
    />
  )
}

/** An Application's notes with its posting's alongside, added to the Application. */
export function ApplicationNotes({
  postingId,
  applicationId,
}: {
  postingId: number
  applicationId: number
}) {
  const refresh = useRefreshNotes(postingId, applicationId)
  const notes = useQuery(listApplicationNotesOptions({ path: { application_id: applicationId } }))
  const add = useMutation({ ...addApplicationNoteMutation(), onSuccess: refresh })
  return (
    <NoteList
      notes={notes}
      markPostingNotes={true}
      refresh={refresh}
      label="New note on the Application"
      pending={add.isPending}
      failed={add.isError}
      onAdd={(text, done) =>
        add.mutate({ path: { application_id: applicationId }, body: { text } }, { onSuccess: done })
      }
    />
  )
}

function NoteList({
  notes,
  markPostingNotes,
  refresh,
  label,
  pending,
  failed,
  onAdd,
}: {
  notes: UseQueryResult<NoteRead[], unknown>
  markPostingNotes: boolean
  refresh: () => Promise<unknown>
  label: string
  pending: boolean
  failed: boolean
  onAdd: (text: string, done: () => void) => void
}) {
  const [text, setText] = useState('')
  const remove = useMutation({ ...deleteNoteMutation(), onSuccess: refresh })

  function confirmDelete(note: NoteRead) {
    if (window.confirm(`Delete this note?\n\n${note.text}`)) {
      remove.mutate({ path: { note_id: note.id } })
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onAdd(text, () => setText(''))
  }

  return (
    <section>
      <h3>Notes</h3>
      {notes.isPending && <Loading />}
      {notes.isError && <p role="alert">Could not load the notes.</p>}
      {notes.isSuccess && notes.data.length === 0 && <p>No notes yet.</p>}
      {notes.isSuccess && notes.data.length > 0 && (
        <ul className="rows">
          {notes.data.map((note) => (
            <li key={note.id}>
              <p className="hint">
                {new Date(note.created_at).toLocaleString()}
                {markPostingNotes && note.job_posting_id !== null && (
                  <Badge>On the posting</Badge>
                )}
              </p>
              <div className="description">{note.text}</div>
              <button type="button" disabled={remove.isPending} onClick={() => confirmDelete(note)}>
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
      {remove.isError && <p role="alert">Could not delete. Try again.</p>}
      <form className="panel" onSubmit={submit}>
        <label>
          {label}
          <textarea
            required
            rows={3}
            placeholder="Interview rounds, contacts, impressions"
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
        </label>
        <button type="submit" disabled={pending || text.trim() === ''} aria-busy={pending}>
          {pending ? 'Adding…' : 'Add note'}
        </button>
        {failed && <p role="alert">Could not add the note. Try again.</p>}
      </form>
    </section>
  )
}
