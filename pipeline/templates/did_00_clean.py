"""00_clean.py - DiD data cleaning template.

Project-specific variables (in the section below) are filled by Claude.
Everything below the FIXED CODE marker handles known DiD pitfalls and must
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
ENTITY_VAR = "{{ENTITY_VAR}}"            # e.g., "state_id" or "firm_id"
TIME_VAR = "{{TIME_VAR}}"                # e.g., "year" or "quarter"
TREATMENT_VAR = "{{TREATMENT_VAR}}"       # e.g., "treated" (binary 0/1 post-treatment)
OUTCOME_VARS = {{OUTCOME_VARS}}           # e.g., ["employment", "wages"]
COVARIATES = {{COVARIATES}}               # e.g., ["population", "gdp_pc"]
FIRST_TREAT_VAR = "{{FIRST_TREAT_VAR}}"  # e.g., "first_treat_year" or None (for staggered)

# ═══════════════════════════════════════════════════════════════════════════════
# FIXED CODE (does not change between projects)
# ═══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_OUT = os.path.join(SCRIPT_DIR, "..", "..", "data", "clean")
os.makedirs(DATA_OUT, exist_ok=True)

print("=" * 70)
print("00_clean.py — DiD Data Cleaning")
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
key_vars = [ENTITY_VAR, TIME_VAR, TREATMENT_VAR] + OUTCOME_VARS + COVARIATES
if FIRST_TREAT_VAR and FIRST_TREAT_VAR != "None":
    key_vars.append(FIRST_TREAT_VAR)
key_vars = [v for v in key_vars if v and v != "None" and v in df.columns]

for var in key_vars:
    n_miss = df[var].isna().sum()
    pct = 100 * n_miss / len(df)
    print(f"  {var:30s}: {n_miss:6,} missing ({pct:.1f}%)")

# ── Validate required variables exist ─────────────────────────────────────────
for required, label in [(ENTITY_VAR, "Entity"), (TIME_VAR, "Time")]:
    if required not in df.columns:
        print(f"\nERROR: {label} variable '{required}' not in data.")
        print(f"Available columns: {list(df.columns[:30])}")
        sys.exit(1)

# ── Filter to non-missing entity and time ─────────────────────────────────────
n_before = len(df)
df_did = df.dropna(subset=[ENTITY_VAR, TIME_VAR]).copy()
n_after = len(df_did)
print(f"\n--- Filter: entity & time non-missing ---")
print(f"  Before: {n_before:,}  After: {n_after:,}  Dropped: {n_before - n_after:,}")

# ── Validate panel structure (balance check) ─────────────────────────────────
print(f"\n--- Panel structure ---")
n_units = df_did[ENTITY_VAR].nunique()
n_periods = df_did[TIME_VAR].nunique()
expected_rows = n_units * n_periods

ct = pd.crosstab(df_did[ENTITY_VAR], df_did[TIME_VAR])
n_balanced = (ct > 0).all(axis=1).sum()
pct_balanced = 100 * n_balanced / n_units if n_units > 0 else 0

print(f"  Units: {n_units:,}  Periods: {n_periods:,}")
print(f"  Expected rows (balanced): {expected_rows:,}  Actual: {len(df_did):,}")
print(f"  Balanced units: {n_balanced:,}/{n_units:,} ({pct_balanced:.1f}%)")
print(f"  Period distribution:")
print(f"  {df_did[TIME_VAR].value_counts().sort_index().to_dict()}")

if pct_balanced < 100:
    print(f"  WARNING: Panel is unbalanced. Consider restricting to balanced panel.")
    # Count obs per unit
    obs_per_unit = df_did.groupby(ENTITY_VAR).size()
    print(f"  Obs per unit: min={obs_per_unit.min()}, "
          f"median={obs_per_unit.median():.0f}, max={obs_per_unit.max()}")

# ── Create / validate treatment indicator ────────────────────────────────────
print(f"\n--- Treatment indicator ---")
if TREATMENT_VAR and TREATMENT_VAR in df_did.columns:
    print(f"  Using existing treatment variable: {TREATMENT_VAR}")
    df_did["treat"] = df_did[TREATMENT_VAR].astype(float)
elif FIRST_TREAT_VAR and FIRST_TREAT_VAR != "None" and FIRST_TREAT_VAR in df_did.columns:
    print(f"  Constructing treatment from FIRST_TREAT_VAR: {FIRST_TREAT_VAR}")
    # treat = 1 if time >= first_treat_year and first_treat_year is not missing/inf
    ft = df_did[FIRST_TREAT_VAR]
    df_did["treat"] = ((df_did[TIME_VAR] >= ft) & ft.notna() & (ft < np.inf)).astype(float)
else:
    print(f"  ERROR: No treatment variable found. Need TREATMENT_VAR or FIRST_TREAT_VAR.")
    sys.exit(1)

n_treated_obs = int(df_did["treat"].sum())
n_control_obs = len(df_did) - n_treated_obs
n_ever_treated = df_did.groupby(ENTITY_VAR)["treat"].max().sum()
n_never_treated = n_units - n_ever_treated
print(f"  Treated obs: {n_treated_obs:,}  Control obs: {n_control_obs:,}")
print(f"  Ever-treated units: {int(n_ever_treated):,}  Never-treated units: {int(n_never_treated):,}")

# ── Staggered adoption check ────────────────────────────────────────────────
is_staggered = False
if FIRST_TREAT_VAR and FIRST_TREAT_VAR != "None" and FIRST_TREAT_VAR in df_did.columns:
    treat_times = df_did.loc[df_did[FIRST_TREAT_VAR].notna() & (df_did[FIRST_TREAT_VAR] < np.inf),
                             FIRST_TREAT_VAR].unique()
    n_treat_times = len(treat_times)
    is_staggered = n_treat_times > 1
    print(f"\n--- Staggered adoption ---")
    print(f"  Distinct treatment times: {n_treat_times}")
    if is_staggered:
        print(f"  Treatment timing distribution:")
        ft_counts = df_did.groupby(ENTITY_VAR)[FIRST_TREAT_VAR].first().value_counts().sort_index()
        for t, c in ft_counts.items():
            if pd.notna(t) and t < np.inf:
                print(f"    Period {t}: {c} units")
        print(f"  STAGGERED design detected: will use Callaway-Sant'Anna in 01_main.py")
    else:
        print(f"  Standard 2-group DiD design detected.")
else:
    print(f"\n  No FIRST_TREAT_VAR provided. Assuming standard 2-period/2-group DiD.")

# ── Outcome validation ────────────────────────────────────────────────────────
print("\n--- Outcome validation ---")
outcomes_present = [o for o in OUTCOME_VARS if o in df_did.columns]
outcomes_missing = [o for o in OUTCOME_VARS if o not in df_did.columns]

if outcomes_missing:
    print(f"  WARNING: Missing outcomes: {outcomes_missing}")
if not outcomes_present:
    print(f"  ERROR: No outcome variables found in data!")
    sys.exit(1)

for var in outcomes_present:
    s = df_did[var].dropna()
    ctrl_pre = df_did.loc[df_did["treat"] == 0, var]
    treat_post = df_did.loc[df_did["treat"] == 1, var]
    ctrl_mean = ctrl_pre.mean() if len(ctrl_pre) > 0 else np.nan
    treat_mean = treat_post.mean() if len(treat_post) > 0 else np.nan
    raw_diff = treat_mean - ctrl_mean if pd.notna(ctrl_mean) and pd.notna(treat_mean) else np.nan
    print(f"  {var}: N_valid={len(s):,}, ctrl_mean={ctrl_mean:.4f}, "
          f"treat_mean={treat_mean:.4f}, raw_diff={raw_diff:.4f}")

# ── Top 10 correlates with treatment ─────────────────────────────────────────
print("\n--- Top 10 variables correlated with treatment ---")
numeric_cols = df_did.select_dtypes(include=[np.number]).columns
corrs = {}
for col in numeric_cols:
    if col in ("treat", TREATMENT_VAR, ENTITY_VAR):
        continue
    try:
        r = df_did[["treat", col]].dropna().corr().iloc[0, 1]
        if not np.isnan(r):
            corrs[col] = abs(r)
    except Exception:
        pass

for i, (col, r) in enumerate(sorted(corrs.items(), key=lambda x: -x[1])[:10], 1):
    print(f"  {i:2d}. {col:40s} |r| = {r:.4f}")

# ── Save ──────────────────────────────────────────────────────────────────────
out_path = os.path.join(DATA_OUT, "clean_data.csv")
df_did.to_csv(out_path, index=False)
print(f"\nSaved: {out_path} ({len(df_did):,} rows x {df_did.shape[1]} cols)")

# Placeholder results
results_path = os.path.join(DATA_OUT, "main_results.csv")
if not os.path.exists(results_path):
    pd.DataFrame(columns=["outcome", "specification", "estimate", "se_robust",
                           "ci_lower", "ci_upper", "N", "N_units", "method"]
                 ).to_csv(results_path, index=False)
    print(f"Saved placeholder: {results_path}")

print("\n" + "=" * 70)
print("00_clean.py complete.")
print("=" * 70)
