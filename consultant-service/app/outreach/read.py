"""Read a business's own website and score what it shows, and nothing else.

Every point in a score is a sign read on the page, or the plain fact that no
page could be read, and each reason is shown to Roy word for word. The fetch is
the consultation's guarded one: public addresses only, size and time limits.
"""
from __future__ import annotations

import json
import logging
import re

from app.config import settings
from app.figures import references
from app.models import Prospect
from app.outreach.find import handle

logger = logging.getLogger("consultant.outreach")

SITE_TEXT_MAX = 20_000
_PLATFORMS = ("fresha", "booksy", "calendly", "setmore", "simplybook", "vagaro", "mindbody", "opentable",
              "sevenrooms", "quandoo", "eatapp", "eat app", "practo", "okadoc", "zenoti", "square.site/book")
_BOOK_ONLINE = re.compile(r"\bbook (?:online|now)\b|\bonline booking\b|\bbook an appointment online\b")
_BY_MESSAGE = re.compile(r"\bdm\b|\bdirect message\b|\bwhatsapp\b|wa\.me/|\bcall (?:us )?to book\b|\bmessage us to book\b")
_WHATSAPP = re.compile(r"\bwhatsapp\b|wa\.me/")
_INSTAGRAM = re.compile(r"instagram\.com/([a-z0-9._]{1,30})")

REASONS = {
    "no_site": "No website was found",
    "unreadable": "Its website could not be read automatically",
    "no_online": "No way to book online on the website",
    "by_message": "Bookings are taken by message or phone",
    "whatsapp": "Customers are sent to WhatsApp",
}


def signals(text: str | None, site: str = "read", quoted: str = "", hrefs: list[str] | None = None) -> dict:
    """What the page and the search's quoted facts show, as plain yes/no facts.
    `site` is "read", "unreadable" (a site exists that we could not read) or
    "none" (no site was found); only "none" may ever be called missing."""
    page = (text or "").lower()
    linked = " ".join(hrefs or [])
    seen = page + "\n" + linked + "\n" + (quoted or "").lower()
    found = _INSTAGRAM.search(linked + " " + page)
    return {
        "site": site,
        "has_site": bool(page.strip()),
        "books_online": any(p in page or p in linked for p in _PLATFORMS) or bool(_BOOK_ONLINE.search(page)),
        "books_by_message": bool(_BY_MESSAGE.search(seen)),
        "shows_whatsapp": bool(_WHATSAPP.search(seen)),
        "instagram": handle(found.group(1)) if found else None,
    }


def score(sig: dict) -> tuple[int, list[str]]:
    """How much the business would gain, and why, from the signals alone."""
    if sig.get("books_online"):
        return 0, []
    site = sig.get("site") or ("read" if sig.get("has_site") else "none")
    if site == "none":
        points, why = 40, [REASONS["no_site"]]
    elif site == "unreadable":
        points, why = 20, [REASONS["unreadable"]]
    else:
        points, why = 30, [REASONS["no_online"]]
    if sig.get("books_by_message"):
        points, why = points + 30, why + [REASONS["by_message"]]
    if sig.get("shows_whatsapp"):
        points, why = points + 10, why + [REASONS["whatsapp"]]
    return points, why


def read(db, p: Prospect) -> Prospect:
    """Fetch the site, keep what it said, score it, and mark it ready or skipped."""
    text, site, hrefs = None, "none", []
    if p.website:
        try:
            html = references._fetch_html(p.website)
            text, hrefs = references._text(html)[:SITE_TEXT_MAX], references.links(html)
            site = "read" if text.strip() else "unreadable"
        except (references.Unreadable, ValueError) as exc:
            site = "unreadable"
            logger.info("outreach: %s could not be read (%s)", p.website[:120], exc)
    sig = signals(text, site, p.what or "", hrefs)
    points, why = score(sig)
    p.site_text = text
    p.signals_json = json.dumps(sig)
    p.score, p.reasons_json = points, json.dumps(why)
    if not p.instagram and sig["instagram"]:
        p.instagram = sig["instagram"]
    if text:
        sources = json.loads(p.sources_json or "[]")
        if not any(s.get("url") == p.website for s in sources):
            sources.append({"url": p.website, "what": "its website"})
        p.sources_json = json.dumps(sources)
    p.status = "ready" if points >= settings.OUTREACH_MIN_SCORE else "skip"
    db.commit()
    return p
