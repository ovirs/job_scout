# What do the evaluation and extraction prompts say, and when is the test set trusted?

Type: prototype
Status: claimed

## Question

The LLM evaluation ticket fixed the shape of an Evaluation and left its wording open; the Application workflow ticket has now fixed the Triage values the test set is labelled with (Interested, Maybe, Ignored).

- What do the evaluation and extraction prompts say: the description of each score level from 1 to 10, the wording of the three recommendation levels so they line up with Interested, Maybe and Ignored, and the instructions for Deal Breaker verdicts and flags?
- How many triaged postings, and how many of each Triage value, must the test set hold before its agreement figure is trusted? Few Ignored labels will exist on postings the LLM skipped unless the user triages some from the skip list.
- How is agreement reported: per recommendation level, and how is the score's ordering compared with three Triage values?
