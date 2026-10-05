"""
00_calibration.py -- model specification and calibration (macro track).

Writes data/model/calibration.json, the single source of truth read by
01_steady_state.py, 02_dynamics.py and 03_output.py.

Supported out of the box (ha_core.py): huggett, aiyagari, hank (one-asset,
rigid prices). Other model classes need a custom solver that still reports
through equilibrium_checks.TestReport (see quality_reports/model_contract.md).
"""

import json
import sys
from pathlib import Path

# ════════════════════════════════════════════════════════════════════════════
# PROJECT-SPECIFIC VARIABLES (Claude fills these)
# ════════════════════════════════════════════════════════════════════════════

PAPER_TITLE = {{PAPER_TITLE}}

# "huggett" | "aiyagari" | "hank"
MODEL_CLASS = {{MODEL_CLASS}}

# Unit of time for all rates ("year" or "quarter")
TIME_UNIT = {{TIME_UNIT}}

# Model parameters. Keys used by ha_core:
#   gamma, rho (or r for hank), B, Y, a_min, a_max, n_a, grid_curvature,
#   z_low, z_high, lam_lh, lam_hl (or z + Lambda), alpha, delta (aiyagari),
#   calibrate ("rho" or "r", hank only)
PARAMS = {{PARAMS}}

# Where every parameter comes from: {"gamma": {"source": "Kaplan et al. (2018)",
#   "how": "external" | "internal" | "normalization", "description": "CRRA"}}
PARAM_SOURCES = {{PARAM_SOURCES}}

# Targeted moments: {"name": {"moment": key from ha_core.moments(), "data": value,
#   "tol": abs tolerance, "source": "SCF 2019", "level": "SOFT"|"HARD"}}
CALIBRATION_TARGETS = {{CALIBRATION_TARGETS}}

# Internal calibration (method of moments) or None:
#   {"free_params": {"z_low": [0.1, 0.9]}, "targets": ["avg_mpc"]}
INTERNAL_CALIBRATION = {{INTERNAL_CALIBRATION}}

# Untargeted moments used to validate the model (no tolerance):
#   {"name": {"moment": key, "data": value, "source": "..."}}
UNTARGETED_MOMENTS = {{UNTARGETED_MOMENTS}}

# Main experiment:
#   {"type": "monetary_shock", "size": 0.0025, "persistence": 1.0,
#    "horizon": 30, "dt": 0.25}                         (hank only)
#   {"type": "comparative_statics", "param": "a_min", "values": [...],
#    "label": "Borrowing limit"}                       (any class)
EXPERIMENT = {{EXPERIMENT}}

# Optional data files from Stage 1.5 used to compute target values
DATA_FILES = {{DATA_FILES}}


def update_targets_from_data(targets, data_files):
    """Optional hook: compute target values from DATA_FILES (edit freely)."""
    return targets


# ════════════════════════════════════════════════════════════════════════════
# FIXED CODE (does not change between projects)
# ════════════════════════════════════════════════════════════════════════════

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "data" / "model"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import equilibrium_checks as ec  # noqa: E402

REQUIRED = {
    "huggett": ["gamma", "rho", "a_min", "a_max", "n_a"],
    "aiyagari": ["gamma", "rho", "alpha", "delta", "a_min", "a_max", "n_a"],
    "hank": ["gamma", "r", "B", "a_min", "a_max", "n_a"],
}


def main():
    report = ec.TestReport(MODEL_DIR / "equilibrium_tests.json", MODEL_CLASS)
    report.reset_stage("calibration")

    if MODEL_CLASS not in REQUIRED:
        print(f"[!] MODEL_CLASS '{MODEL_CLASS}' has no template solver. Write a custom "
              "solver in 01/02 that reports the contract tests (model_contract.md).")
    missing = [k for k in REQUIRED.get(MODEL_CLASS, []) if k not in PARAMS]
    has_income = ({"z_low", "z_high", "lam_lh", "lam_hl"} <= PARAMS.keys()
                  or {"z", "Lambda"} <= PARAMS.keys())
    if not has_income:
        missing.append("income process (z_low, z_high, lam_lh, lam_hl) or (z, Lambda)")
    report.add(ec._result("calibration:required_params", ec.HARD, not missing,
                          len(missing), 0, "missing: " + ", ".join(missing) if missing
                          else "all required parameters present"), "calibration")

    unsourced = [k for k in PARAMS if k not in PARAM_SOURCES
                 and k not in ("n_a", "a_max", "grid_curvature", "calibrate", "bracket")]
    report.add(ec._result("calibration:parameters_sourced", ec.SOFT, not unsourced,
                          len(unsourced), 0, "no source for: " + ", ".join(unsourced)
                          if unsourced else "every economic parameter has a source"),
               "calibration")

    targets = update_targets_from_data(dict(CALIBRATION_TARGETS), DATA_FILES)
    bad_targets = [n for n, t in targets.items() if "data" not in t or "source" not in t]
    report.add(ec._result("calibration:targets_documented", ec.HARD, not bad_targets,
                          len(bad_targets), 0, "targets without data/source: "
                          + ", ".join(bad_targets) if bad_targets
                          else f"{len(targets)} targeted moments documented"), "calibration")

    if INTERNAL_CALIBRATION:
        unknown = [t for t in INTERNAL_CALIBRATION.get("targets", []) if t not in targets]
        n_free = len(INTERNAL_CALIBRATION.get("free_params", {}))
        n_tgt = len(INTERNAL_CALIBRATION.get("targets", []))
        ok = not unknown and n_tgt >= n_free > 0
        report.add(ec._result("calibration:internal_identified", ec.HARD, ok, n_tgt - n_free, 0,
                              f"{n_free} free parameters, {n_tgt} targets"
                              + (f"; unknown targets {unknown}" if unknown else "")),
                   "calibration")

    exp_type = (EXPERIMENT or {}).get("type")
    ok_exp = exp_type == "comparative_statics" or (exp_type == "monetary_shock"
                                                   and MODEL_CLASS == "hank")
    report.add(ec._result("calibration:experiment_supported", ec.SOFT, ok_exp, None, None,
                          f"experiment '{exp_type}' with model '{MODEL_CLASS}'"), "calibration")

    spec = {
        "paper_title": PAPER_TITLE,
        "model_class": MODEL_CLASS,
        "time_unit": TIME_UNIT,
        "params": PARAMS,
        "param_sources": PARAM_SOURCES,
        "calibration_targets": targets,
        "internal_calibration": INTERNAL_CALIBRATION,
        "untargeted_moments": UNTARGETED_MOMENTS,
        "experiment": EXPERIMENT,
        "data_files": DATA_FILES,
    }
    (MODEL_DIR / "calibration.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"[saved] {MODEL_DIR / 'calibration.json'}")
    report.save()
    report.exit_on_hard_failure("calibration")


if __name__ == "__main__":
    main()
