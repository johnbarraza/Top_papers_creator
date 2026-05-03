"""03_output.py — RCT tables and figures template.

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
TREATMENT_VAR = "{{TREATMENT_VAR}}"
TREATMENT_ARMS = {{TREATMENT_ARMS}}       # e.g., {"Control": 0, "Cash": 1, "In-kind": 2}
COVARIATES = {{COVARIATES}}
CLUSTER_VAR = "{{CLUSTER_VAR}}"
BASELINE_OUTCOME = "{{BASELINE_OUTCOME}}"

# ═══════════════════════════════════════════════════════════════════════════════
# FIXED CODE
# ═══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "..", "data", "clean")
TABLES_DIR = os.path.join(SCRIPT_DIR, "..", "..", "paper", "tables")
FIGURES_DIR = os.path.join(SCRIPT_DIR, "..", "..", "paper", "figures")

os.makedirs(TABLES_DIR, exist_ok=True)
os.makedirs(FIGURES_DIR, exist_ok=True)


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
# TABLE 1: Summary Statistics by Arm
# ═══════════════════════════════════════════════════════════════════════════════
def make_table1(df):
    print("Generating Table 1: Summary statistics by arm...")

    stat_vars = OUTCOME_VARS + COVARIATES
    stat_vars = [v for v in stat_vars if v in df.columns]

    # Find the treatment column in data (holds arm values)
    treat_col = None
    arm_vals_set = set(TREATMENT_ARMS.values())
    for col in df.columns:
        vals = set(df[col].dropna().unique())
        if arm_vals_set.issubset(vals) or vals == arm_vals_set:
            treat_col = col
            break
    if treat_col is None:
        treat_col = "treat_any" if "treat_any" in df.columns else None

    arm_names = list(TREATMENT_ARMS.keys())
    n_arms = len(arm_names)
    col_spec = "l" + " ccc" * n_arms

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Summary Statistics by Treatment Arm}",
        r"\label{tab:summary}",
        f"\\begin{{tabular}}{{{col_spec}}}",
        r"\toprule",
    ]

    # Header row
    header = ""
    cmidrules = ""
    col_idx = 2
    for aname in arm_names:
        header += f" & \\multicolumn{{3}}{{c}}{{{aname}}}"
        cmidrules += f" \\cmidrule(lr){{{col_idx}-{col_idx+2}}}"
        col_idx += 3
    tex.append(header + " \\\\")
    tex.append(cmidrules)

    subheader = "Variable"
    for _ in arm_names:
        subheader += " & Mean & SD & N"
    tex.append(subheader + " \\\\")
    tex.append(r"\midrule")

    for var in stat_vars:
        row = f"  {var}"
        for aname, aval in TREATMENT_ARMS.items():
            if treat_col:
                arm_s = df.loc[df[treat_col] == aval, var].dropna()
            else:
                arm_s = df[var].dropna()
            row += f" & {fmt(arm_s.mean())} & {fmt(arm_s.std())} & {len(arm_s)}"
        tex.append(row + " \\\\")

    # Observation counts
    tex.append(r"\midrule")
    obs_row = "  Observations"
    for aname, aval in TREATMENT_ARMS.items():
        if treat_col:
            n = (df[treat_col] == aval).sum()
        else:
            n = len(df)
        obs_row += f" & \\multicolumn{{3}}{{c}}{{{n:,}}}"
    tex.append(obs_row + " \\\\")

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} Summary statistics by randomized treatment arm. "
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
# TABLE 2: Main ITT Results
# ═══════════════════════════════════════════════════════════════════════════════
def make_table2(results):
    print("Generating Table 2: Main ITT results...")

    outcomes = results["outcome"].unique().tolist()
    specs = ["itt_no_controls", "itt_with_controls", "itt_strata_fe"]
    spec_labels = {
        "itt_no_controls": "No controls",
        "itt_with_controls": "With controls",
        "itt_strata_fe": "Strata FE",
    }

    # Filter to specs that exist
    specs = [s for s in specs if s in results["specification"].unique()]
    arms = results["arm"].unique().tolist()
    # Remove interaction arms
    arms = [a for a in arms if "_x_" not in a]

    n_cols = len(outcomes) * len(specs)
    col_spec = "l" + " c" * n_cols

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Main ITT Estimates}",
        r"\label{tab:main_results}",
        f"\\begin{{tabular}}{{{col_spec}}}",
        r"\toprule",
    ]

    # Outcome headers
    header1 = ""
    cmidrules = ""
    col_idx = 2
    for outcome in outcomes:
        n_spec = len(specs)
        header1 += f" & \\multicolumn{{{n_spec}}}{{c}}{{{outcome}}}"
        cmidrules += f" \\cmidrule(lr){{{col_idx}-{col_idx+n_spec-1}}}"
        col_idx += n_spec
    tex.append(header1 + " \\\\")
    tex.append(cmidrules)

    # Spec sub-headers
    header2 = ""
    for _ in outcomes:
        for spec in specs:
            header2 += f" & ({spec_labels.get(spec, spec)[:8]})"
    tex.append(header2 + " \\\\")
    tex.append(r"\midrule")

    # One block per arm
    for arm in arms:
        tex.append(f"\\addlinespace")
        tex.append(f"\\multicolumn{{{n_cols+1}}}{{l}}{{\\textit{{{arm.replace('_', ' ').title()}}}}} \\\\")

        # Estimate row
        row_est = "  Estimate"
        for outcome in outcomes:
            for spec in specs:
                match = results[(results["outcome"] == outcome) &
                                (results["specification"] == spec) &
                                (results["arm"] == arm)]
                if len(match) > 0:
                    est = match.iloc[0]["estimate"]
                    pval = match.iloc[0].get("pvalue", np.nan)
                    stars = fmt_stars(pval)
                    row_est += f" & {fmt(est)}{stars}"
                else:
                    row_est += " & ---"
        tex.append(row_est + " \\\\")

        # SE row
        row_se = "  SE"
        for outcome in outcomes:
            for spec in specs:
                match = results[(results["outcome"] == outcome) &
                                (results["specification"] == spec) &
                                (results["arm"] == arm)]
                if len(match) > 0:
                    se = match.iloc[0].get("se_robust", np.nan)
                    row_se += f" & ({fmt(se)})"
                else:
                    row_se += " & ---"
        tex.append(row_se + " \\\\")

        # Effect size row (% of control mean)
        row_eff = "  Effect (\\% ctrl)"
        for outcome in outcomes:
            for spec in specs:
                match = results[(results["outcome"] == outcome) &
                                (results["specification"] == spec) &
                                (results["arm"] == arm)]
                if len(match) > 0:
                    eff = match.iloc[0].get("effect_pct", np.nan)
                    row_eff += f" & {fmt(eff, 1)}\\%"
                else:
                    row_eff += " & ---"
        tex.append(row_eff + " \\\\")

    # Control mean and N
    tex.append(r"\midrule")
    row_ctrl = "  Control mean"
    for outcome in outcomes:
        for spec in specs:
            match = results[(results["outcome"] == outcome) &
                            (results["specification"] == spec)]
            if len(match) > 0:
                cm = match.iloc[0].get("control_mean", np.nan)
                row_ctrl += f" & {fmt(cm)}"
            else:
                row_ctrl += " & ---"
    tex.append(row_ctrl + " \\\\")

    row_n = "  N"
    for outcome in outcomes:
        for spec in specs:
            match = results[(results["outcome"] == outcome) &
                            (results["specification"] == spec)]
            if len(match) > 0:
                n = match.iloc[0].get("N", 0)
                n_str = f"{int(n):,}" if pd.notna(n) and n > 0 else "---"
                row_n += f" & {n_str}"
            else:
                row_n += " & ---"
    tex.append(row_n + " \\\\")

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} Intent-to-treat estimates from OLS regressions of "
        r"outcomes on treatment arm indicators. Robust standard errors "
        r"(HC2, or clustered if applicable) in parentheses. "
        r"Effect size is the coefficient as a percentage of the control group mean. "
        r"$^{*}p<0.10$, $^{**}p<0.05$, $^{***}p<0.01$. "
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
# TABLE 3: Heterogeneity
# ═══════════════════════════════════════════════════════════════════════════════
def make_table3(results):
    print("Generating Table 3: Heterogeneity...")

    het_results = results[results["specification"].str.startswith("heterogeneity")]
    if len(het_results) == 0:
        print("  No heterogeneity results. Skipping (no blank table produced).")
        return

    # Group by moderator
    moderators = het_results["specification"].str.replace("heterogeneity_", "").unique()

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Heterogeneous Treatment Effects}",
        r"\label{tab:heterogeneity}",
        r"\begin{tabular}{l cccc}",
        r"\toprule",
        r"Interaction & Estimate & SE & $p$-value & N \\",
        r"\midrule",
    ]

    for mod in moderators:
        mod_data = het_results[het_results["specification"] == f"heterogeneity_{mod}"]
        if len(mod_data) == 0:
            continue
        tex.append(f"\\multicolumn{{5}}{{l}}{{\\textit{{Moderator: {mod}}}}} \\\\")
        for _, r in mod_data.iterrows():
            arm_label = r["arm"].replace("_", " ")
            pval = r.get("pvalue", np.nan)
            stars = fmt_stars(pval)
            tex.append(
                f"  {arm_label} & {fmt(r['estimate'])}{stars} "
                f"& ({fmt(r.get('se_robust', np.nan))}) "
                f"& {fmt(pval)} "
                f"& {int(r['N']) if pd.notna(r.get('N')) and r['N'] > 0 else '---'} \\\\"
            )
        tex.append(r"\addlinespace")

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} Estimates from OLS regressions including treatment arm "
        r"indicators, the moderator variable, and their interactions. "
        r"Robust standard errors (HC2, or clustered if applicable) in parentheses. "
        r"$^{*}p<0.10$, $^{**}p<0.05$, $^{***}p<0.01$. "
        r"Interactions are only reported for moderators with variation in the treated sample.",
        r"\end{tablenotes}",
        r"\end{table}",
    ]

    content = "\n".join(tex)
    content = validate_table(content, "table_3_heterogeneity.tex")
    path = os.path.join(TABLES_DIR, "table_3_heterogeneity.tex")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 4: Robustness
# ═══════════════════════════════════════════════════════════════════════════════
def make_table4(robust):
    print("Generating Table 4: Robustness checks...")

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Robustness Checks}",
        r"\label{tab:robustness}",
        r"\begin{tabular}{l l cccc}",
        r"\toprule",
        r"Test & Arm & Estimate & SE & $p$-value & N \\",
        r"\midrule",
    ]

    panels = [
        ("Panel A: Randomization Balance (F-test)", "balance_ftest"),
        ("Panel B: Differential Attrition", "attrition"),
        ("Panel C: Lee Bounds", "lee_bounds"),
        ("Panel D: Logit vs LPM", "logit_vs_lpm"),
        ("Panel E: Placebo Outcomes", "placebo"),
        ("Panel F: Wild Cluster Bootstrap", "wild_cluster_bootstrap"),
    ]

    for panel_name, test_key in panels:
        panel_data = robust[robust["test"] == test_key]
        if len(panel_data) == 0:
            continue

        tex.append(f"\\multicolumn{{6}}{{l}}{{\\textit{{{panel_name}}}}} \\\\")

        for _, r in panel_data.iterrows():
            arm = r.get("arm", "---")
            arm_label = arm.replace("_", " ").title() if arm != "---" else "---"
            pval = r.get("pvalue", np.nan)
            stars = fmt_stars(pval)

            if test_key == "lee_bounds":
                # Show bounds in estimate column
                lb = r.get("ci_lower", np.nan)
                ub = r.get("ci_upper", np.nan)
                tex.append(
                    f"  & {arm_label} "
                    f"& [{fmt(lb)}, {fmt(ub)}] "
                    f"& --- & --- "
                    f"& {int(r['N']) if pd.notna(r.get('N')) and r['N'] > 0 else '---'} \\\\"
                )
            elif test_key == "balance_ftest":
                tex.append(
                    f"  & {arm_label} "
                    f"& F={fmt(r['estimate'], 3)} "
                    f"& --- & {fmt(pval)}{stars} "
                    f"& {int(r['N']) if pd.notna(r.get('N')) and r['N'] > 0 else '---'} \\\\"
                )
            else:
                tex.append(
                    f"  & {arm_label} "
                    f"& {fmt(r['estimate'])}{stars} "
                    f"& ({fmt(r.get('se_robust', np.nan))}) "
                    f"& {fmt(pval)} "
                    f"& {int(r['N']) if pd.notna(r.get('N')) and r['N'] > 0 else '---'} \\\\"
                )
        tex.append(r"\addlinespace")

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} Panel A reports F-statistics from regressing each "
        r"treatment arm indicator on all covariates (test of random assignment). "
        r"Panel B tests whether treatment predicts attrition. "
        r"Panel C reports Lee (2009) trimming bounds under worst-case selective attrition. "
        r"Panel D compares logit marginal effects to linear probability model (binary outcomes). "
        r"Panel E tests for effects on placebo/baseline outcomes. "
        r"Panel F reports wild cluster bootstrap p-values (Rademacher weights). "
        r"$^{*}p<0.10$, $^{**}p<0.05$, $^{***}p<0.01$. "
        r"'---' indicates not applicable or unavailable.",
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
# FIGURE 1: Coefficient Plot by Arm with 95% CIs
# ═══════════════════════════════════════════════════════════════════════════════
def make_figure1(results):
    print("Generating Figure 1: Coefficient plot by arm...")

    # Use baseline (no controls) specification
    baseline = results[results["specification"] == "itt_no_controls"].copy()
    # Exclude interaction terms
    baseline = baseline[~baseline["arm"].str.contains("_x_")]

    if len(baseline) == 0:
        print("  No baseline ITT results. Skipping.")
        return

    outcomes = baseline["outcome"].unique()
    arms = baseline["arm"].unique()
    n_outcomes = len(outcomes)
    n_arms = len(arms)

    # Color palette
    colors = ["#2166ac", "#b2182b", "#4daf4a", "#984ea3", "#ff7f00"][:n_arms]

    fig, axes = plt.subplots(1, n_outcomes, figsize=(4 * n_outcomes, 5), squeeze=False)

    for j, outcome in enumerate(outcomes):
        ax = axes[0, j]
        for i, arm in enumerate(arms):
            match = baseline[(baseline["outcome"] == outcome) & (baseline["arm"] == arm)]
            if len(match) == 0:
                continue
            est = match.iloc[0]["estimate"]
            ci_lo = match.iloc[0].get("ci_lower", est)
            ci_hi = match.iloc[0].get("ci_upper", est)

            # Handle NaN in CIs
            if np.isnan(ci_lo):
                ci_lo = est
            if np.isnan(ci_hi):
                ci_hi = est

            ax.errorbar(i, est, yerr=[[est - ci_lo], [ci_hi - est]],
                        fmt="o", color=colors[i % len(colors)],
                        capsize=6, capthick=2, markersize=10, linewidth=2,
                        label=arm.replace("_", " ").title())

        ax.axhline(y=0, color="black", linestyle="--", linewidth=1, alpha=0.5)
        ax.set_xticks(range(n_arms))
        ax.set_xticklabels([a.replace("_", " ").title() for a in arms],
                           fontsize=10, rotation=15, ha="right")
        ax.set_ylabel("ITT Estimate", fontsize=12)
        ax.set_title(outcome.replace("_", " ").title(), fontsize=13)
        ax.grid(True, alpha=0.3, axis="y")
        if j == 0:
            ax.legend(fontsize=9)

    plt.suptitle("Treatment Effects by Arm (ITT, 95% CI)", fontsize=14, y=1.02)
    plt.tight_layout()

    for ext in ["png", "pdf"]:
        path = os.path.join(FIGURES_DIR, f"figure_1_coefficient_plot.{ext}")
        plt.savefig(path, dpi=150 if ext == "png" else 300, bbox_inches="tight")
    plt.close("all")
    print(f"  Saved: figure_1_coefficient_plot.png/.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 2: Lee Bounds Visualization
# ═══════════════════════════════════════════════════════════════════════════════
def make_figure2(robust):
    print("Generating Figure 2: Lee bounds visualization...")

    lee_data = robust[robust["test"] == "lee_bounds"].copy()
    if len(lee_data) == 0:
        print("  No Lee bounds results. Skipping.")
        return

    arms = lee_data["arm"].unique()
    n_arms = len(arms)
    colors = ["#2166ac", "#b2182b", "#4daf4a", "#984ea3", "#ff7f00"][:n_arms]

    fig, ax = plt.subplots(figsize=(max(6, 2 * n_arms + 2), 5))

    for i, arm in enumerate(arms):
        match = lee_data[lee_data["arm"] == arm]
        if len(match) == 0:
            continue

        est = match.iloc[0]["estimate"]
        lb = match.iloc[0].get("ci_lower", est)
        ub = match.iloc[0].get("ci_upper", est)

        # Handle NaN
        if np.isnan(est):
            est = 0
        if np.isnan(lb):
            lb = est
        if np.isnan(ub):
            ub = est

        # Point estimate
        ax.plot(i, est, "o", color=colors[i % len(colors)], markersize=12, zorder=3)

        # Bounds range (shaded bar)
        ax.fill_between([i - 0.15, i + 0.15], lb, ub,
                        color=colors[i % len(colors)], alpha=0.3, zorder=2)
        ax.plot([i, i], [lb, ub], color=colors[i % len(colors)],
                linewidth=3, zorder=2)

        # Labels
        ax.annotate(f"[{lb:.3f}, {ub:.3f}]", xy=(i, ub),
                    xytext=(0, 10), textcoords="offset points",
                    ha="center", fontsize=9)

    ax.axhline(y=0, color="black", linestyle="--", linewidth=1, alpha=0.5)
    ax.set_xticks(range(n_arms))
    ax.set_xticklabels([a.replace("_", " ").title() for a in arms],
                       fontsize=11)
    ax.set_ylabel("Treatment Effect", fontsize=12)
    ax.set_title("Lee (2009) Trimming Bounds by Treatment Arm", fontsize=13)
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()

    for ext in ["png", "pdf"]:
        path = os.path.join(FIGURES_DIR, f"figure_2_lee_bounds.{ext}")
        plt.savefig(path, dpi=150 if ext == "png" else 300, bbox_inches="tight")
    plt.close("all")
    print(f"  Saved: figure_2_lee_bounds.png/.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 5: ANCOVA Results
# ═══════════════════════════════════════════════════════════════════════════════
def make_table5(results):
    print("Generating Table 5: ANCOVA results...")

    ancova_data = results[results["specification"] == "ancova"]
    if len(ancova_data) == 0:
        print("  No ANCOVA results. Skipping.")
        return

    outcomes = ancova_data["outcome"].unique()
    arms = [a for a in ancova_data["arm"].unique() if "_x_" not in str(a)]

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{ANCOVA Estimates: Controlling for Baseline Outcome}",
        r"\label{tab:ancova}",
        f"\\begin{{tabular}}{{l {'c' * len(outcomes)}}}",
        r"\toprule",
    ]

    header = ""
    for outcome in outcomes:
        header += f" & {outcome}"
    tex.append(header + " \\\\")
    tex.append(r"\midrule")

    for arm in arms:
        tex.append(f"\\multicolumn{{{len(outcomes)+1}}}{{l}}"
                   f"{{\\textit{{{arm.replace('_', ' ').title()}}}}} \\\\")
        row_est = "  Estimate"
        row_se = "  SE"
        for outcome in outcomes:
            match = ancova_data[(ancova_data["outcome"] == outcome) &
                                (ancova_data["arm"] == arm)]
            if len(match) > 0:
                r = match.iloc[0]
                stars = fmt_stars(r.get("pvalue", np.nan))
                row_est += f" & {fmt(r['estimate'])}{stars}"
                row_se += f" & ({fmt(r['se_robust'])})"
            else:
                row_est += " & ---"
                row_se += " & ---"
        tex.append(row_est + " \\\\")
        tex.append(row_se + " \\\\")

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} ANCOVA specification: $Y_{post} \sim T + Y_{baseline} + X$. "
        r"More efficient than simple ITT when baseline outcome is available. "
        r"$^{*}p<0.10$, $^{**}p<0.05$, $^{***}p<0.01$.",
        r"\end{tablenotes}",
        r"\end{table}",
    ]

    content = "\n".join(tex)
    content = validate_table(content, "table_5_ancova.tex")
    path = os.path.join(TABLES_DIR, "table_5_ancova.tex")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 6: Power Calculations
# ═══════════════════════════════════════════════════════════════════════════════
def make_table6(results):
    print("Generating Table 6: Power calculations...")

    power_data = results[results["specification"] == "power_calculation"]
    if len(power_data) == 0:
        print("  No power calculations. Skipping.")
        return

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Power Analysis: Minimum Detectable Effects}",
        r"\label{tab:power}",
        r"\begin{tabular}{l l cccc}",
        r"\toprule",
        r"Outcome & Arm & MDE & Cohen's $d$ MDE & SD & N \\",
        r"\midrule",
    ]

    for _, r in power_data.iterrows():
        arm = str(r.get("arm", "---")).replace("_", " ").title()
        n_val = int(r.get("N", 0)) if pd.notna(r.get("N")) else "---"
        tex.append(
            f"  {r.get('outcome', '---')} & {arm} "
            f"& {fmt(r['estimate'])} & {fmt(r['se_robust'], 3)} "
            f"& {fmt(r.get('ci_lower', np.nan))} & {n_val} \\\\"
        )

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} MDE at 80\% power, $\alpha = 0.05$, two-sided test. "
        r"Cohen's $d$ MDE = MDE / SD(outcome). Compare realized estimate to MDE "
        r"to assess whether study was adequately powered.",
        r"\end{tablenotes}",
        r"\end{table}",
    ]

    content = "\n".join(tex)
    content = validate_table(content, "table_6_power.tex")
    path = os.path.join(TABLES_DIR, "table_6_power.tex")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE A1: Specification Curve (Appendix)
# ═══════════════════════════════════════════════════════════════════════════════
def make_table_a1(results):
    print("Generating Table A1: Specification curve...")

    sc_data = results[results["specification"].str.startswith("spec_curve_")]
    if len(sc_data) == 0:
        print("  No specification curve results. Skipping.")
        return

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Specification Curve: ITT Estimates Across Models}",
        r"\label{tab:spec_curve}",
        r"\begin{tabular}{l l cccc}",
        r"\toprule",
        r"Arm & Specification & Estimate & SE & 95\% CI & $p$-value \\",
        r"\midrule",
    ]

    for _, r in sc_data.iterrows():
        arm = str(r.get("arm", "---")).replace("_", " ").title()
        spec = str(r.get("specification", "---")).replace("spec_curve_", "").replace("_", " ").title()
        pval = r.get("pvalue", np.nan)
        stars = fmt_stars(pval)
        tex.append(
            f"  {arm} & {spec} & {fmt(r['estimate'])}{stars} "
            f"& ({fmt(r['se_robust'])}) "
            f"& [{fmt(r.get('ci_lower', np.nan))}, {fmt(r.get('ci_upper', np.nan))}] "
            f"& {fmt(pval)} \\\\"
        )

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} ITT estimates across all control set $\times$ "
        r"functional form combinations. LPM = linear probability model, "
        r"Probit/Logit report average marginal effects. "
        r"$^{*}p<0.10$, $^{**}p<0.05$, $^{***}p<0.01$.",
        r"\end{tablenotes}",
        r"\end{table}",
    ]

    content = "\n".join(tex)
    content = validate_table(content, "table_a1_spec_curve.tex")
    path = os.path.join(TABLES_DIR, "table_a1_spec_curve.tex")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE A2: Quantile Treatment Effects (Appendix)
# ═══════════════════════════════════════════════════════════════════════════════
def make_table_a2(robust):
    print("Generating Table A2: Quantile treatment effects...")

    qte_data = robust[robust["test"].str.startswith("qte_")]
    if len(qte_data) == 0:
        print("  No QTE results. Skipping.")
        return

    arms = qte_data["arm"].unique()
    quantiles = sorted(qte_data["test"].unique())

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Quantile Treatment Effects}",
        r"\label{tab:qte}",
        f"\\begin{{tabular}}{{l {'c' * len(quantiles)}}}",
        r"\toprule",
    ]

    header = "Arm"
    for q in quantiles:
        q_label = q.replace("qte_q", "Q")
        header += f" & {q_label}"
    tex.append(header + " \\\\")
    tex.append(r"\midrule")

    for arm in arms:
        arm_label = str(arm).replace("_", " ").title()
        row_est = f"  {arm_label}"
        row_se = "  "
        for q in quantiles:
            match = qte_data[(qte_data["arm"] == arm) & (qte_data["test"] == q)]
            if len(match) > 0:
                r = match.iloc[0]
                stars = fmt_stars(r.get("pvalue", np.nan))
                row_est += f" & {fmt(r['estimate'])}{stars}"
                row_se += f" & ({fmt(r['se_robust'])})"
            else:
                row_est += " & ---"
                row_se += " & ---"
        tex.append(row_est + " \\\\")
        tex.append(row_se + " \\\\")
        tex.append(r"\addlinespace")

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} Quantile regression estimates of treatment effects at "
        r"the 10th, 25th, 50th, 75th, and 90th percentiles. Standard errors "
        r"in parentheses. $^{*}p<0.10$, $^{**}p<0.05$, $^{***}p<0.01$.",
        r"\end{tablenotes}",
        r"\end{table}",
    ]

    content = "\n".join(tex)
    content = validate_table(content, "table_a2_qte.tex")
    path = os.path.join(TABLES_DIR, "table_a2_qte.tex")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 3: Specification Curve Plot
# ═══════════════════════════════════════════════════════════════════════════════
def make_figure3(results):
    print("Generating Figure 3: Specification curve plot...")

    sc_data = results[results["specification"].str.startswith("spec_curve_")]
    if len(sc_data) == 0:
        print("  No specification curve results. Skipping.")
        return

    sc = sc_data.sort_values("estimate").reset_index(drop=True)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7),
                                     gridspec_kw={"height_ratios": [3, 1]},
                                     sharex=True)

    colors = []
    for _, r in sc.iterrows():
        spec = str(r.get("specification", ""))
        if "probit" in spec.lower():
            colors.append("#ef8a62")
        elif "logit" in spec.lower():
            colors.append("#4daf4a")
        else:
            colors.append("#2166ac")

    for i, (_, r) in enumerate(sc.iterrows()):
        ci_lo = r.get("ci_lower", r["estimate"])
        ci_hi = r.get("ci_upper", r["estimate"])
        if pd.isna(ci_lo):
            ci_lo = r["estimate"]
        if pd.isna(ci_hi):
            ci_hi = r["estimate"]
        ax1.errorbar(i, r["estimate"],
                     yerr=[[r["estimate"] - ci_lo], [ci_hi - r["estimate"]]],
                     fmt="o", color=colors[i], capsize=3, markersize=5)

    ax1.axhline(y=0, color="black", linestyle="--", linewidth=1, alpha=0.5)
    ax1.set_ylabel("ITT Estimate", fontsize=11)
    ax1.set_title("Specification Curve", fontsize=13)
    ax1.grid(True, alpha=0.3, axis="y")

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#2166ac", label="LPM"),
        Patch(facecolor="#ef8a62", label="Probit"),
        Patch(facecolor="#4daf4a", label="Logit"),
    ]
    ax1.legend(handles=legend_elements, fontsize=9, loc="best")

    # Indicator matrix
    control_types = ["no_controls", "demographics", "full_controls", "ancova"]
    spec_names = sc["specification"].tolist()
    indicator = np.zeros((len(control_types), len(spec_names)))
    for j, spec in enumerate(spec_names):
        for i, ct in enumerate(control_types):
            if ct in str(spec).lower():
                indicator[i, j] = 1

    ax2.imshow(indicator, cmap="Blues", aspect="auto", interpolation="nearest")
    ax2.set_yticks(range(len(control_types)))
    ax2.set_yticklabels(["None", "Demog.", "Full", "ANCOVA"], fontsize=9)
    ax2.set_xlabel("Specification (sorted)", fontsize=11)
    ax2.set_xticks([])

    plt.tight_layout()
    for ext in ["png", "pdf"]:
        path = os.path.join(FIGURES_DIR, f"figure_3_spec_curve.{ext}")
        plt.savefig(path, dpi=150 if ext == "png" else 300, bbox_inches="tight")
    plt.close("all")
    print(f"  Saved: figure_3_spec_curve.png/.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 4: Quantile Treatment Effects
# ═══════════════════════════════════════════════════════════════════════════════
def make_figure4(robust):
    print("Generating Figure 4: Quantile treatment effects plot...")

    qte_data = robust[robust["test"].str.startswith("qte_")]
    if len(qte_data) == 0:
        print("  No QTE results. Skipping.")
        return

    arms = qte_data["arm"].unique()
    colors = ["#2166ac", "#b2182b", "#4daf4a", "#984ea3"]

    fig, ax = plt.subplots(figsize=(8, 5))

    for k, arm in enumerate(arms):
        arm_data = qte_data[qte_data["arm"] == arm].copy()
        # Extract quantile from test name
        arm_data["quantile"] = arm_data["test"].str.extract(r"q(\d+)").astype(float) / 100
        arm_data = arm_data.sort_values("quantile")

        ax.plot(arm_data["quantile"], arm_data["estimate"], "o-",
                color=colors[k % len(colors)], linewidth=2, markersize=8,
                label=str(arm).replace("_", " ").title())

        # CI band
        ci_lo = arm_data["ci_lower"].values
        ci_hi = arm_data["ci_upper"].values
        ax.fill_between(arm_data["quantile"], ci_lo, ci_hi,
                        color=colors[k % len(colors)], alpha=0.15)

    ax.axhline(y=0, color="black", linestyle="--", linewidth=1, alpha=0.5)
    ax.set_xlabel("Quantile", fontsize=12)
    ax.set_ylabel("Treatment Effect", fontsize=12)
    ax.set_title("Quantile Treatment Effects", fontsize=13)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    for ext in ["png", "pdf"]:
        path = os.path.join(FIGURES_DIR, f"figure_4_qte.{ext}")
        plt.savefig(path, dpi=150 if ext == "png" else 300, bbox_inches="tight")
    plt.close("all")
    print(f"  Saved: figure_4_qte.png/.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 5: CONSORT-style Sample Flow
# ═══════════════════════════════════════════════════════════════════════════════
def make_figure5(df):
    print("Generating Figure 5: CONSORT sample flow...")

    n_total = len(df)

    # Try to identify treatment column
    treat_col = None
    arm_vals_set = set(TREATMENT_ARMS.values())
    for col in df.columns:
        vals = set(df[col].dropna().unique())
        if arm_vals_set.issubset(vals) or vals == arm_vals_set:
            treat_col = col
            break
    if treat_col is None:
        treat_col = TREATMENT_VAR if TREATMENT_VAR in df.columns else None

    n_valid_treat = df[treat_col].notna().sum() if treat_col and treat_col in df.columns else n_total
    n_outcome = df[PRIMARY_OUTCOME].notna().sum() if PRIMARY_OUTCOME in df.columns else n_total

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis("off")

    # Top box: total randomized
    ax.add_patch(plt.Rectangle((3, 10.5), 4, 1, fill=True,
                                facecolor="#e6f0ff", edgecolor="#2166ac", linewidth=1.5))
    ax.text(5, 11, f"Randomized\nN = {n_total:,}", ha="center", va="center",
            fontsize=11, fontweight="bold")

    # Per-arm boxes
    arm_names = list(TREATMENT_ARMS.keys())
    n_arms = len(arm_names)
    arm_width = min(3, 8.0 / n_arms)
    arm_spacing = 8.0 / n_arms
    arm_colors = ["#d1e5f0", "#fddbc7", "#d9f0d3", "#e6d5f0"]

    for i, (arm_name, arm_val) in enumerate(TREATMENT_ARMS.items()):
        x_center = 1 + arm_spacing * (i + 0.5)

        # Allocated
        if treat_col and treat_col in df.columns:
            n_arm = (df[treat_col] == arm_val).sum()
        else:
            n_arm = n_total // n_arms

        ax.add_patch(plt.Rectangle((x_center - arm_width / 2, 8), arm_width, 1,
                                    fill=True, facecolor=arm_colors[i % len(arm_colors)],
                                    edgecolor="#333333", linewidth=1))
        ax.text(x_center, 8.5, f"{arm_name}\nN = {n_arm:,}",
                ha="center", va="center", fontsize=9, fontweight="bold")

        # Arrow from top
        ax.annotate("", xy=(x_center, 9), xytext=(5, 10.5),
                     arrowprops=dict(arrowstyle="->", color="#333333", lw=1))

        # Analyzed
        if PRIMARY_OUTCOME in df.columns and treat_col and treat_col in df.columns:
            arm_df = df[df[treat_col] == arm_val]
            n_analyzed = arm_df[PRIMARY_OUTCOME].notna().sum()
            n_lost = n_arm - n_analyzed
        else:
            n_analyzed = n_arm
            n_lost = 0

        ax.add_patch(plt.Rectangle((x_center - arm_width / 2, 5.5), arm_width, 1,
                                    fill=True, facecolor=arm_colors[i % len(arm_colors)],
                                    edgecolor="#333333", linewidth=1))
        ax.text(x_center, 6, f"Analyzed\nN = {n_analyzed:,}",
                ha="center", va="center", fontsize=9)

        ax.annotate("", xy=(x_center, 6.5), xytext=(x_center, 8),
                     arrowprops=dict(arrowstyle="->", color="#333333", lw=1))

        if n_lost > 0:
            ax.text(x_center + arm_width / 2 + 0.1, 7.25,
                    f"Lost: {n_lost:,}", fontsize=8, color="#b2182b", style="italic")

    ax.set_title("CONSORT-Style Sample Flow", fontsize=14, fontweight="bold", pad=20)
    plt.tight_layout()

    for ext in ["png", "pdf"]:
        path = os.path.join(FIGURES_DIR, f"figure_5_consort_flow.{ext}")
        plt.savefig(path, dpi=150 if ext == "png" else 300, bbox_inches="tight")
    plt.close("all")
    print(f"  Saved: figure_5_consort_flow.png/.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("03_output.py — RCT Tables and Figures (Expanded)")
    print("=" * 70)

    df = pd.read_csv(os.path.join(DATA_DIR, "clean_data.csv"))
    print(f"Clean data: {len(df)} rows")

    main_results = pd.read_csv(os.path.join(DATA_DIR, "main_results.csv"))
    print(f"Main results: {len(main_results)} rows")

    robust_path = os.path.join(DATA_DIR, "robustness_results.csv")
    robust = pd.read_csv(robust_path) if os.path.exists(robust_path) else None
    if robust is not None:
        print(f"Robustness: {len(robust)} rows")

    print()
    # ── Core tables ───────────────────────────────────────────────────────
    make_table1(df)                          # Summary stats by arm
    make_table2(main_results)                # Main ITT results
    make_table3(main_results)                # Heterogeneity
    if robust is not None:
        make_table4(robust)                  # Robustness
    make_table5(main_results)                # ANCOVA
    make_table6(main_results)                # Power calculations
    make_table_a1(main_results)              # Spec curve (appendix)
    if robust is not None:
        make_table_a2(robust)                # QTE (appendix)

    print()
    # ── Core figures ──────────────────────────────────────────────────────
    make_figure1(main_results)               # Coefficient plot
    if robust is not None:
        make_figure2(robust)                 # Lee bounds
    make_figure3(main_results)               # Specification curve
    if robust is not None:
        make_figure4(robust)                 # QTE
    make_figure5(df)                         # CONSORT flow

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
