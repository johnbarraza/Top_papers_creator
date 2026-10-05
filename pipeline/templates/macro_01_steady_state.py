"""
01_steady_state.py -- stationary general equilibrium + calibration + tests.

Reads data/model/calibration.json (from 00_calibration.py). Solves the
stationary equilibrium with the HJB-KFE finite-difference method, runs the
internal calibration if requested, and records every equilibrium test in
data/model/equilibrium_tests.json. Exits with code 1 on any HARD failure.
"""

# ════════════════════════════════════════════════════════════════════════════
# PROJECT-SPECIFIC VARIABLES (Claude fills these)
# ════════════════════════════════════════════════════════════════════════════

# Run the steady state twice as fine to test discretization error (True/False)
GRID_ROBUSTNESS = {{GRID_ROBUSTNESS}}

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


def mpc_horizon(time_unit):
    return 0.25 if time_unit == "year" else 1.0     # one quarter


def internal_calibration(model, params, spec):
    from scipy.optimize import least_squares

    ic = spec["internal_calibration"]
    free = ic["free_params"]
    names = list(free)
    lo = np.array([free[n][0] for n in names], float)
    hi = np.array([free[n][1] for n in names], float)
    targets = [spec["calibration_targets"][t] for t in ic["targets"]]
    horizon = mpc_horizon(spec["time_unit"])

    def resid(x):
        p = dict(params, **dict(zip(names, map(float, x))))
        try:
            ss = hc.steady_state(model, p, verbose=False)
        except (RuntimeError, ValueError):
            return np.full(len(targets), 1e3)
        mom = hc.moments(ss, mpc_horizon=horizon)
        return np.array([(mom[t["moment"]] - t["data"]) / max(abs(t["data"]), 1e-3)
                         for t in targets])

    x0 = np.clip(np.array([params.get(n, 0.5 * (a + b)) for n, (a, b) in free.items()]),
                 lo + 1e-9, hi - 1e-9)
    sol = least_squares(resid, x0, bounds=(lo, hi), xtol=1e-8, ftol=1e-10, max_nfev=200)
    print(f"  [calibration] {dict(zip(names, np.round(sol.x, 6)))}, "
          f"max rel. gap = {np.max(np.abs(sol.fun)):.2e}")
    return dict(params, **dict(zip(names, map(float, sol.x)))), sol


def main():
    spec = json.loads((MODEL_DIR / "calibration.json").read_text(encoding="utf-8"))
    model = spec["model_class"]
    report = ec.TestReport(MODEL_DIR / "equilibrium_tests.json", model)
    report.reset_stage("steady_state")
    params = dict(spec["params"])

    if spec.get("internal_calibration"):
        params, sol = internal_calibration(model, params, spec)
        report.add(ec._result("calibration:optimizer_converged", ec.SOFT, sol.success,
                              float(np.max(np.abs(sol.fun))), None, sol.message), "steady_state")

    ss = hc.steady_state(model, params)
    report.add(hc.steady_state_checks(ss), "steady_state")
    if GRID_ROBUSTNESS:
        report.add(hc.grid_robustness_check(model, params, ss), "steady_state")

    mom = hc.moments(ss, mpc_horizon=mpc_horizon(spec["time_unit"]))
    report.add(ec.calibration_targets(mom, spec["calibration_targets"]), "steady_state")

    grid = ss["grid"]
    scalars = {k: float(ss[k]) for k in ("r", "rho", "C", "A_hh", "asset_demand",
                                          "goods_residual", "Y", "T", "B", "K", "w")
               if k in ss}
    out = {"model_class": model, "unknown": ss["unknown"], "unknown_value": float(ss["x"]),
           "params": params, "scalars": scalars, "moments": mom,
           "income_states": grid.z.tolist(), "income_stationary": grid.pi.tolist()}
    (MODEL_DIR / "steady_state.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    (MODEL_DIR / "calibration_final.json").write_text(
        json.dumps(dict(spec, params=params), indent=2), encoding="utf-8")

    rows = ["a," + ",".join(f"{v}_z{j}" for j in range(grid.J) for v in ("c", "s", "mass"))]
    for i, a in enumerate(grid.a):
        vals = []
        for j in range(grid.J):
            vals += [ss["c"][j, i], ss["s"][j, i], ss["m"][j, i]]
        rows.append(f"{a:.10g}," + ",".join(f"{v:.10g}" for v in vals))
    (MODEL_DIR / "steady_state_policies.csv").write_text("\n".join(rows), encoding="utf-8")
    print(f"[saved] steady_state.json, calibration_final.json, steady_state_policies.csv")

    report.save()
    report.exit_on_hard_failure("steady_state")


if __name__ == "__main__":
    main()
