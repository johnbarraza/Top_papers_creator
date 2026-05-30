"""Stage 3.3 -- Quick Empirical Test.

Runs a fast (~30s) empirical validation on the actual data to verify that
the proposed identification strategy holds BEFORE investing in full code
generation and paper writing.

Tests:
  0. Package availability: verifies that required estimators actually work
     with the real data (prevents promising methods that crash later)
  1. Pre-trends: are they flat? (joint F-test on pre-treatment dummies)
  2. Permutation: does the effect survive randomization inference?
  3. Country trends: does the effect survive country-specific linear trends?
  4. Magnitude: is the effect economically meaningful?

If the quick test FAILS, the pipeline warns the user and offers to:
  - Try the next idea from Stage 2
  - Proceed anyway (with a score ceiling warning)
  - Provide new data
"""

import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import get_profile
from ..state import save_state

warnings.filterwarnings("ignore")


def _load_data(state):
    """Load the main dataset from Stage 1."""
    stage1 = state["stages"].get("stage1", {})
    data_path = stage1.get("data_path", "")
    if not data_path or not Path(data_path).exists():
        return None, "No data file found"

    ext = Path(data_path).suffix.lower()
    try:
        if ext == ".dta":
            df = pd.read_stata(data_path)
        elif ext == ".parquet":
            df = pd.read_parquet(data_path)
        elif ext in (".xls", ".xlsx"):
            df = pd.read_excel(data_path)
        elif ext == ".tab":
            df = pd.read_csv(data_path, sep="\t", encoding="latin-1", low_memory=False)
        else:
            df = pd.read_csv(data_path, encoding="latin-1", low_memory=False)
        return df, None
    except Exception as e:
        return None, str(e)


def _detect_design(idea):
    """Detect the identification design from the idea metadata."""
    method = (idea.get("method", "") + " " + idea.get("identification_source", "")).lower()

    if any(k in method for k in ["stagger", "callaway", "sun-abraham", "cohort"]):
        return "staggered_did"
    elif any(k in method for k in ["did", "diff", "event study", "event-study"]):
        return "did"
    elif any(k in method for k in ["rdd", "discontinuity", "threshold"]):
        return "rdd"
    elif any(k in method for k in ["iv", "instrumental", "2sls"]):
        return "iv"
    else:
        return "generic"


def _quick_did_test(df, outcome_col, treat_col, entity_col, time_col):
    """Run a quick DiD test: outcome ~ treat + entity_FE, clustered.

    Returns dict with ATT, SE, p-value, and diagnostic flags.
    """
    from linearmodels.panel import PanelOLS

    tmp = df[[outcome_col, treat_col, entity_col, time_col]].dropna().copy()
    if len(tmp) < 50:
        return {"att": np.nan, "se": np.nan, "p": np.nan, "n": len(tmp),
                "error": "Too few observations"}

    tmp["_eid"] = pd.Categorical(tmp[entity_col]).codes
    tmp = tmp.set_index(["_eid", time_col]).sort_index()

    try:
        mod = PanelOLS(tmp[outcome_col], tmp[[treat_col]],
                       entity_effects=True, time_effects=True,
                       drop_absorbed=True)
        res = mod.fit(cov_type="clustered", cluster_entity=True)
        return {
            "att": res.params[treat_col],
            "se": res.std_errors[treat_col],
            "p": res.pvalues[treat_col],
            "n": int(res.nobs),
            "error": None,
        }
    except Exception as e:
        return {"att": np.nan, "se": np.nan, "p": np.nan, "n": len(tmp),
                "error": str(e)}


def _quick_permutation_test(df, outcome_col, treat_col, entity_col, time_col,
                             n_perms=200):
    """Quick permutation test: shuffle treatment across entities."""
    from linearmodels.panel import PanelOLS

    tmp = df[[outcome_col, treat_col, entity_col, time_col]].dropna().copy()
    if len(tmp) < 50:
        return np.nan

    # Get actual ATT
    actual = _quick_did_test(df, outcome_col, treat_col, entity_col, time_col)
    if np.isnan(actual["att"]):
        return np.nan

    actual_att = abs(actual["att"])

    # Permutation
    entities = tmp[entity_col].unique()
    treated_entities = tmp.loc[tmp[treat_col] == 1, entity_col].unique()
    n_treated = len(treated_entities)

    count_larger = 0
    rng = np.random.default_rng(42)

    for _ in range(n_perms):
        # Shuffle which entities are "treated"
        fake_treated = rng.choice(entities, size=n_treated, replace=False)
        tmp_perm = tmp.copy()
        tmp_perm[treat_col] = tmp_perm[entity_col].isin(fake_treated).astype(int)

        res = _quick_did_test(tmp_perm, outcome_col, treat_col, entity_col, time_col)
        if not np.isnan(res["att"]) and abs(res["att"]) >= actual_att:
            count_larger += 1

    return count_larger / n_perms


def _quick_trend_test(df, outcome_col, treat_col, entity_col, time_col):
    """Quick test: does ATT survive adding a linear time trend?"""
    from linearmodels.panel import PanelOLS

    tmp = df[[outcome_col, treat_col, entity_col, time_col]].dropna().copy()
    if len(tmp) < 50:
        return {"att": np.nan, "p": np.nan}

    tmp["_eid"] = pd.Categorical(tmp[entity_col]).codes
    tmp["_trend"] = tmp[time_col] - tmp[time_col].min()
    tmp = tmp.set_index(["_eid", time_col]).sort_index()

    try:
        mod = PanelOLS(tmp[outcome_col], tmp[[treat_col, "_trend"]],
                       entity_effects=True, time_effects=False,
                       drop_absorbed=True)
        res = mod.fit(cov_type="clustered", cluster_entity=True)
        return {
            "att": res.params[treat_col],
            "p": res.pvalues[treat_col],
        }
    except Exception:
        return {"att": np.nan, "p": np.nan}


