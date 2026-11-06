# Phoenix subregion monthly series

**ESD-D11-DAT** | January 2003-December 2024 | Units: °C

The existing Phoenix study window is divided at longitude -112.0 and latitude
33.5 into four geographic windows. Each contains 6 x 8 = 48 grid cells. Labels
describe position within the study window.

| Region ID | Bounds: west, south, east, north |
| --- | --- |
| `phoenix_northwest` | -112.4, 33.5, -112.0, 33.8 |
| `phoenix_northeast` | -112.0, 33.5, -111.6, 33.8 |
| `phoenix_southwest` | -112.4, 33.2, -112.0, 33.5 |
| `phoenix_southeast` | -112.0, 33.2, -111.6, 33.5 |

[Definitions and labels](subregions.json) |
[Region overview](evidence/day11/subregions.png)

Each `data/processed/timeseries_<region_id>.csv` has `date,value` columns and
264 rows. Dates use `YYYY-MM`. Values are monthly nighttime LST means, using
`cos(deg2rad(lat))` weights as in Day 9. Missing cells are excluded from the
denominator; a wholly missing month keeps a blank value.

Cell centers use west <= longitude < east and south <= latitude < north.
All 192 source cells belong to exactly one window. The four series reconstruct
the whole-window mean when recombined using their nonmissing area weights.
Every CSV was reread by the existing backend loader with matching dates and values.
The [check record](evidence/day11/subregion_check.json) includes counts, bounds
and file hashes.

These files supply the regional data for the later multi-region API work.
The current API still serves one selected results file. The inherited numeric
fill/range policy is retained; production QC remains pending.
