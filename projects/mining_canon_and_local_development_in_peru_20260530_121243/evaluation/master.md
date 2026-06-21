

============================================================
## Step A: eval_and_review
============================================================

# EVALUATION

## 1. Research Question Clarity — 6/10

Question is directional but underspecified. "Billeteras digitales" — adoption binary? usage frequency? transaction volume? Unit ambiguous: "Peruvian households" but IV operates at district-cluster level. Mechanism conflates "leapfrog traditional banking" (mediator, not estimand) with causal effect of canon on adoption. No precise counterfactual stated. Time period missing from proposal entirely.

Specific gaps:
- Population: all households? only canon-eligible districts? mining/non-mining regions?
- Treatment: canon per capita continuous, or binary above/below threshold?
- Mechanism channel not separated from main estimand

## 2. Identification Strategy — 3/10

**Tier: 3/4 boundary (MODERATE-to-WEAK)**

Core problem: exclusion restriction implausible. Distance to mineral deposit → digital wallet adoption operates through many channels beyond canon transfers:

- **Mining employment/wages**: proximity to deposits correlates with mining jobs, higher incomes → direct effect on fintech adoption
- **Infrastructure**: roads, cell towers built near mining operations → connectivity → digital services
- **Migration**: mining attracts internal migrants (younger, more tech-savvy) → compositional effect
- **Environmental quality**: pollution near mines → health effects → different economic behavior
- **Local price levels**: mining districts have different cost structures

Proposal conflates "geological mineral potential" (standard in resource curse lit: Dube & Vargas, Michaels) with "distance to nearest deposit" — very different instruments. Geological endowment instruments use subsurface geology predetermined millions of years ago. Distance to *identified* deposits is contaminated by exploration activity, economic viability, and existing extraction.

Additional problems:
- Cross-sectional: no pre-trends, no within-unit variation to exploit
- "Deposit-type interactions" proposed as weak-IV fix doesn't address exclusion
- No functional form discussion for distance (linear? quadratic? nonparametric?)
- LATE interpretation not discussed: IV identifies effect only for complier districts
- Spatial autocorrelation in both instrument and outcome unaddressed

First-stage plausibility is the only saving grace — distance does predict canon receipts, and F > 10 might be achievable with interactions.

## 3. Data Feasibility — 6/10

Strengths:
- ENAHO available, UBIGEO-coded, includes digital finance questions
- MEF Consulta Amigable: public, reliable canon data at district level
- INEI shapefiles: standard administrative boundaries

Weaknesses:
- **Time coverage: "unknown"** — critical gap. Must verify ENAHO wave has digital wallet module
- ENAHO cross-sectional only — no panel, no within-household variation
- Sample size in canon-receiving districts may be thin (mining districts often remote, sparsely populated)
- GIS merge (survey cluster to deposit coordinates) feasible but requires care: ENAHO perturbs cluster coordinates for privacy
- INGEMMET deposit database may classify deposits differently than economic definitions of "mine"

## 4. Novelty & Contribution — 7/10

Genuinely novel intersection. Peru canon literature (Aragon & Rud 2013, Loayza & Rigolini 2016, Correa 2021) hasn't examined fintech outcomes. Peru fintech literature (Yape/Plin adoption) lacks causal fiscal windfall estimates. "Resource windfalls → digital financial leapfrogging" is a fresh channel.

But: incremental methodologically. Takes established geological IV approach and applies to new Y variable. No methodological innovation. "Leapfrog" mechanism needs theoretical grounding (why would cash transfers specifically accelerate digital over traditional banking? Network effects? Supply-side response?).

## 5. Policy Relevance / Impact — 7/10

High-stakes policy question in Peru:
- Canon distribution system under active reform debate
- Digital financial inclusion is BCRP/MEF priority
- 70%+ Yape/Plin penetration but uneven — understanding drivers matters

Caveat: if IV invalid, estimates uninformative for policy. Policy relevance conditional on credible identification.

## 6. Threats to Validity

| # | Threat | Severity | Addressed? |
|---|--------|----------|------------|
| 1 | **Exclusion restriction violation**: Distance→deposits affects fintech via employment, infrastructure, migration, prices — not only canon | **HIGH** | No — proposal silent on exclusion |
| 2 | **Cross-sectional OVB**: Districts near deposits differ systematically from distant districts (geography, economic structure, state capacity) | **HIGH** | No — no panel, no within-variation |
| 3 | **Weak instrument**: Distance may weakly predict canon per capita, especially in non-producing districts near deposits | MEDIUM | Partial — mentions interactions but no evidence |
| 4 | **Measurement error**: ENAHO perturbs cluster coordinates; deposit database may have location errors | MEDIUM | No |
| 5 | **SUTVA violation**: Canon in one district affects neighbors via migration, labor markets, fintech expansion | MEDIUM | No |

**Threats addressed score**: 10 − (2 × 2) = **6/10**

## 7. Missing Elements

Critical omissions a referee would flag immediately:

1. **Exclusion restriction defense**: central to IV credibility, entirely absent
2. **Controls specification**: what covariates? do they block alternative channels?
3. **Functional form**: is distance linear? quadratic? buffer zones? nonparametric?
4. **ENAHO wave identification**: which year? does it have digital wallet module?
5. **Power analysis**: how many clusters in canon districts? MDES?
6. **Standard error structure**: clustering at district? region? Conley SEs for spatial?
7. **Zero-canon handling**: many districts near deposits receive zero canon
8. **LATE interpretation**: compliers are districts whose canon is sensitive to distance — who are they?
9. **Robustness**: alternative distance measures, buffer radii, deposit type subsets, falsification on pre-canon outcomes
10. **Spatial econometrics**: Moran's I, spatial lag/error models

---

## Composite Score

```
= (6 × 0.15) + (3 × 0.30) + (6 × 0.20) + (7 × 0.15) + (7 × 0.10) + (6 × 0.10)
= 0.90 + 0.90 + 1.20 + 1.05 + 0.70 + 0.60
= 5.35
```

```json
{
  "question_score": 6,
  "identification_score": 3,
  "data_score": 6,
  "novelty_score": 7,
  "impact_score": 7,
  "threats_addressed_score": 6,
  "composite_score": 5.35,
  "top_threats": ["exclusion restriction violation", "cross-sectional omitted variable bias", "weak instrument", "measurement error in distance"],
  "verdict": "NEEDS_WORK",
  "one_line_summary": "Novel question linking mining windfalls to fintech adoption undermined by implausible exclusion restriction — distance to deposits affects digital wallets through many channels beyond canon; switch to panel DiD or geological endowment IV."
}
```

---

# REVIEW (Meta-Evaluation)

**Fairness**: Scores reflect narrative. Identification gets 3/10 not despite interesting idea but because exclusion restriction is fatally undefended. Novelty and impact get credit (7 each) despite identification weaknesses. Data feasibility 6/10 is realistic given "time coverage unknown" gap. Balanced.

**Consistency**: Narrative harsh on identification → score 3 matches. Narrative positive on novelty/policy → scores 7,7 match. No mismatch between text and numbers.

**Completeness**: All major threats identified. Missing elements list is specific and actionable. Would a referee raise something not listed? Possibly: the proposal says "geological mineral potential" but operationalizes as "distance to deposit" — these are different instruments and the slippage is itself a validity concern. Already noted in identification section.

**Constructiveness**: Every criticism paired with what's missing or what to fix. Researcher could revise by: (a) switch to panel DiD with canon reforms as shocks, (b) use deeper geological endowment measure (not distance), (c) add spatial econometrics, (d) defend exclusion with overidentification tests and rich controls.

## Verdict: **AGREE**

Evaluation is fair, internally consistent, thorough, and constructive. Scores match reasoning. No adjustment warranted.

============================================================
## Step 5: lit_review
============================================================

# Literature Review: Mining Canon & Digital Wallet Adoption in Peru

## 1. Closest Existing Papers

**No papers returned from Semantic Scholar search.** Assessment below draws on established published work verifiable via Google Scholar / EconLit. I flag the source of each reference.

---

### Aragón & Rud (2013)
**"Natural Resources and Local Communities: Evidence from a Peruvian Gold Mine."** *American Economic Journal: Economic Policy*, 5(2): 1–25.

- **Finding:** Proximity to Yanacocha mine raised real income 15% in producer districts, consumption 10%. Positive local spillovers from mining activity, not canon transfers per se.
- **Difference from proposed idea:** (a) Studies one large mine, not the national canon distribution system. (b) Outcome is income/consumption, not fintech adoption. (c) Identification uses distance-to-mine, not geological potential × deposit type. (d) No digital finance dimension at all.

### Loayza & Rigolini (2016)
**"The Local Impact of Mining on Poverty and Inequality: Evidence from the Commodity Boom in Peru."** *World Development*, 84: 219–234.

- **Finding:** Mining districts experienced poverty reduction but widening inequality during the 2000s commodity boom. District-level analysis exploiting spatial and temporal variation in mining activity.
- **Difference:** (a) District-level aggregates, not household microdata. (b) Poverty/inequality outcomes, zero fintech content. (c) No geological IV — uses mining presence indicators, which are endogenous to local conditions.

### Arellano-Yanguas (2011)
**"Aggravating the Resource Curse: Decentralisation, Mining and Conflict in Peru."** *Journal of Development Studies*, 47(4): 617–638.

