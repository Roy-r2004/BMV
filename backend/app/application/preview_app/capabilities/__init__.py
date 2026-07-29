"""Capabilities — the plug-in seam for what a generated app can *do*.

The AI-features subsystem already proves this anatomy end to end: a capability is
declared from customer input, classified, placed on a route, given a required
surface, verified to have survived codegen, and enforced by gate codes. Booking
and inquiry are generalised from that shape rather than reinvented, so a later
capability (chatbot, payments) plugs into one registry instead of threading new
special cases through the pipeline.

Mock-backed for now: each capability names a ``submit_seam`` prop that a real
backend hooks into. Nothing here persists anything.
"""
from __future__ import annotations

from app.application.preview_app.capabilities.registry import (
    CAPABILITIES,
    Capability,
    capability,
    implemented_capabilities,
    resolve_capabilities,
    terminal_capability_slots,
)

__all__ = [
    "CAPABILITIES",
    "Capability",
    "capability",
    "implemented_capabilities",
    "resolve_capabilities",
    "terminal_capability_slots",
]
