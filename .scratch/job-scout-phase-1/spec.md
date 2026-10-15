# Job Scout phase 1: manual entry, Evaluation, Triage, Applications and Cover Letters

Status: ready-for-agent

Synthesised from the wayfinder map [job-scout-architecture](../job-scout-architecture/map.md), its resolved tickets [01](../job-scout-architecture/issues/01-tech-stack.md), [02](../job-scout-architecture/issues/02-data-ingestion-strategy.md), [03](../job-scout-architecture/issues/03-llm-evaluation-architecture.md), [06](../job-scout-architecture/issues/06-application-workflow.md), [07](../job-scout-architecture/issues/07-evaluation-prompts-and-test-set.md) and [08](../job-scout-architecture/issues/08-cover-letter-generation.md), the [glossary](../../GLOSSARY.md) and ADRs [0001](../../docs/adr/0001-etl-and-webapp-as-separate-subsystems-joined-by-the-api.md), [0002](../../docs/adr/0002-every-job-posting-is-stored-screening-only-gates-extraction.md) and [0003](../../docs/adr/0003-fit-is-judged-holistically-and-checked-against-the-users-decisions.md).

## Problem Statement

The user is looking for a job and spends an hour or more on each application, including a tailored Cover Letter, so they can apply to only a few Job Postings a week. Postings reach them from many places (mostly LinkedIn), written in very different ways, and deciding which are worth that hour means reading each one against their whole career history, their Deal Breakers and what they actually want. Once they apply, the progress of each Application lives in their head or in scattered notes, and every Cover Letter is written from scratch. They have no single place to collect postings, get a fast and honest first opinion on each, record their own call, track where every Application stands, and produce a truthful first draft of a Cover Letter.

## Solution

A local web application. The user writes four documents once and keeps them up to date: their Career Profile, their Preferences, their Deal Breakers and their Writing Guide. They paste a Job Posting's text into a single box; the app reads it, shows the title, company, location and description it found for the user to correct, warns about similar postings already stored from the same company, and saves it.

The app then evaluates the posting in the background: a verdict on each Deal Breaker with a quote from the posting, red and green flags specific to the user, a 1 to 10 score for ordering, a recommendation (apply, maybe, skip) and a one or two sentence summary. Every quote is checked to occur in the posting. A violated Deal Breaker always forces skip.

Untriaged postings the LLM recommends land in an inbox ordered by score; skips sit in a separate list. The user triages each as Interested, Maybe or Ignored, which overrides the recommendation. When they decide to apply they start an Application, which moves by hand through Preparing, Applied, Screen call, Interview loop and Offer to Accepted, Rejected, Withdrawn or No response. While Preparing, they generate a Cover Letter from the posting, the Career Profile, the Evaluation's flags and the Writing Guide. It claims only what the Career Profile states and lists the requirements it found no support for. The user edits it, asks for revisions in words or regenerates, keeps every draft, and copies the final text out when they apply.

Phase 1 is everything before the ETL: no Watchlist, no Pipelines, no Screening Rules. The Job Posting model is built so Pipeline postings can arrive later without reshaping it.

## User Stories

### Setting up the user's inputs

1. As the user, I want to write my Career Profile as one free-text document, so that the LLM has a complete record of my experience, projects and skills without the limits of a two-page resume.
2. As the user, I want to edit my Career Profile at any time, so that it keeps up with what I have done.
3. As the user, I want to write my Preferences as one free-text document, so that I can say what I am looking for and how to weigh it in my own words.
4. As the user, I want to keep a list of Deal Breakers, each one sentence in my own words, so that postings that cross a line I will not cross are disqualified.
5. As the user, I want to word a Deal Breaker however reads naturally ("fully remote from Romania", "The role expects Spark experience: Spark is required, listed in the team's stack, or central to the daily work"), so that I do not have to follow a writing rule about polarity.
6. As the user, I want to add, edit and delete Deal Breakers individually, so that I can sharpen one without touching the others.
7. As the user, I want to write a Writing Guide (tone, length, structure, phrases to avoid, one or two sample letters), so that generated Cover Letters read like me.
8. As the user, I want every saved change to these four documents to create a new version, so that each Evaluation and Cover Letter draft records exactly which inputs produced it.
9. As the user, I want editing my Career Profile, Preferences or Deal Breakers not to re-run any Evaluation by itself, so that a small edit does not spend LLM calls on every posting.
10. As the user, I want the app to work without logging in while it runs on my own machine, so that there is no friction in a single-user local setup.

