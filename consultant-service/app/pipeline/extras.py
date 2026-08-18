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
from app.pipeline._shared import extract_json_from_text, log_usage
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
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=1600)
        result = extract_json_from_text(body["choices"][0]["message"]["content"])
        scoreboard = [r for r in (result.get("scoreboard") or []) if isinstance(r, dict) and r.get("metric")][:7]
        risks = [r for r in (result.get("risks") or []) if isinstance(r, dict) and r.get("risk")][:5]
        if not scoreboard and not risks:
            raise ValueError("governance had neither scoreboard nor risks")
        return {"payload": {"scoreboard": scoreboard, "risks": risks}, "usage": body.get("usage")}

    def _procedures() -> dict | None:
        prompt = render(
            "procedures.j2",
            business_name=biz_name,
            business_description=biz_desc,
            revenue_today=revenue_today,
            modules=slim,
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=2200)
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
            procs.append(p)
        if not procs:
            raise ValueError("no valid procedures")
        return {"payload": {"procedures": procs[:5]}, "usage": body.get("usage")}

    tasks = [("journey", _journey), ("governance", _governance), ("procedures", _procedures)]

    def _guarded(item):
        name, fn = item
        try:
            return name, fn(), None
        except Exception as exc:  # each layer fails open alone
            return name, None, str(exc)[:500]

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(_guarded, tasks))

    for name, result, error in results:
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose=name,
            usage=(result or {}).get("usage"), success=error is None, error=error,
        )
        if error is not None:
            logger.warning("extras layer %s failed open: request=%s error=%s", name, request_id, error)

    by_name = {name: (result or {}).get("payload") for name, result, _ in results}
    if by_name.get("journey"):
        req.journey_json = json.dumps(by_name["journey"])
    gov = by_name.get("governance") or {}
    if gov.get("scoreboard"):
        req.scoreboard_json = json.dumps(gov["scoreboard"])
    if gov.get("risks"):
        req.risks_json = json.dumps(gov["risks"])
    if by_name.get("procedures"):
        req.procedures_json = json.dumps(by_name["procedures"])
    db.commit()
