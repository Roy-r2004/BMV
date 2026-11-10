"""Published figures from the live web, checked by code before they count.

A web-search model finds numbers that bear on the question: what competitors
charge, how big the market is, what things cost. A model can invent a source or
misquote a real one, so its word is not enough. Code opens each cited page and
confirms that the number is there, next to the words the model quoted, before a
`reference` figure exists. What cannot be confirmed is dropped, and a blocked or
unreadable page counts as unconfirmed.

The addresses come from a model, so fetching them is guarded: web addresses
only, public hosts only (every redirect is checked again, and so is the address
each connection actually reached), a size limit and a clock. The stage adds to a
run and never stops one.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlsplit

import httpx

from app.ai import provider
from app.config import settings
from app.figures.known import known_for, prompt_lines
from app.figures.model import Figure, Reference, as_json, from_json
from app.models import Request
from app.pipeline._shared import ask_until_usable, ledger, reply_json
from app.templating import render

logger = logging.getLogger("consultant.references")

PROGRESS = "Checking the market..."
_TOKENS = 2500
_MAX_BYTES = 2_000_000
_MAX_REDIRECTS = 3
_PAGE_SECONDS = 20.0
_ALL_PAGES_SECONDS = 60.0
_WINDOW = 200
_QUOTE_SHARE = 0.6
_MIN_QUOTE_WORDS = 3
_STALE = frozenset({"references", "sums", "answer", "registry", "roadmap", "register", "exhibits"})
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BuildMyVersionResearch/1.0)"}
_NOT_TEXT = frozenset({"script", "style", "noscript"})
_TAG_NAME = re.compile(r"[a-z0-9]+")


class Unreadable(Exception):
    """The page could not be fetched safely, or read."""


def _public(host: str) -> bool:
    """True only when every address the host resolves to is on the public internet."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0].split("%")[0]).is_global for i in infos)


def _allowed(url: str) -> bool:
    try:
        parts = urlsplit(url)
        parts.hostname  # a malformed address ("http://[x") raises here
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.hostname) and _public(parts.hostname)


def _reached_the_public_internet(response) -> bool:
    """Where this connection actually went. The name was checked before connecting,
    and a name can answer differently a moment later."""
    stream = response.extensions.get("network_stream")
    peer = stream.get_extra_info("server_addr") if stream else None
    if not peer or not peer[0]:
        return False
    return ipaddress.ip_address(peer[0].split("%")[0]).is_global


def _text(html: str) -> str:
    """The words of a page, lowercased. One pass that never goes back, because the
    markup comes from whoever owns the page and may be built to stall a reader."""
    page = html.lower()
    out: list[str] = []
    at = 0
    while True:
        opens = page.find("<", at)
        if opens < 0:
            out.append(page[at:])
            break
        out.append(page[at:opens])
        closes = page.find(">", opens)
        if closes < 0:
            out.append(page[opens:])
            break
        at = closes + 1
        name = _TAG_NAME.match(page, opens + 1, opens + 12)
        if name and name.group(0) in _NOT_TEXT:
            ends = page.find(f"</{name.group(0)}", at)
            if ends < 0:
                break
            at = ends
    return " ".join(" ".join(out).split())


def _fetch(url: str) -> str:
    """The page's text."""
    return _text(_fetch_html(url))


_HREF = re.compile(r"""href\s*=\s*["']?([^"'\s>]{1,500})""", re.I)


def links(html: str) -> list[str]:
    """The addresses a page links to, lowercased, at most 500 of them."""
    return [m.group(1).lower() for _, m in zip(range(500), _HREF.finditer(html or ""))]


def _fetch_html(url: str) -> str:
    """The page as it came. Redirects are followed by hand so each hop is checked."""
    deadline = time.monotonic() + _PAGE_SECONDS
    for _ in range(_MAX_REDIRECTS + 1):
        if not _allowed(url):
            raise Unreadable("not a public web address")
        try:
            with httpx.stream("GET", url, timeout=12.0, headers=_HEADERS, follow_redirects=False) as response:
                if not _reached_the_public_internet(response):
                    raise Unreadable("the connection did not reach a public address")
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                if response.status_code != 200 or "text" not in response.headers.get("content-type", "text"):
                    raise Unreadable(f"status {response.status_code}")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body += chunk
                    if time.monotonic() > deadline:
                        raise Unreadable("the page took too long")
                    if len(body) > _MAX_BYTES:
                        break
                return bytes(body).decode(response.encoding or "utf-8", errors="replace")
        except httpx.HTTPError as exc:
            raise Unreadable(str(exc)) from exc
    raise Unreadable("too many redirects")


