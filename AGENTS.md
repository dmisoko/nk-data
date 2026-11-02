# Refractive index data — machine access contract

This repository publishes a derived, machine-readable data layer next to the
original `.nk` files. Everything is plain static HTTPS: **no API key, no
authentication, no `git clone`**. Two GET requests fetch any material.

## Endpoints

| Purpose | Path | Typical size |
|---|---|---|
| Search index | `catalog.json` | ~118 KB |
| Wavelength coverage only | `catalog/ranges.json` | ~45 KB |
| One material, one source | `db/<id>.<source>.json` | 2–40 KB |
| JSON Schema for `db/` files | `db/_schema.json` | ~2 KB |

Two interchangeable bases, **identical path suffix**:

1. `https://dmisoko.github.io/nk/`            (GitHub Pages — preferred)
2. `https://cdn.jsdelivr.net/gh/dmisoko/nk@main/`  (jsDelivr — fallback)

Switch base only; never change the path. Do not use `api.github.com`
(60 requests/hour per IP) and do not use `raw.githubusercontent.com` in
production (undocumented throttling, `text/plain` content type).

## Protocol

```
1) GET {base}catalog.json
2) GET {base}<variants[].path>        e.g. db/sio2.sopra.json
```

`catalog.json` is compact on purpose: it carries only what is needed to find a
material and locate its file.

```json
{
  "schema": "nk-catalog/1",
  "generated": "2026-11-02",
  "materials": {
    "sio2": {
      "id": "sio2",
      "f": null,
      "a": [],
      "v": [["sopra", "db/sio2.sopra.json"], ["windt", "db/sio2.windt.json"],
          ["kla", "db/sio2.kla.json"]]
    }
  }
}
```

- `materials` is an object keyed by a lowercase slug.
- `id` — display name as used in the original source.
- `f` — chemical formula when the file name is a formula (`Al2O3`), else `null`.
- `a` — extra aliases (may be empty).
- `v` — variants: `[source, path]` (`source:pol` for anisotropic series),
  **ordered by preference**: use `v[0]` by default, override only for a reason
  (required wavelength range, `k` behaviour for metals, polarisation).
  Preference order is `kla`, `palik`, `sopra`, `windt`, `rii`, `setfos`,
  `unight`, `coatings`, `litho`, `various`, `freesnell`.

Match strategy: normalize the query (lowercase, strip spaces/punctuation),
then try exact key, then `id`/`f`/`a` equality, then substring. Example:
`silicon dioxide`, `SiO2`, `silica` all resolve to key `sio2`.

## `db/*.json` format

One file holds exactly one series: one material, one source, one polarisation.

```json
{
  "id": "sio2",
  "source": "sopra",
  "pol": "n",
  "source_file": "sopra/sio2.nk",
  "unit": "nm",
  "kind": "table",
  "range_nm": [163.14, 2066.42],
  "points": 71,
  "data": {
    "wl": [163.14, 165.31, "..."],
    "n": [1.653, 1.6425, "..."],
    "k": [0.0, 0.0, "..."]
  }
}
```

- `wl` is **always in nanometres**, sorted ascending; `n`, `k` are parallel arrays.
- `pol` is `n` for isotropic data, or `o` / `e` for the ordinary / extraordinary
  ray of an anisotropic material. Those ship as separate files, e.g.
  `db/al2o3-a.palik.o.json` and `db/al2o3-a.palik.e.json`, and appear in the
  catalog as `["palik:o", "db/al2o3-a.palik.o.json"]`.
- Absent absorption is `0.0`, never `null`.
- Interpolate linearly between adjacent samples; never extrapolate outside
  `range_nm`.

## Coverage questions

`catalog.json` intentionally omits wavelength ranges to keep it small. If a
question is about coverage ("which material covers 1550 nm?", "what is the
widest range for gold?"), fetch `catalog/ranges.json` once. It lists tabulated
series only; `kind: "sellmeier"` entries have no wavelength grid and are absent:

```json
{"unit": "nm", "materials": {"au": [12.4, 1000000.0], "...": ["min", "max"]}}
```

Otherwise fetch the single material file — its `range_nm` is the authoritative
answer for that variant.

## Token budget

The catalog is up to ~100 KB; never paste it into a prompt. With code
execution, fetch it inside the script and print only the matched entries
(a few hundred bytes). One material file is 2–40 KB and only the requested
wavelength interval matters.

## Provenance

See `NOTICE.md`. Values are reproduced from public scientific sources and the
KLA refractive index database with attribution; verify against your own
measurements before using them in production designs.
