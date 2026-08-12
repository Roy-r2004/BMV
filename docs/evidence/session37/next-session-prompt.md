# Kickoff — make the demo obey the customer

*Supersedes session 36's next-session prompt: the confirmation batch ran
(session 37 results) and the cost program is closed. Do not reopen cost
knobs this session.*

**The goal is fidelity to the customer's request.** Request 107 ("Jeanne
Art") asked to showcase paintings with a four-item header — home, gallery,
about, contact — and received an operations dashboard whose navigation
carried a fifth item our own template invented. Two distinct failures, both
with receipts in the session-37 record: explicit customer constraints lose
to template defaults, and requests outside the dashboard vocabulary get
coerced into it silently. This session fixes the first completely, and
makes an owner-decided start on the second.

**Budget: $6. Stop and report at $5, whatever state you're in.** Bracket
every funded run via `/api/requests/<id>/admin` and put the `/studio/<id>`
link next to every number.

Read first, in this order:

1. `docs/evidence/session37/results.md` — where the config landed and why
   the cost program closed
2. The request-107 analysis: intake text, spec navigation, and the
   template rule that padded it (`app/prompts/ui_spec.j2`, RULES block,
   "5-7 short one-word items")
3. `app/archetypes.py` — the catalog; all five shapes are back-office
   dashboards
4. Memory: "Demo matches the business" (owner's rule, session 15, amended
   with the Jeanne instance)

## Step 1 — explicit constraints win (~$0.70)

When the intake names navigation items, the list is honored verbatim:

- Extract an explicit nav list from the brief deterministically where
  possible, and constrain ui_spec to copy it exactly. Soften the template's
  "5-7 items" to a DEFAULT range that yields to an explicit customer list —
  do not delete the default; sparse navs looked empty in early sessions.
- An honored list must flow into the text-truth expected strings —
  navigation labels are gate-checked material, so an ignored item becomes a
  measured failure, not a vibe.
- Pin with request 107's exact intake sentence as a unit fixture ("I wanna
  showcase my paitings, with a dashboard that contains home, gallery,
  about, contact" — typos and all; real intakes look like this).
- One funded run to see it live, same brief text, before calling it fixed.

## Step 2 — the demo vocabulary (~$3.50, owner decides before building)

Per request class, not a blanket rebuild:

- **"Investment system"** — already lands on `analytics-dashboard` and the
  hedgefund cells (92, 96) show the result is credible. Add an
  intake-classification test pinning it; build nothing.
- **"Chatbot / AI assistant demo"** — no shape exists. If the owner wants
  it: ONE new archetype (conversation anchor; follow-ups from the existing
  vocabulary — conversation analytics, a knowledge/settings screen), one
  golden brief, its own text-truth fields. Two funded pilot runs, looked at
  with eyes before any rollout.
- **"Portfolio / showcase website"** (the Jeanne class) — decide between a
  public-site archetype (a real product bet) and honest out-of-scope
  framing: one paragraph on the result page saying what IS being proposed
  ("back-office software for managing inquiries and sales around your
  work"). The framing is cheap, ships this session, and kills the "I
  didn't get the goal of this" confusion even if the archetype comes later.

## Traps, all of them already paid for

- **The judge is held fixed while generators vary.** A new archetype
  changes what must be judged. Stage it: land against the existing
  instruments where they apply; any rubric extension is its OWN step with
  a golden-set run (the gate-relaxations rule).
- **Any classifier touch** is measured against the synthetic-briefs 20/20
  pin and the stored kind_contexts before landing.
- **Prompt bans have blast radius; scaffolding renders as UI.** New
  archetype prompts inherit every recorded prompt lesson — name the string
  or say nothing.
- **The cost program is closed.** New shapes ship at the same three-screen,
  same-model, same-size economics ($0.390 nominal, ~$0.63 realised). A
  fourth screen or a model change is an owner decision with a price tag,
  not a default.
- **The chart tail is still the open quality lever** (ticks proposal and
  JOB 6, specced in session-36 results). Fund only if defect-carrying
  screens bother the demos commercially — not to chase a cheaper mean.
- Do not run two bakeoff batches concurrently; never mix labels across
  pipeline modes; read spend via the admin endpoint.

## What I want back

For each of the three request classes: the intake text submitted, the
archetype chosen, the screens produced with their `/studio/<id>` links, and
a one-line answer to the only question that matters — would a customer
reading this result page understand what they were just shown? Plus the
usual: running spend, fixes landed with pins, anything found and not fixed
with the reason.
