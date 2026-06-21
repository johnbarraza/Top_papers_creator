# Research Landscape: Mining Canon & Local Development in Peru

## Key Themes, Methods & Gaps

**Theme 1 — Fiscal transfers & poverty.** Bulk of literature uses panel DiD comparing canon-receiving to non-receiving districts. Finds modest poverty reduction (d ≈ 0.1–0.2 SD), concentrated in urban areas. Gap: *household-level mechanisms* — who within treated districts actually benefits?

**Theme 2 — Financial inclusion.** Emerging literature on whether canon windfalls accelerate formal banking adoption. Almost no work on *digital* financial inclusion (billeteras digitales). Peru has 70%+ smartphone penetration. Timely gap.

**Theme 3 — Labor market distortions.** Mixed evidence on "Dutch disease at local level" — canon transfers may reduce formal labor supply via income effects. Gap: *gender-differentiated* labor responses. Women may exit formality at different rates.

**Theme 4 — Human capital.** Canon earmarked for education infrastructure. Studies find weak translation from spending to outcomes. Gap: *within-household* educational spillovers (do siblings of canon beneficiaries get more education?).

**Theme 5 — Digital divide.** Mining districts often remote. Does canon close the internet/smartphone gap? No papers study this. Gap: canon as a tool for bridging digital infrastructure inequality.

**Theme 6 — Absorption capacity heterogeneity.** Some districts convert canon into development; others waste it. Existing work uses cross-district regressions. Gap: *household-level heterogeneity* in who captures benefits conditional on district-level absorption quality.

**Methodological gap:** Most papers use district-level panel DiD. Few exploit household-level variation WITHIN treated districts. This dataset's 117K household observations enables within-district heterogeneity analysis that aggregate studies miss.

---

## 8 Research Ideas

### Idea 1: Geological IV — Mining Canon and Digital Wallet Adoption

**Research question:** Does exposure to mining canon transfers cause higher adoption of digital wallets (billeteras digitales) among rural households?

**Method:** IV-2SLS. Instrument: geological mineral deposit proximity × historical mining district status (pre-1990, before canon system existed). First stage: canon exposure → actual canon receipts at district level (merged via UBIGEO). Second stage: canon receipts → TIENE_BILLETERA / USA_BILLETERA.

**Identification level:** A. Geological endowments are exogenous to current household financial behavior. Exclusion restriction: mineral geology only affects digital wallet adoption through canon transfers (threat: geology may correlate with other economic geography).

**Data needed:** (1) Geological mineral deposit maps (INGEMMET public data), (2) District-level canon transfer amounts 2015–2023 (MEF Consulta Amigable), (3) Historical mining district classification pre-1990.

**Novelty:** First paper linking canon to *digital* financial inclusion. No existing study.

**Sub-topic:** Financial inclusion / digital finance

| N | F | I | ID | EE | Total |
|---|---|---|---|---|---|
| 5 | 4 | 5 | 4 | 4 | **4.30** |

---

### Idea 2: RDD — Mining District Boundary and Poverty

**Research question:** Does living just inside vs. just outside a mining-canon-receiving district border reduce household poverty (POBREZA)?

**Method:** Spatial regression discontinuity. Running variable: distance to district border (positive = inside canon-receiving district, negative = outside). Outcome: POBREZA (binary), INGHOG2D (continuous). Uses geographic coordinates merged from UBIGEO.

**Identification level:** A. District boundaries are administrative artifacts — households just on either side are similar except for canon treatment. Threat: boundaries may correlate with other administrative differences (municipal capacity).

**Data needed:** (1) District boundary shapefiles (INEI/IGN), (2) GPS coordinates of survey clusters (CONGLOME), (3) District-level canon classification.

**Novelty:** Spatial RDD never applied to Peru mining canon. Bypasses endogeneity of which districts have mines.

**Sub-topic:** Poverty / fiscal transfers

| N | F | I | ID | EE | Total |
|---|---|---|---|---|---|
| 5 | 4 | 5 | 4 | 4 | **4.30** |

---

### Idea 3: Dose-Response PSM — Canon Intensity and Formal Employment by Gender

