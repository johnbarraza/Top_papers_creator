"""
equilibrium_checks.py -- model-agnostic equilibrium & numerical-accuracy tests
for quantitative macro papers (general equilibrium, HA/HANK/TANK/RANK).

Copied verbatim into each macro project's scripts/python/ by Stage 4.
Do NOT edit per project. Every macro script must route its tests through
TestReport so Stage 4 / 4.5 / 7 can audit data/model/equilibrium_tests.json.

Each check returns a dict:
    {"id", "level" ("HARD"|"SOFT"), "passed", "value", "tol", "detail"}

HARD = a paper cannot be written if this fails (no equilibrium / wrong math).
SOFT = numerical-quality or calibration diagnostics reported in the appendix.

Requires numpy only (scipy.sparse matrices are accepted duck-typed).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np

HARD = "HARD"
SOFT = "SOFT"


def _result(check_id, level, passed, value=None, tol=None, detail=""):
    if value is not None:
        value = float(value)
        if not np.isfinite(value):
            passed = False
    return {
        "id": check_id,
        "level": level,
        "passed": bool(passed),
        "value": value,
        "tol": None if tol is None else float(tol),
        "detail": detail,
    }


def _maxabs(x) -> float:
    x = np.asarray(x, dtype=float)
    return float(np.max(np.abs(x))) if x.size else 0.0


# ── Market clearing & Walras' law ────────────────────────────────────────────

def market_clearing(market: str, supply, demand, tol=1e-6, level=HARD, scale=1.0):
    """|supply - demand| / scale < tol (scalar or along a path)."""
    resid = _maxabs(np.asarray(supply, float) - np.asarray(demand, float)) / max(scale, 1e-300)
    return _result(f"market_clearing:{market}", level, resid < tol, resid, tol,
                   f"max |{market} supply - demand| = {resid:.2e}")


def walras_law(omitted_market: str, residual, tol=1e-6, level=HARD, scale=1.0):
    """Walras' law: with N markets, clearing N-1 must clear the Nth.

    `residual` is the excess demand of the market NOT imposed by the solver
    (e.g. goods market when the solver clears the bond market). A large value
    means a budget constraint, accounting identity or aggregation is wrong.
    """
    resid = _maxabs(residual) / max(scale, 1e-300)
    return _result(f"walras_law:{omitted_market}", level, resid < tol, resid, tol,
                   f"excess demand in omitted market '{omitted_market}' = {resid:.2e}")


def accounting_identity(name: str, lhs, rhs, tol=1e-8, level=HARD, scale=1.0):
    """Generic identity check (Y = C + I + G, gov. budget, factor shares...)."""
    resid = _maxabs(np.asarray(lhs, float) - np.asarray(rhs, float)) / max(scale, 1e-300)
    return _result(f"identity:{name}", level, resid < tol, resid, tol,
                   f"max |lhs - rhs| = {resid:.2e}")


# ── Finite-difference HJB / KFE diagnostics (Achdou et al. 2022) ─────────────

def generator_rows_sum_zero(A, tol=1e-10):
    """Intensity matrix rows must sum to zero (mass is conserved)."""
    rows = np.asarray(A.sum(axis=1)).ravel()
    v = _maxabs(rows)
    return _result("generator_rows_sum_zero", HARD, v < tol, v, tol,
                   f"max |row sum| = {v:.2e}")


def generator_offdiag_nonnegative(A, tol=1e-12):
    """Upwind monotonicity (Barles-Souganidis): off-diagonals >= 0."""
    try:
        coo = A.tocoo()
        off = coo.data[coo.row != coo.col]
    except AttributeError:
        M = np.asarray(A, float)
        off = M[~np.eye(M.shape[0], dtype=bool)]
    v = float(off.min()) if off.size else 0.0
    return _result("generator_offdiag_nonnegative", HARD, v >= -tol, v, tol,
                   f"min off-diagonal entry = {v:.2e}")


def density_valid(mass, tol=1e-8):
    """Distribution: non-negative and total mass 1."""
    m = np.asarray(mass, float)
    neg = float(m.min())
    tot = float(m.sum())
    ok = neg >= -tol and abs(tot - 1.0) < tol
    return _result("density_valid", HARD, ok, abs(tot - 1.0), tol,
                   f"total mass = {tot:.10f}, min mass = {neg:.2e}")


def value_function_converged(distance, tol, iterations, max_iter):
    ok = distance < tol and iterations < max_iter
    return _result("hjb_converged", HARD, ok, distance, tol,
                   f"sup-norm change {distance:.2e} after {iterations} iterations")


def state_constraints(drift_at_min, drift_at_max, tol=1e-10):
    """Savings cannot push wealth outside [a_min, a_max]."""
    lo = float(np.min(drift_at_min))
    hi = float(np.max(drift_at_max))
    ok = lo >= -tol and hi <= tol
    return _result("state_constraints", HARD, ok, max(-lo, hi, 0.0), tol,
                   f"min drift at a_min = {lo:.2e}, max drift at a_max = {hi:.2e}")


def consumption_positive(c):
    v = float(np.min(c))
    return _result("consumption_positive", HARD, v > 0, v, 0.0,
                   f"min consumption = {v:.4e}")


def monotone_in_wealth(name: str, policy, tol=1e-10, level=SOFT):
    """Policy (rows = types, cols = wealth grid) weakly increasing in wealth."""
    p = np.atleast_2d(np.asarray(policy, float))
    worst = float(np.min(np.diff(p, axis=1))) if p.shape[1] > 1 else 0.0
    return _result(f"monotone_in_wealth:{name}", level, worst >= -tol, worst, tol,
                   f"most negative increment = {worst:.2e}")


def grid_upper_bound_slack(mass, share_of_grid=0.05, tol=1e-3):
    """Little mass near a_max, otherwise the grid truncates the distribution."""
    m = np.atleast_2d(np.asarray(mass, float))
    k = max(1, int(np.ceil(share_of_grid * m.shape[1])))
    top = float(m[:, -k:].sum())
    return _result("grid_upper_bound_slack", SOFT, top < tol, top, tol,
                   f"mass in top {share_of_grid:.0%} of wealth grid = {top:.2e}")


def euler_equation_errors(errors, tol_log10=-3.0, level=SOFT):
    """Discrete-time models: max log10 |Euler error| (Judd 1992)."""
    e = np.abs(np.asarray(errors, float))
    e = e[np.isfinite(e)]
    v = float(np.log10(max(e.max(), 1e-300))) if e.size else -np.inf
    return _result("euler_equation_errors", level, v < tol_log10, v, tol_log10,
                   f"max log10 Euler error = {v:.2f}")


# ── Theory-implied restrictions ─────────────────────────────────────────────

def precautionary_savings(r, rho):
    """Incomplete markets with a borrowing limit imply r < rho (Aiyagari 1994)."""
    return _result("precautionary_savings_r_below_rho", HARD, r < rho, rho - r, 0.0,
                   f"r = {r:.6f}, rho = {rho:.6f}")


def against_analytic(name: str, numeric, analytic, tol=1e-6, level=HARD, relative=False):
    """Numerical solution must reproduce a known closed form (nesting test).

    Examples: TANK multiplier 1/(1 - lambda*chi) (Bilbiie 2008), RANK IRF from
    the Euler equation, Huggett with no income risk -> r = rho.
    """
    num = np.asarray(numeric, float)
    ana = np.asarray(analytic, float)
    diff = _maxabs(num - ana)
    if relative:
        diff = diff / max(_maxabs(ana), 1e-300)
    return _result(f"analytic:{name}", level, diff < tol, diff, tol,
                   f"max |numeric - analytic| = {diff:.2e}")


def blanchard_kahn(n_unstable_eigs: int, n_jump_vars: int):
    """Linear RE models: determinacy iff #unstable eigenvalues = #jump vars."""
    ok = n_unstable_eigs == n_jump_vars
    return _result("blanchard_kahn_determinacy", HARD, ok, n_unstable_eigs - n_jump_vars, 0,
                   f"{n_unstable_eigs} unstable eigenvalues vs {n_jump_vars} jump variables")


