"""The screens stage: the system drawn for this business, screen by screen.

Two kinds of model call. The plan call designs the product once: name,
navigation, one cast of sample people and records every screen shares, the
screen list with a brief for each, and the proposal's narrative pages. Then
one call per screen draws it from that brief, in parallel, in the block
vocabulary of `schema`. Everything is shaped and bounded on the way in; a
screen the renderer cannot draw is retried once with the exact reasons, then
dropped rather than shown broken.

No fallback: when the call that plans the system fails, or the call that
draws any screen of it, or fewer than `schema.SCREENS_MIN` screens come out
drawable, the stage stops the run (`StageFailed`) and saves nothing. Only the
polish stays soft: a redraw that fails in the fit pass keeps
the screen as it was drawn, and a frame that cannot be measured is left alone.

Numbers: the screens carry sample data and say so on every frame, but any
figure the client gave that a screen shows is theirs. Captions and the story
are statements about the business, so they are bound like the answer's prose
against what the request knows (`app.figures.known`), with no leniency: a
number that names no figure removes its sentence, or the story item it is in.
The block values (tiles, rows, sample records) are the sample region and are
not bound here.

The result is `screens_json` on the request, PNG thumbnails when a browser
is available, and one image row per screen so the older parts of the site
that list screens keep working.
"""

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.figures import known as _known
from app.figures.bind import bind, clean_sentences
from app.figures.model import FigureSet
from app.models import GeneratedImage, Request
from app.pipeline import answer as _answer
from app.pipeline._shared import ask_until_usable, ledger, log_usage, reply_json
from app.pipeline.failure import StageFailed
from app.screens import browser, render, schema
from app.templating import render as render_prompt

logger = logging.getLogger("consultant.screens")

PLAN_TOKENS = 7000
SCREEN_TOKENS = 3000
WORKERS = 4
PROMPT_VERSION = "screens-v1"

BLOCK_GUIDE = """Each block is {"kind": ..., "w": 1-3 (share of the row), ...fields}. Kinds and their fields:
- kpis: items[2-6] of {value (short, "22/29", "$18,400", "26 min"), label, sub?}. A row of tiles; usually the first row.
- list: title, rows[≤7] of {tag (≤2 words), tone (good|warn|bad|info|dim), text (one sentence), action? ("Open")}, footer?. A needs-attention list.
- agenda: title, rows[≤7] of {time ("09:00"), title, sub?, now? (true for the current one)}. Today's programme.
- table: title?, sub?, columns[≤6], rows[≤8] of cells; a cell is text, or {"chip": "Overdue", "tone": "bad"}, or {"action": "Send reminder"}, or {"strong": "$1,200"}; footer?.
- pipeline: title?, columns[2-5] of {title, cards[≤4] of {title, tags[≤3] (short), lines[≤3], action?, alert?}}, footer?. A kanban of stages.
- board: title?, sub?, groups[≤4] of {title, cells[≤20] of {code ("M3-A"), label? (a name or a state), state (occupied|free|reserved|preparing|closed)}}, legend[state names], side? {title, lines[≤4], actions[≤2]}. A live board of units.
- record: initials, name, meta (one line of context), action?, tabs[≤5], active_tab. A file header; first row of a record screen.
- stages: items[2-6] of {label, sub?, state (done|now|next)}. A journey or programme timeline; full width, one row.
- progress: title, items[≤5] of {label, pct (0-100), status?}, footer?.
- bars: title, sub?, items[2-8] of {label, value (number), display? ("$5.4k")}, horizontal? (true for a ranked list).
- line: title, sub?, points[3-8] of {label, value, display?}. A trend.
- form: title, sub?, fields[≤7] of {label, type (text|textarea|choice|scale|check|select), value?, help?, options[≤5]?, selected?}, note?, primary? (button), secondary?. A note, an enquiry, a check-in.
- schedule: title, sub?, days[2-7], slots[≤6] of {time, cells[one per day] of {title, sub?, tone (info|good|warn|bad|dim)} or null}, legend[tone names], footer?. A week grid.
- matrix: title, sub?, tabs[≤5] (roles), active, columns[2-4], rows[≤8] of [text per column]. Permissions by role.
- log: title, rows[≤7] of {time, who, text, blocked? (true when an access was refused)}. An activity log.
- cards: title, sub?, items[≤8] of {title, text, state (connected|connect|on|off|none), action?}. Integrations, options, or what an AI agent handles.
- note: text, tone (info|warn|good|bad|dim). One-line callout.
- feed: title, rows[≤6] of {meta ("Today 11:00, individual session, M. Khoury"), text, tag?}. Recent entries.
- draft: title, badge ("AI draft"), note (what it was written from and that a person approves it), bullets[≤4] of {text, cite? ("3 notes")}, primary, secondary. An AI suggestion awaiting approval.
- chat: title, sub?, messages[≤6] of {from (person|agent), text}, note?. A conversation an AI agent handled."""

