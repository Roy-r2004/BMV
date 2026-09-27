"""The screens: what a system mock may contain, and the bounds on it.

A screen is rows of blocks. The block vocabulary is the whole component
library of the renderer (templates/_blocks.html): KPI tiles, a needs-attention
list, an agenda, a table with status chips, a pipeline board, a grid board of
units (beds, rooms, bays, vans), a record header, a stage timeline, progress
bars, small charts, a form, a week schedule, a permissions matrix, an activity
log, a card grid, a callout, a feed, an AI draft-for-review card, and a chat.
Between them they draw any operational system a small business runs on, and
nothing outside them is drawn, whatever the model returns.

Everything here is pure and bounded. How many screens a system has follows
the business (one per module, plus the overview, reports, permissions and
connections where they apply) between SCREENS_MIN and SCREENS_MAX; how much
each block holds is capped at what fits one screen.
"""

import re

SCREENS_MIN, SCREENS_MAX = 4, 16
ROWS_MAX, BLOCKS_PER_ROW_MAX = 4, 3
CAST_MAX = 40

#: Accent palettes a system may be dressed in. Chosen by name so every
#: combination on screen is one that has been looked at.
ACCENTS = {
    "forest": {"accent": "#1f3d2f", "tint": "#e3ede6", "tint_ink": "#1f3d2f"},
    "navy": {"accent": "#1c3557", "tint": "#e2e9f3", "tint_ink": "#1c3557"},
    "teal": {"accent": "#0f4c5c", "tint": "#dfeef1", "tint_ink": "#0f4c5c"},
    "plum": {"accent": "#4a2545", "tint": "#eee2ec", "tint_ink": "#4a2545"},
    "rust": {"accent": "#7c3a1d", "tint": "#f3e5dd", "tint_ink": "#7c3a1d"},
    "ink": {"accent": "#1f2430", "tint": "#e6e8ee", "tint_ink": "#1f2430"},
    "blue": {"accent": "#1d4ed8", "tint": "#e3eafc", "tint_ink": "#1e3a8a"},
    "olive": {"accent": "#4d5a2a", "tint": "#e9ecdd", "tint_ink": "#4d5a2a"},
}
DEFAULT_ACCENT = "navy"

ICONS = frozenset("""home file edit pill phone inbox bed calendar users card chart shield link box
truck cart tag message bot settings star clock map briefcase wrench bell check list grid
person heart key globe camera mail flag folder""".split())

TONES = ("good", "warn", "bad", "info", "dim")
BOARD_STATES = ("occupied", "free", "reserved", "preparing", "closed")
STAGE_STATES = ("done", "now", "next")
FIELD_TYPES = ("text", "textarea", "choice", "scale", "check", "select")
CARD_STATES = ("connected", "connect", "on", "off", "none")
LIMITS = {
    "kpis": 6, "list": 7, "agenda": 7, "table_rows": 8, "table_cols": 6, "pipeline_cols": 5,
    "pipeline_cards": 5, "board_groups": 4, "board_cells": 20, "stages": 6, "progress": 5,
    "bars": 8, "line": 8, "form_fields": 7, "schedule_days": 7, "schedule_slots": 6,
    "matrix_rows": 8, "matrix_cols": 4, "log": 7, "cards": 8, "feed": 6, "chat": 6,
    "draft": 4, "tabs": 5, "options": 5, "tags": 3, "lines": 3, "actions": 2, "legend": 5,
}


def _t(v, limit: int) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()[:limit]


def _slug(v) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", _t(v, 60).casefold())).strip("_")[:40]


def _tone(v, default="dim") -> str:
    v = _t(v, 10).lower()
    return v if v in TONES else default


def _w(v) -> int:
    try:
        return max(1, min(3, int(v)))
    except (TypeError, ValueError):
        return 1


def _strs(items, limit: int, each: int) -> list[str]:
    return [s for s in (_t(x, each) for x in (items if isinstance(items, list) else [])[:limit]) if s]


def _cell(v) -> dict | str:
    """A table cell: plain text, or a chip / action / strong value."""
    if isinstance(v, dict):
        if v.get("chip") is not None:
            return {"chip": _t(v.get("chip"), 40), "tone": _tone(v.get("tone"))}
        if v.get("action") is not None:
            return {"action": _t(v.get("action"), 30)}
        if v.get("strong") is not None:
            return {"strong": _t(v.get("strong"), 60)}
        return _t(v.get("text"), 80)
    return _t(v, 80)


