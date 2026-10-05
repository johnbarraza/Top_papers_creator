"""
03_output.py -- publication tables, figures and the results handoff.

Tables  (paper/tables): tab_calibration.tex, tab_moments.tex,
                        tab_equilibrium_tests.tex, tab_experiment.tex
Figures (paper/figures): fig_wealth_distribution, fig_policy_functions,
                        fig_irf_output + fig_irf_decomposition (monetary
                        shock) or fig_counterfactuals (comparative statics)
Handoff: data/clean/main_results.csv and paper/tables/results_summary.md
"""

# ════════════════════════════════════════════════════════════════════════════
# PROJECT-SPECIFIC VARIABLES (Claude fills these)
# ════════════════════════════════════════════════════════════════════════════

# Human-readable labels for moments in tables: {"mpc": "Average quarterly MPC"}
MOMENT_LABELS = {{MOMENT_LABELS}}

# ════════════════════════════════════════════════════════════════════════════
# FIXED CODE (does not change between projects)
# ════════════════════════════════════════════════════════════════════════════

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "data" / "model"
TAB = ROOT / "paper" / "tables"
FIG = ROOT / "paper" / "figures"
CLEAN = ROOT / "data" / "clean"
for d in (TAB, FIG, CLEAN):
    d.mkdir(parents=True, exist_ok=True)

DEFAULT_LABELS = {
    "r": "Real interest rate", "rho": "Discount rate",
    "wealth_to_income": "Wealth / income", "frac_constrained": "Share at borrowing limit",
    "frac_negative_wealth": "Share with negative wealth", "gini_wealth": "Wealth Gini",
    "top10_wealth_share": "Top 10\\% wealth share", "bottom50_wealth_share": "Bottom 50\\% wealth share",
    "mpc": "Average MPC (one quarter)", "consumption": "Aggregate consumption", "output": "Output",
}
LABELS = {**DEFAULT_LABELS, **(MOMENT_LABELS or {})}


def esc(s):
    return str(s).replace("&", "\\&").replace("%", "\\%").replace("_", "\\_").replace("#", "\\#")


def fmt(x, nd=3):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "---"
    if isinstance(x, (int, float)):
        return f"{x:.{nd}e}" if (x != 0 and abs(x) < 10 ** (-nd)) else f"{x:.{nd}f}"
    return esc(x)


def table(path, caption, label, cols, rows, note):
    body = "\n".join(" & ".join(r) + " \\\\" for r in rows)
    tex = (f"\\begin{{table}}[htbp]\n\\centering\n\\caption{{{caption}}}\n\\label{{{label}}}\n"
           f"\\begin{{tabular}}{{{'l' + 'c' * (len(cols) - 1)}}}\n\\toprule\n"
           f"{' & '.join(cols)} \\\\\n\\midrule\n{body}\n\\bottomrule\n\\end{{tabular}}\n"
           f"\\par\\vspace{{2pt}}\\begin{{minipage}}{{0.92\\linewidth}}\\footnotesize "
           f"\\textit{{Notes:}} {note}\\end{{minipage}}\n\\end{{table}}\n")
    assert "nan" not in body.lower(), f"NaN in {path.name}"
    path.write_text(tex, encoding="utf-8")
    print(f"[saved] {path}")


def savefig(fig, name):
    for ext in ("pdf", "png"):
        fig.savefig(FIG / f"{name}.{ext}", dpi=200, bbox_inches="tight")
    plt.close("all")
    print(f"[saved] {FIG / name}.pdf/.png")


def read_csv(path):
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    head = lines[0].split(",")
    data = np.array([[float(v) for v in ln.split(",")] for ln in lines[1:]])
    return {h: data[:, k] for k, h in enumerate(head)}


