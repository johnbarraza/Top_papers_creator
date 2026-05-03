"""02_robustness.py — RCT robustness template.

All required RCT robustness checks in one file:
1. Randomization balance: regress each arm on all covariates, report F-stat
2. Differential attrition test per arm
3. Lee (2009) trimming bounds per arm (with CORRECT monotonicity check)
4. Placebo outcome test
5. Logit marginal effects vs LPM comparison
6. Compliance/take-up rates if take-up variables exist
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
PRIMARY_OUTCOME = "{{PRIMARY_OUTCOME}}"       # e.g., "consumption"
OUTCOME_VARS = {{OUTCOME_VARS}}               # e.g., ["consumption", "income", "health"]
TREATMENT_VAR = "{{TREATMENT_VAR}}"           # e.g., "treatment"
TREATMENT_ARMS = {{TREATMENT_ARMS}}           # e.g., {"Control": 0, "Cash": 1, "In-kind": 2}
CLUSTER_VAR = "{{CLUSTER_VAR}}"               # e.g., "village_id" or None
COVARIATES = {{COVARIATES}}                   # e.g., ["age", "female", "baseline_income"]
PLACEBO_OUTCOMES = {{PLACEBO_OUTCOMES}}       # e.g., ["baseline_consumption"] or []
BASELINE_OUTCOME = "{{BASELINE_OUTCOME}}"     # e.g., "baseline_consumption" or "None"

# ═══════════════════════════════════════════════════════════════════════════════
# FIXED CODE
# ═══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "..", "data", "clean")
CLEAN_CSV = os.path.join(DATA_DIR, "clean_data.csv")

import statsmodels.api as sm
from scipy import stats as scipy_stats


def _get_control_arm():
    """Identify control arm value."""
    for name, val in TREATMENT_ARMS.items():
        if name.lower() in ("control", "placebo", "comparison", "0"):
            return val
    return min(TREATMENT_ARMS.values())


def _get_treat_arms():
    """Return dict of treatment arms (excluding control)."""
    ctrl_val = _get_control_arm()
    return {k: v for k, v in TREATMENT_ARMS.items() if v != ctrl_val}


def main():
    print("=" * 70)
    print("02_robustness.py — RCT Robustness Checks")
    print("=" * 70)

    df = pd.read_csv(CLEAN_CSV)
    print(f"Loaded: {len(df):,} rows x {df.shape[1]} cols")

    ctrl_val = _get_control_arm()
    treat_arms = _get_treat_arms()
    all_results = []

    # ══════════════════════════════════════════════════════════════════════
    # 1. RANDOMIZATION BALANCE: regress each arm on all covariates
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 1. Randomization balance (F-test: covariates predict arm) ---")
    print("  Expected: F-stat insignificant (covariates don't predict treatment)")

    cov_avail = [c for c in COVARIATES if c in df.columns]
    if cov_avail:
        for arm_name, arm_val in treat_arms.items():
            safe = arm_name.replace(" ", "_").replace("-", "_").lower()
            sub = df.dropna(subset=cov_avail + [TREATMENT_VAR]).copy()
            # Restrict to this arm vs control
            sub = sub[sub[TREATMENT_VAR].isin([ctrl_val, arm_val])].copy()
            sub["_arm_dum"] = (sub[TREATMENT_VAR] == arm_val).astype(float)

            for c in cov_avail:
                sub[c] = pd.to_numeric(sub[c], errors="coerce")
            sub = sub.dropna(subset=cov_avail)

            if len(sub) < len(cov_avail) + 5:
                print(f"  {arm_name}: insufficient obs. Skipping.")
                continue

            Y = sub["_arm_dum"].values
            X = sm.add_constant(sub[cov_avail].values)

            try:
                model = sm.OLS(Y, X).fit(cov_type="HC2")
                fstat = model.fvalue
                fpval = model.f_pvalue
                sig = "***" if fpval < 0.01 else ("**" if fpval < 0.05 else "")
                print(f"  {arm_name:20s}: F({len(cov_avail)},{len(sub)-len(cov_avail)-1}) "
                      f"= {fstat:.3f}  p = {fpval:.4f} {sig}")

                all_results.append({
                    "test": "balance_ftest", "arm": safe,
                    "outcome": "all_covariates",
                    "estimate": fstat, "se_robust": np.nan,
                    "pvalue": fpval, "ci_lower": np.nan, "ci_upper": np.nan,
                    "N": len(sub), "method": "OLS_F_test",
                })
            except Exception as e:
                print(f"  {arm_name}: F-test failed ({e})")

        # Also test individual covariate balance
        print("\n  Individual covariate balance (arm vs control):")
        for cov in cov_avail:
            for arm_name, arm_val in treat_arms.items():
                safe = arm_name.replace(" ", "_").replace("-", "_").lower()
                sub = df.dropna(subset=[cov, TREATMENT_VAR]).copy()
                sub = sub[sub[TREATMENT_VAR].isin([ctrl_val, arm_val])].copy()
                sub["_arm_dum"] = (sub[TREATMENT_VAR] == arm_val).astype(float)
                sub[cov] = pd.to_numeric(sub[cov], errors="coerce")
                sub = sub.dropna(subset=[cov])

                ctrl_vals = sub.loc[sub["_arm_dum"] == 0, cov]
                treat_vals = sub.loc[sub["_arm_dum"] == 1, cov]
                if len(ctrl_vals) < 5 or len(treat_vals) < 5:
                    continue

                tstat, pval = scipy_stats.ttest_ind(treat_vals, ctrl_vals,
                                                     equal_var=False)
                diff = treat_vals.mean() - ctrl_vals.mean()
                flag = " *" if pval < 0.05 else ""
                print(f"    {cov:25s} x {arm_name:15s}: diff={diff:.4f} "
                      f"t={tstat:.3f} p={pval:.4f}{flag}")
    else:
        print("  No covariates available for balance test.")

    # ══════════════════════════════════════════════════════════════════════
    # 2. DIFFERENTIAL ATTRITION TEST PER ARM
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 2. Differential attrition test ---")
    print("  Expected: treatment does not predict attrition")

    if PRIMARY_OUTCOME in df.columns:
        df["_observed"] = df[PRIMARY_OUTCOME].notna().astype(float)
        overall_attrition = 1 - df["_observed"].mean()
        print(f"  Overall attrition rate: {100*overall_attrition:.1f}%")

        for arm_name, arm_val in treat_arms.items():
            safe = arm_name.replace(" ", "_").replace("-", "_").lower()
            sub = df[df[TREATMENT_VAR].isin([ctrl_val, arm_val])].copy()
            sub["_arm_dum"] = (sub[TREATMENT_VAR] == arm_val).astype(float)

            ctrl_attr = 1 - sub.loc[sub["_arm_dum"] == 0, "_observed"].mean()
            treat_attr = 1 - sub.loc[sub["_arm_dum"] == 1, "_observed"].mean()
            diff_attr = treat_attr - ctrl_attr

            # Regression test
            Y = sub["_observed"].values
            X = sm.add_constant(sub["_arm_dum"].values)

            if CLUSTER_VAR and CLUSTER_VAR in sub.columns:
                groups = sub[CLUSTER_VAR].values
                try:
                    model = sm.OLS(Y, X).fit(cov_type="cluster",
                                              cov_kwds={"groups": groups})
                except Exception:
                    model = sm.OLS(Y, X).fit(cov_type="HC2")
            else:
                model = sm.OLS(Y, X).fit(cov_type="HC2")

            pval = model.pvalues[1]
            sig = " *DIFFERENTIAL*" if pval < 0.05 else ""
            print(f"  {arm_name:20s}: ctrl={100*ctrl_attr:.1f}%  "
                  f"treat={100*treat_attr:.1f}%  diff={100*diff_attr:.1f}pp  "
                  f"p={pval:.4f}{sig}")

            all_results.append({
                "test": "attrition", "arm": safe,
                "outcome": PRIMARY_OUTCOME,
                "estimate": diff_attr, "se_robust": model.bse[1],
                "pvalue": pval,
                "ci_lower": model.conf_int()[1][0],
                "ci_upper": model.conf_int()[1][1],
                "N": len(sub), "method": "OLS_attrition",
            })
    else:
        print(f"  Primary outcome '{PRIMARY_OUTCOME}' not in data. Skipping.")

    # ══════════════════════════════════════════════════════════════════════
    # 3. LEE (2009) TRIMMING BOUNDS PER ARM
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 3. Lee (2009) trimming bounds ---")
    print("  Bounds under worst-case selective attrition")

    if PRIMARY_OUTCOME in df.columns:
        for arm_name, arm_val in treat_arms.items():
            safe = arm_name.replace(" ", "_").replace("-", "_").lower()
            sub = df[df[TREATMENT_VAR].isin([ctrl_val, arm_val])].copy()
            sub["_arm_dum"] = (sub[TREATMENT_VAR] == arm_val).astype(float)

            # Attrition rates
            ctrl_obs_rate = sub.loc[sub["_arm_dum"] == 0, PRIMARY_OUTCOME].notna().mean()
            treat_obs_rate = sub.loc[sub["_arm_dum"] == 1, PRIMARY_OUTCOME].notna().mean()

            # CORRECT monotonicity check: determine which group to trim
            # Trim the group with HIGHER observation rate to match the lower rate
            if abs(ctrl_obs_rate - treat_obs_rate) < 0.001:
                print(f"  {arm_name}: attrition rates nearly equal. "
                      f"Bounds = point estimate.")
                # Just compute naive difference
                sub_complete = sub.dropna(subset=[PRIMARY_OUTCOME])
                ctrl_mean = sub_complete.loc[sub_complete["_arm_dum"] == 0,
                                              PRIMARY_OUTCOME].mean()
                treat_mean = sub_complete.loc[sub_complete["_arm_dum"] == 1,
                                               PRIMARY_OUTCOME].mean()
                naive_diff = treat_mean - ctrl_mean
                all_results.append({
                    "test": "lee_bounds", "arm": safe,
                    "outcome": PRIMARY_OUTCOME,
                    "estimate": naive_diff,
                    "se_robust": np.nan,
                    "pvalue": np.nan,
                    "ci_lower": naive_diff,
                    "ci_upper": naive_diff,
                    "N": len(sub_complete),
                    "method": "lee_bounds_equal_attrition",
                })
                continue

            # Determine trimming proportion and which group to trim
            if treat_obs_rate > ctrl_obs_rate:
                # More observed in treated -> trim treated from top/bottom
                trim_group = 1
                trim_pct = 1 - ctrl_obs_rate / treat_obs_rate
            else:
                # More observed in control -> trim control from top/bottom
                # This can happen if attrition variable is "inverted"
                trim_group = 0
                trim_pct = 1 - treat_obs_rate / ctrl_obs_rate
                print(f"  {arm_name}: NOTE - higher attrition in treated. "
                      f"Trimming control group.")

            sub_complete = sub.dropna(subset=[PRIMARY_OUTCOME])
            group_to_trim = sub_complete[sub_complete["_arm_dum"] == trim_group]
            other_group = sub_complete[sub_complete["_arm_dum"] == (1 - trim_group)]

            y_trim = group_to_trim[PRIMARY_OUTCOME].sort_values()
            n_trim = int(np.ceil(len(y_trim) * trim_pct))

            if n_trim >= len(y_trim) or n_trim < 1:
                print(f"  {arm_name}: trimming {n_trim}/{len(y_trim)} -- too extreme. Skipping.")
                continue

            # Upper bound: trim from bottom (remove lowest outcomes)
            y_upper = y_trim.iloc[n_trim:]
            # Lower bound: trim from top (remove highest outcomes)
            y_lower = y_trim.iloc[:len(y_trim) - n_trim]

            other_mean = other_group[PRIMARY_OUTCOME].mean()

            if trim_group == 1:
                # Trimmed treated vs full control
                upper_bound = y_upper.mean() - other_mean
                lower_bound = y_lower.mean() - other_mean
            else:
                # Full treated vs trimmed control
                treat_mean = sub_complete.loc[sub_complete["_arm_dum"] == 1,
                                               PRIMARY_OUTCOME].mean()
                upper_bound = treat_mean - y_lower.mean()  # subtract smaller control
                lower_bound = treat_mean - y_upper.mean()  # subtract larger control

            # Ensure lower <= upper
            lb = min(lower_bound, upper_bound)
            ub = max(lower_bound, upper_bound)

            print(f"  {arm_name}: trim_pct={100*trim_pct:.1f}%  "
                  f"bounds=[{lb:.4f}, {ub:.4f}]  "
                  f"N_trimmed={n_trim}")

            naive_diff = (sub_complete.loc[sub_complete["_arm_dum"] == 1,
                                           PRIMARY_OUTCOME].mean() -
                         sub_complete.loc[sub_complete["_arm_dum"] == 0,
                                           PRIMARY_OUTCOME].mean())

            all_results.append({
                "test": "lee_bounds", "arm": safe,
                "outcome": PRIMARY_OUTCOME,
                "estimate": naive_diff,
                "se_robust": np.nan,
                "pvalue": np.nan,
                "ci_lower": lb,
                "ci_upper": ub,
                "N": len(sub_complete),
                "method": f"lee_bounds_trim_{100*trim_pct:.0f}pct",
            })
    else:
        print(f"  Primary outcome '{PRIMARY_OUTCOME}' not in data. Skipping.")

    # ══════════════════════════════════════════════════════════════════════
    # 4. PLACEBO OUTCOME TEST
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 4. Placebo outcome test ---")
    print("  Expected: NULL effect on baseline/placebo outcomes")

    placebo_present = [p for p in PLACEBO_OUTCOMES if p in df.columns]
    if not placebo_present:
        print("  No placebo outcomes found in data.")

    for pvar in placebo_present:
        for arm_name, arm_val in treat_arms.items():
            safe = arm_name.replace(" ", "_").replace("-", "_").lower()
            sub = df[df[TREATMENT_VAR].isin([ctrl_val, arm_val])].copy()
            sub = sub.dropna(subset=[pvar]).copy()
            sub["_arm_dum"] = (sub[TREATMENT_VAR] == arm_val).astype(float)

            # FIX: Coerce Y to numeric float64 to avoid ArrowStringArray /
            # Categorical dtype errors in statsmodels. Skip placebo if it
            # cannot be coerced (purely categorical/string outcomes are
            # incompatible with OLS placebo tests).
            y_raw = sub[pvar]
            if hasattr(y_raw, "cat"):
                y_raw = pd.to_numeric(y_raw.cat.codes, errors="coerce")
            else:
                y_raw = pd.to_numeric(y_raw, errors="coerce")
            mask = y_raw.notna()
            if mask.sum() < 10:
                print(f"  {pvar} x {arm_name}: skipped (non-numeric or insufficient data)")
                continue
            sub = sub.loc[mask].copy()
            Y = y_raw.loc[mask].astype(float).values
            X = sm.add_constant(sub["_arm_dum"].astype(float).values)

            if CLUSTER_VAR and CLUSTER_VAR in sub.columns:
                groups = sub[CLUSTER_VAR].values
                try:
                    model = sm.OLS(Y, X).fit(cov_type="cluster",
                                              cov_kwds={"groups": groups})
                except Exception:
                    model = sm.OLS(Y, X).fit(cov_type="HC2")
            else:
                model = sm.OLS(Y, X).fit(cov_type="HC2")

            est = model.params[1]
            se = model.bse[1]
            pval = model.pvalues[1]
            ci = model.conf_int()[1]
            sig = " *SIGNIFICANT*" if pval < 0.05 else ""
            print(f"  {pvar} x {arm_name}: est={est:.4f} SE={se:.4f} "
                  f"p={pval:.4f}{sig}")

            all_results.append({
                "test": "placebo", "arm": safe,
                "outcome": pvar,
                "estimate": est, "se_robust": se,
                "pvalue": pval,
                "ci_lower": ci[0], "ci_upper": ci[1],
                "N": len(sub), "method": "OLS_placebo",
            })

    # ══════════════════════════════════════════════════════════════════════
    # 5. LOGIT MARGINAL EFFECTS vs LPM COMPARISON
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 5. Logit marginal effects vs LPM ---")
    print("  (Only for binary outcomes)")

    if PRIMARY_OUTCOME in df.columns:
        y_vals = df[PRIMARY_OUTCOME].dropna().unique()
        is_binary = set(y_vals).issubset({0, 1, 0.0, 1.0})

        if is_binary:
            for arm_name, arm_val in treat_arms.items():
                safe = arm_name.replace(" ", "_").replace("-", "_").lower()
                sub = df[df[TREATMENT_VAR].isin([ctrl_val, arm_val])].copy()
                sub = sub.dropna(subset=[PRIMARY_OUTCOME]).copy()
                sub["_arm_dum"] = (sub[TREATMENT_VAR] == arm_val).astype(float)

                Y = sub[PRIMARY_OUTCOME].values
                X = sm.add_constant(sub["_arm_dum"].values)

                # LPM
                lpm = sm.OLS(Y, X).fit(cov_type="HC2")
                lpm_est = lpm.params[1]
                lpm_se = lpm.bse[1]

                # Logit marginal effects
                try:
                    logit_mod = sm.Logit(Y, X).fit(disp=0)
                    mfx = logit_mod.get_margeff()
                    logit_est = mfx.margeff[0]
                    logit_se = mfx.margeff_se[0]
                    logit_pval = mfx.pvalues[0]
                except Exception:
                    logit_est = np.nan
                    logit_se = np.nan
                    logit_pval = np.nan

                diff = abs(lpm_est - logit_est) if not np.isnan(logit_est) else np.nan
                print(f"  {arm_name}: LPM={lpm_est:.4f}({lpm_se:.4f})  "
                      f"Logit_MFX={logit_est:.4f}({logit_se:.4f})  "
                      f"|diff|={diff:.4f}" if not np.isnan(diff) else
                      f"  {arm_name}: LPM={lpm_est:.4f}({lpm_se:.4f})  Logit failed")

                all_results.append({
                    "test": "logit_vs_lpm", "arm": safe,
                    "outcome": PRIMARY_OUTCOME,
                    "estimate": logit_est if not np.isnan(logit_est) else lpm_est,
                    "se_robust": logit_se if not np.isnan(logit_se) else lpm_se,
                    "pvalue": logit_pval if not np.isnan(logit_pval) else lpm.pvalues[1],
                    "ci_lower": lpm_est,  # store LPM for comparison
                    "ci_upper": logit_est if not np.isnan(logit_est) else lpm_est,
                    "N": len(sub),
                    "method": "logit_marginal_effects",
                })
        else:
            print(f"  {PRIMARY_OUTCOME} is not binary. Skipping logit comparison.")
    else:
        print(f"  Primary outcome not in data. Skipping.")

    # ══════════════════════════════════════════════════════════════════════
    # 6. COMPLIANCE / TAKE-UP RATES
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 6. Compliance / take-up rates ---")
    # Look for columns that might indicate take-up
    takeup_candidates = [c for c in df.columns
                         if any(kw in c.lower() for kw in
                                ["takeup", "take_up", "comply", "compliance",
                                 "received", "participated", "actual_treat"])]

    if takeup_candidates:
        for tvar in takeup_candidates:
            print(f"\n  Take-up variable: {tvar}")
            for arm_name, arm_val in TREATMENT_ARMS.items():
                arm_data = df[df[TREATMENT_VAR] == arm_val]
                if tvar in arm_data.columns:
                    rate = arm_data[tvar].mean()
                    n = arm_data[tvar].notna().sum()
                    rate_str = f"{100*rate:.1f}%" if not np.isnan(rate) else "---"
                    print(f"    {arm_name:20s}: {rate_str} (N={n:,})")
    else:
        print("  No take-up/compliance variables detected.")

    # ══════════════════════════════════════════════════════════════════════
    # 7. QUANTILE TREATMENT EFFECTS
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 7. Quantile treatment effects ---")

    if PRIMARY_OUTCOME in df.columns:
        quantiles = [0.10, 0.25, 0.50, 0.75, 0.90]
        for arm_name, arm_val in treat_arms.items():
            safe = arm_name.replace(" ", "_").replace("-", "_").lower()
            sub = df[df[TREATMENT_VAR].isin([ctrl_val, arm_val])].copy()
            sub = sub.dropna(subset=[PRIMARY_OUTCOME]).copy()
            sub["_arm_dum"] = (sub[TREATMENT_VAR] == arm_val).astype(float)

            Y = sub[PRIMARY_OUTCOME].values
            X = sm.add_constant(sub["_arm_dum"].values)

            print(f"  {arm_name}:")
            for q in quantiles:
                try:
                    qr = sm.QuantReg(Y, X).fit(q=q, max_iter=1000)
                    est = qr.params[1]
                    se = qr.bse[1]
                    pval = qr.pvalues[1]
                    sig = "*" if pval < 0.10 else ""
                    print(f"    Q{int(q*100):02d}: est={est:.4f}  SE={se:.4f}  "
                          f"p={pval:.4f} {sig}")

                    all_results.append({
                        "test": f"qte_q{int(q*100):02d}", "arm": safe,
                        "outcome": PRIMARY_OUTCOME,
                        "estimate": est, "se_robust": se,
                        "pvalue": pval,
                        "ci_lower": est - 1.96 * se,
                        "ci_upper": est + 1.96 * se,
                        "N": len(sub),
                        "method": f"quantile_reg_q{int(q*100):02d}",
                    })
                except Exception:
                    pass

    # ══════════════════════════════════════════════════════════════════════
    # 8. MISSING DATA PATTERN ANALYSIS
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- 8. Missing data pattern analysis ---")

    if PRIMARY_OUTCOME in df.columns:
        # Overall missingness
        all_vars = [PRIMARY_OUTCOME] + [c for c in COVARIATES if c in df.columns]
        print("  Variable missingness:")
        for var in all_vars:
            n_miss = df[var].isna().sum()
            pct = 100 * n_miss / len(df)
            flag = " <-- HIGH" if pct > 10 else ""
            print(f"    {var:30s}: {n_miss:6,} ({pct:.1f}%){flag}")

        # Missingness by arm
        outcome_miss_pct = 100 * df[PRIMARY_OUTCOME].isna().sum() / len(df)
        if outcome_miss_pct > 5:
            print(f"\n  Outcome missingness > 5% ({outcome_miss_pct:.1f}%). "
                  f"Lee bounds applied in Section 3.")

            # Little's MCAR approximation: regress missingness indicator on covariates
            cov_avail = [c for c in COVARIATES if c in df.columns]
            if cov_avail:
                df_mcar = df.copy()
                df_mcar["_missing"] = df[PRIMARY_OUTCOME].isna().astype(float)
                for c in cov_avail:
                    df_mcar[c] = pd.to_numeric(df_mcar[c], errors="coerce")
                df_mcar = df_mcar.dropna(subset=cov_avail)

                Y_m = df_mcar["_missing"].values
                X_m = sm.add_constant(df_mcar[cov_avail].values)
                try:
                    mod_mcar = sm.OLS(Y_m, X_m).fit(cov_type="HC2")
                    f_stat = mod_mcar.fvalue
                    f_pval = mod_mcar.f_pvalue
                    mcar_sig = " *NOT MCAR*" if f_pval < 0.05 else ""
                    print(f"\n  Little's MCAR proxy (F-test): F={f_stat:.3f}  "
                          f"p={f_pval:.4f}{mcar_sig}")

                    all_results.append({
                        "test": "mcar_test", "arm": "all",
                        "outcome": PRIMARY_OUTCOME,
                        "estimate": f_stat, "se_robust": np.nan,
                        "pvalue": f_pval,
                        "ci_lower": np.nan, "ci_upper": np.nan,
                        "N": len(df_mcar), "method": "mcar_proxy_ftest",
                    })
                except Exception as e:
                    print(f"  MCAR test failed: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # 9. WILD CLUSTER BOOTSTRAP (if <50 clusters)
    # ══════════════════════════════════════════════════════════════════════
    if CLUSTER_VAR and CLUSTER_VAR in df.columns and PRIMARY_OUTCOME in df.columns:
        n_clusters = df[CLUSTER_VAR].nunique()
        print(f"\n--- 7. Wild cluster bootstrap (N_clusters={n_clusters}) ---")

        if n_clusters < 50:
            print("  Running wild cluster bootstrap (Rademacher weights, 999 reps)...")
            sub = df.dropna(subset=[PRIMARY_OUTCOME, TREATMENT_VAR, CLUSTER_VAR]).copy()

            for arm_name, arm_val in treat_arms.items():
                safe = arm_name.replace(" ", "_").replace("-", "_").lower()
                arm_sub = sub[sub[TREATMENT_VAR].isin([ctrl_val, arm_val])].copy()
                arm_sub["_arm_dum"] = (arm_sub[TREATMENT_VAR] == arm_val).astype(float)

                Y = arm_sub[PRIMARY_OUTCOME].values
                X = sm.add_constant(arm_sub["_arm_dum"].values)
                clusters = arm_sub[CLUSTER_VAR].values
                unique_clusters = np.unique(clusters)

                # Restricted model (under H0: beta=0)
                model_r = sm.OLS(Y, X[:, [0]]).fit()  # just constant
                resid_r = model_r.resid
                fitted_r = model_r.fittedvalues

                # Unrestricted model
                model_u = sm.OLS(Y, X).fit()
                t_orig = model_u.tvalues[1]

                n_boot = 999
                t_boot = np.zeros(n_boot)
                # FIX: seeded RNG for reproducible bootstrap p-values across runs.
                rng = np.random.default_rng(42)

                for b in range(n_boot):
                    # Rademacher weights: +1 or -1 per cluster
                    # FIX: replaced np.random.choice with seeded rng.choice
                    rademacher = rng.choice([-1, 1], size=len(unique_clusters))
                    weights = np.array([rademacher[np.where(unique_clusters == c)[0][0]]
                                        for c in clusters])
                    y_boot = fitted_r + resid_r * weights
                    try:
                        mod_b = sm.OLS(y_boot, X).fit(cov_type="cluster",
                                                        cov_kwds={"groups": clusters})
                        t_boot[b] = mod_b.tvalues[1]
                    except Exception:
                        t_boot[b] = 0

                # Two-sided p-value
                wcb_pval = np.mean(np.abs(t_boot) >= np.abs(t_orig))
                print(f"  {arm_name}: t_orig={t_orig:.3f}  "
                      f"WCB p-value={wcb_pval:.4f}  "
                      f"(conventional p={model_u.pvalues[1]:.4f})")

                all_results.append({
                    "test": "wild_cluster_bootstrap", "arm": safe,
                    "outcome": PRIMARY_OUTCOME,
                    "estimate": model_u.params[1],
                    "se_robust": model_u.bse[1],
                    "pvalue": wcb_pval,
                    "ci_lower": np.nan, "ci_upper": np.nan,
                    "N": len(arm_sub),
                    "method": f"WCB_rademacher_{n_boot}reps",
                })
        else:
            print(f"  {n_clusters} clusters (>=50). Standard clustered SEs sufficient.")
    else:
        print("\n--- 7. Wild cluster bootstrap ---")
        print("  No cluster variable or primary outcome. Skipping.")

    # ── Save results ──────────────────────────────────────────────────────
    results_df = pd.DataFrame(all_results)

    # Fill NaN in numeric columns with safe defaults for CSV
    for col in ["estimate", "se_robust", "pvalue", "ci_lower", "ci_upper"]:
        if col in results_df.columns:
            results_df[col] = results_df[col].fillna(0.0)

    out_path = os.path.join(DATA_DIR, "robustness_results.csv")
    results_df.to_csv(out_path, index=False)
    print(f"\nSaved: {out_path} ({len(results_df)} rows)")

    print("\n" + "=" * 70)
    print("02_robustness.py complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
