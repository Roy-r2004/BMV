"""Deterministic phase semantics for procedures.

    CURRENT  usable in the client's operation today, with what already exists
    PILOT    executable during the pilot without any unbuilt future module
    FUTURE   usable only after the relevant module is built and approved

"Build first" describes SEQUENCE; FUTURE describes present AVAILABILITY. A
procedure accurately marked FUTURE for a module the build plan commits to
is consistent, not contradictory — it becomes a defect only when the text
tells staff to execute it now, or when a CURRENT/PILOT procedure depends on
something unbuilt. Run 46's bench flagged the former as a contradiction;
this module is the structured answer.
"""

import re

PHASES = {
    "current": "usable in the client's operation today, with what already exists",
    "pilot": "executable during the pilot without any unbuilt future module",
    "future": "usable only after the relevant module is built and approved",
}
_NOW = re.compile(
    r"\b(today|immediately|starting now|from today|right away|as of now|effective immediately|"
    r"from day one|starting this week|begin now|now in force)\b", re.IGNORECASE)
_UNBUILT_TOOLING = re.compile(
    r"\b(dashboard|portal|the module|the system automatically|the ai|the agent|automatically "
    r"(?:sends|flags|routes|scores|predicts)|in the app|the new system)\b", re.IGNORECASE)


def _text_of(p: dict) -> str:
    parts = [str(p.get("trigger") or "")]
    parts += [str(s.get("step") or "") for s in (p.get("steps") or []) if isinstance(s, dict)]
    for e in p.get("exceptions") or []:
        if isinstance(e, dict):
            parts += [str(e.get("when") or ""), str(e.get("then") or "")]
    return " ".join(parts)


def _actors(p: dict) -> list[str]:
    return [str(s.get("actor") or "").strip().lower() for s in (p.get("steps") or []) if isinstance(s, dict)]


def phase_findings(procedures: list, modules: list) -> list[dict]:
    """High findings a machine can prove from the structured layers."""
    out = []
    mods = [m for m in (modules or []) if isinstance(m, dict) and m.get("id")]
    names = {str(m.get("client_facing_name") or m.get("name") or ""): m for m in mods}
    ai_names = [n for n, m in names.items() if n and (m.get("automation_level") == "ai"
                                                      or (m.get("spec") or {}).get("ai")
                                                      or (m.get("tech") or {}).get("ai_agent"))]
    for p in procedures or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "procedure")
        phase = str(p.get("phase") or "").strip().lower()
        text = _text_of(p)
        module = str(p.get("module") or "")
        where = f"procedures.{name}"
        if phase not in PHASES:
            out.append({"severity": "high", "source": "structural", "where": where,
                        "issue": f"Procedure '{name}' declares no valid phase (current/pilot/future).",
                        "fix": "declare the phase in which staff can actually run it"})
            continue
        if phase == "current" and ("ai" in _actors(p) or any(n and n in text for n in names)):
            out.append({"severity": "high", "source": "structural", "where": where,
                        "issue": (f"Procedure '{name}' is marked CURRENT but depends on a module that "
                                  "is not built yet — an unbuilt capability presented as usable today."),
                        "fix": "mark it FUTURE (or PILOT if it runs with today's tools only)"})
        if phase == "pilot" and ("ai" in _actors(p) or any(n in text for n in ai_names)):
            out.append({"severity": "high", "source": "structural", "where": where,
                        "issue": (f"Pilot procedure '{name}' relies on an AI actor or an AI module — "
                                  "a pilot must be executable without any unbuilt module."),
                        "fix": "rewrite the step for a human actor using today's tools"})
        if phase == "future" and _NOW.search(text):
            out.append({"severity": "high", "source": "structural", "where": where,
                        "issue": (f"Procedure '{name}' is FUTURE state but instructs staff to execute "
                                  f"it now (\"{_NOW.search(text).group(0)}\")."),
                        "fix": "remove the immediacy, or re-phase the procedure honestly"})
        if phase == "future" and module and module != "The pilot" and module not in names:
            out.append({"severity": "high", "source": "structural", "where": where,
                        "issue": f"FUTURE procedure '{name}' belongs to '{module}', which is not in the build plan.",
                        "fix": "attach it to a planned module or drop it"})
    return out


def future_is_consistent(procedures: list, modules: list) -> tuple[bool, str]:
    """The structured verdict the semantic auditor lacks: FUTURE procedures
    are consistent when none instructs present execution and each belongs to
    a planned module."""
    findings = [f for f in phase_findings(procedures, modules)
                if "FUTURE" in f["issue"] or "CURRENT" in f["issue"]]
    if findings:
        return False, findings[0]["issue"]
    futures = [p for p in (procedures or []) if isinstance(p, dict)
               and str(p.get("phase") or "").lower() == "future"]
    return True, (f"{len(futures)} FUTURE procedure(s): each belongs to a module the build plan "
                  "commits to and none instructs present execution — FUTURE describes availability, "
                  "'build first' describes sequence")


def semantics_for_prompt() -> str:
    return ("PHASE SEMANTICS (structured, binding): CURRENT = " + PHASES["current"] +
            "; PILOT = " + PHASES["pilot"] + "; FUTURE = " + PHASES["future"] +
            ". 'What we'd build first' describes build SEQUENCE; a procedure's phase describes present "
            "AVAILABILITY. A procedure accurately marked FUTURE for a module the build plan commits to "
            "is CONSISTENT — never a finding. It is a finding only when a FUTURE procedure tells staff "
            "to execute it today, or when a CURRENT/PILOT procedure depends on an unbuilt module.")
