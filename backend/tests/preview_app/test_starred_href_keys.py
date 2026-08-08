r"""`primaryHref` is an href. Nothing in the pipeline could see one.

Session 27's three completed runs each shipped two dead call-to-action targets,
written by the mock writer into `seed.cta`:

    153  primaryHref "/reserve"   secondaryHref "/order"
    156  primaryHref "/shop"      secondaryHref "/alerts"
    157  primaryHref "/gallery"                           <- on a hardware store

Not one of the five distinct paths is a declared route. All six occurrences were
reported as `dead_link_occurrences: 0`, and the dead-link *repair* — which walks
`src/data/mock.ts` along with every other file — left every one of them in place.

One cause, in two files. Both patterns anchored the key as
`(?<![\w-])["']?(?:href|defaultPath)["']?`: in `primaryHref` the `href` has a
word character in front of it, so the lookbehind refuses it, and the quoted-key
arm cannot match `"primaryHref"` either. The key is now `\w*[Hh]ref`, kept
byte-identical between `capabilities/journey.py::_LINK_KEYS` and
`safety/dead_links.py::_HREF_RE` — a repair that cannot see what the gate reports
is the shape of this whole defect.

The second half is where such a link should go. Rung 4 grounded a standalone
object value to `/`, which is the catch-all disguise `dead_links`' own docstring
argues against; a "Get started" button belongs on the page the business converts
on, resolved from the route table like every other target in this pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.capabilities.journey import (  # noqa: E402
    internal_hrefs,
)
from app.application.preview_app.safety.dead_links import (  # noqa: E402
    repair_dead_links,
    repair_file_dead_links,
)
from tests.preview_app.real_route_records import architect  # noqa: E402

#: The `seed.cta` blocks the mock writer produced, verbatim from
#: `bmv-api:/app/data/preview-apps/<id>/src/data/mock.ts`.
SHIPPED_CTA = {
    153: ("/reserve", "/order"),
    156: ("/shop", "/alerts"),
    157: ("/gallery", None),
}


def _mock_with_cta(primary: str, secondary: str | None) -> str:
    lines = [
        "export const seed = {",
        '  "cta": {',
        '    "heading": "Ready to start?",',
        f'    "primaryLabel": "Get started",',
        f'    "primaryHref": "{primary}",',
    ]
    if secondary:
        lines.append(f'    "secondaryHref": "{secondary}",')
    lines += ["  },", "};", ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# the sweep can see them


@pytest.mark.parametrize("request_id", sorted(SHIPPED_CTA))
def test_the_sweep_reads_a_starred_href_key(request_id: int) -> None:
    primary, secondary = SHIPPED_CTA[request_id]
    found = internal_hrefs(_mock_with_cta(primary, secondary))
    assert primary in found
    if secondary:
        assert secondary in found


def test_a_plain_href_still_reads_the_same() -> None:
    """The widening must not cost the keys that already worked."""
    source = 'const nav = [{ "href": "/gallery" }, { href: "/book" }];\n'
    assert set(internal_hrefs(source)) == {"/gallery", "/book"}


def test_a_word_ending_in_href_is_not_split_mid_token() -> None:
    """`\\w*[Hh]ref` must consume the whole key, not the tail of one."""
    source = 'const x = { notAHrefAtAll: "/nope", primaryHref: "/yes" };\n'
    found = internal_hrefs(source)
    assert "/yes" in found
    # `notAHrefAtAll` never reaches a quote directly after the key, so it does
    # not match at all — the point is that it does not match *as* `AHref`.
    assert "/nope" not in found


# --------------------------------------------------------------------------- #
# the repair can fix them


@pytest.mark.parametrize("request_id", sorted(SHIPPED_CTA))
def test_the_repair_no_longer_walks_past_them(request_id: int) -> None:
    primary, secondary = SHIPPED_CTA[request_id]
    source = _mock_with_cta(primary, secondary)
    served = {"/", "/catalogue", "/hire/book/:id"}

    repaired, counts = repair_file_dead_links(source, served)

    assert sum(counts.values()) == (2 if secondary else 1)
    assert primary not in repaired
    if secondary:
        assert secondary not in repaired
    assert not internal_hrefs(repaired) or set(internal_hrefs(repaired)) <= served


def test_a_call_to_action_lands_on_the_page_the_business_converts_on() -> None:
    """Rung 4's target, resolved from the route table rather than always `/`.

    Request 150's shape: a hire business whose booking page is `/hire/reserve`.
    Sending its "Get started" button home is a link that looks live and goes
    somewhere else — the thing this module exists to stop.
    """
    source = _mock_with_cta("/reserve", "/order")
    served = {"/", "/catalogue", "/product", "/hire/reserve", "/services"}

    repaired, counts = repair_file_dead_links(
        source, served, fallback="/hire/reserve"
    )

    assert counts["homed"] == 2
    assert set(internal_hrefs(repaired)) == {"/hire/reserve"}
    assert '"/"' not in repaired


def test_a_fallback_the_router_does_not_serve_is_refused() -> None:
    """A guard that grounds a link on an undeclared path has fixed nothing."""
    source = _mock_with_cta("/reserve", None)
    repaired, _ = repair_file_dead_links(
        source, {"/", "/catalogue"}, fallback="/nowhere"
    )
    assert set(internal_hrefs(repaired)) == {"/"}


def test_the_workspace_repair_resolves_its_own_target(tmp_path: Path) -> None:
    """End to end, against request 150's real route table."""
    contract = architect(150)
    (tmp_path / "src/data").mkdir(parents=True)
    (tmp_path / "src/data/mock.ts").write_text(
        _mock_with_cta("/shop", "/alerts"), encoding="utf-8"
    )
    (tmp_path / "src/App.tsx").write_text(
        "\n".join(
            f'<Route path="{r["path"]}" element={{<Page />}} />'
            for r in contract["routes"]
        ),
        encoding="utf-8",
    )

    actions = repair_dead_links(tmp_path, contract)

    assert actions, "the repair walked past the seed again"
    text = (tmp_path / "src/data/mock.ts").read_text(encoding="utf-8")
    assert "/shop" not in text and "/alerts" not in text
    assert set(internal_hrefs(text)) == {"/hire/reserve"}


# --------------------------------------------------------------------------- #
# the two patterns must not drift apart again


def test_the_gate_and_the_repair_agree_on_what_a_link_key_is() -> None:
    """They were written apart and were wrong in exactly the same way.

    A repair that cannot see what the gate reports withholds runs it could have
    fixed; a gate that cannot see what the repair rewrites passes runs it should
    have caught. Same key, one place to change it.
    """
    from app.application.preview_app.capabilities.journey import _LINK_KEYS
    from app.application.preview_app.safety.dead_links import _HREF_RE

    assert _LINK_KEYS in _HREF_RE.pattern
