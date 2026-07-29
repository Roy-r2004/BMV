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
#   QA_OUT_DIR  where artifacts land        (default: .preview-qa/<tag>)
#   QA_BASE_URL preview origin             (default: http://localhost:8001)
#   QA_CHROME   headless browser binary    (default: macOS Google Chrome)
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
docker compose exec -T api sh -c "cd /app/data/preview-apps/$ID && grep -rnoE 'LEAD DROP|NEXT MOVE|GUEST PATH|Lorem ipsum|\\\\\\\\u[0-9a-fA-F]{4}|TODO|PLACEHOLDER|Your Business' src 2>/dev/null | head -20" 2>/dev/null || echo "  none"

echo
echo "===== 6. SCAFFOLD BLOAT SHIPPED ====="
docker compose exec -T api sh -c "cd /app/data/preview-apps/$ID && echo -n '  workspace bytes (no node_modules/dist): '; du -sk --exclude=node_modules --exclude=dist . 2>/dev/null | cut -f1 || find . -type f -not -path './node_modules/*' -not -path './dist/*' -exec wc -c {} + 2>/dev/null | tail -1; echo -n '  dist bytes: '; du -sk dist 2>/dev/null | cut -f1; echo '  dist non-js assets:'; ls -la dist/*.jpg dist/*.svg dist/*.png 2>/dev/null | head -15 || echo '    (none)'" 2>/dev/null

echo
echo "===== 7. SCREENSHOTS ====="
for r in "home:" "works:works" "gallery:gallery" "about:about" "contact:contact"; do
  name="${r%%:*}"; path="${r#*:}"
  "$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
    --virtual-time-budget=9000 --window-size=1440,2000 \
    --screenshot="$OUT/$name.png" "$BASE/$path" >/dev/null 2>&1
  if [ -f "$OUT/$name.png" ]; then
    echo "  $name -> $OUT/$name.png ($(stat -f%z "$OUT/$name.png") bytes)"
  else
    echo "  $name -> FAILED"
  fi
done

echo
echo "############ END QA — artifacts in $OUT ############"
