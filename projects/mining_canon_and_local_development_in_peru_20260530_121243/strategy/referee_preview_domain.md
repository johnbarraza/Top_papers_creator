```json
{
  "code_requirements": [
    {
      "category": "estimation",
      "requirement": "IV-2SLS via statsmodels.IV2SLS or linearmodels.IV2SLS with geological mineral potential index as excluded instrument for canon transfers. Report both limited-information (ivreg) and GMM variants. If revised design adopted, use interaction IV (commodity price × baseline deposit proximity) in panel FE specification with district and year FE.",
      "priority": "MUST"
    },
    {
      "category": "estimation",
      "requirement": "First-stage regression: canon_per_capita ~ geological_potential_index + covariates. Report Kleibergen-Paap rk Wald F-statistic AND Montiel Olea-Pflueger effective F-statistic with 5% threshold. Reject instrument as weak if effective F < critical value for τ=10% worst-case bias. Do NOT rely solely on rule-of-thumb F>10.",
      "priority": "MUST"
    },
    {
      "category": "estimation",
      "requirement": "Standard errors clustered at district level (canon assignment unit). If <50 clusters: report wild cluster bootstrap p-values (Cameron-Gelbach-Miller, Rademacher weights, 9999 replications). Also compute Conley spatial HAC standard errors with cutoff distance chosen via variogram inspection of residuals.",
      "priority": "MUST"
    },
    {
      "category": "estimation",
      "requirement": "Reduced-form regression: digital_wallet_outcome ~ geological_potential_index + covariates. Report both ITT estimates and scaled LATE (Wald estimator = reduced-form / first-stage). Bootstrap CI for LATE.",
      "priority": "MUST"
    },
    {
      "category": "estimation",
      "requirement": "Complier characterization: estimate κ-weight for each observation. Regress predicted canon quantile on district observables (population, poverty rate, altitude, road density, indigenous share). Compare complier-weighted means to full-sample and always-taker/never-taker means. Report normalized difference (Imbens-Rubin) for each covariate.",
      "priority": "MUST"
    },
    {
      "category": "robustness",
      "requirement": "Placebo falsification: replace geological potential with random Gaussian noise (same mean/variance), re-estimate 2SLS 1000 times. Plot distribution of placebo coefficients against actual estimate. p-value = share of |placebo| > |actual|. Also: test instrument on pre-2010 outcomes (before billeteras digitales existed) if any historical financial access data available.",
      "priority": "MUST"
    },
    {
      "category": "robustness",
      "requirement": "Leave-one-district-out jackknife: re-estimate 2SLS dropping one canon-receiving district at a time. Plot sorted point estimates with CIs. Flag influence points where Cook's distance > 4/N.",
      "priority": "MUST"
    },
    {
      "category": "robustness",
      "requirement": "Alternative instrument constructions: (a) binary indicator for above-median geological potential, (b) mineral deposit count (not value-weighted), (c) distance to nearest major deposit, (d) geological potential interacted with post-2015 indicator. Report overidentification J-test where multiple instruments used with LIML as comparator.",
      "priority": "SHOULD"
    },
    {
      "category": "robustness",
      "requirement": "Donut-hole/Ring test for spatial spillovers: exclude districts within X km of canon-receiving district borders at 5 km increments up to 50 km. Check if IV coefficient stable. This addresses SUTVA violation concern — digital wallet adoption may spill over from treated to control districts via migration/trade.",
      "priority": "SHOULD"
    },
    {
      "category": "robustness",
      "requirement": "OLS vs IV Hausman endogeneity test (Hausman-Wu). Report Durbin-Wu-Hausman χ² statistic. If fail to reject exogeneity, discuss why OLS may still be biased (attenuation from measurement error in self-reported canon awareness).",
      "priority": "MUST"
    },
    {
      "category": "robustness",
      "requirement": "Alternative outcomes: (a) binary: any digital wallet adoption, (b) intensity: log(1 + monthly transaction count), (c) intensity: digital share of total household financial transactions, (d) extensive margin: number of digital wallet platforms used. If binary outcome, also report IV-Probit as robustness to linear probability model in 2SLS. For intensity outcomes with mass at zero, report two-part model (probit selection + log OLS) with IV in both stages.",
      "priority": "MUST"
    },
    {
      "category": "robustness",
      "requirement": "Sensitivity analysis: if IV-2SLS estimates survive, report Conley-Hansen-Rossi plausibly-exogenous bounds — relax exclusion restriction by δ and compute union of confidence intervals for β across δ ∈ [−δ̄, δ̄] calibrated to first-stage coefficient magnitude.",
      "priority": "NICE"
    },
    {
      "category": "robustness",
      "requirement": "Supply-side mechanism test: estimate canon → municipal spending on digital infrastructure (MEF expenditure function codes) as auxiliary IV outcome. Then estimate fintech agent density (SBS registros de cajeros corresponsales) ~ predicted_canon. Report mediation decomposition (Imai-Keele-Tingley) to separate demand-side vs supply-side channels.",
      "priority": "MUST"
    },
    {
      "category": "robustness",
      "requirement": "Bartik/shift-share diagnostics if revised interaction-IV design adopted: compute Rotemberg weights for each commodity and each baseline-period district (Goldsmith-Pinkham-Sorkin-Yang). Report top-5 Rotemberg-weight commodities. Test pre-trends by interacting commodity prices with lagged (not baseline) deposit proximity.",
      "priority": "MUST"
    },
    {
      "category": "construction",
      "requirement": "Geological mineral potential index: principal component of (a) number of known mineral deposits within district, (b) total estimated ore tonnage, (c) deposit type diversity (porphyry, epithermal, skarn, etc.), (d) geological age diversity. Normalize PC scores to mean 0, SD 1. Document eigenvalue share of PC1. If PC1 explains < 60% of variance, report alternative: simple sum of z-scored components.",
      "priority": "MUST"
    },
    {
      "category": "construction",
      "requirement": "Canon transfer variable: use SBS/MEF administrative records (not self-reported). Construct canon_per_capita = total_district_canon / district_population (INEI census or projections). Flag districts where canon = 0 but mineral deposits exist (potential measurement error — check if mining in neighboring district spills canon). Winsorize at 99th percentile.",
      "priority": "MUST"
    },
    {
      "category": "construction",
      "requirement": "Digital wallet outcome: use ENAHO financial inclusion module or SBS demanda de servicios financieros survey. Define adoption = self-reported use of any billetera digital (Yape, Plin, BIM, AgoraPay, Tunki) in past 30 days. Construct intensity from transaction count/frequency question if available. Handle missing/refused responses with indicator variables and mean imputation as robustness.",
      "priority": "MUST"
    },
    {
      "category": "construction",
      "requirement": "Covariate set must include: household size, female head indicator, head education (years), head age (quadratic), log household income (excl. canon), urban/rural indicator, district poverty rate (INEI), district cell coverage (OSIPTEL PUNKU), district bank branch count, district altitude, district road density. Do NOT condition on post-treatment variables (no fintech agent density in main IV specification — it's a mechanism, not a control).",
      "priority": "MUST"
    },
    {
      "category": "construction",
      "requirement": "Spatial merge: assign households to districts via ubigeo code. If household GPS coordinates available, compute distance to nearest mineral deposit (in km, log) as alternative instrument. For Conley SEs, compute pairwise distance matrix across district centroids. Flag districts closer than 10 km to each other for clustering sensitivity.",
      "priority": "MUST"
    },
    {
      "category": "construction",
      "requirement": "Panel construction if revised design adopted: merge ENAHO cross-sections 2015-2023 by household panel identifier. Use repeated cross-section if true panel unavailable. Canon data at district-year level from MEF Consulta Amigable. Commodity price series from BCRP or World Bank Pink Sheet (monthly → annual average). Baseline deposit proximity frozen at 2014 values.",
      "priority": "SHOULD"
    },
    {
      "category": "pitfall",
      "requirement": "Zero-inflation handler: ~94% of districts (~1,674 of ~1,874) receive zero canon. Code must check for complete separation in probit/LPM first stage. Use Firth penalized likelihood or bayesglm if IV-probit fails to converge. Report share of observations with predicted canon = 0 from first stage.",
      "priority": "MUST"
    },
    {
      "category": "pitfall",
      "requirement": "Ceiling effect detector: compute digital wallet adoption rate for top income quintile. If > 85%, intensity outcomes essential — binary outcome loses variation at top. Code must test for heteroskedasticity related to predicted adoption probability (score test, Breusch-Pagan variant for binary outcomes).",
      "priority": "MUST"
    },
    {
      "category": "pitfall",
      "requirement": "Weak instrument power analysis: simulate 2SLS with varying first-stage R² (0.01–0.20) and sample sizes of canon-receiving districts (50–300). Report minimum detectable effect in Cohen's d units at 80% power. If MDE > plausible effect size (e.g., 0.15 SD), STOP and flag as underpowered — do not proceed to 2SLS without caveat.",
      "priority": "MUST"
    },
    {
      "category": "pitfall",
      "requirement": "Multiple hypothesis correction: 4 outcome variables × 3 instrument variants × 2 subsamples = 24 tests minimum. Report both raw p-values and Westfall-Young stepdown adjusted q-values (bootstrap, 9999 reps) or Holm-Bonferroni at minimum. Define primary outcome, primary instrument, and full sample as pre-registered specification.",
      "priority": "SHOULD"
    },
    {
      "category": "pitfall",
      "requirement": "Missing data audit: for each variable, report N, mean, SD, min, p10, p50, p90, max, and N missing. If any variable > 5% missing, compare complete-case estimates to MI estimates (chained equations, 20 imputations). Code must NOT silently drop rows with missing values — log how many rows lost at each step.",
      "priority": "MUST"
    },
    {
      "category": "pitfall",
      "requirement": "Pre-registration commitment: write analysis plan as YAML/JSON specifying primary outcome, primary instrument, covariate set, SE method, subsamples, and robustness checks. Compute hash and timestamp. All exploratory specifications must be labeled 'exploratory: not pre-registered' in output tables. Script must read this file and auto-label outputs.",
      "priority": "MUST"
    }
  ],
  "data_warnings": [
    "Only ~200-300 of ~1,874 districts receive canon → first stage identified off <16% of clusters. Cluster-robust SEs with so few treated clusters may be severely downward-biased. Wild bootstrap mandatory.",
    "Geological potential is time-invariant → IV identifies cross-sectional variation only. Cannot control for district FE. All unobserved district confounders (historical mining infrastructure, colonial roads, NGO presence) threaten exclusion restriction. Need explicit argument for why these don't affect digital wallet adoption through non-canon channels.",
    "Zero canon in ~89% of districts → first stage may be weak even if geological potential strongly predicts non-zero canon among mining districts. Check Tobit-type first stage — if instrument predicts extensive margin (any canon) but not intensive margin (amount), LATE interpretation strained.",
    "Digital wallet adoption likely has strong network effects (Yape adoption concentrated in Banco de Crédito customer base). SUTVA likely violated — adoption in control districts may depend on adoption in nearby treated districts. Donut-hole robustness essential.",
    "ENAHO financial inclusion questions may vary across survey waves. Verify question wording is identical across all waves used. If not, document differences and test for question-wording effects.",
    "Mining canon distribution formula changed in 2011 (Ley 29788) and 2018 — check if geological potential predicts canon differently pre/post reform. Structural break in first stage threatens instrument validity.",
    "Commodity price × deposit proximity instrument (if revised design) inherits Bartik critique: Rotemberg weight on a single commodity (copper) may dominate (>60%). Report weight distribution.",
    "Billeteras digitales usage may be measured with error if households report agent-assisted transactions as own use (common for BIM with older/less-educated users). Differential measurement error by education/SES may bias IV estimates.",
    "Canon transfers may be endogenous to local political pressure/competition — districts with more organized civil society may both attract more canon (through lobbying) and promote digital literacy programs. Geological IV addresses this only if geological potential is truly orthogonal to local political organization.",
    "Power likely low: 200 treated clusters × modest first-stage R² × binary outcome → MDE probably 0.2–0.3 SD. If true effect smaller, study will be uninformative (wide CIs), not null. Code must distinguish 'no evidence of effect' from 'evidence of no effect' via equivalence testing."
  ],
  "tables_required": [
    "Table 1: Summary statistics — full sample, canon-receiving districts, non-canon districts, complier-weighted means. Columns for N, mean, SD, min, max, and normalized difference (canon vs non-canon). Include all outcomes, instrument, canon, and covariates.",
    "Table 2: First-stage results — canon_per_capita ~ geological_potential + covariates. Columns: (1) bivariate, (2) + household controls, (3) + district controls, (4) province FE. Report coefficient, robust SE, cluster-robust SE, Conley SE. Report KP rk Wald F, MOP effective F, first-stage R², partial R², Shea partial R².",
    "Table 3: IV-2SLS main results for each outcome. Panel A: binary adoption. Panel B: transaction intensity. Panel C: digital share. Panel D: platform count. Each panel: (1) OLS, (2) reduced-form, (3) 2SLS, (4) 2SLS + province FE, (5) LIML. Report β, cluster SE, wild bootstrap p-value, Conley SE, N, number of clusters. Bold primary pre-registered specification.",
    "Table 4: Robustness — alternative instruments. Columns for each instrument variant. Rows for each outcome. Report 2SLS coefficient, cluster SE, first-stage F, overidentification J p-value (where identified). Bottom panel: leave-one-out bounds (min, max estimate across jackknife).",
    "Table 5: Complier characteristics. Columns: complier mean (κ-weighted), full sample mean, normalized difference. Rows: all baseline covariates. Bottom: Wald test for joint orthogonality of complier vs full sample characteristics.",
    "Table 6: Placebo falsification. Placebo coefficient mean, SD, share |placebo| > |actual|, 95th percentile of placebo distribution. One row per outcome.",
    "Table 7: Supply-side mechanism — canon → municipal digital infrastructure spending and fintech agent density. First stage for spending outcome, reduced form, 2SLS. Mediation decomposition with bootstrapped CIs.",
    "Table 8: Sensitivity — Conley-Hansen-Rossi bounds. For δ̄ ∈ {0.001, 0.005, 0.01, 0.02} × first-stage coefficient, report union of CIs for β. If union excludes zero at δ̄ ≥ 0.01 × first stage, instrument robust to plausible direct effects.",
    "Table A1: Variable definitions and sources — variable name, definition, source dataset, years, access URL/DOI.",
    "Table A2: Missing data patterns — variable, N missing, % missing, comparison of observed vs missing on key outcomes.",
    "Table A3: Full regression output for all robustness checks not in main tables."
  ],
  "figures_required": [
    "Figure 1: Map of Peru at district level — color by geological mineral potential index (continuous), overlay canon-receiving districts with hatching. Include Lima callout.",
    "Figure 2: First-stage binned scatterplot — residualized canon_per_capita (y-axis) vs residualized geological potential (x-axis), 20 equal-frequency bins, with OLS fit line and 95% CI. Label axes with 'conditional on covariates'.",
    "Figure 3: Coefficient plot — point estimates and 95% CIs for all IV specifications (main + alternative instruments) across all outcomes. Vertical line at zero. Pre-registered specification in solid red, exploratory in dashed gray.",
    "Figure 4: Placebo distribution histogram — 1000 placebo IV coefficients with actual estimate as vertical red line. One panel per outcome. Annotation with randomization-inference p-value.",
    "Figure 5: Leave-one-out influence plot — sorted district names on x-axis, 2SLS coefficient on y-axis with 95% CI. Horizontal band for full-sample estimate ± 1.96 SE. Flag districts where exclusion changes significance.",
    "Figure 6: Donut-hole sensitivity — x-axis: exclusion radius (0-50 km), y-axis: 2SLS coefficient with 95% CI. Vertical line at 0 km (full sample). Horizontal line at zero.",
    "Figure 7: Complier overlap — kernel density plots of geological potential for canon-receiving vs non-receiving districts. Vertical lines at 10th and 90th percentile of canon-district distribution (common support region).",
    "Figure 8: Moran scatterplot — district-level reduced-form residuals (y-axis) vs spatial lag of residuals (x-axis). Report Moran's I statistic and permutation p-value. If I > 0.2, Conley SEs essential.",
    "Figure 9: Power curves — x-axis: true effect size (Cohen's d, 0 to 0.5), y-axis: power. Separate lines for N=100, 200, 300 treated clusters. Horizontal line at 0.80. Annotation: MDE for each N.",
    "Figure 10 (if revised panel design): Event-study/DiD coefficient plot — year relative to canon shock on x-axis, DiD coefficient on y-axis with 95% CI. Pre-period coefficients should be near zero. Include joint F-test of pre-trends p-value."
  ]
}
```