**Research question:** Does the *intensity* of district-level canon transfers affect formal employment (FORMAL) differently for men and women?

**Method:** Generalized propensity score (dose-response) with continuous treatment. Treatment intensity: per-capita canon transfers at district level (merged via UBIGEO). Outcomes: FORMAL (binary) and OCUPADO (binary). Heterogeneity by GENERO.

**Identification level:** B. Treatment is continuous canon intensity — all districts get *some* transfers, but dose varies. Selection on observables assumption. Pre-treatment covariates: EDAD, NIVEL_EDUCATIVO, ESTRATO, DOMINIO, MIEPERHO.

**Data needed:** (1) District-level canon transfer amounts per capita (MEF), (2) District population (INEI).

**Novelty:** Gender heterogeneity in canon labor effects unexplored. Dose-response avoids binary treatment oversimplification.

**Sub-topic:** Labor markets / gender

| N | F | I | ID | EE | Total |
|---|---|---|---|---|---|
| 4 | 5 | 4 | 3 | 3 | **3.60** |

---

### Idea 4: Oaxaca-Blinder — Digital Divide Decomposition in Mining vs. Non-Mining Regions

**Research question:** How much of the digital access gap (INTERNET_HOGAR, SMARTPHONE) between mining and non-mining districts is explained by household characteristics vs. structural differences (returns to those characteristics)?

**Method:** Oaxaca-Blinder decomposition. Group 1: households in canon-receiving districts. Group 2: households in non-canon districts. Decompose gap into "endowment effect" (differences in education, income, urbanness) vs. "coefficient effect" (differences in returns — capturing infrastructure/structural differences potentially caused by canon).

**Identification level:** B. Descriptive decomposition, not causal. But the "coefficient effect" has a structural interpretation: if identical households face different returns in mining areas, this suggests infrastructure/access differences attributable to canon.

**Data needed:** District-level canon classification (binary or continuous).

**Novelty:** First decomposition of digital divide in Peru through mining canon lens.

**Sub-topic:** Digital divide / infrastructure

| N | F | I | ID | EE | Total |
|---|---|---|---|---|---|
| 4 | 5 | 4 | 2 | 4 | **3.55** |

---

### Idea 5: Quantile IV — Mining Canon and the Income Distribution

**Research question:** Does mining canon have heterogeneous effects across the household income distribution within treated districts?

**Method:** Instrumental variable quantile regression. Instrument: geological mining potential (as in Idea 1). Outcome: INGHOG2D. Examine whether canon effects concentrate at top, middle, or bottom of income distribution. Uses FACTOR_EXPANSION for nationally representative estimates.

**Identification level:** A (same IV as Idea 1). Geological instrument. Key contribution: moves beyond mean effects to distributional effects — canon literature overwhelmingly reports means.

**Data needed:** Same as Idea 1 + district-level canon amounts.

**Novelty:** Distributional effects of canon largely unstudied. Policy-relevant for understanding who actually captures canon benefits.

**Sub-topic:** Inequality / distributional effects

| N | F | I | ID | EE | Total |
|---|---|---|---|---|---|
| 5 | 4 | 5 | 4 | 3 | **4.10** |

---

### Idea 6: Heckman Selection — Household Labor Supply Response to Canon

**Research question:** Does canon exposure affect the *selection* into employment (extensive margin) and conditional wages (intensive margin) differently?

**Method:** Heckman two-step selection model. Selection equation: OCUPADO ~ canon_exposure + demographics + household composition. Outcome equation: log(INGHOG2D) ~ canon_exposure + education + controls + inverse Mills ratio.

**Identification level:** B. Selection model relies on exclusion restriction — variables in selection equation but not outcome equation (household dependency ratio MIEPERHO, presence of elderly). Canon exposure identifies via geographic variation.

**Data needed:** District-level canon data (same as above).

**Novelty:** Canon labor literature focuses on employment rates, not selection-corrected wage effects. Heckscher-Ohlin intuition: canon windfall may reduce labor supply via income effect.

**Sub-topic:** Labor markets