def _digits_pattern(number: str) -> re.Pattern:
    whole, _, cents = number.partition(".")
    body = ",?".join(whole)
    if cents:
        body += r"\." + cents
    return re.compile(rf"(?<![\d.,]){body}(?!\d)")


def on_the_page(number: str, quote: str, page: str) -> bool:
    """The number is on the page, in the same place as the words the model quoted."""
    words = set(re.findall(r"[^\W\d_]{4,}", quote.lower()))
    if len(words) < _MIN_QUOTE_WORDS:
        return False
    lowered = page.lower()
    for found in _digits_pattern(number).finditer(lowered):
        window = lowered[max(0, found.start() - _WINDOW):found.end() + _WINDOW]
        if sum(1 for w in words if w in window) / len(words) >= _QUOTE_SHARE:
            return True
    return False


def _year(raw: object, today: int) -> int:
    return raw if isinstance(raw, int) and 1990 <= raw <= today else today


def confirm(found: object, cited: set[str]) -> list[Figure]:
    """The findings that survive: cited by the search itself, and read on the page."""
    out: list[Figure] = []
    now = datetime.now(timezone.utc)
    pages: dict[str, str | None] = {}
    time_up = time.monotonic() + _ALL_PAGES_SECONDS
    for item in found if isinstance(found, list) else []:
        if len(out) >= settings.REFERENCES_MAX:
            break
        try:
            url = str(item["url"]).strip()
            number = str(item["number"]).replace(",", "").strip()
            value = Decimal(number)
            quote = str(item["quote"])
        except (KeyError, TypeError, InvalidOperation):
            continue
        if url not in cited or not value.is_finite():
            logger.info("reference dropped: the search did not cite %s", url[:120])
            continue
        if url not in pages:
            if time.monotonic() > time_up:
                logger.info("references: out of time, stopped opening pages")
                break
            try:
                pages[url] = _fetch(url)
            except Unreadable as exc:
                logger.info("reference dropped: %s could not be read (%s)", url[:120], exc)
                pages[url] = None
        if pages[url] is None or not on_the_page(number, quote, pages[url]):
            logger.info("reference dropped: %s is not on %s", number, url[:120])
            continue
        publication = " ".join(str(item.get("publication") or urlsplit(url).hostname).split())[:80]
        source = Reference(publication=f"{publication}, read {now:%B %Y}", year=_year(item.get("year"), now.year),
                           population=" ".join(str(item.get("what") or "").split())[:120], url=url)
        out.append(Figure(f"REF-{len(out) + 1}", value, str(item.get("unit") or "").strip()[:20], item.get("period") or None,
                          "reference", source, max(0, -value.as_tuple().exponent)))
    return out


def load(req) -> list[Figure]:
    try:
        return [from_json(d) for d in json.loads(req.references_json)] if getattr(req, "references_json", None) else []
    except (TypeError, ValueError):
        return []


def as_claims(req) -> list[dict]:
    """The confirmed figures as claims a hypothesis can test against."""
    return [{"id": f.id, "value": float(f.value), "unit": f.unit, "time_basis": f.period or "as stated",
             "text": f.source.population, "source": f"published: {f.source.publication}", "provenance": "published"}
            for f in load(req)]


def write(db, request_id: int) -> None:
    """Search, confirm, store. A failure at any step means no references."""
    req = db.get(Request, request_id)
    if req is None:
        return
    req.references_json = None
    known = known_for(req, leave_out=_STALE)
    prompt = render("references.j2", main_problem=req.main_problem or "", question=req.desired_outcome or "",
                    description=(req.business_description or "")[:800], industry=req.industry or "",
                    figures_block=prompt_lines(known), most=settings.REFERENCES_MAX)
    cited: set[str] = set()

    def use(body: dict) -> dict:
        message = body["choices"][0]["message"]
        cited.update(a["url_citation"]["url"] for a in message.get("annotations") or [] if a.get("type") == "url_citation")
        return reply_json(body)

    try:
        reply = ask_until_usable(
            lambda: provider.chat(settings.RESEARCH_MODEL, [{"role": "user", "content": prompt}], max_tokens=_TOKENS, timeout=90.0),
            use, ledger(db, request_id, model=settings.RESEARCH_MODEL, purpose="references"))
        figures = confirm(reply.get("found"), cited)
    except Exception as exc:
        logger.warning("the market could not be checked: %s", str(exc)[:200])
        figures = []
    logger.info("request %s: %s published figures confirmed", request_id, len(figures))
    req.references_json = json.dumps([as_json(f) for f in figures]) if figures else None
    db.commit()
