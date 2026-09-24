# The consultation flow

What a client meets at `/demo`, from the first question to the package, and what
each screen is built from. The screens follow the approved mockups (v4, all
blue). The rule under every screen: **a figure shown is one the owner gave,
arithmetic on theirs with the working kept, or a number we propose and label
as ours.**

## The five steps

| Step | Screen | Built from | Code |
|---|---|---|---|
| 1 | **One question**: "What are you trying to work out?" | Their words | `components/consult/FrontDoor.tsx` |
| 2 | **The conversation**: one question at a time, with a live case file | `/api/discovery/interview` (questions), `/api/discovery/casefile` (figures + their week) | `Interview.tsx` |
| 2 | **Here's what we heard**: editable figures, their own idea shown as one to test | `/api/discovery/casefile` with `playback=true` | `Playback.tsx` |
| 3 | **Watching it think**: explanations circled or struck out, reviewers in the margin | the narrated trail (`thinking` on `/progress`) | `Thinking.tsx` |
| 4 | **The honest answer**: the finding in two lines, their week drawn, the value of the move | `answer`, `capacity` on `/decision` | `Answer.tsx`, `WeekGrid.tsx` |
| 5 | **Building** (only if they choose it) | `/progress` | `Building.tsx` |
| 5 | **The package**: Monday first, documents, screens, pilot tracker, the honest box | `/preview`, `/plan` | `Package.tsx`, `Tracker.tsx` |

A client who takes the answer without the build gets the **plan-only package**
(same page, no build documents, "Build the system too" one click away). A
partner opens a read-only copy at `/shared/<token>` (`routes/SharedPage.tsx`).

## New pipeline stages (consultant-service)

All fail open: a stage that cannot produce a verified result stores nothing,
and the screen falls back to what it showed before.

- **`pipeline/figures.py`**: which numbers the owner gave (digits and number
  words), which clock times they named (kept apart: "the 7pm class" is not the
  number 7), and whether a sentence stays inside them.
- **`pipeline/capacity.py`**: their week. A model reads their words into a
  structure (`weekly_grid` or `total`); every number is checked against what
  they said, every time against a time they named, every day name against
  one they used. Totals are computed in code with the working kept. Nothing is
  filled in: a slot whose fill they never gave is drawn hollow, and an unnamed
  column has no time. Runs before the diagnosis, and its totals become
  `CAP-xx` claims that a hypothesis can cite.
- **`pipeline/answer.py`**: the answer screen's parts. The headline, the
  evidence and the figures are checked against their figures. The value of
  the move is a product of terms: each term is a cited figure, a calendar
  constant, or a number we propose, and it is multiplied here, never by the
  model. A move resting only on proposals is refused. Runs after `decide`.
- **`pipeline/action_plan.py`**: what they do on Monday: first steps, the
  schedule, the message to send, the measures with baselines (only ever one
  of their figures by id, or "measure it in week 1"), and the decision rule.
  Written when they take the answer (background thread, polled), and at the
  start of every build.
- **`pipeline/export_pilot.py`**: the plan as a PDF in the volumes' style,
  ending with a blank tracking sheet. Included first in the ZIP.
- **`pipeline/evidence.py`**: files dropped into the conversation are stashed
  (outside the public uploads folder) and read **before** the diagnosis forms
  an explanation.

## New API

| Route | Who | What |
|---|---|---|
| `POST /api/discovery/casefile` | signed in | figures from their answers + their week; `playback=true` adds the summary, their words and their own idea |
| `POST /api/requests` | signed in | now also takes `files` (up to 3, 8 MB each) |
| `GET /api/requests/{ref}/decision` | viewer | now carries `capacity`, `answer`, `action_plan` |
| `POST /api/requests/{ref}/decision/accept` | owner | also starts writing the plan (`plan_started`) |
| `GET /api/requests/{ref}/plan` | viewer | plan, tracker log, capacity |
| `POST /api/requests/{ref}/plan/log` | owner | one week of the pilot against the plan's own measures (upsert) |
| `POST /api/requests/{ref}/plan/retry` | owner | rewrite a plan that failed |
| `POST/DELETE /api/requests/{ref}/share` | owner | make or revoke the partner link |
| `GET /api/shared/{token}` and `/export/{kind}` | anyone with the link | the package, read-only |
| `GET /api/requests/{ref}/export/pdf/pilot` | viewer | the plan PDF (not held by the review gate) |

`/progress` also returns `notify` (the email address and whether mail can be
sent, so the building screen only promises an email it can send), and its
`elapsed_s` now counts from `phase_started_at`, so the build clock counts the
build rather than the time since the first question. When a build finishes and
is not held for review, the owner is emailed (`mailer.notify_owner_ready`).

New columns (added automatically by `_ensure_columns`): `capacity_json`,
`answer_json`, `action_plan_json`, `pilot_log_json`, `share_token`,
`phase_started_at`.

## Tests

`tests/test_consultation_flow.py` pins each checker with the honest reading
and the dishonest one it exists to catch. Examples: an invented timetable is
dropped, a capacity number she never gave kills the picture, a misquoted term
kills the move, an invented baseline becomes "measure in week 1", and a
partner link reads but cannot write and can be turned off.

## Known limits

- The hypothesis tester still returns "couldn't check" more often than it
  should when the owner's figures are thin. The interview now asks for fill
  and price explicitly, which is the real fix. Watch it on live runs.
- The case file is read after every answer (two fast model calls). Cheap, but
  not free.
- Page counts on the document list are not shown; they are only known once a
  PDF has been rendered.
