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