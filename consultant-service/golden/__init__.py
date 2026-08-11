"""The golden brief set — frozen UIDemoSpecs the image pipeline is measured against.

A "golden brief" is one business, frozen at the ui_spec stage: the intake
fields, the archetype the ui_spec stage chose for it, and the exact
UIDemoSpec for every screen. Everything downstream of these files is what
we are actually evaluating (prompt packs, models, QA gates, compositing).

Why frozen rather than regenerated per run: the ui_spec LLM stage produces
different data every call. Comparing two image models across two different
sets of KPI labels measures nothing. These files make the model (or the
prompt pack) the ONLY thing that varies — and make a re-run of any past
evaluation reproducible, months later, for $0 of text calls.

They were not hand-authored: scripts/build_golden.py ran the real ui_spec
stage on the real intake fixtures and froze its output, so a golden brief
is a genuine sample of what the pipeline sees in production, not an
idealized one.
"""

import json
import os

from app.ui_spec import UIDemoSpec

BRIEFS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "briefs")

# The three briefs the W1 bake-off runs on — deliberately three DIFFERENT
# archetypes, so a model that happens to be good at one layout shape can't
# win the whole matrix on that strength alone.
BAKEOFF_BRIEF_IDS = ("dental", "law", "retail")


def brief_ids() -> list[str]:
    if not os.path.isdir(BRIEFS_DIR):
        return []
    return sorted(f[: -len(".json")] for f in os.listdir(BRIEFS_DIR) if f.endswith(".json"))


def load_brief(brief_id: str) -> dict:
    """Returns the frozen bundle with `screens` parsed into UIDemoSpec objects."""
    path = os.path.join(BRIEFS_DIR, f"{brief_id}.json")
    with open(path, encoding="utf-8") as f:
        bundle = json.load(f)
    bundle["screens"] = [UIDemoSpec.model_validate(s) for s in bundle["screens"]]
    return bundle


def load_briefs(brief_ids_: tuple[str, ...] | list[str] | None = None) -> list[dict]:
    return [load_brief(bid) for bid in (brief_ids_ if brief_ids_ is not None else brief_ids())]


def brand_critical_strings(bundle: dict) -> dict:
    """The strings a shipped screen must render EXACTLY — the text-truth gate's
    ground truth (W3). Nav labels are per-screen; name/product are global.
    """
    anchor = bundle["screens"][0]
    return {
        "business_name": anchor.business.name,
        "product_name": anchor.product.name,
        "navigation": list(anchor.navigation),
    }