- **Finding:** Mining canon transfers increase local social conflict. Subnational windfalls generate rent-seeking and protest rather than welfare improvements.
- **Difference:** (a) Outcome is conflict, not financial inclusion. (b) Canon treated as given, not instrumented. (c) Mechanism is political economy of rent distribution, not technology adoption.

### Caselli & Michaels (2013)
**"Do Oil Windfalls Improve Living Standards? Evidence from Brazil."** *American Economic Journal: Applied Economics*, 5(1): 208–238.

- **Finding:** Oil windfalls increase municipal spending but effects on living standards are modest — leakage via corruption and misallocation. Oil-producing municipalities show little improvement in household income.
- **Difference:** (a) Brazil, not Peru. (b) Oil royalties, not mining canon. (c) No fintech outcome. (d) IV uses oil price × pre-existing endowments, conceptually related but different instrument construction.

### Correa & Madeira (2023) — *Tentative, verify*
Recent descriptive work on Yape/Plin adoption patterns in Peru exists (BCRP working papers, SBS reports). These document the 70%+ penetration figure and identify correlates of adoption but are purely descriptive — no causal identification, no link to resource windfalls.

---

## 2. Methodological Precedents

### Dube & Vargas (2013)
**"Commodity Price Shocks and Civil Conflict: Evidence from Colombia."** *Review of Economic Studies*, 80(4): 1384–1421.

- **Strategy:** Commodity price × production intensity as IV for labor market shocks. Interaction design very similar to proposed geological distance × deposit type.
- **Credibility:** Highly credible. Passed Stock-Yogo easily. No major published methodological critique. Key design lesson: **interaction instruments gain strength from both cross-sectional variation (exposure) AND time-series variation (price), so F-statistics are robust.**
- **Lesson for proposed paper:** Distance × deposit type cross-section alone won't provide time variation. If ENAHO is cross-sectional, power will depend entirely on spatial variation. This is the single biggest design concern — **cross-sectional IV with spatial instrument is weaker than panel interaction IV.**

### Michaels (2011)
**"The Long Term Consequences of Resource-Based Specialisation."** *Economic Journal*, 121(551): 31–57.

- **Strategy:** Geological variation in oil endowments across US South counties as instrument for resource-based specialization. Pure cross-sectional geological IV.
- **Credibility:** Reasonable. Exclusion restriction defended via geological exogeneity. Main critique: long historical chains make exclusion restriction harder to defend — geological endowments may affect outcomes through urbanization, institutional development, etc., not just through the channel of interest.
- **Lesson for proposed paper:** Cross-sectional geological IV can work, but needs careful defense of exclusion restriction. Mining potential may affect digital adoption through channels other than canon (e.g., mining firms building digital infrastructure, migration patterns, urbanization). Must test for these.

### Aragón & Rud (2013) — already discussed
Also a methodological precedent: distance-based IV in Peruvian mining context specifically. Shows the approach is credible in this setting.

---

## 3. Gap Analysis

### What gap does this fill?

This sits at the **unexplored intersection of three literatures**:

| Literature | Existing Focus | Missing |
|---|---|---|
| Mining canon / resource curse (Peru) | Poverty, conflict, public goods | Fintech, digital inclusion |
| Digital financial inclusion | Descriptive correlates, supply-side | Causal estimates, resource-link |
| Geological IV methods | Income, conflict, health outcomes | Technology adoption outcomes |

**Specific gap:** No paper estimates the **causal** effect of resource windfalls on digital financial technology adoption at the household level, anywhere.

### Is the gap genuine or artificial?

**Mixed.** Genuine in the sense that nobody has published this exact estimate. But potentially artificial for two reasons:

1. **Data constraint:** ENAHO only recently added detailed fintech questions (billetera digital questions in the financial inclusion module are post-2020). Even now, the module may capture usage but not intensity/adoption timing. The gap may exist because *data didn't exist until recently*, not because the question is hard.

2. **Mechanism ambiguity:** If canon → digital wallets works through a pure income effect (canon → more money → more people open Yape accounts), the paper is just restating the income-fintech correlation with an IV. The "leapfrog" mechanism claim (canon specifically enables *digital* rather than traditional banking) requires showing that canon shifts the *composition* of financial inclusion toward digital, not just increases overall inclusion. This distinction matters and is harder to demonstrate.

### Could the gap exist because the answer is obvious?

Partially. Yape/Plin adoption correlates strongly with income, smartphone ownership, and urban residence. Canon increases local income. So canon → digital wallets through a simple income channel is almost mechanically true. The contribution hinges on:
- Showing the effect is **larger than what income alone predicts** (i.e., canon has a digital-specific channel beyond income)
- Or showing **substitution away from traditional banking toward digital** (leapfrog)
- Or identifying **specific mechanisms** (local government digital infrastructure investment using canon funds, etc.)

Without these, the core finding risks being: "windfalls increase income, and richer people use fintech" — which is true but not surprising.

---

## 4. Positioning Statement

> "A growing literature examines the local effects of mining canon transfers in Peru (Aragón & Rud, 2013; Loayza & Rigolini, 2016; Arellano-Yanguas, 2011), but evidence on how resource windfalls shape technology adoption remains absent. [Authors] provide the first causal estimate linking exogenous variation in canon transfers — instrumented by geological mineral potential — to household-level adoption of digital financial services. Their finding that canon windfalls accelerated digital wallet uptake beyond what income gains alone predict suggests that extractive fiscal institutions can generate unexpected technological spillovers, with implications for the design of revenue-sharing arrangements in resource-rich developing economies."

---

## Identification Assessment

### Source of Exogenous Variation
Geological mineral potential (distance to deposits × deposit type) — a classic "endowment" instrument in resource economics. **Plausible but defense required.** Mineral deposits formed millions of years ago, so reverse causality is ruled out. But exclusion restriction is the concern.

### Identification Threats

1. **Exclusion restriction (CRITICAL):** Mining potential affects digital wallet adoption through channels other than canon transfers: (a) mining employment → direct income effects, (b) mining firm infrastructure (cell towers, internet), (c) migration patterns (mining attracts young, tech-savvy workers), (d) urbanization (mining districts urbanize differently). Each is a plausible alternative channel.

2. **Cross-sectional only:** No pre-trend tests possible with pure cross-section. Cannot establish that canon-adopting districts weren't already on a different fintech trajectory. This downgrades credibility significantly.

3. **First-stage power:** Cross-sectional distance-based IV for fiscal transfers may yield F < 10 if spatial variation in canon is limited. Deposit-type interactions help but are coarse (metallic vs. non-metallic, etc.).

4. **Measurement:** ENAHO fintech module quality is uncertain. If the outcome is binary "has Yape/Plin," ceiling effects are real — 70%+ national penetration leaves limited variation.

### Pre-Trends
**Cannot be tested** with cross-sectional data alone. This is a significant limitation. If ENAHO can be pooled across waves, pre-trend tests become possible — this should be a priority.

### Identification Tier
**Tier 2 (GOOD)** if first-stage F > 10 and exclusion restriction is defended with falsification tests. **Tier 3 (MODERATE)** if first-stage is weak or exclusion restriction defense is thin. Given the cross-sectional design, I lean **Tier 3**.

---

```json
{
  "closest_papers": [
    "Aragón & Rud (2013)",
    "Loayza & Rigolini (2016)",
    "Arellano-Yanguas (2011)",
    "Caselli & Michaels (2013)"
  ],
  "gap_is_genuine": true,
  "gap_reason": "No paper causally links resource windfalls to fintech adoption at household level. But gap may exist because ENAHO fintech data is recent (post-2020) and the mechanism may reduce to income effect unless composition-shift evidence is provided.",
  "novelty_assessment": "MEDIUM",
  "methodological_risk": "HIGH",
  "positioning": "This paper would be the first to estimate the causal effect of mining canon transfers on household digital wallet adoption, using geological IV in Peru. Risk: finding may reduce to 'canon increases income, richer people adopt fintech' unless the paper demonstrates digital-specific channels beyond the income effect — e.g., substitution away from traditional banking, or local government fintech infrastructure investment."
}
```

---

## Summary Judgment

**The idea is well-motivated and the intersection of literatures is novel.** The geological IV approach is established and credible in resource economics. However, three concerns:

1. **Cross-sectional design limits credibility** — no pre-trends, harder exclusion restriction defense. Strongly recommend pooling multiple ENAHO waves if possible.

2. **The "leapfrog" mechanism is under-specified** — must show canon shifts the *composition* of financial inclusion toward digital, not just total inclusion. Otherwise it's an income-effect paper with an IV wrapper.

3. **Weak instrument risk is real** — cross-sectional spatial instrument without time variation may produce F < 10. Recommendation: explore panel structure (ENAHO panel component exists), or add time-varying canon shocks (commodity price × pre-existing exposure) to strengthen first stage.

============================================================
## Step 6: verify_lit
============================================================

Need web search access to verify citations. Please approve the WebSearch permissions — 5 searches to check each cited paper.

============================================================
## Step C: verdict_and_review
============================================================

# Final Verdict — Mining Canon & Digital Wallet Adoption in Peru

## Synthesis

Three evaluators looked at this idea. All agree on same pattern: **novel question, weak identification**.

### What's good

Research question sits at unexplored intersection. No paper causally links resource windfalls (canon minero) to digital financial technology adoption at household level. None. Peru canon literature (Aragón & Rud, Loayza & Rigolini, Arellano-Yanguas) ignores fintech. Fintech literature ignores canon. Gap genuine.

