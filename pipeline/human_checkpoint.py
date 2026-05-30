"""Interactive human-in-the-loop checkpoints for Stages 2.5 and 3.5.

Each checkpoint saves state *before* prompting so that Ctrl-C never loses
progress.  The user can resume with ``--from-stage 2.5`` or ``3.5``.
"""

import textwrap
from typing import Optional


# -- Causal method classification ---------------------------------------------

CAUSAL_METHODS = {
    "did", "diff-in-diff", "difference-in-differences", "difference in differences",
    "twfe", "two-way fixed effects", "event study", "event-study",
    "iv", "instrumental variable", "instrumental variables", "2sls", "tsls",
    "rdd", "regression discontinuity", "regression-discontinuity",
    "rct", "randomized", "experiment",
    "arellano-bond", "arellano bond", "dynamic panel", "gmm",
    "synth", "synthetic control",
    "bunching", "bunching estimator",
    "debiased machine learning", "double machine learning", "double ml",
    "doubleml", "dml", "causal forest", "generalized random forest",
    "grf", "causal tree", "cate", "heterogeneous treatment",
}

PANEL_METHODS = {
    "individual fe", "individual fixed effects", "fixed effects", "panel fe",
    "twfe", "two-way fixed effects", "within-estimator", "within estimator",
    "correlated random effects", "cre", "mundlak",
    "arellano-bond", "arellano bond", "dynamic panel", "gmm",
    "markov", "transition matrix", "survival model", "hazard",
}

DESCRIPTIVE_METHODS = {
    "ols", "wls", "oaxaca", "oaxaca-blinder", "blinder-oaxaca",
    "quantile regression", "rif", "firpo",
    "decomposition", "fairlie",
    "psm", "propensity score", "matching", "cem",
    "heckman", "selection model",
    "probit", "logit", "bivariate probit",
    "descriptive", "correlational",
}


def _classify_method(method_str: str) -> str:
    """Classify a method string as CAUSAL, PANEL, or DESCRIPTIVE."""
    m = method_str.lower().strip()
    # Check causal first (strongest)
    for kw in CAUSAL_METHODS:
        if kw in m:
            return "CAUSAL"
    # Then panel (uses within-individual variation but not necessarily causal)
    for kw in PANEL_METHODS:
        if kw in m:
            return "PANEL"
    # Then descriptive
    for kw in DESCRIPTIVE_METHODS:
        if kw in m:
            return "DESCRIPTIVE"
    return "UNKNOWN"


def _method_tag(classification: str) -> str:
    """Return a colored tag for the method classification."""
    tags = {
        "CAUSAL": "[CAUSAL]",
        "PANEL": "[PANEL]",
        "DESCRIPTIVE": "[DESCRIPTIVE]",
        "UNKNOWN": "[?]",
    }
    return tags.get(classification, "[?]")


# -- Display helpers ----------------------------------------------------------

def _hr(char="-", width=60):
    print(char * width)


