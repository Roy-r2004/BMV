"""Markdown rendering: sections from registry queries, prose from a model that
can only reference claims by token (design 11.1, 11.2).

The laws this module enforces:

  R1  a section renders the entities its declared InputSpecs match, in entity
      order - never in the order the registry happened to write them. Two
      registries holding the same rows therefore render the same bytes, which
      is what makes "identical registry -> identical PDF" provable
  R2  the model words the connecting prose and nothing else: the narrative
      prompt receives entity ids and tokens, never figures. Prose carrying a
      number, or a token that was not offered, is a statement-drift finding
      (L6). It is regenerated MAX_NARRATIVE_REGENERATIONS times with the
      findings and then replaced by a statement list - fail closed, never
      patched by a regex (that is the r30 lesson S15 exists to keep)
  R3  every number that reaches the page traces to a registered quantity
      within RENDERED_RESTATEMENT_TOLERANCE, or it is an L11 finding. A
      coined figure is a defect even when it is plausible
  R4  a token that survives substitution is a claim that lost its wording:
      reported, never deleted

Nothing here reads an engagement type. The renderer for a section is looked
up by its declared name in a table, and the content is whatever the section's
InputSpecs match, so the same eight renderers serve all 21 products.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from decimal import Decimal
from typing import Any, Callable, Iterable, Mapping, Sequence, TYPE_CHECKING

# r30's number reader and its closeness/unit rules, imported rather than
# re-derived: L11 must judge a rendered figure exactly as the r30 gate does.
from app.pipeline.registry import _close, _numbers, _unit_compatible

from app.engine.llm import ModelCall
from app.engine.templating import render as render_prompt
from app.engine.types import (
    BOUNDS,
    TERMINAL_STATUSES,
    Add,
    Entity,
    Finding,
    Kind,
    Quantity,
    Severity,
    Status,
)
from app.engine.work_products import corrections, statements
from app.engine.work_products.canon_bridge import build_canon
from app.engine.work_products.decl import RenderingRules, SectionDecl, WorkProductDecl, plan_sections

if TYPE_CHECKING:
    from app.engine.registry import RegistryView


# ---------------------------------------------------------------------------
# ArtifactRef (contracts section 14)
# ---------------------------------------------------------------------------
# The laws own this shape and gates/laws.py is its home; it is declared here
# only so the renderers that produce artifacts have it before that module
# lands, and the import below hands over the moment it does. One class either
# way - a renderer and a law must be talking about the same artifact.
try:  # pragma: no cover - exercised by whichever component lands first
    from app.engine.gates.laws import ArtifactRef  # type: ignore
except Exception:  # pragma: no cover
    @dataclass(frozen=True)
    class ArtifactRef:  # type: ignore[no-redef]
        product_id: str
        fmt: str
        path: str
        sha256: str
        registry_hash: str
        extracted_text: str = ""


LAW_DRIFT = "L6.statement_drift"
LAW_UNTRACEABLE = "L11.untraceable_number"
LAW_UNRESOLVED_TOKEN = "R4.unresolved_statement_token"

NARRATIVE_PURPOSE = "engine:narrative_section"


def bound(name: str, overrides: Mapping[str, Any] | None = None) -> Any:
    """A named bound's live value: the caller's mapping, else the ENGINE_<name>
    setting, else the frozen default. Never a literal at the point of use."""
    if overrides is not None and name in overrides:
        return overrides[name]
    try:
        from app.config import settings
        value = getattr(settings, f"ENGINE_{name}", None)
        if value is not None:
            return value
    except Exception:
        pass
    return BOUNDS[name]


# ---------------------------------------------------------------------------
# What a render pass carries
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RenderContext:
    view: "RegistryView"
    rules: RenderingRules
    tokens: Mapping[str, str] = field(default_factory=dict)      # entity id -> token
    provider: Any = None
    calc: Any = None
    bounds: Mapping[str, Any] | None = None
    where: str = ""


@dataclass(frozen=True)
class RenderedSection:
    id: str
    title: str
    renderer: str
    body: str = ""
    head: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    entity_ids: tuple[str, ...] = ()
    findings: tuple[Finding, ...] = ()
    model_calls: int = 0


@dataclass(frozen=True)
class RenderedProduct:
    product_id: str
    title: str
    sections: tuple[RenderedSection, ...]
    markdown: str
    statement_deltas: tuple[Add, ...] = ()
    mappings: tuple[corrections.MappingRecord, ...] = ()
    findings: tuple[Finding, ...] = ()
    consumed: tuple[str, ...] = ()
    registry_hash: str = ""


def _id_key(entity_id: str) -> tuple[str, int, str]:
    prefix, _, num = entity_id.rpartition("-")
    return (prefix, int(num) if num.isdigit() else 0, entity_id)


def section_entities(section: SectionDecl, view: "RegistryView") -> tuple[Entity, ...]:
    """R1: what a section prints, in entity-id order. The InputSpec decides
    membership; the id decides order; the registry's write order decides
    nothing."""
    seen: dict[str, Entity] = {}
    for spec in section.query:
        for e in view.query(spec.kind):
            if spec.matches(e):
                seen[e.id] = e
    return tuple(sorted(seen.values(), key=lambda e: _id_key(e.id)))


def _claim(e: Entity, ctx: RenderContext) -> str:
    """The claim as this section prints it: its token when one exists (so the
    wording is written once and substituted everywhere), else its statement."""
    token = ctx.tokens.get(e.id)
    if token:
        return token
    return statements.statement_text(e, ctx.view, rules=ctx.rules)


# ---------------------------------------------------------------------------
# The renderers (SectionDecl.RENDERERS)
# ---------------------------------------------------------------------------

def _statement_list(section: SectionDecl, entities: Sequence[Entity], ctx: RenderContext) -> RenderedSection:
    body = "\n".join(f"- {_claim(e, ctx)}" for e in entities)
    return RenderedSection(id=section.id, title=section.title, renderer=section.renderer, body=body,
                           entity_ids=tuple(e.id for e in entities))


def _label_list(section: SectionDecl, entities: Sequence[Entity], ctx: RenderContext) -> RenderedSection:
    """The same claims, each carrying the kind of thing it is. The label is the
    entity's kind - a closed enum - so it is the same word in every product."""
    lines = []
    for e in entities:
        label = e.kind.value.replace("_", " ")
        lines.append(f"- **{label}:** {_claim(e, ctx)}")
    return RenderedSection(id=section.id, title=section.title, renderer=section.renderer,
                           body="\n".join(lines), entity_ids=tuple(e.id for e in entities))


