#!/usr/bin/env python3
"""Post-run readout for the session-29 validation trio.

Run AFTER the trio finishes, with the three request ids:

    python3 readout_validation_trio.py 167 168 169

Prints, per request, everything the HANDOFF says to read, in reading order:
1. Outcome + wall clock (ready / withheld+codes / upstream death) — feeds
   Phase 2 DoD 10's streak (upstream deaths vs withholds, kept separate).
2. AppSpec: revisions, final terminal_reason, repair attempts, and every
   session-29 mechanism marker found in heal_actions / lineage
   (terminal_salvage, restore_dropped_trace_link, drop_unprovable_visible,
   drop_unbindable_state, drop_exact_duplicate, pre_trace_evidence_repair).
3. Ask health by writer/finish_reason (read by finish_reason, never outcome).
4. Catalogue survival pointer (run session28/check_catalogue_survival.py for
   titles — this script does not re-implement it).

Balance bracketing: run scratch balance probe before AND after the trio and
attribute only the delta (shared key).
"""
from __future__ import annotations

import json
import subprocess
import sys

MARKERS = (
    "terminal_salvage",
    "restore_dropped_trace_link",
    "drop_unprovable_visible_assertion",
    "drop_unbindable_state_assertion",
    "drop_exact_duplicate",
    "pre_trace_evidence_repair",
    "deterministic_trace_repair",
)


def _psql(query: str) -> list[list[str]]:
    out = subprocess.run(
        ["docker", "exec", "bmv-db", "psql", "-U", "bmv", "-d", "buildmyversion",
         "-Atc", query],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return [line.split("|") for line in out.splitlines() if line]


def main(request_ids: list[int]) -> None:
    ids = ",".join(str(i) for i in request_ids)

    print("=== 1. Outcomes (verdict is the generation_log tail; 'Quality lock"
          " failed: <codes>' = withheld, its codes are the gate speaking) ===")
    for row in _psql(
        f"""SELECT id, business_name,
        (SELECT round((max((e->>'t')::bigint) - min((e->>'t')::bigint))::numeric, 0)
           FROM jsonb_array_elements(generation_log::jsonb->'log') e) AS wall_s,
        COALESCE((SELECT e->>'msg' FROM jsonb_array_elements(generation_log::jsonb->'log')
           WITH ORDINALITY AS x(e, n)
           WHERE e->>'msg' LIKE 'Quality lock failed%' ORDER BY n DESC LIMIT 1),
          'ready (no quality-lock failure logged)'),
        (SELECT (e->>'stage') || ': ' || (e->>'msg')
           FROM jsonb_array_elements(generation_log::jsonb->'log')
           WITH ORDINALITY AS y(e, n) ORDER BY n DESC LIMIT 1) AS last_entry
        FROM requests WHERE id IN ({ids}) ORDER BY id;"""
    ):
        req, name, wall = row[0], row[1], row[2]
        verdict, last = row[3], row[4] if len(row) > 4 else ""
        print(f"  {req} | {name} | {wall}s | {verdict[:120]}")
        if "done" not in (last or ""):
            print(f"       LAST LOG ENTRY (run did not reach done): {last[:160]}")

    print("\n=== 2. AppSpec revisions ===")
    for row in _psql(
        f"SELECT request_id, revision, status, "
        f"generation_metadata_json::jsonb->>'terminal_reason', "
        f"generation_metadata_json::jsonb->>'repair_attempts', "
        f"generation_metadata_json::jsonb->>'calls_used' "
        f"FROM app_spec_revisions WHERE request_id IN ({ids}) ORDER BY request_id, revision;"
    ):
        print("  " + " | ".join(row))

    print("\n=== 2b. Session-29 mechanism markers in heal_actions ===")
    rows = _psql(
        f"SELECT request_id, generation_metadata_json::jsonb->'heal_actions' "
        f"FROM app_spec_revisions WHERE request_id IN ({ids}) "
        f"AND status='accepted' ORDER BY request_id;"
    )
    fired_any = False
    for req, actions_json in rows:
        try:
            actions = json.loads(actions_json) or []
        except (ValueError, TypeError):
            actions = []
        hits = [a for a in actions if any(m in a for m in MARKERS)]
        if hits:
            fired_any = True
            print(f"  {req}: " + "; ".join(hits[:10]))
    if not fired_any:
        print("  none fired — every run validated clean on the first shapes "
              "(fix B and the salvage rungs remain live-unproven; say so, do "
              "not claim them proven)")

    print("\n=== 3. Ask health by writer/finish_reason ===")
    for row in _psql(
        f"SELECT purpose, writer, finish_reason, usable, count(*), "
        f"round(avg(completion_tokens)) FROM ai_usage_events "
        f"WHERE request_id IN ({ids}) GROUP BY 1,2,3,4 ORDER BY 1,2,3;"
    ):
        print("  " + " | ".join(row))

    print("\n=== 4. Next ===")
    print("  catalogue survival: python3 docs/evidence/session28/check_catalogue_survival.py " )
    print("  per-item photo queries: docker logs bmv-api | grep -E 'photo|Pexels'")
    print("  Phase 2 DoD 10 streak: upstream deaths above; withholds are the gate codes in 1.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: readout_validation_trio.py <request_id> [...]")
    main([int(a) for a in sys.argv[1:]])
