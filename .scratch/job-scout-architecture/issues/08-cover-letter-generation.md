# How does the app generate a Cover Letter for an Application?

Type: grilling

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
