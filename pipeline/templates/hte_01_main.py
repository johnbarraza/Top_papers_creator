"""01_main.py - HTE/DML main estimation template.

Gate: replicate original ATE first. If reported ATE available, compare.
Difference > 30% → warning in results_summary.md.
Then: DML ATE + CATE via causal forest.
"""

import json
import os
import sys
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT-SPECIFIC VARIABLES (Claude fills these)
# ═══════════════════════════════════════════════════════════════════════════════
OUTCOME_VAR      = "{{OUTCOME_VAR}}"
TREATMENT_VAR    = "{{TREATMENT_VAR}}"
COVARIATES       = {{COVARIATES}}
HTE_VARS         = {{HTE_VARS}}
ENTITY_VAR       = "{{ENTITY_VAR}}"
CLUSTER_VAR      = "{{CLUSTER_VAR}}"
ORIGINAL_ATE     = {{ORIGINAL_ATE}}     # float from paper, or None
ORIGINAL_ATE_SE  = {{ORIGINAL_ATE_SE}}  # SE from paper, or None
BASE_PAPER_TITLE = "{{BASE_PAPER_TITLE}}"
PRIMARY_OUTCOME  = "{{PRIMARY_OUTCOME}}"
N_FOLDS          = 5    # cross-fitting folds for DML
N_TREES          = 500  # causal forest trees

# ═══════════════════════════════════════════════════════════════════════════════
# FIXED CODE
# ═══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_CLEAN   = os.path.join(SCRIPT_DIR, "..", "..", "data", "clean")
RESULTS_DIR  = os.path.join(SCRIPT_DIR, "..", "..", "results")
FIGURES_DIR  = os.path.join(SCRIPT_DIR, "..", "..", "figures")
for d in [DATA_CLEAN, RESULTS_DIR, FIGURES_DIR]:
    os.makedirs(d, exist_ok=True)

print("=" * 70)
print("01_main.py — HTE/DML Main Estimation")
print(f"Paper: {BASE_PAPER_TITLE[:70]}")
print("=" * 70)

# ── Load clean data ───────────────────────────────────────────────────────────
clean_path = os.path.join(DATA_CLEAN, "clean_data.csv")
if not os.path.exists(clean_path):
    print("ERROR: clean_data.csv not found. Run 00_clean.py first.")
    sys.exit(1)

df = pd.read_csv(clean_path)
print(f"Loaded: {len(df):,} rows x {df.shape[1]} cols")

all_vars = [OUTCOME_VAR, TREATMENT_VAR] + COVARIATES + HTE_VARS
missing = [v for v in all_vars if v and v not in df.columns]
if missing:
    print(f"ERROR: Variables missing from clean data: {missing}")
    sys.exit(1)

Y = df[OUTCOME_VAR].values.astype(float)
D = df[TREATMENT_VAR].values.astype(float)
X_cols = [c for c in COVARIATES if c in df.columns]
X = df[X_cols].values.astype(float)

results_rows = []

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — REPLICATION: OLS/FE baseline
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("STEP 1: Replication baseline (OLS)")
print("─" * 70)

try:
    import statsmodels.api as sm
    from statsmodels.stats.sandwich_covariance import cov_hc3

    Xreg = sm.add_constant(np.column_stack([D, X]))
    ols_model = sm.OLS(Y, Xreg).fit(cov_type="HC3")
    ols_ate = ols_model.params[1]
    ols_se  = ols_model.bse[1]
    ols_ci  = ols_model.conf_int().iloc[1].values
    ols_n   = int(ols_model.nobs)
    print(f"  OLS ATE  = {ols_ate:.4f}  SE = {ols_se:.4f}  "
          f"95%CI [{ols_ci[0]:.4f}, {ols_ci[1]:.4f}]  N={ols_n:,}")

    results_rows.append({
        "estimator": "OLS (replication)",
        "outcome": PRIMARY_OUTCOME,
        "estimate": round(ols_ate, 6),
        "se": round(ols_se, 6),
        "ci_lower": round(float(ols_ci[0]), 6),
        "ci_upper": round(float(ols_ci[1]), 6),
        "N": ols_n,
        "replication_target": True,
        "original_ate": ORIGINAL_ATE,
    })

    # ── Replication gate ──────────────────────────────────────────────────
    if ORIGINAL_ATE is not None:
        pct_diff = abs(ols_ate - ORIGINAL_ATE) / (abs(ORIGINAL_ATE) + 1e-10)
        print(f"\n  Replication gate:")
        print(f"    Original ATE: {ORIGINAL_ATE}  (SE: {ORIGINAL_ATE_SE})")
        print(f"    Replicated:   {ols_ate:.4f}")
        print(f"    % difference: {100*pct_diff:.1f}%")

        gate_warning = pct_diff > 0.30
        if gate_warning:
            msg = (
                f"REPLICATION WARNING: OLS estimate ({ols_ate:.4f}) differs "
                f">30% from original ATE ({ORIGINAL_ATE}). "
                f"Check sample restrictions and variable definitions before "
                f"interpreting HTE results."
            )
            print(f"\n  [GATE WARNING] {msg}")
            summary_path = os.path.join(RESULTS_DIR, "results_summary.md")
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(f"\n## Replication Gate\n\n**{msg}**\n")
        else:
            print(f"  [GATE PASS] Replication within 30% tolerance.")
    else:
        print(f"  No original ATE provided — skipping replication gate.")