EXAMPLE_FOR = {
    "pipeline": "waitlist", "board": "floor", "schedule": "schedule", "form": "connections",
    "chat": "frontdesk", "matrix": "permissions", "log": "permissions", "record": "client",
    "draft": "client", "line": "reports", "bars": "reports", "table": "clients", "cards": "instructors",
}


def _example_for(blocks: list[str]) -> str:
    """One example screen of the same shape, from the worked example."""
    example = render.load_example()
    by_id = {s["id"]: s for s in example["screens"]}
    pick = "today"
    for k in blocks:
        if k in EXAMPLE_FOR:
            pick = EXAMPLE_FOR[k]
            break
    s = by_id.get(pick) or example["screens"][0]
    body = {k: s[k] for k in ("heading", "subheading", "actions", "rows") if k in s}
    return json.dumps(body, ensure_ascii=False)


def _modules(req: Request) -> list[dict]:
    try:
        mods = json.loads(req.modules_json) if req.modules_json else []
    except (TypeError, ValueError):
        return []
    out = []
    for m in mods:
        if not isinstance(m, dict):
            continue
        spec = m.get("spec") if isinstance(m.get("spec"), dict) else {}
        tech = m.get("tech") if isinstance(m.get("tech"), dict) else {}
        feats = [f.get("name") if isinstance(f, dict) else str(f) for f in (spec.get("features") or [])][:8]
        ents = [e.get("entity") if isinstance(e, dict) else str(e) for e in (tech.get("data_model") or [])][:8]
        data = [str(d) for d in (spec.get("data") or [])][:6] or [e for e in ents if e]
        ai = spec.get("ai") if isinstance(spec.get("ai"), dict) else None
        out.append({
            "id": str(m.get("id") or ""),
            "name": str(m.get("client_facing_name") or m.get("name") or ""),
            "purpose": str(m.get("purpose") or "")[:240],
            "users": ", ".join(str(u) for u in (m.get("users") or []))[:80],
            "features": "; ".join(f for f in feats if f)[:400],
            "data": ", ".join(d for d in data if d)[:200],
            "ai": (f"{ai.get('role', '')}; decides alone: {ai.get('decides_alone', '')}; hands off: {ai.get('hands_off', '')}"[:240]
                   if ai else ""),
            "integrations": ", ".join(str(i) for i in (spec.get("integrations") or []))[:120],
        })
    return [m for m in out if m["id"] and m["name"]]


def _roles(req: Request) -> str:
    try:
        org = json.loads(req.org_json) if req.org_json else {}
    except (TypeError, ValueError):
        return ""
    lines = []
    for r in (org.get("roles") or [])[:10]:
        if isinstance(r, dict) and r.get("role"):
            lines.append(f"- {r['role']} ({r.get('type') or 'human'})")
    return "\n".join(lines)


def _journey(req: Request) -> list[str]:
    try:
        j = json.loads(req.journey_json) if req.journey_json else {}
    except (TypeError, ValueError):
        return []
    return [str(s.get("stage")) for s in (j.get("stages") or []) if isinstance(s, dict) and s.get("stage")]


