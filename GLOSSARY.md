# Job Scout

Job Scout surfaces the Job Postings that match the user's Career Profile, evaluates them against Deal Breakers, and helps the user apply, including custom cover letters and tracking each Application.

## Language

**Job Posting**:
The actual job description and details available on the market, whether scraped via ATS or entered manually.
_Avoid_: Job, Listing, Opportunity

**Application**:
The user's tracked progress in applying for a specific Job Posting (e.g., applied, interviewing, rejected).
_Avoid_: Job

**Career Profile**:
A living, comprehensive document encompassing all of the user's professional experience, projects, and skills. It evolves with each application and serves as the master knowledge base for the LLM, bypassing the constraints of a traditional 2-page resume.
_Avoid_: Resume, CV, Experience

**Deal Breaker**:
A strict user-defined criterion that, if unmet, disqualifies a Job Posting.
_Avoid_: Preference, Requirement

**Screening Rule**:
A cheap user-defined criterion on a Job Posting's title or location that decides whether the posting is worth evaluating at all. A screened-out Job Posting is kept, not discarded.
_Avoid_: Filter, Pre-filter, Deal Breaker (which is judged on the full posting)

**Pipeline**:
An automated ingestion mechanism to pull Job Postings from specific ATS platforms (like Greenhouse).

**Watchlist**:
The user-maintained set of companies whose Job Postings the Pipelines pull. A company not on the Watchlist is only reachable through manual entry.
_Avoid_: Company list, Sources, Subscriptions
