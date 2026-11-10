"""Find businesses with the web-search model, keeping only what a cited page shows.

The model may name a business it cannot point to, so a business counts only when
the page it says it found it on is one the search itself cited, exactly as the
consultation's market figures are kept (`app/figures/references.confirm`). The
same business found twice under another spelling is one row.
"""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlsplit

from app.ai import provider
from app.config import settings
from app.models import Prospect
from app.outreach import new_token
from app.pipeline._shared import ask_until_usable, ledger, reply_json
from app.templating import render

logger = logging.getLogger("consultant.outreach")

_TOKENS = 3000
_HANDLE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
_SUFFIXES = {"llc", "l", "c", "fz", "fze", "fzco", "fzllc", "est", "co", "company", "trading", "the"}


def handle(raw: object) -> str | None:
    """An Instagram handle from "@x", "x" or an instagram.com address, else None."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    m = re.search(r"instagram\.com/([^/?#\s]+)", text, re.I)
    text = (m.group(1) if m else text).lstrip("@").strip()
    return text if _HANDLE.match(text) and text.lower() not in {"p", "reel", "explore", "accounts"} else None


def _domain(website: str | None) -> str | None:
    if not website:
        return None
    host = urlsplit(website if "//" in website else "https://" + website).hostname or ""
    host = host.lower().removeprefix("www.")
    return host or None


def _name_part(name: str, city: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if w not in _SUFFIXES]
    return "".join(words) + "|" + (city or "").lower().strip()


def keys(name: str, city: str, website: str | None, instagram: str | None) -> set[str]:
    """Every way this business could be recognised again."""
    out = {"name:" + _name_part(name, city)}
    if handle(instagram):
        out.add("ig:" + handle(instagram).lower())
    if _domain(website):
        out.add("web:" + _domain(website))
    return out


def dedup_key(name: str, city: str, website: str | None, instagram: str | None) -> str:
    """The one key a row is stored under: the handle, else the site, else the name."""
    if handle(instagram):
        return "ig:" + handle(instagram).lower()
    if _domain(website):
        return "web:" + _domain(website)
    return "name:" + _name_part(name, city)


def parse_found(body: dict) -> list[dict]:
    """The businesses in a search reply whose page the search itself cited."""
    message = body["choices"][0]["message"]
    cited = {a["url_citation"]["url"] for a in message.get("annotations") or []
             if a.get("type") == "url_citation" and isinstance(a.get("url_citation"), dict)}
    found = reply_json(body).get("found")
    out = []
    for item in found if isinstance(found, list) else []:
        if not isinstance(item, dict):
            continue
        name = " ".join(str(item.get("name") or "").split())[:200]
        source = str(item.get("source") or "").strip()
        if not name or source not in cited:
            continue
        website = str(item.get("website") or "").strip() or None
        if website and "instagram.com" in website:
            website = None
        facts = [" ".join(f.split())[:160] for f in item.get("facts") or [] if isinstance(f, str) and f.strip()][:4]
        what = "\n".join([" ".join(str(item.get("what") or "").split())[:300]] + [f"- {f}" for f in facts])
        out.append({"name": name, "website": website if website and website.startswith("http") else None,
                    "instagram": handle(item.get("instagram")) or (handle(source) if "instagram.com" in source else None),
                    "phone": str(item.get("phone") or "").strip()[:40] or None, "source": source, "what": what})
    return out


def find(db, city: str, kind: str, want: int) -> list[Prospect]:
    """New businesses of `kind` in `city`, saved as found. A failed search finds none."""
    prompt = render("outreach_find.j2", city=city, kind=kind, most=want)
    try:
        items = ask_until_usable(
            lambda: provider.chat(settings.RESEARCH_MODEL, [{"role": "user", "content": prompt}],
                                  max_tokens=_TOKENS, timeout=90.0),
            parse_found, ledger(db, None, model=settings.RESEARCH_MODEL, purpose="outreach:find"))
    except Exception as exc:
        logger.warning("outreach search failed for %s in %s: %s", kind, city, str(exc)[:200])
        return []
    seen: set[str] = set()
    for row in db.query(Prospect.name, Prospect.city, Prospect.website, Prospect.instagram, Prospect.key):
        seen |= keys(row.name, row.city, row.website, row.instagram) | {row.key}
    new = []
    for item in items:
        mine = keys(item["name"], city, item["website"], item["instagram"])
        if mine & seen:
            continue
        seen |= mine
        p = Prospect(token=new_token(), name=item["name"], city=city, kind=kind, website=item["website"],
                     instagram=item["instagram"], phone=item["phone"], what=item["what"],
                     key=dedup_key(item["name"], city, item["website"], item["instagram"]),
                     sources_json=json.dumps([{"url": item["source"], "what": "where the search found it"}]))
        db.add(p)
        new.append(p)
    db.commit()
    logger.info("outreach: %s new %s in %s", len(new), kind, city)
    return new
