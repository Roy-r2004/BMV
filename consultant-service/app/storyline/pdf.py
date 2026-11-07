"""The pages the storyline adds to a file.

The answer page is first. The register is printed in the blueprint and named
in the others. Each proof section opens with its title, its exhibit's words
and its takeaway. A run with no storyline gets none of these pages.
"""
from __future__ import annotations


def opening(story, kind: str, req=None) -> list:
    """The pages that go in front of this volume, or nothing for a run with
    no answer."""
    if story is None:
        return []
    flows = answer_page_flowables(story)
    if kind == "blueprint" and story.register is not None:
        flows += register_flowables(story, req)
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
        flows.append(Paragraph(_rich(page.question), styles["h1toc"]))
    for line in page.answer_lines:
        flows.append(Paragraph(_rich(line), styles["body"]))
    for number in page.numbers:
        flows.append(Paragraph(_rich(f"{number.display} ({number.tag})"), styles["body"]))
    if page.believed:
        flows.append(Paragraph(_rich(f"What you believed: {page.believed}"), styles["body"]))
    if page.tested:
        flows.append(Paragraph(_rich(f"What the test said: {page.tested}"), styles["body"]))
    if page.monday:
        flows.append(Paragraph(_rich(f"Monday: {page.monday}"), styles["body"]))
    if page.would_not:
        flows.append(Paragraph(_rich("What we would not do: " + " ".join(page.would_not)), styles["body"]))
    line = rests_line(page.rests_on)
    if line:
        flows.append(Paragraph(_rich(line), styles["body"]))
    flows.append(PageBreak())
    return flows


def register_flowables(story, req=None) -> list:
    """The register as one table: every column, each row's range and cost,
    then the headline the ranges add up to, then its footnotes."""
    Paragraph, Spacer, PageBreak, styles = _bits()
    from reportlab.lib.units import mm

    from app.figures.known import known_for
    from app.pipeline.export_pdf import DrawnCell, _table
    from app.storyline.register import COLUMNS, table

    shown = table(story.register, known_for(req) if req is not None else _active_known())
    head = ["", *COLUMNS]
    rows = []
    for row in shown["rows"]:
        rows.append([
            DrawnCell(str(row["number"])), row["recommendation"], row["changes"], row["value"] or "",
            row["cost"] or "", row["owner"], row["when"],
            DrawnCell(_after(row["depends_on"])),
        ])
    if shown["total"]:
        rows.append([DrawnCell(""), DrawnCell("All together"), DrawnCell(""), shown["total"],
                     DrawnCell(""), DrawnCell(""), DrawnCell(""), DrawnCell("")])
    widths = [w * mm for w in (6, 36, 30, 26, 20, 20, 18, 18)]
    flows = [Paragraph("The register", styles["h1toc"]), _table(head, rows, widths), Spacer(1, 6)]
    for note in shown["footnotes"]:
        flows.append(Paragraph(_rich(note), styles["meta"]))
    flows.append(PageBreak())
    return flows


def _after(depends: list[int]) -> str:
    """"After 1", "After 1 and 2": the rows a row waits for, by their number."""
    if not depends:
        return ""
    said = [str(n) for n in depends]
    return "After " + (said[0] if len(said) == 1 else ", ".join(said[:-1]) + " and " + said[-1])


def _active_known():
    from app.figures import law
    from app.figures.model import FigureSet

    scope = law.active()
    return scope.known if scope is not None else FigureSet()


def register_reference() -> list:
    """The one line the other files use instead of repeating the register."""
    Paragraph, Spacer, PageBreak, styles = _bits()
    return [Paragraph("The register is in the blueprint.", styles["body"]), PageBreak()]


def proof_lead_flowables(section, exhibit) -> list:
    """The lead page of one proof section: its stamp, its title, its exhibit
    with its number and takeaway, the section's takeaway, then the foot."""
    Paragraph, Spacer, PageBreak, styles = _bits()
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm

    from app.pipeline.export_pdf import _drawn

    flows = []
    if section.stamp:
        stamp = ParagraphStyle("stamp", parent=styles["meta"], alignment=TA_RIGHT)
        flows.append(Paragraph(_drawn(section.stamp), stamp))
    flows.append(Paragraph(_rich(section.title), styles["h1toc"]))
    if exhibit is not None:
        from app.storyline.exhibits import draw_pdf, height_for

        flows.append(Paragraph(_rich(f"Exhibit {exhibit.id}: {exhibit.caption}"), styles["body"]))
        if exhibit.takeaway:
            flows.append(Paragraph(_rich(exhibit.takeaway), styles["body"]))
        flows.append(draw_pdf(exhibit, A4[0] - 36 * mm, height_for(exhibit)))
    if section.takeaway:
        flows.append(Paragraph(_rich(section.takeaway), styles["body"]))
    if section.foot:
        flows.append(Spacer(1, 6))
        for line in section.foot:
            flows.append(Paragraph(_rich(line), styles["meta"]))
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
    if rests.ours:
        parts.append("our estimates")
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


def _rich(text: str) -> str:
    """The volumes' content choke point: inside a release-law scope every number
    is bound to the figure it names or recorded as a finding, and a figure token
    prints as its figure."""
    from app.pipeline.export_pdf import _rich as rich

    return rich(text)
