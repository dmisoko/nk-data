# Data normalisation record

Every file in `db/` is derived from a source file without smoothing, fitting or
extrapolation. The transformations listed here are the only ones applied, and
each output file records what happened to it in its own `processing` object.

## Wavelength

All wavelengths are converted to nanometres and sorted ascending.

| Source | Native unit | Conversion |
|---|---|---|
| `palik/` | micrometre (column 3) | x 1000 |
| `sopra/`, `rii/`, `litho/`, `coatings/`, `various/` | micrometre | x 1000 |
| `windt/` | Angstrom | x 0.1 |
| `freesnell/` | photon energy in eV | 1239.841984 / E |
| `setfos/`, `unight/`, `sources/kla/` | nanometre | none |
| `analytic/*.m` | micrometre (model input) | model keeps micrometre |

The unit is fixed per source except where the source itself is ambiguous: for
sources without a declared unit, a value range of `>= 100` or a maximum above
`2000` is read as nanometres and everything else as micrometres. Every emitted
record states what was assumed in `processing.unit_from`.

Duplicate wavelengths inside one source file are collapsed to the first
occurrence; the number removed is reported as `processing.wl_duplicates_removed`.
Rounding keeps nine significant digits for wavelength and seven for `n`/`k`, so
X-ray values such as `8.26561e-08 nm` are not truncated to zero.

## Missing extinction coefficient

Palik tables use `-0.0001` to mean "no value at this row".

- Rows whose refractive index is `-0.0001` are dropped: no data exists there.
- Palik tables sometimes leave the micrometre column as `-0.0001` while the
  eV and cm-1 columns are populated. The wavelength is then recovered as
  `1239.841984 / E[eV]`, or `1e4 / nu[cm-1]`, and counted in
  `processing.wl_from_energy_column`. Rows with no recoverable wavelength are
  dropped and counted in `processing.rows_dropped_no_wavelength`.
- A missing `k` between two absorbing neighbours (both `> 0.05`) is linearly
  interpolated **in wavelength**, not by array position: `processing.k_interpolated`.
- A missing `k` elsewhere is set to `0.0`, which is what the sentinel means for
  transparent dielectrics: `processing.k_zero_filled`.
- Index-only tables (two columns, or `k` absent) are stored with `k = 0.0`.

The original sentinel is never written to `db/`.

## Negative extinction

`k` must be non-negative. Some source charts plot `-k`:

- If more than 90% of a series is negative, the sign is flipped and
  `processing.k_sign_flipped` is `true`.
- Remaining small negative values are clamped to `0.0` and counted in
  `processing.k_negative_clamped`.

## Polarisation

Anisotropic sources are split into one file per polarisation. The `pol` field
carries the label used by the source (`n` isotropic, `o` ordinary, `e`
extraordinary, or a source-specific label such as `h`). The catalog lists these
as `<source>:<pol>`.

## Quality flags

Rows with a non-positive refractive index are dropped (a source typo such as
`n = -256`); the count lands in `quality.rows_dropped`. A series is marked
`quality.status = "suspect"` when:

- any row was dropped (`rows_dropped > 0`),
- the unit declared in the source header disagrees with the unit inferred from
  the values (`unit_conflict`), or
- values above the plausible ceiling remain (`n > 200` or `k > 1000`,
  `extreme_values`).

Suspect series are still published so nothing disappears silently, but clients
must not load them without showing the reason. A series whose every row has a
non-positive refractive index is not published at all; such files are counted as
`no_valid_rows` in `tools/build_report.json`.

## Not applied

- No smoothing, averaging, fitting or noise removal.
- No extrapolation beyond the source range.
- No unit guessing at read time: the unit is fixed per source and recorded in
  `processing.unit_from`.
