"""Tests for the quantitative-macro track (general equilibrium, HANK/TANK/RANK).

Run: python -m pytest tests/test_macro_track.py -q
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline" / "macro"))   # ha_core imports equilibrium_checks

import equilibrium_checks as ec  # noqa: E402
import ha_core as hc  # noqa: E402
from pipeline.macro import install_support_files, render_template, unfilled_placeholders  # noqa: E402
from pipeline.macro.model_catalog import (  # noqa: E402
    MACRO_DEFAULTS, MODEL_CLASSES, detect_model_class, required_tests)
from pipeline.templates import get_all_templates  # noqa: E402

HANK = dict(gamma=2.0, r=0.02, B=1.0, Y=1.0, a_min=0.0, a_max=20.0, n_a=150,
            z_low=0.5, z_high=1.5, lam_lh=0.5, lam_hl=0.5, calibrate="rho")
HUGGETT = dict(gamma=2.0, rho=0.05, B=0.0, Y=1.0, a_min=-1.0, a_max=8.0, n_a=150,
               z_low=0.1, z_high=0.2, lam_lh=1.2, lam_hl=1.2)
AIYAGARI = dict(gamma=2.0, rho=0.05, alpha=0.36, delta=0.08, a_min=0.0, a_max=60.0,
                n_a=150, z_low=0.1, z_high=0.2, lam_lh=1.2, lam_hl=1.2)


def _hard_failures(checks):
    return [c["id"] for c in checks if c["level"] == ec.HARD and not c["passed"]]


# ── equilibrium_checks ─────────────────────────────────────────────────────

def test_walras_and_market_clearing_flag_residuals():
    assert ec.walras_law("goods", 1e-12)["passed"]
    assert not ec.walras_law("goods", 1e-3)["passed"]
    assert ec.market_clearing("bonds", [1.0, 2.0], [1.0, 2.0])["passed"]
    assert not ec.market_clearing("bonds", [1.0, 2.1], [1.0, 2.0])["passed"]
    assert not ec.walras_law("goods", float("nan"))["passed"]


def test_generator_and_density_checks():
    good = np.array([[-1.0, 1.0], [2.0, -2.0]])
    bad = np.array([[-1.0, 1.5], [-0.5, 0.0]])
    assert ec.generator_rows_sum_zero(good)["passed"]
    assert not ec.generator_rows_sum_zero(bad)["passed"]
    assert ec.generator_offdiag_nonnegative(good)["passed"]
    assert not ec.generator_offdiag_nonnegative(bad)["passed"]
    assert ec.density_valid(np.array([0.25, 0.75]))["passed"]
    assert not ec.density_valid(np.array([0.5, 0.6]))["passed"]
    assert not ec.density_valid(np.array([-0.1, 1.1]))["passed"]


def test_theory_checks():
    assert ec.precautionary_savings(0.03, 0.05)["passed"]
    assert not ec.precautionary_savings(0.05, 0.05)["passed"]
    assert ec.blanchard_kahn(2, 2)["passed"] and not ec.blanchard_kahn(1, 2)["passed"]
    assert ec.euler_equation_errors([1e-5, 1e-6])["passed"]
    assert not ec.euler_equation_errors([1e-2])["passed"]
    res = ec.calibration_targets({"mpc": 0.21}, {"m": {"moment": "mpc", "data": 0.2,
                                                       "tol": 0.02, "source": "x"}})
    assert res[0]["passed"]
    res = ec.calibration_targets({}, {"m": {"moment": "mpc", "data": 0.2, "source": "x"}})
    assert not res[0]["passed"]


def test_report_roundtrip(tmp_path):
    rep = ec.TestReport(tmp_path / "t.json", "hank")
    rep.add([ec.walras_law("goods", 0.0), ec.walras_law("bonds", 1.0)], "steady_state")
    rep.add(ec.grid_robustness("r", 0.03, 0.0301), "steady_state")
    rep.save()
    again = ec.TestReport(tmp_path / "t.json", "hank")
    assert again.summary() == {"hard_total": 2, "hard_passed": 1, "soft_total": 1, "soft_passed": 1}
    assert [t["id"] for t in again.hard_failures()] == ["walras_law:bonds"]
    with pytest.raises(SystemExit):
        again.exit_on_hard_failure("steady_state")
    again.reset_stage("steady_state")
    assert again.summary()["hard_total"] == 0


# ── ha_core: steady states ─────────────────────────────────────────────────

@pytest.mark.parametrize("model,params", [("hank", HANK), ("huggett", HUGGETT),
                                          ("aiyagari", AIYAGARI)])
def test_steady_state_passes_all_hard_checks(model, params):
    ss = hc.steady_state(model, params, verbose=False)
    checks = hc.steady_state_checks(ss)
    assert _hard_failures(checks) == []
    assert ss["r"] < ss["rho"]
    mom = hc.moments(ss)
    assert 0.0 < mom["mpc"] < 1.0
    assert 0.0 <= mom["frac_constrained"] <= 1.0


def test_broken_income_normalization_breaks_walras():
    """If labor income does not aggregate to Y, the goods market cannot clear
    when the bond market does: Walras' law must catch it."""
    ss = hc.steady_state("hank", dict(HANK, normalize_income=False, z_low=0.5, z_high=2.0),
                         verbose=False)
    failed = _hard_failures(hc.steady_state_checks(ss))
    assert "walras_law:goods" in failed
    assert "identity:labor_income_normalization" in failed


