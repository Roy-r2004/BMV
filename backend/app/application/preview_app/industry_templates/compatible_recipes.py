"""compatible_recipes — pack -> recipe pairing map. CONSUMED since Stage A.

Session 25, roadmap item 3.2 (backend half) authored this as inert data; the
owner ruled consumption on 2026-08-08 (session 26) and Stage A (session 30)
landed it. Two consumers, exactly:

1. ``loader.load_templates`` stamps ``compatible_recipes`` onto every loaded
   pack from this map (packs never author the field themselves — pinned).
2. ``pick_recipe_id``'s no-keyword fallback rotates over
   ``MARKETING_RECIPE_IDS`` — the reachable brief-recipe set — instead of all
   eight recipes.

The keyword path in ``pick_recipe_id`` and the fail-closed hint-match pairing
in ``design_recipes.apply_recipe_to_architect`` stay untouched: the
plan_phase null-out remains the guard for keyword false-hits, and
"pottery -> agency stack" must still fail loudly.

WHY ONE MODULE, NOT 27 JSON EDITS. The packs in ``packs/*.json`` are owned
content data whose single behavioral pairing knob is ``recipe_hint``. The
compatible set is *derived* from pipeline code, and its derivation rule needs to
live next to the data exactly once — stamped into 27 JSON files it would be 27
unexplained copies that drift. One keyed map, one docstring, one census
(``scripts/measure/compatible_recipes_census.py``) proving it against HEAD.

DERIVATION RULE (from what HEAD does, not aspiration). "Compatible" means: a
run exists under HEAD in which this pack is the plan's primary industry template
on its own surface AND the plan's effective ``recipe_id`` is that recipe.

1. Ops packs (skeleton ``ops-*``; served only when ``pick_template_id`` runs
   with ``surface="ops"`` as the primary template, i.e. OPS_KINDS runs):
   ``plan_phase`` line ~165 forces ``plan["recipe_id"] = kind_contract.recipe_id``
   after recipe apply, and the contract recipe for ops kinds is exactly one of
   ``dense-ops`` (internal_ops generic / saas_workspace generic),
   ``dense-ops-ledger`` (saas_workspace accounting subtype),
   ``dense-ops-floor`` (internal_ops trading subtype). Pack choice (industry-tag
   overlap) and contract recipe (product-kind classification) are computed from
   the business text independently — the code links them nowhere — so every ops
   pack is compatible with all three ops contract recipes, and only those.

2. Public packs (skeleton ``public-home``; served only with ``surface="public"``,
   i.e. PUBLIC_KINDS runs): the effective recipe is
   ``brief_recipe or template_recipe_hint(...) or kind_contract.recipe_id``.
   - ``template_recipe_hint`` re-runs the same deterministic ``pick_template_id``
     call, so the no-brief pairing is exactly ``pack.recipe_hint``.
   - ``brief_recipe`` comes from ``pick_recipe_id`` over all eight recipes, but
     ``plan_phase`` lines ~130-133 null any hub_variant=="app" recipe for public
     kinds, so the reachable brand-brief set is the five marketing recipes:
     editorial, warm-service, bold-retail, nocturne, craft.
   - ``kind_contract.recipe_id`` (warm-service for both public kinds) is
     shadowed whenever a pack matched, because every pack declares a hint.
   Compatible set = {pack.recipe_hint} union the five marketing recipes; since
   every public pack's hint is itself a marketing recipe, that is the five
   marketing recipes. List order: the pack's own deterministic hint first, then
   the rest in RECIPES declaration order.

3. Unreachable packs (``member-hub``, ``checkout-cart``, ``account-tracking``):
   their skeletons (``member-hub``, ``utility-checkout``, ``utility-account``)
   fail BOTH surface filters in ``loader.pick_template_id`` — not ``ops-*`` and
   excluded from public by the ``utility-``/``member-``/``checkout`` prefixes —
   and no code path calls ``get_template`` with a hardcoded id, so under HEAD no
   pairing exists for them at all. Their entries record the pack's own declared
   ``recipe_hint`` (the only pairing the pack data asserts, and what
   ``template_recipe_hint`` would produce should they ever become selectable) so
   the map stays total; they are flagged in ``UNREACHABLE_PACK_IDS`` and the
   census RED-EXITS if their reachability ever changes.

Facts this map bakes (census RED-EXITS on drift): 27 packs (16 public-home,
8 ops-dashboard, 3 unreachable), 8 recipes (5 marketing hub, 3 app hub),
PUBLIC_KINDS == {storefront, booking_service}, OPS_KINDS == {saas_workspace,
internal_ops}.
"""
from __future__ import annotations