def _inputs(req: Request) -> dict:
    """Everything the two prompts read, and the figure set the checks use."""
    from app.pipeline import diagnose

    decision = json.loads(req.consulting_recommendations_json) if req.consulting_recommendations_json else {}
    ans = _answer.load(req) or {}
    _, claims = diagnose._evidence_lines(req)
    brief = {}
    try:
        brief = json.loads(req.brief_json) if req.brief_json else {}
    except (TypeError, ValueError):
        pass
    answer_line = " ".join(x for x in (ans.get("headline"), ans.get("turn"), ans.get("sub")) if x).strip() \
        or (decision.get("consulting_summary") or "")[:300]
    return {
        "business_name": req.business_name or "the business",
        "description": (req.business_description or "")[:1500],
        "question": (brief.get("question") if isinstance(brief, dict) else "") or "",
        "answer": answer_line,
        "stage": "not launched yet — this is a plan" if req.operating_stage == "opening" else "already operating",
        "concept_name": req.concept_name or "",
        "modules": _modules(req),
        "roles": _roles(req),
        "journey": ", ".join(_journey(req)),
        "claims": _answer._claim_lines(claims) or "none given",
        # what the request knows (their figures, the week, the move, the roadmap) and the times they named
        "known": _known.known_for(req),
        "hours": _known.hours_for(req),
    }


def _clean_text(text: str, known: FigureSet, hours: set[int]) -> str:
    """A statement about the business, bound to the figures, keeping only the
    sentences whose every number names one."""
    if not text:
        return ""
    return clean_sentences(text.strip(), known, hours=hours)[0].strip()


def _check_story(story: dict, known: FigureSet, hours: set[int]) -> dict:
    """The narrative pages, bound to the figures, with any item holding a number
    that names none removed."""
    def bound(t) -> str | None:
        r = bind(str(t or ""), known, hours=hours)
        return None if r.unresolved else r.text

    def item(d, keys: tuple[str, ...]) -> dict | None:
        """The item with each of `keys` bound, or None when one cannot be."""
        if not isinstance(d, dict):
            return None
        texts = {k: bound(d.get(k)) for k in keys}
        if any(t is None for t in texts.values()):
            return None
        return {**d, **{k: t for k, t in texts.items() if d.get(k) is not None}}

    def items(rows, keys: tuple[str, ...]) -> list[dict]:
        return [kept for kept in (item(r, keys) for r in rows or []) if kept is not None]

    out = dict(story)
    out["headline"] = bound(story.get("headline", "")) or ""
    out["intro"] = _clean_text(story.get("intro", ""), known, hours)
    amb = dict(story.get("ambition") or {})
    amb["text"] = _clean_text(amb.get("text", ""), known, hours)
    amb["pillars"] = items(amb.get("pillars"), ("title", "text"))
    out["ambition"] = amb
    out["changes"] = items(story.get("changes"), ("today", "with", "means"))
    for key in ("principles", "local_fit"):
        out[key] = items(story.get(key), ("title", "text"))
    cmp_ = dict(story.get("comparison") or {})
    rows = []
    for r in cmp_.get("rows") or []:
        kept = item(r, ("label",))
        cells = [bound(c) for c in (r.get("cells") or [])] if kept is not None else [None]
        if kept is not None and all(c is not None for c in cells):
            rows.append({**kept, **({"cells": cells} if "cells" in r else {})})
    cmp_["rows"] = rows
    out["comparison"] = cmp_
    out["needs"] = [b for b in (bound(n) for n in story.get("needs") or []) if b is not None]
    return out


def _call(model: str, prompt: str, max_tokens: int, record) -> dict:
    """The reply's JSON. A reply that is not JSON is asked for again (up to
    `STAGE_REPLY_ATTEMPTS` in all), each call told to `record`; a provider
    failure is not."""
    return ask_until_usable(
        lambda: provider.chat(model, [{"role": "user", "content": prompt}], max_tokens=max_tokens),
        reply_json, record)


