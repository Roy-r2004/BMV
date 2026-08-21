"""The decomposition stage — the difference between a brochure and a
deliverable a company would pay for.

The old shape asked one LLM call to write a whole blueprint from
summaries-of-summaries, and it produced exactly what that produces:
confident generic prose. This stage inverts it: FIRST break the proposed
product into named modules and an explicit business case (structured JSON,
each claim traceable to intake facts), THEN deep-spec each module with its
own dedicated call — so the documents downstream are assembled from
specifics that already exist as data, not improvised as sentences.

Fails open like every text stage here: no decomposition means the
blueprint falls back to its pre-decomposition quality, it never kills the
request.
"""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import build_engagement_register, extract_json_from_text, log_usage
from app.pipeline.analyze import _format_site_research
from app.templating import render

logger = logging.getLogger("consultant.decompose")

_NUM_RE = re.compile(r"\d[\d,]*\.?\d*\s*%?")


def _numbers_in(text: str) -> list[float]:
    vals = []
    for m in _NUM_RE.finditer(text or ""):
        tok = m.group(0).strip()
        pct = tok.endswith("%")
        try:
            v = float(tok.rstrip("%").replace(",", "").strip())
        except ValueError:
            continue
        vals.append(v / 100.0 if pct else v)
    return vals


_MONEY_WORDS = re.compile(r"\$|\busd\b|cost|saving|revenue|fee|spend|loss|margin|price", re.IGNORECASE)


def _is_money_line(line: dict) -> bool:
    """A financial line is currency when its figure, its arithmetic or its
    item says so — run 47 printed '70,956' without the sign and every
    monthly restatement lost its anchor."""
    return bool(_MONEY_WORDS.search(str(line.get("annual") or "") + " " + str(line.get("arithmetic") or ""))
                or re.search(r"cost|saving|revenue|fee|spend|loss", str(line.get("item") or ""), re.IGNORECASE))


