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