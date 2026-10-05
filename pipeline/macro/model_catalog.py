"""Catalog of quantitative-macro model classes and their test contracts.

Each class lists the markets that must clear, which market Walras' law
leaves redundant, the solution method, canonical references, typical
calibration targets, and the equilibrium tests a project MUST report in
data/model/equilibrium_tests.json before Stage 5 writes the paper.

`template` = True means ha_core.py solves it out of the box; otherwise
Stage 4 asks for a custom solver that still reports through
equilibrium_checks.TestReport using the same test ids.
"""

from __future__ import annotations

# Test ids required for every class solved with the HJB-KFE toolkit
_HA_STEADY_STATE = [
    "hjb_converged",
    "generator_rows_sum_zero",
    "generator_offdiag_nonnegative",
    "density_valid",
    "state_constraints",
    "consumption_positive",
    "market_clearing:assets",
    "walras_law:goods",
    "precautionary_savings_r_below_rho",
]
_SEQUENCE_SPACE = [
    "transition_solver_converged",
    "market_clearing:goods_path",
    "walras_law:assets_path",
    "identity:household_budget_path",
    "mass_conservation",
    "sequence_space_invertible",
]

MODEL_CLASSES: dict[str, dict] = {
    "rank": {
        "name": "Representative-agent New Keynesian (RANK)",
        "template": False,
        "markets": ["goods", "bonds (zero net supply)", "labor"],
        "walras_redundant": "bonds",
        "solution": "Linearized 3-equation NK model; Blanchard-Kahn / QZ (or sequence space)",
        "references": ["Gali (2015)", "Woodford (2003)"],
        "targets": ["Taylor-rule coefficients", "Phillips-curve slope", "IES"],
        "required_tests": ["blanchard_kahn_determinacy", "analytic:three_equation_nk_irf"],
        "keywords": ["rank", "representative agent", "three-equation", "3-equation", "new keynesian"],
    },
    "tank": {
        "name": "Two-agent New Keynesian (TANK)",
        "template": False,
        "markets": ["goods", "bonds", "labor"],
        "walras_redundant": "bonds",
        "solution": "Closed form / linearized; aggregate demand multiplier 1/(1 - lambda chi)",
        "references": ["Bilbiie (2008, 2020)", "Debortoli and Gali (2018)",
                       "Galí, López-Salido and Vallés (2007)"],
        "targets": ["share of hand-to-mouth lambda", "income cyclicality chi"],
        "required_tests": ["blanchard_kahn_determinacy", "analytic:tank_multiplier",
                           "analytic:tank_lambda0_equals_rank"],
        "keywords": ["tank", "two-agent", "two agent", "hand-to-mouth", "spender-saver"],
    },
    "huggett": {
        "name": "Huggett (1993) bond economy",
        "template": True,
        "markets": ["bonds (fixed supply B)", "goods (endowment)"],
        "walras_redundant": "goods",
        "solution": "Continuous-time HJB-KFE, implicit upwind (Achdou et al. 2022)",
        "references": ["Huggett (1993)", "Achdou, Han, Lasry, Lions and Moll (2022)",
                       "Guerrieri and Lorenzoni (2017)"],
        "targets": ["wealth/income", "share with negative net worth", "average MPC"],
        "required_tests": _HA_STEADY_STATE,
        "keywords": ["huggett", "bond economy", "credit crunch", "borrowing limit", "debt limit"],
    },
    "aiyagari": {
        "name": "Aiyagari (1994) / Bewley economy with capital",
        "template": True,
        "markets": ["capital", "labor", "goods"],
        "walras_redundant": "goods",
        "solution": "Continuous-time HJB-KFE + firm FOCs; bisection on r",
        "references": ["Aiyagari (1994)", "Bewley (1986)", "Achdou et al. (2022)"],
        "targets": ["K/Y", "wealth Gini", "top 10% wealth share"],
        "required_tests": _HA_STEADY_STATE,
        "keywords": ["aiyagari", "bewley", "precautionary", "wealth inequality", "capital tax"],
    },
    "hank": {
        "name": "One-asset HANK (rigid prices, intertemporal Keynesian cross)",
        "template": True,
        "markets": ["liquid bonds (government debt B)", "goods (demand-determined)"],
        "walras_redundant": "bonds (along the transition) / goods (in steady state)",
        "solution": "HJB-KFE steady state; sequence-space Newton with brute-force Jacobian",
        "references": ["Kaplan, Moll and Violante (2018)", "Auclert, Rognlie and Straub (2024)",
                       "McKay, Nakamura and Steinsson (2016)", "Werning (2015)"],
        "targets": ["liquid wealth / income", "average quarterly MPC", "share hand-to-mouth"],
        "required_tests": _HA_STEADY_STATE + _SEQUENCE_SPACE + ["analytic:tank_lambda0_equals_rank"],
        "keywords": ["hank", "heterogeneous agent new keynesian", "monetary transmission",
                     "fiscal multiplier", "intertemporal keynesian cross", "mpc"],
    },
    "hank_two_asset": {
        "name": "Two-asset HANK (liquid/illiquid, Kaplan-Moll-Violante)",
        "template": False,
        "markets": ["liquid bonds", "illiquid capital/equity", "labor", "goods"],
        "walras_redundant": "goods",
        "solution": "2-D HJB-KFE with adjustment cost (KMV 2018 code) or SSJ toolkit",
        "references": ["Kaplan, Moll and Violante (2018)", "Kaplan and Violante (2014)",
                       "Auclert, Bardoczy, Rognlie and Straub (2021)"],
        "targets": ["liquid/illiquid wealth ratios", "wealthy hand-to-mouth share", "MPC"],
        "required_tests": _HA_STEADY_STATE + _SEQUENCE_SPACE + ["market_clearing:illiquid"],
        "keywords": ["two-asset", "two asset", "illiquid", "wealthy hand-to-mouth", "kmv"],
    },
    "krusell_smith": {
        "name": "Krusell-Smith (aggregate risk with heterogeneity)",
        "template": False,
        "markets": ["capital", "labor", "goods"],
        "walras_redundant": "goods",
        "solution": "Approximate aggregation (perceived law of motion) or perturbation in sequence space",
        "references": ["Krusell and Smith (1998)", "Ahn, Kaplan, Moll, Winberry and Wolf (2018)"],
        "targets": ["K/Y", "wealth Gini"],
        "required_tests": _HA_STEADY_STATE + ["plm_r_squared", "den_haan_error"],
        "keywords": ["krusell", "aggregate risk", "approximate aggregation"],
    },
    "olg": {
        "name": "Overlapping generations / life-cycle GE",
        "template": False,
        "markets": ["capital", "labor", "goods", "government budget"],
        "walras_redundant": "goods",
        "solution": "Backward induction over ages + forward cohort distribution; fixed point on prices",
        "references": ["Auerbach and Kotlikoff (1987)", "Conesa, Kitao and Krueger (2009)"],
        "targets": ["K/Y", "life-cycle wealth profile", "replacement rate"],
        "required_tests": ["market_clearing:capital", "walras_law:goods", "density_valid",
                           "identity:government_budget", "euler_equation_errors"],
        "keywords": ["olg", "overlapping generations", "life-cycle", "pension", "social security"],
    },
    "search_matching": {
        "name": "Search and matching labor market (DMP)",
        "template": False,
        "markets": ["labor (matching)", "goods"],
        "walras_redundant": "goods",
        "solution": "Free entry + Nash bargaining; steady state and linearized dynamics",
        "references": ["Mortensen and Pissarides (1994)", "Shimer (2005)", "Hall (2005)"],
        "targets": ["job-finding rate", "separation rate", "unemployment", "vacancy-unemployment ratio"],
        "required_tests": ["identity:beveridge_flow_balance", "identity:free_entry",
                           "walras_law:goods", "blanchard_kahn_determinacy"],
        "keywords": ["search", "matching", "dmp", "unemployment", "vacanc", "labor market"],
    },
}

