# What the Greenhouse, Lever and Ashby job board APIs return

Research for [issue 04](../issues/04-ats-board-apis.md). Researched 2026-10-27.

Each claim is tagged with where it comes from:

- **[docs]**: the vendor's official developer documentation (see Sources).
- **[live]**: an unauthenticated `curl` against the public endpoint on 2026-10-27. Boards sampled: Greenhouse stripe, airbnb, figma, discord, robinhood, gitlab, databricks, cloudflare; Lever palantir, spotify, zoox; Ashby ramp, notion, linear, openai.
- **[inference]**: my own reading of the evidence, not stated by the vendor.

Boilerplate figures come from a script that splits each description into paragraphs (more than 80 characters each) and counts the paragraphs repeated on at least half of a board's postings.

## Summary

| | Greenhouse | Lever | Ashby |
|---|---|---|---|
| Whole board in one unauthenticated GET | Yes: `GET boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | Yes: `GET api.lever.co/v0/postings/{site}?mode=json` (EU accounts: `api.eu.lever.co`) | Yes: `GET api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true` |
| Full description in the list response | Only with `content=true` (HTML-entity-escaped) | Always | Always (`descriptionHtml` and `descriptionPlain`) |
| Posting id | `id` (integer, the job *post*); `internal_job_id` = the underlying job | `id` (UUID) | `id` (UUID; not in the docs, present live) |
| Workplace type | No standard field; only through custom `metadata` if the company exposes it | `workplaceType` | `workplaceType` and `isRemote` |
| Compensation | Not in the list; `pay_input_ranges` only on the single-job endpoint with `pay_transparency=true`. Also as text in `content` | `salaryRange` {min, max, currency, interval} and `salaryDescription`, optional | `compensation` object, only with `includeCompensation=true` |
| Department | `departments[]` (with `content=true`) | `categories.department` / `.team` | `department`, `team` |
| Dates | `first_published`, `updated_at`, `application_deadline` | `createdAt` only (epoch ms, not documented) | `publishedAt` ("last published") only |
| Boilerplate separate | **Partly**: board intro, conclusion and pay blurb are wrapped in `<div class="content-intro">`, `content-conclusion` and `content-pay-transparency` inside `content` | **Partly**: `opening` and `additional` are separate fields, but use varies by company | **No**: everything is inline in `descriptionHtml` |
| Rate limits and terms stated | None found | Only for application POSTs (2/s); published postings "may be scraped by third parties" | None found; responses are CDN-cached with `max-age=60` |
| Unknown board | HTTP 404 `{"status":404,"error":"Job not found"}` | HTTP 404 `{"ok":false,"error":"Document not found"}` | HTTP 404 `Not Found` (plain text) |

## Greenhouse (Job Board API)

**Endpoint**
- `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs`. "Job Board data is publicly available, so authentication is not required for any GET endpoints." [docs]
- `content=true` "include[s] the full post description, department, and office of each job post." [docs]
- No pagination is documented for this endpoint, and the response has `meta.total`. [docs]
- Live, one request returned the whole board: stripe 712 postings (5.5 MB with content), databricks 896. [live]

**List fields**
- Without content: `id`, `internal_job_id`, `title`, `updated_at`, `requisition_id`, `location`, `absolute_url`, `language`, `metadata`. [docs]
- Live responses also included `first_published`, `company_name`, `application_deadline`, `education` and `data_compliance` in the list, although the docs show `first_published` only on the single-job endpoint. [live]
- With `content=true`, the list adds `content`, `departments[]`, `offices[]` and `ai_*` fields. [docs, live]
- `location` is `{name}`: free text only. [live]
- `absolute_url` can point to the company's own site, for example `https://stripe.com/jobs/search?gh_jid=8172508`. [live]

**Ids**
- `id` is the job post id. `internal_job_id` "contains the unique identifier for the job itself", and prospect posts have it set to null. [docs]
- One job can have "any number of internal and external job posts", for example one per city or per title, and a post can be duplicated. [Greenhouse support]
- Live, stripe had 21 internal jobs with more than one post (up to 4), and airbnb had 11 (up to 6). [live]

**Workplace type**
- There is no standard field. `metadata` holds whatever custom fields the company chooses to expose. [docs]
- Airbnb exposes a "Workplace Type" select (`Hybrid`, `Remote`). Stripe's `metadata` is null. [live]