def _design_template_for_method(method: str) -> dict:
    """Return method-specific design templates: formal model, execution steps,
    and required validation tests. This lets the human checkpoint show the
    user EXACTLY what each idea would entail before they pick one.
    """
    m = (method or "").lower()

    if "rdd" in m or "regression discontinuity" in m:
        return {
            "model": (
                "Y_i = α + τ·D_i + f(X_i - c) + ε_i\n"
                "        where D_i = 1{X_i ≥ c} (cutoff indicator),\n"
                "              f(·) = local polynomial in distance to cutoff,\n"
                "              τ = LATE causal effect at the cutoff"
            ),
            "exec_steps": [
                "1. Restrict sample to bandwidth around cutoff (use IK/CCT optimal bw)",
                "2. Fit local linear regression with triangular kernel",
                "3. Use rdrobust package: rdrobust(y, x, c=cutoff)",
                "4. Report point estimate, robust SE, optimal bandwidth, N",
                "5. Robustness: McCrary manipulation test, donut RDD, alt polynomials",
            ],
            "key_tests": [
                "McCrary density test (no sorting around cutoff)",
                "Placebo cutoffs (no jumps at non-treatment cutoffs)",
                "Continuity of pre-treatment covariates at cutoff",
            ],
        }
    if "iv" in m or "2sls" in m or "instrumental" in m:
        return {
            "model": (
                "Two-Stage Least Squares (2SLS):\n"
                "        First stage:  D = π₀ + π₁·Z + γX + u\n"
                "        Second stage: Y = β₀ + β₁·D̂ + δX + ε\n"
                "        where D = endogenous regressor,\n"
                "              Z = instrument(s),\n"
                "              D̂ = first-stage prediction"
            ),
            "exec_steps": [
                "1. First stage: regress D on Z and controls; check F-stat > 10",
                "2. Run 2SLS using linearmodels.iv.IV2SLS",
                "3. Report: first-stage F, β₁ point estimate, robust SE, 95% CI",
                "4. Compare OLS vs IV (size of bias correction)",
                "5. Reduced-form: regress Y on Z directly (intent-to-treat)",
            ],
            "key_tests": [
                "Weak instrument test (Stock-Yogo, F > 10 ideal F > 100)",
                "Hansen J overidentification (if multiple instruments)",
                "Exclusion restriction discussion (theory + placebos)",
            ],
        }
    if "did" in m or "difference" in m or "twfe" in m or "event study" in m:
        return {
            "model": (
                "Y_{it} = α_i + γ_t + β·(Treat_i × Post_t) + δX_{it} + ε_{it}\n"
                "        where α_i = unit FE, γ_t = time FE,\n"
                "              β = average treatment effect on treated"
            ),
            "exec_steps": [
                "1. Build panel structure: confirm same units observed pre/post",
                "2. Test parallel trends with leads/lags (event study)",
                "3. Run TWFE: pyfixest.feols('Y ~ treat_post | unit + time')",
                "4. If staggered: use Callaway-Sant'Anna (att_gt) or Sun-Abraham",
                "5. Robustness: alt windows, leave-one-out, Goodman-Bacon",
            ],
            "key_tests": [
                "Pre-trends (joint test of pre-treatment leads)",
                "Placebo: fake treatment timing in pre-period",
                "Negative controls: untreated outcomes",
            ],
        }
    if "rct" in m or "experiment" in m or "randomiz" in m:
        return {
            "model": (
                "Y_i = α + β·T_i + γX_i + ε_i\n"
                "        where T_i = random treatment assignment,\n"
                "              β = ITT (intent-to-treat) effect"
            ),
            "exec_steps": [
                "1. Verify random assignment via balance test on covariates",
                "2. Estimate ITT: OLS with HC2 robust SEs (cluster if assigned at group)",
                "3. Report: balance table, ITT point estimate, MDE, Cohen's d",
                "4. Heterogeneity: pre-specified interactions only (avoid p-hacking)",
                "5. Robustness: permutation/randomization inference",
            ],
            "key_tests": [
                "Balance F-test (joint orthogonality of covariates to treatment)",
                "Differential attrition test",
                "Lee bounds for worst-case selective attrition",
            ],
        }
    if any(k in m for k in [
        "dml", "double machine", "debiased machine", "causal forest",
        "generalized random forest", "grf", "causal tree", "cate",
        "heterogeneous treatment",
    ]):
        return {
            "model": (
                "Replication + HTE:\n"
                "        Step 1: reproduce original ATE / baseline estimand\n"
                "        Step 2: estimate nuisance functions E[Y|X], E[D|X]\n"
                "        Step 3: cross-fit orthogonal score for ATE/CATE\n"
                "        Step 4: summarize CATE heterogeneity across pre-treatment X"
            ),
            "exec_steps": [
                "1. Reconstruct the original sample restrictions and baseline ATE",
                "2. Define treatment, outcome, controls, and HTE covariates before estimation",
                "3. Run DML or causal forest with cross-fitting / honest splitting",
                "4. Compare replicated ATE against the paper's reported estimate if available",
                "5. Report CATE distribution and top heterogeneity splits with uncertainty",
            ],
            "key_tests": [
                "Baseline ATE replication before any HTE claims",
                "Overlap / propensity diagnostics",
                "Sensitivity to nuisance learners and covariate sets",
                "No post-treatment variables in HTE covariates",
            ],
        }
    # Default / panel FE / observational
    return {
        "model": (
            "Y_{it} = α_i + δ_t + β·X_{it} + γZ_{it} + ε_{it}\n"
            "        where α_i = entity FE absorbs time-invariant heterogeneity"
        ),
        "exec_steps": [
            "1. Profile data structure (panel? cross-section?)",
            "2. Decide identification (FE? instruments? matching?)",
            "3. Run main spec + robustness with controls added stepwise",
            "4. Report: coefficient, SE, R², specification curve",
        ],
        "key_tests": [
            "Specification curve (varying controls)",
            "Oster (2019) coefficient stability (delta)",
            "Sensitivity to outliers",
        ],
    }