### Manual entry

11. As the user, I want to paste a Job Posting's text into a single text box, so that I can add a posting from any site, including LinkedIn, in one step.
12. As the user, I want to give an optional URL with the paste, stored as a reference and never fetched, so that I can go back to the original without the app scraping anything.
13. As the user, I want the app to read the paste and find the title, company, location and the description itself, so that I do not have to fill in a form.
14. As the user, I want the description cut out of my paste by its first and last line rather than retyped by the LLM, so that the stored description is always my own paste, word for word, without the page's menus and buttons.
15. As the user, I want to see what was found on a confirmation screen and correct the title, company, location, workplace type and description before saving, so that a wrong reading never gets stored.
16. As the user, I want to see a clear status while the paste is being read, and the reason if reading fails, with a way to retry, so that I am never left on a blank screen.
17. As the user, I want the confirmation screen to show similar postings I already stored from the same company, so that I do not add the same posting twice.
18. As the user, I want to choose between opening the existing posting and saving mine anyway, so that a duplicate is never merged or discarded without my say.
19. As the user, I want the full pasted text kept next to the posting, so that nothing I pasted is lost if the cut was wrong.
20. As the user, I want the extracted facts (salary ranges, seniority, employment type, workplace type and location restriction, required and nice-to-have technologies) shown on the posting, so that I can see the key facts at a glance.
21. As the user, I want extracted facts to be only what the posting states, never guessed, so that a missing salary shows as missing rather than as an invented figure.
22. As the user, I want several salary ranges (one per region) and several seniority levels ("Senior/Staff") kept as written, so that a posting covering several of them is not flattened to one.
23. As the user, I want "Python, Go or Java" kept as alternatives, so that it does not read as three requirements.
24. As the user, I want to close a manual entry myself (the role is filled, the posting is gone), so that it drops out of my lists without being deleted.
25. As the user, I want saving a confirmed manual entry to start its Evaluation automatically, so that I do not have to ask for it.

### Evaluation

26. As the user, I want each Deal Breaker to get its own verdict (clear, violated or unknown) with a one-sentence explanation, so that I can see exactly how the posting was judged on each line.
27. As the user, I want a violated verdict to need a quote from the posting, so that a posting is never disqualified on something it does not say.
28. As the user, I want a posting that is silent on a Deal Breaker to get unknown rather than violated, so that silence never disqualifies.
29. As the user, I want each unknown verdict to say what I would need to find out, shown as a "to check" item, so that I know what to ask the recruiter.
30. As the user, I want each Deal Breaker applied exactly as worded, no more strictly and no less, so that "nice to have: Spark" does not violate a Deal Breaker about Spark being required.
31. As the user, I want at most five red and five green flags, each one sentence specific to me with the words from the posting it rests on, so that I get reasons, not boilerplate like "competitive salary".
32. As the user, I want a whole-number score from 1 to 10 that judges above all how credible I am as a candidate, as a recruiter at the first screen would, so that the order of my inbox reflects where my application time is best spent.
33. As the user, I want my Preferences to move the score by a level or two at most, and a role they say to avoid to score 4 or less, so that liking a role does not hide that I am not credible for it.
34. As the user, I want a recommendation of apply, maybe or skip, worded as a prediction of what I would do, so that it is comparable to my own Triage.
35. As the user, I want a violated Deal Breaker always to mean skip, so that a line I will not cross is never overridden by an attractive posting.
36. As the user, I want a one or two sentence summary of the role and the main reason for the recommendation, so that I can scan the inbox quickly.
37. As the user, I want every quote the Evaluation relies on checked against the posting, ignoring whitespace, case, quote styles and bullets, so that an invented quote can never disqualify or promote a posting.
38. As the user, I want the posting view to highlight the sentence each verdict and flag quotes, so that I can check the reasoning in seconds.
39. As the user, I want the app to treat the posting as untrusted text and to raise a red flag if it contains instructions aimed at an AI, so that a posting cannot steer its own Evaluation.
40. As the user, I want a posting whose Evaluation failed (error, refusal, malformed result, a quote that is not in the posting) marked "not evaluated" with the reason, so that a failure is never mistaken for a skip.
41. As the user, I want failed Evaluations retried a few times automatically and then left for me to retry by hand, so that a passing outage does not need my attention and a persistent one does not loop forever.
42. As the user, I want to re-run the Evaluation of one posting by hand, so that I can see the effect of rewording a Deal Breaker or Preferences on it.
43. As the user, I want to re-run the Evaluation of all open postings I have not acted on, so that a change to my inputs reaches every posting still waiting for my call.
44. As the user, I want every earlier Evaluation of a posting kept as history, with the model, prompt version and input versions it used, so that I can compare runs.
45. As the user, I want an Evaluation whose posting text changed after I acted on it kept and marked outdated rather than replaced, so that my decision stays tied to what I saw.
46. As the user, I want a posting where a Deal Breaker is violated but the LLM itself recommended applying to show a badge naming the Deal Breaker and its evidence, so that I can catch an Evaluation that contradicts itself.
47. As the user, I want the posting's age shown and sortable but never used in the Evaluation, so that an old posting is judged on its content.

