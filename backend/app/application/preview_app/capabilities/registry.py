"""The capability registry.

One entry per thing a generated app can *do*. A capability owns a section slot, a
kit component that renders it, the anchor a CTA can point at, and the gate code
that fires when the surface is missing. Product kinds and industry packs declare
which capabilities they want; the journey walker checks they actually shipped.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class Capability:
    """A pluggable app capability.

    ``submit_seam`` is the prop a real backend hooks into. While the pipeline is
    mock-backed the component owns its own success state, so the seam is
    documented and unused — that is deliberate, not an oversight: it keeps the
    call shape decided before persistence, tenancy, and auth arrive.
    """

    id: str
    label: str
    #: Section slot that carries the surface (see the skeleton registry).
    slot: str
    #: Kit component that renders it. Must be in the skeleton's allowedComponents.
    component: str
    #: Skeleton the surface belongs on.
    skeleton_id: str
    #: DOM id the component renders, so a CTA has something real to point at.
    anchor: str
    #: A journey may legitimately end here.
    terminal: bool
    #: Prop a real backend attaches to. None for capabilities with no submit.
    submit_seam: str | None
    #: False for capabilities whose shape is declared but not yet emitted.
    implemented: bool
    #: Gate code raised when the declared surface is absent.
    missing_code: str


CAPABILITIES: dict[str, Capability] = {
    "inquiry": Capability(
        id="inquiry",
        label="Inquiry",
        slot="inquire",
        component="InquiryPanel",
        skeleton_id="public-detail",
        anchor="inquire",
        terminal=True,
        submit_seam="onSubmit",
        implemented=True,
        missing_code="capability_inquiry_surface_missing",
    ),
    "booking": Capability(
        id="booking",
        label="Booking",
        slot="booking",
        component="BookingPanel",
        skeleton_id="public-booking",
        anchor="book",
        terminal=True,
        submit_seam="onSubmit",
        implemented=True,
        missing_code="capability_booking_surface_missing",
    ),
    # Declared, not emitted. Present so the registry is exercised by a case the
    # pipeline cannot satisfy — a one-entry-shaped registry hides assumptions.
    "chatbot": Capability(
        id="chatbot",
        label="Assistant",
        slot="assistant",
        component="AiFeaturePanel",
        skeleton_id="public-home",
        anchor="assistant",
        terminal=False,
        submit_seam="onSend",
        implemented=False,
        missing_code="capability_chatbot_surface_missing",
    ),
}

#: Default capabilities per product kind when a pack declares none.
_PRODUCT_KIND_DEFAULTS: dict[str, tuple[str, ...]] = {
    "storefront": ("inquiry",),
    "booking_service": ("booking",),
    # Ops/SaaS surfaces are internal; their journeys are not public funnels.
    "saas_workspace": (),
    "internal_ops": (),
}


def capability(capability_id: str) -> Capability | None:
    """Look up one capability, or None when the id is unknown."""
    return CAPABILITIES.get(str(capability_id or "").strip().lower())


def implemented_capabilities() -> tuple[Capability, ...]:
    """Capabilities the pipeline can actually emit today."""
    return tuple(cap for cap in CAPABILITIES.values() if cap.implemented)


def _declared_by_pack(pack: Mapping[str, Any] | None) -> tuple[str, ...]:
    raw = (pack or {}).get("capabilities") or ()
    if isinstance(raw, str):
        raw = [raw]
    return tuple(str(item).strip().lower() for item in raw if str(item).strip())


def resolve_capabilities(
    product_kind: str,
    pack: Mapping[str, Any] | None = None,
    *,
    include_unimplemented: bool = False,
) -> tuple[Capability, ...]:
    """Capabilities for this app: the pack's declaration, else the kind default.

    A pack declaring ``"capabilities": ["booking"]`` is how a barber shop gets a
    booking funnel while a gallery gets an inquiry funnel, without either needing
    a bespoke code path.
    """
    ids = _declared_by_pack(pack) or _PRODUCT_KIND_DEFAULTS.get(
        str(product_kind or "").strip().lower(), ()
    )
    resolved: list[Capability] = []
    for cap_id in ids:
        cap = capability(cap_id)
        if cap is None:
            continue
        if not cap.implemented and not include_unimplemented:
            continue
        if cap not in resolved:
            resolved.append(cap)
    return tuple(resolved)


def terminal_capability_slots() -> frozenset[str]:
    """Slots that give a page somewhere for its journey to end."""
    return frozenset(cap.slot for cap in CAPABILITIES.values() if cap.terminal)
