"""`catalogue.json` must stay derivable from `registry.ts`.

`registry.ts` declares itself canonical and says catalogue.json is generated from
it via `npm run sync:ui`. That script was removed when the template was slimmed
(`sync-ui-catalogue` is in `test_scaffold_pruned.py`'s forbidden substrings, so
putting it back in the template fails on purpose), leaving two hand-synced files
and nothing to notice a divergence.

The divergence was already there when this test was written: `CatalogGrid` and
`InquiryPanel` were added to `catalogue.json` and `index.ts` but never to
`registry.ts`'s `CATALOGUE_COMPONENTS`, so the template's own
`getCatalogueComponentNames()` did not list the two components its skeletons
allow — within one session of the file being marked hand-synced.

Which direction each drift breaks:
* only in `registry.ts` — invisible to every prompt, validator and skeleton
  contract, because `ui_catalogue.load_catalogue()` reads the JSON.
* only in `catalogue.json` — offered to the model, then fails to import.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

from app.application.ui_registry import (  # noqa: E402
    CATALOGUE_PREAMBLE,
    RegistryParseError,
    build_catalogue_from_registry,
    catalogue_drift,
    catalogue_path,
    registry_path,
    serialize_catalogue,
)

REGISTRY = registry_path()
CATALOGUE = catalogue_path()


def test_the_checked_in_catalogue_matches_the_registry() -> None:
    drift = catalogue_drift()
    assert drift == [], (
        "catalogue.json has drifted from registry.ts:\n  "
        + "\n  ".join(drift)
        + "\n\nregenerate with: python -m app.application.ui_registry --write"
    )


def test_the_generator_round_trips_the_file_byte_for_byte() -> None:
    """Not just semantically equal — regenerating must be a no-op diff.

    Otherwise `--write` reformats 1600 lines on every run and nobody uses it.
    """
    assert serialize_catalogue(build_catalogue_from_registry()) == CATALOGUE.read_text(
        encoding="utf-8"
    )


def _kit_exports() -> set[str]:
    """Value names `@/ui` re-exports, from both the block and one-line forms.

    `UiIcon` uses `export { UiIcon } from '../components/UiIcons';` while the rest
    live in multi-line blocks, so a substring check over the file misses it.
    """
    import re

    index = (REGISTRY.parent / "index.ts").read_text(encoding="utf-8")
    names: set[str] = set()
    for block in re.findall(r"export\s+(?:type\s+)?\{([^}]*)\}", index, re.DOTALL):
        for entry in block.split(","):
            entry = entry.strip()
            if not entry or entry.startswith("type "):
                continue
            # `X as Y` exports Y.
            names.add(entry.split(" as ")[-1].strip())
    return names


def test_every_registry_component_is_importable_from_the_kit() -> None:
    """The third file in the triangle. A catalogue entry with no export is a
    component the model is invited to use and cannot."""
    exported = _kit_exports()
    assert "UiIcon" in exported and "CatalogGrid" in exported, (
        "the export parser stopped seeing real exports; it would pass vacuously"
    )
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    missing = [
        component["name"]
        for component in catalogue["components"]
        if component["name"] not in exported
    ]
    assert missing == [], f"catalogued but not exported from @/ui: {missing}"


def test_every_component_file_named_in_the_catalogue_exists() -> None:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    missing = [
        component["path"]
        for component in catalogue["components"]
        if not (REGISTRY.parent / component["path"]).is_file()
    ]
    assert missing == [], f"catalogue points at files that do not exist: {missing}"


def test_every_skeleton_allows_only_catalogued_components() -> None:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    known = {component["name"] for component in catalogue["components"]}
    problems = [
        f"{skeleton['id']} allows {name}, which is not in the catalogue"
        for skeleton in catalogue["skeletons"]
        for name in skeleton.get("allowedComponents") or []
        if name not in known
    ]
    assert problems == [], problems


# ---------------------------------------------------------------------------
# The parser itself — a quiet partial parse would recreate the drift
# ---------------------------------------------------------------------------

_MINIMAL = """
const PUBLIC_ALLOWED = ['PublicShell', 'Button'] as const;

