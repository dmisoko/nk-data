#!/bin/bash
# Publish the data layer: push master, enable GitHub Pages, tag, verify.
set -u
cd "$(dirname "$0")/.." || exit 1
if [ "${CONFIRM_PUBLISH:-0}" != "1" ]; then
  echo "Refusing to publish: this script pushes to GitHub and creates a tag."
  echo "Re-run as: CONFIRM_PUBLISH=1 bash tools/publish.sh"
  exit 1
fi
REPO="dmisoko/nk-data"
BASE="https://dmisoko.github.io/nk-data"

echo "== authenticated as =="
gh api user --jq .login || { echo "NOT AUTHENTICATED"; exit 1; }
echo "== permissions on $REPO =="
gh api "repos/$REPO" --jq .permissions

echo "== push =="
git push origin master || exit 1

echo "== enable pages =="
gh api --method POST "repos/$REPO/pages" -f "source[branch]=master" -f "source[path]=/" 2>&1 | head -3 \
  || gh api --method PUT "repos/$REPO/pages" -f "source[branch]=master" -f "source[path]=/" 2>&1 | head -3

echo "== wait for build =="
for i in $(seq 1 40); do
  status=$(gh api "repos/$REPO/pages" --jq .status 2>/dev/null)
  echo "  status: $status"
  [ "$status" = "built" ] && break
  sleep 15
done

echo "== verify =="
curl -sS -o /dev/null -w "pages catalog: %{http_code} %{size_download}B\n" "$BASE/catalog.json"
curl -sS -o /dev/null -w "pages material: %{http_code} %{size_download}B\n" "$BASE/db/au.kla.json"
curl -sS -o /dev/null -w "jsdelivr catalog: %{http_code} %{size_download}B\n" "https://cdn.jsdelivr.net/gh/$REPO@master/catalog.json"

echo "== tag =="
git tag -f v2026.11 >/dev/null 2>&1
git push -f origin v2026.11 2>&1 | tail -2
echo PUBLISHED
