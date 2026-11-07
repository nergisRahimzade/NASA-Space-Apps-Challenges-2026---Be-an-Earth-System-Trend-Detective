# Results Contract (v1.1)

The agreed shape of `results.json`. Everyone builds against `results.mock.json`
until real data replaces it (USE_MOCK=false).

## Fields

| Field | Type | Notes |
| --- | --- | --- |
| region | string | Region name |
| variable | string | What is measured |
| units | string | Used for chart axis labels |
| period.start / period.end | string "YYYY-MM" | Monthly data |
| series[] | list of {date, value} | date is "YYYY-MM", value is a number or null for missing |
| trend.slope | number | Change per month, in `units` |
| trend.p | number or null | p-value. Significant if < 0.05 |
| trend.tau | number | Kendall's tau, between -1 and 1 |
| trend.trend | string | One of: "increasing", "decreasing", "no trend" |
| explanation | string | At most 120 words, uses only numbers present in `trend` |

## Rules
- Every field is required. Use null for missing values, never omit a key.
- Dates are sorted oldest to newest, one entry per month.
- Field names are snake_case and do not change without a version bump.

## Sub-regions (v1.1)

- Each sub-region has its own results file, `results/regions/<id>.json`, in exactly the shape above. `<id>` is the region's short name from `docs/subregions.json` (for example `phoenix_northwest`); the file's `region` field holds its label (for example "Phoenix northwest window").
- `results/results.json` stays the whole study area.
- `GET /regions` lists the whole study area first, then every sub-region, as:

```json
{
  "regions": [
    {
      "id": "phoenix_study_area",
      "region": "Phoenix study area",
      "variable": "Nighttime land surface temperature",
      "units": "°C",
      "period": { "start": "2003-01", "end": "2024-12" },
      "trend": { "slope": 0.0078, "p": 0.1962, "tau": 0.053, "trend": "no trend" }
    }
  ]
}
```

- `/series?region=` and `/trend?region=` take a region's `id` or label, ignoring upper/lowercase. A region with no file returns 404.

## v1.2 (ESD-D15-BE) - additive, v1.1 readers keep working

- Files: one per variable at `results/<variable>/results.json`; `results/index.json` lists them;
  `results/results.json` is still written (copy of `output.primary_variable` in config.yaml).
- New top-level: `contract_version` ("1.2"), `variable {name, long_name, units}`,
  `meta {generated_at, config_fingerprint, source_file}`.
- New in `trend`: `test`, `significant` (p < alpha and a direction), `slope_unit`,
  `slope_per_year`, `n` (valid months). `trend.trend` may now also be `"insufficient data"`
  (then `slope`, `p`, `tau` are null).
- `series[].value` may be null for missing months (never NaN).
- Unchanged: `region`, `period`, `series[]`, `trend{slope, p, tau, trend}`, `explanation`.

## Changelog
- v0.1: initial draft
- v1.1: per-region results files in `results/regions/` and the `/regions` list (ESD-D12-BE). The results file shape itself is unchanged.
