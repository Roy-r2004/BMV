#!/bin/sh
# Duo 3 — the run session 12 could not make. The account was exhausted
# (total_usage 330.229 of total_credits 330), so nothing session 12 landed has
# been through a generation.
#
# TWO runs, the briefs of 95/97 (restaurant) and 96/98 (hotel) VERBATIM, which
# makes this a controlled before/after against duo 2 with session 12's two fixes
# as the only variable. Do not "improve" the wording.
#
# The pair is chosen, not arbitrary. `gallery_gapfill_census.py` says the hotel
# brief loses `/gallery` on all 8 of its stored runs and the restaurant on 4 of
# 6 — so a hotel that still ships a gallery means the fix did not land, and a
# restaurant that still ships one means `/menu` did not resolve to a catalogue
# and the measured boundary is wider than the corpus showed.
#
# What to read afterwards:
#   1. no route at `/gallery`, and no `src/pages/ArtworkDetailPage.tsx`   (bbe6359)
#   2. `navigation.public` carries BOTH /reservations and /my-reservations,
#      with DIFFERENT labels, when the architect declares both             (8fe8955)
#   3. no mock.ts contains "warm, specific, and ready when you are"        (8fe8955)
#      — fires in ~11 % of runs, so one run probably will not exercise it
#   4. design_system.font_family is not a squashed slug ("sourcesans3")    (8fe8955)
#   5. DUMP THE LOG THE MOMENT EACH RUN FINISHES and grep `slot_fill rejected`.
#      If AboutPage.tsx or ContactPage.tsx still appear, the remaining cause of
#      the public-detail assignment is the PLAN page and 0e678fa is half a fix.
#
# Pre-flight, in this order — item 1 is new and is why session 12 wasted nothing:
#   1. CREDITS. The probe is in HANDOFF.md, "The next step" item 0. If the
#      account is empty every later step is wasted and the failure looks
#      exactly like defect 1.12.
#   2. docker compose restart api   (the fixes are bind-mounted)
#   3. 28,000-max_tokens probe on google/gemini-2.5-flash, deepseek/deepseek-v4-pro
#      and z-ai/glm-5.2
#   4. shared_npm_root() + node_modules present
#   5. nothing else on the host — no pytest container, no mutation sweep
#   6. APPSPEC_MODE resolved from the RUNNING PROCESS, not from .env: shadow
set -u
OUT=${OUT:-$(pwd)}   # where the launch log lands; override with OUT=...
LOG=${LOG:-$OUT/launch_duo3.log}
API=http://localhost:8001/api/requests   # no trailing slash: 307 drops the body

post() {
  label=$1; shift
  echo "$label start_epoch=$(date +%s) start_iso=$(date -u +%H:%M:%S)" >> "$LOG"
  curl -s -X POST "$API" "$@" >> "$LOG"
  echo "" >> "$LOG"
}

# Same brief as requests 92, 95, 97 and 101.
post run1 \
  -F 'business_name=Osteria Vinci' \
  -F 'business_description=A twelve-table Neapolitan trattoria in Boston serving wood-fired pizza, house-made pasta and a short Campanian wine list. We take reservations, run a weekly changing menu, and host private dinners in the back room.' \
  -F 'email=rr@phoeniciancapital.com' \
  -F 'industry=restaurant' \
  -F 'reference_url=https://www.pizzeriabianco.com/'

sleep 60

# Same brief as requests 94, 96 and 98.
post run2 \
  -F 'business_name=Cedar Point Lodge' \
  -F 'business_description=An eighteen-room lakeside lodge in the Adirondacks with a restaurant, a sauna and guided canoe trips. Guests check availability by date, compare room types, and book direct rather than through an aggregator.' \
  -F 'email=rr@phoeniciancapital.com' \
  -F 'industry=hotel'

echo "ALL LAUNCHED $(date +%s)" >> "$LOG"
