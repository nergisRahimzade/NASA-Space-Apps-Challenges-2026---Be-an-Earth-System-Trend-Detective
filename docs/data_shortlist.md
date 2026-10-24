# Earth System Trend Detective: Phoenix data shortlist

Ticket: ESD-D02-DAT

Research question and study area selected on 2026-10-24. This document defines the Day 2 question and three candidate products; the main dataset and backup will be chosen after the Day 3 feasibility checks.

## Research question

**Has monthly nighttime land surface temperature in the Phoenix study area changed between 2003 and 2024?**

### Study definition

| Item | Definition |
| --- | --- |
| Region label | Phoenix study area, Arizona, USA |
| Analysis boundary | Fixed box: west -112.4, south 33.2, east -111.6, north 33.8 degrees |
| Bounding-box order | `(west, south, east, north)` = `(-112.4, 33.2, -111.6, 33.8)` |
| Boundary meaning | A reproducible study window around Phoenix, not an official city or metropolitan-area boundary. It includes urban land and surrounding landscapes; the result describes this whole window. |
| Variable | Nighttime land surface temperature (LST), sampled by the selected satellite product |
| Period | 2003-01 through 2024-12 inclusive: 22 years, 264 expected monthly positions |
| Display units | Degrees Celsius after metadata-aware decoding of the original Kelvin measurements |
| Initial output | One regional monthly series, followed by seasonal-anomaly and trend results in the later sprint tasks |

The study uses the same geographic window throughout the record. It does not follow changing city boundaries. Day 3 will check the grid cells, quality information and usable observations in this window before committing to a product.

### Why Phoenix and nighttime LST?