def test_stationary_distribution_and_income_normalization():
    z, L = hc.two_state_income(0.2, 1.0, 0.3, 0.6)
    pi = hc.stationary_distribution(L)
    assert np.allclose(pi @ L, 0.0) and np.isclose(pi.sum(), 1.0)
    assert np.isclose(pi @ z, 1.0)


def test_grid_refinement_is_stable():
    ss = hc.steady_state("hank", HANK, verbose=False)
    check = hc.grid_robustness_check("hank", HANK, ss)
    assert check["value"] < 0.02          # < 2% relative change in rho


# ── ha_core: HANK transition (sequence space) ──────────────────────────────

@pytest.fixture(scope="module")
def hank_transition():
    ss = hc.steady_state("hank", HANK, verbose=False)
    dt, N = 0.25, 120          # 30 years: iMPC columns need a long horizon
    r_path, _ = hc.monetary_shock_path(ss, 0.0025, 1.0, N, dt)
    tr = hc.solve_transition_hank(ss, r_path, dt, verbose=False)
    return ss, tr, r_path, dt


def test_transition_clears_markets_and_walras_holds(hank_transition):
    ss, tr, _, _ = hank_transition
    checks = hc.transition_checks(ss, tr)
    assert _hard_failures(checks) == []
    assert np.max(np.abs(tr["A_end"] - ss["B"])) < 1e-6      # bond market (Walras)
    assert np.max(np.abs(tr["C"] - tr["Y"])) < 1e-7          # goods market (imposed)


def test_tightening_contracts_output_and_decomposition(hank_transition):
    ss, tr, r_path, dt = hank_transition
    assert tr["Y"][0] < ss["Y"]
    share = (tr["C_direct"][0] - ss["C"]) / (tr["C"][0] - ss["C"])
    assert 0.0 < share < 1.0             # direct effect is part, not all (KMV 2018)


def test_tank_nests_rank(hank_transition):
    ss, _, r_path, dt = hank_transition
    bm0 = hc.rank_tank_irfs(ss, r_path, dt, lam=0.0)
    assert np.allclose(bm0["tank"], bm0["rank"], atol=1e-14)
    bm = hc.rank_tank_irfs(ss, r_path, dt)
    assert 0.0 < bm["lambda"] < 1.0
    # RANK Euler equation: impact = -(1/gamma) * integral of dr
    expected = -(1 / ss["gamma"]) * np.sum((r_path - ss["r"]) * dt)
    assert np.isclose(bm0["rank"][0], expected)


def test_intertemporal_mpcs_sum_to_one_in_present_value(hank_transition):
    ss, tr, _, dt = hank_transition
    check = ec.intertemporal_mpcs_present_value(tr["Jac"], 1 / (1 - dt * ss["r"]))
    assert check["passed"], check["detail"]


# ── Templates end to end ────────────────────────────────────────────────────

def _run_project(base: Path, model: str) -> Path:
    proj = base / model
    sd = proj / "scripts" / "python"
    install_support_files(sd)
    for name, content in get_all_templates("macro").items():
        rendered = render_template(content, MACRO_DEFAULTS[model])
        assert unfilled_placeholders(rendered) == []
        (sd / name).write_text(rendered, encoding="utf-8")
    (proj / "strategy").mkdir(parents=True, exist_ok=True)
    (proj / "strategy" / "strategy_memo.md").write_text(
        f"Model memo ({model}): equilibrium definition, Walras' law (goods redundant), "
        "calibration table, monetary experiment.", encoding="utf-8")
    for name in ("00_calibration.py", "01_steady_state.py", "02_dynamics.py", "03_output.py"):
        r = subprocess.run([sys.executable, name], cwd=sd, capture_output=True, text=True)
        assert r.returncode == 0, f"{model}/{name}\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}"
    return proj


