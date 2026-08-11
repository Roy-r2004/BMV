"""Three defects the session-28 validation trio found, all pre-existing.

Requests 162-164, the same three briefs as the 27b trio, run against the four
owner rulings. The seed fix worked on all three — `gemini-2.5-flash`, attempt 1,
usable, 15.7 / 24.3 / 33.3 s against 1-of-11 before — and `pack_copy_shipped`
fired zero times, so the writers replaced the pack copy. What the trio bought was
these three, none of which is in the code the rulings touched.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

TEMPLATE = REPO_ROOT / "backend/preview-template"


# ---------------------------------------------------------------------------
# 1. The component supports a variant its own metadata denied — request 163
# ---------------------------------------------------------------------------


def test_every_variant_the_hero_accepts_is_declared_in_the_registry():
    """`MarketingHero.tsx` handles `'item'`; the registry listed only `'split'`.

    Request 163 died at 88 % on `invalid variant:MarketingHero.variant=item` —
    a variant the component has an explicit branch for at
    `MarketingHero.tsx:96`. The type union is the source of truth for what the
    component accepts, so it is read here rather than restated.
    """
    from app.application.ui_registry import build_catalogue_from_registry

    source = (TEMPLATE / "src/ui/public/MarketingHero.tsx").read_text(encoding="utf-8")
    union_line = next(
        line for line in source.splitlines()
        if line.startswith("export type MarketingHeroVariant")
    )
    # Quoted members only — `HeroVariant` is a named union defined elsewhere
    # and is covered by the registry's own list. The trailing `;` is why this
    # reads the quotes rather than stripping punctuation.
    declared_in_tsx = set(re.findall(r"""['"]([a-z-]+)['"]""", union_line))

    catalogue = build_catalogue_from_registry()
    entry = next(
        c for c in _components(catalogue) if c.get("name") == "MarketingHero"
    )
    declared_in_registry = set(entry["variants"]["variant"])

    missing = declared_in_tsx - declared_in_registry
    assert not missing, (
        f"the component accepts {sorted(missing)} and the registry denies it — "
        "the validator will reject a page the template renders fine"
    )


def _components(node):
    if isinstance(node, dict):
        if "name" in node and "requiredProps" in node:
            yield node
        for value in node.values():
            yield from _components(value)
    elif isinstance(node, list):
        for value in node:
            yield from _components(value)


# ---------------------------------------------------------------------------
# 2. The last-resort stub raised on a cosmetic error — request 163
# ---------------------------------------------------------------------------


def test_a_tolerated_contract_error_never_kills_the_last_resort_stub():
    """`write_safe_stub`'s docstring: "this can never fail to build".

    It could. The catalogue-scaffold branch validated with the raw error list
    while `blocking_contract_errors` — which exists to separate cosmetic from
    fatal, and already names `invalid variant:` as cosmetic — was ignored at
    that one call site. A stub that fails the gate is not a stub, it is a
    delayed failure.
    """
    from app.application.preview_app.catalogue_contract.validate import (
        blocking_contract_errors,
    )

    cosmetic = [
        "invalid variant:MarketingHero.variant=item",
        "invalid prop:ProductShowcase.tone",
    ]
    assert blocking_contract_errors(cosmetic) == []

    fatal = ["missing required prop:MarketingHero.headline"]
    assert blocking_contract_errors(cosmetic + fatal) == fatal

    source = (
        REPO_ROOT / "backend/app/application/preview_app/fallback.py"
    ).read_text(encoding="utf-8")
    assert "blocking_contract_errors(" in source, (
        "the catalogue stub must filter tolerated errors before raising"
    )


# ---------------------------------------------------------------------------
# 3. The guard wrote the placeholders its own gate rejects — request 162
# ---------------------------------------------------------------------------


def test_the_seed_scaffold_borrows_titles_instead_of_inventing_placeholders():
    """162 was withheld at 574 s for two titles the pipeline wrote itself.

    The seed model answered — a real bakery catalogue in `products` — and then
    `ensure_seed_scaffold_fields` added a `seed.items` key the model had not
    used, containing `'Everyday essential'` and `'Guest favorite'`, which are
    precisely the strings `placeholder_content_shipped` fails a run for.
    """
    from app.application.preview_app.safety.mock_data import ensure_seed_scaffold_fields

    mock = (
        "export const brand = { name: 'Kestrel & Fern Bakehouse' };\n"
        "export const seed = {\n"
        '  products: [{"title": "Seeded rye"}, {"title": "Celebration cake"},\n'
        '             {"title": "Morning bun"}, {"title": "Sourdough"}],\n'
        "};\n"
    )

    out = ensure_seed_scaffold_fields(mock, brand_name="Kestrel & Fern Bakehouse")

    assert "Everyday essential" not in out
    assert "Guest favorite" not in out
    assert "Seeded rye" in out and "Celebration cake" in out


