#!/usr/bin/env python3
"""Extract n/k series from saved KLA DOM dumps (sources/kla/raw/*.html).

The material pages embed the full series as `let plotDataN = [[nm, n], ...]`
and `let plotDataK = [...]` inside an inline script.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "sources" / "kla" / "raw"
OUT = ROOT / "sources" / "kla"
BASE = "https://www.kla.com/products/instruments/refractive-index-database/"


def series(html, name):
    m = re.search(rf"let\s+{name}\s*=\s*(\[\[.*?\]\]);", html, re.S)
    return json.loads(m.group(1)) if m else None


def title(html):
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return re.sub(r"\s+", " ", m.group(1)).replace("| KLA", "").strip() if m else ""


def main():
    ok = bad = 0
    for path in sorted(RAW.glob("*.html")):
        if path.stem.endswith(".fail"):
            continue
        html = path.read_text(encoding="utf-8", errors="replace")
        n, k = series(html, "plotDataN"), series(html, "plotDataK")
        if not n:
            bad += 1
            print(f"  {path.stem:34s} NO-DATA")
            continue
        slug = path.stem.replace("_", "/", 1) if "_" in path.stem else path.stem
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
        (OUT / f"{path.stem}.json").write_text(json.dumps(rec, separators=(",", ":")), encoding="utf-8")
        ok += 1
        print(f"  {path.stem:34s} n_pts={len(n):4d} k_pts={len(k or []):4d} {n[0][0]}-{n[-1][0]} nm")
    print(f"extracted={ok} nodata={bad}")


if __name__ == "__main__":
    main()
