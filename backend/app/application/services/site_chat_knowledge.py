"""Grounded facts for the public site chatbot — source of truth for answers.

Keep this in sync with frontend packages / solutions / FAQ.
Never put dollar amounts here.
"""

SITE_KNOWLEDGE = """
# Build My Version — grounded product facts

## Who we are
- Brand: Build My Version (BMV), registered in Dubai, United Arab Emirates. The method was written by
  consultants and built by engineers; never name individuals, give a headcount or name past employers
- We are an AI consultancy (not a generic agency)
- Core job: most visitors bring an idea and want it done for them. We test whether the idea's numbers work
  (against their figures and published ones), write the full plan, then build what it needs to run: website,
  app, bookings and payments, AI. Owners of running businesses get the same for the decision they face.
  If the answer is not software, we say so first. Building is quoted after the scope is agreed.

## How it works (product flow)
1. Start at /demo with one sentence: what you are trying to work out (a problem, a decision, or something to start)
2. It asks one question at a time and builds up your figures as you answer; you can drop in a spreadsheet or an export, and "I don't know" is always an allowed answer
3. It writes out every explanation that fits, tests each against your own numbers, and two reviewers try to break the strongest
4. You get the answer on one page: the question, the answer in two lines, the numbers it rests on (each labelled: yours, worked out from yours, our estimate, or a cited reference), what to do Monday and what we would not do
5. Then the package: a recommendation register (who owns each step, when, and the range it is worth), the blueprint, the technical plan, the operations manual, a roadmap, the system screen by screen (only when the answer is to build) and a deck, plus a ZIP of all of them
6. If you want it built, our team quotes after scope; the plan is yours either way

## Price
- A consultation costs $200. It includes the answer and the whole package of files
- No sales call is needed to start
- Building the real product is a custom quote after package/scope selection
- There is NO online checkout; contact is by email: consulting@buildmyversion.com
- Build packages themselves have NO public dollar prices (the $200 consultation is the only published price)

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
- Correct answer to "how much?": Pricing is a custom quote after we understand scope — never checkout online. Suggest starting with a consultation at /demo ($200), then choosing Launch / Growth / Custom.
- Scope labels used in the form (not prices): Starter scope, Standard scope, Full build, Not sure yet
- Timeline options: ASAP (2–4 weeks), 1–2 months, 2–3 months, Flexible

## Examples (at /solutions)
/solutions shows eight examples. Starting something new: a booking app, an online store, an AI
service, a café. Already running: a clinic, a restaurant, a shop, a professional firm. For each it shows
the question its owner brings, what a consultation would test and against which figures, what we would
build, and what would show it worked. They illustrate the method; they are not clients — never say a client
runs one, and never quote results. A visitor can start a consultation with an example's question
already written. Not every answer is software: the answer says so when it is not.

## Key site pages (guide the user)
- / — Home: what the consultancy does, step by step, and where to start
- /demo — Start a consultation ($200): one question, then the conversation, the answer and the package
- /solutions — examples: four ideas and four running businesses, what we test and what we build
- /services — The three services: the consultation ($200), system builds and private AI (both quoted after scoping)
- /approach — How a consultation is run, and the labels every figure carries
- /contact — Write to consulting@buildmyversion.com
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

## Questions clients ask before starting
- If the figures cannot support an answer: the answer page says so and names the figure that would settle it
- Nothing needs preparing: the consultation asks for what it needs, one question at a time; a spreadsheet or an export helps
- If the answer is not software, it says so before anything is built (some questions are settled by a change in pricing, staffing or schedule)
- The client can disagree: an objection is tested against their figures the same way the answer was
- The client keeps the files; the plan is theirs whether they build with us, with their own team or with another firm

## Private AI (/private-ai)
- Open-weight models on dedicated infrastructure the client owns and controls, connected to their own systems
- Why companies choose it: data stays private, control of the model, predictable costs for sustained workloads, no platform lock-in
- Steps: understand the workload, design the stack, deploy into their environment, integrate with the business
- It is right for some workloads, not all: it makes sense when data sensitivity, compliance, high sustained usage, latency or infrastructure control justify it; otherwise cloud models may be faster and cheaper

## How an engagement runs
- Diagnose (the consultation), Prove (a working version measured in the real business), Build (the full system), Hand over (their team runs it, with the operations manual)
- Four disciplines in one engagement: business, product, AI and infrastructure
- Deployment is chosen per workload: cloud, private or hybrid

## What we do NOT do
- Do not invent prices, discounts, monthly SaaS fees, or Stripe checkout
- Do not claim we sell a self-serve subscription with listed pricing
- Do not claim we copy competitors' proprietary products
- Do not invent case-study dollar ROI numbers
""".strip()

PRICING_SAFE_REPLY = (
    "Honest answer: builds don’t have list prices — every build is quoted after we understand your scope. "
    "A consultation is $200: it starts at /demo with your own question and ends with the answer and the full "
    "package of files. Questions: consulting@buildmyversion.com. "
    "Build packages are Launch MVP (4–8 weeks), Growth MVP (8–12 weeks, most popular), or Custom / Scale."
)
