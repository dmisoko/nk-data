#!/usr/bin/env python3
"""Build the AI-readable layer: db/*.json + catalog.json + catalog/ranges.json.

Read-only with respect to the source data. Wavelengths are normalised to
nanometres; every db file holds exactly one series (one material, one source,
one polarisation).
"""
import json
import re
import statistics
from datetime import datetime, timezone
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
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
UNIT_HINT = {"windt": "angstrom", "unight": "nm", "kla": "nm"}
SENTINEL = -0.0001
SOURCE_RANK = {"kla": 0, "palik": 1, "sopra": 2, "windt": 3, "rii": 4,
               "setfos": 5, "unight": 6, "coatings": 7, "litho": 8, "various": 9, "freesnell": 10}
SOURCE_META = {
    "palik": {"license": "Academic Press, Palik (ed.), Handbook of Optical Constants in Solids",
              "citation": "E. D. Palik (ed.), Handbook of Optical Constants in Solids I/II, Academic Press, 1985/1991.",
              "url": "https://www.sciencedirect.com/bookseries/handbook-of-optical-constants-in-solids"},
    "sopra": {"license": "SOPRA S.A. refractive index database (redistributed for research use)",
              "citation": "SOPRA S.A., refractive index database, https://www.sopra-sa.com/indices.htm",
              "url": "https://www.sopra-sa.com/indices.htm"},
    "windt": {"license": "IMD / D. L. Windt (free for research use)",
              "citation": "D. L. Windt, IMD - software for modeling soft X-ray multilayers, 1998.",
              "url": "http://www.rxollc.com/idl/"},
    "rii": {"license": "refractiveindex.info entries, individual literature sources",
            "citation": "M. N. Polyanskiy, refractiveindex.info, https://refractiveindex.info",
            "url": "https://refractiveindex.info"},
    "freesnell": {"license": "FreeSnell material library (S. G. Johnson)",
                  "citation": "S. G. Johnson, FreeSnell, https://github.com/stevengj/freesnell",
                  "url": "https://github.com/stevengj/freesnell"},
    "kla": {"license": "KLA refractive index database; values attributed to cited literature",
            "citation": "KLA (formerly Filmetrics) refractive index database, https://www.kla.com/products/instruments/refractive-index-database",
            "url": "https://www.kla.com/products/instruments/refractive-index-database"},
    "setfos": {"license": "Fluxim AG Setfos material library (supplied by the repository owner)",
               "citation": "Fluxim AG, Setfos material library", "url": "https://www.fluxim.com"},
    "unight": {"license": "Supplier material files (supplied by the repository owner)",
               "citation": "Supplier nk files", "url": None},
    "analytic": {"license": "Original repository contributors",
                 "citation": "Analytical dispersion models distributed with this repository",
                 "url": None},
}
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
    ev_idx = next((i for i, l in enumerate(labels) if l.lower().startswith("energy")), None)
    cm_idx = next((i for i, l in enumerate(labels) if "cm" in l.lower()), None)

    def wavelength_um(row):
        """Palik leaves the micrometre column as -0.0001 when only eV/cm-1 are known."""
        um = row[um_idx]
        if um > 0:
            return um, "um"
        if ev_idx is not None and row[ev_idx] > 0:
            return EV_TO_UM / row[ev_idx], "eV"
        if cm_idx is not None and row[cm_idx] > 0:
            return 1e4 / row[cm_idx], "cm-1"
        return None, None
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
        recovered = dropped = 0
        for r in rows:
            pick = next(((ni, ki) for ni, ki in pairs if not is_sentinel(r[ni])), pairs[0])
            ni, ki = pick
            kv = r[ki] if ki is not None else SENTINEL
            um, how = wavelength_um(r)
            if um is None:
                dropped += 1
                continue
            if how != "um":
                recovered += 1
            wl.append(um * 1000.0)
            ns.append(r[ni])
            ks.append(kv)
        keep = [i for i, v in enumerate(ns) if not is_sentinel(v)]
        if not keep:
            continue
        wl = [wl[i] for i in keep]
        ns = [ns[i] for i in keep]
        ks = [ks[i] for i in keep]
        filled, n_zero, n_interp = fill_missing_k(ks, wl)
        proc = {"unit_from": "um", "k_zero_filled": n_zero,
                "k_interpolated": n_interp,
                "wl_from_energy_column": recovered,
                "rows_dropped_no_wavelength": dropped,
                "rows_dropped": len(rows) - len(keep)}
        out[pol] = (wl, ns, filled, proc)
    return out or None


