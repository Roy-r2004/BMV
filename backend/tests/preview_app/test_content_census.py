"""The DoD 2 / DoD 5 census parsers, pinned.

`scripts/measure/content_census.py` produces two numbers that go into the roadmap,
and both come out of regexes over TSX. This repo's recurring defect is a
measurement instrument that quietly stops measuring — a `tail` that swallowed a
red `tsc`, mutation decoys whose anchors had drifted, a compose service that
mounted the wrong tree. A census whose prose detector starts returning zero would
read as "Phase 2 already landed".

So the discriminators are tested, not the totals: a total is re-derived by running
the script over the archived corpus, and pinning one here would just be a second
copy of a number.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "content_census",
    Path(__file__).resolve().parents[2] / "scripts" / "measure" / "content_census.py",
)
assert _SPEC and _SPEC.loader
content_census = importlib.util.module_from_spec(_SPEC)
sys.modules["content_census"] = content_census
_SPEC.loader.exec_module(content_census)

prose_chars = content_census.prose_chars
seed_keys = content_census.seed_keys
mock_export_keys = content_census.mock_export_keys


@pytest.mark.parametrize(
    "text",
    [
        "flex items-center gap-4 md:grid-cols-2",
        "mt-6 rounded-2xl border border-black/5 bg-white p-8",
        "text-sm text-muted",
    ],
)
def test_a_tailwind_class_list_is_not_prose(text: str) -> None:
    """The single judgment call in DoD 2's definition, and the one that could
    inflate the number by an order of magnitude if it went the other way."""
    assert not content_census._is_prose(text)


@pytest.mark.parametrize(
    "text",
    [
        "Your seamless gateway to an unforgettable Adirondack escape.",
        "Flagship service with clear results and a calm, premium feel.",
        "Book your stay",
        # All lowercase, so only the utility-token ratio separates it from a class
        # list — the first sweep found nothing pinning that.
        "book your stay today",
        # Lowercase *and* hyphenated. The detector called this Tailwind and dropped
        # it until the ratio replaced "any hyphenated token at all".
        "self-catering apartments available",
        # Capitalized and majority-hyphenated: only the capital saves it.
        "Check-in 3pm",
    ],
)
def test_marketing_copy_is_prose(text: str) -> None:
    assert content_census._is_prose(text)


@pytest.mark.parametrize(
    "text",
    ["/gallery", "https://example.com/a b", "#inquire", "./HomePage", "ok",
     "AiFeaturesPage", "gallery",
     # No word of two letters or more: a measurement, not copy.
     "12 34 56", "250 EUR"],
)
def test_paths_urls_and_single_words_are_not_prose(text: str) -> None:
    assert not content_census._is_prose(text)


def test_prose_is_counted_from_props_and_from_jsx_text() -> None:
    source = """
import { PageHeader } from '@/ui/PageHeader';

export default function HomePage() {
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader title="Rooms and suites for every kind of stay" />
      <p>Every room opens onto the lake.</p>
    </div>
  );
}
"""
    assert prose_chars(source) == len("Rooms and suites for every kind of stay") + len(
        "Every room opens onto the lake."
    )


def test_a_wrapper_page_measures_near_zero() -> None:
    """What Phase 2's `<SpecPage routeId="gallery" />` is supposed to leave behind."""
    source = """
import { SpecPage } from '@/render/SpecPage';

export default function GalleryPage() {
  return <SpecPage routeId="gallery" />;
}
"""
    assert prose_chars(source) == 0


def test_class_names_are_excluded_and_the_exclusion_is_measurable() -> None:
    source = '<div className="flex flex-col gap-4 rounded-xl">Stay with us this winter</div>'

    assert prose_chars(source) == len("Stay with us this winter")
    assert prose_chars(source, drop_classnames=False) == prose_chars(source), (
        "a class list must not be prose under either setting"
    )


def test_seed_keys_walks_past_nested_objects_and_strings() -> None:
    """`seed` is the DoD 5 measurement, and its values are objects, arrays and
    strings containing braces. A naive key regex reports the nested keys too and
    the "1 key common to all" result quietly becomes twenty."""
    source = """
export const brand = { name: "X" };
export const seed = {
  hero: { headline: "A place to stay", cta: { label: "Book" } },
  items: [{ title: "Room" }, { title: "Suite" }],
  note: "we close at 5 } sharp, doors: locked",
  footer: { columns: [] }
};
export const roles = [];
  // export const legacyBrand = {};
"""
    assert seed_keys(source) == {"hero", "items", "note", "footer"}
    assert mock_export_keys(source) == {"brand", "seed", "roles"}


def test_a_workspace_with_no_seed_export_reports_no_keys() -> None:
    """11 of the 58 archived workspaces predate `seed` and export bespoke names
    instead. Counting them as "zero keys in common" would drag the DoD 5 number
    to zero for a reason that is not the defect being measured."""
    source = 'export const brand = { name: "X" };\nexport const paintings = [];\n'

    assert seed_keys(source) == set()
    assert mock_export_keys(source) == {"brand", "paintings"}