# Placeholder values for the macro templates, per supported class. Used by
# the Stage 3.3 smoke test and the test-suite; Stage 4 overwrites them with
# the project's calibration.
_INCOME = {"z_low": 0.5, "z_high": 1.5, "lam_lh": 0.5, "lam_hl": 0.5}
_COMMON = {
    "GRID_ROBUSTNESS": "True",
    "TANK_LAMBDA": "None",
    "MOMENT_LABELS": "{}",
    "DATA_FILES": "[]",
    "TIME_UNIT": '"year"',
    "UNTARGETED_MOMENTS": '{"wealth_gini": {"moment": "gini_wealth", "data": 0.6, '
                          '"source": "illustrative"}}',
}
MACRO_DEFAULTS: dict[str, dict[str, str]] = {
    "hank": {
        **_COMMON,
        "PAPER_TITLE": '"Smoke test: one-asset HANK"',
        "MODEL_CLASS": '"hank"',
        "PARAMS": repr({"gamma": 2.0, "r": 0.02, "B": 1.0, "Y": 1.0, "a_min": 0.0,
                        "a_max": 20.0, "n_a": 150, "calibrate": "rho", **_INCOME}),
        "PARAM_SOURCES": repr({k: {"source": "illustrative", "how": "external",
                                   "description": k} for k in
                               ("gamma", "r", "B", "Y", "a_min", *_INCOME)}),
        "CALIBRATION_TARGETS": repr({"liquid_wealth": {"moment": "wealth_to_income",
                                                       "data": 1.0, "tol": 1e-4,
                                                       "source": "illustrative"}}),
        "INTERNAL_CALIBRATION": "None",
        "EXPERIMENT": repr({"type": "monetary_shock", "size": 0.0025, "persistence": 1.0,
                            "horizon": 15, "dt": 0.25}),
    },
    "huggett": {
        **_COMMON,
        "PAPER_TITLE": '"Smoke test: Huggett economy"',
        "MODEL_CLASS": '"huggett"',
        "PARAMS": repr({"gamma": 2.0, "rho": 0.05, "B": 0.0, "Y": 1.0, "a_min": -1.0,
                        "a_max": 8.0, "n_a": 150, "z_low": 0.1, "z_high": 0.2,
                        "lam_lh": 1.2, "lam_hl": 1.2}),
        "PARAM_SOURCES": repr({k: {"source": "Achdou et al. (2022)", "how": "external",
                                   "description": k} for k in
                               ("gamma", "rho", "B", "Y", "a_min", "z_low", "z_high",
                                "lam_lh", "lam_hl")}),
        "CALIBRATION_TARGETS": "{}",
        "INTERNAL_CALIBRATION": "None",
        "UNTARGETED_MOMENTS": "{}",
        "EXPERIMENT": repr({"type": "comparative_statics", "param": "a_min",
                            "values": [-1.0, -0.75, -0.5], "label": "Borrowing limit"}),
    },
    "aiyagari": {
        **_COMMON,
        "PAPER_TITLE": '"Smoke test: Aiyagari economy"',
        "MODEL_CLASS": '"aiyagari"',
        "PARAMS": repr({"gamma": 2.0, "rho": 0.05, "alpha": 0.36, "delta": 0.08,
                        "a_min": 0.0, "a_max": 60.0, "n_a": 150, "z_low": 0.1,
                        "z_high": 0.2, "lam_lh": 1.2, "lam_hl": 1.2}),
        "PARAM_SOURCES": repr({k: {"source": "illustrative", "how": "external",
                                   "description": k} for k in
                               ("gamma", "rho", "alpha", "delta", "a_min", "z_low",
                                "z_high", "lam_lh", "lam_hl")}),
        "CALIBRATION_TARGETS": "{}",
        "INTERNAL_CALIBRATION": "None",
        "EXPERIMENT": repr({"type": "comparative_statics", "param": "rho",
                            "values": [0.045, 0.05, 0.055], "label": "Discount rate"}),
    },
}


