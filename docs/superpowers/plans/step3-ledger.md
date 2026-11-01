# Step 3 ledger

Rulings made while executing `docs/superpowers/plans/2026-11-01-step3-output-shape.md`. The spec wins where it and the plan disagree.

Ruling: commit messages say why and do not carry a Claude co-author line - this session is not that model, and a trailer naming someone else would be false - history lacks the trailer the plan asked for.

Ruling: the roadmap states the plan's real length (plan R7), not a fixed "ninety days" - the spec names a ninety-day plan and also says each file is sized by the business; a six-week plan called ninety days would state a length it does not have - Roy may still want those words as the file's name.

Ruling: the answer page is assembled when the package is rendered, from what the run already stored (plan R1), and the register is computed from the headline so its ranges add up to it - the spec says the page is written last, from the register, which is when it is composed, not a new model call that rewrites the answer from the rows - the answer is not rewritten from the register's wording.

Ruling: Task 4 creates `pagelaw.title_lines` and Task 6 adds the rest of the page law to that module - the stage has to measure a title before the page-law task, and the user order runs Task 4 first - the module appears one task early.

Ruling: Task 10 introduces `roadmap.build_roadmap_pdf` only far enough for the zip to contain a real file, and Task 8 replaces the body with the full roadmap - the zip test requires the file and the user order runs Task 10 before Task 8 - one commit has a thin roadmap that the next task fills in.