def _plan(db: Session, request_id: int, inputs: dict) -> dict:
    """The system's design, from the plan call. A call that fails, or two
    replies that plan too little, raise `StageFailed("screens")`: with no plan
    there are no screens to draw."""
    module_ids = {m["id"] for m in inputs["modules"]}
    base = dict(
        business_name=inputs["business_name"], description=inputs["description"], question=inputs["question"],
        answer=inputs["answer"], stage=inputs["stage"], concept_name=inputs["concept_name"], modules=inputs["modules"],
        roles=inputs["roles"], journey=inputs["journey"], claims=inputs["claims"], block_guide=BLOCK_GUIDE,
        accents=", ".join(schema.ACCENTS), icons=", ".join(sorted(schema.ICONS)),
        min_screens=schema.SCREENS_MIN, max_screens=schema.SCREENS_MAX,
    )
    feedback = ""
    for attempt in (1, 2):
        prompt = render_prompt("screens_plan.j2", **base)
        if feedback:
            prompt += "\n\nYOUR LAST ATTEMPT WAS REJECTED FOR THESE REASONS — fix exactly these:\n" + feedback
        try:
            raw = _call(settings.REASONING_MODEL, prompt, PLAN_TOKENS,
                        ledger(db, request_id, model=settings.REASONING_MODEL, purpose=f"screens_plan:{attempt}"))
        except Exception as exc:
            logger.warning("screens plan call failed: %s", str(exc)[:200])
            raise StageFailed("screens", exc) from exc
        plan, problems = schema.shape_plan(raw, module_ids or None)
        if plan:
            return plan
        feedback = "\n".join(f"- {p}" for p in problems)
        logger.info("screens plan attempt %d rejected: %s", attempt, feedback[:300])
    raise StageFailed("screens", f"no usable plan for the system: {feedback}")


def _draw(inputs: dict, plan: dict, screen: dict, reference: dict | None = None,
          note: str = "") -> tuple[dict | None, list[dict]]:
    """One screen's body, drawn from its brief. Returns (body, usage logs).

    `reference` is a screen of THIS product already drawn (the overview), the
    standard the rest are held to. Only the first screen, with nothing of its
    own to match yet, sees the worked example from another business — so one
    business's nouns never travel into another's screens. `note` is what was
    wrong with a previous drawing (it overflowed the frame), for the redraw."""
    module = next((m for m in inputs["modules"] if m["id"] == screen.get("module_id")), None)
    if reference is not None:
        example = json.dumps({k: reference[k] for k in ("heading", "subheading", "actions", "rows") if k in reference},
                             ensure_ascii=False)
        example_note = f"A screen of {plan['product']['name']} already drawn: the standard to match, with the same cast"
    else:
        example = _example_for(screen.get("blocks") or [])
        example_note = "A screen drawn to the standard, from another business (copy the density and the tone, never the content)"
    base = dict(
        product=plan["product"], business_name=inputs["business_name"],
        nav_labels=", ".join(i["label"] for g in plan["nav"] for i in g["items"]),
        cast=plan["cast"], claims=inputs["claims"], screen=screen, module=module,
        block_guide=BLOCK_GUIDE, example=example, example_note=example_note,
    )
    logs, feedback = [], ""
    for attempt in (1, 2):
        prompt = render_prompt("screen.j2", **base)
        if note:
            prompt += "\n\nYOUR LAST DRAWING OF THIS SCREEN DID NOT FIT THE FRAME:\n" + note
        if feedback:
            prompt += "\n\nYOUR LAST ATTEMPT WAS REJECTED FOR THESE REASONS — fix exactly these:\n" + feedback
        purpose = f"screen:{screen['id']}:{attempt}"
        try:
            # A reply that is not JSON is asked for again inside `_call`; this
            # loop's second attempt is for a drawing that came back wrong.
            raw = _call(settings.REASONING_MODEL, prompt, SCREEN_TOKENS,
                        lambda usage, error, purpose=purpose: logs.append(
                            {"purpose": purpose, "usage": usage, "success": error is None, "error": error}))
        except Exception as exc:
            logger.warning("screen %s call failed: %s", screen["id"], str(exc)[:200])
            return None, logs
        body, problems = schema.shape_body(raw)
        if body and not problems:
            return body, logs
        if body and attempt == 2:
            return body, logs
        feedback = "\n".join(f"- {p}" for p in problems) or "- no drawable rows"
    return None, logs


