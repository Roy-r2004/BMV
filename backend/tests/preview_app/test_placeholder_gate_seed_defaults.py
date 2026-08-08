"""`placeholder_content_shipped` catches the second family item 1.8 specified.

Item 1.8 said to build this gate on `early_brand_placeholder_strings()` /
`early_brand_placeholder_item_titles()`. What shipped used only a
brackets-and-a-capital regex, so the row has been scored against one of the two
families it was meant to catch, and nobody recorded the substitution.

Session 26's census found the missing family live on **7 of 87 stored
workspaces** — `Everyday essential` / `Guest favorite` on requests 19, 34, 37,
39, 43, **135 and 140** — a set that does not overlap the bracket regex's seven,
and two of whose members sit inside the stretch the DoD row was calling clean.

The tests below pin the behaviour *and its boundaries*, because the boundaries
are where this check can go wrong in either direction: fire on a real
business's copy, or go back to missing the family it was added for.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.application.preview_app import product_face
from app.application.preview_app.quality_gate import (
    _NAMED_EARLY_TITLES,
    evaluate_quality_gate,
)
from app.application.preview_app.industry_templates.seed import (
    early_brand_placeholder_strings,
)
from app.application.preview_app.workspace import write_file

_GOOD_HUB = """\
import { AiFeatureDeck } from '@/ui';
import { aiFeatures } from '@/data/mock';
export default function AiFeaturesPage() {
  return <AiFeatureDeck features={aiFeatures} brandName="Brand" />;
}
"""


def _ws(tmp_path: Path) -> Path:
    (tmp_path / "src" / "pages").mkdir(parents=True)
    (tmp_path / "src" / "data").mkdir(parents=True)
    (tmp_path / "dist").mkdir(parents=True)
    (tmp_path / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
    write_file(tmp_path, "src/pages/AiFeaturesPage.tsx", _GOOD_HUB)
    return tmp_path


def _mock(body: str) -> str:
    return (
        'export const navigation = { public: [{ path: "/", label: "Home" }] };\n'
        f"{body}"
        "export const aiFeatures = [] as const;\n"
    )


def _codes(report) -> set[str]:
    return {issue.code for issue in report.issues}


def test_a_seed_default_item_title_fails_the_gate(tmp_path: Path) -> None:
    """`Everyday essential` is what the pipeline writes when it has nothing to say.

    The title deliberately shares its line with a second string literal. A
    greedy leaf regex (`(['"])(.*)\\1`) would swallow both into one span,
    produce the leaf `Everyday essential", href: "/shop` and match nothing —
    the mutation sweep caught this test passing without that second literal,
    so the shape of the fixture is load-bearing.
    """
    ws = _ws(tmp_path)
    write_file(ws, "src/data/mock.ts", _mock(
        'export const seed = { items: [{ title: "Everyday essential", href: "/shop" }] };\n'
    ))
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert "placeholder_content_shipped" in _codes(report)


def test_the_other_named_early_title_also_fails(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    write_file(ws, "src/data/mock.ts", _mock(
        'export const seed = { items: [{ title: "Guest favorite" }] };\n'
    ))
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert "placeholder_content_shipped" in _codes(report)


def test_a_brand_bearing_seed_default_fails(tmp_path: Path) -> None:
    """The `"Brand" in s` half of the guard, exercised on a real member."""
    brand_bearing = sorted(s for s in early_brand_placeholder_strings() if "Brand" in s)
    assert brand_bearing, "the Brand-default seed grew no Brand-bearing leaves"
    ws = _ws(tmp_path)
    write_file(ws, "src/data/mock.ts", _mock(
        f'export const seed = {{ tagline: "{brand_bearing[0]}" }};\n'
    ))
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert "placeholder_content_shipped" in _codes(report)


def test_routes_durations_and_ctas_do_not_fire(tmp_path: Path) -> None:
    """The guard's whole purpose: bare matching fires on 87 of 87 workspaces.

    `/gallery`, `60 min`, `Get started` and `On schedule` are all string leaves
    of the Brand-default seed *and* things a real business legitimately ships.
    Without the `"Brand" in s` co-occurrence test this gate would block almost
    every preview in the corpus.
    """
    ws = _ws(tmp_path)
    write_file(ws, "src/data/mock.ts", _mock(
        "export const seed = {\n"
        '  cta: { label: "Get started", href: "/gallery" },\n'
        '  duration: "60 min",\n'
        '  trustLabels: ["On schedule"],\n'
        "};\n"
    ))
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert "placeholder_content_shipped" not in _codes(report)


def test_a_substring_of_a_default_does_not_fire(tmp_path: Path) -> None:
    """Exact leaves only — a testimonial that *contains* the phrase is real copy.

    Matching case exactly is the point: the first version of this test wrote
    "our guest favorite", lowercase, which a substring scan would not have
    matched either — so it passed against the mutation it was supposed to
    kill. The sweep caught that; the phrase now appears verbatim, capital and
    all, inside a longer sentence.
    """
    ws = _ws(tmp_path)
    write_file(ws, "src/data/mock.ts", _mock(
        'export const seed = { quote: "It has been our Guest favorite for years" };\n'
    ))
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert "placeholder_content_shipped" not in _codes(report)


def test_real_business_copy_does_not_fire(tmp_path: Path) -> None:
    """The negative case that matters — an ordinary filled-in seed stays green."""
    ws = _ws(tmp_path)
    write_file(ws, "src/data/mock.ts", _mock(
        "export const seed = {\n"
        '  items: [{ title: "Sourdough miche", description: "Milled and baked here." }],\n'
        '  tagline: "Bread worth the walk",\n'
        "};\n"
    ))
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert "placeholder_content_shipped" not in _codes(report)


def test_the_named_early_titles_track_product_face() -> None:
    """The two literal lists must not drift apart.

    `quality_gate._NAMED_EARLY_TITLES` restates a set that
    `product_face._entry_is_early_placeholder` also spells out inline. Two
    copies of one decision is exactly the shape this repo keeps finding rotted,
    so the copy is pinned to its source by reading the source rather than by
    remembering to update both.
    """
    source = Path(product_face.__file__).read_text(encoding="utf-8")
    marker = source.split("early_brand_placeholder_item_titles()", 1)[1]
    literals = set(re.findall(r'"([^"]+)"', marker.split("return True", 1)[0]))
    assert _NAMED_EARLY_TITLES <= literals, (
        "quality_gate._NAMED_EARLY_TITLES names a title product_face no longer "
        f"treats as an early placeholder: {_NAMED_EARLY_TITLES - literals}"
    )
