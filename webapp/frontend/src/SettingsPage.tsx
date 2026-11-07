import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import {
  getSetupStatusQueryKey,
  listProvidersOptions,
  listProvidersQueryKey,
  removeProviderKeyMutation,
  saveProviderKeyMutation,
} from './api/@tanstack/react-query.gen'
import type { ProviderRead } from './api/types.gen'
import { age } from './age'
import { Loading } from './Waiting'

const PROVIDER_NAMES: Record<ProviderRead['provider'], string> = {
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  google: 'Google',
}

/** The page of the user's settings: for now the Providers they have a key for. */
export function SettingsPage() {
  const providers = useQuery(listProvidersOptions())

  return (
    <section>
      <h2>Settings</h2>
      <h3>Providers</h3>
      <p>
        Job Scout calls the LLM with your own key for a Provider. The key is kept as you type it,
        in this app's database; only its last characters are ever shown again.
      </p>
      {providers.isPending && <Loading />}
      {providers.isError && <p role="alert">Could not load the Providers.</p>}
      {providers.data?.map((provider) => (
        <ProviderPanel key={provider.provider} provider={provider} />
      ))}
    </section>
  )
}

/** The screen that blocks the app until the user has a Provider. */
export function SetupScreen() {
  const providers = useQuery(listProvidersOptions())
  const available = providers.data?.filter((provider) => provider.available) ?? []

  return (
    <main className="setup">
      <h1>Welcome to Job Scout</h1>
      <p>
        To start, add an API key for a Provider. Job Scout uses it to read, evaluate and write for
        you; nothing works without one.
      </p>
      {providers.isPending && <Loading />}
      {providers.isError && <p role="alert">Could not load the Providers.</p>}
      {available.length > 0 && <KeyForm providers={available} />}
    </main>
  )
}

function ProviderPanel({ provider }: { provider: ProviderRead }) {
  const name = PROVIDER_NAMES[provider.provider]
  const hasKey = provider.masked_key !== null
  const remove = useRemoveKey()

  function confirmRemove() {
    const lastWarning = 'Without a key for a Provider, Job Scout asks you to add one again.'
    if (window.confirm(`Remove the ${name} key?\n\n${lastWarning}`))
      remove.mutate({ path: { provider: provider.provider } })
  }

  return (
    <div className="panel" role="group" aria-label={name}>
      <h4>{name}</h4>
      {!provider.available && <p>Not available yet.</p>}
      {provider.available && hasKey && provider.saved_at && (
        <p>
          Key <code>{provider.masked_key}</code>, saved {age(provider.saved_at)}.
        </p>
      )}
      {provider.available && !hasKey && <p>No key yet.</p>}
      {provider.available && <KeyForm providers={[provider]} replacing={hasKey} />}
      {hasKey && (
        <div className="actions">
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
      {remove.isError && <p role="alert">Could not remove the key. Try again.</p>}
    </div>
  )
}

function useRemoveKey() {
  const refresh = useRefreshProviders()
  return useMutation({ ...removeProviderKeyMutation(), onSuccess: refresh })
}

/** Whatever changed a key: the Providers and whether the user has one at all are read again. */
function useRefreshProviders() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: listProvidersQueryKey() }),
      queryClient.invalidateQueries({ queryKey: getSetupStatusQueryKey() }),
    ])
}

/** The Provider's reason for refusing a key, which the API returns as the error's `detail`. */
function refusalReason(error: unknown): string {
  const detail = (error as { detail?: unknown } | null)?.detail
  return typeof detail === 'string' ? detail : 'Could not save the key. Try again.'
}

function KeyForm({ providers, replacing = false }: { providers: ProviderRead[]; replacing?: boolean }) {
  const refresh = useRefreshProviders()
  const [provider, setProvider] = useState(providers[0].provider)
  const [key, setKey] = useState('')
  const save = useMutation({
    ...saveProviderKeyMutation(),
    onSuccess: () => {
      setKey('')
      return refresh()
    },
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    save.mutate({ path: { provider }, body: { key } })
  }

  return (
    <form onSubmit={submit}>
      {providers.length > 1 && (
        <label>
          Provider
          <select value={provider} onChange={(event) => setProvider(event.target.value as typeof provider)}>
            {providers.map((entry) => (
              <option key={entry.provider} value={entry.provider}>
                {PROVIDER_NAMES[entry.provider]}
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        {replacing ? 'New API key' : 'API key'}
        <input
          type="password"
          autoComplete="off"
          required
          value={key}
          onChange={(event) => setKey(event.target.value)}
        />
      </label>
      <button type="submit" disabled={save.isPending || key.trim() === ''} aria-busy={save.isPending}>
        {save.isPending ? 'Checking the key…' : replacing ? 'Replace key' : 'Save key'}
      </button>
      {save.isError && <p role="alert">{refusalReason(save.error)}</p>}
    </form>
  )
}
