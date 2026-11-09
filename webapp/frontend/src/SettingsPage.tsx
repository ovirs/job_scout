import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { age } from './age'
import {
  getSetupQueryKey,
  hideModelMutation,
  listDefaultsOptions,
  listDefaultsQueryKey,
  listModelsOptions,
  listModelsQueryKey,
  listOfferedModelsOptions,
  listOfferedModelsQueryKey,
  listProvidersOptions,
  listProvidersQueryKey,
  refreshModelsMutation,
  removeProviderKeyMutation,
  saveDefaultsMutation,
  saveProviderKeyMutation,
  saveShowSnapshotsMutation,
  unhideModelMutation,
} from './api/@tanstack/react-query.gen'
import type {
  DefaultRead,
  ModelChoiceBody,
  ModelRead,
  OfferedModelRead,
  Provider,
  ProviderModelsRead,
  ProviderRead,
} from './api/types.gen'
import { Badge } from './Badge'
import { ModelChoiceFields, offeredModel, validChoice } from './ModelChoiceFields'
import { refusal } from './refusal'
import { Loading } from './Waiting'

/** The Settings page: how the app is set up to run. */
export function SettingsPage() {
  return (
    <section>
      <h2>Settings</h2>
      <ProvidersSection />
      <ModelsSection />
      <DefaultsSection />
    </section>
  )
}

/** Every change to a key can set the app up, or undo it, so the setup gate asks again; a
 * saved key also lists its Provider's models, and a removed one takes them away. */
function useKeyChanged() {
  const queryClient = useQueryClient()
  const modelsChanged = useModelsChanged()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: listProvidersQueryKey() }),
      queryClient.invalidateQueries({ queryKey: getSetupQueryKey() }),
      modelsChanged(),
    ])
}

/** Every change to the models offered shows in Settings and in every picker, and can make a
 * step's default usable or not. */
function useModelsChanged() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: listModelsQueryKey() }),
      queryClient.invalidateQueries({ queryKey: listOfferedModelsQueryKey() }),
      queryClient.invalidateQueries({ queryKey: listDefaultsQueryKey() }),
    ])
}

/** Saving defaults shows in Settings, and can finish setting the app up. */
function useDefaultsChanged() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: listDefaultsQueryKey() }),
      queryClient.invalidateQueries({ queryKey: getSetupQueryKey() }),
    ])
}

function ProvidersSection() {
  const providers = useQuery(listProvidersOptions())

  return (
    <>
      <h3>Providers</h3>
      <p>
        The companies whose models the app calls, with your API key for each. You need only one.
        A key is checked with the Provider before it is saved, and is never shown in full again.
      </p>
      {providers.isPending && <Loading />}
      {providers.isError && <p role="alert">Could not load the Providers.</p>}
      {providers.data && (
        <ul className="rows" aria-label="Providers">
          {providers.data.map((provider) => (
            <ProviderItem key={provider.provider} provider={provider} />
          ))}
        </ul>
      )}
    </>
  )
}

function ProviderItem({ provider }: { provider: ProviderRead }) {
  const keyChanged = useKeyChanged()
  const [replacing, setReplacing] = useState(false)
  const remove = useMutation({ ...removeProviderKeyMutation(), onSuccess: keyChanged })
  const path = { provider: provider.provider }

  function confirmRemove() {
    const last = 'If it is your only Provider, the app returns to the setup screen.'
    if (window.confirm(`Remove your ${provider.name} key?\n\n${last}`)) remove.mutate({ path })
  }

  if (!provider.available) {
    return (
      <li>
        <strong>{provider.name}</strong> <Badge>Not available yet</Badge>
      </li>
    )
  }

  return (
    <li aria-label={provider.name}>
      <strong>{provider.name}</strong>{' '}
      {provider.key ? (
        <>
          <code>{provider.key.masked}</code>, saved {age(provider.key.saved_at)}
        </>
      ) : (
        <span className="missing">No key</span>
      )}
      {provider.key && !replacing && (
        <div className="actions">
          <button type="button" onClick={() => setReplacing(true)}>
            Replace key
          </button>
          <button
            type="button"
            onClick={confirmRemove}
            disabled={remove.isPending}
            aria-busy={remove.isPending}
          >
            Remove key
          </button>
        </div>
      )}
      {(!provider.key || replacing) && (
        <KeyForm
          provider={provider.provider}
          name={provider.name}
          onSaved={() => setReplacing(false)}
          onCancel={provider.key ? () => setReplacing(false) : undefined}
        />
      )}
      {remove.isError && <p role="alert">Could not remove the key. Try again.</p>}
    </li>
  )
}