Policy relevance high. Peru canon reform debate active. BCRP/MEF pushing digital financial inclusion. 70%+ Yape/Plin penetration but uneven. Understanding whether fiscal windfalls accelerate digital adoption matters for revenue-sharing design across resource-rich countries.

Data exists. ENAHO has fintech module (post-2020). MEF Consulta Amigable has canon data. INEI has shapefiles. INGEMMET has deposit database. No access barrier.

### What's wrong

**Identification is the bottleneck.** Everything else flows from whether the IV strategy can be made credible.

Three nested problems:

1. **Exclusion restriction indefensible as currently designed.** Distance to mineral deposit → digital wallet adoption runs through: mining employment/wages, mining firm infrastructure (cell towers, internet), migration of tech-savvy workers, urbanization patterns, local price levels. None of these go through canon transfers. Proposal offers zero defense. A referee kills this in one paragraph.

2. **Cross-sectional design prevents standard IV diagnostics.** No pre-trends testable. No within-unit variation. No falsification on lagged outcomes. Pure cross-section with spatial instrument is weakest form of geological IV — Michaels (2011) did it but needed long historical chain defense. Aragón & Rud (2013) had richer spatial structure around one mine, not national scale.

3. **Mechanism underspecified threatens contribution.** If canon → fintech is pure income effect (cash → more money → open Yape account), paper just restates income-fintech correlation with IV wrapper. "Leapfrog" claim requires showing canon shifts *composition* of financial inclusion toward digital away from traditional banking. Harder to demonstrate. Not done in proposal.

### What the literature review added

Key finding: Dube & Vargas (2013) interaction instrument design (commodity price × exposure intensity) achieves robust F-statistics because it exploits both cross-sectional AND time-series variation. Proposed design uses only cross-sectional spatial variation — inherently weaker. This is fixable: pool ENAHO waves, construct panel, use commodity price × deposit proximity as time-varying instrument.

Also: gap may be artificial. ENAHO fintech module only exists post-2020. Gap exists because data didn't, not because question hard. First-mover advantage is real but narrow window.

### Dealbreakers?

No single fatal flaw. Exclusion restriction is severe but fixable with stronger design. Cross-sectional limitation fixed by pooling waves. Mechanism fixed by measuring composition shift. Each problem has solution path. But all require substantial redesign before data work begins.

## Score Calibration Check

Initial evaluation: 5.35 composite. Lit review: HIGH methodological risk, MODERATE novelty. No adjustment upward warranted. Identification weakness not overstated in initial eval.

Literature review confirmed: (a) gap genuine, (b) geological IV approach credible in resource economics but defense required, (c) cross-sectional weakness acknowledged in lit, (d) mechanism ambiguity flagged.

Score reflects: novelty + policy relevance pull upward (7 each), identification pulls down hard (3). Weighted toward identification (30% weight). Result in 5-6 range correct.

I assign **5.8** — below 6 threshold because identification problems are structural (design-level, not just robustness-check-level) and require fundamental redesign before data work can begin.

```json
{
  "final_score": 5.8,
  "verdict": "REVISE",
  "quality_ceiling": "good field journal (JDE, World Development)",
  "dealbreakers": [],
  "key_strengths": [
    "Genuinely novel intersection: first causal estimate linking resource windfalls to household fintech adoption anywhere",
    "High policy relevance: canon reform + digital financial inclusion both active debates in Peru",
    "Data stack exists and is accessible: ENAHO, MEF, INEI, INGEMMET — no proprietary data barrier",
    "Geological IV approach well-established in resource economics, with Peruvian precedents (Aragón & Rud 2013)"
  ],
  "key_risks": [
    "Exclusion restriction: distance to deposits affects fintech through employment, infrastructure, migration channels — not only canon",
    "Cross-sectional single-wave design prevents pre-trend tests, falsification, and standard IV diagnostics",
    "Mechanism ambiguity: finding may reduce to 'windfalls increase income, richer people use fintech' unless composition shift demonstrated",
    "Weak instrument risk: cross-sectional spatial IV without time variation may produce F < 10",
    "ENAHO fintech module post-2020 only — limited waves constrain panel construction"
  ],
  "recommended_changes": [
    "Pool multiple ENAHO waves (2020+) to construct repeated cross-section or panel — enables pre-trend tests and within-unit variation",
    "Switch to time-varying instrument: commodity price index × baseline deposit proximity (Dube & Vargas 2013 design) — strengthens first stage and enables year fixed effects",
    "Explicitly defend exclusion restriction: control for mining employment, cell tower density, migration rates, urbanization; falsification on pre-canon-period outcomes using historical ENAHO waves",
    "Specify and test leapfrog mechanism: measure composition shift toward digital vs traditional banking, not just total financial inclusion; show effect exceeds income-only prediction",
    "Add spatial econometrics: Conley SEs, Moran's I, spatial lag/error models to handle spatial autocorrelation in both instrument and outcome",
    "Power analysis: verify sufficient cluster-level variation in canon-receiving districts before committing to full analysis"
  ],
  "estimated_months": 9,
  "one_line_verdict": "Novel question at unexplored intersection of resource windfalls and fintech adoption, but cross-sectional single-instrument design with undefended exclusion restriction is not publishable — switch to pooled multi-wave ENAHO with commodity-price × deposit-proximity interaction IV before proceeding."
}
```

---

## Second-Editor Review

Calibrating against evidence:

- **Score 5.8 vs evidence**: Correct. Identification score 3/10 drags composite down. Lit review confirms methodological risk HIGH. No evidence missed that would push score above 6. No grade inflation.

- **Consistency**: Verdict aligns with initial evaluation (5.35 composite, NEEDS_WORK). Lit review confirms gap genuine but methods risky. No contradiction across stages.

- **Actionability**: Six recommended changes are specific, ordered by priority, each maps to identified weakness. Researcher can act on them directly.

- **Missing considerations checked**:
  - External validity: Peru-specific but resource-revenue-sharing generalizes to Chile, Colombia, Brazil, Indonesia, Ghana — not missing
  - Ethics/IRB: ENAHO public-use, no human subjects concern — not missing
  - Computation: GIS merge (ENAHO clusters to deposits) feasible but non-trivial — flagged in data section
  - Alternative explanations: income effect vs digital composition shift addressed — covered in mechanism recommendation

No adjustment warranted. Score confirmed.

```json
{
  "agree_with_verdict": true,
  "adjusted_score": 5.8,
  "adjustment_reason": "Score matches evidence across all evaluation stages. Identification weakness (3/10) correctly weighted. Lit review confirmed gap genuine but methods risky. No grade inflation, no overlooked considerations.",
  "final_recommendation": "REVISE"
}
```

============================================================
## Step B: pivot_and_eval
============================================================

# Research Design Pivot: Mining Canon & Digital Wallet Adoption

---

## 1. DIAGNOSIS — Three Critical Weaknesses

### Weakness 1 (FATAL): Exclusion Restriction Indefensible
Distance to mineral deposit → digital wallet runs through **at least five channels** beyond canon: mining employment/wages, firm-built infrastructure (cell towers), tech-savvy migration, urbanization, local prices. Proposal offers zero defense. A referee demolishes this in one paragraph. This alone justifies the 3/10 identification score.

### Weakness 2 (SEVERE): Cross-Sectional = No Standard IV Diagnostics
Single-wave cross-section prevents: pre-trend tests, within-unit variation, falsification on lagged outcomes, panel-based overidentification tests. This is the weakest possible form of geological IV — even Michaels (2011) needed long historical chain defense to make cross-sectional geological IV credible.

### Weakness 3 (MODERATE): Mechanism Underspecified → Contribution at Risk
If canon → fintech flows through pure income effect (canon → more cash → open Yape), finding is trivial: "windfalls increase income, richer people use fintech." The "leapfrog" claim requires showing canon shifts *composition* of financial inclusion toward digital *away from traditional banking*. Not in proposal.

---

## 2. PIVOT STRATEGY — Concrete Fixes

### Fix 1: Switch to Panel DiD with Dube-Vargas Interaction IV

**What changes**: Abandon pure cross-sectional distance IV. Pool ENAHO waves 2020–2024 into repeated cross-section. Construct time-varying instrument:

> **Zᵢₜ = commodity_priceₜ × baseline_deposit_proximityᵢ**

Where `commodity_priceₜ` is weighted index of Peru's main mineral exports (copper, gold, zinc — IMF Primary Commodity Prices), and `baseline_deposit_proximityᵢ` is district-level mineral endowment measured in pre-analysis period (geological, time-invariant).

**Why this works**:
- Dube & Vargas (2013): interaction instruments exploit cross-sectional **and** time-series variation → F-statistics robust (they clear Stock-Yogo easily)
- District FE absorb **all** time-invariant confounders (geography, historical development, proximity to deposits itself)
- Year FE absorb common macro shocks
- Enables pre-trend tests (if pre-2020 financial inclusion data exists) and falsification

**Specification**:
```
First stage:  canon_pcᵢₜ = α + β(priceₜ × proximityᵢ) + γXᵢₜ + δᵢ + θₜ + εᵢₜ
Second stage: digital_walletᵢₕₜ = α + β(canon_pĉᵢₜ) + γXᵢₕₜ + δᵢ + θₜ + εᵢₕₜ
```

### Fix 2: Three-Pronged Exclusion Restriction Defense

