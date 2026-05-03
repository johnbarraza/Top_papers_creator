"""01_main.py — DiD main estimation template.

Uses linearmodels PanelOLS for TWFE (NOT pyfixest feols).
Handles both standard 2-period DiD and staggered adoption designs.
Always produces complete results (no blank cells in tables).
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
OUTCOME_VARS = {{OUTCOME_VARS}}           # e.g., ["employment", "wages"]
ENTITY_VAR = "{{ENTITY_VAR}}"            # e.g., "state_id"
TIME_VAR = "{{TIME_VAR}}"                # e.g., "year"
TREATMENT_VAR = "treat"                   # always use constructed version
CLUSTER_VAR = "{{CLUSTER_VAR}}"          # e.g., "state_id" (cluster SEs at entity level)
COVARIATES = {{COVARIATES}}               # e.g., ["population", "gdp_pc"]
EXPECTED_SIGNS = {{EXPECTED_SIGNS}}       # e.g., {"employment": "+", "wages": "?"}
FIRST_TREAT_VAR = "{{FIRST_TREAT_VAR}}"  # e.g., "first_treat_year" or "None"
HETEROGENEITY_VARS = {{HETEROGENEITY_VARS}}  # e.g., ["female", "urban"]

# ═══════════════════════════════════════════════════════════════════════════════
# FIXED CODE
# ═══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "..", "data", "clean")
CLEAN_CSV = os.path.join(DATA_DIR, "clean_data.csv")

# ── Try to import linearmodels, install if needed ────────────────────────────
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
        print("linearmodels installed successfully.")
    except Exception:
        print("WARNING: linearmodels not available. Using statsmodels fallback.")

# ── Statsmodels fallback import ──────────────────────────────────────────────
import statsmodels.api as sm


def _safe_float(val, default=np.nan):
    """Safely convert to float, return default on failure."""
    try:
        v = float(val)
        return v if not np.isnan(v) else default
    except (ValueError, TypeError):
        return default


def run_twfe_panelols(df, outcome, covariates=None, label="twfe"):
    """Run TWFE DiD using linearmodels PanelOLS with entity + time FE.

    Y_it = alpha_i + gamma_t + beta * treat_it + X_it * delta + epsilon_it
    Clustered SEs at entity level.
    """
    sub = df.dropna(subset=[outcome, TREATMENT_VAR, ENTITY_VAR, TIME_VAR]).copy()

    if len(sub) < 20:
        return _empty_result(outcome, label, len(sub))

    # Build formula components
    exog_vars = [TREATMENT_VAR]
    if covariates:
        avail_covs = [c for c in covariates if c in sub.columns]
        # Drop covariates with zero variance
        avail_covs = [c for c in avail_covs if sub[c].std() > 0]
        exog_vars += avail_covs

    # Drop rows with missing covariates
    sub = sub.dropna(subset=exog_vars)
    if len(sub) < 20:
        return _empty_result(outcome, label, len(sub))

    # Set panel index
    sub = sub.set_index([ENTITY_VAR, TIME_VAR])

    y = sub[outcome]
    X = sub[exog_vars]

    try:
        mod = PanelOLS(y, X, entity_effects=True, time_effects=True,
                       drop_absorbed=True, check_rank=False)

        # Cluster at entity level
        if CLUSTER_VAR == ENTITY_VAR:
            fit = mod.fit(cov_type="clustered", cluster_entity=True)
        else:
            # If cluster var differs from entity, cluster manually
            if CLUSTER_VAR in sub.columns:
                fit = mod.fit(cov_type="clustered", clusters=sub[CLUSTER_VAR])
            else:
                fit = mod.fit(cov_type="clustered", cluster_entity=True)

        estimate = _safe_float(fit.params.get(TREATMENT_VAR, np.nan))
        se = _safe_float(fit.std_errors.get(TREATMENT_VAR, np.nan))
        pval = _safe_float(fit.pvalues.get(TREATMENT_VAR, np.nan))

        # Confidence interval
        ci = fit.conf_int()
        if TREATMENT_VAR in ci.index:
            ci_lower = _safe_float(ci.loc[TREATMENT_VAR, "lower"])
            ci_upper = _safe_float(ci.loc[TREATMENT_VAR, "upper"])
        else:
            ci_lower = estimate - 1.96 * se if pd.notna(se) else np.nan
            ci_upper = estimate + 1.96 * se if pd.notna(se) else np.nan

        n_units = sub.index.get_level_values(0).nunique()

        return {
            "outcome": outcome,
            "specification": label,
            "estimate": estimate,
            "se_robust": se,
            "pvalue": pval,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "N": len(sub),
            "N_units": n_units,
            "r_squared": _safe_float(fit.rsquared, np.nan),
            "method": "PanelOLS_TWFE",
        }

    except Exception as e:
        print(f"    PanelOLS failed for {outcome}: {e}")
        return _twfe_statsmodels_fallback(sub.reset_index(), outcome, exog_vars, label)


def _twfe_statsmodels_fallback(df, outcome, exog_vars, label):
    """Fallback TWFE using statsmodels OLS with dummy variables."""
    try:
        sub = df.dropna(subset=[outcome] + exog_vars).copy()
        if len(sub) < 20:
            return _empty_result(outcome, label, len(sub))

        # Create entity and time dummies
        entity_dummies = pd.get_dummies(sub[ENTITY_VAR], prefix="ent", drop_first=True,
                                        dtype=float)
        time_dummies = pd.get_dummies(sub[TIME_VAR], prefix="t", drop_first=True,
                                      dtype=float)

        X = pd.concat([sub[exog_vars].reset_index(drop=True),
                        entity_dummies.reset_index(drop=True),
                        time_dummies.reset_index(drop=True)], axis=1)
        X = sm.add_constant(X)
        y = sub[outcome].reset_index(drop=True)

        # Cluster SEs
        cluster_col = CLUSTER_VAR if CLUSTER_VAR in sub.columns else ENTITY_VAR
        groups = sub[cluster_col].reset_index(drop=True)

        mod = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": groups})
        idx = TREATMENT_VAR
        estimate = _safe_float(mod.params.get(idx, np.nan))
        se = _safe_float(mod.bse.get(idx, np.nan))
        pval = _safe_float(mod.pvalues.get(idx, np.nan))
        ci = mod.conf_int()
        ci_lower = _safe_float(ci.loc[idx, 0]) if idx in ci.index else np.nan
        ci_upper = _safe_float(ci.loc[idx, 1]) if idx in ci.index else np.nan

        return {
            "outcome": outcome,
            "specification": label,
            "estimate": estimate,
            "se_robust": se,
            "pvalue": pval,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "N": len(sub),
            "N_units": sub[ENTITY_VAR].nunique(),
            "r_squared": _safe_float(mod.rsquared, np.nan),
            "method": "statsmodels_OLS_FE",
        }
    except Exception as e:
        print(f"    Statsmodels fallback also failed: {e}")
        return _empty_result(outcome, label, len(df))


def _empty_result(outcome, label, n=0):
    """Return a complete result dict with NaN values (never incomplete)."""
    return {
        "outcome": outcome,
        "specification": label,
        "estimate": np.nan,
        "se_robust": np.nan,
        "pvalue": np.nan,
        "ci_lower": np.nan,
        "ci_upper": np.nan,
        "N": n,
        "N_units": 0,
        "r_squared": np.nan,
        "method": "none",
    }


def run_event_study(df, outcome, n_leads=4, n_lags=4, label="event_study"):
    """Event study specification with leads and lags around treatment.

    Creates relative-time dummies: rel_time_m4, ..., rel_time_m1, rel_time_p0, ..., rel_time_p4.
    Omits t=-1 as reference period.
    Returns coefficients for all leads/lags.
    """
    sub = df.dropna(subset=[outcome, TREATMENT_VAR, ENTITY_VAR, TIME_VAR]).copy()

    # Need FIRST_TREAT_VAR for event study
    if FIRST_TREAT_VAR == "None" or FIRST_TREAT_VAR not in sub.columns:
        # For standard 2-period DiD, try to infer treatment timing
        # Find first period where treat=1 for each entity
        treat_start = sub.loc[sub[TREATMENT_VAR] == 1].groupby(ENTITY_VAR)[TIME_VAR].min()
        sub = sub.merge(treat_start.rename("_first_treat"), on=ENTITY_VAR, how="left")
    else:
        sub["_first_treat"] = sub[FIRST_TREAT_VAR]

    # Compute relative time
    sub["rel_time"] = sub[TIME_VAR] - sub["_first_treat"]
    # For never-treated, rel_time is NaN — set to large positive to exclude from dummies
    sub["rel_time"] = sub["rel_time"].fillna(9999)

    # Create lead/lag dummies, omit t=-1 as reference
    event_vars = []
    for k in range(-n_leads, n_lags + 1):
        if k == -1:
            continue  # omit reference period
        col_name = f"rel_time_{'m' if k < 0 else 'p'}{abs(k)}"
        sub[col_name] = (sub["rel_time"] == k).astype(float)
        event_vars.append(col_name)

    # Drop rows where rel_time is too extreme (keep only relevant window + never-treated)
    mask = ((sub["rel_time"] >= -n_leads) & (sub["rel_time"] <= n_lags)) | (sub["rel_time"] == 9999)
    sub = sub[mask].copy()

    if len(sub) < 20:
        return [], _empty_result(outcome, label, len(sub))

    # Set panel index
    sub_panel = sub.set_index([ENTITY_VAR, TIME_VAR])
    y = sub_panel[outcome]
    X = sub_panel[event_vars]

    event_results = []
    try:
        if linearmodels_available:
            mod = PanelOLS(y, X, entity_effects=True, time_effects=True,
                           drop_absorbed=True, check_rank=False)
            if CLUSTER_VAR == ENTITY_VAR:
                fit = mod.fit(cov_type="clustered", cluster_entity=True)
            else:
                fit = mod.fit(cov_type="clustered", cluster_entity=True)

            ci = fit.conf_int()
            for ev in event_vars:
                k_str = ev.replace("rel_time_", "")
                k = -int(k_str[1:]) if k_str.startswith("m") else int(k_str[1:])
                est = _safe_float(fit.params.get(ev, np.nan))
                se = _safe_float(fit.std_errors.get(ev, np.nan))
                pval = _safe_float(fit.pvalues.get(ev, np.nan))
                ci_lo = _safe_float(ci.loc[ev, "lower"]) if ev in ci.index else np.nan
                ci_hi = _safe_float(ci.loc[ev, "upper"]) if ev in ci.index else np.nan
                event_results.append({
                    "outcome": outcome,
                    "specification": label,
                    "rel_time": k,
                    "estimate": est,
                    "se_robust": se,
                    "pvalue": pval,
                    "ci_lower": ci_lo,
                    "ci_upper": ci_hi,
                    "method": "PanelOLS_event_study",
                })
        else:
            # Statsmodels fallback
            entity_d = pd.get_dummies(sub[ENTITY_VAR], prefix="ent", drop_first=True, dtype=float)
            time_d = pd.get_dummies(sub[TIME_VAR], prefix="t", drop_first=True, dtype=float)
            X_ols = pd.concat([sub[event_vars].reset_index(drop=True),
                               entity_d.reset_index(drop=True),
                               time_d.reset_index(drop=True)], axis=1)
            X_ols = sm.add_constant(X_ols)
            y_ols = sub[outcome].reset_index(drop=True)
            groups = sub[ENTITY_VAR].reset_index(drop=True)
            fit = sm.OLS(y_ols, X_ols).fit(cov_type="cluster", cov_kwds={"groups": groups})

            ci = fit.conf_int()
            for ev in event_vars:
                k_str = ev.replace("rel_time_", "")
                k = -int(k_str[1:]) if k_str.startswith("m") else int(k_str[1:])
                est = _safe_float(fit.params.get(ev, np.nan))
                se = _safe_float(fit.bse.get(ev, np.nan))
                pval = _safe_float(fit.pvalues.get(ev, np.nan))
                ci_lo = _safe_float(ci.loc[ev, 0]) if ev in ci.index else np.nan
                ci_hi = _safe_float(ci.loc[ev, 1]) if ev in ci.index else np.nan
                event_results.append({
                    "outcome": outcome,
                    "specification": label,
                    "rel_time": k,
                    "estimate": est,
                    "se_robust": se,
                    "pvalue": pval,
                    "ci_lower": ci_lo,
                    "ci_upper": ci_hi,
                    "method": "statsmodels_event_study",
                })

    except Exception as e:
        print(f"    Event study failed for {outcome}: {e}")

    # Add reference period (t=-1) with estimate=0
    event_results.append({
        "outcome": outcome, "specification": label, "rel_time": -1,
        "estimate": 0.0, "se_robust": 0.0, "pvalue": np.nan,
        "ci_lower": 0.0, "ci_upper": 0.0, "method": "reference_period",
    })

    # Pre-trends test: joint F-test on pre-treatment leads
    pre_coeffs = [r for r in event_results if r["rel_time"] < -1
                  and pd.notna(r["estimate"]) and r["estimate"] != 0]
    pre_trends_pval = np.nan
    if pre_coeffs:
        try:
            pre_vars = [f"rel_time_m{abs(r['rel_time'])}" for r in pre_coeffs]
            hypothesis = " = ".join([f"{v}" for v in pre_vars]) + " = 0"
            # Simplified: Wald test
            pre_ests = np.array([r["estimate"] for r in pre_coeffs])
            pre_ses = np.array([r["se_robust"] for r in pre_coeffs])
            valid = ~np.isnan(pre_ests) & ~np.isnan(pre_ses) & (pre_ses > 0)
            if valid.sum() > 0:
                f_stat = np.mean((pre_ests[valid] / pre_ses[valid]) ** 2)
                from scipy import stats as sp_stats
                pre_trends_pval = 1 - sp_stats.chi2.cdf(f_stat * valid.sum(), valid.sum())
        except Exception:
            pass

    summary = {
        "outcome": outcome,
        "specification": "pre_trends_test",
        "estimate": pre_trends_pval,
        "se_robust": np.nan,
        "pvalue": pre_trends_pval,
        "ci_lower": np.nan,
        "ci_upper": np.nan,
        "N": len(sub),
        "N_units": sub[ENTITY_VAR].nunique(),
        "r_squared": np.nan,
        "method": "joint_F_test",
    }

    return event_results, summary


def try_callaway_santanna(df, outcome, label="callaway_santanna"):
    """Try Callaway-Sant'Anna estimator for staggered DiD.

    Attempts csdid package, then pyfixest.did, then returns empty.
    """
    if FIRST_TREAT_VAR == "None" or FIRST_TREAT_VAR not in df.columns:
        return _empty_result(outcome, label)

    sub = df.dropna(subset=[outcome, ENTITY_VAR, TIME_VAR, FIRST_TREAT_VAR]).copy()

    # Try csdid
    try:
        from csdid import att_gt
        result = att_gt(
            yname=outcome,
            tname=TIME_VAR,
            idname=ENTITY_VAR,
            gname=FIRST_TREAT_VAR,
            data=sub,
        )
        # Aggregate to overall ATT
        att = _safe_float(result.att)
        se = _safe_float(result.se)
        ci_lower = att - 1.96 * se if pd.notna(se) else np.nan
        ci_upper = att + 1.96 * se if pd.notna(se) else np.nan
        return {
            "outcome": outcome, "specification": label,
            "estimate": att, "se_robust": se,
            "pvalue": np.nan,
            "ci_lower": ci_lower, "ci_upper": ci_upper,
            "N": len(sub), "N_units": sub[ENTITY_VAR].nunique(),
            "r_squared": np.nan, "method": "csdid_CS",
        }
    except Exception as e:
        print(f"    csdid failed: {e}")

    # Try pyfixest did module
    try:
        import pyfixest as pf
        cs_result = pf.did.event_study(
            data=sub,
            yname=outcome,
            idname=ENTITY_VAR,
            tname=TIME_VAR,
            gname=FIRST_TREAT_VAR,
            att=True,
        )
        att = _safe_float(cs_result.ATT)
        se = _safe_float(cs_result.se)
        ci_lower = att - 1.96 * se if pd.notna(se) else np.nan
        ci_upper = att + 1.96 * se if pd.notna(se) else np.nan
        return {
            "outcome": outcome, "specification": label,
            "estimate": att, "se_robust": se,
            "pvalue": np.nan,
            "ci_lower": ci_lower, "ci_upper": ci_upper,
            "N": len(sub), "N_units": sub[ENTITY_VAR].nunique(),
            "r_squared": np.nan, "method": "pyfixest_CS",
        }
    except Exception as e:
        print(f"    pyfixest CS also failed: {e}")

    return _empty_result(outcome, label, len(sub))


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("01_main.py — DiD Main Estimation")
    print("=" * 70)

    df = pd.read_csv(CLEAN_CSV)
    print(f"Loaded: {len(df):,} rows x {df.shape[1]} cols")

    # ── Expected signs ────────────────────────────────────────────────────
    print("\n--- Expected signs ---")
    for outcome, sign in EXPECTED_SIGNS.items():
        print(f"  {outcome}: {sign}")

    all_results = []
    event_study_results = []
    outcomes_present = [o for o in OUTCOME_VARS if o in df.columns]

    # ── Spec 1: TWFE baseline (no covariates) ────────────────────────────
    print("\n--- TWFE Baseline (entity + time FE, no covariates) ---")
    for outcome in outcomes_present:
        print(f"\n  Outcome: {outcome}")
        res = run_twfe_panelols(df, outcome, covariates=None, label="twfe_baseline")
        all_results.append(res)
        print(f"    Estimate: {res['estimate']:.4f}  SE: {res['se_robust']:.4f}")
        print(f"    95% CI: [{res['ci_lower']:.4f}, {res['ci_upper']:.4f}]")
        print(f"    N: {res['N']}  N_units: {res['N_units']}  Method: {res['method']}")

    # ── Spec 2: TWFE with covariates ─────────────────────────────────────
    covs_avail = [c for c in COVARIATES if c in df.columns]
    if covs_avail:
        print(f"\n--- TWFE with covariates: {covs_avail} ---")
        for outcome in outcomes_present:
            print(f"\n  Outcome: {outcome}")
            res = run_twfe_panelols(df, outcome, covariates=covs_avail,
                                     label="twfe_with_controls")
            all_results.append(res)
            print(f"    Estimate: {res['estimate']:.4f}  SE: {res['se_robust']:.4f}")
            print(f"    95% CI: [{res['ci_lower']:.4f}, {res['ci_upper']:.4f}]")

    # ── Spec 3: Callaway-Sant'Anna (if staggered) ───────────────────────
    if FIRST_TREAT_VAR != "None" and FIRST_TREAT_VAR in df.columns:
        ft = df[FIRST_TREAT_VAR].dropna()
        ft = ft[ft < np.inf]
        if ft.nunique() > 1:
            print(f"\n--- Callaway-Sant'Anna (staggered DiD) ---")
            for outcome in outcomes_present:
                print(f"\n  Outcome: {outcome}")
                res = try_callaway_santanna(df, outcome)
                all_results.append(res)
                print(f"    Estimate: {res['estimate']}  SE: {res['se_robust']}")
                print(f"    Method: {res['method']}")

    # ── Spec 4: Event study ──────────────────────────────────────────────
    print(f"\n--- Event Study ---")
    for outcome in outcomes_present:
        print(f"\n  Outcome: {outcome}")
        ev_res, pre_trends = run_event_study(df, outcome)
        event_study_results.extend(ev_res)
        all_results.append(pre_trends)
        print(f"    Pre-trends test p-value: {pre_trends['pvalue']}")
        if pd.notna(pre_trends["pvalue"]):
            verdict = "PASS (no pre-trends)" if pre_trends["pvalue"] > 0.05 else "FAIL (pre-trends detected)"
            print(f"    Verdict: {verdict}")

    # ── Heterogeneity: treatment × moderator ────────────────────────────
    het_vars = [h for h in HETEROGENEITY_VARS if h in df.columns] if HETEROGENEITY_VARS else []
    if het_vars:
        print(f"\n--- Heterogeneity Analysis ---")
        for outcome in outcomes_present:
            for mod in het_vars:
                sub = df.dropna(subset=[outcome, TREATMENT_VAR, ENTITY_VAR,
                                        TIME_VAR, mod]).copy()
                sub[mod] = pd.to_numeric(sub[mod], errors="coerce")
                sub = sub.dropna(subset=[mod])

                if len(sub) < 30 or sub[mod].nunique() <= 1:
                    print(f"    {outcome} × {mod}: skipped (insufficient variation)")
                    continue

                sub["_treat_x_mod"] = sub[TREATMENT_VAR] * sub[mod]
                exog = [TREATMENT_VAR, mod, "_treat_x_mod"]
                if covs_avail:
                    exog += [c for c in covs_avail if c in sub.columns and c != mod]

                try:
                    sub_panel = sub.set_index([ENTITY_VAR, TIME_VAR])
                    y = sub_panel[outcome]
                    X = sub_panel[exog]

                    if linearmodels_available:
                        mod_fit = PanelOLS(y, X, entity_effects=True, time_effects=True,
                                           drop_absorbed=True, check_rank=False)
                        fit = mod_fit.fit(cov_type="clustered", cluster_entity=True)
                        int_est = _safe_float(fit.params.get("_treat_x_mod", np.nan))
                        int_se = _safe_float(fit.std_errors.get("_treat_x_mod", np.nan))
                        int_pval = _safe_float(fit.pvalues.get("_treat_x_mod", np.nan))
                    else:
                        entity_d = pd.get_dummies(sub[ENTITY_VAR], prefix="ent",
                                                   drop_first=True, dtype=float)
                        time_d = pd.get_dummies(sub[TIME_VAR], prefix="t",
                                                 drop_first=True, dtype=float)
                        X_ols = pd.concat([sub[exog].reset_index(drop=True),
                                           entity_d.reset_index(drop=True),
                                           time_d.reset_index(drop=True)], axis=1)
                        X_ols = sm.add_constant(X_ols)
                        y_ols = sub[outcome].reset_index(drop=True)
                        groups = sub[ENTITY_VAR].reset_index(drop=True)
                        fit = sm.OLS(y_ols, X_ols).fit(cov_type="cluster",
                                                        cov_kwds={"groups": groups})
                        int_est = _safe_float(fit.params.get("_treat_x_mod", np.nan))
                        int_se = _safe_float(fit.bse.get("_treat_x_mod", np.nan))
                        int_pval = _safe_float(fit.pvalues.get("_treat_x_mod", np.nan))

                    sig = "***" if int_pval < 0.01 else ("**" if int_pval < 0.05 else (
                        "*" if int_pval < 0.10 else ""))
                    print(f"    {outcome} × {mod}: interaction={int_est:.4f}  "
                          f"SE={int_se:.4f}  p={int_pval:.4f} {sig}")
                    all_results.append({
                        "outcome": outcome, "specification": f"heterogeneity_{mod}",
                        "estimate": int_est, "se_robust": int_se,
                        "pvalue": int_pval,
                        "ci_lower": int_est - 1.96 * int_se if pd.notna(int_se) else np.nan,
                        "ci_upper": int_est + 1.96 * int_se if pd.notna(int_se) else np.nan,
                        "N": len(sub), "N_units": sub[ENTITY_VAR].nunique(),
                        "r_squared": np.nan, "method": "TWFE_interaction",
                    })
                except Exception as e:
                    print(f"    {outcome} × {mod}: failed ({e})")

    # ── Effect sizes ─────────────────────────────────────────────────────
    print("\n--- Effect Sizes (Cohen's d) ---")
    for outcome in outcomes_present:
        baseline = [r for r in all_results if r["outcome"] == outcome
                    and r["specification"] == "twfe_baseline"]
        if baseline and pd.notna(baseline[0]["estimate"]):
            est = baseline[0]["estimate"]
            sd = df[outcome].std()
            cohens_d = est / sd if sd > 0 else np.nan
            mean_val = df[outcome].mean()
            pct_change = 100 * est / abs(mean_val) if abs(mean_val) > 1e-10 else np.nan
            flag = " ***LARGE***" if (not np.isnan(cohens_d) and abs(cohens_d) > 1.0) else ""
            print(f"  {outcome}: Cohen's d={cohens_d:.3f}  %change={pct_change:.1f}%{flag}")

    # ── Power calculation ────────────────────────────────────────────────
    print("\n--- Power Calculations ---")
    from scipy import stats as sp_stats
    for outcome in outcomes_present:
        sub = df.dropna(subset=[outcome, TREATMENT_VAR])
        n = len(sub)
        sd = sub[outcome].std()
        if n >= 20 and sd > 0:
            z_alpha = sp_stats.norm.ppf(0.975)
            z_beta = sp_stats.norm.ppf(0.80)
            n_units = sub[ENTITY_VAR].nunique()
            # MDE approximation for panel data
            mde = (z_alpha + z_beta) * sd * np.sqrt(4.0 / n)
            cohens_d_mde = mde / sd
            print(f"  {outcome}: N={n} (units={n_units})  MDE={mde:.4f}  "
                  f"Cohen's d_MDE={cohens_d_mde:.3f}")
            all_results.append({
                "outcome": outcome, "specification": "power_calculation",
                "estimate": mde, "se_robust": cohens_d_mde,
                "pvalue": np.nan,
                "ci_lower": sd, "ci_upper": np.nan,
                "N": n, "N_units": n_units,
                "r_squared": np.nan, "method": "power_calc",
            })

    # ── Actual vs expected signs ──────────────────────────────────────────
    print("\n--- Actual vs Expected Signs ---")
    for outcome in outcomes_present:
        baseline = [r for r in all_results if r["outcome"] == outcome
                    and r["specification"] == "twfe_baseline"]
        if baseline:
            est = baseline[0]["estimate"]
            expected = EXPECTED_SIGNS.get(outcome, "?")
            actual = "+" if est > 0 else "-" if est < 0 else "0"
            match = "MATCH" if (expected == actual or expected == "?") else "MISMATCH"
            print(f"  {outcome}: expected={expected} actual={actual} {match} (est={est:.4f})")

    # ── Save results ──────────────────────────────────────────────────────
    results_df = pd.DataFrame(all_results)
    out_path = os.path.join(DATA_DIR, "main_results.csv")
    results_df.to_csv(out_path, index=False)
    print(f"\nSaved: {out_path} ({len(results_df)} rows)")

    if event_study_results:
        es_df = pd.DataFrame(event_study_results)
        es_path = os.path.join(DATA_DIR, "event_study_results.csv")
        es_df.to_csv(es_path, index=False)
        print(f"Saved: {es_path} ({len(es_df)} rows)")

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
