import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { age } from './age'
import {
  getSetupQueryKey,
  listProvidersOptions,
  listProvidersQueryKey,
  removeProviderKeyMutation,
  saveProviderKeyMutation,
} from './api/@tanstack/react-query.gen'
import type { Provider, ProviderRead } from './api/types.gen'
import { Badge } from './Badge'
import { refusal } from './refusal'
import { Loading } from './Waiting'

/** The Settings page: how the app is set up to run. */
export function SettingsPage() {
  return (
    <section>
      <h2>Settings</h2>
      <ProvidersSection />
    </section>
  )
}

/** Every change to a key can set the app up, or undo it, so the setup gate asks again. */
function useKeyChanged() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: listProvidersQueryKey() }),
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

/** The only screen until a Provider is set up: pick a Provider and give its key. */
export function SetupScreen() {
  const providers = useQuery(listProvidersOptions())
  const available = providers.data?.filter((provider) => provider.available) ?? []
  const [chosen, setChosen] = useState<Provider | null>(null)
  const provider = available.find((p) => p.provider === chosen) ?? available[0]

  return (
    <main className="setup">
      <h1>
        <span className="brand-mark" aria-hidden="true">
          ◆
        </span>{' '}
        Set up Job Scout
      </h1>
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
    </main>
  )
}