def _tree(section: SectionDecl, entities: Sequence[Entity], ctx: RenderContext) -> RenderedSection:
    """Parent-child structure where the payload carries one (an issue tree, a
    hypothesis under its issue). Depth is read from parent_id/issue_id, never
    guessed from wording; an entity whose parent is not in this section is
    printed at the top level rather than dropped."""
    present = {e.id for e in entities}
    lines = []
    for e in entities:
        parent = getattr(e.payload, "parent_id", None) or getattr(e.payload, "issue_id", None)
        indent = "  " if parent in present else ""
        lines.append(f"{indent}- {_claim(e, ctx)}")
    return RenderedSection(id=section.id, title=section.title, renderer=section.renderer,
                           body="\n".join(lines), entity_ids=tuple(e.id for e in entities))


def _yes_no(flag: Any, ctx: RenderContext) -> str:
    """A tri-state read of a boolean flag. `is True` / `is False` on purpose
    (owner contract): a row written before the flag existed is unknown, not
    false, and unknown prints as the declared unknown text."""
    if flag is True:
        return "yes"
    if flag is False:
        return "no"
    return ctx.rules.unknown_text


def _table(section: SectionDecl, entities: Sequence[Entity], ctx: RenderContext) -> RenderedSection:
    """The generic table: what is claimed, where it stands, who owns it. The
    columns are envelope fields, so this one renderer serves a risk register, a
    RACI and a conflict list without knowing what any of them are."""
    head = ("Statement", "Status", "Authority")
    rows = tuple((_claim(e, ctx), e.status.value, e.authority.value) for e in entities)
    return RenderedSection(id=section.id, title=section.title, renderer=section.renderer,
                           head=head, rows=rows, body=_rows_as_markdown(head, rows),
                           entity_ids=tuple(e.id for e in entities))


