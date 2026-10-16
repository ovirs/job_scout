# Job Scout

Job Scout surfaces the Job Postings that match the user's Career Profile, evaluates them against Deal Breakers, and helps the user apply, including custom cover letters and tracking each Application.

## Language

**Job Posting**:
The actual job description and details available on the market, whether scraped via ATS or entered manually.
_Avoid_: Job, Listing, Opportunity

**Envelope**:
The part of a Job Posting that every origin provides the same way: its source, company, title, location, workplace type, description, link, and when it was first seen, last seen and closed. The rest is what the LLM reads out of the description.
_Avoid_: Header, Metadata, Core fields

**Manual Entry**:
A Job Posting the user added by hand, from a Clipping, rather than one a Pipeline pulled.
_Avoid_: Manual posting, Custom posting

**Clipping**:
The text the user pasted from a page showing a Job Posting, kept whole while the app reads it, until the user confirms it as a Manual Entry or abandons it. A Clipping is not a Job Posting.
_Avoid_: Paste, Entry draft, Import, Pending entry

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
A line the user will not cross, written in their own words. A Job Posting whose text shows it crosses the line is disqualified; one that is silent on it is not.
_Avoid_: Requirement, Preferences (which never disqualify)

**Preferences**:
The user's own description of what they are looking for and how to weigh it: target roles, level, what appeals and what they would rather avoid. Preferences shape an Evaluation but never disqualify a Job Posting on their own.
_Avoid_: Deal Breaker (which disqualifies), Search criteria, Screening Rule

**User Input**:
What the user writes and maintains for the LLM to work from: the Career Profile, Preferences, Writing Guide and Deal Breakers. Every saved change creates a new version, so each Evaluation and Cover Letter draft records exactly which versions produced it.
_Avoid_: Settings, Config, Profile data

**Document**:
A User Input written as one piece of free text: the Career Profile, Preferences or Writing Guide. Deal Breakers are not a Document, since they are a list of separate one-sentence items.
_Avoid_: File, Note (which belongs to an Application)

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