#: The five hub_variant=="marketing" recipes — the reachable recipe set for
#: public product kinds (plan_phase nulls app-hub brief recipes for those).
MARKETING_RECIPE_IDS: tuple[str, ...] = (
    "editorial",
    "warm-service",
    "bold-retail",
    "nocturne",
    "craft",
)

#: The three hub_variant=="app" recipes — the only recipes a ProductKindContract
#: can force onto an OPS_KINDS run (and therefore onto any ops pack).
OPS_CONTRACT_RECIPE_IDS: tuple[str, ...] = (
    "dense-ops",
    "dense-ops-ledger",
    "dense-ops-floor",
)

#: Packs pick_template_id can never return under HEAD (skeleton fails both
#: surface filters). Entries below carry only the pack's own declared hint.
UNREACHABLE_PACK_IDS: frozenset[str] = frozenset(
    {"member-hub", "checkout-cart", "account-tracking"}
)

#: pack id -> recipe ids HEAD can pair it with (derivation rule in docstring).
#: Public packs list their deterministic hint first.
COMPATIBLE_RECIPES: dict[str, tuple[str, ...]] = {
    # -- public-home packs (16): hint first, then remaining marketing recipes --
    "agency-portfolio-home": ("editorial", "warm-service", "bold-retail", "nocturne", "craft"),
    "art-gallery-portfolio-home": ("editorial", "warm-service", "bold-retail", "nocturne", "craft"),
    "auto-dealership-home": ("bold-retail", "editorial", "warm-service", "nocturne", "craft"),
    "barber-grooming-home": ("editorial", "warm-service", "bold-retail", "nocturne", "craft"),
    "clinic-dental-home": ("editorial", "warm-service", "bold-retail", "nocturne", "craft"),
    "education-tutoring-home": ("warm-service", "editorial", "bold-retail", "nocturne", "craft"),
    "fashion-retail-storefront": ("bold-retail", "editorial", "warm-service", "nocturne", "craft"),
    "fitness-studio-home": ("warm-service", "editorial", "bold-retail", "nocturne", "craft"),
    "home-services-trades": ("warm-service", "editorial", "bold-retail", "nocturne", "craft"),
    "hotel-hospitality-home": ("nocturne", "editorial", "warm-service", "bold-retail", "craft"),
    "law-professional-home": ("editorial", "warm-service", "bold-retail", "nocturne", "craft"),
    "pottery-craft-studio": ("craft", "editorial", "warm-service", "bold-retail", "nocturne"),
    "real-estate-showcase": ("bold-retail", "editorial", "warm-service", "nocturne", "craft"),
    "restaurant-cafe-home": ("warm-service", "editorial", "bold-retail", "nocturne", "craft"),
    "retail-store-home": ("editorial", "warm-service", "bold-retail", "nocturne", "craft"),
    "spa-wellness-home": ("editorial", "warm-service", "bold-retail", "nocturne", "craft"),
    # -- ops-dashboard packs (8): the three contract recipes, nothing else --
    "booking-calendar-ops": OPS_CONTRACT_RECIPE_IDS,
    "clinic-front-desk-ops": OPS_CONTRACT_RECIPE_IDS,
    "hedge-fund-trading-desk": OPS_CONTRACT_RECIPE_IDS,
    "inventory-catalog-ops": OPS_CONTRACT_RECIPE_IDS,
    "leads-crm-list": OPS_CONTRACT_RECIPE_IDS,
    "owner-kpi-dashboard": OPS_CONTRACT_RECIPE_IDS,
    "saas-accounting": OPS_CONTRACT_RECIPE_IDS,
    "staff-floor-ops": OPS_CONTRACT_RECIPE_IDS,
    # -- unreachable packs (3): declared hint only; see UNREACHABLE_PACK_IDS --
    "member-hub": ("warm-service",),
    "checkout-cart": ("bold-retail",),
    "account-tracking": ("dense-ops",),
}


def compatible_recipes_for(pack_id: str) -> tuple[str, ...]:
    """Recipes HEAD can pair with this pack; empty tuple for unknown ids."""
    return COMPATIBLE_RECIPES.get(str(pack_id or "").strip(), ())
