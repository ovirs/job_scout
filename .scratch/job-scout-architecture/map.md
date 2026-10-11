# Job Scout Architecture and Spec

## Destination

Job Scout Web Application: System Architecture and Data Model.
This effort will specify how the app ingests Job Postings, evaluates them against the user's Career Profile and Deal Breakers via an LLM, tracks Applications, and generates Cover Letters, along with the core tech stack.

## Notes

- **Domain**: Job search, Applicant Tracking Systems (ATS), LLM Integration.
- **Skills**: domain-modeling, wayfinder
- **Preferences**:
  - Web Application form factor.
  - Mix of automated ATS pipelines and manual entry.
  - LLM-based matching evaluation and cover letter generation.
  - Build order: the webapp with manual entry first, then LLM evaluation, then Application tracking, then the ETL (Watchlist, Pipelines, screening). Decisions the first three need come before decisions only the ETL needs.
- **Glossary**: [GLOSSARY.md](../../GLOSSARY.md)

## Decisions so far

- [What tech stack should we use for the web application?](issues/01-tech-stack.md): FastAPI + React webapp and a separate Airflow ETL, both Python, joined only by the webapp's API; Postgres; all LLM calls in a webapp background worker; local Docker Compose first.
- [How will we architect the ATS ingestion pipelines and manual entry flow?](issues/02-data-ingestion-strategy.md): every posting's envelope is stored via full board snapshots; Screening Rules (title and location, scored by Jev) gate LLM extraction in the webapp; manual entry is paste-only with confirmation; duplicates are detected and confirmed; Greenhouse, Lever and Ashby first.
- [What is the architecture for the LLM Deal Breaker matching?](issues/03-llm-evaluation-architecture.md): an Evaluation is the LLM's holistic judgement (verdict per Deal Breaker, flags, 1 to 10 score for ordering, three-level recommendation) from the Career Profile, Deal Breakers and Preferences; extraction is a separate call; a violated Deal Breaker forces the lowest recommendation; runs once per new or text-changed posting plus manual re-runs; checked against a test set of the user's own marks; Claude Opus 5.5.

## Not yet specified

- When and how does the app move from local to always-on (home server or cloud), and what login does it need then?
- What do the evaluation and extraction prompts say (the score's level descriptions, the recommendation wording), and how large must the test set be before its agreement figure is trusted? Hangs on the marks the Application workflow defines.
- How does the system facilitate updating the Career Profile continuously based on user context/feedback from new applications?
- How do we orchestrate custom cover letter generation with the LLM?
- How are Screening Rules expressed and tuned (wording of target titles and acceptable locations, the threshold, reviewing screened-out postings)? Hangs on what Jev's API really offers.
- A source of Watchlist suggestions from LinkedIn job-alert emails: needs inbox access and email parsing, and yields company names the user confirms by supplying a board URL. Deferred until company discovery proves to be the bottleneck.

## Out of scope
