"""
ha_core.py -- continuous-time heterogeneous-agent toolkit for one-asset
general-equilibrium models, solved with the finite-difference method of
Achdou, Han, Lasry, Lions & Moll (2022, REStud).

Model classes:
  huggett   bond economy; bonds in fixed supply B; solves for r.
  aiyagari  capital + Cobb-Douglas firm; solves for r (and w).
  hank      one-asset HANK with rigid prices (Auclert, Rognlie & Straub's
            intertemporal Keynesian cross): liquid government debt B,
            taxes T = r B, output demand-determined (Y = C). The steady
            state calibrates rho (or r) so that asset demand equals B.
            Monetary shocks are solved in sequence space (Newton on the
            goods-market residual with a brute-force Jacobian), and compared
            with RANK and TANK benchmarks.

Copied verbatim into each macro project's scripts/python/ by Stage 4.
Do NOT edit per project: project choices live in 00_calibration.py.
Requires numpy + scipy.
"""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.optimize import brentq

import equilibrium_checks as ec


# ═══════════════════════════════════════════════════════════════════════════
# Primitives
# ═══════════════════════════════════════════════════════════════════════════

def u(c, gamma):
    return np.log(c) if gamma == 1 else c ** (1 - gamma) / (1 - gamma)


def up(c, gamma):
    return c ** (-gamma)


def up_inv(x, gamma):
    return x ** (-1.0 / gamma)


def stationary_distribution(Lambda):
    """Stationary distribution pi of a continuous-time Markov chain (pi Lambda = 0)."""
    L = np.asarray(Lambda, float)
    M = L.T.copy()
    M[0, :] = 1.0
    b = np.zeros(L.shape[0])
    b[0] = 1.0
    return np.linalg.solve(M, b)


def two_state_income(z_low, z_high, lam_lh, lam_hl, normalize=True):
    """Two-state Poisson income (low->high at rate lam_lh, high->low at lam_hl).

    normalize=True rescales z so that E[z] = 1 under the stationary
    distribution, which makes aggregate labor income equal to Y (or wL).
    """
    Lambda = np.array([[-lam_lh, lam_lh], [lam_hl, -lam_hl]], float)
    z = np.array([z_low, z_high], float)
    if normalize:
        z = z / (stationary_distribution(Lambda) @ z)
    return z, Lambda


class Grid:
    """Wealth grid x income types. curvature > 1 concentrates points near
    a_min, where policy functions bend (Achdou et al. 2022, numerical
    appendix). The scheme is a Markov-chain approximation, so the KFE is
    solved for cell masses and needs no extra weighting on a non-uniform grid.
    """

    def __init__(self, a_min, a_max, n_a, z, Lambda, curvature=1.0):
        x = np.linspace(0.0, 1.0, int(n_a))
        self.a = a_min + (a_max - a_min) * x ** float(curvature)
        d = np.diff(self.a)
        self.daf = np.append(d, d[-1])          # forward step a_{i+1} - a_i
        self.dab = np.insert(d, 0, d[0])        # backward step a_i - a_{i-1}
        self.z = np.asarray(z, float)
        self.Lambda = np.asarray(Lambda, float)
        if np.max(np.abs(self.Lambda.sum(axis=1))) > 1e-12:
            raise ValueError("Income generator rows must sum to zero")
        self.pi = stationary_distribution(self.Lambda)
        self.I, self.J = self.a.size, self.z.size
        self.N = self.I * self.J
        self.a_rep = np.tile(self.a, self.J)                       # (N,)
        self.A_z = sp.kron(sp.csr_matrix(self.Lambda), sp.identity(self.I), format="csr")
        self.Id = sp.identity(self.N, format="csr")
        # Fix the KFE normalization where mass is guaranteed positive:
        # lowest-income type at the borrowing limit.
        self.i_fix = int(np.argmin(self.z)) * self.I


def make_grid(params) -> Grid:
    z, Lambda = income_process(params)
    return Grid(params["a_min"], params["a_max"], params["n_a"], z, Lambda,
                curvature=params.get("grid_curvature", 2.0))


