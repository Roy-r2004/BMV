"""Persistence helpers for revisioned canonical AppSpecs."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.appspec.source import canonical_json, source_sha256
from app.core.config import settings
from app.domain.models.app_spec import (
    APP_SPEC_STATUS_ACCEPTED,
    APP_SPEC_STATUS_REJECTED,
    AppSpecRevision,
)


def _as_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"Expected mapping/Pydantic model, got {type(value).__name__}")


def _report_passed(report: Any, explicit: bool | None) -> bool:
    if explicit is not None:
        return bool(explicit)
    payload = _as_mapping(report)
    if "passed" in payload:
        return bool(payload["passed"])
    if "is_valid" in payload:
        return bool(payload["is_valid"])
    # The independent coverage contract uses pass/repair rather than a
    # second, redundant boolean field.
    return payload.get("verdict") == "pass"


def _coverage_score(report: Any, explicit: int | None) -> int | None:
    if explicit is not None:
        return max(0, min(100, int(explicit)))
    payload = _as_mapping(report)
    raw = payload.get("score")
    if raw is None:
        return None
    try:
        return max(0, min(100, int(raw)))
    except (TypeError, ValueError):
        return None


def load_json_object(raw: str | None) -> dict[str, Any]:
    """Parse a persisted JSON object without leaking parser failures outward."""
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def app_spec_provenance(revision: AppSpecRevision) -> dict[str, Any]:
    """Small, safe reference to attach to a generated preview artifact."""
    return {
        "id": revision.id,
        "revision": revision.revision,
        "schema_version": revision.schema_version,
        "sha256": revision.app_spec_sha256,
    }


def revision_summary(revision: AppSpecRevision) -> dict[str, Any]:
    """Public-safe status summary; excludes source, contract, and model metadata."""
    return {
        "id": revision.id,
        "request_id": revision.request_id,
        "revision": revision.revision,
        "schema_version": revision.schema_version,
        "status": revision.status,
        "validation_passed": revision.validation_passed,
        "coverage_passed": revision.coverage_passed,
        "coverage_score": revision.coverage_score,
        "app_spec_sha256": revision.app_spec_sha256,
        "created_at": revision.created_at,
        "validated_at": revision.validated_at,
    }


def app_spec_revision_is_complete(
    revision: AppSpecRevision,
    *,
    source_sha256: str | None = None,
    product_strategy_sha256: str | None = None,
) -> bool:
    """Strict v2 completeness predicate; legacy acceptance is not enough."""

    if (
        revision.status != APP_SPEC_STATUS_ACCEPTED
        or not revision.validation_passed
        or not revision.coverage_passed
    ):
        return False
    if source_sha256 is not None and revision.source_sha256 != source_sha256:
        return False
    metadata = load_json_object(revision.generation_metadata_json)
    validation = load_json_object(revision.deterministic_validation_json)
    coverage = load_json_object(revision.semantic_coverage_json)
    if (
        metadata.get("policy") != "v2_strict"
        or metadata.get("generator_version") != "v2"
        or metadata.get("complete") is not True
        or metadata.get("used_fallback") is not False
        or metadata.get("coverage_review_kind") != "independent_model"
        or not isinstance(metadata.get("customer_source_artifact_id"), int)
        or not isinstance(metadata.get("product_strategy_revision_id"), int)
    ):
        return False
    if not (validation.get("passed") or validation.get("is_valid")):
        return False
    if (
        coverage.get("verdict") != "pass"
        or not coverage.get("goal_coverage")
        or revision.coverage_score is None
        or revision.coverage_score < settings.APPSPEC_MIN_COVERAGE_SCORE
    ):
        return False
    families = metadata.get("model_families")
    if not isinstance(families, dict):
        return False
    author = families.get("author")
    repair = families.get("repair")
    reviewer = families.get("coverage")
    if not author or not repair or not reviewer:
        return False
    if reviewer in {author, repair}:
        return False
    if (
        product_strategy_sha256 is not None
        and metadata.get("product_strategy_sha256") != product_strategy_sha256
    ):
        return False
    return True


class AppSpecRepository:
    """Store and retrieve immutable AppSpec attempts for one SQLAlchemy session."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def latest_accepted(
        self,
        request_id: int,
        source_sha256: str | None = None,
        schema_version: str | None = None,
    ) -> AppSpecRevision | None:
        query = self.db.query(AppSpecRevision).filter(
            AppSpecRevision.request_id == request_id,
            AppSpecRevision.status == APP_SPEC_STATUS_ACCEPTED,
            AppSpecRevision.validation_passed.is_(True),
            AppSpecRevision.coverage_passed.is_(True),
        )
        if source_sha256 is not None:
            query = query.filter(AppSpecRevision.source_sha256 == source_sha256)
        if schema_version is not None:
            query = query.filter(AppSpecRevision.schema_version == schema_version)
        return query.order_by(
            AppSpecRevision.revision.desc(),
            AppSpecRevision.id.desc(),
        ).first()

    def latest_attempt(self, request_id: int) -> AppSpecRevision | None:
        return (
            self.db.query(AppSpecRevision)
            .filter(AppSpecRevision.request_id == request_id)
            .order_by(AppSpecRevision.revision.desc(), AppSpecRevision.id.desc())
            .first()
        )

    def latest_complete(
        self,
        request_id: int,
        *,
        source_sha256: str,
        schema_version: str,
        product_strategy_sha256: str,
    ) -> AppSpecRevision | None:
        candidates = (
            self.db.query(AppSpecRevision)
            .filter(
                AppSpecRevision.request_id == request_id,
                AppSpecRevision.status == APP_SPEC_STATUS_ACCEPTED,
                AppSpecRevision.validation_passed.is_(True),
                AppSpecRevision.coverage_passed.is_(True),
                AppSpecRevision.source_sha256 == source_sha256,
                AppSpecRevision.schema_version == schema_version,
            )
            .order_by(
                AppSpecRevision.revision.desc(),
                AppSpecRevision.id.desc(),
            )
            .all()
        )
        return next(
            (
                row
                for row in candidates
                if app_spec_revision_is_complete(
                    row,
                    source_sha256=source_sha256,
                    product_strategy_sha256=product_strategy_sha256,
                )
            ),
            None,
        )

    def get_revision(self, request_id: int, revision: int) -> AppSpecRevision | None:
        return (
            self.db.query(AppSpecRevision)
            .filter(
                AppSpecRevision.request_id == request_id,
                AppSpecRevision.revision == revision,
            )
            .first()
        )

    def list_revisions(self, request_id: int) -> list[AppSpecRevision]:
        return (
            self.db.query(AppSpecRevision)
            .filter(AppSpecRevision.request_id == request_id)
            .order_by(AppSpecRevision.revision.desc(), AppSpecRevision.id.desc())
            .all()
        )

    def next_revision(self, request_id: int) -> int:
        current = (
            self.db.query(func.max(AppSpecRevision.revision))
            .filter(AppSpecRevision.request_id == request_id)
            .scalar()
        )
        return int(current or 0) + 1

    def save_attempt(
        self,
        *,
        request_id: int,
        source_snapshot: Mapping[str, Any],
        app_spec: Any,
        schema_version: str,
        deterministic_validation: Any,
        semantic_coverage: Any,
        generation_metadata: Mapping[str, Any] | None = None,
        status: str | None = None,
        validation_passed: bool | None = None,
        coverage_passed: bool | None = None,
        coverage_score: int | None = None,
        parent_revision_id: int | None = None,
        revision: int | None = None,
        commit: bool = True,
    ) -> AppSpecRevision:
        """Persist one final generation attempt.

        Accepted status cannot be forced past a failing deterministic or
        semantic report.  With ``commit=True`` an automatically allocated
        revision is retried once if another worker won the same revision.
        """
        source_payload = _as_mapping(source_snapshot)
        spec_payload = _as_mapping(app_spec)
        validation_payload = _as_mapping(deterministic_validation)
        coverage_payload = _as_mapping(semantic_coverage)
        metadata_payload = _as_mapping(generation_metadata)

        validation_ok = _report_passed(validation_payload, validation_passed)
        coverage_ok = _report_passed(coverage_payload, coverage_passed)
        score = _coverage_score(coverage_payload, coverage_score)
        eligible = validation_ok and coverage_ok

        resolved_status = status or (
            APP_SPEC_STATUS_ACCEPTED if eligible else APP_SPEC_STATUS_REJECTED
        )
        if resolved_status == APP_SPEC_STATUS_ACCEPTED and not eligible:
            raise ValueError(
                "An AppSpec cannot be accepted unless deterministic validation "
                "and semantic coverage both pass."
            )
        if resolved_status not in {
            APP_SPEC_STATUS_ACCEPTED,
            APP_SPEC_STATUS_REJECTED,
        }:
            raise ValueError(f"Unsupported AppSpec status: {resolved_status}")
        if parent_revision_id is not None:
            parent = self.db.query(AppSpecRevision).filter(
                AppSpecRevision.id == parent_revision_id
            ).first()
            if parent is None or parent.request_id != request_id:
                raise ValueError(
                    "parent_revision_id must refer to an AppSpec revision for "
                    "the same request."
                )

        source_json = canonical_json(source_payload)
        spec_json = canonical_json(spec_payload)
        validation_json = canonical_json(validation_payload)
        coverage_json = canonical_json(coverage_payload)
        metadata_json = canonical_json(metadata_payload)
        source_digest = source_sha256(source_payload)
        spec_digest = hashlib.sha256(spec_json.encode("utf-8")).hexdigest()
        fixed_revision = revision is not None
        attempts = 1 if fixed_revision or not commit else 2

        for attempt in range(attempts):
            revision_number = int(revision) if fixed_revision else self.next_revision(request_id)
            row = AppSpecRevision(
                request_id=request_id,
                revision=revision_number,
                schema_version=schema_version,
                status=resolved_status,
                source_snapshot_json=source_json,
                source_sha256=source_digest,
                app_spec_json=spec_json,
                app_spec_sha256=spec_digest,
                deterministic_validation_json=validation_json,
                validation_passed=validation_ok,
                semantic_coverage_json=coverage_json,
                coverage_passed=coverage_ok,
                coverage_score=score,
                generation_metadata_json=metadata_json,
                parent_revision_id=parent_revision_id,
                validated_at=datetime.utcnow(),
            )
            self.db.add(row)
            try:
                if commit:
                    self.db.commit()
                else:
                    self.db.flush()
                self.db.refresh(row)
                return row
            except IntegrityError:
                self.db.rollback()
                if fixed_revision or attempt + 1 >= attempts:
                    raise

        raise RuntimeError("Could not allocate an AppSpec revision")