except ImportError:
    print("  [warn] statsmodels not installed. Skipping OLS replication.")
    ols_ate = None

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — DML ATE (partially linear model)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("STEP 2: DML ATE (DoubleML partially linear)")
print("─" * 70)

dml_ate = None
dml_se  = None

try:
    import doubleml as dml
    from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
    from sklearn.linear_model import LassoCV, LogisticRegressionCV

    data_dml = dml.DoubleMLData.from_arrays(X, Y, D)
    ml_l = GradientBoostingRegressor(n_estimators=100, max_depth=3, random_state=42)
    ml_m = GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42)
    plr = dml.DoubleMLPLR(data_dml, ml_l, ml_m, n_folds=N_FOLDS)
    plr.fit()

    dml_ate = float(plr.coef[0])
    dml_se  = float(plr.se[0])
    dml_ci  = plr.confint().values[0]
    print(f"  DML ATE  = {dml_ate:.4f}  SE = {dml_se:.4f}  "
          f"95%CI [{dml_ci[0]:.4f}, {dml_ci[1]:.4f}]  folds={N_FOLDS}")

    results_rows.append({
        "estimator": "DML-PLR (GBM)",
        "outcome": PRIMARY_OUTCOME,
        "estimate": round(dml_ate, 6),
        "se": round(dml_se, 6),
        "ci_lower": round(float(dml_ci[0]), 6),
        "ci_upper": round(float(dml_ci[1]), 6),
        "N": len(Y),
        "replication_target": False,
        "original_ate": ORIGINAL_ATE,
    })

except ImportError:
    print("  [warn] doubleml not installed. Falling back to residual-on-residual DML.")

    # Manual residual-on-residual DML
    try:
        from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
        from sklearn.model_selection import KFold

        kf = KFold(n_splits=N_FOLDS, shuffle=True, random_state=42)
        Y_res = np.zeros_like(Y)
        D_res = np.zeros_like(D)

        for train_idx, val_idx in kf.split(X):
            ml_y = GradientBoostingRegressor(n_estimators=100, random_state=42)
            ml_d = GradientBoostingClassifier(n_estimators=100, random_state=42)
            ml_y.fit(X[train_idx], Y[train_idx])
            ml_d.fit(X[train_idx], D[train_idx])
            Y_res[val_idx] = Y[val_idx] - ml_y.predict(X[val_idx])
            D_res[val_idx] = D[val_idx] - ml_d.predict_proba(X[val_idx])[:, 1]

        dml_ate = np.sum(D_res * Y_res) / np.sum(D_res ** 2)
        resid = Y_res - dml_ate * D_res
        dml_var = np.mean(resid ** 2 * D_res ** 2) / (np.mean(D_res ** 2) ** 2) / len(Y)
        dml_se = float(np.sqrt(dml_var))
        dml_ci_l = dml_ate - 1.96 * dml_se
        dml_ci_u = dml_ate + 1.96 * dml_se
        print(f"  DML ATE (manual) = {dml_ate:.4f}  SE = {dml_se:.4f}  "
              f"95%CI [{dml_ci_l:.4f}, {dml_ci_u:.4f}]")

        results_rows.append({
            "estimator": "DML-manual (GBM)",
            "outcome": PRIMARY_OUTCOME,
            "estimate": round(float(dml_ate), 6),
            "se": round(float(dml_se), 6),
            "ci_lower": round(dml_ci_l, 6),
            "ci_upper": round(dml_ci_u, 6),
            "N": len(Y),
            "replication_target": False,
            "original_ate": ORIGINAL_ATE,
        })

    except Exception as e2:
        print(f"  [warn] Manual DML failed: {e2}")

