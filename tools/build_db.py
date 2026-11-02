#!/usr/bin/env python3
"""Build the AI-readable layer: db/*.json + catalog.json + catalog/ranges.json.

Read-only with respect to the source data. Wavelengths are normalised to
nanometres; every db file holds exactly one series (one material, one source,
one polarisation).
"""
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_SOURCES = ["palik", "sopra", "windt", "rii", "freesnell", "litho", "coatings", "various"]
EXTRA_SOURCES = [
    ("setfos", ROOT / "sources" / "setfos"),
    ("unight", ROOT / "sources" / "unight"),
    ("kla", ROOT / "sources" / "kla"),
]
OUT_DB = ROOT / "db"
OUT_CAT = ROOT / "catalog"
EV_TO_UM = 1.239841984
UNIT_HINT = {"windt": "angstrom", "unight": "nm", "kla": "nm"}
SENTINEL = -0.0001
SOURCE_RANK = {"kla": 0, "palik": 1, "sopra": 2, "windt": 3, "rii": 4,
               "setfos": 5, "unight": 6, "coatings": 7, "litho": 8, "various": 9, "freesnell": 10}
SANITY = {"SiO2": (550.0, 1.46), "Si": (632.8, 3.88), "Ag": (632.8, 0.135),
          "TiO2": (550.0, 2.90), "MgF2": (550.0, 1.38), "Au": (632.8, 0.183)}
stats = {"files": 0, "records": 0, "skipped": [], "sanity": []}


def num(t):
    try:
        float(t)
        return True
    except ValueError:
        return False


def is_sentinel(v):
    return abs(v - SENTINEL) < 1e-9


