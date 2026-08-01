"""Design critic and refinement agents."""
from __future__ import annotations

import json
from pathlib import Path

from app.application.prompts import PromptTemplate
from app.application.preview_app.catalogue_contract import (
    blocking_contract_errors,
    enforce_catalogue_page_contract,
    validate_catalogue_page_content,
)
from app.application.preview_app.codegen.architect import _architect_prompt_context, _route_for_file
from app.application.preview_app.codegen.shared import (
    _catalogue_contract_errors,
    _catalogue_retry_context,
    _normalize_critic_result,
    page_plan_for_file,
)
from app.application.preview_app.text_utils import _bounded_json, _parse_json, _strip_fences
from app.application.preview_app.fallback import (
    clear_stubbed_path,
    is_stubbed_path,
    record_stubbed_path,
)
from app.application.preview_app.parallel import parallel_map
from app.application.preview_app.protected_paths import is_template_owned_path, safe_source_path
from app.application.preview_app.source_quality import looks_truncated_source, tsx_parse_error
from app.application.preview_app.utility_compositor import is_utility_catalogue_route
from app.application.preview_app.workspace import read_file, write_file
from app.application.services.ai_context import (
    UNUSABLE_REJECTED,
    UNUSABLE_UNPARSEABLE,
    ai_call,
)
from app.application.ui_catalogue import compact_skeleton_contract, infer_section_slots
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.infrastructure.logging import get_logger

cg_log = get_logger("Codegen")

_DEFAULT_DESIGN_DIRECTION = (
    "Brand-forward and recipe-locked — match the stated design recipe, "
    "avoid generic SaaS chrome, purple-on-white defaults, and placeholder density."
)


def _vision_model() -> str:
    return (getattr(settings, "VISION_MODEL", None) or "").strip() or settings.CRITIC_MODEL


def critique_file(
    workspace: Path,
    file_path: str,
    file_instructions: str,
    full_context: str,
    design_direction: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    architect: dict | None = None,
) -> dict:
    """Design-critic agent: score one page and return revision notes."""
    current = read_file(workspace, file_path)
    if is_stubbed_path(workspace, file_path) or "deterministic catalogue contract scaffold" in current:
        # Scaffold-first pages are intentional catalogue output — do not thrash
        # refine loops that often break Vite (PublicNav leftovers, etc.).
        return {
            "score": 72,
            "verdict": "ok",
            "issues": ["Catalogue scaffold page (structure locked)."],
            "revision_instructions": "",
        }
    route = _route_for_file(file_path, architect or {})
    skeleton_id = str(route.get("skeleton_id") or "")
    skeleton_contract_json = (
        _bounded_json(
            compact_skeleton_contract(
                skeleton_id,
                infer_section_slots(route, skeleton_id),
            ),
            5000,
        )
        if skeleton_id
        else "{}"
    )
    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_CRITIC,
        full_context=full_context[:8000],
        design_direction=design_direction or _DEFAULT_DESIGN_DIRECTION,
        file_instructions=file_instructions or "Client-facing product page",
        file_path=file_path,
        current_content=current[:14000],
        catalogue_page=bool(skeleton_id),
        surface=route.get("surface") or "",
        skeleton_id=skeleton_id,
        skeleton_contract_json=skeleton_contract_json,
    )
    # `verdict == "unavailable"` is this critic's word for "nothing came back I
    # could read" — the exact 200-but-useless shape the census has to see.
    with ai_call("design_critic", writer="critique_file", attempt=1) as call:
        raw = ai_provider.ask_chat(settings.CRITIC_MODEL, [{"role": "user", "content": prompt}], max_tokens=2000)
        try:
            parsed = _parse_json(raw)
        except Exception:
            parsed = None
        normalized = _normalize_critic_result(parsed, threshold=88)
        call.adjudicate(
            normalized.get("verdict") != "unavailable", reason=UNUSABLE_UNPARSEABLE
        )
    if normalized.get("verdict") == "unavailable":
        retry_prompt = (
            prompt
            + "\n\nCRITIC JSON RETRY: The prior response was malformed. Return ONLY "
            "the required JSON object. Do not propose a rewrite unless you can provide "
            "specific, evidence-based issues."
        )
        with ai_call("design_critic", writer="critique_file-retry", attempt=2) as call:
            raw_retry = ai_provider.ask_chat(
                settings.CRITIC_MODEL,
                [{"role": "user", "content": retry_prompt}],
                max_tokens=2000,
            )
            try:
                parsed_retry = _parse_json(raw_retry)
            except Exception:
                parsed_retry = None
            normalized = _normalize_critic_result(parsed_retry, threshold=88)
            call.adjudicate(
                normalized.get("verdict") != "unavailable", reason=UNUSABLE_UNPARSEABLE
            )
    return normalized