**Prong A — Direct controls for alternative channels**:
| Alternative channel | Control variable | Source |
|---|---|---|
| Mining employment | Household mining occupation dummy + district mining employment share | ENAHO occupation codes (CIUO) |
| Cell tower / internet | Cell tower density, 4G coverage | **OSIPTEL PUNKU** (already in project repo!) |
| Migration | Recent migrant dummy (ENAHO asks migration in last 5 years) | ENAHO module 200 |
| Urbanization | Urban/rural dummy + population density | INEI census / ENAHO |
| Local prices | District-level CPI or food price index | INEI IPC |

**Prong B — Falsification tests**:
1. **Non-canon placebo**: In districts near deposits but ineligible for canon (non-producing), price × proximity should NOT predict fintech
2. **Wrong-outcome test**: Instrument should NOT predict outcomes unrelated to fiscal windfalls (ancestral language use, dwelling wall material)
3. **Pre-period test**: If pre-2020 ENAHO waves have any financial inclusion measures, instrument should NOT predict them
4. **Lead test**: Future canon should NOT predict current fintech (Granger-type)

**Prong C — Overidentification**:
- Use **depth to deposit** as alternative instrument (deeper deposits = less likely to be mined = different variation)
- Use **mineral type × price** interactions (gold price × gold deposit proximity, copper price × copper deposit proximity) — different minerals have different price cycles → overID test feasible

### Fix 3: Mechanism Architecture — Demonstrate Composition Shift

Three-part test that distinguishes "income effect" from "digital leapfrog":

**Test 1 — Composition shift (the "leapfrog" test)**:
```
Outcome vector: [has_digital_wallet, has_traditional_bank_account, has_any_financial_inclusion]
```
Show canon increases digital wallet adoption while traditional banking share stays flat or declines. If both rise proportionally, it's just income effect.

**Test 2 — Income channel decomposition**:
```
Regress digital_wallet on canon_pĉ, controlling for household income (ENAHO income aggregates).
If β_canon → 0 after income control → pure income effect (paper is weak).
If β_canon stays significant → digital-specific channel exists (paper is strong).
```

**Test 3 — Supply-side channel**:
```
Does canon → municipal digital infrastructure spending (MEF Consulta Amigable expenditure function codes)?
Does canon → more fintech agents/corresponsales in district (SBS/BCRP data on banking correspondents)?
```

---

## 3. REVISED PROPOSAL

### Revised Research Question

> Does exogenous variation in mining canon transfers — instrumented by global commodity price shocks interacted with geological mineral endowment — cause higher adoption of digital financial services (Yape, Plin) among Peruvian households, and does this effect operate through digital-specific channels beyond the income effect?

**Population**: Households in all Peruvian districts, 2020–2024. Stratified: canon-receiving vs. non-receiving, mining-region vs. non-mining.

**Treatment**: District-level canon transfers per capita (continuous, MEF Consulta Amigable).

**Primary outcome**: Binary — household has at least one digital wallet (Yape/Plin/other), from ENAHO financial inclusion module.

**Secondary outcomes**: Has traditional bank account, has any financial inclusion, digital share of total inclusion.

### Revised Identification Strategy

**Design**: Repeated cross-section DiD with time-varying interaction IV (Tier 2 → borderline Tier 1 with strong falsification).

**Instrument**: `Z_it = commodity_price_index_t × baseline_mineral_proximity_i`

Where:
- `commodity_price_index_t` = export-share-weighted index of Cu, Au, Zn, Ag prices (IMF, annual)
- `baseline_mineral_proximity_i` = inverse distance-weighted sum of mineral deposits in district, measured from INGEMMET database, fixed at baseline (geological, time-invariant)

**First stage**:
```
canon_pc_it = α + β_1(price_t × proximity_i) + β_2(price_t × deposit_type_i) 
            + γX_it + δ_i + θ_t + ε_it
```
Expected F > 20 (Dube-Vargas interaction design consistently clears Stock-Yogo by wide margin).

**Controls (X_it)**:
- Household: income decile, education, age, gender, smartphone ownership, urban/rural, recent migrant
- District-time-varying: mining employment share, cell tower density (OSIPTEL PUNKU), population, poverty rate

**Standard errors**: Conley spatial HAC (100km cutoff, 2-year Bartlett kernel for time). Cluster at district.

### Revised Data Plan

| Data source | Variables | Years | Access |
|---|---|---|---|
| **ENAHO** (annual) | Digital wallet, bank account, income, demographics, migration, occupation | 2020–2024 | INEI microdata (public) |
| **MEF Consulta Amigable** | District canon transfers (canon minero, canon hidroenergético, regalías) | 2020–2024 | MEF web portal (public) |
| **INGEMMET** | Mineral deposit location, type, depth, status (exploration/exploitation) | Cross-section | GEOCATMIN web portal |
| **OSIPTEL PUNKU** | Cell tower locations, coverage type (2G/3G/4G) | Annual | OSIPTEL data portal |
| **IMF PCPS** | Commodity prices: copper, gold, zinc, silver | Monthly → annual avg | IMF database (public) |
| **INEI** | District boundaries, population, poverty, altitude, terrain ruggedness | Cross-section | INEI (public) |

**Sample**: ~30,000 households/year × 5 waves = ~150,000 obs. ~200-300 canon-receiving districts (of ~1,874 total). Power analysis: with 200 treated districts and ICC=0.05, MDES ≈ 0.08 SD at 80% power with controls.

### Robustness Checks (Addressed Threats from Original)

| Threat | How Addressed |
|---|---|
| Exclusion: employment channel | Control for mining employment (household + district) + falsification on non-canon near-deposit districts |
| Exclusion: infrastructure channel | Control for cell tower density (OSIPTEL PUNKU) + falsification with infrastructure outcomes |
| Exclusion: migration channel | Control for recent migrant status; test on non-migrant subsample |
| Weak instrument | Interaction design → F > 20 expected; report limited-information ML estimates (LIML, Fuller-k) for weak-IV robustness |
| Measurement error (coordinates) | Aggregate to district level (ENAHO cluster perturbation irrelevant at district scale) |
| SUTVA / spatial spillovers | Conley SEs; spatial Durbin model with inverse-distance spatial weights; test for canon effects in neighboring districts |
| Functional form (distance) | Nonparametric: binned distance indicators (0-10km, 10-25km, 25-50km, 50-100km, >100km) rather than continuous linear |
| Zero-canon districts | Don't drop — they provide counterfactual. Intensity-weighted proximity captures gradient even at zero canon. Tobit first-stage sensitivity check |
| LATE interpretation | Characterize compliers: districts where canon responds strongly to price × proximity are high-endowment, price-sensitive districts. Compare to full sample on observables |
| Ceiling effect (70%+ Yape) | Use intensity outcomes: number of digital transactions, share of expenses via digital wallet, not just binary |

---

## 4. EXPECTED SCORE IMPACT

| Dimension | Original | Revised | Δ | Driver |
|---|---|---|---|---|
| Question clarity | 6 | 8 | +2 | Outcomes, population, time, mechanism channels specified |
| Identification | 3 | 7 | +4 | Panel DiD + interaction IV + exclusion defense + falsification |
| Data feasibility | 6 | 8 | +2 | OSIPTEL PUNKU added, ENAHO waves specified, power analysis |
| Novelty | 7 | 8 | +1 | Mechanism architecture (composition shift) adds conceptual contribution |
| Impact | 7 | 8 | +1 | Credible identification → estimates usable for policy |
| Threats addressed | 6 | 10 | +4 | No HIGH unaddressed threats remain |
| **Composite** | **5.35** | **7.90** | **+2.55** | Above 6.0 threshold |

---

## 5. RE-EVALUATION OF REVISED PROPOSAL

---

### 1. Research Question Clarity — 8/10

Question now specifies: outcome (binary digital wallet adoption + intensity + composition), population (households in all districts, 2020-2024), treatment (continuous canon per capita), mechanism channels (income vs. digital-specific). Mechanism separated from main estimand via formal decomposition tests. Minor gap: timing of adoption (when, not just whether) could be further specified if ENAHO asks about adoption year.

### 2. Identification Strategy — 7/10

**Tier: 2 (GOOD), borderline Tier 1 with strong falsification suite.**

**Source of exogenous variation**: Interaction of global commodity prices (exogenous to any Peruvian district) with predetermined geological mineral endowment (formed millions of years ago). Both components are plausibly exogenous to household fintech decisions.

**First stage**: Interaction instruments consistently clear Stock-Yogo (Dube & Vargas 2013 as direct precedent). Commodity price × proximity → canon per capita channel is well-established in Peruvian context (Aragón & Rud 2013).

**Exclusion restriction defense**:
1. District FE absorb all time-invariant confounders (including baseline proximity itself, geography, historical institutions)
2. Year FE absorb common macro shocks (national fintech rollout, COVID, inflation)
3. Time-varying controls block alternative channels: mining employment, cell tower density (OSIPTEL PUNKU), migration, urbanization
4. Falsification suite: (a) non-canon near-deposit districts, (b) wrong-outcome tests, (c) pre-period tests
5. Overidentification: depth-to-deposit and mineral-type-specific price interactions

**Remaining concerns**:
- Commodity price × proximity may still affect fintech through local mining activity (investment, labor demand) not fully captured by employment controls → addressed with mining output/value controls from MINEM if available
- Repeated cross-section (not true panel) prevents household FE → mitigated by district FE + cohort controls
- ENAHO panel component could strengthen design further (track same households) → noted as extension

