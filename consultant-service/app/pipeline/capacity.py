"""The owner's capacity, drawn from what they told us — and only that.

A booking studio, a restaurant, a clinic, a van fleet and a bakery all sell
capacity: spots in a class, seats in a sitting, chairs in a day, vans on the
road, loaves out of an oven. When the diagnosis turns on it ("you're not short
of clients, you're full") the client should SEE it before they read it — so
this builds a picture of their week from their own answers.

Two shapes, because not every business runs on a timetable:

  weekly_grid — days x slots x units per slot, with how full a typical slot
                is and which slots sell out (a class schedule, sittings, shifts)
  total       — one pool: N units, M used, per period (orders a month, vans)

and `none` when they gave nothing capacity-shaped. The model only reads their
words into that structure; every number it returns is checked against what
they said (`figures.given`), every time against a time they named, every day
name against one they used. The arithmetic — totals, how many sold, what the
full slots hold — is done here, never by the model, and its working is kept
so the screen can show it.

Nothing is filled in. If they said "about 10 of 12" once, every ordinary slot
is drawn at about 10: we do not invent the Tuesday that ran at 8. If they did
not name their class times, the columns carry no times.
"""

import json
import logging
import math

from app.ai import provider
from app.config import settings
from app.pipeline import figures
from app.pipeline._shared import extract_json_from_text
from app.templating import render

logger = logging.getLogger("consultant.capacity")

SHAPES = ("weekly_grid", "total", "none")
MAX_DAYS = 7
MAX_SLOTS = 16
MAX_PER_SLOT = 400
#: A total pool is drawn one dot per unit up to this many dots; above it,
#: each dot stands for a round number of units, and the legend says so.
MAX_DOTS = 480
CAPACITY_TOKENS = 1500

_DAY_NAMES = {
    "mon": "Mon", "monday": "Mon", "tue": "Tue", "tues": "Tue", "tuesday": "Tue",
    "wed": "Wed", "wednesday": "Wed", "thu": "Thu", "thur": "Thu", "thurs": "Thu",
    "thursday": "Thu", "fri": "Fri", "friday": "Fri", "sat": "Sat", "saturday": "Sat",
    "sun": "Sun", "sunday": "Sun",
}
_FULL_DAYS = {"Mon": "monday", "Tue": "tuesday", "Wed": "wednesday", "Thu": "thursday",
              "Fri": "friday", "Sat": "saturday", "Sun": "sunday"}


def owner_texts(req) -> list[str]:
    """Everything the owner wrote, as the texts their numbers are checked in."""
    try:
        ops = json.loads(req.ops_numbers_json) if req.ops_numbers_json else []
    except (TypeError, ValueError):
        ops = []
    texts = [req.main_problem, req.business_description, req.desired_outcome, req.revenue_today]
    texts += [f"{p.get('question', '')}: {p.get('answer', '')}" for p in ops if isinstance(p, dict)]
    return [t for t in texts if t and str(t).strip()]


