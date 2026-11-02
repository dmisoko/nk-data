#!/usr/bin/env python3
"""Scrape the KLA refractive-index database with a real (headless) browser.

Each material page embeds the full n(lambda) and k(lambda) series as
`let plotDataN = [[nm, n], ...]` inside an inline script, so one DOM dump
per page is enough. Results go to sources/kla/<slug>.json (resumable).

Usage:
  python3 tools/scrape_kla.py --limit 8
  python3 tools/scrape_kla.py            # all materials, resumes
"""
import argparse
import json
import os
import signal
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sources" / "kla"
BASE = "https://www.kla.com/products/instruments/refractive-index-database/"
INDEX_CACHE = Path("/tmp/kla_idx.html")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
PROFILE_ROOT = Path("/tmp/chr-scrape")


def dump_dom(url: str, budget: int = 25000) -> str:
    import shutil
    import tempfile
    import uuid
    prof = PROFILE_ROOT / uuid.uuid4().hex[:8]
    prof.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkstemp(suffix=".html")[1])
    cmd = [
        CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
        f"--user-data-dir={prof}", f"--user-agent={UA}",
        "--disable-blink-features=AutomationControlled", "--lang=en-US",
        "--no-first-run", "--no-default-browser-check", "--disable-extensions",
        "--disable-background-networking", f"--virtual-time-budget={budget}",
        "--dump-dom", url,
    ]
    try:
        with open(out, "w", encoding="utf-8") as fh:
            proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.DEVNULL,
                                    start_new_session=True)
            try:
                proc.wait(timeout=75)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:  # noqa: BLE001
                    proc.kill()
        return out.read_text(encoding="utf-8", errors="replace")
    finally:
        shutil.rmtree(prof, ignore_errors=True)
        out.unlink(missing_ok=True)


def index_links() -> list:
    html = INDEX_CACHE.read_text(encoding="utf-8", errors="replace") if INDEX_CACHE.exists() else dump_dom(BASE)
    if not INDEX_CACHE.exists():
        INDEX_CACHE.write_text(html, encoding="utf-8")
    seen, out = set(), []
    for m in re.finditer(r'href="(/products/instruments/refractive-index-database/([^"#?]+))"', html):
        slug = m.group(2).strip("/")
        if slug and slug not in seen:
            seen.add(slug)
            out.append(slug)
    return out


def series(html: str, name: str):
    m = re.search(rf"let\s+{name}\s*=\s*(\[\[.*?\]\]);", html, re.S)
    return json.loads(m.group(1)) if m else None


def title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).replace("| KLA", "").strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="")
    ap.add_argument("--sleep", type=float, default=1.0)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    slugs = index_links()
    if args.only:
        wanted = [s.strip() for s in args.only.split(",")]
        slugs = [s for s in wanted]
    if args.limit:
        slugs = slugs[: args.limit]
    print(f"targets: {len(slugs)}", flush=True)

    ok = fail = skip = 0
    for i, slug in enumerate(slugs, 1):
        dest = OUT / f"{slug.replace('/', '_')}.json"
        if dest.exists():
            skip += 1
            continue
        try:
            html = dump_dom(BASE + slug)
        except subprocess.TimeoutExpired:
            fail += 1
            print(f"[{i}/{len(slugs)}] {slug} TIMEOUT", flush=True)
            continue
        n, k = series(html, "plotDataN"), series(html, "plotDataK")
        if not n:
            fail += 1
            print(f"[{i}/{len(slugs)}] {slug} NO-DATA ({len(html)} bytes)", flush=True)
            continue
        rec = {
            "slug": slug,
            "name": title(html),
            "url": BASE + slug,
            "retrieved": "2026-11-02",
            "unit": "nm",
            "reference": "KLA (formerly Filmetrics) refractive index database",
            "n": n,
            "k": k or [],
        }
        dest.write_text(json.dumps(rec, separators=(",", ":")), encoding="utf-8")
        ok += 1
        print(f"[{i}/{len(slugs)}] {slug} {len(n)} pts", flush=True)
        time.sleep(args.sleep)

    print(f"done: ok={ok} fail={fail} skip={skip}", flush=True)


if __name__ == "__main__":
    main()
