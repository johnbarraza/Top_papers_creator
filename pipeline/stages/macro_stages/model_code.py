"""Macro track — Stage 4 (model memo, calibration, solution code, equilibrium
tests) and Stage 4.5 (equilibrium & calibration audit).

Gate: Stage 4 FAILS (pipeline stops) if any HARD equilibrium test fails or
the model-class contract is not fully reported. A paper is never written on
a model whose markets do not clear.
"""

import json
from datetime import datetime
from pathlib import Path

from ...claude_runner import request_manual_intervention
from ...macro import MACRO_DIR, SUPPORT_FILES, install_support_files, unfilled_placeholders
from ...macro.model_catalog import MODEL_CLASSES, contract_markdown, detect_model_class
from ...python_runner import run_with_retry
from ...state import save_state
from ...validators.macro_validator import EXPECTED_SCRIPTS, model_validity_score, validate


def _model_class(state: dict) -> str:
    spec = state["stages"].get("stage3_5", {}).get("approved_strategy") or {}
    if spec.get("model_class"):
        return spec["model_class"]
    return detect_model_class(state["stages"].get("stage2_5", {}).get("selected_idea", {}) or {})


def _needs_fill(path: Path) -> bool:
    return not path.exists() or bool(unfilled_placeholders(path.read_text(encoding="utf-8")))


def _intervention_text(project_dir: Path, state: dict, mc: str, missing: list[str]) -> str:
    meta = MODEL_CLASSES[mc]
    s1 = state["stages"].get("stage1", {})
    series = state["stages"].get("stage1_5", {}).get("calibration_series", [])
    checklist = project_dir / "strategy" / "referee_checklist.md"
    musts = []
    if checklist.exists():
        in_must = False
        for line in checklist.read_text(encoding="utf-8").splitlines():
            if line.startswith("## MUST-HAVE"):
                in_must = True
                continue
            if in_must and line.startswith("## "):
                break
            if in_must and line.startswith("- "):
                musts.append(line[2:])
    plan = "\n".join(f"  - {m.get('moment')}: {m.get('typical_value')} ({m.get('source')}, "
                     f"{m.get('role')})" for m in s1.get("calibration_plan", []))
    series_txt = "\n".join(f"  - {x.get('source')} {x.get('series')}: {x.get('local_path')}"
                           for x in series)

    if meta["template"]:
        code_block = (
            "*** TEMPLATE SOLVER (ha_core.py) — FILL, DO NOT REWRITE ***\n"
            "scripts/python/ contains 00_calibration.py, 01_steady_state.py, 02_dynamics.py,\n"
            "03_output.py plus ha_core.py and equilibrium_checks.py (the solver and the test\n"
            "library, copied verbatim from pipeline/macro/).\n"
            "  1. Replace every {{PLACEHOLDER}} above the 'FIXED CODE' line. All project\n"
            "     choices live in 00_calibration.py: MODEL_CLASS, PARAMS, PARAM_SOURCES,\n"
            "     CALIBRATION_TARGETS (with real sources), INTERNAL_CALIBRATION,\n"
            "     UNTARGETED_MOMENTS, EXPERIMENT, DATA_FILES. You may implement\n"
            "     update_targets_from_data() to compute targets from the downloaded series.\n"
            "  2. NEVER edit ha_core.py, equilibrium_checks.py or code below 'FIXED CODE'.\n"
            "     Stage 4 hashes the library and fails the project if it was modified.\n"
            "  3. If the experiment needs features the template lacks (e.g. fiscal shock,\n"
            "     another MIT shock), add a NEW script 02b_<name>.py that imports ha_core and\n"
            "     reports through equilibrium_checks.TestReport (stage='dynamics_extra').\n"
        )
    else:
        code_block = (
            f"*** CUSTOM SOLVER REQUIRED ('{mc}' has no template) ***\n"
            "Write 00_calibration.py, 01_steady_state.py, 02_dynamics.py, 03_output.py\n"
            "yourself. You MUST import equilibrium_checks (already in scripts/python/) and\n"
            "report every contract test id listed in quality_reports/model_contract.md via\n"
            "TestReport(data/model/equilibrium_tests.json, model_class). Produce the same\n"
            "outputs as the template: data/model/{calibration,steady_state,experiment_summary}\n"
            ".json, data/clean/main_results.csv, paper/tables/results_summary.md,\n"
            "tab_calibration.tex, tab_moments.tex, tab_equilibrium_tests.tex, figures.\n"
            "Use validated packages where possible (e.g. sequence-jacobian for SSJ).\n"
        )

    return (
        f"Stage 4 (macro) needs manual intervention. Missing: {', '.join(missing)}. "
        "Tell Claude: 'revisa el pipeline'.\n\n"
        f"MODEL CLASS: {meta['name']} ({mc}). Approved spec: strategy/model_spec.json.\n"
        "Contract (tests that must be reported/pass): quality_reports/model_contract.md\n\n"
        "STEP 1 — write strategy/strategy_memo.md (the MODEL MEMO):\n"
        "  (a) environment: agents, preferences, technology, frictions, shocks\n"
        "  (b) equilibrium definition: prices, markets that clear, government budget\n"
        "  (c) Walras' law: which market is redundant and how the code verifies it\n"
        "  (d) calibration table: each parameter -> value, external/internal, source;\n"
        "      each internal parameter -> the moment that pins it\n"
        "  (e) solution algorithm and numerical tolerances; (f) experiments;\n"
        "  (g) analytical results (propositions) and the benchmark (TANK/RANK) comparison\n\n"
        "STEP 2 — scripts:\n" + code_block + "\n"
        "STEP 3 — run 00 -> 01 -> 02 -> 03 in order from scripts/python/. Each script exits\n"
        "with code 1 if a HARD equilibrium test fails: FIX THE MODEL/CALIBRATION, never the\n"
        "test. SOFT failures are fine but must be discussed in the paper.\n\n"
        "STEP 4 — write quality_reports/intervention_done.json to resume.\n\n"
        "CALIBRATION DATA PLAN (Stage 1):\n" + (plan or "  (none)") + "\n"
        "DOWNLOADED SERIES (Stage 1.5):\n" + (series_txt or "  (none)") + "\n"
        + ("\nREFEREE CHECKLIST — MUST items:\n" + "\n".join(f"  {i + 1}. {m[:220]}"
                                                       for i, m in enumerate(musts)) + "\n"
           if musts else "")
    )


