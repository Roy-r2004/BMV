"""Deterministic structural validation of an engagement's decomposition.

The generator's structural promises — every scenario assumption produces an
impact or an explicit cannot-quantify note, modules depend only backward,
the build order is a valid topological order, the pilot gate is one whole
typed object, the claim registry validates, pilot-phase modules are named
honestly — are checked here by code, before prose is generated (preflight)
and again at audit time. Model quality may vary; structure may not.
"""

import re

_FRACTION = re.compile(r"\d[\d.]*\s*%|\b1 in \d+\b")
_QUANT = re.compile(r"\d[\d,]*(?:\.\d+)?")
_CANNOT = re.compile(r"cannot yet quantify|not yet monetized|needs your|pending your", re.IGNORECASE)


def scenario_component_map(scenario: dict) -> dict:
    """How many impact mechanisms the assumption promises vs how many the
    impact delivers (a quantified figure or an explicit cannot-quantify)."""
    assumption = str(scenario.get("assumption") or "")
    impact = str(scenario.get("impact") or "")
    promised = len(_FRACTION.findall(assumption))
    quantified = len([v for v in _QUANT.findall(impact) if float(v.replace(",", "")) > 1])
    unquantified_notes = len(_CANNOT.findall(impact))
    return {"promised": promised, "delivered": quantified + unquantified_notes,
            "quantified": quantified, "cannot_quantify_notes": unquantified_notes,
            "complete": promised == 0 or (quantified + unquantified_notes) >= promised}


def structural_findings(business_case: dict, modules: list, registry: dict | None = None) -> list[dict]:
    """High findings a machine can prove — appended to the QA report and
    counted by the release gate like any other."""
    findings: list[dict] = []
    bc = business_case if isinstance(business_case, dict) else {}
    fm = bc.get("financial_model") or {}

    for sc in (fm.get("scenarios") or []) if isinstance(fm, dict) else []:
        if not isinstance(sc, dict):
            continue
        m = scenario_component_map(sc)
        if not m["complete"]:
            findings.append({
                "severity": "high", "source": "structural",
                "where": f"financial_model.scenarios.{sc.get('name')}",
                "issue": (f"The assumption promises {m['promised']} impact mechanism(s) but the "
                          f"impact delivers only {m['delivered']} (quantified figures or explicit "
                          f"cannot-quantify notes). Every promised mechanism must produce one or the other."),
                "fix": "add the missing impact clause or an explicit 'cannot yet quantify — needs <input>' note",
            })

    gate = bc.get("pilot_gate") or {}
    if isinstance(gate, dict) and gate:
        from app.pipeline import pilot_gate as _pg

        typed = gate if "canonical_sentence" in gate else _pg.normalize_gate(gate)
        errors = _pg.gate_errors(typed)
        if errors:
            findings.append({
                "severity": "high", "source": "structural", "where": "pilot_gate",
                "issue": ("The pilot gate is not a whole typed object — " + "; ".join(errors) +
                          ". The single source of pilot criteria must be complete before any document restates it."),
                "fix": "regenerate the decomposition with a complete pilot_gate (numerator, denominator, "
                       "geography, control method, explicit percentage-point or relative target, baseline, guardrail)",
            })

    mods = [m for m in (modules or []) if isinstance(m, dict) and m.get("id")]
    by_id = {m["id"]: m for m in mods}
    order = [x for x in (bc.get("build_order") or []) if x in by_id]
    if mods and order and sorted(order) != sorted(by_id):
        findings.append({
            "severity": "high", "source": "structural", "where": "build_order",
            "issue": "build_order does not list every module exactly once.",
            "fix": "regenerate build_order as a permutation of the module ids",
        })

    # dependency sanity: declared depends_on must exist and be acyclic
    def _cycle() -> bool:
        seen, done = set(), set()

        def visit(node: str) -> bool:
            if node in done:
                return False
            if node in seen:
                return True
            seen.add(node)
            for dep in (by_id.get(node, {}).get("depends_on") or []):
                if dep in by_id and visit(dep):
                    return True
            done.add(node)
            return False

        return any(visit(m["id"]) for m in mods)

    if _cycle():
        findings.append({
            "severity": "high", "source": "structural", "where": "modules.depends_on",
            "issue": "The module dependency graph contains a cycle.",
            "fix": "regenerate the decomposition with acyclic dependencies",
        })
    elif order:
        pos = {mid: i for i, mid in enumerate(order)}
        for m in mods:
            for dep in (m.get("depends_on") or []):
                if dep in pos and m["id"] in pos and pos[dep] > pos[m["id"]]:
                    findings.append({
                        "severity": "high", "source": "structural", "where": "build_order",
                        "issue": (f"'{by_id[m['id']].get('name')}' depends on "
                                  f"'{by_id[dep].get('name')}' but is scheduled before it — the "
                                  f"build order is not a valid topological order."),
                        "fix": "reorder build_order to respect depends_on",
                    })

    # a module's own description may not lean on a later module
    if order:
        pos = {mid: i for i, mid in enumerate(order)}
        for m in mods:
            text = " ".join(str(m.get(k) or "") for k in ("purpose", "pain_point_addressed"))
            for other in mods:
                if other["id"] == m["id"] or other.get("name", "") not in text:
                    continue
                if pos.get(other["id"], -1) > pos.get(m["id"], len(order)):
                    findings.append({
                        "severity": "high", "source": "structural", "where": f"modules.{m['id']}",
                        "issue": (f"'{m.get('name')}' is described in terms of "
                                  f"'{other.get('name')}', which is built later — dependencies "
                                  f"flow backward only."),
                        "fix": "describe the earlier module's interim rules-based behavior instead",
                    })

    # pilot-phase modules: honest names, no AI automation
    from app.pipeline.registry import _AI_NAME, validate_registry

    for m in mods:
        if m.get("pilot") and _AI_NAME.search(str(m.get("client_facing_name") or m.get("name") or "")):
            findings.append({
                "severity": "high", "source": "structural", "where": f"modules.{m['id']}",
                "issue": (f"Pilot-phase module '{m.get('name')}' carries a name implying predictive "
                          "intelligence — a Phase 1 pilot is manual or rules-based and its name must say so."),
                "fix": "use the canonical pilot name (e.g. '... Pilot') everywhere",
            })
        if m.get("pilot") and str(m.get("automation_level") or "").lower() == "ai":
            findings.append({
                "severity": "high", "source": "structural", "where": f"modules.{m['id']}",
                "issue": f"Pilot-phase module '{m.get('name')}' is declared AI-automated — a pilot runs without AI.",
                "fix": "set automation_level to manual or rules for the pilot module",
            })

    if registry:
        for err in validate_registry(registry):
            findings.append({
                "severity": "high", "source": "structural", "where": "claim registry",
                "issue": f"The claim registry does not validate: {err}.",
                "fix": "repair the decomposition so every release-critical claim is typed and complete",
            })
    return findings


def preflight(business_case: dict, modules: list, registry: dict | None = None) -> list[dict]:
    """The pre-generation check: the same structural findings, computed
    BEFORE any prose call spends money. A failed preflight means the
    decomposition is retried or the run stops — never a blind spend."""
    return structural_findings(business_case, modules, registry)