export const CATALOGUE_COMPONENTS: readonly ComponentMeta[] = [
  {
    name: 'Button',
    surface: 'core',
    path: 'core/Button.tsx',
    requiredProps: ['children'],
    optionalProps: ['variant'],
    variants: { variant: ['default', 'ghost'] },
  },
] as const;

export const SKELETONS: readonly SkeletonDefinition[] = [
  {
    id: 'public-home',
    surface: 'public',
    shell: 'PublicShell',
    purpose:
      'A purpose that wrapped onto its own line, with a comma, inside it.',
    requiredSections: ['shell'],
    optionalSections: [],
    recommendedOrder: ['shell'],
    allowedComponents: [...PUBLIC_ALLOWED, 'Badge'],
    supportedVariants: {},
  },
] as const;
"""


def test_parses_the_subset_registry_actually_uses() -> None:
    built = build_catalogue_from_registry(_MINIMAL)
    assert built["components"] == [
        {
            "name": "Button",
            "surface": "core",
            "path": "core/Button.tsx",
            "requiredProps": ["children"],
            "optionalProps": ["variant"],
            "variants": {"variant": ["default", "ghost"]},
        }
    ]
    skeleton = built["skeletons"][0]
    assert skeleton["allowedComponents"] == ["PublicShell", "Button", "Badge"]
    assert skeleton["supportedVariants"] == {}
    assert skeleton["optionalSections"] == []
    # The wrapped value, and the comma inside it, both survive.
    assert skeleton["purpose"] == (
        "A purpose that wrapped onto its own line, with a comma, inside it."
    )


def test_a_value_wrapped_onto_the_next_line_is_never_silently_dropped() -> None:
    """This was a real bug in this parser: splitting members on newlines as well
    as commas lost `purpose:` for six skeletons, and the drift report then said
    the JSON had a field the registry did not — inviting a "fix" that deleted it.
    """
    for skeleton in build_catalogue_from_registry()["skeletons"]:
        assert skeleton.get("purpose"), f"{skeleton['id']} lost its purpose"


def test_an_unknown_construct_raises_instead_of_guessing() -> None:
    with pytest.raises(RegistryParseError, match="NOT_A_REAL_ARRAY"):
        build_catalogue_from_registry(
            _MINIMAL.replace("allowedComponents: [...PUBLIC_ALLOWED, 'Badge']",
                             "allowedComponents: [...NOT_A_REAL_ARRAY]")
        )
    with pytest.raises(RegistryParseError, match="unsupported value"):
        build_catalogue_from_registry(
            _MINIMAL.replace("requiredProps: ['children']", "requiredProps: someCall()")
        )
    with pytest.raises(RegistryParseError, match="CATALOGUE_COMPONENTS"):
        build_catalogue_from_registry("export const SKELETONS = [] as const;")


def test_an_object_member_that_is_not_a_key_value_pair_raises() -> None:
    """Spreading a base object into a skeleton is the plausible next edit here.

    Skipping such a member would drop every field it carries and report the
    difference as drift in `catalogue.json` — the failure mode that makes a
    generator worse than no generator.
    """
    with pytest.raises(RegistryParseError, match="unparsed object member"):
        build_catalogue_from_registry(
            _MINIMAL.replace("    id: 'public-home',", "    ...BASE_SKELETON,\n    id: 'public-home',")
        )
    with pytest.raises(RegistryParseError, match="unparsed object member"):
        build_catalogue_from_registry(
            _MINIMAL.replace("    surface: 'core',", "    surface,")
        )


def test_comments_do_not_become_data() -> None:
    """`registry.ts` carries an explanatory comment inside the public-detail
    skeleton about why InquiryPanel is scoped there."""
    with_comment = _MINIMAL.replace(
        "    id: 'public-home',",
        "    // Scoped deliberately: adding it to PUBLIC_ALLOWED blows the budget.\n"
        "    id: 'public-home',",
    )
    assert build_catalogue_from_registry(with_comment) == build_catalogue_from_registry(
        _MINIMAL
    )


def test_the_preamble_is_not_derived_from_the_registry() -> None:
    """The four scalar keys are the JSON's own contract; assert they are stated."""
    built = build_catalogue_from_registry(_MINIMAL)
    for key, value in CATALOGUE_PREAMBLE.items():
        assert built[key] == value
    assert built["generatedFrom"] == "src/ui/registry.ts"
