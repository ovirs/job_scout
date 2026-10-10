# Every Job Posting is stored; screening only gates LLM extraction

The ETL sends every Job Posting on a watched board to the webapp, which stores all of them; Screening Rules run in the webapp afterwards and decide only whether a posting goes on to LLM extraction. We chose this over dropping non-matching postings in the ETL because the Screening Rules will change: with everything stored, a changed rule re-screens existing postings at once, screened-out postings can be reviewed to catch a rule that is too tight, and keyword search covers whole boards. The cost is a database that mostly holds postings the user never wanted, which we accept because the volume is a few thousand rows.

## Consequences

- The ETL holds no user criteria and filters nothing; the Screening Rules are webapp data, like the Watchlist.
- Screening scores are stored on the Job Posting, so changing a threshold needs no new scoring calls.
- A screened-out Job Posting is a normal row that never reaches the LLM. Anything that counts or lists Job Postings has to decide whether it means all of them or only the screened-in ones.
- Manual entries skip screening and always go to extraction.
