# Jev for Screening: API, pricing, limits, calibration, data terms

Research for [issue 05](../issues/05-jev-for-screening.md). Checked 2026-10-27 against TypeSafe AI's own website, docs, legal pages, GitHub org and PyPI. I did not sign up, log in, or send any request to the API.

## Summary

Jev exists, and TypeSafe AI (typesafe.ai, TypeSafe AI, Inc.) is the right company. It has a public docs site, an OpenAPI-described HTTP API, an official Python SDK on PyPI and GitHub, and published legal terms. The API fits both Screening questions: post the title and location as `state`, and ask two `noul` (yes/no probability) questions in one request. The price in the docs is $0.042 per million input tokens with output free, matching the blog figure. At that price, screening costs a fraction of a cent per thousand postings. Five things remain unknown:

- Whether a new account gets API access straight away or still joins the launch waitlist. Finding out needs sign-up.
- The actual rate limits. They are set per organization and shown only in the logged-in console.
- Calibration on very short inputs. TypeSafe claims calibration in general, but publishes no calibration data or short-input guidance.
- A concrete retention period for API inputs.
- Whether an account can opt out of the telemetry it keeps "in perpetuity".

## How is access obtained during early access, and is there a Python client?

**Confirmed from TypeSafe's docs and site**

- **Getting a key:** the quickstart says to "Get an API key from the TypeSafe console" (console.typesafe.ai). The console redirects to a login page ("Sign in or create an account through Google or your email"). Continuing means accepting the Master Customer Agreement and the Privacy Policy.
- **Early access:** the homepage still says "Try our first System One Model, Jev, in early access". The launch post (Diogo Almeida, 2026-09-15) said: "Today, we are opening early access and bringing developers off the waitlist as quickly as we can."
- **Billing:** the MCA requires prepaid credits consumed per Input, with optional auto-refill. It also mentions "Promotional Credits" issued at TypeSafe's discretion. No free tier is stated.
- **Python client:** `typesafe-sdk` on PyPI, MIT licence, Python ≥ 3.10.
  - It has a sync `TypeSafeClient` and an async `AsyncTypeSafeClient`, and reads `TYPESAFE_API_KEY`.
  - Retries on 429 and 529 are built in, with backoff, and the client honours `retry-after`.
  - First public release was 0.5.7 (2026-09-11). The latest is 0.7.5 (2026-10-14).
  - Source: github.com/typesafe-ai/typesafe-sdk-python.
- **AI gateways:** the SDK docs show use through OpenRouter and the Vercel AI Gateway, with `base_url` set and the gateway's own key.
- **TypeSafe's LLM adapter:** TypeSafe also publishes `system-one-adapter` (github.com/typesafe-ai/system-one-adapter-python). It is a "drop-in replacement for `typesafe_sdk`'s `system_one` evaluation API, backed by LLM APIs instead of TypeSafe", and supports OpenAI, Anthropic and Gemini.

**Reported only by secondary sources**

