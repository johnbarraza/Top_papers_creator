"""Stage 2 — Ideation (research-junshi).

Generates 8-10 research ideas from seed papers, scores them, and selects the top 3.
"""

from datetime import datetime
from pathlib import Path

from ..config import get_profile
from ..claude_runner import run_claude
from ..json_utils import extract_json
from ..state import save_state


def run(project_dir: Path, state: dict) -> dict:
    """Execute Stage 2: idea generation."""
    stage1 = state["stages"].get("stage1", {})
    topic = stage1.get("topic", "academic research")

    # Include dataset context — prefer downloaded profiles (Stage 1.5) over recommendations
    stage1_5 = state["stages"].get("stage1_5", {})
    downloaded_datasets = stage1_5.get("downloaded_datasets", [])
    recommended_sources = stage1.get("recommended_data_sources", [])
    sources_context = ""

    if downloaded_datasets:
        # Stage 1.5 downloaded and profiled datasets — use REAL variables
        sources_context = "\n\n## DOWNLOADED DATASETS (with real variables)\n\n"
        sources_context += (
            "These datasets have been downloaded and profiled. "
            "Your ideas MUST use variables that ACTUALLY EXIST in these datasets. "
            "For each idea, specify WHICH dataset and WHICH variables it uses.\n\n"
        )
        for i, ds in enumerate(downloaded_datasets, 1):
            profile = ds.get("profile", {})
            sources_context += f"### Dataset {i}: {ds.get('name', '?')}\n"
            sources_context += f"- File: {Path(ds.get('local_path', '?')).name}\n"
            if profile:
                sources_context += f"- Rows: {profile.get('rows', '?'):,}\n"
                sources_context += f"- Columns: {profile.get('cols', '?')}\n"
                sources_context += f"- Structure: {profile.get('structure', '?')}\n"
                id_cols = profile.get("id_cols", [])
                if id_cols:
                    sources_context += f"- ID columns: {', '.join(id_cols[:5])}\n"
                time_cols = profile.get("time_cols", [])
                if time_cols:
                    sources_context += f"- Time columns: {', '.join(time_cols[:5])}\n"
                columns = profile.get("columns", [])
                if columns:
                    # Rank columns by likely relevance: outcome/treatment/cluster
                    # keywords first, then ID/time, then alphabetical. This
                    # ensures the LLM sees the most important variables in
                    # large datasets (e.g., 618 cols) where naive truncation
                    # would miss the key vars.
                    OUTCOME_KW = ("income", "wage", "employ", "score", "earn",
                                  "test", "y_", "outcome", "result", "consum",
                                  "spend", "rev", "profit", "growth", "rate",
                                  "ratio", "freq", "count", "n_")
                    TREAT_KW = ("treat", "vbt", "assign", "arm", "control",
                                "random", "intervent", "voucher", "lottery",
                                "post_", "did_", "polic", "reform")
                    ID_KW = ("_id", "cluster", "village", "district", "strata",
                             "year", "month", "wave", "round", "time", "date")
                    BASELINE_KW = ("base_", "_base", "pre_", "_pre", "lag")

                    def _col_rank(col: str) -> int:
                        lc = col.lower()
                        if any(k in lc for k in TREAT_KW): return 0
                        if any(k in lc for k in OUTCOME_KW): return 1
                        if any(k in lc for k in ID_KW): return 2
                        if any(k in lc for k in BASELINE_KW): return 3
                        return 4

                    ranked_cols = sorted(columns, key=_col_rank)
                    top_cols = ranked_cols[:50]
                    sources_context += f"- Variables (top 50 ranked by likely relevance): "
                    sources_context += f"{', '.join(top_cols)}\n"
                    if len(columns) > 50:
                        sources_context += f"  ... ({len(columns)} total)\n"
                data_summary = profile.get("data_summary", "")
                if data_summary:
                    sources_context += f"\n**Data summary:**\n{data_summary}\n"
            sources_context += "\n"

        # Also mention datasets that couldn't be downloaded
        not_downloaded = stage1_5.get("not_downloaded", [])
        if not_downloaded:
            sources_context += "### Datasets NOT downloaded (available for manual download):\n"
            for ds in not_downloaded:
                sources_context += f"- {ds.get('name', '?')} — {ds.get('url', 'N/A')}\n"
            sources_context += "\n"

    elif recommended_sources and not stage1.get("data_profile"):
        # Fallback: Stage 1 recommendations without download (no Stage 1.5)
        sources_context = "\n\n## AVAILABLE DATASETS (from Stage 1 Discovery)\n\n"
        sources_context += (
            "These datasets were identified as the best available for this topic. "
            "Your ideas MUST be designed to work with at least one of these datasets. "
            "For each idea, specify WHICH dataset(s) it uses.\n\n"
        )
        for i, ds in enumerate(recommended_sources[:3], 1):
            sources_context += f"### Dataset {i}: {ds.get('name', '?')}\n"
            sources_context += f"- Provider: {ds.get('provider', '?')}\n"
            sources_context += f"- URL: {ds.get('url', 'N/A')}\n"
            sources_context += f"- Structure: {ds.get('data_structure', '?')}\n"
            sources_context += f"- Time span: {ds.get('time_span', '?')}\n"
            nat_exp = ds.get("natural_experiment", "")
            if nat_exp:
                sources_context += f"- Natural experiment: {nat_exp}\n"
            methods = ds.get("causal_methods_enabled", [])
            if methods:
                sources_context += f"- Causal methods enabled: {', '.join(methods)}\n"
            sources_context += f"- Access: {ds.get('access', '?')}\n"
            sources_context += f"- Format: {ds.get('format', '?')}\n\n"

    # If Path B, include rich data context with structure constraints
    data_profile = stage1.get("data_profile")
    data_context = ""
    if data_profile:
        cols = ", ".join(data_profile.get("columns", [])[:25])
        if len(data_profile.get("columns", [])) > 25:
            cols += f", ... ({data_profile['cols']} total)"
        structure = data_profile.get("structure", "unknown")
        panel_details = data_profile.get("panel_details", {})

        # Build structure-specific constraints
        wide_panel = data_profile.get("wide_panel")
        if structure == "wide-panel" and wide_panel:
            core_sample = ", ".join(panel_details.get("core_vars_sample", [])[:10])
            suffixes = panel_details.get("year_suffixes", [])
            years = panel_details.get("time_values", [])
            unsuffixed = ", ".join(panel_details.get("unsuffixed_cols", [])[:15])
            vars_per = panel_details.get("vars_per_period", {})
            vars_per_str = ", ".join(f"{s}: {n} vars" for s, n in vars_per.items())
            structure_block = (
                f"DATA STRUCTURE: WIDE-FORMAT PANEL — time encoded in column name suffixes.\n"
                f"  Year suffixes: {', '.join(suffixes)}\n"
                f"  Corresponding years: {years}\n"
                f"  Time periods: {panel_details.get('n_time_periods', '?')}\n"
                f"  Variables per period: {vars_per_str}\n"
                f"  Core variables (shared across all periods): {panel_details.get('n_core_vars', '?')}\n"
                f"  Sample base vars: {core_sample}\n"
                f"  Time-invariant/ID columns: {unsuffixed}\n"
                f"\n"
                f"  IMPORTANT: Each variable appears once per year with a suffix "
                f"(e.g., variable_{suffixes[0]}, variable_{suffixes[-1]}).\n"
                f"  The data MUST be reshaped from wide to long format before panel analysis.\n"
                f"  After reshaping: one row per individual-year, with columns for year, ID, "
                f"and all base variables.\n"
                f"\n"
                f"  This IS panel data (same individuals tracked over {len(years)} years: {years}).\n"
                f"\n"
                f"  *** PRIORITY METHODS (exploit the panel dimension — use these first): ***\n"
                f"  DiD, event study, TWFE, individual fixed effects, dynamic panel (Arellano-Bond),\n"
                f"  correlated random effects, Markov transition matrices, survival models.\n"
                f"\n"
                f"  SECONDARY METHODS (cross-sectional, use sparingly — max 1 of 3 top ideas):\n"
                f"  IV, RDD, matching (PSM, CEM), Oaxaca-Blinder, quantile regression.\n"
                f"\n"
                f"  AT LEAST 2 of the top 3 ideas MUST use panel methods that exploit within-individual\n"
                f"  variation over time. The whole point of having panel data is to control for\n"
                f"  unobserved heterogeneity — do NOT waste it on purely cross-sectional designs.\n"
                f"  Scripts MUST include a wide-to-long reshape step before estimation.\n"
            )
        elif structure == "panel":
            pd_info = panel_details
            structure_block = (
                f"DATA STRUCTURE: TRUE PANEL — same individuals tracked over time.\n"
                f"  ID column: {pd_info.get('id_column', '?')}\n"
                f"  Time column: {pd_info.get('time_column', '?')}\n"
                f"  Unique individuals: {pd_info.get('n_unique_ids', '?')}\n"
                f"  Time periods: {pd_info.get('n_time_periods', '?')}\n"
                f"\n"
                f"  *** PRIORITY METHODS (exploit the panel dimension — use these first): ***\n"
                f"  DiD, event study, TWFE, individual fixed effects, dynamic panel (Arellano-Bond),\n"
                f"  correlated random effects, Markov transition matrices, survival models.\n"
                f"\n"
                f"  SECONDARY METHODS (cross-sectional, use sparingly — max 1 of 3 top ideas):\n"
                f"  IV, RDD, matching (PSM, CEM), Oaxaca-Blinder, quantile regression.\n"
                f"\n"
                f"  AT LEAST 2 of the top 3 ideas MUST use panel methods that exploit within-individual\n"
                f"  variation over time. The whole point of having panel data is to control for\n"
                f"  unobserved heterogeneity — do NOT waste it on purely cross-sectional designs.\n"
            )
        elif structure == "pooled-cross-sections":
            structure_block = (
                f"DATA STRUCTURE: POOLED CROSS-SECTIONS — different individuals each period.\n"
                f"  Time column: {panel_details.get('time_column', '?')}\n"
                f"  Time periods: {panel_details.get('n_time_periods', '?')}\n"
                f"  Time values: {panel_details.get('time_values', [])}\n"
                f"  IDs repeating across periods: ONLY {panel_details.get('pct_ids_multiple_periods', 0)}%\n"
                f"\n"
                f"  ALLOWED methods: group-level DiD, repeated cross-section DiD, IV, RDD,\n"
                f"    propensity score matching, Oaxaca-Blinder decomposition, cohort analysis.\n"
                f"  FORBIDDEN methods (require individual tracking): individual FE, individual\n"
                f"    event study, Markov transition matrices, survival/hazard models,\n"
                f"    Arellano-Bond, within-individual variation.\n"
            )
        elif structure == "repeated-cross-sections":
            structure_block = (
                f"DATA STRUCTURE: REPEATED CROSS-SECTIONS — multiple waves, no individual ID.\n"
                f"  Time column: {panel_details.get('time_column', '?')}\n"
                f"  Time periods: {panel_details.get('n_time_periods', '?')}\n"
                f"\n"
                f"  ALLOWED methods: group-level DiD, IV, RDD, decompositions, cohort/pseudo-panel.\n"
                f"  FORBIDDEN: individual FE, individual event study, transition matrices.\n"
            )
        else:
            structure_block = (
                f"DATA STRUCTURE: SINGLE CROSS-SECTION — one time snapshot.\n"
                f"\n"
                f"  ALLOWED methods: IV, RDD, matching (PSM, CEM), Oaxaca-Blinder,\n"
                f"    Heckman selection, quantile regression.\n"
                f"  FORBIDDEN: DiD, event study, FE, transition matrices, any method\n"
                f"    requiring time variation.\n"
            )

        data_context = f"""

## USER DATASET (Path B) — READ CAREFULLY

{structure_block}
- Rows: {data_profile.get('rows', '?'):,}
- Columns: {data_profile.get('cols', '?')}
- Variables: {cols}
- ID columns: {', '.join(data_profile.get('id_cols', [])[:5]) or 'None detected'}
- Time columns: {', '.join(data_profile.get('time_cols', [])[:5]) or 'None detected'}

## CRITICAL CONSTRAINTS

1. Every idea you propose MUST use ONLY methods compatible with the data structure above.
   If you propose an incompatible method, the idea will be automatically rejected in
   Stage 3 validation.
2. If the data has a panel or time dimension, you MUST exploit it. Panel data is rare
   and valuable — proposing only cross-sectional methods on panel data is a waste of
   the researcher's data advantage. Prioritize methods that use within-unit variation
   over time (FE, DiD, TWFE, event study, dynamic panel) over purely cross-sectional
   approaches (IV, RDD, matching).
3. Design your identification strategy around the STRONGEST feature of this data."""

    # Determine if panel methods should be enforced
    is_panel = data_profile and data_profile.get("structure") in ("panel", "wide-panel")

    panel_enforcement = ""
    if is_panel:
        panel_enforcement = f"""
## *** MANDATORY: PANEL DATA METHOD REQUIREMENT ***

You have PANEL DATA. This is the single most important fact about this dataset.
Panel data lets you track the SAME individuals over time and control for ALL
time-invariant unobserved heterogeneity (individual fixed effects).

HARD RULES — violation means automatic rejection:
- AT LEAST 6 of your 8-10 ideas MUST use a panel method as the PRIMARY method.
  Panel methods: individual FE, TWFE, DiD, event study, dynamic panel (Arellano-Bond),
  correlated random effects (CRE), Markov transition matrices, survival/hazard models.
- AT LEAST 2 of your TOP 3 ideas MUST use panel methods.
- Cross-sectional methods (IV, RDD, matching, Oaxaca-Blinder, quantile regression)
  are allowed for AT MOST 1 of the top 3. They do NOT exploit the panel dimension.

Think about what CHANGES over time in this data: do people gain education? switch
from informal to formal jobs? move regions? start/stop working? These transitions
are the gold mine of panel data. Design your ideas around TRANSITIONS and CHANGES,
not static snapshots.
"""

    # ── Read feasibility constraints from Stage 1.5 ─────────────────────
    feasibility = state["stages"].get("stage1_5", {}).get("feasibility", {})
    max_tier = feasibility.get("max_tier", 1)
    score_ceiling = feasibility.get("score_ceiling", 100)
    allowed_methods = feasibility.get("allowed_methods", [])
    forbidden_methods = feasibility.get("forbidden_methods", [])
    feasibility_warnings = feasibility.get("warnings", [])

    # ── Recommend optimal identification strategy from data structure ───
    identification_guidance = ""
    if data_profile:
        structure = data_profile.get("structure", "unknown")
        panel_details = data_profile.get("panel_details", {})
        n_periods = panel_details.get("n_time_periods", 1)
        n_entities = panel_details.get("n_entities", 0)
        cols_lower = [c.lower() for c in data_profile.get("columns", [])]

        # Detect potential instruments, thresholds, and treatment variables
        has_policy_vars = any(kw in c for c in cols_lower
                             for kw in ["reform", "policy", "law", "regulation",
                                        "program", "intervention", "treat"])
        has_threshold_vars = any(kw in c for c in cols_lower
                                for kw in ["score", "threshold", "cutoff", "grade",
                                           "rank", "percentile", "index"])
        has_instrument_candidates = any(kw in c for c in cols_lower
                                        for kw in ["distance", "quota", "lottery",
                                                    "rainfall", "temperature", "draft",
                                                    "birth", "quarter", "shift"])
        has_random_assignment = any(kw in c for c in cols_lower
                                   for kw in ["random", "assigned", "voucher",
                                              "lottery", "experiment"])

        strategies = []

        # RCT / Experimental
        if has_random_assignment:
            strategies.append(
                "**BEST: Randomized Controlled Trial (RCT)**\n"
                "  The data appears to contain random assignment variables. This is the\n"
                "  strongest identification — use it. ITT estimation with HC2 SEs.\n"
                "  Identification quality: Level A (score potential: 85+)."
            )

        # RDD
        if has_threshold_vars:
            strategies.append(
                "**STRONG: Regression Discontinuity Design (RDD)**\n"
                "  The data contains score/threshold/cutoff variables. If a policy\n"
                "  assigns treatment based on a threshold (e.g., test score > X),\n"
                "  RDD exploits the discontinuity. Use rdrobust package.\n"
                "  Identification quality: Level A (score potential: 85+)."
            )

        # DiD (panel with policy variation)
        if structure in ("panel", "wide-panel") and n_periods >= 3 and has_policy_vars:
            strategies.append(
                "**STRONG: Difference-in-Differences (DiD)**\n"
                f"  Panel data with {n_periods} periods and policy variables detected.\n"
                "  If treatment timing varies across units → staggered DiD (C&S or Sun-Abraham).\n"
                "  If treatment is simultaneous → standard TWFE with pre-trends.\n"
                "  REQUIRES: at least 2 pre-treatment periods for credible pre-trends test.\n"
                "  Identification quality: Level A-B (score potential: 75-85)."
            )
        elif structure in ("panel", "wide-panel") and n_periods >= 2:
            strategies.append(
                "**MODERATE: Two-Period DiD**\n"
                f"  Panel data with {n_periods} periods. Two-period DiD is feasible\n"
                "  but pre-trends cannot be tested with only 2 periods.\n"
                "  Referees will be skeptical without pre-trend evidence.\n"
                "  Identification quality: Level B (score potential: 70-80)."
            )

        # IV
        if has_instrument_candidates:
            strategies.append(
                "**STRONG: Instrumental Variables (IV/2SLS)**\n"
                "  The data contains potential instrument variables (distance, lottery, etc.).\n"
                "  REQUIRES: instrument must be (1) relevant (F>10 first stage) and\n"
                "  (2) valid (exclusion restriction — instrument affects outcome ONLY through treatment).\n"
                "  Identification quality: Level A-B (score potential: 75-85)."
            )

        # Cross-sectional fallback
        if not strategies:
            if structure in ("cross-section", "unknown"):
                strategies.append(
                    "**BEST AVAILABLE: IV or Matching**\n"
                    "  Cross-sectional data limits identification to IV (if valid instrument exists),\n"
                    "  RDD (if threshold exists), or matching (PSM/CEM — weakest option).\n"
                    "  SEARCH the data for: geographic boundaries, policy thresholds, natural\n"
                    "  experiments, or variables that could serve as instruments.\n"
                    "  Without these, identification quality will be Level C (score ceiling: 65)."
                )
            else:
                strategies.append(
                    "**Panel FE as baseline**\n"
                    f"  Panel data ({n_entities} entities × {n_periods} periods) but no clear\n"
                    "  policy variation detected. Search for:\n"
                    "  (a) Staggered policy adoption (→ DiD)\n"
                    "  (b) Thresholds in any continuous variable (→ RDD)\n"
                    "  (c) External shocks that affect some units but not others (→ IV)\n"
                    "  Panel FE alone is Level C identification (score ceiling: 65)."
                )

        if strategies:
            identification_guidance = (
                "\n\n## *** RECOMMENDED IDENTIFICATION STRATEGIES FOR THIS DATA ***\n\n"
                "Based on the data structure and available variables, these are the\n"
                "strategies most likely to produce credible identification:\n\n"
                + "\n\n".join(strategies)
                + "\n\n*** PRIORITIZE these strategies when generating ideas. ***\n"
                "*** Ideas using the recommended strategy get +0.5 bonus in scoring. ***\n"
            )

    # ── Compute empirical power from actual data ────────────────────────
    power_warning = ""
    data_path = state["stages"].get("stage1", {}).get("data_path")
    if data_path and data_profile:
        try:
            from pathlib import Path as _Path
            _dp = _Path(data_path)
            if _dp.exists():
                import pandas as _pd_power
                if str(_dp).endswith(".dta"):
                    _df_pw = _pd_power.read_stata(_dp)
                elif str(_dp).endswith(".tab"):
                    _df_pw = _pd_power.read_csv(_dp, sep="\t", encoding="utf-8",
                                                 low_memory=False)
                else:
                    _df_pw = _pd_power.read_csv(_dp, encoding="latin-1",
                                                 low_memory=False)

                import numpy as _np_power
                from scipy import stats as _sp_power

                n_total = len(_df_pw)
                # Compute MDE for continuous outcomes (assume 50/50 split)
                numeric_cols = _df_pw.select_dtypes(include=[_np_power.number]).columns
                sds = {}
                for c in numeric_cols:
                    s = _df_pw[c].dropna()
                    if len(s) > 20 and s.std() > 1e-10 and s.nunique() > 5:
                        sds[c] = s.std()

                if sds:
                    median_sd = _np_power.median(list(sds.values()))
                    z_alpha = _sp_power.norm.ppf(0.975)
                    z_beta = _sp_power.norm.ppf(0.80)
                    mde = (z_alpha + z_beta) * median_sd * _np_power.sqrt(4.0 / n_total)
                    mde_d = mde / median_sd  # Cohen's d

                    power_warning = (
                        f"\n\n## *** STATISTICAL POWER FROM ACTUAL DATA ***\n\n"
                        f"  N = {n_total:,} observations\n"
                        f"  Median outcome SD = {median_sd:.3f}\n"
                        f"  Minimum Detectable Effect (80% power, α=0.05):\n"
                        f"    MDE = {mde:.4f} raw units\n"
                        f"    MDE = Cohen's d = {mde_d:.3f}\n\n"
                    )

                    if mde_d > 0.5:
                        power_warning += (
                            f"  *** WARNING: This dataset can only detect LARGE effects (d>{mde_d:.2f}). ***\n"
                            f"  *** Most social science effects are d=0.1-0.3. ***\n"
                            f"  *** Ideas expecting small effects WILL produce null findings. ***\n"
                            f"  *** Score EE (Expected Effect) = 1-2 unless literature shows d>{mde_d:.2f}. ***\n"
                        )
                    elif mde_d > 0.3:
                        power_warning += (
                            f"  *** CAUTION: Only moderate-to-large effects detectable (d>{mde_d:.2f}). ***\n"
                            f"  *** Score EE carefully — only ideas with strong priors for d>{mde_d:.2f} ***\n"
                            f"  *** should get EE >= 3. ***\n"
                        )
                    else:
                        power_warning += (
                            f"  Good power: can detect effects as small as d={mde_d:.2f}.\n"
                            f"  Most social science effects (d=0.1-0.3) are detectable.\n"
                        )

                del _df_pw
        except Exception as _pw_err:
            print(f"  [power] Could not compute power from data: {_pw_err}")

    feasibility_block = ""
    if feasibility:
        self_contained = feasibility.get("self_contained", True)
        n_ordinal = feasibility.get("n_ordinal_vars", 0)
        n_continuous = feasibility.get("n_continuous_vars", 0)

        self_contained_warning = ""
        if not self_contained:
            self_contained_warning = """
  *** SELF-CONTAINMENT WARNING: This dataset does NOT contain both treatment
  and continuous outcome variables. Ideas that require merging with external
  datasets are RISKY — merge attrition, coding inconsistencies, and coverage
  gaps will reduce the effective sample and weaken identification.
  STRONGLY PREFER ideas that use ONLY variables already in this dataset.
  If external data is needed, it must be simple (1-2 variables, well-known source). ***
"""

        ordinal_warning = ""
        if n_ordinal > 0 and n_continuous == 0:
            ordinal_warning = f"""
  *** ORDINAL OUTCOME WARNING: All {n_ordinal} numeric variables are ordinal
  (<=7 unique values). Within-unit variation will be very low.
  PREFER methods that work well with ordinal outcomes:
  - Ordered probit/logit with FE
  - Linear probability model for binary recodings
  - Transition matrices (prob of moving between categories)
  DO NOT propose DiD/event study on ordinal variables with 3-4 values —
  the referee will reject on power grounds. ***
"""
        elif n_ordinal > n_continuous:
            ordinal_warning = f"""
  *** MOSTLY ORDINAL DATA: {n_ordinal} ordinal vs {n_continuous} continuous vars.
  Prefer ideas that use the continuous variables as outcomes. ***
"""

        feasibility_block = f"""
## *** DATA FEASIBILITY CONSTRAINTS (from Stage 1.5 assessment) ***

The data has been downloaded and profiled. Based on its structure, these are the
HARD CONSTRAINTS on what methods are feasible:

  Maximum method tier: {max_tier} ({feasibility.get('tier_label', 'unknown')})
  Score ceiling with this data: {score_ceiling}/100
  Allowed methods: {', '.join(allowed_methods) if allowed_methods else 'all'}
  FORBIDDEN methods: {', '.join(forbidden_methods) if forbidden_methods else 'none'}

{'Data limitations:' if feasibility_warnings else ''}
{chr(10).join('  - ' + w for w in feasibility_warnings)}
{self_contained_warning}
{ordinal_warning}

*** CRITICAL: Do NOT propose methods listed as FORBIDDEN above. ***
*** Ideas using forbidden methods will be AUTOMATICALLY REJECTED. ***
*** Only propose methods that the data can ACTUALLY support. ***
*** A realistic, well-identified Tier {max_tier} design scores higher than ***
*** an ambitious but flawed Tier 1 design that referees will destroy. ***
"""

    prompt = f"""You are a bold but REALISTIC research advisor (Junshi). Your task:

RESEARCH AREA: {topic}

## *** IDENTIFICATION-FIRST DESIGN PRINCIPLE ***

The #1 reason papers get low scores is WEAK IDENTIFICATION — proposing a "causal"
method (DiD, event study) without credible exogenous variation. The pipeline has
learned from experience: identification quality is the binding constraint on paper
quality. Everything else (writing, code, robustness) can be fixed later, but a
weak identification strategy cannot be rescued.

YOUR JOB: Design the identification strategy FROM THE DATA, not from the topic.
Before proposing any method, first ask: "What variation exists in this data that
could serve as a source of exogenous treatment?"

## *** IDENTIFICATION QUALITY LEVELS ***

Level A (STRONG — score 90+): There exists a credible control group.
  - Some units are treated, others are not, and the assignment is plausibly exogenous.
  - Examples: policy rollout that affected some regions first, natural disaster that hit
    some areas but not others, eligibility threshold creating a discontinuity.
  - Methods: DiD with staggered adoption, RDD, IV with strong first stage.

Level B (MODERATE — score 75-85): Treatment is universal but intensity varies.
  - All units are treated, but the DOSE varies cross-sectionally for exogenous reasons.
  - Examples: English proficiency determines how much a country benefits from an
    English-first AI tool, pre-existing broadband penetration determines adoption speed.
  - Methods: Continuous treatment DiD, Bartik shift-share, dose-response models.
  - KEY: The intensity variable must be PRE-DETERMINED (measured before treatment).

Level C (WEAK — score 60-75): Treatment is simultaneous and universal.
  - All units are treated at the same time with the same intensity.
  - No control group, no dose variation. Identification relies solely on before-after.
  - Methods: Interrupted time series, simple event study with entity FE.
  - WARNING: Referees WILL reject causal claims. Pre-trends cannot validate identification.

## *** CRITICAL: AVOID LEVEL C DESIGNS ***

If the topic involves a UNIVERSAL SHOCK (global product launch, pandemic, worldwide
policy), do NOT propose a simple before-after event study as the main design.
Instead, SEARCH THE DATA for cross-sectional variation that creates differential
exposure. Common sources:
  - Geographic variation (some regions affected more than others)
  - Pre-existing characteristics that moderate treatment intensity
  - Policy responses that vary by jurisdiction (bans, delays, regulations)
  - Infrastructure differences (internet access, language, institutions)

If you CANNOT find any cross-sectional variation, honestly say so and propose a
Level C design with appropriate caveats — but this should be AT MOST 1 of your
top 3 ideas, not all of them.

METHOD HIERARCHY (strongest to weakest):
  Tier 1 (CAUSAL): DiD with control group, IV/2SLS, RDD, RCT, synthetic control
  Tier 2 (CONTINUOUS TREATMENT): Continuous DiD, Bartik, dose-response, shift-share
  Tier 3 (PANEL-DESCRIPTIVE): TWFE without clear ID, entity FE + universal shock
  Tier 4 (CROSS-SECTION): OLS, matching, decompositions, probit/logit

HARD RULES:
- Only propose methods up to Tier {max_tier}. Methods beyond this tier are FORBIDDEN.
- For EACH idea, you must specify the IDENTIFICATION LEVEL (A, B, or C) and explain:
  (a) What is the source of exogenous variation? (If universal shock: what creates
      DIFFERENTIAL exposure across units?)
  (b) How many pre-treatment periods are available?
  (c) Can parallel trends be tested? With how many pre-periods?
  (d) Are there enough clusters for reliable inference?
  (e) Is the treatment plausibly exogenous? What threatens this?
- If you cannot identify cross-sectional variation, the design is Level C.
- AT LEAST 2 of the top 3 ideas MUST be Level A or Level B.
- A Level B design with credible dose variation beats a Level A design with
  implausible exclusion restriction.

{identification_guidance}
{power_warning}
{feasibility_block}
{panel_enforcement}
{data_context}
{sources_context}

Based on the current state of research in {topic}:

1. Identify the key themes, methods, and gaps across these papers.
2. Generate 8-10 bold, specific research ideas. Each must be actionable — not "explore X"
   but "do Y to achieve Z, enabled by insight W."

   CRITICAL DIVERSITY RULE: The 8-10 ideas MUST span at least 5 DISTINCT sub-topics
   within "{topic}". Do NOT cluster ideas around a single theme (e.g., do not generate
   4 ideas about wage gaps). Use the seed papers as starting points but BRANCH OUT
   into other important sub-areas of the field. Adapt sub-areas to the specific topic.

   CRITICAL METHOD-DATA FIT RULE: Your method choices MUST match the strongest
   feature of the available data. If the data is panel, the majority of ideas MUST
   exploit within-individual variation over time. A reviewer will immediately ask
   "why didn't you use FE/DiD if you have panel data?" — your ideas must use those methods.

3. For each idea, specify:
   - A clear research question
   - Proposed empirical method — ALWAYS prefer Tier 1-2 causal methods. For each idea,
     state the TIER (1-4) and the SOURCE OF IDENTIFYING VARIATION.
   - Data sources needed
   - Why this is novel and impactful
   - Sub-topic category (to verify diversity)
4. Score each idea on FIVE dimensions:
   - Novelty (N, 1-5): How new is this question/approach?
   - Feasibility (F, 1-5): Can this be done with the available data?
   - Impact (I, 1-5): How important is the answer?
   - Identification (ID, 1-5): How credible is the causal claim?
     * 5 = Level A: clean control group, exogenous assignment
     * 4 = Level A with minor threats, or strong Level B
     * 3 = Level B: universal treatment but credible dose variation
     * 2 = Weak Level B or Level C with good robustness plan
     * 1 = Level C: before-after with no cross-sectional variation
   - Expected Effect (EE, 1-5): How likely is a detectable, meaningful effect?
     * 5 = Strong prior: similar studies found large effects (d > 0.3), data has high treatment variation
     * 4 = Good prior: comparable studies found moderate effects, treatment affects >30% of sample
     * 3 = Uncertain: no comparable prior, but mechanism is plausible and treatment varies
     * 2 = Weak prior: similar studies found null or tiny effects, or treatment is nearly universal
     * 1 = Null expected: treatment has uniform uptake, or prior work consistently finds null effects
     IMPORTANT: A paper with perfect identification but null findings scores POORLY in peer review.
     Referees reward well-identified studies WITH meaningful results.

   Total = N * 0.15 + F * 0.15 + I * 0.15 + ID * 0.35 + EE * 0.20
   (Identification is 35%, Expected Effect is 20% — both are binding constraints)
   {"- Panel bonus: add +0.2 if the idea exploits within-unit variation over time." if is_panel else ""}

5. Select the TOP 3 ideas and elaborate on each. The top 3 MUST come from
   3 DIFFERENT sub-topics. Never select 2 ideas from the same sub-topic.
   AT LEAST 2 of the top 3 MUST have Identification >= 3 (Level A or B).
   {"AT LEAST 2 of the top 3 MUST use panel methods (FE, DiD, TWFE, event study, dynamic panel)." if is_panel else ""}
   If ALL ideas have Identification <= 2, explicitly flag this as a DATA LIMITATION
   and recommend what additional data would raise identification to Level A/B.

IMPORTANT: At the end, output a JSON block:
```json
{{
  "top_ideas": [
    {{
      "rank": 1,
      "title": "...",
      "research_question": "...",
      "method": "DiD with continuous treatment intensity",
      "identification_level": "B",
      "identification_source": "Pre-determined English proficiency creates differential treatment intensity",
      "sub_topic": "informality",
      "data_sources": ["..."],
      "novelty": 4,
      "feasibility": 4,
      "impact": 5,
      "identification": 3,
      "expected_effect": 4,
      "total_score": 3.8,
      "pitch": "2-3 sentence pitch",
      "first_experiment": "What you'd do in week 1"
    }}
  ],
  "identification_warning": "If ALL top 3 have identification <= 2, explain what data would fix this"
}}
```
"""
    output_file = project_dir / "stage2_ideation.md"
    p = get_profile("stage2")
    response = run_claude(prompt, model=p["model"], effort=p["effort"], output_file=output_file)
    ideas_data = extract_json(response)

    state["stages"]["stage2"] = {
        "status": "completed",
        "output_file": str(output_file),
        "completed_at": datetime.now().isoformat(),
    }

    if ideas_data and "top_ideas" in ideas_data:
        state["stages"]["stage2"]["top_ideas"] = ideas_data["top_ideas"]
        print(f"  [ok] Generated {len(ideas_data['top_ideas'])} top ideas")
    else:
        print("  [warn] Could not parse structured JSON. Check stage2_ideation.md manually.")

    state["current_stage"] = 2
    save_state(project_dir, state)
    return state
