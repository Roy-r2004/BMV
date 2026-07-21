"""Grounded facts for the public site chatbot — source of truth for answers.

Keep this in sync with frontend packages / solutions / FAQ.
Never put dollar amounts here.
"""

SITE_KNOWLEDGE = """
# Build My Version — grounded product facts

## Who we are
- Brand: Build My Version (BMV)
- We are an AI consultancy (not a generic agency)
- Core job: find the AI & automation a business actually needs, prove it with a free clickable product preview, then our engineering team builds the real system

## How it works (product flow)
1. Tell us how your business works (free submit flow at /submit)
2. Optionally share inspiration / references
3. We diagnose AI fit and generate a custom clickable product preview
4. When ready, our team builds the production software (quoted after scope)

## Free vs paid
- Starting is free: free AI fit + custom MVP concept + visual/clickable preview
- No credit card required to start the preview
- Building the real product is a custom quote after package/scope selection
- There is NO online checkout and NO public dollar prices

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
- Correct answer to "how much?": Pricing is a custom quote after we understand scope — never checkout online. Suggest starting with the free preview at /submit, then choosing Launch / Growth / Custom.
- Scope labels used in the form (not prices): Starter scope, Standard scope, Full build, Not sure yet
- Timeline options: ASAP (2–4 weeks), 1–2 months, 2–3 months, Flexible

## Industry solutions (ready-made platforms at /solutions)
Each can be customized and launched for a business:
- Healthcare & Clinics — intake AI + patient portal
- Barbershops & Salons — booking + style memory
- Restaurants & Cafes — menu AI + kitchen board
- Real Estate — listing AI + agent CRM
- Gyms & Fitness Coaching — member portal + churn alerts
- Legal & Consulting — counsel AI + vault
- Retail & E-commerce — NL search + seller hub
- Home Services — quote AI + dispatch
- Education & Tutoring — tutor match + auto-billing
- Automotive Services — bay scheduler + status bot
- Hospitality & Hotels — direct booking + concierge
- Nonprofits — donate AI + campaigns

Solution setup phases: ready-made platform → customer tools → team ops → customize & launch

## Key site pages (guide the user)
- / — Home: consultancy story, how it works, examples, packages, FAQ
- /submit — Start free: find AI fit + get preview
- /demo — Live product builds gallery
- /examples — Example output concepts
- /solutions — Industry ready-made solutions
- /solutions/:id — Solution detail
- /about — Who we are / method
- /login, /signup — Account

## What we build (use cases)
AI customer assistants, booking systems, dashboards, lead follow-up, quote generators, client portals, marketplaces, AI workflow tools, business automation

## Principles
- Diagnose before build
- Prove with a live preview
- Ship production systems (not throwaway demos)
- Original by design — references inspire; we never clone proprietary code/brand/design

## What we do NOT do
- Do not invent prices, discounts, monthly SaaS fees, or Stripe checkout
- Do not claim we sell a self-serve subscription with listed pricing
- Do not claim we copy competitors' proprietary products
- Do not invent case-study dollar ROI numbers
""".strip()

PRICING_SAFE_REPLY = (
    "Honest answer: we don’t list dollar prices — every build is quoted after we understand your scope. "
    "Good news: you can start free at /submit (AI fit + clickable preview, no card). "
    "When you’re ready to build, packages are Launch MVP (4–8 weeks), Growth MVP (8–12 weeks, most popular), "
    "or Custom / Scale. What’s your industry, and are you exploring or ready to see a preview?"
)
