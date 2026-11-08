# LLM Providers: Settings, OpenAI and Gemini, and the model chosen per run

Status: ready-for-agent

Settled in a grilling session on 2026-11-06. See the [glossary](../../GLOSSARY.md) (Settings, Provider) and ADRs [0004](../../docs/adr/0004-backend-code-is-one-package-per-domain-concept.md), [0005](../../docs/adr/0005-one-adapter-per-llm-provider-on-its-official-sdk.md) and [0006](../../docs/adr/0006-provider-keys-are-stored-per-owner-unencrypted.md).

## Problem Statement

Every LLM step calls Anthropic. A single global API key, and the model and effort for each step, are read from environment variables. To set the app up, a user has to edit `.env`, and changing a model needs a restart. Nobody can use OpenAI or Google models, and the user cannot run a step with a different model to compare the results. The project is to be open-sourced for people to self-host, so a new user's first experience should not depend on editing files.

## Solution

Each user sets the app up on a new Settings page. They add an API key for at least one Provider (Anthropic, OpenAI or Google); the key is checked against the Provider before it is saved. The models offered come from each Provider's own model list, filtered to the text models the app can use. The user picks a default model, and an effort level where the model has one, for each LLM step: reading a Clipping, evaluating a Job Posting and writing a Cover Letter. Runs the user starts by hand get a model picker, pre-selected with that step's default. Runs that start on their own use the default. Every run records the Provider, model and effort it used, so its results can be compared in the history.

Until a user has a Provider set up, the app shows only the setup screen.

## User Stories

### Setting up

1. As a new self-hoster, I want the app to open on a setup screen until I have added a Provider, so that I never meet an app where nothing works.
2. As the user, I want to add an API key for Anthropic, OpenAI or Google, and need only one of them, so that I can use whichever Provider I already pay for.
3. As the user, I want a key checked against its Provider before it is saved, and the Provider's reason shown when it is refused, so that a typo is caught at once rather than on my first run.
4. As the user, I want to choose one model (and effort) during setup and have it used for every step, so that setup is one decision rather than three.
5. As the user, I want to add more Providers later, from Settings, so that setting up a second one is optional.
6. As the user, I want to replace or remove a Provider's key in Settings without restarting anything, so that a rotated key takes effect on the next run.
7. As the user, I want a stored key shown only masked (for example `sk-…a1b2`), so that it is never displayed in full again.
8. As the user, I want removing my last Provider to send me back to the setup screen, so that the app is never left unable to run.

### Models

9. As the user, I want the models offered to be the ones my Providers list for my keys, so that new models appear without an update to the app.
10. As the user, I want image, video, audio, speech, embedding and moderation models left out, so that I only see models that can do the app's work.
11. As the user, I want only the moving model names (such as `gpt-5`) shown by default, and dated snapshots only when I turn them on in Settings, so that the list stays short.
12. As the user, I want to hide any model from the pickers in Settings, so that I can drop one the filtering let through, or one I do not want to use.
13. As the user, I want to refresh the model list from Settings, so that I can see a model the Provider released today.

### Defaults

14. As the user, I want a default model and effort for each step (extraction, evaluation, Cover Letter), set in Settings, so that each step uses what works best for it.
15. As the user, I want the effort control shown only for models that have one, offering that Provider's own levels plus "Provider default", so that I cannot pick something meaningless.
16. As the user, I want Settings to warn me when a step's default can no longer be used (its Provider's key is gone, or the model was retired or hidden), so that I fix it before a run fails.
17. As the user, I want a run that starts on its own while its step's default cannot be used to fail at once with a reason pointing me to Settings, and never switch to another model silently, so that every result comes from the model I chose.

### Choosing the model for a run

