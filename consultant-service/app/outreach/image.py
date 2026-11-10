"""The report as one tall image, for a business to see right in an Instagram chat.

A stranger's link can read as spam, and Instagram DMs carry no files, so the
report Roy sends after the first reply is a picture. It says exactly what the
report page says, nothing more, and every word from the model is escaped.
Drawn once per business by the service's Chromium and kept beside its uploads.
"""
from __future__ import annotations

import base64
import logging
import os
from functools import lru_cache

from jinja2 import Environment, select_autoescape

from app.config import settings

logger = logging.getLogger("consultant.outreach")

_ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
WIDTH = 540  # CSS pixels; drawn at 2x, so 1080 wide, Instagram's own width

_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:Plex;src:url(data:font/ttf;base64,{{ fonts.regular }});font-weight:400}
@font-face{font-family:Plex;src:url(data:font/ttf;base64,{{ fonts.semibold }});font-weight:600}
@font-face{font-family:Plex;src:url(data:font/ttf;base64,{{ fonts.bold }});font-weight:700}
*{box-sizing:border-box;margin:0}
body{background:#fff;font-family:Plex,Arial,sans-serif;color:#10131a;-webkit-font-smoothing:antialiased}
.card{width:{{ width }}px;padding:34px 30px 30px;background:linear-gradient(#f3f6fb,#fff 220px)}
.brand{display:flex;align-items:center;gap:10px;font-weight:600;font-size:15px}
.brand img{width:30px;height:30px;border-radius:50%}
.for{margin-top:30px;color:#5d6675;font-size:13px}
h1{margin-top:8px;font-size:29px;line-height:1.12;font-weight:700;letter-spacing:-.01em}
h2{margin-top:26px;font-size:16px;font-weight:700}
p.today{margin-top:8px;font-size:15px;line-height:1.5;color:#2b3240}
.change{margin-top:12px;border:1px solid #dfe4ec;border-radius:6px;padding:14px 16px;background:#fff}
.change h3{font-size:16px;font-weight:700;line-height:1.3}
.row{margin-top:8px;font-size:13.5px;line-height:1.45;color:#2b3240}
.row b{display:block;font-size:11.5px;font-weight:600;color:#7a8394}
.foot{margin-top:24px;padding-top:14px;border-top:1px solid #dfe4ec;font-size:12.5px;line-height:1.5;color:#5d6675}
.foot strong{color:#10131a;font-weight:600}
</style></head><body><div class="card">
<div class="brand">{% if logo %}<img src="data:image/png;base64,{{ logo }}" alt="">{% endif %}Build My Version</div>
<p class="for">Made for {{ name }}, {{ city }}</p>
<h1>What AI could change for {{ name }}.</h1>
<h2>What we saw</h2>
<p class="today">{{ report.today }}</p>
<h2>What could change</h2>
{% for c in report.changes %}<div class="change"><h3>{{ c.change }}</h3>
<div class="row"><b>Who does it</b>{{ c.ai }}</div>
<div class="row"><b>What it does each day</b>{{ c.day_to_day }}</div>
<div class="row"><b>What is different for you</b>{{ c.difference }}</div></div>{% endfor %}
<div class="foot"><strong>Reply to this message</strong> to talk it through, or write to {{ email }}.<br>
{{ report.sources_note }} Made only from public information.</div>
</div></body></html>"""


def _b64(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except OSError:
        return ""


@lru_cache(maxsize=1)
def _assets() -> dict:
    fonts = os.path.join(_ASSETS, "fonts")
    return {"fonts": {"regular": _b64(os.path.join(fonts, "PlexSans.ttf")),
                      "semibold": _b64(os.path.join(fonts, "PlexSans-SemiBold.ttf")),
                      "bold": _b64(os.path.join(fonts, "PlexSans-Bold.ttf"))},
            "logo": _b64(os.path.join(_ASSETS, "logo-160.png"))}


_env = Environment(autoescape=select_autoescape(default=True, default_for_string=True))


def html(name: str, city: str, report: dict) -> str:
    """The image's page: the report, escaped, in the BMV look."""
    return _env.from_string(_TEMPLATE).render(name=name, city=city, report=report, width=WIDTH,
                                              email="consulting@buildmyversion.com", **_assets())


def draw(page_html: str) -> bytes | None:
    """The page as a PNG, 1080 wide, as tall as it needs. None without a browser."""
    from app.screens import browser

    if not browser.available():
        return None
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": WIDTH, "height": 900}, device_scale_factor=2)
            page.set_content(page_html, wait_until="load")
            png = page.locator(".card").screenshot(type="png")
            b.close()
            return png
    except Exception as exc:
        logger.warning("the report image could not be drawn: %s", str(exc)[:200])
        return None


def png_for(token: str, name: str, city: str, report: dict) -> bytes | None:
    """The business's image, drawn the first time it is asked for."""
    folder = os.path.join(settings.UPLOADS_DIR, "outreach")
    path = os.path.join(folder, f"{token}.png")
    if os.path.isfile(path):
        with open(path, "rb") as f:
            return f.read()
    png = draw(html(name, city, report))
    if png:
        os.makedirs(folder, exist_ok=True)
        with open(path, "wb") as f:
            f.write(png)
    return png