| N | F | I | ID | EE | Total |
|---|---|---|---|---|---|
| 3 | 4 | 4 | 3 | 4 | **3.55** |

---

### Idea 7: CEM + Heterogeneity — Absorption Capacity and Education Outcomes

**Research question:** Does the effect of canon on household education levels (NIVEL_EDUCATIVO) vary by district-level institutional quality (absorption capacity)?

**Method:** Coarsened exact matching (CEM) on pretreatment covariates, then heterogeneity analysis by tercile of district absorption capacity (external proxy: municipal budget execution rate). Matched pairs: canon-exposed vs. non-exposed households within same ESTRATO × DOMINIO strata.

**Identification level:** B. CEM improves balance over PSM. Heterogeneity by absorption capacity tests a specific mechanism — canon only works where institutions work. Still selection on observables.

**Data needed:** (1) Municipal budget execution rates (MEF), (2) District-level canon data, (3) District human development indicators (PNUD Perú).

**Novelty:** Mechanism-focused. "Canon works, but only where institutions work" is a policy-relevant refinement of the canon literature.

**Sub-topic:** Human capital / governance

| N | F | I | ID | EE | Total |
|---|---|---|---|---|---|
| 5 | 4 | 5 | 3 | 4 | **3.90** |

---

### Idea 8: IV — Mining Canon, Smartphone Access, and Financial Inclusion Mediation

**Research question:** Does smartphone ownership (SMARTPHONE) mediate the effect of mining canon on digital wallet usage (USA_BILLETERA)?

**Method:** IV mediation analysis. Instrument: geological mining potential → canon exposure → SMARTPHONE (mediator) → USA_BILLETERA (outcome). Estimate direct effect (canon → wallet, not through phone) vs. indirect effect (canon → phone → wallet). Uses Imai et al. (2010) or Dippel et al. (2020) mediation framework with IV.

**Identification level:** A for total effect; B for decomposition. Mediation requires sequential ignorability — canon must not affect wallet usage through channels other than smartphone. Threat: canon also increases banking infrastructure directly.

**Data needed:** Same as Idea 1 + Idea 7.

**Novelty:** Causal mediation of fintech adoption never applied to resource transfer contexts.

**Sub-topic:** Digital finance / causal mechanisms

| N | F | I | ID | EE | Total |
|---|---|---|---|---|---|
| 5 | 3 | 4 | 3 | 3 | **3.35** |

---

### Idea 9: Propensity Score Matching — Mining Canon and Household Banking Behavior

**Research question:** Does living in a canon-receiving district increase the probability of having a prior bank account (BANCO_PREVIO), controlling for observables?

**Method:** PSM with nearest-neighbor matching and caliper. Treatment: household in a district receiving above-median per-capita canon. Outcomes: BANCO_PREVIO, TIENE_BILLETERA. Rich covariate set: EDAD, GENERO, NIVEL_EDUCATIVO, INTERNET_HOGAR, SMARTPHONE, ESTRATO, DOMINIO, INGHOG2D, GASHOG2D. Rosenbaum bounds for sensitivity to unobservables.

**Identification level:** B. Selection on observables. PSM alone is weaker than IV or RDD. Rosenbaum bounds partially address this.

**Data needed:** District-level canon classification.

**Novelty:** Comparison of canon effect on *traditional* banking (BANCO_PREVIO) vs. *digital* banking (TIENE_BILLETERA). Tests whether canon accelerates FinTech or reinforces traditional banking.

**Sub-topic:** Financial inclusion

| N | F | I | ID | EE | Total |
|---|---|---|---|---|---|
| 3 | 5 | 4 | 3 | 4 | **3.70** |

---

### Idea 10: IV with Bartik-style Instrument — Mining Canon and Household Expenditure Patterns

**Research question:** Does canon exposure shift household expenditure composition (GASHOG2D vs. INGHOG2D ratio) toward investment or consumption?

**Method:** IV-2SLS with shift-share (Bartik) instrument. Instrument: interaction of (i) pre-2000 district mining employment share with (ii) national-level mineral price index. This interacts a local exposure share (predetermined) with a national shock (exogenous to any single district). Outcome: log(GASHOG2D), log(INGHOG2D), savings rate proxy.

