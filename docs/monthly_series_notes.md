# Phoenix monthly nighttime LST series

**ESD-D09-DAT** | January 2003-December 2024 | Units: °C

`data/processed/timeseries.csv` contains 264 rows with `date,value` columns.
Dates use `YYYY-MM`, matching the existing backend reader. The input is
`lst_night` from [Day 8's clean.nc](https://github.com/nergisRahimzade/NASA-Space-Apps-Challenges-2026---Be-an-Earth-System-Trend-Detective/pull/19).

For each month, weights are `cos(deg2rad(lat))` and the mean is computed with
`.weighted(weights).mean(["lat", "lon"], skipna=True)` across the fixed Phoenix
window: west -112.4, south 33.2, east -111.6, north 33.8 degrees.
Missing cells are excluded from the weighted denominator. An entirely missing
month keeps its row with a blank value, which the backend reads as null.

The CSV was read back with the team's `load_timeseries` function. All 264 dates
and values matched; there are no missing monthly values in this input. An
independent calculation using explicit weighted sums matched every monthly mean.
The [check record](evidence/day9/series_check.json) records file hashes, units,
date coverage and the input quality policy.

The series inherits Day 8's numeric fill/range cleaning. The production QC policy
remains pending.
