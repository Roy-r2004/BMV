# The six fixes, and the trio that came back clean

Session 27, part two. The first trio (`trio-152-157.md`) shipped 1 of 3 and left
one true finding plus four smaller ones. All six were fixed, each gated on a
green suite and a mutation sweep, then the same three briefs were run again.

## The fixes

| | commit | what it was |
|---|---|---|
| **A** planner | `72b6566` | `_inject_blueprint_routes` skipped the blueprint's `/gallery/:id` unless the literal `/gallery` was declared. Two apps shipped a catalogue grid with **no detail route at all** — the direct cause of both withheld runs. |
| **B** appspec | `31fe604` | The repair prompt gave the model no legal move for `state_assertion_state_required`, so it re-emitted the same payload until R2 failed the run closed. Prompt escape + a bounded salvage at the terminal branch. |
| **C** links | `76f0767` | `primaryHref` was invisible to *both* the gate's sweep and the dead-link repair; six dead CTA targets across three apps were reported as zero. |
| **D** brand | `d9d4d51` | "Business" was a second placeholder no filter knew about, and it reached customer-visible copy. |
| **E** literals | `2502043` | The last five route literals — `/contact`, `/checkout`, `/order-tracking`, `/invoices`, `/ticket`. |
| **F** provider | `95eb3bf` | The refusal detector scanned the **model's own output** for the word "safety" and killed the run. |

**Suite 2,153 → 2,233 passed / 1 skipped / 0 failed.** 32 mutations across the six
sweeps, 0 behavioural survivors. Three sweeps needed a second pass and every
first-pass survivor was a fixture defect — the same lesson as sessions 26 and 27a,
now five for five.

## The trio

Restart, verify the running process, simultaneous POSTs (spread 0.002 s), same
three briefs, same reference image.

| id | business | mode | outcome | wall | gate issues | dead links | journey |
|---|---|---|---|---|---|---|---|
| 158 | Kestrel & Fern Bakehouse | plain | **ready** | 563 s | **0** | **0** | browse · detail · inquire |
| 160 | Ridgeline Bike Works | file | **ready** | 554 s | **0** | **0** | browse · detail · inquire |
| 159 | Copperline Hardware | plain | died at blueprint | — | — | — | — |
| 161 | Copperline Hardware (after F) | plain | **ready** | 557 s | **0** | **0** | browse · book |

159 is what found fix F; it was relaunched as 161 once the cause was fixed.

**3 of 3 ready, zero gate issues, zero dead links, every hop walked.** In session
26 the same three briefs produced 1, 4 and 3 gate issues, 1, 3 and 2 dead links,
Ridgeline's whole journey absent and Copperline's booking page reported missing.

`screenshot_session` contention was 7.2 s on 158, and it still finished at 563 s.

## 1. Fix A, visible in the route table

The two runs that were withheld for `journey_no_detail_route` now declare one:

    158  /celebration-cakes/:id  "Celebration Cakes detail"  CelebrationCakesDetailPage.tsx
    160  /bikes/:id              "Bike Range detail"         BikeRangeDetailPage.tsx

Both hung off a catalogue the architect renamed, and neither is called `Artwork`
or lives in `ArtworkDetailPage.tsx` — the naming comes from the listing, because
the title reaches the nav label and the page header.

## 2. Fix C, visible in the seed

The mock writer's call-to-action targets, first trio against second:

| | first trio | second trio |
|---|---|---|
| bakehouse | `/reserve` · `/order` — neither declared | `/celebration-cakes` — declared |
| bike shop | `/shop` · `/alerts` — neither declared | `/workshop/book` — declared |
| hardware | `/gallery` — on a hardware store | `#inquire` · `/hire/reserve` — both live |

Six dead targets became zero, and the guard now aims at the page the business
converts on rather than grounding to `/`.

An independent census over all three shipped workspaces — every `*Href` key in
`src/pages/**` and `src/data/mock.ts`, matched against the routes `App.tsx`
serves, template bases resolved against param routes — reports **no dead literal
links in any of them**.

## 3. Fix F, the one the trio itself found

Request 159 died eleven seconds in, with the model's own business summary as the
error message:

