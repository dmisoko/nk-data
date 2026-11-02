#!/bin/bash
# Wait for the three scrape workers, then extract, rebuild, validate and commit.
set -u
cd "$(dirname "$0")/.." || exit 1
for i in $(seq 1 240); do
  n=$(grep -l SCRAPE_DONE /tmp/scrape_0.log /tmp/scrape_1.log /tmp/scrape_2.log 2>/dev/null | wc -l | tr -d ' ')
  [ "$n" -ge 3 ] && break
  [ "$i" -ge 200 ] && break
  sleep 60
done
sleep 20
bash tools/retry_kla.sh > /tmp/finalize_retry.log 2>&1
python3 tools/extract_kla.py > /tmp/finalize_extract.log 2>&1
rm -rf db catalog
python3 tools/build_db.py > /tmp/finalize_build.log 2>&1
python3 tools/validate.py > /tmp/finalize_validate.log 2>&1
git add -A
git -c user.name="meiguanding" -c user.email="mgddev@163.com" commit -q -m "Import full KLA refractive index dataset" 2>/dev/null
echo FINALIZED >> /tmp/finalize.log