### Triage and lists

48. As the user, I want untriaged open postings recommended apply or maybe gathered in an inbox ordered by score, so that I work through the best ones first.
49. As the user, I want untriaged postings recommended skip in a separate list, so that I never have to ignore them by hand but can still look.
50. As the user, I want to triage any posting as Interested, Maybe or Ignored, so that my own call overrides the recommendation.
51. As the user, I want to triage a posting before it is evaluated, or while its Evaluation has failed, so that I am never blocked by the LLM.
52. As the user, I want Interested postings on a shortlist, Maybe postings on a "later" list and Ignored postings out of sight, so that each list holds only what I still need to act on.
53. As the user, I want to change a Triage at any time while no Application exists, so that I can change my mind.
54. As the user, I want postings that are not evaluated shown with their reason and a retry action, so that a failed Evaluation does not disappear from view.
55. As the user, I want an untriaged posting that closes to drop out of the inbox, so that I do not spend time on a role that is gone.
56. As the user, I want an Interested posting with no Application to stay on the shortlist with a "closed on" badge when it closes, so that I see it closed rather than losing it.
57. As the user, I want my explicit Triages recorded as such, separately from any Triage the app copies, so that they can later serve as labels for checking the Evaluation.

### Applications

58. As the user, I want a "start application" action on a posting that creates an Application in Preparing and sets the Triage to Interested, so that starting to apply is one deliberate step.
59. As the user, I want Interested alone to create nothing, so that a shortlist entry does not clutter my Applications.
60. As the user, I want at most one live Application per posting, so that progress is never split across two records.
61. As the user, I want to set an Application's state by hand to any of Preparing, Applied, Screen call, Interview loop, Offer, Accepted, Rejected, Withdrawn or No response, moving between any two, so that the tracker follows what really happened rather than a fixed path.
62. As the user, I want every state change recorded with its date, so that I can see how long each step took.
63. As the user, I want the Triage locked at Interested while an Application exists, so that a posting I am applying to cannot be ignored by mistake.
64. As the user, I want closing an Application (Accepted, Rejected, Withdrawn, No response) to leave the Triage at Interested, so that the record of my interest stays true.
65. As the user, I want the Application to take a copy of the posting's title, company, location, description and URL when it first becomes Applied, which never changes, so that I always have what I applied to.
66. As the user, I want the Application to show when the live posting differs from that copy, so that I notice an edited posting.
67. As the user, I want to delete an Application while it is Preparing, so that an application I abandoned before sending leaves no trace in my lists.
68. As the user, I want a deleted Application hidden but never removed from the database, and the Triage left at Interested and changeable again, so that nothing I created is lost and I am free to re-triage.
69. As the user, I want an Application past Preparing to be closed rather than deleted, so that my history of real applications stays complete.
70. As the user, I want to start a new Application on a posting whose earlier one I deleted, starting with no Cover Letter, so that I can come back to a posting cleanly.
71. As the user, I want to add free-text, dated notes to a posting and to an Application, so that I can record interview rounds, contacts and impressions.
72. As the user, I want a posting's notes shown alongside its Application, so that nothing I wrote before applying is out of sight.
73. As the user, I want to delete a note, with it hidden and kept in the database, so that I can tidy up without losing data.
74. As the user, I want a list of my Applications by state, so that I see what is in flight and what is closed.

