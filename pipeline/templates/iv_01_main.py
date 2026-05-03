"""01_main.py — IV/2SLS main estimation template.

Handles OLS baseline, first stage, 2SLS, reduced form, Hausman test,
and over-identification test. ALWAYS reports first stage F-statistic.
If F < 10, flags WEAK INSTRUMENT and reports Anderson-Rubin CI.

CRITICAL: Never lets NaN reach tables. Uses linearmodels or statsmodels IV.
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
OUTCOME_VARS = {{OUTCOME_VARS}}             # e.g., ["log_wage", "employment"]
ENDOGENOUS_VAR = "{{ENDOGENOUS_VAR}}"       # e.g., "years_schooling"
INSTRUMENT_VARS = {{INSTRUMENT_VARS}}       # e.g., ["quarter_of_birth"]
ENTITY_VAR = "{{ENTITY_VAR}}"              # e.g., "state_id" or None
TIME_VAR = "{{TIME_VAR}}"                  # e.g., "year" or None
CLUSTER_VAR = "{{CLUSTER_VAR}}"             # e.g., "state_id"
COVARIATES = {{COVARIATES}}                 # e.g., ["age", "age_sq", "female"]
EXPECTED_SIGNS = {{EXPECTED_SIGNS}}         # e.g., {"log_wage": "+", "employment": "?"}
HETEROGENEITY_VARS = {{HETEROGENEITY_VARS}} # e.g., ["female", "age_group"]
MEDIATOR_VAR = "{{MEDIATOR_VAR}}"           # e.g., "pchoice" or "None"
PLACEBO_OUTCOMES = {{PLACEBO_OUTCOMES}}     # e.g., ["pre_treatment_score"] or []

# ═══════════════════════════════════════════════════════════════════════════════
# FIXED CODE
# ═══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "..", "data", "clean")
CLEAN_CSV = os.path.join(DATA_DIR, "clean_data.csv")

USE_FE = (ENTITY_VAR and ENTITY_VAR != "None")
USE_TIME_FE = (TIME_VAR and TIME_VAR != "None")

# ── Try to import linearmodels, fallback to statsmodels ──────────────────────
linearmodels_available = False
try:
    from linearmodels.iv import IV2SLS
    linearmodels_available = True
except ImportError:
    try:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "linearmodels"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        from linearmodels.iv import IV2SLS
        linearmodels_available = True
        print("linearmodels installed successfully.")
    except Exception:
        print("WARNING: linearmodels not available. Using statsmodels IV fallback.")


def _prepare_data(df, outcome):
    """Prepare analysis DataFrame with all required columns, dropping NaN."""
    cols = [outcome, ENDOGENOUS_VAR] + INSTRUMENT_VARS + COVARIATES
    if CLUSTER_VAR and CLUSTER_VAR in df.columns:
        cols.append(CLUSTER_VAR)
    if USE_FE and ENTITY_VAR in df.columns:
        cols.append(ENTITY_VAR)
    if USE_TIME_FE and TIME_VAR in df.columns:
        cols.append(TIME_VAR)
    cols = list(dict.fromkeys([c for c in cols if c in df.columns]))
    sub = df[cols].dropna().copy()
    return sub


def _get_cov_formula(include_endogenous=False):
    """Build covariate list for formulas."""
    cov_list = [c for c in COVARIATES]
    if include_endogenous:
        cov_list = [ENDOGENOUS_VAR] + cov_list
    return cov_list


def run_ols(df, outcome):
    """OLS baseline: Y ~ endogenous + controls (+ FE)."""
    import statsmodels.api as sm

    sub = _prepare_data(df, outcome)
    if len(sub) < 20:
        return _empty_result(outcome, "OLS")

    y = sub[outcome].values
    X_cols = [ENDOGENOUS_VAR] + [c for c in COVARIATES if c in sub.columns]

    # Add entity FE dummies if panel
    X_df = sub[X_cols].copy()
    if USE_FE and ENTITY_VAR in sub.columns and sub[ENTITY_VAR].nunique() < 500:
        fe_dummies = pd.get_dummies(sub[ENTITY_VAR], prefix="fe", drop_first=True)
        X_df = pd.concat([X_df, fe_dummies], axis=1)
    if USE_TIME_FE and TIME_VAR in sub.columns and sub[TIME_VAR].nunique() < 100:
        te_dummies = pd.get_dummies(sub[TIME_VAR], prefix="te", drop_first=True)
        X_df = pd.concat([X_df, te_dummies], axis=1)

    X_df = sm.add_constant(X_df)

    try:
        # Cluster SEs if available
        if CLUSTER_VAR and CLUSTER_VAR in sub.columns:
            mod = sm.OLS(y, X_df).fit(
                cov_type="cluster",
                cov_kwds={"groups": sub[CLUSTER_VAR].values})
        else:
            mod = sm.OLS(y, X_df).fit(cov_type="HC1")

        idx = list(X_df.columns).index(ENDOGENOUS_VAR)
        ci = mod.conf_int().iloc[idx]
        return {
            "outcome": outcome, "specification": "OLS",
            "estimate": mod.params.iloc[idx],
            "se_robust": mod.bse.iloc[idx],
            "pvalue": mod.pvalues.iloc[idx],
            "ci_lower": ci[0], "ci_upper": ci[1],
            "first_stage_F": np.nan,
            "N": len(sub), "method": "OLS",
        }
    except Exception as e:
        print(f"    OLS failed: {e}")
        return _empty_result(outcome, "OLS")


def run_first_stage(df, outcome):
    """First stage: endogenous ~ instruments + controls. Reports F-statistic."""
    import statsmodels.api as sm

    sub = _prepare_data(df, outcome)
    if len(sub) < 20:
        return _empty_result(outcome, "first_stage"), np.nan

    y_endo = sub[ENDOGENOUS_VAR].values
    X_cols = INSTRUMENT_VARS + [c for c in COVARIATES if c in sub.columns]

    X_df = sub[X_cols].copy()
    if USE_FE and ENTITY_VAR in sub.columns and sub[ENTITY_VAR].nunique() < 500:
        fe_dummies = pd.get_dummies(sub[ENTITY_VAR], prefix="fe", drop_first=True)
        X_df = pd.concat([X_df, fe_dummies], axis=1)
    if USE_TIME_FE and TIME_VAR in sub.columns and sub[TIME_VAR].nunique() < 100:
        te_dummies = pd.get_dummies(sub[TIME_VAR], prefix="te", drop_first=True)
        X_df = pd.concat([X_df, te_dummies], axis=1)

    X_df = sm.add_constant(X_df)

    try:
        if CLUSTER_VAR and CLUSTER_VAR in sub.columns:
            mod = sm.OLS(y_endo, X_df).fit(
                cov_type="cluster",
                cov_kwds={"groups": sub[CLUSTER_VAR].values})
        else:
            mod = sm.OLS(y_endo, X_df).fit(cov_type="HC1")

        # Partial F-statistic: test that all instrument coefficients = 0
        z_indices = [list(X_df.columns).index(z) for z in INSTRUMENT_VARS if z in X_df.columns]
        if len(z_indices) > 0:
            R = np.zeros((len(z_indices), len(mod.params)))
            for i, idx in enumerate(z_indices):
                R[i, idx] = 1
            f_test = mod.f_test(R)
            f_stat = float(f_test.fvalue)
            f_pval = float(f_test.pvalue)
        else:
            f_stat = np.nan
            f_pval = np.nan

        # Report each instrument coefficient
        result_rows = []
        for z in INSTRUMENT_VARS:
            if z in X_df.columns:
                idx = list(X_df.columns).index(z)
                ci = mod.conf_int().iloc[idx]
                result_rows.append({
                    "outcome": ENDOGENOUS_VAR, "specification": "first_stage",
                    "instrument": z,
                    "estimate": mod.params.iloc[idx],
                    "se_robust": mod.bse.iloc[idx],
                    "pvalue": mod.pvalues.iloc[idx],
                    "ci_lower": ci[0], "ci_upper": ci[1],
                    "first_stage_F": f_stat,
                    "first_stage_F_pval": f_pval,
                    "N": len(sub), "method": "OLS_first_stage",
                })

        return result_rows, f_stat
    except Exception as e:
        print(f"    First stage failed: {e}")
        return [_empty_result(outcome, "first_stage")], np.nan


def run_2sls(df, outcome, f_stat):
    """2SLS estimation using linearmodels or statsmodels."""
    sub = _prepare_data(df, outcome)
    if len(sub) < 20:
        return _empty_result(outcome, "2SLS")

    # ── Try linearmodels IV2SLS ──────────────────────────────────────────
    if linearmodels_available:
        try:
            cov_str = " + ".join(COVARIATES) if COVARIATES else ""
            z_str = " + ".join(INSTRUMENT_VARS)

            # Build formula: dependent ~ exogenous + [endogenous ~ instruments]
            if USE_FE and ENTITY_VAR in sub.columns:
                sub = sub.set_index([ENTITY_VAR, TIME_VAR] if USE_TIME_FE and TIME_VAR in sub.columns
                                    else [ENTITY_VAR, sub.index.name or "obs_id"])
                if sub.index.names[-1] == "obs_id" or sub.index.names[-1] is None:
                    sub.index = sub.index.set_names(["entity", "obs_id"])
                    # For entity FE without time, use simple entity index
                    sub = sub.droplevel("obs_id")
                    sub.index.name = "entity"

            exog = "1 + " + " + ".join(COVARIATES) if COVARIATES else "1"
            formula = f"{outcome} ~ {exog} + [{ENDOGENOUS_VAR} ~ {z_str}]"

            if USE_FE and ENTITY_VAR in sub.columns:
                from linearmodels.iv import IV2SLS as _IV2SLS
                mod = _IV2SLS.from_formula(formula, data=sub).fit(
                    cov_type="clustered",
                    clusters=sub.reset_index()[CLUSTER_VAR].values if CLUSTER_VAR and CLUSTER_VAR in df.columns else None)
            else:
                mod = IV2SLS.from_formula(formula, data=sub).fit(
                    cov_type="clustered",
                    clusters=sub[CLUSTER_VAR].values if CLUSTER_VAR and CLUSTER_VAR in sub.columns else None)

            ci = mod.conf_int().loc[ENDOGENOUS_VAR]
            result = {
                "outcome": outcome, "specification": "2SLS",
                "estimate": float(mod.params[ENDOGENOUS_VAR]),
                "se_robust": float(mod.std_errors[ENDOGENOUS_VAR]),
                "pvalue": float(mod.pvalues[ENDOGENOUS_VAR]),
                "ci_lower": float(ci.iloc[0]),
                "ci_upper": float(ci.iloc[1]),
                "first_stage_F": f_stat,
                "N": int(mod.nobs), "method": "IV2SLS_linearmodels",
            }

            # CRITICAL: If F < 10, flag weak instrument
            if not np.isnan(f_stat) and f_stat < 10:
                result["weak_instrument_flag"] = True
                print(f"    WEAK INSTRUMENT WARNING: F = {f_stat:.2f} < 10")
                # Compute Anderson-Rubin CI
                ar_ci = _anderson_rubin_ci(df, outcome)
                if ar_ci is not None:
                    result["ar_ci_lower"] = ar_ci[0]
                    result["ar_ci_upper"] = ar_ci[1]
                    print(f"    Anderson-Rubin 95% CI: [{ar_ci[0]:.4f}, {ar_ci[1]:.4f}]")

            return result
        except Exception as e:
            print(f"    linearmodels IV2SLS failed: {e}. Trying statsmodels fallback.")

    # ── Statsmodels IV2SLS fallback ──────────────────────────────────────
    try:
        from statsmodels.sandbox.regression.gmm import IV2SLS as smIV2SLS
        import statsmodels.api as sm

        sub_clean = _prepare_data(df, outcome)
        y = sub_clean[outcome].values
        endog_col = sub_clean[ENDOGENOUS_VAR].values
        exog_cols = [c for c in COVARIATES if c in sub_clean.columns]
        X = sm.add_constant(sub_clean[exog_cols].values) if exog_cols else np.ones((len(y), 1))
        X_endog = np.column_stack([X, endog_col])
        Z = np.column_stack([X] + [sub_clean[z].values for z in INSTRUMENT_VARS if z in sub_clean.columns])

        mod = smIV2SLS(y, X_endog, Z).fit()
        # Endogenous var is last column
        idx = -1
        estimate = float(mod.params[idx])
        se = float(mod.bse[idx])
        ci_lower = estimate - 1.96 * se
        ci_upper = estimate + 1.96 * se
        pval = float(mod.pvalues[idx])

        result = {
            "outcome": outcome, "specification": "2SLS",
            "estimate": estimate, "se_robust": se,
            "pvalue": pval,
            "ci_lower": ci_lower, "ci_upper": ci_upper,
            "first_stage_F": f_stat,
            "N": len(y), "method": "IV2SLS_statsmodels",
        }

        if not np.isnan(f_stat) and f_stat < 10:
            result["weak_instrument_flag"] = True
            print(f"    WEAK INSTRUMENT WARNING: F = {f_stat:.2f} < 10")
            ar_ci = _anderson_rubin_ci(df, outcome)
            if ar_ci is not None:
                result["ar_ci_lower"] = ar_ci[0]
                result["ar_ci_upper"] = ar_ci[1]

        return result
    except Exception as e:
        print(f"    statsmodels IV2SLS also failed: {e}")
        return _empty_result(outcome, "2SLS")


def _anderson_rubin_ci(df, outcome, alpha=0.05):
    """Compute Anderson-Rubin confidence set (weak-instrument robust)."""
    import statsmodels.api as sm

    sub = _prepare_data(df, outcome)
    if len(sub) < 20:
        return None

    y = sub[outcome].values
    endog = sub[ENDOGENOUS_VAR].values
    Z_cols = INSTRUMENT_VARS + [c for c in COVARIATES if c in sub.columns]
    Z = sm.add_constant(sub[Z_cols].values)

    # Grid search over beta values
    betas = np.linspace(
        np.percentile(y / (endog + 1e-10), 5),
        np.percentile(y / (endog + 1e-10), 95),
        500)

    ar_accept = []
    crit = stats.chi2.ppf(1 - alpha, df=len(INSTRUMENT_VARS))

    for beta in betas:
        resid = y - beta * endog
        try:
            if CLUSTER_VAR and CLUSTER_VAR in sub.columns:
                mod = sm.OLS(resid, Z).fit(
                    cov_type="cluster",
                    cov_kwds={"groups": sub[CLUSTER_VAR].values})
            else:
                mod = sm.OLS(resid, Z).fit(cov_type="HC1")

            # Test that instrument coefficients = 0
            z_indices = [list(sub[Z_cols].columns).index(z) + 1
                         for z in INSTRUMENT_VARS if z in sub[Z_cols].columns]
            if len(z_indices) > 0:
                R = np.zeros((len(z_indices), len(mod.params)))
                for i, idx in enumerate(z_indices):
                    R[i, idx] = 1
                f_test = mod.f_test(R)
                ar_stat = float(f_test.fvalue) * len(z_indices)
                if ar_stat <= crit:
                    ar_accept.append(beta)
        except Exception:
            continue

    if len(ar_accept) > 0:
        return (min(ar_accept), max(ar_accept))
    return None


def run_reduced_form(df, outcome):
    """Reduced form: Y ~ instruments + controls (intent-to-treat analog)."""
    import statsmodels.api as sm

    sub = _prepare_data(df, outcome)
    if len(sub) < 20:
        return _empty_result(outcome, "reduced_form")

    y = sub[outcome].values
    X_cols = INSTRUMENT_VARS + [c for c in COVARIATES if c in sub.columns]

    X_df = sub[X_cols].copy()
    if USE_FE and ENTITY_VAR in sub.columns and sub[ENTITY_VAR].nunique() < 500:
        fe_dummies = pd.get_dummies(sub[ENTITY_VAR], prefix="fe", drop_first=True)
        X_df = pd.concat([X_df, fe_dummies], axis=1)
    if USE_TIME_FE and TIME_VAR in sub.columns and sub[TIME_VAR].nunique() < 100:
        te_dummies = pd.get_dummies(sub[TIME_VAR], prefix="te", drop_first=True)
        X_df = pd.concat([X_df, te_dummies], axis=1)

    X_df = sm.add_constant(X_df)

    try:
        if CLUSTER_VAR and CLUSTER_VAR in sub.columns:
            mod = sm.OLS(y, X_df).fit(
                cov_type="cluster",
                cov_kwds={"groups": sub[CLUSTER_VAR].values})
        else:
            mod = sm.OLS(y, X_df).fit(cov_type="HC1")

        results = []
        for z in INSTRUMENT_VARS:
            if z in X_df.columns:
                idx = list(X_df.columns).index(z)
                ci = mod.conf_int().iloc[idx]
                results.append({
                    "outcome": outcome, "specification": "reduced_form",
                    "instrument": z,
                    "estimate": mod.params.iloc[idx],
                    "se_robust": mod.bse.iloc[idx],
                    "pvalue": mod.pvalues.iloc[idx],
                    "ci_lower": ci[0], "ci_upper": ci[1],
                    "first_stage_F": np.nan,
                    "N": len(sub), "method": "OLS_reduced_form",
                })
        return results
    except Exception as e:
        print(f"    Reduced form failed: {e}")
        return [_empty_result(outcome, "reduced_form")]


def run_hausman_test(df, outcome, ols_est, ols_se, iv_est, iv_se):
    """Hausman test: OLS vs 2SLS. Significant => endogeneity present."""
    try:
        diff = iv_est - ols_est
        var_diff = iv_se**2 - ols_se**2
        if var_diff > 0:
            hausman_stat = diff**2 / var_diff
            hausman_pval = 1 - stats.chi2.cdf(hausman_stat, df=1)
        else:
            hausman_stat = np.nan
            hausman_pval = np.nan
        return hausman_stat, hausman_pval
    except Exception:
        return np.nan, np.nan


def run_overid_test(df, outcome):
    """Sargan/Hansen J test for over-identification (requires >1 instrument)."""
    if len(INSTRUMENT_VARS) <= 1:
        return np.nan, np.nan

    import statsmodels.api as sm

    sub = _prepare_data(df, outcome)
    if len(sub) < 20:
        return np.nan, np.nan

    try:
        # Run 2SLS, get residuals, regress on instruments + controls
        y = sub[outcome].values
        X_cols = [ENDOGENOUS_VAR] + [c for c in COVARIATES if c in sub.columns]
        Z_cols = INSTRUMENT_VARS + [c for c in COVARIATES if c in sub.columns]

        X = sm.add_constant(sub[X_cols].values)
        Z = sm.add_constant(sub[Z_cols].values)

        # First stage
        endog = sub[ENDOGENOUS_VAR].values
        fs_mod = sm.OLS(endog, Z).fit()
        endog_hat = fs_mod.fittedvalues

        # Second stage
        X_2sls = X.copy()
        X_2sls[:, list(sub[X_cols].columns).index(ENDOGENOUS_VAR) + 1] = endog_hat
        ss_mod = sm.OLS(y, X_2sls).fit()
        resid = y - ss_mod.fittedvalues

        # Sargan test: regress residuals on all instruments and controls
        Z_full = sm.add_constant(sub[Z_cols].values)
        aux_mod = sm.OLS(resid, Z_full).fit()

        n = len(y)
        j_stat = n * aux_mod.rsquared
        j_df = len(INSTRUMENT_VARS) - 1  # overid degrees of freedom
        j_pval = 1 - stats.chi2.cdf(j_stat, df=j_df)

        return j_stat, j_pval
    except Exception as e:
        print(f"    Over-identification test failed: {e}")
        return np.nan, np.nan


def _empty_result(outcome, spec):
    """Return a complete result dict with NaN values."""
    return {
        "outcome": outcome, "specification": spec,
        "estimate": np.nan, "se_robust": np.nan,
        "pvalue": np.nan,
        "ci_lower": np.nan, "ci_upper": np.nan,
        "first_stage_F": np.nan,
        "N": 0, "method": "none",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# COMPLIANCE STRUCTURE (always-takers, never-takers, compliers, defiers)
# ═══════════════════════════════════════════════════════════════════════════════
def run_compliance_structure(df):
    """Compute compliance shares using Imbens-Rubin framework.

    For binary instrument Z and binary endogenous D:
      P(complier)      = P(D=1|Z=1) - P(D=1|Z=0)
      P(always-taker)  = P(D=1|Z=0)
      P(never-taker)   = P(D=0|Z=1)
      P(defier)         = max(0, P(D=1|Z=0) - P(D=1|Z=1))  [should be ~0 under monotonicity]
    """
    z_var = INSTRUMENT_VARS[0]
    if z_var not in df.columns or ENDOGENOUS_VAR not in df.columns:
        return None

    sub = df[[z_var, ENDOGENOUS_VAR]].dropna()
    if len(sub) < 20:
        return None

    # Binarize instrument if needed
    z = sub[z_var].values
    d = sub[ENDOGENOUS_VAR].values

    z_median = np.median(z)
    z_bin = (z > z_median).astype(float) if len(np.unique(z)) > 2 else z

    # Binarize endogenous if needed
    d_median = np.median(d)
    d_bin = (d > d_median).astype(float) if len(np.unique(d)) > 2 else d

    p_d1_z1 = d_bin[z_bin == 1].mean() if (z_bin == 1).sum() > 0 else np.nan
    p_d1_z0 = d_bin[z_bin == 0].mean() if (z_bin == 0).sum() > 0 else np.nan

    if np.isnan(p_d1_z1) or np.isnan(p_d1_z0):
        return None

    compliance_rate = p_d1_z1 - p_d1_z0
    always_takers = p_d1_z0
    never_takers = 1 - p_d1_z1
    defiers = max(0, p_d1_z0 - p_d1_z1)

    # Monotonicity check
    monotonicity_ok = defiers < 0.01

    return {
        "compliance_rate": compliance_rate,
        "always_takers": always_takers,
        "never_takers": never_takers,
        "compliers": max(0, compliance_rate),
        "defiers": defiers,
        "monotonicity_ok": monotonicity_ok,
        "p_d1_z1": p_d1_z1,
        "p_d1_z0": p_d1_z0,
        "N_z1": int((z_bin == 1).sum()),
        "N_z0": int((z_bin == 0).sum()),
    }


def run_wald_crosscheck(df, outcome, compliance_info):
    """Wald estimator: ITT / compliance_rate. Must match 2SLS LATE."""
    if compliance_info is None or abs(compliance_info.get("compliance_rate", 0)) < 1e-10:
        return None

    import statsmodels.api as sm
    z_var = INSTRUMENT_VARS[0]
    sub = df[[outcome, z_var] + [c for c in COVARIATES if c in df.columns]].dropna()
    if len(sub) < 20:
        return None

    # ITT: outcome ~ instrument
    y = sub[outcome].values
    X = sm.add_constant(sub[z_var].values)
    try:
        mod = sm.OLS(y, X).fit(cov_type="HC1")
        itt = mod.params[1]
        itt_se = mod.bse[1]
    except Exception:
        return None

    cr = compliance_info["compliance_rate"]
    if abs(cr) < 1e-10:
        return None
    wald = itt / cr
    # Delta method SE for Wald
    wald_se = abs(itt_se / cr)

    return {
        "itt_estimate": itt,
        "itt_se": itt_se,
        "compliance_rate": compliance_info["compliance_rate"],
        "wald_estimate": wald,
        "wald_se": wald_se,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# POWER CALCULATIONS
# ═══════════════════════════════════════════════════════════════════════════════
def run_power_calculation(df, outcome, compliance_rate=None):
    """Post-hoc power calc: MDE at 80% power for ITT and LATE."""
    sub = df[[outcome] + INSTRUMENT_VARS].dropna()
    if len(sub) < 20:
        return None

    y = sub[outcome].values
    n = len(y)
    sd = np.std(y, ddof=1)
    if sd < 1e-10:
        print(f"    WARNING: zero variance in {outcome} — cannot compute power")
        return None
    alpha = 0.05
    power = 0.80

    # z-scores for two-sided test
    z_alpha = stats.norm.ppf(1 - alpha / 2)  # 1.96
    z_beta = stats.norm.ppf(power)            # 0.84

    # MDE for ITT (simple formula for continuous outcome)
    mde_itt = (z_alpha + z_beta) * sd * np.sqrt(4.0 / n)

    # MDE for LATE (scales by 1/compliance_rate)
    mde_late = np.nan
    if compliance_rate and abs(compliance_rate) > 0.01:
        mde_late = mde_itt / abs(compliance_rate)

    # Cohen's d equivalent
    cohens_d_mde = mde_itt / sd if sd > 0 else np.nan

    return {
        "N": n,
        "outcome_mean": np.mean(y),
        "outcome_sd": sd,
        "mde_itt": mde_itt,
        "mde_late": mde_late,
        "cohens_d_mde": cohens_d_mde,
        "alpha": alpha,
        "power": power,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# EFFECT SIZES
# ═══════════════════════════════════════════════════════════════════════════════
def compute_effect_sizes(estimate, se, df_data, outcome):
    """Cohen's d, percentage-point change, percentage change vs control mean."""
    sub = df_data[outcome].dropna()
    if len(sub) < 5:
        return {"cohens_d": np.nan, "pct_change": np.nan, "outcome_mean": np.nan,
                "outcome_sd": np.nan, "large_effect_flag": False}
    sd = sub.std()
    mean_val = sub.mean()

    cohens_d = estimate / sd if sd > 1e-10 else np.nan
    pct_change = 100 * estimate / abs(mean_val) if abs(mean_val) > 1e-10 else np.nan

    # Flag if effect > 1 SD
    large_effect_flag = abs(cohens_d) > 1.0 if not np.isnan(cohens_d) else False

    return {
        "cohens_d": cohens_d,
        "pct_change": pct_change,
        "outcome_mean": mean_val,
        "outcome_sd": sd,
        "large_effect_flag": large_effect_flag,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# COVARIATE BALANCE ON INSTRUMENT
# ═══════════════════════════════════════════════════════════════════════════════
def run_covariate_balance(df):
    """Test whether instrument predicts covariates (randomization check)."""
    import statsmodels.api as sm

    z_var = INSTRUMENT_VARS[0]
    if z_var not in df.columns:
        return []

    results = []
    cov_avail = [c for c in COVARIATES if c in df.columns]

    for cov in cov_avail:
        sub = df[[cov, z_var]].dropna()
        if len(sub) < 20:
            continue
        sub[cov] = pd.to_numeric(sub[cov], errors="coerce")
        sub = sub.dropna()

        y = sub[cov].values
        X = sm.add_constant(sub[z_var].values)
        try:
            mod = sm.OLS(y, X).fit(cov_type="HC2")
            est = mod.params[1]
            se = mod.bse[1]
            pval = mod.pvalues[1]

            # Standardized mean difference
            z_vals = sub[z_var].values
            if len(np.unique(z_vals)) == 2:
                g1 = sub.loc[sub[z_var] == np.unique(z_vals)[0], cov]
                g2 = sub.loc[sub[z_var] == np.unique(z_vals)[1], cov]
                pooled_sd = np.sqrt((g1.var() + g2.var()) / 2)
                smd = (g2.mean() - g1.mean()) / pooled_sd if pooled_sd > 0 else 0
            else:
                smd = est / sub[cov].std() if sub[cov].std() > 0 else 0

            results.append({
                "covariate": cov, "estimate": est, "se": se,
                "pvalue": pval, "smd": smd, "N": len(sub),
            })
        except Exception:
            continue

    # Joint F-test: regress instrument on all covariates
    sub_all = df[[z_var] + cov_avail].dropna()
    for c in cov_avail:
        sub_all[c] = pd.to_numeric(sub_all[c], errors="coerce")
    sub_all = sub_all.dropna()

    if len(sub_all) > len(cov_avail) + 5:
        try:
            y = sub_all[z_var].values
            X = sm.add_constant(sub_all[cov_avail].values)
            mod = sm.OLS(y, X).fit(cov_type="HC2")
            joint_f = mod.fvalue
            joint_f_pval = mod.f_pvalue
        except Exception:
            joint_f, joint_f_pval = np.nan, np.nan
    else:
        joint_f, joint_f_pval = np.nan, np.nan

    return results, joint_f, joint_f_pval


# ═══════════════════════════════════════════════════════════════════════════════
# HETEROGENEITY ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════
def run_heterogeneity_iv(df, outcome, moderator, f_stat):
    """Run IV with treatment × moderator interaction."""
    import statsmodels.api as sm

    sub = _prepare_data(df, outcome)
    if moderator not in sub.columns:
        return None
    sub[moderator] = pd.to_numeric(sub[moderator], errors="coerce")
    sub = sub.dropna(subset=[moderator])

    if len(sub) < 30 or sub[moderator].nunique() <= 1:
        return None

    # Create interaction: endogenous × moderator
    sub["_endog_x_mod"] = sub[ENDOGENOUS_VAR] * sub[moderator]

    # Instruments: Z and Z × moderator
    z_var = INSTRUMENT_VARS[0]
    sub["_z_x_mod"] = sub[z_var] * sub[moderator]

    try:
        # Build formula components
        y = sub[outcome].values
        endog = sub[ENDOGENOUS_VAR].values
        endog_x_mod = sub["_endog_x_mod"].values
        z = sub[z_var].values
        z_x_mod = sub["_z_x_mod"].values
        mod_vals = sub[moderator].values

        # First stage for endogenous
        cov_cols = [c for c in COVARIATES if c in sub.columns]
        X_fs = np.column_stack([np.ones(len(sub)), z, z_x_mod, mod_vals] +
                               [sub[c].values for c in cov_cols])
        fs1 = sm.OLS(endog, X_fs).fit()
        endog_hat = fs1.fittedvalues

        # First stage for interaction
        fs2 = sm.OLS(endog_x_mod, X_fs).fit()
        endog_x_mod_hat = fs2.fittedvalues

        # Second stage
        X_2s = np.column_stack([np.ones(len(sub)), endog_hat, endog_x_mod_hat, mod_vals] +
                               [sub[c].values for c in cov_cols])
        ss = sm.OLS(y, X_2s).fit(cov_type="HC1")

        # Interaction coefficient is index 2
        interaction_est = ss.params[2]
        interaction_se = ss.bse[2]
        interaction_pval = ss.pvalues[2]
        ci = ss.conf_int()[2]

        return {
            "outcome": outcome,
            "moderator": moderator,
            "interaction_estimate": interaction_est,
            "interaction_se": interaction_se,
            "interaction_pval": interaction_pval,
            "ci_lower": ci[0], "ci_upper": ci[1],
            "main_estimate": ss.params[1],
            "main_se": ss.bse[1],
            "N": len(sub),
        }
    except Exception as e:
        print(f"    Heterogeneity IV failed for {moderator}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# MISSING DATA ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════
def run_missing_data_analysis(df, outcome):
    """Report missing data counts and run attrition/Lee bounds if needed."""
    import statsmodels.api as sm

    all_vars = [outcome, ENDOGENOUS_VAR] + INSTRUMENT_VARS + COVARIATES
    all_vars = [v for v in all_vars if v in df.columns]

    missing_report = {}
    for var in all_vars:
        n_miss = df[var].isna().sum()
        pct = 100 * n_miss / len(df)
        missing_report[var] = {"n_missing": n_miss, "pct_missing": pct}

    # Outcome missingness analysis
    outcome_miss_pct = missing_report.get(outcome, {}).get("pct_missing", 0)

    # Differential attrition: does instrument predict missingness?
    z_var = INSTRUMENT_VARS[0]
    attrition_result = None
    if z_var in df.columns:
        df_attr = df[[z_var]].copy()
        df_attr["_observed"] = df[outcome].notna().astype(float)
        df_attr = df_attr.dropna(subset=[z_var])

        y = df_attr["_observed"].values
        X = sm.add_constant(df_attr[z_var].values)
        try:
            mod = sm.OLS(y, X).fit(cov_type="HC2")
            attrition_result = {
                "attrition_coef": mod.params[1],
                "attrition_se": mod.bse[1],
                "attrition_pval": mod.pvalues[1],
                "differential": mod.pvalues[1] < 0.05,
            }
        except Exception:
            pass

    # Lee (2009) trimming bounds if missingness > 5%
    lee_bounds = None
    if outcome_miss_pct > 5 and z_var in df.columns:
        sub = df[[outcome, z_var]].copy()
        sub["_z_bin"] = sub[z_var]
        if sub[z_var].nunique() > 2:
            sub["_z_bin"] = (sub[z_var] > sub[z_var].median()).astype(float)

        obs_rate_z1 = sub.loc[sub["_z_bin"] == 1, outcome].notna().mean()
        obs_rate_z0 = sub.loc[sub["_z_bin"] == 0, outcome].notna().mean()

        if abs(obs_rate_z1 - obs_rate_z0) > 0.001:
            if obs_rate_z1 > obs_rate_z0:
                trim_group, trim_pct = 1, 1 - obs_rate_z0 / obs_rate_z1
            else:
                trim_group, trim_pct = 0, 1 - obs_rate_z1 / obs_rate_z0

            sub_complete = sub.dropna(subset=[outcome])
            group_to_trim = sub_complete[sub_complete["_z_bin"] == trim_group]
            other = sub_complete[sub_complete["_z_bin"] == (1 - trim_group)]

            y_trim = group_to_trim[outcome].sort_values()
            n_trim = int(np.ceil(len(y_trim) * trim_pct))

            if 0 < n_trim < len(y_trim):
                y_upper = y_trim.iloc[n_trim:]
                y_lower = y_trim.iloc[:len(y_trim) - n_trim]
                other_mean = other[outcome].mean()

                if trim_group == 1:
                    ub = y_upper.mean() - other_mean
                    lb = y_lower.mean() - other_mean
                else:
                    treat_mean = sub_complete.loc[sub_complete["_z_bin"] == 1, outcome].mean()
                    ub = treat_mean - y_lower.mean()
                    lb = treat_mean - y_upper.mean()

                lee_bounds = {
                    "lower_bound": min(lb, ub),
                    "upper_bound": max(lb, ub),
                    "trim_pct": trim_pct,
                    "N_trimmed": n_trim,
                }

    return {
        "missing_report": missing_report,
        "outcome_miss_pct": outcome_miss_pct,
        "attrition_result": attrition_result,
        "lee_bounds": lee_bounds,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MULTIPLE SPECIFICATION ITT (no controls, demographics, full controls)
# ═══════════════════════════════════════════════════════════════════════════════
def run_multi_spec_itt(df, outcome):
    """Run ITT (reduced form) with progressively more controls."""
    import statsmodels.api as sm

    z_var = INSTRUMENT_VARS[0]
    results = []

    specs = [
        ("no_controls", []),
        ("demographics", COVARIATES[:min(5, len(COVARIATES))]),
        ("full_controls", COVARIATES),
    ]

    for spec_name, controls in specs:
        cols = [outcome, z_var] + [c for c in controls if c in df.columns]
        sub = df[cols].dropna()
        if len(sub) < 20:
            continue

        y = sub[outcome].values
        rhs = [z_var] + [c for c in controls if c in sub.columns]
        X = sm.add_constant(sub[rhs].values)

        try:
            if CLUSTER_VAR and CLUSTER_VAR in df.columns and CLUSTER_VAR in sub.columns:
                mod = sm.OLS(y, X).fit(cov_type="cluster",
                                       cov_kwds={"groups": sub[CLUSTER_VAR].values})
            else:
                mod = sm.OLS(y, X).fit(cov_type="HC2")

            ci = mod.conf_int()[1]
            results.append({
                "outcome": outcome, "specification": f"itt_{spec_name}",
                "estimate": mod.params[1], "se_robust": mod.bse[1],
                "pvalue": mod.pvalues[1],
                "ci_lower": ci[0], "ci_upper": ci[1],
                "r_squared": mod.rsquared,
                "N": len(sub), "method": f"OLS_ITT_{spec_name}",
            })
        except Exception:
            continue

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("01_main.py — IV/2SLS Main Estimation (Expanded)")
    print("=" * 70)

    df = pd.read_csv(CLEAN_CSV)
    print(f"Loaded: {len(df):,} rows x {df.shape[1]} cols")

    # ── Expected signs ────────────────────────────────────────────────────
    print("\n--- Expected signs ---")
    for outcome, sign in EXPECTED_SIGNS.items():
        print(f"  {outcome}: {sign}")

    all_results = []
    outcomes_present = [o for o in OUTCOME_VARS if o in df.columns]

    # ══════════════════════════════════════════════════════════════════════
    # COMPLIANCE STRUCTURE
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- Compliance Structure (Imbens-Rubin) ---")
    compliance_info = run_compliance_structure(df)
    if compliance_info:
        print(f"  P(D=1|Z=1) = {compliance_info['p_d1_z1']:.4f}  (N={compliance_info['N_z1']})")
        print(f"  P(D=1|Z=0) = {compliance_info['p_d1_z0']:.4f}  (N={compliance_info['N_z0']})")
        print(f"  Compliance rate:  {compliance_info['compliance_rate']:.4f}")
        print(f"  Always-takers:    {compliance_info['always_takers']:.4f}")
        print(f"  Never-takers:     {compliance_info['never_takers']:.4f}")
        print(f"  Compliers:        {compliance_info['compliers']:.4f}")
        print(f"  Defiers:          {compliance_info['defiers']:.4f}")
        print(f"  Monotonicity OK:  {compliance_info['monotonicity_ok']}")
        if not compliance_info['monotonicity_ok']:
            print(f"  *** WARNING: Possible defiers detected. LATE interpretation may break. ***")

        all_results.append({
            "outcome": "compliance", "specification": "compliance_structure",
            "estimate": compliance_info['compliance_rate'],
            "se_robust": np.nan, "pvalue": np.nan,
            "ci_lower": compliance_info['always_takers'],
            "ci_upper": compliance_info['never_takers'],
            "first_stage_F": np.nan,
            "N": compliance_info['N_z1'] + compliance_info['N_z0'],
            "method": "imbens_rubin",
        })
    else:
        print("  Could not compute compliance structure.")

    # ══════════════════════════════════════════════════════════════════════
    # COVARIATE BALANCE ON INSTRUMENT
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- Covariate Balance on Instrument ---")
    balance_results, joint_f, joint_f_pval = run_covariate_balance(df)
    if balance_results:
        for br in balance_results:
            flag = " *" if br['pvalue'] < 0.10 else ""
            smd_flag = " [SMD>0.1]" if abs(br['smd']) > 0.1 else ""
            print(f"  {br['covariate']:30s}: coef={br['estimate']:.4f}  "
                  f"SE={br['se']:.4f}  p={br['pvalue']:.4f}  SMD={br['smd']:.3f}{flag}{smd_flag}")

            all_results.append({
                "outcome": br['covariate'], "specification": "balance_test",
                "estimate": br['estimate'], "se_robust": br['se'],
                "pvalue": br['pvalue'],
                "ci_lower": br['smd'], "ci_upper": np.nan,
                "first_stage_F": np.nan,
                "N": br['N'], "method": "OLS_balance",
            })

        print(f"\n  Joint F-test: F={joint_f:.3f}  p={joint_f_pval:.4f}")
        sig = " ***" if joint_f_pval < 0.01 else (" **" if joint_f_pval < 0.05 else "")
        print(f"  {sig}")

    # ══════════════════════════════════════════════════════════════════════
    # POWER CALCULATIONS
    # ══════════════════════════════════════════════════════════════════════
    print("\n--- Power Calculations ---")
    for outcome in outcomes_present:
        cr = compliance_info['compliance_rate'] if compliance_info else None
        power_info = run_power_calculation(df, outcome, cr)
        if power_info:
            print(f"  {outcome}:")
            print(f"    N={power_info['N']}, SD={power_info['outcome_sd']:.4f}")
            print(f"    MDE (ITT):  {power_info['mde_itt']:.4f}  "
                  f"(Cohen's d = {power_info['cohens_d_mde']:.3f})")
            if not np.isnan(power_info['mde_late']):
                print(f"    MDE (LATE): {power_info['mde_late']:.4f}")

            all_results.append({
                "outcome": outcome, "specification": "power_calculation",
                "estimate": power_info['mde_itt'],
                "se_robust": power_info['mde_late'],
                "pvalue": np.nan,
                "ci_lower": power_info['cohens_d_mde'],
                "ci_upper": power_info['outcome_sd'],
                "first_stage_F": np.nan,
                "N": power_info['N'], "method": "power_calc",
            })

    # ══════════════════════════════════════════════════════════════════════
    # MAIN ESTIMATION LOOP
    # ══════════════════════════════════════════════════════════════════════
    for outcome in outcomes_present:
        print(f"\n{'='*50}")
        print(f"Outcome: {outcome}")
        print(f"{'='*50}")

        # ── OLS baseline ─────────────────────────────────────────────────
        print("\n  --- OLS Baseline ---")
        ols_res = run_ols(df, outcome)
        all_results.append(ols_res)
        print(f"    Estimate: {ols_res['estimate']:.4f}  SE: {ols_res['se_robust']:.4f}")
        print(f"    95% CI: [{ols_res['ci_lower']:.4f}, {ols_res['ci_upper']:.4f}]")

        # ── First stage ──────────────────────────────────────────────────
        print("\n  --- First Stage ---")
        fs_results, f_stat = run_first_stage(df, outcome)
        for fs_res in fs_results:
            all_results.append(fs_res)
            z_name = fs_res.get("instrument", "?")
            print(f"    {z_name}: coef={fs_res['estimate']:.4f}  SE={fs_res['se_robust']:.4f}")

        print(f"    First-stage F-statistic: {f_stat:.2f}")
        if not np.isnan(f_stat) and f_stat < 10:
            print(f"    *** WEAK INSTRUMENT: F = {f_stat:.2f} < 10 ***")
            print(f"    Standard 2SLS inference unreliable. Using Anderson-Rubin CI.")
        elif not np.isnan(f_stat):
            print(f"    F > 10: Instrument passes Stock-Yogo weak ID threshold.")

        # ── 2SLS ─────────────────────────────────────────────────────────
        print("\n  --- 2SLS ---")
        iv_res = run_2sls(df, outcome, f_stat)
        all_results.append(iv_res)
        print(f"    Estimate: {iv_res['estimate']:.4f}  SE: {iv_res['se_robust']:.4f}")
        print(f"    95% CI: [{iv_res['ci_lower']:.4f}, {iv_res['ci_upper']:.4f}]")
        if "ar_ci_lower" in iv_res:
            print(f"    Anderson-Rubin CI: [{iv_res['ar_ci_lower']:.4f}, {iv_res['ar_ci_upper']:.4f}]")

        # ── Effect sizes ─────────────────────────────────────────────────
        print("\n  --- Effect Sizes (2SLS) ---")
        if not np.isnan(iv_res['estimate']):
            eff = compute_effect_sizes(iv_res['estimate'], iv_res['se_robust'], df, outcome)
            print(f"    Cohen's d: {eff['cohens_d']:.3f}")
            print(f"    % change vs mean: {eff['pct_change']:.1f}%")
            if eff['large_effect_flag']:
                print(f"    *** LARGE EFFECT (>1 SD) — verify against literature ***")
            iv_res['cohens_d'] = eff['cohens_d']
            iv_res['pct_change'] = eff['pct_change']

        # ── Wald estimator cross-check ───────────────────────────────────
        print("\n  --- Wald Estimator Cross-Check ---")
        if compliance_info:
            wald_info = run_wald_crosscheck(df, outcome, compliance_info)
            if wald_info:
                print(f"    ITT:         {wald_info['itt_estimate']:.4f}")
                print(f"    Compliance:  {wald_info['compliance_rate']:.4f}")
                print(f"    Wald (ITT/compliance): {wald_info['wald_estimate']:.4f}")
                print(f"    2SLS LATE:   {iv_res['estimate']:.4f}")
                diff = abs(wald_info['wald_estimate'] - iv_res['estimate'])
                print(f"    |Wald - 2SLS|: {diff:.4f}")
                if diff > 0.01:
                    print(f"    *** DISCREPANCY > 0.01 — check specification ***")

                all_results.append({
                    "outcome": outcome, "specification": "wald_crosscheck",
                    "estimate": wald_info['wald_estimate'],
                    "se_robust": wald_info['wald_se'],
                    "pvalue": np.nan,
                    "ci_lower": wald_info['itt_estimate'],
                    "ci_upper": iv_res['estimate'],
                    "first_stage_F": f_stat,
                    "N": iv_res.get("N", 0), "method": "wald",
                })

        # ── LATE/ITT ratio ───────────────────────────────────────────────
        if (not np.isnan(ols_res['estimate']) and not np.isnan(iv_res['estimate'])
                and abs(ols_res['estimate']) > 1e-10):
                late_itt_ratio = iv_res['estimate'] / ols_res['estimate']
                print(f"\n  LATE/OLS ratio: {late_itt_ratio:.2f}")
                if abs(late_itt_ratio) > 3:
                    print(f"    *** Large ratio — LATE identifies narrow complier population ***")

        # ── Reduced form ─────────────────────────────────────────────────
        print("\n  --- Reduced Form ---")
        rf_results = run_reduced_form(df, outcome)
        for rf_res in rf_results:
            all_results.append(rf_res)
            z_name = rf_res.get("instrument", "?")
            print(f"    {z_name}: coef={rf_res['estimate']:.4f}  SE={rf_res['se_robust']:.4f}")

        # ── Multi-spec ITT (no controls / demographics / full) ───────────
        print("\n  --- ITT: Multiple Specifications ---")
        itt_results = run_multi_spec_itt(df, outcome)
        for itt_res in itt_results:
            all_results.append(itt_res)
            print(f"    {itt_res['specification']}: est={itt_res['estimate']:.4f}  "
                  f"SE={itt_res['se_robust']:.4f}  R²={itt_res.get('r_squared', 0):.4f}")

        # ── Hausman test ─────────────────────────────────────────────────
        print("\n  --- Hausman Test (OLS vs 2SLS) ---")
        h_stat, h_pval = run_hausman_test(
            df, outcome,
            ols_res["estimate"], ols_res["se_robust"],
            iv_res["estimate"], iv_res["se_robust"])
        print(f"    Hausman stat: {h_stat:.4f}  p-value: {h_pval:.4f}")
        if not np.isnan(h_pval):
            if h_pval < 0.05:
                print(f"    => Reject OLS consistency. 2SLS preferred.")
            else:
                print(f"    => Cannot reject OLS consistency.")
        all_results.append({
            "outcome": outcome, "specification": "hausman_test",
            "estimate": h_stat, "se_robust": np.nan,
            "pvalue": h_pval,
            "ci_lower": np.nan, "ci_upper": np.nan,
            "first_stage_F": f_stat,
            "N": iv_res.get("N", 0), "method": "hausman",
        })

        # ── Over-identification test ─────────────────────────────────────
        if len(INSTRUMENT_VARS) > 1:
            print("\n  --- Over-identification Test (Sargan/Hansen J) ---")
            j_stat, j_pval = run_overid_test(df, outcome)
            print(f"    J-statistic: {j_stat:.4f}  p-value: {j_pval:.4f}")
            if not np.isnan(j_pval):
                if j_pval < 0.05:
                    print(f"    => Reject: at least one instrument may be invalid.")
                else:
                    print(f"    => Cannot reject validity of instruments.")
            all_results.append({
                "outcome": outcome, "specification": "overid_test",
                "estimate": j_stat, "se_robust": np.nan,
                "pvalue": j_pval,
                "ci_lower": np.nan, "ci_upper": np.nan,
                "first_stage_F": f_stat,
                "N": iv_res.get("N", 0), "method": "sargan_hansen",
            })

        # ── Heterogeneity ────────────────────────────────────────────────
        het_vars = [h for h in HETEROGENEITY_VARS if h in df.columns] if HETEROGENEITY_VARS else []
        if het_vars:
            print(f"\n  --- Heterogeneity Analysis ---")
            for mod in het_vars:
                het_res = run_heterogeneity_iv(df, outcome, mod, f_stat)
                if het_res:
                    sig = "***" if het_res['interaction_pval'] < 0.01 else (
                        "**" if het_res['interaction_pval'] < 0.05 else (
                        "*" if het_res['interaction_pval'] < 0.10 else ""))
                    print(f"    {mod}: interaction={het_res['interaction_estimate']:.4f}  "
                          f"SE={het_res['interaction_se']:.4f}  "
                          f"p={het_res['interaction_pval']:.4f} {sig}")
                    all_results.append({
                        "outcome": outcome,
                        "specification": f"heterogeneity_{mod}",
                        "estimate": het_res['interaction_estimate'],
                        "se_robust": het_res['interaction_se'],
                        "pvalue": het_res['interaction_pval'],
                        "ci_lower": het_res['ci_lower'],
                        "ci_upper": het_res['ci_upper'],
                        "first_stage_F": f_stat,
                        "N": het_res['N'], "method": "IV_heterogeneity",
                    })
                else:
                    print(f"    {mod}: skipped (insufficient variation)")

        # ── Missing data analysis ────────────────────────────────────────
        print(f"\n  --- Missing Data Analysis ---")
        miss_info = run_missing_data_analysis(df, outcome)
        print(f"    Outcome missingness: {miss_info['outcome_miss_pct']:.1f}%")
        if miss_info['attrition_result']:
            ar = miss_info['attrition_result']
            diff_flag = " *DIFFERENTIAL*" if ar['differential'] else ""
            print(f"    Instrument predicts attrition: coef={ar['attrition_coef']:.4f}  "
                  f"p={ar['attrition_pval']:.4f}{diff_flag}")
        if miss_info['lee_bounds']:
            lb = miss_info['lee_bounds']
            print(f"    Lee bounds: [{lb['lower_bound']:.4f}, {lb['upper_bound']:.4f}]  "
                  f"(trimmed {lb['N_trimmed']} obs, {100*lb['trim_pct']:.1f}%)")
            all_results.append({
                "outcome": outcome, "specification": "lee_bounds",
                "estimate": (lb['lower_bound'] + lb['upper_bound']) / 2,
                "se_robust": np.nan, "pvalue": np.nan,
                "ci_lower": lb['lower_bound'], "ci_upper": lb['upper_bound'],
                "first_stage_F": np.nan,
                "N": iv_res.get("N", 0), "method": "lee_trimming_bounds",
            })

    # ── Actual vs expected signs ──────────────────────────────────────────
    print("\n--- Actual vs Expected Signs (2SLS) ---")
    for outcome in outcomes_present:
        iv_rows = [r for r in all_results if r["outcome"] == outcome
                   and r["specification"] == "2SLS"]
        if iv_rows:
            est = iv_rows[0]["estimate"]
            expected = EXPECTED_SIGNS.get(outcome, "?")
            actual = "+" if est > 0 else "-" if est < 0 else "0"
            match = "MATCH" if (expected == actual or expected == "?") else "MISMATCH"
            print(f"  {outcome}: expected={expected} actual={actual} {match} (est={est:.4f})")

    # ── Multiple testing correction ──────────────────────────────────────
    if len(outcomes_present) > 1:
        print("\n--- Benjamini-Hochberg FDR Correction (2SLS) ---")
        iv_results_list = [r for r in all_results if r["specification"] == "2SLS"
                           and not np.isnan(r["pvalue"])]
        if len(iv_results_list) > 1:
            pvals = np.array([r["pvalue"] for r in iv_results_list])
            n_p = len(pvals)
            ranked = np.argsort(pvals)
            adj = np.empty(n_p)
            for i, rank_idx in enumerate(reversed(ranked)):
                rank = n_p - i
                if i == 0:
                    adj[rank_idx] = pvals[rank_idx]
                else:
                    adj[rank_idx] = min(pvals[rank_idx] * n_p / rank,
                                        adj[ranked[n_p - i]])
            adj = np.minimum(adj, 1.0)
            for i, r in enumerate(iv_results_list):
                r["pvalue_bh"] = adj[i]
                print(f"  {r['outcome']}: p={r['pvalue']:.4f} -> p_BH={adj[i]:.4f}")

    # ── Save results ──────────────────────────────────────────────────────
    results_df = pd.DataFrame(all_results)
    out_path = os.path.join(DATA_DIR, "main_results.csv")
    results_df.to_csv(out_path, index=False)
    print(f"\nSaved: {out_path} ({len(results_df)} rows)")

    # ── Verify no NaN in critical columns ─────────────────────────────────
    for col in ["estimate", "ci_lower", "ci_upper"]:
        if col in results_df.columns:
            n_nan = results_df[col].isna().sum()
            if n_nan > 0:
                print(f"  WARNING: {n_nan} NaN values in '{col}' — check estimator output")

    print("\n" + "=" * 70)
    print("01_main.py complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