def _fit(db: Session, request_id: int, inputs: dict, plan: dict, bodies: dict, reference: dict | None) -> dict:
    """Measure every drawn screen in the browser and redraw the ones that run
    past the frame. Without a browser there is nothing to measure."""
    if not bodies or not browser.available():
        return bodies
    try:
        html = render.system_html(schema.assemble(plan, bodies), mode="print")
        over = browser.measure_overflow(html, list(bodies))
    except Exception as exc:
        logger.warning("screens could not be measured: %s", str(exc)[:200])
        return bodies
    if not over:
        return bodies
    by_id = {s["id"]: s for s in plan["screens"]}
    for sid, px in over.items():
        note = (f"- it ran {px}px past the bottom of the 800px frame. Use fewer rows, shorter tables, "
                f"fewer cards per column, or drop the least important block; keep the same content otherwise")
        body, logs = _draw(inputs, plan, by_id[sid], None if sid == plan["screens"][0]["id"] else reference, note=note)
        for entry in logs:
            log_usage(db, request_id, provider="openrouter", model=settings.REASONING_MODEL,
                      purpose=entry["purpose"].replace("screen:", "screen-fit:"), usage=entry.get("usage"),
                      success=entry["success"], error=entry.get("error"))
        if body:
            bodies[sid] = body
    return bodies


def _save_pngs(db: Session, req: Request, system: dict) -> int:
    """PNG per screen, and one image row each for the parts of the site that
    list screens by image. Nothing without a browser, and nothing fails."""
    request_id = req.id
    out_dir = os.path.join(settings.UPLOADS_DIR, "images", str(request_id))
    try:
        html = render.system_html(system, mode="print")
        pngs = browser.render_pngs(html, [s["id"] for s in system["screens"]], out_dir)
    except Exception as exc:
        logger.warning("screens could not be captured: %s", str(exc)[:200])
        pngs = {}
    if not pngs:
        return 0
    db.query(GeneratedImage).filter(GeneratedImage.request_id == request_id).delete(synchronize_session=False)
    for s in system["screens"]:
        if s["id"] not in pngs:
            continue
        db.add(GeneratedImage(
            request_id=request_id, role_id=s["id"], role_label=s["title"], variant=0,
            file_path=f"/uploads/images/{request_id}/{s['id']}.png", prompt="html screen",
            screen_type="html", archetype=None, composition_variant=None, provider="chromium",
            model="", prompt_version=PROMPT_VERSION, qa_score=None, qa_issues=None,
            text_truth_json=None, spec_json=None,
        ))
    db.commit()
    return len(pngs)


def _ledger_draw(db: Session, request_id: int, logs: list[dict]) -> str | None:
    """Put one screen's calls on the cost ledger, on the calling thread. Returns
    the error the drawing ended on, or None when its last call worked: a reply
    that could not be read and was then asked for again is on the ledger as
    failed, but it is not what the screen ended on."""
    for entry in logs:
        log_usage(db, request_id, provider="openrouter", model=settings.REASONING_MODEL,
                  purpose=entry["purpose"], usage=entry.get("usage"), success=entry["success"],
                  error=entry.get("error"))
    last = logs[-1] if logs else None
    if last is None or last["success"]:
        return None
    return last.get("error") or f"{last['purpose']} failed"


