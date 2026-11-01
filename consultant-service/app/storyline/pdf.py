"""The pages the storyline adds to a file.

The answer page is first. The register is printed in the blueprint and named
in the others. Each proof section opens with its title, its exhibit's words
and its takeaway. A run with no storyline gets none of these pages.
"""
from __future__ import annotations

from xml.sax.saxutils import escape


def opening(story, kind: str) -> list:
    """The pages that go in front of this volume, or nothing for a run with
    no answer."""
    if story is None:
        return []
    flows = answer_page_flowables(story)
    if kind == "blueprint" and story.register is not None:
        flows += register_flowables(story)
    elif story.register is not None:
        flows += register_reference()
    for section in story.sections:
        flows += proof_lead_flowables(section, section.exhibit)
    return flows


def answer_page_flowables(story) -> list:
    """One page: the question, the answer, the numbers, and what it rests on."""
    Paragraph, Spacer, PageBreak, styles = _bits()
    page = story.answer
    flows = []
    if page.question:
        flows.append(Paragraph(escape(page.question), styles["h1toc"]))
    for line in page.answer_lines:
        flows.append(Paragraph(escape(line), styles["body"]))
    for number in page.numbers:
        flows.append(Paragraph(escape(f"{number.display} ({number.tag})"), styles["body"]))
    if page.believed:
        flows.append(Paragraph(escape(f"What you believed: {page.believed}"), styles["body"]))
    if page.tested:
        flows.append(Paragraph(escape(f"What the test said: {page.tested}"), styles["body"]))
    if page.monday:
        flows.append(Paragraph(escape(f"Monday: {page.monday}"), styles["body"]))
    if page.would_not:
        flows.append(Paragraph(escape("What we would not do: " + " ".join(page.would_not)), styles["body"]))
    line = rests_line(page.rests_on)
    if line:
        flows.append(Paragraph(escape(line), styles["body"]))
    flows.append(PageBreak())
    return flows


def register_flowables(story) -> list:
    """The register, then its footnotes."""
    Paragraph, Spacer, PageBreak, styles = _bits()
    register = story.register
    flows = [Paragraph("The register", styles["h1toc"])]
    for row in register.rows:
        flows.append(Paragraph(escape(f"{row.recommendation} {row.when} {row.owner}"), styles["body"]))
    for note in register.footnotes:
        flows.append(Paragraph(escape(note), styles["meta"]))
    flows.append(PageBreak())
    return flows


def register_reference() -> list:
    """The one line the other files use instead of repeating the register."""
    Paragraph, Spacer, PageBreak, styles = _bits()
    return [Paragraph("The register is in the blueprint.", styles["body"]), PageBreak()]


def proof_lead_flowables(section, exhibit) -> list:
    """The lead page of one proof section."""
    Paragraph, Spacer, PageBreak, styles = _bits()
    flows = [Paragraph(escape(section.title), styles["h1toc"])]
    if exhibit is not None and exhibit.caption:
        flows.append(Paragraph(escape(exhibit.caption), styles["body"]))
    if section.takeaway:
        flows.append(Paragraph(escape(section.takeaway), styles["body"]))
    flows.append(PageBreak())
    return flows


def rests_line(rests) -> str | None:
    """What the answer rests on, naming only the kinds that are there.

    A count is a number, and the known set has no figure for a census, so the
    line does not print one. A kind with nothing behind it is left off.
    """
    parts = []
    if rests.theirs:
        parts.append("your figures")
    if rests.derived:
        parts.append("what we worked out")
    if rests.reference:
        parts.append("references with their sources")
    if rests.checks_passed:
        parts.append("the checks that passed")
    if not parts:
        return None
    return "What this rests on: " + ", ".join(parts) + "."


def _bits():
    from reportlab.platypus import PageBreak, Paragraph, Spacer

    from app.pipeline.export_pdf import _S

    return Paragraph, Spacer, PageBreak, _S
