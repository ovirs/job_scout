import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { age } from './age'
import { generateCoverLetterMutation, getCoverLetterOptions } from './api/@tanstack/react-query.gen'
import type { CoverLetterDraftRead, CoverLetterRead } from './api/types.gen'

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

/** The detail the API gives for a refused request, if it gives one. */
function refusal(error: unknown): string | null {
  const detail = (error as { detail?: unknown } | null)?.detail
  return typeof detail === 'string' ? detail : null
}

/** An Application's Cover Letter: its latest draft beside the requirements the Career
 * Profile does not support, and, while Preparing, the action that generates a new one. */
export function CoverLetter({ applicationId }: { applicationId: number }) {
  const queryClient = useQueryClient()
  const options = getCoverLetterOptions({ path: { application_id: applicationId } })
  const letter = useQuery({
    ...options,
    // Poll while the worker is writing a draft
    refetchInterval: (query) => {
      const status = query.state.data?.generation?.status
      return status === 'queued' || status === 'running' ? 1000 : false
    },
  })
  const generate = useMutation({
    ...generateCoverLetterMutation(),
    onSuccess: (found) => queryClient.setQueryData(options.queryKey, found),
    // A refusal may mean the Evaluation's case changed: show the one it is now
    onError: () => queryClient.invalidateQueries({ queryKey: options.queryKey }),
  })
  const [instruction, setInstruction] = useState('')

  if (letter.isPending) return <p>Loading the Cover Letter…</p>
  if (letter.isError) return <p role="alert">Could not load the Cover Letter.</p>
  const { draft, generation, evaluation, editable } = letter.data
  const underWay = generation?.status === 'queued' || generation?.status === 'running'

  function request(text: string) {
    const question = CONFIRMATIONS[evaluation.case]
    if (question && !window.confirm(question)) return
    generate.mutate({
      path: { application_id: applicationId },
      body: { evaluation_case: evaluation.case, instruction: text.trim() || null },
    })
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    request(instruction)
  }

  return (
    <section>
      <h3>Cover Letter</h3>
      {draft ? <Draft key={draft.id} draft={draft} /> : <p className="missing">No Cover Letter yet.</p>}
      {underWay && <p>Writing a draft…</p>}
      {generation?.status === 'failed' && (
        <div role="alert">
          <p>
            The last draft could not be written, so the Cover Letter is as it was:{' '}
            {generation.failure?.reason}
          </p>
          {editable && (
            <button
              type="button"
              disabled={generate.isPending}
              onClick={() => request(generation.instruction ?? '')}
            >
              Retry
            </button>
          )}
        </div>
      )}
      {editable ? (
        <form onSubmit={submit}>
          <label>
            Instructions for this Cover Letter (optional)
            <textarea
              rows={3}
              value={instruction}
              placeholder="What to stress, or the language to write in"
              onChange={(e) => setInstruction(e.target.value)}
            />
          </label>
          <div className="actions">
            <button type="submit" disabled={generate.isPending || underWay}>
              Generate cover letter
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
      {generate.isError && (
        <p role="alert">{refusal(generate.error) ?? 'Could not ask for a draft. Try again.'}</p>
      )}
    </section>
  )
}

function Draft({ draft }: { draft: CoverLetterDraftRead }) {
  const [copied, setCopied] = useState<boolean | null>(null)

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
        <p className="hint">
          {ORIGINS[draft.origin]} {age(draft.created_at)}{' '}
          {draft.evaluation_case && CASE_NOTES[draft.evaluation_case]}
          {draft.instruction && <> · instructions: “{draft.instruction}”</>}
        </p>
        <div className="description letter">{draft.text}</div>
        <div className="actions">
          <button type="button" onClick={copy}>
            Copy text
          </button>
          {copied === true && <span className="hint">Copied</span>}
          {copied === false && <span role="alert">Could not copy: select the text instead.</span>}
        </div>
      </div>
      <aside>
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
        <p className="hint">
          {draft.model} · prompt {draft.prompt_version} · Career Profile v
          {draft.career_profile_version_number}
          {draft.writing_guide_version_number !== null
            ? ` · Writing Guide v${draft.writing_guide_version_number}`
            : ' · no Writing Guide'}
        </p>
      </aside>
    </div>
  )
}
