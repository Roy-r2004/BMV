"""Preview pipeline — shared mutable context threaded through phase functions.

Each phase (appspec_gate, plan_phase, codegen_phase, polish_phase,
build_phase, finalize) reads fields set by earlier phases and sets/updates
fields consumed by later ones. Fields are grouped below by the phase that
first populates them, but nothing prevents a later phase from reading an
earlier group.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models.request import Request
from app.infrastructure.logging import WatchBmv


@dataclass
class PipelineContext:
    # --- constructor / request-scoped ---
    db: Session
    request_id: int
    ai_provider: AIProvider
    template_renderer: TemplateRenderer
    app_spec_revision_id: int | None
    req: Request
    generator_version: str = "v1"

    pipeline_watch: WatchBmv | None = None

    # --- appspec_gate ---
    enforce_app_spec: bool = False
    app_spec_result: Any = None
    app_spec_scope: Any = None
    demo: dict = field(default_factory=dict)
    brand_brief: dict = field(default_factory=dict)
    primary: str = "#0f766e"
    secondary: str = "#134e4a"
    images: dict = field(default_factory=dict)

    # --- plan_phase ---
    full_context: str = ""
    plan: dict = field(default_factory=dict)
    manifest: dict = field(default_factory=dict)
    design_system: dict = field(default_factory=dict)
    design_brief: dict = field(default_factory=dict)
    architect: dict = field(default_factory=dict)
    workspace: Any = None
    brand_name: str = "Brand"
    industry: str = ""
    files_to_gen: list = field(default_factory=list)
    specs_by_path: dict = field(default_factory=dict)

    # --- codegen_phase ---
    total_files: int = 0
    workers: int = 1
    max_fix_attempts: int = 0
    max_fix_seconds: float = 0.0
    generated_ok: int = 0
    page_ok: int = 0
    files_completed: int = 0
    progress_lock: threading.RLock = field(default_factory=threading.RLock)

    # --- polish_phase ---
    font: str = ""

    # --- build_phase ---
    base_path: str = ""
    ok: bool = False
    build_log: str = ""
    attempt: int = 0
