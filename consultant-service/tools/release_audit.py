"""The release decision, recorded against the exact artifacts.

    python tools/release_audit.py <request_id>

Builds the three volumes for the run, inspects every rendered page
(tools/inspect_pdf.py), runs the typed-registry checks on the EXACT
extracted PDF text (paraphrased gate, unmapped KPI numbers, internal ids,
monthly-identity drift), computes each file's SHA-256, derives the totals
PROGRAMMATICALLY from the manifest, validates the record against itself,
and freezes everything as an immutable revision
`<uploads>/exports/releases/<id>-r<N>/`. FINAL is valid ONLY for those exact
hashes — any rebuild earns the next revision; nothing is ever overwritten.

    python tools/release_audit.py --verify <record.json>

Recomputes the hashes of the recorded files: "valid" only if every hash
still matches; anything else is "stale — re-audit required".

    python tools/release_audit.py --reaudit <revision-dir> <request_id>

Re-audits a FROZEN revision with the current controls without touching it:
verifies its hashes, extracts its text, re-adjudicates the run's findings in
memory, runs the registry checks, and writes a NEW audit revision
`<revision>-a<N>/record.json` beside it.
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _next_revision(releases_dir: str, run_id: int) -> int:
    n = 1
    if os.path.isdir(releases_dir):
        for name in os.listdir(releases_dir):
            m = re.fullmatch(rf"{run_id}-r(\d+)", name)
            if m:
                n = max(n, int(m.group(1)) + 1)
    return n


def _next_audit(releases_dir: str, rev_id: str) -> int:
    n = 2
    if os.path.isdir(releases_dir):
        for name in os.listdir(releases_dir):
            m = re.fullmatch(rf"{re.escape(rev_id)}-a(\d+)", name)
            if m:
                n = max(n, int(m.group(1)) + 1)
    return n


def totals_from(volumes: dict) -> dict:
    """Totals derive from the manifest — never typed by hand."""
    vols = [v for v in volumes.values() if isinstance(v, dict) and "pages" in v]
    pages = sum(int(v.get("pages") or 0) for v in vols)
    inspected = sum(int(v.get("inspected_pages") if v.get("inspected_pages") is not None else 0) for v in vols)
    return {"volumes": len(vols), "pages": pages, "inspected_pages": inspected,
            "every_page_inspected": bool(vols) and inspected == pages
            and all(v.get("every_page_inspected", v.get("inspected_pages") == v.get("pages")) for v in vols)}


def validate_record(record: dict) -> list[str]:
    """A release report must be arithmetically and logically consistent
    with its own manifest, or it is not a report."""
    errors = []
    vols = record.get("volumes") or {}
    t = record.get("totals") or {}
    expect = totals_from(vols)
    if t.get("pages") != expect["pages"]:
        errors.append(f"total pages {t.get('pages')} != sum of volume pages {expect['pages']}")
    if t.get("inspected_pages") != expect["inspected_pages"]:
        errors.append(f"inspected pages {t.get('inspected_pages')} != sum of per-volume inspected {expect['inspected_pages']}")
    if (t.get("inspected_pages") or 0) > (t.get("pages") or 0):
        errors.append("inspected pages exceed the artifact total")
    if t.get("every_page_inspected") != expect["every_page_inspected"]:
        errors.append("every-page claim does not match the inspection records")
    if t.get("volumes") != expect["volumes"]:
        errors.append("volume count does not match the manifest")
    for kind, v in vols.items():
        if isinstance(v, dict) and "pages" in v:
            if (v.get("inspected_pages") or 0) > (v.get("pages") or 0):
                errors.append(f"{kind}: inspected pages exceed its page count")
            if v.get("inspection_ok") and v.get("failures"):
                errors.append(f"{kind}: inspection_ok with failures listed")
    if record.get("status") in ("final", "client_approved"):
        if record.get("reasons"):
            errors.append(f"status {record['status']} with reasons listed")
        if any(isinstance(v, dict) and not v.get("inspection_ok") for v in vols.values()):
            errors.append(f"status {record['status']} with a failed inspection")
        if not expect["every_page_inspected"]:
            errors.append(f"status {record['status']} without every page inspected")
    if record.get("status") == "client_approved" and not (record.get("client_approval") or {}).get("complete"):
        errors.append("status client_approved without a client-supplied owner and approver")
    # lineage: the cumulative corrections are the parent's cumulative plus this pass
    if "corrections_current_pass" in record:
        cur, cum = record["corrections_current_pass"], record.get("corrections_cumulative") or {}
        for k, v in cur.items():
            distinct = {json.dumps(e, sort_keys=True) for e in (v or [])}  # the merge keeps one copy of identical entries
            if len(cum.get(k) or []) < len(distinct):
                errors.append(f"corrections_cumulative[{k}] holds fewer entries than the current pass")
    return errors


def _latest_revision_dir(releases_dir: str, run_id: int) -> str | None:
    best, best_n = None, 0
    if os.path.isdir(releases_dir):
        for name in os.listdir(releases_dir):
            m = re.fullmatch(rf"{run_id}-r(\d+)", name)
            if m and int(m.group(1)) > best_n:
                best, best_n = os.path.join(releases_dir, name), int(m.group(1))
    return best


def _merge_corrections(base: dict, extra: dict) -> dict:
    """Union by key; an entry already present (same JSON) is not repeated."""
    out = {k: list(v or []) for k, v in (base or {}).items()}
    for k, v in (extra or {}).items():
        seen = {json.dumps(e, sort_keys=True) for e in out.get(k, [])}
        out.setdefault(k, [])
        for e in v or []:
            if json.dumps(e, sort_keys=True) not in seen:
                out[k].append(e)
                seen.add(json.dumps(e, sort_keys=True))
    return out


def cumulative_corrections(rev_dir: str | None) -> dict:
    """Every correction applied to a run up to and including `rev_dir`,
    walking parent_revision links (a legacy record without lineage counts
    its own `corrections` as its pass and links to the previous number)."""
    if not rev_dir or not os.path.isfile(os.path.join(rev_dir, "record.json")):
        return {}
    with open(os.path.join(rev_dir, "record.json"), encoding="utf-8") as f:
        rec = json.load(f)
    if "corrections_cumulative" in rec:
        return rec["corrections_cumulative"]
    releases_dir = os.path.dirname(rev_dir)
    m = re.fullmatch(r"(\d+)-r(\d+)", os.path.basename(rev_dir))
    parent = rec.get("parent_revision")
    if not parent and m and int(m.group(2)) > 1:
        parent = f"{m.group(1)}-r{int(m.group(2)) - 1}"
    base = cumulative_corrections(os.path.join(releases_dir, parent)) if parent else {}
    return _merge_corrections(base, rec.get("corrections_current_pass", rec.get("corrections") or {}))


def _registry_blockers(row, texts: dict[str, str]) -> list[str]:
    from app.pipeline import export_pdf

    return export_pdf.registry_reasons(row, texts=texts)


def audit_run(row, out_dir: str | None = None) -> dict:
    """Build, inspect and hash all three volumes for one engagement row,
    then freeze them as an immutable revision: exports/releases/<id>-r<N>/
    holds the exact audited PDFs plus record.json. An existing revision is
    NEVER overwritten — a rebuild earns the next revision number, and every
    earlier audit record stands untouched."""
    from app.config import settings
    from app.pipeline import export_pdf
    import inspect_pdf

    from app.pipeline import registry as _registry

    gate = export_pdf.release_status(row)
    expect = "draft" if gate["status"] == "draft" else "final"
    reg = _registry.registry_for(row)
    record = {
        "request_id": row.id,
        "status": gate["status"],
        "status_label": gate["status_label"],
        "client_approval": gate.get("client_approval"),
        "reasons": list(gate["reasons"]),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "note": "FINAL applies ONLY to the exact file hashes below; any rebuild "
                "invalidates this decision and requires re-audit. States: draft (open quality findings) / "
                "final (FINAL — CONSULTANCY DELIVERABLE: every quality check passes; client approval not required) / "
                "client_approved (the client supplied the document owner and approver).",
        "volumes": {},
    }
    blockers = list(gate["reasons"])
    texts = {}
    for kind in ("blueprint", "technical", "operations"):
        try:
            path = export_pdf.build_pdf(row, kind)
        except ValueError as exc:
            record["volumes"][kind] = {"error": str(exc)}
            continue
        result = inspect_pdf.inspect(path, expect=expect, concept=row.concept_name or row.business_name, registry=reg)
        texts[kind] = result.pop("text", "")
        record["volumes"][kind] = {
            "file": os.path.basename(path),
            "pages": result["pages"],
            "inspected_pages": result["inspected_pages"],
            "every_page_inspected": result["every_page_inspected"],
            "sha256": _sha256(path),
            "inspection_ok": result["ok"],
            "failures": result["failures"],
        }
        blockers += [f"{kind}: {f}" for f in result["failures"]]
    # the registry checks on the EXACT rendered text, not the markdown
    text_blockers = _registry_blockers(row, texts) if texts else []
    blockers += [f"rendered text: {b}" for b in text_blockers if b not in gate["reasons"]]
    record["rendered_text_checks"] = text_blockers
    if blockers and record["status"] != "draft":
        record["status"] = "draft"
        record["status_label"] = export_pdf.STATUS_LABELS["draft"]
    record["reasons"] = sorted(set(blockers))
    record["totals"] = totals_from(record["volumes"])

    import shutil

    base = out_dir or os.path.join(settings.UPLOADS_DIR, "exports")
    releases_dir = os.path.join(base, "releases")
    # lineage: this pass's corrections, the parent revision, and the
    # cumulative corrections across every revision of the run
    parent_dir = _latest_revision_dir(releases_dir, row.id)
    record["parent_revision"] = os.path.basename(parent_dir) if parent_dir else None
    record["corrections_current_pass"] = _registry.corrections(reg)
    record["corrections_cumulative"] = _merge_corrections(cumulative_corrections(parent_dir), record["corrections_current_pass"])
    record["corrections"] = record["corrections_cumulative"]  # alias kept for readers of earlier records
    record["validation_errors"] = validate_record(record)
    if record["validation_errors"]:
        raise RuntimeError("release record does not validate: " + "; ".join(record["validation_errors"]))
    revision = _next_revision(releases_dir, row.id)
    rev_id = f"{row.id}-r{revision}"
    rev_dir = os.path.join(releases_dir, rev_id)
    if os.path.exists(rev_dir):
        raise RuntimeError(f"revision store {rev_dir} already exists — refusing to overwrite")
    os.makedirs(rev_dir)
    for kind, vol in record["volumes"].items():
        if "file" not in vol:
            continue
        src = os.path.join(base, vol["file"])
        if os.path.isfile(src):
            shutil.copy(src, os.path.join(rev_dir, vol["file"]))
    record["revision"] = rev_id
    record_path = os.path.join(rev_dir, "record.json")
    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=1)
    record["record_path"] = record_path
    return record


def verify(record_path: str, files_dir: str | None = None) -> str:
    """'valid' only if every recorded hash still matches its file."""
    with open(record_path, encoding="utf-8") as f:
        record = json.load(f)
    base = files_dir or os.path.dirname(record_path)
    for kind, vol in (record.get("volumes") or {}).items():
        if "sha256" not in vol:
            continue
        path = os.path.join(base, vol["file"])
        if not os.path.isfile(path) or _sha256(path) != vol["sha256"]:
            return f"stale — {kind} no longer matches the audited hash; re-audit required"
    return "valid"


def reaudit_revision(rev_dir: str, row) -> dict:
    """Re-audit a frozen revision with the CURRENT controls, writing a new
    immutable audit revision beside it. The frozen files, their record and
    the run's persisted findings are read, never written."""
    import pypdfium2 as pdfium

    import inspect_pdf
    from app.pipeline import export_pdf
    from app.pipeline.adjudicate import adjudicate
    from app.pipeline import qa_experts, registry as _registry

    rev_dir = os.path.abspath(rev_dir)
    rev_id = os.path.basename(rev_dir)
    record_path = os.path.join(rev_dir, "record.json")
    with open(record_path, encoding="utf-8") as f:
        original = json.load(f)
    integrity = verify(record_path)
    if integrity != "valid":
        raise RuntimeError(f"{rev_id}: {integrity}")
    before = {k: v.get("sha256") for k, v in original["volumes"].items() if isinstance(v, dict)}
    # registry built in memory from the run's own structures (the run may
    # predate the registry column); nothing is persisted
    import copy
    bc = copy.deepcopy(json.loads(row.business_case_json) if row.business_case_json else {})
    mods = copy.deepcopy(json.loads(row.modules_json) if row.modules_json else [])
    reg = _registry.registry_for(row) or _registry.build_registry(
        row.ops_numbers_json, bc, mods,
        free_texts=[row.business_description or "", row.main_problem or "", row.desired_outcome or ""])

    texts, volumes = {}, {}
    for kind, vol in original["volumes"].items():
        if not isinstance(vol, dict) or "file" not in vol:
            continue
        path = os.path.join(rev_dir, vol["file"])
        expect = "draft" if original.get("status") == "draft" else "final"
        result = inspect_pdf.inspect(path, expect=expect, concept=row.concept_name or row.business_name, registry=reg)
        texts[kind] = result.pop("text", "")
        doc = pdfium.PdfDocument(path)
        doc.close()
        volumes[kind] = {"file": vol["file"], "sha256": _sha256(path), "pages": result["pages"],
                         "inspected_pages": result["inspected_pages"],
                         "every_page_inspected": result["every_page_inspected"],
                         "draft_stamped": bool(result.get("draft_watermark")),
                         "inspection_ok": result["ok"], "failures": result["failures"]}

    # in-memory re-adjudication: the run's persisted findings are not altered
    result = adjudicate(row, texts, persist=False)
    ledger = result["ledger"]

    class _Shadow:  # the row as the audit sees it, with an in-memory registry
        pass

    shadow = _Shadow()
    for attr in ("id", "mvp_blueprint", "technical_plan", "business_case_json", "modules_json",
                 "procedures_json", "qa_report_json", "status", "is_failed", "checklists_json",
                 "scoreboard_json", "org_json", "journey_json", "playbook_json", "ops_numbers_json"):
        setattr(shadow, attr, getattr(row, attr, None))
    shadow.registry_json = json.dumps(reg)
    from app.pipeline.structural import structural_findings

    machine = qa_experts.machine_findings(shadow, reg, texts=texts)
    machine += [{**f, "source": "structural"} for f in structural_findings(bc, mods, reg)]
    text_blockers = export_pdf.registry_reasons(shadow, texts=texts)
    artifacts = sorted({h for t in texts.values() for h in export_pdf.find_artifacts(t, reg)})

    open_real = [e for e in ledger if e.get("classification") == "real defect"]
    reasons = []
    if open_real:
        reasons.append(f"{len(open_real)} open high finding(s) on the quality bench")
    # a re-audit can clear findings; it can never turn DRAFT-stamped pages
    # into a FINAL — that takes a fresh render, inspection and freeze
    if any(v.get("draft_stamped") for v in volumes.values()):
        reasons.append("frozen files carry the DRAFT stamp — a FINAL requires a fresh render and freeze")
    if machine:
        reasons.append(f"{len(machine)} machine finding(s) from the current controls")
    if artifacts:
        reasons.append("client-unsafe artifacts: " + ", ".join(artifacts))
    reasons += [f"rendered text: {b}" for b in text_blockers]
    for kind, v in volumes.items():
        reasons += [f"{kind}: {f}" for f in v["failures"]]

    record = {
        "request_id": row.id,
        "source_revision": rev_id,
        "source_record": record_path,
        "source_integrity": integrity,
        "status": "draft" if reasons else "final",
        "status_label": export_pdf.STATUS_LABELS["draft" if reasons else "final"],
        "reasons": sorted(set(reasons)),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "note": ("Re-audit of a frozen revision with the current controls. The source files, their "
                 "record and the run's persisted findings were read, never modified."),
        "volumes": volumes,
        "ledger": ledger,
        "machine_findings": machine,
        "rendered_text_checks": text_blockers,
        "artifacts": artifacts,
        "registry_summary": {
            "claims": len(reg.get("claims") or []),
            "errors": reg.get("errors") or [],
            "renames": reg.get("renames") or [],
            "proposals": len(_registry.proposals(reg)),
        },
    }
    record["totals"] = totals_from(volumes)
    record["validation_errors"] = validate_record(record)
    if record["validation_errors"]:
        raise RuntimeError("audit record does not validate: " + "; ".join(record["validation_errors"]))
    after = {k: v["sha256"] for k, v in volumes.items()}
    if after != before:
        raise RuntimeError("frozen files changed during the audit — aborting")

    releases_dir = os.path.dirname(rev_dir)
    audit_id = f"{rev_id}-a{_next_audit(releases_dir, rev_id)}"
    audit_dir = os.path.join(releases_dir, audit_id)
    if os.path.exists(audit_dir):
        raise RuntimeError(f"audit revision {audit_dir} already exists — refusing to overwrite")
    os.makedirs(audit_dir)
    record["audit_revision"] = audit_id
    out_path = os.path.join(audit_dir, "record.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=1)
    record["record_path"] = out_path
    record["source_integrity_after"] = verify(record_path)
    return record


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--verify":
        print(verify(argv[1]))
        return 0
    from app.database import SessionLocal
    from app.models import Request

    db = SessionLocal()
    if argv[0] == "--reaudit":
        row = db.get(Request, int(argv[2]))
        record = reaudit_revision(argv[1], row)
        db.close()
        print(json.dumps({k: v for k, v in record.items() if k not in ("ledger", "machine_findings")}, indent=1))
        return 0 if record["status"] != "draft" else 1
    row = db.get(Request, int(argv[0]))
    if row is None:
        print(f"request {argv[0]} not found")
        return 2
    record = audit_run(row)
    db.close()
    print(json.dumps(record, indent=1))
    return 0 if record["status"] != "draft" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