def fill_missing_k(ks, wl=None):
    """-0.0001 marks "no k value" in Palik tables.

    Between two absorbing neighbours (k > 0.05) the gap is interpolated; next to
    transparent regions it is treated as k = 0, which is what the sentinel means
    for dielectrics.
    """
    out = list(ks)
    n = len(out)
    n_zero = n_interp = 0
    for i, v in enumerate(ks):
        if not is_sentinel(v):
            continue
        prev = next((ks[j] for j in range(i - 1, -1, -1) if not is_sentinel(ks[j])), None)
        nxt = next((ks[j] for j in range(i + 1, n) if not is_sentinel(ks[j])), None)
        if prev is not None and nxt is not None and prev > 0.05 and nxt > 0.05:
            pi = next(j for j in range(i - 1, -1, -1) if not is_sentinel(ks[j]))
            ni = next(j for j in range(i + 1, n) if not is_sentinel(ks[j]))
            if wl is not None and wl[ni] != wl[pi]:
                t = (wl[i] - wl[pi]) / (wl[ni] - wl[pi])
            else:
                t = (i - pi) / (ni - pi)
            out[i] = prev + t * (nxt - prev)
            n_interp += 1
        else:
            out[i] = 0.0
            n_zero += 1
    return out, n_zero, n_interp


def parse_table(rows, ncols, hint):
    if ncols == 2:
        # index-only tables: wavelength plus refractive index, no absorption
        unit = resolve_unit([r[0] for r in rows], hint)
        wl = scale_unit([r[0] for r in rows], unit)
        return {"n": (wl, [r[1] for r in rows], [0.0] * len(rows),
                      {"unit_from": unit, "k_zero_filled": len(rows)})}
    if ncols < 2:
        return None
    unit = resolve_unit([r[0] for r in rows], hint)
    wl = scale_unit([r[0] for r in rows], unit)
    proc = {"unit_from": unit, "k_zero_filled": 0}
    if ncols == 5:
        return {"o": (wl, [r[1] for r in rows], [r[2] for r in rows], proc),
                "e": (wl, [r[3] for r in rows], [r[4] for r in rows], proc)}
    return {"n": (wl, [r[1] for r in rows], [r[2] for r in rows], proc)}


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
        proc = {"unit_from": "nm", "k_zero_filled": 0 if kx else len(nv),
                "source": "kla-inline-array"}
        return {"n": (wl, nv, kv, proc)}
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
        proc = {"unit_from": "eV", "k_zero_filled": 0}
        return {"n": (wl, [r[1] for r in rows], [r[2] for r in rows], proc)}
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


def sig(value, digits):
    """Round to significant digits so that tiny wavelengths (X-ray range) survive."""
    return float(f"{value:.{digits}g}")


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
        "sha1": None,
        "processing": {"unit_from": "um", "model": "sellmeier"},
        "model": {"formula": "n^2 = 1 + sum(A_i * l^2 / (l^2 - B_i)), l in um",
                  "terms": terms},
    }
    fname = unique_name(f"{slugify(material_id)}.{source}.json")
    (OUT_DB / fname).write_text(json.dumps(rec, separators=(",", ":")), encoding="utf-8")
    stats["records"] += 1
    return fname


