"""Macro track — Stage 3 idea text, 3.3 model smoke test, 3.5 human model
specification review, 3.7 macro referee preview.
"""

import json
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path

from ...claude_runner import run_claude_parallel
from ...config import get_profile
from ...json_utils import extract_json, smart_truncate
from ...macro import install_support_files, render_template
from ...macro.model_catalog import (
    MACRO_DEFAULTS,
    MODEL_CLASSES,
    contract_markdown,
    detect_model_class,
)
from ...state import save_state


def _selected(state: dict) -> dict:
    return state["stages"].get("stage2_5", {}).get("selected_idea", {}) or {}


# ── Stage 3: idea text for the evaluation pipeline ─────────────────────────

def stage3_idea_text(idea: dict, state: dict) -> str:
    mc = detect_model_class(idea)
    meta = MODEL_CLASSES[mc]
    plan = state["stages"].get("stage1", {}).get("calibration_plan", [])
    moments = "\n".join(f"- {m.get('moment')}: {m.get('typical_value')} ({m.get('source')}; "
                        f"{m.get('role')})" for m in plan) or "(none)"
    js = lambda x: json.dumps(x, ensure_ascii=False) if x else "N/A"  # noqa: E731
    return f"""RESEARCH IDEA SUBMISSION
========================

PAPER TYPE: Quantitative macroeconomics (model-based, general equilibrium)

IDEA TITLE:
{idea.get('title', 'Untitled')}

RESEARCH QUESTION:
{idea.get('research_question', 'N/A')}

MECHANISM:
{idea.get('mechanism', idea.get('pitch', 'N/A'))}

MODEL CLASS: {meta['name']} (template solver: {'yes' if meta['template'] else 'no, custom'})
ENVIRONMENT: {idea.get('environment', 'N/A')}
EQUILIBRIUM: {idea.get('equilibrium', 'N/A')}
MARKETS THAT MUST CLEAR: {', '.join(meta['markets'])}
MARKET REDUNDANT BY WALRAS' LAW: {idea.get('walras_redundant_market', meta['walras_redundant'])}
SOLUTION METHOD: {idea.get('method', meta['solution'])}

ANALYTICAL RESULTS CLAIMED: {js(idea.get('analytical_results'))}
TARGETED MOMENTS: {js(idea.get('targeted_moments'))}
UNTARGETED MOMENTS: {js(idea.get('untargeted_moments'))}
MAIN EXPERIMENT: {js(idea.get('experiment'))}
ANTICIPATED REFEREE OBJECTION: {idea.get('referee_objection', 'N/A')}

CALIBRATION DATA PLAN (Stage 1):
{moments}

EQUILIBRIUM TESTS THE CODE WILL HAVE TO PASS:
{', '.join(meta['required_tests'])}

*** MODEL ASSESSMENT (MANDATORY) ***
There is no causal identification strategy in this paper. Evaluate instead:
1. Is the mechanism sharp, and does the model isolate it (vs a TANK/RANK benchmark)?
2. Is the equilibrium fully specified (prices, markets, government budget, Walras' law)?
3. Do credible data moments discipline the parameters that drive the result?
4. Is the solution method feasible and verifiable with the tests above?
A model whose answer is mechanically pinned by calibration should not score above 6/10.
"""


# ── Stage 3.3: model smoke test ────────────────────────────────────────────