@pytest.fixture(scope="module")
def projects(tmp_path_factory):
    base = tmp_path_factory.mktemp("macro_projects")
    return {m: _run_project(base, m) for m in ("hank", "huggett")}


def test_templates_produce_handoff_outputs(projects):
    for model, proj in projects.items():
        for rel in ("data/model/equilibrium_tests.json", "data/clean/main_results.csv",
                    "paper/tables/results_summary.md", "paper/tables/tab_equilibrium_tests.tex",
                    "paper/tables/tab_calibration.tex", "paper/tables/tab_moments.tex",
                    "paper/tables/tab_experiment.tex"):
            assert (proj / rel).exists(), f"{model}: {rel}"
        rep = json.loads((proj / "data/model/equilibrium_tests.json").read_text())
        assert rep["summary"]["hard_passed"] == rep["summary"]["hard_total"] > 10
        for tex in (proj / "paper/tables").glob("*.tex"):
            assert "nan" not in tex.read_text().lower()


def test_macro_validator_passes_and_scores(projects):
    from pipeline.validators.macro_validator import model_validity_score, validate
    for model, proj in projects.items():
        vr = validate(proj / "scripts" / "python", proj)
        assert vr.hard_pass, [f"{c.name}: {c.detail}" for c in vr.hard_failures]
        assert model_validity_score(proj) >= 60


def test_macro_validator_detects_tampered_solver(projects, tmp_path):
    from pipeline.validators.macro_validator import validate
    proj = tmp_path / "tampered"
    shutil.copytree(projects["huggett"], proj)
    lib = proj / "scripts" / "python" / "equilibrium_checks.py"
    lib.write_text(lib.read_text().replace("resid < tol", "True"), encoding="utf-8")
    vr = validate(proj / "scripts" / "python", proj)
    assert "solver_library_intact:equilibrium_checks.py" in [c.name for c in vr.hard_failures]


def test_macro_validator_requires_contract_tests(projects, tmp_path):
    from pipeline.validators.macro_validator import validate
    proj = tmp_path / "incomplete"
    shutil.copytree(projects["hank"], proj)
    path = proj / "data/model/equilibrium_tests.json"
    rep = json.loads(path.read_text())
    rep["tests"] = [t for t in rep["tests"] if not t["id"].startswith("walras_law")]
    path.write_text(json.dumps(rep))
    names = [c.name for c in validate(proj / "scripts" / "python", proj).hard_failures]
    assert "contract_tests_reported" in names and "walras_law_verified" in names


def test_integration_validator_uses_model_checks(projects):
    from pipeline.validators.integration_validator import validate
    vr = validate(projects["hank"])
    names = [c.name for c in vr.checks]
    assert "main_script_exists" not in names            # no econometric 01_main.py needed
    assert "walras_in_memo" in names


def test_stage4_5_macro_audit(projects):
    from pipeline.stages.macro_stages.model_code import run_stage4_5
    state = {"project": "t", "stages": {}, "config": {"paper_type": "macro"}}
    proj = projects["hank"]
    (proj / "quality_reports").mkdir(exist_ok=True)
    import pipeline.stages.macro_stages.model_code as mc
    mc.save_state = lambda *a, **k: None
    state = run_stage4_5(proj, state)
    assert state["stages"]["stage4_5"]["n_critical"] == 0
    assert "Equilibrium & Calibration Audit" in (proj / "quality_reports/data_audit.md").read_text()


# ── Catalog, routing, models ───────────────────────────────────────────────

def test_catalog_contracts_and_detection():
    assert detect_model_class({"method": "Two-asset HANK with illiquid capital"}) == "hank_two_asset"
    assert detect_model_class({"title": "TANK model of fiscal multipliers"}) == "tank"
    assert detect_model_class({"model_class": "aiyagari"}) == "aiyagari"
    full = required_tests("hank", "monetary_shock")
    statics = required_tests("hank", "comparative_statics")
    assert "walras_law:assets_path" in full and "walras_law:assets_path" not in statics
    for key, meta in MODEL_CLASSES.items():
        assert meta["required_tests"], key
        assert meta["template"] == (key in MACRO_DEFAULTS), key


def test_paper_type_routing():
    from pipeline.paper_types import is_macro, stage_name
    macro = {"config": {"paper_type": "macro"}}
    emp = {"config": {}}
    assert is_macro(macro) and not is_macro(emp)
    assert stage_name(3.3, macro) == "Model Smoke Test"
    assert stage_name(3.3, emp) == "Quick Empirical Test"