def _num(value, allowed) -> float | None:
    """The number if the owner said it, else None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if figures.holds(v, allowed) else None


def _clock(value, named_hours: set[int]) -> str | None:
    """'18:00' when the owner named that time in any spelling, else None."""
    hours = figures.times_in(str(value or ""))
    if not hours:
        return None
    h = hours[0]
    if h not in named_hours:
        return None
    minutes = str(value).split(":")[1][:2] if ":" in str(value) else "00"
    return f"{h:02d}:{minutes if minutes.isdigit() else '00'}"


def _day(value, texts_lower: str) -> str | None:
    key = str(value or "").strip().lower().rstrip(".")
    short = _DAY_NAMES.get(key)
    if not short:
        return None
    # Named by them, in full or abbreviated. "Monday to Saturday" names both ends,
    # which is enough to name the ones between.
    if _FULL_DAYS[short] in texts_lower or f"{short.lower()} " in texts_lower:
        return short
    return None


def _day_range(texts_lower: str) -> list[str] | None:
    order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for a in order:
        for b in order:
            if a == b:
                continue
            for sep in (" to ", " through ", "-", " - ", "–"):
                if f"{_FULL_DAYS[a]}{sep}{_FULL_DAYS[b]}" in texts_lower:
                    i, j = order.index(a), order.index(b)
                    return order[i:j + 1] if i < j else None
    return None


def _dot_scale(units: float) -> int:
    if units <= MAX_DOTS:
        return 1
    raw = units / MAX_DOTS
    for step in (2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if step >= raw:
            return step
    return int(math.ceil(raw))


def say_time(t: str) -> str:
    """'18:00' -> '6pm', '09:30' -> '9:30am' — how an owner says it."""
    try:
        h, m = (int(x) for x in t.split(":"))
    except (ValueError, AttributeError):
        return str(t)
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}{suffix}" if m == 0 else f"{h12}:{m:02d}{suffix}"


def _fmt(v: float) -> str:
    return f"{int(v):,}" if float(v).is_integer() else f"{v:,.1f}"


def shape(raw: dict, texts: list[str]) -> dict | None:
    """Turn the model's reading into a verified picture, or None.

    Pure: no model, no database — so it is testable against any reading,
    including the dishonest ones.
    """
    if not isinstance(raw, dict):
        return None
    kind = raw.get("shape")
    if kind not in SHAPES or kind == "none":
        return None
    allowed = figures.given(texts)
    named_hours = {h for t in texts for h in figures.times_in(t)}
    lower = " ".join(texts).lower()

    unit = str(raw.get("unit") or "").strip()[:40] or "spot"
    unit_plural = str(raw.get("unit_plural") or "").strip()[:40] or f"{unit}s"
    quote = str(raw.get("quote") or "").strip()
    quote = quote[:300] if quote and figures.quoted(quote, texts) else ""

    if kind == "total":
        cap = _num(raw.get("total_capacity"), allowed)
        taken = _num(raw.get("total_taken"), allowed)
        if not cap or cap <= 0 or (taken is not None and taken > cap):
            return None
        period = str(raw.get("period") or "").strip().lower()
        period = period if period in ("day", "week", "month", "year") else "week"
        scale = _dot_scale(cap)
        derived = [{"key": "CAP-01", "value": cap, "label": f"{unit_plural} a {period}", "working": "as you told us"}]
        if taken is not None:
            derived.append({"key": "CAP-02", "value": taken, "label": f"{unit_plural} used a {period}",
                            "working": "as you told us"})
            derived.append({"key": "CAP-03", "value": cap - taken, "label": f"{unit_plural} unused a {period}",
                            "working": f"{_fmt(cap)} − {_fmt(taken)}"})
        return {
            "shape": "total", "unit": unit, "unit_plural": unit_plural, "period": period,
            "capacity": cap, "taken": taken, "dot_scale": scale,
            "pct": round(100 * taken / cap) if taken is not None else None,
            "derived": derived, "quote": quote,
            "basis": [f"{_fmt(cap)} {unit_plural} a {period}"]
                     + ([f"{_fmt(taken)} used"] if taken is not None else []),
        }

    per_slot = _num(raw.get("per_slot"), allowed)
    slots = _num(raw.get("slots_per_day"), allowed)
    days = _num(raw.get("days_per_week"), allowed)
    if not per_slot or not slots or not days:
        return None
    if not (1 <= days <= MAX_DAYS and 1 <= slots <= MAX_SLOTS and 1 <= per_slot <= MAX_PER_SLOT):
        return None
    if not (float(days).is_integer() and float(slots).is_integer() and float(per_slot).is_integer()):
        return None
    days, slots, per_slot = int(days), int(slots), int(per_slot)
    typical = _num(raw.get("typical_taken"), allowed)
    if typical is not None and not (0 <= typical <= per_slot):
        typical = None

    # Times: only ones they named, in the column the model put them in. A
    # schedule of six with two named is drawn as four unnamed columns and two
    # named ones — not as six invented times.
    raw_times = list(raw.get("slot_times") or [])[:slots]
    raw_times += [None] * (slots - len(raw_times))
    times = [_clock(t, named_hours) if t else None for t in raw_times]
    seen, deduped = set(), []
    for t in times:
        deduped.append(t if t and t not in seen else None)
        if t:
            seen.add(t)
    times = deduped
    named = [t for t in times if t]
    if named != sorted(named):
        # Columns read left to right through the day; a model that put 19:00
        # before 18:00 has scrambled which column is which.
        times = [None] * (slots - len(named)) + sorted(named)

    full = {_clock(t, named_hours) for t in (raw.get("full_slots") or [])} - {None}
    full = {t for t in full if t in times}
    waitlist = bool(raw.get("waitlist")) and bool(full)
    waitlist_size = _num(raw.get("waitlist_size"), allowed) if waitlist else None
    if waitlist_size is not None and not (1 <= waitlist_size <= per_slot * 3):
        waitlist_size = None

    day_labels = None
    names = [_day(d, lower) for d in (raw.get("day_names") or [])]
    if names and all(names) and len(names) == days:
        day_labels = names
    if day_labels is None:
        rng = _day_range(lower)
        if rng and len(rng) == days:
            day_labels = rng
    labels_given = day_labels is not None
    if day_labels is None:
        day_labels = [f"Day {i + 1}" for i in range(days)]

    grid = []
    for d in day_labels:
        row = []
        for t in times:
            is_full = bool(t and t in full)
            taken = per_slot if is_full else typical
            row.append({"time": t, "capacity": per_slot, "taken": taken, "full": is_full,
                        "waitlist": (int(waitlist_size) if waitlist_size else "unknown") if (is_full and waitlist) else None})
        grid.append({"day": d, "slots": row})

    total = per_slot * slots * days
    full_count = sum(1 for t in times if t and t in full)
    full_spots = per_slot * full_count * days
    derived = [
        {"key": "CAP-01", "value": total, "label": f"{unit_plural} a week",
         "working": f"{per_slot} × {slots} a day × {days} days"},
        {"key": "CAP-02", "value": slots * days, "label": "slots a week",
         "working": f"{slots} a day × {days} days"},
    ]
    taken_total = None
    if typical is not None:
        taken_total = typical * (slots - full_count) * days + full_spots
        working = (f"{_fmt(typical)} × {slots - full_count} ordinary slots × {days} days"
                   + (f" + {per_slot} × {full_count} full slots × {days} days" if full_count else ""))
        derived.append({"key": "CAP-03", "value": taken_total, "label": f"{unit_plural} taken a week",
                        "working": working})
        derived.append({"key": "CAP-04", "value": total - taken_total, "label": f"{unit_plural} empty a week",
                        "working": f"{_fmt(total)} − {_fmt(taken_total)}"})
    if full_count:
        derived.append({"key": "CAP-05", "value": full_spots, "label": f"{unit_plural} a week in the slots that sell out",
                        "working": f"{per_slot} × {full_count} × {days} days"})

    basis = [f"{per_slot} {unit_plural} a slot", f"{slots} slots a day", f"{days} days a week"]
    if typical is not None:
        basis.append(f"about {_fmt(typical)} of {per_slot} in a typical slot")
    if full:
        basis.append(f"{' and '.join(say_time(t) for t in sorted(full))} sell out"
                     + (" with a waiting list" if waitlist else ""))

    return {
        "shape": "weekly_grid", "unit": unit, "unit_plural": unit_plural,
        "slot_noun": str(raw.get("slot_noun") or "slot").strip()[:24] or "slot",
        "per_slot": per_slot, "slots_per_day": slots, "days_per_week": days,
        "days_named": labels_given, "times": times, "typical_taken": typical,
        "full": sorted(full), "waitlist": waitlist, "waitlist_size": waitlist_size,
        "grid": grid, "capacity": total, "taken": taken_total,
        "pct": round(100 * taken_total / total) if taken_total is not None else None,
        "derived": derived, "quote": quote, "basis": basis,
    }


def read(texts: list[str], stage: str = "operating") -> tuple[dict | None, dict | None, str | None]:
    """One model call and the verification. Returns (picture, usage, error).

    Never raises and never touches a database: it is called from the
    interview (before any engagement exists) as well as from the pipeline.
    """
    if not texts:
        return None, None, None
    try:
        prompt = render("capacity.j2", owner_words="\n".join(f"- {t}" for t in texts),
                        stage=stage)
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}],
                             max_tokens=CAPACITY_TOKENS)
        raw = extract_json_from_text(body["choices"][0]["message"]["content"])
        return shape(raw, texts), body.get("usage"), None
    except Exception as exc:
        logger.warning("capacity could not be read: %s", str(exc)[:200])
        return None, None, str(exc)[:500]


def as_claims(picture: dict | None) -> list[dict]:
    """The computed figures as claims a hypothesis can cite, marked computed.

    The diagnosis used to have "12 reformers" and "six classes a day" and was
    left to multiply them itself — and the tester, told to combine figures,
    often did not. Handing it the product, with its working, means a
    conclusion like "you are at your ceiling" can rest on a number.
    """
    out = []
    for d in (picture or {}).get("derived") or []:
        out.append({"id": d["key"], "value": d["value"], "unit": picture.get("unit_plural") or "units",
                    "time_basis": "week" if picture.get("shape") == "weekly_grid" else picture.get("period", "as stated"),
                    "text": f"{_fmt(d['value'])} {d['label']} ({d['working']})",
                    "source": "computed from their figures", "provenance": "machine_computed"})
    return out


def load(req) -> dict | None:
    try:
        return json.loads(req.capacity_json) if getattr(req, "capacity_json", None) else None
    except (TypeError, ValueError):
        return None
