```json
{
  "topic": "Mining Canon and Local Development in Peru",
  "data_profile": {
    "rows": 117721,
    "cols": 27,
    "structure": "cross-sectional",
    "panel": false,
    "id_cols": ["CONGLOME", "VIVIENDA", "HOGAR", "CODPERSO", "UBIGEO"],
    "time_cols": [],
    "warnings": [
      "No mining canon variable in dataset — must merge via UBIGEO (district) from external source (MEF canon transfers)",
      "27% missing in OCUPADO, 18% in TIENE* vars, 9% in NIVEL_EDUCATIVO — check missingness mechanism",
      "Single cross-section blocks DiD, panel FE, event study — no temporal variation",
      "FACTOR_EXPANSION present — must use survey weights for population inference",
      "POBREZA only 3 ordinal levels (1-3) — limited granularity for welfare analysis",
      "GENERO, EDAD have 3% missing — likely children in roster, verify coding"
    ],
    "recommended_methods": [
      "IV/2SLS — instrument mining canon with intl commodity price × historical mine presence (Bartik-style), use FACTOR_EXPANSION",
      "Spatial RDD — compare outcomes across district borders where canon regime changes discontinuously",
      "Matching (PSM/CEM) — match mining-receiving vs non-receiving districts on pre-treatment covariates, then compare outcomes",
      "Oaxaca-Blinder decomposition — decompose outcome gaps (financial inclusion, income, poverty) between mining vs non-mining regions",
      "Quantile regression — canon effects at bottom vs top of INGRESO_PC or GASHOG2D distribution",
      "LASSO for variable selection — select controls from 27 vars + polynomial/spatial terms for IV first stage or matching propensity score",
      "Heckman selection model — correct for selection into OCUPADO if analyzing labor outcomes (wages, formality)",
      "Robustness: falsification test on non-treatment-eligible outcomes (e.g., canon should not affect coastal districts)"
    ],
    "merge_needed": [
      "Mining canon transfers per capita (MEF — DATASS or SIAF) by UBIGEO/year",
      "Mine production/site data (MINEM) by district",
      "Historical mining presence (pre-2000) for Bartik instrument construction",
      "District-level poverty/FONIPREL eligibility threshold if RDD feasible"
    ]
  }
}
```