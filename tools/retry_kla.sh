#!/bin/bash
# Second pass over pages that failed the first time (mostly slow SCHOTT pages).
set -u
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BASE="https://www.kla.com/products/instruments/refractive-index-database"
cd "$(dirname "$0")/.." || exit 1
[ -f sources/kla/failed.txt ] || exit 0
WORKER="${WORKER:-0}"
WORKERS="${WORKERS:-1}"
sort -u sources/kla/failed.txt | sed 's/^FAIL //' > "/tmp/retry_slugs_$WORKER.txt"
: > "/tmp/retry_failed_$WORKER.txt"
n=0
i=0
while IFS= read -r slug; do
  [ -z "$slug" ] && continue
  i=$((i+1))
  [ $(( (i - 1) % WORKERS )) -ne "$WORKER" ] && continue
  f="sources/kla/raw/$(echo "$slug" | tr '/' '_').html"
  if [ -s "$f" ] && grep -q plotDataN "$f"; then continue; fi
  n=$((n+1))
  rm -rf "/tmp/chr-retry-$WORKER"; mkdir -p "/tmp/chr-retry-$WORKER"
  timeout -k 5 60 "$CHROME" --headless=new --disable-gpu --no-sandbox \
    --user-data-dir="/tmp/chr-retry-$WORKER" --user-agent="$UA" \
    --disable-blink-features=AutomationControlled --lang=en-US \
    --virtual-time-budget=25000 --dump-dom "$BASE/$slug" > "$f.tmp" 2>/dev/null
  if grep -q plotDataN "$f.tmp" 2>/dev/null; then mv "$f.tmp" "$f"; else rm -f "$f.tmp"; echo "$slug" >> "/tmp/retry_failed_$WORKER.txt"; fi
  echo "[retry $n] $slug"
  sleep 2
done < "/tmp/retry_slugs_$WORKER.txt"
echo RETRY_DONE