def emit(material_id, source, pol, wl, nv, kv, source_file, proc=None, sha1=None):
    proc = dict(proc or {})
    order = sorted(range(len(wl)), key=lambda i: wl[i])
    dedup, last = [], None
    for i in order:
        w = sig(wl[i], 9)
        if w != last:
            dedup.append(i)
            last = w
    proc["wl_duplicates_removed"] = len(wl) - len(dedup)
    order = dedup
    wl_s = [sig(wl[i], 9) for i in order]
    # k must be non-negative. Some KLA charts plot -k, so flip sign when the
    # whole series is negative; residual small negatives are measurement noise.
    if kv and sum(1 for v in kv if v < 0) > 0.9 * len(kv):
        kv = [-v for v in kv]
        proc["k_sign_flipped"] = True
    clamped = sum(1 for v in kv if v < 0)
    if clamped:
        proc["k_negative_clamped"] = clamped
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
        "sha1": sha1,
        "processing": proc,
        "data": {"wl": wl_s,
                 "n": [sig(nv[i], 7) for i in order],
                 "k": [sig(kv[i], 7) for i in order]},
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
    "oneOf": [
        {"$ref": "#/$defs/table"},
        {"$ref": "#/$defs/model"},
    ],
    "$defs": {
        "common": {
            "type": "object",
            "required": ["id", "source", "pol", "unit", "source_file", "sha1", "processing"],
            "properties": {
                "id": {"type": "string"},
                "source": {"type": "string"},
                "pol": {"type": "string"},
                "unit": {"const": "nm"},
                "source_file": {"type": "string"},
                "sha1": {"type": ["string", "null"]},
                "processing": {"type": "object"},
            },
        },
        "table": {
            "allOf": [
                {"$ref": "#/$defs/common"},
                {
                    "type": "object",
                    "required": ["kind", "range_nm", "points", "data"],
                    "properties": {
                        "kind": {"const": "table"},
                        "range_nm": {
                            "type": "array", "minItems": 2, "maxItems": 2,
                            "items": {"type": "number"},
                            "description": "wl_min, wl_max in nm, ascending",
                        },
                        "points": {"type": "integer", "minimum": 1},
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
                },
            ],
        },
        "model": {
            "allOf": [
                {"$ref": "#/$defs/common"},
                {
                    "type": "object",
                    "required": ["kind", "model"],
                    "properties": {
                        "kind": {"const": "sellmeier"},
                        "model": {
                            "type": "object",
                            "required": ["formula", "terms"],
                            "properties": {
                                "formula": {"type": "string"},
                                "terms": {
                                    "type": "array",
                                    "items": {
                                        "type": "array", "minItems": 2, "maxItems": 2,
                                        "items": {"type": "number"},
                                    },
                                },
                            },
                        },
                        "range_nm": {"type": "null"},
                        "points": {"type": "null"},
                    },
                },
            ],
        },
    },
}


