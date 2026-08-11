import os

from dotenv import load_dotenv

load_dotenv()


def _env_or(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


class Settings:
    # Everything routes through OpenRouter — one key, one place cost is tracked.
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "").strip()
    ANALYSIS_MODEL: str = _env_or("ANALYSIS_MODEL", "google/gemini-2.5-flash")
    # Bake-off (2026-08-10, dashboard-image-v1 prompt, same input): gemini-3-pro
    # rendered a crisp true-16:9 desktop screenshot at $0.14; gpt-5.4-image-2 was
    # close but square/softer at $0.25; gpt-5-image bled content off both edges
    # with typos at $0.29. Gemini also accepts image input, which the
    # screen-continuation step needs.
    IMAGE_MODEL: str = _env_or("IMAGE_MODEL", "google/gemini-3-pro-image")

    # ── Per-role, per-archetype image models (W1) ─────────────────────────
    # The anchor screen and the follow-up screens are different jobs: the
    # anchor invents a design, the follow-ups copy one they're handed as a
    # reference image. So the model is chosen per ROLE, and per archetype —
    # a kanban pipeline and a chart-led analytics screen don't have to be
    # best served by the same model. Entries are written here ONLY from a
    # measured bake-off (see docs/evidence/session31/images-bakeoff.md);
    # anything absent falls back to IMAGE_MODEL, so an archetype nobody has
    # measured behaves exactly as before.
    #
    # Measured 2026-08-11, W1 bake-off (docs/evidence/session31/images-bakeoff.md).
    # Same answer on all three archetypes measured, so the entries are
    # identical — kept per-archetype anyway because that is the axis a
    # future measurement will disagree on, and a shared constant would
    # quietly hide the disagreement:
    #   anchor   = gemini-3-pro-image. Won the swap-tested pairwise on crm
    #              and analytics, tied on operations, and matched or beat
    #              flash's anchor QA everywhere (8.7 / 8.7 / 8.7 vs
    #              8.7 / 7.9 / 8.7). gpt-5.4-image-2 was eliminated: it
    #              renders SQUARE, took 354s, and scored lowest.
    #   followup = gemini-3.1-flash-image. Follow-ups copy a design they
    #              are handed as a reference image rather than inventing
    #              one, which is the cheaper job — and all-pro costs $0.72
    #              for a 3-screen request, over the $0.60 DoD line, while
    #              this tiering measured $0.583 at 175s.
    # HONEST LIMIT: the pro-anchor + flash-follow-up combination was
    # measured end-to-end on operations-dashboard only. crm and analytics
    # inherit it by extrapolation from their all-flash follow-up scores
    # (8.7 and 7.0), not from a tiering run of their own.
    ARCHETYPE_IMAGE_MODELS: dict[str, dict[str, str]] = {
        "operations-dashboard": {"anchor": "google/gemini-3-pro-image", "followup": "google/gemini-3.1-flash-image"},
        "crm-dashboard": {"anchor": "google/gemini-3-pro-image", "followup": "google/gemini-3.1-flash-image"},
        "analytics-dashboard": {"anchor": "google/gemini-3-pro-image", "followup": "google/gemini-3.1-flash-image"},
        # scheduling-dashboard and pipeline-dashboard are unmeasured — no
        # golden brief landed on them — so they fall back to IMAGE_MODEL.
    }
    # Operator-level escape hatches (env), used by bake-off runs and by
    # incident response — they outrank the measured table on purpose.
    IMAGE_MODEL_ANCHOR: str = _env_or("IMAGE_MODEL_ANCHOR", "")
    IMAGE_MODEL_FOLLOWUP: str = _env_or("IMAGE_MODEL_FOLLOWUP", "")

    # What a follow-up screen runs on when its archetype has no measured
    # entry above. Added 2026-08-11 because the old chain fell through to
    # IMAGE_MODEL, which is pro-class — so a request landing on
    # scheduling-dashboard or pipeline-dashboard (both real, both selectable
    # by the public intake, neither covered by any golden brief) ran
    # pro-class on all four calls and projected at $0.68, over the $0.60 DoD
    # line. Nothing said so, because every measurement this project has ever
    # taken was on one of the three archetypes that DO have entries.
    #
    # This is an EXTRAPOLATION, deliberately kept out of the measured table
    # above so the table stays "measured cells only". What is measured is
    # that follow-ups are a different, cheaper job — they copy a design
    # handed to them as a reference image rather than inventing one — and
    # that finding came back identical on all three archetypes tested. What
    # is NOT measured is this model on these two archetypes.
    #
    # Set to empty to restore the old behaviour (follow-ups on IMAGE_MODEL).
    # To force one model on both roles, use IMAGE_MODEL_ANCHOR /
    # IMAGE_MODEL_FOLLOWUP — they outrank this, and setting IMAGE_MODEL
    # alone no longer does it.
    FOLLOWUP_MODEL_FALLBACK: str = _env_or("FOLLOWUP_MODEL_FALLBACK", "google/gemini-3.1-flash-image")

    # ── Output resolution (JOB 1, session 34) ─────────────────────────────
    # Asked of the model via OpenRouter's image_config; empty string = send
    # nothing and take the model's default (~1376x768).
    #
    # Probed 2026-08-12 on the real salon anchor prompt
    # (docs/evidence/session34/probe/results.json):
    #   gemini-3.1-flash-image at 2K  -> 2752x1536, the same 1.79:1 shape as
    #                                    its default, $0.1019/image (ledger-
    #                                    measured default: $0.070), 24s.
    #   gemini-3-pro-image at 2K      -> IGNORED on both slugs: 1376x768,
    #                                    image_tokens=1120, price unchanged.
    #
    # Why the default is follow-ups-only: five of the six collapsed-
    # letterform defects in the session-33 sweep ("Cilents", "Portfollo",
    # "Highiights", "beoking", "10:1S") are on flash FOLLOW-UP screens,
    # and flash honours the request. The sixth ("SLB", retail's analytics)
    # was a PRO ANCHOR — a residual risk resolution cannot fix, because
    # pro ignores the field; it is left to the text-truth gate and the
    # regeneration it buys. The anchor knob exists so the probe can be
    # re-run from env when a provider change makes pro honour it too.
    IMAGE_SIZE_ANCHOR: str = _env_or("IMAGE_SIZE_ANCHOR", "")
    IMAGE_SIZE_FOLLOWUP: str = _env_or("IMAGE_SIZE_FOLLOWUP", "2K")
    # Sent only when a size is set. 16:9 maps to the same 1.79:1 the models
    # produce unprompted, so this changes pixel count, never composition.
    IMAGE_ASPECT_RATIO: str = _env_or("IMAGE_ASPECT_RATIO", "16:9")

    def image_config_for_role(self, role: str) -> dict | None:
        size = self.IMAGE_SIZE_ANCHOR if role == "anchor" else self.IMAGE_SIZE_FOLLOWUP
        if not size:
            return None
        return {"image_size": size, "aspect_ratio": self.IMAGE_ASPECT_RATIO}

    def anchor_model_for(self, archetype_id: str | None) -> str:
        return (
            self.IMAGE_MODEL_ANCHOR
            or self.ARCHETYPE_IMAGE_MODELS.get(archetype_id or "", {}).get("anchor")
            or self.IMAGE_MODEL
        )

    def followup_model_for(self, archetype_id: str | None) -> str:
        return (
            self.IMAGE_MODEL_FOLLOWUP
            or self.ARCHETYPE_IMAGE_MODELS.get(archetype_id or "", {}).get("followup")
            or self.FOLLOWUP_MODEL_FALLBACK
            or self.IMAGE_MODEL
        )

    # Soft bounds, not a fixed target — the plan stage decides the actual
    # count per business (see prompts/plan.j2). MIN only guards the fallback
    # path; MAX is a cost/sanity cap on a real model response.
    MIN_ROLES_PER_REQUEST: int = int(_env_or("MIN_ROLES_PER_REQUEST", "2"))
    MAX_ROLES_PER_REQUEST: int = int(_env_or("MAX_ROLES_PER_REQUEST", "4"))
    VARIANTS_PER_ROLE: int = int(_env_or("VARIANTS_PER_ROLE", "2"))

    # ── Demo-screenshot pipeline (cost knobs — this is lead gen) ──────────
    # Screens per request (anchor dashboard + follow-ups, 2-3).
    DEMO_SCREEN_COUNT: int = int(_env_or("DEMO_SCREEN_COUNT", "3"))
    # Candidates generated for the anchor screen; the vision judge picks the
    # best. More candidates = better anchor = better whole set, since every
    # follow-up screen inherits the anchor's look via reference image.
    #
    # 2, not 3, since 2026-08-11. The anchor is the expensive screen — it runs
    # on the pro-class model at a measured $0.14578 a call — so this knob moves
    # a request's cost more than anything else in this file. At 3 the projected
    # request lands at ~$0.60, exactly ON the DoD ceiling with no headroom for
    # the one regeneration MAX_REGENERATIONS allows; at 2 it lands at ~$0.45.
    # The third candidate was also the weakest lever available: composition
    # variants are ranked by a judge that scored four materially different
    # conditions at exactly 9.2 (docs/evidence/session32/results.md), so
    # "the judge picked the best of 3" is not a claim this project can support.
    # Pinned by tests/test_cost_model.py.
    DASHBOARD_CANDIDATES: int = int(_env_or("DASHBOARD_CANDIDATES", "2"))
    SECONDARY_CANDIDATES: int = int(_env_or("SECONDARY_CANDIDATES", "1"))
    # Vision-model QA over every candidate (cheap flash call per image).
    ENABLE_VISION_QA: bool = _env_bool("ENABLE_VISION_QA", True)
    QA_MODEL: str = _env_or("QA_MODEL", _env_or("ANALYSIS_MODEL", "google/gemini-2.5-flash"))
    # 8, not 7, since 2026-08-12 — owner's decision, and it closes a gap that
    # had been open the whole time: DoD line 2 says "no shipped screen scores
    # below 8" and this gate accepted 7. The pipeline had never been
    # configured to enforce the number it is judged against, and sessions 31
    # and 32 passed that clause by luck rather than by construction (session
    # 33's golden set shipped four screens between 7.5 and 7.9).
    #
    # Measured consequence, from the 20 candidates of that run: at 7 the gate
    # rejected 2, at 8 it would have rejected 7 — so roughly one extra image
    # per request, about $0.10. Nominal projection is unchanged because a
    # regeneration only fires when nothing was approved; the EXPECTED cost
    # rises to ~$0.55 and the worst case is unchanged at $0.75.
    #
    # It still does not GUARANTEE the floor: when no candidate is approved,
    # _render_screen ships the best of a bad set rather than failing the
    # request. Raising the gate buys another roll of the dice, not certainty.
    # tests/test_qa_and_selection.py pins this against DOD_MIN_SHIPPED_SCORE
    # so the two can never drift apart silently again.
    QA_MIN_SCORE: float = float(_env_or("QA_MIN_SCORE", "8"))
    # The pairwise judge ("which of these two is better") is a separate
    # instrument from the per-image scorer and may need more capability:
    # comparing two dense screenshots is harder than scoring one. Kept as
    # its own setting so it can be strengthened WITHOUT ever varying the
    # per-image judge — the rule is that judge and generator never change
    # together, not that one model must do both jobs.
    PAIRWISE_JUDGE_MODEL: str = _env_or("PAIRWISE_JUDGE_MODEL", _env_or("QA_MODEL", "google/gemini-2.5-flash"))
    # W3 text-truth gate: transcribe what the image actually rendered and
    # diff the brand-critical strings (business name, product name, nav
    # labels) against the spec in code. A misspelled client name is an
    # auto-reject at any aesthetic score. One extra cheap vision call per
    # candidate (~$0.001).
    ENABLE_TEXT_TRUTH_GATE: bool = _env_bool("ENABLE_TEXT_TRUTH_GATE", True)
    # Attach 3x magnifications of the top and left bands to the transcription
    # call. The gate's job is to notice a misspelled brand string, and on the
    # session-33 golden set it missed one ("Cilents" for "Clients") because
    # the label is ~10px tall and the transcriber read the word it expected.
    # Deterministic PIL crops, no extra model call, a few tenths of a cent in
    # extra image input. Off restores the single-image call exactly.
    ENABLE_TEXT_TRUTH_ZOOM: bool = _env_bool("ENABLE_TEXT_TRUTH_ZOOM", True)
    # JOB 3 (session 34): per-screen structural defect check. One inspector
    # reports countable structural defects (text claims forbidden — text
    # truth is text_truth.py's job), then EACH claim goes to a separate
    # verifier told to refute it, defaulting to refuted when uncertain. A
    # claim both stages agree on rejects the candidate; the existing
    # regeneration path handles the rest. This two-stage shape found 13 of
    # 15 golden-set screens defective in session 33 — including two the
    # per-image judge scored 9.2 — and refuted 16 further claims that would
    # each have been a single-stage false rejection. Runs concurrently with
    # the judge and the transcription, on the flash-class model: cents.
    ENABLE_DEFECT_CHECK: bool = _env_bool("ENABLE_DEFECT_CHECK", True)
    DEFECT_MODEL: str = _env_or("DEFECT_MODEL", _env_or("QA_MODEL", "google/gemini-2.5-flash"))
    # W2 art-direction packs: a per-archetype design system (type pairing,
    # density, chart treatment, color stance) appended to the image prompt.
    #
    # DEFAULT OFF — the A/B did not win. Measured 2026-08-11 on two
    # archetypes, swap-tested pairwise: 0 wins, 2 losses, and all four
    # judged runs named the same cause — the pack's denser, fuller layout
    # pushes content into the bottom-right corner reserved for the
    # composited logo, which is a structural defect that outweighs the
    # craft it does add. (Per-image QA scores went the other way, 9.1/8.5
    # with the pack vs 8.7/7.5 without; pairwise is the better instrument
    # and it says no.) Turn on only after W4 changes where the watermark
    # lives and the comparison is re-run.
    # See docs/evidence/session31/art-packs-ab.md.
    ENABLE_ART_PACKS: bool = _env_bool("ENABLE_ART_PACKS", False)
    # W4 presentation compositing: browser chrome, shadow, brand backdrop
    # and detail crops, all PIL. No model call, no cost, no variance — the
    # deck's artifacts, and the reason the image model is never asked for a
    # device mockup (it garbles the UI text it just got right).
    ENABLE_PRESENTATION_COMPOSITING: bool = _env_bool("ENABLE_PRESENTATION_COMPOSITING", True)
    # JOB 2 (session 34): when the model draws the interface as a rounded
    # card floating on a backdrop — forbidden in the prompt twice, drawn
    # anyway on 5 of 15 session-33 screens — detect it deterministically in
    # PIL and crop to the interface. Conservative by construction (three
    # independent guards, see images._floating_backdrop_bbox); a full-bleed
    # screen passes through bit-identical, pinned.
    ENABLE_BACKDROP_CROP: bool = _env_bool("ENABLE_BACKDROP_CROP", True)
    # ── Session 32: the cinematic register ───────────────────────────────
    # Where the BMV mark goes. "footer" grows the canvas by a thin strip
    # BELOW the interface and puts the mark there; "corner" is the original
    # behaviour, pasting it over the bottom-right of the screenshot.
    #
    # This is not a cosmetic preference. The corner mark forced the image
    # prompt to reserve ~12%x17% of the canvas, and that reservation is the
    # single cause named by every losing comparison in session 31 (W2 art
    # packs 0-2, W5 design sheet, one W1 cell) — anything that makes the
    # model fill the canvas more confidently pushes content under the mark.
    # It also mis-fires today: in both session-31 anchors the logo sits on
    # top of the AI card and clips its status text.
    # See docs/evidence/session31/art-packs-ab.md.
    WATERMARK_STYLE: str = _env_or("WATERMARK_STYLE", "footer")
    # The design register the image prompt asks for.
    #   "light"     — the original Linear/Stripe/Ramp light interface.
    #   "cinematic" — deep single-hue ground, one luminous accent, a
    #                 photoreal hero asset, display typography.
    # "light" is kept reachable ONLY so the funded A/B has something to
    # compare against; it is not a fallback path and nothing selects it
    # automatically.
    IMAGE_REGISTER: str = _env_or("IMAGE_REGISTER", "cinematic")
    # A rendered, industry-specific centerpiece inside the app's content
    # area (the tower render in a property configurator, the machine in a
    # plant monitor). Plays to what image models are actually good at —
    # photoreal rendering — instead of spending the whole canvas on the
    # small dense text they are worst at.
    ENABLE_HERO_ASSET: bool = _env_bool("ENABLE_HERO_ASSET", True)
    # Let a screen be a TOOL (selector / configurator / explorer) rather
    # than always a metrics dashboard. Without this the spec has no field
    # in which "choose a block, then a floor, then a unit" can be said, so
    # no prompt can produce it.
    ENABLE_TOOL_SCREENS: bool = _env_bool("ENABLE_TOOL_SCREENS", True)
    # Promote AI from a log card ("AI Workstream", three rows) to a
    # first-class module carrying a recommendation, its reasoning and a
    # confidence read. Nobody says "wow" at a log.
    ENABLE_AI_LAYER: bool = _env_bool("ENABLE_AI_LAYER", True)

    # W5 experiment: generate a design-system style board first and condition
    # every screen on it, instead of letting follow-ups inherit whatever the
    # anchor happened to do. Costs one extra image per request. Default off
    # until the experiment wins — see docs/evidence/session31/.
    USE_DESIGN_SHEET: bool = _env_bool("USE_DESIGN_SHEET", False)
    # At most ONE extra attempt per screen when no candidate is approved —
    # never an open-ended regeneration loop.
    MAX_REGENERATIONS: int = int(_env_or("MAX_REGENERATIONS", "1"))
    # Attach the selected anchor screenshot to follow-up screen calls so all
    # screens look like the same product (needs an image-input-capable model).
    USE_REFERENCE_IMAGES: bool = _env_bool("USE_REFERENCE_IMAGES", True)
    # Money-safety valve on the open intake endpoint: how many requests may
    # be generating simultaneously before new submissions get a 429.
    MAX_CONCURRENT_GENERATIONS: int = int(_env_or("MAX_CONCURRENT_GENERATIONS", "3"))

    # INFO, because the pipeline's INFO lines are the run's only narrative:
    # per-candidate score, winning composition variant, model, and the
    # text-truth rejections. Set to WARNING for a quiet console.
    LOG_LEVEL: str = _env_or("LOG_LEVEL", "INFO").upper()

    DATABASE_URL: str = _env_or("DATABASE_URL", "sqlite:///./consultant.db")
    PORT: int = int(_env_or("PORT", "8002"))
    FRONTEND_ORIGIN: str = _env_or("FRONTEND_ORIGIN", "http://localhost:5173")

    UPLOADS_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")

    # The real BMV logo, composited onto every generated image as a corner
    # credit mark — more reliable than asking the image model to draw
    # legible "BMV" text (we've seen it garble small text like URLs/labels).
    BMV_LOGO_PATH: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "frontend", "public", "logo.png",
    )


settings = Settings()
