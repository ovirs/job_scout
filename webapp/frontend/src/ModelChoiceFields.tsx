import type { ModelChoiceBody, OfferedModelRead } from './api/types.gen'

const PROVIDER_DEFAULT = ''

function key(provider: string, model: string) {
  return `${provider}/${model}`
}

/** The offered model a choice names, if it is offered. */
export function offeredModel(
  models: OfferedModelRead[],
  choice: ModelChoiceBody | null,
): OfferedModelRead | undefined {
  if (!choice) return undefined
  return models.find((m) => m.provider === choice.provider && m.id === choice.model)
}

/** The choice if its model is offered and takes its effort; otherwise the first model offered,
 * at the Provider's default effort; null when nothing is offered. */
export function validChoice(
  models: OfferedModelRead[],
  choice: ModelChoiceBody | null,
): ModelChoiceBody | null {
  const model = offeredModel(models, choice)
  if (choice && model) {
    const effort = choice.effort && model.efforts.includes(choice.effort) ? choice.effort : null
    return { ...choice, effort }
  }
  const first = models[0]
  return first ? { provider: first.provider, model: first.id, effort: null } : null
}

/** A model, and its effort where the model has an effort control, from the models offered.
 * `value` must be a valid choice among them (see `validChoice`). */
export function ModelChoiceFields({
  models,
  value,
  onChange,
}: {
  models: OfferedModelRead[]
  value: ModelChoiceBody
  onChange: (choice: ModelChoiceBody) => void
}) {
  const model = offeredModel(models, value)

  function chooseModel(chosen: string) {
    const found = models.find((m) => key(m.provider, m.id) === chosen)
    if (found) onChange({ provider: found.provider, model: found.id, effort: null })
  }

  return (
    <>
      <label>
        Model
        <select
          value={key(value.provider, value.model)}
          onChange={(e) => chooseModel(e.target.value)}
        >
          {models.map((m) => (
            <option key={key(m.provider, m.id)} value={key(m.provider, m.id)}>
              {m.display_name} ({m.id})
            </option>
          ))}
        </select>
      </label>
      {model && model.efforts.length > 0 && (
        <label>
          Effort
          <select
            value={value.effort ?? PROVIDER_DEFAULT}
            onChange={(e) => {
              const effort = e.target.value
              onChange({ ...value, effort: effort === PROVIDER_DEFAULT ? null : effort })
            }}
          >
            <option value={PROVIDER_DEFAULT}>Provider default</option>
            {model.efforts.map((effort) => (
              <option key={effort} value={effort}>
                {effort}
              </option>
            ))}
          </select>
        </label>
      )}
    </>
  )
}