def critique_file_visual(
    workspace: Path,
    file_path: str,
    screenshot_path: str,
    file_instructions: str,
    full_context: str,
    design_direction: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    architect: dict | None = None,
    business_identity: str = "",
) -> dict:
    """Visual-critic agent: score one page from its rendered screenshot.

    Same return shape as `critique_file` so callers can feed the result into
    the same `refine_file` used by the text critic — but this one judges what
    is actually visible on screen (a screenshot), not raw source, so it can
    catch rendering defects (blank icon slots, broken images, empty-looking
    lists, overlap) that a text-only read of the source can never see.

    Scaffold-first pages are reviewed like any other page: they render real
    imagery and real copy to a real user, so exempting them from visual review
    hides exactly the defects only a screenshot can reveal. What the scaffold
    lock buys them is immunity from *refine* — `verdict` stays out of "revise"
    so no freeform rewrite is triggered — while `visual_verdict` carries the
    honest judgement for callers that gate on it.
    """
    scaffold_locked = is_stubbed_path(workspace, file_path) or (
        "deterministic catalogue contract scaffold" in read_file(workspace, file_path)
    )
    route = _route_for_file(file_path, architect or {})
    skeleton_id = str(route.get("skeleton_id") or "")
    skeleton_contract_json = (
        _bounded_json(
            compact_skeleton_contract(
                skeleton_id,
                infer_section_slots(route, skeleton_id),
            ),
            5000,
        )
        if skeleton_id
        else "{}"
    )
    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_VISUAL_CRITIC,
        full_context=full_context[:8000],
        design_direction=design_direction or _DEFAULT_DESIGN_DIRECTION,
        file_instructions=file_instructions or "Client-facing product page",
        file_path=file_path,
        catalogue_page=bool(skeleton_id),
        surface=route.get("surface") or "",
        skeleton_id=skeleton_id,
        skeleton_contract_json=skeleton_contract_json,
        business_identity=business_identity,
    )
    with ai_call("vision", writer="critique_file_visual", attempt=1) as call:
        raw = ai_provider.ask_vision(_vision_model(), prompt, screenshot_path)
        try:
            parsed = _parse_json(raw)
        except Exception:
            parsed = None
        normalized = _normalize_critic_result(parsed, threshold=80)
        call.adjudicate(
            normalized.get("verdict") != "unavailable", reason=UNUSABLE_UNPARSEABLE
        )
    if normalized.get("verdict") == "unavailable":
        retry_prompt = (
            prompt
            + "\n\nCRITIC JSON RETRY: The prior response was malformed. Return ONLY "
            "the required JSON object. Preserve the page unless specific visual issues "
            "can be stated in the required schema."
        )
        with ai_call("vision", writer="critique_file_visual-retry", attempt=2) as call:
            raw_retry = ai_provider.ask_vision(
                _vision_model(),
                retry_prompt,
                screenshot_path,
            )
            try:
                parsed_retry = _parse_json(raw_retry)
            except Exception:
                parsed_retry = None
            normalized = _normalize_critic_result(parsed_retry, threshold=80)
            call.adjudicate(
                normalized.get("verdict") != "unavailable", reason=UNUSABLE_UNPARSEABLE
            )
    if scaffold_locked and normalized.get("verdict") != "unavailable":
        return {
            **normalized,
            "verdict": "ok",
            "visual_verdict": normalized.get("verdict"),
            "revision_instructions": "",
            "scaffold_locked": True,
        }
    return normalized

