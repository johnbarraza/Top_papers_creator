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