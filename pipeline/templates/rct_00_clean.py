"""00_clean.py - RCT data cleaning template.

Project-specific variables (in the section below) are filled by Claude.
Everything below the FIXED CODE marker handles known RCT pitfalls and must
not be modified.
"""

import os
import sys
import numpy as np
import pandas as pd

# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT-SPECIFIC VARIABLES (Claude fills these)
# ═══════════════════════════════════════════════════════════════════════════════
DATA_FILE = "{{DATA_FILE}}"               # e.g., "../../data/external/data.dta"
DATA_FORMAT = "{{DATA_FORMAT}}"           # "stata", "csv", "tab", "parquet"
TREATMENT_VAR = "{{TREATMENT_VAR}}"       # e.g., "treatment" or "assigned"
TREATMENT_ARMS = {{TREATMENT_ARMS}}       # e.g., {"Control": 0, "Cash": 1, "In-kind": 2}
OUTCOME_VARS = {{OUTCOME_VARS}}           # e.g., ["consumption", "income", "health"]
CLUSTER_VAR = "{{CLUSTER_VAR}}"           # e.g., "village_id" or None
COVARIATES = {{COVARIATES}}               # e.g., ["age", "female", "baseline_income"]
STRATA_VAR = "{{STRATA_VAR}}"             # e.g., "strata_id" or None

# ═══════════════════════════════════════════════════════════════════════════════
# FIXED CODE (does not change between projects)
# ═══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_OUT = os.path.join(SCRIPT_DIR, "..", "..", "data", "clean")
os.makedirs(DATA_OUT, exist_ok=True)

print("=" * 70)
print("00_clean.py — RCT Data Cleaning")
print("=" * 70)

# ── Load data ─────────────────────────────────────────────────────────────────
data_path = os.path.join(SCRIPT_DIR, DATA_FILE)
print(f"Loading: {data_path}")

if DATA_FORMAT == "stata":
    df = pd.read_stata(data_path)
elif DATA_FORMAT == "tab":
    df = pd.read_csv(data_path, sep="\t", encoding="latin-1", low_memory=False)
elif DATA_FORMAT == "parquet":
    df = pd.read_parquet(data_path)
else:
    df = pd.read_csv(data_path, encoding="latin-1", low_memory=False)

print(f"Raw data: {len(df):,} rows x {df.shape[1]} cols")

# ── Missingness table ─────────────────────────────────────────────────────────
print("\n--- Missingness table (key variables) ---")
key_vars = [TREATMENT_VAR] + OUTCOME_VARS + COVARIATES
if CLUSTER_VAR:
    key_vars.append(CLUSTER_VAR)
if STRATA_VAR:
    key_vars.append(STRATA_VAR)
key_vars = [v for v in key_vars if v and v in df.columns]

for var in key_vars:
    n_miss = df[var].isna().sum()
    pct = 100 * n_miss / len(df)
    print(f"  {var:30s}: {n_miss:6,} missing ({pct:.1f}%)")

# ── Validate treatment variable exists ────────────────────────────────────────
if TREATMENT_VAR not in df.columns:
    print(f"\nERROR: Treatment variable '{TREATMENT_VAR}' not in data.")
    print(f"Available columns: {list(df.columns[:30])}")
    sys.exit(1)

# ── Filter to valid treatment assignment ──────────────────────────────────────
valid_values = list(TREATMENT_ARMS.values())
n_before = len(df)
df_rct = df[df[TREATMENT_VAR].isin(valid_values)].copy()
n_after = len(df_rct)
print(f"\n--- Filter: valid treatment arms only ---")
print(f"  Before: {n_before:,}  After: {n_after:,}  Dropped: {n_before - n_after:,}")

# ── Validate treatment arms: print N per arm ─────────────────────────────────
print("\n--- Treatment arm validation ---")
control_arm = None
for arm_name, arm_val in TREATMENT_ARMS.items():
    n_arm = (df_rct[TREATMENT_VAR] == arm_val).sum()
    print(f"  {arm_name:20s} (value={arm_val}): N = {n_arm:,}")
    if arm_name.lower() in ("control", "placebo", "comparison", "0"):
        control_arm = arm_val
    elif control_arm is None:
        # Default: smallest value is control
        pass