def refine_file(
    workspace: Path,
    file_path: str,
    file_instructions: str,
    critic_notes: str,
    full_context: str,
    manifest: dict,
    images: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    architect: dict | None = None,
    skipped_out: list[str] | None = None,
) -> str:
    """Rewrite a page to satisfy the critic's notes.

    Two routes are deliberately left alone (template-owned, and contract-driven
    utility pages). Callers used to record those as refined anyway: request 40
    logged `refined 2 page(s)` for two pages the critic had scored 60 `revise`
    and this function returned untouched — and both then failed the build with
    syntax errors nobody had looked for. `skipped_out` collects them so a caller
    can report what actually happened.
    """
    safe_file_path = safe_source_path(file_path, workspace)
    if not safe_file_path:
        raise ValueError(f"Unsafe generated source path: {file_path}")
    file_path = safe_file_path
    current = read_file(workspace, file_path)
    if is_template_owned_path(file_path, architect, workspace):
        if skipped_out is not None:
            skipped_out.append(file_path)
        return current
    route = _route_for_file(file_path, architect or {})
    skeleton_id = str(route.get("skeleton_id") or "")
    # Composed utility pages are content-JSON driven. Freeform refine would undo
    # the contract and reintroduce invent-React crashes — keep them intact.
    if is_utility_catalogue_route(route, skeleton_id) or "composed public-utility page" in current:
        cg_log.debug("refine skip composed utility page %s", file_path)
        if skipped_out is not None:
            skipped_out.append(file_path)
        return current
    catalogue_page = bool(skeleton_id)
    catalogue_contract_json = (
        _bounded_json(
            compact_skeleton_contract(
                skeleton_id,
                infer_section_slots(route, skeleton_id),
            ),
            5000,
        )
        if catalogue_page
        else "{}"
    )
    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_REFINE,
        full_context=full_context[:9000],
        manifest_json=json.dumps(manifest, ensure_ascii=False, indent=2),
        images_json=json.dumps(images, ensure_ascii=False, indent=2),
        file_instructions=file_instructions or "Client-facing product page",
        critic_notes=critic_notes,
        file_path=file_path,
        current_content=current[:14000],
        catalogue_page=catalogue_page,
        skeleton_id=skeleton_id,
        shell_component="OpsShell" if route.get("surface") == "ops" else "PublicShell",
        catalogue_contract_json=catalogue_contract_json,
    )
    with ai_call("refine", writer="refine_file", attempt=1) as call:
        raw = ai_provider.ask_chat(settings.PREVIEW_APP_MODEL, [{"role": "user", "content": prompt}], max_tokens=14000)
        content = _strip_fences(raw)
        call.adjudicate(
            bool((content or "").strip()) and not looks_truncated_source(content),
            reason=UNUSABLE_REJECTED,
        )
    for attempt in range(1, 3):
        incomplete = looks_truncated_source(content) or not (content or "").strip()
        contract_errors = (
            _catalogue_contract_errors(file_path, content, route, workspace=workspace)
            if catalogue_page and not incomplete
            else []
        )
        if not incomplete and not blocking_contract_errors(contract_errors):
            break
        retry_prompt = (
            f"{prompt}\n\n"
            + (
                _catalogue_retry_context(
                    errors=contract_errors,
                    contract_json=catalogue_contract_json,
                    rejected_source=content,
                )
                if contract_errors
                else
                "IMPORTANT: Your previous rewrite was CUT OFF or empty. "
                "Return the COMPLETE page file."
            )
        )
        with ai_call("refine", writer="refine_file-retry", attempt=attempt) as call:
            raw2 = ai_provider.ask_chat(
                settings.PREVIEW_APP_MODEL, [{"role": "user", "content": retry_prompt}], max_tokens=14000,
            )
            retry_content = _strip_fences(raw2)
            call.adjudicate(
                bool(retry_content) and not looks_truncated_source(retry_content),
                reason=UNUSABLE_REJECTED,
            )
            if retry_content:
                content = retry_content
    if looks_truncated_source(content) or not (content or "").strip():
        content = current
    if catalogue_page:
        contract_errors = _catalogue_contract_errors(file_path, content, route, workspace=workspace)
        # A refine that breaks the contract must never cost the user a page
        # that was valid before the critic touched it.
        if (
            blocking_contract_errors(contract_errors)
            and not blocking_contract_errors(
                validate_catalogue_page_content(current, route)
            )
        ):
            cg_log.warning("refine rejected — keeping pre-refine %s", file_path)
            content = current
    # A rewrite that does not parse must never replace source that did. The
    # slot-fill path has checked this since the start; refine did not, so
    # request 45's second pass on LoginPage wrote adjacent JSX and killed the
    # build for all twelve pages.
    if content != current:
        parse_error = tsx_parse_error(content)
        if parse_error and not tsx_parse_error(current):
            cg_log.warning(
                "refine rejected — %s does not parse (%s); keeping pre-refine source",
                file_path,
                parse_error,
            )
            content = current
    content, replaced = enforce_catalogue_page_contract(
        file_path,
        content,
        architect,
        brand_name=(
            (manifest.get("brand") or {}).get("name")
            if isinstance(manifest.get("brand"), dict)
            else manifest.get("brand_name")
        ),
    )
    if replaced:
        cg_log.warning("catalogue contract scaffolded %s after refine", file_path)
        record_stubbed_path(workspace, file_path)
    elif catalogue_page:
        if "deterministic catalogue contract scaffold" in content:
            record_stubbed_path(workspace, file_path)
        else:
            clear_stubbed_path(workspace, file_path)
    write_file(workspace, file_path, content)
    return content