def _expected_score_band(idea: dict, has_external_data: bool) -> str:
    """Heuristic peer-review score band based on identification level + execution complexity.

    External data merges add 2-3 hrs of work and a small execution risk
    (merge keys, missing observations), so we report a slightly wider lower
    bound when external data is required.
    """
    id_level = idea.get("identification_level", "").upper()
    id_score = idea.get("identification", 0)
    if id_level == "A" or id_score >= 4:
        if has_external_data:
            return "78-88 (top field journal range; -2-4 pts execution risk from external merge)"
        return "82-90 (top field journal range)"
    if id_level == "B" or id_score == 3:
        if has_external_data:
            return "70-80 (general field journal range; external merge adds risk)"
        return "75-82 (general field journal range)"
    return "65-75 (specialty journal at best)"


def _print_idea(idx: int, idea: dict):
    """Pretty-print one research idea with FULL implementation detail.

    Shows: design (formal model), identification logic, execution steps,
    data needs, pros/cons, expected peer-review score band, AND a project
    application workflow so the user can pick informedly.
    """
    method = idea.get('method', 'N/A')
    classification = _classify_method(method)
    tag = _method_tag(classification)

    id_level = idea.get("identification_level", "")
    id_score = idea.get("identification", "")
    id_tag = f"[ID: {id_level}]" if id_level else ""

    # Header (compact)
    print(f"\n  ╔══ [{idx}] {idea.get('title', 'Untitled')[:65]} ══╗")
    print(f"      Score: {idea.get('total_score', '?')}  "
          f"(N={idea.get('novelty','?')} F={idea.get('feasibility','?')} "
          f"I={idea.get('impact','?')} ID={id_score if id_score else '?'} "
          f"EE={idea.get('expected_effect', '?')})")
    print(f"      Method: {method}  {tag} {id_tag}")

    # Research question
    rq = idea.get('research_question', 'N/A')
    rq_wrapped = textwrap.fill(rq, width=70, initial_indent="      RQ: ",
                                subsequent_indent="          ")
    print(rq_wrapped)

    # Pitch (1-line summary)
    pitch = idea.get("pitch", "")
    if pitch:
        wrapped = textwrap.fill(pitch, width=70, initial_indent="      Pitch: ",
                                subsequent_indent="             ")
        print(wrapped)

    # ── DETAILED SECTIONS ─────────────────────────────────────────────
    template = _design_template_for_method(method)

    # Formal model
    print()
    print(f"      ── FORMAL MODEL ──")
    for line in template["model"].splitlines():
        print(f"      {line}")

    # Identification source
    id_source = idea.get("identification_source", "")
    if id_source:
        print()
        print(f"      ── IDENTIFICATION LOGIC ──")
        wrapped = textwrap.fill(id_source, width=70,
                                initial_indent="      ",
                                subsequent_indent="      ")
        print(wrapped)

    # Data sources + external data check
    data = idea.get("data_sources", [])
    has_external = False
    if data:
        print()
        print(f"      ── DATA NEEDED ──")
        for d in data:
            d_lower = d.lower()
            is_external = any(k in d_lower for k in [
                "osiptel", "sbs", "minedu", "bcrp", "external", "registry",
                "shapefile", "merge", "publicly available", "public"
            ])
            marker = "[EXT]" if is_external else "[OK ]"
            if is_external:
                has_external = True
            wrapped = textwrap.fill(
                f"{marker} {d}", width=70,
                initial_indent="      ", subsequent_indent="            "
            )
            print(wrapped)
        if has_external:
            print(f"      ⚠ Requires merging external data (added work)")

    # Execution steps
    print()
    print(f"      ── EXECUTION STEPS ──")
    for step in template["exec_steps"]:
        wrapped = textwrap.fill(step, width=70,
                                initial_indent="      ",
                                subsequent_indent="         ")
        print(wrapped)

    # Required validation tests
    print()
    print(f"      ── KEY VALIDATION TESTS ──")
    for test in template["key_tests"]:
        print(f"      • {test}")

    # First experiment (if specified by Stage 2)
    first_exp = idea.get("first_experiment", "")
    if first_exp:
        print()
        print(f"      ── WEEK 1 ACTION ──")
        wrapped = textwrap.fill(first_exp, width=70,
                                initial_indent="      ",
                                subsequent_indent="      ")
        print(wrapped)

    # Project workflow (how to actually apply this idea end-to-end)
    print()
    print(f"      ── HOW THIS PROJECT WOULD UNFOLD ──")
    workflow_steps = [
        "Stage 4 (auto):    Generate scripts using the FORMAL MODEL above",
    ]
    if has_external:
        workflow_steps.insert(0,
            "Stage 4 (manual):  Merge external data first (~1-3 hours)")
    workflow_steps.extend([
        "Stage 4 (auto):    Run 00_clean → 01_main → 02_robustness → 03_output",
        "Stage 4 (auto):    Validation runs the KEY TESTS automatically",
        "Stage 5 (auto):    Write LaTeX paper with Tables 1-7 + 5 Figures",
        "Stage 6 (auto):    6 peer-review agents score the paper",
        "Stage 7 (auto):    Final report + journal targeting recommendation",
    ])
    for step in workflow_steps:
        print(f"      {step}")

    # Expected peer-review score band
    print()
    print(f"      ── EXPECTED PEER-REVIEW SCORE ──")
    print(f"      {_expected_score_band(idea, has_external)}")

    print(f"      ╚══════════════════════════════════════════════════════════════════════╝")


