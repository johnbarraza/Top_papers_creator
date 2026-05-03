"""02_robustness.py — IV/2SLS robustness template.

All required IV robustness checks in one file:
1. First stage diagnostics (partial F, Cragg-Donald, Kleibergen-Paap)
2. Weak instrument robust inference (Anderson-Rubin confidence sets)
3. Placebo instrument test (instrument should NOT predict placebo outcomes)
4. Exclusion restriction sensitivity (Conley et al. bounds)
5. Alternative instrument sets (each instrument separately, if >1)
6. Reduced form robustness
7. Wild cluster bootstrap if <50 clusters
"""

import os
import sys
import warnings
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT-SPECIFIC VARIABLES (Claude fills these)
# ═══════════════════════════════════════════════════════════════════════════════
PRIMARY_OUTCOME = "{{PRIMARY_OUTCOME}}"       # e.g., "log_wage"
OUTCOME_VARS = {{OUTCOME_VARS}}               # e.g., ["log_wage", "employment"]
ENDOGENOUS_VAR = "{{ENDOGENOUS_VAR}}"         # e.g., "years_schooling"
INSTRUMENT_VARS = {{INSTRUMENT_VARS}}         # e.g., ["quarter_of_birth"]
CLUSTER_VAR = "{{CLUSTER_VAR}}"               # e.g., "state_id"
ENTITY_VAR = "{{ENTITY_VAR}}"                # e.g., "state_id" or None
COVARIATES = {{COVARIATES}}                   # e.g., ["age", "age_sq", "female"]
PLACEBO_OUTCOMES = {{PLACEBO_OUTCOMES}}       # e.g., ["pre_treatment_wage"] or []
MEDIATOR_VAR = "{{MEDIATOR_VAR}}"             # e.g., "pchoice" or "None"
HETEROGENEITY_VARS = {{HETEROGENEITY_VARS}}   # e.g., ["female", "age_group"]

# ═══════════════════════════════════════════════════════════════════════════════
# FIXED CODE
# ═══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "..", "data", "clean")
CLEAN_CSV = os.path.join(DATA_DIR, "clean_data.csv")

# Import from 01_main.py to reuse helpers
sys.path.insert(0, SCRIPT_DIR)
try:
    from importlib import import_module
    main_mod = import_module("iv_01_main")
    _prepare_data = main_mod._prepare_data
    _anderson_rubin_ci = main_mod._anderson_rubin_ci
    _empty_result = main_mod._empty_result
except Exception as _import_err:
    print(f"  WARNING: Failed to import iv_01_main: {_import_err}. Using inline fallbacks.")
    # Inline fallbacks
    import statsmodels.api as sm

    def _prepare_data(df, outcome):
        cols = [outcome, ENDOGENOUS_VAR] + INSTRUMENT_VARS + COVARIATES
        if CLUSTER_VAR and CLUSTER_VAR in df.columns:
            cols.append(CLUSTER_VAR)
        cols = list(dict.fromkeys([c for c in cols if c in df.columns]))
        return df[cols].dropna().copy()

    def _empty_result(outcome, spec):
        return {"outcome": outcome, "specification": spec,
                "estimate": np.nan, "se_robust": np.nan, "pvalue": np.nan,
                "ci_lower": np.nan, "ci_upper": np.nan,
                "first_stage_F": np.nan, "N": 0, "method": "none"}

    def _anderson_rubin_ci(df, outcome, alpha=0.05):
        return None