def run_stage3_3(project_dir: Path, state: dict) -> dict:
    idea = _selected(state)
    mc = detect_model_class(idea)
    meta = MODEL_CLASSES[mc]
    qr = project_dir / "quality_reports"
    qr.mkdir(exist_ok=True)
    (qr / "model_contract.md").write_text(contract_markdown(mc), encoding="utf-8")
    print(f"  [3.3] Model class: {meta['name']} -> contract in quality_reports/model_contract.md")

    result = {"status": "completed", "model_class": mc, "template_supported": meta["template"],
              "completed_at": datetime.now().isoformat()}
    if not meta["template"]:
        print("  [3.3] No template solver for this class: Stage 4 will require a custom "
              "solver that reports the contract tests. Smoke test skipped.")
        result.update(smoke_passed=None, action="proceed_custom_solver")
        state["stages"]["stage3_3"] = result
        save_state(project_dir, state)
        return state

    from ...templates import get_all_templates
    smoke = qr / "smoke_test"
    shutil.rmtree(smoke, ignore_errors=True)
    sd = smoke / "scripts" / "python"
    install_support_files(sd)
    for name, content in get_all_templates("macro").items():
        (sd / name).write_text(render_template(content, MACRO_DEFAULTS[mc]), encoding="utf-8")

    log = []
    ok = True
    for name in ("00_calibration.py", "01_steady_state.py", "02_dynamics.py"):
        r = subprocess.run([sys.executable, name], cwd=sd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
        log.append(f"## {name} (rc={r.returncode})\n{r.stdout[-3000:]}\n{r.stderr[-2000:]}")
        print(f"  [3.3] {name}: {'OK' if r.returncode == 0 else 'FAILED'}")
        if r.returncode != 0:
            ok = False
            break
    (qr / "smoke_test.md").write_text("# Model smoke test\n\n" + "\n".join(log), encoding="utf-8")
    summary = {}
    rep = smoke / "data" / "model" / "equilibrium_tests.json"
    if rep.exists():
        summary = json.loads(rep.read_text(encoding="utf-8")).get("summary", {})
    print(f"  [3.3] Smoke test {'PASSED' if ok else 'FAILED'}: {summary}")
    if not ok:
        print("  [3.3] The solver toolchain fails on the default calibration -- check numpy/"
              "scipy and quality_reports/smoke_test.md before Stage 4.")
    result.update(smoke_passed=ok, smoke_summary=summary,
                  action="proceed" if ok else "proceed_with_warning")
    state["stages"]["stage3_3"] = result
    save_state(project_dir, state)
    return state


# ── Stage 3.5: model specification review (human) ──────────────────────────

def _model_spec(state: dict) -> dict:
    idea = _selected(state)
    mc = detect_model_class(idea)
    meta = MODEL_CLASSES[mc]
    verdict = state["stages"].get("stage3", {}).get("result", {})
    return {
        "title": idea.get("title"),
        "research_question": idea.get("research_question"),
        "mechanism": idea.get("mechanism"),
        "model_class": mc,
        "model_name": meta["name"],
        "template_solver": meta["template"],
        "environment": idea.get("environment"),
        "equilibrium": idea.get("equilibrium"),
        "markets": meta["markets"],
        "walras_redundant_market": idea.get("walras_redundant_market", meta["walras_redundant"]),
        "solution_method": meta["solution"],
        "targeted_moments": idea.get("targeted_moments", []),
        "untargeted_moments": idea.get("untargeted_moments", []),
        "experiment": idea.get("experiment", {}),
        "analytical_results": idea.get("analytical_results", []),
        "required_tests": meta["required_tests"],
        "validation_score": verdict.get("final_score"),
        "recommended_changes": verdict.get("recommended_changes", []),
    }


def run_stage3_5(project_dir: Path, state: dict) -> dict:
    spec = _model_spec(state)
    print("\nSTAGE 3.5 - MODEL SPECIFICATION REVIEW (human checkpoint)\n")
    for k in ("title", "research_question", "mechanism", "model_name", "environment",
              "equilibrium", "walras_redundant_market", "solution_method"):
        if spec.get(k):
            print(textwrap.fill(str(spec[k]), 76, initial_indent=f"  {k}: ",
                                subsequent_indent="      "))
    print(f"  markets: {', '.join(spec['markets'])}")
    print(f"  targeted moments: {[m.get('moment') for m in spec['targeted_moments']]}")
    print(f"  experiment: {spec['experiment']}")
    print(f"  validation score (Stage 3): {spec['validation_score']}")
    for c in spec["recommended_changes"][:5]:
        print(f"  - recommended: {c}")
    if not spec["template_solver"]:
        print("  [!] Custom solver required (no template for this class).")
    print("\n  APPROVE | REFORMULATE | REJECT")
    print("\a", end="", flush=True)
    notes = ""
    while True:
        try:
            choice = input("\n>> ").strip().upper()
        except EOFError:
            choice = "APPROVE"
            print("  [auto] No interactive input: APPROVE")
        if choice in ("APPROVE", "REJECT"):
            break
        if choice == "REFORMULATE":
            print("  Enter changes to the model (empty line to finish):")
            lines = []
            while True:
                line = input("  | ")
                if not line:
                    break
                lines.append(line)
            notes = "\n".join(lines)
            break
        print("  Type APPROVE, REFORMULATE or REJECT.")
    action = "APPROVE" if choice == "REFORMULATE" else choice
    spec["user_notes"] = notes
    strategy_dir = project_dir / "strategy"
    strategy_dir.mkdir(exist_ok=True)
    (strategy_dir / "model_spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    (project_dir / "approved_strategy.md").write_text(
        "# Approved model specification\n\n```json\n" + json.dumps(spec, indent=2) + "\n```\n",
        encoding="utf-8")
    state["stages"]["stage3_5"] = {
        "status": "completed", "action": action, "approved_strategy": spec,
        "reformulated": bool(notes), "completed_at": datetime.now().isoformat(),
    }
    state["current_stage"] = 3.5
    save_state(project_dir, state)
    return state


# ── Stage 3.7: macro referee preview ───────────────────────────────────────

_JSON_SPEC = """Output a JSON block:
```json
{
  "code_requirements": [
    {"category": "equilibrium|calibration|computation|experiment|presentation|pitfall",
     "requirement": "...", "priority": "MUST|SHOULD|NICE"}
  ],
  "tables_required": ["..."],
  "figures_required": ["..."],
  "must_not_claim": ["..."]
}
```"""


def run_stage3_7(project_dir: Path, state: dict) -> dict:
    if state["stages"].get("stage3_7", {}).get("status") == "completed":
        print("  [3.7] Already completed — skipping.")
        return state
    spec = state["stages"].get("stage3_5", {}).get("approved_strategy") or _model_spec(state)
    ctx = smart_truncate(json.dumps(spec, indent=2), 6000)

    theory = f"""You are a referee for a top macro journal (theory/quantitative side)
reviewing a MODEL PROPOSAL, not a finished paper. Produce a CONCRETE checklist of what
the model code and paper must contain to survive review.

{ctx}

Focus on: (1) is the mechanism isolated (compare with TANK/RANK; decompose direct vs
indirect effects); (2) equilibrium definition and accounting (government budget, profits,
resource constraint, which market is dropped by Walras' law and verified numerically);
(3) calibration: which moments pin which parameters, untargeted moments for validation,
sensitivity to the parameters that drive the answer; (4) experiments and counterfactuals;
(5) what the paper MUST NOT claim (e.g. causal/empirical claims; welfare without a welfare
criterion; results that hold only at one calibration).

{_JSON_SPEC}
"""
    computation = f"""You are a computational-economics referee (finite-difference HJB-KFE,
sequence-space Jacobians, perturbation). Review this MODEL PROPOSAL and list what the code
must implement and report.

{ctx}

Always require (MUST) unless clearly inapplicable:
- HJB convergence; upwind monotone generator (rows sum to 0, off-diagonals >= 0);
  KFE density non-negative with mass 1; state constraints at the grid bounds
- market clearing of every imposed market AND Walras' law on the omitted market,
  in steady state and along every transition path
- household budget identity along transitions; mass conservation
- r < rho for incomplete-markets steady states; determinacy (Blanchard-Kahn or a
  well-conditioned sequence-space Jacobian)
- discretization robustness (grid refinement) and horizon robustness for transitions
- nesting tests: closed forms the code must reproduce (TANK lambda=0 equals RANK, etc.)
- a table of all equilibrium tests in the appendix
Add model-specific requirements for this proposal.

{_JSON_SPEC}
"""
    p = get_profile("macro_referee")
    strategy_dir = project_dir / "strategy"
    strategy_dir.mkdir(exist_ok=True)
    responses = run_claude_parallel([
        {"prompt": theory, "model": p["model"], "effort": p["effort"], "allowed_tools": [],
         "output_file": strategy_dir / "referee_preview_domain.md", "label": "macro-theory-preview"},
        {"prompt": computation, "model": p["model"], "effort": p["effort"], "allowed_tools": [],
         "output_file": strategy_dir / "referee_preview_methods.md", "label": "macro-computation-preview"},
    ], max_workers=2)
    results = [extract_json(r) or {} for r in responses]
    reqs = []
    for src, res in zip(("theory", "computation"), results):
        for r in res.get("code_requirements", []):
            r["source"] = src
            reqs.append(r)
    lines = ["# Referee Preview: Model & Code Requirements Checklist (macro)",
             f"\nGenerated: {datetime.now().isoformat()}"]
    counts = {}
    for prio in ("MUST", "SHOULD", "NICE"):
        items = [r for r in reqs if r.get("priority") == prio]
        counts[prio] = len(items)
        title = {"MUST": "MUST-HAVE", "SHOULD": "SHOULD-HAVE", "NICE": "NICE-TO-HAVE"}[prio]
        lines.append(f"\n## {title} ({len(items)} requirements)")
        lines += [f"- [{r['source'].upper()}] {r.get('category', '?')}: {r.get('requirement', '')}"
                  for r in items]
    for key, title in (("tables_required", "REQUIRED TABLES"),
                       ("figures_required", "REQUIRED FIGURES"),
                       ("must_not_claim", "MUST NOT CLAIM")):
        items = results[0].get(key, []) + results[1].get(key, [])
        if items:
            lines.append(f"\n## {title}")
            lines += [f"- {x}" for x in items]
    path = strategy_dir / "referee_checklist.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  [3.7] {counts.get('MUST', 0)} MUST, {counts.get('SHOULD', 0)} SHOULD "
          f"-> {path}")
    state["stages"]["stage3_7"] = {
        "status": "completed", "n_must": counts.get("MUST", 0),
        "n_should": counts.get("SHOULD", 0), "n_nice": counts.get("NICE", 0),
        "checklist_path": str(path), "completed_at": datetime.now().isoformat(),
    }
    save_state(project_dir, state)
    return state