# If no control explicitly labeled, use the minimum value
if control_arm is None:
    control_arm = min(TREATMENT_ARMS.values())
    control_name = [k for k, v in TREATMENT_ARMS.items() if v == control_arm][0]
    print(f"  Inferred control arm: {control_name} (value={control_arm})")

# Create binary treatment indicator (any treatment vs control)
df_rct["treat_any"] = (df_rct[TREATMENT_VAR] != control_arm).astype(float)

# Create arm dummies
for arm_name, arm_val in TREATMENT_ARMS.items():
    safe_name = arm_name.replace(" ", "_").replace("-", "_").lower()
    df_rct[f"arm_{safe_name}"] = (df_rct[TREATMENT_VAR] == arm_val).astype(float)

n_treated = int(df_rct["treat_any"].sum())
n_control = len(df_rct) - n_treated
print(f"\n  Overall: Treated={n_treated:,}  Control={n_control:,}")

# ── Outcome validation ────────────────────────────────────────────────────────
print("\n--- Outcome validation ---")
outcomes_present = [o for o in OUTCOME_VARS if o in df_rct.columns]
outcomes_missing = [o for o in OUTCOME_VARS if o not in df_rct.columns]

if outcomes_missing:
    print(f"  WARNING: Missing outcomes: {outcomes_missing}")
if not outcomes_present:
    print(f"  ERROR: No outcome variables found in data!")
    sys.exit(1)

for var in outcomes_present:
    s = df_rct[var].dropna()
    ctrl_mean = df_rct.loc[df_rct["treat_any"] == 0, var].mean()
    treat_mean = df_rct.loc[df_rct["treat_any"] == 1, var].mean()
    corr_val = df_rct[[var, "treat_any"]].dropna().corr().iloc[0, 1]
    corr_str = f"{corr_val:.4f}" if not np.isnan(corr_val) else "---"
    print(f"  {var}: N_valid={len(s)}, ctrl_mean={ctrl_mean:.4f}, "
          f"treat_mean={treat_mean:.4f}, corr_with_treat={corr_str}")

# ── Top 10 correlates with treatment ─────────────────────────────────────────
print("\n--- Top 10 variables correlated with treatment ---")
numeric_cols = df_rct.select_dtypes(include=[np.number]).columns
corrs = {}
for col in numeric_cols:
    if col in ("treat_any", TREATMENT_VAR) or col.startswith("arm_"):
        continue
    try:
        r = df_rct[["treat_any", col]].dropna().corr().iloc[0, 1]
        if not np.isnan(r):
            corrs[col] = abs(r)
    except Exception:
        pass

for i, (col, r) in enumerate(sorted(corrs.items(), key=lambda x: -x[1])[:10], 1):
    flag = " <-- potential imbalance" if r > 0.10 else ""
    print(f"  {i:2d}. {col:40s} |r| = {r:.4f}{flag}")

# ── Validate heterogeneity variables have variation IN TREATED SAMPLE ────────
print("\n--- Heterogeneity variable validation (variation in treated) ---")
for var in COVARIATES:
    if var not in df_rct.columns:
        print(f"  {var:30s}: NOT IN DATA")
        continue
    treated_vals = df_rct.loc[df_rct["treat_any"] == 1, var].dropna()
    # FIX: Categorical dtypes (e.g. from Stata labelled vars) cannot be std'd
    # directly. Coerce to numeric where possible; report 'categorical' for
    # non-numeric columns instead of crashing.
    if hasattr(treated_vals, "cat"):
        treated_vals = pd.to_numeric(treated_vals.cat.codes, errors="coerce")
    elif treated_vals.dtype == object:
        treated_vals = pd.to_numeric(treated_vals, errors="coerce").dropna()
    n_unique = treated_vals.nunique()
    if n_unique <= 1:
        print(f"  {var:30s}: NO VARIATION in treated (unique={n_unique}) -- SKIP in heterogeneity")
    else:
        try:
            std_val = float(treated_vals.std())
            print(f"  {var:30s}: OK (unique={n_unique}, std={std_val:.4f})")
        except (TypeError, ValueError):
            print(f"  {var:30s}: OK (unique={n_unique}, non-numeric -- skipping std)")