def _print_strategy(strategy: dict | str):
    """Pretty-print the proposed identification strategy."""
    if isinstance(strategy, str):
        for line in strategy.splitlines():
            print(f"  {line}")
        return
    print(f"  Method: {strategy.get('method', 'N/A')}")
    print(f"  Design: {strategy.get('design', 'N/A')}")
    print(f"  Data: {strategy.get('data_sources', 'N/A')}")
    pap = strategy.get("pre_analysis_plan", "")
    if pap:
        wrapped = textwrap.fill(pap, width=56, initial_indent="  PAP: ", subsequent_indent="       ")
        print(wrapped)


# -- Stage 2.5: Idea Selection -----------------------------------------------

def idea_selection(top_ideas: list[dict]) -> dict:
    """Present the top 3 ideas and let the researcher choose.

    Returns
    -------
    dict
        ``{"action": "SELECT"|"COMBINE"|"REJECT", "selected_idea": {...} | None}``
    """
    _hr("=")
    print("STAGE 2.5 - IDEA SELECTION (human checkpoint)")
    _hr("=")
    print("\nThe pipeline generated the following top ideas:\n")

    for i, idea in enumerate(top_ideas[:3], 1):
        _print_idea(i, idea)

    # ── Identification quality audit ──────────────────────────────────────
    top3 = top_ideas[:3]
    classifications = [_classify_method(idea.get("method", "")) for idea in top3]
    n_causal = sum(1 for c in classifications if c == "CAUSAL")
    n_panel = sum(1 for c in classifications if c == "PANEL")
    n_descriptive = sum(1 for c in classifications if c in ("DESCRIPTIVE", "UNKNOWN"))

    # New: check identification levels
    id_levels = [idea.get("identification_level", "C") for idea in top3]
    # id_scores used for future weighted audit
    n_level_a = sum(1 for l in id_levels if l == "A")
    n_level_b = sum(1 for l in id_levels if l == "B")
    n_level_c = sum(1 for l in id_levels if l == "C")

    print()
    _hr("-")
    print("IDENTIFICATION QUALITY AUDIT")
    _hr("-")
    print(f"  Level A (strong - control group):     {n_level_a} of 3")
    print(f"  Level B (moderate - dose variation):   {n_level_b} of 3")
    print(f"  Level C (weak - before/after only):    {n_level_c} of 3")
    print(f"  Causal methods: {n_causal} | Panel: {n_panel} | Descriptive: {n_descriptive}")

    if n_level_a + n_level_b >= 2:
        print(f"\n  [ok] {n_level_a + n_level_b} of 3 ideas have credible identification (A or B).")
        print(f"       These designs are competitive for top field journals.")
    elif n_level_a + n_level_b == 1:
        print(f"\n  [!] WARNING: Only 1 of 3 ideas has credible identification.")
        print(f"      Select the Level A/B idea for the strongest paper.")
        print(f"      Level C ideas face a score ceiling of ~75/100.")
    else:
        print(f"\n  [!!] WARNING: ALL ideas are Level C (weak identification).")
        print(f"       No idea has a credible control group or dose variation.")
        print(f"       Score ceiling: ~75/100 regardless of execution quality.")
        print(f"\n       Options:")
        print(f"       - REJECT ALL and provide data with cross-sectional treatment variation")
        print(f"       - Proceed knowing the paper will be descriptive, not causal")

        print(f"\n       To improve: find data where some units are MORE treated than others")
        print(f"       (geographic variation, policy bans, infrastructure differences)")

    print()
    _hr()
    print("Options:")
    print("  SELECT  <number>   - proceed with that idea  (e.g. SELECT 1)")
    print("  COMBINE <n> <m>    - merge two ideas          (e.g. COMBINE 1 2)")
    print("  REJECT ALL         - discard all, re-run Stage 2")
    _hr()
    print("\a", end="", flush=True)  # Terminal bell — user input needed

    while True:
        choice = input("\n>> ").strip().upper()

        if choice.startswith("SELECT"):
            parts = choice.split()
            if len(parts) == 2 and parts[1].isdigit():
                idx = int(parts[1])
                if 1 <= idx <= len(top_ideas[:3]):
                    selected = top_ideas[idx - 1]
                    print(f"\n  [ok] Selected idea {idx}: {selected.get('title')}")
                    return {"action": "SELECT", "selected_idea": selected}
            print("  Usage: SELECT <1|2|3>")

        elif choice.startswith("COMBINE"):
            parts = choice.split()
            if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                a, b = int(parts[1]), int(parts[2])
                limit = len(top_ideas[:3])
                if 1 <= a <= limit and 1 <= b <= limit and a != b:
                    idea_a = top_ideas[a - 1]
                    idea_b = top_ideas[b - 1]
                    combined = {
                        "title": f"{idea_a.get('title', '')} + {idea_b.get('title', '')}",
                        "research_question": f"Combined: {idea_a.get('research_question','')} | {idea_b.get('research_question','')}",
                        "method": f"{idea_a.get('method','')}/{idea_b.get('method','')}",
                        "data_sources": list(set(idea_a.get("data_sources", []) + idea_b.get("data_sources", []))),
                        "novelty": max(idea_a.get("novelty", 0), idea_b.get("novelty", 0)),
                        "feasibility": min(idea_a.get("feasibility", 0), idea_b.get("feasibility", 0)),
                        "impact": max(idea_a.get("impact", 0), idea_b.get("impact", 0)),
                        "pitch": f"{idea_a.get('pitch','')} - merged with - {idea_b.get('pitch','')}",
                        "first_experiment": idea_a.get("first_experiment", idea_b.get("first_experiment", "")),
                    }
                    print(f"\n  [ok] Combined ideas {a} & {b}")
                    return {"action": "COMBINE", "selected_idea": combined}
            print("  Usage: COMBINE <n> <m>  (e.g. COMBINE 1 3)")

        elif choice == "REJECT ALL":
            print("\n  [x] All ideas rejected. Pipeline will re-run Stage 2.")
            return {"action": "REJECT", "selected_idea": None}

        else:
            print("  Unrecognised command. Type SELECT <n>, COMBINE <n> <m>, or REJECT ALL.")


