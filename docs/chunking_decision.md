# Per-cell preparation decision

**ESD-D12-DAT** | MOD11C3.061 nighttime LST | January 2003-December 2024

Requested Dask chunks are `{"time": -1, "lat": 50, "lon": 50}`. The Phoenix
window is smaller, so the actual nighttime array is one `264 x 12 x 16` chunk
(405,504 bytes). Every cell retains its full monthly record.

The centered `4 x 4` sample contains 16 cells with 264 months each. All sample
values matched the direct NetCDF read; all 16 existing trend-function calls
completed, with no missing or failed cells.

| Local check | Seconds |
| --- | ---: |
| Dask sample load | 0.017 |
| Serial trend calls for 16 cells | 0.254 |
| Estimated load and serial calls for all 192 cells | 3.063 |
| Local full-window time budget | 30.000 |

The estimate is sample load time plus sample trend time / 16 x 192. Loading is
counted once because the requested chunk already spans the whole Phoenix window.

**Decision: proceed with the optional Day 13 per-cell trial.** Retain the four
subregion series as the fallback if that trial exceeds the budget.

The [check record](evidence/day12/chunk_check.json) includes chunks, sample
coordinates, timings, source hash and runtime versions. Timing uses a single
thread and the existing `run_trend` on original monthly values. This local
estimate is not a full-window benchmark; final QC and scientific method review
remain pending.