def build(db: Session, request_id: int) -> int:
    """Design and draw the system. Returns how many screens were drawn (at
    least `schema.SCREENS_MIN`; 0 only if the request does not exist).

    Raises `StageFailed("screens")` when the plan call fails or comes back
    unusable, when the call that draws any screen fails, or when fewer than
    `schema.SCREENS_MIN` screens come out drawable: nothing is saved then, and
    nothing stands in for the screens that were not drawn."""
    req = db.get(Request, request_id)
    if req is None:
        return 0
    inputs = _inputs(req)
    plan = _plan(db, request_id, inputs)

    # The overview is drawn first and alone; every other screen is then drawn
    # against it, in parallel, so the whole system matches one standard that
    # belongs to this business.
    first, rest = plan["screens"][0], plan["screens"][1:]

    def stop(failed: list) -> StageFailed:  # failed: (screen, error) for each screen whose call failed
        screen, error = failed[0]
        return StageFailed("screens", f"{len(failed)} of {len(plan['screens'])} screens could not be drawn; "
                                      f"first, {screen['title']}: {error}")

    first_body, first_logs = _draw(inputs, plan, first)
    bodies, failed_calls = {}, []
    error = _ledger_draw(db, request_id, first_logs)
    if error is not None:
        # nothing else is drawn, or paid for, against an overview that is not there
        raise stop([(first, error)])
    if first_body:
        bodies[first["id"]] = first_body
    reference = first_body
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        drawn = list(pool.map(lambda s: (s, _draw(inputs, plan, s, reference)), rest))
    for screen, (body, logs) in drawn:
        error = _ledger_draw(db, request_id, logs)
        if error is not None:
            failed_calls.append((screen, error))
        if body:
            bodies[screen["id"]] = body
    if failed_calls:
        raise stop(failed_calls)

    # A screen that overfills the fixed frame is redrawn once, told by how
    # much; one that still overflows is kept (the frame clips the bottom)
    # rather than dropped, since a slightly cut screen beats a missing one.
    bodies = _fit(db, request_id, inputs, plan, bodies, reference)

    for s in plan["screens"]:
        s["caption"] = _clean_text(s.get("caption", ""), inputs["known"], inputs["hours"])
    plan["story"] = _check_story(plan.get("story") or {}, inputs["known"], inputs["hours"])
    system = schema.assemble(plan, bodies)
    if len(system["screens"]) < schema.SCREENS_MIN:
        # Every call is already on the ledger. Too few screens is no system.
        raise StageFailed("screens", f"only {len(system['screens'])} screens could be drawn")

    system["version"] = PROMPT_VERSION
    req = db.get(Request, request_id)
    req.screens_json = json.dumps(system, ensure_ascii=False)
    db.commit()
    _save_pngs(db, req, system)
    return len(system["screens"])


def load(req: Request) -> dict | None:
    try:
        raw = json.loads(req.screens_json) if getattr(req, "screens_json", None) else None
    except (TypeError, ValueError):
        return None
    return raw if isinstance(raw, dict) and raw.get("screens") else None


def payload(req: Request) -> dict:
    """What the site needs to show the system live: the screens with their
    captions and thumbnails, and the page itself."""
    empty = {"available": False, "product": None, "screens": [], "html": None, "pdf_available": False}
    system = load(req)
    if not system:
        return empty
    try:
        html = render.system_html(system, mode="web")
    except Exception as exc:
        # A saved system the templates cannot draw is a bug to log, never a
        # page that fails to open.
        logger.exception("saved system for request %s could not be rendered: %s", req.id, str(exc)[:200])
        return empty
    cache_v = int(req.created_at.timestamp()) if req.created_at else 0
    out_dir = os.path.join(settings.UPLOADS_DIR, "images", str(req.id))
    screens = []
    for s in system["screens"]:
        has_png = os.path.isfile(os.path.join(out_dir, f"{s['id']}.png"))
        screens.append({"id": s["id"], "title": s["title"], "caption": s.get("caption", ""),
                        "module_id": s.get("module_id") or None,
                        "png_url": f"/uploads/images/{req.id}/{s['id']}.png?v={cache_v}" if has_png else None})
    p = system["product"]
    return {"available": True,
            "product": {"name": p["name"], "tagline": p.get("tagline", ""), "workspace": p.get("workspace", "")},
            "screens": screens, "html": html, "pdf_available": browser.available()}
