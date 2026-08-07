"""Prompt vocabulary for locked listing faces — derived from the validator.

Session 18: "catalogue-contract: missing directory face component:PageHeader,
missing BRAND_MANIFEST services binding" caused 5 of the session's 6 contract
rejections, and request 107's retry repeated the violation byte-identically
with the validator errors in hand — the slot_fill prompt told the writer to
edit `slots.<name>` values on a page that has no slots object, and never named
the components or the binding the validator grades. This block is built from
the validator's own required-component tuples, so the taught vocabulary and
the graded contract cannot drift apart.
"""
from __future__ import annotations

from app.application.preview_app.catalogue_contract.scaffold import (
    LISTING_FACE_COMPONENTS,
)
from app.application.preview_app.catalogue_contract.validate import (
    _DIRECTORY_FACE_MARKER,
    _DIRECTORY_FACE_REQUIRED,
    _SCHEDULE_FACE_MARKER,
    _SCHEDULE_FACE_REQUIRED,
)

_HEADER = "=== LOCKED LISTING FACE (this page has NO slots object) ===\n"


def listing_face_contract_block(scaffold: str) -> str:
    """The face-contract section for a slot_fill prompt, or "" for slot pages.

    Keyed on the scaffold's own face marker — the same string the validator
    branches on — so the block renders exactly when the face rules are the
    ones the fill will be graded against.
    """
    text = scaffold or ""
    if _DIRECTORY_FACE_MARKER in text:
        required = ", ".join(_DIRECTORY_FACE_REQUIRED)
        listing = " or ".join(LISTING_FACE_COMPONENTS)
        return (
            _HEADER
            + "This scaffold is a dedicated directory/catalogue listing face. It has no "
            "SkeletonComposer and no `slots` object, so the slot-editing rules above do not "
            "apply here. The validator rejects your file unless ALL of these survive, by "
            "exact name:\n"
            f"- Keep these components rendered: {required} — and the item grid stays "
            f"{listing}. A rejection saying \"missing directory face component:PageHeader\" "
            "means you dropped or renamed the <PageHeader> title band. Keep it; never "
            "replace it with MarketingHero.\n"
            "- Keep the import from '@/ui'.\n"
            "- Keep the scaffold's catalogue-source comment that names "
            "BRAND_MANIFEST.services, exactly as written. A rejection saying \"missing "
            "BRAND_MANIFEST services binding\" means that comment was deleted — the file "
            "must keep the name BRAND_MANIFEST.\n"
            "- Never read seed.hero on this page.\n"
            "- Change ONLY copy: headings, descriptions, CTA labels and hrefs, footer text, "
            "and the item mapping's fallback strings. Keep the structure, the bindings, and "
            "every data-appspec-* attribute.\n"
        )
    if _SCHEDULE_FACE_MARKER in text:
        required = ", ".join(_SCHEDULE_FACE_REQUIRED)
        return (
            _HEADER
            + "This scaffold is a dedicated schedule listing face. It has no "
            "SkeletonComposer and no `slots` object, so the slot-editing rules above do not "
            "apply here. The validator rejects your file unless ALL of these survive, by "
            "exact name:\n"
            f"- Keep these components rendered: {required}.\n"
            "- Keep the import from '@/ui'.\n"
            "- Keep the `const services = ... BRAND_MANIFEST.services ...` binding — a "
            "rejection saying \"missing BRAND_MANIFEST services binding\" means it was "
            "deleted.\n"
            "- Change ONLY copy: headings, subcopy, CTA labels and hrefs, footer text. Keep "
            "the structure, the bindings, and every data-appspec-* attribute.\n"
        )
    return ""


__all__ = ["listing_face_contract_block"]