**Identification level:** A. Bartik instruments are standard in spatial economics. Exclusion: pre-2000 mining share only affects current expenditure through canon channel, not through other economic trends. Threat: differential trends correlated with initial mining share (Goldsmith-Pinkham et al. 2020 critique).

**Data needed:** (1) 1993 Census mining employment shares at district level, (2) Mineral price indices (BCRP or World Bank), (3) District canon amounts.

**Novelty:** First Bartik-style instrument for Peru mining canon. Expenditure patterns reveal whether canon promotes investment or consumption — key policy question.

**Sub-topic:** Consumption / household welfare

| N | F | I | ID | EE | Total |
|---|---|---|---|---|---|
| 5 | 4 | 4 | 4 | 4 | **4.20** |

---

## Summary Score Table

| # | Idea | N | F | I | ID | EE | **Total** | Level | Sub-topic |
|---|------|---|---|---|---|---|---------|-------|-----------|
| 1 | Geological IV → Digital Wallets | 5 | 4 | 5 | 4 | 4 | **4.30** | A | Financial inclusion |
| 2 | Spatial RDD → Poverty | 5 | 4 | 5 | 4 | 4 | **4.30** | A | Poverty |
| 10 | Bartik IV → Expenditure Patterns | 5 | 4 | 4 | 4 | 4 | **4.20** | A | Consumption |
| 5 | Quantile IV → Income Distribution | 5 | 4 | 5 | 4 | 3 | **4.10** | A | Inequality |
| 7 | CEM → Absorption × Education | 5 | 4 | 5 | 3 | 4 | **3.90** | B | Human capital |
| 9 | PSM → Banking Behavior | 3 | 5 | 4 | 3 | 4 | **3.70** | B | Financial inclusion |
| 3 | Dose-Response → Gender × Employment | 4 | 5 | 4 | 3 | 3 | **3.60** | B | Labor/gender |
| 4 | Oaxaca-Blinder → Digital Divide | 4 | 5 | 4 | 2 | 4 | **3.55** | B | Digital divide |
| 6 | Heckman → Labor Supply Selection | 3 | 4 | 4 | 3 | 4 | **3.55** | B | Labor markets |
| 8 | IV Mediation → Smartphone → Wallet | 5 | 3 | 4 | 3 | 3 | **3.35** | B | Digital finance |

---

## TOP 3 IDEAS — Elaborated

### 🥇 RANK 1: Geological IV — Mining Canon and Digital Wallet Adoption

**Sub-topic:** Financial inclusion / digital finance

**Research question:** Does exogenous variation in mining canon transfers cause higher adoption of digital wallets (billeteras digitales) among Peruvian households?

**Pitch:** Peru's fintech revolution (Yape, Plin, BIM) has reached 70%+ penetration, but uptake is uneven across regions. Mining canon districts receive massive fiscal windfalls — up to 40% of municipal budgets. If canon accelerates digital financial inclusion, it reveals an unexpected benefit of extractive fiscal institutions: they may leapfrog traditional banking infrastructure. This paper provides the first causal estimate of whether resource windfalls drive fintech adoption, using geological mineral potential as an instrument for canon exposure.

**Method detail:** IV-2SLS with geological instrument.
- **First stage:** Canon_per_capita_district = α + β × Geological_Mining_Potential + γ × X + ε
  - Geological_Mining_Potential: distance to nearest major mineral deposit × deposit type indicator (copper, gold, zinc) from INGEMMET geological maps.
- **Second stage:** TIENE_BILLETERA / USA_BILLETERA = δ + θ × Canon_per_capita_hat + λ × X + ν
- Controls (X): EDAD, GENERO, NIVEL_EDUCATIVO, ESTRATO, DOMINIO, INTERNET_HOGAR, SMARTPHONE, INGHOG2D, BANCO_PREVIO
- SE clustered at district level (UBIGEO).
- F-statistic target > 10 (Stock-Yogo).

