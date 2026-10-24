# Phoenix nighttime land surface temperature — Data notes

**Ticket:** ESD-D03-DAT | **Date:** 2026-10-24

## Study

**Question:** Has monthly nighttime land surface temperature in the Phoenix study
area changed between 2003 and 2024?

- **Period:** January 2003–December 2024; 264 months.
- **Fixed window:** west −112.4°, south 33.2°, east −111.6°, north 33.8°;
  includes urban and surrounding land.
- **Measurement:** clear-sky nighttime land surface temperature (LST).

## Dataset selection

Both are NASA MODIS/Terra monthly temperature products. `.061` identifies
Collection 6.1.

| Role | Dataset | Reason |
| --- | --- | --- |
| Primary | [MOD11C3.061][primary] | Covers the study period; sample downloaded and read successfully; lower download volume. |
| Backup | [MOD21C3.061][backup] | Same monthly variable and grid, with a different temperature/emissivity retrieval method. Requires a separate sample and quality check before use. |

## Specifications

| Property | MOD11C3.061 | MOD21C3.061 |
| --- | --- | --- |
| Nighttime field | `LST_Night_CMG` | `LST_Night` |
| Units | Decoded Kelvin; output in °C | Same |
| Spatial resolution | Global 0.05° grid; approximately 5.6 km north–south | Same |
| Temporal resolution | Calendar-month composite | Same |
| Record coverage | From February 2000; all 264 study-period monthly records found | Same |
| Format | HDF-EOS/HDF4 | Same |
| Stored type and fill | uint16; fill = 0 | Same |
| Valid stored range | 7,500–65,535 | Same |
| Scale | 0.02 K per stored unit | Same |
| Full-period catalogue size | 18,535.43 MB | 34,307.15 MB |

Mask fill and out-of-range values, then convert:

```text
LST (°C) = valid stored value × 0.02 − 273.15
```

Original HDF4 files are global; Phoenix is extracted locally. The 264-file count
confirms the calendar, not regional observation quality.

## Sample check

**File:** `MOD11C3.A2024122.061.2024162162404.hdf`  
**Period:** May 2024 | **Size:** 73,205,010 bytes  
[Official download][sample] — Earthdata login required.

| Check | Result |
| --- | --- |
| File identity, dates and grid | Confirmed from actual metadata |
| HDF4 reading | Nighttime LST, quality, observation-time and clear-night layers opened |
| Phoenix extraction | 12 × 16 cells; all 192 temperatures nonfill and in range |
| Conversion | Celsius decoding and xarray/NetCDF transfer verified |

**Quality finding:** all 192 cells carry mandatory QA code 1 (produced, other
quality). A test requiring mandatory code 0, good L1B quality and the lowest
LST-error class retained 0 cells; its mean remains null. This conservative test
is not a NASA-required monthly rule. Resolve the monthly QA interpretation and
production mask before analysis.

Checks dated October 24, 2026:
[catalogue audit](evidence/day3/inventory_summary.json),
[sample results](evidence/day3/sample_evidence.json),
[xarray validation](evidence/day3/xarray_bridge_validation.json).

[primary]: https://ladsweb.modaps.eosdis.nasa.gov/filespec/MODIS/61/MOD11C3
[backup]: https://ladsweb.modaps.eosdis.nasa.gov/filespec/MODIS/61/MOD21C3
[sample]: https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/MOD11C3.061/MOD11C3.A2024122.061.2024162162404/MOD11C3.A2024122.061.2024162162404.hdf