**Compensation**
- `pay_input_ranges` (`min_cents`, `max_cents`, `currency_type`, `title`, `blurb`) is returned only by `GET …/jobs/{id}?pay_transparency=true`. [docs]
- Live: present for figma, discord and robinhood (robinhood's are hourly zones in cents); empty for stripe. [live]
- The same pay text usually also sits inside `content` in a `content-pay-transparency` div: on 153 of 189 airbnb postings, 487 of 896 databricks, 90 of 141 figma. [live]

**Description encoding**
- `content` is HTML escaped as entities: "Any HTML … will be automatically converted into corresponding HTML entities." [docs, live]

**Boilerplate**
- The board-level intro and conclusion are injected into `content`, wrapped in `<div class="content-intro">` and `<div class="content-conclusion">`. [live; the class names are not documented]
- Prevalence: airbnb, figma, discord, robinhood, gitlab and cloudflare had both on 100% of postings; databricks had the conclusion only. Stripe uses neither. [live]
- With the three divs removed, most repeated text disappears. Remaining shared paragraphs:
  - zero at discord, gitlab, databricks and cloudflare;
  - about 0.4–0.9 kB per posting at airbnb, figma and robinhood, out of 2.8–5.1 kB, where the company pasted EEO or perks text into the body itself.

  [live]
- Before removal, for comparison: airbnb had 2.7 kB of shared text out of 7.0 kB per posting, figma 3.5 kB out of 6.0 kB. [live]

**Dates**
- `first_published`, `updated_at` and `application_deadline` (rarely set: 1 of 189 at airbnb, 0 of 712 at stripe). [docs, live]
- `updated_at` is bumped in bulk:
  - every stripe posting had an `updated_at` within the last 7 days (536 of them on 2026-10-22);
  - 382 of 461 cloudflare postings were updated on 2026-10-21.

  [live]
- [inference] `updated_at` changes for reasons other than a text edit, so it is no use as a change signal.

**Board identifier**
- `{board_token}`, the "Job Board URL token". [docs]
- The "Retrieve a job board" endpoint `GET /v1/boards/{token}` returns `{name, content}`, which is a cheap existence check. [docs, live]

## Lever (Postings API)

**Endpoint**
- `GET https://api.lever.co/v0/postings/{SITE}?mode=json`, with an EU instance at `https://api.eu.lever.co/v0/postings/`. [docs]
- Optional `skip` and `limit` exist, with no default limit documented. [docs]
- Live, one request with no `limit` returned all postings: palantir 307 (6.0 MB), zoox 232. [live]
- The docs do not explicitly say GET needs no authentication, but they state "all job postings in the `published` state are publicly viewable" and "These jobs may be scraped by third parties". No key was needed live. [docs, live]
- "Each company currently only has one site (usually your company name with no spaces)." [docs]

**Fields**
- Documented: `id`, `text` (title), `categories` {location, commitment, team, department, allLocations}, `country`, `description`, `descriptionPlain`, `opening`, `openingPlain`, `descriptionBody`, `descriptionBodyPlain`, `lists[]` {text, content}, `additional`, `additionalPlain`, `hostedUrl`, `applyUrl`, `workplaceType`, `salaryRange`, `salaryDescription`. [docs]
- `description` is "Combined job description opening and body". [docs]
- [inference from the field definitions] `lists` and `additional` are not part of `description`. The full text is `description` + `lists` + `additional`.
- `workplaceType` is documented as `unspecified | on-site | remote | hybrid`, but live returns `onsite` (no hyphen). Tolerate both. [docs vs live]
- `createdAt` (epoch milliseconds) appears live on every posting but is not documented. There is no `updatedAt`. [live]

**Compensation**
- `salaryRange` {min, max, currency, interval}, documented as optional. [docs]
- Live: zoox had 218 of 232 (`{'min':123000,'max':168000,'currency':'USD','interval':'per-year-salary'}`); palantir and spotify had none. Spotify writes pay text into `additional` instead. [live]

**Boilerplate**
- `opening` and `additional` are the natural boilerplate slots, but companies use them inconsistently. [live]
  - palantir: `opening` is near-pure boilerplate ("A World-Changing Company"), and `additional` is about 2.8 kB of 3.2 kB repeated text.
  - spotify: `opening` is almost always empty; `additional` holds EEO text and pay.
  - zoox: `opening` is empty; "About Zoox" sits in `additional` on 123 of 232 postings.
- `descriptionBody` had no paragraph repeated on half or more of the postings at any of the three companies. [live]
- `lists` had at most one repeated paragraph, at spotify. [live]

**Dates and reposts**
- Only `createdAt`. Palantir's oldest live posting has `createdAt` 2009-12-05 (London, Forward Deployed Software Engineer). [live]
- [inference] Evergreen postings keep their id and creation date for years.

**Board identifier**
- `{SITE}` in `jobs.lever.co/{SITE}`. Docs example: `https://jobs.lever.co/leverdemo`. [docs]

## Ashby (public job posting API)

**Endpoint**
- `GET https://api.ashbyhq.com/posting-api/job-board/{JOB_BOARD_NAME}?includeCompensation=true`. [docs]
- No authentication is mentioned, and none was needed live. [docs, live]
- "The final part of the URL path [of the hosted job board] will be the jobs page name." [docs]
- One request returns the whole board: openai 795 postings (13.9 MB with compensation). [live]
- The board name is case-insensitive: `Ramp` and `RAMP` both return 200. [live]

**Fields**
- Documented: `title`, `department`, `team`, `employmentType`, `location`, `secondaryLocations[]`, `address.postalAddress`, `isRemote` (true for Remote *or* Hybrid), `workplaceType` (`OnSite | Remote | Hybrid`), `publishedAt`, `isListed`, `jobUrl`, `applyUrl`, `descriptionHtml`, `descriptionPlain`, `compensation`. [docs]
- Not documented but present live:
  - `id` (UUID, the same as the last segment of `jobUrl`);
  - `shouldDisplayCompensationOnJobPostings`;
  - top-level `apiVersion` ("1").

  [live]
- `workplaceType` can be null: 52 of 140 at notion. [live]
- All postings live had `isListed: true`. [live]

**Compensation**
- The `compensation` object is absent without `includeCompensation=true` (checked on ramp). [docs, live]
- With the parameter it holds:
  - `compensationTierSummary` (string);
  - `scrapeableCompensationSalarySummary`;
  - `compensationTiers[]`, whose components include `compensationType`, `interval`, `currencyCode`, `minValue` and `maxValue`;
  - `summaryComponents[]`.

  [docs, live]
- Coverage: populated for ramp (166 of 173) and openai (632 of 795); empty tiers for notion and linear. It matches `shouldDisplayCompensationOnJobPostings`. [live]

**Boilerplate**
- Fully inline in `descriptionHtml`, with no wrapper or class seen. [live]
- Shared paragraphs per board: ramp 11 (1.7 kB of 4.6 kB average), notion 2.6 kB of 6.9 kB, openai 2.5 kB of 6.3 kB, linear 1.3 kB of 3.4 kB. [live]

**Dates**
- `publishedAt`, "when the job was last published". There is no created, updated or closing date. [docs]
- Ashby's admin UI tracks "Days since last published, Created At date, and Published At date" separately, but only `publishedAt` is exposed. [Ashby product update]
- Linear has a posting with `publishedAt` 2021-04-27 still live. [live]

## Answers per ticket question

**1. Public, unauthenticated, whole-board endpoint?** Yes for all three: one GET per board, no key, no pagination needed in practice (see each ATS section). Greenhouse needs `content=true` for descriptions; Ashby needs `includeCompensation=true` for pay.

**2. Structured envelope fields**

| Envelope field | Greenhouse | Lever | Ashby |
|---|---|---|---|
| title | `title` | `text` | `title` (may have leading whitespace, e.g. `' Security Engineer, Cloud'` [live]) |
| location | `location.name` (free text); `offices[]` | `categories.location`, `categories.allLocations[]`, `country` | `location`, `secondaryLocations[]`, `address.postalAddress` |
| workplace type | none standard (custom `metadata` only) | `workplaceType` | `workplaceType` (nullable), `isRemote` |
| compensation | single-job `pay_input_ranges` only | `salaryRange` (optional) | `compensation` (opt-in parameter) |
| department | `departments[].name` | `categories.department`, `categories.team` | `department`, `team` |
| updated timestamp | `updated_at` (noisy, bulk-bumped) | none | none (`publishedAt` only) |
| posting id | `id` (int; `internal_job_id` groups posts of one job) | `id` (UUID) | `id` (UUID, not documented) |
| URL | `absolute_url` (may be the company's own domain) | `hostedUrl`, `applyUrl` | `jobUrl`, `applyUrl` |

**3. Full description in the list?** Greenhouse: yes with `content=true` (entity-escaped HTML). Lever: yes, always, as HTML and plaintext, but split across `description`, `lists` and `additional`. Ashby: yes, always, as HTML and plaintext. No per-posting requests are needed, except for Greenhouse structured pay (`pay_input_ranges`), which is per job.

**4. Rate limits and usage terms**
- None of the three documents a rate limit for these GET endpoints. Lever's only stated limit is 2 application POSTs per second, which "may also be changed without warning". [docs]
- No terms of use appear on any of the three API pages. Lever says published postings "may be scraped by third parties". [docs]
- Ashby responses carry `cache-control: public, max-age=60` and are served from Cloudflare cache. Greenhouse returns a weak `etag`; Lever returns an `ETag`. [live]
- [inference] One request per board per day is far below any plausible limit. Conditional requests with the etag are possible but unnecessary.

**5. Board URL patterns → identifier → API URL**

| Pasted URL pattern | ATS | Identifier | API URL |
|---|---|---|---|
| `boards.greenhouse.io/{token}` (301 → job-boards) [live] | Greenhouse | `{token}` | `https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` |
| `job-boards.greenhouse.io/{token}` (may 302 to the company site) [live] | Greenhouse | `{token}` | same |
| `boards.greenhouse.io/{token}/jobs/{id}`, `job-boards.greenhouse.io/{token}/jobs/{id}` [live] | Greenhouse | `{token}` (+ post id) | same |
| `boards.greenhouse.io/embed/job_board?for={token}` (301 → `job-boards.greenhouse.io/embed/job_board?for=`) [live] | Greenhouse | `for` query parameter | same |
| `job-boards.eu.greenhouse.io/{token}` (host exists [live]) | Greenhouse EU | `{token}` | **unknown**: `boards-api.eu.greenhouse.io` does not resolve in DNS [live]; no EU host in the docs |
| company domain with `?gh_jid={id}` | Greenhouse | post id only, **not the board** | cannot be parsed to a board |
| `jobs.lever.co/{site}[/{uuid}[/apply]]` [docs, live] | Lever | `{site}` | `https://api.lever.co/v0/postings/{site}?mode=json` |
| `jobs.eu.lever.co/{site}[/…]` | Lever EU | `{site}` | `https://api.eu.lever.co/v0/postings/{site}?mode=json` [docs; no EU board found to test] |
| `jobs.ashbyhq.com/{name}[/{uuid}[/application]]` [docs, live] | Ashby | `{name}` | `https://api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true` |

Notes:
- [inference] Lowercase the identifier for Ashby, which is case-insensitive live.
- [inference] Keep the Lever region with the Watchlist entry: the identifier alone does not say which region a board is in.

**6. Dates and reposts**
- Greenhouse:
  - Dates: `first_published`, `updated_at`, `application_deadline` (rarely set).
  - The docs say nothing about reposts. The support docs describe two practices: multiple posts per job, and **Duplicate** to copy a post. Taking a post Offline "removes the page from the internet and any links to the post stop working". [Greenhouse support]
  - [inference] A duplicated post is a new `id` with the same text and the same `internal_job_id`. An Offline-then-Live toggle probably keeps the `id`; not verified.
- Lever:
  - Dates: `createdAt` only, undocumented. No repost semantics are documented.
  - [inference] Postings left open for years keep their id; a "repost" by creating a new posting gives a new UUID with the same text.
- Ashby:
  - Dates: `publishedAt` = "last published". No creation or closing date.
  - [inference] Republishing the same posting keeps the `id` and moves `publishedAt`. A new posting is a new UUID.
- None of the three exposes a closing date in practice: Greenhouse's `application_deadline` is almost always null. Closing can only be detected by absence from a snapshot.

**7. Is boilerplate in a separate field?**
- Greenhouse: not a separate field, but in practice separable. Board-level intro, conclusion and pay text sit inside `content` in `content-intro`, `content-conclusion` and `content-pay-transparency` divs. These carry most of the repeated text on the boards sampled. [live; class names undocumented]
- Lever: partly separate. `opening` and `additional` (and sometimes `lists`) often carry the company boilerplate, but not reliably, and some companies put it in the body. [docs for fields; live for usage]
- Ashby: not separate. Repeated text is inline in `descriptionHtml`, about 25–40% of each posting's text on the boards sampled. [live]

**8. Tally of which ATS the user's companies are on**: **open**. It needs the user's company list and was not attempted.

## Implications for the ingestion design

1. **One request per board, no detail calls.** All three adapters can fill the envelope and description from one GET. Greenhouse `pay_input_ranges` would need N extra calls, but it is not needed: the pay text is in `content` for the LLM extraction.
2. **The posting id is the ATS key.** Use Greenhouse `id` (not `internal_job_id`), Lever `id` and Ashby `id`. Greenhouse multi-post jobs will look like near-duplicates with distinct ids, which is correct, since they are distinct postings (different city or title).
3. **Hash input must strip boilerplate, per ATS:**
   - Greenhouse: hash `content` with the `content-intro`, `content-conclusion` and `content-pay-transparency` divs removed. This handles most board-wide edits deterministically, but these class names are undocumented and could change.
   - Lever: hash `descriptionBody` + `lists`, and exclude `opening` and `additional`.
     - [inference] Risk: a real edit in `additional` (for example a pay change at spotify) would be missed by the hash.
   - Ashby: no structural boundary. Options:
     - (a) hash the full text and accept re-evaluation when boilerplate changes;
     - (b) strip paragraphs that appear on at least half of the board's postings in the same snapshot, which needs the whole snapshot (and the webapp has it);
     - (c) store the per-board common-paragraph set and hash the remainder.

     Option (b) also works as a uniform fallback for all three ATSs and for Greenhouse boards like stripe that do not use the divs.
   - Store and show the full text in every case; only the hash input is reduced.
4. **Don't use ATS timestamps for change detection.** Greenhouse `updated_at` is bumped in bulk (all 712 stripe postings in one week), and Lever and Ashby have no updated time at all. The design's own hash is the right signal.
5. **Closing detection by absence is the only option.** It is safe because each endpoint returns the whole board in one response, so "complete snapshot" is simply a 200 with valid JSON.
   - A 404 means the board is gone or was mistyped. Report it as a failed pull, not as "every posting closed".
   - An empty array `[]` was seen for some Lever sites (mistral, whoop, kraken) whose hosted pages 404. [inference] Treat an empty board as complete but suspicious: perhaps close nothing when the previous snapshot was large and this one is empty.
6. **Dates in the envelope.** Map Greenhouse `first_published`, Lever `createdAt` and Ashby `publishedAt` into an optional "ATS published" field, kept separate from the webapp's own first-seen date. Their meanings differ, and Ashby's moves on republish.
7. **Reposts** under a new id with the same text will arrive as new postings. The duplicate detection planned for manual entries could be extended to flag same-company, same-title, same-hash Pipeline postings.
8. **Workplace type** is missing for Greenhouse (except custom `metadata`) and nullable for Ashby. Keep it optional, and normalise Lever `onsite`/`on-site` and Ashby `OnSite` to one vocabulary.
9. **Watchlist URL parser** must handle these cases:
   - the Greenhouse `?for=` variant;
   - the Lever `.eu.` host: store the region with the entry;
   - case-insensitive Ashby names;
   - Greenhouse boards that redirect to a custom domain: the pasted URL may be the company's own careers page, and `gh_jid` gives no board token.

   Greenhouse EU (`job-boards.eu.greenhouse.io`) has no confirmed API host. Treat it as unsupported until it is verified against a real EU board.
10. **Payload size.** The largest boards are 5–14 MB per daily request (openai, palantir, stripe). This is acceptable, but the ETL-to-webapp snapshot call should expect payloads of that size.

## Open / not established

- The tally of the user's companies by ATS needs the user's company list.
- The Greenhouse EU API host: none documented, and `boards-api.eu.greenhouse.io` does not resolve. No EU board was found to test.
- The Lever EU instance is documented, but no EU-hosted site was found to verify it live.
- Repost behaviour is undocumented for all three. The statements in section 6 are inferences.
- Whether Greenhouse's `content-intro` and `content-conclusion` wrappers are a stable contract: they are undocumented.
- Rate limits: none documented for any of the three GET endpoints.

## Sources

- Greenhouse Job Board API docs: https://docs.greenhouse.io/job-board.html (formerly developers.greenhouse.io/job-board.html)
- Greenhouse support, multiple job posts: https://support.greenhouse.io/hc/en-us/articles/217267766-Create-multiple-job-posts-for-a-single-job
- Greenhouse support, job post status: https://support.greenhouse.io/hc/en-us/articles/16183212618139-Change-a-job-post-s-status
- Lever Postings API (official repo/README): https://github.com/lever/postings-api
- Ashby public job posting API: https://developers.ashbyhq.com/docs/public-job-posting-api
- Ashby product update (posting list columns): https://www.ashbyhq.com/product-updates/job-posting-list-ux
- Live requests, 2026-10-27 (raw JSON kept outside the repo in the session scratchpad):
  - `https://boards-api.greenhouse.io/v1/boards/{stripe,airbnb,figma,discord,robinhood,gitlab,databricks,cloudflare}/jobs?content=true`
  - `…/jobs/{id}?pay_transparency=true`
  - `https://api.lever.co/v0/postings/{palantir,spotify,zoox}?mode=json`
  - `https://api.ashbyhq.com/posting-api/job-board/{ramp,notion,linear,openai}?includeCompensation=true`