# -- Stage 3.5: Data Source Selection ----------------------------------------

def data_source_selection(
    main_data_name: str,
    external_sources: list[str],
    external_justifications: list[dict] | None = None,
) -> dict:
    """Ask the user whether to work with only the main dataset or also external data.

    Parameters
    ----------
    main_data_name : str
        Name of the main dataset file.
    external_sources : list[str]
        Names/descriptions of proposed external data sources.
    external_justifications : list[dict] | None
        For each external source: {"source", "role", "impact_without"}.

    Returns
    -------
    dict
        ``{"choice": 1|2, "use_external": bool}``
    """
    _hr("=")
    print("STAGE 3.5 - DATA SOURCE SELECTION")
    _hr("=")

    print(f"\n  Main dataset: {main_data_name}")
    if external_sources:
        print(f"\n  External sources proposed by the strategy:")
        if external_justifications:
            for j in external_justifications:
                print(f"\n    * {j.get('source', '?')}")
                print(f"      Role: {j.get('role', 'N/A')}")
                print(f"      Without it: {j.get('impact_without', 'N/A')}")
        else:
            for i, src in enumerate(external_sources, 1):
                print(f"    {i}. {src}")

        # Show recommendation
        if external_justifications:
            critical = [j for j in external_justifications if j.get("critical", False)]
            if critical:
                print(f"\n  [!] {len(critical)} source(s) are CRITICAL for the identification strategy.")
                print(f"      Without them, the strategy will need to be adapted.")
            else:
                print(f"\n  [i] External sources are optional — they strengthen the study")
                print(f"      but the main analysis can proceed without them.")
    else:
        print(f"\n  No external datasets are needed for this strategy.")

    print()
    _hr()
    print("Options:")
    print(f"  1  -  Work ONLY with the main dataset ({main_data_name})")
    if external_sources:
        print(f"  2  -  Work with the main dataset + external datasets")
    _hr()
    print("\a", end="", flush=True)  # Terminal bell — user input needed

    while True:
        choice = input("\n>> ").strip()
        if choice == "1":
            print(f"\n  [ok] Dataset fixed: {main_data_name}")
            print(f"  The strategy will use ONLY this dataset.")
            return {"choice": 1, "use_external": False}
        elif choice == "2":
            if not external_sources:
                print("  [warn] No external sources were proposed. Defaulting to option 1.")
                print(f"\n  [ok] Dataset fixed: {main_data_name}")
                return {"choice": 1, "use_external": False}
            print(f"\n  [ok] Will attempt to download and merge external datasets.")
            return {"choice": 2, "use_external": True}
        else:
            print("  Please enter 1 or 2.")