- API keys are issued in batches from a waitlist ([Layer3Labs](https://www.layer3labs.io/guides/is-jev-free), [OpenTweet](https://opentweet.io/jev/api-access), both September 2026).
- Gateways serve Jev without a waitlist, at the same rate ([OpenTweet](https://opentweet.io/jev/api-access)).
- The OpenRouter model page linked from TypeSafe's SDK docs (openrouter.ai/~typesafe/jev-latest) returned 404 when checked.

**Not found**

- Whether a newly created account gets an API key at once or waits. I could not establish this without signing up.

## What is the request shape, and can several postings or questions go in one request?

**Confirmed from TypeSafe's docs**

- **Request:** `POST https://api.typesafe.ai/v1/systemone` with `Authorization: Bearer <key>`. The body has three parts:
  - `model`: `jev-latest`, `jev-preview` or a pinned ID such as `jev-1.14.0`.
  - `state`: a string, an object or an array.
  - `questions`: an object keyed by your own ids.

  Each question is one of:
  - `noul`: yes/no. Takes `instructions` and optional `criteria: {true, false}`.
  - `choice`: pick one of several options.
  - `score`: ordered levels.
  - `box`: image only, behind a header flag.
- **Response:** `answers` keyed by the same ids, the versioned `model` that answered, and `usage` (input and output tokens).
  - A Noul answer is a single probability: `{"type": "noul", "noul": 0.93}`.
  - Choice and Score answers also carry `probabilities` and a `confidence` value.
- **Several questions in one request:** yes, and the docs encourage it. "There is no separate limit on the number of questions in a request". The questions are evaluated in parallel against the same state. The limits that apply are context sizes:
  - 64k tokens for the state plus all questions.
  - 32k tokens for the state plus any one question.
  - Long context (262k) is an opt-in "danger zone" header, and the docs say it is less accurate.
- **Several postings in one request:** a request has one `state`, and there is no batch endpoint. The docs do show packing several items into one state, with one question per item, for example `items[i]` in the counting example. The same pages warn that "Accuracy falls as the state grows with content unrelated to the decision". The RAG cookbook sends one request per passage when each question concerns one item. For Screening, this means one request per posting carrying both questions, run concurrently.
- **Other request rules:**
  - Body at most 32 MiB.
  - UTF-8 JSON.
  - Nesting at most 64 levels.
  - Finite numbers only.
  - gzip or zstd compression allowed.

## What are the current price and rate limits?

**Confirmed from TypeSafe's docs and site**

- **Price:** both `jev-1.14.0` and `jev-1.13.0` cost "$42 / $0.042" per billion and per million tokens. "You pay per input token. Output tokens are free." The homepage and the launch post say the same. The blog figure of $0.042 per million input tokens with output free is correct.
- **Pricing caveat:** the launch post says "We can't prove it isn't subsidized; we'll need the long-term to prove the sustainability of our pricing (which we expect to go down, not up)."
- **Rate limits:** "Rate limits are set per organization. Your organization's current limits are in the developer console." They are measured in tokens per second and requests per second. Exceeding either returns 429. Higher limits come with custom or enterprise plans.
- **Latency:** the launch post claims "End-to-end response time is 70ms-500ms".

**Reported only by secondary sources**

- A launch demo ran at about 10 queries per second ([eesel.ai](https://www.eesel.ai/blog/typesafe-jev-pricing)).

**Not found**

- The actual default rate-limit numbers. They are visible only in the console, after login.

**Cost estimate (my arithmetic, not from TypeSafe)**

- One posting's request, with the title, location and two Noul questions listing the target titles and locations, is a few hundred input tokens.
- At 300 tokens, that is about $0.0000126 per posting, or about $0.13 per 10,000 postings.

## How well calibrated are the scores on short inputs like a job title, and is there threshold guidance?

**Confirmed from TypeSafe's docs (claims, not evidence)**

- **Calibration claim:** Jev is trained with "RLCD" (Reinforcement Learning for Calibrated Decisions) to return calibrated probabilities. The AI primer explains: "Outcomes assigned a probability of `0.8` should occur about 80% of the time … These rates describe groups of predictions, not a guarantee about any single answer."
- **Threshold guidance for Noul:**
  - "A good starting point is 0.7 for yes and 0.3 for no." Raise the yes threshold when a false yes is costly, and lower it when a missed yes is costly.
  - Values in between can go to review.
  - "Avoid fitting thresholds closely to a handful of test cases."
  - "The correct threshold values depend on your domain … Start with conservative thresholds, test with your own data, and adjust."
- **Pin the model version:** aliases move between versions. "If you have tuned confidence thresholds against one version, send that version's ID instead of the alias." `jev-latest` moved from 1.13.0 to 1.14.0 in October 2026. TypeSafe intends to give 60 days' notice before deprecating 1.13.0 and 30 days for 1.14.0. The formal deprecation policy is not yet published.
- **Known failure modes that matter here** (from the "Jev 1.13 jaggedness" page):
  - **Literal reading:** "answers the question you wrote, not the one you meant". Write the exact condition and put boundary cases in `criteria`.
  - **Indirection:** "a property of a property" costs accuracy.
  - **Choice option order:** Jev leans toward the first option.
  - **Language:** English is the primary training language, and other languages are "handled but not equally well".
- **Example values:** the Noul page shows recorded `jev-1.13.0` values on one-sentence inputs (0.02 to 0.99). These are illustrative, not a calibration study.

**Not found**

- Calibration curves, reliability diagrams, ECE or Brier scores, or any accuracy numbers on short inputs or job titles.
- The 1.14 launch post shows internal intelligence measurements, and itself says "Don't believe it entirely. Always favor your own experimentation".

## What are the data retention terms?

**Confirmed from TypeSafe's legal pages**

- **No training on customer data:**
  - Privacy Policy (updated 2025-11-19): "We … will not train or fine tune any artificial intelligence or machine learning models on Input". Input is not disclosed to third parties other than service providers.
  - The MCA §4.1 says the same, unless the customer consents.
  - The docs say Jev's weights are the same for every account.
- **Retention of Input and Output** (MCA updated 2026-09-23, §4.1):
  - TypeSafe may process Input and Output "during the Term" to provide the service and calculate fees.
  - It may also process them "in perpetuity" to derive Telemetry, to monitor for fraud and abuse, and for legal compliance.
  - Telemetry includes "technical logs, hashes, summary statistics and classifications, metrics", and TypeSafe "may Process Telemetry without restriction".
- **Deletion:** under MCA §10.3, TypeSafe has no obligation to keep Customer Data and "may delete Customer Data at any time".
- **DPA** (updated 2026-04-24): personal data is kept "for as long as necessary taking into account the purpose of the Processing". Subprocessors are listed at trust.typesafe.ai/subprocessors. EU transfers use the SCCs, under Irish law.
- **Privacy Policy retention:** "as long as reasonably necessary to provide you with the Services, or otherwise in support of our business or commercial purposes."
- **Zero data retention:** offered "for enterprise customers" via sales.
- **Jaggedness opt-in:** the 1.14 post adds an opt-in that lets TypeSafe use your queries to find model "jaggedness", while still not training on them.

**Not found**

- A specific retention period, in days, for API request and response bodies on non-enterprise accounts.
- Any opt-out from the "in perpetuity" Telemetry use.

## Implications for the Screening design

- **The API fits the design:**
  - Make one request per posting, with `state = {title, location, workplace_type}`.
  - Ask two Noul questions: `title_matches` and `location_compatible`.
  - Store the two probabilities on the posting. A threshold change then needs no new calls, as ADR 0002 intended.
  - Keep "missing location passes" in code and skip that question. Do the same for anything deterministic, such as workplace type equal to remote when remote is acceptable. The docs say to keep deterministic work in code.
- **Write the questions literally and directly:**
  - Put the user's target titles and acceptable locations into structured `instructions`, for example `{"target_titles": [...], "question": "Is the posting's title one of, or equivalent to, a target title?"}`.
  - Add `true` and `false` criteria with boundary cases, such as seniority variants and "Data Entry Clerk" versus "Data Engineer".
  - Avoid multi-hop location reasoning: give acceptable regions explicitly.
- **Pin the version:**
  - Send a versioned model ID (`jev-1.14.0`), not `jev-latest`.
  - Store the answering model ID next to each score, so a model change can trigger a re-score and a threshold review.
- **Thresholds:** start at the documented 0.7, and lean lower for the title question. A false screen-out only means a posting skips extraction, and it stays stored and visible. Tune on a small labelled sample of real postings, because there is no published short-input calibration.
- **Cost is a non-issue; access and rate limits are the open risks.** The SDK's built-in 429 backoff suits a background worker.
- **Data sensitivity is low:** postings are public, and the questions reveal only the user's target titles and locations. The perpetual-telemetry clause is still worth knowing before sending any Career Profile text, which Screening does not need.
- **Should keyword rules be the default?** Yes. Recommendation:
  - Implement keyword rules as the default behind the thin interface, so the app works with no TypeSafe account.
  - Switch to Jev by configuration once all three hold:
    - an API key is in hand;
    - the rate limits shown in the console fit the daily volume;
    - a labelled check of a few dozen titles at the chosen threshold beats keyword rules.

  Reasons:
  - Access may still be waitlisted.
  - The company and its API are a few weeks into early access: SDK 0.x, with breaking changes in September and model aliases that move.
  - There is no independent or short-input calibration evidence.

  A cheap middle path is TypeSafe's own `system-one-adapter`. It keeps the same `system_one` question and answer shape over the Anthropic API already in use, so moving between Jev and an LLM backend is a configuration change. TypeSafe itself warns that LLM probabilities are less well calibrated.

## Sources

Primary (TypeSafe):
- Homepage: https://typesafe.ai/
- Launch post, 2026-09-15: https://typesafe.ai/blog/introducing-system-one-models-and-jev
- Jev 1.14 post, 2026-10-14: https://typesafe.ai/blog/jev-1-14
- Docs index: https://docs.typesafe.ai/llms.txt
- Quick start: https://docs.typesafe.ai/introduction/quickstart.md
- API reference (OpenAPI): https://docs.typesafe.ai/api/system-one.md
- Request rules and errors: https://docs.typesafe.ai/api/errors.md
- Models, pricing, context, rate limits, aliases, data handling: https://docs.typesafe.ai/models.md
- Primitives: https://docs.typesafe.ai/primitives.md
- Noul: https://docs.typesafe.ai/primitives/noul.md
- Confidence: https://docs.typesafe.ai/confidence.md
- AI primer (RLCD and calibration): https://docs.typesafe.ai/introduction/machine-learning-primer.md
- Jev 1.13 jaggedness: https://docs.typesafe.ai/model-jaggedness/jev-1.13.md
- Python SDK: https://docs.typesafe.ai/sdk/python.md
- Python SDK changelog: https://docs.typesafe.ai/sdk/python/changelog.md
- Python SDK usage with gateways: https://docs.typesafe.ai/sdk/python/usage/basic.md
- RAG passages cookbook (one request per passage): https://docs.typesafe.ai/cookbooks/classifying_rag_passages.md
- Legal index and ZDR: https://docs.typesafe.ai/legal.md
- Privacy Policy: https://typesafe.ai/legal/privacy-policy
- Master Customer Agreement: https://typesafe.ai/legal/mca
- Data Processing Addendum: https://typesafe.ai/legal/data-processing
- Website Terms: https://typesafe.ai/legal/terms
- Console (login only): https://console.typesafe.ai/
- PyPI: https://pypi.org/project/typesafe-sdk/
- GitHub org: https://github.com/typesafe-ai
- Python SDK repo: https://github.com/typesafe-ai/typesafe-sdk-python
- system-one-adapter repo: https://github.com/typesafe-ai/system-one-adapter-python

Secondary (used only where marked):
- https://www.layer3labs.io/guides/is-jev-free
- https://opentweet.io/jev/api-access
- https://www.eesel.ai/blog/typesafe-jev-pricing
