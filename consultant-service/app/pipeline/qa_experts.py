"""The quality bench — expert AI auditors that review the finished text
deliverables before the human review gate.

Two auditors run in parallel: the NUMBERS auditor (every figure traces
to a client input, attributed, with explicit conservative assumptions)
and the STRUCTURE auditor (canonical sections present, documents
consistent with the structured layers, scope obeys the register). Their
verdicts persist as the run's quality report — shown to the reviewing
human, and surfaced to the waiting client as the review checklist.

When the auditors flag anything, the SENIOR PARTNER pass applies
surgical fixes to the blueprint — only what was flagged plus mechanical
defects, guarded hard: if the corrected document loses headings or
drifts in size, the original stands. Everything here fails open; a
quality pass that dies never costs the client their engagement.
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

logger = logging.getLogger("consultant.qa_experts")

_REQUIRED_HEADINGS = ("## The decision", "## Executive summary", "## How this makes money")


def _sanitize_report(result: dict) -> dict:
    checks = [
        {"label": str(c.get("label"))[:120], "passed": bool(c.get("passed")), "note": str(c.get("note") or "")[:300]}
        for c in (result.get("checks") or []) if isinstance(c, dict) and c.get("label")
    ]
    findings = [
        {
            "severity": c.get("severity") if c.get("severity") in ("high", "low") else "low",
            "where": str(c.get("where") or "")[:200],
            "issue": str(c.get("issue") or "")[:400],
            "fix": str(c.get("fix") or "")[:400],
        }
        for c in (result.get("findings") or []) if isinstance(c, dict) and c.get("issue")
    ]
    return {"checks": checks, "findings": findings}


def review_quality(db: Session, request_id: int) -> None:
    req = db.get(Request, request_id)
    if req is None or not req.mvp_blueprint:
        return

    # Snapshots before threads — the standing rule.
    blueprint = req.mvp_blueprint
    technical = req.technical_plan or "(not produced)"
    owner_numbers = _format_owner_numbers(req)
    register = build_engagement_register(
        req.engagement_type, req.needs_ai, req.main_problem, req.desired_outcome,
    )
    business_case = req.business_case_json or "{}"
    modules = json.loads(req.modules_json) if req.modules_json else []
    journey = json.loads(req.journey_json) if req.journey_json else {}
    org = json.loads(req.org_json) if req.org_json else {}
    checklists = json.loads(req.checklists_json) if req.checklists_json else {}
    playbook = json.loads(req.playbook_json) if req.playbook_json else {}
    procedures = (json.loads(req.procedures_json) if req.procedures_json else {}).get("procedures") or []
    scoreboard = json.loads(req.scoreboard_json) if req.scoreboard_json else []
    risks = json.loads(req.risks_json) if req.risks_json else []

    def _numbers():
        prompt = render(
            "qa_numbers.j2",
            owner_numbers=owner_numbers,
            business_case=business_case,
            blueprint=blueprint,
            technical_plan=technical,
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=3000)
        return _sanitize_report(extract_json_from_text(body["choices"][0]["message"]["content"])), body.get("usage")

    def _completeness():
        prompt = render(
            "qa_completeness.j2",
            engagement_register=register,
            blueprint=blueprint,
            module_names=json.dumps([m.get("name") for m in modules]),
            pilot_gate=json.dumps((json.loads(business_case) if business_case.strip().startswith("{") else {}).get("pilot_gate") or "none defined"),
            journey_stages=json.dumps([s.get("stage") for s in journey.get("stages") or []]),
            org_count=len(org.get("roles") or []),
            scoreboard_count=len(scoreboard),
            risks_count=len(risks),
            procedures_count=len(procedures),
            procedures_list=json.dumps([
                {"name": p.get("name"), "phase": p.get("phase"), "module": p.get("module")}
                for p in procedures if isinstance(p, dict)
            ]),
            checklists_count=len(checklists.get("checklists") or []),
            quick_wins_count=len(playbook.get("quick_wins") or []),
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=1800)
        return _sanitize_report(extract_json_from_text(body["choices"][0]["message"]["content"])), body.get("usage")

    def _guarded(item):
        name, fn = item
        try:
            report, usage = fn()
            return name, report, usage, None
        except Exception as exc:
            return name, None, None, str(exc)[:500]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_guarded, [("qa_numbers", _numbers), ("qa_completeness", _completeness)]))

    checks, findings = [], []
    for name, report, usage, error in results:
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose=name,
            usage=usage, success=error is None, error=error,
        )
        if report:
            checks += report["checks"]
            # Tag each finding with its auditor — routing to the repair pass
            # is by source, never by sniffing the finding's prose.
            findings += [{**f, "source": name} for f in report["findings"]]

    polish_applied = False
    # The red pen only ever acts on the NUMBERS auditor's findings —
    # wording-level fixes to specific figures. Structure findings mean a
    # section is missing, and "fixing" that would mean inventing content;
    # they go to the human reviewer instead.
    numbers_findings = [f for f in findings if f.get("source") == "qa_numbers"]
    if numbers_findings:
        try:
            prompt = render(
                "qa_polish.j2",
                findings=json.dumps(numbers_findings, indent=1),
                blueprint=blueprint,
            )
            body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=8000)
            corrected = body["choices"][0]["message"]["content"].strip()
            # Hard guards: the partner pass may only ever be surgical.
            size_ok = 0.6 < (len(corrected) / max(1, len(blueprint))) < 1.4
            headings_ok = all(h in corrected for h in _REQUIRED_HEADINGS)
            if size_ok and headings_ok:
                req.mvp_blueprint = corrected
                polish_applied = True
                # A finding the red pen just corrected in the document is no
                # longer an OPEN finding -- the release gate counts only what
                # still stands. Structure findings were never forwarded and
                # stay open.
                for f in numbers_findings:
                    f["repaired"] = True
                # The corrected document is re-audited against the same duty:
                # repairs must hold, and the rewrite must not have introduced
                # a new defect. Recheck findings stay OPEN — no repair loop.
                try:
                    blueprint = corrected
                    recheck, usage2 = _numbers()
                    findings += [{**f, "source": "qa_numbers_recheck"}
                                 for f in recheck["findings"]]
                    log_usage(
                        db, request_id,
                        provider="openrouter", model=settings.ANALYSIS_MODEL,
                        purpose="qa_numbers_recheck", usage=usage2, success=True,
                    )
                except Exception as exc:
                    log_usage(
                        db, request_id,
                        provider="openrouter", model=settings.ANALYSIS_MODEL,
                        purpose="qa_numbers_recheck", success=False, error=str(exc)[:500],
                    )
            else:
                logger.warning(
                    "polish pass discarded (size_ok=%s headings_ok=%s): request=%s",
                    size_ok, headings_ok, request_id,
                )
            log_usage(
                db, request_id,
                provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="qa_polish",
                usage=body.get("usage"), success=True,
            )
        except Exception as exc:
            log_usage(
                db, request_id,
                provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="qa_polish",
                success=False, error=str(exc)[:500],
            )

    req.qa_report_json = json.dumps({
        "checks": checks,
        "findings": findings,
        "polish_applied": polish_applied,
    })
    db.commit()