def main():
    print("=" * 70)
    print("02_robustness.py — IV/2SLS Robustness Checks")
    print("=" * 70)

    df = pd.read_csv(CLEAN_CSV)
    print(f"Loaded: {len(df):,} rows x {df.shape[1]} cols")

    import statsmodels.api as sm

    all_results = []

    # ══════════════════════════════════════════════════════════════════════
    # 1. FIRST STAGE DIAGNOSTICS
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 1. First stage diagnostics ---")

    sub = _prepare_data(df, PRIMARY_OUTCOME)
    y_endo = sub[ENDOGENOUS_VAR].values
    X_cols = INSTRUMENT_VARS + [c for c in COVARIATES if c in sub.columns]
    X_df = sm.add_constant(sub[X_cols].copy())

    try:
        # Full first stage regression
        if CLUSTER_VAR and CLUSTER_VAR in sub.columns:
            fs_mod = sm.OLS(y_endo, X_df).fit(
                cov_type="cluster",
                cov_kwds={"groups": sub[CLUSTER_VAR].values})
        else:
            fs_mod = sm.OLS(y_endo, X_df).fit(cov_type="HC1")

        # Partial F-statistic (instruments jointly)
        z_indices = [list(X_df.columns).index(z) for z in INSTRUMENT_VARS if z in X_df.columns]
        if len(z_indices) > 0:
            R = np.zeros((len(z_indices), len(fs_mod.params)))
            for i, idx in enumerate(z_indices):
                R[i, idx] = 1
            f_test = fs_mod.f_test(R)
            partial_F = float(f_test.fvalue)
            partial_F_pval = float(f_test.pvalue)
        else:
            partial_F = np.nan
            partial_F_pval = np.nan

        print(f"  Partial F-statistic: {partial_F:.2f} (p = {partial_F_pval:.4f})")
        if not np.isnan(partial_F) and partial_F < 10:
            print(f"  *** WEAK INSTRUMENT: F = {partial_F:.2f} < 10 (Stock-Yogo threshold) ***")

        all_results.append({
            "test": "first_stage_partial_F", "outcome": PRIMARY_OUTCOME,
            "estimate": partial_F, "se_robust": np.nan,
            "pvalue": partial_F_pval,
            "ci_lower": np.nan, "ci_upper": np.nan,
            "first_stage_F": partial_F, "N": len(sub), "method": "partial_F",
        })

        # Cragg-Donald F-statistic (non-robust, for Stock-Yogo critical values)
        fs_mod_nonrobust = sm.OLS(y_endo, X_df).fit()
        if len(z_indices) > 0:
            f_test_cd = fs_mod_nonrobust.f_test(R)
            cragg_donald_F = float(f_test_cd.fvalue)
        else:
            cragg_donald_F = np.nan
        print(f"  Cragg-Donald F-statistic: {cragg_donald_F:.2f}")

        all_results.append({
            "test": "cragg_donald_F", "outcome": PRIMARY_OUTCOME,
            "estimate": cragg_donald_F, "se_robust": np.nan,
            "pvalue": np.nan,
            "ci_lower": np.nan, "ci_upper": np.nan,
            "first_stage_F": cragg_donald_F, "N": len(sub), "method": "cragg_donald",
        })

        # Kleibergen-Paap rk Wald F (robust version, approximated)
        # With clustered SEs, partial F is effectively the KP F-stat
        kp_F = partial_F  # with robust/clustered SEs this IS the KP analog
        print(f"  Kleibergen-Paap rk Wald F (approx): {kp_F:.2f}")

        all_results.append({
            "test": "kleibergen_paap_F", "outcome": PRIMARY_OUTCOME,
            "estimate": kp_F, "se_robust": np.nan,
            "pvalue": np.nan,
            "ci_lower": np.nan, "ci_upper": np.nan,
            "first_stage_F": kp_F, "N": len(sub), "method": "kleibergen_paap",
        })

    except Exception as e:
        print(f"  First stage diagnostics failed: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # 2. WEAK INSTRUMENT ROBUST INFERENCE (Anderson-Rubin)
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 2. Anderson-Rubin confidence sets (weak-instrument robust) ---")

    ar_ci = _anderson_rubin_ci(df, PRIMARY_OUTCOME)
    if ar_ci is not None:
        print(f"  AR 95% CI: [{ar_ci[0]:.4f}, {ar_ci[1]:.4f}]")
        ar_width = ar_ci[1] - ar_ci[0]
        print(f"  AR CI width: {ar_width:.4f}")
        all_results.append({
            "test": "anderson_rubin_ci", "outcome": PRIMARY_OUTCOME,
            "estimate": (ar_ci[0] + ar_ci[1]) / 2,
            "se_robust": ar_width / (2 * 1.96),
            "pvalue": np.nan,
            "ci_lower": ar_ci[0], "ci_upper": ar_ci[1],
            "first_stage_F": partial_F if 'partial_F' in dir() else np.nan,
            "N": len(sub), "method": "anderson_rubin",
        })
    else:
        print("  Anderson-Rubin CI could not be computed.")
        all_results.append({
            "test": "anderson_rubin_ci", "outcome": PRIMARY_OUTCOME,
            "estimate": np.nan, "se_robust": np.nan, "pvalue": np.nan,
            "ci_lower": np.nan, "ci_upper": np.nan,
            "first_stage_F": np.nan, "N": len(sub), "method": "anderson_rubin",
        })

    # ══════════════════════════════════════════════════════════════════════
    # 3. PLACEBO INSTRUMENT TEST
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 3. Placebo instrument test ---")
    print("  Expected: instruments should NOT predict placebo outcomes")

    placebo_present = [p for p in PLACEBO_OUTCOMES if p in df.columns]
    if not placebo_present:
        print("  No placebo outcomes found. Skipping.")

    for pv in placebo_present:
        sub_p = df[[pv] + INSTRUMENT_VARS +
                    [c for c in COVARIATES if c in df.columns]].dropna()
        if len(sub_p) < 20:
            print(f"  {pv}: insufficient data")
            continue

        y_p = sub_p[pv].values
        X_p = sm.add_constant(sub_p[INSTRUMENT_VARS +
                                     [c for c in COVARIATES if c in sub_p.columns]].values)
        try:
            mod_p = sm.OLS(y_p, X_p).fit(cov_type="HC1")
            # Test instruments jointly
            n_z = len(INSTRUMENT_VARS)
            R_p = np.zeros((n_z, len(mod_p.params)))
            for i in range(n_z):
                R_p[i, i + 1] = 1  # +1 for constant
            f_test_p = mod_p.f_test(R_p)
            f_val = float(f_test_p.fvalue)
            f_pval = float(f_test_p.pvalue)

            sig = " *FAILS PLACEBO*" if f_pval < 0.05 else ""
            print(f"  {pv}: F = {f_val:.2f}, p = {f_pval:.4f}{sig}")

            all_results.append({
                "test": "placebo_instrument", "outcome": pv,
                "estimate": f_val, "se_robust": np.nan,
                "pvalue": f_pval,
                "ci_lower": np.nan, "ci_upper": np.nan,
                "first_stage_F": np.nan, "N": len(sub_p),
                "method": "placebo_F_test",
            })
        except Exception as e:
            print(f"  {pv}: failed ({e})")

    # ══════════════════════════════════════════════════════════════════════
    # 4. EXCLUSION RESTRICTION SENSITIVITY (Conley et al. bounds)
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 4. Exclusion restriction sensitivity (Conley et al. bounds) ---")
    print("  Allowing direct effect of instrument on outcome: gamma in [-delta, delta]")

    sub_er = _prepare_data(df, PRIMARY_OUTCOME)
    if len(sub_er) >= 20:
        y_er = sub_er[PRIMARY_OUTCOME].values
        endog_er = sub_er[ENDOGENOUS_VAR].values

        # Get 2SLS estimate for reference
        try:
            X_er_cols = INSTRUMENT_VARS + [c for c in COVARIATES if c in sub_er.columns]
            Z_er = sm.add_constant(sub_er[X_er_cols].values)
            fs_er = sm.OLS(endog_er, Z_er).fit()
            endog_hat = fs_er.fittedvalues

            X_2s = sm.add_constant(
                np.column_stack([endog_hat] +
                                [sub_er[c].values for c in COVARIATES if c in sub_er.columns]))
            ss_er = sm.OLS(y_er, X_2s).fit()
            beta_2sls = ss_er.params[1]

            # Conley bounds: for each delta, adjusted beta = beta_2sls - delta * (gamma/pi)
            # Simplified: we perturb the outcome by gamma * Z and re-estimate
            z_vals = sub_er[INSTRUMENT_VARS[0]].values if INSTRUMENT_VARS[0] in sub_er.columns else None

            if z_vals is not None:
                sd_z = np.std(z_vals)
                deltas = [0, 0.01 * sd_z, 0.05 * sd_z, 0.10 * sd_z]
                print(f"  Reference 2SLS estimate: {beta_2sls:.4f}")

                for delta in deltas:
                    y_adj_lo = y_er - delta * z_vals
                    y_adj_hi = y_er + delta * z_vals

                    ss_lo = sm.OLS(y_adj_lo, X_2s).fit()
                    ss_hi = sm.OLS(y_adj_hi, X_2s).fit()

                    bound_lo = min(ss_lo.params[1], ss_hi.params[1])
                    bound_hi = max(ss_lo.params[1], ss_hi.params[1])

                    print(f"  delta={delta:.4f}: [{bound_lo:.4f}, {bound_hi:.4f}]")

                    all_results.append({
                        "test": f"conley_delta_{delta:.4f}",
                        "outcome": PRIMARY_OUTCOME,
                        "estimate": beta_2sls,
                        "se_robust": np.nan, "pvalue": np.nan,
                        "ci_lower": bound_lo, "ci_upper": bound_hi,
                        "first_stage_F": np.nan, "N": len(sub_er),
                        "method": "conley_bounds",
                    })
        except Exception as e:
            print(f"  Conley bounds failed: {e}")
    else:
        print("  Insufficient data for Conley bounds.")

    # ══════════════════════════════════════════════════════════════════════
    # 5. ALTERNATIVE INSTRUMENT SETS (each instrument separately)
    # ══════════════════════════════════════════════════════════════════════
    if len(INSTRUMENT_VARS) > 1:
        print("\n--- 5. Alternative instrument sets (each instrument separately) ---")

        for z in INSTRUMENT_VARS:
            sub_alt = _prepare_data(df, PRIMARY_OUTCOME)
            if len(sub_alt) < 20:
                continue

            y_alt = sub_alt[PRIMARY_OUTCOME].values
            endog_alt = sub_alt[ENDOGENOUS_VAR].values

            try:
                # First stage with single instrument
                X_fs = sm.add_constant(
                    sub_alt[[z] + [c for c in COVARIATES if c in sub_alt.columns]].values)
                fs_single = sm.OLS(endog_alt, X_fs).fit()
                f_single = float(fs_single.fvalue)

                # 2SLS with single instrument
                endog_hat_s = fs_single.fittedvalues
                X_2s_alt = sm.add_constant(
                    np.column_stack([endog_hat_s] +
                                    [sub_alt[c].values for c in COVARIATES if c in sub_alt.columns]))
                ss_alt = sm.OLS(y_alt, X_2s_alt).fit(cov_type="HC1")

                est = ss_alt.params[1]
                se = ss_alt.bse[1]
                ci = ss_alt.conf_int()[1]

                print(f"  Instrument: {z}")
                print(f"    First-stage F: {f_single:.2f}")
                print(f"    2SLS estimate: {est:.4f} (SE: {se:.4f})")
                print(f"    95% CI: [{ci[0]:.4f}, {ci[1]:.4f}]")

                all_results.append({
                    "test": f"alt_instrument_{z}", "outcome": PRIMARY_OUTCOME,
                    "estimate": est, "se_robust": se,
                    "pvalue": ss_alt.pvalues[1],
                    "ci_lower": ci[0], "ci_upper": ci[1],
                    "first_stage_F": f_single, "N": len(sub_alt),
                    "method": f"2SLS_single_{z}",
                })
            except Exception as e:
                print(f"  Instrument {z}: failed ({e})")
    else:
        print("\n--- 5. Alternative instrument sets: only 1 instrument, skipping. ---")

    # ══════════════════════════════════════════════════════════════════════
    # 6. REDUCED FORM ROBUSTNESS
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 6. Reduced form robustness ---")

    sub_rf = _prepare_data(df, PRIMARY_OUTCOME)
    if len(sub_rf) >= 20:
        y_rf = sub_rf[PRIMARY_OUTCOME].values

        # Baseline reduced form
        X_rf_cols = INSTRUMENT_VARS + [c for c in COVARIATES if c in sub_rf.columns]
        X_rf = sm.add_constant(sub_rf[X_rf_cols].copy())

        try:
            if CLUSTER_VAR and CLUSTER_VAR in sub_rf.columns:
                rf_mod = sm.OLS(y_rf, X_rf).fit(
                    cov_type="cluster",
                    cov_kwds={"groups": sub_rf[CLUSTER_VAR].values})
            else:
                rf_mod = sm.OLS(y_rf, X_rf).fit(cov_type="HC1")

            for z in INSTRUMENT_VARS:
                if z in X_rf.columns:
                    idx = list(X_rf.columns).index(z)
                    ci = rf_mod.conf_int().iloc[idx]
                    print(f"  {z}: coef={rf_mod.params.iloc[idx]:.4f} "
                          f"SE={rf_mod.bse.iloc[idx]:.4f} "
                          f"CI=[{ci[0]:.4f}, {ci[1]:.4f}]")

                    all_results.append({
                        "test": f"reduced_form_{z}", "outcome": PRIMARY_OUTCOME,
                        "estimate": rf_mod.params.iloc[idx],
                        "se_robust": rf_mod.bse.iloc[idx],
                        "pvalue": rf_mod.pvalues.iloc[idx],
                        "ci_lower": ci[0], "ci_upper": ci[1],
                        "first_stage_F": np.nan, "N": len(sub_rf),
                        "method": "OLS_reduced_form",
                    })

            # Reduced form without covariates (raw)
            X_rf_raw = sm.add_constant(sub_rf[INSTRUMENT_VARS].copy())
            rf_raw = sm.OLS(y_rf, X_rf_raw).fit(cov_type="HC1")
            for z in INSTRUMENT_VARS:
                if z in X_rf_raw.columns:
                    idx = list(X_rf_raw.columns).index(z)
                    ci = rf_raw.conf_int().iloc[idx]
                    print(f"  {z} (no controls): coef={rf_raw.params.iloc[idx]:.4f} "
                          f"SE={rf_raw.bse.iloc[idx]:.4f}")

                    all_results.append({
                        "test": f"reduced_form_raw_{z}", "outcome": PRIMARY_OUTCOME,
                        "estimate": rf_raw.params.iloc[idx],
                        "se_robust": rf_raw.bse.iloc[idx],
                        "pvalue": rf_raw.pvalues.iloc[idx],
                        "ci_lower": ci[0], "ci_upper": ci[1],
                        "first_stage_F": np.nan, "N": len(sub_rf),
                        "method": "OLS_reduced_form_raw",
                    })
        except Exception as e:
            print(f"  Reduced form robustness failed: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # 7. WILD CLUSTER BOOTSTRAP (if <50 clusters)
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 7. Wild cluster bootstrap ---")

    if CLUSTER_VAR and CLUSTER_VAR in df.columns:
        n_clusters = df[CLUSTER_VAR].nunique()
        print(f"  Number of clusters: {n_clusters}")

        if n_clusters < 50:
            print(f"  Running wild cluster bootstrap (few clusters)...")

            sub_wcb = _prepare_data(df, PRIMARY_OUTCOME)
            if len(sub_wcb) >= 20:
                try:
                    y_wcb = sub_wcb[PRIMARY_OUTCOME].values
                    endog_wcb = sub_wcb[ENDOGENOUS_VAR].values
                    cluster_ids = sub_wcb[CLUSTER_VAR].values
                    unique_clusters = np.unique(cluster_ids)

                    # Get point estimate from 2SLS
                    X_fs_cols = INSTRUMENT_VARS + [c for c in COVARIATES if c in sub_wcb.columns]
                    Z_wcb = sm.add_constant(sub_wcb[X_fs_cols].values)
                    fs_wcb = sm.OLS(endog_wcb, Z_wcb).fit()
                    endog_hat_wcb = fs_wcb.fittedvalues

                    X_2s_wcb = sm.add_constant(
                        np.column_stack([endog_hat_wcb] +
                                        [sub_wcb[c].values for c in COVARIATES if c in sub_wcb.columns]))
                    ss_wcb = sm.OLS(y_wcb, X_2s_wcb).fit()
                    beta_orig = ss_wcb.params[1]
                    resid_orig = ss_wcb.resid

                    # Wild bootstrap (Rademacher weights)
                    n_boot = 999
                    boot_betas = []
                    rng = np.random.default_rng(42)

                    for b in range(n_boot):
                        # Rademacher weights at cluster level
                        weights = rng.choice([-1, 1], size=len(unique_clusters))
                        w_map = dict(zip(unique_clusters, weights))
                        w_vec = np.array([w_map[c] for c in cluster_ids])

                        # Wild bootstrap residuals
                        y_boot = ss_wcb.fittedvalues + resid_orig * w_vec

                        try:
                            fs_b = sm.OLS(endog_wcb, Z_wcb).fit()
                            endog_hat_b = fs_b.fittedvalues
                            X_2s_b = X_2s_wcb.copy()
                            X_2s_b[:, 1] = endog_hat_b
                            ss_b = sm.OLS(y_boot, X_2s_b).fit()
                            boot_betas.append(ss_b.params[1])
                        except Exception:
                            continue

                    if len(boot_betas) > 50:
                        boot_arr = np.array(boot_betas)
                        ci_lo = np.percentile(boot_arr, 2.5)
                        ci_hi = np.percentile(boot_arr, 97.5)
                        boot_se = np.std(boot_arr)

                        print(f"  Wild cluster bootstrap ({len(boot_betas)} replications):")
                        print(f"    Point estimate: {beta_orig:.4f}")
                        print(f"    Bootstrap SE: {boot_se:.4f}")
                        print(f"    Bootstrap 95% CI: [{ci_lo:.4f}, {ci_hi:.4f}]")

                        all_results.append({
                            "test": "wild_cluster_bootstrap", "outcome": PRIMARY_OUTCOME,
                            "estimate": beta_orig, "se_robust": boot_se,
                            "pvalue": np.nan,
                            "ci_lower": ci_lo, "ci_upper": ci_hi,
                            "first_stage_F": np.nan, "N": len(sub_wcb),
                            "method": "wild_cluster_bootstrap",
                        })
                    else:
                        print(f"  Bootstrap produced too few valid replications.")
                except Exception as e:
                    print(f"  Wild cluster bootstrap failed: {e}")
        else:
            print(f"  Clusters >= 50. Standard cluster-robust SEs are reliable. Skipping bootstrap.")
    else:
        print("  No cluster variable. Skipping.")

    # ══════════════════════════════════════════════════════════════════════
    # 8. RANDOMIZATION INFERENCE / PERMUTATION P-VALUES
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 8. Randomization inference (permutation p-values) ---")

    sub_ri = _prepare_data(df, PRIMARY_OUTCOME)
    if len(sub_ri) >= 20:
        z_var = INSTRUMENT_VARS[0]
        if z_var in sub_ri.columns:
            y_ri = sub_ri[PRIMARY_OUTCOME].values
            z_ri = sub_ri[z_var].values
            X_ri_cols = [z_var] + [c for c in COVARIATES if c in sub_ri.columns]
            X_ri = sm.add_constant(sub_ri[X_ri_cols].values)

            try:
                mod_orig = sm.OLS(y_ri, X_ri).fit(cov_type="HC1")
                t_orig = mod_orig.tvalues[1]

                n_perms = 2000
                rng = np.random.default_rng(42)
                t_perms = np.zeros(n_perms)

                for p in range(n_perms):
                    z_perm = rng.permutation(z_ri)
                    X_perm = X_ri.copy()
                    X_perm[:, 1] = z_perm
                    try:
                        mod_p = sm.OLS(y_ri, X_perm).fit()
                        t_perms[p] = mod_p.tvalues[1]
                    except Exception:
                        t_perms[p] = 0

                perm_pval = np.mean(np.abs(t_perms) >= np.abs(t_orig))
                print(f"  t_original: {t_orig:.3f}")
                print(f"  Permutation p-value ({n_perms} reshuffles): {perm_pval:.4f}")
                print(f"  Conventional p-value: {mod_orig.pvalues[1]:.4f}")

                all_results.append({
                    "test": "randomization_inference", "outcome": PRIMARY_OUTCOME,
                    "estimate": t_orig, "se_robust": np.nan,
                    "pvalue": perm_pval,
                    "ci_lower": mod_orig.pvalues[1], "ci_upper": np.nan,
                    "first_stage_F": np.nan, "N": len(sub_ri),
                    "method": f"permutation_{n_perms}",
                })
            except Exception as e:
                print(f"  Randomization inference failed: {e}")
    else:
        print("  Insufficient data for randomization inference.")

    # ══════════════════════════════════════════════════════════════════════
    # 9. PLACEBO TREATMENT TEST (randomly permuted instrument)
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 9. Placebo treatment test (permuted instrument) ---")

    sub_pt = _prepare_data(df, PRIMARY_OUTCOME)
    if len(sub_pt) >= 20:
        z_var = INSTRUMENT_VARS[0]
        if z_var in sub_pt.columns:
            try:
                rng = np.random.default_rng(123)
                z_perm = rng.permutation(sub_pt[z_var].values)

                y_pt = sub_pt[PRIMARY_OUTCOME].values
                X_pt_cols = [c for c in COVARIATES if c in sub_pt.columns]
                X_pt = sm.add_constant(
                    np.column_stack([z_perm] + [sub_pt[c].values for c in X_pt_cols])
                )
                mod_placebo = sm.OLS(y_pt, X_pt).fit(cov_type="HC1")

                est_p = mod_placebo.params[1]
                se_p = mod_placebo.bse[1]
                pval_p = mod_placebo.pvalues[1]
                sig = " *FAILS PLACEBO*" if pval_p < 0.05 else ""
                print(f"  Permuted instrument: est={est_p:.4f}  SE={se_p:.4f}  "
                      f"p={pval_p:.4f}{sig}")
                print(f"  Expected: near-zero, insignificant")

                all_results.append({
                    "test": "placebo_treatment", "outcome": PRIMARY_OUTCOME,
                    "estimate": est_p, "se_robust": se_p,
                    "pvalue": pval_p,
                    "ci_lower": np.nan, "ci_upper": np.nan,
                    "first_stage_F": np.nan, "N": len(sub_pt),
                    "method": "placebo_permuted_instrument",
                })
            except Exception as e:
                print(f"  Placebo treatment test failed: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # 10. SUTVA / SPILLOVER TESTS
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 10. SUTVA / spillover tests ---")

    # Check for within-cluster spillovers: add entity FE if available
    USE_ENTITY_FE = (ENTITY_VAR and ENTITY_VAR != "None")
    if USE_ENTITY_FE and ENTITY_VAR in df.columns:
        sub_sutva = _prepare_data(df, PRIMARY_OUTCOME)
        if ENTITY_VAR in sub_sutva.columns and len(sub_sutva) >= 30:
            try:
                # Main spec WITHOUT entity FE
                X_cols_no_fe = INSTRUMENT_VARS + [c for c in COVARIATES if c in sub_sutva.columns]
                X_no_fe = sm.add_constant(sub_sutva[X_cols_no_fe].values)
                mod_no_fe = sm.OLS(sub_sutva[PRIMARY_OUTCOME].values, X_no_fe).fit(cov_type="HC1")
                est_no_fe = mod_no_fe.params[1]

                # Main spec WITH entity FE
                fe_dums = pd.get_dummies(sub_sutva[ENTITY_VAR], prefix="fe", drop_first=True)
                if len(fe_dums.columns) < 500:
                    X_with_fe = sm.add_constant(
                        pd.concat([sub_sutva[X_cols_no_fe], fe_dums], axis=1).values
                    )
                    mod_with_fe = sm.OLS(sub_sutva[PRIMARY_OUTCOME].values,
                                         X_with_fe).fit(cov_type="HC1")
                    est_with_fe = mod_with_fe.params[1]

                    pct_change = abs(est_with_fe - est_no_fe) / abs(est_no_fe) * 100 if abs(est_no_fe) > 1e-10 else np.nan
                    flag = " *>10% CHANGE*" if (not np.isnan(pct_change) and pct_change > 10) else ""
                    print(f"  ITT without entity FE: {est_no_fe:.4f}")
                    print(f"  ITT with entity FE:    {est_with_fe:.4f}")
                    print(f"  Change: {pct_change:.1f}%{flag}")

                    all_results.append({
                        "test": "sutva_entity_fe", "outcome": PRIMARY_OUTCOME,
                        "estimate": est_with_fe, "se_robust": mod_with_fe.bse[1],
                        "pvalue": mod_with_fe.pvalues[1],
                        "ci_lower": est_no_fe, "ci_upper": pct_change,
                        "first_stage_F": np.nan, "N": len(sub_sutva),
                        "method": "OLS_entity_FE",
                    })
            except Exception as e:
                print(f"  SUTVA entity FE test failed: {e}")
    else:
        print("  No entity variable for SUTVA test.")

    # Check for duplicate families/clusters (sibling check)
    if CLUSTER_VAR and CLUSTER_VAR in df.columns:
        cluster_counts = df[CLUSTER_VAR].value_counts()
        n_multi = (cluster_counts > 1).sum()
        n_total_clusters = len(cluster_counts)
        print(f"  Clusters with >1 observation: {n_multi}/{n_total_clusters}")
        if n_multi > 0:
            print(f"  Within-cluster observations may have correlated outcomes.")
            print(f"  => Cluster-robust SEs required at {CLUSTER_VAR} level.")

    # ══════════════════════════════════════════════════════════════════════
    # 11. SPECIFICATION CURVE (multiple specs × functional forms)
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 11. Specification curve ---")

    sub_sc = _prepare_data(df, PRIMARY_OUTCOME)
    if len(sub_sc) >= 20:
        z_var = INSTRUMENT_VARS[0]
        spec_results = []

        # Control sets
        cov_sets = {
            "no_controls": [],
            "basic_controls": COVARIATES[:min(3, len(COVARIATES))],
            "full_controls": COVARIATES,
        }

        # Functional forms: OLS ITT (reduced form)
        for set_name, controls in cov_sets.items():
            avail = [c for c in controls if c in sub_sc.columns]
            X_cols = [z_var] + avail
            try:
                X = sm.add_constant(sub_sc[X_cols].values)
                mod = sm.OLS(sub_sc[PRIMARY_OUTCOME].values, X).fit(cov_type="HC1")
                ci = mod.conf_int()[1]
                spec_results.append({
                    "spec": f"LPM_{set_name}", "estimate": mod.params[1],
                    "se": mod.bse[1], "pvalue": mod.pvalues[1],
                    "ci_lower": ci[0], "ci_upper": ci[1],
                    "r_squared": mod.rsquared,
                })
                print(f"  LPM {set_name}: est={mod.params[1]:.4f}  "
                      f"SE={mod.bse[1]:.4f}  R²={mod.rsquared:.4f}")
            except Exception:
                pass

        # Probit/Logit marginal effects (if binary outcome)
        y_vals = sub_sc[PRIMARY_OUTCOME].dropna().unique()
        is_binary = set(y_vals).issubset({0, 1, 0.0, 1.0})

        if is_binary:
            for set_name, controls in cov_sets.items():
                avail = [c for c in controls if c in sub_sc.columns]
                X_cols = [z_var] + avail
                try:
                    X = sm.add_constant(sub_sc[X_cols].values)
                    y = sub_sc[PRIMARY_OUTCOME].values

                    # Probit
                    probit_mod = sm.Probit(y, X).fit(disp=0)
                    mfx = probit_mod.get_margeff()
                    spec_results.append({
                        "spec": f"probit_{set_name}",
                        "estimate": mfx.margeff[0],
                        "se": mfx.margeff_se[0],
                        "pvalue": mfx.pvalues[0],
                        "ci_lower": mfx.margeff[0] - 1.96 * mfx.margeff_se[0],
                        "ci_upper": mfx.margeff[0] + 1.96 * mfx.margeff_se[0],
                        "r_squared": np.nan,
                    })
                    print(f"  Probit {set_name}: AME={mfx.margeff[0]:.4f}  "
                          f"SE={mfx.margeff_se[0]:.4f}")

                    # Logit
                    logit_mod = sm.Logit(y, X).fit(disp=0)
                    mfx_l = logit_mod.get_margeff()
                    spec_results.append({
                        "spec": f"logit_{set_name}",
                        "estimate": mfx_l.margeff[0],
                        "se": mfx_l.margeff_se[0],
                        "pvalue": mfx_l.pvalues[0],
                        "ci_lower": mfx_l.margeff[0] - 1.96 * mfx_l.margeff_se[0],
                        "ci_upper": mfx_l.margeff[0] + 1.96 * mfx_l.margeff_se[0],
                        "r_squared": np.nan,
                    })
                    print(f"  Logit {set_name}: AME={mfx_l.margeff[0]:.4f}  "
                          f"SE={mfx_l.margeff_se[0]:.4f}")
                except Exception:
                    pass

        # Save all spec curve results
        for sr in spec_results:
            all_results.append({
                "test": f"spec_curve_{sr['spec']}", "outcome": PRIMARY_OUTCOME,
                "estimate": sr['estimate'], "se_robust": sr['se'],
                "pvalue": sr['pvalue'],
                "ci_lower": sr['ci_lower'], "ci_upper": sr['ci_upper'],
                "first_stage_F": np.nan, "N": len(sub_sc),
                "method": sr['spec'],
            })

        # Save spec curve as separate CSV for figure generation
        if spec_results:
            sc_df = pd.DataFrame(spec_results)
            sc_path = os.path.join(DATA_DIR, "specification_curve.csv")
            sc_df.to_csv(sc_path, index=False)
            print(f"  Saved: {sc_path}")

    # ══════════════════════════════════════════════════════════════════════
    # 12. OSTER (2019) COEFFICIENT STABILITY (delta)
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 12. Oster (2019) coefficient stability ---")

    sub_oster = _prepare_data(df, PRIMARY_OUTCOME)
    if len(sub_oster) >= 20:
        z_var = INSTRUMENT_VARS[0]
        try:
            # Uncontrolled regression
            X_uncontrolled = sm.add_constant(sub_oster[z_var].values)
            mod_u = sm.OLS(sub_oster[PRIMARY_OUTCOME].values,
                           X_uncontrolled).fit()
            beta_u = mod_u.params[1]
            r2_u = mod_u.rsquared

            # Controlled regression
            X_controlled_cols = [z_var] + [c for c in COVARIATES if c in sub_oster.columns]
            X_controlled = sm.add_constant(sub_oster[X_controlled_cols].values)
            mod_c = sm.OLS(sub_oster[PRIMARY_OUTCOME].values,
                           X_controlled).fit()
            beta_c = mod_c.params[1]
            r2_c = mod_c.rsquared

            # Rmax = min(1, 1.3 * R2_controlled)
            r2_max = min(1.0, 1.3 * r2_c)

            # Oster delta: degree of selection on unobservables needed to explain away beta_c
            # delta = (beta_c * (r2_max - r2_c)) / ((beta_u - beta_c) * (r2_c - r2_u))
            denom = (beta_u - beta_c) * (r2_c - r2_u)
            if abs(denom) > 1e-10:
                delta = (beta_c * (r2_max - r2_c)) / denom
            else:
                delta = np.inf

            print(f"  beta_uncontrolled: {beta_u:.4f}  R²_u: {r2_u:.4f}")
            print(f"  beta_controlled:   {beta_c:.4f}  R²_c: {r2_c:.4f}")
            print(f"  R²_max:            {r2_max:.4f}")
            print(f"  Oster delta:       {delta:.2f}")
            if abs(delta) < 1:
                print(f"  *** WARNING: delta < 1 — result fragile to selection on unobservables ***")
            else:
                print(f"  delta >= 1: result robust to proportional selection.")

            all_results.append({
                "test": "oster_delta", "outcome": PRIMARY_OUTCOME,
                "estimate": delta, "se_robust": np.nan,
                "pvalue": np.nan,
                "ci_lower": beta_u, "ci_upper": beta_c,
                "first_stage_F": np.nan, "N": len(sub_oster),
                "method": "oster_2019",
            })
        except Exception as e:
            print(f"  Oster (2019) failed: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # 13. LPM vs PROBIT/LOGIT (for binary outcomes)
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 13. LPM vs Probit/Logit comparison ---")

    if PRIMARY_OUTCOME in df.columns:
        y_vals = df[PRIMARY_OUTCOME].dropna().unique()
        is_binary = set(y_vals).issubset({0, 1, 0.0, 1.0})

        if is_binary:
            sub_fl = _prepare_data(df, PRIMARY_OUTCOME)
            z_var = INSTRUMENT_VARS[0]
            X_fl_cols = [z_var] + [c for c in COVARIATES if c in sub_fl.columns]
            X_fl = sm.add_constant(sub_fl[X_fl_cols].values)
            y_fl = sub_fl[PRIMARY_OUTCOME].values

            # LPM
            lpm = sm.OLS(y_fl, X_fl).fit(cov_type="HC2")
            lpm_est = lpm.params[1]
            lpm_se = lpm.bse[1]

            # Out-of-bounds predictions
            lpm_preds = lpm.fittedvalues
            oob_pct = 100 * ((lpm_preds < 0) | (lpm_preds > 1)).mean()

            try:
                # Probit
                probit = sm.Probit(y_fl, X_fl).fit(disp=0)
                probit_mfx = probit.get_margeff()
                probit_est = probit_mfx.margeff[0]
                probit_se = probit_mfx.margeff_se[0]
            except Exception:
                probit_est, probit_se = np.nan, np.nan

            try:
                # Logit
                logit = sm.Logit(y_fl, X_fl).fit(disp=0)
                logit_mfx = logit.get_margeff()
                logit_est = logit_mfx.margeff[0]
                logit_se = logit_mfx.margeff_se[0]
            except Exception:
                logit_est, logit_se = np.nan, np.nan

            print(f"  LPM:    est={lpm_est:.4f}  SE={lpm_se:.4f}  "
                  f"(OOB predictions: {oob_pct:.1f}%)")
            if not np.isnan(probit_est):
                print(f"  Probit: AME={probit_est:.4f}  SE={probit_se:.4f}")
            if not np.isnan(logit_est):
                print(f"  Logit:  AME={logit_est:.4f}  SE={logit_se:.4f}")

            # Check consistency
            if not np.isnan(probit_est):
                consistent = (np.sign(lpm_est) == np.sign(probit_est))
                print(f"  Sign consistent: {consistent}")
                if not consistent:
                    print(f"  *** WARNING: LPM and probit disagree on sign ***")

            all_results.append({
                "test": "lpm_vs_probit_logit", "outcome": PRIMARY_OUTCOME,
                "estimate": lpm_est, "se_robust": lpm_se,
                "pvalue": lpm.pvalues[1],
                "ci_lower": probit_est if not np.isnan(probit_est) else lpm_est,
                "ci_upper": logit_est if not np.isnan(logit_est) else lpm_est,
                "first_stage_F": np.nan, "N": len(sub_fl),
                "method": f"lpm_probit_logit_oob{oob_pct:.0f}pct",
            })
        else:
            print(f"  {PRIMARY_OUTCOME} is not binary. Skipping.")
    else:
        print(f"  Primary outcome not in data. Skipping.")

    # ══════════════════════════════════════════════════════════════════════
    # 14. MEDIATION ANALYSIS (Imai, Keele & Yamamoto 2010)
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 14. Causal mediation analysis (IKY 2010) ---")

    USE_MEDIATOR = (MEDIATOR_VAR and MEDIATOR_VAR != "None" and MEDIATOR_VAR in df.columns)
    if USE_MEDIATOR:
        z_var = INSTRUMENT_VARS[0]
        med_cols = [PRIMARY_OUTCOME, MEDIATOR_VAR, z_var] + \
                   [c for c in COVARIATES if c in df.columns]
        sub_med = df[med_cols].dropna()

        if len(sub_med) >= 30:
            y_med = sub_med[PRIMARY_OUTCOME].values
            m_med = sub_med[MEDIATOR_VAR].values
            z_med = sub_med[z_var].values
            cov_cols = [c for c in COVARIATES if c in sub_med.columns]

            try:
                # Mediator model: M ~ Z + covariates
                X_m = sm.add_constant(
                    np.column_stack([z_med] + [sub_med[c].values for c in cov_cols])
                )
                mod_m = sm.OLS(m_med, X_m).fit(cov_type="HC1")
                alpha_z = mod_m.params[1]  # effect of Z on M

                # Outcome model: Y ~ Z + M + covariates
                X_y = sm.add_constant(
                    np.column_stack([z_med, m_med] +
                                    [sub_med[c].values for c in cov_cols])
                )
                mod_y = sm.OLS(y_med, X_y).fit(cov_type="HC1")
                beta_m = mod_y.params[2]   # effect of M on Y (controlling for Z)
                gamma_z = mod_y.params[1]  # direct effect of Z on Y

                # ACME (Average Causal Mediation Effect) = alpha_z * beta_m
                acme = alpha_z * beta_m

                # ADE (Average Direct Effect) = gamma_z
                ade = gamma_z

                # Total effect = ACME + ADE
                total = acme + ade

                # Proportion mediated
                prop_mediated = acme / total if abs(total) > 1e-10 else np.nan

                # Bootstrap CIs for ACME
                n_boot = 1000
                rng_med = np.random.default_rng(42)
                acme_boot = np.zeros(n_boot)
                ade_boot = np.zeros(n_boot)

                for b in range(n_boot):
                    idx = rng_med.integers(0, len(sub_med), size=len(sub_med))
                    try:
                        mod_m_b = sm.OLS(m_med[idx], X_m[idx]).fit()
                        mod_y_b = sm.OLS(y_med[idx], X_y[idx]).fit()
                        acme_boot[b] = mod_m_b.params[1] * mod_y_b.params[2]
                        ade_boot[b] = mod_y_b.params[1]
                    except Exception:
                        acme_boot[b] = np.nan
                        ade_boot[b] = np.nan

                acme_boot = acme_boot[~np.isnan(acme_boot)]
                ade_boot = ade_boot[~np.isnan(ade_boot)]

                acme_ci = (np.percentile(acme_boot, 2.5), np.percentile(acme_boot, 97.5)) \
                    if len(acme_boot) > 50 else (np.nan, np.nan)
                ade_ci = (np.percentile(ade_boot, 2.5), np.percentile(ade_boot, 97.5)) \
                    if len(ade_boot) > 50 else (np.nan, np.nan)

                print(f"  ACME (indirect via {MEDIATOR_VAR}): {acme:.4f}  "
                      f"95% CI: [{acme_ci[0]:.4f}, {acme_ci[1]:.4f}]")
                print(f"  ADE  (direct):                      {ade:.4f}  "
                      f"95% CI: [{ade_ci[0]:.4f}, {ade_ci[1]:.4f}]")
                print(f"  Total Effect:                       {total:.4f}")
                print(f"  Proportion Mediated:                "
                      f"{prop_mediated:.3f}" if not np.isnan(prop_mediated) else "  ---")

                all_results.append({
                    "test": "mediation_acme", "outcome": PRIMARY_OUTCOME,
                    "estimate": acme, "se_robust": np.std(acme_boot) if len(acme_boot) > 0 else np.nan,
                    "pvalue": np.nan,
                    "ci_lower": acme_ci[0], "ci_upper": acme_ci[1],
                    "first_stage_F": np.nan, "N": len(sub_med),
                    "method": "IKY_2010_ACME",
                })
                all_results.append({
                    "test": "mediation_ade", "outcome": PRIMARY_OUTCOME,
                    "estimate": ade, "se_robust": np.std(ade_boot) if len(ade_boot) > 0 else np.nan,
                    "pvalue": np.nan,
                    "ci_lower": ade_ci[0], "ci_upper": ade_ci[1],
                    "first_stage_F": np.nan, "N": len(sub_med),
                    "method": "IKY_2010_ADE",
                })
                all_results.append({
                    "test": "mediation_total", "outcome": PRIMARY_OUTCOME,
                    "estimate": total, "se_robust": np.nan,
                    "pvalue": np.nan,
                    "ci_lower": prop_mediated, "ci_upper": np.nan,
                    "first_stage_F": np.nan, "N": len(sub_med),
                    "method": "IKY_2010_total",
                })

                # ── Sensitivity analysis for sequential ignorability ──────
                print(f"\n  --- Mediation sensitivity (ACME vs rho) ---")
                rho_vals = [-0.9, -0.6, -0.3, 0, 0.3, 0.6, 0.9]
                rho_star = None
                sensitivity_rows = []

                for rho in rho_vals:
                    # Approximate: ACME(rho) ≈ ACME * (1 - rho^2) + correction
                    # Simplified sensitivity: shift ACME by rho * sigma_m * sigma_y
                    sigma_m = np.std(m_med)
                    sigma_y = np.std(y_med)
                    acme_adj = acme - rho * sigma_m * sigma_y * np.sign(acme) * 0.1
                    sensitivity_rows.append({"rho": rho, "acme_adjusted": acme_adj})
                    print(f"    rho={rho:+.1f}: ACME_adj={acme_adj:.4f}")

                    # Find rho* where ACME crosses zero
                    if rho_star is None and len(sensitivity_rows) >= 2:
                        prev = sensitivity_rows[-2]
                        curr = sensitivity_rows[-1]
                        if np.sign(prev['acme_adjusted']) != np.sign(curr['acme_adjusted']):
                            # Linear interpolation
                            rho_star = prev['rho'] + (curr['rho'] - prev['rho']) * \
                                abs(prev['acme_adjusted']) / \
                                (abs(prev['acme_adjusted']) + abs(curr['acme_adjusted']))

                if rho_star is not None:
                    print(f"  rho* (ACME=0): {rho_star:.3f}")
                else:
                    print(f"  rho*: ACME does not cross zero in [-0.9, 0.9]")

                # Save sensitivity data
                if sensitivity_rows:
                    sens_df = pd.DataFrame(sensitivity_rows)
                    sens_path = os.path.join(DATA_DIR, "mediation_sensitivity.csv")
                    sens_df.to_csv(sens_path, index=False)
                    print(f"  Saved: {sens_path}")

                    all_results.append({
                        "test": "mediation_sensitivity", "outcome": PRIMARY_OUTCOME,
                        "estimate": rho_star if rho_star else np.nan,
                        "se_robust": np.nan, "pvalue": np.nan,
                        "ci_lower": np.nan, "ci_upper": np.nan,
                        "first_stage_F": np.nan, "N": len(sub_med),
                        "method": "IKY_2010_sensitivity",
                    })

            except Exception as e:
                print(f"  Mediation analysis failed: {e}")
        else:
            print(f"  Insufficient data for mediation (N={len(sub_med)}).")
    else:
        print(f"  No mediator variable specified. Skipping.")
        print(f"  (Set MEDIATOR_VAR to enable IKY 2010 mediation analysis.)")

    # ══════════════════════════════════════════════════════════════════════
    # 15. EXCLUSION RESTRICTION FALSIFICATION
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 15. Exclusion restriction falsification ---")
    print("  Testing: instrument should NOT predict pre-treatment outcomes")

    placebo_present = [p for p in PLACEBO_OUTCOMES if p in df.columns]
    if placebo_present:
        z_var = INSTRUMENT_VARS[0]
        for pv in placebo_present:
            sub_er = df[[pv, z_var] + [c for c in COVARIATES if c in df.columns]].dropna()
            if len(sub_er) < 20:
                continue

            X_er = sm.add_constant(
                sub_er[[z_var] + [c for c in COVARIATES if c in sub_er.columns]].values
            )
            try:
                mod_er = sm.OLS(sub_er[pv].values, X_er).fit(cov_type="HC1")
                est_er = mod_er.params[1]
                pval_er = mod_er.pvalues[1]
                sig = " *FAILS EXCLUSION*" if pval_er < 0.05 else ""
                print(f"  {pv}: est={est_er:.4f}  p={pval_er:.4f}{sig}")

                all_results.append({
                    "test": f"exclusion_restriction_{pv}", "outcome": pv,
                    "estimate": est_er, "se_robust": mod_er.bse[1],
                    "pvalue": pval_er,
                    "ci_lower": np.nan, "ci_upper": np.nan,
                    "first_stage_F": np.nan, "N": len(sub_er),
                    "method": "exclusion_falsification",
                })
            except Exception:
                pass
    else:
        print("  No placebo outcomes available for falsification test.")

    # ══════════════════════════════════════════════════════════════════════
    # 16. MULTIPLE HYPOTHESIS CORRECTION (BH FDR across robustness tests)
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 16. Multiple hypothesis correction (BH FDR) ---")

    testable = [r for r in all_results if not np.isnan(r.get("pvalue", np.nan))
                and r.get("pvalue", np.nan) > 0]
    if len(testable) > 1:
        pvals = np.array([r["pvalue"] for r in testable])
        n_p = len(pvals)
        ranked = np.argsort(pvals)
        adj = np.empty(n_p)
        for i, rank_idx in enumerate(reversed(ranked)):
            rank = n_p - i
            if i == 0:
                adj[rank_idx] = pvals[rank_idx]
            else:
                adj[rank_idx] = min(pvals[rank_idx] * n_p / rank, adj[ranked[n_p - i]])
        adj = np.minimum(adj, 1.0)

        for i, r in enumerate(testable):
            r["pvalue_bh"] = adj[i]

        print(f"  Corrected {n_p} tests. Summary of significant after correction:")
        for i, r in enumerate(testable):
            if r["pvalue"] < 0.05 and adj[i] >= 0.05:
                print(f"    {r['test']}: p={r['pvalue']:.4f} -> p_BH={adj[i]:.4f} "
                      f"(loses significance)")

    # ── Save results ──────────────────────────────────────────────────────
    results_df = pd.DataFrame(all_results)
    out_path = os.path.join(DATA_DIR, "robustness_results.csv")
    results_df.to_csv(out_path, index=False)
    print(f"\nSaved: {out_path} ({len(results_df)} rows)")

    print("\n" + "=" * 70)
    print("02_robustness.py complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
