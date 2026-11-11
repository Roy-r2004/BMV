"""Write a business its report and DM, and refuse anything that was not read.

The model sees only what was read about the business: its name, city, kind,
what the search said it does, its own website's text, and why it was picked.
Code then refuses a draft carrying a number that was not in that text, any
claim about BMV's past work or results, or a DM without its link. A refused
draft is asked for once more with the reasons; refused again, the business is
skipped. A business never gets a report that says something it did not say.
"""
from __future__ import annotations

import json
import logging
import re

from app.ai import provider
from app.config import settings
from app.models import Prospect
from app.pipeline._shared import ask_until_usable, ledger, reply_json
from app.templating import render

logger = logging.getLogger("consultant.outreach")

_TOKENS = 2000
SITE_FOR_PROMPT = 6000
DM_MAX = 400
FOLLOWUP_MAX = 300
_URL = re.compile(r"https?://|www\.|\{link\}", re.I)
COULD_NOT = "The draft could not be written from what was read"
_NUMBER = re.compile(r"(?<![\d.])\d[\d,]*(?:\.\d+)?")
_WORDS = ("two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
          "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
          "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "hundreds", "thousand", "thousands",
          "dozen", "dozens")
_SCALE = re.compile(r"\b(?:half|halve|halves|halving|double|doubles|doubling|twice|triple|triples|tripling|"
                    r"quadruple|tenfold)\b", re.I)
_UNITS = (r"(?:minutes?|hours?|days?|weeks?|months?|years?|bookings?|customers?|clients?|patients?|calls?|"
          r"messages?|aed|dirhams?|riyals?|dollars?|people|staff|times)")
_WORD_NUMBER = re.compile(rf"\b({'|'.join(_WORDS)})\s+(?:\w+\s+)?{_UNITS}\b", re.I)
_CLAIMS = re.compile(r"\bwe(?:'ve| have)? (?:helped|worked with|built for|done this for)\b|\bour clients\b|"
                     r"\bclients like you\b|\bcase stud(?:y|ies)\b|\bguarantee|\bincrease your revenue by\b|"
                     r"\btrusted by\b", re.I)
_LOSING = re.compile(r"\b(?:may|might|could) be (?:missing|losing)\b|\bare (?:missing|losing) (?:out|bookings|customers)\b",
                     re.I)
_CHANGE_KEYS = ("change", "ai", "day_to_day", "difference")
CHAT_TURNS = (4, 6)
_GUESS = re.compile(r"\b(?:likely|perhaps|probably|presumably|might be|we assume|it seems|seemingly)\b", re.I)


def _numbers(text: str) -> set[str]:
    return {m.group(0).replace(",", "").rstrip(".") for m in _NUMBER.finditer(text or "")}


def _texts(report: dict, dm: str) -> list[str]:
    out = [dm or ""]
    for value in (report or {}).values():
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, list):
            out += [str(v) for item in value if isinstance(item, dict) for v in item.values()]
    return out