def sequence_space_invertibility(M, max_cond=1e10):
    """Sequence-space determinacy proxy: (J - I) must be well conditioned."""
    c = float(np.linalg.cond(np.asarray(M, float)))
    return _result("sequence_space_invertible", HARD, c < max_cond, c, max_cond,
                   f"condition number of the equilibrium Jacobian = {c:.2e}")


# ── Transition / dynamics ───────────────────────────────────────────────────

def path_converges(name: str, path, steady_state, tol=1e-3, tail=5, level=SOFT, scale=1.0):
    """Transition must return to the steady state by the end of the horizon."""
    p = np.asarray(path, float)
    v = _maxabs(p[-tail:] - steady_state) / max(scale, 1e-300)
    return _result(f"path_converges:{name}", level, v < tol, v, tol,
                   f"max deviation over last {tail} periods = {v:.2e}")


def newton_converged(residual_norm, tol, iterations, max_iter):
    ok = residual_norm < tol and iterations <= max_iter
    return _result("transition_solver_converged", HARD, ok, residual_norm, tol,
                   f"max equilibrium residual {residual_norm:.2e} after {iterations} iterations")


def mass_conservation(total_mass_path, tol=1e-8):
    v = _maxabs(np.asarray(total_mass_path, float) - 1.0)
    return _result("mass_conservation", HARD, v < tol, v, tol,
                   f"max |total mass - 1| along the path = {v:.2e}")