def test_the_fallback_titles_are_not_strings_the_gate_rejects():
    """With nothing to borrow it still must not write a known-failing string."""

    from app.application.preview_app.industry_templates.seed import (
        early_brand_placeholder_item_titles,
    )
    from app.application.preview_app.safety.mock_data import ensure_seed_scaffold_fields

    out = ensure_seed_scaffold_fields(
        "export const brand = { name: 'Vantage' };\nexport const seed = {\n};\n",
        brand_name="Vantage",
    )

    named = {"Everyday essential", "Guest favorite"}
    for bad in named | {t for t in early_brand_placeholder_item_titles() if "Brand" in t}:
        assert bad not in out, f"the stub writes {bad!r}, which the gate fails on"


def test_borrowing_escapes_a_quote_in_a_title():
    """A real catalogue says "Baker's dozen"; an unescaped apostrophe is TS1002."""

    from app.application.preview_app.safety.mock_data import ensure_seed_scaffold_fields

    mock = (
        "export const brand = { name: 'X' };\n"
        "export const seed = {\n"
        '  products: [{"title": "Baker\'s dozen"}],\n'
        "};\n"
    )
    out = ensure_seed_scaffold_fields(mock, brand_name="X")

    # The borrowed title is written into a single-quoted TS literal, so the
    # apostrophe must arrive escaped or the module does not parse.
    assert "Baker\\'s dozen" in out


def test_the_stub_borrows_at_most_three_titles():
    """`seed.items` is a scaffold key, not a second copy of the catalogue.

    Copying a twenty-item catalogue in here doubles it in `mock.ts` and leaves
    two arrays that can drift apart.
    """
    from app.application.preview_app.safety.mock_data import ensure_seed_scaffold_fields

    products = ", ".join(f'{{"title": "Item {n}"}}' for n in range(1, 21))
    out = ensure_seed_scaffold_fields(
        "export const brand = { name: 'X' };\n"
        f"export const seed = {{\n  products: [{products}],\n}};\n",
        brand_name="X",
    )
    items_block = out.split("items: [", 1)[1].split("]", 1)[0]

    assert items_block.count("title:") == 3


# ---------------------------------------------------------------------------
# 4. The seed shipped an import into a module that forbids them — all three
# ---------------------------------------------------------------------------


def test_a_seed_that_imports_anything_is_rejected():
    """Request 163's line 1: `import { Role } from './types';`.

    The prompt's first rule is "Plain data module — NO imports". The validator
    checked three exotic shapes — dynamic `import(`, aliased `import x =`, URL
    specifiers — and waved through the ordinary one. `vite` then failed with
    `Could not resolve './types'`, the repair ladder failed with it, and the
    nuclear stabilizer replaced the model's whole catalogue with the plumbing
    mock. **All three runs of the 162-164 trio shipped generic content for this
    one reason**, which is also why the seed telemetry said `usable` while the
    shipped app had no catalogue in it.

    Rejecting it here costs one ask on the next model in the chain. Accepting it
    costs a build, a repair ladder and the catalogue.
    """
    from app.application.preview_app.codegen.mock import _valid_synthesized_mock_source

    bad = (
        "import { Role } from './types';\n"
        "export const brand = { name: 'X' };\n"
        "export const seed = {};\n"
    )
    assert _valid_synthesized_mock_source(bad, ["brand"]) is False

    for form in (
        "import Role from './types';\n",
        "import * as t from './types';\n",
        "import type { Role } from './types';\n",
        "export { Role } from './types';\n",
        "export * from './types';\n",
    ):
        source = form + "export const brand = { name: 'X' };\n"
        assert _valid_synthesized_mock_source(source, ["brand"]) is False, form


def test_a_data_key_called_from_is_not_an_import():
    """`{ from: '2026-01-01', to: '2026-01-31' }` is ordinary seed data.

    A token rule on `from` could not tell a date range from a re-export, which
    is why the re-export check reads the source line instead.
    """
    from app.application.preview_app.codegen.mock import _REEXPORT_RE

    assert not _REEXPORT_RE.search(
        "export const seed = { range: { from: '2026-01-01', to: '2026-01-31' } };\n"
    )
    assert _REEXPORT_RE.search("export { Role } from './types';\n")