**Identification:** Level A. Geological mineral deposits formed millions of years ago. Their location is exogenous to current household financial behavior. Exclusion restriction: mineral geology affects digital wallet use ONLY through canon transfers. Threat: geology may correlate with remoteness/altitude, which independently affects fintech adoption. Mitigated by controlling for DOMINIO (coast/highlands/jungle) and ESTRATO (urbanization level). Overidentification tests if multiple geological measures used.

**First experiment (week 1):** Merge INGEMMET mineral deposit database with ENAHO UBIGEO codes. Compute distance from each survey cluster (CONGLOME) to nearest deposit. Run first-stage regression. Target F > 10. If weak, add deposit type interactions for stronger first stage.

**Why top choice:** Combines three hot literatures (resource curse, fintech, fiscal federalism). Method is credible (geological IV is standard in resource economics). Data exists and is public. Policy relevance is immediate — Peru's government actively promotes digital payments in mining regions.

---

### 🥈 RANK 2: Spatial RDD — Mining District Border Effects on Poverty

**Sub-topic:** Poverty / fiscal transfers

**Research question:** Does living just inside a mining-canon-receiving district border causally reduce household poverty compared to living just outside in a non-receiving neighboring district?

**Pitch:** Peru's Mining Canon distributes billions of soles annually to districts where mining occurs. But does this money actually reach the poor? Debate is fierce: some argue canon breeds corruption and inequality; others point to improved infrastructure. Administrative district boundaries create a natural experiment: households just across the border from each other share the same geography, markets, and culture — but one side gets canon and the other doesn't. This paper exploits this spatial discontinuity to provide the cleanest estimate yet of canon's poverty impact.

**Method detail:** Spatial regression discontinuity.
- Running variable: signed distance to nearest district border, where `distance > 0` = inside canon-receiving district.
- Specification: POBREZA = α + τ × 1{distance > 0} + f(distance) + β × X + ε
- f(distance): local linear with MSE-optimal bandwidth (Calonico-Cattaneo-Titiunik).
- Restricted to households within optimal bandwidth of district borders.
- Outcome: POBREZA (binary poverty classification) and INGHOG2D (continuous income).
- Heterogeneity: by ESTRATO (urban vs. rural border segments) and by canon intensity.

**Identification:** Level A. Spatial RDD design. District boundaries are administrative artifacts drawn decades before the modern canon system. Within a narrow bandwidth around the border, households are exchangeable except for canon treatment. Key threat: sorting across borders (households moving to canon side). Mitigated by testing for covariate smoothness at cutoff (EDAD, NIVEL_EDUCATIVO, MIEPERHO should not jump).

**Identification checklist:**
- (a) Source of variation: administrative boundary × mining location creates treatment/control groups.
- (b) Pre-treatment periods: N/A (cross-section), but covariate balance at cutoff is testable.
- (c) Parallel trends: N/A for cross-section; density test for manipulation (McCrary) and covariate smoothness.
- (d) Clusters: 1,874 districts in Peru. Sufficient clusters for robust inference at district level.
- (e) Exogeneity: District boundaries are predetermined. But mining districts may differ systematically from neighbors (selection). Spatial RDD mitigates this by comparing ONLY near-border households.

**First experiment (week 1):** Obtain district shapefiles from INEI. Geocode CONGLOME clusters. Classify each district as canon-receiving or not using MEF data. Compute border distances. Test for density discontinuity at border (manipulation check). Run baseline RDD with POBREZA as outcome.

---

### 🥉 RANK 3: Bartik IV — Mining Canon and Household Expenditure Patterns

**Sub-topic:** Consumption / household welfare

**Research question:** Does mining canon income shift household expenditure from consumption toward savings/investment, and does this depend on financial access?

**Pitch:** Canon transfers are meant to fund *public* investment, but they also affect *private* household behavior through local labor markets, prices, and transfers. Whether households save or spend canon-driven income gains determines long-term welfare. If canon merely fuels consumption booms, the resource curse operates at household level. If it enables investment in human capital or assets, canon breaks the curse. This paper uses a Bartik-style shift-share instrument — interacting historical mining employment shares with global mineral prices — to identify causal effects on household expenditure composition.

