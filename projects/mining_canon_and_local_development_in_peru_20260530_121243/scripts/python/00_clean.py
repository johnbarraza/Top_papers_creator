"""00_clean.py - IV/2SLS data cleaning template.

Project-specific variables (in the section below) are filled by Claude.
Everything below the FIXED CODE marker handles known IV pitfalls and must
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
ENDOGENOUS_VAR = "{{ENDOGENOUS_VAR}}"     # e.g., "years_schooling"
INSTRUMENT_VARS = {{INSTRUMENT_VARS}}     # e.g., ["quarter_of_birth"] or ["z1", "z2"]
OUTCOME_VARS = {{OUTCOME_VARS}}           # e.g., ["log_wage", "employment"]
ENTITY_VAR = "{{ENTITY_VAR}}"            # e.g., "state_id" or None
TIME_VAR = "{{TIME_VAR}}"                # e.g., "year" or None
CLUSTER_VAR = "{{CLUSTER_VAR}}"           # e.g., "state_id"
COVARIATES = {{COVARIATES}}               # e.g., ["age", "age_sq", "female"]

# ═══════════════════════════════════════════════════════════════════════════════
# FIXED CODE (does not change between projects)
# ═══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_OUT = os.path.join(SCRIPT_DIR, "..", "..", "data", "clean")
os.makedirs(DATA_OUT, exist_ok=True)

print("=" * 70)
print("00_clean.py — IV/2SLS Data Cleaning")
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
key_vars = ([ENDOGENOUS_VAR, CLUSTER_VAR] + INSTRUMENT_VARS +
            OUTCOME_VARS + COVARIATES)
if ENTITY_VAR and ENTITY_VAR != "None":
    key_vars.append(ENTITY_VAR)
if TIME_VAR and TIME_VAR != "None":
    key_vars.append(TIME_VAR)
key_vars = [v for v in key_vars if v and v != "None" and v in df.columns]

for var in key_vars:
    n_miss = df[var].isna().sum()
    pct = 100 * n_miss / len(df)
    print(f"  {var:30s}: {n_miss:6,} missing ({pct:.1f}%)")

# ── Validate instrument(s) exist and have variation ──────────────────────────
print("\n--- Instrument validation ---")
for z in INSTRUMENT_VARS:
    if z not in df.columns:
        print(f"  ERROR: Instrument '{z}' not in data.")
        print(f"  Available columns: {list(df.columns[:30])}")
        sys.exit(1)
    n_unique = df[z].nunique()
    n_valid = df[z].notna().sum()
    print(f"  {z}: {n_valid:,} non-missing, {n_unique} unique values")
    if n_unique < 2:
        print(f"  ERROR: Instrument '{z}' has no variation (only {n_unique} unique value).")
        sys.exit(1)

# ── Validate endogenous variable exists ──────────────────────────────────────
if ENDOGENOUS_VAR not in df.columns:
    print(f"\nERROR: Endogenous variable '{ENDOGENOUS_VAR}' not in data.")
    print(f"Available columns: {list(df.columns[:30])}")
    sys.exit(1)

# ── Filter to analysis sample (non-missing key variables) ───────────────────
required = [ENDOGENOUS_VAR] + INSTRUMENT_VARS + OUTCOME_VARS
required = [v for v in required if v in df.columns]
n_before = len(df)
df_iv = df.dropna(subset=required).copy()
n_after = len(df_iv)
print(f"\n--- Filter: key variables non-missing ---")
print(f"  Before: {n_before:,}  After: {n_after:,}  Dropped: {n_before - n_after:,}")

# ── Instrument-endogenous correlation (first stage relevance) ────────────────
print("\n--- Instrument-endogenous correlation (first stage relevance check) ---")
for z in INSTRUMENT_VARS:
    if z in df_iv.columns:
        pair = df_iv[[z, ENDOGENOUS_VAR]].dropna()
        if len(pair) > 10:
            corr = pair.corr().iloc[0, 1]
            print(f"  corr({z}, {ENDOGENOUS_VAR}) = {corr:.4f}")
            if abs(corr) < 0.05:
                print(f"  WARNING: Very low correlation. Instrument may be weak.")
        else:
            print(f"  WARNING: Insufficient observations for {z} correlation.")

# ── Instrument-outcome correlation (reduced form) ───────────────────────────
print("\n--- Instrument-outcome correlation (reduced form check) ---")
for z in INSTRUMENT_VARS:
    for y_var in OUTCOME_VARS:
        if z in df_iv.columns and y_var in df_iv.columns:
            pair = df_iv[[z, y_var]].dropna()
            if len(pair) > 10:
                corr = pair.corr().iloc[0, 1]
                print(f"  corr({z}, {y_var}) = {corr:.4f}")

# ── Outcome validation ────────────────────────────────────────────────────────
print("\n--- Outcome validation ---")
outcomes_present = [o for o in OUTCOME_VARS if o in df_iv.columns]
outcomes_missing = [o for o in OUTCOME_VARS if o not in df_iv.columns]

if outcomes_missing:
    print(f"  WARNING: Missing outcomes: {outcomes_missing}")
if not outcomes_present:
    print(f"  ERROR: No outcome variables found in data!")
    sys.exit(1)

for var in outcomes_present:
    s = df_iv[var].dropna()
    print(f"  {var}: N_valid={len(s)}, mean={s.mean():.4f}, sd={s.std():.4f}, "
          f"min={s.min():.4f}, max={s.max():.4f}")

# ── Endogenous variable summary ──────────────────────────────────────────────
print(f"\n--- Endogenous variable summary: {ENDOGENOUS_VAR} ---")
s = df_iv[ENDOGENOUS_VAR].dropna()
print(f"  N_valid={len(s)}, mean={s.mean():.4f}, sd={s.std():.4f}, "
      f"min={s.min():.4f}, max={s.max():.4f}")

# ── Panel structure check (if applicable) ────────────────────────────────────
if (ENTITY_VAR and ENTITY_VAR != "None" and ENTITY_VAR in df_iv.columns and
        TIME_VAR and TIME_VAR != "None" and TIME_VAR in df_iv.columns):
    print(f"\n--- Panel structure ---")
    n_units = df_iv[ENTITY_VAR].nunique()
    n_periods = df_iv[TIME_VAR].nunique()
    ct = pd.crosstab(df_iv[ENTITY_VAR], df_iv[TIME_VAR])
    n_balanced = (ct > 0).all(axis=1).sum()
    print(f"  Entities: {n_units}, Periods: {n_periods}")
    print(f"  Balanced: {n_balanced}/{n_units} ({100*n_balanced/n_units:.1f}%)")
    print(f"  Time distribution:")
    print(f"  {df_iv[TIME_VAR].value_counts().sort_index().to_dict()}")

# ── Save ──────────────────────────────────────────────────────────────────────
out_path = os.path.join(DATA_OUT, "clean_data.csv")
df_iv.to_csv(out_path, index=False)
print(f"\nSaved: {out_path} ({len(df_iv):,} rows x {df_iv.shape[1]} cols)")

# Placeholder results
results_path = os.path.join(DATA_OUT, "main_results.csv")
if not os.path.exists(results_path):
    pd.DataFrame(columns=["outcome", "specification", "estimate", "se_robust",
                           "ci_lower", "ci_upper", "first_stage_F", "N",
                           "method"]).to_csv(results_path, index=False)
    print(f"Saved placeholder: {results_path}")

print("\n" + "=" * 70)
print("00_clean.py complete.")
print("=" * 70)
