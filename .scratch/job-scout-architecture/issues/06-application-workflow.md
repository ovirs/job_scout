# How does the user triage Job Postings and track Applications?

Type: grilling
Status: resolved (2026-10-12)

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
- Same ticket: a Job Posting where a Deal Breaker is violated but the LLM itself recommended applying is surfaced for manual review. Where that list lives and what the user can do from it is open.
- Same ticket: a same-text repost under a new posting id is linked to the earlier Job Posting and copies its Evaluation. What the link means for an existing Application or an earlier "ignored" mark is open.

## Answer

The user's own call on a Job Posting and the progress of applying to it are two separate things. Triage is new and comes first; an Application exists only once the user starts applying.

- **Triage**: the user's sorting of a Job Posting into Interested, Maybe or Ignored, mirroring the three levels of the Evaluation's recommendation. A posting has at most one Triage, and it can be changed. It overrides the recommendation. Any stored posting can be triaged, including screened-out and not-yet-evaluated ones.
- **Untriaged**: the absence of a Triage, not a fourth value. The user never has to ignore anything by hand. The Evaluation's recommendation routes untriaged postings: open ones recommended as apply or maybe form the inbox, ordered by score; ones recommended as skip sit in a separate list. Triaging removes a posting from the inbox: Interested to a shortlist, Maybe to a "later" list, Ignored out of sight. An untriaged posting that closes drops away.
- **Test set labels**: only explicit Triages. An untriaged skip is not counted as agreement, or the Evaluation would confirm itself. Triages copied to a repost are excluded, so one judgement is not counted twice. Labels on LLM-skipped postings exist only if the user opens the skip list and triages some.
- **Application start**: an explicit "start application" action on a posting creates the Application in the state Preparing and sets the Triage to Interested. Triage of Interested alone creates nothing. Starting one on a screened-out posting queues its extraction and Evaluation, as for a manual entry.
- **Application states**: Preparing, Applied, Screen call, Interview loop, Offer, then four closed states: Accepted, Rejected (the company said no), Withdrawn (the user pulled out, including abandoning while Preparing), No response (the user gave up waiting). The user sets the state by hand and can move between any two. Each change is recorded with its date. Interview rounds are dated notes, not states. "Screen call" is never shortened to "Screening", which belongs to Screening Rules.
- **Triage and Application together**: a posting has at most one Application. While it exists, the Triage is Interested and locked. Closing an Application leaves the Triage at Interested. An Application can be deleted only while Preparing; after that it is closed, never deleted.
- **Posting copy**: when an Application becomes Applied, it copies the posting's title, company, location, description and URL, and the copy never changes. The live posting stays linked, and the Application shows when it differs from the copy.
- **Acted on**: a posting with any Triage or an Application. Only untriaged postings are evaluated again automatically when their text changes or in the bulk re-run. An edited posting the user had triaged keeps its Evaluation, marked outdated, shows an "edited since you triaged it" badge, and can be re-run by hand.
- **Cost of edits**: no cap and no boilerplate stripping for now. The webapp records how many postings changed text in each board snapshot, so a mass change (a company editing boilerplate shared by all its postings) is visible. The board API research ticket now asks whether boilerplate comes in a separate field.
- **Disqualified but recommended**: no separate screen. These postings appear in the inbox with a badge naming the violated Deal Breaker and its evidence, and are triaged as usual. Interested marks the gate as wrong; Ignored confirms it. Rewording the Deal Breaker is a separate edit followed by the manual bulk re-run.
- **Reposts**: what a repost inherits depends on the earlier posting. Ignored: the Triage is copied and the repost never reaches the inbox. Maybe, or Interested without an Application: the Triage is copied and a "reposted" badge shown. An Application: the repost stays untriaged and enters the inbox with a badge giving the date applied and the outcome; the Application stays on the earlier posting.
- **Duplicate merge**: the Triage moves to the surviving Pipeline posting along with the Application and notes. If both postings have a Triage, the manual entry's wins.
- **Notes**: free-text, dated notes on a Job Posting and on an Application. A posting's notes stay on the posting when an Application starts and are shown alongside. No structured fields for contacts, interview dates or reminders.
- **Closed postings**: closing on the ATS changes neither Triage nor Application. An Interested posting with no Application stays on the shortlist with a "closed on" badge until re-triaged.

Rejected: triage as an early state of an Application (ignored postings would get Applications, and test labels would be tangled with states like Interview loop); the terms Mark (unclear as a noun), Decision ("undecided" reads as Maybe) and Rating (suggests the score); a single Interviewing state; pre-Applied states beyond Preparing; enforced state transitions; counting untriaged skips as Ignored labels; a separate manual review screen.
