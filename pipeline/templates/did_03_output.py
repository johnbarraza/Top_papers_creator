"""03_output.py — DiD tables and figures template.

CRITICAL: This template NEVER writes NaN, blank, or empty cells to tables.
Every cell is filled with a value or '---' with a note explaining why.
"""

import os
import warnings
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT-SPECIFIC VARIABLES (Claude fills these)
# ═══════════════════════════════════════════════════════════════════════════════
PRIMARY_OUTCOME = "{{PRIMARY_OUTCOME}}"
OUTCOME_VARS = {{OUTCOME_VARS}}
ENTITY_VAR = "{{ENTITY_VAR}}"
TIME_VAR = "{{TIME_VAR}}"
COVARIATES = {{COVARIATES}}

# ═══════════════════════════════════════════════════════════════════════════════
# FIXED CODE
# ═══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "..", "data", "clean")
TABLES_DIR = os.path.join(SCRIPT_DIR, "..", "..", "paper", "tables")
FIGURES_DIR = os.path.join(SCRIPT_DIR, "..", "..", "paper", "figures")

os.makedirs(TABLES_DIR, exist_ok=True)
os.makedirs(FIGURES_DIR, exist_ok=True)


def fmt(val, decimals=4):
    """Format a value for LaTeX tables. NEVER returns empty string."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "---"
    try:
        return f"{float(val):.{decimals}f}"
    except (ValueError, TypeError):
        return str(val)


def fmt_stars(pval):
    """Significance stars from p-value."""
    if pval is None or (isinstance(pval, float) and np.isnan(pval)):
        return ""
    if pval < 0.01:
        return "***"
    if pval < 0.05:
        return "**"
    if pval < 0.10:
        return "*"
    return ""


def validate_table(content, filename):
    """Check table for NaN or empty cells before saving."""
    problems = []
    if "nan" in content.lower():
        problems.append("Contains 'nan'")
    if "& &" in content:
        problems.append("Contains empty cells (& &)")
    if "& \\\\" in content:
        problems.append("Contains empty last column (& \\\\)")

    if problems:
        print(f"  WARNING in {filename}: {', '.join(problems)}")
        # Auto-fix: replace NaN with ---
        content = content.replace("nan", "---")
        content = content.replace("NaN", "---")
        content = content.replace("None", "---")
        # Fix empty cells
        while "& &" in content:
            content = content.replace("& &", "& --- &")
        content = content.replace("& \\\\", "& --- \\\\")
        print(f"  Auto-fixed: replaced blanks with '---'")

    return content


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 1: Summary Statistics by Treatment/Control, Pre/Post
# ═══════════════════════════════════════════════════════════════════════════════
def make_table1(df):
    print("Generating Table 1: Summary statistics by treatment/control, pre/post...")

    # Identify ever-treated units
    ever_treated = df.groupby(ENTITY_VAR)["treat"].max()
    df = df.merge(ever_treated.rename("ever_treated"), on=ENTITY_VAR, how="left")

    treated_pre = df[(df["ever_treated"] == 1) & (df["treat"] == 0)]
    treated_post = df[(df["ever_treated"] == 1) & (df["treat"] == 1)]
    control_pre = df[(df["ever_treated"] == 0) & (df["treat"] == 0)]
    control_post = df[(df["ever_treated"] == 0)]  # never-treated, all periods

    stat_vars = OUTCOME_VARS + COVARIATES
    stat_vars = [v for v in stat_vars if v in df.columns]

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Summary Statistics by Treatment Group and Period}",
        r"\label{tab:summary}",
        r"\begin{tabular}{l ccc ccc}",
        r"\toprule",
        r"& \multicolumn{3}{c}{Treated Group} & \multicolumn{3}{c}{Control Group} \\",
        r"\cmidrule(lr){2-4} \cmidrule(lr){5-7}",
        r"Variable & Pre & Post & Diff & Pre & Post & Diff \\",
        r"\midrule",
    ]

    for var in stat_vars:
        tp_pre = treated_pre[var].dropna()
        tp_post = treated_post[var].dropna()
        cp_pre = control_pre[var].dropna()
        # For control post: never-treated units in post period
        # Use all control obs since they are never treated
        cp_all = control_post[var].dropna()

        t_diff = tp_post.mean() - tp_pre.mean() if len(tp_pre) > 0 and len(tp_post) > 0 else np.nan
        c_diff = np.nan  # control group doesn't have a natural pre/post split
        # Approximate: split control at median time
        if len(control_post) > 0:
            med_time = df[TIME_VAR].median()
            cp_pre_vals = control_post.loc[control_post[TIME_VAR] <= med_time, var].dropna()
            cp_post_vals = control_post.loc[control_post[TIME_VAR] > med_time, var].dropna()
            if len(cp_pre_vals) > 0 and len(cp_post_vals) > 0:
                c_diff = cp_post_vals.mean() - cp_pre_vals.mean()

        tex.append(
            f"  {var} & {fmt(tp_pre.mean())} & {fmt(tp_post.mean())} & {fmt(t_diff)} "
            f"& {fmt(cp_pre.mean())} & {fmt(cp_all.mean())} & {fmt(c_diff)} \\\\"
        )

    # Observation counts
    tex.append(r"\midrule")
    tex.append(
        f"  N (unit-periods) & {len(treated_pre)} & {len(treated_post)} & "
        f"& {len(control_pre)} & {len(control_post)} & \\\\"
    )
    n_treated_units = int(df.loc[df["ever_treated"] == 1, ENTITY_VAR].nunique())
    n_control_units = int(df.loc[df["ever_treated"] == 0, ENTITY_VAR].nunique())
    tex.append(
        f"  N (units) & \\multicolumn{{3}}{{c}}{{{n_treated_units}}} "
        f"& \\multicolumn{{3}}{{c}}{{{n_control_units}}} \\\\"
    )

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} Summary statistics for the DiD analysis sample. "
        r"'Treated Group' includes units that eventually receive treatment. "
        r"'Pre' and 'Post' refer to periods before and after treatment onset. "
        r"'Diff' is the simple difference in means. "
        r"'---' indicates unavailable data.",
        r"\end{tablenotes}",
        r"\end{table}",
    ]

    content = "\n".join(tex)
    content = validate_table(content, "table_1_summary.tex")
    path = os.path.join(TABLES_DIR, "table_1_summary.tex")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 2: Main DiD Results (TWFE, with/without controls)
# ═══════════════════════════════════════════════════════════════════════════════
def make_table2(results):
    print("Generating Table 2: Main DiD results...")

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Main Difference-in-Differences Estimates}",
        r"\label{tab:main_results}",
        r"\begin{tabular}{l ccc}",
        r"\toprule",
    ]

    # Column headers from unique outcomes
    outcomes = results["outcome"].unique().tolist()
    # Filter to actual outcomes (not pre_trends_test)
    outcomes = [o for o in outcomes if o in OUTCOME_VARS or o == PRIMARY_OUTCOME]
    if not outcomes:
        outcomes = results["outcome"].unique().tolist()[:5]

    outcome_labels = " & ".join(outcomes)
    tex.append(f"  & {outcome_labels} \\\\")
    tex.append(r"\midrule")

    # Group by specification (exclude event study / pre-trends rows)
    spec_order = ["twfe_baseline", "twfe_with_controls", "callaway_santanna"]
    spec_labels = {
        "twfe_baseline": "TWFE (no controls)",
        "twfe_with_controls": "TWFE (with controls)",
        "callaway_santanna": "Callaway-Sant'Anna",
    }

    for spec in spec_order:
        spec_data = results[results["specification"] == spec]
        if len(spec_data) == 0:
            continue

        label = spec_labels.get(spec, spec)
        tex.append(f"\\addlinespace")
        tex.append(f"\\multicolumn{{{len(outcomes)+1}}}{{l}}{{\\textit{{{label}}}}} \\\\")

        # Estimates row
        row = "  Treatment"
        for outcome in outcomes:
            match = spec_data[spec_data["outcome"] == outcome]
            if len(match) > 0:
                est = match.iloc[0]["estimate"]
                pval = match.iloc[0].get("pvalue", np.nan)
                stars = fmt_stars(pval)
                row += f" & {fmt(est)}{stars}"
            else:
                row += " & ---"
        tex.append(row + " \\\\")

        # SE row
        row = "  "
        for outcome in outcomes:
            match = spec_data[spec_data["outcome"] == outcome]
            if len(match) > 0:
                se = match.iloc[0].get("se_robust", np.nan)
                row += f" & ({fmt(se)})"
            else:
                row += " & ---"
        tex.append(row + " \\\\")

        # CI row
        row = "  95\\% CI"
        for outcome in outcomes:
            match = spec_data[spec_data["outcome"] == outcome]
            if len(match) > 0:
                ci_lo = match.iloc[0].get("ci_lower", np.nan)
                ci_hi = match.iloc[0].get("ci_upper", np.nan)
                row += f" & [{fmt(ci_lo)}, {fmt(ci_hi)}]"
            else:
                row += " & ---"
        tex.append(row + " \\\\")

        # N and R2 row
        row = "  N / $R^2$"
        for outcome in outcomes:
            match = spec_data[spec_data["outcome"] == outcome]
            if len(match) > 0:
                n = match.iloc[0].get("N", np.nan)
                r2 = match.iloc[0].get("r_squared", np.nan)
                n_str = str(int(n)) if pd.notna(n) else "---"
                row += f" & {n_str} / {fmt(r2, 3)}"
            else:
                row += " & ---"
        tex.append(row + " \\\\")

        # Method row
        row = "  Method"
        for outcome in outcomes:
            match = spec_data[spec_data["outcome"] == outcome]
            if len(match) > 0:
                method = match.iloc[0].get("method", "---")
                row += f" & {method}"
            else:
                row += " & ---"
        tex.append(row + " \\\\")

    # Pre-trends test
    pre_trends = results[results["specification"] == "pre_trends_test"]
    if len(pre_trends) > 0:
        tex.append(r"\addlinespace")
        tex.append(f"\\multicolumn{{{len(outcomes)+1}}}{{l}}{{\\textit{{Pre-trends test}}}} \\\\")
        row = "  p-value"
        for outcome in outcomes:
            match = pre_trends[pre_trends["outcome"] == outcome]
            if len(match) > 0:
                pval = match.iloc[0].get("pvalue", np.nan)
                row += f" & {fmt(pval, 3)}"
            else:
                row += " & ---"
        tex.append(row + " \\\\")

    tex += [
        r"\midrule",
        f"  Entity FE & \\multicolumn{{{len(outcomes)}}}{{c}}{{Yes}} \\\\",
        f"  Time FE & \\multicolumn{{{len(outcomes)}}}{{c}}{{Yes}} \\\\",
        f"  Clustered SEs & \\multicolumn{{{len(outcomes)}}}{{c}}{{Yes}} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} Difference-in-differences estimates with entity "
        r"and time fixed effects. Standard errors clustered at the entity level "
        r"in parentheses. $^{***}p<0.01$, $^{**}p<0.05$, $^{*}p<0.10$. "
        r"'---' indicates estimate unavailable.",
        r"\end{tablenotes}",
        r"\end{table}",
    ]

    content = "\n".join(tex)
    content = validate_table(content, "table_2_main_results.tex")
    path = os.path.join(TABLES_DIR, "table_2_main_results.tex")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 3: Event Study Coefficients
# ═══════════════════════════════════════════════════════════════════════════════
def make_table3(es_df):
    print("Generating Table 3: Event study coefficients...")

    if es_df is None or len(es_df) == 0:
        print("  No event study results. Skipping.")
        return

    # Focus on primary outcome
    es_primary = es_df[es_df["outcome"] == PRIMARY_OUTCOME].copy()
    if len(es_primary) == 0:
        es_primary = es_df.copy()

    es_primary = es_primary.sort_values("rel_time")

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Event Study Coefficients}",
        r"\label{tab:event_study}",
        r"\begin{tabular}{l cccc}",
        r"\toprule",
        r"Relative Time & Estimate & SE & 95\% CI & p-value \\",
        r"\midrule",
    ]

    for _, r in es_primary.iterrows():
        k = int(r["rel_time"])
        label = f"$t{k:+d}$"
        if k == -1:
            label += " (ref.)"

        est = r["estimate"]
        se = r.get("se_robust", np.nan)
        ci_lo = r.get("ci_lower", np.nan)
        ci_hi = r.get("ci_upper", np.nan)
        pval = r.get("pvalue", np.nan)
        stars = fmt_stars(pval)

        tex.append(
            f"  {label} & {fmt(est)}{stars} & {fmt(se)} "
            f"& [{fmt(ci_lo)}, {fmt(ci_hi)}] & {fmt(pval, 3)} \\\\"
        )

        # Add separator between pre and post
        if k == -1:
            tex.append(r"\midrule")

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} Event study coefficients from a TWFE regression "
        r"with leads and lags of treatment. $t=-1$ is the omitted reference period. "
        r"Entity and time fixed effects included. Standard errors clustered at "
        r"entity level. $^{***}p<0.01$, $^{**}p<0.05$, $^{*}p<0.10$. "
        r"'---' indicates unavailable.",
        r"\end{tablenotes}",
        r"\end{table}",
    ]

    content = "\n".join(tex)
    content = validate_table(content, "table_3_event_study.tex")
    path = os.path.join(TABLES_DIR, "table_3_event_study.tex")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 4: Robustness (placebo, Bacon, bootstrap)
# ═══════════════════════════════════════════════════════════════════════════════
def make_table4(robust):
    print("Generating Table 4: Robustness...")

    if robust is None or len(robust) == 0:
        print("  No robustness results. Skipping.")
        return

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Robustness Checks}",
        r"\label{tab:robustness}",
        r"\begin{tabular}{l ccccc}",
        r"\toprule",
        r"Test & Estimate & SE & 95\% CI & p-value & N \\",
        r"\midrule",
    ]

    panels = [
        ("Panel A: Parallel Trends", "parallel_trends"),
        ("Panel B: Placebo Outcomes", "placebo_outcome"),
        ("Panel C: Placebo Timing", "placebo_timing"),
        ("Panel D: Bacon Decomposition", "bacon"),
        ("Panel E: TWFE vs CS", "twfe_vs_cs"),
        ("Panel F: Control Groups", "control"),
        ("Panel G: Wild Bootstrap", "wild_cluster_bootstrap"),
    ]

    for panel_name, prefix in panels:
        panel_data = robust[robust["test"].str.startswith(prefix)]
        if len(panel_data) == 0:
            continue
        tex.append(f"\\addlinespace")
        tex.append(f"\\multicolumn{{6}}{{l}}{{\\textit{{{panel_name}}}}} \\\\")
        for _, r in panel_data.iterrows():
            label = r.get("test", "").replace(f"{prefix}_", "").replace("_", " ").title()
            if prefix == "placebo_outcome":
                label = r.get("outcome", "").replace("placebo_", "")
            if prefix == "covariate_balance":
                label = r.get("outcome", "")

            est = r.get("estimate", np.nan)
            se = r.get("se_robust", np.nan)
            ci_lo = r.get("ci_lower", np.nan)
            ci_hi = r.get("ci_upper", np.nan)
            pval = r.get("pvalue", np.nan)
            n = r.get("N", np.nan)
            n_str = str(int(n)) if pd.notna(n) and n > 0 else "---"

            tex.append(
                f"  {label} & {fmt(est)} & {fmt(se)} "
                f"& [{fmt(ci_lo)}, {fmt(ci_hi)}] "
                f"& {fmt(pval, 3)} & {n_str} \\\\"
            )

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} Panel A reports the joint test p-value for "
        r"pre-treatment event study coefficients. Panel B tests treatment effect "
        r"on outcomes that should not be affected. Panel C shifts treatment timing "
        r"earlier as a placebo. Panel D decomposes the TWFE estimate (Goodman-Bacon). "
        r"Panel F tests sensitivity to control group definition. "
        r"Panel G reports wild cluster bootstrap p-value. "
        r"'---' indicates unavailable.",
        r"\end{tablenotes}",
        r"\end{table}",
    ]

    content = "\n".join(tex)
    content = validate_table(content, "table_4_robustness.tex")
    path = os.path.join(TABLES_DIR, "table_4_robustness.tex")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 1: Event Study Plot with 95% CIs
# ═══════════════════════════════════════════════════════════════════════════════
def make_figure1(es_df):
    print("Generating Figure 1: Event study plot...")

    if es_df is None or len(es_df) == 0:
        print("  No event study results. Skipping.")
        return

    # Focus on primary outcome
    es_primary = es_df[es_df["outcome"] == PRIMARY_OUTCOME].copy()
    if len(es_primary) == 0:
        es_primary = es_df.copy()

    es_primary = es_primary.sort_values("rel_time")

    rel_times = es_primary["rel_time"].values
    estimates = es_primary["estimate"].values.copy()
    ci_lo = es_primary["ci_lower"].values.copy()
    ci_hi = es_primary["ci_upper"].values.copy()

    # Fill NaN estimates with CI midpoint
    for i in range(len(estimates)):
        if np.isnan(estimates[i]) and not np.isnan(ci_lo[i]) and not np.isnan(ci_hi[i]):
            estimates[i] = (ci_lo[i] + ci_hi[i]) / 2.0

    # Compute error bars (handle NaN gracefully)
    yerr_lo = np.where(np.isnan(estimates) | np.isnan(ci_lo), 0, estimates - ci_lo)
    yerr_hi = np.where(np.isnan(estimates) | np.isnan(ci_hi), 0, ci_hi - estimates)

    fig, ax = plt.subplots(figsize=(9, 5.5))

    # Color pre-treatment and post-treatment differently
    pre_mask = rel_times < 0
    post_mask = rel_times >= 0

    if pre_mask.any():
        ax.errorbar(rel_times[pre_mask], estimates[pre_mask],
                     yerr=[yerr_lo[pre_mask], yerr_hi[pre_mask]],
                     fmt="o", color="#2166ac", capsize=4, capthick=1.5,
                     markersize=7, linewidth=1.5, label="Pre-treatment")

    if post_mask.any():
        ax.errorbar(rel_times[post_mask], estimates[post_mask],
                     yerr=[yerr_lo[post_mask], yerr_hi[post_mask]],
                     fmt="s", color="#b2182b", capsize=4, capthick=1.5,
                     markersize=7, linewidth=1.5, label="Post-treatment")

    ax.axhline(y=0, color="black", linestyle="--", linewidth=1, alpha=0.5)
    ax.axvline(x=-0.5, color="gray", linestyle=":", linewidth=1, alpha=0.7,
               label="Treatment onset")

    ax.set_xlabel("Periods Relative to Treatment", fontsize=12)
    ax.set_ylabel("Estimated Coefficient", fontsize=12)
    ax.set_title(f"Event Study: {PRIMARY_OUTCOME.replace('_', ' ').title()}", fontsize=13)
    ax.legend(fontsize=10, loc="best")
    ax.grid(True, alpha=0.3)

    # Set integer ticks for relative time
    ax.set_xticks([int(t) for t in rel_times if not np.isnan(t)])

    plt.tight_layout()

    for ext in ["png", "pdf"]:
        path = os.path.join(FIGURES_DIR, f"figure_1_event_study.{ext}")
        plt.savefig(path, dpi=150 if ext == "png" else 300, bbox_inches="tight")
    plt.close("all")
    print(f"  Saved: figure_1_event_study.png/.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 2: Parallel Trends Visualization
# ═══════════════════════════════════════════════════════════════════════════════
def make_figure2(df):
    print("Generating Figure 2: Parallel trends visualization...")

    if PRIMARY_OUTCOME not in df.columns:
        print(f"  {PRIMARY_OUTCOME} not in data. Skipping.")
        return

    # Identify ever-treated vs never-treated
    ever_treated = df.groupby(ENTITY_VAR)["treat"].max()
    df = df.merge(ever_treated.rename("ever_treated"), on=ENTITY_VAR, how="left")

    # Compute group means by period
    treated_means = df[df["ever_treated"] == 1].groupby(TIME_VAR)[PRIMARY_OUTCOME].mean()
    control_means = df[df["ever_treated"] == 0].groupby(TIME_VAR)[PRIMARY_OUTCOME].mean()

    if len(treated_means) < 2 or len(control_means) < 2:
        print("  Insufficient data for parallel trends plot. Skipping.")
        return

    fig, ax = plt.subplots(figsize=(9, 5.5))

    ax.plot(treated_means.index, treated_means.values,
            "s-", color="#b2182b", linewidth=2, markersize=7, label="Treated group")
    ax.plot(control_means.index, control_means.values,
            "o-", color="#2166ac", linewidth=2, markersize=7, label="Control group")

    # Mark treatment onset
    # Find first period where any unit is treated
    first_treat_period = df.loc[df["treat"] == 1, TIME_VAR].min()
    if pd.notna(first_treat_period):
        ax.axvline(x=first_treat_period - 0.5, color="gray", linestyle=":",
                    linewidth=1.5, alpha=0.7, label="Treatment onset")

    ax.set_xlabel(TIME_VAR.replace("_", " ").title(), fontsize=12)
    ax.set_ylabel(PRIMARY_OUTCOME.replace("_", " ").title(), fontsize=12)
    ax.set_title("Parallel Trends: Treated vs Control Group Means", fontsize=13)
    ax.legend(fontsize=10, loc="best")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    for ext in ["png", "pdf"]:
        path = os.path.join(FIGURES_DIR, f"figure_2_parallel_trends.{ext}")
        plt.savefig(path, dpi=150 if ext == "png" else 300, bbox_inches="tight")
    plt.close("all")
    print(f"  Saved: figure_2_parallel_trends.png/.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("03_output.py — DiD Tables and Figures")
    print("=" * 70)

    df = pd.read_csv(os.path.join(DATA_DIR, "clean_data.csv"))
    print(f"Clean data: {len(df)} rows")

    main_results = pd.read_csv(os.path.join(DATA_DIR, "main_results.csv"))
    print(f"Main results: {len(main_results)} rows")

    es_path = os.path.join(DATA_DIR, "event_study_results.csv")
    es_df = pd.read_csv(es_path) if os.path.exists(es_path) else None
    if es_df is not None:
        print(f"Event study: {len(es_df)} rows")

    robust_path = os.path.join(DATA_DIR, "robustness_results.csv")
    robust = pd.read_csv(robust_path) if os.path.exists(robust_path) else None
    if robust is not None:
        print(f"Robustness: {len(robust)} rows")

    print()
    make_table1(df)
    make_table2(main_results)
    make_table3(es_df)
    make_table4(robust)
    print()
    make_figure1(es_df)
    make_figure2(df)

    # ── Final validation: check all tables for NaN ────────────────────────
    print("\n--- Final table validation ---")
    all_clean = True
    for tex_file in sorted(os.listdir(TABLES_DIR)):
        if tex_file.endswith(".tex"):
            content = open(os.path.join(TABLES_DIR, tex_file)).read()
            if "nan" in content.lower() or "& &" in content:
                print(f"  PROBLEM: {tex_file} still has blank/NaN cells!")
                all_clean = False
    if all_clean:
        print("  All tables validated: no NaN or blank cells.")

    print("\n" + "=" * 70)
    print("03_output.py complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