# ── one shaper per block kind; each returns a clean block or None ──

def _kpis(b):
    items = [{"value": _t(i.get("value"), 14), "label": _t(i.get("label"), 40), "sub": _t(i.get("sub"), 40)}
             for i in (b.get("items") or [])[:LIMITS["kpis"]] if isinstance(i, dict)]
    items = [i for i in items if i["value"] and i["label"]]
    return {"kind": "kpis", "items": items} if len(items) >= 2 else None


def _list(b):
    rows = []
    for r in (b.get("rows") or [])[:LIMITS["list"]]:
        if isinstance(r, dict) and _t(r.get("text"), 140):
            rows.append({"tag": _t(r.get("tag"), 18), "tone": _tone(r.get("tone")),
                         "text": _t(r.get("text"), 140), "action": _t(r.get("action"), 20)})
    return {"kind": "list", "title": _t(b.get("title"), 50), "rows": rows,
            "footer": _t(b.get("footer"), 140)} if rows else None


def _agenda(b):
    rows = [{"time": _t(r.get("time"), 12), "title": _t(r.get("title"), 60), "sub": _t(r.get("sub"), 50),
             "now": bool(r.get("now"))}
            for r in (b.get("rows") or [])[:LIMITS["agenda"]] if isinstance(r, dict)]
    rows = [r for r in rows if r["time"] and r["title"]]
    return {"kind": "agenda", "title": _t(b.get("title"), 50), "rows": rows} if rows else None


def _table(b):
    cols = _strs(b.get("columns"), LIMITS["table_cols"], 30)
    rows = []
    for r in (b.get("rows") or [])[:LIMITS["table_rows"]]:
        if isinstance(r, list) and r:
            cells = [_cell(c) for c in r[:len(cols) or LIMITS["table_cols"]]]
            rows.append(cells + [""] * (len(cols) - len(cells)))
    if not cols or not rows:
        return None
    return {"kind": "table", "title": _t(b.get("title"), 50), "sub": _t(b.get("sub"), 120),
            "columns": cols, "rows": rows, "footer": _t(b.get("footer"), 160)}


def _pipeline(b):
    cols = []
    for c in (b.get("columns") or [])[:LIMITS["pipeline_cols"]]:
        if not isinstance(c, dict) or not _t(c.get("title"), 30):
            continue
        cards = []
        for k in (c.get("cards") or [])[:LIMITS["pipeline_cards"]]:
            if isinstance(k, dict) and _t(k.get("title"), 40):
                cards.append({"title": _t(k.get("title"), 40), "tags": _strs(k.get("tags"), LIMITS["tags"], 18),
                              "lines": _strs(k.get("lines"), LIMITS["lines"], 60),
                              "action": _t(k.get("action"), 24), "alert": _t(k.get("alert"), 40)})
        cols.append({"title": _t(c.get("title"), 30), "cards": cards})
    return {"kind": "pipeline", "title": _t(b.get("title"), 50), "columns": cols,
            "footer": _t(b.get("footer"), 160)} if len(cols) >= 2 else None


def _board(b):
    groups = []
    for g in (b.get("groups") or [])[:LIMITS["board_groups"]]:
        if not isinstance(g, dict):
            continue
        cells = []
        for c in (g.get("cells") or [])[:LIMITS["board_cells"]]:
            if isinstance(c, dict) and _t(c.get("code"), 8):
                st = _t(c.get("state"), 12).lower()
                cells.append({"code": _t(c.get("code"), 8), "label": _t(c.get("label"), 14),
                              "state": st if st in BOARD_STATES else "free"})
        if cells:
            groups.append({"title": _t(g.get("title"), 40), "cells": cells})
    if not groups:
        return None
    side = b.get("side") if isinstance(b.get("side"), dict) else None
    return {"kind": "board", "title": _t(b.get("title"), 50), "sub": _t(b.get("sub"), 120), "groups": groups,
            "legend": [s for s in _strs(b.get("legend"), LIMITS["legend"], 12)] or [],
            "side": ({"title": _t(side.get("title"), 40), "lines": _strs(side.get("lines"), 4, 60),
                      "actions": _strs(side.get("actions"), LIMITS["actions"], 20)} if side else None)}


