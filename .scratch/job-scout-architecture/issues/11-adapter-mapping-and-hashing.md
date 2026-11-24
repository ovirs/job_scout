# How does each ATS payload map to the envelope, and what text is hashed?

Type: grilling

## Question

Given [What do the Greenhouse, Lever and Ashby job board APIs actually return?](04-ats-board-apis.md): which fields fill each envelope field per ATS (workplace type where there is none or it is null, which Lever text parts make the description, Greenhouse multiple posts of one job); how boilerplate is kept out of the change hash (Greenhouse content divs, Lever opening/additional, the repeated-paragraph fallback) without hiding it from extraction and the Evaluation; whether compensation from the ATS is used or left to extraction; and when a snapshot counts as complete (an empty board, a vanished Lever site). Revisits parts of [How will we architect the ATS ingestion pipelines and manual entry flow?](02-data-ingestion-strategy.md) that assumed the description could be hashed whole.
