# One adapter per LLM Provider, each on the Provider's official SDK

The app calls Anthropic, OpenAI and Google models through the existing `Llm` interface, with one adapter per Provider built on that Provider's official Python SDK (`anthropic`, `openai`, `google-genai`). Each run uses the adapter for the Provider it was queued with. We chose this over a multi-provider library (LiteLLM, pydantic-ai) because those reduce every Provider to a common subset. The features we rely on differ between Providers: prompt caching (explicit breakpoints on Anthropic, automatic on OpenAI, implicit on Gemini), reasoning controls (each Provider has its own effort or thinking levels), structured-output schema dialects, and what the model listing reports. A shared library would hide these, or expose them through a second layer of options that are specific to each Provider anyway. Its capability data is also a community-maintained table rather than the Provider's own. We accept writing and maintaining three adapters, and a set of filtering rules per Provider for the models it lists.

## Consequences

- Each adapter turns the step's schema into its Provider's dialect, and every answer still goes through the same checks in code. A Provider that cannot express a schema gets a `rejected` failure, never a looser check: the refusal is the same on every attempt, so the run fails at once without retrying.
- Adding a Provider means writing an adapter and its model filtering rules. Nothing outside the LLM layer changes.
- Effort levels are stored and shown under each Provider's own names. There is no shared effort scale.
