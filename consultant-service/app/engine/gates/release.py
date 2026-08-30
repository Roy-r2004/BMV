"""The release decision, recorded against the exact artifacts (design 12.4).

The record has `tools/release_audit.validate_record`'s shape and is validated
by it UNCHANGED (release_audit.py:83). That is the point: r30 already learned,
the hard way, what a release report has to be arithmetically consistent with,
and a second validator would be a second opinion. `_sha256` (:38),
`_next_revision` (:46), `totals_from` (:66), `_merge_corrections` (:172),
`cumulative_corrections` (:185) and `verify` (:347) are reused for the same
reason.

The laws this module enforces:

  R1  a record that does not validate is never frozen. `validate_record` runs
      before anything is written, and its errors are raised, not recorded
  R2  `corrections_current_pass` is THIS pass's corrections bound to THIS
      content hash. Run 53-r22 presented seventeen corrections recovered from
      revision r3 as the current pass's work; the registry's correction log
      accumulates across every revision, so it is lineage and never a
      description of now
  R3  MF2.8: legacy r30 references live in `integrity.legacy` and nowhere
      else. A revision id from another run inside `corrections_current_pass`
      is a release claiming another run's work as its own
  R4  a revision is immutable. `uploads/engagements/<id>/releases/<id>-r<N>/`
      holds the exact audited files and `record.json`; an existing revision is
      never overwritten, a rebuild earns the next number, and FINAL is valid
      only for the hashes it names
  R5  totals derive from the manifest, never from a count someone typed
      (`totals_from`), and the same is true of the status: DRAFT while any
      blocking finding is open

There is no engagement-type branching here and no fixed number of volumes: a
release has one volume per artifact the planner produced, whatever that turns
out to be.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence, TYPE_CHECKING

from app.engine.gates import presentation
from app.engine.gates.laws import ArtifactRef, LawId, blocking, run_laws
from app.engine.types import Finding

if TYPE_CHECKING:
    from app.engine.registry import RegistryView


STATUS_DRAFT = "draft"
STATUS_FINAL = "final"
STATUS_CLIENT_APPROVED = "client_approved"

# The Integrity Record states r30's audit vocabulary uses.
INTEGRITY_CURRENT = "current"


def _audit():
    """`tools/release_audit`, imported unchanged (frozen manifest, 13.5)."""
    return presentation.import_tool("release_audit")


def status_labels() -> Mapping[str, str]:
    """One spelling of each release state, r30's (export_pdf.py:625). A second
    spelling would be a second state."""
    from app.pipeline.export_pdf import STATUS_LABELS

    return STATUS_LABELS


# ---------------------------------------------------------------------------
# Where a revision lives
# ---------------------------------------------------------------------------

def releases_dir(engagement_id: str) -> str:
    """uploads/engagements/<id>/releases/. The engagement's own document root
    (persistence.store.documents_dir) so a release sits beside the evidence it
    was built from, and under a directory `.gitignore` covers (MF3.3)."""
    try:
        from app.engine.persistence.store import documents_dir

        return os.path.join(documents_dir(engagement_id), "releases")
    except Exception:                                     # pragma: no cover - persistence absent
        from app.config import settings

        return os.path.join(settings.UPLOADS_DIR, "engagements", engagement_id, "releases")


def next_revision(engagement_id: str, base_dir: str | None = None) -> int:
    """The next free revision number. `release_audit._next_revision` (:46)
    unchanged: one function decides what "next" means for r30 and for the
    engine, so two revisions can never claim one number."""
    return _audit()._next_revision(base_dir or releases_dir(engagement_id), engagement_id)


def revision_id(engagement_id: str, revision: int) -> str:
    """`<engagement_id>-r<N>` (MF2.8). Legacy r30 revisions are
    `<request_id>-r<N>` in their own store; the two never share a directory
    and never share a record."""
    return f"{engagement_id}-r{revision}"


def revision_dir(engagement_id: str, revision: int, base_dir: str | None = None) -> str:
    return os.path.join(base_dir or releases_dir(engagement_id), revision_id(engagement_id, revision))


# ---------------------------------------------------------------------------
# R5: the status
# ---------------------------------------------------------------------------

def client_approval(view: "RegistryView") -> dict:
    """The document owner and the approver, from the registry - client facts,
    never invented (registry.document_control, registry.py:1606, as a query).
    CLIENT APPROVED is the optional later state: a consultancy deliverable is
    FINAL on its own quality checks."""
    from app.engine.types import Kind, Status, TERMINAL_STATUSES

    owner = None
    for e in view.query(Kind.DECISION_OWNER):
        if e.status not in TERMINAL_STATUSES:
            owner = e.payload.name
            break
    approver = None
    for e in view.query(Kind.CHARTER, status=Status.APPROVED):
        approver = e.confirmed_by
        break
    return {"owner": owner or None, "approver": approver or None,
            "complete": bool(owner and approver),
            "source": "engagement registry (DECISION_OWNER, the APPROVED charter)"}


def _reason(f: Finding) -> str:
    return f"{f.law}: {f.where}: {f.issue}"


def release_status(findings: Iterable[Finding], *, approval: Mapping[str, Any] | None = None) -> dict:
    """DRAFT while any blocking finding is open; FINAL when none is; CLIENT
    APPROVED when the client has additionally supplied the owner and approver.
    The reasons ARE the findings - there is no separate list to fall out of
    step with them."""
    reasons = sorted({_reason(f) for f in blocking(findings)})
    approval = dict(approval or {"owner": None, "approver": None, "complete": False})
    if reasons:
        status = STATUS_DRAFT
    elif approval.get("complete"):
        status = STATUS_CLIENT_APPROVED
    else:
        status = STATUS_FINAL
    return {"status": status, "status_label": status_labels()[status],
            "reasons": reasons, "client_approval": approval}


# ---------------------------------------------------------------------------
# The volumes
# ---------------------------------------------------------------------------

def _safe_name(name: str) -> str:
    keep = "".join(c if (c.isalnum() or c in "._-") else "_" for c in (name or ""))
    return keep[:120] or "artifact"


@dataclass(frozen=True)
class Volume:
    """One artifact as the record describes it, plus the file to freeze."""
    key: str
    entry: dict
    source_path: str
    failures: tuple[str, ...] = ()


def _inspect_volume(ref: ArtifactRef, *, expect: str | None, title: str) -> tuple[dict, list[str]]:
    """A PDF is inspected page by page (tools/inspect_pdf.inspect, unchanged)
    and measured against the body frame; a file with no pages is not
    paginated, says so with zeros, and is not pretended to have been page-
    inspected."""
    if ref.fmt != "pdf" or not os.path.isfile(ref.path):
        # `every_page_inspected` on a file with no pages is vacuously true and
        # recorded as such: totals_from sums it with the rest, and a reader can
        # see there was nothing to page through.
        return ({"pages": 0, "inspected_pages": 0, "every_page_inspected": True}, [])
    result = presentation.inspect_pdf_result(ref.path, expect=expect)
    failures = list(result.get("failures") or [])
    failures += presentation.stamp_findings(result)
    failures += presentation.pipeline_presentation_findings(ref.path)
    failures += presentation.clipping_findings(ref.path, title=title)
    return ({"pages": int(result.get("pages") or 0),
             "inspected_pages": int(result.get("inspected_pages") or 0),
             "every_page_inspected": bool(result.get("every_page_inspected")),
             "draft_stamped_pages": int(result.get("draft_stamped_pages") or 0)}, failures)


def build_volumes(artifacts: Sequence[ArtifactRef], *, expect: str | None = None,
                  titles: Mapping[str, str] | None = None) -> list[Volume]:
    """One entry per planned product and format, keyed `<product>.<fmt>`. The
    file name is the artifact's own; a collision is disambiguated rather than
    silently overwritten, because two volumes sharing a name in the frozen
    directory would mean one of them was never frozen."""
    titles = dict(titles or {})
    taken_keys: set[str] = set()
    taken_files: set[str] = set()
    out: list[Volume] = []
    for ref in artifacts:
        key = f"{ref.product_id}.{ref.fmt}"
        n = 2
        while key in taken_keys:
            key = f"{ref.product_id}.{ref.fmt}.{n}"
            n += 1
        taken_keys.add(key)

        name = _safe_name(os.path.basename(ref.path) or key)
        n = 2
        while name in taken_files:
            stem, dot, ext = name.rpartition(".")
            name = f"{stem}-{n}{dot}{ext}" if dot else f"{name}-{n}"
            n += 1
        taken_files.add(name)

        pages, failures = _inspect_volume(ref, expect=expect, title=titles.get(ref.product_id, ""))
        entry = {"file": name, "product_id": ref.product_id, "fmt": ref.fmt,
                 "sha256": ref.sha256, "registry_hash": ref.registry_hash,
                 "inspection_ok": not failures, "failures": sorted(set(failures))}
        entry.update(pages)
        out.append(Volume(key=key, entry=entry, source_path=ref.path, failures=tuple(failures)))
    return out


# ---------------------------------------------------------------------------
# R2 / R3: this pass's corrections
# ---------------------------------------------------------------------------

def _as_dicts(mappings: Iterable[Any]) -> list[dict]:
    return [m.as_dict() if hasattr(m, "as_dict") else dict(m) for m in mappings]


def revision_tokens(blob: str) -> set[str]:
    """Every `<digits>-r<digits>` token in a string. Hand-scanned rather than
    matched: this is the one place a release could quietly inherit another
    run's work, and a literal scan is easier to be sure of than a pattern."""
    out: set[str] = set()
    text = blob or ""
    at = text.find("-r")
    while at >= 0:
        start = at
        while start > 0 and text[start - 1].isdigit():
            start -= 1
        end = at + 2
        while end < len(text) and text[end].isdigit():
            end += 1
        if start < at and end > at + 2:
            out.add(text[start:end])
        at = text.find("-r", at + 1)
    return out


