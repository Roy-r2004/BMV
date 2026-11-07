"""Grounded facts for the public site chatbot — source of truth for answers.

Keep this in sync with frontend packages / solutions / FAQ.
Never put dollar amounts here.
"""

SITE_KNOWLEDGE = """
# Build My Version — grounded product facts

## Who we are
- Brand: Build My Version (BMV)
- We are an AI consultancy (not a generic agency)
- Core job: answer the question a business owner is stuck on, tested against their own figures, then design (and, if they want, build) the system that fixes it. If the fix is not software, we say so first.

## How it works (product flow)
1. Start at /demo with one sentence: what you are trying to work out (a problem, a decision, or something to start)
2. It asks one question at a time and builds up your figures as you answer; you can drop in a spreadsheet or an export, and "I don't know" is always an allowed answer
3. It writes out every explanation that fits, tests each against your own numbers, and two reviewers try to break the strongest
4. You get the answer on one page: the question, the answer in two lines, the numbers it rests on (each labelled: yours, worked out from yours, our estimate, or a cited reference), what to do Monday and what we would not do
5. Then the package: a recommendation register (who owns each step, when, and the range it is worth), the blueprint, the technical plan, the operations manual, a roadmap, the system screen by screen (only when the answer is to build) and a deck, plus a ZIP of all of them
6. If you want it built, our team quotes after scope; the plan is yours either way

## Free vs paid
- Starting is free: the consultation, the answer and the whole package cost nothing
- No credit card and no sales call to start
- Building the real product is a custom quote after package/scope selection
- ONE fixed-price service exists: the Deep-Dive working session — $200, 90 minutes with our consultant, the demo's plan corrected together from the client's real numbers, an exact build quote at the end. The $200 is credited in full against the build.
- There is NO online checkout; contact is by email: consulting@buildmyversion.com
- Build packages themselves have NO public dollar prices (the $200 deep-dive is the only published price)

## Build packages (NO public prices — quote only)
1) Launch MVP
   - Timeline: 4–8 weeks
   - Best for: getting live fast with core customer + owner flows
   - Includes: production build of the preview, owner/admin basics, AI from preview wired for production, payments on main path, customer confirmations (email + WhatsApp/SMS basics), brand + deploy, launch handoff

2) Growth MVP (most popular)
   - Timeline: 8–12 weeks
   - Best for: teams that need staff roles, fuller automations, and care
   - Includes: everything in Launch + staff/role dashboards, richer reminder/follow-up automations, domain extras, cinematic polish, 30-day care after launch

3) Custom / Scale
   - Timeline: scoped together
   - Best for: complex ops, integrations, multi-location, longer partnership
   - Includes: everything in Growth + third-party integrations, advanced roles, custom workflows/reporting, dedicated scope call before we quote

## Pricing rules (absolute)
- We never publish dollar/euro/pound prices for packages
- Correct answer to "how much?": Pricing is a custom quote after we understand scope — never checkout online. Suggest starting with a free consultation at /demo, then choosing Launch / Growth / Custom.
- Scope labels used in the form (not prices): Starter scope, Standard scope, Full build, Not sure yet
- Timeline options: ASAP (2–4 weeks), 1–2 months, 2–3 months, Flexible

## Solutions (concepts at /solutions)
/solutions shows concepts of large AI systems we can build, each shown screen by screen.
They are concepts, not delivered client projects and not ready-made products — never
say a client already runs one, and never quote results for them.
- Run the business — Business Digital Twin, Autonomous AI Workforce, Autonomous Finance Office,
  AI Procurement Negotiator, AI Compliance Officer, Sovereign Company AI
- Grow revenue — Synthetic Customer Lab, AI Sales Development Team, Voice AI Contact Center,
  Personal Video Studio, Dynamic Pricing Engine
- Create — Generative Product Studio, AI Ad Film Studio, 3D & AR Commerce,
  Global Localisation Studio, Brand & Legal Guardian
- See the physical world — Vision-Powered Store, Hospital Command Center, Construction Site Twin,
  Predictive Maintenance Radar, Energy Autopilot
Any of them is shaped around the visitor's business after a consultation; building is quoted.

## Key site pages (guide the user)
- / — Home: what the consultancy does, step by step, and where to start
- /demo — Start a consultation (free): one question, then the conversation, the answer and the package
- /solutions — AI solution concepts, grouped by area of the business
- /private-ai — Private AI deployments on infrastructure the client owns and controls
- /about — Who we are / method
- /login, /signup — Account

## What we build (use cases)
AI customer assistants, booking systems, dashboards, lead follow-up, quote generators, client portals, marketplaces, AI workflow tools, business automation

## Principles
- Diagnose before build
- Every figure traced: the client's, worked out from theirs, our estimate, or a cited reference
- If the fix is not software, say so first
- Ship production systems (not throwaway demos)
- Original by design — references inspire; we never clone proprietary code/brand/design

## What we do NOT do
- Do not invent prices, discounts, monthly SaaS fees, or Stripe checkout
- Do not claim we sell a self-serve subscription with listed pricing
- Do not claim we copy competitors' proprietary products
- Do not invent case-study dollar ROI numbers
""".strip()

PRICING_SAFE_REPLY = (
    "Honest answer: builds don’t have list prices — every build is quoted after we understand your scope. "
    "You can start free at /demo (a free consultation that starts with your own question, no card). "
    "If you want a human pass before committing, the Deep-Dive working session is $200 — 90 minutes with our "
    "consultant, your plan corrected together, an exact quote at the end, and the $200 is credited in full "
    "against your build (email consulting@buildmyversion.com). "
    "Build packages are Launch MVP (4–8 weeks), Growth MVP (8–12 weeks, most popular), or Custom / Scale."
)
