"""The report as a few portrait slides, sent together as one swipeable set.

Instagram shows a 4:5 picture full screen without shrinking it, so each slide
is 1080 x 1350 and readable without zooming: a cover with what we saw, one
slide per change, and a closing slide. They say exactly what the report page
says, nothing more, and every word from the model is escaped. Drawn once per
business by the service's Chromium and kept beside its uploads.
"""
from __future__ import annotations

import base64
import glob
import logging
import os
from functools import lru_cache

from jinja2 import Environment, select_autoescape

from app.config import settings

logger = logging.getLogger("consultant.outreach")

_ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
WIDTH, HEIGHT = 540, 675  # CSS pixels; drawn at 2x, so 1080 x 1350, Instagram's portrait size

_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:Plex;src:url(data:font/ttf;base64,{{ fonts.regular }});font-weight:400}
@font-face{font-family:Plex;src:url(data:font/ttf;base64,{{ fonts.semibold }});font-weight:600}
@font-face{font-family:Plex;src:url(data:font/ttf;base64,{{ fonts.bold }});font-weight:700}
*{box-sizing:border-box;margin:0}
body{background:#fff;font-family:Plex,Arial,sans-serif;color:#10131a;-webkit-font-smoothing:antialiased}
.slide{width:{{ width }}px;min-height:{{ height }}px;padding:38px 36px 34px;display:flex;flex-direction:column;
  background:linear-gradient(#f3f6fb,#fff 260px)}
.brand{display:flex;align-items:center;gap:10px;font-weight:600;font-size:15px}
.brand img{width:30px;height:30px;border-radius:50%}
.brand .n{margin-left:auto;color:#7a8394;font-weight:400;font-size:13px}
.body{flex:1;display:flex;flex-direction:column;justify-content:center;padding:18px 0}
.for{color:#5d6675;font-size:14px}
h1{margin-top:10px;font-size:34px;line-height:1.1;font-weight:700;letter-spacing:-.01em}
h2{font-size:30px;line-height:1.15;font-weight:700;letter-spacing:-.01em}
.label{margin-top:26px;font-size:13px;font-weight:600;color:#7a8394}
.text{margin-top:6px;font-size:18px;line-height:1.5;color:#2b3240}
.row{margin-top:20px}
.row b{display:block;font-size:13px;font-weight:600;color:#7a8394}
.row span{display:block;margin-top:4px;font-size:18px;line-height:1.45;color:#2b3240}
.foot{font-size:13px;color:#7a8394;line-height:1.5}
</style></head><body>
{% set total = report.changes|length + 2 %}
<div class="slide"><div class="brand">{{ logo_tag }}Build My Version<span class="n">1 / {{ total }}</span></div>
<div class="body"><p class="for">Made for {{ name }}, {{ city }}</p>
<h1>What AI could change for {{ name }}.</h1>
<p class="label">What we saw</p><p class="text">{{ report.today }}</p></div>
<p class="foot">{{ report.sources_note }}</p></div>
{% for c in report.changes %}
<div class="slide"><div class="brand">{{ logo_tag }}Build My Version<span class="n">{{ loop.index + 1 }} / {{ total }}</span></div>
<div class="body"><p class="for">Change {{ loop.index }} of {{ report.changes|length }}</p>
<h2 style="margin-top:10px">{{ c.change }}</h2>
<div class="row"><b>Who does it</b><span>{{ c.ai }}</span></div>
<div class="row"><b>What it does each day</b><span>{{ c.day_to_day }}</span></div>
<div class="row"><b>What is different for you</b><span>{{ c.difference }}</span></div></div></div>
{% endfor %}
<div class="slide"><div class="brand">{{ logo_tag }}Build My Version<span class="n">{{ total }} / {{ total }}</span></div>
<div class="body"><h2>Want to talk it through?</h2>
<p class="text" style="margin-top:16px">Reply to this message, or write to {{ email }}.</p></div>
<p class="foot">Made only from public information.</p></div>
</body></html>"""


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


def count(report: dict) -> int:
    """How many slides the report makes: a cover, one per change, a close."""
    changes = report.get("changes") if isinstance(report, dict) else None
    return len(changes) + 2 if isinstance(changes, list) else 0


def html(name: str, city: str, report: dict) -> str:
    """The slides' page: the report, escaped, in the BMV look."""
    from markupsafe import Markup

    a = _assets()
    logo_tag = Markup(f'<img src="data:image/png;base64,{a["logo"]}" alt="">') if a["logo"] else ""
    return _env.from_string(_TEMPLATE).render(name=name, city=city, report=report, width=WIDTH, height=HEIGHT,
                                              email="consulting@buildmyversion.com", fonts=a["fonts"],
                                              logo_tag=logo_tag)


def draw(page_html: str) -> list[bytes] | None:
    """Each slide as a PNG, 1080 x 1350. None without a browser."""
    from app.screens import browser

    if not browser.available():
        return None
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=2)
            page.set_content(page_html, wait_until="load")
            slides = page.locator(".slide")
            pngs = [slides.nth(i).screenshot(type="png") for i in range(slides.count())]
            b.close()
            return pngs or None
    except Exception as exc:
        logger.warning("the report slides could not be drawn: %s", str(exc)[:200])
        return None


def _folder() -> str:
    return os.path.join(settings.UPLOADS_DIR, "outreach")


def slides_for(token: str, name: str, city: str, report: dict) -> list[bytes] | None:
    """The business's slides, drawn the first time they are asked for."""
    n = count(report)
    paths = [os.path.join(_folder(), f"{token}-{i}.png") for i in range(1, n + 1)]
    if n and all(os.path.isfile(p) for p in paths):
        out = []
        for path in paths:
            with open(path, "rb") as f:
                out.append(f.read())
        return out
    pngs = draw(html(name, city, report))
    if pngs:
        os.makedirs(_folder(), exist_ok=True)
        for i, png in enumerate(pngs, start=1):
            with open(os.path.join(_folder(), f"{token}-{i}.png"), "wb") as f:
                f.write(png)
    return pngs


def forget(token: str) -> None:
    """Delete a business's drawn slides, when its details are forgotten."""
    for path in glob.glob(os.path.join(_folder(), glob.escape(token) + "*.png")):
        try:
            os.remove(path)
        except OSError:
            pass