function ModelsSection() {
  const queryClient = useQueryClient()
  const modelsChanged = useModelsChanged()
  const models = useQuery(listModelsOptions())
  const refresh = useMutation({
    ...refreshModelsMutation(),
    onSuccess: async (refreshed) => {
      queryClient.setQueryData(listModelsQueryKey(), refreshed)
      await queryClient.invalidateQueries({ queryKey: listOfferedModelsQueryKey() })
    },
  })
  const snapshots = useMutation({ ...saveShowSnapshotsMutation(), onSuccess: modelsChanged })

  return (
    <>
      <h3>Models</h3>
      <p>
        The models your Providers list for your keys, less those for images, video, audio,
        speech, embeddings and moderation. The list is fetched again each day; refresh it to see
        a model released today. Hide any model you do not want offered.
      </p>
      {models.isPending && <Loading />}
      {models.isError && <p role="alert">Could not load the models.</p>}
      {models.data && (
        <>
          <div className="toolbar">
            <label className="check">
              <input
                type="checkbox"
                checked={models.data.show_snapshots}
                disabled={snapshots.isPending}
                onChange={(event) =>
                  snapshots.mutate({ body: { show_snapshots: event.target.checked } })
                }
              />
              Show dated snapshots, such as <code>gpt-5-2025-08-07</code>
            </label>
            <button
              type="button"
              onClick={() => refresh.mutate({})}
              disabled={refresh.isPending}
              aria-busy={refresh.isPending}
            >
              {refresh.isPending ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
          {snapshots.isError && <p role="alert">Could not save that. Try again.</p>}
          {refresh.isError && <p role="alert">Could not refresh the models. Try again.</p>}
          {models.data.providers.length === 0 && (
            <p className="missing">Add a Provider's key to list its models.</p>
          )}
          {models.data.providers.map((provider) => (
            <ProviderModels key={provider.provider} provider={provider} />
          ))}
        </>
      )}
    </>
  )
}

function ProviderModels({ provider }: { provider: ProviderModelsRead }) {
  return (
    <>
      <h4>
        {provider.name}{' '}
        {provider.fetched_at && (
          <span className="missing">listed {age(provider.fetched_at)}</span>
        )}
      </h4>
      {provider.refused && <p role="alert">{provider.refused}</p>}
      {provider.models.length === 0 ? (
        <p className="missing">No models listed.</p>
      ) : (
        <ul className="rows" aria-label={`${provider.name} models`}>
          {provider.models.map((model) => (
            <ModelItem key={model.id} model={model} />
          ))}
        </ul>
      )}
    </>
  )
}

function ModelItem({ model }: { model: ModelRead }) {
  const modelsChanged = useModelsChanged()
  const hide = useMutation({ ...hideModelMutation(), onSuccess: modelsChanged })
  const unhide = useMutation({ ...unhideModelMutation(), onSuccess: modelsChanged })
  const path = { provider: model.provider, model_id: model.id }
  const pending = hide.isPending || unhide.isPending

  return (
    <li aria-label={model.display_name}>
      <strong>{model.display_name}</strong> <code>{model.id}</code>{' '}
      {model.snapshot && <Badge>Snapshot</Badge>} {model.hidden && <Badge tone="warn">Hidden</Badge>}
      {model.efforts.length > 0 && <p className="summary">Effort: {model.efforts.join(', ')}</p>}
      <div className="actions">
        <button
          type="button"
          onClick={() => (model.hidden ? unhide : hide).mutate({ path })}
          disabled={pending}
          aria-busy={pending}
        >
          {model.hidden ? 'Offer again' : 'Hide'}
        </button>
      </div>
      {(hide.isError || unhide.isError) && <p role="alert">Could not save that. Try again.</p>}
    </li>
  )
}

function DefaultsSection() {
  const defaults = useQuery(listDefaultsOptions())
  const offered = useQuery(listOfferedModelsOptions())

  return (
    <>
      <h3>Defaults</h3>
      <p>
        The model each step runs with, and its effort where the model has one. A run takes its
        step's default when it is queued, and never switches to another model on its own.
      </p>
      {(defaults.isPending || offered.isPending) && <Loading />}
      {(defaults.isError || offered.isError) && <p role="alert">Could not load the defaults.</p>}
      {defaults.data && offered.data && (
        <ul className="rows" aria-label="Defaults">
          {defaults.data.map((entry) => (
            <DefaultItem key={entry.step} entry={entry} models={offered.data} />
          ))}
        </ul>
      )}
    </>
  )
}

function DefaultItem({ entry, models }: { entry: DefaultRead; models: OfferedModelRead[] }) {
  const defaultsChanged = useDefaultsChanged()
  const [choice, setChoice] = useState<ModelChoiceBody | null>(entry.choice)
  const valid = validChoice(models, choice)
  const save = useMutation({ ...saveDefaultsMutation(), onSuccess: defaultsChanged })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (valid) save.mutate({ body: { [entry.step]: valid } })
  }

  return (
    <li aria-label={entry.name}>
      <strong>{entry.name}</strong>{' '}
      {entry.choice ? (
        <ChoiceText choice={entry.choice} models={models} />
      ) : (
        <span className="missing">None chosen</span>
      )}
      {entry.choice && entry.problem && (
        <p role="alert">
          This default cannot be used: {entry.problem}. Runs of this step fail until you choose
          another.
        </p>
      )}
      {valid ? (
        <form onSubmit={submit}>
          <ModelChoiceFields models={models} value={valid} onChange={setChoice} />
          <div className="actions">
            <button type="submit" disabled={save.isPending} aria-busy={save.isPending}>
              Save
            </button>
          </div>
          {save.isError && (
            <p role="alert">{refusal(save.error) ?? 'Could not save the default. Try again.'}</p>
          )}
        </form>
      ) : (
        <p className="missing">No models are offered: add a Provider's key, or offer one again.</p>
      )}
    </li>
  )
}