18. As the user, I want a model picker, pre-selected with the step's default, when I paste a Clipping, retry a Clipping, re-run an Evaluation, and generate or revise a Cover Letter, so that I can try another model on the spot.
19. As the user, I want the Evaluation that starts after I confirm a Clipping or start an Application to use the evaluation default, so that those flows ask me nothing new.
20. As the user, I want a retry to use the same Provider, model and effort as the run it retries unless I change them in the picker, so that a retry repeats what failed.
21. As the user, I want each Evaluation and each Cover Letter draft in the history labelled with its Provider, model and effort, so that I can compare models side by side.
22. As the user, I want the latest finished Evaluation to stay the current one, whatever model made it, so that the rule stays simple. If I prefer another model's judgement, I run it again with that model.
23. As the user, I want a run whose effort level the model does not accept to fail at once with the Provider's reason, without retrying, so that I can pick another level straight away.

### Upgrading

24. As the existing user, I want my existing runs labelled as Anthropic runs, so that the history stays correct.

## Implementation Decisions

### Settings and keys

- A new `settings` package (ADR 0004) owns the Provider keys and the step defaults. It sits low in the package order, since the LLM runs read it. Every row carries `owner_id`.
- Keys are stored as plain text (ADR 0006). The API never returns a key, only its masked form and when it was saved.
- Saving a key lists the Provider's models with it. A refused listing means the key is not saved, and the Provider's reason is returned.
- The environment variables `ANTHROPIC_API_KEY`, `*_MODEL` and `*_EFFORT` are removed from `Settings` (config), `compose.yaml` and the README. The environment holds only infrastructure. `LLM_RETRY_WAIT_SECONDS` stays.
- A Provider is available only once it has an adapter. Tickets 1 to 4 ship with Anthropic available, and the OpenAI and Gemini adapter tickets each make theirs available. Setup and Settings offer only available Providers.

### Setup gate

- The frontend asks the backend whether the owner has at least one Provider and a default set for every step. Until both are true, every route shows the setup screen.
- The setup screen asks for a Provider and key first. Then it asks for one model and effort, applied to all three steps.
- The backend refuses, with 409 and a reason, any request that would start an LLM run without a usable choice, so the gate is not only enforced in the UI.

### Model discovery