except Exception as e:
    print(f"  [warn] DML failed: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — CATE via Causal Forest
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("STEP 3: CATE via Causal Forest")
print("─" * 70)

cate_df = None

try:
    from econml.dml import CausalForestDML
    from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier

    cf = CausalForestDML(
        model_y=GradientBoostingRegressor(n_estimators=100, random_state=42),
        model_t=GradientBoostingClassifier(n_estimators=100, random_state=42),
        n_estimators=N_TREES,
        random_state=42,
        cv=N_FOLDS,
    )
    cf.fit(Y, D, X=X)
    cate_preds = cf.effect(X)
    cate_mean  = float(np.mean(cate_preds))
    cate_std   = float(np.std(cate_preds))
    print(f"  Causal Forest CATE: mean={cate_mean:.4f}  std={cate_std:.4f}")

    # CATE by HTE_VARS subgroups
    cate_df = pd.DataFrame({"cate": cate_preds})
    for var in HTE_VARS:
        if var not in df.columns:
            continue
        cate_df[var] = df[var].values

    results_rows.append({
        "estimator": "Causal Forest CATE (mean)",
        "outcome": PRIMARY_OUTCOME,
        "estimate": round(cate_mean, 6),
        "se": round(cate_std / np.sqrt(len(Y)), 6),
        "ci_lower": round(cate_mean - 1.96 * cate_std / np.sqrt(len(Y)), 6),
        "ci_upper": round(cate_mean + 1.96 * cate_std / np.sqrt(len(Y)), 6),
        "N": len(Y),
        "replication_target": False,
        "original_ate": ORIGINAL_ATE,
    })

    # Feature importance (treatment effect heterogeneity)
    try:
        importance = cf.feature_importances_
        top_idx = np.argsort(importance)[::-1][:5]
        print(f"\n  Top heterogeneity drivers:")
        for i in top_idx:
            if i < len(X_cols):
                print(f"    {X_cols[i]:35s}: {importance[i]:.4f}")
    except Exception:
        pass

except ImportError:
    print("  [warn] econml not installed. Trying GRF (rpy2) or skipping CATE.")
    try:
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.model_selection import cross_val_predict

        # Honest pseudo-outcome CATE approximation (Robinson transform)
        if dml_ate is not None:
            from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
            from sklearn.model_selection import KFold

            kf = KFold(n_splits=N_FOLDS, shuffle=True, random_state=42)
            Y_res = np.zeros_like(Y)
            D_res = np.zeros_like(D)
            for train_idx, val_idx in kf.split(X):
                ml_y = GradientBoostingRegressor(n_estimators=100, random_state=42)
                ml_d = GradientBoostingClassifier(n_estimators=100, random_state=42)
                ml_y.fit(X[train_idx], Y[train_idx])
                ml_d.fit(X[train_idx], D[train_idx])
                Y_res[val_idx] = Y[val_idx] - ml_y.predict(X[val_idx])
                D_res[val_idx] = D[val_idx] - ml_d.predict_proba(X[val_idx])[:, 1]

            # Pseudo-outcome for CATE: Robinson (1988)
            with np.errstate(divide="ignore", invalid="ignore"):
                pseudo_y = np.where(np.abs(D_res) > 1e-6,
                                    Y_res / D_res,
                                    dml_ate)

            rf_cate = RandomForestRegressor(n_estimators=N_TREES, random_state=42)
            cate_preds = cross_val_predict(rf_cate, X, pseudo_y, cv=N_FOLDS)
            cate_df = pd.DataFrame({"cate": cate_preds})
            for var in HTE_VARS:
                if var in df.columns:
                    cate_df[var] = df[var].values
            print(f"  Pseudo-outcome CATE: mean={cate_preds.mean():.4f}")
    except Exception as e2:
        print(f"  [warn] CATE approximation failed: {e2}")

except Exception as e:
    print(f"  [warn] Causal forest failed: {e}")

# ── Save results ──────────────────────────────────────────────────────────────
results_path = os.path.join(DATA_CLEAN, "main_results.csv")
pd.DataFrame(results_rows).to_csv(results_path, index=False)
print(f"\nSaved main results: {results_path}")

if cate_df is not None:
    cate_path = os.path.join(DATA_CLEAN, "cate_predictions.csv")
    cate_df.to_csv(cate_path, index=False)
    print(f"Saved CATE predictions: {cate_path}")

# ── Summary JSON for downstream scripts ──────────────────────────────────────
summary = {
    "ols_ate": float(ols_ate) if ols_ate is not None else None,
    "dml_ate": float(dml_ate) if dml_ate is not None else None,
    "dml_se":  float(dml_se)  if dml_se  is not None else None,
    "original_ate": ORIGINAL_ATE,
    "original_ate_se": ORIGINAL_ATE_SE,
    "n_obs": len(Y),
    "n_covariates": len(X_cols),
    "hte_vars": HTE_VARS,
}
with open(os.path.join(RESULTS_DIR, "main_summary.json"), "w") as f:
    json.dump(summary, f, indent=2)

print("\n" + "=" * 70)
print("01_main.py complete.")
print("=" * 70)
