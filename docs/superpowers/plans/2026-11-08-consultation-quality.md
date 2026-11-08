# Consultation quality: implementation plan

**Goal:** a consultation on real models finishes, reasons soundly and reads well, on paper and on screen.
**Approved by Roy, 2026-11-08:** "you have a green light, finish everything and push." Web research uses an AI model with web search enabled.

**Why now:** the first real-model run (CleanHour, 2026-11-08) stopped at the plan summary. Every PDF was DRAFT, a claim its own diagnosis called untestable was stated as fact, and no demand, competitor or owner-income question was asked. Every earlier end-to-end test used stub replies.

## Global constraints

- Figures: `theirs`, `derived`, `ours`, `reference`. The arithmetic is never the model's. No invented clients, numbers or names.
- A `reference` figure exists only after code has fetched the page and found the number on it.
- No hedging boilerplate. Honesty comes from what was checked and from stating what is not known.
- `app/pipeline/**`, `app/prompts/**`, `tools/**`, top-level `tests/*.py` are hash-frozen: changing them means re-running `tests/engine/refreeze_r30.py` after the commit.
- Tests never call a model. Quality is proven by real runs on an isolated database with mail off.
- Baseline: 4 known failures in the consultant suite. Anything else red is new.

## Tasks

1. **Safe and reliable.** Done: only pictures are public, and picture addresses carry a key; thinking models get token headroom.
2. **The interview covers what the answer depends on.** For a business being planned the brief must ask about demand evidence, competitors and their prices, the cost of winning a customer, running costs, and what the founder needs to earn. The business name is asked once, and stored as the name rather than the sentence it came in.
3. **The sums come first.** A new stage before the diagnosis: the model proposes which sums matter, as expressions over figure ids; code computes them through `figures.calc` and stores `derived` figures (break-even, take-home at the goal, months of runway). They join `known_for`, so the diagnosis, the answer and the documents use them and the number law accepts them.
4. **Market evidence.** A research stage using a web-search model through OpenRouter. Code fetches each cited page and confirms the number is on it before a `reference` figure exists. What cannot be confirmed is dropped.
5. **Confidence binds the words.** Code works out how strong the evidence is from the diagnosis verdict and confidence. A finding that is untested cannot be written as settled: the answer says what is not yet known and the cheapest way to find out.
6. **Clean documents.** Internal ids never print (`T6-2`, `TH-...-38`), money uses the client's currency, a section built for a running business does not appear for one being planned, and the DRAFT causes from the first run are gone.
7. **The screens.** Walk the consultation on a finished real run at desktop and phone width and fix what is wrong.
8. **Measure.** A fixed set of founder and owner cases, each run on real models and graded against one rubric.

## Needs something from Roy

- Payment for the $200 consultation needs a payment-provider account. It cannot be finished without one.

## Rubric for task 8

Finished without a stop. No DRAFT stamp. The headline is no stronger than its evidence. At least one derived figure the client did not state changes the advice. Market claims are sourced or said to be unknown. A founder could act on page one.