def _record(b):
    name = _t(b.get("name"), 40)
    if not name:
        return None
    initials = _t(b.get("initials"), 3) or "".join(p[0] for p in name.split()[:2]).upper()
    tabs = _strs(b.get("tabs"), LIMITS["tabs"], 24)
    return {"kind": "record", "initials": initials, "name": name, "meta": _t(b.get("meta"), 120),
            "action": _t(b.get("action"), 24), "tabs": tabs, "active_tab": _t(b.get("active_tab"), 24) or (tabs[0] if tabs else "")}


def _stages(b):
    items = []
    for i in (b.get("items") or [])[:LIMITS["stages"]]:
        if isinstance(i, dict) and _t(i.get("label"), 30):
            st = _t(i.get("state"), 6).lower()
            items.append({"label": _t(i.get("label"), 30), "sub": _t(i.get("sub"), 30),
                          "state": st if st in STAGE_STATES else "next"})
    return {"kind": "stages", "items": items} if len(items) >= 2 else None


def _progress(b):
    items = []
    for i in (b.get("items") or [])[:LIMITS["progress"]]:
        if isinstance(i, dict) and _t(i.get("label"), 50):
            try:
                pct = max(0, min(100, int(float(i.get("pct") or 0))))
            except (TypeError, ValueError):
                pct = 0
            items.append({"label": _t(i.get("label"), 50), "pct": pct, "status": _t(i.get("status"), 24)})
    return {"kind": "progress", "title": _t(b.get("title"), 50), "items": items,
            "footer": _t(b.get("footer"), 120)} if items else None


def _series(items, limit):
    out = []
    for i in (items or [])[:limit]:
        if not isinstance(i, dict):
            continue
        try:
            v = float(i.get("value"))
        except (TypeError, ValueError):
            continue
        out.append({"label": _t(i.get("label"), 16), "value": max(0.0, v), "display": _t(i.get("display"), 12)})
    return [o for o in out if o["label"]]


def _bars(b):
    items = _series(b.get("items"), LIMITS["bars"])
    return {"kind": "bars", "title": _t(b.get("title"), 50), "sub": _t(b.get("sub"), 100), "items": items,
            "horizontal": bool(b.get("horizontal"))} if len(items) >= 2 else None


def _line(b):
    pts = _series(b.get("points"), LIMITS["line"])
    return {"kind": "line", "title": _t(b.get("title"), 50), "sub": _t(b.get("sub"), 100),
            "points": pts} if len(pts) >= 3 else None


def _form(b):
    fields = []
    for f in (b.get("fields") or [])[:LIMITS["form_fields"]]:
        if not isinstance(f, dict) or not _t(f.get("label"), 60):
            continue
        ft = _t(f.get("type"), 10).lower()
        fields.append({"label": _t(f.get("label"), 60), "type": ft if ft in FIELD_TYPES else "text",
                       "value": _t(f.get("value"), 240), "help": _t(f.get("help"), 90),
                       "options": _strs(f.get("options"), LIMITS["options"], 24),
                       "selected": _t(f.get("selected"), 24)})
    if not fields:
        return None
    return {"kind": "form", "title": _t(b.get("title"), 50), "sub": _t(b.get("sub"), 120), "fields": fields,
            "note": _t(b.get("note"), 160), "primary": _t(b.get("primary"), 24), "secondary": _t(b.get("secondary"), 24)}


def _schedule(b):
    days = _strs(b.get("days"), LIMITS["schedule_days"], 10)
    slots = []
    for s in (b.get("slots") or [])[:LIMITS["schedule_slots"]]:
        if not isinstance(s, dict) or not _t(s.get("time"), 10):
            continue
        cells = []
        for c in (s.get("cells") or [])[:len(days)]:
            cells.append({"title": _t(c.get("title"), 30), "sub": _t(c.get("sub"), 30), "tone": _tone(c.get("tone"), "info")}
                         if isinstance(c, dict) and _t(c.get("title"), 30) else None)
        slots.append({"time": _t(s.get("time"), 10), "cells": cells + [None] * (len(days) - len(cells))})
    if len(days) < 2 or not slots:
        return None
    return {"kind": "schedule", "title": _t(b.get("title"), 50), "sub": _t(b.get("sub"), 120), "days": days,
            "slots": slots, "legend": _strs(b.get("legend"), LIMITS["legend"], 16), "footer": _t(b.get("footer"), 140)}


