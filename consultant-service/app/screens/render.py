"""HTML for a system: the live page the website embeds, and the proposal
the browser prints. One set of templates draws both, so what the client
navigates on the site is exactly what they hold on paper.

`prepare` measures what the templates only draw (grid columns, bar heights,
line paths); `system_html` and `proposal_html` render. Nothing here talks to
a model or a database: `proposal_context` takes plain values.

The release law (`app.figures.law`) reads what the templates print. Every
`{{ ... }}` that prints a string passes the environment's `finalize`, which is
the screens' content choke point: inside a law scope (the proposal PDF) its
numbers are bound or recorded. Not read, by declaration of the code that draws
them: markup the code builds (`Markup`: the stylesheet, icons, JSON), numbers
the code computes (ints and floats: geometry, counters, list numbering),
anything piped through `|drawn` (dates, SVG paths, colours), and everything
inside `{% call sample() %}`, a drawn screen's sample data, which refuses to
render without the SAMPLE DATA stamp.
"""

import base64
import copy
import json
import os
import re
from datetime import date
from functools import lru_cache

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from app.figures import law
from app.figures.known import move_figures
from app.figures.model import display
from app.figures.read import mentions
from app.screens import schema

TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")
#: how much a 1280px frame is scaled to sit on an A4 landscape page
PAGE_SCALE = 0.78


def _finalize(value):
    """Every printed value. A plain string is content and goes through the
    release law; markup the code built and numbers it computed are drawn."""
    if isinstance(value, str) and not isinstance(value, Markup):
        return law.check(value)
    return value


def _drawn(value) -> Markup:
    """`{{ x|drawn }}`: a value the template draws as furniture (a date it
    stamps, an SVG path, a colour), escaped and not read by the law."""
    return Markup(escape("" if value is None else value))


def _sample(caller) -> Markup:
    """`{% call sample() %}...{% endcall %}`: a drawn screen's sample data. The
    law does not read it, and it must carry the SAMPLE DATA stamp, or the page
    is not drawn."""
    with law.sample_region():
        body = caller()
    if not law.stamped(body):
        raise law.UnstampedSample("a sample region was drawn without its SAMPLE DATA stamp")
    return Markup(body)


_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]),
                   trim_blocks=False, lstrip_blocks=False, finalize=_finalize)
_env.filters["drawn"] = _drawn
_env.globals["sample"] = _sample

# ── icons: stroke paths, 24-unit box, drawn in currentColor ──
ICONS = {
    "dot": '<circle cx="12" cy="12" r="3"/>',
    "home": '<path d="M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/>',
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    "edit": '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    "pill": '<rect x="3" y="9" width="18" height="6" rx="3" transform="rotate(-45 12 12)"/><path d="M8.5 15.5l7-7"/>',
    "phone": '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.6a2 2 0 0 1-.5 2.1L8.1 9.7a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.8.3 1.7.5 2.6.7a2 2 0 0 1 1.7 2z"/>',
    "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.5 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.5A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.5z"/>',
    "bed": '<path d="M2 20v-8a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v8"/><path d="M2 16h20"/><path d="M6 10V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v4"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "users": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
    "card": '<rect x="1" y="4" width="22" height="16" rx="2"/><path d="M1 10h22"/>',
    "chart": '<path d="M3 3v18h18"/><path d="M7 14l4-4 4 4 5-6"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
    "box": '<path d="M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4a2 2 0 0 0 1-1.7z"/><path d="M3.3 7 12 12l8.7-5M12 22V12"/>',
    "truck": '<rect x="1" y="3" width="15" height="13"/><path d="M16 8h4l3 3v5h-7z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>',
    "cart": '<circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.7 13.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L23 6H6"/>',
    "tag": '<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8z"/><path d="M7 7h.01"/>',
    "message": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "bot": '<rect x="3" y="8" width="18" height="12" rx="2"/><path d="M12 8V4M8 14h.01M16 14h.01M9 18h6"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "star": '<path d="m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1z"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "map": '<path d="M1 6v16l7-4 8 4 7-4V2l-7 4-8-4z"/><path d="M8 2v16M16 6v16"/>',
    "briefcase": '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
    "wrench": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.8-3.8a6 6 0 0 1-7.9 7.9l-7 7a2.1 2.1 0 0 1-3-3l7-7a6 6 0 0 1 7.9-7.9z"/>',
    "bell": '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "grid": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
    "person": '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "heart": '<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.8z"/>',
    "key": '<path d="m21 2-2 2m-7.6 7.6a5.5 5.5 0 1 1-7.8 7.8 5.5 5.5 0 0 1 7.8-7.8zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    "camera": '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
    "mail": '<path d="M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><path d="m22 6-10 7L2 6"/>',
    "flag": '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7"/>',
    "folder": '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
}
ICON_MARKUP = {k: Markup(v) for k, v in ICONS.items()}


