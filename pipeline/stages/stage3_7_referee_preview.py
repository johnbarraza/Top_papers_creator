"""Stage 3.7 — Referee Preview (automatic).

Runs BEFORE Stage 4 (code generation). Two simulated referees review the
research design and produce a concrete checklist of what the code and paper
must include to pass peer review. This checklist is saved to the strategy
directory so that Stage 4 (manual intervention) can read it and generate
scripts that already satisfy referee expectations.

No human checkpoint — fully automatic via CLI.
"""

from datetime import datetime
from pathlib import Path

from ..config import CLO_AUTHOR, get_profile
from ..claude_runner import run_claude, run_claude_parallel
from ..json_utils import extract_json, smart_truncate
from ..state import save_state


def _read_file_or(path: Path, default: str = "") -> str:
    return path.read_text(encoding="utf-8") if path.exists() else default


def run(project_dir: Path, state: dict) -> dict:
    """Execute Stage 3.7: referee preview of code/analysis requirements."""

    # Skip if already completed
    if state["stages"].get("stage3_7", {}).get("status") == "completed":
        print("  [3.7] Already completed — skipping.")
        return state

    print("  [3.7] Generating referee preview of code requirements...")

    # Gather context
    stage2_5 = state["stages"].get("stage2_5", {})
    selected_idea = stage2_5.get("selected_idea", {})
    stage3 = state["stages"].get("stage3", {})
    validation = stage3.get("result", {})

    # Read strategy if it exists (from 4a), otherwise use idea
    strategy_dir = project_dir / "strategy"
    strategy_memo = _read_file_or(strategy_dir / "strategy_memo.md")

    # Data profile
    stage1 = state["stages"].get("stage1", {})
    data_profile = stage1.get("data_profile", {})

    context = f"""
## Research Design
Title: {selected_idea.get('title', validation.get('title', 'N/A'))}
Method: {selected_idea.get('method', validation.get('method', 'N/A'))}
Research Question: {selected_idea.get('research_question', validation.get('refined_question', 'N/A'))}

## Data
- Rows: {data_profile.get('rows', '?')}
- Columns: {data_profile.get('cols', '?')}
- Structure: {data_profile.get('structure', '?')}

## Validation Result
Score: {validation.get('final_score', '?')}
Verdict: {validation.get('verdict', '?')}
Recommended changes: {validation.get('recommended_changes', [])}

## Strategy Memo (if available)
{smart_truncate(strategy_memo, 3000) if strategy_memo else '(not yet generated)'}
"""

    # Build prompts for two referee perspectives
    domain_prompt = f"""You are a domain referee in applied health/labor economics reviewing
a research PROPOSAL (not a finished paper). Your job is to anticipate what
the final paper will need to pass peer review and produce a CONCRETE CHECKLIST
of requirements for the code and analysis.

{context}

Based on this research design, produce a checklist of SPECIFIC requirements
that the Python analysis scripts must implement. Focus on:

1. STATISTICAL METHODS required (exact estimators, not vague)
2. ROBUSTNESS CHECKS that referees will demand
3. DATA CONSTRUCTION issues to watch for
4. TABLES AND FIGURES that must be included
5. POTENTIAL PITFALLS in the data that the code must handle

Be calibrated: for an observational/descriptive study, do NOT require
quasi-experimental methods (RDD, IV) unless the data supports them.
DO require proper standard errors, robustness checks, and honest
limitation acknowledgment.

Output a JSON block:
```json
{{
  "code_requirements": [
    {{"category": "estimation", "requirement": "...", "priority": "MUST|SHOULD|NICE"}},
    ...
  ],
  "data_warnings": ["..."],
  "tables_required": ["..."],
  "figures_required": ["..."]
}}
```
"""

    methods_prompt = f"""You are a methods referee (econometrician) reviewing a research
PROPOSAL. Your job is to anticipate methodological issues and produce a
CONCRETE CHECKLIST of what the analysis code must implement.

{context}

Produce requirements focusing on:

1. INFERENCE: what standard errors are appropriate? Clustering level?
   Bootstrap? Wild bootstrap? Analytical?
2. SPECIFICATION TESTS: what diagnostics must be run?
3. ROBUSTNESS: what alternative specifications are essential?
4. PRESENTATION: what must tables include (SEs, CIs, N, R2)?
5. COMMON MISTAKES to avoid with this method and data structure

*** MANDATORY CHECKS FOR CAUSAL DESIGNS (DiD, IV, RDD, event study): ***
If the method claims causal identification, the following are ALWAYS MUST priority:

- PRE-TREND TEST: If DiD or event study, require a joint F-test on all pre-treatment
  coefficients (H0: all pre-period effects = 0). If no pre-treatment data exists,
  require an explicit statement of this limitation and its impact on credibility.
  Also require Roth (2022) sensitivity analysis for pre-trend testing power.

- WILD CLUSTER BOOTSTRAP: If clustering has fewer than 50 clusters, require
  wild cluster bootstrap (Rademacher weights, 999+ replications) as the PRIMARY
  inference method. Asymptotic cluster-robust SEs are unreliable below 50 clusters.
  Recommend the 'wildboottest' Python package or 'boottest' in Stata.

- HETEROGENEITY-ROBUST ESTIMATOR: Apply ONLY when appropriate:
  * STAGGERED DiD (units treated at different times): MUST use Sun & Abraham (2021)
    or Callaway & Sant'Anna (2021) — standard TWFE produces biased estimates with
    negative weights. This is the primary case where these estimators are essential.
  * SIMULTANEOUS TREATMENT (all units treated at same time, e.g., COVID shock):
    Sun-Abraham/CS are NOT needed. Standard TWFE is valid because there is no
    staggering. Instead, focus on heterogeneous effects via subgroup interactions.
  * CONTINUOUS TREATMENT INTENSITY (e.g., teleworkability score):
    de Chaisemartin & D'Haultfoeuille (2020) DIDM can be used as robustness.
  Do NOT require Sun-Abraham/CS when treatment timing is identical for all units.

- PLACEBO TEST: Require at least one placebo test (false treatment timing or
  false treatment group).

*** DESIGN-SPECIFIC ASSUMPTION AUDIT (add ALL relevant items as MUST): ***

For DiD / Event Study:
  - Parallel trends assumption: joint F-test on pre-treatment coefficients
  - No-anticipation assumption: test leads (t-2, t-3) for significance
  - Stable treatment composition: document entry/exit of units
  - Common support across treatment/control groups
  - Sensitivity: Rambachan-Roth (2023) HonestDiD breakdown point

For IV / 2SLS:
  - First-stage F-statistic (>10 rule of thumb, Montiel Olea-Pflueger preferred)
  - Exclusion restriction: justify why instrument affects outcome ONLY through treatment
  - Monotonicity assumption for LATE interpretation
  - Anderson-Rubin confidence intervals if weak instrument concern
  - Over-identification test if multiple instruments (Hansen J-test)

For RDD:
  - McCrary (2008) density test: no manipulation of running variable
  - Bandwidth sensitivity: IK-optimal, CER-optimal, and manual bandwidths
  - Donut-hole specification: exclude observations very close to cutoff
  - Continuity of baseline covariates at cutoff
  - Local polynomial order: linear preferred, quadratic as robustness

For RCT / Experiment:
  - Covariate balance table with SMD and joint F-test
  - Permutation/randomization inference (2000+ reshuffles)
  - Differential attrition check by treatment arm
  - Lee (2009) attrition bounds
  - CONSORT-style flow diagram or sample accounting
  - Effect sizes (Cohen's d) alongside p-values

For Synthetic Control:
  - Pre-treatment fit quality (RMSPE ratio)
  - Predictor balance between treated and synthetic unit
  - Donor pool justification (no spillovers)
  - Permutation inference (in-space placebo)
  - Leave-one-out sensitivity of donor pool

*** SANITY CHECK REQUIREMENTS (add as MUST for all designs): ***
  - Report expected sign based on theory BEFORE running regressions
  - If result contradicts expected sign, require explicit discussion
  - Report effect magnitude in interpretable units (SD, percentage, dollar)
  - Compare magnitude to prior literature estimates
  - Flag any result that implies implausibly large effects (>1 SD shift)

*** FALSIFICATION PLANNING (add as MUST for all causal designs): ***
  - At least ONE placebo outcome (variable that should NOT be affected)
  - At least ONE placebo treatment timing or group
  - Pre-commit to these tests in the strategy memo BEFORE seeing results

Be calibrated: for a descriptive quantile regression, do NOT require
causal identification tests. DO require proper handling of:
- Mass points at zero
- Extreme quantile behavior
- Multiple comparison concerns
- Conditional vs unconditional interpretation

Output a JSON block:
```json
{{
  "code_requirements": [
    {{"category": "inference|specification|robustness|presentation|pitfall",
      "requirement": "...", "priority": "MUST|SHOULD|NICE"}},
    ...
  ],
  "method_warnings": ["..."],
  "must_not_claim": ["..."]
}}
```
"""

    # Run both referees in parallel
    p = get_profile("stage6_referee")
    responses = run_claude_parallel([
        {
            "prompt": domain_prompt,
            "model": p["model"],
            "effort": p["effort"],
            "output_file": strategy_dir / "referee_preview_domain.md",
            "label": "domain-preview",
            "allowed_tools": [],
        },
        {
            "prompt": methods_prompt,
            "model": p["model"],
            "effort": p["effort"],
            "output_file": strategy_dir / "referee_preview_methods.md",
            "label": "methods-preview",
            "allowed_tools": [],
        },
    ], max_workers=2)

    domain_result = extract_json(responses[0]) or {}
    methods_result = extract_json(responses[1]) or {}

    # Merge requirements into a single checklist
    all_requirements = []
    for r in domain_result.get("code_requirements", []):
        r["source"] = "domain"
        all_requirements.append(r)
    for r in methods_result.get("code_requirements", []):
        r["source"] = "methods"
        all_requirements.append(r)

    # Separate by priority
    must = [r for r in all_requirements if r.get("priority") == "MUST"]
    should = [r for r in all_requirements if r.get("priority") == "SHOULD"]
    nice = [r for r in all_requirements if r.get("priority") == "NICE"]

    # Print summary
    print(f"  [3.7] Requirements: {len(must)} MUST, {len(should)} SHOULD, {len(nice)} NICE")
    for r in must:
        print(f"    [MUST] {r.get('category', '?')}: {r.get('requirement', '?')[:100]}")

    # Save merged checklist as markdown for Stage 4 to read
    checklist_lines = [
        "# Referee Preview: Code Requirements Checklist",
        f"\nGenerated: {datetime.now().isoformat()}",
        f"\n## MUST-HAVE ({len(must)} requirements)",
    ]
    for r in must:
        checklist_lines.append(
            f"- [{r.get('source', '?').upper()}] {r.get('category', '?')}: "
            f"{r.get('requirement', '?')}"
        )
    checklist_lines.append(f"\n## SHOULD-HAVE ({len(should)} requirements)")
    for r in should:
        checklist_lines.append(
            f"- [{r.get('source', '?').upper()}] {r.get('category', '?')}: "
            f"{r.get('requirement', '?')}"
        )
    checklist_lines.append(f"\n## NICE-TO-HAVE ({len(nice)} requirements)")
    for r in nice:
        checklist_lines.append(
            f"- [{r.get('source', '?').upper()}] {r.get('category', '?')}: "
            f"{r.get('requirement', '?')}"
        )

    # Add warnings
    data_warnings = domain_result.get("data_warnings", [])
    method_warnings = methods_result.get("method_warnings", [])
    must_not_claim = methods_result.get("must_not_claim", [])

    if data_warnings or method_warnings:
        checklist_lines.append("\n## WARNINGS")
        for w in data_warnings:
            checklist_lines.append(f"- [DATA] {w}")
        for w in method_warnings:
            checklist_lines.append(f"- [METHOD] {w}")

    if must_not_claim:
        checklist_lines.append("\n## MUST NOT CLAIM")
        for c in must_not_claim:
            checklist_lines.append(f"- {c}")

    # Tables and figures
    tables_req = domain_result.get("tables_required", [])
    figures_req = domain_result.get("figures_required", [])
    if tables_req:
        checklist_lines.append("\n## REQUIRED TABLES")
        for t in tables_req:
            checklist_lines.append(f"- {t}")
    if figures_req:
        checklist_lines.append("\n## REQUIRED FIGURES")
        for f in figures_req:
            checklist_lines.append(f"- {f}")

    # ── Filter checklist against verified estimators from Stage 3.3 ──────
    stage3_3 = state["stages"].get("stage3_3", {})
    avail_est = stage3_3.get("available_estimators", {})
    est_warnings = stage3_3.get("estimator_warnings", [])

    if avail_est:
        # Map broken estimators to checklist keywords
        broken_keywords = []
        if not avail_est.get("pyfixest_did2s", True):
            broken_keywords.extend(["did2s", "gardner", "two-step"])
        if not avail_est.get("pyfixest_sunab", True):
            broken_keywords.extend(["sun-abraham", "sun abraham", "sunab",
                                    "interaction-weighted", "interaction weighted"])
        if not avail_est.get("csdid", True) and not avail_est.get("pyfixest_did2s", True):
            broken_keywords.extend(["callaway-sant", "callaway sant", "csdid",
                                    "att(g,t)", "att_gt", "doubly robust"])

        if broken_keywords:
            # Downgrade MUST to SHOULD for requirements that need broken estimators
            downgraded = 0
            for i, line in enumerate(checklist_lines):
                if not line.startswith("- ["):
                    continue
                line_lower = line.lower()
                if any(kw in line_lower for kw in broken_keywords):
                    # Add a note that this was downgraded
                    checklist_lines[i] = line + " [DOWNGRADED: estimator not available in Python]"
                    downgraded += 1

            if downgraded > 0:
                checklist_lines.insert(3,
                    f"\n**NOTE: {downgraded} requirement(s) reference estimators that failed "
                    f"on the real data in Stage 3.3 testing. These have been marked "
                    f"[DOWNGRADED]. Do NOT implement them -- use available alternatives.**\n"
                )
                print(f"  [3.7] Downgraded {downgraded} requirements (broken estimators)")

        # Add available estimators info to checklist
        working = [k for k, v in avail_est.items() if v]
        checklist_lines.append("\n## AVAILABLE PYTHON ESTIMATORS (verified on real data)")
        checklist_lines.append("These estimators were tested on the actual dataset and work:")
        for w in working:
            checklist_lines.append(f"- {w}")
        if est_warnings:
            checklist_lines.append("\nThese FAILED and must NOT be used:")
            for ew in est_warnings:
                checklist_lines.append(f"- {ew}")

    strategy_dir.mkdir(exist_ok=True)
    checklist_path = strategy_dir / "referee_checklist.md"
    checklist_path.write_text("\n".join(checklist_lines), encoding="utf-8")
    print(f"  [saved] {checklist_path}")

    # ── VETO CHECK: detect fatal structural issues ──────────────────────
    # If referees flagged problems that make the design fundamentally unworkable,
    # stop the pipeline here instead of wasting time on doomed code generation.
    fatal_keywords = [
        "cannot support", "impossible", "fundamentally flawed",
        "no pre-treatment", "zero pre-treatment", "no exogenous variation",
        "data structure crisis", "no identification", "not feasible",
        "desk-reject", "desk reject",
    ]
    pitfall_reqs = [r for r in must if r.get("category", "") == "pitfall"]
    fatal_pitfalls = []
    for r in pitfall_reqs:
        req_text = r.get("requirement", "").lower()
        if any(kw in req_text for kw in fatal_keywords):
            fatal_pitfalls.append(r.get("requirement", ""))

    veto = False
    if fatal_pitfalls:
        print(f"\n  {'=' * 60}")
        print(f"  REFEREE PREVIEW — FATAL ISSUES DETECTED")
        print(f"  {'=' * 60}")
        for i, fp in enumerate(fatal_pitfalls, 1):
            print(f"  [{i}] {fp[:200]}")
        print(f"\n  These issues make the current design fundamentally unworkable.")
        print(f"  Proceeding to code generation will likely produce a paper that")
        print(f"  fails peer review with score < 60.")
        print(f"\n  Options:")
        print(f"    PROCEED  - Continue anyway (not recommended)")
        print(f"    BACK     - Return to Stage 2.5 to select a different idea")
        print(f"  {'=' * 60}")
        print("\a", end="", flush=True)

        while True:
            choice = input("\n  >> ").strip().upper()
            if choice == "PROCEED":
                print(f"  [ok] Proceeding despite fatal issues.")
                break
            elif choice == "BACK":
                veto = True
                print(f"  [veto] Returning to Stage 2.5 for idea reselection.")
                break
            else:
                print(f"  Enter PROCEED or BACK.")

    # Save state
    state["stages"]["stage3_7"] = {
        "status": "vetoed" if veto else "completed",
        "n_must": len(must),
        "n_should": len(should),
        "n_nice": len(nice),
        "n_fatal_pitfalls": len(fatal_pitfalls),
        "fatal_pitfalls": fatal_pitfalls[:5],
        "domain_result": domain_result,
        "methods_result": methods_result,
        "checklist_path": str(checklist_path),
        "completed_at": datetime.now().isoformat(),
    }
    save_state(project_dir, state)

    return state
