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
import re
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import build_engagement_register, extract_json_from_text, log_usage
from app.pipeline.decompose import _format_owner_numbers
from app.templating import render

logger = logging.getLogger("consultant.extras")


def canonicalize_layers(procedures: list, by_name: dict, modules: list,
                        registry: dict | None, gate: dict | None) -> list:
    """Apply the registry to the operations layers in place. Pure data
    transformation — no model call — so it is testable on fixtures."""
    from app.pipeline import pilot_gate as _pg
    from app.pipeline import registry as _registry

    claims = (registry or {}).get("claims") or []
    counter = {"n": sum(1 for c in claims if str(c.get("id", "")).startswith("TH-"))}
    renames = [(r["from"], r["to"]) for r in ((registry or {}).get("renames") or []) if r.get("from") and r.get("to")]

    policy_notes: list[dict] = []

    def _fix(s):
        if not isinstance(s, str):
            return s
        s, _ = _pg.enforce(s, gate)
        for old, new in renames:
            s = s.replace(old, new)
        s, notes = _registry.policy_pass(s, claims)
        policy_notes.extend({"source": "operations layers", "note": n} for n in notes)
        return _registry.resolve_module_ids(s, modules)

    ai_names = [str(m.get("client_facing_name") or m.get("name") or "") for m in (modules or [])
                if isinstance(m, dict) and (m.get("automation_level") == "ai" or (m.get("spec") or {}).get("ai"))]
    later_names = [str(m.get("client_facing_name") or m.get("name") or "") for m in (modules or [])
                   if isinstance(m, dict) and not m.get("pilot")]

    # a later module a customer uses stands in as the customer-facing pilot
    # form; a staff module as the internal queue
    stand_in = {}
    for m in modules or []:
        if isinstance(m, dict) and not m.get("pilot"):
            users = " ".join(str(u) for u in (m.get("users") or []))
            form = bool(_registry._CUSTOMER_USER.search(users)) and not _registry._STAFF_ONLY.search(users)
            for nm in (m.get("client_facing_name"), m.get("name"), m.get("original_name")):
                if nm:
                    stand_in[str(nm)] = _pg.PILOT_CUSTOMER_FORM if form else _pg.PILOT_TOOLING

    def _pilot_tooling(s):
        # a pilot-state step runs with today's tools: a later-phase or AI
        # module named in it becomes the lightweight pilot tooling
        if not isinstance(s, str):
            return s
        for n in sorted(set(ai_names + later_names), key=len, reverse=True):
            if n:
                s = s.replace(n, stand_in.get(n, _pg.PILOT_TOOLING))
        return s

    pilot_only_names = {str(m.get("client_facing_name") or m.get("name") or "") for m in (modules or [])
                        if isinstance(m, dict) and m.get("pilot")}
    pilot_module_names = pilot_only_names | {"The pilot"}
    design_records: list[dict] = []
    ai_records: list[dict] = []
    channel_records: list[dict] = []
    population_records: list[dict] = []
    # ONE pilot procedure set: the pilot SOP; module-level pilot procedures
    # that restate it are removed (recorded)
    consolidated = _registry.consolidate_pilot_procedures(procedures, pilot_only_names)
    # the SOP's attempt total governs the pilot module's own strings — and,
    # through the registry, the prose every volume is finished with
    attempt_records = _registry.pilot_attempts_pass(modules, procedures)
    if registry is not None:
        registry["pilot_attempt_total"] = _registry.sop_attempt_total(procedures)

    def _pilot_scrub(s, where: str):
        # a pilot-phase step runs with today's tools, the pilot's rules and its
        # human operator, on the canonical randomized design, for the gate's
        # population; a customer never receives the internal queue
        if not isinstance(s, str):
            return s
        fixed = _pilot_tooling(s)
        scrubbed = _registry.scrub_ai_logic(fixed, _pg.PILOT_OPERATOR)
        if scrubbed != fixed:
            ai_records.append({"where": where, "original": fixed[:160], "replaced_with": scrubbed[:160]})
        fixed = scrubbed
        fixed, recs = _pg.enforce_design(fixed, gate)
        design_records.extend({"where": where, **r} for r in recs)
        fixed, recs = _registry.customer_facing_pass(fixed)
        channel_records.extend({"where": where, **r} for r in recs)
        fixed, recs = _registry.population_pass(fixed, gate, (registry or {}).get("service_types"))
        population_records.extend({"where": where, **r} for r in recs)
        return fixed

    for p in procedures or []:
        if not isinstance(p, dict):
            continue
        for key in ("name", "trigger", "module"):
            p[key] = _fix(p.get(key))
        if str(p.get("phase") or "").lower() == "pilot" and p.get("module") in pilot_module_names:
            where = f"procedures: {p.get('name')}"
            p["trigger"] = _pilot_scrub(p.get("trigger"), where)
            for st in p.get("steps") or []:
                if isinstance(st, dict):
                    st["step"] = _pilot_scrub(st.get("step"), where)
                    if str(st.get("actor") or "").strip().lower() in ("ai", "the ai", "ai agent", "the ai agent") \
                            or st.get("actor") in ai_names:
                        st["actor"] = _pg.PILOT_OPERATOR
            for ex in p.get("exceptions") or []:
                if isinstance(ex, dict):
                    ex["when"], ex["then"] = _pilot_scrub(ex.get("when"), where), _pilot_scrub(ex.get("then"), where)
        for st in p.get("steps") or []:
            if isinstance(st, dict):
                st["step"] = _fix(st.get("step"))
                # run 47 put a module id in the actor field — resolve it too
                st["actor"] = _fix(st.get("actor"))
        for ex in p.get("exceptions") or []:
            if isinstance(ex, dict):
                ex["when"], ex["then"] = _fix(ex.get("when")), _fix(ex.get("then"))
        # a "pilot" procedure that needs an AI actor or an AI module cannot run
        # in the pilot — it is honestly a FUTURE procedure
        if str(p.get("phase") or "").lower() == "pilot" and p.get("module") != "The pilot":
            text = " ".join([str(p.get("trigger") or "")] + [str(s.get("step") or "") + " " + str(s.get("actor") or "")
                                                              for s in p.get("steps") or [] if isinstance(s, dict)])
            actors = [str(s.get("actor") or "").strip().lower() for s in p.get("steps") or [] if isinstance(s, dict)]
            if "ai" in actors or any(n and n in text for n in ai_names):
                p["phase"] = "future"
                p["phase_note"] = "re-phased from pilot: depends on an AI actor or module that must be built first"
    new_claims = _registry.type_procedures(procedures or [], claims, counter) if registry is not None else []

    checklists = (by_name.get("checklists") or {})
    for c in checklists.get("checklists") or []:
        if isinstance(c, dict):
            items = []
            for it in c.get("items") or []:
                it = _fix(it)
                it, more = _registry.threshold_pass(it, claims, source="checklists.items",
                                                    module_id="checklist", counter=counter)
                for cc in more:
                    cc["type"] = "operational_policy" if cc["type"] in ("proposed_threshold", "timing_sla") else cc["type"]
                new_claims += more
                items.append(it)
            c["items"] = items
    for f in checklists.get("forms") or []:
        if isinstance(f, dict):
            f["purpose"] = _fix(f.get("purpose"))

    gov = by_name.get("governance") or {}
    if gov.get("scoreboard"):
        metric_terms = {w for w in re.findall(r"[a-z]+", str((gate or {}).get("primary_metric") or "").lower()) if len(w) > 3}
        canon = _pg.canonical_sentence(gate) if gate else ""
        vals = _registry.claim_values(registry) if registry else []
        kpi_vals = [(v, c, cid) for v, c, cid in vals
                    if cid == "PG" or "*" in (c.get("allowed_sections") or []) or str(c.get("type")) in ("pilot_gate", "module_kpi")]
        for row in gov["scoreboard"]:
            if not isinstance(row, dict):
                continue
            for key in ("metric", "baseline", "target", "formula"):
                row[key] = _fix(row.get(key))
            words = set(re.findall(r"[a-z]+", str(row.get("metric") or "").lower()))
            if gate and metric_terms and len(metric_terms & words) >= max(2, len(metric_terms) - 1):
                row["target"] = canon
                row["baseline"] = (str(gate.get("baseline") or "measure in week 1")
                                   + (" (your figure)" if gate.get("baseline_source") == "client" else ""))
                continue
            # the scoreboard's targets obey the module-KPI law: a number that
            # is not a client figure, a scenario assumption or the gate is
            # coinage — the row keeps its direction and measures in week one
            target = str(row.get("target") or "")
            coined = [tok + (unit if unit == "%" else (" " + unit if unit else ""))
                      for tok, v, unit, _, _ in _registry._numbers(target)
                      if registry and not _registry._value_registered(v, unit, kpi_vals)]
            if coined:
                direction = re.match(r"\s*(down|up|lower|higher|fewer|more|decrease|increase|reduce)\w*", target, re.IGNORECASE)
                row["target"] = ((direction.group(1).capitalize() + " — ") if direction else "") + \
                    "target to be established during week-one measurement"
                row["target_note"] = f"coined figure(s) removed: {', '.join(coined)}"
    journey = by_name.get("journey") or {}
    for s in journey.get("stages") or []:
        if isinstance(s, dict):
            for key in ("customer_action", "frontstage", "fail_point_removed"):
                s[key] = _fix(s.get(key))
    org = by_name.get("organization") or {}
    pilot_names = [str(m.get("client_facing_name") or m.get("name") or "") for m in (modules or [])
                   if isinstance(m, dict) and m.get("pilot")]
    roles_out = []
    for r in org.get("roles") or []:
        if isinstance(r, dict):
            r["responsibilities"] = [_fix(x) for x in (r.get("responsibilities") or [])]
            r["decides_alone"], r["hands_off"] = _fix(r.get("decides_alone")), _fix(r.get("hands_off"))
            # the Phase-1 pilot is not a person and not an AI: the role that
            # runs it is the human Pilot Support Operator
            if any(pn and pn in str(r.get("role") or "") for pn in pilot_names):
                r["role"] = _pg.PILOT_OPERATOR
                r["type"] = "human"
                r["responsibilities"] = [re.sub(r"\b(?:the )?AI\b", "the operator", x) for x in r["responsibilities"]]
                if str(r.get("decides_alone") or "").startswith("Does not decide autonomously"):
                    r["decides_alone"] = "Which pilot conversations to escalate and how to log each outcome."
                if str(r.get("hands_off") or "").startswith("Hands every action"):
                    r["hands_off"] = "Any customer complaint or unresolved address after the approved maximum number of attempts — to the operations lead."
            # an AI role's empty decision right is stated as the constraint it
            # is — never the literal "Null" (the renderer's rule, applied to the data)
            if r.get("type") == "ai":
                for key, default in (("decides_alone", "Does not decide autonomously — proposes, a human approves."),
                                     ("hands_off", "Hands every action to a human for approval.")):
                    v = str(r.get(key) or "").strip()
                    if not v or v.lower() in ("null", "none", "n/a", "-", "nothing"):
                        r[key] = default
            roles_out.append(r)
    seen_roles = set()
    if org.get("roles") is not None:
        org["roles"] = [r for r in roles_out if not (str(r.get("role")) in seen_roles or seen_roles.add(str(r.get("role"))))]
    for c in org.get("change_impact") or []:
        if isinstance(c, dict) and any(pn and pn in str(c.get("role") or "") for pn in pilot_names):
            c["role"] = _pg.PILOT_OPERATOR
    # Phase-1 risk language never speaks of AI: the pilot is rules-based and
    # human-reviewed, so a risk about the pilot is a risk about its workflow
    for rk in (gov.get("risks") or []):
        if isinstance(rk, dict):
            pilot_risk = any(pn and pn in (str(rk.get("risk") or "") + " " + str(rk.get("mitigation") or ""))
                             for pn in pilot_names)
            for key in ("risk", "mitigation", "who_feels_it"):
                s = _fix(rk.get(key))
                if isinstance(s, str) and pilot_risk:
                    s = re.sub(r"\bAI-(?:handled|driven|powered|operated|generated)\b", "pilot-workflow", s)
                    s = re.sub(r"\bthe AI\b", "the pilot workflow", s)
                    s = re.sub(r"\bAI\b", "the rules-based workflow", s)
                if isinstance(s, str) and key == "mitigation":
                    # a proposed duration in a counter-move ("for the first 2 weeks") is labeled like any other
                    s, more = _registry.threshold_pass(s, claims, source="risks.mitigation", module_id="risk", counter=counter)
                    new_claims += more
                rk[key] = s
    if registry is not None:
        if new_claims:
            registry.setdefault("claims", []).extend(new_claims)
            registry["errors"] = _registry.validate_registry(registry)
        if design_records:
            registry.setdefault("pilot_design_corrections", []).extend(design_records)
        if ai_records:
            registry.setdefault("pilot_ai_removed", []).extend(ai_records)
        if policy_notes:
            registry.setdefault("policy_corrections", []).extend(policy_notes)
        if consolidated:
            registry.setdefault("pilot_procedures_consolidated", []).extend(consolidated)
        if attempt_records:
            registry.setdefault("pilot_attempt_corrections", []).extend(attempt_records)
            registry["_modules_changed"] = True
        if channel_records:
            registry.setdefault("customer_channel_corrections", []).extend(channel_records)
        if population_records:
            registry.setdefault("population_corrections", []).extend(population_records)
        if counter.get("operating_time_labels"):
            registry.setdefault("operating_time_labels", []).extend(counter["operating_time_labels"])
    return procedures


