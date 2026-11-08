import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { age } from './age'
import {
  deleteCoverLetterDraftMutation,
  generateCoverLetterMutation,
  getCoverLetterOptions,
  restoreCoverLetterDraftMutation,
  reviseCoverLetterMutation,
  saveCoverLetterDraftMutation,
} from './api/@tanstack/react-query.gen'
import type { CoverLetterDraftRead, CoverLetterRead } from './api/types.gen'
import { Badge } from './Badge'
import { refusal } from './refusal'
import { Loading, Working } from './Waiting'

type EvaluationCase = CoverLetterRead['evaluation']['case']

/** The question asked before generating from a missing or outdated Evaluation; none for a
 * current one. */
const CONFIRMATIONS: Record<EvaluationCase, string | null> = {
  current: null,
  missing:
    'This posting has no Evaluation, so the Cover Letter will be written without its green and ' +
    'red flags. Generate anyway?',
  outdated:
    'The posting has changed since its Evaluation, so the Cover Letter will use the flags of the ' +
    'old text as they are. Generate anyway?',
}

const ORIGINS: Record<CoverLetterDraftRead['origin'], string> = {
  generated: 'Generated',
  revised_in_words: 'Revised in words',
  edited_by_hand: 'Edited by hand',
}

const CASE_NOTES: Record<EvaluationCase, string> = {
  current: "with the Evaluation's flags",
  outdated: "with an outdated Evaluation's flags",
  missing: 'without flags: there was no Evaluation',
}

/** An Application's Cover Letter: its latest draft beside the requirements the Career
 * Profile does not support, every earlier draft, and, while Preparing, the actions that
 * make a new one: edit by hand, revise in words, regenerate, restore and delete. */
export function CoverLetter({ applicationId }: { applicationId: number }) {
  const queryClient = useQueryClient()
  const options = getCoverLetterOptions({ path: { application_id: applicationId } })
  const letter = useQuery({
    ...options,
    // Poll while the worker is writing a draft, unless it is stuck
    refetchInterval: (query) => {
      const generation = query.state.data?.generation
      const underWay = generation?.status === 'queued' || generation?.status === 'running'
      return underWay && !generation.stuck ? 1000 : false
    },
  })
  const handlers = {
    onSuccess: (found: CoverLetterRead) => queryClient.setQueryData(options.queryKey, found),
    // A refusal may mean the Evaluation's case or the Application's state changed
    onError: () => queryClient.invalidateQueries({ queryKey: options.queryKey }),
  }
  const generate = useMutation({ ...generateCoverLetterMutation(), ...handlers })
  const revise = useMutation({ ...reviseCoverLetterMutation(), ...handlers })
  const save = useMutation({ ...saveCoverLetterDraftMutation(), ...handlers })
  const restore = useMutation({ ...restoreCoverLetterDraftMutation(), ...handlers })
  const remove = useMutation({ ...deleteCoverLetterDraftMutation(), ...handlers })
  const [instruction, setInstruction] = useState('')

  if (letter.isPending) return <Loading label="Loading the Cover Letter…" />
  if (letter.isError) return <p role="alert">Could not load the Cover Letter.</p>
  const { draft, drafts, generation, evaluation, editable, posting_edited_since_draft, sent } =
    letter.data
  // A stuck request blocks nothing: requesting again replaces it
  const underWay =
    (generation?.status === 'queued' || generation?.status === 'running') && !generation.stuck
  const path = { application_id: applicationId }
  const mutations = [generate, revise, save, restore, remove]
  // While a draft is being written, a change to the latest one would be pushed down by it
  const busy = underWay || mutations.some((m) => m.isPending)
  const failed = mutations.find((m) => m.isError)

  /** Whether the user agrees to the Evaluation's case, asking for a missing or outdated one. */
  function confirmed() {
    const question = CONFIRMATIONS[evaluation.case]
    return !question || window.confirm(question)
  }

  /** Ask the LLM for a new draft from scratch. */
  function generateDraft(text: string) {
    if (!confirmed()) return
    generate.mutate({
      path,
      body: { evaluation_case: evaluation.case, instruction: text.trim() || null },
    })
  }

  /** Ask the LLM to revise the latest draft as `text` says. */
  function reviseDraft(text: string) {
    if (!confirmed()) return
    revise.mutate({ path, body: { evaluation_case: evaluation.case, instruction: text.trim() } })
  }

  function removeDraft(id: number) {
    if (!window.confirm('Delete this draft? It is hidden from the Cover Letter but kept.')) return
    remove.mutate({ path: { ...path, draft_id: id } })
  }

  return (
    <section>
      <h3>Cover Letter</h3>
      {posting_edited_since_draft && <Badge tone="warn">Posting edited since this draft</Badge>}
      {draft ? (
        <Draft
          key={draft.id}
          draft={draft}
          editable={editable && !busy}
          onSave={(text) => save.mutate({ path, body: { text } })}
        />
      ) : (
        <p className="missing">No Cover Letter yet.</p>
      )}
      {underWay && <Working>Writing a draft…</Working>}
      {generation?.stuck && (
        <p role="alert">Writing the last draft got stuck and never finished. Ask again.</p>
      )}
      {generation?.status === 'failed' && (
        <div role="alert">
          <p>
            The last draft could not be written, so the Cover Letter is as it was:{' '}
            {generation.failure?.reason}
          </p>
          {editable && (
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                generation.revised_draft_id !== null && generation.instruction
                  ? reviseDraft(generation.instruction)
                  : generateDraft(generation.instruction ?? '')
              }
            >
              Retry
            </button>
          )}
        </div>
      )}
      {editable ? (
        <form className="panel" onSubmit={(e) => e.preventDefault()}>
          <label>
            Instructions (optional when generating)
            <textarea
              rows={3}
              value={instruction}
              placeholder={
                draft
                  ? 'What to change: "shorter, and lead with the Kafka migration"'
                  : 'What to stress, or the language to write in'
              }
              onChange={(e) => setInstruction(e.target.value)}
            />
          </label>
          <div className="actions">
            {draft && (
              <button
                type="button"
                disabled={busy || !instruction.trim()}
                aria-busy={revise.isPending}
                onClick={() => reviseDraft(instruction)}
              >
                Revise this draft
              </button>
            )}
            <button
              type="button"
              disabled={busy}
              aria-busy={generate.isPending}
              onClick={() => generateDraft(instruction)}
            >
              {draft ? 'Regenerate from scratch' : 'Generate cover letter'}
            </button>
          </div>
          {evaluation.case !== 'current' && (
            <p className="hint">
              {evaluation.case === 'missing'
                ? 'The posting has no Evaluation: a new draft would have no flags.'
                : "The posting's Evaluation is outdated: a new draft would use its old flags."}
            </p>
          )}
        </form>
      ) : (
        <p className="hint">The Cover Letter is locked while the Application is not Preparing.</p>
      )}
      {sent && (
        <p className="hint">
          {sent.draft
            ? `Sent with the move to Applied ${age(sent.applied_at)}: the ${ORIGINS[
                sent.draft.origin
              ].toLowerCase()} draft from ${age(sent.draft.created_at)}.`
            : `No Cover Letter sent: moved to Applied ${age(sent.applied_at)} without one.`}
        </p>
      )}
      {failed && <p role="alert">{refusal(failed.error) ?? 'Could not do that. Try again.'}</p>}
      {drafts.length > 1 && (
        <details>
          <summary>Earlier drafts ({drafts.length - 1})</summary>
          <ul>
            {drafts.slice(1).map((earlier) => (
              <EarlierDraft
                key={earlier.id}
                draft={earlier}
                editable={editable && !busy}
                onRestore={() => restore.mutate({ path: { ...path, draft_id: earlier.id } })}
                onDelete={() => removeDraft(earlier.id)}
              />
            ))}
          </ul>
        </details>
      )}
      {editable && draft && (
        <div className="actions">
          <button type="button" disabled={busy} onClick={() => removeDraft(draft.id)}>
            Delete the latest draft
          </button>
        </div>
      )}
    </section>
  )
}