def income_process(params):
    if "z" in params and "Lambda" in params:
        z = np.asarray(params["z"], float)
        Lambda = np.asarray(params["Lambda"], float)
        if params.get("normalize_income", True):
            z = z / (stationary_distribution(Lambda) @ z)
        return z, Lambda
    return two_state_income(params["z_low"], params["z_high"],
                            params["lam_lh"], params["lam_hl"],
                            normalize=params.get("normalize_income", True))


# ═══════════════════════════════════════════════════════════════════════════
# Household block
# ═══════════════════════════════════════════════════════════════════════════

def _policies(V, grid, r, y, gamma):
    """Upwind consumption/savings given V (J x I), rate r, income y (J,)."""
    inc = y[:, None] + r * grid.a[None, :]
    if np.min(inc) <= 0:
        raise ValueError(
            f"Non-positive cash flow y + r a = {np.min(inc):.3e}: a_min is below the "
            "natural borrowing limit for these prices. Raise a_min or check income.")
    dVf = np.empty_like(V)
    dVb = np.empty_like(V)
    dVf[:, :-1] = (V[:, 1:] - V[:, :-1]) / grid.daf[:-1]
    dVf[:, -1] = up(inc[:, -1], gamma)
    dVb[:, 1:] = (V[:, 1:] - V[:, :-1]) / grid.dab[1:]
    dVb[:, 0] = up(inc[:, 0], gamma)
    dVf = np.maximum(dVf, 1e-12)
    dVb = np.maximum(dVb, 1e-12)

    cf = up_inv(dVf, gamma)
    cb = up_inv(dVb, gamma)
    sf = inc - cf
    sb = inc - cb
    sf[:, -1] = 0.0          # state constraint at a_max
    sb[:, 0] = 0.0           # state constraint at a_min
    If = sf > 0
    Ib = (sb < 0) & ~If
    c = np.where(If, cf, np.where(Ib, cb, inc))
    return c, np.where(If, sf, 0.0), np.where(Ib, sb, 0.0)


def _generator(grid, s_f, s_b):
    """Intensity matrix A (N x N): wealth drift (upwind) + income switching."""
    X = (-s_b / grid.dab[None, :]).ravel()
    Z = (s_f / grid.daf[None, :]).ravel()
    A_a = sp.diags([X[1:], -(X + Z), Z[:-1]], [-1, 0, 1],
                   shape=(grid.N, grid.N), format="csr")
    return (A_a + grid.A_z).tocsr()


def solve_hjb(grid, r, y, rho, gamma, V0=None, Delta=1000.0, tol=1e-8, max_iter=1000):
    y = np.asarray(y, float)
    if V0 is None:
        V0 = u(y[:, None] + r * grid.a[None, :], gamma) / rho
    V = V0.copy()
    dist = np.inf
    it = 0
    for it in range(1, max_iter + 1):
        c, sf, sb = _policies(V, grid, r, y, gamma)
        A = _generator(grid, sf, sb)
        M = ((1.0 / Delta + rho) * grid.Id - A).tocsc()
        V_new = spla.spsolve(M, (u(c, gamma) + V / Delta).ravel()).reshape(V.shape)
        dist = float(np.max(np.abs(V_new - V)))
        V = V_new
        if dist < tol:
            break
    c, sf, sb = _policies(V, grid, r, y, gamma)
    A = _generator(grid, sf, sb)
    return {"V": V, "c": c, "s_f": sf, "s_b": sb, "s": sf + sb, "A": A,
            "hjb_distance": dist, "hjb_iterations": it, "hjb_tol": tol,
            "hjb_max_iter": max_iter}


def solve_kfe(grid, A):
    """Stationary mass vector m (J x I), sum(m) = 1."""
    AT = A.T.tolil()
    AT[grid.i_fix, :] = 0.0
    AT[grid.i_fix, grid.i_fix] = 1.0
    b = np.zeros(grid.N)
    b[grid.i_fix] = 1.0
    g = spla.spsolve(AT.tocsc(), b)
    return (g / g.sum()).reshape(grid.J, grid.I)


