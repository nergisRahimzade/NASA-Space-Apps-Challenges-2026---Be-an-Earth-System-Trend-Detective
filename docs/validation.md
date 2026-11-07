# Validation against published trends

**ESD-D14-DAT** | Phoenix nighttime LST | MOD11C3.061 | 2003-2024

## Current result

The fixed window is west -112.4, south 33.2, east -111.6, north 33.8 degrees.
Its 264 monthly values use cosine-latitude weights. The current function applies
the original Mann-Kendall test and Sen slope.

| Whole-window series | Slope (°C/decade) | p | Interpretation |
| --- | ---: | ---: | --- |
| Original monthly values | +0.931 | 0.1962 | Not significant at 0.05; backend direction is `no trend` |
| Existing monthly anomalies | +0.844 | 5.78e-11 | Diagnostic only; seasonality removed, serial dependence not corrected |

Anomalies use the confirmed 2003-2024 calendar-month baseline. Rates above use
unrounded library slopes multiplied by 120. Backend and map rounding are unchanged;
the backend's anomaly `p=0.0` is a rounded display, not a zero probability.
The [check record](evidence/day14/validation_check.json) contains source hashes
and full-precision results.

## Published comparisons

| Study | Published result | Comparison limits |
| --- | --- | --- |
| [Waring et al. (2023)](https://doi.org/10.1080/01431161.2023.2240522), Sections 3.2 and 4.2.2, Figure 8, Table 1 | Western U.S.A. nighttime LST anomalies, Aqua MYDCCI, 2002-2021: **+0.52 K/decade**, significant at 0.05. A temperature change of 1 K equals 1°C. | Regional nighttime context, with a different boundary, sensor/product and period. The paper corrects p-values for autocorrelation where detected; our current test does not. |
| [Zhu et al. (2023)](https://doi.org/10.1029/2022AV000816), Table 1, Section 2.2.2, Section 3.1/Figure 2e | Phoenix summer Landsat LST, 2000-2020: average pixel Sen slope **+0.11°C/year = +1.10°C/decade**. | Summer annual means at 30 m, different coverage and period, and an average of pixel slopes rather than a slope of the regional mean. This is not a nighttime MODIS benchmark. |

Waring's results text reports +0.52; its abstract, also reproduced in the
[NASA publication record](https://modis.gsfc.nasa.gov/sci_team/pubs/abstract_new.php?id=62131),
reports +0.54 K/decade. The table uses the results text and retains this discrepancy.
Zhu's nighttime ECOSTRESS scenes are from summer 2019, separate from the
Landsat trend record; see the [author data archive](https://zenodo.org/records/7406719).

## Assessment

The positive slopes agree in direction, but neither paper reproduces our exact
measurement. Our original-series p-value also differs from Waring's significant
result. Different spatial coverage, years, seasonal sampling, aggregation and
statistical treatment prevent interpreting those differences as a measured error.

The anomaly diagnostic shows that the significance conclusion depends on seasonal
treatment. It does not establish corrected significance. The current series and
map remain preliminary while production QC, observation-time stability and
seasonality/serial-dependence treatment are reviewed with the analysis layer.

**Outcome:** the literature comparison is complete; quantitative replication and
scientific sign-off are not established. The existing analysis method is unchanged.