def critique_and_refine(
    workspace: Path,
    files_to_gen: list[dict],
    full_context: str,
    design_direction: str,
    manifest: dict,
    images: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    on_progress=None,
    max_workers: int | None = None,
    architect: dict | None = None,
) -> list[str]:
    """Run the design-critic on each page; refine any that score below the bar.

    `on_progress(index, total, path)` is called as pages complete.
    When `max_workers` > 1, critique and refine run in parallel batches.
    """
    workers = max_workers if max_workers is not None else settings.PREVIEW_PARALLEL_WORKERS
    specs_by_path = {f.get("path", ""): f for f in files_to_gen}
    pages = [f for f in files_to_gen if f.get("kind") == "page" and f.get("path")]
    total = len(pages)
    if not pages:
        return []

    def _critique_spec(spec: dict) -> tuple[str, dict]:
        path = spec.get("path", "")
        review = critique_file(
            workspace, path, spec.get("instructions", ""), full_context, design_direction,
            ai_provider, template_renderer, architect,
        )
        return path, review

    reviews: dict[str, dict] = {}
    if workers <= 1:
        for i, spec in enumerate(pages, 1):
            path = spec.get("path", "")
            if on_progress:
                try:
                    on_progress(i, total, path)
                except Exception:
                    pass
            try:
                path, review = _critique_spec(spec)
            except Exception as exc:
                cg_log.warning("critic skip %s: %s", path, exc)
                continue
            reviews[path] = review
            score = review.get("score", 100)
            verdict = review.get("verdict", "pass")
            cg_log.info("critic %s: %s (%s)", path, score, verdict)
    else:
        def _on_critique_done(done: int, tot: int, spec: dict, result, exc) -> None:
            path = spec.get("path", "")
            if on_progress:
                try:
                    on_progress(done, tot, path)
                except Exception:
                    pass
            if exc:
                cg_log.warning("critic skip %s: %s", path, exc)
            elif result:
                path, review = result
                cg_log.info("critic %s: %s (%s)", path, review.get("score", 100), review.get("verdict", "pass"))

        for spec, result, exc in parallel_map(
            pages, _critique_spec, max_workers=workers, on_done=_on_critique_done,
        ):
            if result:
                path, review = result
                reviews[path] = review

    to_refine: list[tuple[dict, dict]] = []
    for spec in pages:
        path = spec.get("path", "")
        review = reviews.get(path)
        if not review or review.get("verdict") != "revise":
            continue
        notes = review.get("revision_instructions") or "; ".join(review.get("issues", []))
        if notes:
            to_refine.append((spec, review))

    refined: list[str] = []
    # Pages `refine_file` declined to touch. Counting them as refined turned a
    # "revise" verdict into a silent no-op with a reassuring log line.
    skipped: list[str] = []

    def _refine_item(item: tuple[dict, dict]) -> str | None:
        spec, review = item
        path = spec.get("path", "")
        notes = review.get("revision_instructions") or "; ".join(review.get("issues", []))
        refine_file(
            workspace,
            path,
            specs_by_path.get(path, {}).get("instructions", ""),
            notes,
            full_context,
            manifest,
            images,
            ai_provider,
            template_renderer,
            architect,
            skipped_out=skipped,
        )
        if path in skipped:
            cg_log.warning(
                "refine SKIPPED %s — critic asked for a revision (%s) and the page "
                "was left as-is",
                path,
                review.get("score"),
            )
            return None
        return path

    if to_refine:
        if workers <= 1:
            for spec, review in to_refine:
                path = spec.get("path", "")
                try:
                    if _refine_item((spec, review)) is None:
                        continue
                    refined.append(path)
                    cg_log.info("refined %s", path)
                    if review.get("score", 100) < 55:
                        review2 = critique_file(
                            workspace, path, spec.get("instructions", ""), full_context, design_direction,
                            ai_provider, template_renderer, architect,
                        )
                        if review2.get("verdict") == "revise":
                            notes2 = review2.get("revision_instructions") or "; ".join(review2.get("issues", []))
                            if notes2:
                                cg_log.info("second pass %s (%s)", path, review2.get("score"))
                                refine_file(
                                    workspace, path, spec.get("instructions", ""),
                                    notes2, full_context, manifest, images,
                                    ai_provider, template_renderer, architect,
                                )
                except Exception as e:
                    cg_log.error("refine FAIL %s: %s", path, e)
        else:
            for item, result, exc in parallel_map(to_refine, _refine_item, max_workers=workers):
                spec, _review = item
                path = spec.get("path", "")
                if exc:
                    cg_log.error("refine FAIL %s: %s", path, exc)
                    continue
                if result is None:
                    continue
                refined.append(path)
                cg_log.info("refined %s", path)

            poor = [(s, r) for s, r in to_refine if r.get("score", 100) < 55]
            if poor:
                def _second_pass(item: tuple[dict, dict]) -> str | None:
                    spec, _ = item
                    path = spec.get("path", "")
                    review2 = critique_file(
                        workspace, path, spec.get("instructions", ""), full_context, design_direction,
                        ai_provider, template_renderer, architect,
                    )
                    if review2.get("verdict") != "revise":
                        return None
                    notes2 = review2.get("revision_instructions") or "; ".join(review2.get("issues", []))
                    if not notes2:
                        return None
                    cg_log.info("second pass %s (%s)", path, review2.get("score"))
                    refine_file(
                        workspace, path, spec.get("instructions", ""),
                        notes2, full_context, manifest, images,
                        ai_provider, template_renderer, architect,
                    )
                    return path

                parallel_map(poor, _second_pass, max_workers=workers)

    return refined
