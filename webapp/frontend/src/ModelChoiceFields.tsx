import type { ModelChoiceBody, OfferedModelRead, Provider } from './api/types.gen'

export const PROVIDER_NAMES: Record<Provider, string> = {
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  google: 'Google',
}

const PROVIDER_DEFAULT = ''

/** What a run was made with, as text: its Provider, model and effort. */
export function modelLabel(provider: Provider, model: string, effort: string | null) {
  return `${PROVIDER_NAMES[provider]} ${model}, ${effort ? `effort ${effort}` : 'default effort'}`
}

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

/** A model, by Provider, and its effort where the model has an effort control, from the models
 * offered. `value` must be a valid choice among them (see `validChoice`). */
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
  const providers = [...new Set(models.map((m) => m.provider))]

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
          {providers.map((provider) => (
            <optgroup key={provider} label={PROVIDER_NAMES[provider]}>
              {models
                .filter((m) => m.provider === provider)
                .map((m) => (
                  <option key={key(m.provider, m.id)} value={key(m.provider, m.id)}>
                    {m.display_name} ({m.id})
                  </option>
                ))}
            </optgroup>
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
