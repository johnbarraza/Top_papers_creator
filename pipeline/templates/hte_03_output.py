"""03_output.py - HTE/DML LaTeX tables and figures template.

Tables:
  Table 1 — Replication: OLS ATE vs original paper
  Table 2 — DML ATE (main + robustness)
  Table 3 — CATE by subgroup (HTE_VARS)
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
HTE_VARS         = {{HTE_VARS}}
BASE_PAPER_TITLE = "{{BASE_PAPER_TITLE}}"
PRIMARY_OUTCOME  = "{{PRIMARY_OUTCOME}}"
OUTCOME_LABEL    = "{{OUTCOME_LABEL}}"   # display label, e.g., "Log earnings"
TREATMENT_LABEL  = "{{TREATMENT_LABEL}}" # display label, e.g., "Cash transfer (=1)"
ORIGINAL_ATE     = {{ORIGINAL_ATE}}
ORIGINAL_ATE_SE  = {{ORIGINAL_ATE_SE}}
JOURNAL_FORMAT   = "{{JOURNAL_FORMAT}}"  # "aer", "restat", "generic"

# ═══════════════════════════════════════════════════════════════════════════════
# FIXED CODE
# ═══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_CLEAN  = os.path.join(SCRIPT_DIR, "..", "..", "data", "clean")
RESULTS_DIR = os.path.join(SCRIPT_DIR, "..", "..", "results")
TABLES_DIR  = os.path.join(SCRIPT_DIR, "..", "..", "tables")
FIGURES_DIR = os.path.join(SCRIPT_DIR, "..", "..", "figures")
for d in [RESULTS_DIR, TABLES_DIR, FIGURES_DIR]:
    os.makedirs(d, exist_ok=True)

print("=" * 70)
print("03_output.py — HTE/DML Tables and Figures")
print(f"Paper: {BASE_PAPER_TITLE[:70]}")
print("=" * 70)

# ── Load results ──────────────────────────────────────────────────────────────
main_results_path = os.path.join(DATA_CLEAN, "main_results.csv")
robust_path       = os.path.join(RESULTS_DIR, "robustness_results.csv")
cate_path         = os.path.join(DATA_CLEAN, "cate_predictions.csv")
summary_path      = os.path.join(RESULTS_DIR, "main_summary.json")

if not os.path.exists(main_results_path):
    print("ERROR: main_results.csv not found. Run 01_main.py first.")
    sys.exit(1)

results_df = pd.read_csv(main_results_path)
robust_df  = pd.read_csv(robust_path) if os.path.exists(robust_path) else pd.DataFrame()
cate_df    = pd.read_csv(cate_path)   if os.path.exists(cate_path)   else pd.DataFrame()

main_summary = {}
if os.path.exists(summary_path):
    with open(summary_path) as f:
        main_summary = json.load(f)

print(f"Loaded {len(results_df)} main results, {len(robust_df)} robustness checks")

# ── Helper ────────────────────────────────────────────────────────────────────

def fmt_est(est, se, stars=True):
    """Format estimate with standard errors and significance stars."""
    if pd.isna(est) or pd.isna(se):
        return "---", "---"
    t = abs(est) / (se + 1e-12)
    star = ""
    if stars:
        if t > 3.291:
            star = "***"
        elif t > 2.576:
            star = "**"
        elif t > 1.960:
            star = "*"
    est_str = f"{est:.4f}{star}"
    se_str  = f"({se:.4f})"
    return est_str, se_str


def latex_table(rows, caption, label, note=""):
    """Build a basic LaTeX table."""
    n_cols = max(len(r) for r in rows) if rows else 2
    col_spec = "l" + "c" * (n_cols - 1)
    lines = [
        "\\begin{table}[htbp]",
        "  \\centering",
        f"  \\caption{{{caption}}}",
        f"  \\label{{tab:{label}}}",
        f"  \\begin{{tabular}}{{{col_spec}}}",
        "  \\hline\\hline",
    ]
    for i, row in enumerate(rows):
        cells = " & ".join(str(c) for c in row) + " \\\\"
        lines.append(f"  {cells}")
        if i == 0:
            lines.append("  \\hline")
    lines += [
        "  \\hline",
        "  \\end{tabular}",
    ]
    if note:
        lines.append(f"  \\begin{{minipage}}{{\\linewidth}}")
        lines.append(f"  \\footnotesize \\textit{{Notes:}} {note}")
        lines.append(f"  \\end{{minipage}}")
    lines.append("\\end{table}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 1 — Replication: OLS vs original paper
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- Table 1: Replication ---")

ols_row = results_df[results_df["estimator"].str.contains("OLS", na=False)]
ols_ate = float(ols_row["estimate"].iloc[0]) if len(ols_row) > 0 else None
ols_se  = float(ols_row["se"].iloc[0])       if len(ols_row) > 0 else None
ols_n   = int(ols_row["N"].iloc[0])          if len(ols_row) > 0 else None

orig_est_str, orig_se_str = fmt_est(ORIGINAL_ATE, ORIGINAL_ATE_SE) if ORIGINAL_ATE else ("---", "---")
repl_est_str, repl_se_str = fmt_est(ols_ate, ols_se)

if ols_ate is not None and ORIGINAL_ATE is not None:
    pct_diff = abs(ols_ate - ORIGINAL_ATE) / (abs(ORIGINAL_ATE) + 1e-10)
    print(f"  Original: {ORIGINAL_ATE}  Replicated: {ols_ate:.4f}  Δ%: {100*pct_diff:.1f}%")

t1_rows = [
    ["", "Original paper", "This replication"],
    [TREATMENT_LABEL, orig_est_str, repl_est_str],
    ["",              orig_se_str,  repl_se_str],
    ["N", str(main_summary.get("n_obs", "---")), str(ols_n or "---")],
]
t1_note = (
    f"Dependent variable: {OUTCOME_LABEL}. "
    f"Original paper: \\citealt{{{BASE_PAPER_TITLE[:30].replace(' ', '_')}}}. "
    f"Replication uses OLS with HC3 standard errors. "
    f"*** p<0.01, ** p<0.05, * p<0.10."
)
t1_tex = latex_table(t1_rows, "Replication of Baseline ATE", "replication", note=t1_note)

t1_path = os.path.join(TABLES_DIR, "table_replication.tex")
with open(t1_path, "w", encoding="utf-8") as f:
    f.write(t1_tex)
print(f"  Saved: {t1_path}")

# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 2 — DML ATE (main + robustness)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- Table 2: DML ATE ---")

dml_rows_main = results_df[~results_df["estimator"].str.contains("OLS|CATE", na=False)]
dml_rows_rob  = robust_df[robust_df["check"].str.startswith("DML", na=False)] if len(robust_df) > 0 else pd.DataFrame()

t2_rows = [["Specification", "Estimate", "SE", "95\\% CI", "N"]]

for _, row in dml_rows_main.iterrows():
    est, se_ = fmt_est(row["estimate"], row["se"])
    ci = f"[{row['ci_lower']:.4f}, {row['ci_upper']:.4f}]" if "ci_lower" in row else "---"
    t2_rows.append([row["estimator"], est, se_[1:-1], ci, f"{int(row['N']):,}"])

for _, row in dml_rows_rob.iterrows():
    est, se_ = fmt_est(row["estimate"], row["se"])
    t2_rows.append([row["check"], est, se_[1:-1], "---", f"{int(row['N']):,}"])

t2_note = (
    f"All specifications use {main_summary.get('n_folds', 5)}-fold cross-fitting. "
    f"GBM = Gradient Boosting Machines. Standard errors from influence-function formula. "
    f"*** p<0.01, ** p<0.05, * p<0.10."
)
t2_tex = latex_table(t2_rows, f"DML Average Treatment Effect: {OUTCOME_LABEL}", "dml_ate", note=t2_note)

t2_path = os.path.join(TABLES_DIR, "table_dml_ate.tex")
with open(t2_path, "w", encoding="utf-8") as f:
    f.write(t2_tex)
print(f"  Saved: {t2_path}")

# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 3 — CATE by subgroup
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- Table 3: CATE by subgroup ---")

if len(cate_df) > 0 and "cate" in cate_df.columns and HTE_VARS:
    t3_rows = [["Subgroup", "Mean CATE", "SD", "N", "vs. ATE"]]
    overall_ate = main_summary.get("dml_ate")

    for var in HTE_VARS:
        if var not in cate_df.columns:
            continue
        n_vals = cate_df[var].nunique()
        if n_vals <= 6:
            for val in sorted(cate_df[var].dropna().unique()):
                mask = cate_df[var] == val
                sub_cate = cate_df.loc[mask, "cate"]
                mean_c = sub_cate.mean()
                sd_c   = sub_cate.std()
                n_c    = len(sub_cate)
                delta  = (mean_c - overall_ate) if overall_ate else np.nan
                t3_rows.append([
                    f"{var}={val}",
                    f"{mean_c:.4f}",
                    f"{sd_c:.4f}",
                    f"{n_c:,}",
                    f"{delta:+.4f}" if not pd.isna(delta) else "---",
                ])
        else:
            # Quartiles for continuous HTE_VAR
            q_labels = ["Q1 (low)", "Q2", "Q3", "Q4 (high)"]
            try:
                cate_df[f"_{var}_q"] = pd.qcut(cate_df[var], 4, labels=False)
                for q in range(4):
                    mask = cate_df[f"_{var}_q"] == q
                    sub_cate = cate_df.loc[mask, "cate"]
                    mean_c = sub_cate.mean()
                    sd_c   = sub_cate.std()
                    n_c    = len(sub_cate)
                    delta  = (mean_c - overall_ate) if overall_ate else np.nan
                    t3_rows.append([
                        f"{var} {q_labels[q]}",
                        f"{mean_c:.4f}",
                        f"{sd_c:.4f}",
                        f"{n_c:,}",
                        f"{delta:+.4f}" if not pd.isna(delta) else "---",
                    ])
            except Exception:
                pass

    t3_note = (
        f"CATE estimates from Causal Forest / pseudo-outcome random forest. "
        f"'vs. ATE' shows deviation of subgroup mean CATE from overall DML ATE "
        f"({overall_ate:.4f} if available). "
        f"Positive values indicate above-average treatment effects for the subgroup."
    )
    t3_tex = latex_table(t3_rows, f"Heterogeneous Treatment Effects: {OUTCOME_LABEL}", "hte_subgroups", note=t3_note)
    t3_path = os.path.join(TABLES_DIR, "table_hte_subgroups.tex")
    with open(t3_path, "w", encoding="utf-8") as f:
        f.write(t3_tex)
    print(f"  Saved: {t3_path}")
else:
    print("  [skip] No CATE predictions or no HTE_VARS — skipping Table 3.")

# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 1 — CATE distribution
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- Figure 1: CATE distribution ---")

if len(cate_df) > 0 and "cate" in cate_df.columns:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(cate_df["cate"], bins=50, edgecolor="white", color="#2E86AB", alpha=0.85)
        if overall_ate := main_summary.get("dml_ate"):
            ax.axvline(overall_ate, color="#E84855", linewidth=2, label=f"DML ATE = {overall_ate:.3f}")
        if ORIGINAL_ATE is not None:
            ax.axvline(ORIGINAL_ATE, color="#3BB273", linewidth=2, linestyle="--",
                       label=f"Original ATE = {ORIGINAL_ATE:.3f}")
        ax.set_xlabel(f"CATE — {OUTCOME_LABEL}", fontsize=11)
        ax.set_ylabel("Count", fontsize=11)
        ax.set_title(f"Distribution of Individual Treatment Effects\n{BASE_PAPER_TITLE[:60]}", fontsize=10)
        ax.legend(fontsize=9)
        plt.tight_layout()
        fig_path = os.path.join(FIGURES_DIR, "fig_cate_distribution.pdf")
        plt.savefig(fig_path)
        plt.close()
        print(f"  Saved: {fig_path}")
    except Exception as e:
        print(f"  [warn] Figure failed: {e}")

# ── Results summary markdown ──────────────────────────────────────────────────
summary_md_path = os.path.join(RESULTS_DIR, "results_summary.md")
with open(summary_md_path, "a", encoding="utf-8") as f:
    f.write(f"\n## Output Tables\n\n")
    f.write(f"- Table 1 (Replication): `tables/table_replication.tex`\n")
    f.write(f"- Table 2 (DML ATE):     `tables/table_dml_ate.tex`\n")
    f.write(f"- Table 3 (HTE subgroups): `tables/table_hte_subgroups.tex`\n")
    f.write(f"- Figure 1 (CATE dist):  `figures/fig_cate_distribution.pdf`\n")

print(f"\nAppended to: {summary_md_path}")

print("\n" + "=" * 70)
print("03_output.py complete.")
print("=" * 70)