def _matrix(b):
    cols = _strs(b.get("columns"), LIMITS["matrix_cols"], 30)
    rows = [[_t(c, 40) for c in r[:len(cols)]] + [""] * max(0, len(cols) - len(r))
            for r in (b.get("rows") or [])[:LIMITS["matrix_rows"]] if isinstance(r, list) and r]
    if len(cols) < 2 or not rows:
        return None
    tabs = _strs(b.get("tabs"), LIMITS["tabs"], 24)
    return {"kind": "matrix", "title": _t(b.get("title"), 50), "sub": _t(b.get("sub"), 120), "tabs": tabs,
            "active": _t(b.get("active"), 24) or (tabs[0] if tabs else ""), "columns": cols, "rows": rows}


def _log(b):
    rows = [{"time": _t(r.get("time"), 12), "who": _t(r.get("who"), 30), "text": _t(r.get("text"), 100),
             "blocked": bool(r.get("blocked"))}
            for r in (b.get("rows") or [])[:LIMITS["log"]] if isinstance(r, dict)]
    rows = [r for r in rows if r["time"] and r["text"]]
    return {"kind": "log", "title": _t(b.get("title"), 50), "rows": rows} if rows else None


def _cards(b):
    items = []
    for i in (b.get("items") or [])[:LIMITS["cards"]]:
        if isinstance(i, dict) and _t(i.get("title"), 40):
            st = _t(i.get("state"), 10).lower()
            items.append({"title": _t(i.get("title"), 40), "text": _t(i.get("text"), 110),
                          "state": st if st in CARD_STATES else "none", "action": _t(i.get("action"), 20)})
    return {"kind": "cards", "title": _t(b.get("title"), 50), "sub": _t(b.get("sub"), 120),
            "items": items} if items else None


def _note(b):
    text = _t(b.get("text"), 220)
    return {"kind": "note", "text": text, "tone": _tone(b.get("tone"), "info")} if text else None


def _feed(b):
    rows = [{"meta": _t(r.get("meta"), 60), "text": _t(r.get("text"), 160), "tag": _t(r.get("tag"), 20)}
            for r in (b.get("rows") or [])[:LIMITS["feed"]] if isinstance(r, dict)]
    rows = [r for r in rows if r["text"]]
    return {"kind": "feed", "title": _t(b.get("title"), 50), "rows": rows} if rows else None


def _draft(b):
    bullets = [{"text": _t(x.get("text"), 140), "cite": _t(x.get("cite"), 16)} if isinstance(x, dict)
               else {"text": _t(x, 140), "cite": ""} for x in (b.get("bullets") or [])[:LIMITS["draft"]]]
    bullets = [x for x in bullets if x["text"]]
    if not bullets:
        return None
    return {"kind": "draft", "title": _t(b.get("title"), 50), "badge": _t(b.get("badge"), 16) or "AI draft",
            "note": _t(b.get("note"), 140), "bullets": bullets,
            "primary": _t(b.get("primary"), 24), "secondary": _t(b.get("secondary"), 24)}


def _chat(b):
    msgs = [{"from": "agent" if _t(m.get("from"), 8).lower() == "agent" else "person", "text": _t(m.get("text"), 200)}
            for m in (b.get("messages") or [])[:LIMITS["chat"]] if isinstance(m, dict)]
    msgs = [m for m in msgs if m["text"]]
    return {"kind": "chat", "title": _t(b.get("title"), 50), "sub": _t(b.get("sub"), 90), "messages": msgs,
            "note": _t(b.get("note"), 140)} if msgs else None


SHAPERS = {
    "kpis": _kpis, "list": _list, "agenda": _agenda, "table": _table, "pipeline": _pipeline, "board": _board,
    "record": _record, "stages": _stages, "progress": _progress, "bars": _bars, "line": _line, "form": _form,
    "schedule": _schedule, "matrix": _matrix, "log": _log, "cards": _cards, "note": _note, "feed": _feed,
    "draft": _draft, "chat": _chat,
}
BLOCK_KINDS = tuple(SHAPERS)


