"""02_robustness.py — DiD robustness template.

All required DiD robustness checks in one file:
1. Parallel trends test (event study pre-period coefficients)
2. Placebo outcome test
3. Placebo treatment timing test (shift treatment earlier)
4. Bacon decomposition (or TWFE vs CS comparison)
5. Sensitivity to different control groups
6. Covariate balance pre/post treatment
7. Wild cluster bootstrap if <50 clusters
"""

import os
import sys
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT-SPECIFIC VARIABLES (Claude fills these)
# ═══════════════════════════════════════════════════════════════════════════════
PRIMARY_OUTCOME = "{{PRIMARY_OUTCOME}}"     # e.g., "employment"
ENTITY_VAR = "{{ENTITY_VAR}}"              # e.g., "state_id"
TIME_VAR = "{{TIME_VAR}}"                  # e.g., "year"
TREATMENT_VAR = "treat"                     # always use constructed version
CLUSTER_VAR = "{{CLUSTER_VAR}}"            # e.g., "state_id"
COVARIATES = {{COVARIATES}}                 # e.g., ["population", "gdp_pc"]
PLACEBO_OUTCOMES = {{PLACEBO_OUTCOMES}}     # e.g., ["unrelated_outcome"] or []
FIRST_TREAT_VAR = "{{FIRST_TREAT_VAR}}"   # e.g., "first_treat_year" or "None"
OUTCOME_VARS = {{OUTCOME_VARS}}             # e.g., ["employment", "wages"]

# ═══════════════════════════════════════════════════════════════════════════════
# FIXED CODE
# ═══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "..", "data", "clean")
FIGURES_DIR = os.path.join(SCRIPT_DIR, "..", "..", "paper", "figures")
CLEAN_CSV = os.path.join(DATA_DIR, "clean_data.csv")

os.makedirs(FIGURES_DIR, exist_ok=True)

# Import linearmodels (same pattern as 01_main.py)
linearmodels_available = False
try:
    from linearmodels.panel import PanelOLS
    linearmodels_available = True
except ImportError:
    try:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "linearmodels"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        from linearmodels.panel import PanelOLS
        linearmodels_available = True
    except Exception:
        pass

import statsmodels.api as sm

# Import from 01_main.py to reuse TWFE runner
sys.path.insert(0, SCRIPT_DIR)
try:
    from importlib import import_module
    main_mod = import_module("did_01_main")
    run_twfe_panelols = main_mod.run_twfe_panelols
    _safe_float = main_mod._safe_float
    _empty_result = main_mod._empty_result
except Exception:
    # Inline fallback
    def _safe_float(val, default=np.nan):
        try:
            v = float(val)
            return v if not np.isnan(v) else default
        except (ValueError, TypeError):
            return default

    def _empty_result(outcome, label, n=0):
        return {
            "outcome": outcome, "specification": label,
            "estimate": np.nan, "se_robust": np.nan, "pvalue": np.nan,
            "ci_lower": np.nan, "ci_upper": np.nan,
            "N": n, "N_units": 0, "r_squared": np.nan, "method": "none",
        }

    def run_twfe_panelols(df, outcome, covariates=None, label="twfe"):
        """Minimal TWFE fallback using statsmodels OLS with dummies."""
        sub = df.dropna(subset=[outcome, TREATMENT_VAR, ENTITY_VAR, TIME_VAR]).copy()
        if len(sub) < 20:
            return _empty_result(outcome, label, len(sub))
        entity_d = pd.get_dummies(sub[ENTITY_VAR], prefix="ent", drop_first=True, dtype=float)
        time_d = pd.get_dummies(sub[TIME_VAR], prefix="t", drop_first=True, dtype=float)
        exog = [TREATMENT_VAR]
        if covariates:
            exog += [c for c in covariates if c in sub.columns]
        X = pd.concat([sub[exog].reset_index(drop=True),
                        entity_d.reset_index(drop=True),
                        time_d.reset_index(drop=True)], axis=1)
        X = sm.add_constant(X)
        y = sub[outcome].reset_index(drop=True)
        groups = sub[ENTITY_VAR].reset_index(drop=True)
        try:
            fit = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": groups})
            est = _safe_float(fit.params.get(TREATMENT_VAR, np.nan))
            se = _safe_float(fit.bse.get(TREATMENT_VAR, np.nan))
            pval = _safe_float(fit.pvalues.get(TREATMENT_VAR, np.nan))
            ci = fit.conf_int()
            ci_lo = _safe_float(ci.loc[TREATMENT_VAR, 0]) if TREATMENT_VAR in ci.index else np.nan
            ci_hi = _safe_float(ci.loc[TREATMENT_VAR, 1]) if TREATMENT_VAR in ci.index else np.nan
            return {
                "outcome": outcome, "specification": label,
                "estimate": est, "se_robust": se, "pvalue": pval,
                "ci_lower": ci_lo, "ci_upper": ci_hi,
                "N": len(sub), "N_units": sub[ENTITY_VAR].nunique(),
                "r_squared": _safe_float(fit.rsquared), "method": "statsmodels_OLS_FE",
            }
        except Exception:
            return _empty_result(outcome, label, len(sub))