def _sanitize_financial_model(business_case: dict) -> None:
    bc_dict = business_case if isinstance(business_case, dict) else {}
    """Deterministic arithmetic check on the financial model's annualized
    lines: when a line's arithmetic is a plain product of its numbers, the
    printed result must BE that product (allowing an unstated x12/x26/x52/
    x365 period step) — a wrong result is an invented figure wearing perfect
    attribution, so the figure is dropped and the honest arithmetic stays.
    Sums and prose we cannot verify are left for the quality bench."""
    fm = (business_case or {}).get("financial_model")
    if not isinstance(fm, dict):
        return
    for line in fm.get("lines") or []:
        if not isinstance(line, dict):
            continue
        arith = str(line.get("arithmetic") or "")
        annual = str(line.get("annual") or "")
        # additions and spaced subtractions are not plain products — skip
        # (hyphens inside words like "no-shows" are not subtraction)
        if not arith or not annual or "+" in arith or " - " in arith:
            continue
        operands = _numbers_in(arith)
        results = _numbers_in(annual)
        if len(operands) < 2 or not results:
            continue
        product = 1.0
        for v in operands:
            product *= v
        target = results[0]
        if not target:
            continue
        # find the period step the model intended (annualizing x12/x52/...)
        period, rel = min(
            ((p, abs(product * p - target) / abs(target)) for p in (1, 12, 26, 52, 365)),
            key=lambda pair: pair[1],
        )
        if rel <= 0.05:
            # the arithmetic is real, so the printed figure must BE the
            # product to the dollar: a 0.15% drift is still an invented
            # number. Self-repair in place rather than delete.
            if rel > 0.0005:
                m = _NUM_RE.search(annual)
                if m:
                    exact = f"{product * period:,.0f}"
                    line["annual"] = annual[:m.start()] + exact + annual[m.end():]
            line["arithmetic_verified"] = True
        else:
            line["annual"] = ""

    # Scenario impacts must compute from the SAME canonical bases as the
    # lines — a scenario built on a drifted base ($71,064 where the line
    # says $70,956) contradicts the document it sits in. When a scenario's
    # assumption carries one clean fraction and its impact figure matches
    # fraction x some line's exact product within 5%, snap it to the exact
    # value; an unmatchable figure is left for the quality bench.
    bases = []
    for line in fm.get("lines") or []:
        if not isinstance(line, dict):
            continue
        nums = _numbers_in(str(line.get("annual") or ""))
        if nums:
            bases.append(nums[0])
    # Every "$X per <basis>" restatement is verified (or snapped) against
    # the canonical annual claims by the deterministic time-basis engine —
    # run 43's "$1,944/day" against a $194.40 truth is its fixture. Counts
    # of discrete things are rounded whole; the audit trail persists.
    from app.pipeline import timebasis

    claims = []
    for l in fm.get("lines") or []:
        if isinstance(l, dict) and l.get("arithmetic_verified") and _is_money_line(l):
            vals = _numbers_in(str(l.get("annual") or ""))
            if vals:
                claims.append(vals[0])
    _records = []
    coi = bc_dict.get("cost_of_inaction") if isinstance(bc_dict, dict) else None
    if isinstance(coi, str) and coi:
        fixed, recs = timebasis.check_restatements(coi, claims)
        bc_dict["cost_of_inaction"] = timebasis.round_counts(fixed)
        _records += recs
    for sc in fm.get("scenarios") or []:
        if not isinstance(sc, dict):
            continue
        impact = str(sc.get("impact") or "")
        fracs = [v for v in _numbers_in(str(sc.get("assumption") or "")) if 0 < v < 1]
        targets = _numbers_in(impact)
        if not fracs or not targets or not bases:
            continue
        target = targets[0]
        if not target:
            continue
        # multi-mechanism assumptions carry several fractions — the leading
        # dollar figure snaps on whichever (fraction x base) it belongs to
        for base, frac0 in [(b, f) for b in bases for f in fracs]:
            exact = base * frac0
            rel = abs(exact - target) / abs(target) if target else 1.0
            if exact and 0.0005 < rel <= 0.05:
                # snap the result AND any drifted copy of the base itself --
                # the released defect showed "(0.15 * $71,064)" one page
                # after the canonical $70,956
                def _snap(m):
                    vals = _numbers_in(m.group(0))
                    if not vals:
                        return m.group(0)
                    v = vals[0]
                    if abs(v - target) / max(abs(target), 1e-9) <= 0.05:
                        return f"{exact:,.0f}"
                    if v != base and abs(v - base) / max(abs(base), 1e-9) <= 0.05:
                        return f"{base:,.0f}"
                    return m.group(0)

                sc["impact"] = _NUM_RE.sub(_snap, impact)
                sc["impact_verified"] = True
                break
        else:
            if any(abs(base * f - target) / abs(target) <= 0.0005
                   for base in bases for f in fracs):
                sc["impact_verified"] = True
    # the for-else above: an exact match verifies without snapping
    # scenario-verified dollars extend the claim set for the payback note
    for sc in fm.get("scenarios") or []:
        if not isinstance(sc, dict):
            continue
        if sc.get("impact_verified"):
            vals = [v for v in _numbers_in(str(sc.get("impact") or "")) if v > 1]
            if vals:
                claims.append(vals[0])
        if isinstance(sc.get("impact"), str):
            sc["impact"] = timebasis.round_counts(sc["impact"])
    pn = fm.get("payback_note")
    if isinstance(pn, str) and pn:
        fm["payback_note"], recs = timebasis.check_restatements(pn, claims)
        _records += recs
    # every other business-case prose field is held to the same arithmetic,
    # against the FULL claim set (lines + verified scenario impacts): a
    # formula announces the figure it computes, and monthly restatements sit
    # on the package identity (run 49: payback_logic's "25% … ≈ $490")
    if isinstance(bc_dict, dict):
        for key in ("payback_logic",):
            if isinstance(bc_dict.get(key), str) and bc_dict[key]:
                fixed, recs = timebasis.repair_expressions(bc_dict[key])
                _records += recs
                fixed, recs = timebasis.check_restatements(fixed, claims)
                _records += recs
                bc_dict[key] = timebasis.round_counts(fixed)
        for key, field in (("costs_removed", "how"), ("revenue_streams", "description")):
            for it in bc_dict.get(key) or []:
                if isinstance(it, dict) and isinstance(it.get(field), str) and it[field]:
                    fixed, recs = timebasis.repair_expressions(it[field])
                    _records += recs
                    fixed, recs = timebasis.check_restatements(fixed, claims)
                    _records += recs
                    it[field] = timebasis.round_counts(fixed)
    if _records:
        fm["restatements"] = _records
    # An impact component the assumption never promised is stated INTO the
    # assumption with the exact fraction it used — the figure already stands
    # in the impact; the assumption must own it (run 47: 51,100 'where is my
    # order' inquiries at 40% with no 40% promised for them).
    from app.pipeline.structural import unpromised_components

    repairs = []
    for sc in fm.get("scenarios") or []:
        if not isinstance(sc, dict):
            continue
        for u in unpromised_components(sc, fm.get("lines") or []):
            clause = f" and {u['fraction']:.0%} of {u['subject']}"
            if "inquir" in u["subject"] or "order" in u["subject"]:
                clause = f" and resolves {u['fraction']:.0%} of '{u['subject']}' inquiries" if "inquir" not in u["subject"] \
                    else f" and resolves {u['fraction']:.0%} of {u['subject']}"
            assumption = str(sc.get("assumption") or "").rstrip(". ")
            sc["assumption"] = assumption + clause + "."
            repairs.append({"scenario": sc.get("name"), "added": clause.strip(), "for": u["value"]})
    if repairs:
        fm["assumption_repairs"] = repairs
    # A scenario's arithmetic field is DERIVED from its verified components
    # (fraction x line = figure) — never the model's own, which run 47 wrote
    # as 127,750 x 0.20 beside an impact that said 51,100 (40%).
    line_items = []
    for line in fm.get("lines") or []:
        if isinstance(line, dict):
            nums = _numbers_in(str(line.get("annual") or ""))
            if nums:
                line_items.append((nums[0], str(line.get("item") or "")))
    for sc in fm.get("scenarios") or []:
        if not isinstance(sc, dict) or not sc.get("impact_verified"):
            continue
        fracs = [v for v in _numbers_in(str(sc.get("assumption") or "")) if 0 < v < 1]
        parts = []
        for v in _numbers_in(str(sc.get("impact") or "")):
            if v <= 1:
                continue
            hit = next(((f, base, item) for f in fracs for base, item in line_items
                        if base and abs(base * f - v) / max(v, 1e-9) <= 0.005), None)
            if hit:
                f, base, item = hit
                parts.append(f"{base:,.0f} x {f:.0%} = {v:,.0f} ({item})")
        if parts:
            sc["arithmetic"] = "; ".join(parts)
        else:
            sc.pop("arithmetic", None)


