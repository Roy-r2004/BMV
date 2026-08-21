"""Stages 4-5 of the consulting workflow: the client-facing MVP Blueprint
and the Technical Implementation Plan — the written half of the paid
deliverable (the images are the visual half).

Both are raw Markdown (no JSON envelope — long documents survive better
without escaping), and both fail OPEN: a missing document degrades the
deliverable, it doesn't kill the request. The frontend only marks the
Blueprint/Technical sections ready when the field is non-null.

Both are written FROM the typed claim registry and validated AGAINST it
after generation: the canonical pilot-gate sentence replaces the
[[PILOT_GATE]] token and every paraphrase of the gate; raw module ids
resolve to client-facing names; monthly restatements snap to the package
identity; threshold sentences in the technical plan are typed and labeled.
"""

import json
import re

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import build_engagement_register, log_usage
from app.templating import render


def _markdown_call(db: Session, request_id: int, purpose: str, prompt: str, *, max_tokens: int = 4000) -> str | None:
    try:
        body = provider.chat(
            settings.ANALYSIS_MODEL,
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        content = (body["choices"][0]["message"]["content"] or "").strip()
        if content.startswith("```"):
            content = content.strip("`").removeprefix("markdown").strip()
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose=purpose,
            usage=body.get("usage"), success=True,
        )
        return content or None
    except Exception as exc:
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose=purpose,
            success=False, error=str(exc)[:500],
        )
        return None


def _prompt_modules(modules: list) -> list:
    """The modules as the prose model may see them: registry-rendered KPI
    statements only — a coined candidate never reaches a prompt."""
    out = []
    for m in modules or []:
        if not isinstance(m, dict):
            continue
        mm = json.loads(json.dumps(m))
        spec = mm.get("spec")
        if isinstance(spec, dict):
            spec.pop("kpi_candidates", None)
        mm.pop("original_name", None)
        out.append(mm)
    return out


def _annual_claims(business_case: dict) -> list[float]:
    from app.pipeline.decompose import _is_money_line
    from app.pipeline.decompose import _numbers_in as _nums

    fm = (business_case or {}).get("financial_model") or {}
    claims = []
    for l in (fm.get("lines") or []) if isinstance(fm, dict) else []:
        if isinstance(l, dict) and l.get("arithmetic_verified") and _is_money_line(l):
            vals = _nums(str(l.get("annual") or ""))
            if vals:
                claims.append(vals[0])
    for sc in (fm.get("scenarios") or []) if isinstance(fm, dict) else []:
        if isinstance(sc, dict) and sc.get("impact_verified"):
            vals = [v for v in _nums(str(sc.get("impact") or "")) if v > 1]
            if vals:
                claims.append(vals[0])
    return claims


def _monthly_identity_note(business_case: dict) -> str:
    from app.pipeline import timebasis

    claims = _annual_claims(business_case)
    if not claims:
        return "No verified annual claims exist; state no monthly figures."
    parts = [f"${c:,.0f}/year = ${c / 365 * 30:,.0f} per 30-day operating month = ${c / 365:,.2f} per day"
             for c in claims[:6]]
    return ("MONTHLY IDENTITY (binding): this package uses the 30-day operating month ONLY "
            f"(annual / {timebasis.YEAR_DAYS} x {timebasis.MONTH_DAYS}); never divide a year by 12. "
            "The only monthly and daily figures permitted: " + "; ".join(parts) + ".")


_COST_LINE = re.compile(r"(\*\*What staying manual costs:\*\*[^\n]*)")
_MONTHLY = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?(?=\s*(?:per month|/\s*month|a month|monthly))", re.IGNORECASE)


def _align_cost_line(content: str, business_case: dict) -> str:
    """'What staying manual costs' restates business_case.cost_of_inaction —
    its monthly figure must BE that figure. Run 47 borrowed the Upside
    scenario's $2,333 (a verified number attached to the wrong claim); the
    canonical cost line is the one anchor, so the figure snaps to it."""
    coi = str((business_case or {}).get("cost_of_inaction") or "")
    canon = _MONTHLY.search(coi)
    m = _COST_LINE.search(content or "")
    if not canon or not m:
        return content
    line = m.group(1)
    fixed = _MONTHLY.sub(canon.group(0), line, count=1)
    return content.replace(line, fixed, 1)