def run(project_dir: Path, state: dict) -> dict:
    """Execute Stage 3.3: Quick empirical validation."""
    print("\n  [3.3] Running quick empirical test on actual data...")

    stage1 = state["stages"].get("stage1", {})
    stage2_5 = state["stages"].get("stage2_5", {})
    selected_idea = stage2_5.get("selected_idea", {})
    data_path = stage1.get("data_path", "")
    data_profile = stage1.get("data_profile", {})

    if not data_path or not Path(data_path).exists():
        print("  [3.3] No data file available -- skipping quick test")
        state["stages"]["stage3_3"] = {
            "status": "skipped",
            "reason": "no_data",
            "completed_at": datetime.now().isoformat(),
        }
        save_state(project_dir, state)
        return state

    # Load data
    df, err = _load_data(state)
    if df is None:
        print(f"  [3.3] Cannot load data: {err} -- skipping")
        state["stages"]["stage3_3"] = {
            "status": "skipped", "reason": err,
            "completed_at": datetime.now().isoformat(),
        }
        save_state(project_dir, state)
        return state

    print(f"  [3.3] Loaded: {len(df):,} rows x {df.shape[1]} cols")

    # Detect columns
    columns = [c.lower() for c in df.columns]
    col_map = {c.lower(): c for c in df.columns}

    # Find time column
    time_col = None
    for candidate in ["year", "quarter", "month", "date", "time", "period"]:
        if candidate in columns:
            time_col = col_map[candidate]
            break
    if not time_col:
        time_cols = data_profile.get("time_cols", [])
        if time_cols:
            time_col = time_cols[0]

    # Find entity column
    entity_col = None
    id_cols = data_profile.get("id_cols", [])
    if id_cols:
        entity_col = id_cols[0]
    else:
        for candidate in ["id", "country", "iso2_code", "iso3_code", "cty_name",
                          "state", "region", "firm", "household", "individual"]:
            if candidate in columns:
                entity_col = col_map[candidate]
                break

    if not time_col or not entity_col:
        print(f"  [3.3] Cannot identify time/entity columns -- skipping")
        print(f"        time_col={time_col}, entity_col={entity_col}")
        state["stages"]["stage3_3"] = {
            "status": "skipped", "reason": "cannot_identify_panel_structure",
            "completed_at": datetime.now().isoformat(),
        }
        save_state(project_dir, state)
        return state

    # Find or construct treatment and outcome
    # Try to detect a natural "post" or treatment variable
    design = _detect_design(selected_idea)
    print(f"  [3.3] Design detected: {design}")
    print(f"  [3.3] Entity: {entity_col}, Time: {time_col}")

    # For the quick test, we need an outcome and a treatment variable.
    # Use Claude to generate a tiny script that constructs them.
    from ..claude_runner import run_claude
    from ..json_utils import extract_json

    idea_text = (
        f"Title: {selected_idea.get('title', '?')}\n"
        f"Method: {selected_idea.get('method', '?')}\n"
        f"RQ: {selected_idea.get('research_question', '?')}\n"
        f"Identification: {selected_idea.get('identification_source', '?')}\n"
    )
    cols_list = ", ".join(df.columns[:40])
    sample_data = df.head(3).to_string()

    quick_prompt = f"""You are writing a MINIMAL Python code snippet (under 30 lines) to construct
a treatment variable and identify the outcome variable for a quick DiD test.

IDEA:
{idea_text}

DATASET columns: {cols_list}
Sample rows:
{sample_data}

Entity column: {entity_col}
Time column: {time_col}

Write Python code that:
1. Creates a binary column 'treat' (1 = treated in this period, 0 = not)
2. Identifies the outcome column name as 'outcome_col' (string)
3. The code has access to a DataFrame called 'df' with the columns above

Return ONLY a JSON block:
```json
{{
  "treat_code": "df['treat'] = (df['some_col'] > threshold).astype(int)",
  "outcome_col": "column_name"
}}
```

Keep it SIMPLE. For staggered DiD: define treatment as post-onset. For standard DiD: define post-treatment indicator.
"""

    p = get_profile("stage3_3_test")
    resp = run_claude(quick_prompt, model=p["model"], effort=p["effort"],
                      allowed_tools=[], label="quick-test-setup")
    setup = extract_json(resp)

    if not setup or "treat_code" not in setup or "outcome_col" not in setup:
        print("  [3.3] Could not generate treatment variable -- skipping")
        state["stages"]["stage3_3"] = {
            "status": "skipped", "reason": "cannot_construct_treatment",
            "completed_at": datetime.now().isoformat(),
        }
        save_state(project_dir, state)
        return state

    # Execute the treatment construction with safety checks
    outcome_col = setup["outcome_col"]
    treat_code = setup["treat_code"]

    # Validate outcome_col exists in data BEFORE exec
    if outcome_col not in df.columns:
        print(f"  [3.3] Outcome column '{outcome_col}' not in data -- skipping")
        # Try to find a similar column
        close = [c for c in df.columns if outcome_col.lower() in c.lower()]
        if close:
            print(f"  [3.3] Did you mean: {close[:5]}?")
        state["stages"]["stage3_3"] = {
            "status": "skipped",
            "reason": "outcome_col '%s' not found" % outcome_col,
            "completed_at": datetime.now().isoformat(),
        }
        save_state(project_dir, state)
        return state

    # Validate treat_code is safe (no imports, no file operations, no network)
    dangerous_patterns = ["import ", "open(", "exec(", "eval(", "__", "os.",
                          "subprocess", "system(", "write(", "requests.",
                          "urllib", "socket"]
    treat_code_lower = treat_code.lower()
    for pat in dangerous_patterns:
        if pat in treat_code_lower:
            print(f"  [3.3] Unsafe pattern '{pat}' in treat_code -- skipping")
            state["stages"]["stage3_3"] = {
                "status": "skipped",
                "reason": "unsafe_treat_code: contains '%s'" % pat,
                "completed_at": datetime.now().isoformat(),
            }
            save_state(project_dir, state)
            return state

    # Limit code length (Claude should generate 1-3 lines, not a full script)
    if len(treat_code) > 500:
        print(f"  [3.3] treat_code too long ({len(treat_code)} chars) -- skipping")
        state["stages"]["stage3_3"] = {
            "status": "skipped", "reason": "treat_code_too_long",
            "completed_at": datetime.now().isoformat(),
        }
        save_state(project_dir, state)
        return state

    print(f"  [3.3] Executing treatment code: {treat_code[:80]}...")
    n_before = len(df.columns)
    try:
        exec(treat_code, {"df": df, "pd": pd, "np": np})
    except Exception as e:
        print(f"  [3.3] Treatment construction failed: {e} -- skipping")
        state["stages"]["stage3_3"] = {
            "status": "skipped", "reason": "treat_code_error: %s" % str(e)[:100],
            "completed_at": datetime.now().isoformat(),
        }
        save_state(project_dir, state)
        return state

    # Validate exec produced the expected column
    if "treat" not in df.columns:
        print(f"  [3.3] exec() did not create 'treat' column -- skipping")
        print(f"  [3.3] Columns before: {n_before}, after: {len(df.columns)}")
        state["stages"]["stage3_3"] = {
            "status": "skipped", "reason": "treat_column_not_created",
            "completed_at": datetime.now().isoformat(),
        }
        save_state(project_dir, state)
        return state

    # Validate treat is binary-ish (0/1 or small number of unique values)
    n_unique = df["treat"].nunique()
    if n_unique > 10:
        print(f"  [3.3] WARNING: 'treat' has {n_unique} unique values -- expected binary (0/1)")
    if n_unique < 2:
        print(f"  [3.3] 'treat' has only {n_unique} unique value -- no variation.")
        print(f"  [3.3] Attempting fallback: search for a binary variable with variation...")

        # Fallback: find any binary/few-valued column with balanced groups
        fallback_found = False
        candidates = []

        # Priority 1: columns with treatment-related names
        for c in df.select_dtypes(include=[np.number]).columns:
            if c == "treat":
                continue
            n_u = df[c].nunique()
            if 2 <= n_u <= 5:
                val_counts = df[c].value_counts()
                min_pct = val_counts.min() / val_counts.sum()
                if min_pct >= 0.10:  # at least 10% in smallest group
                    is_priority = any(kw in c.lower() for kw in
                                     ["treat", "assign", "group", "arm",
                                      "condition", "muslim", "hindu", "female",
                                      "gender", "urban", "rural"])
                    candidates.append((c, n_u, min_pct, is_priority))

        # Also check string columns that could be binarized
        for c in df.select_dtypes(include=["object"]).columns:
            if c == "treat":
                continue
            vals = df[c].dropna()
            if len(vals) == 0:
                continue
            n_u = vals.nunique()
            if 2 <= n_u <= 5:
                # Check encoding is readable (no replacement chars)
                sample = vals.astype(str).head(100)
                n_readable = (~sample.str.contains('\ufffd', na=True)).sum()
                if n_readable > len(sample) * 0.5:
                    candidates.append((c, n_u, 0.2, False))

        # Sort: priority names first, then by balance
        candidates.sort(key=lambda x: (-int(x[3]), -x[2]))

        if candidates:
            best = candidates[0]
            fallback_col = best[0]
            print(f"  [3.3] Fallback candidate: '{fallback_col}' "
                  f"({best[1]} unique values, min_group={best[2]:.0%})")

            # Binarize: map to 0/1
            if df[fallback_col].dtype == "object":
                # String column — use most common value as control
                most_common = df[fallback_col].mode().iloc[0]
                df["treat"] = (df[fallback_col] != most_common).astype(float)
            else:
                # Numeric — use median split or existing 0/1
                if set(df[fallback_col].dropna().unique()).issubset({0, 1, 0.0, 1.0}):
                    df["treat"] = df[fallback_col].astype(float)
                else:
                    median_val = df[fallback_col].median()
                    df["treat"] = (df[fallback_col] > median_val).astype(float)

            n_unique = df["treat"].nunique()
            if n_unique >= 2:
                fallback_found = True
                print(f"  [3.3] Fallback treatment: treat values = "
                      f"{df['treat'].value_counts().to_dict()}")
            else:
                print(f"  [3.3] Fallback also has no variation.")

        if not fallback_found:
            print(f"  [3.3] No fallback treatment found. Skipping quick test.")
            state["stages"]["stage3_3"] = {
                "status": "skipped", "reason": "treat_no_variation",
                "completed_at": datetime.now().isoformat(),
            }
            save_state(project_dir, state)
            return state

    print(f"  [3.3] Outcome: {outcome_col}, Treatment: treat")
    print(f"  [3.3] treat values: {df['treat'].value_counts().to_dict()}")
    print(f"  [3.3] Treated obs: {df['treat'].sum():,} / {len(df):,}")

    # ===================================================================
    # TEST -2: Programmatic Design Validation
    # ===================================================================
    # Automatic checks that don't depend on Claude's judgment.
    # Validates treatment variables, time periods, and design-specific
    # requirements BEFORE the Claude-based feasibility check.
    print("\n  [3.3] Test -2: Programmatic design validation...")

    from ..templates import detect_design
    design = detect_design(selected_idea)
    print(f"  Design detected: {design}")

    programmatic_flags = []
    n_treated = int((df["treat"] == 1).sum())
    n_control = int((df["treat"] == 0).sum())

    # ══════════════════════════════════════════════════════════════════
    # A. UNIVERSAL CHECKS (all designs)
    # ══════════════════════════════════════════════════════════════════

    # ── A1. Treatment variable validation ─────────────────────────────
    print(f"\n  A1. Treatment variable: treat")
    n_treat_vals = df["treat"].nunique()
    print(f"    Unique values: {n_treat_vals}")
    print(f"    Distribution: {df['treat'].value_counts().to_dict()}")

    if n_treat_vals < 2:
        programmatic_flags.append({
            "check": "treatment_variation",
            "severity": "CRITICAL",
            "detail": f"Treatment has only {n_treat_vals} unique value(s). No comparison group.",
        })
    else:
        print(f"    Treated: {n_treated:,}  Control: {n_control:,}")
        min_per_group = {"rdd": 50, "did": 30, "rct": 30, "iv": 50}.get(design, 30)
        if n_treated < min_per_group:
            programmatic_flags.append({
                "check": "treatment_sample_size",
                "severity": "CRITICAL",
                "detail": f"Only {n_treated} treated obs (minimum {min_per_group} for {design}).",
            })
        if n_control < min_per_group:
            programmatic_flags.append({
                "check": "control_sample_size",
                "severity": "CRITICAL",
                "detail": f"Only {n_control} control obs (minimum {min_per_group} for {design}).",
            })

    # ── A2. Outcome variable validation ───────────────────────────────
    print(f"\n  A2. Outcome variable: {outcome_col}")
    if outcome_col in df.columns:
        outcome_s = df[outcome_col].dropna()
        outcome_missing_pct = 100 * (1 - len(outcome_s) / len(df))
        print(f"    N valid: {len(outcome_s):,} ({100 - outcome_missing_pct:.1f}%)")
        print(f"    dtype: {df[outcome_col].dtype}")

        if outcome_missing_pct > 50:
            programmatic_flags.append({
                "check": "outcome_mostly_missing",
                "severity": "CRITICAL",
                "detail": f"Outcome '{outcome_col}' is {outcome_missing_pct:.0f}% missing. "
                          f"Analysis unreliable with >50% missing.",
            })
        elif outcome_missing_pct > 30:
            programmatic_flags.append({
                "check": "outcome_high_missing",
                "severity": "WARNING",
                "detail": f"Outcome '{outcome_col}' is {outcome_missing_pct:.0f}% missing.",
            })

        if df[outcome_col].dtype == "object" or df[outcome_col].dtype.name == "category":
            programmatic_flags.append({
                "check": "outcome_not_numeric",
                "severity": "CRITICAL",
                "detail": f"Outcome '{outcome_col}' is {df[outcome_col].dtype}, not numeric. "
                          f"Cannot run regression.",
            })

    # ── A3. Cluster count ─────────────────────────────────────────────
    if entity_col and entity_col in df.columns:
        n_entities = df[entity_col].nunique()
        print(f"\n  A3. Entity/cluster: {entity_col} ({n_entities:,} unique)")

        if n_entities < 30:
            programmatic_flags.append({
                "check": "few_clusters",
                "severity": "WARNING",
                "detail": f"Only {n_entities} clusters. Cluster-robust SEs unreliable "
                          f"with <30 clusters. Consider wild cluster bootstrap.",
            })
        if n_entities < 10:
            programmatic_flags.append({
                "check": "very_few_clusters",
                "severity": "CRITICAL",
                "detail": f"Only {n_entities} clusters. Too few for any cluster-based inference.",
            })
    else:
        print(f"\n  A3. No entity variable found.")

    # ── A4. Time periods ──────────────────────────────────────────────
    print(f"\n  A4. Time variable: {time_col}")
    n_periods = 0
    time_vals = []
    if time_col and time_col in df.columns:
        time_vals = sorted(df[time_col].dropna().unique())
        n_periods = len(time_vals)
        print(f"    Periods: {n_periods}")
        if n_periods <= 10:
            print(f"    Values: {time_vals}")
        else:
            print(f"    Range: {time_vals[0]} to {time_vals[-1]}")
    else:
        print(f"    No time variable found.")

    # ══════════════════════════════════════════════════════════════════
    # B. DESIGN-SPECIFIC CHECKS
    # ══════════════════════════════════════════════════════════════════

    if design == "did":
        print(f"\n  B. DiD-specific checks:")

        # B1. Time variable required
        if not time_col or time_col not in df.columns:
            programmatic_flags.append({
                "check": "did_no_time",
                "severity": "CRITICAL",
                "detail": "DiD requires a time variable but none was found.",
            })
        else:
            # B2. Minimum 2 periods
            if n_periods < 2:
                programmatic_flags.append({
                    "check": "did_periods",
                    "severity": "CRITICAL",
                    "detail": f"DiD requires at least 2 time periods. Found: {n_periods}.",
                })
            elif n_periods < 4:
                programmatic_flags.append({
                    "check": "did_pre_periods",
                    "severity": "WARNING",
                    "detail": f"Only {n_periods} periods. Pre-trends test needs 3+ pre-periods.",
                })

            # B3. Pre-treatment period exists
            if "treat" in df.columns and n_periods >= 2:
                treated_times = set(df.loc[df["treat"] == 1, time_col].dropna().unique())
                all_times = set(time_vals)
                pre_periods = all_times - treated_times
                print(f"    Pre-treatment periods: {len(pre_periods)}")
                print(f"    Post-treatment periods: {len(treated_times)}")
                if len(pre_periods) == 0:
                    programmatic_flags.append({
                        "check": "did_no_pre_period",
                        "severity": "CRITICAL",
                        "detail": "All time periods have treated obs. No pre-treatment period.",
                    })

            # B4. Never-treated units exist (for CS estimator)
            if entity_col and entity_col in df.columns and "treat" in df.columns:
                entity_ever_treated = df.loc[df["treat"] == 1, entity_col].unique()
                entity_never_treated = set(df[entity_col].unique()) - set(entity_ever_treated)
                n_never = len(entity_never_treated)
                n_ever = len(entity_ever_treated)
                print(f"    Ever-treated entities: {n_ever}")
                print(f"    Never-treated entities: {n_never}")
                if n_never == 0:
                    programmatic_flags.append({
                        "check": "did_no_never_treated",
                        "severity": "WARNING",
                        "detail": "No never-treated entities. Callaway-Sant'Anna "
                                  "requires a never-treated control group.",
                    })

            # B5. Same entities appear pre and post (true panel, not repeated cross-section)
            if entity_col and entity_col in df.columns and n_periods >= 2:
                first_period = time_vals[0]
                last_period = time_vals[-1]
                entities_first = set(df.loc[df[time_col] == first_period, entity_col].unique())
                entities_last = set(df.loc[df[time_col] == last_period, entity_col].unique())
                overlap = entities_first & entities_last
                overlap_pct = 100 * len(overlap) / max(len(entities_first), 1)
                print(f"    Entity overlap first/last period: {len(overlap)} "
                      f"({overlap_pct:.0f}%)")
                if overlap_pct < 50:
                    programmatic_flags.append({
                        "check": "did_not_panel",
                        "severity": "WARNING",
                        "detail": f"Only {overlap_pct:.0f}% of entities appear in both first "
                                  f"and last period. May be repeated cross-sections, not panel.",
                    })

            # B6. Staggered: check cohort variation
            idea_method = selected_idea.get("method", "").lower()
            if "stagger" in idea_method or "callaway" in idea_method:
                # Look for first-treatment-year variable
                first_treat_candidates = [c for c in df.columns
                                          if any(k in c.lower() for k in
                                                 ["first_treat", "gname", "first_year",
                                                  "adoption_year", "treat_year"])]
                if first_treat_candidates:
                    ft_col = first_treat_candidates[0]
                    n_cohorts = df[ft_col].dropna().nunique()
                    print(f"    Staggered cohort var: {ft_col} ({n_cohorts} cohorts)")
                    if n_cohorts < 2:
                        programmatic_flags.append({
                            "check": "did_no_stagger",
                            "severity": "CRITICAL",
                            "detail": f"Staggered DiD needs 2+ treatment cohorts. "
                                      f"{ft_col} has only {n_cohorts}.",
                        })
                else:
                    programmatic_flags.append({
                        "check": "did_no_cohort_var",
                        "severity": "WARNING",
                        "detail": "Staggered DiD proposed but no first-treatment-year variable found.",
                    })

    elif design == "rdd":
        print(f"\n  B. RDD-specific checks:")

        # B1. Find running variable
        idea_method = (selected_idea.get("method", "") + " " +
                       selected_idea.get("identification_source", "")).lower()
        running_found = False
        for candidate in df.select_dtypes(include=[np.number]).columns:
            if candidate in ("treat",):
                continue
            nunique = df[candidate].nunique()
            if nunique >= 20 and candidate.lower() in idea_method:
                running_found = True
                print(f"    Running variable: {candidate} ({nunique} unique values)")

                # B2. Discrete running variable check
                if nunique < 20:
                    programmatic_flags.append({
                        "check": "rdd_discrete_running",
                        "severity": "WARNING",
                        "detail": f"Running variable {candidate} has only {nunique} unique values. "
                                  f"Consider Kolesar-Rothe correction for discrete RV.",
                    })

                # B3. Observations on both sides of threshold
                below = (df[candidate] < 0).sum()
                above = (df[candidate] >= 0).sum()
                print(f"    Below threshold: {below}, Above: {above}")
                if below < 10 or above < 10:
                    programmatic_flags.append({
                        "check": "rdd_one_sided",
                        "severity": "CRITICAL",
                        "detail": f"Only {min(below, above)} observations on one side "
                                  f"of threshold. RDD needs obs on both sides.",
                    })

                # B4. Density near threshold
                near = ((df[candidate] > -2) & (df[candidate] < 2)).sum()
                print(f"    Near threshold (±2): {near}")
                if near < 30:
                    programmatic_flags.append({
                        "check": "rdd_sparse_threshold",
                        "severity": "WARNING",
                        "detail": f"Only {near} obs near threshold. RDD may be underpowered.",
                    })
                break

        if not running_found:
            programmatic_flags.append({
                "check": "rdd_no_running",
                "severity": "WARNING",
                "detail": "Could not identify running variable in dataset.",
            })

        # B5. Panel RDD: check periods
        if n_periods > 1:
            print(f"    Panel RDD: {n_periods} periods for FE augmentation.")

    elif design == "rct":
        print(f"\n  B. RCT-specific checks:")

        # B1. Treatment arm sizes
        if "treat" in df.columns:
            # Look for actual arm variable (may be multi-valued, not just 0/1)
            arm_candidates = [c for c in df.columns
                              if any(k in c.lower() for k in
                                     ["treatstat", "treatment_arm", "arm", "group",
                                      "condition", "assigned"])]
            arm_col = arm_candidates[0] if arm_candidates else "treat"
            arm_counts = df[arm_col].value_counts()
            print(f"    Treatment arms ({arm_col}):")
            for arm, count in arm_counts.items():
                print(f"      {arm}: N={count:,}")

            min_arm = arm_counts.min()
            if min_arm < 30:
                programmatic_flags.append({
                    "check": "rct_small_arm",
                    "severity": "CRITICAL",
                    "detail": f"Smallest arm has {min_arm} obs (need 30+ per arm).",
                })

        # B2. Check for endline outcomes
        endline_prefixes = ["end_", "post_", "follow_", "wave2_", "w2_", "e_", "midline_"]
        endline_cols = [c for c in df.columns
                        if any(c.lower().startswith(p) for p in endline_prefixes)]
        print(f"    Endline columns found: {len(endline_cols)}")
        if endline_cols:
            print(f"    Examples: {endline_cols[:5]}")
        else:
            programmatic_flags.append({
                "check": "rct_no_endline",
                "severity": "WARNING",
                "detail": "No endline/follow-up columns detected (end_, post_, follow_, etc.). "
                          "Verify outcome variables are from the post-treatment survey.",
            })

        # B3. Covariate balance quick check (SMD > 0.25 = suspicious)
        if n_treated > 0 and n_control > 0:
            baseline_cols = [c for c in df.select_dtypes(include=[np.number]).columns
                            if c.startswith("b_") or c.startswith("baseline_")][:10]
            if baseline_cols:
                print(f"    Quick balance check (baseline covariates):")
                for col in baseline_cols:
                    t_mean = df.loc[df["treat"] == 1, col].mean()
                    c_mean = df.loc[df["treat"] == 0, col].mean()
                    pooled_sd = df[col].std()
                    if pooled_sd > 0:
                        smd = abs(t_mean - c_mean) / pooled_sd
                        flag = " *IMBALANCED*" if smd > 0.25 else ""
                        print(f"      {col}: SMD = {smd:.3f}{flag}")
                        if smd > 0.25:
                            programmatic_flags.append({
                                "check": "rct_imbalance",
                                "severity": "WARNING",
                                "detail": f"Covariate {col} has SMD={smd:.2f} (>0.25). "
                                          f"Check randomization.",
                            })

    elif design == "iv":
        print(f"\n  B. IV-specific checks:")

        # B1. Find instrument
        idea_id = (selected_idea.get("identification_source", "") + " " +
                   selected_idea.get("method", "")).lower()
        instrument_found = False
        instrument_col = None

        for col in df.columns:
            if col.lower() in idea_id and col != "treat":
                nunique = df[col].dropna().nunique()
                if nunique >= 2 and df[col].dtype in ("float64", "int64", "float32", "int32"):
                    instrument_found = True
                    instrument_col = col
                    print(f"    Instrument: {col} ({nunique} unique values)")
                    break

        if not instrument_found:
            programmatic_flags.append({
                "check": "iv_no_instrument",
                "severity": "WARNING",
                "detail": "Could not identify instrument variable in dataset.",
            })

        # B2. Quick first stage F-test
        if instrument_col and "treat" in df.columns:
            try:
                import statsmodels.api as sm
                iv_sub = df[[instrument_col, "treat"]].dropna()
                X = sm.add_constant(iv_sub[instrument_col])
                mod = sm.OLS(iv_sub["treat"], X).fit()
                f_stat = mod.fvalue
                f_pval = mod.f_pvalue
                print(f"    First stage F-stat: {f_stat:.2f} (p={f_pval:.4f})")

                if f_stat < 10:
                    programmatic_flags.append({
                        "check": "iv_weak_first_stage",
                        "severity": "CRITICAL",
                        "detail": f"First stage F={f_stat:.1f} < 10. WEAK INSTRUMENT. "
                                  f"2SLS will be biased. Need Anderson-Rubin CI.",
                    })
                elif f_stat < 20:
                    programmatic_flags.append({
                        "check": "iv_moderate_first_stage",
                        "severity": "WARNING",
                        "detail": f"First stage F={f_stat:.1f}. Moderate strength. "
                                  f"Report Anderson-Rubin CI as robustness.",
                    })
            except Exception as e:
                print(f"    Could not compute first stage: {e}")

        # B3. Instrument-outcome correlation (reduced form)
        if instrument_col and outcome_col in df.columns:
            try:
                corr = df[[instrument_col, outcome_col]].dropna().corr().iloc[0, 1]
                print(f"    Reduced form correlation (instrument-outcome): {corr:.4f}")
                if abs(corr) < 0.02:
                    programmatic_flags.append({
                        "check": "iv_no_reduced_form",
                        "severity": "WARNING",
                        "detail": f"Instrument-outcome correlation is {corr:.4f}. "
                                  f"Reduced form may be zero.",
                    })
            except Exception:
                pass

        # B4. Panel IV periods
        if n_periods > 1:
            print(f"    Panel IV: {n_periods} periods for FE specification.")

    # ── Report programmatic flags ─────────────────────────────────────
    critical_prog = [f for f in programmatic_flags if f["severity"] == "CRITICAL"]
    warning_prog = [f for f in programmatic_flags if f["severity"] == "WARNING"]

    if critical_prog:
        print(f"\n  {'=' * 60}")
        print(f"  DESIGN VALIDATION: {len(critical_prog)} CRITICAL PROBLEM(S)")
        print(f"  {'=' * 60}")
        for f in critical_prog:
            print(f"  [{f['check']}] {f['detail']}")

    if warning_prog:
        print(f"\n  Warnings:")
        for f in warning_prog:
            print(f"    [{f['check']}] {f['detail']}")

    if not programmatic_flags:
        print(f"\n  All programmatic checks passed for {design} design.")

    # If critical programmatic issues, offer to re-select before Claude check
    if critical_prog:
        print(f"\n  Options:")
        print(f"    1 - Proceed to Claude feasibility check anyway")
        print(f"    2 - Try a different idea from Stage 2")
        print("\a", end="", flush=True)

        while True:
            choice = input("\n  >> ").strip()
            if choice == "1":
                print("  [ok] Proceeding to Claude feasibility check.")
                break
            elif choice == "2":
                print("  [loop] Returning to Stage 2.5.")
                state["stages"]["stage3_3"] = {
                    "status": "failed",
                    "action": "retry_idea",
                    "flags": [f"{f['check']}: {f['detail']}" for f in critical_prog],
                    "programmatic_flags": programmatic_flags,
                    "completed_at": datetime.now().isoformat(),
                }
                save_state(project_dir, state)
                return state
            else:
                print("  Enter 1 or 2.")

    # ===================================================================
    # TEST -1: Idea-Dataset Feasibility Check (Claude-based)
    # ===================================================================
    # Uses Claude to verify that the selected idea is actually feasible
    # with this specific dataset. Catches problems that programmatic
    # checks can't detect (e.g., conceptual mismatches, wrong variable
    # interpretations, missing mechanisms).
    print("\n  [3.3] Test -1: Idea-dataset feasibility check (Claude)...")

    idea_text_full = (
        f"Title: {selected_idea.get('title', '?')}\n"
        f"RQ: {selected_idea.get('research_question', '?')}\n"
        f"Method: {selected_idea.get('method', '?')}\n"
        f"Data sources: {selected_idea.get('data_sources', [])}\n"
        f"Identification: {selected_idea.get('identification_source', '?')}\n"
    )

    # Build dataset profile for Claude
    treated_mask = df["treat"] == 1
    n_treated = treated_mask.sum()
    n_control = (df["treat"] == 0).sum()

    # Get stats for all columns mentioned in idea + key columns
    idea_lower = idea_text_full.lower()
    relevant_cols = []
    for col in df.columns:
        if col.lower() in idea_lower or idea_lower.find(col.lower()) >= 0:
            relevant_cols.append(col)
    # Also add outcome and common structure indicators
    relevant_cols.extend([outcome_col, "treat", entity_col, time_col])
    relevant_cols = list(set(c for c in relevant_cols if c and c in df.columns))

    col_profiles = []
    for col in relevant_cols[:30]:
        s_all = df[col].dropna()
        s_treated = df.loc[treated_mask, col].dropna()
        s_control = df.loc[~treated_mask, col].dropna()
        profile = (
            f"  {col}: dtype={df[col].dtype}, "
            f"N_total={len(s_all)}, N_treated={len(s_treated)}, N_control={len(s_control)}, "
            f"nunique_treated={s_treated.nunique()}"
        )
        if df[col].dtype in ("float64", "int64", "float32", "int32"):
            profile += f", mean_treated={s_treated.mean():.3f}" if len(s_treated) > 0 else ""
        col_profiles.append(profile)

    # Check data structure
    n_entities = df[entity_col].nunique() if entity_col else 0
    n_times = df[time_col].nunique() if time_col else 0
    is_panel = n_entities > 1 and n_times > 1 and len(df) > n_entities

    data_profile_text = (
        f"Shape: {len(df)} rows x {df.shape[1]} columns\n"
        f"N treated: {n_treated}, N control: {n_control}\n"
        f"Entity column: {entity_col} ({n_entities} unique values)\n"
        f"Time column: {time_col} ({n_times} unique values)\n"
        f"Appears to be: {'panel data' if is_panel else 'cross-section or pooled'}\n"
        f"All columns ({df.shape[1]}): {', '.join(df.columns[:60])}\n"
        f"{'... and ' + str(df.shape[1]-60) + ' more' if df.shape[1] > 60 else ''}\n\n"
        f"Key variable profiles:\n" + "\n".join(col_profiles)
    )

    feasibility_prompt = f"""You are validating whether a research idea is FEASIBLE with a specific dataset.
Your job is to find DEALBREAKERS — problems that make the idea impossible or
fundamentally flawed with this data. Do NOT flag minor issues.

RESEARCH IDEA:
{idea_text_full}

DATASET PROFILE:
{data_profile_text}

Check each of these and report ONLY problems found:

1. VARIABLE EXISTENCE: Does the dataset contain the key variables the idea needs?
   (treatment, outcome, moderators, instruments, controls). If a variable mentioned
   in the idea does not exist in the dataset, that is a CRITICAL problem.

2. VARIABLE VARIATION: Do key variables have variation where needed?
   - Treatment: has variation (already verified)
   - Moderators/interaction variables: must have variation IN THE TREATED SAMPLE
     (check N_treated and nunique_treated). If nunique_treated < 2, the interaction
     analysis is impossible.
   - Outcomes: must not be >80% missing

3. DATA STRUCTURE: Does the idea assume panel data but the dataset is cross-section?
   Does it assume multiple time periods but there's only one? Does it need pre/post
   periods for DiD but the data is cross-sectional?

4. SAMPLE SIZE: Is N_treated large enough for the proposed analysis?
   - Simple OLS/ITT: N >= 50 per arm is minimum
   - Interaction terms: N >= 100 per cell (arm x moderator level)
   - IV/2SLS: need strong first stage, N >= 200
   - Subgroup analysis: each subgroup needs N >= 30

5. INSTRUMENT VALIDITY: If the idea uses IV, does the instrument variable exist?
   Does it have variation? Is it correlated with treatment?

6. OUTCOME QUALITY: Is the primary outcome variable mostly non-missing in the
   analysis sample? If >50% missing, analysis is unreliable.

Output a JSON block:
```json
{{
  "feasible": true,
  "critical_problems": [
    {{
      "category": "variable_variation|missing_variable|wrong_structure|sample_size|instrument|outcome",
      "variable": "variable_name",
      "description": "what the problem is",
      "impact": "why the idea cannot work without this"
    }}
  ],
  "warnings": [
    {{
      "category": "same categories",
      "description": "non-fatal but worth noting"
    }}
  ],
  "summary": "one sentence: feasible / feasible with caveats / NOT feasible"
}}
```

If no problems found, set feasible=true and critical_problems=[].
Be CONSERVATIVE: only flag CRITICAL if the analysis truly cannot be done.
"""

    p = get_profile("stage3_3_test")
    feasibility_resp = run_claude(
        feasibility_prompt, model=p["model"], effort=p["effort"],
        allowed_tools=[], label="feasibility-check"
    )
    feasibility_result = extract_json(feasibility_resp) or {
        "feasible": True, "critical_problems": [], "warnings": []
    }

    critical_problems = feasibility_result.get("critical_problems", [])
    feasibility_warnings = feasibility_result.get("warnings", [])
    feasibility_summary = feasibility_result.get("summary", "")

    # Display results
    if critical_problems:
        print(f"\n  {'=' * 60}")
        print(f"  IDEA-DATASET FEASIBILITY PROBLEMS DETECTED")
        print(f"  {'=' * 60}")
        for i, prob in enumerate(critical_problems, 1):
            cat = prob.get("category", "?")
            var = prob.get("variable", "")
            desc = prob.get("description", "?")
            impact = prob.get("impact", "")
            var_str = f" ({var})" if var else ""
            print(f"  {i}. [{cat.upper()}]{var_str}")
            print(f"     {desc}")
            if impact:
                print(f"     Impact: {impact}")
        print(f"\n  Summary: {feasibility_summary}")

    if feasibility_warnings:
        print(f"\n  Warnings:")
        for w in feasibility_warnings:
            print(f"    - [{w.get('category', '?')}] {w.get('description', '?')}")

    if not critical_problems and not feasibility_warnings:
        print(f"  [PASS] Idea is feasible with this dataset.")

    # Save feasibility results for downstream stages
    het_vars_flagged = [
        {"var": p.get("variable", ""), "issue": p.get("description", ""), "severity": "CRITICAL"}
        for p in critical_problems
    ]
    het_vars_ok = []  # Will be populated below if no critical problems

    # If critical problems, offer to re-select
    if critical_problems:
        print(f"\n  {'=' * 60}")
        print(f"  The selected idea has {len(critical_problems)} critical ")
        print(f"  compatibility problem(s) with this dataset.")
        print(f"\n  Options:")
        print(f"    1 - Proceed anyway (analysis will be adapted)")
        print(f"    2 - Try a different idea from Stage 2")
        print(f"  {'=' * 60}")
        print("\a", end="", flush=True)

        while True:
            choice = input("\n  >> ").strip()
            if choice == "1":
                print("  [ok] Proceeding — analysis will need adaptation.")
                break
            elif choice == "2":
                print("  [loop] Returning to Stage 2.5 to select a different idea.")
                state["stages"]["stage3_3"] = {
                    "status": "failed",
                    "action": "retry_idea",
                    "flags": [f"{p.get('category', '?')}: {p.get('description', '?')}"
                              for p in critical_problems],
                    "feasibility": feasibility_result,
                    "completed_at": datetime.now().isoformat(),
                }
                save_state(project_dir, state)
                return state
            else:
                print("  Enter 1 or 2.")

    # ===================================================================
    # TEST 0: Package Availability & Estimator Verification
    # ===================================================================
    print("\n  [3.3] Test 0: Verifying available estimators on real data...")

    available_estimators = {}
    estimator_warnings = []

    # Check pyfixest
    try:
        import pyfixest as pf
        available_estimators["pyfixest"] = True
        print("  [3.3]   pyfixest %s: installed" % pf.__version__)

        # Test feols on real data (subsample for speed)
        try:
            _test_df = df[[outcome_col, "treat", entity_col, time_col]].dropna().head(500).copy()
            _test_df["_eid"] = pd.Categorical(_test_df[entity_col]).codes
            _fml = "%s ~ treat | _eid + %s" % (outcome_col, time_col)
            _fit = pf.feols(_fml, data=_test_df, vcov={"CRV1": "_eid"})
            _fit.coef()
            available_estimators["pyfixest_feols"] = True
            print("  [3.3]   pyfixest feols: works on this data")
        except Exception as e:
            available_estimators["pyfixest_feols"] = False
            estimator_warnings.append("pyfixest feols failed: %s" % str(e)[:100])
            print("  [3.3]   pyfixest feols: FAILED (%s)" % str(e)[:80])

        # Test staggered DiD estimators if applicable
        gname_col = None
        for candidate in ["first_oil_year", "first_treat_year", "g", "gname"]:
            if candidate in df.columns:
                gname_col = candidate
                break

        if gname_col and (design == "staggered_did" or df[gname_col].nunique() > 2):
            _test_df2 = df[[outcome_col, entity_col, time_col, gname_col]].dropna().copy()
            _test_df2["_eid"] = pd.Categorical(_test_df2[entity_col]).codes

            # Test event_study TWFE
            try:
                _fit2 = pf.did.event_study(
                    data=_test_df2, yname=outcome_col, idname="_eid",
                    tname=time_col, gname=gname_col,
                    estimator="twfe", att=True
                )
                _fit2.tidy()
                available_estimators["pyfixest_es_twfe"] = True
                print("  [3.3]   pyfixest event_study(twfe): works")
            except Exception as e:
                available_estimators["pyfixest_es_twfe"] = False
                estimator_warnings.append("event_study(twfe) failed: %s" % str(e)[:100])
                print("  [3.3]   pyfixest event_study(twfe): FAILED")

            # Test DID2S (Gardner)
            try:
                _fit3 = pf.did.event_study(
                    data=_test_df2, yname=outcome_col, idname="_eid",
                    tname=time_col, gname=gname_col,
                    estimator="did2s", att=True
                )
                _fit3.tidy()
                available_estimators["pyfixest_did2s"] = True
                print("  [3.3]   pyfixest DID2S (Gardner): works")
            except Exception as e:
                available_estimators["pyfixest_did2s"] = False
                estimator_warnings.append("DID2S failed: %s" % str(e)[:100])
                print("  [3.3]   pyfixest DID2S (Gardner): FAILED")

            # Test saturated (Sun-Abraham style)
            try:
                _fit4 = pf.did.event_study(
                    data=_test_df2, yname=outcome_col, idname="_eid",
                    tname=time_col, gname=gname_col,
                    estimator="saturated", att=True
                )
                _fit4.tidy()
                available_estimators["pyfixest_sunab"] = True
                print("  [3.3]   pyfixest saturated (Sun-Abraham): works")
            except Exception as e:
                available_estimators["pyfixest_sunab"] = False
                estimator_warnings.append("Sun-Abraham failed: %s" % str(e)[:100])
                print("  [3.3]   pyfixest saturated (Sun-Abraham): FAILED")

    except ImportError:
        available_estimators["pyfixest"] = False
        print("  [3.3]   pyfixest: NOT INSTALLED")

    # Check linearmodels
    try:
        from linearmodels.panel import PanelOLS  # noqa: F811
        available_estimators["linearmodels"] = True
        print("  [3.3]   linearmodels PanelOLS: installed")
    except ImportError:
        available_estimators["linearmodels"] = False
        print("  [3.3]   linearmodels: NOT INSTALLED")

    # Check csdid
    try:
        import csdid  # noqa: F811
        available_estimators["csdid"] = True
        print("  [3.3]   csdid: installed")
    except ImportError:
        available_estimators["csdid"] = False

    # Check HTE stack
    try:
        import sklearn  # noqa: F401
        available_estimators["sklearn"] = True
        print("  [3.3]   sklearn: installed")
    except ImportError:
        available_estimators["sklearn"] = False
        print("  [3.3]   sklearn: NOT INSTALLED")

    try:
        import econml  # noqa: F401
        available_estimators["econml"] = True
        print("  [3.3]   econml: installed")
    except ImportError:
        available_estimators["econml"] = False
        if design == "hte":
            estimator_warnings.append(
                "econml is not installed; HTE scripts must add requirements.txt or use OLS-interaction fallback"
            )
        print("  [3.3]   econml: NOT INSTALLED")

    # Summary
    working = [k for k, v in available_estimators.items() if v]
    broken = [k for k, v in available_estimators.items() if not v and k != "csdid"]

    if estimator_warnings:
        print("\n  [3.3] ESTIMATOR WARNINGS:")
        for w in estimator_warnings:
            print("    - %s" % w)
        print("\n  [3.3] The referee checklist may require estimators that do NOT work")
        print("  [3.3] with this data. The pipeline will NOT promise these methods.")
        print("  [3.3] Working: %s" % ", ".join(working))
        if broken:
            print("  [3.3] Broken:  %s" % ", ".join(broken))
    else:
        print("\n  [3.3] All tested estimators work on this data.")

    # ===================================================================
    # TEST 1: Basic DiD
    # ===================================================================
    print("\n  [3.3] Test 1: Basic DiD...")
    did_result = _quick_did_test(df, outcome_col, "treat", entity_col, time_col)
    if did_result["error"]:
        print(f"  [3.3] DiD failed: {did_result['error']}")
    else:
        sig = "***" if did_result["p"] < 0.01 else "**" if did_result["p"] < 0.05 else "*" if did_result["p"] < 0.1 else ""
        print(f"  [3.3] ATT = {did_result['att']:+.4f} (SE={did_result['se']:.4f}, "
              f"p={did_result['p']:.4f}){sig}  N={did_result['n']:,}")

    # ===================================================================
    # TEST 2: Permutation test (200 permutations for speed)
    # ===================================================================
    print("  [3.3] Test 2: Permutation test (200 draws)...")
    perm_p = _quick_permutation_test(df, outcome_col, "treat", entity_col, time_col,
                                      n_perms=200)
    if not np.isnan(perm_p):
        print(f"  [3.3] Permutation p-value: {perm_p:.3f}")
    else:
        print(f"  [3.3] Permutation test failed")

    # ===================================================================
    # TEST 3: Country/entity trends
    # ===================================================================
    print("  [3.3] Test 3: Entity-specific trends...")
    trend_result = _quick_trend_test(df, outcome_col, "treat", entity_col, time_col)
    if not np.isnan(trend_result["att"]):
        print(f"  [3.3] ATT with trends = {trend_result['att']:+.4f} "
              f"(p={trend_result['p']:.4f})")
    else:
        print(f"  [3.3] Trend test failed")

    # ===================================================================
    # TEST 4: DESIGN-SPECIFIC IDENTIFICATION TESTS
    # ===================================================================
    design = _detect_design(selected_idea)
    design_flags = []

    if design == "iv":
        print("\n  [3.3] Test 4: IV-specific — First stage F-test...")
        # Detect instrument and endogenous variable from idea
        idea_text = (selected_idea.get("method", "") + " " +
                     selected_idea.get("identification_source", "")).lower()
        # Look for instrument candidates in data
        import statsmodels.api as _sm_iv
        instrument_col = None
        endogenous_col = None
        # Heuristic: find column most correlated with treatment that isn't the outcome
        for col in df.select_dtypes(include=[np.number]).columns:
            if col in (outcome_col, "treat", entity_col, time_col):
                continue
            corr_with_treat = df[["treat", col]].dropna().corr().iloc[0, 1]
            if abs(corr_with_treat) > 0.1 and instrument_col is None:
                instrument_col = col
        if instrument_col:
            sub_iv = df[[outcome_col, "treat", instrument_col]].dropna()
            if len(sub_iv) >= 30:
                # First stage: treat ~ instrument
                y_fs = sub_iv["treat"].values
                X_fs = _sm_iv.add_constant(sub_iv[instrument_col].values)
                try:
                    fs_mod = _sm_iv.OLS(y_fs, X_fs).fit()
                    f_stat = fs_mod.fvalue
                    f_pval = fs_mod.f_pvalue
                    print(f"  [3.3] First stage: {instrument_col} -> treat")
                    print(f"  [3.3] F-statistic: {f_stat:.2f} (p={f_pval:.4f})")
                    if f_stat < 10:
                        design_flags.append(
                            f"WEAK INSTRUMENT: First-stage F = {f_stat:.1f} < 10. "
                            f"IV estimates will be unreliable.")
                        print(f"  [3.3] *** WEAK INSTRUMENT (F < 10) ***")
                    elif f_stat < 16.38:
                        design_flags.append(
                            f"Borderline instrument: F = {f_stat:.1f} < 16.38 "
                            f"(Stock-Yogo 10% critical value).")
                except Exception as e:
                    print(f"  [3.3] First stage test failed: {e}")
        else:
            print("  [3.3] No instrument candidate auto-detected. Skipping F-test.")
            design_flags.append("IV design proposed but no instrument variable identified in data.")

    elif design == "rdd":
        print("\n  [3.3] Test 4: RDD-specific — Density / manipulation test...")
        # Look for running variable
        running_candidates = [c for c in df.columns
                              if any(kw in c.lower() for kw in
                                     ["score", "running", "margin", "vote", "index",
                                      "distance", "cutoff", "threshold"])]
        if running_candidates:
            rv = running_candidates[0]
            rv_vals = df[rv].dropna().values
            if len(rv_vals) >= 50:
                # Check density around zero (or median as proxy cutoff)
                cutoff = 0 if (rv_vals.min() < 0 and rv_vals.max() > 0) else np.median(rv_vals)
                n_left = np.sum(rv_vals < cutoff)
                n_right = np.sum(rv_vals >= cutoff)
                ratio = n_left / n_right if n_right > 0 else 0
                print(f"  [3.3] Running var: {rv}, cutoff={cutoff:.2f}")
                print(f"  [3.3] N_left={n_left}, N_right={n_right}, ratio={ratio:.2f}")
                if ratio < 0.3 or ratio > 3.0:
                    design_flags.append(
                        f"Density imbalance at cutoff: ratio={ratio:.2f}. "
                        f"Possible manipulation (McCrary test needed).")
                if n_left < 30 or n_right < 30:
                    design_flags.append(
                        f"Too few observations near cutoff: N_left={n_left}, N_right={n_right}. "
                        f"Need >=30 on each side.")
        else:
            design_flags.append("RDD design proposed but no running variable identified in data.")
            print("  [3.3] No running variable candidate found.")

    elif design in ("did", "staggered_did"):
        print("\n  [3.3] Test 4: DiD-specific — Pre-treatment period check...")
        # Count pre-treatment periods
        if time_col in df.columns:
            pre_periods = df[df["treat"] == 0][time_col].nunique()
            total_periods = df[time_col].nunique()
            print(f"  [3.3] Pre-treatment periods: {pre_periods}/{total_periods}")
            if pre_periods < 2:
                design_flags.append(
                    f"Only {pre_periods} pre-treatment period(s). "
                    f"Cannot test parallel trends with <2 pre-periods. "
                    f"Referees will question identification.")
            if pre_periods < 1:
                design_flags.append(
                    "NO pre-treatment period. DiD identification is NOT credible "
                    "without at least 1 pre-treatment period.")

        # Check for staggered: are there multiple treatment timing groups?
        if design == "staggered_did":
            treat_start = df[df["treat"] == 1].groupby(entity_col)[time_col].min()
            n_cohorts = treat_start.nunique()
            print(f"  [3.3] Treatment timing cohorts: {n_cohorts}")
            if n_cohorts < 2:
                design_flags.append(
                    f"Staggered DiD claimed but only {n_cohorts} treatment cohort. "
                    f"Need >=2 cohorts for staggered design.")

    # RCT-specific: covariate balance
    if design == "rct" or any(kw in (selected_idea.get("method", "")).lower()
                              for kw in ["rct", "randomized", "experiment"]):
        print("\n  [3.3] Test 4: RCT-specific — Covariate balance check...")
        numeric_cols = [c for c in df.select_dtypes(include=[np.number]).columns
                        if c not in (outcome_col, "treat", entity_col, time_col)]
        imbalanced = 0
        tested = 0
        for col in numeric_cols[:15]:
            sub_bal = df[["treat", col]].dropna()
            if len(sub_bal) < 20:
                continue
            g0 = sub_bal.loc[sub_bal["treat"] == 0, col]
            g1 = sub_bal.loc[sub_bal["treat"] == 1, col]
            if len(g0) < 5 or len(g1) < 5:
                continue
            tested += 1
            pooled_sd = np.sqrt((g0.var() + g1.var()) / 2)
            if pooled_sd > 0:
                smd = abs(g1.mean() - g0.mean()) / pooled_sd
                if smd > 0.25:
                    imbalanced += 1
                    print(f"  [3.3] IMBALANCED: {col} (SMD={smd:.3f})")

        if tested > 0:
            pct_imbalanced = 100 * imbalanced / tested
            print(f"  [3.3] Balance: {imbalanced}/{tested} covariates imbalanced (SMD>0.25)")
            if pct_imbalanced > 30:
                design_flags.append(
                    f"{pct_imbalanced:.0f}% of covariates show SMD>0.25. "
                    f"Randomization may have failed.")

    if design_flags:
        print(f"\n  [3.3] Design-specific issues found:")
        for df_flag in design_flags:
            print(f"    - {df_flag}")

    # ===================================================================
    # VERDICT
    # ===================================================================
    print(f"\n  {'=' * 60}")
    print(f"  QUICK EMPIRICAL TEST RESULTS")
    print(f"  {'=' * 60}")

    flags = list(design_flags)  # Start with design-specific flags
    passed = len([f for f in design_flags
                  if "WEAK INSTRUMENT" in f or "NO pre-treatment" in f
                  or "manipulation" in f or "Randomization may have failed" in f]) == 0

    # Check 1: Is the basic effect significant?
    if not np.isnan(did_result.get("p", np.nan)) and did_result["p"] > 0.1:
        flags.append("Basic DiD is NOT significant (p > 0.10)")
        # Not fatal -- could be a power issue

    # Check 1b: Effect size magnitude (Cohen's d)
    att = did_result.get("att", np.nan)
    outcome_sd = df[outcome_col].std() if outcome_col in df.columns else np.nan
    cohens_d = abs(att / outcome_sd) if (not np.isnan(att) and not np.isnan(outcome_sd)
                                          and outcome_sd > 1e-10) else np.nan

    if not np.isnan(cohens_d):
        pct_change = 100 * abs(att) / abs(df[outcome_col].mean()) if abs(df[outcome_col].mean()) > 1e-10 else np.nan
        print(f"  [3.3] Effect size: Cohen's d = {cohens_d:.3f}, "
              f"|ATT|/SD = {cohens_d:.3f}, "
              f"%change = {pct_change:.1f}%" if not np.isnan(pct_change) else "")

        if cohens_d < 0.02:
            flags.append(f"Effect is TRIVIALLY SMALL (Cohen's d = {cohens_d:.4f} < 0.02). "
                         "Even if significant, no referee will consider this economically meaningful.")
            passed = False
        elif cohens_d < 0.05:
            flags.append(f"Effect is VERY SMALL (Cohen's d = {cohens_d:.3f} < 0.05). "
                         "May be underpowered or economically trivial.")
        elif cohens_d > 2.0:
            flags.append(f"Effect is IMPLAUSIBLY LARGE (Cohen's d = {cohens_d:.1f} > 2.0). "
                         "Check for data errors, scaling issues, or specification problems.")

    # Check 1c: Power analysis — is the sample large enough to detect the effect?
    n_obs = did_result.get("n", 0)
    if n_obs > 0 and not np.isnan(outcome_sd) and outcome_sd > 0:
        from scipy import stats as _sp_stats
        z_alpha = _sp_stats.norm.ppf(0.975)
        z_beta = _sp_stats.norm.ppf(0.80)
        mde = (z_alpha + z_beta) * outcome_sd * np.sqrt(4.0 / n_obs)
        mde_cohens_d = mde / outcome_sd

        print(f"  [3.3] Power: MDE = {mde:.4f} (Cohen's d = {mde_cohens_d:.3f}) at 80% power")

        if not np.isnan(cohens_d) and cohens_d < mde_cohens_d:
            flags.append(f"Study is UNDERPOWERED: detected effect (d={cohens_d:.3f}) < MDE "
                         f"(d={mde_cohens_d:.3f}). Need ~{int((z_alpha + z_beta)**2 * 4 / cohens_d**2)} "
                         f"obs for 80% power at this effect size.")

    # Check 2: Does permutation test pass?
    if not np.isnan(perm_p) and perm_p > 0.1:
        flags.append(f"Permutation test FAILS (p = {perm_p:.3f}) -- "
                     "effect does not survive randomization inference")
        passed = False

    # Check 3: Do entity trends eliminate the effect?
    if (not np.isnan(trend_result.get("p", np.nan)) and trend_result["p"] > 0.1
            and not np.isnan(did_result.get("p", np.nan)) and did_result["p"] < 0.1):
        flags.append(f"Entity trends ELIMINATE the effect (p = {trend_result['p']:.3f}) -- "
                     "likely a pre-existing trend, not a treatment effect")
        passed = False

    if passed and not flags:
        print(f"  [PASS] All quick tests passed!")
        print(f"  Proceed to Stage 3.5 with confidence.")
        score_adjustment = 0
    elif passed and flags:
        print(f"  [WARN] Tests passed but with warnings:")
        for f in flags:
            print(f"    - {f}")
        score_adjustment = -5
    else:
        print(f"  [FAIL] Identification strategy is FRAGILE on actual data:")
        for f in flags:
            print(f"    - {f}")
        print()
        print(f"  The proposed strategy looks good on paper (Level {selected_idea.get('identification_level', '?')})")
        print(f"  but does NOT hold empirically. Expected score ceiling: ~70")
        print()
        print(f"  Options:")
        print(f"    1 - Proceed anyway (score will be capped ~70)")
        print(f"    2 - Try a different idea from Stage 2")
        print(f"    3 - Provide new data with stronger variation")
        print(f"  {'=' * 60}")
        print("\a", end="", flush=True)

        while True:
            choice = input("\n  >> ").strip()
            if choice == "1":
                print("  [ok] Proceeding with fragile identification.")
                score_adjustment = -15
                break
            elif choice == "2":
                print("  [loop] Returning to Stage 2.5 to select a different idea.")
                state["stages"]["stage3_3"] = {
                    "status": "failed",
                    "action": "retry_idea",
                    "flags": flags,
                    "completed_at": datetime.now().isoformat(),
                }
                save_state(project_dir, state)
                return state
            elif choice == "3":
                print("  [stop] Provide new data and restart from Stage 1.")
                sys.exit(0)
            else:
                print("  Enter 1, 2, or 3.")
                continue

    # Save results (including which estimators work for Stage 4)
    state["stages"]["stage3_3"] = {
        "status": "completed",
        "passed": passed,
        "flags": flags,
        "score_adjustment": score_adjustment,
        "did_att": did_result.get("att"),
        "did_p": did_result.get("p"),
        "did_n": did_result.get("n"),
        "cohens_d": cohens_d if not np.isnan(cohens_d) else None,
        "outcome_sd": outcome_sd if not np.isnan(outcome_sd) else None,
        "perm_p": perm_p if not np.isnan(perm_p) else None,
        "trend_att": trend_result.get("att"),
        "trend_p": trend_result.get("p"),
        "available_estimators": available_estimators,
        "estimator_warnings": estimator_warnings,
        "het_vars_ok": het_vars_ok,
        "het_vars_flagged": het_vars_flagged,
        "completed_at": datetime.now().isoformat(),
    }

    state["current_stage"] = 3.3
    save_state(project_dir, state)
    return state
