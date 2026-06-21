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