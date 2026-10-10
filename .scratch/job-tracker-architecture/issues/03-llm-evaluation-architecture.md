# What is the architecture for the LLM Deal Breaker matching?

Type: grilling

## Question

Once a Job Posting is ingested, we need to evaluate it against the user's Career Profile and defined Deal Breakers. 
How should this matching system operate? 
- Will it run automatically on every ingested Job Posting?
- Do we store the raw LLM responses or just a boolean `is_match` with a `reasoning` text?
- Which LLM provider/model is best suited for this structured extraction and reasoning task?

## Raised elsewhere, to discuss here

Surfaced while resolving the ingestion strategy ticket; noted, not yet discussed.

- Only Job Postings that pass screening, plus all manual entries, reach the LLM. That narrows "run automatically on every ingested Job Posting".
- LLM extraction of structured fields (salary, seniority and so on) was decided there as a step of its own; which fields it produces is open and depends on what Deal Breakers need. Whether extraction and Deal Breaker evaluation are one call or two is also open.