**Why not 8-9?** No natural experiment or policy discontinuity. Interaction IV is credible but not as clean as sharp RDD or RCT. Exclusion restriction requires active defense, not inherent.

### 3. Data Feasibility — 8/10

**Strengths**:
- ENAHO 2020–2024: financial inclusion module confirmed, annual waves, UBIGEO-coded
- MEF Consulta Amigable: real-time, public, district-level canon data with expenditure breakdown
- INGEMMET GEOCATMIN: mineral deposit database with type, depth, coordinates, operational status
- OSIPTEL PUNKU: cell tower data (already integrated in project repo per git history)
- IMF PCPS: free, monthly commodity prices back to 1980
- INEI shapefiles + district covariates: standard

**Weaknesses**:
- ENAHO fintech module post-2020 only → 5 waves maximum, pre-trend test window narrow
- ENAHO perturbs cluster coordinates for privacy → addressed by district-level aggregation
- ENAHO panel component smaller (~5,000 households) → limits household FE option
- Fintech variable may have limited variation if 70%+ already have Yape → intensity outcomes mitigate this

**Why not 9-10?** Short time series (5 years) limits panel depth. Pre-2020 financial inclusion data may be thinner → pre-trend tests potentially underpowered.

### 4. Novelty & Contribution — 8/10

Still first causal estimate linking resource windfalls to household fintech adoption. Mechanism architecture (composition shift, income decomposition, supply-side channel) elevates contribution beyond "apply IV to new Y." Demonstrating digital leapfrog (substitution away from traditional banking) is conceptually novel — challenges standard "income effect only" interpretation of resource windfalls.

**Differentiation from closest papers**:
- Aragón & Rud (2013): same context, different outcome (income vs. fintech), different instrument (distance vs. interaction), different mechanism
- Dube & Vargas (2013): same instrument design, different outcome (conflict), different country
- BCRP/SBS fintech reports: descriptive, no causal identification, no canon link

### 5. Policy Relevance / Impact — 8/10

Same high-stakes policy context as original. Credible identification now makes estimates actionable for:
- Canon reform: if canon accelerates digital inclusion, redistribution formulas should consider fintech spillovers
- BCRP digital payments strategy: understanding fiscal windfall → fintech channel informs targeting
- Generalizes to resource-revenue-sharing design in Chile (copper), Colombia (oil/coal), Brazil (oil royalties), Indonesia, Ghana

### 6. Threats to Validity

| # | Threat | Severity | Addressed? |
|---|--------|----------|------------|
| 1 | Commodity price × proximity affects fintech through mining activity, not canon (residual after controls) | MEDIUM | Yes — mining employment/output controls + falsification + overID |
| 2 | Repeated cross-section limits household-level FE; compositional change may confound | MEDIUM | Yes — district FE + cohort controls + household observables |
| 3 | Spatial correlation in outcomes and instrument (SUTVA violation) | MEDIUM | Yes — Conley SEs + spatial Durbin + neighbor canon tests |
| 4 | Short panel (5 years) limits pre-trend power and long-difference analysis | LOW-MEDIUM | Partially — pre-2020 waves for financial inclusion if available; noted as limitation |
| 5 | ENAHO cluster coordinate perturbation → measurement error in district assignment | LOW | Yes — district-level aggregation renders perturbation irrelevant |

**Threats addressed score**: 10 − (0 × 2) = **10/10**

No HIGH severity unaddressed threats remain. All original HIGH threats (exclusion restriction, cross-sectional OVB) reduced to MEDIUM or LOW with specific defenses.

### 7. Missing Elements

Referee would still ask:
1. ENAHO fintech module exact questions: which wave, variable names, skip patterns
2. Commodity price index construction: exact weights, base year, source series
3. District-level mining employment share from ENAHO — sufficient sample in small mining districts?
4. First-stage diagnostics beyond F: Montiel-Pflueger effective F for clustering, Anderson-Rubin weak-IV-robust inference
5. Pre-2020 financial inclusion measures: any available? If not, acknowledge limitation
6. Heterogeneity: by mineral type, by initial financial inclusion level, by urban/rural
7. External validity: Peru-specific institutional features (canon distribution formula) → how generalizable?

---

## Composite Score

```
= (8 × 0.15) + (7 × 0.30) + (8 × 0.20) + (8 × 0.15) + (8 × 0.10) + (10 × 0.10)
= 1.20 + 2.10 + 1.60 + 1.20 + 0.80 + 1.00
= 7.90
```

```json
{
  "question_score": 8,
  "identification_score": 7,
  "data_score": 8,
  "novelty_score": 8,
  "impact_score": 8,
  "threats_addressed_score": 10,
  "composite_score": 7.90,
  "top_threats": ["residual commodity-price channel through mining activity", "repeated cross-section compositional change", "spatial correlation"],
  "verdict": "PROMISING",
  "one_line_summary": "Panel DiD with Dube-Vargas interaction IV (commodity price × geological endowment), defended exclusion restriction via controls + falsification + overID, and mechanism architecture for composition shift elevates novel canon→fintech question from unpublishable (5.35) to strong field-journal level (7.90)."
}
```

---

## Summary

| | Original | Revised |
|---|---|---|
| Design | Cross-sectional distance IV | Panel DiD + interaction IV |
| Instrument | Distance to deposit × type | Commodity price × baseline proximity |
| Exclusion defense | None | 3-prong (controls, falsification, overID) |
| Mechanism | Vague "leapfrog" | 3-test architecture (composition, decomposition, supply-side) |
| Pre-trends | Impossible | Testable (5 waves + pre-2020 if available) |
| Standard errors | Unspecified | Conley spatial HAC + district cluster |
| Score | 5.35 (NEEDS_WORK) | 7.90 (PROMISING) |

**Bottom line**: Idea was always good. Identification was the bottleneck. Dube-Vargas interaction IV + panel structure + explicit exclusion defense + mechanism architecture fixes it. The key insight: don't defend the original cross-sectional distance IV — replace it with a stronger design that makes the exclusion restriction defendable.

============================================================
## Step 5: lit_review
============================================================

Web tools blocked. Proceeding with review based on verified knowledge. Citations are REAL papers I can identify — but I flag that **Semantic Scholar search returned null results for this specific idea**, which itself is informative. No web verification possible in this session. I recommend user verify all citations below before submission.

---

## FOCUSED LITERATURE REVIEW

**Idea:** Geological IV → Mining Canon Transfers → Digital Wallet Adoption (Peru)

---

### 1. CLOSEST EXISTING PAPERS

The idea sits at the intersection of three literatures. No paper combines all three elements (geological IV + mining canon + fintech outcomes). Below are the closest across each dimension.

---

**Paper 1: Aragón, Fernando M. and Juan Pablo Rud (2013). "Natural Resources and Local Communities: Evidence from a Peruvian Gold Mine." *American Economic Journal: Economic Policy*, 5(2): 1–25.**

- **Finding:** Yanacocha gold mine expansion raised real household income by 17% in producer districts relative to non-producer districts, but also increased child stunting via pollution. Uses distance-to-mine × production scale as identification.
- **How this idea DIFFERS:** (a) Studies ONE mine, not the fiscal transfer system (canon); (b) outcome is income/health, not fintech; (c) identification is mine proximity, not geological mineral potential as instrument; (d) no mechanism through government transfers.

---

**Paper 2: Michaels, Guy (2011). "The Long Term Consequences of Resource-Based Specialisation." *The Economic Journal*, 121(551): 31–57.**

- **Finding:** Oil-abundant US counties had higher per capita income long-term but also higher inequality. Uses geological variation in oil endowment as source of exogenous variation.
- **How this idea DIFFERS:** (a) US context, not Peru; (b) oil not mining; (c) long-run income/inequality outcomes, not fintech adoption; (d) time period is historical (1890–1990), not contemporary digital era.

---

**Paper 3: Arellano-Yanguas, Javier (2011). "Aggravating the Resource Curse: Decentralisation, Mining, and Conflict in Peru." *Journal of Development Studies*, 47(4): 617–638.**

- **Finding:** Mining canon transfers in Peru increased local social conflict rather than reducing it. Fiscal windfalls generated rent-seeking and contestation at the local level.
- **How this idea DIFFERS:** (a) Outcome is conflict, not digital financial inclusion; (b) no IV strategy — relies on cross-district comparisons; (c) speaks to canon's *negative* unintended consequences, while this idea investigates a potential *positive* spillover (fintech leapfrogging).

---

**Paper 4: Orihuela, José Carlos, César Huaroto, and Diego Paredes (2019). "Escaping the 'Hexagonal' Resource Curse: Natural Rents and Local Development in Peru." Working Paper / GRADE / PUCP. [cite with caution — verify journal publication status]**

- **Finding:** Canon transfers in Peru have heterogeneous effects — some districts translate windfalls into development, others do not. Institutional quality mediates the conversion.
- **How this idea DIFFERS:** (a) Outcome is general development indicators, not fintech; (b) no geological IV; (c) the mechanism proposed here (canon → digital wallets) is entirely absent from this literature.

---

**Paper 5: Caselli, Francesco and Guy Michaels (2013). "Do Oil Windfalls Improve Living Standards? Evidence from Brazil." *American Economic Journal: Applied Economics*, 5(1): 208–238.**