def household_ss(grid, r, y, rho, gamma, V0=None, **hjb_kw):
    hh = solve_hjb(grid, r, y, rho, gamma, V0=V0, **hjb_kw)
    m = solve_kfe(grid, hh["A"])
    hh["m"] = m
    hh["assets"] = float((m * grid.a[None, :]).sum())
    hh["consumption"] = float((m * hh["c"]).sum())
    return hh


# ═══════════════════════════════════════════════════════════════════════════
# Steady state (general equilibrium)
# ═══════════════════════════════════════════════════════════════════════════

def _prices(model, params, x, grid):
    """Map the unknown x into (r, rho, y-vector, aggregates dict, asset demand)."""
    gamma = params["gamma"]
    if model == "aiyagari":
        r, rho = x, params["rho"]
        alpha, delta = params["alpha"], params["delta"]
        L = float(grid.pi @ grid.z)
        K = L * (alpha / (r + delta)) ** (1.0 / (1.0 - alpha))
        w = (1 - alpha) * K ** alpha * L ** (-alpha)
        Y = K ** alpha * L ** (1 - alpha)
        return r, rho, w * grid.z, {"K": K, "w": w, "Y": Y, "L": L, "T": 0.0}, K
    B = params.get("B", 0.0)
    Y = params.get("Y", 1.0)
    if model == "huggett":
        r, rho = x, params["rho"]
    elif model == "hank":
        if params.get("calibrate", "rho") == "rho":
            r, rho = params["r"], x
        else:
            r, rho = x, params["rho"]
    else:
        raise ValueError(f"Unknown model class '{model}' (huggett|aiyagari|hank)")
    T = r * B
    return r, rho, grid.z * (Y - T), {"Y": Y, "T": T, "B": B, "w": Y - T}, B


def _unknown(model, params):
    if model == "hank" and params.get("calibrate", "rho") == "rho":
        return "rho"
    return "r"


def _bracket(model, params, grid):
    name = _unknown(model, params)
    if "bracket" in params:
        return tuple(params["bracket"])
    if name == "rho":
        return params["r"] + 1e-4, params["r"] + 0.25
    rho = params["rho"]
    hi = rho - 1e-5
    if model == "aiyagari":
        return -params["delta"] + 1e-3, hi
    # Bond economy: keep cash flow y_min + r a > 0 on the whole grid.
    y_min = float(np.min(grid.z)) * (params.get("Y", 1.0) - max(rho, 0.0) * params.get("B", 0.0))
    lo = max(-rho, -0.95 * y_min / params["a_max"])
    if params["a_min"] < 0:
        hi = min(hi, 0.95 * y_min / (-params["a_min"]))
    return lo, hi


def steady_state(model, params, grid=None, xtol=1e-10, verbose=True):
    """Solve the stationary equilibrium. Returns a dict with policies,
    distribution, prices, aggregates and the market-clearing residuals."""
    grid = grid or make_grid(params)
    gamma = params["gamma"]
    hjb_kw = {k: params[k] for k in ("Delta", "hjb_tol") if k in params}
    if "hjb_tol" in hjb_kw:
        hjb_kw["tol"] = hjb_kw.pop("hjb_tol")
    cache = {"V": None}

    def excess(x):
        r, rho, y, agg, demand = _prices(model, params, x, grid)
        hh = household_ss(grid, r, y, rho, gamma, V0=cache["V"], **hjb_kw)
        cache["V"] = hh["V"]
        return hh["assets"] - demand

    lo, hi = _bracket(model, params, grid)
    e_lo, e_hi = excess(lo), excess(hi)
    if np.sign(e_lo) == np.sign(e_hi):
        raise RuntimeError(
            f"No sign change in asset-market excess demand on [{lo:.4f}, {hi:.4f}] "
            f"({e_lo:.3e}, {e_hi:.3e}). Widen params['bracket'] or raise a_max.")
    cache["V"] = None
    x = brentq(excess, lo, hi, xtol=xtol, maxiter=200)

    r, rho, y, agg, demand = _prices(model, params, x, grid)
    hh = household_ss(grid, r, y, rho, gamma, **hjb_kw)
    ss = {"model": model, "unknown": _unknown(model, params), "x": x,
          "params": dict(params), "grid": grid, "r": r, "rho": rho, "gamma": gamma,
          "y": y, **agg, **hh}
    ss["asset_demand"] = demand
    ss["C"] = hh["consumption"]
    ss["A_hh"] = hh["assets"]
    if model == "aiyagari":
        ss["goods_residual"] = ss["Y"] - ss["C"] - params["delta"] * ss["K"]
    else:
        ss["goods_residual"] = ss["C"] - ss["Y"]
    if verbose:
        print(f"  [ss] {model}: {ss['unknown']} = {x:.6f}, r = {r:.6f}, rho = {rho:.6f}, "
              f"A = {ss['A_hh']:.6f} vs demand {demand:.6f}")
    return ss


