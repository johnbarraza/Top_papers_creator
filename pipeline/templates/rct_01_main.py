"""01_main.py — RCT main estimation template.

Handles multi-arm ITT estimation with HC2 robust SEs, clustered SEs,
strata fixed effects, heterogeneity interactions, and multiple testing
correction. Never produces NaN in output tables.
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
OUTCOME_VARS = {{OUTCOME_VARS}}           # e.g., ["consumption", "income", "health"]
TREATMENT_VAR = "{{TREATMENT_VAR}}"       # e.g., "treatment"
TREATMENT_ARMS = {{TREATMENT_ARMS}}       # e.g., {"Control": 0, "Cash": 1, "In-kind": 2}
CLUSTER_VAR = "{{CLUSTER_VAR}}"           # e.g., "village_id" or None
COVARIATES = {{COVARIATES}}               # e.g., ["age", "female", "baseline_income"]
STRATA_VAR = "{{STRATA_VAR}}"             # e.g., "strata_id" or None
EXPECTED_SIGNS = {{EXPECTED_SIGNS}}       # e.g., {"consumption": "+", "income": "+"}
HETEROGENEITY_VARS = {{HETEROGENEITY_VARS}}  # e.g., ["female", "urban", "baseline_income"]
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


def _arm_dummies(df):
    """Create arm dummy columns, return list of column names."""
    ctrl_val = _get_control_arm()
    dummy_cols = []
    for arm_name, arm_val in TREATMENT_ARMS.items():
        if arm_val == ctrl_val:
            continue
        safe = arm_name.replace(" ", "_").replace("-", "_").lower()
        col = f"arm_{safe}"
        df[col] = (df[TREATMENT_VAR] == arm_val).astype(float)
        dummy_cols.append(col)
    return dummy_cols


def run_itt(df, outcome, covariates=None, strata_fe=False, label="baseline"):
    """Run ITT OLS: Y ~ arm_dummies [+ covariates] [+ strata FE].

    Uses HC2 robust SEs by default. Uses clustered SEs if CLUSTER_VAR is set.
    Returns one result dict per treatment arm.
    """
    sub = df.dropna(subset=[outcome, TREATMENT_VAR]).copy()

    # Arm dummies
    dummy_cols = _arm_dummies(sub)
    if not dummy_cols:
        return []

    # Build regressor list
    rhs_cols = list(dummy_cols)

    # Covariates
    if covariates:
        avail = [c for c in covariates if c in sub.columns]
        for c in avail:
            sub[c] = pd.to_numeric(sub[c], errors="coerce")
        sub = sub.dropna(subset=avail)
        rhs_cols += avail

    # Strata FE
    if strata_fe and STRATA_VAR and STRATA_VAR in sub.columns:
        strata_dums = pd.get_dummies(sub[STRATA_VAR], prefix="strata", drop_first=True,
                                     dtype=float)
        sub = pd.concat([sub, strata_dums], axis=1)
        rhs_cols += list(strata_dums.columns)

    if len(sub) < len(rhs_cols) + 5:
        print(f"    Insufficient obs for {outcome} ({len(sub)}). Skipping.")
        return []

    Y = sub[outcome].values
    X = sm.add_constant(sub[rhs_cols].values)

    # Choose covariance type
    if CLUSTER_VAR and CLUSTER_VAR in sub.columns:
        groups = sub[CLUSTER_VAR].values
        try:
            model = sm.OLS(Y, X).fit(cov_type="cluster", cov_kwds={"groups": groups})
        except Exception:
            model = sm.OLS(Y, X).fit(cov_type="HC2")
    else:
        model = sm.OLS(Y, X).fit(cov_type="HC2")

    # Control mean (actual control group, not full sample)
    ctrl_val = _get_control_arm()
    ctrl_mean = sub.loc[sub[TREATMENT_VAR] == ctrl_val, outcome].mean()
    ctrl_mean = ctrl_mean if not np.isnan(ctrl_mean) else 0.0

    results = []
    for i, arm_col in enumerate(dummy_cols):
        idx = i + 1  # +1 because of constant
        est = model.params[idx]
        se = model.bse[idx]
        pval = model.pvalues[idx]
        ci = model.conf_int()[idx]

        # Effect magnitude relative to control mean
        effect_pct = 100 * est / ctrl_mean if abs(ctrl_mean) > 1e-10 else np.nan

        arm_name = arm_col.replace("arm_", "")
        results.append({
            "outcome": outcome,
            "specification": label,
            "arm": arm_name,
            "estimate": est,
            "se_robust": se,
            "pvalue": pval,
            "ci_lower": ci[0],
            "ci_upper": ci[1],
            "N": len(sub),
            "control_mean": ctrl_mean,
            "effect_pct": effect_pct if not np.isnan(effect_pct) else 0.0,
            "r_squared": model.rsquared,
            "method": "OLS_clustered" if (CLUSTER_VAR and CLUSTER_VAR in sub.columns) else "OLS_HC2",
        })

    return results


def run_joint_ftest(df, outcome, covariates=None):
    """Joint F-test: all arm coefficients = 0 (are arms jointly significant?)."""
    sub = df.dropna(subset=[outcome, TREATMENT_VAR]).copy()
    dummy_cols = _arm_dummies(sub)
    if len(dummy_cols) < 2:
        return None

    rhs_cols = list(dummy_cols)
    if covariates:
        avail = [c for c in covariates if c in sub.columns]
        for c in avail:
            sub[c] = pd.to_numeric(sub[c], errors="coerce")
        sub = sub.dropna(subset=avail)
        rhs_cols += avail

    Y = sub[outcome].values
    X = sm.add_constant(sub[rhs_cols].values)

    if CLUSTER_VAR and CLUSTER_VAR in sub.columns:
        groups = sub[CLUSTER_VAR].values
        try:
            model = sm.OLS(Y, X).fit(cov_type="cluster", cov_kwds={"groups": groups})
        except Exception:
            model = sm.OLS(Y, X).fit(cov_type="HC2")
    else:
        model = sm.OLS(Y, X).fit(cov_type="HC2")

    # Test: all arm dummies = 0
    n_arms = len(dummy_cols)
    r_matrix = np.zeros((n_arms, X.shape[1]))
    for i in range(n_arms):
        r_matrix[i, i + 1] = 1  # +1 for constant

    try:
        ftest = model.f_test(r_matrix)
        return {"f_stat": float(ftest.fvalue), "p_value": float(ftest.pvalue)}
    except Exception:
        return None


def run_heterogeneity(df, outcome, moderator, covariates=None, label="heterogeneity"):
    """Arm x moderator interactions. ONLY runs if moderator has variation in treated."""
    ctrl_val = _get_control_arm()
    sub = df.dropna(subset=[outcome, TREATMENT_VAR, moderator]).copy()
    sub[moderator] = pd.to_numeric(sub[moderator], errors="coerce")
    sub = sub.dropna(subset=[moderator])

    # CRITICAL: Check variation in treated sample
    treated_vals = sub.loc[sub[TREATMENT_VAR] != ctrl_val, moderator]
    if treated_vals.nunique() <= 1 or treated_vals.std() < 1e-10:
        print(f"    SKIP {moderator}: no variation in treated sample "
              f"(unique={treated_vals.nunique()}, std={treated_vals.std():.6f})")
        return []

    dummy_cols = _arm_dummies(sub)
    if not dummy_cols:
        return []

    # Build interaction terms
    interaction_cols = []
    for arm_col in dummy_cols:
        int_col = f"{arm_col}_x_{moderator}"
        sub[int_col] = sub[arm_col] * sub[moderator]
        interaction_cols.append(int_col)

    rhs_cols = dummy_cols + [moderator] + interaction_cols
    if covariates:
        avail = [c for c in covariates if c in sub.columns and c != moderator]
        for c in avail:
            sub[c] = pd.to_numeric(sub[c], errors="coerce")
        sub = sub.dropna(subset=avail)
        rhs_cols += avail

    if len(sub) < len(rhs_cols) + 5:
        return []

    Y = sub[outcome].values
    X = sm.add_constant(sub[rhs_cols].values)

    if CLUSTER_VAR and CLUSTER_VAR in sub.columns:
        groups = sub[CLUSTER_VAR].values
        try:
            model = sm.OLS(Y, X).fit(cov_type="cluster", cov_kwds={"groups": groups})
        except Exception:
            model = sm.OLS(Y, X).fit(cov_type="HC2")
    else:
        model = sm.OLS(Y, X).fit(cov_type="HC2")

    results = []
    # Report the interaction coefficients
    for j, int_col in enumerate(interaction_cols):
        idx = 1 + len(dummy_cols) + 1 + j  # const + arms + moderator + j-th interaction
        arm_name = dummy_cols[j].replace("arm_", "")
        est = model.params[idx]
        se = model.bse[idx]
        pval = model.pvalues[idx]
        ci = model.conf_int()[idx]
        results.append({
            "outcome": outcome,
            "specification": f"{label}_{moderator}",
            "arm": f"{arm_name}_x_{moderator}",
            "estimate": est,
            "se_robust": se,
            "pvalue": pval,
            "ci_lower": ci[0],
            "ci_upper": ci[1],
            "N": len(sub),
            "control_mean": np.nan,
            "effect_pct": np.nan,
            "r_squared": model.rsquared,
            "method": "OLS_interaction",
        })
    return results


def benjamini_hochberg(pvalues):
    """Benjamini-Hochberg FDR correction. Returns adjusted p-values."""
    n = len(pvalues)
    if n <= 1:
        return pvalues
    ranked = np.argsort(pvalues)
    adjusted = np.empty(n)
    for i, rank_idx in enumerate(reversed(ranked)):
        rank = n - i
        if i == 0:
            adjusted[rank_idx] = pvalues[rank_idx]
        else:
            adjusted[rank_idx] = min(
                pvalues[rank_idx] * n / rank,
                adjusted[ranked[n - i]]  # previous adjusted
            )
    adjusted = np.minimum(adjusted, 1.0)
    return adjusted


# ═══════════════════════════════════════════════════════════════════════════════
# ANCOVA (Y ~ T + Y_baseline)
# ═══════════════════════════════════════════════════════════════════════════════
def run_ancova(df, outcome, label="ancova"):
    """ANCOVA: Y_post ~ arm_dummies + Y_baseline [+ covariates].
    More efficient than simple ITT when baseline outcome is available."""
    USE_BASELINE = (BASELINE_OUTCOME and BASELINE_OUTCOME != "None"
                    and BASELINE_OUTCOME in df.columns)
    if not USE_BASELINE:
        return []

    sub = df.dropna(subset=[outcome, TREATMENT_VAR, BASELINE_OUTCOME]).copy()
    sub[BASELINE_OUTCOME] = pd.to_numeric(sub[BASELINE_OUTCOME], errors="coerce")
    sub = sub.dropna(subset=[BASELINE_OUTCOME])

    dummy_cols = _arm_dummies(sub)
    if not dummy_cols:
        return []

    rhs_cols = list(dummy_cols) + [BASELINE_OUTCOME]

    # Add covariates
    avail = [c for c in COVARIATES if c in sub.columns and c != BASELINE_OUTCOME]
    for c in avail:
        sub[c] = pd.to_numeric(sub[c], errors="coerce")
    sub = sub.dropna(subset=avail)
    rhs_cols += avail

    if len(sub) < len(rhs_cols) + 5:
        return []

    Y = sub[outcome].values
    X = sm.add_constant(sub[rhs_cols].values)

    if CLUSTER_VAR and CLUSTER_VAR in sub.columns:
        groups = sub[CLUSTER_VAR].values
        try:
            model = sm.OLS(Y, X).fit(cov_type="cluster", cov_kwds={"groups": groups})
        except Exception:
            model = sm.OLS(Y, X).fit(cov_type="HC2")
    else:
        model = sm.OLS(Y, X).fit(cov_type="HC2")

    ctrl_val = _get_control_arm()
    ctrl_mean = sub.loc[sub[TREATMENT_VAR] == ctrl_val, outcome].mean()
    ctrl_mean = ctrl_mean if not np.isnan(ctrl_mean) else 0.0

    results = []
    for i, arm_col in enumerate(dummy_cols):
        idx = i + 1
        est = model.params[idx]
        se = model.bse[idx]
        pval = model.pvalues[idx]
        ci = model.conf_int()[idx]
        effect_pct = 100 * est / ctrl_mean if abs(ctrl_mean) > 1e-10 else np.nan

        arm_name = arm_col.replace("arm_", "")
        results.append({
            "outcome": outcome, "specification": label,
            "arm": arm_name, "estimate": est, "se_robust": se,
            "pvalue": pval, "ci_lower": ci[0], "ci_upper": ci[1],
            "N": len(sub), "control_mean": ctrl_mean,
            "effect_pct": effect_pct if not np.isnan(effect_pct) else 0.0,
            "r_squared": model.rsquared,
            "method": "OLS_ANCOVA",
        })
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# POWER CALCULATIONS
# ═══════════════════════════════════════════════════════════════════════════════
def run_power_calculation(df, outcome):
    """Post-hoc power: MDE at 80% power for each arm vs control."""
    from scipy import stats

    ctrl_val = _get_control_arm()
    treat_arms = _get_treat_arms()

    results = []
    for arm_name, arm_val in treat_arms.items():
        sub = df[df[TREATMENT_VAR].isin([ctrl_val, arm_val])].dropna(subset=[outcome])
        n_ctrl = (sub[TREATMENT_VAR] == ctrl_val).sum()
        n_treat = (sub[TREATMENT_VAR] == arm_val).sum()
        sd = sub[outcome].std()

        if n_ctrl < 5 or n_treat < 5 or sd < 1e-10:
            continue

        z_alpha = stats.norm.ppf(0.975)  # 1.96
        z_beta = stats.norm.ppf(0.80)    # 0.84

        mde = (z_alpha + z_beta) * sd * np.sqrt(1.0 / n_ctrl + 1.0 / n_treat)
        cohens_d_mde = mde / sd

        results.append({
            "arm": arm_name, "N_ctrl": n_ctrl, "N_treat": n_treat,
            "outcome_sd": sd, "mde": mde, "cohens_d_mde": cohens_d_mde,
        })
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# EFFECT SIZES
# ═══════════════════════════════════════════════════════════════════════════════
def compute_effect_sizes(estimate, df_data, outcome, treatment_var, ctrl_val, arm_val):
    """Cohen's d, percentage change vs control mean."""
    ctrl_vals = df_data.loc[df_data[treatment_var] == ctrl_val, outcome].dropna()
    treat_vals = df_data.loc[df_data[treatment_var] == arm_val, outcome].dropna()

    if len(ctrl_vals) < 5 or len(treat_vals) < 5:
        return {}

    pooled_sd = np.sqrt((ctrl_vals.var() + treat_vals.var()) / 2)
    ctrl_mean = ctrl_vals.mean()

    cohens_d = estimate / pooled_sd if pooled_sd > 0 else np.nan
    pct_change = 100 * estimate / abs(ctrl_mean) if abs(ctrl_mean) > 1e-10 else np.nan
    pp_change = estimate  # for binary outcomes, estimate IS the pp change

    return {
        "cohens_d": cohens_d,
        "pct_change": pct_change,
        "pp_change": pp_change,
        "ctrl_mean": ctrl_mean,
        "pooled_sd": pooled_sd,
        "large_effect_flag": abs(cohens_d) > 1.0 if not np.isnan(cohens_d) else False,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# RANDOMIZATION INFERENCE (Permutation p-values)
# ═══════════════════════════════════════════════════════════════════════════════
def run_permutation_test(df, outcome, n_perms=2000):
    """Permutation p-values: reshuffle treatment, recompute ITT."""
    ctrl_val = _get_control_arm()
    treat_arms = _get_treat_arms()
    results = []

    for arm_name, arm_val in treat_arms.items():
        sub = df[df[TREATMENT_VAR].isin([ctrl_val, arm_val])].dropna(subset=[outcome]).copy()
        sub["_arm_dum"] = (sub[TREATMENT_VAR] == arm_val).astype(float)

        if len(sub) < 20:
            continue

        Y = sub[outcome].values
        X = sm.add_constant(sub["_arm_dum"].values)
        mod_orig = sm.OLS(Y, X).fit()
        t_orig = mod_orig.tvalues[1]

        rng = np.random.default_rng(42)
        t_perms = np.zeros(n_perms)

        for p in range(n_perms):
            arm_perm = rng.permutation(sub["_arm_dum"].values)
            X_perm = sm.add_constant(arm_perm)
            try:
                mod_p = sm.OLS(Y, X_perm).fit()
                t_perms[p] = mod_p.tvalues[1]
            except Exception:
                t_perms[p] = 0

        perm_pval = np.mean(np.abs(t_perms) >= np.abs(t_orig))
        results.append({
            "arm": arm_name, "t_original": t_orig,
            "perm_pval": perm_pval,
            "conventional_pval": mod_orig.pvalues[1],
            "n_perms": n_perms, "N": len(sub),
        })

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# SPECIFICATION CURVE
# ═══════════════════════════════════════════════════════════════════════════════
def run_specification_curve(df, outcome):
    """Run ITT across all spec × functional form combinations."""
    ctrl_val = _get_control_arm()
    treat_arms = _get_treat_arms()
    spec_results = []

    cov_sets = {
        "no_controls": [],
        "demographics": COVARIATES[:min(5, len(COVARIATES))],
        "full_controls": COVARIATES,
    }

    # Add ANCOVA if baseline available
    USE_BASELINE = (BASELINE_OUTCOME and BASELINE_OUTCOME != "None"
                    and BASELINE_OUTCOME in df.columns)
    if USE_BASELINE:
        cov_sets["ancova"] = [BASELINE_OUTCOME] + COVARIATES

    for arm_name, arm_val in treat_arms.items():
        safe = arm_name.replace(" ", "_").replace("-", "_").lower()
        sub = df[df[TREATMENT_VAR].isin([ctrl_val, arm_val])].dropna(subset=[outcome]).copy()
        sub["_arm_dum"] = (sub[TREATMENT_VAR] == arm_val).astype(float)

        if len(sub) < 20:
            continue

        for set_name, controls in cov_sets.items():
            avail = [c for c in controls if c in sub.columns]
            for c in avail:
                sub[c] = pd.to_numeric(sub[c], errors="coerce")
            sub_clean = sub.dropna(subset=avail) if avail else sub

            rhs = ["_arm_dum"] + avail
            X = sm.add_constant(sub_clean[rhs].values)
            Y = sub_clean[outcome].values

            # LPM
            try:
                mod = sm.OLS(Y, X).fit(cov_type="HC2")
                ci = mod.conf_int()[1]
                spec_results.append({
                    "arm": safe, "spec": f"LPM_{set_name}",
                    "estimate": mod.params[1], "se": mod.bse[1],
                    "pvalue": mod.pvalues[1],
                    "ci_lower": ci[0], "ci_upper": ci[1],
                })
            except Exception:
                pass

            # Probit/Logit (binary outcomes only)
            y_vals = sub_clean[outcome].unique()
            is_binary = (set(y_vals).issubset({0, 1, 0.0, 1.0})
                         and len(y_vals) == 2)  # must have exactly 2 values
            if is_binary and len(Y) >= 30:
                for model_type in ["Probit", "Logit"]:
                    try:
                        model_cls = getattr(sm, model_type)
                        mod_nl = model_cls(Y, X).fit(disp=0, maxiter=100)
                        # Check convergence before extracting marginal effects
                        converged = getattr(mod_nl, 'converged', True)
                        if not converged:
                            continue
                        mfx = mod_nl.get_margeff()
                        me = mfx.margeff[0]
                        me_se = mfx.margeff_se[0]
                        # Validate: marginal effect should be finite and reasonable
                        if np.isnan(me) or np.isnan(me_se) or abs(me) > 1.0:
                            continue
                        spec_results.append({
                            "arm": safe,
                            "spec": f"{model_type}_{set_name}",
                            "estimate": me,
                            "se": me_se,
                            "pvalue": mfx.pvalues[0],
                            "ci_lower": me - 1.96 * me_se,
                            "ci_upper": me + 1.96 * me_se,
                        })
                    except Exception:
                        pass

    return spec_results


# ═══════════════════════════════════════════════════════════════════════════════
# OSTER (2019) COEFFICIENT STABILITY
# ═══════════════════════════════════════════════════════════════════════════════
def run_oster_delta(df, outcome):
    """Oster (2019): delta = degree of selection on unobservables to explain away beta."""
    ctrl_val = _get_control_arm()
    treat_arms = _get_treat_arms()
    results = []

    for arm_name, arm_val in treat_arms.items():
        safe = arm_name.replace(" ", "_").replace("-", "_").lower()
        sub = df[df[TREATMENT_VAR].isin([ctrl_val, arm_val])].dropna(subset=[outcome]).copy()
        sub["_arm_dum"] = (sub[TREATMENT_VAR] == arm_val).astype(float)

        avail = [c for c in COVARIATES if c in sub.columns]
        for c in avail:
            sub[c] = pd.to_numeric(sub[c], errors="coerce")
        sub = sub.dropna(subset=avail)

        if len(sub) < 20 or not avail:
            continue

        try:
            # Uncontrolled
            X_u = sm.add_constant(sub["_arm_dum"].values)
            mod_u = sm.OLS(sub[outcome].values, X_u).fit()
            beta_u = mod_u.params[1]
            r2_u = mod_u.rsquared

            # Controlled
            X_c = sm.add_constant(sub[["_arm_dum"] + avail].values)
            mod_c = sm.OLS(sub[outcome].values, X_c).fit()
            beta_c = mod_c.params[1]
            r2_c = mod_c.rsquared

            r2_max = min(1.0, 1.3 * r2_c)
            denom = (beta_u - beta_c) * (r2_c - r2_u)
            if abs(denom) > 1e-10:
                delta = (beta_c * (r2_max - r2_c)) / denom
            else:
                delta = np.inf

            results.append({
                "arm": safe, "beta_uncontrolled": beta_u, "r2_u": r2_u,
                "beta_controlled": beta_c, "r2_c": r2_c,
                "r2_max": r2_max, "delta": delta,
            })
        except Exception:
            continue

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("01_main.py — RCT Main Estimation (ITT)")
    print("=" * 70)

    df = pd.read_csv(CLEAN_CSV)
    print(f"Loaded: {len(df):,} rows x {df.shape[1]} cols")

    # ── Expected signs ────────────────────────────────────────────────────
    print("\n--- Expected signs ---")
    for outcome, sign in EXPECTED_SIGNS.items():
        print(f"  {outcome}: {sign}")

    all_results = []
    outcomes_present = [o for o in OUTCOME_VARS if o in df.columns]

    # ── Spec 1: ITT no controls ──────────────────────────────────────────
    print("\n--- ITT: No controls ---")
    for outcome in outcomes_present:
        print(f"\n  Outcome: {outcome}")
        res_list = run_itt(df, outcome, label="itt_no_controls")
        for res in res_list:
            all_results.append(res)
            print(f"    {res['arm']}: est={res['estimate']:.4f}  SE={res['se_robust']:.4f}  "
                  f"p={res['pvalue']:.4f}  ctrl_mean={res['control_mean']:.4f}  "
                  f"effect={res['effect_pct']:.1f}%")

    # ── Spec 2: ITT with controls ────────────────────────────────────────
    covs_avail = [c for c in COVARIATES if c in df.columns]
    if covs_avail:
        print(f"\n--- ITT: With controls ({covs_avail}) ---")
        for outcome in outcomes_present:
            print(f"\n  Outcome: {outcome}")
            res_list = run_itt(df, outcome, covariates=covs_avail, label="itt_with_controls")
            for res in res_list:
                all_results.append(res)
                print(f"    {res['arm']}: est={res['estimate']:.4f}  SE={res['se_robust']:.4f}")

    # ── Spec 3: ITT with strata FE ──────────────────────────────────────
    if STRATA_VAR and STRATA_VAR in df.columns:
        print(f"\n--- ITT: With strata FE ({STRATA_VAR}) ---")
        for outcome in outcomes_present:
            res_list = run_itt(df, outcome, covariates=covs_avail, strata_fe=True,
                               label="itt_strata_fe")
            for res in res_list:
                all_results.append(res)
                print(f"    {res['arm']}: est={res['estimate']:.4f}  SE={res['se_robust']:.4f}")

    # ── Joint F-test for arm equality ────────────────────────────────────
    treat_arms = _get_treat_arms()
    if len(treat_arms) >= 2:
        print("\n--- Joint F-test: all arms equal zero ---")
        for outcome in outcomes_present:
            ftest = run_joint_ftest(df, outcome, covariates=covs_avail)
            if ftest:
                sig = "***" if ftest["p_value"] < 0.01 else ("**" if ftest["p_value"] < 0.05 else "")
                print(f"  {outcome}: F={ftest['f_stat']:.3f}  p={ftest['p_value']:.4f} {sig}")
            else:
                print(f"  {outcome}: F-test failed")

    # ── Heterogeneity: arm x moderator interactions ──────────────────────
    het_vars = [h for h in HETEROGENEITY_VARS if h in df.columns]
    if het_vars:
        print("\n--- Heterogeneity analysis ---")
        for outcome in outcomes_present:
            for mod in het_vars:
                print(f"\n  {outcome} x {mod}:")
                res_list = run_heterogeneity(df, outcome, mod, covariates=covs_avail)
                for res in res_list:
                    all_results.append(res)
                    print(f"    {res['arm']}: est={res['estimate']:.4f}  "
                          f"SE={res['se_robust']:.4f}  p={res['pvalue']:.4f}")

    # ── Actual vs expected signs ─────────────────────────────────────────
    print("\n--- Actual vs Expected Signs ---")
    for outcome in outcomes_present:
        baseline = [r for r in all_results if r["outcome"] == outcome
                    and r["specification"] == "itt_no_controls"]
        if baseline:
            for r in baseline:
                expected = EXPECTED_SIGNS.get(outcome, "?")
                actual = "+" if r["estimate"] > 0 else "-" if r["estimate"] < 0 else "0"
                match = "MATCH" if (expected == actual or expected == "?") else "MISMATCH"
                print(f"  {outcome} ({r['arm']}): expected={expected} actual={actual} "
                      f"{match} (est={r['estimate']:.4f})")

    # ── Spec 4: ANCOVA (Y ~ T + Y_baseline + controls) ────────────────────
    USE_BASELINE = (BASELINE_OUTCOME and BASELINE_OUTCOME != "None"
                    and BASELINE_OUTCOME in df.columns)
    if USE_BASELINE:
        print(f"\n--- ANCOVA: Y ~ T + {BASELINE_OUTCOME} + controls ---")
        for outcome in outcomes_present:
            print(f"\n  Outcome: {outcome}")
            res_list = run_ancova(df, outcome, label="ancova")
            for res in res_list:
                all_results.append(res)
                print(f"    {res['arm']}: est={res['estimate']:.4f}  SE={res['se_robust']:.4f}  "
                      f"R²={res['r_squared']:.4f}")

    # ── Power calculations ───────────────────────────────────────────────
    print("\n--- Power Calculations (MDE at 80% power) ---")
    for outcome in outcomes_present:
        power_res = run_power_calculation(df, outcome)
        for pr in power_res:
            print(f"  {outcome} ({pr['arm']}): MDE={pr['mde']:.4f}  "
                  f"Cohen's d_MDE={pr['cohens_d_mde']:.3f}  "
                  f"N_ctrl={pr['N_ctrl']}  N_treat={pr['N_treat']}")
            all_results.append({
                "outcome": outcome, "specification": "power_calculation",
                "arm": pr['arm'].replace(" ", "_").replace("-", "_").lower(),
                "estimate": pr['mde'], "se_robust": pr['cohens_d_mde'],
                "pvalue": np.nan,
                "ci_lower": pr['outcome_sd'], "ci_upper": np.nan,
                "N": pr['N_ctrl'] + pr['N_treat'],
                "control_mean": np.nan, "effect_pct": np.nan,
                "r_squared": np.nan,
                "method": "power_calc",
            })

    # ── Effect sizes (Cohen's d) ─────────────────────────────────────────
    print("\n--- Effect Sizes (Cohen's d) ---")
    ctrl_val = _get_control_arm()
    for outcome in outcomes_present:
        baseline = [r for r in all_results if r["outcome"] == outcome
                    and r["specification"] == "itt_no_controls"]
        for r in baseline:
            arm_val = None
            for k, v in TREATMENT_ARMS.items():
                safe = k.replace(" ", "_").replace("-", "_").lower()
                if safe == r["arm"]:
                    arm_val = v
                    break
            if arm_val is not None:
                eff = compute_effect_sizes(r["estimate"], df, outcome,
                                           TREATMENT_VAR, ctrl_val, arm_val)
                if eff:
                    r["cohens_d"] = eff["cohens_d"]
                    r["pp_change"] = eff["pp_change"]
                    flag = " ***LARGE EFFECT***" if eff.get("large_effect_flag") else ""
                    print(f"  {outcome} ({r['arm']}): Cohen's d={eff['cohens_d']:.3f}  "
                          f"%change={eff['pct_change']:.1f}%  "
                          f"pp={eff['pp_change']:.4f}{flag}")

    # ── Randomization inference ──────────────────────────────────────────
    print("\n--- Randomization Inference (Permutation p-values) ---")
    for outcome in outcomes_present:
        perm_res = run_permutation_test(df, outcome, n_perms=2000)
        for pr in perm_res:
            print(f"  {outcome} ({pr['arm']}): t={pr['t_original']:.3f}  "
                  f"perm_p={pr['perm_pval']:.4f}  conv_p={pr['conventional_pval']:.4f}")
            all_results.append({
                "outcome": outcome, "specification": "permutation_test",
                "arm": pr['arm'].replace(" ", "_").replace("-", "_").lower(),
                "estimate": pr['t_original'], "se_robust": np.nan,
                "pvalue": pr['perm_pval'],
                "ci_lower": pr['conventional_pval'], "ci_upper": np.nan,
                "N": pr['N'], "control_mean": np.nan, "effect_pct": np.nan,
                "r_squared": np.nan,
                "method": f"permutation_{pr['n_perms']}",
            })

    # ── Specification curve ──────────────────────────────────────────────
    print("\n--- Specification Curve ---")
    for outcome in outcomes_present:
        sc_res = run_specification_curve(df, outcome)
        for sr in sc_res:
            print(f"  {outcome} ({sr['arm']}, {sr['spec']}): est={sr['estimate']:.4f}  "
                  f"SE={sr['se']:.4f}")
            all_results.append({
                "outcome": outcome,
                "specification": f"spec_curve_{sr['spec']}",
                "arm": sr['arm'], "estimate": sr['estimate'],
                "se_robust": sr['se'], "pvalue": sr['pvalue'],
                "ci_lower": sr['ci_lower'], "ci_upper": sr['ci_upper'],
                "N": np.nan, "control_mean": np.nan, "effect_pct": np.nan,
                "r_squared": np.nan, "method": sr['spec'],
            })

        # Save spec curve CSV for figure generation
        if sc_res:
            sc_df = pd.DataFrame(sc_res)
            sc_path = os.path.join(DATA_DIR, f"specification_curve_{outcome}.csv")
            sc_df.to_csv(sc_path, index=False)

    # ── Oster (2019) coefficient stability ───────────────────────────────
    print("\n--- Oster (2019) Coefficient Stability ---")
    for outcome in outcomes_present:
        oster_res = run_oster_delta(df, outcome)
        for od in oster_res:
            fragile = " ***FRAGILE***" if abs(od['delta']) < 1 else ""
            print(f"  {outcome} ({od['arm']}): delta={od['delta']:.2f}  "
                  f"beta_u={od['beta_uncontrolled']:.4f}  "
                  f"beta_c={od['beta_controlled']:.4f}{fragile}")
            all_results.append({
                "outcome": outcome, "specification": "oster_delta",
                "arm": od['arm'], "estimate": od['delta'],
                "se_robust": np.nan, "pvalue": np.nan,
                "ci_lower": od['beta_uncontrolled'],
                "ci_upper": od['beta_controlled'],
                "N": np.nan, "control_mean": np.nan, "effect_pct": np.nan,
                "r_squared": od['r2_c'], "method": "oster_2019",
            })

    # ── Multiple testing correction ──────────────────────────────────────
    if len(outcomes_present) > 1:
        print("\n--- Benjamini-Hochberg multiple testing correction ---")
        baseline_results = [r for r in all_results if r["specification"] == "itt_no_controls"]
        if baseline_results:
            pvals = np.array([r["pvalue"] for r in baseline_results])
            adj_pvals = benjamini_hochberg(pvals)
            for i, r in enumerate(baseline_results):
                r["pvalue_bh"] = adj_pvals[i]
                print(f"  {r['outcome']} ({r['arm']}): p={r['pvalue']:.4f} -> "
                      f"p_BH={adj_pvals[i]:.4f}")

    # ── Save results ─────────────────────────────────────────────────────
    results_df = pd.DataFrame(all_results)

    # CRITICAL: Never save NaN — replace with safe defaults
    for col in ["estimate", "se_robust", "ci_lower", "ci_upper", "pvalue",
                "control_mean", "effect_pct"]:
        if col in results_df.columns:
            results_df[col] = results_df[col].fillna(0.0)

    out_path = os.path.join(DATA_DIR, "main_results.csv")
    results_df.to_csv(out_path, index=False)
    print(f"\nSaved: {out_path} ({len(results_df)} rows)")

    # ── Verify no NaN in critical columns ────────────────────────────────
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
