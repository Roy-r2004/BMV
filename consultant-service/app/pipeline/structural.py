"""Deterministic structural validation of an engagement's decomposition.

The generator's structural promises — every scenario assumption produces an
impact or an explicit cannot-quantify note, modules depend only backward,
the build order is a valid topological order, the pilot gate is one whole
typed object, the claim registry validates, pilot-phase modules are named
honestly — are checked here by code, before prose is generated (preflight)
and again at audit time. Model quality may vary; structure may not.
"""

import json
import re

_FRACTION = re.compile(r"\d[\d.]*\s*%|\b1 in \d+\b")
_QUANT = re.compile(r"\d[\d,]*(?:\.\d+)?")
_CANNOT = re.compile(r"cannot yet quantify|not yet monetized|not yet calculable|needs your|pending your", re.IGNORECASE)


def scenario_component_map(scenario: dict, lines: list | None = None) -> dict:
    """How many impact mechanisms the assumption promises vs how many the
    impact delivers (a quantified figure or an explicit cannot-quantify) —
    and, when the financial lines are given, whether every quantified
    component's SUBJECT is promised by the assumption (a past run promised
    two mechanisms and quantified a third nobody promised)."""
    assumption = str(scenario.get("assumption") or "")
    impact = str(scenario.get("impact") or "")
    promised = len(_FRACTION.findall(assumption))
    quantified = len([v for v in _QUANT.findall(impact) if float(v.replace(",", "")) > 1])
    unquantified_notes = len(_CANNOT.findall(impact))
    unpromised = unpromised_components(scenario, lines or [])
    return {"promised": promised, "delivered": quantified + unquantified_notes,
            "quantified": quantified, "cannot_quantify_notes": unquantified_notes,
            "unpromised": unpromised,
            "complete": (promised == 0 or (quantified + unquantified_notes) >= promised) and not unpromised}


_GENERIC = {"annual", "total", "current", "inquiries", "inquiry", "costs", "cost", "from", "hours", "staff",
            "volume", "year", "month", "support", "team", "time", "number", "rate", "with", "that", "this",
            "per", "the", "and", "for"}


def _subjects_of(item: str) -> tuple[str | None, list[str]]:
    """The subject a financial line is about: a quoted phrase when the item
    carries one (matched as a phrase), else its distinctive content words
    (matched by 5-letter prefix, so a plural meets its singular and an
    acronym meets itself)."""
    q = re.search(r"['\"‘’“”]([^'\"‘’“”]{3,40})['\"‘’“”]", item or "")
    phrase = q.group(1).lower() if q else None
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z-]{2,}", item or "")
             if w.lower() not in _GENERIC]
    return phrase, words


def _promised(assumption: str, phrase: str | None, words: list[str]) -> bool:
    a = assumption.lower()
    if phrase:
        return phrase in a
    for w in words:
        parts = [p for p in re.split(r"-", w) if len(p) >= 3]
        for p in parts:
            key = p.lower()[:5] if len(p) > 5 else p.lower()
            if key in a:
                return True
    return False


def unpromised_components(scenario: dict, lines: list) -> list[dict]:
    """Quantified impact components whose base line's subject the
    assumption never names."""
    out = []
    assumption = str(scenario.get("assumption") or "").lower()
    impact = str(scenario.get("impact") or "")
    fracs = [float(x.rstrip("%")) / 100 for x in re.findall(r"(\d[\d.]*)\s*%", assumption)]
    fracs += [1 / float(n) for n in re.findall(r"\b1 in (\d+)\b", assumption)]
    bases = []
    for line in lines or []:
        if not isinstance(line, dict):
            continue
        nums = [float(v.replace(",", "")) for v in _QUANT.findall(str(line.get("annual") or ""))]
        if nums:
            bases.append((nums[0], str(line.get("item") or "")))
    for tok in _QUANT.findall(impact):
        v = float(tok.replace(",", ""))
        if v <= 1:
            continue
        hit = next(((f, item) for f in fracs for base, item in bases
                    if base and abs(base * f - v) / max(v, 1e-9) <= 0.005), None)
        if not hit:
            continue
        f, item = hit
        phrase, words = _subjects_of(item)
        if (phrase or words) and not _promised(assumption, phrase, words):
            subject = phrase or max(words, key=len).lower()
            out.append({"value": tok, "fraction": f, "subject": subject})
    return out


_INLINE_PRODUCT = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*[x×*]\s*(0?\.\d+|\d{1,2}(?:\.\d+)?\s*%)\s*(?:\)|=|≈|~|→|->|,|\s)\s*"
    r"(?:(?:=|≈|~|→|->|leading to|giving|yields?|or|i\.e\.)\s*)?(?:about |approximately |~)?(\d[\d,]*(?:\.\d+)?)?",
    re.IGNORECASE)


