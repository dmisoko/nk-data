#!/usr/bin/env python3
"""Classify and audit every refractive-index file in this repository.

Outputs a JSON report plus a human summary. Read-only: it never modifies source files.
"""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIRS = ["analytic", "coatings", "freesnell", "litho", "palik", "rii", "sopra", "various", "windt"]


def strip_comment(line: str) -> str:
    for sep in (";", "//", "#"):
        i = line.find(sep)
        if i >= 0:
            line = line[:i]
    return line


def is_num(t: str) -> bool:
    try:
        float(t)
        return True
    except ValueError:
        return False


def parse_file(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    header, rows = [], []
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        toks = strip_comment(s).split()
        if toks and all(is_num(t) for t in toks):
            rows.append([float(t) for t in toks])
        else:
            header.append(s)

    # Drop a leading "point count" line (Unight style: 95 on its own line).
    if len(rows) >= 2 and len(rows[0]) == 1 and abs(rows[0][0] - (len(rows) - 1)) < 1e-6:
        rows = rows[1:]

    ncols = statistics.mode([len(r) for r in rows]) if rows else 0
    rows = [r for r in rows if len(r) == ncols]

    htxt = " ".join(header)
    adapter = "unknown"
    unit = None
    if ncols == 5 and ("cm-1" in htxt or "cm^-1" in htxt or "eV" in htxt):
        adapter, unit = "palik5", "um"
    elif ncols == 5:
        adapter, unit = "anisotropic5", "nm"
    elif ncols == 3:
        adapter = "table3"
    elif ncols == 4:
        adapter = "table4"

    if ncols >= 3:
        wl = [r[1] if adapter == "palik5" else r[0] for r in rows]
        nn = [r[3] if adapter == "palik5" else r[1] for r in rows]
        kk = [r[4] if adapter == "palik5" else r[2] for r in rows]
    else:
        wl = nn = kk = []

    flags = []
    if adapter == "table3" and wl:
        med = statistics.median(wl)
        if med < 0.5:
            unit = "um"
        elif med > 5000:
            unit = "angstrom"
        elif med > 50:
            unit = "nm"
        else:
            # Ambiguous band: decide by span, then flag for review.
            unit = "um" if max(wl) <= 2000 else "nm"
            flags.append("unit_ambiguous")
    if wl and any(b <= a for a, b in zip(wl, wl[1:])):
        flags.append("wl_not_increasing")
    if nn and (min(nn) < 0 or max(nn) > 12):
        flags.append("n_out_of_range")
    if kk and (min(kk) < -1e-9 or max(kk) > 12):
        flags.append("k_out_of_range")
    if not rows:
        flags.append("no_numeric_rows")

    return {
        "path": str(path.relative_to(ROOT)),
        "adapter": adapter,
        "unit": unit,
        "cols": ncols,
        "points": len(rows),
        "wl_min": round(min(wl), 6) if wl else None,
        "wl_max": round(max(wl), 6) if wl else None,
        "flags": flags,
    }


def main() -> None:
    out = []
    for d in SRC_DIRS:
        for p in sorted((ROOT / d).rglob("*")):
            if p.is_file() and p.suffix.lower() in (".nk", ".nkk"):
                out.append(parse_file(p))

    report = {"files": len(out), "records": out}
    (ROOT / "tools" / "audit_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")

    print(f"files scanned: {len(out)}")
    print("\n-- adapter counts --")
    for k in sorted({r["adapter"] for r in out}):
        print(f"{k:14s} {sum(1 for r in out if r['adapter'] == k)}")
    print("\n-- unit counts --")
    for k in sorted({str(r["unit"]) for r in out}):
        print(f"{k:10s} {sum(1 for r in out if str(r['unit']) == k)}")
    print("\n-- flagged --")
    for r in out:
        if r["flags"]:
            print(f"{r['path']:40s} {r['adapter']:13s} {r['unit']} {r['points']:5d} "
                  f"[{r['wl_min']}, {r['wl_max']}] {','.join(r['flags'])}")
    print("\n-- wavelength span by adapter (min,max) --")
    for k in sorted({r["adapter"] for r in out}):
        vals = [(r["wl_min"], r["wl_max"]) for r in out if r["adapter"] == k and r["wl_min"] is not None]
        if vals:
            print(f"{k:14s} {min(v[0] for v in vals)} .. {max(v[1] for v in vals)}")


if __name__ == "__main__":
    main()
