# Job Scout

Job Scout surfaces the Job Postings that match the user's Career Profile, evaluates them against Deal Breakers, and helps the user apply, including custom cover letters and tracking each Application.

## Language

**Job Posting**:
The actual job description and details available on the market, whether scraped via ATS or entered manually.
_Avoid_: Job, Listing, Opportunity

**Triage**:
The user's own sorting of a Job Posting into Interested, Maybe or Ignored. It overrides the Evaluation's recommendation. A Job Posting the user has not sorted is untriaged.
_Avoid_: Mark, Decision, Rating, Screening (which is done by Screening Rules)

**Application**:
The user's tracked progress in applying for a specific Job Posting, from preparing it through to its outcome (e.g., applied, interview loop, rejected). It exists only once the user starts applying; Triage comes before it.
_Avoid_: Job

**Cover Letter**:
The letter the user sends with one Application, written from the Career Profile and the Job Posting and finished by the user. An Application has at most one, and its successive texts are drafts of that one letter.
_Avoid_: Motivation letter, Letter (alone), Draft (which is one text of a Cover Letter)

**Writing Guide**:
The user's own description of how their Cover Letters should read: tone, length, structure, phrases to avoid, and sample letters they are happy with.
_Avoid_: Style guide, Template, Writing sample

**Career Profile**:
A living, comprehensive document encompassing all of the user's professional experience, projects, and skills. It evolves with each application and serves as the master knowledge base for the LLM, bypassing the constraints of a traditional 2-page resume.
_Avoid_: Resume, CV, Experience

**Deal Breaker**:
A strict user-defined criterion that, if unmet, disqualifies a Job Posting.
_Avoid_: Requirement, Preferences (which never disqualify)

**Preferences**:
The user's own description of what they are looking for and how to weigh it: target roles, level, what appeals and what they would rather avoid. Preferences shape an Evaluation but never disqualify a Job Posting on their own.
_Avoid_: Deal Breaker (which disqualifies), Search criteria, Screening Rule

**Evaluation**:
A judgement of one Job Posting against the Career Profile, Deal Breakers and Preferences, made to help the user decide whether applying is worth it. It holds a verdict per Deal Breaker, red and green flags, a score used only for ordering, and a recommendation.
_Avoid_: Match, Matching, Assessment

**Screening Rule**:
A cheap user-defined criterion on a Job Posting's title or location that decides whether the posting is worth evaluating at all. A screened-out Job Posting is kept, not discarded.
_Avoid_: Filter, Pre-filter, Deal Breaker (which is judged on the full posting)

**Pipeline**:
An automated ingestion mechanism to pull Job Postings from specific ATS platforms (like Greenhouse).

**Watchlist**:
The user-maintained set of companies whose Job Postings the Pipelines pull. A company not on the Watchlist is only reachable through manual entry.
_Avoid_: Company list, Sources, Subscriptions
