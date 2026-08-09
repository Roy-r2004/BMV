"""Stage A / A4 — the license policy's guard suite (PHASE3_LICENSE_POLICY.md).

Stage B cannot start unmanifested: these guards run in the default suite and
each policy rule is proven ABLE to fire on a synthetic violation — a guard
that can only pass is the mutation survivor this repo keeps paying for.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.provenance import (
    LICENSE_ALLOWLIST,
    STAGE_A_DEPENDENCY_BASELINE,
    attributions_path,
    dependency_delta_problems,
    generate_attributions,
    load_manifest,
    validate_manifest,
)

#: A row that satisfies every rule — the base each violation test perturbs.
#: The path must be a real kit file; cn.ts is load-bearing and template-owned.
_VALID_ROW = {
    "path": "src/ui/lib/cn.ts",
    "source_repo": "https://github.com/magicuidesign/magicui",
    "source_path": "registry/magicui/example.tsx",
    "source_commit": "a" * 40,
    "license": "MIT",
    "license_url": "https://github.com/magicuidesign/magicui/blob/main/LICENSE.md",
    "retrieved": "2026-08-09",
    "rewritten": True,
    "rewrite_notes": "restyled onto --recipe tokens",
    "recipe_personalities": ["bold-retail"],
}


def test_committed_manifest_validates_with_zero_problems() -> None:
    """Stage A landed this manifest empty; Stage B appends one row per mined
    file. Whatever it holds, every row must clear every policy rule and the
    dependency delta must be fully manifested."""
    rows = load_manifest()
    assert validate_manifest(rows) == []
    assert dependency_delta_problems(rows) == []


def test_broken_manifest_never_reads_as_empty(tmp_path: Path) -> None:
    """A manifest that fails to parse (or is not an array) must raise — a
    broken file silently reading as [] would wave Stage B through."""
    import pytest

    (tmp_path / "PROVENANCE.json").write_text('{"not": "an array"}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_manifest(tmp_path)
    (tmp_path / "PROVENANCE.json").write_text("not json at all", encoding="utf-8")
    with pytest.raises(Exception):
        load_manifest(tmp_path)


def test_attributions_file_matches_the_generator() -> None:
    """The committed ATTRIBUTIONS.md is generator output, byte for byte —
    regeneration is the only legal way to change it."""
    assert attributions_path().read_text(encoding="utf-8") == generate_attributions(
        load_manifest()
    )


def test_allowlist_carries_exactly_one_non_plain_entry() -> None:
    """MIT-or-stricter plus the single owner-ruled exception, nothing else."""
    plain = {"MIT", "ISC", "BSD-2-Clause", "BSD-3-Clause", "0BSD", "Unlicense", "CC0-1.0"}
    assert LICENSE_ALLOWLIST - plain == {"MIT+Commons-Clause"}
    assert plain <= LICENSE_ALLOWLIST


def test_a_fully_valid_row_passes() -> None:
    assert validate_manifest([_VALID_ROW]) == []


def test_disallowed_license_fires() -> None:
    row = {**_VALID_ROW, "license": "CC-BY-4.0"}
    assert any("not in the allowlist" in p for p in validate_manifest([row]))


def test_missing_or_short_commit_pin_fires() -> None:
    # "abcdef1" is the classic short pin — 7 lowercase hex must NOT satisfy
    # "full sha at time of copy".
    for bad in ("", "abc123", "abcdef1", "a" * 39, "A" * 40):
        row = {**_VALID_ROW, "source_commit": bad}
        assert any("full 40-hex sha" in p for p in validate_manifest([row])), bad


def test_missing_license_url_fires() -> None:
    row = {**_VALID_ROW, "license_url": ""}
    assert any("license_url is empty" in p for p in validate_manifest([row]))


def test_path_outside_src_ui_fires() -> None:
    row = {**_VALID_ROW, "path": "src/pages/HomePage.tsx"}
    assert any("not under src/ui/**" in p for p in validate_manifest([row]))


def test_nonexistent_manifested_file_fires() -> None:
    row = {**_VALID_ROW, "path": "src/ui/effects/DoesNotExist.tsx"}
    assert any("does not exist" in p for p in validate_manifest([row]))


def test_react_bits_as_plain_mit_fires() -> None:
    """The bright line: React Bits rows say MIT+Commons-Clause, never MIT."""
    row = {
        **_VALID_ROW,
        "source_repo": "https://github.com/DavidHDev/react-bits",
        "license": "MIT",
    }
    assert any("never 'MIT'" in p for p in validate_manifest([row]))
    ok = {**row, "license": "MIT+Commons-Clause"}
    assert not any("never" in p for p in validate_manifest([ok]))


def test_aceternity_stays_gated() -> None:
    """No findable license text — no ruling can cure absence. Any row citing
    it fails until a human check finds actual text and edits the gate."""
    row = {**_VALID_ROW, "source_repo": "https://ui.aceternity.com/components"}
    assert any("GATED" in p for p in validate_manifest([row]))


def test_missing_rewritten_flag_fires() -> None:
    row = {k: v for k, v in _VALID_ROW.items() if k != "rewritten"}
    assert any("rewritten flag missing" in p for p in validate_manifest([row]))


def test_dependency_beyond_baseline_requires_a_manifest_row() -> None:
    current = set(STAGE_A_DEPENDENCY_BASELINE) | {"lenis"}
    problems = dependency_delta_problems([], dependencies=current)
    assert problems and "lenis" in problems[0]
    lenis_row = {
        "kind": "dependency",
        "name": "lenis",
        "source_repo": "https://github.com/darkroomengineering/lenis",
        "license": "MIT",
        "license_url": "https://github.com/darkroomengineering/lenis/blob/main/LICENSE",
        "retrieved": "2026-08-09",
    }
    assert dependency_delta_problems([lenis_row], dependencies=current) == []
    assert validate_manifest([lenis_row]) == []


def test_the_frozen_baseline_is_the_stage_a_snapshot() -> None:
    """The baseline never grows — a new dependency gets a manifest row
    instead. This pin holds the exact Stage-A names so tampering with the
    constant (the easy way around the delta guard) fails loudly."""
    assert STAGE_A_DEPENDENCY_BASELINE == frozenset(
        {
            "@radix-ui/react-dialog",
            "@radix-ui/react-select",
            "@radix-ui/react-tabs",
            "@radix-ui/react-tooltip",
            "@tanstack/react-table",
            "animejs",
            "class-variance-authority",
            "clsx",
            "date-fns",
            "lucide-react",
            "motion",
            "react",
            "react-dom",
            "react-router-dom",
            "recharts",
            "sonner",
            "tailwind-merge",
            "@tailwindcss/vite",
            "@types/node",
            "@types/react",
            "@types/react-dom",
            "@vitejs/plugin-react",
            "tailwindcss",
            "tsx",
            "typescript",
            "vite",
        }
    )
    # And the real package.json introduces nothing beyond it today.
    assert dependency_delta_problems([]) == []


def test_attributions_generator_renders_rows_deterministically() -> None:
    rows = [
        _VALID_ROW,
        {
            "kind": "dependency",
            "name": "lenis",
            "source_repo": "https://github.com/darkroomengineering/lenis",
            "license": "MIT",
            "license_url": "https://github.com/darkroomengineering/lenis/blob/main/LICENSE",
            "retrieved": "2026-08-09",
        },
    ]
    text = generate_attributions(rows)
    assert "## https://github.com/darkroomengineering/lenis" in text
    assert "- dependency `lenis` — MIT" in text
    assert "`src/ui/lib/cn.ts` — MIT, adapted from `registry/magicui/example.tsx` @ `aaaaaaaaaaaa`" in text
    assert generate_attributions(rows) == text  # deterministic
    assert generate_attributions([]) != text


if __name__ == "__main__":
    test_committed_manifest_validates_with_zero_problems()
    test_attributions_file_matches_the_generator()
    test_allowlist_carries_exactly_one_non_plain_entry()
    test_a_fully_valid_row_passes()
    test_disallowed_license_fires()
    test_missing_or_short_commit_pin_fires()
    test_missing_license_url_fires()
    test_path_outside_src_ui_fires()
    test_nonexistent_manifested_file_fires()
    test_react_bits_as_plain_mit_fires()
    test_aceternity_stays_gated()
    test_missing_rewritten_flag_fires()
    test_dependency_beyond_baseline_requires_a_manifest_row()
    test_the_frozen_baseline_is_the_stage_a_snapshot()
    test_attributions_generator_renders_rows_deterministically()
    print("Provenance guard tests passed (15 tests)")