def _evidence_table(section: SectionDecl, entities: Sequence[Entity], ctx: RenderContext) -> RenderedSection:
    head = ("Source", "Kind", "Record class", "Confirmed by client", "sha256")
    rows = []
    for e in entities:
        p = e.payload
        rows.append((
            _claim(e, ctx),
            getattr(getattr(p, "source_kind", None), "value", ctx.rules.unknown_text),
            getattr(getattr(p, "record_class", None), "value", ctx.rules.unknown_text),
            _yes_no(getattr(p, "record_class_confirmed_by_client", None), ctx),
            str(getattr(p, "sha256", None) or ctx.rules.unknown_text),
        ))
    rows = tuple(rows)
    return RenderedSection(id=section.id, title=section.title, renderer=section.renderer,
                           head=head, rows=rows, body=_rows_as_markdown(head, rows),
                           entity_ids=tuple(e.id for e in entities))


def _calc_table(section: SectionDecl, entities: Sequence[Entity], ctx: RenderContext) -> RenderedSection:
    """Every calculated claim with the arithmetic behind it. `Recomputed` is
    the calculator's own verdict when one was supplied; with no calculator the
    column is unknown, never an assumed pass (L7 is the gate, not this table)."""
    head = ("Claim", "Formula", "Inputs", "Recomputed")
    rows = []
    for e in entities:
        p = e.payload
        recomputed = ctx.rules.unknown_text
        if ctx.calc is not None:
            recomputed = _yes_no(bool(ctx.calc.recompute(e, ctx.view)), ctx)
        rows.append((_claim(e, ctx), str(getattr(p, "formula", None) or ctx.rules.unknown_text),
                     ", ".join(getattr(p, "inputs", ()) or ()) or ctx.rules.unknown_text, recomputed))
    rows = tuple(rows)
    return RenderedSection(id=section.id, title=section.title, renderer=section.renderer,
                           head=head, rows=rows, body=_rows_as_markdown(head, rows),
                           entity_ids=tuple(e.id for e in entities))


