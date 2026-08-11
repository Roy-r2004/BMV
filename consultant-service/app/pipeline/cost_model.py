"""What a request is PROJECTED to cost, from the knobs that decide it.

DoD line 4 is a number — "≤ $0.60 per request" — and until this module
existed nothing in the repo could evaluate it without spending money. The
knobs that set it (DASHBOARD_CANDIDATES, DEMO_SCREEN_COUNT,
SECONDARY_CANDIDATES, the per-archetype model table) live in config.py
where each looks individually harmless; it is only their product that
crosses the line. Raising DASHBOARD_CANDIDATES back to 3 puts a request at
roughly $0.60 with no headroom left for the regeneration MAX_REGENERATIONS
allows, and nothing would have said so.

Two honest limits on the arithmetic here:

  - The per-image rates are MEASURED from this service's own ai_usage_events
    rows, not quoted from a price list, and they are a snapshot. A provider
    price change makes them stale, and the only thing that will notice is a
    funded run diverging from the projection.
  - It projects the IMAGE spend plus the per-candidate QA calls. The text
    stages (analyze → consult → plan → blueprint → ui_spec) are counted as
    one measured constant rather than modelled, because their cost is
    dominated by model output length rather than by any knob in config.py.

The shape of the count mirrors images.generate_demo_screens exactly — one
call per anchor composition variant, SECONDARY_CANDIDATES per follow-up
screen, at most MAX_REGENERATIONS extra per screen. If that function's
shape changes, this one is wrong, and the pin in tests/test_cost_model.py
is what says so.
"""

from app.config import settings

# Measured 2026-08-11 from ai_usage_events (successful purpose='image' rows):
#   google/gemini-3-pro-image      90 calls, mean $0.14578 (range $0.141–0.158)
#   google/gemini-3.1-flash-image  25 calls, mean $0.06959 (range $0.068–0.071)
#   openai/gpt-5.4-image-2          5 calls, mean $0.26197  (eliminated in W1)
MEASURED_IMAGE_COST_USD: dict[str, float] = {
    "google/gemini-3-pro-image": 0.14578,
    "google/gemini-3.1-flash-image": 0.06959,
    "openai/gpt-5.4-image-2": 0.26197,
}
# The same models asked for a 2K canvas (image_config, session 34).
#   flash: 3 ledgered calls on request 76 (the s34-2k salon run), mean
#          $0.10341 (range $0.1025–0.1052) — 1680 image tokens vs ~1290
#          at the default size.
#   pro:   probe-measured once (docs/evidence/session34/probe/) — it
#          IGNORES the size request on both slugs and bills exactly its
#          default 1120 tokens, which is why its entry equals its
#          default rate.
MEASURED_IMAGE_COST_2K_USD: dict[str, float] = {
    "google/gemini-3.1-flash-image": 0.10341,
    "google/gemini-3-pro-image": 0.14663,
}
# Anything unmeasured is costed at the most expensive thing we have ever run,
# so an unknown model can only ever make a projection look WORSE than it is.
# A projection that flatters an unmeasured model is the failure mode that
# would matter here.
UNMEASURED_IMAGE_COST_USD = max(MEASURED_IMAGE_COST_USD.values())

# Measured 2026-08-11, same source: one aesthetic judge call ($0.00112) plus
# one transcription call ($0.00169) per candidate.
QA_COST_PER_CANDIDATE_USD = 0.00281
# The structural defect check (JOB 3): one inspector plus its verifier
# calls. Measured on request 77 (the s34-defects dental run): 6 inspections
# $0.006153 + 9 verifications $0.007540 over 6 candidates = $0.00228 per
# candidate at the observed 1.5 claims/candidate. Counted only while
# ENABLE_DEFECT_CHECK is on.
DEFECT_CHECK_COST_PER_CANDIDATE_USD = 0.00228
# analyze + consult + plan + blueprint + technical_plan + ui_spec, all on
# ANALYSIS_MODEL. Measured on request 68, the first end-to-end run through
# the public intake path (docs/evidence/session33/job1-real-pipeline.md):
#   analyze $0.00070  consult $0.00102  plan $0.00121
#   blueprint $0.00186  technical_plan $0.00348  ui_spec $0.01012
# One sample, so it is a constant rather than a model. It is also 3.4% of a
# request — the images are the cost, and this line exists so the projection
# is not silently short by a rounding error's worth of text.
TEXT_STAGES_COST_USD = 0.01839


def projected_image_count(archetype_id: str | None = None) -> dict:
    """Images a request generates: nominal, and with every screen taking the
    one regeneration it is allowed."""
    screens = max(2, min(3, settings.DEMO_SCREEN_COUNT))
    anchor_candidates = max(1, settings.DASHBOARD_CANDIDATES)
    followup_candidates = (screens - 1) * max(1, settings.SECONDARY_CANDIDATES)
    nominal = anchor_candidates + followup_candidates
    return {
        "screens": screens,
        "anchor_candidates": anchor_candidates,
        "followup_candidates": followup_candidates,
        "nominal": nominal,
        # One regeneration per screen is the cap, not the expectation: it only
        # fires when no candidate for that screen was approved.
        "worst_case": nominal + screens * max(0, settings.MAX_REGENERATIONS),
    }


def _rate(model: str, image_size: str | None = None) -> float:
    """The measured $/image for a model at the size the pipeline will ask it
    for. A size we have never measured falls to the most-expensive-known
    rate, same principle as an unmeasured model — never flatter the
    projection with an assumed bargain."""
    if image_size == "2K":
        return MEASURED_IMAGE_COST_2K_USD.get(model, UNMEASURED_IMAGE_COST_USD)
    if image_size:
        return UNMEASURED_IMAGE_COST_USD
    return MEASURED_IMAGE_COST_USD.get(model, UNMEASURED_IMAGE_COST_USD)


def projected_request_cost(archetype_id: str | None = None) -> dict:
    """USD a request is projected to cost, at the models this archetype
    actually resolves to. `nominal_usd` is the number DoD line 4 is about."""
    counts = projected_image_count(archetype_id)
    anchor_rate = _rate(settings.anchor_model_for(archetype_id), settings.IMAGE_SIZE_ANCHOR or None)
    followup_rate = _rate(settings.followup_model_for(archetype_id), settings.IMAGE_SIZE_FOLLOWUP or None)

    images_nominal = counts["anchor_candidates"] * anchor_rate + counts["followup_candidates"] * followup_rate
    # A regeneration re-fires the screen's OWN model, so the anchor's retry is
    # a pro-class call and a follow-up's is not.
    regen_per_screen = max(0, settings.MAX_REGENERATIONS)
    images_worst = images_nominal + regen_per_screen * (anchor_rate + (counts["screens"] - 1) * followup_rate)

    per_candidate_qa = QA_COST_PER_CANDIDATE_USD + (
        DEFECT_CHECK_COST_PER_CANDIDATE_USD if settings.ENABLE_DEFECT_CHECK else 0
    )
    qa_nominal = counts["nominal"] * per_candidate_qa
    qa_worst = counts["worst_case"] * per_candidate_qa

    return {
        **counts,
        "anchor_model": settings.anchor_model_for(archetype_id),
        "followup_model": settings.followup_model_for(archetype_id),
        "images_usd": round(images_nominal, 5),
        "qa_usd": round(qa_nominal, 5),
        "text_stages_usd": TEXT_STAGES_COST_USD,
        "nominal_usd": round(images_nominal + qa_nominal + TEXT_STAGES_COST_USD, 5),
        "worst_case_usd": round(images_worst + qa_worst + TEXT_STAGES_COST_USD, 5),
    }