### Cover Letters

75. As the user, I want a "generate cover letter" action while an Application is Preparing, so that a letter is written only when I ask and after I have had a chance to add instructions.
76. As the user, I want to type instructions for one letter (what to stress, the language to write in), so that each letter fits its posting.
77. As the user, I want the letter written from the posting's live title, company and description, my whole Career Profile, the Evaluation's flags and my Writing Guide, so that it speaks to this posting in my voice.
78. As the user, I want my Preferences and Deal Breakers kept out of the letter's inputs, so that my private reasons never leak into a letter a company reads.
79. As the user, I want every claim about me restricted to what my Career Profile states, so that I never send a letter that overstates my experience.
80. As the user, I want the requirements the letter found no support for in my Career Profile listed beside the draft, so that I can decide how to address them and notice gaps in my profile.
81. As the user, I want to be told and asked to confirm when the Evaluation is missing or outdated before generating, so that I know the letter will lack flags or use old ones.
82. As the user, I want the letter written in the posting's language unless my instructions say otherwise, with its length from the Writing Guide, so that I do not have to set language or length fields.
83. As the user, I want to edit the draft by hand, so that I finish the letter myself.
84. As the user, I want to ask for a revision in words ("shorter, and lead with the Kafka migration"), with my hand edits sent back with the instruction, so that I can steer the LLM without losing my changes.
85. As the user, I want to regenerate from scratch, so that I can start over when a draft is off.
86. As the user, I want every LLM result and every saved hand edit kept as a draft, and the ability to go back to any earlier one, so that I never lose a version I liked.
87. As the user, I want each draft to record its origin (generated, revised in words, edited by hand), its instruction and its unsupported requirements, so that later I can see what the LLM wrote and what I changed.
88. As the user, I want a "posting edited since this draft" badge if the posting text changes while I prepare, so that I can decide whether to regenerate.
89. As the user, I want the Cover Letter locked whenever the Application is not Preparing, and unlocked again if I move it back to Preparing, so that the letter I sent cannot be changed by accident.
90. As the user, I want to copy the letter as plain text with one button, so that I can paste it into any application form.
91. As the user, I want to move an Application to Applied without a Cover Letter, with the Application showing that no letter was sent, so that postings that need no letter are not blocked.
92. As the user, I want a failed generation to leave the Cover Letter as it was, show the reason and wait for my retry, so that a failure never overwrites my draft.
93. As the user, I want the app to record how much of the last LLM draft survived into the letter I sent, so that I can see over time whether the generated drafts are getting closer to what I send.
94. As the user, I want a command that regenerates letters for a handful of past Applied Applications under a new prompt or model and shows each beside the letter I actually sent, without saving them as drafts, so that I can judge a change by eye.
95. As the user, I want to delete a Cover Letter draft, hidden and kept, and excluded from the quality aids, so that a junk draft does not distort them.

### Operating it

96. As the user, I want to start the whole app locally with Docker Compose and configure it from environment variables, so that moving it to a home server or the cloud later is a configuration change.
97. As the user, I want the model for each LLM step (extraction, evaluation, Cover Letter) configurable, so that a cheaper model can be tried for one step without touching the others.
98. As the user, I want all LLM calls made in a background worker and never inside a request, so that the UI stays responsive and a slow call never times out a page.

## Implementation Decisions

### Stack and running it

- Webapp only. FastAPI with Pydantic, SQLAlchemy 2 and Alembic; a React and TypeScript single-page app built with Vite, using TanStack Query and an API client generated from the backend's OpenAPI schema. No server rendering.
- PostgreSQL, one database for the webapp. Airflow and its metadata database are not set up in phase 1.
- A background worker fed by a Postgres-backed queue (Procrastinate) runs every LLM call: manual entry extraction, Evaluation and Cover Letter generation. Request handlers only enqueue and report status.
- LLM calls go through the Anthropic Python SDK behind a thin internal interface with one method per step. It takes a step's inputs and returns a validated Pydantic result or a typed failure (error, refusal, malformed). It is the seam a fake replaces in tests and the place a later Jev scorer or another provider plugs in as a further adapter.
- Default model for every step: Claude Opus 5.5 (`claude-opus-5-5`), configurable per step by environment variable. Structured output validated against the step's Pydantic schema. No batch interface.
- Prompt layout puts the unchanging part first so it can be cached: for evaluation, the instructions, then the Career Profile, Preferences and numbered Deal Breakers, then the posting last; for Cover Letters, the Career Profile and Writing Guide first.
- Local only, through a Compose file at the repository root; all configuration from environment variables. No login while local.
- Every user-owned table carries an owner column, with a single user. Nothing else is built for multi-tenancy.
- `uv` for Python. Repository layout `webapp/backend` and `webapp/frontend`; the `etl` directory is not created in phase 1.