# ═══════════════════════════════════════════════════════════════════════════
# Moments
# ═══════════════════════════════════════════════════════════════════════════

def mpc(ss, horizon=0.25, windfall=None, n_steps=25):
    """Average MPC over `horizon` out of a one-time windfall (Feynman-Kac,
    Achdou et al. 2022, Appendix). Returns (average MPC, MPC array J x I)."""
    grid = ss["grid"]
    income = ss.get("Y", 1.0)
    windfall = 0.01 * income if windfall is None else windfall
    dt = horizon / n_steps
    lu = spla.splu(((1.0 / dt) * grid.Id - ss["A"]).tocsc())
    G = np.zeros(grid.N)
    c = ss["c"].ravel()
    for _ in range(n_steps):
        G = lu.solve(c + G / dt)
    G = G.reshape(grid.J, grid.I)
    mpcs = np.empty_like(G)
    for j in range(grid.J):
        mpcs[j] = (np.interp(grid.a + windfall, grid.a, G[j]) - G[j]) / windfall
    return float((ss["m"] * mpcs).sum()), mpcs


def _lorenz_shares(values, weights):
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cw = np.cumsum(w)
    cv = np.cumsum(v * w)
    total = cv[-1]
    if total <= 1e-10 * max(np.sum(np.abs(v) * w), 1e-300):
        return float("nan"), float("nan"), float("nan")   # no positive net wealth
    gini = 1.0 - np.sum(w * (np.concatenate(([0.0], cv[:-1])) + cv)) / total
    top10 = 1.0 - np.interp(0.9, cw, cv) / total
    bottom50 = np.interp(0.5, cw, cv) / total
    return float(gini), float(top10), float(bottom50)