/** A model choice as text: the model's name when it is offered, its id and the effort. */
function ChoiceText({ choice, models }: { choice: ModelChoiceBody; models: OfferedModelRead[] }) {
  const model = offeredModel(models, choice)
  return (
    <span>
      {model ? `${model.display_name} ` : ''}
      <code>{choice.model}</code>,{' '}
      {choice.effort ? `effort ${choice.effort}` : 'Provider default effort'}
    </span>
  )
}

/** Saves a Provider's key once the Provider accepts it; shows the Provider's reason if not. */
export function KeyForm({
  provider,
  name,
  onSaved,
  onCancel,
}: {
  provider: Provider
  name: string
  onSaved?: () => void
  onCancel?: () => void
}) {
  const keyChanged = useKeyChanged()
  const [apiKey, setApiKey] = useState('')
  const save = useMutation({
    ...saveProviderKeyMutation(),
    onSuccess: async () => {
      setApiKey('')
      await keyChanged()
      onSaved?.()
    },
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    save.mutate({ path: { provider }, body: { api_key: apiKey } })
  }

  return (
    <form onSubmit={submit}>
      <label>
        {name} API key
        <input
          type="password"
          autoComplete="off"
          required
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
        />
      </label>
      <div className="actions">
        <button
          type="submit"
          disabled={save.isPending || apiKey.trim() === ''}
          aria-busy={save.isPending}
        >
          {save.isPending ? 'Checking…' : 'Save key'}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
      {save.isError && (
        <p role="alert">{refusal(save.error) ?? 'Could not save the key. Try again.'}</p>
      )}
    </form>
  )
}

/** The only screen until the app is set up: first a Provider and its key, then the model every
 * step starts with. */
export function SetupScreen({ hasProvider }: { hasProvider: boolean }) {
  return (
    <main className="setup">
      <h1>
        <span className="brand-mark" aria-hidden="true">
          ◆
        </span>{' '}
        Set up Job Scout
      </h1>
      {hasProvider ? <DefaultsSetup /> : <ProviderSetup />}
    </main>
  )
}

/** One model and effort, saved as the default of every step. */
function DefaultsSetup() {
  const defaultsChanged = useDefaultsChanged()
  const offered = useQuery(listOfferedModelsOptions())
  const [choice, setChoice] = useState<ModelChoiceBody | null>(null)
  const valid = validChoice(offered.data ?? [], choice)
  const save = useMutation({ ...saveDefaultsMutation(), onSuccess: defaultsChanged })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (valid) save.mutate({ body: { extraction: valid, evaluation: valid, cover_letter: valid } })
  }

  return (
    <>
      <h2>Choose a default model</h2>
      <p>
        The model, and its effort where it has one, that reads, evaluates and writes. You can
        choose another for each step later in Settings.
      </p>
      {offered.isPending && <Loading />}
      {offered.isError && <p role="alert">Could not load the models.</p>}
      {offered.data && !valid && (
        <p className="missing">Your Provider lists no model the app can use.</p>
      )}
      {valid && (
        <form className="panel" onSubmit={submit}>
          <ModelChoiceFields models={offered.data ?? []} value={valid} onChange={setChoice} />
          <div className="actions">
            <button type="submit" disabled={save.isPending} aria-busy={save.isPending}>
              {save.isPending ? 'Saving…' : 'Use for every step'}
            </button>
          </div>
          {save.isError && (
            <p role="alert">{refusal(save.error) ?? 'Could not save the default. Try again.'}</p>
          )}
        </form>
      )}
    </>
  )
}

/** Pick a Provider and give its key. */
function ProviderSetup() {
  const providers = useQuery(listProvidersOptions())
  const available = providers.data?.filter((provider) => provider.available) ?? []
  const [chosen, setChosen] = useState<Provider | null>(null)
  const provider = available.find((p) => p.provider === chosen) ?? available[0]

  return (
    <>
      <p>
        Job Scout reads, evaluates and writes with an LLM. Add an API key for a Provider to start;
        you can add more, or change it, later in Settings.
      </p>
      {providers.isPending && <Loading />}
      {providers.isError && <p role="alert">Could not load the Providers.</p>}
      {provider && (
        <div className="panel">
          <label>
            Provider
            <select
              value={provider.provider}
              onChange={(event) => setChosen(event.target.value as Provider)}
            >
              {available.map((p) => (
                <option key={p.provider} value={p.provider}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <KeyForm key={provider.provider} provider={provider.provider} name={provider.name} />
        </div>
      )}
    </>
  )
}
