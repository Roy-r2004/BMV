"""Adjudicate a run's open findings against its exact rendered PDFs.

    python tools/adjudicate_run.py <request_id>

Builds the three volumes, extracts their text, runs deterministic
adjudication (app/pipeline/adjudicate.py) over the persisted QA findings,
persists the verdicts, and prints the complete ledger. Follow with
tools/release_audit.py to re-bind the release decision to fresh hashes.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pypdfium2 as pdfium


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    from app.database import SessionLocal
    from app.models import Request
    from app.pipeline import export_pdf
    from app.pipeline.adjudicate import adjudicate

    db = SessionLocal()
    row = db.get(Request, int(argv[0]))
    if row is None:
        print(f"request {argv[0]} not found")
        return 2
    texts = {}
    for kind in ("blueprint", "technical", "operations"):
        try:
            path = export_pdf.build_pdf(row, kind)
        except ValueError:
            continue
        doc = pdfium.PdfDocument(path)
        texts[kind] = export_pdf.strip_page_chrome(
            "\n".join(p.get_textpage().get_text_range() for p in doc), row.concept_name or row.business_name)
        doc.close()
    result = adjudicate(row, texts)
    db.commit()
    for e in result["ledger"]:
        print(f"{e['id']} [{e.get('classification')}] {str(e.get('where'))[:55]}")
        if e.get("evidence"):
            print("     evidence:", e["evidence"][:160])
    print(f"\nfalse positives: {result['false_positives']} | real open: {result['open_real']}")
    print("release:", json.dumps(export_pdf.release_status(row)))
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
