# What do the Greenhouse, Lever and Ashby job board APIs actually return?

Type: research
Status: resolved (2026-10-27)

## Question

The ingestion strategy picked Greenhouse, Lever and Ashby as the first adapters from memory, without checking their APIs. For each of the three, from the primary documentation:

- Is there a public, unauthenticated endpoint that returns a company's whole board in one request?
- Which envelope fields are structured: title, location, workplace type, compensation, department, updated timestamp, posting id, URL?
- Does the list response include the full description, or does each posting need its own request?
- What rate limits or usage terms apply?
- What does a board URL look like, so the webapp can recognise the ATS and extract the board identifier from a pasted URL?

- Which dates does each posting carry (first published, last updated, closing date), and how does a repost appear: the same posting id with a new date, or a new posting id with the same text?

- Does the description each API returns include company-wide boilerplate (an "About us", benefits or legal paragraph repeated on every posting), or is that in a separate field? Raised by the Application workflow ticket: a boilerplate edit changes the text hash of every posting on a board at once and would re-run the Evaluation of each untriaged one. A separate field could be left out of the hash.

Also needed, and it takes the user's company list: a tally of which ATS each company the user cares about is on, to decide whether a fourth adapter (Workday or another) is needed early.

## Answer

All three boards can be pulled whole with one public, unauthenticated request, but none separates boilerplate cleanly and none gives a closing date. Full findings, per ATS and per question, with sources and live-request evidence: [research/ats-board-apis.md](../research/ats-board-apis.md).

- **Whole board**: yes for all three, one GET, no key, no paging in practice (up to about 14 MB for a large Ashby board).
- **Description in the list**: Greenhouse only with `?content=true` (entity-escaped HTML); Lever always, split across `description`, `lists` and `additional`; Ashby always, as HTML and plain text.
- **Structured fields**: title, location, id and URL on all three. Workplace type: none on Greenhouse (only per-company custom metadata), Lever's live value differs from its docs, Ashby's may be null. Compensation: Greenhouse only on the single-job endpoint (the pay text is inside the description), Lever optional `salaryRange`, Ashby with `includeCompensation=true`.
- **Dates**: Greenhouse `first_published` and `updated_at` (bumped in bulk, so useless as a change signal); Lever `createdAt` only; Ashby `publishedAt` only. No usable closing date anywhere: closing is detectable only by absence from a full snapshot, as already decided.
- **Reposts**: undocumented on all three. Inference only: a duplicate is a new id with the same text; Greenhouse groups several posts of one job under `internal_job_id`.
- **Boilerplate**: Greenhouse often wraps it in undocumented `content-intro`, `content-conclusion` and `content-pay-transparency` divs; Lever's `opening` and `additional` often hold it, inconsistently; Ashby repeats it inline (25 to 40 percent of the text). A cross-ATS fallback: drop paragraphs repeated on at least half of a board's postings in the same snapshot before hashing.
- **Rate limits and terms**: none documented for these read endpoints; Lever says published postings may be scraped by third parties.
- **Board URLs**: patterns and board-id extraction for each ATS are tabled in the findings, including Greenhouse's redirect to `job-boards.greenhouse.io`, its embed form, and Lever's EU host. Greenhouse's EU board host has no documented API.
- **Caution**: some Lever boards return an empty list while their hosted page is gone, so an empty "complete" snapshot should not close every posting.

Open: the tally of which ATS the user's companies are on needs the user's company list; it moves to [Which ATS are the user's target companies on?](09-company-ats-tally.md).
