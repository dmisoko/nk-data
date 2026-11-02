#!/usr/bin/env python3
"""Validate the generated data layer: schema shape, monotonicity, catalog links."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLS = {"n", "o", "e"}
errors = []


def check_series(path: Path):
    d = json.loads(path.read_text(encoding="utf-8"))
    keys = ("id", "source", "pol", "unit", "kind", "range_nm")
    if d.get("kind") != "sellmeier":
        keys = keys + ("data",)
    for key in keys:
        if key not in d:
            errors.append(f"{path.name}: missing {key}")
            return
    if d["pol"] not in POLS:
        errors.append(f"{path.name}: bad pol {d['pol']}")
    if d["unit"] != "nm":
        errors.append(f"{path.name}: unit {d['unit']}")
    if d["kind"] == "sellmeier":
        if not d.get("model", {}).get("terms"):
            errors.append(f"{path.name}: empty model")
        return
    wl, n, k = d["data"]["wl"], d["data"]["n"], d["data"]["k"]
    if not (len(wl) == len(n) == len(k)):
        errors.append(f"{path.name}: length mismatch")
        return
    if any(b <= a for a, b in zip(wl, wl[1:])):
        errors.append(f"{path.name}: wl not strictly increasing")
    if [round(wl[0], 5), round(wl[-1], 5)] != [round(v, 5) for v in d["range_nm"]]:
        errors.append(f"{path.name}: range_nm mismatch")
    if any(v < 0 for v in k):
        errors.append(f"{path.name}: negative k")


def main():
    cat = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    mats = cat["materials"]
    seen = set()
    for slug, entry in mats.items():
        if not entry["v"]:
            errors.append(f"catalog {slug}: no variants")
        for src, rel in entry["v"]:
            p = ROOT / rel
            if not p.exists():
                errors.append(f"catalog {slug}: missing file {rel}")
                continue
            d = json.loads(p.read_text(encoding="utf-8"))
            key = (d["id"].lower(), d["source"], d["pol"])
            if key in seen:
                errors.append(f"duplicate series {key}")
            seen.add(key)
    for p in sorted((ROOT / "db").glob("*.json")):
        if p.name != "_schema.json":
            check_series(p)
    print(f"catalog materials: {len(mats)}")
    print(f"db files: {len(list((ROOT / 'db').glob('*.json'))) - 1}")
    print(f"errors: {len(errors)}")
    for e in errors[:25]:
        print("  ", e)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
