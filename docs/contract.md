# Results Contract (v1.2

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

- v1.2: trend map file and GET /map (ESD-D13-BE). Other files unchanged.
## Trend map (v1.2)

Per-cell trends for the map live in their own file, so `results.json` does not change.

- Mock: `trend_map.mock.json` (made-up numbers on the Phoenix grid; rebuild with `scripts/make_mock_map.py`).
- Real: `results/trend_map.json`, written by the Data layer's trend map step (ESD-D13-DAT). `MAP_PATH` overrides both.

| Field | Type | Notes |
| --- | --- | --- |
| region, variable, units, period | as above | Describe the whole map |
| test | string | Trend test run on each cell |
| resolution_deg | number | Grid spacing in degrees; each point is a cell center |
| points[] | list | One entry per grid cell |
| points[].lat / lon | number | Cell center, degrees |
| points[].slope | number or null | Change per month, in `units` |
| points[].p, tau, trend | as in `trend` | Same meaning as the area trend |

A cell with fewer than 24 months of values has `slope`, `p`, `tau` and `trend` all null. They are either all set or all null.

`GET /map` returns this file plus `point_count` and `original_point_count`. It never sends more than 5,000 cells (`?max_points=` lowers that): a bigger grid is thinned to every k-th row and column, and `resolution_deg` is multiplied by k so the cells still tile the area. Answers over 1 kB are gzip-compressed for clients that accept it.
## Changelog
- v0.1: initial draft
- v1.1: per-region results files in `results/regions/` and the `/regions` list (ESD-D12-BE). The results file shape itself is unchanged.
