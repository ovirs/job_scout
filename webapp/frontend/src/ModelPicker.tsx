import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { listDefaultsOptions, listOfferedModelsOptions } from './api/@tanstack/react-query.gen'
import type { ModelChoiceBody, OfferedModelRead, Step } from './api/types.gen'
import { ModelChoiceFields, modelLabel, validChoice } from './ModelChoiceFields'

/** The model choice of a run the user is about to start, and how to change it. */
export type RunChoice = {
  models: OfferedModelRead[]
  // Null until the models offered and the defaults load, and while no model is offered: the
  // run then takes its step's default
  choice: ModelChoiceBody | null
  pick: (choice: ModelChoiceBody) => void
  // The choice it would have started with, when that can no longer be used and `choice` is
  // another: the picker says so, rather than switch models silently
  replaced: ModelChoiceBody | null
}

/** The model choice for a run of `step`: pre-selected with `kept`, the choice of the run a
 * retry repeats, or else with the step's default, until the user picks another. */
export function useRunChoice(step: Step, kept: ModelChoiceBody | null = null): RunChoice {
  const offered = useQuery(listOfferedModelsOptions())
  const defaults = useQuery(listDefaultsOptions())
  const [picked, setPicked] = useState<ModelChoiceBody | null>(null)
  const models = offered.data ?? []
  const preselected = kept ?? defaults.data?.find((entry) => entry.step === step)?.choice ?? null
  const choice = offered.data && defaults.data ? validChoice(models, picked ?? preselected) : null
  const replaced =
    choice && !picked && preselected && !sameChoice(choice, preselected) ? preselected : null
  return { models, choice, pick: setPicked, replaced }
}

function sameChoice(a: ModelChoiceBody, b: ModelChoiceBody) {
  return a.provider === b.provider && a.model === b.model && (a.effort ?? null) === (b.effort ?? null)
}

/** A compact picker of the Provider's model, and its effort where it has one, placed next to
 * the button that starts the run. */
export function ModelPicker({ run }: { run: RunChoice }) {
  if (!run.choice) return null
  const { replaced } = run
  return (
    <>
      {replaced && (
        <p role="alert">
          {modelLabel(replaced.provider, replaced.model, replaced.effort ?? null)} can no longer
          be used: check the model picked instead.
        </p>
      )}
      <div className="model-picker">
        <ModelChoiceFields models={run.models} value={run.choice} onChange={run.pick} />
      </div>
    </>
  )
}