@lru_cache(maxsize=1)
def _embedded_fonts() -> str:
    """@font-face rules with the brand fonts inlined, for the browser that
    prints: no network, no fallback face on paper."""
    faces = [("IBM Plex Sans", 400, "PlexSans.ttf"), ("IBM Plex Sans", 500, "PlexSans-Medium.ttf"),
             ("IBM Plex Sans", 600, "PlexSans-SemiBold.ttf"), ("IBM Plex Sans", 700, "PlexSans-Bold.ttf"),
             ("Syne", 700, "Syne-Bold.ttf"), ("Syne", 800, "Syne-ExtraBold.ttf")]
    out = []
    for family, weight, name in faces:
        path = os.path.join(FONT_DIR, name)
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        out.append(f'@font-face{{font-family:"{family}";font-weight:{weight};font-style:normal;'
                   f'src:url(data:font/ttf;base64,{b64}) format("truetype");}}')
    return "\n".join(out)


def stylesheet(accent_name: str) -> str:
    accent = schema.ACCENTS.get(accent_name) or schema.ACCENTS[schema.DEFAULT_ACCENT]
    with law.furniture():                     # colours and sizes, not content
        return _env.get_template("screens.css").render(accent=accent)


def short_name(name: str) -> str:
    """'Halo Reformer Studio LLC' → 'Halo Reformer Studio'; the first three
    words otherwise, so headings stay one line."""
    words = [w for w in re.sub(r"\b(llc|ltd|inc|sarl|sal|gmbh|co\.?|company|plc)\b\.?", "", name or "", flags=re.I).split() if w]
    return " ".join(words[:3]) or (name or "your business")


def _initials(text: str) -> str:
    words = [w for w in re.sub(r"[^\w\s]", " ", text or "").split() if w and not w.lower().startswith("dr")]
    return "".join(w[0] for w in words[:2]).upper() or "AA"


def _fmt(v: float) -> str:
    return f"{int(v):,}" if float(v).is_integer() else f"{v:,.1f}"


def _legend(entries: list[str], states: tuple[str, ...]) -> list[dict]:
    out = []
    for e in entries:
        key = e.lower()
        if key in states:
            out.append({"state": key, "label": e.capitalize()})
        else:
            out.append({"state": states[0], "label": e})
    return out


def _line_geometry(points: list[dict]) -> dict:
    w, h, px, top, bottom = 600, 120, 14, 12, 108
    vals = [p["value"] for p in points]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    n = len(points)
    pts = []
    for i, p in enumerate(points):
        x = px + i * ((w - 2 * px) / (n - 1))
        y = bottom - (p["value"] - lo) / span * (bottom - top)
        pts.append({"x": round(x, 1), "y": round(y, 1)})
    path = "M" + " L".join(f"{p['x']},{p['y']}" for p in pts)
    area = f"{path} L{pts[-1]['x']},{h} L{pts[0]['x']},{h} Z"
    return {"w": w, "h": h, "path": path, "area": area, "pts": pts}