- Each Provider has a model lister next to its adapter. It returns a common shape: Provider, model id, display name, whether the model is a dated snapshot, and the effort levels it accepts (known levels for Anthropic, the Provider's full set for OpenAI and Gemini).
- Filtering:
  - **Anthropic:** active models that support structured outputs, from the listing's own capabilities. Effort levels come from `capabilities.effort`.
  - **OpenAI:** the listing has no capabilities. Keep known chat families (`gpt-*`, `o<digit>*`). Drop names marking other kinds of models (`-tts`, `-transcribe`, `-audio`, `-realtime`, `-image`, `-search`, `embedding`, `moderation`, `whisper`, `dall-e`, `sora`), and drop fine-tunes (`ft:`). A dated snapshot ends in `-YYYY-MM-DD`.
  - **Gemini:** keep models whose `supportedGenerationMethods` include `generateContent`. Drop names marking other kinds of models (`-tts`, `-image`, `-live`, `-audio`, `embedding`, `imagen`, `veo`, `lyria`, `robotics`). Dated and versioned names count as snapshots, while `-latest` and plain family names are moving names. Effort is offered when the listing's `thinking` is true.
- The rules are code, tested against saved sample listings. No model names are kept in the code.
- Each owner's filtered list is cached in the database for a day. It is fetched when a key is saved, when the cache is older than a day, and when the user presses Refresh.
- Hidden models and the "show snapshots" switch are per owner, and both apply to every picker.
- A model is **usable** for an owner when its Provider is available and has a key, and the model is in the cached list and not hidden.

### Effort

- Effort is stored and shown under each Provider's own names (ADR 0005). There is no shared scale. Null means the Provider's default.
- The adapters map effort as follows:
  - Anthropic: `output_config.effort`.
  - OpenAI: `reasoning.effort`.
  - Gemini: `thinkingConfig.thinkingLevel`.

### The choice on each run

- A **model choice** is (Provider, model, effort).
- Each run stores the choice it was queued with. The `LlmRun` columns gain the requested Provider, model and effort, set when the run is queued. `model` stays the id the Provider reports back. A new `provider` column records the Provider that answered.
- A migration fills in existing runs with Anthropic as their Provider and their stored model as the requested model.
- A run started by the user takes a choice in its request body. It defaults to the step's default when omitted, and is refused with 422 when the model is not usable.
- A run that starts on its own takes the step's default when it is queued. If that default is not usable, the run is failed at once with kind `missing_input`, a reason pointing to Settings, and no retry.
- A retry keeps the run's stored choice unless the request gives a new one. This covers the Clipping retry, which requeues the Clipping in place. Evaluation reruns and Cover Letter generations create new runs.
- Generating and revising a Cover Letter share the Cover Letter default.

### Calling the Providers

- One adapter per Provider, each on the official SDK: `anthropic`, `openai` (Responses API) and `google-genai` (ADR 0005). Each adapter implements the `Llm` interface.
- The worker no longer builds one client at startup. For each attempt, the run reads its owner's key for the run's Provider and calls that Provider's adapter. A key replaced while a run waits takes effect on its next attempt.
- Each adapter converts the step's Pydantic schema into its Provider's structured-output dialect. Every answer goes through the same checks as today. A schema the Provider refuses is a failure, never a looser check.
- Prompt caching follows each Provider's own mechanism: explicit `cache_control` on Anthropic as today, automatic on OpenAI (with a stable `prompt_cache_key` per owner and step), and implicit on Gemini.
- The adapters report a new failure kind, `rejected`. It covers a request the Provider refused as invalid: an unsupported effort level, an unknown model, a bad key. It fails the run at once, without retrying. Rate limits, timeouts and server errors stay `error` and are retried as today.
- An `Outcome` carries the Provider as well as the model.

### UI

- **Settings page:**
  - A Providers section: add, replace or remove a key, shown masked.
  - A Models section: the list per Provider, hide toggles, the snapshots switch and Refresh.
  - A Defaults section: model and effort per step, with a warning on a default that is not usable.
- **Model picker:** a compact control (Provider and model, plus effort when the model has one), placed next to the button of each run the user starts:
  - Add Posting
  - Clipping retry
  - Evaluation re-run
  - Cover Letter generate and revise
- The Evaluation history and the Cover Letter drafts show each one's Provider, model and effort.

## Testing Decisions

- API tests through the HTTP seam, against real Postgres, with fakes for the LLM and for the model listers, as today. A fake lister returns canned listings per Provider and can refuse a key.
- The filtering rules get unit tests over saved sample listings from each Provider, including the image, audio, embedding and snapshot entries they must drop or flag.
- Tested behaviour:
  - the setup gate (the backend's 409);
  - a key is refused when its listing fails;
  - keys are masked in every response;
  - a choice is refused when its model is not usable;
  - a run that starts on its own fails at once when its default is not usable;
  - a retry keeps its choice;
  - `rejected` fails without retrying;
  - existing runs are filled in by the migration.
- The real adapters stay out of automated tests, as the Anthropic adapter is today. Their schema conversion can be unit tested where it is pure code.
- The browser smoke test covers setup, from an empty database to a saved Clipping.

## Out of Scope

- Encrypting keys, login and anything a hosted service would need (ADR 0006).
- Running several models at once and showing their results side by side.
- Choosing which Evaluation is current.
- Comparing Clipping extractions (a retry still overwrites the result).
- Tracking the cost of runs.
- Providers other than Anthropic, OpenAI and Google, including local models.
- Importing a key from an old `.env`.

## Further Notes

- The facts about each Provider's model listing, effort controls, structured-output dialects and caching were read from the official docs on 2026-11-06. Only Anthropic's listing reports capabilities. Re-check the OpenAI and Gemini filtering rules whenever a Provider's catalogue changes shape.
