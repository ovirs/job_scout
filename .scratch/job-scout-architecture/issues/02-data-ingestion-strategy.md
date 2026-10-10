# How will we architect the ATS ingestion pipelines and manual entry flow?

Type: grilling
Status: resolved (2026-10-10)

## Question

We need a strategy for ingesting Job Postings. We have two main vectors:
1. Automated pipelines scraping from ATS systems (e.g., Greenhouse).
2. Manual copy/paste of jobs from sites like LinkedIn.

How will this data be ingested and normalized into our database? Should manual entries be parsed by an LLM to match the normalized schema of the ATS pipelines?

## Raised elsewhere, to discuss here

Surfaced while resolving the tech stack ticket; noted, not yet discussed.

- A Pipeline that monitors the user's email inbox for LinkedIn job alerts and adds the companies it finds to the Watchlist. Open points: the glossary defines a Pipeline as pulling Job Postings from ATS platforms and the Watchlist as user-maintained, so this either widens both terms or needs its own; whether additions are automatic or proposed for the user to confirm; how a company name from an email is resolved to an ATS board.
- Keyword search is built on top of locally ingested Job Postings, not as a source.

## Answer

Every Job Posting, whatever its origin, has the same two layers, and nothing is discarded at ingestion.

- **Two layers**: an *envelope* (source, company, source posting id, title, location text, optional workplace type, description, URL, timestamps) and *extracted fields* (salary, seniority and the like). ATS adapters fill the envelope deterministically, with no LLM in the ETL. One LLM extraction step in the webapp worker fills the extracted fields for every posting that reaches it. Which fields are extracted is left to the LLM evaluation ticket.
- **Store everything**: the ETL sends the envelope of every posting on a watched board. The webapp stores all of them, so changing the criteria re-screens what is already stored, rejections stay auditable, and keyword search covers the whole board. See [ADR 0002](../../../docs/adr/0002-every-job-posting-is-stored-screening-only-gates-extraction.md).
- **Screening**: Screening Rules run in the webapp worker and gate only LLM extraction. Two questions per posting, over envelope fields only: does the title match a target title, and is the location (location text plus workplace type when present) compatible. A missing location passes. Scores are stored on the posting, so a threshold change needs no new calls. The scorer is Jev (TypeSafe AI's hosted classifier), behind the same thin interface as the Anthropic calls so keyword rules can replace it. Starting point, to be adjusted with use.
- **Manual entry**: pasted text only, in a single text box, with an optional URL stored as a reference and never fetched. One LLM call fills the envelope and the extracted fields; the user corrects the envelope on a confirmation screen before saving. Manual entries skip screening. The pasted text is kept.
- **Duplicates**: detect and confirm, never merge automatically. A manual entry has a generated id with source "manual"; the ATS key (ATS, board, ATS posting id) is for Pipeline postings only. At manual entry the confirmation screen shows similar stored postings from the same company. At Pipeline ingestion a posting resembling a manual entry is flagged; on confirmation the Pipeline posting survives and takes over the Application and notes.
- **Watchlist entry**: a company name plus an ATS and a board identifier, added by pasting the board URL, which the webapp parses by pattern without a network call. An entry is unverified until the Pipeline's first run; the ETL reports last successful pull or error per entry. A company with two boards has two entries. A company on an unsupported ATS cannot be on the Watchlist. A manual entry whose URL matches a supported ATS offers to add the company.
- **Lifecycle**: each daily run sends a full snapshot of each board. The webapp hashes title, location and description: unchanged postings only move their last-seen date; edited postings are overwritten, then screened and extracted again, with no version history. A posting absent from a complete snapshot is marked closed with a date, never deleted, and reopens if it reappears. A failed or partial pull closes nothing. Manual entries are closed only by the user.
- **Raw payloads**: the latest raw ATS payload is stored next to the envelope, overwritten on change.
- **ETL-facing API contract**, all with the service credential: (1) read the Watchlist (ATS and board identifier per entry); (2) submit a board snapshot, one call per entry, with every posting's ATS posting id, envelope and raw payload, plus a flag that the pull was complete, idempotent on resubmission; (3) report a failed pull with the entry and the error, and no postings. The webapp does the rest on receipt: hashing, upsert, closing, duplicate detection, queueing screening and extraction.
- **First adapters**: Greenhouse, Lever and Ashby, pending verification of their board APIs.
- **LinkedIn-alert email**: deferred. If built, it is a source of Watchlist suggestions the user confirms by supplying a board URL, not a Pipeline, so neither glossary term widens.

Rejected: rich per-ATS mapping with the LLM only for manual entries (field coverage would differ by source); dropping screened-out postings in the ETL (criteria changes would not apply retroactively and rejections would be invisible); string similarity for title matching (scores "Data Entry Clerk" near "Data Engineer"); fetching pasted URLs (the main source is LinkedIn, whose scraping is already ruled out); automatic duplicate merging (a wrong merge silently loses a posting); discovering a board from a company name by probing (misses often and can match the wrong company); version history for postings.
