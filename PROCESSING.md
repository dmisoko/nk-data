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

Duplicate wavelengths inside one source file are collapsed to the first
occurrence; the number removed is reported as `processing.wl_duplicates_removed`.

## Missing extinction coefficient

Palik tables use `-0.0001` to mean "no value at this row".

- Rows whose refractive index is `-0.0001` are dropped: no data exists there.
- A missing `k` between two absorbing neighbours (both `> 0.05`) is linearly
  interpolated in wavelength: `processing.k_interpolated`.
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

## Not applied

- No smoothing, averaging, fitting or noise removal.
- No extrapolation beyond the source range.
- No unit guessing at read time: the unit is fixed per source and recorded in
  `processing.unit_from`.
