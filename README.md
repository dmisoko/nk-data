
Refractive Index Spectra Collections for TFTB thin film toolbox
===============================================================

Multilayer analysis software can only be as good as the optical
constants that it uses. The data collections in this archive combine
all publicly available refractive index data I could find on the Web,
with the exception of those data still buried in scientific
publications. The index spectra collections also contain functions for
MATLAB and Octave that allow the data files to be read by the TFTB thin
film toolbox.


sopra 
----- 
A collection of optical constant data that is distributed free by the
French company SOPRA S.A., a maker of ellipsometry equipment. Origin
and quality of the data is not known to me. I have reformatted the
files to make them easier to read.


coatings
--------
A collection of refractive index data for materials in thin film coatings.
The file headers of the data files should contain information about the
coating processes, parameters, and conditions.


windt
-----
A collection of refractive index data that are distributed by David
Windt together with his imd software
(http://www.rxollc.com/windt). Emphasis is on short wavelengths
(x-rays). Contains many data sets from Edward Palik's "Handbook of
Optical Constants".


palik
-----
Refractive index data from Edward Palik, Handbook of Optical Constants
I & II, Published by the Optical Society of America. Data are of high
quality, with references to original publications. Some data files for
optically active materials have a different format and must be read
"manually". A value of -0.0001 is used to indicate missing data.


freesnell
---------
A collection of optical constant data that is distributed with
FreeSnell ( http://people.csail.mit.edu/jaffer/FreeSnell/ ) Most data
appear to be from fairly recent publications, which makes it possible
to evaluate the data quality and uncertainty. Some data for polymers.


litho
-----
A small collection of refractive index spectra in the visible and UV,
mostly for lithography related materials. Some were obtained from
publications or data sheets, and some were measured at NIST using
ellipsometry.


rii
---
Refractive index data from the main "book" of http://refractiveindex.info,
compiled by Mikhail Polyanskiy. The data were converted from their
native .yaml format into tables and functions that can be used by the 
toolbox.


various
-------
Index spectra from different, usually commercial sources such as
www.filmetrics.com and www.pvlighthouse.com.au. The uncertainty of the
data is unknown, references to original publications are included in
the files where available.


analytic
--------
MATLAB & Octave functions for refractive indices that can be
calculated from a Sellmeir or Cauchy (or similar) formula.


http://refractiveindex.info is a wonderful new source of refractive
index data. The site is maintained by Mikhail Polyanskiy who seems to
be continuing where E. Palik left off.


Installation
============
When the refractive index data collections are used with the MATLAB &
Octave thin film toolbox they should be installed as follows:

Windows: unzip the data into the root folder 'tftb' of the thin film
toolbox. The read_*.m functions are then automatically in the MATLAB /
Octave search path when the 'tftb' folder is in the search path.

Linux / Unix: either unzip the data into the root directory 'tftb' or
unzip it anywhere and create a symbolic link in the root directory:

  tftb$ ln -s anywhere/nk ./nk  


Please report inconsistencies, problems, and errors. 

Ulf Griesmann, September 2014
ulf.griesmann@nist.gov
ulfgri@gmail.com


## Programmatic access

A machine-readable layer is generated from the original files:

- `catalog.json` - search index (names, formulas, ranked variants)
- `catalog/variants.json` - per-variant band, point count and polarisation
- `catalog/sources.json` - licence and citation per source
- `catalog/ranges.json` - envelope band per material
- `catalog/ambiguous.json` - names that collide after case folding
- `catalog/manifest.json` - build timestamp and SHA-256 of every catalog file
- `db/*.json` - one file per material and source, wavelengths in nanometres

Fetch any material with two plain HTTPS GET requests, no clone and no token:

```
https://dmisoko.github.io/nk/catalog.json
https://dmisoko.github.io/nk/db/sio2.sopra.json
```

Pin a commit, not a branch: CDN edges cache `@master` independently and can serve
older bytes. Use `@<commit-sha>` (or a release tag) for every request in a batch,
compare `catalog/manifest.json` hashes before and after, and never mix variants
read from one revision with `db/` files from another.

See `NOTICE.md` for data provenance and `PROCESSING.md` for the normalisations
applied to the numbers.
Regenerate the derived layer with `python3 tools/build_db.py`.