def foreign_revision_errors(record: Mapping[str, Any]) -> list[str]:
    """R3. `validate_record` makes this check too, but only against the
    numeric run id it can read out of the revision string; an engine revision
    is `E-7-r2`, so the check is repeated here against the whole revision id.
    A correction sourced from another revision is another run's work presented
    as this pass's."""
    mine = str(record.get("revision") or "")
    applied = ((record.get("corrections_current_pass") or {}).get("applied")) or []
    out: list[str] = []
    for entry in applied:
        blob = json.dumps(entry, sort_keys=True)
        for token in sorted(revision_tokens(blob)):
            if token not in mine:
                out.append(f"this pass lists a correction sourced from revision {token}: {blob[:120]}")
                break
    return out


def corrections_block(mappings: Sequence[Any], integrity: Mapping[str, Any]) -> dict:
    """R2. What the integrity layer applied to the content THIS record hashes:
    the entries themselves, not a count of them, each carrying where it was
    applied and the authority it was applied under."""
    applied = _as_dicts(mappings)
    return {"proven": bool(integrity), "content_hash": integrity.get("content_hash"),
            "count": len(applied), "applied": applied}


# ---------------------------------------------------------------------------
# The integrity block
# ---------------------------------------------------------------------------

def integrity_block(record: Mapping[str, Any], findings: Sequence[Finding],
                    mappings: Sequence[Any]) -> dict:
    """The Integrity Record as the release record carries it (design 12.4).

    Two fields are re-stated rather than copied. `mappings_applied` is the
    LIST of corrections, because `validate_record` compares its length with
    this pass's; and `findings` is the BLOCKING findings, because that is what
    r30's own gate means by the word (export_pdf.py:674) - an advisory LOW
    finding is recorded, and is not an open blocker that can fail a release it
    does not block.
    """
    blockers = blocking(findings)
    advisory = [f for f in findings if not f.blocks_final]
    out = dict(record)
    out["status"] = INTEGRITY_CURRENT if not blockers else "blocked"
    out["mappings_applied"] = _as_dicts(mappings)
    out["mappings_count"] = len(mappings)
    out["blocked"] = [f.as_dict() for f in blockers]
    out["findings"] = [f.as_dict() for f in blockers]
    out["advisory_findings"] = [f.as_dict() for f in advisory]
    out["laws"] = [{"id": law.value, "findings": [f.as_dict() for f in findings if f.law == law.value]}
                   for law in LawId]
    return out


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------