**Method detail:** IV-2SLS with Bartik instrument.
- Instrument: `Bartik_d = Share_Mining_Emp_d,1993 × ΔMineral_Price_Index_t`
  - `Share_Mining_Emp_d,1993`: district mining employment share from 1993 Census (pre-canon system reform).
  - `ΔMineral_Price_Index_t`: change in BCRP mineral export price index between survey year and 1993 baseline.
- First stage: canon_per_capita on Bartik instrument + district FE controls.
- Second stage: log(GASHOG2D) and savings proxy (log(INGHOG2D) − log(GASHOG2D) residual) on predicted canon.
- Heterogeneity: by INTERNET_HOGAR and SMARTPHONE (does digital access amplify savings behavior?).

**Identification:** Level A. Bartik instruments are widely accepted in spatial economics. The 1993 employment share is predetermined (30+ years before survey). Global mineral prices are exogenous to any single Peruvian district. Exclusion: pre-1993 mining intensity may correlate with long-run development trends. Addressed by controlling for 1993 district characteristics (urbanization, education, poverty from 1993 Census).

**Identification checklist:**
- (a) Source of variation: interaction of predetermined local exposure × exogenous national price shock.
- (b) Pre-treatment: 1993 employment shares measured decades before outcome.
- (c) Parallel trends: Not applicable (cross-section), but overidentification possible with multiple mineral prices.
- (d) Clusters: District-level clustering with sufficient districts.
- (e) Exogeneity: Mineral prices exogenous. 1993 shares may correlate with district trends — controlled for.

**First experiment (week 1):** Obtain 1993 Census microdata (INEI). Compute district-level mining employment shares. Merge with BCRP mineral price indices. Construct Bartik instrument. Run first stage. Validate with falsification test: Bartik instrument should NOT predict outcomes in non-canon districts.

---

## JSON Output

