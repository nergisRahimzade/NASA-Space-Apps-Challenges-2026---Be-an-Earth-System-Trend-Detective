# Phoenix nighttime LST data card

**ESD-D16-DAT** | Preliminary analysis

| Item | Specification |
| --- | --- |
| Source | NASA Terra/MODIS, [MOD11C3.061](https://www.earthdata.nasa.gov/data/catalog/lpcloud-mod11c3-061), archived by LP DAAC |
| DOI | [10.5067/MODIS/MOD11C3.061](https://doi.org/10.5067/MODIS/MOD11C3.061) |
| Citation | Wan, Z., Hook, S., & Hulley, G. (2021). *MODIS/Terra Land Surface Temperature/Emissivity Monthly L3 Global 0.05Deg CMG V061* [Data set]. NASA LP DAAC. |
| Use policy | NASA open data: no restrictions on subsequent use or redistribution; dataset citation requested. [Official policy](https://modaps.modaps.eosdis.nasa.gov/services/faq/LAADS_Data-Use_Citation_Policies.pdf). |
| Resolution | 0.05° latitude/longitude grid, about 5.6 km at the equator; calendar-month composites of daily MOD11C1 values. [Product specification](https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/MOD11C3/). |
| Measurement | Clear-sky nighttime land surface temperature, source field `LST_Night_CMG`; output °C. This measures surfaces, not near-surface air temperature. |
| Study window | West -112.4, south 33.2, east -111.6, north 33.8 degrees; fixed Phoenix-area window containing urban and surrounding land, 12 x 16 cells. |
| Period | January 2003-December 2024, 264 months. |
| Outputs | Whole-window and four subregion `date,value` CSVs, monthly anomalies, and a 192-cell `trend_map.nc`. |

## Processing

1. Verify the original HDF4 files against the monthly manifest, including SHA-256,
   dates, product version, grid and variable metadata.
2. Combine the monthly files, extract the fixed window, mask numeric fill and
   out-of-range values, apply metadata scaling once, and convert LST from Kelvin
   to Celsius. Preserve QC flags and clear-sky bitmaps.
3. Compute monthly means with `cos(deg2rad(latitude))` weights. Missing cells are
   excluded from the denominator; an empty month retains a missing value.
4. Subtract the 2003-2024 mean for each calendar month to form anomalies.
5. Use the existing original Mann-Kendall/Sen function for the preliminary
   raw-series map. Incomplete cell records retain missing statistics.

Production QC, observation-time stability and seasonal/serial-dependence treatment
remain under review. See [validation](validation.md) for the significance
sensitivity and literature comparison.

## Reproduction

Requires the 264 original files and `data/manifest.csv` from the
[Day 5 download](https://github.com/nergisRahimzade/NASA-Space-Apps-Challenges-2026---Be-an-Earth-System-Trend-Detective/pull/15).
From the repository root, choose a new output directory:

```sh
uv sync --locked
uv run --locked python scripts/reproduce_data.py --output data/day16_replay
```

The script stages the three preprocessing modules from
[Day 8 commit 5364599](https://github.com/nergisRahimzade/NASA-Space-Apps-Challenges-2026---Be-an-Earth-System-Trend-Detective/tree/5364599356de78c1dec1ec147bb9624b0c2f7718/src),
then uses the current aggregation, anomaly, subregion and map functions. If that
Git object is absent, run `git fetch origin feature/ESD-D08-DAT` first.
It starts from the downloaded raw snapshot and empty outputs; this is a processing
replay, not a new download. The output directory contains its check report.

The [Day 16 check](evidence/day16/reproduction_check.json) records source
checksums and code versions. All 264 raw-file checksums passed; all 17 clean
variables matched, the six CSVs were byte-identical, and all map fields and
coordinates matched. This confirms computational reproduction of the current
preliminary products.
