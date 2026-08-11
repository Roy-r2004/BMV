"""Local test command for the demo-screenshot pipeline.

    python scripts/demo_image_test.py --business dental
    python scripts/demo_image_test.py --business hvac --generate
    python scripts/demo_image_test.py --business law --generate --model google/gemini-3-pro-image
    python scripts/demo_image_test.py --business salon --generate \
        --anchor-model google/gemini-3-pro-image \
        --followup-model google/gemini-3.1-flash-image      # tiering trial

Without --generate: runs analysis -> UIDemoSpec -> prompt building only
(one cheap text call if OPENROUTER_API_KEY is set, deterministic fallback
otherwise) and prints the specs + image prompts for inspection.

With --generate: ALSO runs real image generation + vision QA (REAL COST —
roughly $0.15-0.30 per image depending on model). Outputs land in
scripts/out/<business>/ and the total cost is printed from the usage table.

Uses the real dev DB and the real pipeline code paths on purpose — rows are
created with status="test" so they're easy to spot and delete.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from golden.intake import INTAKE_FIXTURES as FIXTURES


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--business", choices=sorted(FIXTURES), default="dental")
    parser.add_argument("--generate", action="store_true", help="really generate images (REAL COST)")
    parser.add_argument("--model", help="override IMAGE_MODEL for this run (bake-offs)")
    parser.add_argument("--anchor-model", help="model for the anchor screen only (tiering trial)")
    parser.add_argument("--followup-model", help="model for follow-up screens only (tiering trial)")
    parser.add_argument("--screens", type=int, help="limit to the first N screens (e.g. 1 = anchor dashboard only, for cheap prompt iteration)")
    parser.add_argument("--reuse-spec", help="path to a saved <n>_<screen>.spec.json — skip ui_spec's LLM call and reuse this exact spec, for a clean prompt-only A/B test")
    parser.add_argument("--reference", help="path to a PNG attached as a style reference to the ANCHOR generation itself — for the no-reference-vs-reference ceiling experiment; prompt text is unchanged")
    args = parser.parse_args()

    from app.config import settings

    if args.model:
        settings.IMAGE_MODEL = args.model

    from app.database import SessionLocal, init_db
    from app.models import AiUsageEvent, Request
    from app.pipeline import prompt_builder, ui_spec
    from app.ui_spec import UIDemoSpec

    init_db()
    fixture = FIXTURES[args.business]
    db = SessionLocal()
    req = Request(
        business_name=fixture["business_name"],
        business_description=fixture["business_description"],
        industry=fixture["industry"],
        email=fixture["email"],
        status="test",
        is_generating=False,
    )
    db.add(req)
    db.commit()
    print(f"[fixture={args.business}] test request id={req.id} model={settings.IMAGE_MODEL}")

    if args.reuse_spec:
        with open(args.reuse_spec, encoding="utf-8") as f:
            spec = UIDemoSpec.model_validate_json(f.read())
        archetype_id, specs = spec.style.archetype, [spec]
        print(f"reusing spec from {args.reuse_spec} (archetype={archetype_id}) — no ui_spec LLM call")
    else:
        archetype_id, specs = ui_spec.build_ui_specs(db, req.id, fixture["consult_result"], fixture["plan_result"])
    if args.screens:
        specs = specs[: args.screens]
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", args.business)
    os.makedirs(out_dir, exist_ok=True)

    print(f"\narchetype: {archetype_id}")
    prompts: list[tuple[str, str]] = []
    for i, spec in enumerate(specs):
        if i == 0:
            prompt = prompt_builder.build_dashboard_image_prompt(spec)
        else:
            prompt = prompt_builder.build_continuation_prompt(spec, specs[0].screen_title)
        prompts.append((spec.screen_slug, prompt))
        spec_path = os.path.join(out_dir, f"{i}_{spec.screen_slug}.spec.json")
        prompt_path = os.path.join(out_dir, f"{i}_{spec.screen_slug}.prompt.txt")
        with open(spec_path, "w", encoding="utf-8") as f:
            f.write(spec.model_dump_json(indent=2))
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"\n===== screen {i}: {spec.screen_title} =====")
        print(f"  spec   -> {spec_path}")
        print(f"  prompt -> {prompt_path}")
        print(f"  kpis: {[k.label for k in spec.kpis]}")
        print(f"  nav:  {spec.navigation}")

    if not args.generate:
        print("\n(no images generated — pass --generate for a real paid run)")
        return

    from app.pipeline import images as images_stage

    anchor_reference_images = None
    if args.reference:
        with open(args.reference, "rb") as f:
            anchor_reference_images = [f.read()]
        print(f"attaching anchor reference: {args.reference}")

    print("\ngenerating images (REAL COST)...")
    saved = images_stage.generate_demo_screens(
        db, req.id, archetype_id, specs,
        anchor_reference_images=anchor_reference_images,
        anchor_model=args.anchor_model,
        followup_model=args.followup_model,
    )
    for row in saved:
        abs_path = os.path.join(settings.UPLOADS_DIR, row.file_path.split("/uploads/", 1)[1])
        print(f"  {row.role_label}: qa={row.qa_score} -> {abs_path}")

    total = sum(
        e.cost_usd or 0
        for e in db.query(AiUsageEvent).filter(AiUsageEvent.request_id == req.id)
    )
    print(f"\ntotal cost for this run: ${total:.3f}")


if __name__ == "__main__":
    main()