def _format_owner_numbers(req: Request) -> str:
    """The discovery Q&A as prompt lines. 'none provided' rather than an
    empty block — the prompt's number rules key off whether real numbers
    exist, and the model must be able to tell."""
    if not req.ops_numbers_json:
        return "none provided"
    try:
        pairs = json.loads(req.ops_numbers_json)
    except ValueError:
        return "none provided"
    lines = [
        f"- {p.get('question')}: {p.get('answer')}"
        for p in pairs
        if isinstance(p, dict) and p.get("question") and p.get("answer")
    ]
    return "\n".join(lines) or "none provided"


def _clamp_modules(modules: list) -> list:
    """Soft bounds, same pattern as roles: trust the model's count, step in
    only on a degenerate or runaway answer."""
    cleaned = [m for m in modules if isinstance(m, dict) and m.get("name")]
    return cleaned[: settings.MAX_MODULES_PER_REQUEST]


def decompose_business(
    db: Session, request_id: int, analysis: dict, consult_result: dict, plan_result: dict,
    feedback: list[str] | None = None,
) -> dict | None:
    """Break the product into modules + business case, then deep-spec each
    module with its own call (in parallel — they are independent).

    Returns {"modules": [...], "business_case": {...}} with each module
    carrying its deep spec under "spec" (None when that one call failed),
    or None when the decomposition call itself failed.
    """
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    try:
        prompt = render(
            "decompose.j2",
            business_name=req.business_name or "",
            business_description=req.business_description or "",
            industry=req.industry or "unspecified",
            revenue_today=req.revenue_today or "not stated — infer carefully from the business type, and say so",
            main_problem=req.main_problem or "unspecified",
            desired_outcome=req.desired_outcome or "unspecified",
            site_research=_format_site_research(req),
            operating_stage=req.operating_stage or "operating",
            owner_numbers=_format_owner_numbers(req),
            engagement_register=build_engagement_register(
                req.engagement_type, req.needs_ai, req.main_problem, req.desired_outcome,
            req.business_description,
            ),
            business_model=analysis.get("business_model", "Unknown"),
            target_customer_profile=analysis.get("target_customer_profile", ""),
            pain_points=json.dumps(analysis.get("pain_points", [])),
            growth_opportunity=analysis.get("growth_opportunity", ""),
            consulting_summary=consult_result.get("consulting_summary", ""),
            recommended_ai_employees=json.dumps(consult_result.get("recommended_ai_employees", [])),
            recommended_features=json.dumps(consult_result.get("recommended_features", [])),
            concept_name=plan_result.get("concept_name", req.business_name or ""),
            min_modules=settings.MIN_MODULES_PER_REQUEST,
            max_modules=settings.MAX_MODULES_PER_REQUEST,
            preflight_feedback="\n".join(f"- {f}" for f in (feedback or [])),
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=6400)
        content = body["choices"][0]["message"]["content"]
        result = extract_json_from_text(content)
        modules = _clamp_modules(result.get("modules") or [])
        business_case = result.get("business_case") or {}
        _sanitize_financial_model(business_case)
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="decompose",
            usage=body.get("usage"), success=True,
        )
    except Exception as exc:
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="decompose",
            success=False, error=str(exc)[:500],
        )
        return None

    if not modules:
        logger.warning("decomposition returned no usable modules: request=%s", request_id)
        return None

    # Deep-spec each module with its own dedicated call. The calls are pure
    # HTTP and independent, so they run in parallel — but the DB session is
    # not thread-safe, so: usage is collected in-thread and ledgered here on
    # the request thread afterwards, and the request's fields are snapshotted
    # into plain strings BEFORE any thread starts. The commit inside
    # log_usage expires the ORM instance, so touching req.<attr> from a
    # worker thread triggers a concurrent refresh on the shared session —
    # seen failing 3 of 4 parallel calls with "concurrent operations are
    # not permitted".
    site_research = _format_site_research(req)
    biz_name = req.business_name or ""
    biz_desc = req.business_description or ""

    def _spec_one(module: dict) -> tuple[dict | None, dict | None, str | None]:
        others = "\n".join(
            f"- {m.get('name')}: {m.get('purpose', '')}" for m in modules if m is not module
        ) or "none"
        try:
            spec_prompt = render(
                "module_spec.j2",
                business_name=biz_name,
                business_description=biz_desc,
                site_research=site_research,
                target_customer_profile=analysis.get("target_customer_profile", ""),
                module_id=module.get("id") or "module",
                module_name=module.get("name") or "",
                module_purpose=module.get("purpose") or "",
                module_users=json.dumps(module.get("users") or []),
                module_pain_point=module.get("pain_point_addressed") or "",
                pilot_gate=json.dumps(business_case.get("pilot_gate") or "") if isinstance(business_case, dict) else '""',
                other_modules=others,
            )
            body = provider.chat(
                settings.ANALYSIS_MODEL, [{"role": "user", "content": spec_prompt}], max_tokens=2000,
            )
            return extract_json_from_text(body["choices"][0]["message"]["content"]), body.get("usage"), None
        except Exception as exc:  # one module's spec failing must not sink the rest
            return None, None, str(exc)[:500]

    with ThreadPoolExecutor(max_workers=min(4, len(modules))) as pool:
        results = list(pool.map(_spec_one, modules))

    for module, (spec, usage, error) in zip(modules, results):
        module["spec"] = spec
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="module_spec",
            usage=usage, success=error is None, error=error,
        )

    # Second pass: the TECHNICAL anatomy of each module — data model, and
    # for AI-bearing modules the agent's brain/tools/memory/guardrails/
    # escalation/evaluation. Its own dedicated call per module, fed that
    # module's business spec, so the technical plan downstream is written
    # from engineering facts rather than improvising them.
    def _tech_one(module: dict) -> tuple[dict | None, dict | None, str | None]:
        others = "\n".join(
            f"- {m.get('name')}: {m.get('purpose', '')}" for m in modules if m is not module
        ) or "none"
        try:
            tech_prompt = render(
                "tech_spec.j2",
                business_name=biz_name,
                business_description=biz_desc,
                module_id=module.get("id") or "module",
                module_name=module.get("name") or "",
                module_purpose=module.get("purpose") or "",
                module_spec=json.dumps(module.get("spec") or {}, indent=1),
                other_modules=others,
            )
            body = provider.chat(
                settings.ANALYSIS_MODEL, [{"role": "user", "content": tech_prompt}], max_tokens=3200,
            )
            return extract_json_from_text(body["choices"][0]["message"]["content"]), body.get("usage"), None
        except Exception as exc:
            return None, None, str(exc)[:500]

    with ThreadPoolExecutor(max_workers=min(4, len(modules))) as pool:
        tech_results = list(pool.map(_tech_one, modules))

    for module, (tech, usage, error) in zip(modules, tech_results):
        module["tech"] = tech
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="tech_spec",
            usage=usage, success=error is None, error=error,
        )

    # The typed claim registry: client facts, verified derivations, the
    # canonical pilot gate, typed/labeled technical thresholds, registry-
    # rendered module KPI statements and honest pilot-module names — applied
    # to the structures BEFORE any prose is written from them.
    from app.pipeline import registry as _registry

    reg = _registry.build_registry(
        req.ops_numbers_json, business_case, modules,
        free_texts=[req.business_description or "", req.main_problem or "",
                    req.desired_outcome or "", req.revenue_today or ""],
    )
    req.registry_json = json.dumps(reg)
    req.modules_json = json.dumps(modules)
    req.business_case_json = json.dumps(business_case)
    db.commit()
    return {"modules": modules, "business_case": business_case, "registry": reg}
