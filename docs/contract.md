# Results Contract (v0.1)

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

## Changelog
- v0.1: initial draft