def intertemporal_mpcs_present_value(J, R_step, cols=None, tol=0.05):
    """Columns of the iMPC matrix sum to 1 in present value (ARS 2024).

    Truncated at the horizon, so only columns well inside it are tested and
    the check is SOFT.
    """
    J = np.asarray(J, float)
    N = J.shape[0]
    cols = range(0, max(1, N // 4)) if cols is None else cols
    disc = R_step ** (-np.arange(N))
    errs = [abs(disc @ J[:, s] / disc[s] - 1.0) for s in cols]
    v = float(max(errs))
    return _result("impc_present_value_one", SOFT, v < tol, v, tol,
                   f"max |PV(column) - 1| over first {len(errs)} columns = {v:.3f}")


def sign_restriction(name: str, value, expected_sign: int, level=SOFT):
    v = float(value)
    ok = np.sign(v) == np.sign(expected_sign)
    return _result(f"sign:{name}", level, ok, v, None,
                   f"value = {v:.4e}, expected sign {'+' if expected_sign > 0 else '-'}")


# ── Discretization & calibration ────────────────────────────────────────────

def grid_robustness(name: str, coarse, fine, tol=1e-3, level=SOFT, relative=False):
    diff = abs(float(coarse) - float(fine))
    if relative:
        diff = diff / max(abs(float(fine)), 1e-300)
    return _result(f"grid_robustness:{name}", level, diff < tol, diff, tol,
                   f"coarse = {float(coarse):.6f}, fine = {float(fine):.6f}")


def calibration_targets(model_moments: dict, targets: dict) -> list[dict]:
    """One check per targeted moment.

    targets = {name: {"moment": key, "data": value, "tol": abs_tol,
                      "level": "SOFT"|"HARD", "source": "..."}}
    """
    out = []
    for name, spec in targets.items():
        key = spec.get("moment", name)
        data = float(spec["data"])
        tol = float(spec.get("tol", 0.05 * max(abs(data), 1e-3)))
        level = spec.get("level", SOFT)
        model = model_moments.get(key)
        if model is None:
            out.append(_result(f"calibration_target:{name}", level, False, None, tol,
                               f"moment '{key}' not computed by the model"))
            continue
        gap = abs(float(model) - data)
        out.append(_result(f"calibration_target:{name}", level, gap < tol, gap, tol,
                           f"model = {float(model):.4f}, data = {data:.4f} "
                           f"({spec.get('source', 'source n/a')})"))
    return out


# ── Report ──────────────────────────────────────────────────────────────────

class TestReport:
    """Accumulates checks across scripts into data/model/equilibrium_tests.json."""

    def __init__(self, path, model_class: str = "unknown"):
        self.path = Path(path)
        self.data = {"model_class": model_class, "tests": []}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        self.data["model_class"] = model_class or self.data.get("model_class", "unknown")

    def reset_stage(self, stage: str):
        self.data["tests"] = [t for t in self.data["tests"] if t.get("stage") != stage]

    def add(self, check, stage: str):
        checks = check if isinstance(check, list) else [check]
        for c in checks:
            c = dict(c)
            c["stage"] = stage
            self.data["tests"] = [t for t in self.data["tests"]
                                  if not (t["id"] == c["id"] and t.get("stage") == stage)]
            self.data["tests"].append(c)
            mark = "PASS" if c["passed"] else "FAIL"
            print(f"  [{mark}] [{c['level']}] {c['id']}: {c['detail']}")

    def summary(self) -> dict:
        tests = self.data["tests"]
        hard = [t for t in tests if t["level"] == HARD]
        soft = [t for t in tests if t["level"] == SOFT]
        return {
            "hard_total": len(hard),
            "hard_passed": sum(t["passed"] for t in hard),
            "soft_total": len(soft),
            "soft_passed": sum(t["passed"] for t in soft),
        }

    def hard_failures(self, stage: str | None = None) -> list[dict]:
        return [t for t in self.data["tests"]
                if t["level"] == HARD and not t["passed"]
                and (stage is None or t.get("stage") == stage)]

    def save(self):
        self.data["summary"] = self.summary()
        self.data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        s = self.data["summary"]
        print(f"  [tests] HARD {s['hard_passed']}/{s['hard_total']}, "
              f"SOFT {s['soft_passed']}/{s['soft_total']} -> {self.path}")

    def exit_on_hard_failure(self, stage: str):
        failed = self.hard_failures(stage)
        if failed:
            print("\nEQUILIBRIUM TEST FAILED -- the model is not solved; do not write a paper on it:")
            for t in failed:
                print(f"  - {t['id']}: {t['detail']}")
            raise SystemExit(1)
