#!/bin/sh
# Preview QA harness — reports what the pipeline's own gates cannot see:
# shell identity, the route table, image references resolved by CONTENT-TYPE
# rather than status code, tsc error counts, leaked placeholder copy, shipped
# bundle weight, and a screenshot of every public route.
#
# Usage:  scripts/preview-qa.sh <request_id> [tag]
# Run from the repo root (it shells into the `api` compose service).
#
# Env overrides:
#   QA_OUT_DIR   where artifacts land       (default: .preview-qa/<tag>)
#   QA_BASE_URL  preview origin             (default: http://localhost:8001)
#   QA_CHROME    headless browser binary    (default: macOS Google Chrome)
#   QA_DETAIL_ID id substituted for :param routes            (default: 1)
#   QA_LEGACY_CHROME=1  viewport-only host Chrome capture, the old behaviour
set -u
ID="${1:?usage: preview-qa.sh <request_id> [tag]}"
TAG="${2:-qa}"
OUT="${QA_OUT_DIR:-.preview-qa/$TAG}"
CHROME="${QA_CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
BASE="${QA_BASE_URL:-http://localhost:8001}/api/preview-apps/$ID"
mkdir -p "$OUT"

echo "############ PREVIEW QA — request $ID ############"

echo
echo "===== 1. SHELL IDENTITY ====="
curl -sS "$BASE/" | grep -iE "<title>|<meta name=\"description\"" || echo "  (no title/description found)"
docker compose exec -T api sh -c "cd /app/data/preview-apps/$ID && grep -m1 '\"name\"' package.json" 2>/dev/null

echo
echo "===== 2. ROUTES DECLARED ====="
docker compose exec -T api sh -c "cd /app/data/preview-apps/$ID && grep -oE 'path=\"[^\"]+\"' src/App.tsx | sort -u" 2>/dev/null

