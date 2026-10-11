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
- From the LLM evaluation ticket: the marks the user makes on Job Postings are the labels of the Evaluation test set, so their set of values matters beyond the UI. The Evaluation's recommendation has three levels (roughly apply, maybe, skip); the marks should be comparable to them.
- Same ticket: "has the user acted on this posting" decides whether an edited posting is evaluated again and which postings the bulk re-run covers. This ticket defines what counts as acted on.
- Same ticket: disqualified Job Postings with a strong score are surfaced for manual review. Where that list lives and what counts as strong is open.
- Same ticket: a same-text repost under a new posting id is linked to the earlier Job Posting and copies its Evaluation. What the link means for an existing Application or an earlier "ignored" mark is open.