[NASA/JPL's Phoenix case study](https://www.nasa.gov/centers-and-facilities/jpl/nasa-data-shows-fierce-surface-temperatures-during-phoenix-heat-wave/) shows how roads and buildings retained heat overnight during July 2023, with different temperatures over irrigated landscapes. This provides a clear motivation for investigating nighttime surface-temperature changes over a longer record.

That case uses VIIRS observations of a particular heat-wave episode. It does not establish a 2003-2024 MODIS trend. The direction and significance of our trend will be determined by analysis. LST is the temperature of visible surfaces such as roofs, soil and vegetation, not weather-report air temperature; see [NASA's LST explanation](https://science.nasa.gov/earth/earth-observatory/global-maps/land-surface-temperature-anomaly/).

## Three candidate datasets

These are distinct monthly products covering the study window and spanning more than 20 years. Each has a nighttime LST layer. They are alternatives for evaluating the same question, not records to splice together.

| Dataset | Short name / version / CMR collection | Coverage and resolution | Nighttime variable and suitability | Direct sources |
| --- | --- | --- | --- | --- |
| MODIS/Terra Land Surface Temperature/Emissivity Monthly L3 Global 0.05Deg CMG V061 | `MOD11C3` / `061`; `C2565788897-LPCLOUD` | Monthly; record starts 2000-02-01 and extends beyond 2024. Global 0.05-degree CMG, about 5.6 km north-south; longitude-cell width varies with latitude. Raw format: HDF-EOS/HDF4. | `LST_Night_CMG`. A long Terra monthly record with nighttime quality and observation-time information. Check clear-sky sampling, missing data and orbit-drift effects. | [NASA product](https://doi.org/10.5067/MODIS/MOD11C3.061); [Earthdata Search](https://search.earthdata.nasa.gov/search/granules?p=C2565788897-LPCLOUD); [file specification](https://ladsweb.modaps.eosdis.nasa.gov/filespec/MODIS/61/MOD11C3) |
| MODIS/Aqua Land Surface Temperature/Emissivity Monthly L3 Global 0.05Deg CMG V061 | `MYD11C3` / `061`; `C2565794044-LPCLOUD` | Monthly; record starts 2002-07-01 and extends beyond 2024. Global 0.05-degree CMG; HDF-EOS/HDF4. | `LST_Night_CMG`. An Aqua alternative with different nighttime sampling from Terra. Evaluate separately, including quality and observation-time changes. | [NASA metadata](https://data.nasa.gov/dataset/modis-aqua-land-surface-temperature-emissivity-monthly-l3-global-0-05deg-cmg-v061-0f265); [Earthdata Search](https://search.earthdata.nasa.gov/search/granules?p=C2565794044-LPCLOUD); [file specification](https://ladsweb.modaps.eosdis.nasa.gov/filespec/MODIS/61/MYD11C3) |
| MODIS/Terra Land Surface Temperature/3-Band Emissivity Monthly L3 Global 0.05Deg CMG V061 | `MOD21C3` / `061`; `C2565791050-LPCLOUD` | Monthly; record starts 2000-02-01 and extends beyond 2024. Global 0.05-degree CMG; HDF-EOS/HDF4. | `LST_Night`. Uses a temperature/emissivity separation approach. It shares Terra observations with MOD11C3 and is not an independent third observing system; dust/cloud contamination and product-specific quality screening need assessment. | [NASA metadata](https://data.nasa.gov/dataset/modis-terra-land-surface-temperature-3-band-emissivity-monthly-l3-global-0-05deg-cmg-v061-f4999); [Earthdata Search](https://search.earthdata.nasa.gov/search/granules?p=C2565791050-LPCLOUD); [file specification](https://ladsweb.modaps.eosdis.nasa.gov/filespec/MODIS/61/MOD21C3) |

The [NASA LP DAAC CMR tutorial](https://nasa.github.io/LPDAAC-Data-Resources/python/tutorials/Data_Discovery_CMR_API_Request.html) lists the collection identifiers above. The catalogue span establishes eligibility for the shortlist. It does not prove that all 264 monthly files or all regional observations are usable; completeness remains an explicit Day 3 check.

## Earthdata search specification

Use the linked collection for each candidate, version `061`, and the same date window and bounding box:

- Start: `2003-01-01T00:00:00Z`
- End: `2024-12-31T23:59:59Z`
- Study box: `(-112.4, 33.2, -111.6, 33.8)`
- Measurement: the product's nighttime LST layer, kept separate from daytime observations.

The search box filters files whose coverage overlaps Phoenix. These CMG products are global granules: a bounding-box search does not crop the file or reduce download size. A regional extract or subset must be a separate, verified operation.

## Day 3: choose the main dataset and backup

Before selecting a product or planning the full download:

1. **Check monthly availability and regional quality.** Verify dates, missing months, usable land cells and valid observation counts. A complete file calendar does not guarantee complete clear-sky observations in Phoenix.
2. **Open one file successfully.** The raw products are HDF4. Having xarray and netCDF4 installed does not establish HDF4 support. Verify an appropriate reader and a working path into xarray, or a genuinely supported conversion/subsetting route. No monthly AppEEARS or OPeNDAP route has been verified for this shortlist.
3. **Check the download/storage budget.** Record the real file size and expected full-period volume before bulk download, because each source granule is global.
4. **Decode the nighttime layer correctly.** Stored LST uses a 0.02 Kelvin scale and stored zero is fill. Apply the selected product's metadata and quality rules, then convert decoded Kelvin to Celsius by subtracting 273.15. Do not apply scaling twice or reuse one product family's QC bitmask for another without checking its specification.
5. **Inspect nighttime observation times.** Terra and Aqua sample at different times, and [NASA reports effects of orbit drift](https://landweb.modaps.eosdis.nasa.gov/displayissue?id=1254). Choose a consistent product record and assess changing sampling times before interpreting a long-term trend.
6. **Define the regional aggregation rules.** Retain the fixed geographic boundary, inspect mixed land cover and elevation, document any fixed land/water mask and missing-data threshold, and use appropriate area weights. Changing cloud coverage or the mix of valid cells must not silently change the meaning of the series.

If the file-reading, quality or volume check fails, revise the shortlist or access strategy before bulk download. The Day 2 shortlist is not a claim that a complete analysis pipeline already runs.

## Frontend and contract notes

Use the actual variable and boundary label when replacing the mock data. The mock's surface-air-temperature label is not the measurement selected here.

| UI / result field | Planned meaning |
| --- | --- |
| `region` | `Phoenix study area` |
| `variable` | `Nighttime land surface temperature` |
| `units` | `°C` after decoding and conversion |
| `period.start` / `period.end` | `2003-01` / `2024-12` |
| `series[]` | Sorted monthly values; 264 expected calendar positions, with missing values handled explicitly |
| `trend.slope` | `°C per month`, following the current contract; any per-year display requires an explicit conversion and label |
| `trend.p`, `trend.tau`, `trend.trend` | Analysis outputs to be computed later, not numbers established by this shortlist |

The raw/anomaly toggle needs a documented baseline and coordinated series fields. A trend map additionally needs spatial geometry and per-region or per-cell results; one regional slope is insufficient. The approximately 0.05-degree monthly grid supports regional analysis, not street-level heat claims.

This question estimates a clear-sky nighttime surface-temperature trend in a fixed study area. Urban heat-island intensity would require an additional urban-versus-rural comparison; heat-wave-day frequency would require data finer than monthly means. Neither is claimed by the first version.

## Scope and handoff

Day 2 supplies the chosen question, explicit study window and three sourced candidates. Day 3 owns detailed metadata notes, main/backup selection and the sample-file check; Day 4 owns the automated downloader. No temperature trend, causal explanation or final dataset choice has been claimed here.