def shape_block(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    kind = _t(raw.get("kind"), 12).lower()
    shaper = SHAPERS.get(kind)
    if shaper is None:
        return None
    block = shaper(raw)
    if block is not None:
        block["w"] = _w(raw.get("w"))
    return block


def shape_body(raw) -> tuple[dict | None, list[str]]:
    """One screen's body: the heading over the work area, its line under,
    the actions top right, and the rows. None when nothing is drawable."""
    if not isinstance(raw, dict):
        return None, ["the screen was not an object"]
    rows, problems = shape_rows(raw.get("rows"))
    if not rows:
        return None, problems or ["no drawable rows"]
    return {"heading": _t(raw.get("heading"), 40), "subheading": _t(raw.get("subheading"), 110),
            "actions": _strs(raw.get("actions"), LIMITS["actions"], 24), "rows": rows}, problems


def shape_rows(raw_rows) -> tuple[list[list[dict]], list[str]]:
    """The rows of one screen. Blocks the renderer cannot draw are dropped
    and named, so a retry can fix exactly them."""
    rows, problems = [], []
    for ri, row in enumerate((raw_rows if isinstance(raw_rows, list) else [])[:ROWS_MAX]):
        items = row if isinstance(row, list) else [row]
        clean = []
        for bi, b in enumerate(items[:BLOCKS_PER_ROW_MAX]):
            block = shape_block(b)
            if block is None:
                kind = b.get("kind") if isinstance(b, dict) else "?"
                problems.append(f"row {ri + 1} block {bi + 1} ({kind}) was empty or of an unknown kind")
                continue
            clean.append(block)
        if clean:
            rows.append(clean)
    return rows, problems


# ── the plan: product, navigation, cast and the screen index ──

def shape_nav(raw_nav, screen_ids: set[str]) -> list[dict]:
    groups = []
    seen = set()
    for g in (raw_nav if isinstance(raw_nav, list) else [])[:6]:
        if not isinstance(g, dict):
            continue
        items = []
        for i in (g.get("items") or [])[:8]:
            if not isinstance(i, dict):
                continue
            sid = _slug(i.get("screen"))
            label = _t(i.get("label"), 26)
            if not sid or not label or sid in seen:
                continue
            icon = _t(i.get("icon"), 12).lower()
            items.append({"screen": sid, "label": label, "icon": icon if icon in ICONS else "dot",
                          "live": sid in screen_ids})
            seen.add(sid)
        if items:
            groups.append({"group": _t(g.get("group"), 24), "items": items})
    return groups


def shape_product(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    accent = _t(raw.get("accent"), 12).lower()
    return {
        "name": _t(raw.get("name"), 30) or "Your system",
        "tagline": _t(raw.get("tagline"), 40),
        "workspace": _t(raw.get("workspace"), 40),
        "signed_in": _t(raw.get("signed_in"), 60),
        "languages": _strs(raw.get("languages"), 3, 8),
        "search_hint": _t(raw.get("search_hint"), 60),
        "date_line": _t(raw.get("date_line"), 60),
        "accent": accent if accent in ACCENTS else DEFAULT_ACCENT,
    }


def shape_cast(raw) -> list[dict]:
    out = []
    for c in (raw if isinstance(raw, list) else [])[:CAST_MAX]:
        if isinstance(c, dict) and _t(c.get("name"), 40):
            out.append({"name": _t(c.get("name"), 40), "role": _t(c.get("role"), 60), "note": _t(c.get("note"), 120)})
    return out


def shape_index(raw_screens, module_ids: set[str] | None = None) -> list[dict]:
    """The screen list of the plan: id, title, caption, module and a brief."""
    out, seen = [], set()
    for s in (raw_screens if isinstance(raw_screens, list) else [])[:SCREENS_MAX]:
        if not isinstance(s, dict):
            continue
        sid = _slug(s.get("id") or s.get("title"))
        title = _t(s.get("title"), 40)
        if not sid or not title or sid in seen:
            continue
        mid = _t(s.get("module_id"), 60)
        out.append({"id": sid, "title": title, "caption": _t(s.get("caption"), 280),
                    "module_id": mid if (module_ids is None or mid in module_ids) else "",
                    "brief": _t(s.get("brief"), 400),
                    "blocks": [k for k in _strs(s.get("blocks"), 6, 12) if k.lower() in SHAPERS]})
        seen.add(sid)
    return out


def shape_story(raw) -> dict:
    """The proposal's narrative pages. Bounded; statements about the business
    are checked for invented figures by the caller, not here."""
    raw = raw if isinstance(raw, dict) else {}
    amb = raw.get("ambition") if isinstance(raw.get("ambition"), dict) else {}
    cmp_ = raw.get("comparison") if isinstance(raw.get("comparison"), dict) else {}
    return {
        "headline": _t(raw.get("headline"), 80),
        "intro": _t(raw.get("intro"), 400),
        "ambition": {
            "title": _t(amb.get("title"), 60), "text": _t(amb.get("text"), 300),
            "pillars": [{"title": _t(p.get("title"), 40), "text": _t(p.get("text"), 160)}
                        for p in (amb.get("pillars") or [])[:3] if isinstance(p, dict) and _t(p.get("title"), 40)],
        },
        "changes": [{"today": _t(c.get("today"), 120), "with": _t(c.get("with"), 220), "means": _t(c.get("means"), 160)}
                    for c in (raw.get("changes") or [])[:6] if isinstance(c, dict) and _t(c.get("today"), 120)],
        "principles": [{"title": _t(p.get("title"), 50), "text": _t(p.get("text"), 200)}
                       for p in (raw.get("principles") or [])[:6] if isinstance(p, dict) and _t(p.get("title"), 50)],
        "local_fit": [{"title": _t(p.get("title"), 50), "text": _t(p.get("text"), 200)}
                      for p in (raw.get("local_fit") or [])[:5] if isinstance(p, dict) and _t(p.get("title"), 50)],
        "comparison": {
            "columns": _strs(cmp_.get("columns"), 3, 30),
            "rows": [{"label": _t(r.get("label"), 60), "cells": _strs(r.get("cells"), 3, 60)}
                     for r in (cmp_.get("rows") or [])[:7] if isinstance(r, dict) and _t(r.get("label"), 60)],
        },
        "needs": _strs(raw.get("needs"), 4, 100),
    }


def shape_plan(raw, module_ids: set[str] | None = None) -> tuple[dict | None, list[str]]:
    """(plan, problems). The plan is everything but the screens' rows."""
    if not isinstance(raw, dict):
        return None, ["the response was not an object"]
    problems = []
    index = shape_index(raw.get("screens"), module_ids)
    if len(index) < SCREENS_MIN:
        problems.append(f"only {len(index)} usable screens; at least {SCREENS_MIN} are needed")
        return None, problems
    ids = {s["id"] for s in index}
    nav = shape_nav(raw.get("nav"), ids)
    if not nav:
        # a navigation the plan forgot is built from the screens themselves
        nav = [{"group": "", "items": [{"screen": s["id"], "label": s["title"], "icon": "dot", "live": True} for s in index]}]
    return {"product": shape_product(raw.get("product")), "nav": nav, "cast": shape_cast(raw.get("cast")),
            "screens": index, "story": shape_story(raw.get("story"))}, problems


def assemble(plan: dict, bodies: dict[str, dict]) -> dict:
    """The system: the plan with each screen's body in place. Screens whose
    body never arrived are dropped, and the navigation marks them absent."""
    screens = []
    for s in plan["screens"]:
        body = bodies.get(s["id"])
        if body and body.get("rows"):
            screens.append({**{k: v for k, v in s.items() if k not in ("brief", "blocks")}, **body})
    ids = {s["id"] for s in screens}
    nav = [{"group": g["group"], "items": [{**i, "live": i["screen"] in ids} for i in g["items"]]} for g in plan["nav"]]
    return {"product": plan["product"], "nav": nav, "cast": plan.get("cast", []), "screens": screens,
            "story": plan.get("story", shape_story({}))}


def shape_system(raw) -> tuple[dict | None, list[str]]:
    """A whole system in one object (fixtures, tests, a single-call model)."""
    plan, problems = shape_plan(raw)
    if plan is None:
        return None, problems
    bodies = {}
    for s in (raw.get("screens") or []):
        if isinstance(s, dict):
            sid = _slug(s.get("id") or s.get("title"))
            body, p = shape_body(s)
            problems += [f"{sid}: {x}" for x in p]
            if body:
                bodies[sid] = body
    system = assemble(plan, bodies)
    if len(system["screens"]) < SCREENS_MIN:
        problems.append(f"only {len(system['screens'])} screens had drawable rows")
        return None, problems
    return system, problems