_KPI_LINE = re.compile(r"(?im)^(\s*(?:[-*•]\s*)?\*\*(?:You.ll|How you.ll) know it.s working(?: when)?:?\*\*)[^\n]*(?:\n(?![\s]*(?:[-*•]\s*)?\*\*|\s*###|\s*##|\s*$)[^\n]*)*")
_NULL_LINE = re.compile(r"(\*\*What the AI does on its own:\*\*)\s*(?:Null|None|N/A|null|none|-)\s*$", re.MULTILINE)
_ANY_NULL = re.compile(r"(\*\*[^*\n]{2,60}:\*\*)\s*(?:Null|null)\b")


def _pin_kpi_lines(content: str, modules: list) -> str:
    """Volume I's 'You'll know it's working when' line for each module IS the
    registry's KPI statement — the model may neither reword it nor append
    evaluation bullets to it (run 47 pass 4 did both)."""
    if not content or not modules:
        return content
    by_name = {str(m.get("client_facing_name") or m.get("name") or ""): m for m in modules if isinstance(m, dict)}
    parts = re.split(r"(?m)^(### [^\n]+)$", content)
    # parts: [pre, heading, body, heading, body, ...]
    for i in range(1, len(parts), 2):
        name = parts[i][4:].strip().strip("*").strip()
        m = by_name.get(name)
        if not m:
            continue
        statement = str(((m.get("spec") or {}).get("kpi_statement")) or "").strip()
        if not statement:
            continue
        body = parts[i + 1]
        if _KPI_LINE.search(body):
            body = _KPI_LINE.sub(lambda mm: f"{mm.group(1)} {statement}", body, count=1)
        else:
            body = body.rstrip("\n") + f"\n- **You'll know it's working when:** {statement}\n"
        parts[i + 1] = body
    return "".join(parts)


def _no_null_lines(content: str) -> str:
    out = _NULL_LINE.sub(r"\1 No AI in this part — deliberately.", content or "")
    return _ANY_NULL.sub(r"\1 none", out)


def finish_document(content: str | None, *, modules: list, business_case: dict,
                    registry: dict | None, kind: str) -> tuple[str | None, dict]:
    """Every deterministic pass a finished volume goes through. Returns the
    corrected text and the new threshold claims the prose pass registered."""
    from app.pipeline import pilot_gate as _pg
    from app.pipeline import registry as _reg
    from app.pipeline import timebasis

    report = {"new_claims": [], "gate": {}}
    if not content:
        return content, report
    gate = (registry or {}).get("pilot_gate") or (
        (business_case or {}).get("pilot_gate") if isinstance((business_case or {}).get("pilot_gate"), dict)
        and "canonical_sentence" in (business_case or {}).get("pilot_gate", {}) else None)
    content, report["gate"] = _pg.enforce(content, gate)
    if kind == "blueprint":
        content = _pg.ensure_in_decision(content, gate)
        content = _pin_kpi_lines(content, modules)
    content = _no_null_lines(content)
    content = _reg.resolve_module_ids(content, modules)
    content, _ = timebasis.check_restatements(content, _annual_claims(business_case))
    content = timebasis.round_counts(content)
    if kind == "blueprint":
        content = _align_cost_line(content, business_case)
    if registry:
        # invented settlement/remittance periods in prose are corrected to the
        # client's stated cycle exactly as they are in the specs
        lines = []
        for line in content.split("\n"):
            fixed, _ = _reg.policy_pass(line, registry.get("claims") or [])
            lines.append(fixed)
        content = "\n".join(lines)
    if kind == "technical" and registry:
        counter = {"n": sum(1 for c in registry.get("claims") or [] if str(c.get("id", "")).startswith("TH-"))}
        content, new = _reg.label_prose_thresholds(content, registry.get("claims") or [], counter,
                                                   source="technical_plan", module_id="tp")
        report["new_claims"] = new
    return content, report