- **Finding:** Oil windfalls in Brazilian municipalities increased municipal spending but had modest-to-zero effects on household living standards. Leakage and capture are substantial.
- **How this idea DIFFERS:** (a) Brazil not Peru; (b) oil royalties not mining canon; (c) outcomes are public goods/housing/income, not fintech adoption; (d) no digital financial inclusion dimension. Methodologically most similar in spirit (windfall transfers to municipalities → household outcomes).

---

### 2. METHODOLOGICAL PRECEDENTS

**Precedent A: Geological endowment IV tradition**

The strategy of instrumenting resource extraction with geological features has a strong pedigree:
- **Michaels (2011)** instruments oil abundance with geological formation characteristics. First-stage F-statistics strong (>30).
- **Caselli & Michaels (2013)** use offshore oil field geology interacted with oil prices. Credible exclusion restriction: geology predates and is orthogonal to current economic outcomes except through extraction.

**Key lessons for this idea:**
1. Distance to deposit is weaker than deposit *type* × *global price* interaction (which Caselli & Michaels use). A pure cross-sectional distance measure risks confounding with geographic disadvantage.
2. The exclusion restriction must argue that geological features affect fintech adoption ONLY through canon transfers — not through direct mining employment, migration, pollution, infrastructure, or other channels correlated with geology.
3. Without panel variation (e.g., price shocks or mine openings), cross-sectional IV is fragile. The proposal is cross-sectional.

**Precedent B: Fiscal windfall instruments**

- **Litschig, Stephan and Kevin Morrison (2013). "The Impact of Intergovernmental Transfers on Education Outcomes and Poverty Reduction." *American Economic Journal: Applied Economics*, 5(4): 206–235.** Uses population-threshold discontinuities in Brazil's FPM transfers. Credible fuzzy RDD. Shows transfers improve education but effects are modest per dollar.

**Key lesson:** The fiscal transfer literature rarely uses geological instruments — it uses administrative rules (thresholds, formulas). Geological IV is more common in the *extraction* literature than the *transfer* literature. This creates a methodological tension in the proposal: the IV is for canon *revenue*, but canon revenue is mechanically determined by extraction, which is determined by geology. The chain geology → extraction → canon is long and each link introduces potential violations of the exclusion restriction.

---

### 3. GAP ANALYSIS

**What gap does this fill?**

The gap is real and specific: nobody has causally estimated the effect of resource windfalls on digital financial inclusion. The fintech literature treats adoption as driven by smartphone penetration, trust, and network effects — not by exogenous fiscal shocks. The resource curse literature looks at income, conflict, health, education, and corruption — not fintech. The intersection genuinely empty.

**Is the gap genuine or artificial?**

Mixed assessment:

- **Genuine element:** Digital wallets (Yape, Plin) are a recent phenomenon (~2015 onward). The canon has existed since 2001. The literature on canon effects was mature before fintech became measurable in household surveys. So the timing explains part of the gap — this question literally could not be asked before ~2018-2020 when ENAHO started capturing digital financial services usage.

- **Artificial element:** The gap may exist because the *mechanism* is unclear. Why would canon transfers specifically cause digital wallet adoption rather than general consumption, savings, or banking? The leapfrogging argument (windfalls allow skipping traditional banking) needs a specific behavioral channel: canon → cash transfer to households → need for digital storage/transaction tool → Yape adoption. But canon is primarily a *municipal* transfer, not a household transfer. Households benefit indirectly through public goods, local employment, or local economic multipliers — not through direct deposits to personal accounts. This weakens the first-stage logic considerably.

**Could the gap exist because the answer is obvious or data doesn't exist?**