def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat() + "Z"


@dataclass
class ReleaseResult:
    record: dict
    findings: tuple[Finding, ...]
    revision: str
    directory: str = ""
    verification: str = ""


def build_release_record(*, engagement_id: str, view: "RegistryView",
                         artifacts: Sequence[ArtifactRef],
                         integrity: Mapping[str, Any],
                         findings: Sequence[Finding],
                         mappings: Sequence[Any] = (),
                         revision: int = 1,
                         parent_revision: str | None = None,
                         parent_dir: str | None = None,
                         titles: Mapping[str, str] | None = None,
                         legacy: Mapping[str, Any] | None = None,
                         clock: Callable[[], str] | None = None) -> dict:
    """The release record for one pass. Pure: it writes nothing, so a caller
    can inspect the decision before freezing it."""
    audit = _audit()
    approval = client_approval(view)
    gate = release_status(findings, approval=approval)

    # r30's order, for r30's reason: the expected stamp state comes from the
    # gate, so `inspect` checks the pages against the decision that was made
    # about them rather than against a guess.
    expect = STATUS_DRAFT if gate["status"] == STATUS_DRAFT else STATUS_FINAL
    volumes = build_volumes(artifacts, expect=expect, titles=titles)

    reasons = list(gate["reasons"])
    for vol in volumes:
        reasons += [f"{vol.key}: {f}" for f in vol.failures]
    status = STATUS_DRAFT if reasons else gate["status"]

    integ = integrity_block(integrity, findings, mappings)
    record: dict = {
        "engagement_id": engagement_id,
        "revision": revision_id(engagement_id, revision),
        "parent_revision": parent_revision,
        "status": status,
        "status_label": status_labels()[status],
        "client_approval": approval,
        "reasons": sorted(set(reasons)),
        "generated_at": (clock or _now)(),
        "note": ("FINAL applies ONLY to the exact file hashes below; any rebuild invalidates this "
                 "decision and requires a new revision. States: draft (open blocking findings) / "
                 "final (every law passes; client approval not required) / client_approved (the "
                 "client supplied the document owner and approver)."),
        "volumes": {vol.key: vol.entry for vol in volumes},
        "integrity": integ,
        "registry_hash": view.content_hash(),
    }
    record["totals"] = audit.totals_from(record["volumes"])
    record["corrections_current_pass"] = corrections_block(mappings, integ)
    # Lineage: the registry's own log for this pass, and the cumulative log
    # walked back through parent_revision links (release_audit:172, :185).
    record["corrections_registry_log"] = {"mappings": _as_dicts(mappings)}
    record["corrections_cumulative"] = audit._merge_corrections(
        audit.cumulative_corrections(parent_dir), record["corrections_registry_log"])
    record["corrections"] = record["corrections_cumulative"]      # the alias earlier records use
    # MF2.8: the r30 package is referenced HERE and nowhere else in the record.
    if legacy is not None:
        record["integrity"]["legacy"] = dict(legacy)
    record["validation_errors"] = sorted(set(audit.validate_record(record) + foreign_revision_errors(record)))
    return record


