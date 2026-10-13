# How does the app generate a Cover Letter for an Application?

Type: grilling
Status: resolved (2026-10-13)

## Question

Cover Letter generation is part of phase 1: the user cannot apply without one. The Application workflow ticket gave it a home, the Preparing state of an Application, and nothing else about it is decided.

- What goes into the LLM call: the Job Posting, the Career Profile, the Evaluation's flags, a writing sample or style guidance, instructions typed by the user for this one letter?
- How does the user work on the result: regenerate, edit by hand, ask for a revision in words? Are earlier drafts kept?
- What is stored on the Application, and is the letter frozen when the Application becomes Applied, as the posting copy is?
- In what form does the letter leave the app (copied text, a file), and does the app need to know the language or length the posting asks for?
- Which model, and how is a letter's quality judged, given that the Evaluation's test set does not cover it?
- Is "Cover Letter" a glossary term, and does an Application have at most one?

## Raised elsewhere, to discuss here

- The map lists, as not yet specified, updating the Career Profile from what the user writes during new applications. Edits made to a letter are one likely source; decide here whether this ticket only leaves room for that or takes it on.

## Answer

A Cover Letter belongs to one Application, is written by the LLM on request while the Application is Preparing, and is finished by the user. Two glossary terms are new: Cover Letter and Writing Guide.

- **Cover Letter**: the letter the user sends with one Application. An Application has at most one, and it has no existence outside an Application. Its successive texts are drafts of that one letter; the latest draft is the Cover Letter.
- **Trigger**: an explicit "generate cover letter" action, available only while the Application is Preparing. Starting an Application generates nothing.
- **Inputs**: the Job Posting's live title, company and description; the whole Career Profile; the Evaluation's green and red flags, as hints on what to emphasise and which gaps to address; the Writing Guide; optional instructions typed for this one letter. Preferences and Deal Breakers are left out, so the user's private reasons cannot leak into a letter a company reads. Letters the user already sent are never fed in automatically.
- **Writing Guide**: one free-text document the user edits, passed whole: tone, length, structure, phrases to avoid, and one or two pasted letters as samples. It is versioned like the Career Profile, Deal Breakers and Preferences.
- **Truthfulness**: every claim about the user is restricted to what the Career Profile states. Where the posting asks for something the profile lacks, the letter leaves it out. The call also returns the posting requirements it found no support for, shown to the user beside the draft.
- **Missing or outdated Evaluation**: generation never waits for one. Before generating, the app tells the user the Evaluation is missing or outdated and asks for a yes/no confirmation. With none, the letter is written without flags; with an outdated one, its flags are used as they are. The draft records which case applied.
- **Working on the draft**, all while Preparing: edit by hand; ask for a revision in words, which sends the current text (hand edits included) back with the instruction; regenerate from scratch. Every LLM result and every saved hand edit is kept as a draft, and the user can go back to any earlier one.
- **Draft record**: the text, the date, the origin (generated, revised in words, edited by hand), the instruction typed for it, the unsupported requirements, and for LLM drafts the model, the prompt version, the versions of the Career Profile and Writing Guide, and which Evaluation supplied the flags.
- **Posting edited while Preparing**: nothing is regenerated. The Cover Letter shows a "posting edited since this draft" badge.
- **Locking**: the Cover Letter is editable only while the Application is Preparing and locked in every other state. Going back to Preparing unlocks it, and the next move to Applied locks the latest draft. Unlike the posting copy, which never changes once taken, the lock follows the state. Drafts are kept after locking.
- **Applying without a letter**: allowed. The Application shows that no letter was sent.
- **Form**: plain text with a copy button. No file export in phase 1. The LLM writes in the language of the posting unless the per-letter instructions say otherwise; length comes from the Writing Guide. The app holds no language or length fields.
- **Model and call**: Claude Opus 5.5, configurable per step, run in the webapp's background worker. Structured output with two fields: the letter text and the unsupported requirements. The Career Profile and Writing Guide come first in the prompt so they can be cached. A failed call leaves the Cover Letter as it was, shows the reason and waits for a manual retry.
- **Judging quality**: by eye, with two aids and no automated score. For every sent letter the app records how much of the last LLM draft survived into the locked text. A command the user starts regenerates letters for a handful of past Applied Applications under a new prompt or model and shows each beside the letter actually sent; those texts are never saved as drafts.
- **Lifecycle**: the Cover Letter follows its Application. A duplicate merge moves it with the Application. A repost never inherits a letter.
- **Nothing is physically deleted**: a standing rule for everything the user creates. Applications, Cover Letters, drafts and notes are marked with a deletion date and never removed from the database. A deleted record is hidden everywhere in the app and excluded from the quality aids. Phase 1 has no restore screen. This amends the Application workflow ticket: "deleted only while Preparing" means marked as deleted.
- **Starting again after a deletion**: a new Application is created with no Cover Letter, and the deleted one's drafts are not carried over. "At most one Application per posting" means at most one that is not deleted. On deletion the Triage stays Interested and becomes changeable again.
- **Career Profile updates**: not taken on here. Keeping every draft with its origin preserves the difference between what the LLM wrote and what the user changed, which later work would need. The list of unsupported requirements is the only nudge towards the profile in phase 1.

Rejected: generating a letter automatically when an Application starts (costs a call for Applications that need no letter, and leaves no room for instructions first); Preferences and Deal Breakers as inputs; a structured style form or a sample library; feeding sent letters in as style examples (new letters would drift towards the last few); freezing the letter permanently at the first Applied, as the posting copy is; requiring a letter before Applied; an automated quality score; physical deletion.