def _execute(scripts_dir: Path) -> dict:
    results = {}
    for name in EXPECTED_SCRIPTS + sorted(p.name for p in scripts_dir.glob("02[a-z]_*.py")):
        path = scripts_dir / name
        if not path.exists():
            results[name] = {"ok": False, "stderr": "missing"}
            continue
        # No LLM auto-patching here: a HARD equilibrium failure must be fixed in
        # the model or calibration, never by editing the test code.
        results[name] = run_with_retry(path, cwd=scripts_dir, max_retries=0)
        if not results[name]["ok"]:
            print(f"  [4] {name} failed — later scripts depend on it; stopping.")
            break
    return results


def run_stage4(project_dir: Path, state: dict) -> dict:
    mc = _model_class(state)
    meta = MODEL_CLASSES[mc]
    scripts_dir = project_dir / "scripts" / "python"
    strategy_dir = project_dir / "strategy"
    qr = project_dir / "quality_reports"
    for d in (scripts_dir, strategy_dir, qr, project_dir / "data" / "model",
              project_dir / "data" / "clean", project_dir / "paper" / "tables",
              project_dir / "paper" / "figures"):
        d.mkdir(parents=True, exist_ok=True)
    (qr / "model_contract.md").write_text(contract_markdown(mc), encoding="utf-8")
    install_support_files(scripts_dir)

    if meta["template"]:
        from ...templates import get_all_templates
        for name, content in get_all_templates("macro").items():
            target = scripts_dir / name
            if not target.exists():
                target.write_text(content, encoding="utf-8")
                print(f"  [template] macro/{name} -> scripts/python/{name}")

    missing = []
    if not (strategy_dir / "strategy_memo.md").exists():
        missing.append("strategy_memo.md (model memo)")
    unfilled = [n for n in EXPECTED_SCRIPTS if _needs_fill(scripts_dir / n)]
    if unfilled:
        missing.append("filled scripts: " + ", ".join(unfilled))
    if not (project_dir / "data" / "model" / "equilibrium_tests.json").exists():
        missing.append("executed model (data/model/equilibrium_tests.json)")

    if missing:
        request_manual_intervention(
            stage="stage4_macro",
            issue=_intervention_text(project_dir, state, mc, missing),
            files=[str(strategy_dir), str(scripts_dir), str(qr / "model_contract.md")],
            project_dir=project_dir,
        )
        # The agent may have touched the library; restore it so the hash check is meaningful
        if meta["template"]:
            for name in SUPPORT_FILES:
                local = scripts_dir / name
                if local.read_text(encoding="utf-8") != (MACRO_DIR / name).read_text(encoding="utf-8"):
                    print(f"  [integrity] {name} was modified — restored; results re-run.")
                    install_support_files(scripts_dir)
                    (project_dir / "data" / "model" / "equilibrium_tests.json").unlink(missing_ok=True)
                    break

    if meta["template"]:
        for name in EXPECTED_SCRIPTS:
            text = (scripts_dir / name).read_text(encoding="utf-8") if (scripts_dir / name).exists() else ""
            if "FIXED CODE" not in text:
                print(f"  [TEMPLATE VIOLATION] {name}: 'FIXED CODE' section removed.")

    print(f"\n  [4] Executing model scripts in order (re-run for a clean audit trail)...")
    (project_dir / "data" / "model" / "equilibrium_tests.json").unlink(missing_ok=True)
    results = _execute(scripts_dir)
    all_ok = all(r.get("ok") for r in results.values())

    vr = validate(scripts_dir, project_dir, results)
    print(f"  [4] {vr.format_for_log()}")
    counts = vr.summary_counts
    code_score = (60 if vr.hard_pass else 40) + int(
        40 * counts["soft_passed"] / max(counts["soft_total"], 1))
    validity = model_validity_score(project_dir)
    now = datetime.now().isoformat()
    state["stages"]["stage4a"] = {
        "status": "completed", "strategy_dir": str(strategy_dir),
        "critic_score": validity, "score_basis": "model validity (equilibrium tests + calibration)",
        "completed_at": now,
    }
    state["stages"]["stage4bc"] = {
        "status": "completed" if (vr.hard_pass and all_ok) else "failed",
        "reason": "" if vr.hard_pass and all_ok else
                  "; ".join(c.detail for c in vr.hard_failures)[:600] or "a script failed",
        "scripts_dir": str(scripts_dir),
        "scripts": list(results),
        "all_scripts_ok": all_ok,
        "critic_score": min(100, code_score),
        "validation": counts,
        "validation_hard_pass": vr.hard_pass,
        "model_class": mc,
        "completed_at": now,
    }
    print(f"  [4] Model validity {validity}/100, code {min(100, code_score)}/100")
    state["current_stage"] = 4
    save_state(project_dir, state)
    return state


