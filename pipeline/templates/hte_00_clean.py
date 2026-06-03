"""00_clean.py - HTE/DML data cleaning template.

Project-specific variables (below) are filled by Claude.
Fixed code handles loading, sample restrictions, missingness, and overlap checks.
"""

import os
import sys
import numpy as np
import pandas as pd

# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT-SPECIFIC VARIABLES (Claude fills these)
# ═══════════════════════════════════════════════════════════════════════════════
DATA_FILE      = "{{DATA_FILE}}"       # e.g., "../../data/external/enaho.dta"
DATA_FORMAT    = "{{DATA_FORMAT}}"     # "stata", "csv", "tab", "parquet"
OUTCOME_VAR    = "{{OUTCOME_VAR}}"     # Y — continuous or binary outcome
TREATMENT_VAR  = "{{TREATMENT_VAR}}"   # D — binary treatment indicator (0/1)
COVARIATES     = {{COVARIATES}}        # X list, e.g., ["age", "female", "educ"]
HTE_VARS       = {{HTE_VARS}}          # subgroup variables for CATE, e.g., ["female", "rural"]
ENTITY_VAR     = "{{ENTITY_VAR}}"      # unit ID for clustering (or None)
CLUSTER_VAR    = "{{CLUSTER_VAR}}"     # clustering variable for SEs (often same as ENTITY_VAR)
SAMPLE_FILTERS = {{SAMPLE_FILTERS}}    # list of pandas query strings, e.g., ["age >= 18", "year == 2019"]
BASE_PAPER_TITLE = "{{BASE_PAPER_TITLE}}"  # title of paper being replicated

# ═══════════════════════════════════════════════════════════════════════════════
# FIXED CODE
# ═══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_OUT   = os.path.join(SCRIPT_DIR, "..", "..", "data", "clean")
os.makedirs(DATA_OUT, exist_ok=True)

print("=" * 70)
print("00_clean.py — HTE/DML Data Cleaning")
print(f"Paper: {BASE_PAPER_TITLE[:70]}")
print("=" * 70)

# ── Load ──────────────────────────────────────────────────────────────────────
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

# ── Sample restrictions ───────────────────────────────────────────────────────
if SAMPLE_FILTERS:
    n_before = len(df)
    for filt in SAMPLE_FILTERS:
        try:
            df = df.query(filt)
            print(f"  Filter '{filt}': {n_before:,} → {len(df):,} rows")
            n_before = len(df)
        except Exception as e:
            print(f"  [warn] Filter '{filt}' failed: {e}")

print(f"After restrictions: {len(df):,} rows")

# ── Validate key variables exist ──────────────────────────────────────────────
all_required = [OUTCOME_VAR, TREATMENT_VAR] + COVARIATES + HTE_VARS
missing_cols = [v for v in all_required if v and v not in df.columns]
if missing_cols:
    print(f"\nERROR: Variables not found in data: {missing_cols}")
    print(f"Available columns: {list(df.columns[:40])}")
    sys.exit(1)

# ── Missingness ───────────────────────────────────────────────────────────────
print("\n--- Missingness (key variables) ---")
key_vars = [OUTCOME_VAR, TREATMENT_VAR] + COVARIATES[:10]
for var in key_vars:
    if var not in df.columns:
        continue
    n_miss = df[var].isna().sum()
    print(f"  {var:35s}: {n_miss:6,} missing ({100*n_miss/len(df):.1f}%)")

# ── Drop rows with missing Y, D, or any covariate ────────────────────────────
n_before = len(df)
drop_vars = [v for v in [OUTCOME_VAR, TREATMENT_VAR] + COVARIATES if v in df.columns]
df = df.dropna(subset=drop_vars).copy()
print(f"\nDropped {n_before - len(df):,} rows with missing Y/D/X. Remaining: {len(df):,}")

# ── Treatment validation ──────────────────────────────────────────────────────
print(f"\n--- Treatment ({TREATMENT_VAR}) ---")
treat_vals = df[TREATMENT_VAR].unique()
treat_counts = df[TREATMENT_VAR].value_counts().sort_index()
print(f"  Unique values: {sorted(treat_vals)}")
for val, cnt in treat_counts.items():
    print(f"  {val}: {cnt:,} obs ({100*cnt/len(df):.1f}%)")

if not set(treat_vals).issubset({0, 1, 0.0, 1.0, True, False}):
    print(f"  [warn] Treatment is not binary 0/1. Check TREATMENT_VAR encoding.")

p_treat = df[TREATMENT_VAR].mean()
print(f"  Propensity (raw): {p_treat:.4f}")
if p_treat < 0.05 or p_treat > 0.95:
    print(f"  [warn] Extreme propensity — overlap may be violated.")

# ── Outcome summary ───────────────────────────────────────────────────────────
print(f"\n--- Outcome ({OUTCOME_VAR}) ---")
y = df[OUTCOME_VAR]
d = df[TREATMENT_VAR].astype(float)
y0 = y[d == 0]
y1 = y[d == 1]
print(f"  Overall: mean={y.mean():.4f}, sd={y.std():.4f}, N={len(y):,}")
print(f"  Control (D=0): mean={y0.mean():.4f}, sd={y0.std():.4f}, N={len(y0):,}")
print(f"  Treated (D=1): mean={y1.mean():.4f}, sd={y1.std():.4f}, N={len(y1):,}")
raw_diff = y1.mean() - y0.mean()
print(f"  Raw difference (T-C): {raw_diff:.4f}")

# ── HTE subgroup summary ──────────────────────────────────────────────────────
if HTE_VARS:
    print(f"\n--- HTE subgroup variables ---")
    for var in HTE_VARS:
        if var not in df.columns:
            continue
        n_vals = df[var].nunique()
        if n_vals <= 6:
            dist = df[var].value_counts(normalize=True).sort_index().to_dict()
            print(f"  {var}: {dist}")
        else:
            print(f"  {var}: mean={df[var].mean():.3f}, n_unique={n_vals}")

# ── Covariate balance by treatment ───────────────────────────────────────────
print(f"\n--- Covariate balance (standardized mean differences) ---")
for var in COVARIATES[:10]:
    if var not in df.columns:
        continue
    try:
        m1 = df.loc[d == 1, var].mean()
        m0 = df.loc[d == 0, var].mean()
        sd_pool = df[var].std()
        smd = (m1 - m0) / sd_pool if sd_pool > 0 else np.nan
        flag = " [IMBALANCED]" if abs(smd) > 0.1 else ""
        print(f"  {var:35s}: SMD = {smd:.3f}{flag}")
    except Exception:
        pass

# ── Save ──────────────────────────────────────────────────────────────────────
out_path = os.path.join(DATA_OUT, "clean_data.csv")
df.to_csv(out_path, index=False)
print(f"\nSaved: {out_path} ({len(df):,} rows x {df.shape[1]} cols)")

# Placeholder for downstream scripts
results_path = os.path.join(DATA_OUT, "main_results.csv")
if not os.path.exists(results_path):
    pd.DataFrame(columns=["estimator", "outcome", "estimate", "se", "ci_lower", "ci_upper",
                           "N", "replication_target", "original_ate"]
                 ).to_csv(results_path, index=False)
    print(f"Saved placeholder: {results_path}")

print("\n" + "=" * 70)
print("00_clean.py complete.")
print("=" * 70)