# ── Balance table (pre-treatment covariates by arm) ──────────────────────────
print("\n--- Balance table (covariates by treatment arm) ---")
cov_avail = [c for c in COVARIATES if c in df_rct.columns]
if cov_avail:
    balance_rows = []
    for cov in cov_avail:
        row = {"variable": cov}
        ctrl_vals = df_rct.loc[df_rct["treat_any"] == 0, cov].dropna()
        # FIX: coerce Categorical/object to numeric before mean/std/var
        if hasattr(ctrl_vals, "cat"):
            ctrl_vals = pd.to_numeric(ctrl_vals.cat.codes, errors="coerce")
        elif ctrl_vals.dtype == object:
            ctrl_vals = pd.to_numeric(ctrl_vals, errors="coerce").dropna()
        try:
            row["ctrl_mean"] = float(ctrl_vals.mean())
            row["ctrl_sd"] = float(ctrl_vals.std())
        except (TypeError, ValueError):
            row["ctrl_mean"] = np.nan
            row["ctrl_sd"] = np.nan
        row["ctrl_n"] = len(ctrl_vals)

        for arm_name, arm_val in TREATMENT_ARMS.items():
            if arm_val == control_arm:
                continue
            safe = arm_name.replace(" ", "_").replace("-", "_").lower()
            arm_vals = df_rct.loc[df_rct[TREATMENT_VAR] == arm_val, cov].dropna()
            diff = arm_vals.mean() - ctrl_vals.mean()
            pooled_sd = np.sqrt((ctrl_vals.var() + arm_vals.var()) / 2)
            norm_diff = diff / pooled_sd if pooled_sd > 0 else np.nan
            row[f"{safe}_diff"] = diff
            row[f"{safe}_normdiff"] = norm_diff
        balance_rows.append(row)

    balance_df = pd.DataFrame(balance_rows)
    print(balance_df.to_string(index=False, float_format="%.4f"))

    # Flag imbalances
    for col in balance_df.columns:
        if col.endswith("_normdiff"):
            max_nd = balance_df[col].abs().max()
            if max_nd > 0.25:
                print(f"  WARNING: Large normalized difference in {col}: {max_nd:.3f}")
else:
    print("  No covariates available for balance test.")

# ── Attrition check ─────────────────────────────────────────────────────────
print("\n--- Attrition check (outcome non-missing by arm) ---")
for var in outcomes_present:
    print(f"\n  Outcome: {var}")
    for arm_name, arm_val in TREATMENT_ARMS.items():
        arm_data = df_rct[df_rct[TREATMENT_VAR] == arm_val]
        n_total = len(arm_data)
        n_observed = arm_data[var].notna().sum()
        n_missing = n_total - n_observed
        attrition_pct = 100 * n_missing / n_total if n_total > 0 else 0
        flag = " <-- HIGH" if attrition_pct > 15 else ""
        print(f"    {arm_name:20s}: {n_observed:,}/{n_total:,} observed "
              f"({attrition_pct:.1f}% attrition){flag}")

    # Test differential attrition
    df_rct[f"_observed_{var}"] = df_rct[var].notna().astype(float)

# ── Save ──────────────────────────────────────────────────────────────────────
out_path = os.path.join(DATA_OUT, "clean_data.csv")
df_rct.to_csv(out_path, index=False)
print(f"\nSaved: {out_path} ({len(df_rct):,} rows x {df_rct.shape[1]} cols)")

# Placeholder results
results_path = os.path.join(DATA_OUT, "main_results.csv")
if not os.path.exists(results_path):
    pd.DataFrame(columns=["outcome", "specification", "arm", "estimate", "se_robust",
                           "ci_lower", "ci_upper", "pvalue", "N", "control_mean",
                           "effect_pct", "method"]
                 ).to_csv(results_path, index=False)
    print(f"Saved placeholder: {results_path}")

print("\n" + "=" * 70)
print("00_clean.py complete.")
print("=" * 70)