def run_stage4_5(project_dir: Path, state: dict) -> dict:
    model_dir = project_dir / "data" / "model"
    tests_path = model_dir / "equilibrium_tests.json"
    if not tests_path.exists():
        print("  [4.5] No equilibrium_tests.json — run Stage 4 first.")
        state["stages"]["stage4_5"] = {"status": "completed", "n_critical": 1,
                                       "reason": "no_model_outputs"}
        save_state(project_dir, state)
        return state
    rep = json.loads(tests_path.read_text(encoding="utf-8"))
    tests = rep.get("tests", [])
    ss = json.loads((model_dir / "steady_state.json").read_text(encoding="utf-8")) \
        if (model_dir / "steady_state.json").exists() else {}
    spec = json.loads((model_dir / "calibration_final.json").read_text(encoding="utf-8")) \
        if (model_dir / "calibration_final.json").exists() else {}
    mom = ss.get("moments", {})

    flags = []
    for t in tests:
        if not t["passed"]:
            sev = "CRITICAL" if t["level"] == "HARD" else "WARNING"
            flags.append({"severity": sev, "check": t["id"], "detail": t["detail"]})
    for name, u in (spec.get("untargeted_moments") or {}).items():
        model, data = mom.get(u.get("moment")), u.get("data")
        if isinstance(model, (int, float)) and isinstance(data, (int, float)) and data:
            gap = abs(model - data) / abs(data)
            if gap > 0.5:
                flags.append({"severity": "WARNING", "check": f"untargeted:{name}",
                              "detail": f"model {model:.3f} vs data {data:.3f} "
                                        f"({gap:.0%} gap) — discuss as a limitation"})
    if mom.get("frac_constrained", 0) > 0.5:
        flags.append({"severity": "WARNING", "check": "share_constrained",
                      "detail": f"{mom['frac_constrained']:.0%} of households at the borrowing "
                                "limit — check a_min and income risk"})
    if isinstance(mom.get("mpc"), float) and not (0.0 < mom["mpc"] < 1.0):
        flags.append({"severity": "CRITICAL", "check": "mpc_range",
                      "detail": f"average MPC {mom['mpc']:.3f} outside (0, 1)"})

    n_crit = sum(f["severity"] == "CRITICAL" for f in flags)
    s = rep.get("summary", {})
    lines = ["# Data Audit Report — Equilibrium & Calibration Audit (macro)", "",
             f"Model class: {rep.get('model_class')}",
             f"Equilibrium tests: HARD {s.get('hard_passed')}/{s.get('hard_total')}, "
             f"SOFT {s.get('soft_passed')}/{s.get('soft_total')}", "",
             f"## Flags ({n_crit} critical, {len(flags) - n_crit} warnings)"]
    lines += [f"- [{f['severity']}] {f['check']}: {f['detail']}" for f in flags] or ["- none"]
    lines += ["", "## Steady-state moments"] + [f"- {k}: {v}" for k, v in mom.items()]
    out = project_dir / "quality_reports" / "data_audit.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"  [4.5] {n_crit} critical, {len(flags) - n_crit} warnings -> {out}")
    state["stages"]["stage4_5"] = {"status": "completed", "n_critical": n_crit,
                                   "n_warnings": len(flags) - n_crit, "flags": flags[:20],
                                   "report": str(out), "completed_at": datetime.now().isoformat()}
    save_state(project_dir, state)
    return state
