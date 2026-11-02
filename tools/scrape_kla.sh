#!/bin/bash
# Dump every KLA material page to sources/kla/raw/<slug>.html (resumable).
# The pages embed the full n/k series as inline `plotDataN` / `plotDataK` arrays.
set -u
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BASE="https://www.kla.com/products/instruments/refractive-index-database"
cd "$(dirname "$0")/.." || exit 1
WORKER="${WORKER:-0}"
WORKERS="${WORKERS:-1}"
mkdir -p sources/kla/raw
total=$(wc -l < sources/kla/slugs.txt | tr -d ' ')
i=0
while IFS= read -r slug; do
  [ -z "$slug" ] && continue
  i=$((i+1))
  [ $(( (i - 1) % WORKERS )) -ne "$WORKER" ] && continue
  f="sources/kla/raw/$(echo "$slug" | tr '/' '_').html"
  if [ -s "$f" ] && grep -q plotDataN "$f"; then continue; fi
  if [ -f sources/kla/skip.txt ] && grep -qxF "$slug" sources/kla/skip.txt; then continue; fi
  rm -rf "/tmp/chr-run-$WORKER"; mkdir -p "/tmp/chr-run-$WORKER"
  timeout -k 5 40 "$CHROME" --headless=new --disable-gpu --no-sandbox \
    --user-data-dir="/tmp/chr-run-$WORKER" --user-agent="$UA" \
    --disable-blink-features=AutomationControlled --lang=en-US \
    --virtual-time-budget=12000 --dump-dom "$BASE/$slug" > "$f.tmp" 2>/dev/null
  if grep -q plotDataN "$f.tmp" 2>/dev/null; then mv "$f.tmp" "$f"; else rm -f "$f.tmp"; echo "FAIL $slug" >> sources/kla/failed.txt; fi
  echo "[$i/$total] $slug"
  sleep 1
done < sources/kla/slugs.txt
echo "SCRAPE_DONE"