def prepare(system: dict) -> dict:
    """Measure what the templates draw. Returns a deep copy."""
    s = copy.deepcopy(system)
    prod = s["product"]
    prod["initials"] = _initials(prod.get("signed_in") or prod.get("workspace") or prod["name"])
    alerts = 0
    for scr in s["screens"]:
        for row in scr.get("rows") or []:
            for b in row:
                if b.get("kind") == "list" and not alerts:
                    alerts = len(b["rows"])
    prod["alerts"] = alerts or 3
    for scr in s["screens"]:
        rows_out = []
        for row in scr.get("rows") or []:
            total = sum(b.get("w", 1) for b in row) or 1
            for b in row:
                kind = b.get("kind")
                share = b.get("w", 1) / total
                if kind == "bars":
                    mx = max(i["value"] for i in b["items"]) or 1
                    for i in b["items"]:
                        i["h"] = round(i["value"] / mx * 100)
                        i["value_text"] = _fmt(i["value"])
                elif kind == "line":
                    b["svg"] = _line_geometry(b["points"])
                elif kind == "cards":
                    b["cols"] = 2 if share >= 0.6 and len(b["items"]) >= 2 else 1
                elif kind == "board":
                    b["legend"] = _legend(b.get("legend") or [], schema.BOARD_STATES)
                elif kind == "schedule":
                    b["legend"] = _legend(b.get("legend") or [], ("info", "good", "warn", "bad", "dim"))
            rows_out.append({"cols": " ".join(f"{b.get('w', 1)}fr" for b in row), "blocks": row})
        scr["rows"] = rows_out
    return s


def system_html(system: dict, mode: str = "web") -> str:
    """The live system. `web` loads the type from Google Fonts; `print` embeds
    it, for a browser with no network (the PNG and PDF renders)."""
    s = prepare(system)
    return _env.get_template("system.html").render(
        system=s, css=stylesheet(s["product"]["accent"]), icons=ICON_MARKUP,
        fonts_link=(mode == "web"), fonts_css=("" if mode == "web" else _embedded_fonts()),
        screen_ids=[x["id"] for x in s["screens"]],
    )


def _journey(stages: list[str]) -> tuple[list[dict], str]:
    names = [str(x).strip()[:28] for x in stages if str(x).strip()][:5]
    if len(names) < 2:
        return [], ""
    n = len(names)
    pts = []
    for i, name in enumerate(names):
        x = 20 + i * (560 / (n - 1))
        y = 22 if i % 2 == 0 else 50
        pts.append({"x": round(x, 1), "y": y, "label": name, "sub": ""})
    d = f"M{pts[0]['x']},{pts[0]['y']}"
    for a, b in zip(pts, pts[1:]):
        cx = (a["x"] + b["x"]) / 2
        d += f" C{cx},{a['y']} {cx},{b['y']} {b['x']},{b['y']}"
    return pts, d


def _first_block(system: dict, kind: str) -> dict | None:
    for scr in system["screens"]:
        for row in scr.get("rows") or []:
            for b in row:
                if b.get("kind") == kind:
                    return b
    return None


_FILL = re.compile(r"(\d+)\s*(?:/|of)\s*(\d+)")


def _fill_of(value: str) -> int:
    m = _FILL.search(value or "")
    if m and int(m.group(2)) > 0:
        return max(0, min(24, round(int(m.group(1)) / int(m.group(2)) * 24)))
    return 16


