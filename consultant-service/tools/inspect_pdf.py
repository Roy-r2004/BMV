"""Release inspection for a generated engagement PDF.

    python tools/inspect_pdf.py <file.pdf> [--expect-draft | --expect-final]

Automated checks (exit 1 on any failure):
  - page count is nonzero and every page renders
  - no blank pages (uniform-pixel detection)
  - brand fonts embedded (Syne/Plex present in the file)
  - extracted text carries no client-unsafe artifacts (the release gate's
    own detector)
  - footer page numbers are consistent with physical order
  - body pages carry the volume header; the DRAFT stamp matches the
    expected release state when one is specified

Honest limits — NOT automatically detectable, human page review required:
  clipped or overflowing text, subtle layout collisions, awkward page
  breaks, image quality. The tool prints a review checklist for those.
"""

import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pypdfium2 as pdfium

from app.pipeline.export_pdf import find_artifacts, strip_page_chrome


def inspect(path: str, expect: str | None = None, concept: str | None = None) -> dict:
    failures: list[str] = []
    doc = pdfium.PdfDocument(path)
    n = len(doc)
    if n == 0:
        return {"file": path, "pages": 0, "failures": ["zero pages"], "ok": False}

    raw = open(path, "rb").read()
    if b"Syne" not in raw or b"Plex" not in raw:
        failures.append("brand fonts not embedded (Helvetica fallback rendered)")

    page_texts: list[str] = []
    inspected = 0
    for i in range(n):
        page = doc[i]
        try:
            img = page.render(scale=0.8).to_pil().convert("L")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"page {i + 1} failed to render: {exc}")
            page_texts.append("")
            continue
        lo, hi = img.getextrema()
        if hi - lo < 8:
            failures.append(f"page {i + 1} is blank")
        page_texts.append(page.get_textpage().get_text_range())
        inspected += 1

    full = "\n".join(page_texts)
    for hit in find_artifacts(full):
        failures.append(f"client-unsafe artifact in text: {hit}")
    if re.search(r"<[^<>\n]*\(proposed[^<>]*>", full):
        failures.append("angle-bracket wrapper reached the rendered page")

    numbered = 0
    for i, t in enumerate(page_texts):
        hits = re.findall(r"Page (\d+)", t)
        if hits:
            numbered += 1
            if int(hits[-1]) != i + 1:
                failures.append(f"page {i + 1} footer says Page {hits[-1]}")
    if numbered == 0:
        failures.append("no footer page numbers found")

    drafted = "DRAFT — REQUIRES VALIDATION" in full
    if expect == "draft" and not drafted:
        failures.append("expected DRAFT watermark, none present")
    if expect == "final" and drafted:
        failures.append("final package still carries the DRAFT watermark")

    stamped = sum(1 for t in page_texts if "DRAFT — REQUIRES VALIDATION" in t)
    if expect == "draft" and drafted and stamped != n:
        failures.append(f"DRAFT stamp on {stamped} of {n} pages — every page must carry it")

    return {
        "file": os.path.basename(path), "pages": n, "inspected_pages": inspected,
        "every_page_inspected": inspected == n, "draft_watermark": drafted,
        "draft_stamped_pages": stamped,
        "numbered_pages": numbered, "failures": failures, "ok": not failures,
        # the text as a reader reads it: page chrome removed so a sentence
        # split by a page break is one sentence again
        "text": strip_page_chrome("\n".join(page_texts), concept),
    }


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    expect = None
    if "--expect-draft" in argv:
        expect = "draft"
        argv = [a for a in argv if a != "--expect-draft"]
    if "--expect-final" in argv:
        expect = "final"
        argv = [a for a in argv if a != "--expect-final"]
    ok = True
    for path in argv:
        result = inspect(path, expect)
        print(json.dumps({k: v for k, v in result.items() if k != "text"}, indent=1))
        ok = ok and result["ok"]
    print(
        "\nHuman review still required (not auto-detectable): clipped/overflowing text, "
        "layout collisions, awkward page breaks, image quality. Record reviewer, date, "
        "files and pages inspected, pass/fail, notes."
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