def inline_product_findings(business_case: dict) -> list[dict]:
    """Arithmetic the model writes INSIDE business-case prose (payback logic,
    costs removed, revenue streams, pricing levers) must (a) compute, and
    (b) apply a fraction the scenarios actually assume for that base — run 47
    wrote '(127750 * 0.20) = 25,550 fewer inquiries' while its scenarios
    assumed 40/60/80% for that line."""
    out = []
    bc = business_case if isinstance(business_case, dict) else {}
    fm = bc.get("financial_model") if isinstance(bc.get("financial_model"), dict) else {}
    bases = {}
    for line in fm.get("lines") or []:
        if isinstance(line, dict):
            nums = [float(v.replace(",", "")) for v in _QUANT.findall(str(line.get("annual") or ""))]
            if nums:
                bases[round(nums[0], 2)] = str(line.get("item") or "")
    fracs = set()
    for sc in fm.get("scenarios") or []:
        if isinstance(sc, dict):
            a = str(sc.get("assumption") or "")
            fracs |= {round(float(x) / 100, 4) for x in re.findall(r"(\d[\d.]*)\s*%", a)}
            fracs |= {round(1 / float(n), 4) for n in re.findall(r"\b1 in (\d+)\b", a)}
    texts = []
    for key in ("payback_logic", "cost_of_inaction"):
        if isinstance(bc.get(key), str):
            texts.append((key, bc[key]))
    for key, field in (("costs_removed", "how"), ("revenue_streams", "description")):
        for i, it in enumerate(bc.get(key) or []):
            if isinstance(it, dict) and isinstance(it.get(field), str):
                texts.append((f"{key}[{i}].{field}", it[field]))
    for i, it in enumerate(bc.get("pricing_levers") or []):
        if isinstance(it, str):
            texts.append((f"pricing_levers[{i}]", it))
    # a scenario's own arithmetic field (run 47 added one beside assumption
    # and impact) must produce the figures its impact states
    for i, sc in enumerate(fm.get("scenarios") or []):
        if not (isinstance(sc, dict) and isinstance(sc.get("arithmetic"), str)):
            continue
        impact_nums = [float(v.replace(",", "")) for v in _QUANT.findall(str(sc.get("impact") or ""))]
        for m in re.finditer(r"\(([^()]*\d[^()]*)\)", sc["arithmetic"]):
            expr = m.group(1)
            operands = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", expr)]
            if len(operands) < 2 or not re.fullmatch(r"[\d,.\s*x×$%]+", expr.replace("$", "")):
                continue
            product = 1.0
            for v in operands:
                product *= v
            if product < 10:
                continue
            if not any(abs(product - n) / max(n, 1e-9) <= 0.005 for n in impact_nums):
                nearest = min(impact_nums, key=lambda n: abs(n - product)) if impact_nums else None
                out.append({"severity": "high", "source": "structural",
                            "where": f"financial_model.scenarios[{i}].arithmetic",
                            "issue": (f"Scenario '{sc.get('name')}' arithmetic '({expr})' = {product:,.0f} matches no figure "
                                      f"in its impact" + (f" (nearest stated: {nearest:,.0f})" if nearest else "") +
                                      " — assumption, arithmetic and impact must agree."),
                            "fix": "regenerate the scenario so its arithmetic produces the stated impact figures"})
    for where, text in texts:
        for m in _INLINE_PRODUCT.finditer(text):
            base = float(m.group(1).replace(",", ""))
            ftok = m.group(2)
            frac = float(ftok.rstrip("% ")) / 100 if "%" in ftok else float(ftok)
            result = float(m.group(3).replace(",", "")) if m.group(3) else None
            if base not in bases or base < 100:
                continue
            product = base * frac
            if result is not None and abs(product - result) / max(result, 1e-9) > 0.005:
                out.append({"severity": "high", "source": "structural", "where": f"business_case.{where}",
                            "issue": (f"Inline arithmetic '{m.group(0).strip()}' does not compute: "
                                      f"{base:,.0f} x {frac:g} = {product:,.0f}, not {result:,.0f}."),
                            "fix": "correct the result or remove the arithmetic"})
            elif fracs and round(frac, 4) not in fracs:
                out.append({"severity": "high", "source": "structural", "where": f"business_case.{where}",
                            "issue": (f"Inline arithmetic applies {frac:.0%} to the '{bases[base][:40]}' line, but the "
                                      f"scenarios assume {', '.join(f'{f:.0%}' for f in sorted(fracs))} — one base, one set of fractions."),
                            "fix": "use a scenario fraction or remove the arithmetic from the prose"})
    return out


