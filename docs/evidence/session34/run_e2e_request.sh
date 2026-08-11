#!/bin/sh
# One real request through the public intake — the DoD line-4 measurement
# (≤ $0.60, ≤ 3 minutes) on the full session-34 stack: 2K follow-ups,
# backdrop crop, defect check, parallel screens, ui-spec-v3.
#
# The service runs in a named container; cost is read through the /admin
# endpoint while it runs (SQLite WAL over a bind mount is not readable by
# a second process — the ledger bracket trap), and the container is
# stopped cleanly afterwards so the WAL checkpoints.
#
# Run from the repo root:  sh docs/evidence/session34/run_e2e_request.sh
set -e

docker rm -f bmv-consultant-e2e 2>/dev/null || true
docker run -d --name bmv-consultant-e2e \
  -v "$PWD:/repo" -w /repo/consultant-service \
  -e DATABASE_URL=sqlite:////repo/consultant-service/consultant.db \
  -p 8002:8002 \
  --entrypoint sh bmv-consultant-py -c \
  'python -m uvicorn main:app --host 0.0.0.0 --port 8002' >/dev/null

printf 'waiting for service'
i=0
until curl -sf http://localhost:8002/docs >/dev/null 2>&1; do
  i=$((i+1)); [ $i -gt 60 ] && echo ' TIMEOUT' && docker logs bmv-consultant-e2e | tail -20 && exit 1
  printf '.'; sleep 1
done
echo ' up'

START=$(date +%s)
RESP=$(curl -sf -X POST http://localhost:8002/api/requests \
  -F "business_name=Beacon Physiotherapy" \
  -F "business_description=Physiotherapy and sports rehabilitation clinic with four treatment rooms and six therapists. Patients book assessments and follow-up sessions; we juggle therapist availability, insurance pre-approvals and no-shows. We lose evenings to manual scheduling and chasing claim paperwork." \
  -F "email=owner@beaconphysio.example" \
  -F "industry=Physiotherapy clinic" \
  -F "main_problem=Manual scheduling and insurance claim chasing eat our admin hours" \
  -F "desired_outcome=A workable demo of software that runs the clinic day-to-day" \
  -F "needs_ai=yes")
echo "created: $RESP"
ID=$(echo "$RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

while :; do
  P=$(curl -sf "http://localhost:8002/api/requests/$ID/progress" || echo '{}')
  STAGE=$(echo "$P" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("stage",""), d.get("progress_pct",""))' 2>/dev/null || echo '?')
  NOW=$(date +%s); ELAPSED=$((NOW-START))
  echo "  t=${ELAPSED}s  $STAGE"
  case "$STAGE" in done*|failed*) break;; esac
  [ $ELAPSED -gt 900 ] && echo "TIMEOUT at 15 min" && break
  sleep 5
done
END=$(date +%s)
echo "WALL CLOCK: $((END-START))s"

curl -sf "http://localhost:8002/api/requests/$ID/admin" > "docs/evidence/session34/e2e-admin-payload.json"
python3 - <<EOF
import json
d = json.load(open("docs/evidence/session34/e2e-admin-payload.json"))
print("cost:", json.dumps(d.get("cost"), indent=2)[:600])
print("screens:", [(s.get("role_id"), s.get("qa_score")) for s in d.get("screens", [])])
EOF

docker stop bmv-consultant-e2e >/dev/null
docker rm bmv-consultant-e2e >/dev/null
echo "service stopped cleanly (WAL checkpointed)"
