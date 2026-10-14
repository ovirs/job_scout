# Fit is judged holistically by the LLM and checked against the user's own decisions

An Evaluation's recommendation and score come from the LLM reading the whole Job Posting against the Career Profile, Deal Breakers and Preferences, not from code that counts matched requirements. We considered having the LLM list each requirement, mark the evidence for it, and computing a score with thresholds in code, which would be steadier between runs and tunable without new calls. We rejected it because postings are written too differently to itemise reliably and because the things that decide fit (what the role does day to day, how much a technology is emphasised, how the level is framed) are lost when every requirement counts the same. The cost is a judgement that cannot be tuned by moving a number, so it is controlled in three other places: the user's own inputs, a fixed output shape with evidence written before the verdict, and a test set built from the user's own marks.

## Consequences

- The recommendation is given directly by the LLM. The 1 to 10 score is only for ordering and is never turned into a recommendation by thresholds.
- Deal Breakers are the exception: each gets its own verdict, and a violated one sets the lowest recommendation in code. The LLM's own recommendation is kept, and a posting it recommended despite a violated Deal Breaker is surfaced for manual review. The prompt itself tells the LLM that a violated Deal Breaker means skip, so that review catches an Evaluation that contradicts itself; how strict a Deal Breaker is lives in its wording, which names the signals that count as evidence.
- Every piece of evidence the LLM quotes is checked in code to occur in the posting; a result that quotes words the posting does not contain is rejected.
- Any change to the prompt, the model or the wording of the Preferences is judged by re-running the test set and reading the agreement, so the test set is part of the system and not an optional extra. Until the test set is large enough to trust its figures, it is read posting by posting.
- Tuning costs LLM calls. Each Evaluation records the model, prompt version and input versions so runs can be compared.
- Extracted fields are facts for filtering and display and do not feed the Evaluation.