# -- Stage 3.5: Strategy Review ----------------------------------------------

def _diagnose_strategy(
    strategy: dict | str,
    main_data_name: str = "",
    data_validation: dict | None = None,
) -> None:
    """Analyze the strategy and print a quality ceiling diagnosis.

    Detects structural limitations in the identification strategy that
    will cap the final paper score, BEFORE the user commits to code and
    writing. Also recommends the optimal strategy for ~95/100 and lists
    exactly which data files the user would need to provide.
    """
    if isinstance(strategy, str):
        text = strategy.lower()
        method = ""
        design = ""
        title = ""
    else:
        text = " ".join(str(v) for v in strategy.values()).lower()
        method = str(strategy.get("method", "")).lower()
        design = str(strategy.get("design", "")).lower()
        title = str(strategy.get("title", ""))

    warnings = []
    ceiling = 100
    recommended_design = []
    recommended_data = []

    # Detect which ENAHO year from main dataset name
    import re
    year_match = re.search(r"20\d{2}", main_data_name or text)
    year = year_match.group() if year_match else "YYYY"

    # ── Cross-sectional design ──
    is_cross_section = "cross-section" in text or "cross section" in text
    has_panel = "panel" in text or "diff-in-diff" in text or "rdd" in text
    if is_cross_section and not has_panel:
        warnings.append({
            "issue": "Cross-sectional design — no causal identification",
            "impact": "Score ceiling ~70. Referees will flag all causal language.",
            "fix": "Use panel data (ENAHO rotating panel) or quasi-experimental design",
        })
        ceiling -= 30
        recommended_design.append("Panel (ENAHO rotating panel, DiD/event-study)")
        # Need multiple years of Module 500
        for y in range(int(year) - 2, int(year) + 1):
            fname = f"Enaho01a-{y}-500.csv"
            recommended_data.append({
                "file": fname,
                "module": f"Module 500 (Employment) — {y}",
                "purpose": "Build rotating panel via CONGLOME+VIVIENDA+HOGAR+CODPERSO",
                "have": fname.lower() in main_data_name.lower() if main_data_name else False,
            })

    # ── PSM without actual treatment history ──
    if ("psm" in method or "propensity score" in method or "matching" in method):
        if not has_panel:
            warnings.append({
                "issue": "PSM on cross-section — identifies associations, not causal effects",
                "impact": "Referees will require reframing as 'risk-profile gap', not 'penalty'",
                "fix": "Panel data to observe actual NEET->employment transitions",
            })
            ceiling -= 15
            if not recommended_design:
                recommended_design.append("Diff-in-Differences on NEET->employment transitions")

    # ── Heckman without clear instrument ──
    if "heckman" in method or "selection" in method:
        if "instrument" not in text and "exclusion restriction" not in text:
            warnings.append({
                "issue": "Heckman selection model without specified exclusion restriction",
                "impact": "Weak instrument -> Heckman demoted to robustness check",
                "fix": "Identify credible instrument (e.g. local labor demand shock)",
            })
            ceiling -= 10
            recommended_design.append("Heckman with credible instrument (local labor demand shock)")

    # ── Multinomial logit IIA concern ──
    if "multinomial logit" in method or "mnl" in method or "mlogit" in method:
        if "nested" not in method and "mixed logit" not in method:
            warnings.append({
                "issue": "Multinomial logit assumes IIA — may not hold for close substitutes",
                "impact": "If IIA test fails, referees will require nested logit",
                "fix": "Include nested logit as primary or robustness specification",
            })
            ceiling -= 5
            recommended_design.append("Nested logit for multinomial NEET determinants")

    # ── Small wage sample ──
    if "wage" in text and ("module 500" in text or "p524" in text):
        if "module 600" not in text and "ingresos" not in text:
            warnings.append({
                "issue": "Wage data from Module 500 only — likely small effective sample",
                "impact": "Module 500 has wages only for dependent workers (~5% of youth)",
                "fix": "Merge with Module 500 income variables or use total income",
            })
            ceiling -= 5
            recommended_design.append("Panel wage equation with individual fixed effects")

    # ── Missing education module ──
    if "p50410" in text and "p306" not in text:
        warnings.append({
            "issue": "Student classification via P50410 (reference-week) instead of P306 (enrollment)",
            "impact": "NEET rate will be ~42% instead of ~20%. Referees will flag immediately.",
            "fix": "Merge Module 300 (Education) for P306 enrollment status",
        })
        ceiling -= 10
        recommended_data.append({
            "file": f"Enaho01a-{year}-300.csv",
            "module": f"Module 300 (Education) — {year}",
            "purpose": "P306 enrollment status for accurate NEET classification",
            "have": False,
        })

    # ── Missing household composition for Fairlie ──
    if "fairlie" in method or "fairlie" in text or ("decomposition" in method and "gender" in text):
        if "module 200" not in text and "children" not in text and "caregiving" not in text:
            warnings.append({
                "issue": "Fairlie decomposition without caregiving/children variables",
                "impact": "Large 'unexplained' component may be due to omitted variables, not discrimination",
                "fix": "Merge Module 200 (Household) for children under 5, dependency ratio",
            })
            ceiling -= 5
            recommended_data.append({
                "file": f"Enaho01-{year}-200.csv",
                "module": f"Module 200 (Household) — {year}",
                "purpose": "Children under 5, dependency ratio for Fairlie decomposition",
                "have": False,
            })

    # Recommend Module 300 only if not already in main dataset or recommendations
    mod300_in_data = any("300" in d.get("module", "") for d in recommended_data)
    mod300_in_main = "300" in (main_data_name or "")
    if not mod300_in_data and not mod300_in_main:
        recommended_data.append({
            "file": f"Enaho01a-{year}-300.csv",
            "module": f"Module 300 (Education) — {year}",
            "purpose": "P306 enrollment for accurate NEET classification",
            "have": False,
        })

    # ── Data-grounded variable validation ──
    # If Stage 3.5 ran a cross-file variable check, fold the result into the
    # warnings here. Missing CRITICAL variables (treatment / assignment /
    # cohort indicators) are a hard blocker — the proposed estimator cannot
    # run at all, so we cap the ceiling regardless of how clean the design
    # would be in the abstract. Missing soft variables become regular
    # warnings.
    if data_validation and data_validation.get("ran"):
        critical_missing = data_validation.get("critical_missing") or []
        soft_missing = [
            t for t in (data_validation.get("missing") or [])
            if t not in critical_missing
        ]
        files_scanned = data_validation.get("files_scanned") or []
        n_columns = data_validation.get("n_columns", 0)

        if critical_missing:
            warnings.append({
                "issue": (
                    f"Strategy references variables that DO NOT EXIST in the data: "
                    f"{', '.join(critical_missing)}"
                ),
                "impact": (
                    f"These look like treatment/assignment indicators required by "
                    f"the proposed estimator. Searched {len(files_scanned)} file(s) "
                    f"({', '.join(files_scanned) or 'none'}) covering {n_columns} "
                    f"unique columns. The estimator cannot run on data that lacks "
                    f"its core identifying variables."
                ),
                "fix": (
                    "Either (a) point the pipeline at the file(s) that contain "
                    "these variables, (b) extract them from the source replication "
                    "package, or (c) reformulate the strategy to use variables that "
                    "ARE present in the data."
                ),
            })
            # Hard cap — no amount of methodological elegance saves a strategy
            # whose treatment indicator doesn't exist.
            ceiling = min(ceiling, 30)

        if soft_missing:
            # Show only the first few to avoid spamming the console with
            # every false positive from the variable tokenizer.
            shown = soft_missing[:8]
            more = f" (+{len(soft_missing) - len(shown)} more)" if len(soft_missing) > len(shown) else ""
            warnings.append({
                "issue": (
                    f"Strategy mentions variables not found in any data file: "
                    f"{', '.join(shown)}{more}"
                ),
                "impact": (
                    "May be informal references rather than actual column names, "
                    "but worth confirming before Stage 4 generates code that "
                    "expects them."
                ),
                "fix": (
                    "Confirm these are variable names; if so, locate the file "
                    "that contains them. If they are paper/method names, ignore."
                ),
            })

    # ── Print diagnosis ──
    print()
    _hr("-")
    print("STRATEGY QUALITY DIAGNOSIS")
    _hr("-")

    ceiling = max(ceiling, 0)
    if ceiling >= 85:
        tier = "STRONG — publishable in top field journals"
    elif ceiling >= 75:
        tier = "GOOD — publishable in solid applied journals"
    elif ceiling >= 65:
        tier = "ACCEPTABLE — publishable in regional/applied journals"
    else:
        tier = "LIMITED — significant methodological constraints"

    print(f"\n  Estimated score ceiling: ~{ceiling}/100 ({tier})")

    # Surface what the data validator actually scanned, even on the happy path,
    # so the user can confirm the right files were considered.
    if data_validation and data_validation.get("ran"):
        files_scanned = data_validation.get("files_scanned") or []
        n_cols = data_validation.get("n_columns", 0)
        n_found = len(data_validation.get("found") or [])
        n_missing = len(data_validation.get("missing") or [])
        print(
            f"\n  Data check: scanned {len(files_scanned)} file(s) "
            f"({n_cols} unique columns); "
            f"matched {n_found} strategy variable(s), {n_missing} not found."
        )
        if files_scanned:
            print(f"  Files: {', '.join(files_scanned)}")

    if warnings:
        print(f"\n  Structural limitations detected ({len(warnings)}):\n")
        for i, w in enumerate(warnings, 1):
            print(f"  {i}. {w['issue']}")
            print(f"     Impact: {w['impact']}")
            print(f"     To improve: {w['fix']}")
            print()
        print(f"  These limitations are inherent to the research design.")
        print(f"  They CANNOT be fixed by editing text — only by changing")
        print(f"  the data or methodology.")
    else:
        print(f"\n  No major structural limitations detected.")
        print(f"  Strategy has strong identification potential.")

    # ── Recommended strategy for ~95/100 ──
    if warnings:
        print(f"\n  {'=' * 60}")
        print(f"  RECOMMENDED STRATEGY FOR ~95/100")
        print(f"  {'=' * 60}")
        print()
        print(f"  If you want the highest possible score, the optimal")
        print(f"  identification strategy would be:")
        print()
        if recommended_design:
            for i, d in enumerate(recommended_design):
                label = ["Design", "Primary", "Secondary", "Wage", "Selection", "Decomp"][min(i, 5)]
                print(f"  {label:12s}: {d}")
        print()

        # ── Data needed ──
        # Deduplicate by file name
        seen_files = set()
        unique_data = []
        for d in recommended_data:
            if d["file"] not in seen_files:
                seen_files.add(d["file"])
                unique_data.append(d)

        if unique_data:
            print(f"  Data you would need to provide:")
            border = "+" + "-" * 62 + "+"
            print(f"  {border}")
            for d in unique_data:
                have_tag = " (already have)" if d["have"] else ""
                print(f"  |  {d['module']}{have_tag}")
                print(f"  |    File: {d['file']}")
                print(f"  |    Purpose: {d['purpose']}")
                print(f"  |")
            print(f"  |  Download: https://proyectos.inei.gob.pe/microdatos/")
            print(f"  |  Select ENAHO -> year -> module")
            print(f"  {border}")

    _hr("-")