### Standing rules

- Nothing the user creates is physically deleted. Applications, Cover Letter drafts, notes, Deal Breakers and the user's documents are marked with a deletion date and hidden from the live app: current views and anything used for new work. A version that an Evaluation or Cover Letter draft references stays intact, deleted records included. Phase 1 has no restore screen.
- Every LLM-produced record stores the model, the prompt version and the versions of the inputs it used.

### User inputs

- Four kinds of user input: Career Profile, Preferences and Writing Guide (each one free-text document) and Deal Breakers (a list of one-sentence free-text items).
- Each is versioned: saving creates a new immutable version, and Evaluations and Cover Letter drafts reference the versions they used. The Deal Breakers are versioned as a set. Each Deal Breaker also keeps a stable id across versions so verdicts can be compared between runs.
- Deleting a Deal Breaker creates a new set version without it. Earlier set versions keep it and stay retrievable by id, so an Evaluation always shows the Deal Breakers it was judged against.
- Editing any input triggers no LLM call.

### Job Posting model

- One Job Posting entity for every origin, in two layers:
  - **Envelope**: source (`manual` in phase 1; ATS names later), company, source posting id, title, location text, optional workplace type, description, URL, created and last-seen timestamps, closed date.
  - **Extracted fields**: the `ExtractedFields` shape below, filled by the LLM, nullable until extraction has run.
- Ready for Pipelines, unused in phase 1: a nullable ATS key (ATS, board identifier, ATS posting id), unique when present, so the later snapshot upsert is idempotent; a nullable latest raw ATS payload; nullable screening scores and a screened-in state (null for manual entries, which skip screening per ADR 0002); a nullable link to an earlier posting for reposts; a nullable link for a confirmed duplicate.
- A manual entry gets a generated id as its source posting id and keeps the full pasted text.
- A content hash over title, location text and description is stored on every posting. Any change to the posting's text goes through one update path that recomputes the hash and applies the re-evaluation rule below, so Pipeline updates will reuse it.
- Closing never deletes. A manual entry is closed only by the user; the closed date is set and can be cleared.
- Age (from the created date) is shown and sortable and never passed to the LLM.

### Manual entry flow

1. The user submits pasted text and an optional URL. The URL is stored, never fetched.
2. The backend stores a pending entry and enqueues extraction. The frontend polls its status.
3. The worker runs the extraction step with the manual entry variant of the prompt (`ManualEntryExtraction`). Code cuts the description from the pasted text from the first occurrence of `description_first_line` to `description_last_line`, never using LLM-written description text. If the markers cannot be found, the confirmation screen opens with the whole paste as the description for the user to trim.
4. The confirmation screen shows title, company, location text, workplace type and description, all editable, plus the extracted fields, plus stored postings from the same company (company name compared case- and whitespace-insensitively), most similar title first.
5. The user saves, or opens one of the similar postings and abandons the entry. Saving never merges. The extracted fields are stored with the saved posting, so extraction is not run again.
6. Saving enqueues the Evaluation.
- Extraction failure: the entry shows the reason and a retry; the queue retries a few times first.

### Extraction output

The extraction schema, from the prompt prototype (prompt text: branch `prototype/evaluation-prompts`, `.scratch/job-scout-architecture/prototypes/07-evaluation-prompts/extraction-prompt.md`):