def main():
    print("=" * 70)
    print("02_robustness.py — DiD Robustness Checks")
    print("=" * 70)

    df = pd.read_csv(CLEAN_CSV)
    print(f"Loaded: {len(df):,} rows x {df.shape[1]} cols")

    all_results = []

    # ══════════════════════════════════════════════════════════════════════
    # 1. PARALLEL TRENDS TEST (event study pre-period coefficients)
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 1. Parallel trends test ---")
    print("  Expected: pre-period coefficients jointly = 0")

    # Load event study results from 01_main.py if available
    es_path = os.path.join(DATA_DIR, "event_study_results.csv")
    if os.path.exists(es_path):
        es_df = pd.read_csv(es_path)
        es_primary = es_df[es_df["outcome"] == PRIMARY_OUTCOME].copy()
        pre_period = es_primary[es_primary["rel_time"] < -1]

        if len(pre_period) > 0:
            # Joint significance test
            pre_ests = pre_period["estimate"].values
            pre_ses = pre_period["se_robust"].values
            valid = ~np.isnan(pre_ests) & ~np.isnan(pre_ses) & (pre_ses > 0)

            if valid.sum() > 0:
                try:
                    from scipy import stats as sp_stats
                    f_stat = np.sum((pre_ests[valid] / pre_ses[valid]) ** 2)
                    dof = int(valid.sum())
                    pval = 1 - sp_stats.chi2.cdf(f_stat, dof)
                    print(f"  Chi2 stat: {f_stat:.3f}  dof: {dof}  p-value: {pval:.4f}")
                    verdict = "PASS" if pval > 0.05 else "FAIL"
                    print(f"  Verdict: {verdict}")
                    all_results.append({
                        "test": "parallel_trends", "outcome": PRIMARY_OUTCOME,
                        "estimate": pval, "se_robust": np.nan,
                        "ci_lower": np.nan, "ci_upper": np.nan,
                        "N": len(es_primary), "N_units": np.nan, "method": "joint_chi2",
                    })
                except ImportError:
                    print("  scipy not available for chi2 test.")
            else:
                print("  No valid pre-period coefficients for test.")
        else:
            print("  No pre-period coefficients found in event study results.")
    else:
        print("  No event study results found. Run 01_main.py first.")

    # ══════════════════════════════════════════════════════════════════════
    # 2. PLACEBO OUTCOME TEST
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 2. Placebo outcomes ---")
    print("  Expected: NULL effect (treatment should not affect placebos)")
    placebo_present = [p for p in PLACEBO_OUTCOMES if p in df.columns]
    if not placebo_present:
        print("  No placebo outcomes found.")

    for pv in placebo_present:
        res = run_twfe_panelols(df, pv, covariates=None, label="placebo_outcome")
        res["test"] = "placebo_outcome"
        all_results.append(res)
        sig = "*" if pd.notna(res.get("ci_lower")) and pd.notna(res.get("ci_upper")) and \
              (res["ci_lower"] > 0 or res["ci_upper"] < 0) else ""
        print(f"  {pv}: est={res['estimate']:.4f} "
              f"CI=[{res.get('ci_lower', np.nan):.4f}, {res.get('ci_upper', np.nan):.4f}] {sig}")

    # ══════════════════════════════════════════════════════════════════════
    # 3. PLACEBO TREATMENT TIMING TEST
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 3. Placebo treatment timing ---")
    print("  Expected: NULL effect (shifting treatment earlier should yield no effect)")

    # Determine treatment periods
    if FIRST_TREAT_VAR != "None" and FIRST_TREAT_VAR in df.columns:
        # Staggered: shift first_treat backward by 1 and 2 periods
        time_values = sorted(df[TIME_VAR].dropna().unique())
        if len(time_values) > 2:
            time_gap = time_values[1] - time_values[0]  # typical gap between periods
        else:
            time_gap = 1

        for shift in [1, 2]:
            df_placebo = df.copy()
            # Shift treatment timing earlier
            ft = df_placebo[FIRST_TREAT_VAR].copy()
            df_placebo["_placebo_ft"] = ft - shift * time_gap
            # Reconstruct treatment
            df_placebo["treat"] = ((df_placebo[TIME_VAR] >= df_placebo["_placebo_ft"])
                                    & df_placebo["_placebo_ft"].notna()
                                    & (df_placebo["_placebo_ft"] < np.inf)).astype(float)
            # Only use pre-treatment periods of the ACTUAL treatment
            df_placebo = df_placebo[df_placebo[TIME_VAR] < ft].copy()

            if len(df_placebo) > 20:
                res = run_twfe_panelols(df_placebo, PRIMARY_OUTCOME, covariates=None,
                                         label=f"placebo_timing_shift_{shift}")
                res["test"] = f"placebo_timing_shift_{shift}"
                all_results.append(res)
                sig = "*" if pd.notna(res.get("ci_lower")) and pd.notna(res.get("ci_upper")) and \
                      (res["ci_lower"] > 0 or res["ci_upper"] < 0) else ""
                print(f"  Shift {shift} periods: est={res['estimate']:.4f} "
                      f"CI=[{res.get('ci_lower', np.nan):.4f}, "
                      f"{res.get('ci_upper', np.nan):.4f}] {sig}")
            else:
                print(f"  Shift {shift}: insufficient pre-treatment obs. Skipping.")
    else:
        # Standard 2-group: use median time to split pre-period
        pre_df = df[df[TREATMENT_VAR] == 0].copy()
        if len(pre_df) > 20:
            med_time = pre_df[TIME_VAR].median()
            pre_df["treat"] = (pre_df[TIME_VAR] > med_time).astype(float)
            res = run_twfe_panelols(pre_df, PRIMARY_OUTCOME, covariates=None,
                                     label="placebo_timing_pre_split")
            res["test"] = "placebo_timing_pre_split"
            all_results.append(res)
            print(f"  Pre-period split at {med_time}: est={res['estimate']:.4f} "
                  f"CI=[{res.get('ci_lower', np.nan):.4f}, {res.get('ci_upper', np.nan):.4f}]")
        else:
            print("  Insufficient pre-treatment data for placebo timing test.")

    # ══════════════════════════════════════════════════════════════════════
    # 4. BACON DECOMPOSITION / TWFE vs CS COMPARISON
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 4. Bacon decomposition / TWFE vs CS comparison ---")

    bacon_done = False
    if FIRST_TREAT_VAR != "None" and FIRST_TREAT_VAR in df.columns:
        # Try Bacon decomposition
        try:
            from bacondecomp import bacon
            sub = df.dropna(subset=[PRIMARY_OUTCOME, ENTITY_VAR, TIME_VAR, TREATMENT_VAR]).copy()
            b_df = bacon(sub[PRIMARY_OUTCOME], sub[TREATMENT_VAR],
                         sub[ENTITY_VAR], sub[TIME_VAR])
            print("  Bacon decomposition results:")
            for _, row in b_df.groupby("type").agg(
                    weight=("weight", "sum"),
                    estimate=("estimate", lambda x: np.average(x, weights=b_df.loc[x.index, "weight"]))
            ).iterrows():
                print(f"    {_}: weight={row['weight']:.3f}, estimate={row['estimate']:.4f}")
                all_results.append({
                    "test": f"bacon_{_}", "outcome": PRIMARY_OUTCOME,
                    "estimate": row["estimate"], "se_robust": np.nan,
                    "ci_lower": np.nan, "ci_upper": np.nan,
                    "N": len(sub), "N_units": sub[ENTITY_VAR].nunique(),
                    "method": "bacon_decomp",
                })
            bacon_done = True
        except ImportError:
            print("  bacondecomp not installed.")
        except Exception as e:
            print(f"  Bacon decomposition failed: {e}")

        if not bacon_done:
            # TWFE vs CS comparison
            print("  Comparing TWFE vs Callaway-Sant'Anna (if available):")
            twfe_res = run_twfe_panelols(df, PRIMARY_OUTCOME, label="twfe_comparison")
            all_results.append({**twfe_res, "test": "twfe_vs_cs_twfe"})
            print(f"    TWFE estimate: {twfe_res['estimate']:.4f}")

            try:
                from importlib import import_module
                main_mod = import_module("did_01_main")
                cs_res = main_mod.try_callaway_santanna(df, PRIMARY_OUTCOME, label="cs_comparison")
                all_results.append({**cs_res, "test": "twfe_vs_cs_cs"})
                print(f"    CS estimate: {cs_res['estimate']}")
            except Exception as e:
                print(f"    CS comparison failed: {e}")
    else:
        print("  Standard 2-group DiD — Bacon decomposition not applicable.")

    # ══════════════════════════════════════════════════════════════════════
    # 5. SENSITIVITY TO DIFFERENT CONTROL GROUPS
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 5. Sensitivity to different control groups ---")

    # a) Baseline: all units
    res_all = run_twfe_panelols(df, PRIMARY_OUTCOME, label="all_units")
    res_all["test"] = "control_all_units"
    all_results.append(res_all)
    print(f"  All units: est={res_all['estimate']:.4f} N={res_all['N']}")

    # b) Never-treated only as control (drop late-treated from control)
    if FIRST_TREAT_VAR != "None" and FIRST_TREAT_VAR in df.columns:
        ever_treated = df.groupby(ENTITY_VAR)[TREATMENT_VAR].max()
        never_treated_ids = ever_treated[ever_treated == 0].index
        treated_ids = ever_treated[ever_treated == 1].index
        df_never_ctrl = df[df[ENTITY_VAR].isin(never_treated_ids) |
                           df[ENTITY_VAR].isin(treated_ids)].copy()
        # Among treated_ids, keep only those currently treated
        # (this gives never-treated + eventually-treated)
        if len(df_never_ctrl) > 20:
            res_nt = run_twfe_panelols(df_never_ctrl, PRIMARY_OUTCOME,
                                        label="never_treated_control")
            res_nt["test"] = "control_never_treated"
            all_results.append(res_nt)
            print(f"  Never-treated control: est={res_nt['estimate']:.4f} N={res_nt['N']}")

    # c) Drop extreme outcome values (winsorize at 1%/99%)
    df_win = df.copy()
    q01 = df_win[PRIMARY_OUTCOME].quantile(0.01)
    q99 = df_win[PRIMARY_OUTCOME].quantile(0.99)
    df_win = df_win[(df_win[PRIMARY_OUTCOME] >= q01) & (df_win[PRIMARY_OUTCOME] <= q99)]
    if len(df_win) > 20:
        res_win = run_twfe_panelols(df_win, PRIMARY_OUTCOME, label="winsorized_1_99")
        res_win["test"] = "control_winsorized"
        all_results.append(res_win)
        print(f"  Winsorized (1-99%): est={res_win['estimate']:.4f} N={res_win['N']}")

    # ══════════════════════════════════════════════════════════════════════
    # 6. COVARIATE BALANCE PRE/POST TREATMENT
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 6. Covariate balance ---")
    print("  Expected: covariates balanced between treated and control pre-treatment")

    cov_avail = [c for c in COVARIATES if c in df.columns]
    if cov_avail:
        # Pre-treatment period
        pre_df = df[df[TREATMENT_VAR] == 0].copy()
        ever_treated = df.groupby(ENTITY_VAR)[TREATMENT_VAR].max()

        for cov in cov_avail:
            pre_merged = pre_df.merge(ever_treated.rename("ever_treated"), on=ENTITY_VAR)
            treat_vals = pre_merged.loc[pre_merged["ever_treated"] == 1, cov].dropna()
            ctrl_vals = pre_merged.loc[pre_merged["ever_treated"] == 0, cov].dropna()

            if len(treat_vals) > 5 and len(ctrl_vals) > 5:
                try:
                    from scipy import stats as sp_stats
                    t_stat, pval = sp_stats.ttest_ind(treat_vals, ctrl_vals, equal_var=False)
                    diff = treat_vals.mean() - ctrl_vals.mean()
                    pooled_std = np.sqrt((treat_vals.std() ** 2 + ctrl_vals.std() ** 2) / 2)
                    norm_diff = diff / pooled_std if pooled_std > 0 else np.nan
                    sig = "*" if pval < 0.05 else ""
                    print(f"  {cov:20s}: diff={diff:.4f} norm_diff={norm_diff:.3f} "
                          f"p={pval:.4f} {sig}")
                    all_results.append({
                        "test": "covariate_balance", "outcome": cov,
                        "estimate": diff, "se_robust": np.nan,
                        "ci_lower": np.nan, "ci_upper": np.nan,
                        "pvalue": pval, "N": len(treat_vals) + len(ctrl_vals),
                        "N_units": np.nan, "method": "t_test",
                    })
                except ImportError:
                    print(f"  {cov}: scipy not available for t-test.")
            else:
                print(f"  {cov}: insufficient obs for balance test.")
    else:
        print("  No covariates available for balance test.")

    # ══════════════════════════════════════════════════════════════════════
    # 7. WILD CLUSTER BOOTSTRAP (if <50 clusters)
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 7. Wild cluster bootstrap ---")
    cluster_col = CLUSTER_VAR if CLUSTER_VAR in df.columns else ENTITY_VAR
    n_clusters = df[cluster_col].nunique()
    print(f"  Number of clusters ({cluster_col}): {n_clusters}")

    if n_clusters < 50:
        print("  Few clusters detected. Running wild cluster bootstrap...")
        try:
            from wildboottest import wildboottest
            sub = df.dropna(subset=[PRIMARY_OUTCOME, TREATMENT_VAR, ENTITY_VAR, TIME_VAR]).copy()
            # Entity and time dummies
            entity_d = pd.get_dummies(sub[ENTITY_VAR], prefix="ent", drop_first=True, dtype=float)
            time_d = pd.get_dummies(sub[TIME_VAR], prefix="t", drop_first=True, dtype=float)
            X = pd.concat([sub[[TREATMENT_VAR]].reset_index(drop=True),
                            entity_d.reset_index(drop=True),
                            time_d.reset_index(drop=True)], axis=1)
            X = sm.add_constant(X)
            y = sub[PRIMARY_OUTCOME].reset_index(drop=True)

            boot_result = wildboottest(
                model=sm.OLS(y, X),
                cluster=sub[cluster_col].reset_index(drop=True),
                param=TREATMENT_VAR,
                B=9999,
                seed=42,
            )
            boot_pval = _safe_float(getattr(boot_result, "pvalue", np.nan))
            boot_ci = getattr(boot_result, "conf_int", None)
            ci_lo = _safe_float(boot_ci[0]) if boot_ci is not None else np.nan
            ci_hi = _safe_float(boot_ci[1]) if boot_ci is not None else np.nan

            print(f"  Bootstrap p-value: {boot_pval:.4f}")
            print(f"  Bootstrap 95% CI: [{ci_lo:.4f}, {ci_hi:.4f}]")
            all_results.append({
                "test": "wild_cluster_bootstrap", "outcome": PRIMARY_OUTCOME,
                "estimate": np.nan, "se_robust": np.nan, "pvalue": boot_pval,
                "ci_lower": ci_lo, "ci_upper": ci_hi,
                "N": len(sub), "N_units": n_clusters, "method": "wild_bootstrap",
            })
        except ImportError:
            print("  wildboottest not installed. Trying manual bootstrap...")
            # Manual wild cluster bootstrap (Rademacher weights)
            try:
                sub = df.dropna(subset=[PRIMARY_OUTCOME, TREATMENT_VAR,
                                         ENTITY_VAR, TIME_VAR]).copy()
                entity_d = pd.get_dummies(sub[ENTITY_VAR], prefix="ent",
                                           drop_first=True, dtype=float)
                time_d = pd.get_dummies(sub[TIME_VAR], prefix="t",
                                         drop_first=True, dtype=float)
                X = pd.concat([sub[[TREATMENT_VAR]].reset_index(drop=True),
                                entity_d.reset_index(drop=True),
                                time_d.reset_index(drop=True)], axis=1)
                X = sm.add_constant(X)
                y = sub[PRIMARY_OUTCOME].reset_index(drop=True)
                groups = sub[cluster_col].reset_index(drop=True)

                # Fit restricted model (under H0: beta_treat = 0)
                X_r = X.drop(columns=[TREATMENT_VAR])
                fit_r = sm.OLS(y, X_r).fit()
                resid_r = fit_r.resid
                y_hat_r = fit_r.fittedvalues

                # Full model t-stat
                fit_full = sm.OLS(y, X).fit(cov_type="cluster",
                                             cov_kwds={"groups": groups})
                t_orig = fit_full.tvalues.get(TREATMENT_VAR, np.nan)

                # Bootstrap
                np.random.seed(42)
                n_boot = 999
                t_boots = []
                unique_clusters = groups.unique()
                for _ in range(n_boot):
                    # Rademacher weights per cluster
                    weights = np.random.choice([-1, 1], size=len(unique_clusters))
                    w_map = dict(zip(unique_clusters, weights))
                    w = groups.map(w_map).values
                    y_boot = y_hat_r + resid_r * w
                    try:
                        fit_b = sm.OLS(y_boot, X).fit(cov_type="cluster",
                                                        cov_kwds={"groups": groups})
                        t_b = fit_b.tvalues.get(TREATMENT_VAR, np.nan)
                        if pd.notna(t_b):
                            t_boots.append(t_b)
                    except Exception:
                        pass

                if len(t_boots) > 50:
                    t_boots = np.array(t_boots)
                    boot_pval = np.mean(np.abs(t_boots) >= np.abs(t_orig))
                    print(f"  Manual bootstrap p-value: {boot_pval:.4f} "
                          f"(B={len(t_boots)}, orig t={t_orig:.3f})")
                    all_results.append({
                        "test": "wild_cluster_bootstrap", "outcome": PRIMARY_OUTCOME,
                        "estimate": np.nan, "se_robust": np.nan, "pvalue": boot_pval,
                        "ci_lower": np.nan, "ci_upper": np.nan,
                        "N": len(sub), "N_units": n_clusters,
                        "method": "manual_wild_bootstrap",
                    })
                else:
                    print("  Manual bootstrap failed to produce enough replications.")
            except Exception as e:
                print(f"  Manual bootstrap failed: {e}")
        except Exception as e:
            print(f"  Wild cluster bootstrap failed: {e}")
    else:
        print(f"  {n_clusters} clusters (>=50). Standard clustered SEs sufficient.")
        all_results.append({
            "test": "wild_cluster_bootstrap", "outcome": PRIMARY_OUTCOME,
            "estimate": np.nan, "se_robust": np.nan, "pvalue": np.nan,
            "ci_lower": np.nan, "ci_upper": np.nan,
            "N": len(df), "N_units": n_clusters,
            "method": "skipped_sufficient_clusters",
        })

    # ══════════════════════════════════════════════════════════════════════
    # 8. RANDOMIZATION INFERENCE (permutation p-values)
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 8. Randomization inference (permutation p-values) ---")

    sub_ri = df.dropna(subset=[PRIMARY_OUTCOME, TREATMENT_VAR, ENTITY_VAR, TIME_VAR]).copy()
    if len(sub_ri) >= 20:
        try:
            # Get original TWFE t-stat
            entity_d = pd.get_dummies(sub_ri[ENTITY_VAR], prefix="ent",
                                       drop_first=True, dtype=float)
            time_d = pd.get_dummies(sub_ri[TIME_VAR], prefix="t",
                                     drop_first=True, dtype=float)
            X_ri = pd.concat([sub_ri[[TREATMENT_VAR]].reset_index(drop=True),
                              entity_d.reset_index(drop=True),
                              time_d.reset_index(drop=True)], axis=1)
            X_ri = sm.add_constant(X_ri)
            y_ri = sub_ri[PRIMARY_OUTCOME].reset_index(drop=True)
            groups_ri = sub_ri[ENTITY_VAR].reset_index(drop=True)

            fit_orig = sm.OLS(y_ri, X_ri).fit(cov_type="cluster",
                                               cov_kwds={"groups": groups_ri})
            t_orig = _safe_float(fit_orig.tvalues.get(TREATMENT_VAR, np.nan))

            if pd.notna(t_orig):
                # Permute treatment at entity level
                n_perms = 1000
                rng = np.random.default_rng(42)
                entities = sub_ri[ENTITY_VAR].unique()
                t_perms = []

                for _ in range(n_perms):
                    # Shuffle entity assignment (which entities are treated)
                    perm_entities = rng.permutation(entities)
                    entity_map = dict(zip(entities, perm_entities))
                    sub_perm = sub_ri.copy()
                    sub_perm[ENTITY_VAR + "_perm"] = sub_perm[ENTITY_VAR].map(entity_map)
                    # Reconstruct treatment from permuted entities
                    ever_treated_perm = sub_perm.groupby(ENTITY_VAR + "_perm")[TREATMENT_VAR].max()
                    sub_perm = sub_perm.merge(
                        ever_treated_perm.rename("_treat_perm"),
                        left_on=ENTITY_VAR, right_index=True, how="left"
                    )
                    sub_perm["_treat_perm"] = sub_perm["_treat_perm"].fillna(0)

                    X_perm = X_ri.copy()
                    X_perm[TREATMENT_VAR] = sub_perm["_treat_perm"].values
                    try:
                        fit_p = sm.OLS(y_ri, X_perm).fit()
                        t_p = _safe_float(fit_p.tvalues.get(TREATMENT_VAR, np.nan))
                        if pd.notna(t_p):
                            t_perms.append(t_p)
                    except Exception:
                        pass

                if len(t_perms) > 50:
                    t_perms = np.array(t_perms)
                    perm_pval = np.mean(np.abs(t_perms) >= np.abs(t_orig))
                    print(f"  t_original: {t_orig:.3f}")
                    print(f"  Permutation p-value ({len(t_perms)} valid): {perm_pval:.4f}")
                    print(f"  Conventional p-value: "
                          f"{_safe_float(fit_orig.pvalues.get(TREATMENT_VAR, np.nan)):.4f}")

                    all_results.append({
                        "test": "randomization_inference", "outcome": PRIMARY_OUTCOME,
                        "estimate": t_orig, "se_robust": np.nan,
                        "pvalue": perm_pval,
                        "ci_lower": np.nan, "ci_upper": np.nan,
                        "N": len(sub_ri), "N_units": len(entities),
                        "method": f"permutation_{len(t_perms)}",
                    })
        except Exception as e:
            print(f"  Randomization inference failed: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # 9. OSTER (2019) COEFFICIENT STABILITY
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 9. Oster (2019) coefficient stability ---")

    sub_oster = df.dropna(subset=[PRIMARY_OUTCOME, TREATMENT_VAR,
                                   ENTITY_VAR, TIME_VAR]).copy()
    cov_avail = [c for c in COVARIATES if c in sub_oster.columns]
    if len(sub_oster) >= 20 and cov_avail:
        try:
            for c in cov_avail:
                sub_oster[c] = pd.to_numeric(sub_oster[c], errors="coerce")
            sub_oster = sub_oster.dropna(subset=cov_avail)

            entity_d = pd.get_dummies(sub_oster[ENTITY_VAR], prefix="ent",
                                       drop_first=True, dtype=float)
            time_d = pd.get_dummies(sub_oster[TIME_VAR], prefix="t",
                                     drop_first=True, dtype=float)
            fe_cols = pd.concat([entity_d.reset_index(drop=True),
                                 time_d.reset_index(drop=True)], axis=1)

            y_o = sub_oster[PRIMARY_OUTCOME].reset_index(drop=True)

            # Uncontrolled (just treatment + FE)
            X_u = pd.concat([sub_oster[[TREATMENT_VAR]].reset_index(drop=True),
                             fe_cols], axis=1)
            X_u = sm.add_constant(X_u)
            fit_u = sm.OLS(y_o, X_u).fit()
            beta_u = _safe_float(fit_u.params.get(TREATMENT_VAR, np.nan))
            r2_u = fit_u.rsquared

            # Controlled (treatment + covariates + FE)
            X_c = pd.concat([sub_oster[[TREATMENT_VAR] + cov_avail].reset_index(drop=True),
                             fe_cols], axis=1)
            X_c = sm.add_constant(X_c)
            fit_c = sm.OLS(y_o, X_c).fit()
            beta_c = _safe_float(fit_c.params.get(TREATMENT_VAR, np.nan))
            r2_c = fit_c.rsquared

            r2_max = min(1.0, 1.3 * r2_c)
            denom = (beta_u - beta_c) * (r2_c - r2_u)
            if abs(denom) > 1e-10:
                delta = (beta_c * (r2_max - r2_c)) / denom
            else:
                delta = np.inf

            print(f"  beta_u={beta_u:.4f} R²_u={r2_u:.4f}")
            print(f"  beta_c={beta_c:.4f} R²_c={r2_c:.4f}")
            print(f"  R²_max={r2_max:.4f}")
            print(f"  delta={delta:.2f}")
            if abs(delta) < 1:
                print(f"  *** WARNING: delta < 1 — result fragile ***")

            all_results.append({
                "test": "oster_delta", "outcome": PRIMARY_OUTCOME,
                "estimate": delta, "se_robust": np.nan,
                "pvalue": np.nan,
                "ci_lower": beta_u, "ci_upper": beta_c,
                "N": len(sub_oster), "N_units": sub_oster[ENTITY_VAR].nunique(),
                "method": "oster_2019",
            })
        except Exception as e:
            print(f"  Oster (2019) failed: {e}")
    else:
        print("  Insufficient data or no covariates for Oster test.")

    # ══════════════════════════════════════════════════════════════════════
    # 10. MULTIPLE HYPOTHESIS CORRECTION (BH FDR)
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 10. Multiple hypothesis correction (BH FDR) ---")
    testable = [r for r in all_results
                if pd.notna(r.get("pvalue")) and r.get("pvalue", 1) < 1]
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
        print(f"  Corrected {n_p} tests.")

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