# ---------------------------------------------------------------------------
# R4: freezing
# ---------------------------------------------------------------------------

def freeze(record: Mapping[str, Any], artifacts: Sequence[ArtifactRef], *,
           engagement_id: str, revision: int, base_dir: str | None = None) -> str:
    """Copy the exact audited files and the record into an immutable revision
    directory. An existing directory is never written into: a rebuild earns
    the next number, and every earlier record stands untouched."""
    if record.get("validation_errors"):
        raise RuntimeError("release record does not validate: " + "; ".join(record["validation_errors"]))
    directory = revision_dir(engagement_id, revision, base_dir)
    if os.path.exists(directory):
        raise RuntimeError(f"revision store {directory} already exists - refusing to overwrite")
    os.makedirs(directory)
    by_key = {f"{ref.product_id}.{ref.fmt}": ref for ref in artifacts}
    for key, vol in (record.get("volumes") or {}).items():
        ref = by_key.get(key)
        source = ref.path if ref is not None else ""
        if source and os.path.isfile(source):
            shutil.copy(source, os.path.join(directory, vol["file"]))
    with open(os.path.join(directory, "record.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(record, fh, indent=1, sort_keys=True, default=str)
    return directory


def verify(directory_or_record: str) -> str:
    """'valid' only if every recorded hash still matches its file.
    `release_audit.verify` (:347) unchanged."""
    path = directory_or_record
    if os.path.isdir(path):
        path = os.path.join(path, "record.json")
    return _audit().verify(path)


def persist_release(record: Mapping[str, Any], *, engagement_id: str, revision: int,
                    parent: int | None = None, db: Any = None) -> None:
    """Record the revision in `engagement_releases` (C20's table). The frozen
    directory is the artifact of record; this row is the index into it."""
    from app.engine.persistence.models import EngagementRelease

    own = db is None
    if own:
        from app.database import SessionLocal

        db = SessionLocal()
    try:
        db.add(EngagementRelease(engagement_id=engagement_id, revision=revision, parent_revision=parent,
                                 record_json=json.dumps(record, default=str),
                                 status=str(record.get("status") or STATUS_DRAFT)))
        db.commit()
    finally:
        if own:
            db.close()


# ---------------------------------------------------------------------------
# The whole pass
# ---------------------------------------------------------------------------

def _parent(engagement_id: str, base_dir: str | None) -> tuple[str | None, str | None, int]:
    """(parent revision id, parent directory, the number this pass takes)."""
    directory = base_dir or releases_dir(engagement_id)
    revision = next_revision(engagement_id, directory)
    if revision <= 1:
        return (None, None, revision)
    parent_id = revision_id(engagement_id, revision - 1)
    parent_dir = os.path.join(directory, parent_id)
    return (parent_id, parent_dir if os.path.isdir(parent_dir) else None, revision)


def release(view: "RegistryView", artifacts: Sequence[ArtifactRef], *,
            engagement_id: str,
            integrity: Mapping[str, Any],
            extra_findings: Sequence[Finding] = (),
            mappings: Sequence[Any] = (),
            titles: Mapping[str, str] | None = None,
            legacy: Mapping[str, Any] | None = None,
            base_dir: str | None = None,
            freeze_it: bool = True,
            clock: Callable[[], str] | None = None) -> ReleaseResult:
    """Run every law, decide the status, build the record, validate it with
    r30's own validator and freeze the revision. The findings are returned
    with the record: a DRAFT that does not say why is not a decision."""
    artifacts = tuple(artifacts)
    findings = tuple(run_laws(view, artifacts)) + tuple(extra_findings)
    parent_id, parent_dir, revision = _parent(engagement_id, base_dir)
    record = build_release_record(
        engagement_id=engagement_id, view=view, artifacts=artifacts, integrity=integrity,
        findings=findings, mappings=mappings, revision=revision, parent_revision=parent_id,
        parent_dir=parent_dir, titles=titles, legacy=legacy, clock=clock)
    result = ReleaseResult(record=record, findings=findings, revision=record["revision"])
    if freeze_it:
        result.directory = freeze(record, artifacts, engagement_id=engagement_id,
                                  revision=revision, base_dir=base_dir)
        result.verification = verify(result.directory)
    return result
