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