def build_extras(db: Session, request_id: int, analysis: dict, decomposition: dict | None,
                 only: set[str] | None = None) -> None:
    """Build the consultancy layers. With `only` (task names such as
    {"procedures:pilot"}), run just those calls and merge their output into
    the layers already on the row — the retry path for one failed layer."""
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
            req.business_description,
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
    pilot_gate = business_case.get("pilot_gate") if isinstance(business_case, dict) else None
    from app.pipeline import registry as _registry

    registry = (decomposition or {}).get("registry") or _registry.registry_for(req) or {}
    gate_sentence = registry.get("pilot_gate_sentence") or ""

    def _pilot() -> dict | None:
        prompt = render(
            "pilot_sop.j2",
            business_name=biz_name,
            business_description=biz_desc,
            pilot_gate=json.dumps(pilot_gate, indent=1),
            pilot_gate_sentence=gate_sentence,
            modules=slim,
            engagement_register=register,
        )
        # four procedures x eight steps x exceptions ran past 2600 tokens twice
        # (runs 47 and 49: JSON cut mid-object at ~10.8k characters)
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=4200)
        result = extract_json_from_text(body["choices"][0]["message"]["content"])
        procs = []
        for p in result.get("procedures") or []:
            if not (isinstance(p, dict) and p.get("name")):
                continue
            # a manual pilot has no AI actors, whatever the model says
            steps = [s for s in (p.get("steps") or [])
                     if isinstance(s, dict) and s.get("step")
                     and str(s.get("actor") or "").strip().lower() != "ai"]
            if not steps:
                continue
            p["steps"] = steps[:8]
            p["exceptions"] = [e for e in (p.get("exceptions") or []) if isinstance(e, dict) and e.get("when")][:3]
            p["phase"] = "pilot"
            p["module"] = "The pilot"
            procs.append(p)
        if not procs:
            raise ValueError("no valid pilot procedures")
        return {"payload": {"procedures": procs[:4]}, "usage": body.get("usage")}

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
            pilot_gate_sentence=gate_sentence,
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
    ] + ([("procedures:pilot", _pilot)] if pilot_gate else []) + [
        (f"procedures:{m.get('id') or i}", _procedures_for(m))
        for i, m in enumerate(modules)
    ]

    if only:
        tasks = [t for t in tasks if t[0] in only]
        if not tasks and "__canonicalize__" not in only:
            return

    def _guarded(item):
        name, fn = item
        try:
            return name, fn(), None
        except Exception as exc:  # each layer fails open alone
            return name, None, str(exc)[:500]

    results = []
    if tasks:
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
    if only:
        # a partial rebuild keeps every existing layer and splices the new
        # procedures in front of the library already on the row
        existing = (json.loads(req.procedures_json) if req.procedures_json else {}).get("procedures") or []
        fresh_modules = {p.get("module") for p in procedure_library}
        procedure_library = procedure_library + [p for p in existing if p.get("module") not in fresh_modules]
        for layer, attr in (("journey", "journey_json"), ("organization", "org_json"), ("checklists", "checklists_json")):
            if not by_name.get(layer) and getattr(req, attr, None):
                by_name[layer] = json.loads(getattr(req, attr))
        if not by_name.get("governance") and req.scoreboard_json:
            by_name["governance"] = {"scoreboard": json.loads(req.scoreboard_json),
                                     "risks": json.loads(req.risks_json) if req.risks_json else []}
    # The registry's deterministic passes over the operations layers: the
    # canonical gate sentence replaces the token and every paraphrase, raw
    # ids resolve to names, waits/retries/cut-offs are typed and labeled,
    # and the scoreboard's gate row is the canonical sentence itself.
    gate_obj = registry.get("pilot_gate") if registry else None
    procedure_library = canonicalize_layers(
        procedure_library, by_name, modules, registry, gate_obj)
    if procedure_library:
        by_name["procedures"] = {"procedures": procedure_library}
    if registry:
        # the canonicalizer aligned the pilot module's own strings with its SOP
        if registry.pop("_modules_changed", None) and modules:
            req.modules_json = json.dumps(modules)
        req.registry_json = json.dumps(registry)
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