def main():
    spec = json.loads((MODEL_DIR / "calibration_final.json").read_text(encoding="utf-8"))
    ss = json.loads((MODEL_DIR / "steady_state.json").read_text(encoding="utf-8"))
    tests = json.loads((MODEL_DIR / "equilibrium_tests.json").read_text(encoding="utf-8"))
    exp = json.loads((MODEL_DIR / "experiment_summary.json").read_text(encoding="utf-8"))
    mom = ss["moments"]
    unit = spec["time_unit"]

    # ── Table 1: calibration ────────────────────────────────────────────
    rows = []
    for k, v in ss["params"].items():
        if k in ("n_a", "grid_curvature", "bracket", "calibrate", "a_max", "Lambda", "z"):
            continue
        src = spec["param_sources"].get(k, {})
        rows.append([esc(k), fmt(v) if isinstance(v, (int, float)) else esc(v),
                     esc(src.get("description", "")), esc(src.get("how", "")),
                     esc(src.get("source", ""))])
    rows.append([esc(ss["unknown"]), fmt(ss["unknown_value"], 4),
                 "Clears the asset market", "equilibrium", "Model"])
    table(TAB / "tab_calibration.tex", "Calibration", "tab:calibration",
          ["Parameter", "Value", "Description", "Method", "Source"], rows,
          f"Rates are per {unit}. ``Internal'' parameters are chosen to match the targeted "
          f"moments in Table~\\ref{{tab:moments}}; ``equilibrium'' is the price that clears the "
          f"asset market.")

    # ── Table 2: targeted and untargeted moments ───────────────────────
    rows = []
    for name, t in spec["calibration_targets"].items():
        rows.append([esc(LABELS.get(t["moment"], name)), fmt(t["data"]),
                     fmt(mom.get(t["moment"])), "Targeted", esc(t.get("source", ""))])
    for name, t in (spec.get("untargeted_moments") or {}).items():
        rows.append([esc(LABELS.get(t["moment"], name)), fmt(t.get("data")),
                     fmt(mom.get(t["moment"])), "Untargeted", esc(t.get("source", ""))])
    if not rows:
        rows = [[esc(LABELS.get(k, k)), "---", fmt(v), "Model only", ""] for k, v in mom.items()]
    table(TAB / "tab_moments.tex", "Model fit: targeted and untargeted moments",
          "tab:moments", ["Moment", "Data", "Model", "Type", "Source"], rows,
          "Model moments are computed from the stationary distribution. MPCs are out of a "
          "windfall of 1\\% of output over one quarter (Feynman--Kac, Achdou et al. 2022).")

    # ── Table 3: equilibrium & numerical tests (appendix) ──────────────
    rows = [[esc(t["id"]), t["level"], "Pass" if t["passed"] else "\\textbf{Fail}",
             fmt(t["value"]), fmt(t["tol"])] for t in tests["tests"]]
    s = tests.get("summary", {})
    table(TAB / "tab_equilibrium_tests.tex", "Equilibrium and numerical accuracy tests",
          "tab:eqtests", ["Test", "Level", "Result", "Value", "Tolerance"], rows,
          f"HARD tests must pass for the equilibrium to exist numerically "
          f"({s.get('hard_passed', '?')}/{s.get('hard_total', '?')} passed); SOFT tests are "
          f"accuracy diagnostics ({s.get('soft_passed', '?')}/{s.get('soft_total', '?')} passed). "
          "Walras' law is verified on the market the solver does not impose.")

    # ── Figures: steady state ───────────────────────────────────────────
    pol = read_csv(MODEL_DIR / "steady_state_policies.csv")
    J = len(ss["income_states"])
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    for j in range(J):
        ax[0].plot(pol["a"], pol[f"c_z{j}"], label=f"z = {ss['income_states'][j]:.2f}")
        ax[1].plot(pol["a"], pol[f"s_z{j}"], label=f"z = {ss['income_states'][j]:.2f}")
    ax[0].set(xlabel="Wealth a", ylabel="Consumption c(a, z)", title="Consumption")
    ax[1].axhline(0, color="k", lw=0.6)
    ax[1].set(xlabel="Wealth a", ylabel="Savings s(a, z)", title="Savings")
    ax[0].legend(frameon=False)
    savefig(fig, "fig_policy_functions")

    fig, ax = plt.subplots(figsize=(6, 3.8))
    mass = sum(pol[f"mass_z{j}"] for j in range(J))
    ax.bar(pol["a"][1:], mass[1:], width=np.diff(pol["a"]), color="C0", alpha=0.7,
           label="Mass per grid cell")
    ax.axvline(pol["a"][0], color="C3", lw=1.5,
               label=f"Mass at borrowing limit: {mass[0]:.3f}")
    ax.set(xlabel="Wealth a", ylabel="Mass", title="Stationary wealth distribution")
    ax.legend(frameon=False)
    savefig(fig, "fig_wealth_distribution")

    # ── Experiment ─────────────────────────────────────────────────────
    results = [("unknown_" + ss["unknown"], ss["unknown_value"])]
    results += [(f"moment_{k}", v) for k, v in mom.items()]
    if exp["experiment"] == "monetary_shock":
        irf = read_csv(MODEL_DIR / "irfs.csv")
        fig, ax = plt.subplots(figsize=(6.5, 3.8))
        ax.plot(irf["t"], 100 * irf["Y_hank"], label="HANK", lw=2)
        ax.plot(irf["t"], 100 * irf["Y_tank"], "--", label="TANK")
        ax.plot(irf["t"], 100 * irf["Y_rank"], ":", label="RANK")
        ax.axhline(0, color="k", lw=0.6)
        ax.set(xlabel=f"Time ({unit}s)", ylabel="Output, % deviation",
               title="Output response to a monetary tightening")
        ax.legend(frameon=False)
        savefig(fig, "fig_irf_output")

        fig, ax = plt.subplots(figsize=(6.5, 3.8))
        ax.plot(irf["t"], 100 * irf["C_hank"], label="Total", lw=2)
        ax.plot(irf["t"], 100 * irf["C_direct"], "--", label="Direct (interest rate)")
        ax.plot(irf["t"], 100 * (irf["C_hank"] - irf["C_direct"]), ":",
                label="Indirect (income and taxes)")
        ax.axhline(0, color="k", lw=0.6)
        ax.set(xlabel=f"Time ({unit}s)", ylabel="Consumption, % deviation",
               title="Decomposition (Kaplan, Moll and Violante 2018)")
        ax.legend(frameon=False)
        savefig(fig, "fig_irf_decomposition")
        rows = [["Impact output response, HANK", fmt(100 * exp["impact_output_hank"])],
                ["Impact output response, TANK", fmt(100 * exp["impact_output_tank"])],
                ["Impact output response, RANK", fmt(100 * exp["impact_output_rank"])],
                ["HANK / RANK impact ratio", fmt(exp["hank_to_rank_impact_ratio"])],
                ["Direct-effect share on impact", fmt(exp["direct_effect_share_impact"])],
                ["Cumulative output loss, HANK", fmt(100 * exp["cumulative_output_hank"])],
                ["Cumulative output loss, RANK", fmt(100 * exp["cumulative_output_rank"])],
                ["TANK hand-to-mouth share", fmt(exp["tank_lambda"])]]
        note = (f"Shock: real rate +{100 * exp['shock_size']:.2f} pp, decaying at rate "
                f"{exp['persistence']} per {unit}. Output in \\% of steady state; cumulative "
                f"responses integrate over the horizon. Equilibrium solved in sequence space "
                f"(Newton, {exp['newton_iterations']} iterations, max goods residual "
                f"{exp['max_goods_residual']:.1e}, max asset residual "
                f"{exp['max_asset_residual']:.1e}).")
    else:
        cf = read_csv(MODEL_DIR / "counterfactuals.csv")
        p = exp["param"]
        fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
        ax[0].plot(cf[p], cf["r"], marker="o")
        ax[0].set(xlabel=esc(exp["label"]), ylabel="r", title="Equilibrium interest rate")
        ax[1].plot(cf[p], cf["wealth_to_income"], marker="o")
        ax[1].set(xlabel=esc(exp["label"]), ylabel="Wealth / income", title="Wealth")
        savefig(fig, "fig_counterfactuals")
        rows = [[fmt(cf[p][k]), fmt(cf["r"][k], 4), fmt(cf["wealth_to_income"][k]),
                 fmt(cf["frac_constrained"][k]), fmt(cf["mpc"][k])] for k in range(len(cf[p]))]
        table(TAB / "tab_experiment.tex", f"Counterfactual steady states: {esc(exp['label'])}",
              "tab:experiment", [esc(exp["label"]), "r", "Wealth/income", "Constrained", "MPC"],
              rows, "Each row is a separate stationary equilibrium; market clearing and "
              "Walras' law are verified for each (Table~\\ref{tab:eqtests}).")
        rows = None
    if rows:
        table(TAB / "tab_experiment.tex", "Monetary policy transmission", "tab:experiment",
              ["Statistic", "Value"], rows, note)
    results += [(f"experiment_{k}", v) for k, v in exp.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)]

    lines = ["statistic,value"] + [f"{k},{v:.10g}" for k, v in results
                                   if isinstance(v, (int, float)) and math.isfinite(v)]
    (CLEAN / "main_results.csv").write_text("\n".join(lines), encoding="utf-8")

    s = tests["summary"]
    md = [f"# Results summary -- {spec['paper_title']}", "",
          f"Model class: **{spec['model_class']}**; time unit: {unit}.",
          f"Equilibrium tests: HARD {s['hard_passed']}/{s['hard_total']}, "
          f"SOFT {s['soft_passed']}/{s['soft_total']} (Table tab:eqtests).", "",
          "## Steady state", f"- {ss['unknown']} = {ss['unknown_value']:.6f}"]
    md += [f"- {LABELS.get(k, k)}: {v:.4f}" for k, v in mom.items()
           if isinstance(v, float) and math.isfinite(v)]
    md += ["", "## Experiment"] + [f"- {k}: {v}" for k, v in exp.items()]
    failed_soft = [t["id"] for t in tests["tests"] if t["level"] == "SOFT" and not t["passed"]]
    if failed_soft:
        md += ["", "## SOFT tests that failed (discuss in the paper)"] + [f"- {f}" for f in failed_soft]
    (TAB / "results_summary.md").write_text("\n".join(md), encoding="utf-8")
    print(f"[saved] {CLEAN / 'main_results.csv'}, {TAB / 'results_summary.md'}")


if __name__ == "__main__":
    main()
