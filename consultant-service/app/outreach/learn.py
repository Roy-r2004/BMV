"""Learn what makes one business itself, before its report is written.

The search that found it gave a line or two; a report built on that reads like
it could be for anyone. One cited web search per business collects its named
services, what its customers say, and what sets it apart. Only facts from a page
the search itself cited are kept. They join what was read about the business,
so the writer may use them and the number check allows them, and nothing else.
"""
from __future__ import annotations

import json
import logging

from app.ai import provider
from app.config import settings
from app.models import Prospect
from app.pipeline._shared import ask_until_usable, ledger, reply_json
from app.templating import render

logger = logging.getLogger("consultant.outreach")

LEARNED = "what we learned about it"
MOST = 8
_TOKENS = 1500


def parse_facts(body: dict) -> list[dict]:
    """The facts in a search reply whose page the search itself cited."""
    message = body["choices"][0]["message"]
    cited = {a["url_citation"]["url"] for a in message.get("annotations") or []
             if a.get("type") == "url_citation" and isinstance(a.get("url_citation"), dict)}
    facts = reply_json(body).get("facts")
    out = []
    for item in facts if isinstance(facts, list) else []:
        if not isinstance(item, dict):
            continue
        fact = " ".join(str(item.get("fact") or "").split())[:240]
        source = str(item.get("source") or "").strip()
        if fact and source in cited:
            out.append({"fact": fact, "source": source})
    return out[:MOST]


def learned(p: Prospect) -> bool:
    return any(s.get("what") == LEARNED for s in json.loads(p.sources_json or "[]"))


def learn(db, p: Prospect) -> Prospect:
    """Add what public pages say about the business to what was read. Once per
    business, even when the search found nothing; a search that could not be
    done leaves it as it was, to be written anyway."""
    if learned(p):
        return p
    prompt = render("outreach_learn.j2", name=p.name, kind=p.kind, city=p.city, website=p.website,
                    instagram=p.instagram, phone=p.phone)
    try:
        facts = ask_until_usable(
            lambda: provider.chat(settings.RESEARCH_MODEL, [{"role": "user", "content": prompt}],
                                  max_tokens=_TOKENS, timeout=90.0),
            parse_facts, ledger(db, None, model=settings.RESEARCH_MODEL, purpose="outreach:learn"))
    except Exception as exc:
        # not reached: tried again on the next run; the report is written now without it
        logger.warning("outreach: nothing learned about %s: %s", p.name[:80], str(exc)[:200])
        return p
    sources = json.loads(p.sources_json or "[]")
    known = {s.get("url") for s in sources}
    if facts:
        p.what = (p.what or "").rstrip() + "\nMore from public pages about it:\n" + \
            "\n".join(f"- {f['fact']}" for f in facts)
    sources += [{"url": u, "what": LEARNED} for u in dict.fromkeys(f["source"] for f in facts) if u not in known]
    if not any(s.get("what") == LEARNED for s in sources):
        sources.append({"url": "", "what": LEARNED})
    p.sources_json = json.dumps(sources)
    db.commit()
    return p
