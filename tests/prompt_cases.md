# ESD-D05-AI: Prompt Validation Test Cases Matrix

This document tracks the 5 core tricky statistical edge scenarios designed to audit the structural accuracy and physical rule compliance of the LLM pipeline (`src/prompts/explain_v1.txt`).

## 1. Case: Strong Increasing Trend
* **Description:** Highly obvious positive trend with an extremely low p-value.
* **Expected AI Behavior:** Clearly state that a statistically significant increasing trend exists using the exact slope.

```json
{
  "region": "Arctic Circle",
  "period": "2006-2026",
  "trend": {
    "direction": "increasing",
    "p_value": 0.00001,
    "tau": 0.72,
    "slope": 0.045
  }
}
```

---

## 2. Case: No Trend (High Noise)
* **Description:** Data fluctuates rapidly with no stable continuous direction; p-value is completely insignificant.
* **Expected AI Behavior:** State that no statistically significant trend is present in the data.

```json
{
  "region": "Equatorial Pacific",
  "period": "2006-2026",
  "trend": {
    "direction": "no trend",
    "p_value": 0.68000,
    "tau": 0.03,
    "slope": 0.001
  }
}
```

---

## 3. Case: Borderline Significance (p ≈ 0.05)
* **Description:** A potential positive trend that hovers right at the alpha boundary threshold.
* **Expected AI Behavior:** Strictly classify this as **NOT** statistically significant because $0.051 \ge 0.05$.

```json
{
  "region": "North Atlantic Gyre",
  "period": "2006-2026",
  "trend": {
    "direction": "increasing",
    "p_value": 0.05100,
    "tau": 0.18,
    "slope": 0.012
  }
}
```

---

## 4. Case: Missing/Insufficient Data Gaps
* **Description:** A region with structural spatial/temporal blindspots causing high p-values and near-zero slope.
* **Expected AI Behavior:** Refuse to make sweeping climate generalizations; explicitly reference data constraint values.

```json
{
  "region": "Southern Amazon Sector",
  "period": "2006-2026",
  "trend": {
    "direction": "no trend",
    "p_value": 0.89000,
    "tau": -0.01,
    "slope": 0.000
  }
}
```

---

## 5. Case: Strong Decreasing Trend
* **Description:** Clear negative slope velocity with strong statistical verification.
* **Expected AI Behavior:** State that a statistically significant decreasing trend exists using the negative slope value.

```json
{
  "region": "Tibetan Plateau Ice Fields",
  "period": "2006-2026",
  "trend": {
    "direction": "decreasing",
    "p_value": 0.00200,
    "tau": -0.45,
    "slope": -0.038
  }
}
```
