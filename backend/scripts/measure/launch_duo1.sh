#!/bin/sh
# Duo 1 — the 1.13 proof run. TWO runs, not three, and that is deliberate.
#
# What three buys is the DoD row's own wording ("3 runs started 60 s apart",
# one reference_url, one reference_file) and nothing else: contention was
# recorded on only 4 of 16 runs, and trios 3, 4 and 7 collided on none. The
# questions this run has to answer are binary, not distributional — did the
# runway reservation fire, did appspec cap at 8 calls per request, did the
# duplicate authoring pass go away — so a third run adds a third sample to
# something that is not a rate. Keep a trio for closing the 600 s row.
#
# The two briefs are requests 92 and 94 VERBATIM. Those are the runs that
# stored no preview_app at all, with appspec at 353 s and 339 s, so reusing
# them makes this a controlled before/after with the bound as the only
# variable. Do not "improve" the wording — that is the control.
#
# Pre-flight, all five verified before this was run (2026-08-04):
#   1. docker compose restart api — 1.13 is bind-mounted; without the restart
#      the running interpreter keeps the old modules and the run measures the
#      OLD code while looking exactly like a fix that did nothing.
#   2. one real 28,000-max_tokens call per production model, both returned.
#   3. shared_npm_root() + _vite_ready(node_modules) both true, so no cold
#      npm ci inside the first run's clock.
#   4. nothing else on the host — no pytest container, no mutation sweep.
#   5. both briefs produce catalogue routes.
set -u
OUT=${OUT:-$(pwd)}   # where the launch log lands; override with OUT=...
API=http://localhost:8001/api/requests   # no trailing slash: 307 drops the body

post() {
  label=$1; shift
  echo "$label start_epoch=$(date +%s) start_iso=$(date -u +%H:%M:%S)" >> "$OUT/launch_duo1.log"
  curl -s -X POST "$API" "$@" >> "$OUT/launch_duo1.log"
  echo "" >> "$OUT/launch_duo1.log"
}

# Same brief as request 92 (appspec 353.2 s / 7 calls, stored nothing).
post run1 \
  -F 'business_name=Osteria Vinci' \
  -F 'business_description=A twelve-table Neapolitan trattoria in Boston serving wood-fired pizza, house-made pasta and a short Campanian wine list. We take reservations, run a weekly changing menu, and host private dinners in the back room.' \
  -F 'email=rr@phoeniciancapital.com' \
  -F 'industry=restaurant' \
  -F 'reference_url=https://www.pizzeriabianco.com/'

sleep 60

# Same brief as request 94 (appspec 338.8 s / 10 calls against a configured 6,
# stored nothing). The plain one, and the run most likely to sit behind a lock.
post run2 \
  -F 'business_name=Cedar Point Lodge' \
  -F 'business_description=An eighteen-room lakeside lodge in the Adirondacks with a restaurant, a sauna and guided canoe trips. Guests check availability by date, compare room types, and book direct rather than through an aggregator.' \
  -F 'email=rr@phoeniciancapital.com' \
  -F 'industry=hotel'

echo "ALL LAUNCHED $(date +%s)" >> "$OUT/launch_duo1.log"
