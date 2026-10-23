import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import {
  getCurrentDocumentOptions,
  getCurrentDocumentQueryKey,
  saveDocumentMutation,
} from './api/@tanstack/react-query.gen'
import type { DocumentVersionRead } from './api/types.gen'
import { age } from './age'
import { Loading } from './Waiting'

export type DocumentKind = DocumentVersionRead['kind']

export const DOCUMENTS: Record<DocumentKind, { title: string; hint: string }> = {
  'career-profile': {
    title: 'Career Profile',
    hint: 'Everything you have done: experience, projects and skills. Leave nothing out; this is not a two-page resume.',
  },
  preferences: {
    title: 'Preferences',
    hint: 'What you are looking for and how to weigh it: target roles, level, what appeals and what you would rather avoid. Preferences never disqualify a posting on their own.',
  },
  'writing-guide': {
    title: 'Writing Guide',
    hint: 'How your Cover Letters should read: tone, length, structure, phrases to avoid, and one or two sample letters you are happy with.',
  },
}

export function DocumentPage({ kind }: { kind: DocumentKind }) {
  const current = useQuery(getCurrentDocumentOptions({ path: { kind } }))
  const { title, hint } = DOCUMENTS[kind]

  return (
    <section>
      <h2>{title}</h2>
      <p>{hint}</p>
      {current.isPending && <Loading />}
      {current.isError && <p role="alert">Could not load the {title}.</p>}
      {current.isSuccess && (
        // A new key resets the form to the saved text after each save
        <DocumentForm key={current.data?.id ?? 'unwritten'} kind={kind} current={current.data} />
      )}
    </section>
  )
}

function DocumentForm({ kind, current }: { kind: DocumentKind; current: DocumentVersionRead | null }) {
  const queryClient = useQueryClient()
  const savedText = current?.text ?? ''
  const [text, setText] = useState(savedText)
  const save = useMutation({
    ...saveDocumentMutation(),
    onSuccess: (version) =>
      queryClient.setQueryData(getCurrentDocumentQueryKey({ path: { kind } }), version),
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    save.mutate({ path: { kind }, body: { text } })
  }

  return (
    <form className="panel" onSubmit={submit}>
      <p className="hint">
        {current
          ? `Version ${current.number}, saved ${age(current.created_at)}.`
          : 'Not written yet.'}
      </p>
      <textarea
        className="document"
        aria-label={DOCUMENTS[kind].title}
        rows={24}
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
      <button type="submit" disabled={save.isPending || text === savedText} aria-busy={save.isPending}>
        {save.isPending ? 'Saving…' : 'Save as a new version'}
      </button>
      {save.isError && <p role="alert">Could not save. Try again.</p>}
    </form>
  )
}
