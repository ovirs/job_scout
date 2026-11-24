# Does Jev's actual API, pricing and limits support screening on title and location?

Type: research
Status: resolved (2026-10-27)

## Question

The ingestion strategy chose Jev (TypeSafe AI's hosted classifier, early access since 2026-09-15) to score Screening Rules, based only on blogs and trade write-ups. From TypeSafe's own documentation:

- How is access obtained during early access, and is there a Python client?
- What is the request shape for a probability question over a short text, and can several postings or several questions go in one request?
- What are the current price and rate limits? (One blog reported $0.042 per million input tokens with output free.)
- How well calibrated are the scores on short inputs like a job title, and is there guidance on thresholds?
- What are the data retention terms?

## Answer

Yes, Jev's API fits screening on title and location; access, rate limits and short-input calibration remain unverified until an account exists. Full findings, with sources: [research/jev-for-screening.md](../research/jev-for-screening.md).

- **Access**: API keys from console.typesafe.ai after a Google or email sign-up, on prepaid credits under TypeSafe's Master Customer Agreement. Whether a new account gets a key at once or waits on the early-access waitlist can only be learned by signing up. Official Python SDK: `typesafe-sdk` (sync and async clients, retries 429s).
- **Request shape**: `POST /v1/systemone` with one `state` (string or object) and any number of named `questions`, of which `noul` is a yes/no probability. Both Screening questions fit in one request per posting. No batch endpoint; packing several postings into one state is discouraged by the docs.
- **Price and limits**: $0.042 per million input tokens, output free (the blog figure holds), so screening cost is negligible. Rate limits are per organisation and visible only in the logged-in console.
- **Calibration**: claimed but unpublished; no guidance for short inputs. Suggested starting thresholds 0.7 (yes) and 0.3 (no), tuned on own data; pin a model version (`jev-1.14.0`), since aliases move.
- **Data terms**: inputs are not used for training without consent, but TypeSafe may derive telemetry from inputs and outputs in perpetuity; no retention period in days for ordinary accounts, zero retention for enterprise only. Screening inputs are public posting titles and locations, so this is low-risk here.
- **Fallback**: TypeSafe's own `system-one-adapter` runs the same question shape over the Anthropic API.

Bearing on the Screening Rules fog: the research suggests keeping keyword rules as the default behind the thin interface and switching Jev on once a key is in hand, the console's limits fit the daily volume, and a small labelled check beats keyword rules. That is a suggestion for the Screening Rules decision, not decided here.