```python
class SalaryRange(BaseModel):
    minimum: float | None
    maximum: float | None
    currency: str                      # ISO 4217
    period: Literal["year", "month", "day", "hour"]
    applies_to: str | None             # "New York and San Francisco", "EU", ...

class Technology(BaseModel):
    name: str
    alternative_group: int | None      # same number = "any one of these"

class ExtractedFields(BaseModel):
    salary_ranges: list[SalaryRange]
    seniority: list[Literal["intern", "junior", "mid", "senior", "staff",
                            "principal", "lead", "manager", "director", "executive"]]
    employment_type: Literal["full_time", "part_time", "contract",
                             "internship", "temporary"] | None
    workplace_type: Literal["remote", "hybrid", "onsite"] | None
    location_restriction: str | None
    required_technologies: list[Technology]
    nice_to_have_technologies: list[Technology]

class ManualEntryExtraction(ExtractedFields):
    title: str | None
    company: str | None
    location_text: str | None
    description_first_line: str | None  # verbatim; code slices the pasted text
    description_last_line: str | None
```

- Extracted fields are facts for display (and later filtering) and are never inputs to the Evaluation (ADR 0003).
- Years of experience are not turned into a seniority level.

### Evaluation

- Prompt text: branch `prototype/evaluation-prompts`, `.scratch/job-scout-architecture/prototypes/07-evaluation-prompts/evaluation-prompt.md`, used as the baseline v0 and versioned in the app. The posting is passed as untrusted third-party text.
- Output schema, from the prompt prototype. Fields are produced in this order, so evidence and verdicts come before the score and recommendation:

```python
class DealBreakerVerdict(BaseModel):
    deal_breaker_id: int
    verdict: Literal["clear", "violated", "unknown"]
    evidence: str | None      # verbatim from the posting; required when clear or violated
    explanation: str          # one sentence

class Flag(BaseModel):
    point: str                # one sentence, specific to this person
    evidence: str             # verbatim from the posting

class EvaluationResult(BaseModel):
    deal_breaker_verdicts: list[DealBreakerVerdict]
    red_flags: list[Flag]     # at most 5
    green_flags: list[Flag]   # at most 5
    score: int                # 1 to 10
    recommendation: Literal["apply", "maybe", "skip"]
    summary: str              # one or two sentences
```

- Checks in code after the call; any failure makes the result malformed:
  - exactly one verdict per Deal Breaker id in the version used;
  - `evidence` present for clear and violated;
  - at most five flags of each colour;
  - score a whole number from 1 to 10;
  - every `evidence` string occurs in the posting text after normalising whitespace, case, quote styles and bullet characters. The match position is stored so the posting view can highlight it.
- **Hard gate**: if any verdict is violated, the stored recommendation is skip. The LLM's own recommendation is stored beside it. A posting with a violated verdict and an LLM recommendation other than skip is flagged "disqualified but recommended". It is routed by the LLM's own recommendation into the inbox with a badge naming the violated Deal Breaker and its evidence. Everywhere else the stored (gated) recommendation is used.
- An unknown verdict changes nothing and is shown as a "to check" item with its explanation.
- **Record**: each Evaluation is its own row holding the full structured result, the stored and LLM recommendations, the model, the prompt version, the Career Profile, Preferences and Deal Breaker versions, the posting's content hash at the time, a status (queued, running, done, not evaluated with reason) and timestamps. Earlier Evaluations of a posting are kept as history; the latest done one is current.
- **Outdated**: an Evaluation is outdated when the posting's content hash differs from the one it recorded.
- **Triggers in phase 1**:
  - a confirmed manual entry;
  - the user re-runs one posting;
  - the user re-runs all open postings they have not acted on;
  - starting an Application on a posting with no Evaluation.
  
  The update path also applies the rule for later Pipeline postings: a content hash change re-runs the Evaluation only if the posting is not acted on; otherwise the old one stays and shows as outdated with an "edited since you triaged it" badge. Date and metadata changes trigger nothing.
- **Acted on**: a posting with any Triage or a live Application.
- **Failures**: an error, a refusal, a schema failure or a failed check retries a few times on the queue, then leaves the posting "not evaluated" with the reason until a manual retry. A not-evaluated posting never counts as a skip.

### Triage and lists

- Triage values: Interested, Maybe, Ignored. A posting has at most one; untriaged is the absence of a Triage, not a fourth value. Any posting can be triaged, including one not yet evaluated.
- Each Triage records whether it was set by the user or copied by the app. Phase 1 creates only user-set ones; copied ones come with reposts and are never test labels.
- Triage changes are recorded with dates.
- While a live (not deleted) Application exists, the Triage is Interested and cannot be changed through the API.
- Lists, all over open postings unless stated:
  - **Inbox**: untriaged, routed apply or maybe, ordered by score descending.
  - **Skip list**: untriaged, routed skip.
  - **Not evaluated**: untriaged, with no done Evaluation (queued, running or failed), with status, reason and retry.
  - **Shortlist**: Interested, open or closed, closed ones with a "closed on" badge.
  - **Later**: Maybe.
  - **Ignored**: Ignored, reachable but not in the main navigation.
