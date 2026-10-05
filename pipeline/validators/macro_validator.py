"""Stage 4 validator for the macro track.

Objective checks on a model-based project: scripts ran, the solver library
is intact, every test in the model-class contract was reported, every HARD
equilibrium test passed, and the handoff outputs for Stage 5 exist.
"""

import hashlib
import json
from pathlib import Path

from . import CheckLevel, ValidationResult
from ..macro import MACRO_DIR, SUPPORT_FILES
from ..macro.model_catalog import MODEL_CLASSES, required_tests

EXPECTED_SCRIPTS = ["00_calibration.py", "01_steady_state.py", "02_dynamics.py", "03_output.py"]


def _sha(path: Path) -> str:
    """Content hash that ignores CRLF/LF differences (git autocrlf checkouts)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _reported(test_ids: set[str], required: str) -> bool:
    return required in test_ids or any(t.startswith(required + "@") for t in test_ids)


def validate(scripts_dir: Path, project_dir: Path, all_results: dict | None = None) -> ValidationResult:
    vr = ValidationResult()
    model_dir = project_dir / "data" / "model"

    for name in EXPECTED_SCRIPTS:
        vr.add(f"script_exists:{name}", CheckLevel.HARD, (scripts_dir / name).exists(),
               f"{name} {'found' if (scripts_dir / name).exists() else 'MISSING'}")
        if all_results is not None:
            res = all_results.get(name, {})
            vr.add(f"script_ran:{name}", CheckLevel.HARD, res.get("ok", False),
                   "ran OK" if res.get("ok") else f"FAILED: {str(res.get('stderr', ''))[-200:]}")

    tests_path = model_dir / "equilibrium_tests.json"
    if not tests_path.exists():
        vr.add("equilibrium_tests_reported", CheckLevel.HARD, False,
               "data/model/equilibrium_tests.json not found")
        return vr
    report = json.loads(tests_path.read_text(encoding="utf-8"))
    model_class = report.get("model_class", "unknown")
    tests = report.get("tests", [])
    ids = {t["id"] for t in tests}

    if MODEL_CLASSES.get(model_class, {}).get("template"):
        for name in SUPPORT_FILES:
            local = scripts_dir / name
            same = local.exists() and _sha(local) == _sha(MACRO_DIR / name)
            vr.add(f"solver_library_intact:{name}", CheckLevel.HARD, same,
                   "identical to pipeline/macro copy" if same
                   else "modified or missing -- solver/test code must not be edited per project")

    exp_type = None
    exp_path = model_dir / "experiment_summary.json"
    if exp_path.exists():
        exp_type = json.loads(exp_path.read_text(encoding="utf-8")).get("experiment")
    missing = [t for t in required_tests(model_class, exp_type) if not _reported(ids, t)]
    vr.add("contract_tests_reported", CheckLevel.HARD, not missing,
           f"model class '{model_class}': all contract tests reported" if not missing
           else f"missing contract tests: {', '.join(missing)}")

    hard_failed = [t["id"] for t in tests if t["level"] == "HARD" and not t["passed"]]
    vr.add("equilibrium_hard_tests_pass", CheckLevel.HARD, not hard_failed,
           f"{len([t for t in tests if t['level'] == 'HARD'])} HARD tests pass" if not hard_failed
           else f"HARD failures: {', '.join(hard_failed[:8])}")

    walras = [t for t in tests if t["id"].startswith("walras_law")]
    vr.add("walras_law_verified", CheckLevel.HARD, bool(walras) and all(t["passed"] for t in walras),
           f"{len(walras)} Walras' law checks" if walras else "no Walras' law check reported")

    soft = [t for t in tests if t["level"] == "SOFT"]
    soft_failed = [t["id"] for t in soft if not t["passed"]]
    vr.add("equilibrium_soft_tests", CheckLevel.SOFT, not soft_failed,
           f"{len(soft) - len(soft_failed)}/{len(soft)} SOFT tests pass"
           + (f"; failed: {', '.join(soft_failed[:6])}" if soft_failed else ""))

    calib = [t for t in tests if t["id"].startswith("calibration_target:")]
    calib_failed = [t["id"] for t in calib if not t["passed"]]
    vr.add("calibration_targets_matched", CheckLevel.SOFT, not calib_failed,
           f"{len(calib) - len(calib_failed)}/{len(calib)} targeted moments within tolerance")

    for rel, level in (("data/model/calibration.json", CheckLevel.HARD),
                       ("data/model/steady_state.json", CheckLevel.HARD),
                       ("data/model/experiment_summary.json", CheckLevel.HARD),
                       ("data/clean/main_results.csv", CheckLevel.HARD),
                       ("paper/tables/results_summary.md", CheckLevel.HARD),
                       ("paper/tables/tab_equilibrium_tests.tex", CheckLevel.SOFT),
                       ("paper/tables/tab_calibration.tex", CheckLevel.SOFT),
                       ("paper/tables/tab_moments.tex", CheckLevel.SOFT),
                       ("strategy/strategy_memo.md", CheckLevel.SOFT)):
        exists = (project_dir / rel).exists()
        vr.add(f"output_exists:{rel}", level, exists, "found" if exists else "MISSING")

    figs = list((project_dir / "paper" / "figures").glob("*.png"))
    vr.add("figures_generated", CheckLevel.SOFT, len(figs) >= 2, f"{len(figs)} figures")

    memo = project_dir / "strategy" / "strategy_memo.md"
    if memo.exists():
        text = memo.read_text(encoding="utf-8").lower()
        has = all(k in text for k in ("equilibrium", "walras", "calibrat"))
        vr.add("model_memo_complete", CheckLevel.SOFT, has,
               "memo defines equilibrium, Walras' law and calibration" if has
               else "memo should define the equilibrium, state Walras' law and the calibration")
    return vr


def model_validity_score(project_dir: Path) -> int:
    """0-100 score that replaces 'identification' in the macro quality weights.

    60 if every HARD equilibrium test passes (else 30), plus up to 25 for the
    SOFT pass rate and up to 15 for calibration targets within tolerance.
    """
    path = project_dir / "data" / "model" / "equilibrium_tests.json"
    if not path.exists():
        return 0
    tests = json.loads(path.read_text(encoding="utf-8")).get("tests", [])
    hard = [t for t in tests if t["level"] == "HARD"]
    soft = [t for t in tests if t["level"] == "SOFT"]
    calib = [t for t in tests if t["id"].startswith("calibration_target:")]
    score = 60 if hard and all(t["passed"] for t in hard) else 30
    if soft:
        score += round(25 * sum(t["passed"] for t in soft) / len(soft))
    score += round(15 * (sum(t["passed"] for t in calib) / len(calib))) if calib else 8
    return min(100, score)
