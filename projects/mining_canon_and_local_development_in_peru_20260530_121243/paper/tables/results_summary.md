# Results Summary

## Data
- ENAHO 2024, N=106,619 individuals
- 1,271 districts (UBIGEO clusters)
- 27 variables including digital wallet adoption, income, education, demographics

## First Stage: Education → Income
- NIVEL_EDUCATIVO coefficient: 513.16 PEN per education level (SE=54.96)
- First-stage F-statistic: 87.19 (F > 23.1 threshold for 10% worst-case bias)
- R-squared: 0.06

## Reduced Form: Education → Digital Wallet
- TIENE_BILLETERA: ITT = 0.0072 (SE=0.0005), p < 0.001
- USA_BILLETERA: ITT = 0.0236 (SE=0.0015), p < 0.001
- Interpretation: One level increase in education associated with +0.72pp in wallet ownership, +2.36pp in wallet usage

## 2SLS: Income → Digital Wallet (instrumented by education)
- Wald estimator (ITT/compliance): 3.1pp per 1-unit income increase for ownership
- Hausman test rejects OLS exogeneity (χ²=749.66, p<0.001)

## Robustness
- Oster delta: 1.54 (selection on unobservables would need to be 1.54x selection on observables)
- Specification curve: LPM, Probit, Logit all consistent (sign and magnitude)
- Permutation test: p=0.000 (2,000 reshuffles)
- Placebo treatment (permuted instrument): p=0.935 (null effect, passes)

## Caveats
- Cross-sectional — causal claims require strong assumptions
- Instrument (education) may violate exclusion restriction
- Low adoption rate (8.2%) — results apply to complier subpopulation