def _rows_as_markdown(head: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Rows as bullets rather than a pipe table: a cell is printed exactly as
    the registry holds it, and a claim containing a pipe would have to be
    escaped to survive a markdown table - which would be this module rewriting
    a client's words. The structured rows go to the PDF and the CSV."""
    lines = []
    for row in rows:
        rest = "; ".join(f"{h}: {v}" for h, v in zip(head[1:], row[1:]))
        lines.append(f"- {row[0]}" + (f" ({rest})" if rest else ""))
    return "\n".join(lines)


def _narrative(section: SectionDecl, entities: Sequence[Entity], ctx: RenderContext) -> RenderedSection:
    """R2. The model connects claims it cannot see; every claim is a token."""
    claims = [{"entity_id": e.id, "token": ctx.tokens.get(e.id, ""),
               "label": f"{e.kind.value} {e.id}"} for e in entities if ctx.tokens.get(e.id)]
    allowed = {c["token"] for c in claims}
    entity_ids = tuple(e.id for e in entities)
    if ctx.provider is None or not claims:
        # No provider, or nothing tokenised to talk about: the section is the
        # claims themselves. Fail closed - never prose without a source.
        return replace(_statement_list(section, entities, ctx), renderer=section.renderer)

    max_regen = int(bound("MAX_NARRATIVE_REGENERATIONS", ctx.bounds))
    findings: tuple[Finding, ...] = ()
    calls = 0
    for attempt in range(max_regen + 1):
        prompt = render_prompt(
            "narrative_section.j2", section_title=section.title,
            section_purpose=f"the {section.id} section of {ctx.where}", audience="the decision owner",
            claims=claims, findings=[f.issue for f in findings])
        response = ctx.provider.complete(ModelCall(
            purpose=NARRATIVE_PURPOSE, messages=({"role": "user", "content": prompt},),
            engagement_id=ctx.view.engagement_id))
        calls += 1
        if response.error is not None or not response.text:
            break
        prose = response.text.strip()
        findings = narrative_findings(prose, allowed, where=f"{ctx.where}:{section.id}")
        if not findings:
            return RenderedSection(id=section.id, title=section.title, renderer=section.renderer,
                                   body=prose, entity_ids=entity_ids, model_calls=calls)
    fallback = _statement_list(section, entities, ctx)
    return RenderedSection(id=section.id, title=section.title, renderer=section.renderer,
                           body=fallback.body, entity_ids=entity_ids, findings=findings, model_calls=calls)


# Declared renderer name -> implementation. A table, not a chain of string
# comparisons: adding a renderer is a new declaration, never a new branch.
RENDERERS: Mapping[str, Callable[[SectionDecl, Sequence[Entity], RenderContext], RenderedSection]] = {
    "statement_list": _statement_list,
    "label_list": _label_list,
    "tree": _tree,
    "table": _table,
    "evidence_table": _evidence_table,
    "calc_table": _calc_table,
    "narrative": _narrative,
}
assert set(RENDERERS) == set(SectionDecl.RENDERERS), "every declared renderer has an implementation"


# ---------------------------------------------------------------------------
# The findings a render can raise about its own output
# ---------------------------------------------------------------------------

def mask_tokens(text: str, tokens: Iterable[str]) -> str:
    """The text with every token blanked to spaces of the same length, so a
    scan of what the prose itself says never reads inside a claim. Same-length
    blanking keeps every offset the scanner reports true of the original."""
    out = text or ""
    for token in sorted(set(tokens), key=lambda t: (-len(t), t)):
        out = out.replace(token, " " * len(token))
    return out


def narrative_findings(prose: str, allowed_tokens: Iterable[str], *, where: str) -> tuple[Finding, ...]:
    """L6 at the point of writing: a number outside a token is the model
    restating a claim in its own words, and a token nobody offered is a claim
    the model invented a reference for."""
    allowed = set(allowed_tokens)
    out: list[Finding] = []
    used = corrections.unresolved_tokens(prose)
    for token in used:
        if token not in allowed:
            out.append(Finding(law=LAW_DRIFT, where=where,
                               issue=f"the narrative references {token}, which this section was not given",
                               fix="reference only the tokens listed for the section"))
    outside = mask_tokens(prose, allowed | set(used))
    for tok, _value, _unit, _start, _end in _numbers(outside):
        out.append(Finding(law=LAW_DRIFT, where=where,
                           issue=f"the narrative states the figure {tok!r} in prose instead of a claim token",
                           fix="reference the claim by its token; the engine substitutes the exact wording"))
    return tuple(out)


def _quantities_of(payload: Any) -> list[Quantity]:
    out = []
    for f in fields(payload):
        value = getattr(payload, f.name, None)
        if isinstance(value, Quantity):
            out.append(value)
    return out


def registered_quantities(view: "RegistryView") -> list[tuple[str, Quantity]]:
    """Every quantity the registry holds live, whatever kind carries it. Read
    off the dataclass fields rather than a per-kind list, so a kind that grows
    a quantity is traceable the day it does."""
    out: list[tuple[str, Quantity]] = []
    for e in view.query():
        if e.status in TERMINAL_STATUSES:
            continue
        for q in _quantities_of(e.payload):
            out.append((e.id, q))
    return out


def untraceable_number_findings(text: str, view: "RegistryView", *, where: str,
                                bounds: Mapping[str, Any] | None = None) -> tuple[Finding, ...]:
    """R3/L11: a printed figure that matches no registered quantity, in a
    compatible unit, within the declared tolerance."""
    tolerance = float(bound("RENDERED_RESTATEMENT_TOLERANCE", bounds))
    known = registered_quantities(view)
    out: list[Finding] = []
    for tok, value, unit, _start, _end in _numbers(text or ""):
        traced = False
        for entity_id, q in known:
            claim = {"unit": q.unit, "time_basis": q.dimensions.period_basis or "n/a"}
            if _unit_compatible(unit, claim) and _close(value, float(q.value), tolerance):
                traced = True
                break
        if not traced:
            out.append(Finding(law=LAW_UNTRACEABLE, where=where,
                               issue=f"the figure {tok!r} on the page matches no quantity in the registry",
                               fix="register the quantity as a fact or a calculation, or remove the figure"))
    return tuple(out)


def unresolved_token_findings(text: str, *, where: str) -> tuple[Finding, ...]:
    return tuple(Finding(law=LAW_UNRESOLVED_TOKEN, where=where,
                         issue=f"the claim token {token} reached the page without its wording",
                         fix="register the STATEMENT the token names before rendering")
                 for token in corrections.unresolved_tokens(text))


# ---------------------------------------------------------------------------
# The product
# ---------------------------------------------------------------------------

def product_title(decl: WorkProductDecl, view: "RegistryView") -> str:
    """The title the planner recorded on the WORK_PRODUCT row, when there is
    one - a product's identity is the row's, not a second rendering of the
    template."""
    for e in view.query(Kind.WORK_PRODUCT):
        if e.status not in TERMINAL_STATUSES and e.payload.product_id == decl.id:
            return e.payload.title
    central = view.central_decision()
    unknown = decl.rules.unknown_text
    return decl.title_template.format_map({
        "central_decision": central.payload.statement if central is not None else unknown,
        "deadline": unknown, "workstream": unknown})


def _narrative_ids(decl: WorkProductDecl, planned: Sequence[str], view: "RegistryView") -> set[str]:
    """Every entity a narrative section will speak about. A narrative may only
    reference tokens, so those claims need a STATEMENT even when one section
    alone prints them."""
    out: set[str] = set()
    for s in decl.sections:
        if s.id in planned and RENDERERS[s.renderer] is _narrative:
            out.update(e.id for e in section_entities(s, view))
    return out


def render_product(decl: WorkProductDecl, view: "RegistryView", *, provider: Any = None,
                   calc: Any = None, rules: RenderingRules | None = None,
                   section_ids: Sequence[str] | None = None,
                   bounds: Mapping[str, Any] | None = None) -> RenderedProduct:
    """One work product as markdown, plus the deltas, mappings and findings the
    pass produced. Pure: the caller applies the deltas."""
    rules = rules or decl.rules
    planned = tuple(section_ids) if section_ids is not None else plan_sections(decl, view)
    sections = [s for s in decl.sections if s.id in planned]

    consumed_by = {s.id: tuple(e.id for e in section_entities(s, view)) for s in sections}
    deltas = statements.statement_deltas(view, consumed_by, rules=rules,
                                         always=_narrative_ids(decl, planned, view))
    ctx = RenderContext(view=view, rules=rules, tokens=statements.token_index(view, deltas),
                        provider=provider, calc=calc, bounds=bounds, where=decl.id)

    rendered = tuple(RENDERERS[s.renderer](s, section_entities(s, view), ctx) for s in sections)

    canon = build_canon(view)
    protected = statements.client_fact_texts(view, rules=rules)
    token_texts = statements.token_texts(view, deltas)
    mappings: list[corrections.MappingRecord] = []

    def fix(text: str, where: str) -> str:
        result = corrections.correct(text, tokens=token_texts, canon=canon, protected=protected, where=where)
        mappings.extend(result.applied)
        return result.text

    title = fix(product_title(decl, view), f"{decl.id}:title")
    corrected = []
    for section in rendered:
        where = f"{decl.id}:{section.id}"
        corrected.append(replace(
            section,
            body=fix(section.body, where),
            rows=tuple(tuple(fix(cell, where) for cell in row) for row in section.rows)))
    corrected_sections = tuple(corrected)

    markdown = render_markdown(title, corrected_sections)
    findings = tuple(f for s in corrected_sections for f in s.findings)
    findings += unresolved_token_findings(markdown, where=decl.id)
    findings += untraceable_number_findings(markdown, view, where=decl.id, bounds=bounds)
    consumed = tuple(sorted({eid for s in corrected_sections for eid in s.entity_ids}, key=_id_key))
    return RenderedProduct(product_id=decl.id, title=title, sections=corrected_sections, markdown=markdown,
                           statement_deltas=deltas, mappings=tuple(mappings), findings=findings,
                           consumed=consumed, registry_hash=view.content_hash())


def render_markdown(title: str, sections: Sequence[RenderedSection]) -> str:
    """The .md artifact: one H1, then the sections in declaration order. The
    heading level matters - export_pdf._split_md_sections reads '## ' as the
    section boundary, so the PDF and the markdown carry the same structure."""
    parts = [f"# {title}", ""]
    for s in sections:
        parts.append(f"## {s.title}")
        parts.append("")
        if s.body:
            parts.append(s.body)
            parts.append("")
    return "\n".join(parts).rstrip("\n") + "\n"