def test_model_resolution(monkeypatch):
    from pipeline.config import resolve_model
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("PIPELINE_MODEL_OPUS", raising=False)
    assert resolve_model("opus") == "claude-opus-5-5"
    assert resolve_model("sonnet") == "claude-sonnet-5-5"
    assert resolve_model("haiku") == "claude-haiku-4-5"
    monkeypatch.setenv("PIPELINE_MODEL_OPUS", "claude-fable-5-1")
    assert resolve_model("opus") == "claude-fable-5-1"
    monkeypatch.delenv("PIPELINE_MODEL_OPUS")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    assert resolve_model("opus") == "opus"          # alias -> ANTHROPIC_DEFAULT_OPUS_MODEL


def test_claude_cmd_passes_effort_levels():
    from pipeline.claude_runner import _build_cmd
    cmd = _build_cmd(model="sonnet", effort="xhigh")
    assert cmd[cmd.index("--effort") + 1] == "xhigh"
    cmd = _build_cmd(model="sonnet", effort="bogus")
    assert cmd[cmd.index("--effort") + 1] == "medium"


# ── Stage 5.5 Lean (optional) ──────────────────────────────────────────────

def _lean_state(tmp_path, **cfg):
    return {"project": "demo", "stages": {"stage2_5": {"selected_idea": {
        "title": "Monetary transmission in HANK", "analytical_results": ["r < rho"]}}},
            "config": {"paper_type": "macro", **cfg}}


def test_lean_stage_is_optional(tmp_path, monkeypatch):
    import pipeline.stages.stage5_5_lean as lean
    monkeypatch.setattr(lean, "save_state", lambda *a, **k: None)
    state = lean.run(tmp_path, _lean_state(tmp_path))
    assert state["stages"]["stage5_5"]["status"] == "skipped"
    state = lean.run(tmp_path, _lean_state(tmp_path, lean="auto", lean_lib=str(tmp_path / "nope")))
    assert state["stages"]["stage5_5"]["status"] == "skipped"
    assert "not found" in state["stages"]["stage5_5"]["reason"]


def test_lean_stage_checks_then_copies_exactly(tmp_path, monkeypatch):
    import filecmp
    import pipeline.stages.stage5_5_lean as lean
    monkeypatch.setattr(lean, "save_state", lambda *a, **k: None)
    lib = tmp_path / "AppliedModelingLib"
    (lib / "scripts").mkdir(parents=True)
    (lib / "scripts" / "paper_contribution.py").write_text(
        "import sys\nprint('checking', sys.argv[2], sys.argv[3])\n"
        "print('FAIL: theorem T2 has sorry')\nsys.exit(1)\n", encoding="utf-8")
    folder = lib / "papers" / "PH26Demo"
    (folder / "Proofs").mkdir(parents=True)
    (folder / "Proofs" / "Main.lean").write_text("theorem t : True := trivial\n")
    (folder / "STATUS.md").write_text("partial: T2 blocked\n")
    (folder / ".gitignore").write_text("*.pdf\n")
    (folder / "source.pdf").write_bytes(b"%PDF-1.4 ignored")
    monkeypatch.setattr(lean, "LEAN_AGENT_CMD", f'"{sys.executable}" -c "print(1)"')
    project = tmp_path / "project"
    (project / "paper").mkdir(parents=True)
    (project / "paper" / "main.tex").write_text("\\documentclass{article}")
    export = tmp_path / "weekly"
    export.mkdir()
    state = lean.run(project, _lean_state(tmp_path, lean="auto", lean_lib=str(lib),
                                          lean_folder="PH26Demo", lean_export=str(export)))
    info = state["stages"]["stage5_5"]
    assert info["status"] == "completed" and info["check_rc"] == 1
    assert info["verdict"] == "FAILED/PARTIAL"
    for dst in (project / "lean", export / "lean"):
        cmp = filecmp.dircmp(folder, dst)
        assert not cmp.left_only and not cmp.right_only and not cmp.diff_files
        assert (dst / "source.pdf").exists() and (dst / ".gitignore").exists()
    check = (project / "quality_reports" / "lean_check.md").read_text()
    assert "theorem T2 has sorry" in check and "--fast" in check
    assert (export / "lean_check.md").exists()
    task = (project / "quality_reports" / "lean_task.md").read_text()
    assert "PH26Demo" in task and "r < rho" in task


# ── Stage 4 gate (agent simulated) ─────────────────────────────────────────

