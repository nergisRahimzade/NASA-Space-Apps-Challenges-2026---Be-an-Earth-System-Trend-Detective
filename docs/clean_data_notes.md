# Clean Phoenix data

**ESD-D08-DAT** | MOD11C3.061 | January 2003-December 2024

## Output

`data/processed/clean.nc` contains all 17 fields on `(time=264, lat=12, lon=16)`.
Latitude centers run from 33.775 to 33.225 degrees north; longitude centers run
from -112.375 to -111.625 degrees east. The month-start time coordinates are retained.
The file is generated locally under the ignored `data/processed/` directory.

## Cleaning

- Numeric fill and out-of-range stored values become NaN before decoding.
- LST is scaled to Kelvin, then converted to Celsius.
- Original dimensions become `lat` and `lon`; `.sel()` selects the fixed Phoenix
  window. Variables use the names below.
- QC and clear-sky bitmaps retain their unsigned integer values, including 0.
  Their NA text declarations are not numeric fill values.

| Clean fields | Units or meaning |
| --- | --- |
| `lst_day`, `lst_night` | Degrees Celsius |
| `day_view_time`, `night_view_time` | Numeric UTC clock hours (`hrs`) |
| `day_view_angle`, `night_view_angle` | Degrees |
| `emissivity_20/22/23/29/31/32` | Dimensionless emissivity |
| `percent_land` | Percent |
| `qc_day`, `qc_night` | Original monthly QC bytes |
| `clear_sky_days`, `clear_sky_nights` | Original calendar-day bitmaps |

Original variable attributes are retained as provenance JSON. Active packed
scaling is removed so reopening does not decode the values twice. The original
global-grid metadata is replaced with the Phoenix coordinates and study bounds.

## Checks

The saved NetCDF was reopened and all values, coordinates and types matched.
Five source months (2003-01, 2004-02, 2024-05, 2024-07, 2024-12) independently
matched all 17 cleaned fields. Nighttime LST ranges from -1.11 to 36.53 degrees
Celsius across the study window and period.

[Check record](evidence/day8/clean_check.json) |
[January, May and July 2024 maps](evidence/day8/clean_maps.png)

This file applies numeric fill/range cleaning. The monthly production QC policy
remains pending; flags are preserved for that step.
