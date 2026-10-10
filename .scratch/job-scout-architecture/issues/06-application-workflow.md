# How does the user triage Job Postings and track Applications?

Type: grilling

## Question

Application tracking is essential to the tool, and its workflow is undecided. What states does an Application move through, what actions does the user take at each, and how does the user mark a Job Posting as interesting or ignore it before any Application exists?

## Raised elsewhere, to discuss here

Noted while resolving other tickets and setting the build order; not yet discussed.

- The user wants to mark Job Postings that interest them and ignore ones that don't, even when the evaluation scored them highly. The user's judgment overrides the score.
- The glossary defines an Application as progress in applying for a Job Posting. Marking interest or ignoring happens before that, so it is either an early state of an Application or a separate concept that needs its own term.
- Job Postings are overwritten when the ATS edits them, with no version history (see the ingestion strategy ticket). Should an Application keep a copy of the posting text as it was when the user applied?
- A confirmed duplicate merge moves the Application and notes to the surviving Job Posting (same ticket).
