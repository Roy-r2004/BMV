"""The release decision, recorded against the exact artifacts.

    python tools/release_audit.py <request_id>

Builds the three volumes for the run, inspects every rendered page
(tools/inspect_pdf.py), computes each file's SHA-256, and writes
`<uploads>/exports/release-<id>.json` recording status, reasons, per-file
inspection and hashes. FINAL is valid ONLY for those exact hashes — any
rebuild changes the hashes and the old decision no longer applies.

    python tools/release_audit.py --verify <record.json>

Recomputes the hashes of the recorded files: "valid" only if every hash
still matches; anything else is "stale — re-audit required".
"""

import hashlib
import json
import os
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


def audit_run(row, out_dir: str | None = None) -> dict:
    """Build, inspect and hash all three volumes for one engagement row.
    Returns the release record (also written to disk)."""
    from app.config import settings
    from app.pipeline import export_pdf
    import inspect_pdf

    gate = export_pdf.release_status(row)
    expect = "final" if gate["status"] == "final" else "draft"
    record = {
        "request_id": row.id,
        "status": gate["status"],
        "reasons": gate["reasons"],
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "note": "FINAL applies ONLY to the exact file hashes below; any rebuild "
                "invalidates this decision and requires re-audit.",
        "volumes": {},
    }
    blockers = list(gate["reasons"])
    for kind in ("blueprint", "technical", "operations"):
        try:
            path = export_pdf.build_pdf(row, kind)
        except ValueError as exc:
            record["volumes"][kind] = {"error": str(exc)}
            continue
        result = inspect_pdf.inspect(path, expect=expect)
        record["volumes"][kind] = {
            "file": os.path.basename(path),
            "pages": result["pages"],
            "sha256": _sha256(path),
            "inspection_ok": result["ok"],
            "failures": result["failures"],
        }
        blockers += [f"{kind}: {f}" for f in result["failures"]]
    if blockers and record["status"] == "final":
        record["status"] = "draft"
        record["reasons"] = blockers
    out_dir = out_dir or os.path.join(settings.UPLOADS_DIR, "exports")
    os.makedirs(out_dir, exist_ok=True)
    record_path = os.path.join(out_dir, f"release-{row.id}.json")
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
    row = db.get(Request, int(argv[0]))
    if row is None:
        print(f"request {argv[0]} not found")
        return 2
    record = audit_run(row)
    db.close()
    print(json.dumps(record, indent=1))
    return 0 if record["status"] == "final" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
