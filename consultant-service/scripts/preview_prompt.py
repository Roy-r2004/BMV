"""Print the exact image prompt the pipeline would send — no network, no cost.

The image prompt is the whole product: everything the model does is
downstream of these words, and until now the only way to read one was to
spend $0.145 generating from it. This makes the prompt itself reviewable.

    python scripts/preview_prompt.py dental
    python scripts/preview_prompt.py dental --register light
    python scripts/preview_prompt.py --demo tool          # the tool-screen shape
    python scripts/preview_prompt.py dental --diff        # light vs cinematic

`--demo tool` renders a hand-authored selector spec rather than a frozen
golden brief: the frozen briefs predate the hero/concept/ai fields, so they
have nothing to show for them until the set is re-frozen under ui-spec-v2.
It is labelled a demo for exactly that reason — it is not evidence of what
the spec stage produces, only of what the builder does with it.
"""

import argparse
import difflib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import golden
from app.config import settings
from app.pipeline import prompt_builder
from app.ui_spec import UIDemoSpec

DEMO_SPECS = {
    "tool": {
        "business": {
            "name": "Garden View",
            "industry": "Residential property development",
            "location": "Beirut Central District",
            "primary_color": "#0B3B2E",
            "secondary_color": "#C9A227",
        },
        "product": {
            "name": "Garden View Explorer",
            "purpose": "choosing a residence",
            "screen_type": "block-floor-selection",
        },
        "user": {"name": "Rana", "role": "Sales Director"},
        "navigation": ["Residences", "Amenities", "Gallery", "Location", "About"],
        "greeting": "Block & Floor Selection",
        "subheading": "Choose a block and floor",
        "kpis": [
            {"label": "Blocks", "value": "3"},
            {"label": "Floors", "value": "61"},
            {"label": "Residences", "value": "180+"},
        ],
        "hero": {
            "subject": "a 30-storey glass residential tower at dusk above a lit city",
            "treatment": "photoreal render",
            "caption": "Block A",
            "placement": "center",
        },
        "concept": {
            "kind": "selector",
            "steps": [
                {"label": "Select Block", "options": ["Block A", "Block B", "Block C"], "selected": "Block A"},
                {"label": "Select Floor", "options": ["30", "25", "18", "12", "02"], "selected": "18"},
            ],
            "detail": {
                "title": "Block A · Level 18",
                "rows": [
                    {"unit": "A-1801", "beds": "2 Bedrooms", "size": "124.5 SQM"},
                    {"unit": "A-1802", "beds": "1 Bedroom", "size": "86.3 SQM"},
                    {"unit": "A-1803", "beds": "3 Bedrooms", "size": "162.4 SQM"},
                    {"unit": "A-1804", "beds": "2 Bedrooms", "size": "118.7 SQM"},
                ],
            },
            "primary_action": "View Floor Plan",
            "secondary_action": "Explore Units",
        },
        "ai": {
            "headline": "Recommended: A-1803",
            "rationale": "Best light, under budget, ready March",
            "confidence": "94% match",
            "chips": ["Corner unit", "Sea view", "Ready March"],
        },
        "style": {"archetype": "operations-dashboard", "density": "normal"},
    },
}


def _spec(args) -> tuple[UIDemoSpec, str | None, str]:
    if args.demo:
        return UIDemoSpec.model_validate(DEMO_SPECS[args.demo]), None, f"demo:{args.demo}"
    bundle = golden.load_brief(args.brief)
    return bundle["screens"][0], bundle["archetype"], f"golden:{args.brief}"


def _build(spec: UIDemoSpec, archetype_id: str | None, register: str) -> str:
    settings.IMAGE_REGISTER = register
    return prompt_builder.build_dashboard_image_prompt(spec, archetype_id=archetype_id)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("brief", nargs="?", help="a golden brief id (see golden/briefs/)")
    ap.add_argument("--demo", choices=sorted(DEMO_SPECS), help="a hand-authored spec instead of a frozen brief")
    ap.add_argument("--register", default=None, choices=("cinematic", "light"))
    ap.add_argument("--diff", action="store_true", help="unified diff, light -> cinematic")
    ap.add_argument("--out", help="write to this path instead of stdout")
    args = ap.parse_args()

    if not args.brief and not args.demo:
        ap.error("give a brief id or --demo")

    spec, archetype_id, source = _spec(args)

    if args.diff:
        light = _build(spec, archetype_id, "light").splitlines(keepends=True)
        cinematic = _build(spec, archetype_id, "cinematic").splitlines(keepends=True)
        text = "".join(difflib.unified_diff(light, cinematic, "light", "cinematic", n=1))
    else:
        register = args.register or settings.IMAGE_REGISTER
        prompt = _build(spec, archetype_id, register)
        version = prompt_builder.prompt_version(
            prompt_builder.DASHBOARD_IMAGE_PROMPT_VERSION, spec, archetype_id
        )
        header = (
            f"# source: {source}\n"
            f"# prompt_version: {version}\n"
            f"# watermark: {settings.WATERMARK_STYLE}\n"
            f"# characters: {len(prompt)}\n\n"
        )
        text = header + prompt + "\n"

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {args.out} ({len(text)} chars)")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
