"""02_robustness.py - HTE/DML robustness checks template.

Checks: alternative learners, overlap/propensity, placebo outcomes,
sensitivity to covariate selection.
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
CLUSTER_VAR      = "{{CLUSTER_VAR}}"
PLACEBO_OUTCOMES = {{PLACEBO_OUTCOMES}}  # pre-treatment outcomes, e.g., ["y_pre"]
BASE_PAPER_TITLE = "{{BASE_PAPER_TITLE}}"
PRIMARY_OUTCOME  = "{{PRIMARY_OUTCOME}}"
N_FOLDS          = 5

# ═══════════════════════════════════════════════════════════════════════════════
# FIXED CODE
# ═══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_CLEAN  = os.path.join(SCRIPT_DIR, "..", "..", "data", "clean")
RESULTS_DIR = os.path.join(SCRIPT_DIR, "..", "..", "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

print("=" * 70)
print("02_robustness.py — HTE/DML Robustness Checks")
print(f"Paper: {BASE_PAPER_TITLE[:70]}")
print("=" * 70)

# ── Load ──────────────────────────────────────────────────────────────────────
df = pd.read_csv(os.path.join(DATA_CLEAN, "clean_data.csv"))
print(f"Loaded: {len(df):,} rows")

Y = df[OUTCOME_VAR].values.astype(float)
D = df[TREATMENT_VAR].values.astype(float)
X_cols = [c for c in COVARIATES if c in df.columns]
X = df[X_cols].values.astype(float)

robustness_rows = []

# ── Load main summary ─────────────────────────────────────────────────────────
summary_path = os.path.join(RESULTS_DIR, "main_summary.json")
main_summary = {}
if os.path.exists(summary_path):
    with open(summary_path) as f:
        main_summary = json.load(f)

baseline_dml = main_summary.get("dml_ate")
print(f"Baseline DML ATE: {baseline_dml}")

# ═══════════════════════════════════════════════════════════════════════════════
# CHECK 1 — Overlap / Propensity Score
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("CHECK 1: Overlap (propensity score distribution)")
print("─" * 70)

try:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import cross_val_predict

    ps_model = GradientBoostingClassifier(n_estimators=100, random_state=42)
    ps_scores = cross_val_predict(ps_model, X, D, cv=N_FOLDS, method="predict_proba")[:, 1]

    ps_treated = ps_scores[D == 1]
    ps_control = ps_scores[D == 0]
    print(f"  Propensity (treated): min={ps_treated.min():.3f}  "
          f"mean={ps_treated.mean():.3f}  max={ps_treated.max():.3f}")
    print(f"  Propensity (control): min={ps_control.min():.3f}  "
          f"mean={ps_control.mean():.3f}  max={ps_control.max():.3f}")

    # Trim units with extreme PS
    trim_mask = (ps_scores > 0.05) & (ps_scores < 0.95)
    pct_trimmed = 100 * (1 - trim_mask.mean())
    print(f"  Extreme PS (outside [0.05,0.95]): {pct_trimmed:.1f}% of sample")
    if pct_trimmed > 10:
        print(f"  [warn] >10% of sample has extreme propensity. Overlap concern.")

    ps_df = pd.DataFrame({"ps": ps_scores, "treated": D})
    ps_path = os.path.join(RESULTS_DIR, "propensity_scores.csv")
    ps_df.to_csv(ps_path, index=False)

    # DML on trimmed sample
    Y_trim = Y[trim_mask]
    D_trim = D[trim_mask]
    X_trim = X[trim_mask]
    if len(Y_trim) > 100:
        print(f"\n  DML on trimmed sample (N={len(Y_trim):,}):")
        from sklearn.model_selection import KFold
        kf = KFold(n_splits=N_FOLDS, shuffle=True, random_state=42)
        Y_res = np.zeros_like(Y_trim)
        D_res = np.zeros_like(D_trim)
        from sklearn.ensemble import GradientBoostingRegressor
        for train_idx, val_idx in kf.split(X_trim):
            ml_y = GradientBoostingRegressor(n_estimators=100, random_state=42)
            ml_d = GradientBoostingClassifier(n_estimators=100, random_state=42)
            ml_y.fit(X_trim[train_idx], Y_trim[train_idx])
            ml_d.fit(X_trim[train_idx], D_trim[train_idx])
            Y_res[val_idx] = Y_trim[val_idx] - ml_y.predict(X_trim[val_idx])
            D_res[val_idx] = D_trim[val_idx] - ml_d.predict_proba(X_trim[val_idx])[:, 1]
        ate_trim = np.sum(D_res * Y_res) / np.sum(D_res ** 2)
        resid = Y_res - ate_trim * D_res
        se_trim = np.sqrt(np.mean(resid ** 2 * D_res ** 2) /
                          (np.mean(D_res ** 2) ** 2) / len(Y_trim))
        print(f"    DML ATE (trimmed) = {ate_trim:.4f}  SE = {se_trim:.4f}")
        robustness_rows.append({
            "check": "DML trimmed sample (PS in [0.05, 0.95])",
            "outcome": PRIMARY_OUTCOME,
            "estimate": round(float(ate_trim), 6),
            "se": round(float(se_trim), 6),
            "N": int(len(Y_trim)),
            "baseline_dml": baseline_dml,
        })

except Exception as e:
    print(f"  [warn] Propensity check failed: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
# CHECK 2 — Alternative learners (Lasso, Ridge)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("CHECK 2: Alternative learners (Lasso, Ridge)")
print("─" * 70)

try:
    from sklearn.linear_model import LassoCV, RidgeCV, LogisticRegressionCV
    from sklearn.model_selection import KFold
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    for learner_name, ml_y_cls, ml_d_cls in [
        ("Lasso/LogReg", LassoCV(cv=5), LogisticRegressionCV(cv=5, max_iter=500)),
        ("Ridge/LogReg", RidgeCV(), LogisticRegressionCV(cv=5, max_iter=500)),
    ]:
        try:
            kf = KFold(n_splits=N_FOLDS, shuffle=True, random_state=42)
            Y_res = np.zeros_like(Y)
            D_res = np.zeros_like(D)
            for train_idx, val_idx in kf.split(X_scaled):
                ml_y = type(ml_y_cls)(**ml_y_cls.get_params())
                ml_d = type(ml_d_cls)(**ml_d_cls.get_params())
                ml_y.fit(X_scaled[train_idx], Y[train_idx])
                ml_d.fit(X_scaled[train_idx], D[train_idx])
                Y_res[val_idx] = Y[val_idx] - ml_y.predict(X_scaled[val_idx])
                D_res[val_idx] = D[val_idx] - ml_d.predict_proba(X_scaled[val_idx])[:, 1]
            ate = np.sum(D_res * Y_res) / np.sum(D_res ** 2)
            resid = Y_res - ate * D_res
            se = np.sqrt(np.mean(resid ** 2 * D_res ** 2) /
                         (np.mean(D_res ** 2) ** 2) / len(Y))
            print(f"  {learner_name}: ATE = {ate:.4f}  SE = {se:.4f}")
            robustness_rows.append({
                "check": f"DML {learner_name}",
                "outcome": PRIMARY_OUTCOME,
                "estimate": round(float(ate), 6),
                "se": round(float(se), 6),
                "N": len(Y),
                "baseline_dml": baseline_dml,
            })
        except Exception as e2:
            print(f"  [warn] {learner_name} failed: {e2}")

except Exception as e:
    print(f"  [warn] Alternative learners check failed: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
# CHECK 3 — Placebo outcomes (pre-treatment)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("CHECK 3: Placebo outcomes (should be ~0 if identification holds)")
print("─" * 70)

for placebo_var in PLACEBO_OUTCOMES:
    if placebo_var not in df.columns:
        print(f"  [skip] {placebo_var} not in data")
        continue
    try:
        from sklearn.model_selection import KFold
        from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier

        Y_p = df[placebo_var].dropna().values.astype(float)
        idx = df[placebo_var].notna().values
        D_p = D[idx]
        X_p = X[idx]

        kf = KFold(n_splits=N_FOLDS, shuffle=True, random_state=42)
        Y_res = np.zeros_like(Y_p)
        D_res = np.zeros_like(D_p)
        for train_idx, val_idx in kf.split(X_p):
            ml_y = GradientBoostingRegressor(n_estimators=100, random_state=42)
            ml_d = GradientBoostingClassifier(n_estimators=100, random_state=42)
            ml_y.fit(X_p[train_idx], Y_p[train_idx])
            ml_d.fit(X_p[train_idx], D_p[train_idx])
            Y_res[val_idx] = Y_p[val_idx] - ml_y.predict(X_p[val_idx])
            D_res[val_idx] = D_p[val_idx] - ml_d.predict_proba(X_p[val_idx])[:, 1]
        ate_p = np.sum(D_res * Y_res) / np.sum(D_res ** 2)
        resid = Y_res - ate_p * D_res
        se_p = np.sqrt(np.mean(resid ** 2 * D_res ** 2) /
                       (np.mean(D_res ** 2) ** 2) / len(Y_p))
        t_stat = ate_p / (se_p + 1e-10)
        flag = " [FAIL — placebo significant!]" if abs(t_stat) > 1.96 else " [pass]"
        print(f"  {placebo_var}: ATE={ate_p:.4f}  SE={se_p:.4f}  t={t_stat:.2f}{flag}")
        robustness_rows.append({
            "check": f"Placebo: {placebo_var}",
            "outcome": placebo_var,
            "estimate": round(float(ate_p), 6),
            "se": round(float(se_p), 6),
            "N": len(Y_p),
            "baseline_dml": baseline_dml,
        })
    except Exception as e:
        print(f"  [warn] Placebo {placebo_var} failed: {e}")

if not PLACEBO_OUTCOMES:
    print("  No PLACEBO_OUTCOMES specified. Skipping.")

# ═══════════════════════════════════════════════════════════════════════════════
# CHECK 4 — Leave-one-covariate-out sensitivity
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("CHECK 4: Leave-one-covariate-out sensitivity (top 5 covariates)")
print("─" * 70)

if len(X_cols) > 1:
    try:
        from sklearn.model_selection import KFold
        from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier

        for drop_col in X_cols[:5]:
            X_loo = df[[c for c in X_cols if c != drop_col]].values.astype(float)
            kf = KFold(n_splits=N_FOLDS, shuffle=True, random_state=42)
            Y_res = np.zeros_like(Y)
            D_res = np.zeros_like(D)
            for train_idx, val_idx in kf.split(X_loo):
                ml_y = GradientBoostingRegressor(n_estimators=100, random_state=42)
                ml_d = GradientBoostingClassifier(n_estimators=100, random_state=42)
                ml_y.fit(X_loo[train_idx], Y[train_idx])
                ml_d.fit(X_loo[train_idx], D[train_idx])
                Y_res[val_idx] = Y[val_idx] - ml_y.predict(X_loo[val_idx])
                D_res[val_idx] = D[val_idx] - ml_d.predict_proba(X_loo[val_idx])[:, 1]
            ate_loo = np.sum(D_res * Y_res) / np.sum(D_res ** 2)
            resid = Y_res - ate_loo * D_res
            se_loo = np.sqrt(np.mean(resid ** 2 * D_res ** 2) /
                             (np.mean(D_res ** 2) ** 2) / len(Y))
            delta = ate_loo - baseline_dml if baseline_dml else np.nan
            print(f"  Drop {drop_col:30s}: ATE={ate_loo:.4f}  Δ from baseline={delta:+.4f}")
            robustness_rows.append({
                "check": f"LOO: drop {drop_col}",
                "outcome": PRIMARY_OUTCOME,
                "estimate": round(float(ate_loo), 6),
                "se": round(float(se_loo), 6),
                "N": len(Y),
                "baseline_dml": baseline_dml,
            })
    except Exception as e:
        print(f"  [warn] LOO sensitivity failed: {e}")

# ── Save ──────────────────────────────────────────────────────────────────────
robustness_path = os.path.join(RESULTS_DIR, "robustness_results.csv")
pd.DataFrame(robustness_rows).to_csv(robustness_path, index=False)
print(f"\nSaved: {robustness_path} ({len(robustness_rows)} checks)")

print("\n" + "=" * 70)
print("02_robustness.py complete.")
print("=" * 70)
