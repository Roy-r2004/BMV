#!/bin/sh
# Duo 2 — session 11's control, and the first generation to see session 10's
# four fixes. TWO runs, the briefs of 95 and 96 VERBATIM (which are the briefs
# of 92 and 94 verbatim), so this is a controlled before/after against duo 1
# with only the four landed fixes as the variable.
#
# It is a control in a second sense: run C of the appspec spike re-uses run 1's
# brief with APPSPEC_MODE=on, so this run's route table is what C is diffed
# against. Do not "improve" the wording.
#
# What to read afterwards, all four of which are unproven claims from session 10:
#   - codegen_cost.py shows a `planning` stage and NO `(unattributed)` bucket
#   - withheld_reason present on both runs (None when served)
#   - the fix agent's route block carries a `detail_level`
#   - no mock.ts contains "Explore the collection"
#
# Pre-flight verified 2026-08-05 before this was run:
#   1. docker compose restart api (the four fixes are bind-mounted)
#   2. 28,000-max_tokens probe returned on google/gemini-2.5-flash AND
#      z-ai/glm-5.2 (the fix agent's model, which the older probe skipped)
#   3. shared_npm_root() + _vite_ready(node_modules) both true
#   4. nothing else on the host — no pytest container, no mutation sweep
#   5. APPSPEC_MODE resolved from the running process, not from .env: shadow
set -u
OUT=${OUT:-$(pwd)}   # where the launch log lands; override with OUT=...
LOG=${LOG:-$OUT/launch_duo2.log}
API=http://localhost:8001/api/requests   # no trailing slash: 307 drops the body

post() {
  label=$1; shift
  echo "$label start_epoch=$(date +%s) start_iso=$(date -u +%H:%M:%S)" >> "$LOG"
  curl -s -X POST "$API" "$@" >> "$LOG"
  echo "" >> "$LOG"
}

# Same brief as requests 92 and 95.
post run1 \
  -F 'business_name=Osteria Vinci' \
  -F 'business_description=A twelve-table Neapolitan trattoria in Boston serving wood-fired pizza, house-made pasta and a short Campanian wine list. We take reservations, run a weekly changing menu, and host private dinners in the back room.' \
  -F 'email=rr@phoeniciancapital.com' \
  -F 'industry=restaurant' \
  -F 'reference_url=https://www.pizzeriabianco.com/'

sleep 60

# Same brief as requests 94 and 96.
post run2 \
  -F 'business_name=Cedar Point Lodge' \
  -F 'business_description=An eighteen-room lakeside lodge in the Adirondacks with a restaurant, a sauna and guided canoe trips. Guests check availability by date, compare room types, and book direct rather than through an aggregator.' \
  -F 'email=rr@phoeniciancapital.com' \
  -F 'industry=hotel'

echo "ALL LAUNCHED $(date +%s)" >> "$LOG"