```json
{
  "top_ideas": [
    {
      "rank": 1,
      "title": "Geological IV: Mining Canon and Digital Wallet Adoption in Peru",
      "research_question": "Does exogenous variation in mining canon transfers cause higher adoption of digital financial services (billeteras digitales) among Peruvian households?",
      "method": "IV-2SLS with geological mineral potential as instrument",
      "identification_level": "A",
      "identification_source": "Geological mineral deposit locations (formed millions of years ago) predict canon exposure but are exogenous to current household financial behavior. Distance to nearest major mineral deposit × deposit type serves as excluded instrument.",
      "sub_topic": "financial inclusion",
      "data_sources": ["ENAHO (household survey, provided)", "INGEMMET geological mineral deposit maps", "MEF Consulta Amigable (district-level canon transfers)", "INEI district boundary shapefiles"],
      "novelty": 5,
      "feasibility": 4,
      "impact": 5,
      "identification": 4,
      "expected_effect": 4,
      "total_score": 4.30,
      "pitch": "Peru's fintech revolution (Yape, Plin) reaches 70%+ but uptake is uneven. Mining canon districts receive billions in windfalls. If canon accelerates digital financial inclusion, it reveals an unexpected benefit of extractive fiscal institutions: resource windfalls may leapfrog traditional banking. This paper provides the first causal estimate using geological mineral potential as an instrument for canon exposure — a classic resource economics identification strategy applied to a novel fintech outcome.",
      "first_experiment": "Merge INGEMMET mineral deposit database with ENAHO UBIGEO codes. Compute distance from each survey cluster to nearest deposit. Run first-stage: canon_per_capita on geological distance × deposit type. Target F-statistic > 10 (Stock-Yogo). If weak, add deposit-type interactions."
    },
    {
      "rank": 2,
      "title": "Spatial RDD: Mining District Border Effects on Household Poverty",
      "research_question": "Does living just inside a mining-canon-receiving district border causally reduce household poverty compared to living just outside in a non-receiving neighboring district?",
      "method": "Spatial regression discontinuity design with distance-to-border as running variable",
      "identification_level": "A",
      "identification_source": "Administrative district boundaries are predetermined artifacts drawn decades before the modern canon system. Within a narrow bandwidth around the border, households on either side share geography, markets, and culture but differ in canon treatment status. This creates quasi-random assignment of treatment at the boundary.",
      "sub_topic": "poverty",
      "data_sources": ["ENAHO (household survey, provided)", "INEI district boundary shapefiles", "MEF Consulta Amigable (district-level canon classification)", "IGN geographic coordinates for CONGLOME clusters"],
      "novelty": 5,
      "feasibility": 4,
      "impact": 5,
      "identification": 4,
      "expected_effect": 4,
      "total_score": 4.30,
      "pitch": "Peru's Mining Canon distributes billions to mining districts — but does this money reach the poor? Debate is fierce. Spatial RDD exploits administrative district boundaries as a natural experiment: households just across the border share identical geography and markets, but one side gets canon and the other doesn't. This provides the cleanest estimate yet of canon's poverty impact, bypassing the endogeneity of which districts have mines.",
      "first_experiment": "Obtain district shapefiles from INEI. Geocode CONGLOME clusters. Classify each district as canon-receiving or not. Compute signed distance to nearest treatment border. Run McCrary density test for manipulation. Estimate local linear RDD with MSE-optimal bandwidth (CCT). Test covariate smoothness at cutoff."
    },
    {
      "rank": 3,
      "title": "Bartik IV: Mining Canon, Expenditure Composition, and the Household Resource Curse",
      "research_question": "Does mining canon income shift household expenditure from consumption toward savings and investment, and does digital access amplify this effect?",
      "method": "IV-2SLS with Bartik shift-share instrument (1993 mining employment share × mineral price changes)",
      "identification_level": "A",
      "identification_source": "Interaction of predetermined 1993 district mining employment shares (measured 30+ years before survey, before modern canon system) with exogenous global mineral price changes. 1993 shares are fixed; price changes are global. Neither is caused by current household behavior.",
      "sub_topic": "consumption",
      "data_sources": ["ENAHO (household survey, provided)", "1993 Peru Census microdata (INEI)", "BCRP mineral export price indices", "MEF Consulta Amigable (district canon transfers)"],
      "novelty": 5,
      "feasibility": 4,
      "impact": 4,
      "identification": 4,
      "expected_effect": 4,
      "total_score": 4.20,
      "pitch": "Canon is meant to fund public investment, but it also reshapes private household budgets through labor markets and local prices. Whether households save or spend windfall income determines if canon breaks or reinforces the resource curse at the micro level. A Bartik shift-share instrument — historical mining employment interacted with global mineral prices — identifies the causal effect of canon on expenditure composition. Heterogeneity by smartphone and internet access tests whether digital tools amplify savings behavior.",
      "first_experiment": "Obtain 1993 Census microdata from INEI. Compute district-level mining employment shares. Merge BCRP mineral price indices. Construct Bartik instrument = share_mining_1993 × Δprice_index. Run first stage: canon_per_capita on Bartik. Falsification: Bartik should not predict outcomes in non-canon districts. Test overidentification with multiple mineral price series."
    }
  ],
  "identification_warning": "All top 3 ideas achieve Identification Level A (4/5). No warning needed. However, ALL ideas require merging external data (geological maps, census microdata, district boundaries, canon transfer amounts) with the provided ENAHO cross-section. The cross-sectional nature of the survey means that pre-trends cannot be tested. The credibility of each design rests on (i) the quality of the external data merge via UBIGEO, (ii) the validity of the exclusion restriction for IV designs, and (iii) the smoothness of covariates at the boundary for the spatial RDD. Recommendation: Merge external data FIRST, validate instruments and discontinuities, then select the design with the strongest first-stage / sharpest discontinuity."
}
```

---

**Bottom line:** Cross-section constraint is real but NOT fatal for credible identification. Three Level-A strategies available — geological IV (standard in resource economics), spatial RDD (standard in policy evaluation), Bartik shift-share (standard in spatial economics). All three exploit geographic variation in canon exposure that is exogenous to current household outcomes. Each targets a different sub-topic (financial inclusion, poverty, consumption). Merge external data first; pick the design with the strongest first stage.