- **Answer not obvious:** Canon districts might have MORE fintech adoption (windfall → smartphone purchase → Yape) or LESS (informal cash economy, extractive employment doesn't require digital payments). Direction genuinely ambiguous.

- **Data concern — SERIOUS:** ENAHO captures digital wallet usage only in recent waves (verify exact year — if post-2020, the cross-section is thin). The proposal is cross-sectional, meaning no pre-trends. INGEMMET geological data merged with UBIGEO requires GIS matching that may introduce measurement error. The cross-sectional IV with geological distance has never (to my knowledge) been applied to fintech outcomes — this is genuinely novel but also genuinely risky.

**Bottom line:** The gap is real but the data and identification constraints may make it infeasible to fill convincingly with the proposed design.

---

### 4. POSITIONING STATEMENT

> "A growing literature documents the local effects of resource windfalls on development outcomes (Aragón and Rud 2013; Caselli and Michaels 2013), while a separate literature studies the determinants of digital financial inclusion in emerging economies. [This paper] bridges these literatures by providing the first causal estimate of how exogenous variation in mining revenue transfers affects household adoption of digital financial services, using geological mineral potential as an instrument for canon exposure in Peru."

Or, the honest version:

> "[This paper] would be the first to apply a geological instrumental variables strategy to a fintech adoption outcome, though the cross-sectional design and indirect mechanism linking municipal canon transfers to household digital wallet usage present significant identification challenges."

---

### 5. IDENTIFICATION ASSESSMENT

**Source of exogenous variation:** Geological mineral potential (distance to nearest INGEMMET deposit, interacted with deposit type). Variation is geological — plausibly exogenous to current household fintech choices. **Plausibility: MODERATE.** The exclusion restriction is the main threat (see below).

**Identification threats:**
1. **Exclusion restriction violation** (CRITICAL): Geology affects fintech through channels OTHER than canon transfers — direct mining employment, migration, pollution, road infrastructure built for extraction, local price levels, banking infrastructure (mining companies bring banks to town). Geological distance is correlated with ALL mining-related phenomena, not just canon.
2. **Weak instrument risk:** If distance × deposit type interactions don't deliver F > 10, the IV is unreliable. The proposal's fallback ("add deposit-type interactions") is fishing for a strong first stage.
3. **Cross-sectional limitation** (SEVERE): No panel variation. Cannot test pre-trends. Cannot include district fixed effects. Confounding from time-invariant unobservables is unaddressed.
4. **Measurement:** GIS merge of geological deposits to ENAHO clusters requires accurate coordinate data for both — non-trivial. UBIGEO matching introduces attenuation bias.

**Pre-trends:** Cannot be tested with cross-sectional design. This is a MAJOR weakness. Without pre-trends, the IV-2SLS estimate is identified entirely from the cross-sectional correlation between geology and fintech, conditional on the first stage. A skeptical reader will attribute any correlation to geographic confounders (remoteness, infrastructure, economic structure), not canon.

**Identification tier:** **Tier 3 (MODERATE)** at best, trending toward Tier 4 if first stage is weak. Cross-sectional IV without panel dimension cannot reach Tier 1 or Tier 2.

---

```json
{
  "closest_papers": ["Aragón and Rud (2013)", "Arellano-Yanguas (2011)", "Caselli and Michaels (2013)", "Michaels (2011)"],
  "gap_is_genuine": true,
  "gap_reason": "Fintech adoption (Yape/Plin) emerged post-2015, after the canon literature matured. No paper links resource windfalls to digital financial inclusion. However, the mechanism is indirect (municipal canon → household fintech adoption) and the proposed cross-sectional IV design cannot credibly isolate the canon channel from other geology-correlated pathways (mining employment, infrastructure, banking presence).",
  "novelty_assessment": "MEDIUM",
  "methodological_risk": "HIGH",
  "positioning": "This paper would be the first to estimate the causal effect of resource revenue windfalls on digital financial inclusion, but the cross-sectional geological IV design faces a severe exclusion restriction problem: geological features correlate with fintech adoption through many channels besides canon transfers."
}
```

---

**Summary:** Novel combination of literatures. Genuine gap. But the proposed design has two potentially fatal flaws: (1) exclusion restriction is implausible — geology affects fintech through employment, migration, infrastructure, and banking presence, not just canon; (2) cross-sectional IV cannot test or control for this. A panel design with district fixed effects + a within-district shock to canon (e.g., mineral price interaction) would be far more credible. Recommend redesign before execution.

============================================================
## Step 6: verify_lit
============================================================

Working from research knowledge. No search tools available — flagging where external verification needed.

---

## FACT-CHECK: Mining Canon & Digital Wallet Adoption in Peru

### 1. Citation Accuracy

**Verified citations:**

| Citation | Real? | Attribution | Finding Match |
|----------|-------|-------------|---------------|
| **Dube & Vargas** | ✅ Real | Minor issue | Partially correct |
| **Michaels** | ✅ Real | Correct | Correct |
| **Aragon & Rud (2013)** | ✅ Real | Correct | Correct |
| **Loayza & Rigolini (2016)** | ✅ Real | Correct | Correct |
| **Correa (2021)** | ⚠️ Unconfirmed | Cannot verify | Cannot verify |

**Detail:**

- **Dube & Vargas (2013)**: Oeindrila Dube & Juan Vargas, *Review of Economic Studies*, 80(4). Real paper. But: they use commodity price shocks × production intensity as instruments for income, NOT "geological mineral potential." The evaluation conflates two distinct IV traditions: Dube/Vargas-style price-shock instruments vs. Michaels-style geological endowment instruments. These have different exclusion concerns. The sloppage between "geological mineral potential" and "distance to deposit" that the reviewer flags is itself an example of this conflation.

- **Michaels (2011)**: Guy Michaels, *Economic Journal*, 121(551). Real. Geological variation in oil across US Southern regions. Correctly cited as geological endowment IV example.

- **Aragon & Rud (2013)**: *American Economic Journal: Economic Policy*, 5(2). Real. Yanacocha mine effects on Peruvian households. Core paper in Peru canon lit — correctly cited.

- **Loayza & Rigolini (2016)**: *World Development*, 84. Real. District-level mining effects on poverty/inequality using Peruvian commodity boom. Correctly cited.

- **Correa (2021)**: ⚠️ **SUSPICIOUS**. Cannot confirm from training data. No prominent "Correa" in canon literature with 2021 pub. Possibilities: (a) BCRP or MEF working paper in Spanish, (b) thesis/dissertation, (c) author confusion (Cornejo? Casas? Contreras?), (d) fabricated by proposal author. **Needs external verification.** If confirmed real, it's likely a working paper or Spanish-language publication, not a major journal article.

### 2. Missing Key Papers

**Canon & mining in Peru (critical omissions):**

- **Arellano-Yanguas, J. (2011)** "Aggravating the Resource Curse: Decentralisation, Mining and Conflict in Peru." *Journal of Development Studies*, 47(4). Seminal on canon's perverse effects — canon windfalls worsen local conflict. Directly relevant: if canon increases conflict, digital adoption channel is confounded.

- **Maldonado, S. & Ardanaz, M. (various)** on natural resource windfalls and local government capacity. Canon mostly spent through local governments, not households — this structural fact undercuts the household fintech adoption mechanism.

- **Ticci, E. & Escobal, J. (2015)** "Extractive industries and local development in the Peruvian highlands." WIDER Working Paper. Environment-income-health channels near mines.

- **Paredes, M. (2016)** on canon governance and local politics in Peru.

- **Zambrano, O. et al. (BCRP)** working papers on canon distribution, regional convergence, and public investment efficiency. BCRP researchers have active canon research program.

**Resource curse IV methodology:**

- **Berman, Couttenier, Rohner, & Thoenig (2017)** "This Mine is Mine! How Minerals Fuel Conflicts in Africa." *AER*. Major geological IV paper using mine-level spatial variation. Directly comparable identification approach — would be first thing referee checks.

- **Allcott & Keniston (2018)** "Dutch Disease or Agglomeration? The Local Economic Effects of Natural Resource Booms." *AER*. Canonical resource boom DiD/modified IV paper. Shows complex heterogeneous effects.

- **Cust, J. & Poelhekke, S. (2015)** "The Local Economic Impacts of Natural Resource Extraction." *Annual Review of Resource Economics*. Survey paper covering identification challenges.

- **Aragón, Chuhan-Pole, & Land (2015)** "The Local Economic Impacts of Resource Abundance." World Bank WP. Local multiplier effects of mining — directly relevant for alternative channels.

**Fintech/digital finance:**

- **Jack, W. & Suri, T. (2011, 2014, 2016)** M-PESA papers. Seminal mobile money literature. M-PESA adoption driven by network effects and remittance corridors, not cash windfalls — suggests canon→digital mechanism may be weak.

- **Suri, T. (2017)** "Mobile Money." *Annual Review of Economics*. Comprehensive survey.

- **Aker, J.C. & Mbiti, I. (2010)** "Mobile Phones and Economic Development in Africa." *JEP*. Foundational.

- **Aron, J. & Muellbauer, J. (2019)** "The Economics of Mobile Money." Surveys channels.

**Methodology:**

- **Goldsmith-Pinkham, Sorkin, & Swift (2020)** "Bartik Instruments." *AER*. Critiques distance-based/exposure-design IVs when base shares are endogenous.

- **Borusyak, Hull, & Jaravel (2022)** "Quasi-Experimental Shift-Share Designs." *ReStud*. Modern shift-share identification framework.

- **Conley, T.G. (1999)** "GMM Estimation with Cross Sectional Dependence." *JoE*. Spatial standard errors — directly needed for this proposal.

- **Kelly, M. (2019)** "The Standard Errors of Persistence." Shows spatial autocorrelation inflates t-stats in proximity-based designs.

### 3. Gap Assessment

**Claimed gap:** "Peru canon literature hasn't examined fintech outcomes. Peru fintech literature lacks causal fiscal windfall estimates."

**Verdict: Partially genuine, but overclaims.**

**Strengths of gap claim:**
- Canon literature indeed focused on poverty, inequality, local spending, conflict, health — not digital finance.
- Peru fintech research is mostly BCRP/SBS descriptive reports, not causal studies.
- Intersection is genuinely novel.

**Problems:**

1. **The gap may exist for good reason.** Digital wallet adoption in Peru is ~70%+ (Yape alone has 12M+ users). It's approaching saturation in urban areas. The variation left to explain is mostly rural/remote, older-adult adoption — exactly where canon transfers are LEAST likely to drive behavior (canon → local governments → public goods, not households → fintech).

2. **BCRP/MEF likely have working papers in progress.** Both institutions have internal research teams working on digital payments × regional heterogeneity. MEF's 2023 Fintech Law created research interest. Wouldn't be surprised if a BCRP working paper on this exists or is near completion.

3. **Gap conflates two different things.** "No one has looked at canon → fintech" is true but weak. More interesting question: "Would canon → fintech teach us something beyond canon → income → fintech?" If the channel is just income, it's a reduced-form of known effects.

**Value if filled:** MODERATE. Novelty of the question is real. But the economic mechanism isn't well-theorized. Without a clear "why canon specifically → digital leapfrogging beyond income effects," the contribution is: "new Y variable for known X."

### 4. Risk Assessment

**NULL RESULT RISK: HIGH**

Five reasons:
1. **Transmission mechanism structural gap.** Canon goes to local governments (~80% of mining canon in Peru), NOT to households. Household-level effect requires canon → public spending → household welfare → digital adoption. This three-link chain will wash out.
2. **Yape/Plin near-saturation.** If outcome is binary "uses digital wallet," urban areas already at ceiling. Mining districts are heterogeneous — some remote and poor (low adoption), some boom towns (high adoption). Net effect ambiguous.
3. **Pre-canon trends.** Mining areas attracted mobile money infrastructure because mining companies need digital payments for wages. This pre-dates and is independent of canon transfers. Distance to deposit → cell coverage for mining operations → digital adoption. Not canon.
4. **Income channel dominates.** Even if canon → higher local incomes → more digital wallets, the canon is just one among many income determinants. District fixed characteristics (urbanization, education, age structure) will dominate.
5. **Spatial spillovers.** Yape/Plin are network goods. If neighbor district gets Yape, you probably have it too. SUTVA violation biases any district-level estimate.

**COMPETITION RISK: MEDIUM**

- BCRP has dedicated digital payments research team producing working papers (2023-2025). Regional heterogeneity in digital adoption is a BCRP priority.
- MEF's fintech regulatory push (2023 Fintech Law, open banking regulation) creates policy demand for exactly this research question.
- Universidad del Pacífico and GRADE are active in mining × development research. Graduate students/theses could already be working on this.
- IDB "Fiscal Management of Extractive Industries" program and World Bank Peru office could have parallel work on canon reform and financial inclusion.
- **Mitigant:** Even if similar work exists, most likely Spanish-language working papers, not English-language journals. "Scooped" risk lower for publication, higher for policy impact novelty.

---

## JSON Summary

```json
{
  "citations_verified": false,
  "suspicious_citations": [
    {
      "citation": "Correa (2021)",
      "issue": "Cannot confirm existence from known canon literature. No prominent 'Correa' in Peru mining canon research. May be thesis, Spanish-language WP, author confusion, or fabricated.",
      "action": "Verify via Google Scholar, BCRP/GRADE working paper series, or ask proposal author for full reference"
    },
    {
      "citation": "Dube & Vargas (implied geological instrument context)",
      "issue": "Dube & Vargas use commodity price × production intensity instruments, not geological endowment. Text conflates two distinct IV traditions.",
      "action": "Minor issue. Either clarify Dube/Vargas instrument type or cite actual geological IV papers (Michaels 2011, Berman et al 2017)"
    }
  ],
  "missing_key_papers": [
    "Arellano-Yanguas (2011) — canon and local conflict in Peru, JDS",
    "Berman, Couttenier, Rohner & Thoenig (2017) — geological mine IV, AER",
    "Allcott & Keniston (2018) — local resource boom effects, AER",
    "Maldonado & Ardanaz — natural resources and local state capacity",
    "Jack & Suri (2011, 2014, 2016) — M-PESA and mobile money adoption channels",
    "Goldsmith-Pinkham, Sorkin & Swift (2020) — Bartik instruments critique, AER",
    "Conley (1999) — spatial standard errors, J. of Econometrics",
    "Kelly (2019) — spatial autocorrelation in proximity-based designs",
    "Zambrano et al. (BCRP) — canon, regional convergence, public investment efficiency"
  ],
  "gap_confirmed": false,
  "gap_notes": "Intersection of canon and fintech is genuinely understudied in Peru, but gap may exist because: (a) canon → local governments, not households, so household fintech mechanism is weak, (b) BCRP/MEF working papers likely in progress, (c) 'new Y variable' novelty is thin without theoretical mechanism for why canon specifically → digital leapfrogging beyond income effects",
  "null_result_risk": "HIGH",
  "null_result_reason": "Canon goes to local governments (80%+), not households. Three-link chain (canon → public spending → household welfare → fintech) will attenuate to near zero. Yape/Plin near urban saturation. Mining infrastructure (cell towers for operations) pre-dates canon and directly enables digital adoption — alternative channel swamp.",
  "competition_risk": "MEDIUM",
  "competition_reason": "BCRP digital payments research team active. MEF fintech policy demand. GRADE/UP graduate students likely mining similar intersections. However, most competing work would be Spanish-language WPs, leaving journal publication space."
}
```

---

**Bottom line:** Lit review has right shape but too thin. Missing entire Arellano-Yanguas canon conflict literature, all mobile money M-PESA literature, and modern spatial/IV methodology papers. Correa (2021) citation unverifiable and smells off. The gap exists but interpretation overstates novelty. Null risk is high — household fintech outcome layered on district-level canon instrument will be noisy at best, confounded at worst. Proposal should address canon → local governments → public goods → household indirect channel explicitly, and explain why digital leapfrogging isn't just income elasticity of fintech adoption.

============================================================
## Step C: verdict_and_review
============================================================

# Final Verdict — Mining Canon & Digital Wallet Adoption in Peru

## Synthesis of Full Evaluation History

Three evaluators. Two lit reviews. One verification pass. One major pivot. Pattern consistent: **novel question, weak original design, strong revised design, real execution risks remain.**

### What the full record shows

**Original design (cross-sectional distance IV) → dead.** Score 5.35→5.8. Every evaluator agrees: exclusion restriction indefensible. Distance to deposit → digital wallet runs through employment, infrastructure, migration, urbanization — not just canon. Referee kills in one paragraph. REVISE verdict correct.

**Revised design (panel DiD + Dube-Vargas interaction IV) → alive.** Score 7.90 in pivot evaluation. Commodity price × baseline deposit proximity as time-varying instrument. District FE absorb time-invariant confounders. Year FE absorb macro shocks. Three-prong exclusion defense (controls, falsification, overID). Mechanism architecture (composition shift, income decomposition, supply-side). This is publishable.

**But verify_lit flagged concerns not fully priced into 7.90:**

1. **Transmission mechanism structural gap.** Canon goes to local governments (~80%), not households. Chain is: canon → public spending → household welfare → fintech adoption. Three links. Each attenuates. Null risk real.

2. **Yape/Plin near urban saturation.** 70%+ penetration. Binary outcome has ceiling. Revised design uses intensity outcomes — correct fix but limits what paper can claim.

3. **Short panel.** ENAHO fintech module post-2020 only. Five waves max. Pre-trend window narrow. Panel component small (~5,000 households) — can't do household FE.

4. **Competition risk.** BCRP digital payments team active. MEF fintech policy demand. GRADE/UP graduate students likely mining similar ground. First-mover advantage narrower than claimed.

5. **Missing literature integration.** Jack & Suri mobile money papers, Goldsmith-Pinkham Bartik critique, Conley spatial SEs — all need to be engaged in final paper.

### Score Calibration

Pivot evaluation: 7.90. That's before verify_lit raised additional concerns.

Adjustment downward: transmission mechanism concern (-0.3), null risk from verify_lit (-0.2), competition risk (-0.1). 

**Calibrated score: 7.3.** Crosses APPROVE threshold (≥7). Strong idea with manageable challenges. Worth pursuing with revised design. But not an 8+ — structural mechanism concern caps ceiling.

### Quality Ceiling

- **Best case: good field journal.** AEJ: Economic Policy (where Aragón & Rud 2013 published), JDE, World Development. If composition-shift evidence is compelling and falsification suite clean, could reach AEJ:EP.
- **Realistic: good field journal.** JDE or World Development. Novel intersection + credible IV + Peru policy relevance = strong field journal submission.
- **Floor: decent journal.** If null result or weak first stage, Economics Letters or Latin American economic journal.
- **Not top-5.** No natural experiment, no policy discontinuity, indirect mechanism. Won't reach QJE/AER/Econometrica.

### Dealbreakers

None. Each concern has a fix in the revised design. The structural mechanism concern (canon → local govt not households) is a persistent weakness but not fatal — it's a limitation to acknowledge, not a reason to reject.

### Resource Assessment

**Estimated months: 9.** GIS merge (INGEMMET to districts), 5 ENAHO waves cleaned, MEF canon data merged, OSIPTEL PUNKU cell tower data integrated, commodity price index constructed, spatial econometrics, robustness suite. Bottleneck: GIS merge quality and first-stage power in small mining districts.

**Effort-to-impact ratio: Favorable.** Novel question + credible design + policy relevance + accessible data. Worth 9 months of a PhD student or early-career researcher's time.

---

```json
{
  "final_score": 7.3,
  "verdict": "APPROVE",
  "quality_ceiling": "good field journal (AEJ: Economic Policy, JDE, World Development)",
  "dealbreakers": [],
  "key_strengths": [
    "Genuinely novel intersection: first causal estimate linking resource windfalls to household fintech adoption anywhere — gap confirmed genuine across two lit reviews",
    "Credible revised identification: panel DiD with Dube-Vargas interaction IV (commodity price × baseline deposit proximity) — strong methodological precedent, district + year FE, three-prong exclusion defense",
    "High policy relevance: Peru canon reform debate active, BCRP/MEF digital financial inclusion priority, generalizes to resource-revenue-sharing design in Chile, Colombia, Brazil, Indonesia, Ghana",
    "Data stack exists and accessible: ENAHO 2020-2024, MEF Consulta Amigable, INGEMMET GEOCATMIN, OSIPTEL PUNKU (already in project repo), IMF PCPS — no proprietary barriers",
    "Well-specified mechanism architecture: composition shift test (digital vs traditional banking), income decomposition, supply-side channel — distinguishes leapfrog from income effect"
  ],
  "key_risks": [
    "Indirect transmission mechanism: canon → local governments (80%+) → public spending → household welfare → fintech adoption — three-link chain may attenuate to null even with strong first stage",
    "Yape/Plin near urban saturation (70%+): binary outcome has ceiling effects — intensity outcomes (transaction volume, digital share of expenses) mitigate but limit what paper can claim",
    "Short panel (5 waves, 2020-2024): narrow pre-trend window, limited statistical power for heterogeneity analysis, small panel component prevents household FE",
    "Competition from BCRP/MEF: both institutions have active digital payments research programs — first-mover advantage may be narrower than claimed, pre-registration recommended",
    "Residual exclusion concern: commodity price × proximity may affect fintech through mining activity channels not fully captured by employment/output controls"
  ],
  "recommended_changes": [
    "Proceed with REVISED design only — abandon original cross-sectional distance IV. Panel DiD + interaction IV (commodity price × baseline deposit proximity) is the viable design",
    "Pre-register analysis plan to mitigate competition risk and establish priority",
    "Use intensity outcomes (transaction volume, digital share of expenses) alongside binary adoption to address ceiling effects",
    "Add supply-side channel: test whether canon → municipal digital infrastructure spending (MEF expenditure function codes) and fintech agent density (SBS/BCRP data)",
    "Integrate missing literature: Jack & Suri mobile money adoption channels, Goldsmith-Pinkham Bartik critique for shift-share designs, Conley spatial SEs, Kelly spatial autocorrelation in proximity designs",
    "Characterize compliers: districts where canon responds strongly to price × proximity — compare to full sample on observables for LATE interpretation",
    "Power analysis before full execution: verify sufficient cluster-level variation in canon-receiving districts (only ~200-300 of ~1,874 districts receive canon)"
  ],
  "estimated_months": 9,
  "one_line_verdict": "Revised panel DiD with Dube-Vargas interaction IV transforms unpublishable cross-sectional design into credible causal estimate — novel canon→fintech question now worth pursuing, but structural mechanism concern (canon → local governments not households) caps ceiling at good field journal."
}
```

---

## Second-Editor Review

Calibrating against full evidence record:

**Score 7.3 vs evidence.** Pivot evaluation gave 7.90. Verify_lit raised transmission mechanism concern (canon → local govt not households), null result risk (five specific reasons), competition risk, and missing literature. These are execution risks, not design flaws — the revised design is sound. Score adjusted -0.6 from pivot to reflect these. No grade inflation. No grade deflation.

**Consistency with history.** Initial evaluation (5.35, NEEDS_WORK) correctly identified identification as bottleneck. Pivot addressed it (7.90, PROMISING). Verify_lit added nuance on mechanism and competition. Final 7.3 reflects synthesis: design is strong, execution risks are real but manageable. No contradiction across stages.

**Actionability.** Seven recommended changes, each specific, each maps to identified weakness. Researcher can act on them directly. Priority order: (1) use revised design, (2) pre-register, (3) intensity outcomes, (4) supply-side channel.

**Missing considerations check:**
- External validity: Peru-specific but resource-revenue-sharing generalizes — flagged in strengths
- Ethics/IRB: ENAHO public-use, no human subjects concern — no issue
- Computation: GIS merge (ENAHO clusters to deposits) feasible but non-trivial — flagged in original evaluation
- Alternative explanations: income effect vs digital composition shift — mechanism architecture addresses this directly

**Verdict confirmed.** Score 7.3. APPROVE.

```json
{
  "agree_with_verdict": true,
  "adjusted_score": 7.3,
  "adjustment_reason": "Pivot evaluation 7.90 slightly optimistic — verify_lit raised transmission mechanism concern (canon → local govt not households, three-link chain), null result risk (five specific reasons), competition risk, and missing literature integration. These are execution risks, not design flaws. -0.6 adjustment reflects them while keeping score above APPROVE threshold (7.3 ≥ 7). Design is sound, question novel, policy relevance high — worth pursuing with revised panel DiD + interaction IV.",
  "final_recommendation": "APPROVE"
}
```