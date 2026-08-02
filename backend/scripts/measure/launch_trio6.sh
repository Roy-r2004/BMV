#!/bin/sh
# Three generations, 60 s apart. Different industries on purpose: three of the
# same would only prove one path. Run 3 is the plain one — it is the run most
# likely to sit behind both locks, and a reference on it would confound the
# cause of any degradation.
set -u
OUT=${OUT:-$(pwd)}   # where the launch log lands; override with OUT=...
API=http://localhost:8001/api/requests
REF=/Users/maurice/Documents/Dev/BMV/docs/maverick-qa/contact-inquire-top.png

post() {
  label=$1; shift
  echo "$label start_epoch=$(date +%s) start_iso=$(date -u +%H:%M:%S)" >> "$OUT/launch6.log"
  curl -s -X POST "$API" "$@" >> "$OUT/launch6.log"
  echo "" >> "$OUT/launch6.log"
}

post run1 \
  -F 'business_name=Osteria Vinci' \
  -F 'business_description=A twelve-table Neapolitan trattoria in Boston serving wood-fired pizza, house-made pasta and a short Campanian wine list. We take reservations, run a weekly changing menu, and host private dinners in the back room.' \
  -F 'email=rr@phoeniciancapital.com' \
  -F 'industry=restaurant' \
  -F 'reference_url=https://www.pizzeriabianco.com/'

sleep 60

post run2 \
  -F 'business_name=Northgate Dental Studio' \
  -F 'business_description=A three-chair family dental practice in Leeds offering check-ups, hygienist visits, clear aligners and emergency appointments. Patients book online, see their treatment plan and costs up front, and are reminded before each visit.' \
  -F 'email=rr@phoeniciancapital.com' \
  -F 'industry=dental clinic' \
  -F "reference_file=@$REF"

sleep 60

post run3 \
  -F 'business_name=Cedar Point Lodge' \
  -F 'business_description=An eighteen-room lakeside lodge in the Adirondacks with a restaurant, a sauna and guided canoe trips. Guests check availability by date, compare room types, and book direct rather than through an aggregator.' \
  -F 'email=rr@phoeniciancapital.com' \
  -F 'industry=hotel'

echo "ALL LAUNCHED $(date +%s)" >> "$OUT/launch6.log"