def strategy_review(
    strategy: dict | str,
    main_data_name: str = "",
    data_validation: dict | None = None,
) -> dict:
    """Present the proposed identification strategy for human approval.

    Parameters
    ----------
    strategy : dict or str
        The proposed identification strategy.
    main_data_name : str
        Name of the main dataset file (used for year detection in diagnosis).
    data_validation : dict, optional
        Result of cross-checking the strategy against the actual data files
        (produced by ``stage3_5_review._validate_strategy_against_data``).
        When supplied, missing-variable warnings are folded into the
        diagnosis and a hard ceiling cap is applied if critical variables
        are absent from the data.

    Returns
    -------
    dict
        ``{"action": "APPROVE"|"REFORMULATE"|"REJECT", "notes": str}``
    """
    _hr("=")
    print("STAGE 3.5 - STRATEGY REVIEW (human checkpoint)")
    _hr("=")
    print("\nProposed identification strategy:\n")
    _print_strategy(strategy)

    # Show quality diagnosis BEFORE asking for decision
    _diagnose_strategy(
        strategy,
        main_data_name=main_data_name,
        data_validation=data_validation,
    )

    print()
    _hr()
    print("Options:")
    print("  APPROVE                - accept the strategy as-is")
    print("  REFORMULATE            - upgrade to recommended strategy (provide data listed above)")
    print("  REJECT                 - discard and go back to Stage 2.5")
    _hr()
    print("\a", end="", flush=True)  # Terminal bell — user input needed

    while True:
        choice = input("\n>> ").strip().upper()

        if choice == "APPROVE":
            print("\n  [ok] Strategy approved. Proceeding to Stage 4.")
            return {"action": "APPROVE", "notes": ""}

        elif choice == "REFORMULATE":
            print("\n  Enter your revised strategy (end with an empty line):")
            lines = []
            while True:
                line = input("  | ")
                if not line:
                    break
                lines.append(line)
            notes = "\n".join(lines)
            print("\n  [ok] Strategy reformulated. Pipeline will use your version.")
            return {"action": "REFORMULATE", "notes": notes}

        elif choice == "REJECT":
            print("\n  [x] Strategy rejected. Pipeline will return to Stage 2.5.")
            return {"action": "REJECT", "notes": ""}

        else:
            print("  Unrecognised command. Type APPROVE, REFORMULATE, or REJECT.")