- An untriaged posting that closes drops out of the inbox, the skip list and the not-evaluated list.
- Inbox rows show title, company, age, score, recommendation, summary and badges (disqualified but recommended, outdated). Lists sort by score or age.

### Applications

- "Start application" on a posting creates an Application in Preparing and sets the Triage to Interested. It is refused if a live Application already exists for the posting.
- States: Preparing, Applied, Screen call, Interview loop, Offer, Accepted, Rejected, Withdrawn, No response. The last four are closed. Any transition is allowed. Every change is stored with its date in a state history.
- On the first move to Applied, the Application copies the posting's title, company, location text, description and URL. The copy never changes, even after later moves back and forth. The Application view shows when the live posting's content hash differs from the one at copy time.
- Deletion is allowed only while Preparing, and only marks a deletion date. On deletion the Triage stays Interested and becomes changeable. A later "start application" creates a new Application with no Cover Letter.
- Notes: free-text, dated, on a Job Posting or on an Application, each soft-deletable. A posting's notes stay on the posting and are shown alongside its Application.

### Cover Letters

- An Application has at most one Cover Letter, made of drafts; the latest live draft is the Cover Letter, and the user can make any earlier draft the latest by restoring it as a new draft.
- Actions while Preparing: generate, revise in words, edit by hand (save as a draft), restore an earlier draft. All are refused when the Application is in any other state.
- **Generate**: inputs are the posting's live title, company and description, the whole Career Profile, the current Evaluation's green and red flags, the Writing Guide and optional per-letter instructions. Never the Preferences, Deal Breakers or earlier sent letters.
- Before generating, the API reports whether the current Evaluation is missing or outdated, and the frontend asks for a yes or no confirmation. With none, flags are left out; with an outdated one, its flags are used as they are. The draft records which case applied and which Evaluation supplied the flags.
- **Revise in words**: sends the current latest draft text (hand edits included) with the user's instruction, along with the same inputs as generate.
- **LLM output**: two fields, the letter text and the list of posting requirements the Career Profile does not support. The letter is in the posting's language unless the instructions say otherwise; length comes from the Writing Guide.
- **Draft record**: the text, the date, the origin (generated, revised in words, edited by hand), the instruction typed for it, the unsupported requirements, and for LLM drafts the model, the prompt version, the Career Profile and Writing Guide versions, the Evaluation used (or that none was), and the posting's content hash.
- A "posting edited since this draft" badge shows when the posting's content hash differs from the latest draft's.
- **Locking**: editable only in Preparing. Moving to any other state locks it; moving back to Preparing unlocks it. The next move to Applied locks the then-latest draft as the sent letter. Drafts are kept after locking.
- Applied with no Cover Letter is allowed and shown as "no letter sent".
- Failed calls leave the Cover Letter unchanged, show the reason and wait for a manual retry.
- Output: plain text with a copy button. No file export.
- **Quality aids**:
  - On each move to Applied, the app records how much of the last LLM-produced draft survived into the locked text (a text-similarity ratio).
  - A user-started backend command regenerates letters for a chosen handful of past Applied Applications under a given prompt version or model and shows each beside the letter actually sent. It saves nothing as a draft. Deleted records are excluded from both aids.

### API shape

- The frontend uses only the webapp's HTTP API, described by its OpenAPI schema, with resources for the four user inputs, Job Postings (manual entry submission, confirmation, close and reopen, lists), Evaluations (per posting, re-run one, re-run all unacted), Triage, Applications (start, state change, delete), notes and Cover Letter drafts (generate, revise, save, restore, copy text).
- Long-running actions return immediately with a queued status and are polled.

## Testing Decisions

