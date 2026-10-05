"""
02_dynamics.py -- main experiment: transition dynamics or comparative statics.

monetary_shock (hank): MIT shock to the real rate, equilibrium output path in
sequence space, HANK vs TANK vs RANK, Kaplan-Moll-Violante decomposition.
comparative_statics (any class): steady states across parameter values, each
one re-tested for market clearing and Walras' law.
"""

# ════════════════════════════════════════════════════════════════════════════
# PROJECT-SPECIFIC VARIABLES (Claude fills these)
# ════════════════════════════════════════════════════════════════════════════

# Share of hand-to-mouth for the TANK benchmark (None = HANK mass at a_min)
TANK_LAMBDA = {{TANK_LAMBDA}}

# ════════════════════════════════════════════════════════════════════════════
# FIXED CODE (does not change between projects)
# ════════════════════════════════════════════════════════════════════════════

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "data" / "model"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import equilibrium_checks as ec  # noqa: E402
import ha_core as hc  # noqa: E402


def monetary_shock(spec, ss, report):
    exp = spec["experiment"]
    dt = float(exp.get("dt", 0.25))
    N = int(round(float(exp.get("horizon", 30)) / dt))
    r_path, t = hc.monetary_shock_path(ss, float(exp["size"]), float(exp["persistence"]), N, dt)
    tr = hc.solve_transition_hank(ss, r_path, dt)
    report.add(hc.transition_checks(ss, tr), "dynamics")
    bm = hc.rank_tank_irfs(ss, r_path, dt, lam=TANK_LAMBDA)

    # Nesting test: TANK with lambda = 0 must equal RANK exactly
    bm0 = hc.rank_tank_irfs(ss, r_path, dt, lam=0.0)
    report.add(ec.against_analytic("tank_lambda0_equals_rank", bm0["tank"], bm0["rank"],
                                   tol=1e-12), "dynamics")

    header = "t,r,Y_hank,C_hank,C_direct,T,A_hh,Y_tank,Y_rank"
    rows = [header]
    for k in range(N):
        rows.append(",".join(f"{v:.10g}" for v in (
            t[k], r_path[k], tr["Y"][k] - ss["Y"], tr["C"][k] - ss["C"],
            tr["C_direct"][k] - ss["C"], tr["T"][k] - ss["T"], tr["A_end"][k] - ss["B"],
            bm["tank"][k], bm["rank"][k])))
    (MODEL_DIR / "irfs.csv").write_text("\n".join(rows), encoding="utf-8")

    dY0 = tr["Y"][0] - ss["Y"]
    dC0 = tr["C"][0] - ss["C"]
    summary = {
        "experiment": "monetary_shock",
        "shock_size": float(exp["size"]),
        "persistence": float(exp["persistence"]),
        "impact_output_hank": float(dY0),
        "impact_output_rank": float(bm["rank"][0]),
        "impact_output_tank": float(bm["tank"][0]),
        "tank_lambda": bm["lambda"],
        "hank_to_rank_impact_ratio": float(dY0 / bm["rank"][0]) if bm["rank"][0] else None,
        "direct_effect_share_impact": float((tr["C_direct"][0] - ss["C"]) / dC0) if dC0 else None,
        "cumulative_output_hank": float(np.sum(tr["Y"] - ss["Y"]) * dt),
        "cumulative_output_rank": float(np.sum(bm["rank"]) * dt),
        "newton_iterations": tr["iterations"],
        "max_goods_residual": tr["residual"],
        "max_asset_residual": float(np.max(np.abs(tr["A_end"] - ss["B"]))),
    }
    np.save(MODEL_DIR / "jacobian_C_Y.npy", tr["Jac"])
    return summary


def comparative_statics(spec, params, model, report):
    exp = spec["experiment"]
    name = exp["param"]
    horizon = 0.25 if spec["time_unit"] == "year" else 1.0
    rows, keys = [], None
    for v in exp["values"]:
        p = dict(params, **{name: v})
        ss_v = hc.steady_state(model, p)
        scale = max(abs(ss_v.get("Y", 1.0)), 1e-12)
        report.add([
            dict(ec.market_clearing("assets", ss_v["A_hh"], ss_v["asset_demand"], scale=scale),
                 id=f"market_clearing:assets@{name}={v}"),
            dict(ec.walras_law("goods", ss_v["goods_residual"], scale=scale),
                 id=f"walras_law:goods@{name}={v}"),
            dict(ec.density_valid(ss_v["m"]), id=f"density_valid@{name}={v}"),
        ], "dynamics")
        mom = hc.moments(ss_v, mpc_horizon=horizon)
        keys = keys or list(mom)
        rows.append([v] + [mom[k] for k in keys])
    lines = [",".join([name] + keys)] + [",".join(f"{x:.10g}" for x in r) for r in rows]
    (MODEL_DIR / "counterfactuals.csv").write_text("\n".join(lines), encoding="utf-8")
    first, last = dict(zip(keys, rows[0][1:])), dict(zip(keys, rows[-1][1:]))
    return {"experiment": "comparative_statics", "param": name,
            "label": exp.get("label", name), "values": list(exp["values"]),
            "r_first": first["r"], "r_last": last["r"],
            "wealth_to_income_first": first["wealth_to_income"],
            "wealth_to_income_last": last["wealth_to_income"]}


def main():
    spec = json.loads((MODEL_DIR / "calibration_final.json").read_text(encoding="utf-8"))
    saved = json.loads((MODEL_DIR / "steady_state.json").read_text(encoding="utf-8"))
    model, params = spec["model_class"], spec["params"]
    report = ec.TestReport(MODEL_DIR / "equilibrium_tests.json", model)
    report.reset_stage("dynamics")

    ss = hc.steady_state(model, params)
    report.add(ec.accounting_identity("steady_state_reproducible", ss["x"],
                                      saved["unknown_value"], tol=1e-8), "dynamics")

    exp_type = spec["experiment"]["type"]
    if exp_type == "monetary_shock":
        if model != "hank":
            raise SystemExit("monetary_shock requires MODEL_CLASS = 'hank' in the template "
                             "solver; write custom dynamics for other classes.")
        summary = monetary_shock(spec, ss, report)
    elif exp_type == "comparative_statics":
        summary = comparative_statics(spec, params, model, report)
    else:
        raise SystemExit(f"Unknown experiment type '{exp_type}'")

    (MODEL_DIR / "experiment_summary.json").write_text(json.dumps(summary, indent=2),
                                                       encoding="utf-8")
    print(f"[saved] experiment_summary.json")
    report.save()
    report.exit_on_hard_failure("dynamics")


if __name__ == "__main__":
    main()