def write_blueprint(
    db: Session,
    request_id: int,
    analysis: dict,
    consult_result: dict,
    plan_result: dict,
    decomposition: dict | None = None,
) -> str | None:
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    from app.pipeline import registry as _reg
    from app.pipeline.analyze import _format_site_research

    modules = (decomposition or {}).get("modules") or []
    business_case = (decomposition or {}).get("business_case") or {}
    registry = (decomposition or {}).get("registry") or _reg.registry_for(req) or {}
    prompt = render(
        "blueprint.j2",
        business_name=req.business_name or "",
        business_description=req.business_description or "",
        industry=req.industry or "unspecified",
        revenue_today=req.revenue_today or "not stated",
        site_research=_format_site_research(req),
        business_model=analysis.get("business_model", "Unknown"),
        target_customer_profile=analysis.get("target_customer_profile", ""),
        pain_points=json.dumps(analysis.get("pain_points", [])),
        growth_opportunity=analysis.get("growth_opportunity", ""),
        consulting_summary=consult_result.get("consulting_summary", ""),
        recommended_ai_employees=json.dumps(consult_result.get("recommended_ai_employees", [])),
        concept_name=plan_result.get("concept_name", req.business_name or ""),
        roles=json.dumps(plan_result.get("roles", [])),
        modules=json.dumps(_prompt_modules(modules), indent=1) if modules else "(empty)",
        business_case=json.dumps(business_case, indent=1) if business_case else "(empty)",
        modules_present=bool(modules),
        engagement_register=build_engagement_register(
            req.engagement_type, req.needs_ai, req.main_problem, req.desired_outcome,
            req.business_description,
        ),
        pilot_gate_sentence=registry.get("pilot_gate_sentence") or "",
        build_order_names="\n".join(f"{i}. {n}" for i, n in enumerate(registry.get("build_order_names") or [], 1))
        or "(derive from the modules' dependencies)",
        monthly_identity_note=_monthly_identity_note(business_case),
    )
    # Four front-matter sections joined the document (engagement scope,
    # current state, opportunity) — give it room to finish them all.
    content = _markdown_call(db, request_id, "blueprint", prompt, max_tokens=6000)
    content, _ = finish_document(content, modules=modules, business_case=business_case,
                                 registry=registry, kind="blueprint")
    req.mvp_blueprint = content
    db.commit()
    return content


def write_technical_plan(
    db: Session,
    request_id: int,
    consult_result: dict,
    plan_result: dict,
    decomposition: dict | None = None,
) -> str | None:
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    from app.pipeline import registry as _reg

    modules = (decomposition or {}).get("modules") or []
    business_case = (decomposition or {}).get("business_case") or {}
    registry = (decomposition or {}).get("registry") or _reg.registry_for(req) or {}
    prompt = render(
        "technical_plan.j2",
        business_name=req.business_name or "",
        business_description=req.business_description or "",
        concept_name=plan_result.get("concept_name", req.business_name or ""),
        roles=json.dumps(plan_result.get("roles", [])),
        recommended_ai_employees=json.dumps(consult_result.get("recommended_ai_employees", [])),
        modules=json.dumps(_prompt_modules(modules), indent=1) if modules else "(empty)",
        modules_present=bool(modules),
        engagement_register=build_engagement_register(
            req.engagement_type, req.needs_ai, req.main_problem, req.desired_outcome,
            req.business_description,
        ),
        pilot_gate_sentence=registry.get("pilot_gate_sentence") or "",
    )
    # Per-module anatomy (data model, agent brain/tools/guardrails, APIs)
    # makes this the longest document — give it the budget to finish.
    content = _markdown_call(db, request_id, "technical_plan", prompt, max_tokens=8000)
    content, report = finish_document(content, modules=modules, business_case=business_case,
                                      registry=registry, kind="technical")
    if report["new_claims"] and registry:
        registry.setdefault("claims", []).extend(report["new_claims"])
        registry["errors"] = _reg.validate_registry(registry)
        req.registry_json = json.dumps(registry)
    req.technical_plan = content
    db.commit()
    return content