def proposal_context(system: dict, *, business_name: str, journey_stages: list[str] | None = None,
                     answer: dict | None = None, roadmap: dict | None = None,
                     on: date | None = None) -> dict:
    """Everything the proposal pages need, from values the run already holds."""
    story = system.get("story") or schema.shape_story({})
    short = short_name(business_name)
    product = system["product"]["name"]
    lst = _first_block(system, "list")
    # The cover's hero is the answer's first headline figure, bound to the
    # client's own figures; with none, the cover has no hero. Never a sample
    # tile: the cover is not a sample region (plan ruling 3).
    hero_kpi = None
    headline = next(iter((answer or {}).get("figures") or []), None)
    if isinstance(headline, dict) and str(headline.get("value") or "").strip():
        value = str(headline["value"])
        hero_kpi = {"value": value, "label": str(headline.get("label") or ""), "sub": "",
                    "ids": list(headline.get("ids") or []),
                    "fill": _fill_of(value) if _FILL.search(value) else None}
    # the cover's floating cards show the product, so they carry no number:
    # only list rows that hold none are drawn there
    hero_rows = [r for r in (lst or {}).get("rows", [])
                 if isinstance(r, dict) and not any(mentions(str(r.get(k) or "")) for k in ("text", "tag", "action"))]
    pts, path = _journey(journey_stages or [])

    groups = []
    by_id = {s["id"]: s for s in system["screens"]}
    for g in system["nav"]:
        items = []
        for i in g["items"]:
            scr = by_id.get(i["screen"])
            if scr:
                cap = re.split(r"(?<=[.!?])\s", scr.get("caption") or "")[0][:110]
                items.append({"title": scr["title"], "text": cap})
        if items:
            groups.append({"title": g["group"] or product, "sub": "", "items": items})
    # Four cards on the page: a one-screen group joins its neighbour rather
    # than taking a card of its own, and the fullest group takes the lead.
    while len(groups) > 4:
        i = min(range(len(groups)), key=lambda k: len(groups[k]["items"]))
        j = i + 1 if i + 1 < len(groups) else i - 1
        groups[j]["items"] = groups[i]["items"] + groups[j]["items"] if j < i else groups[j]["items"] + groups[i]["items"]
        groups.pop(i)
    groups.sort(key=lambda g: -len(g["items"]))

    move = (answer or {}).get("move") or None
    if move:
        # each number we propose prints as its figure (PROP-n) displays it, so a
        # price reads "$28" and the law binds it to the proposal
        proposed = [f for f in move_figures(move) if f.id.startswith("PROP-")]
        move = {"display": move.get("display", ""), "label": move.get("label", ""),
                "working": move.get("working", ""),
                "proposed": (" and ".join(f"{f.source.note or 'the proposed figure'} ({display(f)})" for f in proposed)
                             + (" is our proposal, not your figure." if len(proposed) == 1 else " are our proposals, not your figures.")
                             if proposed else "")}
    figures = [{"value": f.get("value", ""), "label": f.get("label", "")} for f in (answer or {}).get("figures") or []][:4]

    comparison = story.get("comparison") or {}
    cols = comparison.get("columns") or []
    if len(cols) < 3:
        cols = ["What you use today", "Off-the-shelf software", product]
    phases = [p for p in ((roadmap or {}).get("phases") or []) if p.get("title")][:4]

    return {
        "title": f"{product} for {short}",
        "product_name": product,
        "business": business_name,
        "business_short": short,
        "date": (on or date.today()).strftime("%d %B %Y").lstrip("0"),
        "headline": story.get("headline") or f"One system to run all of {short}.",
        "intro": story.get("intro") or system["screens"][0].get("caption", ""),
        "journey": pts, "journey_path": path,
        "hero_kpi": hero_kpi,
        "hero_rows": hero_rows[:2],
        "ambition": story.get("ambition") or {},
        "changes": story.get("changes") or [],
        "move": move, "figures": figures,
        "groups": groups,
        "principles": story.get("principles") or [],
        "principles_title": story.get("principles_title") or f"Built around what matters to {short}",
        "principles_intro": story.get("principles_intro") or "",
        "local_fit": story.get("local_fit") or [],
        "local_title": story.get("local_title") or f"Made for how {short} actually runs",
        "comparison": {"columns": cols[:3], "rows": comparison.get("rows") or []},
        "phases": phases,
        "needs": story.get("needs") or [],
        "k": PAGE_SCALE,
    }


def proposal_html(system: dict, ctx: dict) -> str:
    s = prepare(system)
    return _env.get_template("proposal.html").render(
        system=s, p=ctx, css=stylesheet(s["product"]["accent"]), icons=ICON_MARKUP, fonts_css=_embedded_fonts(),
    )


def load_example() -> dict:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "example.json"), encoding="utf-8") as fh:
        return json.load(fh)
