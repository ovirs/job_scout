# What is the architecture for the LLM Deal Breaker matching?

Type: grilling
Status: resolved (2026-10-11)

## Question

Once a Job Posting is ingested, we need to evaluate it against the user's Career Profile and defined Deal Breakers. 
How should this matching system operate? 
- Will it run automatically on every ingested Job Posting?
- Do we store the raw LLM responses or just a boolean `is_match` with a `reasoning` text?
- Which LLM provider/model is best suited for this structured extraction and reasoning task?

## Raised elsewhere, to discuss here

Surfaced while resolving the ingestion strategy ticket; noted, not yet discussed.

- Only Job Postings that pass screening, plus all manual entries, reach the LLM. That narrows "run automatically on every ingested Job Posting".
- LLM extraction of structured fields (salary, seniority and so on) was decided there as a step of its own; which fields it produces is open and depends on what Deal Breakers need. Whether extraction and Deal Breaker evaluation are one call or two is also open.

## Answer

An Evaluation is the LLM's holistic judgement of whether a Job Posting is worth applying to, returned in a fixed shape and checked against the user's own decisions. It is not computed from a formula.

- **Inputs**: the Career Profile and the Preferences, each a free-text document passed whole with no chunking or retrieval, and the Deal Breakers, a list of free-text items. Preferences is a new term: what the user is looking for and how to weigh it. It never disqualifies.
- **Deal Breakers**: each is a sentence the LLM judges against the full posting and gets its own verdict: met, violated or unknown. "Violated" needs evidence in the posting, so silence never disqualifies; anything more specific goes in the Deal Breaker's own wording. A stack Deal Breaker is worded as "X is a required skill" or "X is a primary daily responsibility"; a nice-to-have mention is not a violation and only weighs on the judgement.
- **Two LLM calls**: extraction and evaluation are separate. Extraction depends only on the posting; evaluation depends on the user's three inputs, so editing them redoes evaluation only. Manual entry already forces the split, since extraction runs before the confirmation screen.
- **Extracted fields**, all optional: salary range with currency and period, seniority level, employment type, workplace type with any location restriction, required technologies, nice-to-have technologies. They are for filtering and display and play no part in the Evaluation.
- **Evaluation output**, in this order within one call: a verdict per Deal Breaker; red flags and green flags, each tied to what the posting says; a whole-number score from 1 to 10 with each level described in the prompt; a three-level recommendation (roughly apply, maybe, skip; wording open). The recommendation comes directly from the LLM and is never derived from the score. The score only orders postings, so the user can prioritise limited application time.
- **Hard gate**: when any Deal Breaker is violated, code sets the recommendation to the lowest level whatever the LLM wrote. The posting is kept as a normal row with its verdicts, flags and score, and listed apart from the rest. Disqualified postings with a strong score are surfaced for manual review, so a Deal Breaker that is too strict gets noticed. An unknown verdict changes nothing and appears as a "to check" item.
- **Triggers**: an Evaluation runs for every new screened-in posting and every confirmed manual entry, including old postings on the first pull of a board. For an existing posting it runs again only when the hash of title, location and description changes and the user has not acted on the posting; if they have, the old Evaluation stays and is marked outdated. Otherwise only two manual actions re-run it: one posting, or all open postings the user has not acted on. Date and other metadata changes trigger nothing.
- **Age**: never an input to the Evaluation. It is shown and sortable.
- **Reposts**: a new posting from the same company with exactly the same text as a stored one is linked to it and copies its Evaluation instead of calling the LLM. This depends on whether the ATS boards produce such reposts, which the board API research ticket now asks.
- **Storage**: each Evaluation is its own record holding the full structured result, the model, the prompt version and the versions of the three inputs it used. Earlier Evaluations of the same posting are kept as history.
- **Test set**: the marks the user makes on postings in normal use are the labels. A command the user starts re-runs the Evaluation over them and reports agreement, including whether the score's ordering matches. It is the way to judge a change of prompt, Preferences wording or model. Which marks exist is left to the Application workflow ticket.
- **Model**: Claude Opus 5.5 for evaluation. The model is configurable per step; extraction starts on the same model until the test set shows whether a cheaper one does as well. Structured output validated against a Pydantic schema; the unchanging part of the prompt (instructions and the three inputs) comes first so it can be cached. No batch interface and no other model families for now; another provider would be one more adapter behind the existing thin interface.
- **Failures**: an error, a refusal or a malformed result leaves the posting "not evaluated" with the reason. The queue retries a few times, then it waits for a manual retry. It never counts as a skip.

See [ADR 0003](../../../docs/adr/0003-fit-is-judged-holistically-and-checked-against-the-users-decisions.md).

Rejected: typed Deal Breaker rules over extracted fields (most real Deal Breakers have no field); a per-Deal-Breaker setting for what silence means (one rule plus wording covers it); a score computed in code from per-requirement matches (treats every requirement alike and misses emphasis and day-to-day framing); deriving the recommendation from score thresholds (postings near a threshold would flip between runs); half-point scores (false precision); automatic re-evaluation when the Career Profile, Deal Breakers or Preferences are edited; posting age as an input.