- A good test drives the system the way a client does and asserts what a client can observe: responses and the state later responses show. Tests do not reach into tables, queue internals or private functions, so the storage layout and module boundaries can change without breaking them.
- **Main seam: the webapp's HTTP API**, run against a real Postgres, with the thin LLM interface replaced by a fake that returns canned structured results or typed failures per step. Queued worker jobs are run to completion inside the test. Everything below is asserted through this seam:
  - manual entry: pending, extraction, description cut by line markers (and the fallback when markers are missing), confirmation with corrections, similar postings from the same company, save, Evaluation enqueued;
  - Evaluation checks: a quote missing from the posting, a missing verdict, an out-of-range score, too many flags, each leading after retries to "not evaluated" with a reason;
  - quote normalisation: whitespace, case, quote styles and bullets;
  - the hard gate, the stored LLM recommendation, the "disqualified but recommended" routing and badge, and unknown verdicts as "to check" items;
  - triggers and the acted-on rule, including the content hash update path, outdated marking and re-run all unacted;
  - list membership and ordering for inbox, skip list, not evaluated, shortlist, later and ignored, including closing;
  - Triage rules: changeable, locked while an Application is live, freed on deletion, user-set versus copied;
  - Application states, any-to-any moves, dated history, the posting copy on first Applied, delete only while Preparing, soft deletion everywhere, a new Application after deletion;
  - Cover Letter: inputs sent to the fake (Preferences and Deal Breakers never included; flags absent, current or outdated), the missing or outdated Evaluation confirmation, every draft origin, restore, locking and unlocking with state, the survival ratio on Applied, a failed call leaving the letter unchanged;
  - versions recorded on Evaluations and drafts.
- **One browser smoke test** of paste, confirm and save, driving the React app against the running API and Postgres with the fake LLM, to check the wiring from the frontend to the database end to end. No other UI tests in phase 1.
- The real Anthropic adapter is not covered by automated tests. Prompt quality is judged by reading Evaluations one by one: the user pastes 8 to 10 postings they would reject, some breaking a Deal Breaker, to check skip and the gate (ticket 07).
- Prior art: none. The repository has no code yet, so these tests set the pattern.

## Out of Scope

- The ETL: Airflow, the ATS adapters (Greenhouse, Lever, Ashby), board snapshots, the ETL-facing API and its service credential, raw ATS payloads, closing postings absent from a snapshot, counting changed postings per snapshot.
- The Watchlist, including offering to add a company when a manual entry's URL matches a supported ATS.
- Screening Rules and Jev scoring, including how they are expressed and tuned.
- Duplicate flagging and merging between Pipeline postings and manual entries (the model keeps room for the link).
- Reposts: linking same-text postings and copying their Evaluation or Triage (the model keeps room for the link and for copied Triages).
- The Evaluation agreement report, the test set thresholds (30 and 100 Triages), comparing two prompt runs and the "show me 10 random skipped postings" action. They wait for the ETL; phase 1 only records user-set Triages and Evaluation versions so they can be built later.
- Keyword search over stored postings, and filtering lists by extracted fields.
- File export of Cover Letters.
- From the map's "Not yet specified":
  - moving from local to always-on (home server or cloud) and the login it would need;
  - updating the Career Profile from new applications (phase 1 only keeps draft origins and unsupported requirements as raw material);
  - restoring deleted records, including the offer to restore when starting an Application on a posting that has a deleted one;
  - how Screening Rules are expressed and tuned;
  - Watchlist suggestions from LinkedIn job-alert emails.

## Further Notes

- **Calls made in this spec that the tickets left open**, to check before building:
  - a "not evaluated" list, since failed Evaluations need a place to be retried;
  - "similar" at manual entry means same company with titles ranked by similarity;
  - editing a saved manual entry's text: phase 1 offers no such action, but the update path and outdated marking exist for Pipelines;
  - Deal Breakers carry stable ids and are versioned as a set.
- Ticket 03 named one salary range and one seniority level; the prompt prototype made both lists, which this spec follows. Ticket 03's verdict "met" is now "clear" (ticket 07).
- The prompt drafts are a v0 baseline that has not been run against a real posting. They should be versioned in the app from the start, so the first tuning is visible in the Evaluation history.
- Starting an Application on a posting that has no Evaluation queues one, as for a manual entry. In phase 1 every posting is a manual entry and already has one queued, so this matters mostly for failed Evaluations.
- No ADR is contradicted. ADR 0002's "manual entries skip screening" holds trivially, since no screening exists yet.