_NAME_NOISE = {"module", "handler", "bot", "assistant", "system", "engine", "workflow", "integration", "automated",
               "smart", "the", "and", "for", "of", "with", "via", "tool", "service", "portal", "manager", "ai",
               "reply", "agent", "pilot", "layer", "hub", "center", "centre", "platform"}
_PURPOSE_NOISE = _NAME_NOISE | {"this", "that", "from", "into", "their", "your", "which", "when", "then", "than",
                                "using", "based", "about", "after", "before", "each", "every", "provides", "provide",
                                "enables", "enable", "allows", "allow", "helps", "help", "through", "within", "across",
                                "customers", "customer", "business", "clients", "client", "data", "information"}


def _words(text: str, noise: set) -> set:
    return {w.lower().strip("'\"") for w in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", text or "")
            if w.lower() not in noise}


def module_overlap_findings(modules: list) -> list[dict]:
    """Two modules whose names share two distinctive words and whose purposes
    share three are one job split in two — a decomposition defect."""
    out = []
    mods = [m for m in (modules or []) if isinstance(m, dict) and m.get("id")]
    for i, a in enumerate(mods):
        for b in mods[i + 1:]:
            na, nb = _words(str(a.get("name") or ""), _NAME_NOISE), _words(str(b.get("name") or ""), _NAME_NOISE)
            shared_name = na & nb
            if len(shared_name) < 2:
                continue
            pa = _words(" ".join(str(a.get(k) or "") for k in ("purpose", "pain_point_addressed")), _PURPOSE_NOISE)
            pb = _words(" ".join(str(b.get(k) or "") for k in ("purpose", "pain_point_addressed")), _PURPOSE_NOISE)
            shared_purpose = pa & pb
            if len(shared_purpose) >= 3:
                out.append({"severity": "high", "source": "structural", "where": f"modules.{a['id']}+{b['id']}",
                            "issue": (f"'{a.get('name')}' and '{b.get('name')}' overlap: their names share "
                                      f"{', '.join(sorted(shared_name))} and their purposes share "
                                      f"{', '.join(sorted(shared_purpose)[:4])} — one capability split into two modules."),
                            "fix": "merge them into one module, or give each a distinct job and name"})
    return out


