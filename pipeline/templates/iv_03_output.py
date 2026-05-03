"""03_output.py — IV/2SLS tables and figures template.

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
ENDOGENOUS_VAR = "{{ENDOGENOUS_VAR}}"
INSTRUMENT_VARS = {{INSTRUMENT_VARS}}
COVARIATES = {{COVARIATES}}
CLUSTER_VAR = "{{CLUSTER_VAR}}"
HETEROGENEITY_VARS = {{HETEROGENEITY_VARS}}
MEDIATOR_VAR = "{{MEDIATOR_VAR}}"

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
    if pval is None or np.isnan(pval):
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
# TABLE 1: Summary Statistics
# ═══════════════════════════════════════════════════════════════════════════════
def make_table1(df):
    print("Generating Table 1: Summary statistics...")

    stat_vars = OUTCOME_VARS + [ENDOGENOUS_VAR] + INSTRUMENT_VARS + COVARIATES
    stat_vars = list(dict.fromkeys([v for v in stat_vars if v in df.columns]))

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Summary Statistics}",
        r"\label{tab:summary}",
        r"\begin{tabular}{l ccccc}",
        r"\toprule",
        r"Variable & Mean & SD & Min & Max & N \\",
        r"\midrule",
    ]

    # Separate sections: outcomes, endogenous, instruments, controls
    sections = [
        ("Outcome Variables", OUTCOME_VARS),
        ("Endogenous Variable", [ENDOGENOUS_VAR]),
        ("Instruments", INSTRUMENT_VARS),
        ("Controls", COVARIATES),
    ]

    for sec_name, sec_vars in sections:
        present = [v for v in sec_vars if v in df.columns]
        if not present:
            continue
        tex.append(f"\\addlinespace")
        tex.append(f"\\multicolumn{{6}}{{l}}{{\\textit{{{sec_name}}}}} \\\\")
        for var in present:
            s = df[var].dropna()
            tex.append(
                f"  {var} & {fmt(s.mean())} & {fmt(s.std())} "
                f"& {fmt(s.min())} & {fmt(s.max())} & {len(s)} \\\\"
            )

    tex += [
        r"\midrule",
        f"  Total Observations & \\multicolumn{{5}}{{c}}{{{len(df)}}} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} Summary statistics for the IV analysis sample. "
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
# TABLE 2: First Stage Results
# ═══════════════════════════════════════════════════════════════════════════════
def make_table2(results):
    print("Generating Table 2: First stage results...")

    fs_data = results[results["specification"] == "first_stage"]
    if len(fs_data) == 0:
        print("  No first stage results found. Skipping.")
        return

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{First Stage Results: Effect of Instruments on Endogenous Variable}",
        r"\label{tab:first_stage}",
        r"\begin{tabular}{l cc}",
        r"\toprule",
        f"  & \\multicolumn{{2}}{{c}}{{{ENDOGENOUS_VAR}}} \\\\",
        r"\midrule",
    ]

    for _, r in fs_data.iterrows():
        z_name = r.get("instrument", "---")
        pval = r.get("pvalue", np.nan)
        stars = fmt_stars(pval)
        tex.append(f"  {z_name} & {fmt(r['estimate'])}{stars} & \\\\")
        tex.append(f"  & ({fmt(r['se_robust'])}) & \\\\")

    # F-statistic row (prominently displayed)
    f_stat = fs_data.iloc[0].get("first_stage_F", np.nan)
    tex.append(r"\addlinespace")
    tex.append(r"\midrule")
    tex.append(f"  \\textbf{{First-stage F-statistic}} & \\multicolumn{{2}}{{c}}{{\\textbf{{{fmt(f_stat, 2)}}}}} \\\\")

    # Flag weak instrument
    if not (f_stat is None or (isinstance(f_stat, float) and np.isnan(f_stat))):
        if float(f_stat) < 10:
            tex.append(r"  \textbf{WEAK INSTRUMENT} & \multicolumn{2}{c}{\textbf{F $<$ 10}} \\")

    n_obs = fs_data.iloc[0].get("N", "---")
    tex.append(f"  Observations & \\multicolumn{{2}}{{c}}{{{int(n_obs) if pd.notna(n_obs) else '---'}}} \\\\")

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} First stage regression of the endogenous variable on "
        r"instrument(s) and controls. Robust standard errors in parentheses. "
        r"F-statistic tests joint significance of excluded instruments. "
        r"Stock-Yogo critical value for 10\% maximal IV size: 16.38 (1 endogenous, 1 instrument). "
        r"$^{***}$p$<$0.01, $^{**}$p$<$0.05, $^{*}$p$<$0.10. "
        r"'---' indicates unavailable data.",
        r"\end{tablenotes}",
        r"\end{table}",
    ]

    content = "\n".join(tex)
    content = validate_table(content, "table_2_first_stage.tex")
    path = os.path.join(TABLES_DIR, "table_2_first_stage.tex")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 3: Main Results (OLS vs 2SLS vs Reduced Form)
# ═══════════════════════════════════════════════════════════════════════════════
def make_table3(results):
    print("Generating Table 3: Main results (OLS vs 2SLS vs reduced form)...")

    outcomes = [o for o in OUTCOME_VARS if o in results["outcome"].unique()]
    specs = ["OLS", "2SLS", "reduced_form"]
    spec_labels = {"OLS": "OLS", "2SLS": "2SLS", "reduced_form": "Reduced Form"}

    n_cols = len(outcomes) * len(specs)

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Main Results: OLS, 2SLS, and Reduced Form Estimates}",
        r"\label{tab:main_results}",
        f"\\begin{{tabular}}{{l {'c' * n_cols}}}",
        r"\toprule",
    ]

    # Outcome headers
    header1 = ""
    for outcome in outcomes:
        header1 += f" & \\multicolumn{{{len(specs)}}}{{c}}{{{outcome}}}"
    tex.append(header1 + " \\\\")

    # Cmidrule for each outcome
    col_start = 2
    for outcome in outcomes:
        col_end = col_start + len(specs) - 1
        tex.append(f"\\cmidrule(lr){{{col_start}-{col_end}}}")
        col_start = col_end + 1

    # Spec headers
    header2 = ""
    for outcome in outcomes:
        for spec in specs:
            header2 += f" & {spec_labels[spec]}"
    tex.append(header2 + " \\\\")
    tex.append(r"\midrule")

    # Coefficient row (endogenous var for OLS/2SLS, instrument for RF)
    row_est = f"  {ENDOGENOUS_VAR}"
    row_se = "  "
    row_ci = "  95\\% CI"
    row_n = "  N"
    row_f = "  First-stage F"

    for outcome in outcomes:
        for spec in specs:
            match = results[(results["outcome"] == outcome) &
                            (results["specification"] == spec)]
            if len(match) > 0:
                r = match.iloc[0]
                pval = r.get("pvalue", np.nan)
                stars = fmt_stars(pval)
                row_est += f" & {fmt(r['estimate'])}{stars}"
                row_se += f" & ({fmt(r['se_robust'])})"
                row_ci += f" & [{fmt(r.get('ci_lower', np.nan))}, {fmt(r.get('ci_upper', np.nan))}]"
                n_val = r.get("N", np.nan)
                row_n += f" & {int(n_val) if pd.notna(n_val) else '---'}"
                f_val = r.get("first_stage_F", np.nan)
                row_f += f" & {fmt(f_val, 2)}"
            else:
                row_est += " & ---"
                row_se += " & ---"
                row_ci += " & ---"
                row_n += " & ---"
                row_f += " & ---"

    tex.append(row_est + " \\\\")
    tex.append(row_se + " \\\\")
    tex.append(row_ci + " \\\\")
    tex.append(r"\addlinespace")
    tex.append(row_f + " \\\\")
    tex.append(row_n + " \\\\")

    # Hausman test row
    hausman_data = results[results["specification"] == "hausman_test"]
    if len(hausman_data) > 0:
        tex.append(r"\addlinespace")
        row_h = "  Hausman p-val"
        for outcome in outcomes:
            h_match = hausman_data[hausman_data["outcome"] == outcome]
            if len(h_match) > 0:
                h_pval = h_match.iloc[0].get("pvalue", np.nan)
                row_h += f" & \\multicolumn{{{len(specs)}}}{{c}}{{{fmt(h_pval)}}}"
            else:
                row_h += f" & \\multicolumn{{{len(specs)}}}{{c}}{{---}}"
        tex.append(row_h + " \\\\")

    # Over-id test row
    overid_data = results[results["specification"] == "overid_test"]
    if len(overid_data) > 0:
        row_j = "  Sargan J p-val"
        for outcome in outcomes:
            j_match = overid_data[overid_data["outcome"] == outcome]
            if len(j_match) > 0:
                j_pval = j_match.iloc[0].get("pvalue", np.nan)
                row_j += f" & \\multicolumn{{{len(specs)}}}{{c}}{{{fmt(j_pval)}}}"
            else:
                row_j += f" & \\multicolumn{{{len(specs)}}}{{c}}{{---}}"
        tex.append(row_j + " \\\\")

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} Column (1) reports OLS estimates, (2) reports 2SLS "
        r"estimates using the listed instruments, (3) reports reduced form estimates "
        r"(effect of instrument on outcome directly). Robust/clustered standard errors "
        r"in parentheses. First-stage F-statistic reported for 2SLS. "
        r"Hausman test p-value tests equality of OLS and 2SLS coefficients. "
        r"$^{***}$p$<$0.01, $^{**}$p$<$0.05, $^{*}$p$<$0.10. "
        r"'---' indicates unavailable data.",
        r"\end{tablenotes}",
        r"\end{table}",
    ]

    content = "\n".join(tex)
    content = validate_table(content, "table_3_main_results.tex")
    path = os.path.join(TABLES_DIR, "table_3_main_results.tex")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 4: Robustness (weak instrument, alternative instruments, placebo)
# ═══════════════════════════════════════════════════════════════════════════════
def make_table4(robust):
    print("Generating Table 4: Robustness...")

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Robustness Checks}",
        r"\label{tab:robustness}",
        r"\begin{tabular}{l cccccc}",
        r"\toprule",
        r"Test & Estimate & SE & 95\% CI & F-stat & N \\",
        r"\midrule",
    ]

    panels = [
        ("Panel A: Weak Instrument Diagnostics",
         ["first_stage_partial_F", "cragg_donald_F", "kleibergen_paap_F", "anderson_rubin_ci"]),
        ("Panel B: Alternative Instruments",
         [t for t in robust["test"].unique() if t.startswith("alt_instrument_")]),
        ("Panel C: Placebo Tests",
         [t for t in robust["test"].unique() if t.startswith("placebo_")]),
        ("Panel D: Exclusion Restriction Sensitivity",
         [t for t in robust["test"].unique() if t.startswith("conley_")]),
        ("Panel E: Bootstrap",
         [t for t in robust["test"].unique() if t.startswith("wild_cluster")]),
    ]

    for panel_name, test_names in panels:
        panel_data = robust[robust["test"].isin(test_names)]
        if len(panel_data) == 0:
            continue
        tex.append(f"\\addlinespace")
        tex.append(f"\\multicolumn{{6}}{{l}}{{\\textit{{{panel_name}}}}} \\\\")

        for _, r in panel_data.iterrows():
            label = r.get("test", "---").replace("_", " ").title()
            f_val = r.get("first_stage_F", np.nan)
            n_val = r.get("N", np.nan)
            tex.append(
                f"  {label} & {fmt(r['estimate'])} & {fmt(r.get('se_robust', np.nan))} "
                f"& [{fmt(r.get('ci_lower', np.nan))}, {fmt(r.get('ci_upper', np.nan))}] "
                f"& {fmt(f_val, 2)} "
                f"& {int(n_val) if pd.notna(n_val) and n_val > 0 else '---'} \\\\"
            )

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} Panel A reports weak instrument diagnostics. "
        r"Anderson-Rubin CI is robust to weak instruments. "
        r"Panel B reports 2SLS estimates using each instrument separately. "
        r"Panel C tests whether instruments predict placebo outcomes (should be insignificant). "
        r"Panel D reports Conley et al.\ bounds allowing direct effect of instrument on outcome. "
        r"Panel E reports wild cluster bootstrap CI. "
        r"'---' indicates unavailable data.",
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
# FIGURE 1: First Stage Scatter/Binscatter (instrument vs endogenous)
# ═══════════════════════════════════════════════════════════════════════════════
def make_figure1(df):
    print("Generating Figure 1: First stage scatter...")

    z_var = INSTRUMENT_VARS[0]
    if z_var not in df.columns or ENDOGENOUS_VAR not in df.columns:
        print("  Missing instrument or endogenous variable. Skipping.")
        return

    sub = df[[z_var, ENDOGENOUS_VAR]].dropna()
    x = sub[z_var].values
    y = sub[ENDOGENOUS_VAR].values

    if len(x) < 20:
        print("  Insufficient data. Skipping.")
        return

    fig, ax = plt.subplots(figsize=(8, 5))

    # Binscatter if many observations
    if len(x) > 200:
        n_bins = 20
        # Use percentile-based bins for even counts
        percentiles = np.linspace(0, 100, n_bins + 1)
        bin_edges = np.percentile(x, percentiles)
        bin_edges = np.unique(bin_edges)
        n_actual_bins = len(bin_edges) - 1

        bx, by = [], []
        for i in range(n_actual_bins):
            if i < n_actual_bins - 1:
                mask = (x >= bin_edges[i]) & (x < bin_edges[i + 1])
            else:
                mask = (x >= bin_edges[i]) & (x <= bin_edges[i + 1])
            if mask.sum() > 0:
                bx.append(x[mask].mean())
                by.append(y[mask].mean())

        ax.scatter(bx, by, color="#2166ac", s=80, zorder=3, label="Bin means")
    else:
        ax.scatter(x, y, color="#2166ac", s=30, alpha=0.5, zorder=2, label="Observations")

    # Linear fit
    if len(x) > 2:
        coeffs = np.polyfit(x, y, 1)
        xs = np.linspace(x.min(), x.max(), 100)
        ax.plot(xs, np.poly1d(coeffs)(xs), color="#b2182b", linewidth=2,
                label=f"Linear fit (slope={coeffs[0]:.3f})")

    ax.set_xlabel(z_var.replace("_", " ").title(), fontsize=12)
    ax.set_ylabel(ENDOGENOUS_VAR.replace("_", " ").title(), fontsize=12)
    ax.set_title("First Stage: Instrument vs Endogenous Variable", fontsize=13)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    for ext in ["png", "pdf"]:
        path = os.path.join(FIGURES_DIR, f"figure_1_first_stage.{ext}")
        plt.savefig(path, dpi=150 if ext == "png" else 300, bbox_inches="tight")
    plt.close("all")
    print(f"  Saved: figure_1_first_stage.png/.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 2: OLS vs 2SLS Coefficient Comparison Plot
# ═══════════════════════════════════════════════════════════════════════════════
def make_figure2(results):
    print("Generating Figure 2: OLS vs 2SLS coefficient comparison...")

    outcomes = [o for o in OUTCOME_VARS if o in results["outcome"].unique()]
    if not outcomes:
        print("  No outcome results found. Skipping.")
        return

    ols_ests, ols_cis = [], []
    iv_ests, iv_cis = [], []
    labels = []

    for outcome in outcomes:
        ols_match = results[(results["outcome"] == outcome) &
                            (results["specification"] == "OLS")]
        iv_match = results[(results["outcome"] == outcome) &
                           (results["specification"] == "2SLS")]

        if len(ols_match) > 0 and len(iv_match) > 0:
            ols_r = ols_match.iloc[0]
            iv_r = iv_match.iloc[0]

            ols_est = ols_r["estimate"]
            iv_est = iv_r["estimate"]

            if pd.notna(ols_est) and pd.notna(iv_est):
                labels.append(outcome.replace("_", " ").title())
                ols_ests.append(ols_est)
                iv_ests.append(iv_est)

                ols_lo = ols_r.get("ci_lower", ols_est)
                ols_hi = ols_r.get("ci_upper", ols_est)
                iv_lo = iv_r.get("ci_lower", iv_est)
                iv_hi = iv_r.get("ci_upper", iv_est)

                ols_cis.append((
                    ols_est - ols_lo if pd.notna(ols_lo) else 0,
                    ols_hi - ols_est if pd.notna(ols_hi) else 0))
                iv_cis.append((
                    iv_est - iv_lo if pd.notna(iv_lo) else 0,
                    iv_hi - iv_est if pd.notna(iv_hi) else 0))

    if not labels:
        print("  No comparable OLS/2SLS results. Skipping.")
        return

    fig, ax = plt.subplots(figsize=(8, max(4, len(labels) * 1.5)))

    y_pos = np.arange(len(labels))
    offset = 0.15

    # OLS
    ols_yerr = np.array(ols_cis).T
    ax.errorbar(ols_ests, y_pos - offset, xerr=ols_yerr,
                fmt="s", color="#2166ac", capsize=5, capthick=2,
                markersize=8, linewidth=2, label="OLS")

    # 2SLS
    iv_yerr = np.array(iv_cis).T
    ax.errorbar(iv_ests, y_pos + offset, xerr=iv_yerr,
                fmt="o", color="#b2182b", capsize=5, capthick=2,
                markersize=8, linewidth=2, label="2SLS")

    ax.axvline(x=0, color="black", linestyle="--", linewidth=1, alpha=0.5)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=11)
    ax.set_xlabel("Coefficient Estimate", fontsize=12)
    ax.set_title("OLS vs 2SLS Estimates", fontsize=13)
    ax.legend(fontsize=10, loc="best")
    ax.grid(True, alpha=0.3, axis="x")
    plt.tight_layout()

    for ext in ["png", "pdf"]:
        path = os.path.join(FIGURES_DIR, f"figure_2_ols_vs_2sls.{ext}")
        plt.savefig(path, dpi=150 if ext == "png" else 300, bbox_inches="tight")
    plt.close("all")
    print(f"  Saved: figure_2_ols_vs_2sls.png/.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 5: Covariate Balance on Instrument
# ═══════════════════════════════════════════════════════════════════════════════
def make_table5(results):
    print("Generating Table 5: Covariate balance on instrument...")

    bal_data = results[results["specification"] == "balance_test"]
    if len(bal_data) == 0:
        print("  No balance results found. Skipping.")
        return

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Covariate Balance on Instrument}",
        r"\label{tab:balance}",
        r"\begin{tabular}{l cccc}",
        r"\toprule",
        r"Covariate & Coefficient & SE & $p$-value & SMD \\",
        r"\midrule",
    ]

    for _, r in bal_data.iterrows():
        cov_name = r.get("outcome", "---")
        pval = r.get("pvalue", np.nan)
        stars = fmt_stars(pval)
        smd = r.get("ci_lower", np.nan)  # SMD stored in ci_lower
        smd_flag = r" $\dagger$" if (not np.isnan(smd) and abs(smd) > 0.1) else ""
        tex.append(
            f"  {cov_name} & {fmt(r['estimate'])}{stars} & ({fmt(r['se_robust'])}) "
            f"& {fmt(pval)} & {fmt(smd, 3)}{smd_flag} \\\\"
        )

    tex += [
        r"\midrule",
        r"\multicolumn{5}{l}{\textit{Joint F-test reported in text}} \\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} Each row reports the coefficient from regressing the "
        r"covariate on the instrument with HC2 robust SEs. SMD = standardized mean "
        r"difference. $\dagger$ flags $|$SMD$| > 0.1$. "
        r"$^{***}$p$<$0.01, $^{**}$p$<$0.05, $^{*}$p$<$0.10.",
        r"\end{tablenotes}",
        r"\end{table}",
    ]

    content = "\n".join(tex)
    content = validate_table(content, "table_5_balance.tex")
    path = os.path.join(TABLES_DIR, "table_5_balance.tex")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 6: ITT with Multiple Specifications
# ═══════════════════════════════════════════════════════════════════════════════
def make_table6(results):
    print("Generating Table 6: ITT multiple specifications...")

    itt_specs = ["itt_no_controls", "itt_demographics", "itt_full_controls"]
    itt_data = results[results["specification"].isin(itt_specs)]
    if len(itt_data) == 0:
        print("  No multi-spec ITT results. Skipping.")
        return

    outcomes = [o for o in OUTCOME_VARS if o in itt_data["outcome"].unique()]
    spec_labels = {
        "itt_no_controls": "(1) No Controls",
        "itt_demographics": "(2) Demographics",
        "itt_full_controls": "(3) Full Controls",
    }
    specs_present = [s for s in itt_specs if s in itt_data["specification"].unique()]
    n_cols = len(outcomes) * len(specs_present)

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{ITT Estimates: Multiple Specifications}",
        r"\label{tab:itt_multi}",
        f"\\begin{{tabular}}{{l {'c' * n_cols}}}",
        r"\toprule",
    ]

    # Headers
    header1 = ""
    for outcome in outcomes:
        header1 += f" & \\multicolumn{{{len(specs_present)}}}{{c}}{{{outcome}}}"
    tex.append(header1 + " \\\\")

    header2 = ""
    for _ in outcomes:
        for spec in specs_present:
            header2 += f" & {spec_labels.get(spec, spec)}"
    tex.append(header2 + " \\\\")
    tex.append(r"\midrule")

    # Estimate row
    row_est = f"  {INSTRUMENT_VARS[0]}"
    row_se = "  "
    row_n = "  N"
    row_r2 = "  $R^2$"

    for outcome in outcomes:
        for spec in specs_present:
            match = itt_data[(itt_data["outcome"] == outcome) &
                             (itt_data["specification"] == spec)]
            if len(match) > 0:
                r = match.iloc[0]
                stars = fmt_stars(r.get("pvalue", np.nan))
                row_est += f" & {fmt(r['estimate'])}{stars}"
                row_se += f" & ({fmt(r['se_robust'])})"
                n_val = r.get("N", np.nan)
                row_n += f" & {int(n_val) if pd.notna(n_val) else '---'}"
                row_r2 += f" & {fmt(r.get('r_squared', np.nan), 3)}"
            else:
                row_est += " & ---"
                row_se += " & ---"
                row_n += " & ---"
                row_r2 += " & ---"

    tex.append(row_est + " \\\\")
    tex.append(row_se + " \\\\")
    tex.append(r"\addlinespace")
    tex.append(row_r2 + " \\\\")
    tex.append(row_n + " \\\\")

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} Reduced form (ITT) estimates across control sets. "
        r"HC2 robust SEs in parentheses. "
        r"$^{***}$p$<$0.01, $^{**}$p$<$0.05, $^{*}$p$<$0.10.",
        r"\end{tablenotes}",
        r"\end{table}",
    ]

    content = "\n".join(tex)
    content = validate_table(content, "table_6_itt_multi.tex")
    path = os.path.join(TABLES_DIR, "table_6_itt_multi.tex")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 7: Heterogeneity
# ═══════════════════════════════════════════════════════════════════════════════
def make_table7(results):
    print("Generating Table 7: Heterogeneity (IV interactions)...")

    het_data = results[results["specification"].str.startswith("heterogeneity")]
    if len(het_data) == 0:
        print("  No heterogeneity results. Skipping.")
        return

    moderators = het_data["specification"].str.replace("heterogeneity_", "").unique()

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Heterogeneous Treatment Effects (IV)}",
        r"\label{tab:heterogeneity}",
        r"\begin{tabular}{l ccccc}",
        r"\toprule",
        r"Interaction & Estimate & SE & 95\% CI & $p$-value & N \\",
        r"\midrule",
    ]

    for mod in moderators:
        mod_data = het_data[het_data["specification"] == f"heterogeneity_{mod}"]
        tex.append(f"\\multicolumn{{6}}{{l}}{{\\textit{{$\\times$ {mod}}}}} \\\\")
        for _, r in mod_data.iterrows():
            pval = r.get("pvalue", np.nan)
            stars = fmt_stars(pval)
            n_val = int(r.get("N", 0)) if pd.notna(r.get("N")) else "---"
            tex.append(
                f"  {r.get('outcome', '---')} & {fmt(r['estimate'])}{stars} "
                f"& ({fmt(r['se_robust'])}) "
                f"& [{fmt(r.get('ci_lower', np.nan))}, {fmt(r.get('ci_upper', np.nan))}] "
                f"& {fmt(pval)} & {n_val} \\\\"
            )
        tex.append(r"\addlinespace")

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} IV/2SLS estimates with treatment $\times$ moderator "
        r"interactions. Instruments: $Z$ and $Z \times$ moderator. "
        r"HC1 robust SEs in parentheses. "
        r"$^{***}$p$<$0.01, $^{**}$p$<$0.05, $^{*}$p$<$0.10.",
        r"\end{tablenotes}",
        r"\end{table}",
    ]

    content = "\n".join(tex)
    content = validate_table(content, "table_7_heterogeneity.tex")
    path = os.path.join(TABLES_DIR, "table_7_heterogeneity.tex")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 8: Mediation Decomposition (IKY 2010)
# ═══════════════════════════════════════════════════════════════════════════════
def make_table8(robust):
    print("Generating Table 8: Causal mediation decomposition...")

    med_tests = ["mediation_acme", "mediation_ade", "mediation_total"]
    med_data = robust[robust["test"].isin(med_tests)]
    if len(med_data) == 0:
        print("  No mediation results. Skipping.")
        return

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Causal Mediation Decomposition (Imai, Keele \& Yamamoto 2010)}",
        r"\label{tab:mediation}",
        r"\begin{tabular}{l cccc}",
        r"\toprule",
        r"Component & Estimate & SE & 95\% CI (Bootstrap) & N \\",
        r"\midrule",
    ]

    labels = {
        "mediation_acme": "ACME (Indirect Effect)",
        "mediation_ade": "ADE (Direct Effect)",
        "mediation_total": "Total Effect",
    }

    for test_key, label in labels.items():
        match = med_data[med_data["test"] == test_key]
        if len(match) > 0:
            r = match.iloc[0]
            n_val = int(r.get("N", 0)) if pd.notna(r.get("N")) else "---"
            tex.append(
                f"  {label} & {fmt(r['estimate'])} & {fmt(r['se_robust'])} "
                f"& [{fmt(r.get('ci_lower', np.nan))}, {fmt(r.get('ci_upper', np.nan))}] "
                f"& {n_val} \\\\"
            )

    # Proportion mediated (stored in total's ci_lower)
    total_match = med_data[med_data["test"] == "mediation_total"]
    if len(total_match) > 0:
        prop = total_match.iloc[0].get("ci_lower", np.nan)
        if not np.isnan(prop):
            tex.append(r"\addlinespace")
            tex.append(f"  Proportion Mediated & {fmt(prop, 3)} & --- & --- & --- \\\\")

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} Causal mediation analysis following IKY (2010). "
        r"ACME = Average Causal Mediation Effect (indirect path through mediator). "
        r"ADE = Average Direct Effect. Bootstrap 95\% CI based on 1000 replications. "
        r"'---' indicates unavailable.",
        r"\end{tablenotes}",
        r"\end{table}",
    ]

    content = "\n".join(tex)
    content = validate_table(content, "table_8_mediation.tex")
    path = os.path.join(TABLES_DIR, "table_8_mediation.tex")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE A1: Lee (2009) Trimming Bounds (Appendix)
# ═══════════════════════════════════════════════════════════════════════════════
def make_table_a1(results):
    print("Generating Table A1: Lee (2009) trimming bounds...")

    lee_data = results[results["specification"] == "lee_bounds"]
    if len(lee_data) == 0:
        print("  No Lee bounds. Skipping.")
        return

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Lee (2009) Trimming Bounds}",
        r"\label{tab:lee_bounds}",
        r"\begin{tabular}{l ccc}",
        r"\toprule",
        r"Outcome & Point Estimate & Lower Bound & Upper Bound \\",
        r"\midrule",
    ]

    for _, r in lee_data.iterrows():
        tex.append(
            f"  {r.get('outcome', '---')} & {fmt(r['estimate'])} "
            f"& {fmt(r.get('ci_lower', np.nan))} & {fmt(r.get('ci_upper', np.nan))} \\\\"
        )

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} Lee (2009) trimming bounds under worst-case selective "
        r"attrition. Bounds trim the group with higher observation rate to match the "
        r"lower rate. Applicable when outcome missingness exceeds 5\%.",
        r"\end{tablenotes}",
        r"\end{table}",
    ]

    content = "\n".join(tex)
    content = validate_table(content, "table_a1_lee_bounds.tex")
    path = os.path.join(TABLES_DIR, "table_a1_lee_bounds.tex")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE A2: Specification Curve (Appendix)
# ═══════════════════════════════════════════════════════════════════════════════
def make_table_a2(robust):
    print("Generating Table A2: Specification curve...")

    sc_data = robust[robust["test"].str.startswith("spec_curve_")]
    if len(sc_data) == 0:
        print("  No specification curve results. Skipping.")
        return

    tex = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Specification Curve: ITT Estimates Across Models}",
        r"\label{tab:spec_curve}",
        r"\begin{tabular}{l ccccc}",
        r"\toprule",
        r"Specification & Estimate & SE & 95\% CI & $p$-value & N \\",
        r"\midrule",
    ]

    for _, r in sc_data.iterrows():
        spec_name = r.get("test", "---").replace("spec_curve_", "").replace("_", " ").title()
        pval = r.get("pvalue", np.nan)
        stars = fmt_stars(pval)
        n_val = int(r.get("N", 0)) if pd.notna(r.get("N")) else "---"
        tex.append(
            f"  {spec_name} & {fmt(r['estimate'])}{stars} & ({fmt(r['se_robust'])}) "
            f"& [{fmt(r.get('ci_lower', np.nan))}, {fmt(r.get('ci_upper', np.nan))}] "
            f"& {fmt(pval)} & {n_val} \\\\"
        )

    tex += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}",
        r"\small",
        r"\item \textit{Notes:} ITT (reduced form) estimates across combinations of "
        r"control sets and functional forms (LPM, probit AME, logit AME). "
        r"$^{***}$p$<$0.01, $^{**}$p$<$0.05, $^{*}$p$<$0.10.",
        r"\end{tablenotes}",
        r"\end{table}",
    ]

    content = "\n".join(tex)
    content = validate_table(content, "table_a2_spec_curve.tex")
    path = os.path.join(TABLES_DIR, "table_a2_spec_curve.tex")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 3: Compliance Diagram
# ═══════════════════════════════════════════════════════════════════════════════
def make_figure3(results):
    print("Generating Figure 3: Compliance diagram...")

    comp = results[results["specification"] == "compliance_structure"]
    if len(comp) == 0:
        print("  No compliance data. Skipping.")
        return

    r = comp.iloc[0]
    compliance_rate = r.get("estimate", 0)
    always_takers = r.get("ci_lower", 0)
    never_takers = r.get("ci_upper", 0)
    compliers = max(0, compliance_rate)
    defiers = max(0, 1 - always_takers - never_takers - compliers)

    fig, ax = plt.subplots(figsize=(8, 5))

    categories = ["Always-Takers", "Compliers", "Never-Takers", "Defiers"]
    values = [always_takers, compliers, never_takers, defiers]
    colors = ["#ef8a62", "#67a9cf", "#999999", "#b2182b"]

    bars = ax.bar(categories, values, color=colors, edgecolor="black", linewidth=0.5)

    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                f"{val:.3f}", ha="center", fontsize=11, fontweight="bold")

    ax.set_ylabel("Share of Population", fontsize=12)
    ax.set_title("Compliance Structure (Imbens-Rubin Framework)", fontsize=13)
    ax.set_ylim(0, max(values) * 1.2 + 0.05)
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()

    for ext in ["png", "pdf"]:
        path = os.path.join(FIGURES_DIR, f"figure_3_compliance.{ext}")
        plt.savefig(path, dpi=150 if ext == "png" else 300, bbox_inches="tight")
    plt.close("all")
    print(f"  Saved: figure_3_compliance.png/.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 4: Mediation Sensitivity Plot (ACME vs rho)
# ═══════════════════════════════════════════════════════════════════════════════
def make_figure4():
    print("Generating Figure 4: Mediation sensitivity plot...")

    sens_path = os.path.join(DATA_DIR, "mediation_sensitivity.csv")
    if not os.path.exists(sens_path):
        print("  No mediation sensitivity data. Skipping.")
        return

    sens = pd.read_csv(sens_path)
    if len(sens) == 0:
        print("  Empty sensitivity data. Skipping.")
        return

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.plot(sens["rho"], sens["acme_adjusted"], "o-", color="#2166ac",
            linewidth=2, markersize=8, label="ACME(ρ)")
    ax.axhline(y=0, color="black", linestyle="--", linewidth=1, alpha=0.5)
    ax.axvline(x=0, color="gray", linestyle=":", linewidth=0.5)

    # Find rho* (where ACME crosses zero)
    for i in range(1, len(sens)):
        if np.sign(sens.iloc[i - 1]["acme_adjusted"]) != np.sign(sens.iloc[i]["acme_adjusted"]):
            rho_star = sens.iloc[i - 1]["rho"] + \
                (sens.iloc[i]["rho"] - sens.iloc[i - 1]["rho"]) * \
                abs(sens.iloc[i - 1]["acme_adjusted"]) / \
                (abs(sens.iloc[i - 1]["acme_adjusted"]) + abs(sens.iloc[i]["acme_adjusted"]))
            ax.axvline(x=rho_star, color="#b2182b", linestyle="--", linewidth=2,
                       label=f"ρ* = {rho_star:.3f}")
            break

    ax.set_xlabel("ρ (sequential ignorability violation)", fontsize=12)
    ax.set_ylabel("ACME (adjusted)", fontsize=12)
    ax.set_title("Mediation Sensitivity Analysis", fontsize=13)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    for ext in ["png", "pdf"]:
        path = os.path.join(FIGURES_DIR, f"figure_4_mediation_sensitivity.{ext}")
        plt.savefig(path, dpi=150 if ext == "png" else 300, bbox_inches="tight")
    plt.close("all")
    print(f"  Saved: figure_4_mediation_sensitivity.png/.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 5: Specification Curve
# ═══════════════════════════════════════════════════════════════════════════════
def make_figure5():
    print("Generating Figure 5: Specification curve plot...")

    sc_path = os.path.join(DATA_DIR, "specification_curve.csv")
    if not os.path.exists(sc_path):
        print("  No specification curve data. Skipping.")
        return

    sc = pd.read_csv(sc_path)
    if len(sc) == 0:
        print("  Empty specification curve. Skipping.")
        return

    # Sort by estimate
    sc = sc.sort_values("estimate").reset_index(drop=True)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7),
                                     gridspec_kw={"height_ratios": [3, 1]},
                                     sharex=True)

    # Top panel: estimates with CIs
    colors = []
    for _, r in sc.iterrows():
        spec = r.get("spec", "")
        if "probit" in spec:
            colors.append("#ef8a62")
        elif "logit" in spec:
            colors.append("#4daf4a")
        else:
            colors.append("#2166ac")

    x = range(len(sc))
    for i, (_, r) in enumerate(sc.iterrows()):
        ci_lo = r.get("ci_lower", r["estimate"])
        ci_hi = r.get("ci_upper", r["estimate"])
        if np.isnan(ci_lo):
            ci_lo = r["estimate"]
        if np.isnan(ci_hi):
            ci_hi = r["estimate"]
        ax1.errorbar(i, r["estimate"],
                     yerr=[[r["estimate"] - ci_lo], [ci_hi - r["estimate"]]],
                     fmt="o", color=colors[i], capsize=3, markersize=6)

    ax1.axhline(y=0, color="black", linestyle="--", linewidth=1, alpha=0.5)
    ax1.set_ylabel("Estimate", fontsize=11)
    ax1.set_title("Specification Curve: ITT Estimates", fontsize=13)
    ax1.grid(True, alpha=0.3, axis="y")

    # Legend for colors
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#2166ac", label="LPM"),
        Patch(facecolor="#ef8a62", label="Probit"),
        Patch(facecolor="#4daf4a", label="Logit"),
    ]
    ax1.legend(handles=legend_elements, fontsize=9, loc="best")

    # Bottom panel: indicator matrix
    spec_names = sc["spec"].tolist()
    control_types = ["no_controls", "basic_controls", "full_controls"]

    indicator_matrix = np.zeros((len(control_types), len(spec_names)))
    for j, spec in enumerate(spec_names):
        for i, ct in enumerate(control_types):
            if ct in spec:
                indicator_matrix[i, j] = 1

    ax2.imshow(indicator_matrix, cmap="Blues", aspect="auto", interpolation="nearest")
    ax2.set_yticks(range(len(control_types)))
    ax2.set_yticklabels(["No controls", "Basic", "Full"], fontsize=9)
    ax2.set_xlabel("Specification (sorted by estimate)", fontsize=11)
    ax2.set_xticks([])

    plt.tight_layout()

    for ext in ["png", "pdf"]:
        path = os.path.join(FIGURES_DIR, f"figure_5_spec_curve.{ext}")
        plt.savefig(path, dpi=150 if ext == "png" else 300, bbox_inches="tight")
    plt.close("all")
    print(f"  Saved: figure_5_spec_curve.png/.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 6: CONSORT-style Sample Flow
# ═══════════════════════════════════════════════════════════════════════════════
def make_figure6(df, results):
    print("Generating Figure 6: CONSORT-style sample flow...")

    # Extract N at different stages from results
    n_total = len(df)
    n_instrument = df[INSTRUMENT_VARS[0]].notna().sum() if INSTRUMENT_VARS[0] in df.columns else n_total
    n_endogenous = df[ENDOGENOUS_VAR].notna().sum() if ENDOGENOUS_VAR in df.columns else n_total
    n_outcome = df[PRIMARY_OUTCOME].notna().sum() if PRIMARY_OUTCOME in df.columns else n_total

    # Final analysis sample
    analysis_cols = [PRIMARY_OUTCOME, ENDOGENOUS_VAR] + INSTRUMENT_VARS
    analysis_cols = [c for c in analysis_cols if c in df.columns]
    n_analysis = df[analysis_cols].dropna().shape[0]

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

    # Boxes
    boxes = [
        (5, 9, f"Total observations\nN = {n_total:,}"),
        (5, 7, f"Non-missing instrument\nN = {n_instrument:,}"),
        (5, 5, f"Non-missing endogenous\nN = {n_endogenous:,}"),
        (5, 3, f"Non-missing outcome\nN = {n_outcome:,}"),
        (5, 1, f"Final analysis sample\nN = {n_analysis:,}"),
    ]

    for x, y, text in boxes:
        ax.add_patch(plt.Rectangle((x - 2, y - 0.6), 4, 1.2,
                                    fill=True, facecolor="#e6f0ff",
                                    edgecolor="#2166ac", linewidth=1.5))
        ax.text(x, y, text, ha="center", va="center", fontsize=10, fontweight="bold")

    # Arrows and dropout labels
    dropouts = [
        (8, 8, f"Dropped: {n_total - n_instrument:,}"),
        (8, 6, f"Dropped: {n_instrument - n_endogenous:,}"),
        (8, 4, f"Dropped: {n_endogenous - n_outcome:,}"),
        (8, 2, f"Dropped: {n_outcome - n_analysis:,}"),
    ]

    for i in range(len(boxes) - 1):
        ax.annotate("", xy=(5, boxes[i + 1][1] + 0.6), xytext=(5, boxes[i][1] - 0.6),
                     arrowprops=dict(arrowstyle="->", color="#333333", lw=1.5))

    for x, y, text in dropouts:
        ax.text(x, y, text, ha="center", va="center", fontsize=9,
                color="#b2182b", style="italic")

    ax.set_title("Sample Flow Diagram", fontsize=14, fontweight="bold", pad=20)
    plt.tight_layout()

    for ext in ["png", "pdf"]:
        path = os.path.join(FIGURES_DIR, f"figure_6_sample_flow.{ext}")
        plt.savefig(path, dpi=150 if ext == "png" else 300, bbox_inches="tight")
    plt.close("all")
    print(f"  Saved: figure_6_sample_flow.png/.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("03_output.py — IV/2SLS Tables and Figures (Expanded)")
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
    # ── Core tables (always generated) ────────────────────────────────────
    make_table1(df)                          # Summary statistics
    make_table2(main_results)                # First stage
    make_table3(main_results)                # Main results (OLS vs 2SLS vs RF)
    if robust is not None:
        make_table4(robust)                  # Robustness checks
    make_table5(main_results)                # Covariate balance
    make_table6(main_results)                # ITT multiple specifications
    make_table7(main_results)                # Heterogeneity
    if robust is not None:
        make_table8(robust)                  # Mediation decomposition
    make_table_a1(main_results)              # Lee bounds (appendix)
    if robust is not None:
        make_table_a2(robust)                # Specification curve (appendix)

    print()
    # ── Core figures ──────────────────────────────────────────────────────
    make_figure1(df)                         # First stage scatter
    make_figure2(main_results)               # OLS vs 2SLS comparison
    make_figure3(main_results)               # Compliance diagram
    make_figure4()                           # Mediation sensitivity
    make_figure5()                           # Specification curve
    make_figure6(df, main_results)           # CONSORT sample flow

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
