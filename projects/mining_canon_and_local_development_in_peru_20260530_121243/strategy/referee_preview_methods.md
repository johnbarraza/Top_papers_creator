```json
{
  "code_requirements": [
    {
      "category": "inference",
      "requirement": "Cluster SEs at district level — canon transfers vary at district level, household outcomes correlated within district. Primary clustering unit: ubigeo district code.",
      "priority": "MUST"
    },
    {
      "category": "inference",
      "requirement": "Conley spatial HAC standard errors — proximity-based instrument (deposit proximity × price) induces spatial correlation across neighboring districts. Report both district-clustered and Conley SEs with distance cutoffs at 50km, 100km, 200km.",
      "priority": "MUST"
    },
    {
      "category": "inference",
      "requirement": "Wild cluster bootstrap (Rademacher weights, 9999 replications) IF number of canon-receiving district clusters < 50 in any specification. Verify cluster count before choosing inference method. Use 'wildboottest' package.",
      "priority": "MUST"
    },
    {
      "category": "inference",
      "requirement": "Compute Montiel Olea & Pflueger (2013) effective F-statistic for first stage, NOT raw Cragg-Donald. Report critical values for τ=10% worst-case bias. Threshold: effective F > 23.1 for 10% relative bias tolerance (5% significance).",
      "priority": "MUST"
    },
    {
      "category": "inference",
      "requirement": "Report Anderson-Rubin (1949) weak-instrument-robust confidence intervals for the treatment effect. AR test does not rely on first-stage strength.",
      "priority": "MUST"
    },
    {
      "category": "specification",
      "requirement": "Pre-trend joint F-test for DiD specification: H0 = all pre-treatment period coefficients jointly zero. Report F-statistic, df, p-value. If reject H0, DiD not credible.",
      "priority": "MUST"
    },
    {
      "category": "specification",
      "requirement": "Roth (2022) pre-trend sensitivity: compute δ — the magnitude of differential trend that would overturn the result. Report breakdown point: how large must violation of parallel trends be to nullify the estimated effect?",
      "priority": "MUST"
    },
    {
      "category": "specification",
      "requirement": "Goldsmith-Pinkham et al. (2020) Bartik diagnostics for shift-share instrument (price × proximity). Report: (a) Rotemberg weights, (b) top-5 share districts by Rotemberg weight, (c) just-identified overidentification test (δ=1 elasticity). Check if shares or shocks drive variation.",
      "priority": "MUST"
    },
    {
      "category": "specification",
      "requirement": "First-stage balance test: regress baseline household/district covariates on instrument (price × proximity) to verify instrument is orthogonal to observables. Report standardized mean differences and joint F-test.",
      "priority": "MUST"
    },
    {
      "category": "specification",
      "requirement": "Exclusion restriction argument in code: implement reduced-form of instrument on supply-side outcomes (municipal digital infrastructure spending per MEF function codes). If significant, exclusion violation possible — canon-to-outcome channel may run through public investment, not direct household income.",
      "priority": "MUST"
    },
    {
      "category": "specification",
      "requirement": "McCrary-style density test on canon-receiving threshold (if any eligibility discontinuity): test for manipulation/heaping at canon eligibility or distribution cutoffs.",
      "priority": "SHOULD"
    },
    {
      "category": "specification",
      "requirement": "Monotonicity assessment: verify that higher price×proximity increases canon transfers for all districts (no defiers). Plot first-stage relationship by district subgroup; test for sign flips.",
      "priority": "MUST"
    },
    {
      "category": "robustness",
      "requirement": "Report OLS, reduced-form (Y ~ Z), first-stage (D ~ Z), and 2SLS (Y ~ D_hat | Z) in single table. Every specification must show all four. Never report 2SLS without reduced-form.",
      "priority": "MUST"
    },
    {
      "category": "robustness",
      "requirement": "Intensity outcomes alongside binary adoption: (a) monthly transaction count, (b) transaction volume in PEN, (c) digital share of total expenditures, (d) number of digital financial products used. Binary adoption ceiling masks intensive margin effects in already-high-adoption areas.",
      "priority": "MUST"
    },
    {
      "category": "robustness",
      "requirement": "Alternative distance measures for proximity instrument: (a) straight-line distance, (b) road-network distance, (c) travel time (if GIS data available). Show first-stage strength across all three.",
      "priority": "SHOULD"
    },
    {
      "category": "robustness",
      "requirement": "Supply-side channel test: instrument → (a) MEF municipal spending on digital infrastructure (function codes 0106 Telecomunicaciones, 0052 Tecnologías de Información), (b) SBS fintech agent/corresponsal density per 100k population. Mediation analysis to assess exclusion restriction plausibility.",
      "priority": "MUST"
    },
    {
      "category": "robustness",
      "requirement": "K-fold jackknife instrument: leave out one commodity at a time; recompute price index. Show results stable across commodity composition. Addresses concern that single mineral (copper) drives all variation.",
      "priority": "SHOULD"
    },
    {
      "category": "robustness",
      "requirement": "Donut-hole specification: exclude households within 5km, 10km, 25km of mining deposits — test whether proximity channel operates through direct mining employment/income rather than canon fiscal transfers.",
      "priority": "SHOULD"
    },
    {
      "category": "robustness",
      "requirement": "Subsample analysis: (a) canon-receiving districts only (intensive margin of canon amount), (b) non-canon districts only (test for spillovers), (c) urban vs rural households within district.",
      "priority": "SHOULD"
    },
    {
      "category": "robustness",
      "requirement": "Alternative commodity price indices: (a) equal-weighted, (b) production-value-weighted, (c) PCA first principal component of price series. First-stage stability check.",
      "priority": "SHOULD"
    },
    {
      "category": "presentation",
      "requirement": "Main table must include for each specification: coefficient, SE (cluster-robust), Conley SE, t-statistic, 95% CI, N observations, N clusters, first-stage effective F (Montiel Olea-Pflueger), Kleibergen-Paap LM p-value, AR weak-IV-robust p-value, R² (first stage), R² (second stage), Cragg-Donald Wald F (for comparison).",
      "priority": "MUST"
    },
    {
      "category": "presentation",
      "requirement": "First-stage visualization: binned scatterplot of instrument (price×proximity) vs canon transfers with 20 equal-frequency bins, linear fit, and 95% CI. Annotate with effective F-statistic and partial R².",
      "priority": "MUST"
    },
    {
      "category": "presentation",
      "requirement": "Event-study plot for DiD specification: coefficient estimates and 95% CI for each period relative to treatment (canon shock). Vertical line at t=0. Pre-period coefficients must include joint F-test result annotation. Separate panel for each outcome.",
      "priority": "MUST"
    },
    {
      "category": "presentation",
      "requirement": "Complier characterization table: compare complier-weighted mean of covariates (using Abadie 2003 kappa-weighting) to full sample means. Report differences in income, education, urban/rural, prior financial access, phone ownership, internet access. LATE interpretation requires this.",
      "priority": "MUST"
    },
    {
      "category": "presentation",
      "requirement": "Correlogram or variogram of outcome residuals by spatial distance to justify Conley SE bandwidth choice. Show spatial autocorrelation decays by ~200km in Peruvian context.",
      "priority": "SHOULD"
    },
    {
      "category": "pitfall",
      "requirement": "DO NOT use cross-sectional distance-to-mine as instrument. Endogenous: mining firms locate near infrastructure, skilled labor, and existing economic activity. Distance correlated with omitted variables (urbanization, road access, historical development). Validation explicitly rejects this design.",
      "priority": "MUST"
    },
    {
      "category": "pitfall",
      "requirement": "DO NOT use raw commodity price as sole instrument without proximity interaction. Price common to all districts — no cross-sectional variation. Interaction (price × baseline proximity) generates variation but introduces Bartik/shift-share concerns.",
      "priority": "MUST"
    },
    {
      "category": "pitfall",
      "requirement": "DO NOT report only cluster-robust SEs without Conley spatial SEs when instrument uses geographic proximity. Spatial correlation in proximity-based instruments violates independence across clusters assumption. Kelly (2019) shows this inflates t-statistics.",
      "priority": "MUST"
    },
    {
      "category": "pitfall",
      "requirement": "DO NOT claim ATE (average treatment effect). This is LATE (local average treatment effect) for compliers: districts whose canon transfers respond to price×proximity shocks. Generalizability requires complier characterization and explicit bounds on external validity.",
      "priority": "MUST"
    },
    {
      "category": "pitfall",
      "requirement": "DO NOT pool canon-receiving and non-canon districts without testing for differential first-stage. If price×proximity has zero first-stage in non-mining districts, they contribute nothing to identification and inflate SEs. Consider limiting sample to districts with positive baseline deposit exposure.",
      "priority": "MUST"
    },
    {
      "category": "pitfall",
      "requirement": "DO NOT use standard errors clustered at household level. Canon variation is at district level. Household-level clustering is anti-conservative (Moulton 1990). Minimum defensible clustering: district. Also consider province-level clustering for robustness (196 provinces).",
      "priority": "MUST"
    },
    {
      "category": "pitfall",
      "requirement": "DO NOT omit the no-anticipation test. Households in canon-expectant districts may adjust digital wallet adoption before canon disbursement. Test leads (t-1, t-2 periods) for significance. If significant, redefine treatment timing.",
      "priority": "MUST"
    },
    {
      "category": "specification",
      "requirement": "Placebo outcome test: regress instrument on outcomes that should NOT respond to canon — (a) household religion, (b) indigenous language status, (c) dwelling construction material (pre-determined). Any significant effect suggests instrument not exogenous.",
      "priority": "MUST"
    },
    {
      "category": "specification",
      "requirement": "Placebo treatment timing: shift canon shock 2 periods earlier and rerun DiD. Insignificant placebo treatment effect supports validity.",
      "priority": "MUST"
    },
    {
      "category": "robustness",
      "requirement": "Power analysis BEFORE full execution: simulate minimum detectable effect given (a) ~200-300 treated district clusters, (b) expected within-district ICC, (c) expected first-stage partial R². Report MDES in SD units. If MDES > 0.15σ, design underpowered for plausible canon effects on digital adoption.",
      "priority": "MUST"
    },
    {
      "category": "specification",
      "requirement": "Stable unit composition: document entry/exit of households in panel. Report attrition rate by treatment status. If attrition > 5% differential, implement Lee (2009) bounds.",
      "priority": "SHOULD"
    },
    {
      "category": "robustness",
      "requirement": "Report effect sizes in interpretable units: (a) percentage point change in adoption probability, (b) SD change in transaction volume, (c) PEN change in monthly digital expenditure. Compare to mean outcome level. Flag any effect > 1 SD as implausibly large.",
      "priority": "MUST"
    },
    {
      "category": "robustness",
      "requirement": "Benchmark against prior literature: compare estimated canon-income pass-through to Correa et al. and Aragón & Rud estimates. Compare digital adoption elasticity to Jack & Suri mobile money findings. Large deviations require explicit discussion.",
      "priority": "SHOULD"
    },
    {
      "category": "presentation",
      "requirement": "Pre-commit to all specifications, placebo tests, and outcomes in pre-analysis plan BEFORE any regression output is examined. Register on OSF or AsPredicted. Cite registration in paper.",
      "priority": "MUST"
    }
  ],
  "method_warnings": [
    "Original cross-sectional distance IV explicitly rejected by validation. If code retains this specification, label it 'discredited baseline — included for reviewer reference only' and do not interpret causally.",
    "Bartik/shift-share instrument (price × proximity) inherits Goldsmith-Pinkham critique. If price variation is low-dimensional (e.g., copper dominates Peru's mineral exports), instrument collapses to proximity-weighted single shock. Report Adão et al. (2019) standard errors for shift-share designs.",
    "District-level canon disbursement rules depend on production value AND fiscal redistribution formulas (canon minero = 50% of income tax from mining). Redistribution formula (Ley de Canon) allocates across regional/local governments by complex rules — instrument must isolate exogenous variation net of formula-determined allocation.",
    "Only ~200-300 of ~1,874 Peruvian districts receive canon. Statistical power concentrated in small treated subset. Weak instrument likely if price×proximity has low variation within this subset. Report first-stage separately for canon-positive sample.",
    "Digital wallet data (SBS/BCRP billeteras digitales) may suffer from non-random measurement: fintech reporting requirements differ from traditional banking. If ENAHO survey data is primary source, verify digital wallet question wording is consistent across survey waves.",
    "Conley SE implementation requires arbitrary bandwidth choice. Pre-commit to bandwidth selection rule: (a) distance at which spatial autocorrelation of residuals falls below 0.05, or (b) 200km based on Peruvian district size distribution. Report sensitivity to 50-300km range.",
    "Pre-registration is essential: competition risk noted in validation. Without pre-analysis plan, results may be interpreted as specification mining. Pre-commit to one primary specification, all tests, and all outcomes before touching data."
  ],
  "must_not_claim": [
    "ATE (average treatment effect) — IV identifies LATE for complier districts. Do not claim results generalize to non-canon-receiving districts or districts where canon does not respond to price×proximity.",
    "Causal effect of digital wallets on financial inclusion — this design estimates effect of canon transfers (fiscal windfall) on digital adoption. It does not identify the causal effect of digital wallets themselves on downstream outcomes.",
    "Exclusion restriction is 'plausibly satisfied' without testing supply-side channel — validation mandates testing whether canon → municipal digital infrastructure spending, which would violate exclusion if infrastructure spending independently affects digital adoption.",
    "Distance to mine is exogenous — this is the rejected original design. Mining location is endogenous to local economic geography, infrastructure, and labor markets.",
    "Standard TWFE is sufficient — if panel data reveals staggered canon shocks across districts (e.g., new mining projects starting at different times), Sun & Abraham (2021) or Callaway & Sant'Anna (2021) estimators are required, not standard TWFE.",
    "Results are robust without Conley SEs — spatial correlation in proximity-based instruments is well-documented (Kelly 2019). Non-spatial SEs likely over-reject the null."
  ]
}
```