"""Intake fixtures — the business inputs behind the golden briefs.

One dict per business, shaped exactly like what the pipeline's earlier
stages hand to ui_spec (`consult_result` + `plan_result`), so the golden
briefs can be rebuilt from scratch without re-running analyze/consult/plan.

Lives here rather than in scripts/demo_image_test.py (its original home)
because two consumers now need the same inputs: the ad-hoc test command
and scripts/build_golden.py, which freezes them into the golden set. The
set spans every archetype in app/archetypes.py — the evaluation must not
be able to hide a model that is only good at one layout shape.
"""

INTAKE_FIXTURES: dict[str, dict] = {
    "dental": {
        "business_name": "SmileBright Dental",
        "business_description": (
            "Family dental clinic with 3 dentists and 2 hygienists. Cleanings, crowns, implants, "
            "Invisalign. Struggles with no-shows and slow recall of lapsed patients."
        ),
        "industry": "Dental Clinic",
        "email": "test@example.com",
        "consult_result": {
            "consulting_summary": "An AI front-desk that fills the schedule, chases no-shows and recalls lapsed patients automatically.",
        },
        "plan_result": {
            "concept_name": "SmileBright Operations",
            "visual_theme": {"primary_color": "#0e9594", "secondary_color": "#1d4ed8", "mood": "clean, clinical, trustworthy"},
        },
    },
    "hvac": {
        "business_name": "Summit Air Heating & Cooling",
        "business_description": (
            "Residential HVAC company with 6 technicians. Installs, repairs, seasonal maintenance plans. "
            "Loses jobs to slow estimate follow-up and messy dispatching."
        ),
        "industry": "HVAC Services",
        "email": "test@example.com",
        "consult_result": {
            "consulting_summary": "An AI dispatcher that books jobs, routes technicians and chases open estimates before they go cold.",
        },
        "plan_result": {
            "concept_name": "Summit Dispatch",
            "visual_theme": {"primary_color": "#ea580c", "secondary_color": "#0f766e", "mood": "practical, dependable"},
        },
    },
    "law": {
        "business_name": "Hartwell & Grey LLP",
        "business_description": (
            "Boutique family-law firm, 4 attorneys. Consultations, mediation, litigation. "
            "New-lead intake is manual and follow-ups slip through the cracks."
        ),
        "industry": "Law Firm",
        "email": "test@example.com",
        "consult_result": {
            "consulting_summary": "An AI intake paralegal that qualifies leads, books consultations and keeps every matter's follow-ups on schedule.",
        },
        "plan_result": {
            "concept_name": "Hartwell Chambers",
            "visual_theme": {"primary_color": "#1e3a5f", "secondary_color": "#8a6d3b", "mood": "authoritative, discreet"},
        },
    },
    "salon": {
        "business_name": "Lumière Hair Studio",
        "business_description": (
            "Upscale hair salon with 5 stylists and a dedicated color specialist. Cuts, color, styling, "
            "bridal packages. Loses revenue to stylist double-booking and last-minute cancellations."
        ),
        "industry": "Hair Salon",
        "email": "test@example.com",
        "consult_result": {
            "consulting_summary": "An AI concierge that manages stylist schedules, fills cancellations instantly and upsells add-on services at booking.",
        },
        "plan_result": {
            "concept_name": "Lumière Studio OS",
            "visual_theme": {"primary_color": "#b76e79", "secondary_color": "#2d2a26", "mood": "elegant, warm, editorial"},
        },
    },
    "hedgefund": {
        "business_name": "Meridian Capital Partners",
        "business_description": (
            "Boutique long/short equity hedge fund managing $180M for institutional and high-net-worth "
            "clients, 6 analysts. Investor reporting and portfolio risk monitoring are manual and slow."
        ),
        "industry": "Hedge Fund / Asset Management",
        "email": "test@example.com",
        "consult_result": {
            "consulting_summary": "An AI analyst that monitors portfolio risk in real time, drafts investor updates and flags exposure limits before they're breached.",
        },
        "plan_result": {
            "concept_name": "Meridian Intelligence",
            "visual_theme": {"primary_color": "#0a2540", "secondary_color": "#c9a227", "mood": "authoritative, precise, institutional"},
        },
    },
    # Added for the golden set: a numbers-first business, the natural home of
    # the analytics archetype (hero chart, top-items table) — the layout shape
    # none of the five originals reliably lands on.
    "retail": {
        "business_name": "Northgate Coffee Roasters",
        "business_description": (
            "Specialty coffee roastery with one café and a growing online subscription business. "
            "Wholesale accounts with 12 local cafés. Nobody has time to watch which blends are "
            "selling, and reorder decisions are made from gut feel."
        ),
        "industry": "Coffee Roastery & E-commerce",
        "email": "test@example.com",
        "consult_result": {
            "consulting_summary": "An AI merchandiser that watches sales and subscription churn daily, forecasts roast volumes and flags reorders before a blend runs out.",
        },
        "plan_result": {
            "concept_name": "Northgate Roast Intelligence",
            "visual_theme": {"primary_color": "#7c3f21", "secondary_color": "#166534", "mood": "warm, crafted, confident"},
        },
    },
    # Added session 38 with the assistant-console archetype: a business
    # whose product IS the assistant. Every other fixture here has an AI
    # employee working somewhere inside a dashboard; this one has nothing
    # else, which is the case the catalogue could not previously express —
    # measured live, request 110, where a chatbot brief came back as an
    # operations dashboard with "Chatbot" as its fourth navigation item.
    "assistant": {
        "business_name": "Halden & Co",
        "business_description": (
            "Two-partner accountancy practice. Most of the day goes on the same questions from "
            "clients — deadlines, what to send us, where their return is up to — and booking the "
            "calls that follow. We want an assistant answering those and a record of every "
            "conversation it handled."
        ),
        "industry": "Accountancy Practice",
        "email": "test@example.com",
        "consult_result": {
            "consulting_summary": "An AI assistant that answers client questions around the clock, books the calls it cannot close, and hands you every conversation it had.",
        },
        "plan_result": {
            "concept_name": "Halden Desk",
            "visual_theme": {"primary_color": "#155e75", "secondary_color": "#b45309", "mood": "calm, precise, reassuring"},
        },
    },
}