> Copperline Hardware is a multi-service independent retailer specializing in
> high-quality garden and tool lines alongside a professional tool-hire desk…

`_looks_like_refusal(finish_reason, error_message)` was being called with the
**assistant's output text** as `error_message` and scanning it for
`content_filter | content filter | refusal | refused | safety | moderation`.
A hardware store that hires out tools writes "safety" into its own description,
so the pipeline read the business back to itself, classified it
`provider_content_refused` with `retryable=False`, and the transport ladder above
it correctly declined to re-ask a refusal.

Across all **138 stored blueprints the scan had never matched once**. It was not
a check that mostly worked — it was a check nothing had exercised until a brief
happened to say the word, and then it took the same brief out twice (152 and
159). It now reads `finish_reason` alone. The OpenAI `refusal` field and
`finish_reason: content_filter` still fire, still non-retryable.

## 4. What is left, and it is a different kind of defect

Both shipped apps carry **industry-pack copy verbatim, and one of them has the
wrong pack**:

    160  Ridgeline Bike Works (bike workshop)
         "The rack is live" · "Shop the new drop before sizes thin out."
         · "Restock alerts"
         → packs/fashion-retail-storefront.json, lines 60-64, unedited

    158  Kestrel & Fern Bakehouse (bakery doing pre-orders)
         "Hungry tonight?" · "Hold a table — or join the walk-in list with a
         real wait time."
         → packs/restaurant-cafe-home.json, line 60, unedited

The bakery's pack is roughly right and its copy is not ("hold a table" is not
what that business sells). The bike shop's is neither. Nothing here is a dead
link or a contract violation, so no gate sees it — it is the *demo does not match
the business* problem, in the one place nobody was looking: the pack ships
literal sentences, not a shape to fill.

Two decisions are needed and neither is a bug fix:

- **Should a pack carry copy at all**, or only structure and slot choices, with
  every sentence written for the business?
- **How is the pack chosen?** A bike workshop landing on fashion-retail suggests
  the selector is matching on "retail" and losing "workshop"/"service".

Left alone deliberately. It needs a ruling, not a patch, and patching it blind
would bury the finding.

## 5. One thing the trio disproved

Request 161 declares **two** `public-catalog` routes — `/catalogue` and `/hire` —
which is a coherent thing for a hardware store with a separate tool-hire counter
to want. The kickoff's premise, and the docstring on `booking_route`, said "at
most one `public-catalog`", verified across 146-151. It is not a rule.

Nothing broke: `catalog_route` returns the first declared match, every consumer
needs *a* browse face rather than *the* browse face, and 161 shipped `ready` with
zero dead links. The premise is now split in the test that asserted it — one
booking face per app still holds across the corpus and is still checked; the
catalogue half is recorded as contradicted, with a test pinning that two faces
resolve deterministically, so nobody re-derives a uniqueness guarantee the corpus
has already broken.

## 6. Budget

    session start   381.560541831
    first trio      382.460838476   (+$0.900297, 6 launches, 3 completed)
    second trio     383.176949250   (+$0.716111, 4 launches, 3 completed)

**Session total $1.616407 across 10 launches. $1.823 left.**
Six of the ten launches produced a finished app; the four that did not are the
three upstream failures fixes B and F were written from, plus 154's AppSpec death.

## Process notes

- **`docker restart bmv-api` and then *prove* the fix is loaded.** Import the new
  symbols out of the running process and assert their behaviour, not their
  existence — `_looks_like_refusal('stop')` returning False is the check that
  matters, not that the function imports.
- **`app.domain.appspec` ↔ `app.application.appspec` is a real import cycle and
  it predates this session** — verified against `72b6566`, where importing
  `sanitize.heal` first fails identically. Production enters through the
  application package, so it never fires there; a test or a script that imports
  the domain module first must do the same. Left alone: fixing it means moving
  `canonical_json` out of the application layer.
- **`requests.status` is still not the run verdict** (see `trio-152-157.md`). The
  poll loop here waits on `generated_pages -> preview_app -> status` being
  non-null *or* `status='failed'`, which covers both endings.