function Record({ draft }: { draft: CoverLetterDraftRead }) {
  return (
    <p className="hint">
      {ORIGINS[draft.origin]} {age(draft.created_at)}{' '}
      {draft.evaluation_case && CASE_NOTES[draft.evaluation_case]}
      {draft.instruction && <> · instructions: “{draft.instruction}”</>}
      {draft.restored_from_draft_id !== null && <> · restored</>}
    </p>
  )
}

function Draft({
  draft,
  editable,
  onSave,
}: {
  draft: CoverLetterDraftRead
  editable: boolean
  onSave: (text: string) => void
}) {
  const [copied, setCopied] = useState<boolean | null>(null)
  const [editing, setEditing] = useState<string | null>(null)

  async function copy() {
    try {
      await navigator.clipboard.writeText(draft.text)
      setCopied(true)
    } catch {
      setCopied(false) // the browser refused; the text can still be selected by hand
    }
  }

  return (
    <div className="confirmation">
      <div>
        <Record draft={draft} />
        {editing !== null ? (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              onSave(editing)
            }}
          >
            <textarea rows={16} value={editing} onChange={(e) => setEditing(e.target.value)} />
            <div className="actions">
              <button
                type="submit"
                disabled={!editable || !editing.trim() || editing === draft.text}
              >
                Save as a new draft
              </button>
              <button type="button" onClick={() => setEditing(null)}>
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <>
            <div className="description letter">{draft.text}</div>
            <div className="actions">
              <button type="button" onClick={copy}>
                Copy text
              </button>
              {editable && (
                <button type="button" onClick={() => setEditing(draft.text)}>
                  Edit by hand
                </button>
              )}
              {copied === true && <span className="hint">Copied</span>}
              {copied === false && (
                <span role="alert">Could not copy: select the text instead.</span>
              )}
            </div>
          </>
        )}
      </div>
      <aside className="panel">
        <h4>Not supported by your Career Profile</h4>
        {draft.unsupported_requirements.length === 0 ? (
          <p className="missing">Nothing: the profile supports every requirement found.</p>
        ) : (
          <ul>
            {draft.unsupported_requirements.map((requirement, i) => (
              <li key={i}>{requirement}</li>
            ))}
          </ul>
        )}
        {draft.model !== null && (
          <p className="hint">
            {draft.model} · prompt {draft.prompt_version} · Career Profile v
            {draft.career_profile_version_number}
            {draft.writing_guide_version_number !== null
              ? ` · Writing Guide v${draft.writing_guide_version_number}`
              : ' · no Writing Guide'}
          </p>
        )}
      </aside>
    </div>
  )
}

function EarlierDraft({
  draft,
  editable,
  onRestore,
  onDelete,
}: {
  draft: CoverLetterDraftRead
  editable: boolean
  onRestore: () => void
  onDelete: () => void
}) {
  return (
    <li>
      <Record draft={draft} />
      <details>
        <summary>Text</summary>
        <div className="description letter">{draft.text}</div>
      </details>
      {editable && (
        <div className="actions">
          <button type="button" onClick={onRestore}>
            Restore as the latest draft
          </button>
          <button type="button" onClick={onDelete}>
            Delete
          </button>
        </div>
      )}
    </li>
  )
}
