# What do the Greenhouse, Lever and Ashby job board APIs actually return?

Type: research

## Question

The ingestion strategy picked Greenhouse, Lever and Ashby as the first adapters from memory, without checking their APIs. For each of the three, from the primary documentation:

- Is there a public, unauthenticated endpoint that returns a company's whole board in one request?
- Which envelope fields are structured: title, location, workplace type, compensation, department, updated timestamp, posting id, URL?
- Does the list response include the full description, or does each posting need its own request?
- What rate limits or usage terms apply?
- What does a board URL look like, so the webapp can recognise the ATS and extract the board identifier from a pasted URL?

- Which dates does each posting carry (first published, last updated, closing date), and how does a repost appear: the same posting id with a new date, or a new posting id with the same text?

Also needed, and it takes the user's company list: a tally of which ATS each company the user cares about is on, to decide whether a fourth adapter (Workday or another) is needed early.