echo
echo "===== 3. IMAGE REFERENCES + RESOLUTION ====="
docker compose exec -T api sh -c "cd /app/data/preview-apps/$ID && grep -rhoE '(https?://[^\"'\'' )]+\.(jpg|jpeg|png|webp|avif|svg))|(/[a-zA-Z0-9_/.-]+\.(jpg|jpeg|png|webp|avif|svg))' src 2>/dev/null | sort -u" 2>/dev/null > "$OUT/imgrefs.txt"
wc -l < "$OUT/imgrefs.txt" | tr -d ' ' | sed 's/^/  distinct refs: /'
while IFS= read -r ref; do
  case "$ref" in
    http*) printf "  REMOTE  %s\n" "$ref" ;;
    /*)
      ct=$(curl -sS -o /dev/null -w "%{http_code} %{content_type}" "$BASE$ref")
      case "$ct" in
        *image*) printf "  OK      %s  (%s)\n" "$ref" "$ct" ;;
        *)       printf "  BROKEN  %s  (%s)\n" "$ref" "$ct" ;;
      esac ;;
  esac
done < "$OUT/imgrefs.txt"

echo
echo "===== 4. UNDEFINED / MISSING SEED + IMAGE KEYS (tsc) ====="
docker compose exec -T api sh -c "cd /app/data/preview-apps/$ID && ./node_modules/.bin/tsc -b --pretty false 2>&1 | head -80" > "$OUT/tsc.txt" 2>&1
ERRS=$(grep -cE "error TS" "$OUT/tsc.txt" 2>/dev/null || echo 0)
echo "  typescript errors: $ERRS   (full output: $OUT/tsc.txt)"
grep -oE "error TS[0-9]+" "$OUT/tsc.txt" 2>/dev/null | sort | uniq -c | sort -rn | head -12

echo
echo "===== 5. LEAKED PLACEHOLDER / JARGON / ESCAPES IN COPY ====="
# Two trees, and which one a hit lands in is the whole point. A leak under
# src/pages or src/data belongs to this request. A leak under src/ui came from
# the UI kit, so it is on every request in the fleet and the fix is a template
# commit, not a re-run — the kit is scanned at source as well, because a kit
# string this request never renders is still shipping to the next twenty.
#
# `[Painter's Name]` rendered on request 68's /about-artist and this section
# reported clean, because no pattern described bracketed placeholders. They are
# their own class now, anchored on a capital and comma-free so that
# `const [name, setName] = useState()` is not a hit.
#
# The section also prints a verdict either way. It used to print nothing when it
# found nothing AND nothing when it could not run, and those must not look alike.
#
# CASING. Two pattern sets, because one flag cannot serve both.
#
# `LEAK_RE_I` is matched case-INSENSITIVELY. What a visitor reads is not what the
# source says: `CTABand.tsx:40` held the string `Next move` under a Tailwind
# `uppercase` class and rendered **NEXT MOVE** above the CTA of every generated
# site. A case-sensitive grep for `NEXT MOVE` returns nothing and certifies the
# page clean — and that is exactly what this check did, and what the engineer
# auditing this check did before writing this comment. Any pattern describing
# *rendered copy* must be case-insensitive, or a CSS text-transform defeats it.
# Case-insensitivity also caught "Overview of your business" on request 68's
# owner hub, which `Your Business` had missed.
#
# `LEAK_RE` stays case-SENSITIVE, and each member has a measured reason:
#   * `PLACEHOLDER` — `-i` matches the `placeholder=` attribute on every form
#     input; 11 hits across the kit's Input/Select/FilterBar/DataTable alone.
#   * the bracket classes — anchored on a capital so `[pathname]` and
#     `[location.pathname]` (React hook dep arrays) are not hits; `-i` turned
#     `[filename]`-shaped identifiers into leaks.
#   * `\u` escapes are a literal byte sequence, not copy.
LEAK_RE_I='lead drop|next move|guest path|lorem ipsum|your business|\btodo\b|\btbd\b'
LEAK_RE='PLACEHOLDER|\\u[0-9a-fA-F]{4}|\[[A-Z][^],]{0,40}(Name|NAME|Business|Company|City|Address|Email|Phone|Date|Title|Here)\]|\[(Your|Insert|Enter|Add|TBD)[^],]{0,40}\]'
docker compose exec -T api sh -c "cd /app/data/preview-apps/$ID && test -f src/data/mock.ts && echo READABLE" > "$OUT/leak-probe.txt" 2>/dev/null
if ! grep -q READABLE "$OUT/leak-probe.txt" 2>/dev/null; then
  echo "  NOT CHECKED — /app/data/preview-apps/$ID/src is not readable from the api service"
else
  docker compose exec -T api sh -c \
    "cd /app/data/preview-apps/$ID && { grep -rnoE '$LEAK_RE' src; grep -rnoiE '$LEAK_RE_I' src; } 2>/dev/null | sort -u" \
    > "$OUT/leaks.txt" 2>/dev/null
  docker compose exec -T api sh -c \
    "cd \"\${PREVIEW_TEMPLATE_DIR:-/app/backend/preview-template}\" && { grep -rnoE '$LEAK_RE' src; grep -rnoiE '$LEAK_RE_I' src; } 2>/dev/null | sort -u" \
    > "$OUT/leaks-kit.txt" 2>/dev/null
  # OWNERSHIP. Which bucket a hit lands in decides who fixes it, and the
  # boundary is not this script's opinion. `is_template_owned_path`
  # (backend/app/application/preview_app/protected_paths.py) is the rule the
  # pipeline itself applies — snapshot before the guards, restore after — so a
  # hit under it survives every re-run and only a template commit clears it.
  # This calls that function rather than restating it; `^src/ui/` was a hand
  # copy and it had already drifted.
  #
  # Three buckets, because the ownership rule and the set of files the template
  # ships do not agree. The template also puts `src/pages/HomePage.tsx` and
  # `src/pages/admin/**` in every workspace, and the ownership rule covers
  # neither — the pipeline may rewrite them and does not restore them. So a hit
  # there is the kit's when the line is verbatim from the template and this
  # request's when it is not, and the script decides that by reading the
  # template's own copy of the file rather than by guessing. Request 71 billed
  # two kit strings in `src/pages/admin/AdminDashboardPage.tsx` to the request.
  docker compose exec -T api python -c '
import os, sys
from pathlib import Path
from app.application.preview_app.protected_paths import is_template_owned_path

template = Path(os.environ.get("PREVIEW_TEMPLATE_DIR", "/app/backend/preview-template"))
architect = {"_catalogue_workspace": True}
for raw in sys.stdin.read().splitlines():
    if not raw.strip():
        continue
    fields = raw.split(":", 2)
    path, hit = fields[0], (fields[2] if len(fields) > 2 else "")
    if is_template_owned_path(path, architect):
        bucket = "KIT-OWNED"
    else:
        try:
            verbatim = bool(hit) and hit in (template / path).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            verbatim = False
        bucket = "KIT-COPY" if verbatim else "REQUEST"
    print(bucket + "\t" + raw)
' < "$OUT/leaks.txt" > "$OUT/leaks-bucketed.txt" 2>"$OUT/leaks-bucketed.log"

  TPL_N=$(wc -l < "$OUT/leaks-kit.txt" 2>/dev/null | tr -d ' ')
  if [ -s "$OUT/leaks.txt" ] && [ ! -s "$OUT/leaks-bucketed.txt" ]; then
    # A bucket that cannot run must not read like a bucket that found nothing.
    echo "  OWNERSHIP NOT RESOLVED — protected_paths.py was not reachable from the api"
    echo "  service, so no hit below is attributed. This is not a clean result."
    awk '{ print "  UNATTRIBUTED  " $0 }' "$OUT/leaks.txt" | head -20
    echo "  kit at source          : $TPL_N   (template — every future request)"
    awk '{ print "  KIT        " $0 }' "$OUT/leaks-kit.txt" 2>/dev/null | head -20
    echo "  (why: $OUT/leaks-bucketed.log)"
  else
    GEN_N=$(grep -c '^REQUEST' "$OUT/leaks-bucketed.txt" 2>/dev/null | tr -d ' ')
    OWN_N=$(grep -c '^KIT-OWNED' "$OUT/leaks-bucketed.txt" 2>/dev/null | tr -d ' ')
    CPY_N=$(grep -c '^KIT-COPY' "$OUT/leaks-bucketed.txt" 2>/dev/null | tr -d ' ')
    echo "  generated pages + data : ${GEN_N:-0}"
    echo "  kit, ownership-protected: ${OWN_N:-0}   (is_template_owned_path — restored every run)"
    echo "  kit, shipped unprotected: ${CPY_N:-0}   (template file, verbatim line, rewritable)"
    echo "  kit at source          : ${TPL_N:-0}   (template — every future request)"
    if [ "${GEN_N:-0}" = "0" ] && [ "${OWN_N:-0}" = "0" ] && [ "${CPY_N:-0}" = "0" ] \
       && [ "${TPL_N:-0}" = "0" ]; then
      echo "  CLEAN"
    else
      awk -F'\t' '{ printf "  %-10s %s\n", $1, $2 }' "$OUT/leaks-bucketed.txt" | head -20
      awk '{ print "  KIT        " $0 }' "$OUT/leaks-kit.txt" 2>/dev/null | head -20
      echo "  (full lists: $OUT/leaks-bucketed.txt, $OUT/leaks-kit.txt)"
    fi
  fi
fi

echo
echo "===== 6. SCAFFOLD BLOAT SHIPPED ====="
docker compose exec -T api sh -c "cd /app/data/preview-apps/$ID && echo -n '  workspace bytes (no node_modules/dist): '; du -sk --exclude=node_modules --exclude=dist . 2>/dev/null | cut -f1 || find . -type f -not -path './node_modules/*' -not -path './dist/*' -exec wc -c {} + 2>/dev/null | tail -1; echo -n '  dist bytes: '; du -sk dist 2>/dev/null | cut -f1; echo '  dist non-js assets:'; ls -la dist/*.jpg dist/*.svg dist/*.png 2>/dev/null | head -15 || echo '    (none)'" 2>/dev/null

echo
echo "===== 7. SCREENSHOTS (full page, reveals primed) ====="
# Host Chrome's --screenshot captures the VIEWPORT ONLY, and public heroes are
# viewport-height, so this section used to return the hero for every route no
# matter which one it asked for — it structurally could not see a broken
# catalogue grid. Worse, sections below the fold sit at opacity:0 until an
# IntersectionObserver fires, so even a full-page capture of an unscrolled page
# is a hero over blank space.
#
# Playwright in the api image gives both: full_page (CDP captureBeyondViewport)
# and reduced_motion, which makes the template's reveal paths no-op to visible.
# PNGs come back base64 on stdout so no shared volume is needed.
# Set QA_LEGACY_CHROME=1 to fall back to the old viewport-only host capture.
# Every declared route, with `:param` segments resolved to QA_DETAIL_ID so the
# detail page — the whole point of the journey contract — is actually captured.
ROUTES=$(docker compose exec -T api sh -c "cd /app/data/preview-apps/$ID && grep -oE 'path=\"[^\"]+\"' src/App.tsx | sed 's/path=//;s/\"//g'" 2>/dev/null \
  | grep -v '\*' \
  | sed "s#:[A-Za-z_][A-Za-z0-9_]*#${QA_DETAIL_ID:-1}#g" \
  | sort -u)
[ -z "$ROUTES" ] && ROUTES="/"

ROUTE_ARGS=""
for path in $ROUTES; do
  name=$(echo "$path" | sed 's#^/##; s#/#-#g')
  [ -z "$name" ] && name="home"
  ROUTE_ARGS="$ROUTE_ARGS --route $name:$path"
done
echo "  routes: $(echo "$ROUTES" | tr '\n' ' ')"

if [ "${QA_LEGACY_CHROME:-0}" = "1" ]; then
  for path in $ROUTES; do
    name=$(echo "$path" | sed 's#^/##; s#/#-#g'); [ -z "$name" ] && name="home"
    "$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
      --force-prefers-reduced-motion \
      --virtual-time-budget=9000 --window-size=1440,2000 \
      --screenshot="$OUT/$name.png" "$BASE$path" >/dev/null 2>&1
    if [ -f "$OUT/$name.png" ]; then
      echo "  $name -> $OUT/$name.png ($(stat -f%z "$OUT/$name.png") bytes, VIEWPORT ONLY)"
    else
      echo "  $name -> FAILED"
    fi
  done
else
  # shellcheck disable=SC2086
  docker compose exec -T api python -m scripts.cli.capture_full_page \
    --base-url "http://localhost:8000/api/preview-apps/$ID" \
    $ROUTE_ARGS --stdout > "$OUT/shots.b64" 2>"$OUT/shots.log"
  awk -v out="$OUT" '
    /^===PNG /   { name = $2; next }
    name != ""   { print > (out "/" name ".b64"); name = "" }
  ' "$OUT/shots.b64"
  for b64 in "$OUT"/*.b64; do
    case "$b64" in *shots.b64) continue ;; esac
    name=$(basename "$b64" .b64)
    base64 -D -i "$b64" -o "$OUT/$name.png" 2>/dev/null || base64 -d "$b64" > "$OUT/$name.png"
    rm -f "$b64"
  done
  rm -f "$OUT/shots.b64"
  # name <TAB> path <TAB> bytes <TAB> page-height, straight from the capturer.
  while IFS="$(printf '\t')" read -r name _target bytes height rest; do
    [ -z "$name" ] && continue
    if [ "$bytes" = "0" ] || [ -z "$bytes" ]; then
      echo "  $name -> FAILED ${rest:-}"
    else
      echo "  $name -> $OUT/$name.png ($bytes bytes, page ${height}px tall)"
    fi
  done < "$OUT/shots.log"
fi

echo
echo "############ END QA — artifacts in $OUT ############"
