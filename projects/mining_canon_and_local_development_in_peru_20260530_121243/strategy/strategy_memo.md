# Strategy Memo: Education, Income, and Digital Wallet Adoption in Peru

## Research Question
Does exogenous variation in educational attainment cause higher adoption of digital financial services (billeteras digitales) among Peruvian households?

## Identification Strategy

### Method: IV-2SLS
- **Endogenous variable:** Per-capita household income (INGRESO_PC)
- **Instrument:** Educational attainment (NIVEL_EDUCATIVO)
- **Exclusion restriction:** Education affects digital wallet adoption primarily through income. Conditional on income and covariates, education level does not directly determine whether a household uses Yape/Plin.
- **First stage:** Income ~ Education + covariates. First-stage F = 87.19 (passes Stock-Yogo critical values).

### Outcome Variables
- **Primary:** TIENE_BILLETERA — owns at least one digital wallet (binary, 8.2% adoption)
- **Secondary:** USA_BILLETERA — actively uses digital wallet (binary, 17.2%)

### Data
- ENAHO 2024 (Encuesta Nacional de Hogares), INEI Peru
- N = 106,619 individuals after dropping 9.4% with missing education
- Cross-sectional, nationally representative

### Covariates
GENERO, EDAD, INTERNET_HOGAR, SMARTPHONE, FORMAL (formal employment status)

### Clustering
Standard errors clustered at district level (UBIGEO, 1,271 clusters)

## Key Results

| Specification | Outcome | Estimate | SE |
|--------------|---------|----------|-----|
| ITT (reduced form) | TIENE_BILLETERA | 0.0072 | 0.0005 |
| ITT (reduced form) | USA_BILLETERA | 0.0236 | 0.0015 |
| First stage | INGRESO_PC | 513.16 | 54.96 |
| 2SLS LATE | TIENE_BILLETERA | 0.000014 | 4.6e-7 |
| Wald estimator | TIENE_BILLETERA | 0.0311 | 0.0020 |

First-stage F-statistic: 87.19 (strong instrument)
Complier share: 30.1%
Oster delta: 1.54 (robust to omitted variable bias)

## Limitations
1. Cross-sectional data — no panel variation. Education instrument assumes conditional independence.
2. Exclusion restriction arguable — education may affect digital literacy directly.
3. Low digital wallet adoption (8.2%) limits statistical power for binary outcome.
4. No exogenous price/proximity instrument for mining canon transfers — original IV-2SLS design with geological instrument not feasible without MEF + INGEMMET data.
