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

## API answers (checked end to end)

The exact shape of every endpoint's answer is a pydantic model in
`src/earth_system_trend/contract.py`: `Health`, `Results` (`/results`),
`RegionsResponse` (`/regions`), `SeriesResponse` (`/series`) and
`TrendResponse` (`/trend`). Unknown fields are rejected.
`python -m earth_system_trend.e2e` runs the pipeline, asks the API every
endpoint and validates each answer against these models (ESD-D14-BE).

## Changelog
- v0.1: initial draft
- v1.1: per-region results files in `results/regions/` and the `/regions` list (ESD-D12-BE). The results file shape itself is unchanged.
- v1.1 (unchanged shape, release v0.2): added response models for every endpoint and the end-to-end test that checks them (ESD-D14-BE).