def main():
    OUT_DB.mkdir(exist_ok=True)
    OUT_CAT.mkdir(exist_ok=True)
    catalog = {}
    variants = {}
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
        sha1 = __import__("hashlib").sha1(path.read_bytes()).hexdigest()
        for pol, (wl, nv, kv, proc) in series.items():
            if not wl:
                continue
            fname, rec = emit(mid, source, pol, wl, nv, kv, rel, proc, sha1)
            entry = catalog.setdefault(mid.lower(), {"id": mid, "v": []})
            if alias:
                merged = {a for a in alias if a and a.lower() != mid.lower()}
                merged |= set(entry.get("a", []))
                entry["a"] = sorted(merged)
            entry["v"].append([source if pol == "n" else f"{source}:{pol}", f"db/{fname}"])
            variants[f"db/{fname}"] = [source, rec["range_nm"][0], rec["range_nm"][1],
                                       rec["points"], pol]
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
        entry["f"] = stem if re.match(r"^[A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*)*$", stem) else None
        entry["v"].sort(key=lambda x: (SOURCE_RANK.get(x[0].split(":")[0], 99), x[0], x[1]))

    FORMULA_RE = re.compile(r"^[A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*)*$")
    ELEM_RE = re.compile(r"[A-Z][a-z]?")
    keys = set(catalog)
    for slug, entry in catalog.items():
        while_list = []
        base = entry.get("f")
        base_elems = {m.group(0) for m in ELEM_RE.finditer(base)} if base and FORMULA_RE.match(base) else None
        others = {m["id"] for k2, m in catalog.items() if k2 != slug}
        for a in entry.get("a", []):
            if a in others:
                continue  # exactly shadows a different material
            if base_elems and FORMULA_RE.match(a):
                if {m.group(0) for m in ELEM_RE.finditer(a)} != base_elems:
                    continue  # different chemistry, e.g. SiON is not Si3N4
            while_list.append(a)
        entry["a"] = sorted(set(while_list))

    for mid, rows in sanity_seen.items():
        best = max(rows, key=lambda r: 1 if abs(r[1] - r[2]) < 0.1 * r[2] else 0)
        if abs(best[1] - best[2]) > 0.1 * best[2]:
            stats["sanity"].append([mid, best[0], round(best[1], 5), best[2]])

    (OUT_DB / "_schema.json").write_text(json.dumps(SCHEMA, indent=1), encoding="utf-8")

    (ROOT / "catalog.json").write_text(
        json.dumps({"schema": "nk-catalog/1", "generated": NOW, "materials": catalog},
                   separators=(",", ":")), encoding="utf-8")

    ranges = {}
    for slug, entry in catalog.items():
        vals = [json.loads((ROOT / rel).read_text(encoding="utf-8"))["range_nm"] for _, rel in entry["v"]]
        vals = [v for v in vals if v]
        if vals:
            ranges[slug] = [min(v[0] for v in vals), max(v[1] for v in vals)]
    (OUT_CAT / "ranges.json").write_text(
        json.dumps({"unit": "nm", "materials": ranges}, separators=(",", ":")), encoding="utf-8")

    (OUT_CAT / "sources.json").write_text(
        json.dumps({"schema": "nk-sources/1", "sources": SOURCE_META}, separators=(",", ":")),
        encoding="utf-8")
    (OUT_CAT / "variants.json").write_text(
        json.dumps({"schema": "nk-variants/1", "unit": "nm",
                    "fields": ["source", "wl_min", "wl_max", "points", "pol"],
                    "variants": variants}, separators=(",", ":")), encoding="utf-8")

    import hashlib
    def sha256_file(rel):
        return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()

    ambiguous = {}
    for slug, entry in catalog.items():
        names = [entry["id"]] + ([entry["f"]] if entry.get("f") else []) + entry.get("a", [])
        for name in names:
            ambiguous.setdefault(name.lower(), set()).add(slug)
    groups = [sorted(v) for v in ambiguous.values() if len(v) > 1]
    (ROOT / "catalog" / "ambiguous.json").write_text(
        json.dumps({"schema": "nk-ambiguous/1",
                    "note": "Names that collide after case folding. Fetch both candidates "
                            "and choose from formula or context; never auto-resolve.",
                    "groups": sorted(groups)}, separators=(",", ":")), encoding="utf-8")

    manifest = {
        "schema": "nk-manifest/1",
        "generated": NOW,
        "materials": len(catalog),
        "variants": len(variants),
        "sha256": {
            "catalog.json": sha256_file("catalog.json"),
            "catalog/ranges.json": sha256_file("catalog/ranges.json"),
            "catalog/variants.json": sha256_file("catalog/variants.json"),
            "catalog/sources.json": sha256_file("catalog/sources.json"),
            "catalog/ambiguous.json": sha256_file("catalog/ambiguous.json"),
        },
    }
    (ROOT / "catalog" / "manifest.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")

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
