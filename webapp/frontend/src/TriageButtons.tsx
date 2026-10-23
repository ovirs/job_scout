import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getJobPostingQueryKey,
  listJobPostingsQueryKey,
  setJobPostingTriageMutation,
} from './api/@tanstack/react-query.gen'
import type { JobPostingRead, TriageSet } from './api/types.gen'

export const TRIAGE_LABELS: Record<TriageSet['value'], string> = {
  interested: 'Interested',
  maybe: 'Maybe',
  ignored: 'Ignored',
}

/** The user's own call on a posting, over whatever the Evaluation recommends. The current
 * value is pressed; pressing another changes it. Works before an Evaluation is done, and is
 * locked at Interested while the posting has a live Application. */
export function TriageButtons({ posting }: { posting: JobPostingRead }) {
  const queryClient = useQueryClient()
  const triage = useMutation({
    ...setJobPostingTriageMutation(),
    onSuccess: async (changed) => {
      queryClient.setQueryData(
        getJobPostingQueryKey({ path: { job_posting_id: changed.id } }),
        changed,
      )
      await queryClient.invalidateQueries({ queryKey: listJobPostingsQueryKey() })
    },
  })
  const path = { job_posting_id: posting.id }
  const locked = posting.application !== null

  return (
    <div className="actions">
      <div className="segmented" role="group" aria-label="Triage">
        {(Object.keys(TRIAGE_LABELS) as TriageSet['value'][]).map((value) => (
          <button
            key={value}
            type="button"
            className={`triage ${value}`}
            aria-pressed={posting.triage?.value === value}
            disabled={triage.isPending || locked}
            onClick={() => triage.mutate({ path, body: { value } })}
          >
            {TRIAGE_LABELS[value]}
          </button>
        ))}
      </div>
      {locked && <span className="hint">Locked while you have an Application</span>}
      {triage.isError && <p role="alert">Could not save. Try again.</p>}
    </div>
  )
}