def moments(ss, mpc_horizon=0.25):
    grid = ss["grid"]
    m = ss["m"]
    marg = m.sum(axis=0)
    income = ss.get("Y", 1.0)
    gini, top10, bottom50 = _lorenz_shares(grid.a, marg)
    avg_mpc, _ = mpc(ss, horizon=mpc_horizon)
    return {
        "r": ss["r"],
        "rho": ss["rho"],
        "wealth_to_income": ss["A_hh"] / income,
        "frac_constrained": float(marg[0]),
        "frac_negative_wealth": float(marg[grid.a < 0].sum()),
        "gini_wealth": gini,
        "top10_wealth_share": top10,
        "bottom50_wealth_share": bottom50,
        "mpc": avg_mpc,
        "consumption": ss["C"],
        "output": income,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Steady-state equilibrium tests
# ═══════════════════════════════════════════════════════════════════════════

def steady_state_checks(ss, tol_market=1e-6, tol_walras=1e-6):
    grid = ss["grid"]
    scale = max(abs(ss.get("Y", 1.0)), 1e-12)
    checks = [
        ec.value_function_converged(ss["hjb_distance"], ss["hjb_tol"],
                                    ss["hjb_iterations"], ss["hjb_max_iter"]),
        ec.generator_rows_sum_zero(ss["A"]),
        ec.generator_offdiag_nonnegative(ss["A"]),
        ec.density_valid(ss["m"]),
        ec.state_constraints(ss["s"][:, 0], ss["s"][:, -1]),
        ec.consumption_positive(ss["c"]),
        ec.monotone_in_wealth("consumption", ss["c"]),
        ec.grid_upper_bound_slack(ss["m"]),
        ec.market_clearing("assets", ss["A_hh"], ss["asset_demand"], tol=tol_market, scale=scale),
        ec.walras_law("goods", ss["goods_residual"], tol=tol_walras, scale=scale),
        ec.precautionary_savings(ss["r"], ss["rho"]),
        ec.accounting_identity("labor_income_normalization",
                               float(grid.pi @ grid.z), 1.0, tol=1e-10),
    ]
    if ss["model"] in ("huggett", "hank"):
        checks.append(ec.accounting_identity("government_budget", ss["T"],
                                             ss["r"] * ss["B"], tol=1e-12))
    return checks


def grid_robustness_check(model, params, ss, factor=2):
    fine = dict(params)
    fine["n_a"] = int(params["n_a"] * factor)
    ss_fine = steady_state(model, fine, verbose=False)
    return ec.grid_robustness(ss["unknown"], ss["x"], ss_fine["x"], tol=5e-3, relative=True)


# ═══════════════════════════════════════════════════════════════════════════
# Dynamics: one-asset HANK with rigid prices (sequence space)
# ═══════════════════════════════════════════════════════════════════════════

def household_path(ss, r_path, y_path, dt, first_dev=None):
    """Backward HJB + forward KFE for given price paths.

    r_path (N,), y_path (J, N). Returns C (N,), A_end (N,), mass (N,),
    income (N,): C[t] and income[t] are evaluated on the end-of-step
    distribution, which makes the discrete household budget hold exactly:
        A[t+1] - A[t] = dt * (r[t] A[t+1] + income[t] - C[t]).
    `first_dev`: if inputs are at steady state for t > first_dev, the backward
    pass reuses steady-state policies there (Jacobian speed-up).
    """
    grid = ss["grid"]
    N = r_path.size
    rho, gamma = ss["rho"], ss["gamma"]
    last = N - 1 if first_dev is None else min(int(first_dev), N - 1)
    A_list = [None] * N
    c_list = [None] * N
    V = ss["V"]
    for t in range(N - 1, -1, -1):
        if t > last:
            A_list[t], c_list[t] = None, ss["c"]
            continue
        c, sf, sb = _policies(V, grid, r_path[t], y_path[:, t], gamma)
        A = _generator(grid, sf, sb)
        M = ((1.0 / dt + rho) * grid.Id - A).tocsc()
        V = spla.spsolve(M, (u(c, gamma) + V / dt).ravel()).reshape(V.shape)
        A_list[t], c_list[t] = A, c

    lu_ss = None
    m = ss["m"].ravel()
    C = np.empty(N)
    A_end = np.empty(N)
    mass = np.empty(N)
    income = np.empty(N)
    for t in range(N):
        if A_list[t] is None:
            if lu_ss is None:
                lu_ss = spla.splu((grid.Id - dt * ss["A"].T).tocsc())
            m = lu_ss.solve(m)
        else:
            m = spla.spsolve((grid.Id - dt * A_list[t].T).tocsc(), m)
        C[t] = m @ c_list[t].ravel()
        A_end[t] = m @ grid.a_rep
        mass[t] = m.sum()
        income[t] = m @ np.repeat(y_path[:, t], grid.I)
    return {"C": C, "A_end": A_end, "mass": mass, "income": income}


def _hank_inputs(ss, r_path, Y_path, hold_taxes=False):
    T_path = np.full_like(r_path, ss["T"]) if hold_taxes else r_path * ss["B"]
    y = ss["grid"].z[:, None] * (Y_path - T_path)[None, :]
    return T_path, y


def jacobian_C_Y(ss, N, dt, h=1e-4):
    """dC_t / dY_s at the steady state (brute force, one pass per column)."""
    r0 = np.full(N, ss["r"])
    Y0 = np.full(N, ss["Y"])
    _, y0 = _hank_inputs(ss, r0, Y0)
    base = household_path(ss, r0, y0, dt)["C"]
    Jac = np.empty((N, N))
    for s in range(N):
        Y = Y0.copy()
        Y[s] += h
        _, y = _hank_inputs(ss, r0, Y)
        Jac[:, s] = (household_path(ss, r0, y, dt, first_dev=s)["C"] - base) / h
    return Jac


def monetary_shock_path(ss, size, persistence, N, dt):
    t = dt * np.arange(N)
    return ss["r"] + size * np.exp(-persistence * t), t


def solve_transition_hank(ss, r_path, dt, tol=1e-9, max_iter=30, Jac=None, verbose=True):
    """Equilibrium output path: Newton on H(Y) = C(Y; r) - Y = 0."""
    N = r_path.size
    Jac = jacobian_C_Y(ss, N, dt) if Jac is None else Jac
    M = Jac - np.eye(N)
    Y = np.full(N, ss["Y"])
    res_norm = np.inf
    it = 0
    for it in range(1, max_iter + 1):
        T_path, y = _hank_inputs(ss, r_path, Y)
        out = household_path(ss, r_path, y, dt)
        res = out["C"] - Y
        res_norm = float(np.max(np.abs(res)))
        if verbose:
            print(f"  [transition] iter {it}: max |C - Y| = {res_norm:.2e}")
        if res_norm < tol:
            break
        Y = Y - np.linalg.solve(M, res)
    T_path, y = _hank_inputs(ss, r_path, Y)
    out = household_path(ss, r_path, y, dt)
    out.update({"Y": Y, "T": T_path, "r": r_path, "Jac": Jac, "M": M,
                "residual": float(np.max(np.abs(out["C"] - Y))), "iterations": it,
                "tol": tol, "max_iter": max_iter, "dt": dt})
    # Kaplan-Moll-Violante decomposition: direct effect of r holding income fixed
    _, y_fixed = _hank_inputs(ss, r_path, np.full(N, ss["Y"]), hold_taxes=True)
    out["C_direct"] = household_path(ss, r_path, y_fixed, dt)["C"]
    return out


def rank_tank_irfs(ss, r_path, dt, lam=None):
    """Linearized RANK and TANK output IRFs (levels, deviation from ss) for the
    same real-rate path. Rigid prices: Y = C.

    RANK: Euler  dc_t = -(1/gamma) sum_{u>=t} dr_u dt.
    TANK: share lam of hand-to-mouth consume Y - T, savers follow the Euler
    equation (Bilbiie 2008; Debortoli & Gali 2018). lam defaults to the HANK
    mass at the borrowing constraint.
    """
    gamma = ss["gamma"]
    dr = r_path - ss["r"]
    euler = -(1.0 / gamma) * np.cumsum((dr * dt)[::-1])[::-1]
    rank = ss["Y"] * euler
    lam = float(ss["m"][:, 0].sum()) if lam is None else float(lam)
    B, Y, T = ss["B"], ss["Y"], ss["T"]
    C_saver = (Y - lam * (Y - T)) / (1.0 - lam)
    tank = C_saver * euler - lam / (1.0 - lam) * B * dr
    return {"rank": rank, "tank": tank, "lambda": lam}


def transition_checks(ss, tr, tol_newton=1e-7, tol_walras=1e-6):
    N = tr["Y"].size
    dt = tr["dt"]
    R_step = 1.0 / (1.0 - dt * ss["r"])
    A_start = np.concatenate(([ss["A_hh"]], tr["A_end"][:-1]))
    budget_lhs = tr["A_end"] - A_start
    budget_rhs = dt * (tr["r"] * tr["A_end"] + tr["income"] - tr["C"])
    return [
        ec.newton_converged(tr["residual"], tol_newton, tr["iterations"], tr["max_iter"]),
        ec.market_clearing("goods_path", tr["C"], tr["Y"], tol=tol_newton),
        ec.walras_law("assets_path", tr["A_end"] - ss["B"], tol=tol_walras,
                      scale=max(abs(ss["B"]), 1.0)),
        ec.accounting_identity("household_budget_path", budget_lhs, budget_rhs, tol=1e-8),
        ec.mass_conservation(tr["mass"]),
        ec.sequence_space_invertibility(tr["M"]),
        ec.intertemporal_mpcs_present_value(tr["Jac"], R_step),
        ec.path_converges("output", tr["Y"], ss["Y"], tol=1e-3),
        ec.sign_restriction("output_impact_of_tightening",
                            (tr["Y"][0] - ss["Y"]) * np.sign(tr["r"][0] - ss["r"]), -1),
    ]