def problems(report: dict, dm: str, read_text: str, followup: str = "") -> list[str]:
    """Why a draft cannot go out; empty when it can."""
    found: list[str] = []
    if not isinstance(report, dict) or not isinstance(report.get("today"), str) or not report.get("today", "").strip():
        found.append("The report needs 'today': what the business does now, as read.")
    changes = report.get("changes") if isinstance(report, dict) else None
    if not isinstance(changes, list) or not 2 <= len(changes) <= 3 or not all(
            isinstance(c, dict) and all(str(c.get(k) or "").strip() for k in _CHANGE_KEYS) for c in changes):
        found.append("The report needs two or three changes, each with change, ai, day_to_day and difference.")
    if not isinstance(report, dict) or not str(report.get("sources_note") or "").strip():
        found.append("The report needs 'sources_note': what it was read from.")
    if not isinstance(report, dict) or not str(report.get("noticed") or "").strip():
        found.append("The report needs 'noticed': the most specific thing we saw about them.")
    chat = report.get("chat") if isinstance(report, dict) else None
    if not isinstance(chat, list) or not CHAT_TURNS[0] <= len(chat) <= CHAT_TURNS[1] or not all(
            isinstance(t, dict) and t.get("from") in ("customer", "assistant") and str(t.get("text") or "").strip()
            for t in chat) or chat[0].get("from") != "customer":
        found.append("The report needs 'chat': four to six turns, each from the customer or the assistant, "
                     "the customer first.")
    if not isinstance(dm, str) or not dm.strip():
        found.append("The first message is missing.")
    else:
        if _URL.search(dm):
            found.append("The first message must carry no link: a stranger's link reads as spam.")
        if not dm.rstrip().endswith("?"):
            found.append("The first message must end by asking whether they want the breakdown.")
        if len(dm) > DM_MAX:
            found.append(f"The first message must be under {DM_MAX} characters.")
    if not isinstance(followup, str) or "{link}" not in followup:
        found.append("The follow-up must contain {link}.")
    elif len(followup) > FOLLOWUP_MAX:
        found.append(f"The follow-up must be under {FOLLOWUP_MAX} characters.")
    read = (read_text or "").lower()
    allowed = _numbers(read)
    for text in _texts(report if isinstance(report, dict) else {}, dm if isinstance(dm, str) else "") + \
            [followup if isinstance(followup, str) else ""]:
        clean = text.replace("{link}", "").replace("\u2019", "'").replace("\u2018", "'")
        for n in _numbers(clean) - allowed:
            found.append(f"The number {n} was not in anything we read about them. Remove it.")
        for m in _WORD_NUMBER.finditer(clean):
            if m.group(0).lower() not in read:
                found.append(f"'{m.group(0)}' was not in anything we read about them. Remove it.")
        for m in _CLAIMS.finditer(clean):
            found.append(f"'{m.group(0)}' claims past work or results we cannot show. Remove it.")
        for m in _GUESS.finditer(clean):
            found.append(f"'{m.group(0)}' is a guess. Say only what was read, or leave it out.")
        for m in list(_SCALE.finditer(clean)) + list(_LOSING.finditer(clean)):
            if m.group(0).lower() not in read:
                found.append(f"'{m.group(0)}' claims an amount or a loss nobody measured. Remove it.")
    return list(dict.fromkeys(found))


def _read_text(p: Prospect) -> str:
    return " ".join(x for x in (p.name, p.city, p.what, p.site_text) if x)


def write(db, p: Prospect) -> Prospect:
    """The report and DM for one business, or the business skipped."""
    base = render("outreach_report.j2", name=p.name, city=p.city, kind=p.kind, what=p.what or "",
                  site_text=(p.site_text or "")[:SITE_FOR_PROMPT], reasons=json.loads(p.reasons_json or "[]"),
                  site=json.loads(p.signals_json or "{}").get("site") or ("read" if p.site_text else "none"))
    feedback = ""
    for _ in range(2):
        prompt = base + (("\n\nYOUR LAST DRAFT WAS REFUSED FOR THESE REASONS. Fix exactly these:\n" + feedback)
                         if feedback else "")
        try:
            draft = ask_until_usable(
                lambda prompt=prompt: provider.chat(settings.REASONING_MODEL, [{"role": "user", "content": prompt}],
                                                    max_tokens=_TOKENS),
                reply_json, ledger(db, None, model=settings.REASONING_MODEL, purpose="outreach:write"))
        except Exception as exc:
            # the model could not be reached: nothing was refused, so the
            # business waits for the next run instead of being skipped
            logger.warning("outreach: no draft for %s: %s", p.name[:80], str(exc)[:200])
            return p
        report, dm = draft.get("report"), str(draft.get("dm") or "").strip()
        followup = str(draft.get("followup") or "").strip()
        found = problems(report, dm, _read_text(p), followup)
        if not found:
            p.report_json, p.dm_text, p.followup_text = json.dumps(report), dm, followup
            db.commit()
            return p
        feedback = "\n".join(f"- {f}" for f in found)
    reasons = json.loads(p.reasons_json or "[]")
    p.reasons_json = json.dumps(reasons + [COULD_NOT])
    p.status = "skip"
    db.commit()
    return p
