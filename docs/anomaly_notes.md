# Phoenix monthly nighttime LST anomalies

**ESD-D10-DAT** | Baseline: January 2003-December 2024 | Units: °C difference

`data/processed/anomaly.csv` contains 264 `date,value` rows, matching the dates
in Day 9's monthly series.

For each calendar month, the baseline is the mean of its 22 values during
2003-2024. Each anomaly is the original value minus that month's baseline.
For example, January values are compared with the January mean, not with an
annual average. The calculation uses `groupby("time.month").mean()`.

Positive values are above that calendar month's baseline; negative values are
below it. Missing input values remain blank. A calendar month with fewer than
two known baseline values also remains blank, matching the frontend behavior.
All 12 baseline months currently have 22 known values, so there are no missing
anomalies.

The [comparison plot](evidence/day10/raw_vs_anomaly.png) shows the original
monthly temperatures and anomalies in separate panels. The anomaly panel has
a zero reference line. The [check record](evidence/day10/anomaly_check.json)
contains the 12 baseline means, counts and file hashes.

The source retains Day 9's fill/range-only cleaning; the production QC policy
remains pending.
