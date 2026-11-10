# GCC Outreach Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A daily, best-first list of GCC businesses, each with a private report page and an English Instagram DM that Roy copies and sends by hand.

**Architecture:** A new `app/outreach/` package in `consultant-service`, which already has the web-search model (`settings.RESEARCH_MODEL`), the guarded fetcher (`app/figures/references._fetch`) and the cost ledger (`app/pipeline/_shared.ledger`). The stages are find → read → score → write → queue, and code checks every model output before it is kept. A reviewer-token admin API feeds a new `/admin/outreach` page in the frontend. A public API feeds the report page at `/for/:token`.

**Tech Stack:** FastAPI, SQLAlchemy (SQLite), OpenRouter models, pytest; React 19 + Vite + TypeScript.

**Spec:** `docs/superpowers/specs/2026-11-10-gcc-outreach-design.md`

## Global Constraints

- Nothing is ever sent from the pipeline. Roy sends every DM by hand.
- Instagram is never fetched, logged into or automated. A handle comes only from the business's website or from a URL the web search cites.
- Facts only. Every statement about a business is traceable to a fetched page or a cited search URL. Every number in a report or DM must appear in the text that was read. Never write BMV clients, results, team members or "we helped" claims.
- English only.
- Daily count: `OUTREACH_DAILY` defaults to 30. Monthly spend cap: `OUTREACH_MONTHLY_USD` defaults to 100.0. A call whose `cost_usd` is null counts as `OUTREACH_UNPRICED_CALL_USD`, default 0.02.
- Start with city "Dubai" and kinds "clinic", "salon", "gym", "restaurant", "real estate agent". Then Riyadh, Doha, Abu Dhabi, Kuwait City, Manama and Muscat. These are settings (`OUTREACH_CITIES`, `OUTREACH_KINDS`, comma-separated), not code.
- The "book a call" button opens `mailto:consulting@buildmyversion.com?subject=Call about <business name>`. The "remove this page" link opens `mailto:consulting@buildmyversion.com?subject=Remove the page for <business name>`.
- The report page is never listed anywhere. Its token is 22+ characters from `secrets.token_urlsafe(16)`. It sends `X-Robots-Tag: noindex, nofollow` and carries `<meta name="robots" content="noindex,nofollow">`. `robots.txt` disallows `/for/`.
- Opens are stored as times only, never an IP or device. A request whose User-Agent matches `facebookexternalhit|Instagram|WhatsApp|bot|crawler|spider|preview` is not counted.
- A business marked `not_interested` or `skip` keeps only its name, city and status after 90 days. Everything else about it is deleted.
- Admin endpoints require the reviewer token (`settings.REVIEW_TOKEN`, compared with `hmac.compare_digest`), sent as the `X-Review-Token` header. With no token configured, they refuse.
- Commit messages say why and end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. `app/outreach/` and `tests/outreach/` are not frozen files; `app/prompts/**` is, so a new prompt needs the r30 re-freeze (see the repo's CLAUDE.md and the steps used before: `tests/engine/refreeze_r30.py --commit <sha>` and the two `manifest["commit"]` constants).

## Review Focus

1. A web search that names the same business twice, or one already on file, under a slightly different name or URL: one row, never two (Task 2, `test_the_same_business_is_found_once`).
2. A website that is down, blocked, huge or redirects inside the network: the business is still scored as "no working website", never crashes the run (Task 3, `test_a_site_that_cannot_be_read_scores_as_no_website`).
3. A model report that slips in a number, a percentage or a "we helped" line that was not read: the report is rejected and rewritten once, then the business is dropped (Task 5, `test_a_report_with_an_unread_number_is_refused`).
4. Reaching the $100 cap in the middle of a run: the run stops before the next paid call and the list says why (Task 6, `test_the_run_stops_at_the_cap`).
5. Instagram's link preview opening the report when Roy pastes the link: not counted as an open (Task 7, `test_a_preview_bot_is_not_an_open`).

---

### Task 1: The prospect record and its settings

**Files:**
- Modify: `consultant-service/app/models.py` (add `Prospect`, `OutreachRun`)
- Modify: `consultant-service/app/config.py` (add the `OUTREACH_*` settings above)
- Create: `consultant-service/app/outreach/__init__.py` (empty docstring module)
- Test: `consultant-service/tests/outreach/test_record.py`

**Interfaces:**
- Produces: `Prospect` (table `outreach_prospects`) with columns: `id`, `token` (unique), `name`, `city`, `kind`, `website` (nullable), `instagram` (handle without @, nullable), `phone` (nullable), `key` (unique dedup key, see Task 2), `sources_json` (list of `{"url","what"}`), `site_text` (nullable Text, the fetched website text, capped at 20,000 chars), `signals_json`, `score` (int), `reasons_json` (list[str]), `report_json` (nullable), `dm_text` (nullable), `status` (`found|ready|queued|sent|replied|call_booked|not_interested|skip|removed`, default `found`), `queued_on` (Date, nullable), `sent_at`, `opened_first_at`, `opens` (int, default 0), `created_at`, `updated_at`.
- Produces: `OutreachRun` (table `outreach_runs`) with `id`, `day` (Date, unique), `started_at`, `finished_at`, `found`, `queued`, `stopped_because` (nullable str).
- Produces: `new_token() -> str` in `app/outreach/__init__.py`, returning `secrets.token_urlsafe(16)`.

- [ ] **Step 1: Write the failing tests.** `test_a_prospect_is_stored_with_an_unguessable_token`: create a `Prospect` with `token=new_token()` and assert `len(token) >= 22` and that two tokens differ. `test_one_run_per_day`: add two `OutreachRun(day=date(2026,11,11))` and assert the second commit raises `IntegrityError`. `test_the_settings_have_the_agreed_defaults`: `OUTREACH_DAILY == 30`, `OUTREACH_MONTHLY_USD == 100.0`, `OUTREACH_UNPRICED_CALL_USD == 0.02`, `OUTREACH_CITIES[0] == "Dubai"`, `"salon" in OUTREACH_KINDS`.
- [ ] **Step 2:** Run `./.venv/Scripts/python.exe -m pytest tests/outreach/test_record.py -q -p no:cacheprovider --basetemp=D:/bmv-pytest-tmp` and expect it to FAIL.
- [ ] **Step 3:** Add the models, settings (cities and kinds parsed from comma-separated env strings into lists) and `new_token`. `_ensure_columns`/`create_all` in `app/database.py` already creates new tables at startup.
- [ ] **Step 4:** Run again and expect it to PASS.
- [ ] **Step 5:** Commit: "feat(outreach): a prospect record that keeps its sources".

### Task 2: Find businesses with the web-search model

**Files:**
- Create: `consultant-service/app/outreach/find.py`
- Create: `consultant-service/app/prompts/outreach_find.j2`
- Test: `consultant-service/tests/outreach/test_find.py`

**Interfaces:**
- Consumes: `Prospect`, `new_token` (Task 1); `provider.chat`, `ask_until_usable`, `ledger`, `reply_json` from `app/pipeline/_shared`; `render` from `app/templating`.
- Produces: `dedup_key(name: str, city: str, website: str | None, instagram: str | None) -> str`, which is `"ig:" + handle` when there is a handle, else `"web:" + registered domain` when there is a website, else `"name:" + lowercased alphanumerics of name + "|" + city.lower()`.
- Produces: `parse_found(body: dict) -> list[dict]`, which keeps only items whose `source` URL is in the reply's `url_citation` annotations (the same rule as `references.confirm`) and drops items without a name. Each item is `{"name","website","instagram","phone","source","what"}`. An Instagram value is kept only if it is a handle `^[A-Za-z0-9._]{1,30}$` (strip a leading @ and any `instagram.com/` prefix).
- Produces: `find(db, city: str, kind: str, want: int) -> list[Prospect]`, which saves new `Prospect` rows with status `found` (skipping any whose `dedup_key` exists) and returns them. Ledger purpose: `"outreach:find"`, request_id `None`.

- [ ] **Step 1: Write the failing tests.**
  - `test_only_cited_sources_are_kept`: a body with two items, one whose source is not in the annotations, so `parse_found` keeps one.
  - `test_an_instagram_url_becomes_a_handle`: `"https://www.instagram.com/glow.dxb/"` becomes `"glow.dxb"`, and `"not a handle!"` becomes `None`.
  - `test_the_same_business_is_found_once`: `dedup_key("Glow Salon", "Dubai", "https://www.glowsalon.ae/book", None) == dedup_key("Glow Salon LLC", "Dubai", "http://glowsalon.ae", None)`. Then `find` with a monkeypatched `provider.chat` returning the same business twice plus one already in the DB saves exactly one new row.
  - `test_a_failed_search_finds_nothing_and_does_not_raise`: `provider.chat` raises, so `find(...) == []`.
- [ ] **Step 2:** Run and expect FAIL.
- [ ] **Step 3:** Implement. The prompt asks the research model for up to `want` real businesses of `kind` in `city`, preferring ones that take bookings by DM, phone or WhatsApp. For each it asks for name, website, Instagram handle if shown on a page it cites, phone, the page it found it on, and a few words on what they do. It asks for JSON only, and it says plainly that a business it cannot point to on a page is left out.
- [ ] **Step 4:** Run and expect PASS.
- [ ] **Step 5:** Commit: "feat(outreach): find businesses a web search can point to".

### Task 3: Read each website and score what it shows

**Files:**
- Create: `consultant-service/app/outreach/read.py`
- Test: `consultant-service/tests/outreach/test_read.py`

**Interfaces:**
- Consumes: `app.figures.references._fetch` (guarded fetch, raises `references.Unreadable`).
- Produces: `signals(text: str | None) -> dict` with boolean keys `has_site`, `books_online` (a link or text naming Fresha, Booksy, Calendly, Setmore, SimplyBook, Vagaro, Mindbody, OpenTable, SevenRooms, Quandoo, Eat App, Practo, Okadoc, or "book online"/"book now" next to a form or link), `books_by_message` ("DM", "direct message", "WhatsApp", "wa.me", "call to book", "call us to book"), `shows_whatsapp`, and `instagram` (first handle from an `instagram.com/<handle>` link, or None).
- Produces: `score(sig: dict) -> tuple[int, list[str]]`. Points: no working website +40 ("No working website was found"); site but no online booking +30 ("No way to book online on the website"); bookings by message +30 ("Bookings are taken by message or phone"); WhatsApp only +10. Each reason is shown to Roy word for word. A business with `books_online` and `has_site` scores 0.
- Produces: `read(db, p: Prospect) -> Prospect`, which fetches `p.website` (if any), stores `site_text` (≤20,000 chars), `signals_json`, `score`, `reasons_json`, fills `p.instagram` from the site when it was empty, and sets status `ready` when `score >= settings.OUTREACH_MIN_SCORE` (default 30), else `skip`.

- [ ] **Step 1: Write the failing tests.**
  - `test_a_booking_platform_link_counts_as_online_booking`: `"<a href='https://www.fresha.com/a/glow'>Book</a>"` gives `books_online is True`.
  - `test_dm_to_book_is_booking_by_message`: `"DM us to book your slot"` gives `books_by_message is True`.
  - `test_a_site_that_cannot_be_read_scores_as_no_website`: monkeypatch `_fetch` to raise `Unreadable`, so `read` gives `score == 40` (plus message points only if the search's `what` said so; here it is 40) and status `ready`.
  - `test_a_business_that_already_books_online_is_skipped`: `score({"has_site": True, "books_online": True, ...}) == (0, [])` and `read` sets status `skip`.
  - `test_the_handle_comes_from_the_site`: page with `instagram.com/glow.dxb`, so `p.instagram == "glow.dxb"`.
- [ ] **Step 2:** Run and expect FAIL. **Step 3:** Implement. **Step 4:** Run and expect PASS.
- [ ] **Step 5:** Commit: "feat(outreach): score a business only on what its own site shows".

### Task 4: Spending stays under the cap

**Files:**
- Create: `consultant-service/app/outreach/budget.py`
- Test: `consultant-service/tests/outreach/test_budget.py`

**Interfaces:**
- Consumes: `AiUsageEvent` (`purpose`, `cost_usd`, `created_at`).
- Produces: `spent_this_month(db, now: datetime | None = None) -> float`, which sums `cost_usd` (or `OUTREACH_UNPRICED_CALL_USD` when null) of events whose `purpose` starts with `"outreach:"` in the current UTC calendar month.
- Produces: `can_spend(db, now=None) -> bool`, true when `spent_this_month < OUTREACH_MONTHLY_USD`.

- [ ] **Step 1: Write the failing tests.** `test_unpriced_calls_count_at_the_fallback` (three null-cost outreach events give 0.06). `test_other_purposes_and_last_month_do_not_count`. `test_spending_stops_at_the_cap` (one event with cost 100.0 gives `can_spend is False`).
- [ ] **Step 2:** Run and expect FAIL. **Step 3:** Implement. **Step 4:** Run and expect PASS. **Step 5:** Commit: "feat(outreach): a hundred dollars a month, counted from the ledger".

### Task 5: Write the report and the DM, and refuse anything not read

**Files:**
- Create: `consultant-service/app/outreach/write.py`
- Create: `consultant-service/app/prompts/outreach_report.j2`
- Test: `consultant-service/tests/outreach/test_write.py`

**Interfaces:**
- Consumes: `Prospect` with `site_text`, `sources_json`, `signals_json`, `reasons_json`.
- Produces: `problems(report: dict, dm: str, read_text: str) -> list[str]`, the reasons a draft is refused:
  - a number (digits, or one of the words one to twelve followed by a noun of time, money or people) not present in `read_text`;
  - any of `we helped`, `our clients`, `clients like you`, `case study`, `guarantee`, `increase your revenue by`, `%` (unless the same percentage is in `read_text`);
  - a DM over 600 characters, or one without the placeholder `{link}`;
  - a report missing any of the keys `today`, `changes` (2–3 items of `{"change","ai","day_to_day","difference"}`) or `sources_note`.
- Produces: `write(db, p: Prospect) -> Prospect`, which calls `settings.ANALYSIS_MODEL` (ledger purpose `"outreach:write"`). If `problems(...)` is not empty, it asks once more with those problems listed. If problems remain, it sets status `skip` and appends "The draft could not be written from what was read" to `reasons_json`. On success it stores `report_json`, `dm_text` with `{link}` intact, and status stays `ready`.
- The prompt gives the model only: business name, city, kind, `what` from the search, the website text (first 6,000 chars), and the reasons. It asks for English, plain words, no numbers it was not given, no claims about BMV's past work, and a DM of 2–4 short lines that names one specific thing from what was read and ends with `{link}`.

- [ ] **Step 1: Write the failing tests.**
  - `test_a_report_with_an_unread_number_is_refused`: report text "you lose 40 bookings a week" with read_text lacking "40", so `problems` is non-empty.
  - `test_a_claim_about_past_clients_is_refused`: dm "We helped 3 salons in Dubai".
  - `test_a_clean_draft_passes`: a report whose only number "4.8" is in read_text, and a DM ending `{link}`, gives `[]`.
  - `test_a_draft_still_wrong_after_the_second_try_skips_the_business`: monkeypatched `provider.chat` returning a bad draft twice gives status `skip`.
  - `test_the_model_sees_no_more_than_was_read`: capture the prompt and assert it contains the site text and not the business's phone number.
- [ ] **Step 2:** Run and expect FAIL. **Step 3:** Implement. **Step 4:** Run and expect PASS.
- [ ] **Step 5:** Commit, then re-freeze r30 (new prompt files) as described in Global Constraints, committing the manifest and both constants together: "feat(outreach): a report that says only what was read".

### Task 6: One run fills today's list

**Files:**
- Create: `consultant-service/app/outreach/run.py`
- Modify: `consultant-service/main.py` (start the daily thread in `on_startup` when `OUTREACH_AUTO == "on"`, default `"off"`)
- Test: `consultant-service/tests/outreach/test_run.py`

**Interfaces:**
- Consumes: `find`, `read`, `write`, `can_spend` (Tasks 2–5).
- Produces: `fill(db, day: date, want: int | None = None) -> OutreachRun`. It creates the day's `OutreachRun` (returning the existing one unchanged if the day already ran, so a second worker or a double click does nothing). It first queues any existing `ready` rows that have a `dm_text`, best score first. Then it walks `OUTREACH_CITIES × OUTREACH_KINDS` in order, calling `find` → `read` → `write` until `want` (default `OUTREACH_DAILY`) rows are queued, and checks `can_spend` before every paid call. Queued rows get status `queued` and `queued_on = day`. If the cap stops it, it sets `stopped_because = "The monthly budget of $100 is used up"`. If the cities and kinds run out, it sets `"No more businesses found today"`.
- Produces: `purge(db, now=None) -> int`. For rows in `not_interested`/`skip` whose `updated_at` is older than 90 days, it clears every column except `id`, `token`, `name`, `city`, `key`, `status`, and returns the count.
- The daily thread sleeps until 06:00 Asia/Dubai, calls `fill` then `purge` in a fresh session, and logs exceptions without dying.

- [ ] **Step 1: Write the failing tests.**
  - `test_a_run_queues_the_best_first_up_to_the_daily_number`: stub find/read/write to make 40 ready prospects with varied scores, `want=30`, so 30 are queued in score order.
  - `test_the_same_day_twice_does_nothing`.
  - `test_the_run_stops_at_the_cap`: `can_spend` returns False after the second call, so the run stops, `stopped_because` names the budget, and no further `provider.chat` is called.
  - `test_nothing_older_than_90_days_is_kept_about_a_skipped_business`.
- [ ] **Step 2:** Run and expect FAIL. **Step 3:** Implement. **Step 4:** Run and expect PASS. **Step 5:** Commit: "feat(outreach): one run a day fills the list, best first, under the cap".

### Task 7: The API, admin and public

**Files:**
- Create: `consultant-service/app/routers/outreach.py`
- Modify: `consultant-service/main.py` (`app.include_router(outreach_router.router)`)
- Test: `consultant-service/tests/outreach/test_api.py`

**Interfaces:**
- Admin (header `X-Review-Token`, 403 without the right one):
  - `GET /api/outreach/today?day=YYYY-MM-DD` returns `{"day", "rows": [{"id","name","city","kind","instagram","instagram_url","website","reasons","dm","report_url","status","opens","opened_first_at"}], "spent", "cap", "stopped_because"}`. `dm` has `{link}` replaced by `report_url`, and `report_url` is `settings.PUBLIC_SITE_URL + "/for/" + token`. Use the existing public-site setting if one exists; otherwise add `PUBLIC_SITE_URL`, default `"https://buildmyversion.com"`.
  - `POST /api/outreach/fill` starts `fill` for today in a background thread and returns 202.
  - `PATCH /api/outreach/{id}` with `{"status": ...}` (only `sent|replied|call_booked|not_interested|skip|removed`). `sent` sets `sent_at`.
- Public:
  - `GET /api/outreach/report/{token}` returns `{"name","city","today","changes","sources","sources_note","book_subject","remove_subject"}` with `X-Robots-Tag: noindex, nofollow`. It returns 404 when the token is unknown or the status is `removed` or purged. It counts an open (`opens += 1`, `opened_first_at` if empty) unless the User-Agent matches the bot pattern in Global Constraints.

- [ ] **Step 1: Write the failing tests.** `test_admin_needs_the_token`. `test_today_lists_the_queue_with_the_link_in_the_message`. `test_marking_sent_records_the_time`. `test_an_unknown_status_is_refused`. `test_the_report_is_not_indexed` (header present). `test_a_preview_bot_is_not_an_open` (UA `facebookexternalhit/1.1` leaves `opens == 0`; a Chrome UA gives 1). `test_a_removed_page_is_gone`.
- [ ] **Step 2:** Run and expect FAIL. **Step 3:** Implement. **Step 4:** Run and expect PASS. **Step 5:** Commit: "feat(outreach): Roy's list and the private report, over the API".

### Task 8: The report page and Roy's list in the frontend

**Files:**
- Create: `frontend/src/api/outreach.ts`
- Create: `frontend/src/routes/OutreachReportPage.tsx` (route `/for/:token`)
- Create: `frontend/src/routes/AdminOutreachPage.tsx` (route `/admin/outreach`, linked in `AdminLayout`'s rail as "Outreach")
- Modify: `frontend/src/App.tsx`, `frontend/src/components/AdminLayout.tsx`, `frontend/public/robots.txt` (create if absent: `User-agent: *` / `Disallow: /for/`)

**Interfaces:**
- Consumes: the Task 7 endpoints through the consultant API base (`VITE_CONSULTANT_API_BASE_URL`, as `api/consultant.ts` does).
- The report page uses the white film look of the consultation screens (the `cx-*` classes in `styles/consult.css`). It sets `<meta name="robots" content="noindex,nofollow">` while mounted. It shows, in order: the business name, "What we saw", the 2–3 changes (each with the AI that does it, what it does day to day, and what changes for them), a "Book a call" button (`mailto:` with the subject from the API), "This page was made from public information: <sources>", and a quiet "Remove this page" mailto link. It has no site navigation or chat widget, and no prices.
- The admin page asks once for the reviewer token and keeps it in `sessionStorage` under `bmv_review_token`. It shows spent / cap and `stopped_because`, a "Fill today's list" button, and one row per business: name, city, reasons, the DM with a "Copy" button, "Open Instagram" (`https://instagram.com/<handle>` in a new tab, or "Find the handle" with the website or a Google search link when there is no handle), "Open report", and buttons for each status.

- [ ] **Step 1:** Build both pages and wire the routes.
- [ ] **Step 2:** Run `npx tsc -b --noEmit` (expect 0 errors), `npx oxlint` (expect 0 errors), `npx vite build` (expect success).
- [ ] **Step 3:** Serve a test database with a seeded queued prospect (the scratchpad `serve_run.py` pattern) and open `/admin/outreach` and `/for/<token>` with Playwright at 1440 and 390 wide. Expect no horizontal overflow, no console errors, the copy button copying the DM with the real link, and the robots meta present.
- [ ] **Step 4:** Commit: "feat(outreach): the report a business opens and the list Roy works from".

### Task 9: A real run, then ship

- [ ] **Step 1:** Run the full consultant suite. Expect exactly the four known failures listed in the earlier work (mutation-manifest ×3, universality ×1).
- [ ] **Step 2:** With the real models, on an isolated database, run `fill` for Dubai with `want=5`. Read all five reports and DMs against their sources. Every claim must trace to a cited URL or the site text, there must be no unread number, and each DM must name something specific. Record the spend.
- [ ] **Step 3:** Push to `main` (Coolify deploys). Tell Roy to set `REVIEW_TOKEN` if it isn't set, and `OUTREACH_AUTO=on` when he wants the 06:00 run.