def _run_stage4_with_fake_agent(tmp_path, monkeypatch, model, overrides=None):
    import pipeline.stages.macro_stages.model_code as mc
    values = dict(MACRO_DEFAULTS[model], **(overrides or {}))

    def fake_agent(stage, issue, files, project_dir, script_results=None):
        assert "Walras" in issue and "contract" in issue.lower()
        sd = project_dir / "scripts" / "python"
        for name in ("00_calibration.py", "01_steady_state.py", "02_dynamics.py", "03_output.py"):
            (sd / name).write_text(render_template((sd / name).read_text(encoding="utf-8"), values),
                                   encoding="utf-8")
        (project_dir / "strategy" / "strategy_memo.md").write_text(
            "Equilibrium definition; Walras' law: goods market redundant; calibration table.")
        return True

    monkeypatch.setattr(mc, "request_manual_intervention", fake_agent)
    monkeypatch.setattr(mc, "save_state", lambda *a, **k: None)
    state = {"project": "p", "config": {"paper_type": "macro"},
             "stages": {"stage2_5": {"selected_idea": {"model_class": model}}}}
    return mc.run_stage4(tmp_path / "proj", state)


def test_stage4_gate_passes_valid_model(tmp_path, monkeypatch):
    state = _run_stage4_with_fake_agent(tmp_path, monkeypatch, "huggett")
    s4 = state["stages"]["stage4bc"]
    assert s4["status"] == "completed", s4["reason"]
    assert s4["validation_hard_pass"] and state["stages"]["stage4a"]["critic_score"] >= 60
    assert (tmp_path / "proj" / "quality_reports" / "model_contract.md").exists()


def test_stage4_gate_stops_on_hard_failure(tmp_path, monkeypatch):
    bad_target = repr({"liquid_wealth": {"moment": "wealth_to_income", "data": 5.0,
                                         "tol": 0.01, "source": "test", "level": "HARD"}})
    state = _run_stage4_with_fake_agent(tmp_path, monkeypatch, "hank",
                                        {"CALIBRATION_TARGETS": bad_target})
    s4 = state["stages"]["stage4bc"]
    assert s4["status"] == "failed"
    assert not s4["all_scripts_ok"]


# ── Journal-targeted literature search (OpenAlex mocked) ───────────────────

def test_journal_search_filters_and_ranks(monkeypatch, tmp_path):
    import pipeline.macro.literature as lit
    monkeypatch.setattr(lit, "_CACHE", tmp_path / "cache.json")
    calls = []

    def fake_get(path, params):
        calls.append((path, params))
        if path == "sources":
            return {"results": [{"id": "https://openalex.org/S999", "display_name":
                                 "Revista Estudios Economicos", "works_count": 37}]}
        loc = lambda sid: {"source": {"id": f"https://openalex.org/{sid}"}}  # noqa: E731
        return {"results": [
            {"title": "A field paper", "publication_year": 2020, "cited_by_count": 50,
             "authorships": [], "locations": [loc("S6711363")], "doi": None,
             "abstract_inverted_index": {"hank": [0]}},
            {"title": "A top-5 paper", "publication_year": 2018, "cited_by_count": 50,
             "authorships": [{"author": {"display_name": "G. Kaplan"}}],
             "locations": [loc("S2809516038"), loc("S23254222")],
             "doi": "https://doi.org/10.1257/x", "abstract_inverted_index": None},
            {"title": "Outside venue", "publication_year": 2021, "cited_by_count": 999,
             "authorships": [], "locations": [loc("S1")], "doi": None},
        ]}

    monkeypatch.setattr(lit, "_get", fake_get)
    papers = lit.search_journals("hank", extra_journals=["Revista Estudios Economicos"])
    works_filter = [p for path, p in calls if path == "works"][0]["filter"]
    assert "S23254222" in works_filter and "S999" in works_filter   # top-5 + custom journal
    assert [p["title"] for p in papers] == ["A top-5 paper", "A field paper"]
    assert papers[0]["venue_tier"] == "top5" and papers[0]["doi"] == "10.1257/x"
    assert lit.resolve_journal("Revista Estudios Economicos")[0] == "S999"   # cached


def test_literature_scopes_from_state():
    from pipeline.macro.literature import DEFAULT_SCOPES, scopes_from_state, venue_map
    assert scopes_from_state({"config": {}}) == (DEFAULT_SCOPES, [])
    scopes, extra = scopes_from_state({"config": {"lit_scope": "top5,preprints,bogus",
                                                  "journals": "A; B"}})
    assert scopes == ("top5", "preprints") and extra == ["A", "B"]
    assert len(venue_map(("top5",))) == 5