def structural_findings(business_case: dict, modules: list, registry: dict | None = None) -> list[dict]:
    """High findings a machine can prove — appended to the QA report and
    counted by the release gate like any other."""
    findings: list[dict] = []
    bc = business_case if isinstance(business_case, dict) else {}
    fm = bc.get("financial_model") or {}

    for sc in (fm.get("scenarios") or []) if isinstance(fm, dict) else []:
        if not isinstance(sc, dict):
            continue
        m = scenario_component_map(sc, (fm.get("lines") or []) if isinstance(fm, dict) else [])
        if m["unpromised"]:
            u = m["unpromised"][0]
            findings.append({
                "severity": "high", "source": "structural",
                "where": f"financial_model.scenarios.{sc.get('name')}",
                "issue": (f"The impact quantifies '{u['value']}' for '{u['subject']}' ({u['fraction']:.0%} of its "
                          f"line) but the assumption never promises a mechanism for '{u['subject']}'."),
                "fix": f"state the {u['fraction']:.0%} assumption for '{u['subject']}' in the assumption, or drop the component",
            })
        elif not m["complete"]:
            findings.append({
                "severity": "high", "source": "structural",
                "where": f"financial_model.scenarios.{sc.get('name')}",
                "issue": (f"The assumption promises {m['promised']} impact mechanism(s) but the "
                          f"impact delivers only {m['delivered']} (quantified figures or explicit "
                          f"cannot-quantify notes). Every promised mechanism must produce one or the other."),
                "fix": "add the missing impact clause or an explicit 'cannot yet quantify — needs <input>' note",
            })

    findings += inline_product_findings(bc)

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
                "fix": ("regenerate the decomposition with a complete pilot_gate (numerator, denominator, geography, "
                        "randomized control method, explicit percentage-point or relative target, baseline, guardrail); "
                        "target_value is the number written in the target text (5 for '5 percentage points', 25 for "
                        "'25% relative'), never the resulting rate"),
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

    # a template placeholder in a spec is a skeleton defect, retried with feedback
    # keyword placeholders in any case; ALL-CAPS tokens case-sensitively — a
    # merge field such as "[CustomerName]" in a message script is legitimate
    _PLACEHOLDER = re.compile(r"(?i:\[(?:TODO|TBD|PLACEHOLDER|INSERT|YOUR |CLIENT_INPUT)[^\]]*\]|CLIENT_INPUT_OR_ARITHMET)|\[[A-Z][A-Z_]{4,}\]")
    for m in mods:
        blob = json.dumps({k: m.get(k) for k in ("spec", "tech", "purpose")})
        hit = _PLACEHOLDER.search(blob)
        if hit:
            findings.append({
                "severity": "high", "source": "structural", "where": f"modules.{m['id']}",
                "issue": f"'{m.get('name')}' carries a template placeholder ('{hit.group(0)}') where a value or a labeled proposal belongs.",
                "fix": "state the value as a labeled proposal '(proposed — client approval required)' or describe it in words — never a placeholder",
            })

    # every module ships with acceptance checks the owner can verify — "to
    # be established later" is not an acceptance criterion (run 49)
    for m in mods:
        tech = m.get("tech") if isinstance(m.get("tech"), dict) else None
        if tech is None:
            continue  # the tech call failed open; the bench sees the gap
        done = [d for d in (tech.get("done_when") or []) if isinstance(d, str) and len(d.strip()) > 12
                and not re.search(r"to be (?:defined|established|determined)|later|TBD|depends on the pilot", d, re.IGNORECASE)]
        if len(done) < 2:
            findings.append({
                "severity": "high", "source": "structural", "where": f"modules.{m['id']}.tech.done_when",
                "issue": f"'{m.get('name')}' has {len(done)} verifiable acceptance check(s); every module needs at least two concrete 'finished when' checks.",
                "fix": "state 2-4 checks a non-technical owner can verify once the module exists",
            })

    # two modules for one job: overlapping names AND overlapping purposes
    # (a past run split one inquiry-handling job into two near-identical modules)
    findings += module_overlap_findings(mods)

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

    # the pilot is rules-based, human-supervised and depends on no module;
    # financial detail needs more than a number match; API paths are slugs
    from app.pipeline.registry import api_path_findings, auth_findings, pilot_isolation_findings

    findings += pilot_isolation_findings(mods)
    findings += auth_findings(mods)
    findings += api_path_findings(mods)
    # the pilot's own strings: no customer into the internal queue, no
    # narrowing of the gate's population
    from app.pipeline.registry import customer_queue_findings, population_findings

    from app.pipeline.registry import _strings_in, integration_channel_findings

    typed_gate = bc.get("pilot_gate") if isinstance(bc.get("pilot_gate"), dict) else None
    for m in mods:
        if m.get("pilot"):
            # string by string — never a JSON blob whose fields would read as one clause
            for s in [x for k in ("spec", "tech", "purpose") for x in _strings_in(m.get(k))]:
                findings += customer_queue_findings(s, f"modules.{m['id']}")
                if typed_gate:
                    findings += population_findings(s, typed_gate, f"modules.{m['id']}", (registry or {}).get("service_types"),
                                                    pilot_scope=False)
            findings += integration_channel_findings(m)

    # a scenario that "releases" hours by applying an inquiry share to an
    # hours pool asserts a client fact the client never gave
    from app.pipeline.decompose import _numbers_in, line_unit

    claims = (registry or {}).get("claims") or []
    share_given = any(c.get("type") == "client_fact" and str(c.get("unit")) == "%"
                      and re.search(r"hour|time", str(c.get("question") or ""), re.IGNORECASE)
                      and re.search(r"share|inquir|handling|spent on", str(c.get("question") or ""), re.IGNORECASE)
                      for c in claims)
    if isinstance(fm, dict) and not share_given:
        hour_bases = [(_numbers_in(str(l.get("annual") or ""))[0], str(l.get("item") or ""))
                      for l in (fm.get("lines") or []) if isinstance(l, dict)
                      and _numbers_in(str(l.get("annual") or "")) and str(l.get("unit") or line_unit(l)) == "hours"]
        for sc in fm.get("scenarios") or []:
            if not isinstance(sc, dict):
                continue
            fracs = [v for v in _numbers_in(str(sc.get("assumption") or "")) if 0 < v < 1]
            for v in _numbers_in(str(sc.get("impact") or "")):
                if v <= 1:
                    continue
                hit = next((item for f in fracs for base, item in hour_bases
                            if base and abs(base * f - v) / max(v, 1e-9) <= 0.005), None)
                if hit:
                    findings.append({
                        "severity": "high", "source": "structural",
                        "where": f"financial_model.scenarios.{sc.get('name')}",
                        "issue": (f"'{v:,.0f}' hours released is an inquiry share applied to the hours line '{hit}' — "
                                  "the share of those hours spent on inquiries is a client input that was never given."),
                        "fix": "state 'hours released: not yet calculable — needs <the client's share>' and add it to missing_inputs",
                    })
                    break

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
