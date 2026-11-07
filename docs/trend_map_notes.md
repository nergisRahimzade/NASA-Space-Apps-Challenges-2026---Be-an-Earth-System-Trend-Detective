# Phoenix per-cell trend map

**ESD-D13-DAT** | MOD11C3.061 nighttime LST | January 2003-December 2024

`data/processed/trend_map.nc` contains the existing 12 x 16 Phoenix grid,
with each cell using its complete 264-month record. Computation uses
`xr.apply_ufunc(vectorize=True, dask="parallelized")` and the existing
`run_trend` on original monthly values.

| Field | Meaning |
| --- | --- |
| `slope` | Sen slope, °C per month |
| `p`, `tau` | Original Mann-Kendall p-value and Kendall tau |
| `direction` | -1 decreasing, 0 no trend, 1 increasing, 2 not computed |
| `n_valid` | Number of finite monthly values |
| `status` | 0 computed, 1 incomplete, 2 short, 3 test error |

Cells with missing months keep missing statistics rather than compressing the
calendar. Backend rounding is retained: slope/p to four decimals, tau to three.

The 4 x 4 sample took 0.071 seconds; the full 192-cell window took 0.649 seconds
on one thread. All 192 cells completed, and the sample matched the full-window
result. **Decision: retain the optional map**, within the 30-second local budget.
The four subregion series remain the fallback for slower runs.

[Preview](evidence/day13/trend_map.png) |
[Run and NetCDF readback check](evidence/day13/trend_map_check.json) |
[Independent library check](evidence/day13/map_validation.json)

The map is preliminary. It uses raw monthly values and the current original
Mann-Kendall method; seasonality, serial dependence and production QC remain
subject to scientific review. The preview shows slopes without significance
markers. NetCDF coordinates, values, attributes and integer flags were verified
after saving; all 192 cells also matched direct library calculations.