def detect_model_class(idea: dict) -> str:
    """Best-effort mapping from a Stage 2 idea to a catalog key."""
    explicit = str(idea.get("model_class", "")).strip().lower()
    if explicit in MODEL_CLASSES:
        return explicit
    text = " ".join(str(idea.get(k, "")) for k in
                    ("model_class", "method", "title", "research_question", "mechanism")).lower()
    # Most specific first
    for key in ("hank_two_asset", "krusell_smith", "tank", "hank", "aiyagari", "huggett",
                "olg", "search_matching", "rank"):
        if any(kw in text for kw in MODEL_CLASSES[key]["keywords"]):
            return key
    return "hank"


def required_tests(model_class: str, experiment_type: str | None = None) -> list[str]:
    """Contract test ids. A HANK project whose experiment is comparative
    statics (no transition) is not asked for the sequence-space tests."""
    tests = list(MODEL_CLASSES.get(model_class, MODEL_CLASSES["hank"])["required_tests"])
    if model_class == "hank" and experiment_type not in (None, "monetary_shock"):
        drop = set(_SEQUENCE_SPACE) | {"analytic:tank_lambda0_equals_rank"}
        tests = [t for t in tests if t not in drop]
    return tests


def contract_markdown(model_class: str) -> str:
    """Human/agent-readable contract written to quality_reports/model_contract.md."""
    m = MODEL_CLASSES.get(model_class, MODEL_CLASSES["hank"])
    lines = [
        f"# Model contract: {m['name']} (`{model_class}`)",
        "",
        f"- Template solver available: {'yes (ha_core.py)' if m['template'] else 'NO -- custom solver required'}",
        f"- Markets that must clear: {', '.join(m['markets'])}",
        f"- Market made redundant by Walras' law (verify, do not impose): {m['walras_redundant']}",
        f"- Solution method: {m['solution']}",
        f"- Canonical references: {'; '.join(m['references'])}",
        f"- Typical calibration targets: {', '.join(m['targets'])}",
        "",
        "## Required tests (ids in data/model/equilibrium_tests.json)",
        "",
        "Every id below must be reported via `equilibrium_checks.TestReport`. HARD",
        "tests must pass; Stage 4 fails otherwise and no paper is written.",
        "",
    ]
    lines += [f"- `{t}`" for t in m["required_tests"]]
    lines += [
        "",
        "## Flow every macro project goes through",
        "",
        "1. `00_calibration.py`  spec + sources -> data/model/calibration.json",
        "2. `01_steady_state.py` stationary GE, internal calibration, steady-state tests",
        "3. `02_dynamics.py`     experiment (MIT shock in sequence space or counterfactual",
        "   steady states), Walras along the path, budget identities, determinacy",
        "4. `03_output.py`       tables (calibration, fit, tests, experiment), figures,",
        "   data/clean/main_results.csv, paper/tables/results_summary.md",
    ]
    return "\n".join(lines) + "\n"