def read_rows(path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    rows, header = [], []
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        body = s
        for sep in (";", "//"):
            i = body.find(sep)
            if i >= 0:
                body = body[:i]
        if body.startswith("#"):
            header.append(s)
            continue
        toks = body.split()
        if toks and all(num(t) for t in toks):
            rows.append([float(t) for t in toks])
        else:
            header.append(s)
    return lines, rows, header


def resolve_unit(wl, hint=None):
    if hint in ("nm", "um", "angstrom"):
        return hint
    mn, mx = min(wl), max(wl)
    if mn >= 100 or mx > 2000:
        return "nm"
    return "um"


def scale_unit(wl, unit):
    return [w * {"um": 1000.0, "nm": 1.0, "angstrom": 0.1}[unit] for w in wl]


def parse_palik(path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    rows, labels = [], []
    for raw in lines:
        if raw.startswith(";L"):
            labels = re.split(r"\s+", raw[2:].strip())
            continue
        if raw.startswith(";"):
            continue
        t = raw.split()
        if t and all(num(x) for x in t):
            rows.append([float(x) for x in t])
    if not rows or not labels:
        return None
    width = statistics.mode([len(r) for r in rows])
    rows = [r for r in rows if len(r) == width]
    um_idx = next((i for i, l in enumerate(labels) if "um" in l.lower()), 2)
    groups, order = {}, []
    for i, lab in enumerate(labels):
        low = lab.lower()
        if not (low.startswith("n") or low.startswith("k")):
            continue
        m = re.search(r"\((\w+)\)", lab)
        pol = m.group(1).lower() if m else "n"
        groups.setdefault(pol, {"n": [], "k": []})
        if pol not in order:
            order.append(pol)
        groups[pol]["n" if low.startswith("n") else "k"].append(i)
    out = {}
    for pol in order:
        g = groups[pol]
        pairs = list(zip(g["n"], g["k"] if g["k"] else [None] * len(g["n"])))
        if not pairs:
            continue
        wl, ns, ks = [], [], []
        for r in rows:
            pick = next(((ni, ki) for ni, ki in pairs if not is_sentinel(r[ni])), pairs[0])
            ni, ki = pick
            kv = r[ki] if ki is not None else SENTINEL
            wl.append(r[um_idx] * 1000.0)
            ns.append(r[ni])
            ks.append(kv)
        keep = [i for i, v in enumerate(ns) if not is_sentinel(v)]
        if not keep:
            continue
        wl = [wl[i] for i in keep]
        ns = [ns[i] for i in keep]
        ks = [ks[i] for i in keep]
        out[pol] = (wl, ns, fill_missing_k(ks))
    return out or None


def fill_missing_k(ks):
    """-0.0001 marks "no k value" in Palik tables.

    Between two absorbing neighbours (k > 0.05) the gap is interpolated; next to
    transparent regions it is treated as k = 0, which is what the sentinel means
    for dielectrics.
    """
    out = list(ks)
    n = len(out)
    for i, v in enumerate(ks):
        if not is_sentinel(v):
            continue
        prev = next((ks[j] for j in range(i - 1, -1, -1) if not is_sentinel(ks[j])), None)
        nxt = next((ks[j] for j in range(i + 1, n) if not is_sentinel(ks[j])), None)
        if prev is not None and nxt is not None and prev > 0.05 and nxt > 0.05:
            pi = next(j for j in range(i - 1, -1, -1) if not is_sentinel(ks[j]))
            ni = next(j for j in range(i + 1, n) if not is_sentinel(ks[j]))
            t = (i - pi) / (ni - pi)
            out[i] = prev + t * (nxt - prev)
        else:
            out[i] = 0.0
    return out


def parse_table(rows, ncols, hint):
    if ncols < 3:
        return None
    unit = resolve_unit([r[0] for r in rows], hint)
    wl = scale_unit([r[0] for r in rows], unit)
    if ncols == 5:
        return {"o": (wl, [r[1] for r in rows], [r[2] for r in rows]),
                "e": (wl, [r[3] for r in rows], [r[4] for r in rows])}
    return {"n": (wl, [r[1] for r in rows], [r[2] for r in rows])}


def kla_identity(rec):
    """KLA titles look like 'Refractive Index of Ag, Silver for Thin Film ...'."""
    name = re.sub(r"^Refractive Index of ", "", rec.get("name", ""))
    name = re.sub(r"\s+for Thin Film.*$", "", name).strip()
    parts = [p.strip() for p in name.split(",") if p.strip()]
    primary = parts[0] if parts else rec.get("slug", "")
    aliases = parts[1:]
    base = re.sub(r"\s*\([^)]*\)\s*", " ", primary).strip()
    if base and base.lower() != primary.lower():
        aliases.append(base)
    return primary, aliases


def series_from_file(path, source):
    """Return {polarisation: (wl_nm, n, k)} or None."""
    if source == "kla":
        rec = json.loads(path.read_text(encoding="utf-8"))
        nx, kx = rec["n"], rec["k"]
        wl = [p[0] for p in nx]
        nv = [p[1] for p in nx]
        kv = [p[1] for p in kx] if kx else [0.0] * len(nv)
        return {"n": (wl, nv, kv)}
    try:
        _, rows, header = read_rows(path)
    except Exception:  # noqa: BLE001
        return None
    if not rows:
        return None
    if source == "palik":
        return parse_palik(path)
    if source == "freesnell":
        if len(rows[0]) != 4:
            return None
        wl = [EV_TO_UM * 1000.0 / r[0] for r in rows]
        return {"n": (wl, [r[1] for r in rows], [r[2] for r in rows])}
    ncols = statistics.mode([len(r) for r in rows])
    rows = [r for r in rows if len(r) == ncols]
    hint = None
    if source == "setfos":
        for h in header:
            tag = h.lstrip("#").strip().lower()
            if tag in ("nm", "um", "µm"):
                hint = "um" if tag in ("um", "µm") else "nm"
                break
    if hint is None:
        hint = UNIT_HINT.get(source)
    return parse_table(rows, ncols, hint)


def parse_analytic(path):
    """Sellmeier-style MATLAB models: A1..An / B1..Bn plus the dispersion formula."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if "sellmeir" not in text.lower() and "sellmeier" not in text.lower():
        return None
    a = {int(m.group(1)): float(m.group(2)) for m in re.finditer(r"^\s*A(\d+)\s*=\s*([-+0-9.eE]+)\s*;", text, re.M)}
    b = {int(m.group(1)): float(m.group(2)) for m in re.finditer(r"^\s*B(\d+)\s*=\s*([-+0-9.eE]+)\s*;", text, re.M)}
    terms = [[a[k], b[k]] for k in sorted(a) if k in b]
    if not terms:
        nums = {m.group(1): float(m.group(2))
                for m in re.finditer(r"^\s*([A-Z])N\s*=\s*([-+0-9.eE]+)\s*;", text, re.M)}
        dens = {m.group(1): float(m.group(2))
                for m in re.finditer(r"^\s*([A-Z])D\s*=\s*([-+0-9.eE]+)\s*;", text, re.M)}
        terms = [[nums[k], dens[k]] for k in sorted(nums) if k in dens]
    return terms or None


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "material"


_used_names = set()


def unique_name(name):
    candidate, i = name, 2
    while candidate in _used_names:
        candidate = f"{name}-{i}"
        i += 1
    _used_names.add(candidate)
    return candidate


def emit_model(material_id, source, terms, source_file):
    rec = {
        "id": material_id,
        "source": source,
        "pol": "n",
        "source_file": source_file,
        "unit": "nm",
        "kind": "sellmeier",
        "range_nm": None,
        "points": None,
        "model": {"formula": "n^2 = 1 + sum(A_i * l^2 / (l^2 - B_i)), l in um",
                  "terms": terms},
    }
    fname = unique_name(f"{slugify(material_id)}.{source}.json")
    (OUT_DB / fname).write_text(json.dumps(rec, separators=(",", ":")), encoding="utf-8")
    stats["records"] += 1
    return fname


def emit(material_id, source, pol, wl, nv, kv, source_file):
    order = sorted(range(len(wl)), key=lambda i: wl[i])
    dedup, last = [], None
    for i in order:
        w = round(wl[i], 5)
        if w != last:
            dedup.append(i)
            last = w
    order = dedup
    wl_s = [round(wl[i], 5) for i in order]
    # k must be non-negative. Some KLA charts plot -k, so flip sign when the
    # whole series is negative; residual small negatives are measurement noise.
    if kv and sum(1 for v in kv if v < 0) > 0.9 * len(kv):
        kv = [-v for v in kv]
    kv = [max(v, 0.0) for v in kv]
    rec = {
        "id": material_id,
        "source": source,
        "pol": pol,
        "source_file": source_file,
        "unit": "nm",
        "kind": "table",
        "range_nm": [wl_s[0], wl_s[-1]],
        "points": len(wl_s),
        "data": {"wl": wl_s,
                 "n": [round(nv[i], 6) for i in order],
                 "k": [round(kv[i], 6) for i in order]},
    }
    suffix = "" if pol == "n" else f".{pol}"
    fname = unique_name(f"{slugify(material_id)}.{source}{suffix}.json")
    (OUT_DB / fname).write_text(json.dumps(rec, separators=(",", ":")), encoding="utf-8")
    stats["records"] += 1
    return fname, rec


SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "nk-db series",
    "type": "object",
    "required": ["id", "source", "pol", "unit", "kind", "range_nm", "points", "data"],
    "properties": {
        "id": {"type": "string"},
        "source": {"type": "string"},
        "pol": {"type": "string"},
        "source_file": {"type": "string"},
        "unit": {"const": "nm"},
        "kind": {"enum": ["table", "sellmeier"]},
        "range_nm": {"type": ["array", "null"], "items": {"type": "number"}},
        "points": {"type": ["integer", "null"]},
        "model": {"type": "object"},
        "data": {
            "type": "object",
            "required": ["wl", "n", "k"],
            "properties": {
                "wl": {"type": "array", "items": {"type": "number"}},
                "n": {"type": "array", "items": {"type": "number"}},
                "k": {"type": "array", "items": {"type": "number"}},
            },
        },
    },
}


def main():
    OUT_DB.mkdir(exist_ok=True)
    OUT_CAT.mkdir(exist_ok=True)
    catalog = {}
    sanity_seen = {}
    seen_kla = set()

    def handle(path, source, rel):
        stats["files"] += 1
        series = series_from_file(path, source)
        if not series:
            stats["skipped"].append([rel, "no_series"])
            return
        mid = path.stem.strip()
        alias = []
        if source == "kla":
            rec_kla = json.loads(path.read_text(encoding="utf-8"))
            mid, alias = kla_identity(rec_kla)
            pol0 = series["n"]
            key = (mid.lower(), len(pol0[0]), round(pol0[0][0], 3), round(pol0[0][-1], 3))
            if key in seen_kla:
                return
            seen_kla.add(key)
        for pol, (wl, nv, kv) in series.items():
            if not wl:
                continue
            fname, rec = emit(mid, source, pol, wl, nv, kv, rel)
            entry = catalog.setdefault(mid.lower(), {"id": mid, "v": []})
            if alias:
                merged = {a for a in alias if a and a.lower() != mid.lower()}
                merged |= set(entry.get("a", []))
                entry["a"] = sorted(merged)
            entry["v"].append([source if pol == "n" else f"{source}:{pol}", f"db/{fname}"])
            if mid in SANITY and pol == "n":
                x, ref = SANITY[mid]
                got = interp(rec["data"]["wl"], rec["data"]["n"], x)
                if got is not None:
                    sanity_seen.setdefault(mid, []).append((source, got, ref))

    for src in REPO_SOURCES:
        for p in sorted((ROOT / src).rglob("*.nk")):
            handle(p, src, str(p.relative_to(ROOT)))
    for p in sorted((ROOT / "analytic").glob("n_*.m")):
        stats["files"] += 1
        terms = parse_analytic(p)
        if not terms:
            stats["skipped"].append([str(p.relative_to(ROOT)), "no_sellmeier"])
            continue
        mid = p.stem[2:]
        fname = emit_model(mid, "analytic", terms, str(p.relative_to(ROOT)))
        entry = catalog.setdefault(mid.lower(), {"id": mid, "v": [], "a": []})
        entry["v"].append(["analytic", f"db/{fname}"])

    for src, base in EXTRA_SOURCES:
        if not base.exists():
            continue
        pattern = "*.json" if src == "kla" else "*.nk"
        for p in sorted(base.rglob(pattern)):
            handle(p, src, f"{src}/{p.stem}")

    for slug, entry in catalog.items():
        stem = entry["id"]
        entry["f"] = stem if re.match(r"^[A-Z][a-z]?(?:\d+)?(?:[A-Z][a-z]?\d*)+$", stem) else None
        entry["v"].sort(key=lambda x: (SOURCE_RANK.get(x[0].split(":")[0], 99), x[0], x[1]))

    for mid, rows in sanity_seen.items():
        best = max(rows, key=lambda r: 1 if abs(r[1] - r[2]) < 0.1 * r[2] else 0)
        if abs(best[1] - best[2]) > 0.1 * best[2]:
            stats["sanity"].append([mid, best[0], round(best[1], 5), best[2]])

    (OUT_DB / "_schema.json").write_text(json.dumps(SCHEMA, indent=1), encoding="utf-8")

    (ROOT / "catalog.json").write_text(
        json.dumps({"schema": "nk-catalog/1", "generated": "2026-11-02", "materials": catalog},
                   separators=(",", ":")), encoding="utf-8")

    ranges = {}
    for slug, entry in catalog.items():
        vals = [json.loads((ROOT / rel).read_text(encoding="utf-8"))["range_nm"] for _, rel in entry["v"]]
        vals = [v for v in vals if v]
        if vals:
            ranges[slug] = [min(v[0] for v in vals), max(v[1] for v in vals)]
    (OUT_CAT / "ranges.json").write_text(
        json.dumps({"unit": "nm", "materials": ranges}, separators=(",", ":")), encoding="utf-8")

    report = {"files_scanned": stats["files"], "records_written": stats["records"],
              "materials": len(catalog), "skipped": stats["skipped"],
              "sanity_failures": stats["sanity"],
              "db_bytes": sum(p.stat().st_size for p in OUT_DB.glob("*.json")),
              "catalog_bytes": (ROOT / "catalog.json").stat().st_size}
    (ROOT / "tools" / "build_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("files_scanned", "records_written", "materials",
                                             "db_bytes", "catalog_bytes")}, indent=1))
    print(f"skipped={len(report['skipped'])} sanity_failures={len(report['sanity_failures'])}")


def interp(wl, vals, x):
    for i in range(len(wl) - 1):
        if wl[i] <= x <= wl[i + 1]:
            t = (x - wl[i]) / (wl[i + 1] - wl[i])
            return vals[i] + t * (vals[i + 1] - vals[i])
    return None


if __name__ == "__main__":
    main()
