"""The roadmap file. Task 8 replaces this body with the full plan.

Until then the file is a real PDF, so the package can include it, and it
names no length and no number the run has not stored.
"""
from __future__ import annotations

import os

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.config import settings
from app.pipeline import action_plan


class NotReady(Exception):
    """The roadmap has no plan to print. `key` is the file that is missing."""

    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


def build_roadmap_pdf(req) -> str:
    """A PDF at uploads/exports/{id}-roadmap.pdf. Raises NotReady("roadmap")
    when the run has no action plan to base it on."""
    plan = action_plan.load(req)
    phases = plan.get("phases") if isinstance(plan, dict) else None
    if (not isinstance(phases, list) or not phases
            or plan.get("status") in (action_plan.WRITING, action_plan.FAILED)):
        raise NotReady("roadmap")
    out_dir = os.path.join(settings.UPLOADS_DIR, "exports")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{getattr(req, 'id', None)}-roadmap.pdf")
    sheet = canvas.Canvas(path, pagesize=A4)
    sheet.setFont("Helvetica", 16)
    sheet.drawString(72, 780, "The implementation roadmap")
    sheet.setFont("Helvetica", 11)
    name = getattr(req, "business_name", None) or "This business"
    sheet.drawString(72, 750, f"Prepared for {name}.")
    sheet.showPage()
    sheet.save()
    return path
