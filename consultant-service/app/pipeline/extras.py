"""The blueprint's consultancy layers — journey, governance, procedures.

Three independent calls that turn the decomposition into the sections a
real consulting deliverable carries beyond the documents themselves:

- the service-blueprint JOURNEY (where each module lives in the
  customer's experience, frontstage vs backstage),
- the GOVERNANCE layer (a KPI scoreboard whose baselines are only ever
  the owner's own numbers or "measure in week 1", plus the risk
  register), and
- the franchise-manual PROCEDURES (trigger -> numbered steps ->
  exceptions, one actor per step).

They run in parallel — pure HTTP, independent — under the same thread
rules decompose.py learned the hard way: request fields are snapshotted
to plain strings BEFORE any thread starts, and usage is ledgered
afterwards on the request thread. Each call fails open alone: a missing
journey never costs the client their scoreboard, and nothing here can
kill the request.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import build_engagement_register, extract_json_from_text, log_usage
from app.pipeline.decompose import _format_owner_numbers
from app.templating import render

logger = logging.getLogger("consultant.extras")


def build_extras(db: Session, request_id: int, analysis: dict, decomposition: dict | None) -> None:
    req = db.get(Request, request_id)
    if req is None:
        return

    modules = (decomposition or {}).get("modules") or []
    business_case = (decomposition or {}).get("business_case") or {}
    if not modules:
        # Nothing to shape from — the documents' own fallback path is
        # already carrying this request.
        return

    module_ids = {m.get("id") for m in modules if isinstance(m, dict) and m.get("id")}

    # Snapshots — commits inside log_usage expire ORM instances, so worker
    # threads must never touch req.<attr> (see decompose.py).
    biz_name = req.business_name or ""
    biz_desc = req.business_description or ""
    revenue_today = req.revenue_today or "not stated"
    owner_numbers = _format_owner_numbers(req)
    operating_stage = req.operating_stage or "operating"
    register = build_engagement_register(
        req.engagement_type, req.needs_ai, req.main_problem, req.desired_outcome,
    )

    # Slim module context: the full deep specs would triple every prompt;
    # id/name/purpose/ai/kpis is what these three layers actually consume.
    slim = json.dumps(
        [
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "purpose": m.get("purpose"),
                "users": m.get("users"),
                "ai": (m.get("spec") or {}).get("ai"),
                "kpis": (m.get("spec") or {}).get("kpis") or [],
            }
            for m in modules
        ],
        indent=1,
    )
    bc_json = json.dumps(business_case, indent=1)

    def _journey() -> dict | None:
        prompt = render(
            "journey.j2",
            business_name=biz_name,
            business_description=biz_desc,
            target_customer_profile=analysis.get("target_customer_profile", ""),
            pain_points=json.dumps(analysis.get("pain_points", [])),
            modules=slim,
            engagement_register=register,
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=1500)
        result = extract_json_from_text(body["choices"][0]["message"]["content"])
        stages = []
        for s in result.get("stages") or []:
            if not (isinstance(s, dict) and s.get("stage")):
                continue
            s["backstage_modules"] = [m for m in (s.get("backstage_modules") or []) if m in module_ids]
            stages.append(s)
        if not stages:
            raise ValueError("journey had no valid stages")
        return {"payload": {"stages": stages[:6]}, "usage": body.get("usage")}

    def _governance() -> dict | None:
        prompt = render(
            "governance.j2",
            business_name=biz_name,
            business_description=biz_desc,
            operating_stage=operating_stage,
            owner_numbers=owner_numbers,
            modules=slim,
            business_case=bc_json,
            engagement_register=register,
        )
        # Seven scoreboard rows + five risks occasionally truncated at 1600.
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=2400)
        result = extract_json_from_text(body["choices"][0]["message"]["content"])
        scoreboard = [r for r in (result.get("scoreboard") or []) if isinstance(r, dict) and r.get("metric")][:7]
        risks = [r for r in (result.get("risks") or []) if isinstance(r, dict) and r.get("risk")][:5]
        if not scoreboard and not risks:
            raise ValueError("governance had neither scoreboard nor risks")
        return {"payload": {"scoreboard": scoreboard, "risks": risks}, "usage": body.get("usage")}

    def _procedures_for(module: dict):
        """Factory: one SOP call per module — the franchise-manual library
        is built module by module, 2-3 procedures each."""
        module_name = module.get("name") or ""
        module_json = json.dumps(
            {k: module.get(k) for k in ("id", "name", "purpose", "users", "spec")}, indent=1,
        )
        others = "\n".join(
            f"- {m.get('name')}: {m.get('purpose', '')}" for m in modules if m is not module
        ) or "none"

        def _call() -> dict | None:
            prompt = render(
                "procedures.j2",
                business_name=biz_name,
                business_description=biz_desc,
                revenue_today=revenue_today,
                module=module_json,
                other_modules=others,
                engagement_register=register,
            )
            body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=1800)
            result = extract_json_from_text(body["choices"][0]["message"]["content"])
            procs = []
            for p in result.get("procedures") or []:
                if not (isinstance(p, dict) and p.get("name")):
                    continue
                steps = [s for s in (p.get("steps") or []) if isinstance(s, dict) and s.get("step")]
                if not steps:
                    continue
                p["steps"] = steps[:8]
                p["exceptions"] = [e for e in (p.get("exceptions") or []) if isinstance(e, dict) and e.get("when")][:3]
                p["module"] = module_name
                procs.append(p)
            if not procs:
                raise ValueError("no valid procedures")
            return {"payload": {"procedures": procs[:3]}, "usage": body.get("usage")}

        return _call

    def _checklists() -> dict | None:
        prompt = render(
            "checklists.j2",
            business_name=biz_name,
            business_description=biz_desc,
            modules=slim,
            engagement_register=register,
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=2200)
        result = extract_json_from_text(body["choices"][0]["message"]["content"])
        checklists = []
        for c in result.get("checklists") or []:
            if not (isinstance(c, dict) and c.get("name")):
                continue
            items = [str(i) for i in (c.get("items") or []) if i][:10]
            if not items:
                continue
            c["items"] = items
            checklists.append(c)
        forms = []
        for f in result.get("forms") or []:
            if not (isinstance(f, dict) and f.get("name")):
                continue
            fields = [str(i) for i in (f.get("fields") or []) if i][:10]
            if not fields:
                continue
            f["fields"] = fields
            forms.append(f)
        if not checklists and not forms:
            raise ValueError("checklists call produced nothing valid")
        return {"payload": {"checklists": checklists[:6], "forms": forms[:4]}, "usage": body.get("usage")}

    def _organization() -> dict | None:
        prompt = render(
            "organization.j2",
            business_name=biz_name,
            business_description=biz_desc,
            modules=slim,
            engagement_register=register,
        )
        # Twelve roles with responsibilities run long — 1800 tokens was seen
        # truncating mid-JSON on a 5-module business.
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=3000)
        result = extract_json_from_text(body["choices"][0]["message"]["content"])
        roles = [r for r in (result.get("roles") or []) if isinstance(r, dict) and r.get("role")][:12]
        impact = [c for c in (result.get("change_impact") or []) if isinstance(c, dict) and c.get("role")][:8]
        if not roles:
            raise ValueError("organization had no valid roles")
        return {"payload": {"roles": roles, "change_impact": impact}, "usage": body.get("usage")}

    tasks = [
        ("journey", _journey),
        ("governance", _governance),
        ("organization", _organization),
        ("checklists", _checklists),
    ] + [
        (f"procedures:{m.get('id') or i}", _procedures_for(m))
        for i, m in enumerate(modules)
    ]

    def _guarded(item):
        name, fn = item
        try:
            return name, fn(), None
        except Exception as exc:  # each layer fails open alone
            return name, None, str(exc)[:500]

    with ThreadPoolExecutor(max_workers=min(6, len(tasks))) as pool:
        results = list(pool.map(_guarded, tasks))

    for name, result, error in results:
        log_usage(
            db, request_id,
            # per-module SOP calls all ledger under one purpose
            provider="openrouter", model=settings.ANALYSIS_MODEL,
            purpose="procedures" if name.startswith("procedures:") else name,
            usage=(result or {}).get("usage"), success=error is None, error=error,
        )
        if error is not None:
            logger.warning("extras layer %s failed open: request=%s error=%s", name, request_id, error)

    by_name = {name: (result or {}).get("payload") for name, result, _ in results}
    # Merge the per-module SOP calls into one library, module order kept.
    procedure_library = []
    for name, result, _ in results:
        if name.startswith("procedures:") and result:
            procedure_library.extend(result["payload"]["procedures"])
    if procedure_library:
        by_name["procedures"] = {"procedures": procedure_library}
    if by_name.get("journey"):
        req.journey_json = json.dumps(by_name["journey"])
    gov = by_name.get("governance") or {}
    if gov.get("scoreboard"):
        req.scoreboard_json = json.dumps(gov["scoreboard"])
    if gov.get("risks"):
        req.risks_json = json.dumps(gov["risks"])
    if by_name.get("procedures"):
        req.procedures_json = json.dumps(by_name["procedures"])
    if by_name.get("organization"):
        req.org_json = json.dumps(by_name["organization"])
    if by_name.get("checklists"):
        req.checklists_json = json.dumps(by_name["checklists"])
    db.commit()
