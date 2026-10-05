"""Macro track — Stage 2 (model-based ideation) and 2.5 (human selection).

Ideas are scored on what makes a Moll/KMV-style paper good: one sharp
mechanism, quantitative discipline from data, tractability with available
solution methods, and policy relevance. There is no identification score.
"""

import json
import textwrap
from datetime import datetime
from pathlib import Path

from ...claude_runner import run_claude
from ...config import get_profile
from ...json_utils import extract_json
from ...macro.model_catalog import MODEL_CLASSES, detect_model_class
from ...state import save_state

WEIGHTS = {"novelty": 0.20, "mechanism": 0.25, "discipline": 0.20,
           "tractability": 0.20, "impact": 0.15}


def run_stage2(project_dir: Path, state: dict) -> dict:
    s1 = state["stages"].get("stage1", {})
    topic = s1.get("topic", "macroeconomics")
    seeds = "\n".join(f"- {p.get('authors', '?')} ({p.get('year', '?')}), \"{p.get('title', '')}\": "
                      f"{p.get('contribution', '')}" for p in s1.get("seed_papers", []))
    plan = "\n".join(f"- {m.get('moment')}: {m.get('typical_value')} ({m.get('source')}, "
                     f"{m.get('role', '?')})" for m in s1.get("calibration_plan", []))
    series = state["stages"].get("stage1_5", {}).get("calibration_series", [])
    series_txt = "\n".join(f"- {x.get('source')} {x.get('series')}: last={x.get('last')}"
                           for x in series) or "(none downloaded)"
    classes = "\n".join(
        f"- {k}: {v['name']}. Template solver: {'YES' if v['template'] else 'no (custom code)'}. "
        f"Method: {v['solution']}" for k, v in MODEL_CLASSES.items())
    rejected = state["stages"].get("stage2", {}).get("rejected_ideas", [])
    rejected_txt = "\n".join(f"- {r.get('title')}: {r.get('flags')}" for r in rejected[-5:])

    prompt = f"""You are a research advisor in quantitative macroeconomics. Generate
MODEL-BASED paper ideas on: {topic}

The benchmark is a paper like Kaplan, Moll and Violante (2018, AER), Achdou et al.
(2022, REStud), Auclert, Rognlie and Straub (2024), Bilbiie (2020) or Guerrieri and
Lorenzoni (2017): a general-equilibrium model with ONE sharp economic mechanism,
disciplined by micro and macro data, solved with a credible numerical method, whose
equilibrium is verified (markets clear; Walras' law holds on the omitted market).

SEED PAPERS:
{seeds or '(none)'}

CALIBRATION DATA PLAN:
{plan or '(none)'}

DOWNLOADED SERIES:
{series_txt}

MODEL CLASSES (prefer template=YES unless the question truly needs more):
{classes}

{('PREVIOUSLY REJECTED (do not repeat):' + chr(10) + rejected_txt) if rejected_txt else ''}

Generate 8 ideas across at least 4 distinct mechanisms. For EACH idea specify:
- research question and the ONE mechanism (e.g. "indirect income effects dominate
  the direct intertemporal-substitution effect of monetary policy")
- model_class (a key from the list), environment (agents, frictions, markets),
  equilibrium concept, which market Walras' law makes redundant
- analytical result you can prove (e.g. TANK multiplier 1/(1-lambda chi), r < rho)
  -- these are candidates for optional Lean formalization
- calibration: targeted moments (with sources) and untargeted moments for validation
- main experiment: MIT shock (size, persistence) or counterfactual steady states
- what would make a referee say "this is just RANK with extra steps" and the answer

Score 1-5 on: novelty (N), mechanism clarity (M), quantitative discipline (D: are
there data moments that pin the key parameters?), tractability (T: 5 = template
solver handles it; 2 = needs a two-asset or aggregate-risk solver), impact (I).
Total = 0.20 N + 0.25 M + 0.20 D + 0.20 T + 0.15 I.

Select the TOP 3 from 3 different mechanisms. Output a JSON block:
```json
{{
  "top_ideas": [
    {{
      "rank": 1,
      "title": "...",
      "research_question": "...",
      "mechanism": "...",
      "model_class": "hank",
      "method": "One-asset HANK, continuous-time HJB-KFE (Achdou et al. 2022), sequence-space transition",
      "environment": "...",
      "equilibrium": "...",
      "walras_redundant_market": "goods",
      "analytical_results": ["..."],
      "targeted_moments": [{{"moment": "mpc", "data": 0.2, "source": "..."}}],
      "untargeted_moments": [{{"moment": "gini_wealth", "data": 0.77, "source": "SCF 2019"}}],
      "experiment": {{"type": "monetary_shock", "size": 0.0025, "persistence": 1.0}},
      "data_sources": ["..."],
      "referee_objection": "...",
      "novelty": 4, "mechanism_score": 5, "discipline": 4, "tractability": 5, "impact": 4,
      "total_score": 4.4,
      "pitch": "2-3 sentences",
      "first_experiment": "what you would solve in week 1"
    }}
  ]
}}
```
"""
    p = get_profile("macro_ideation")
    out = project_dir / "stage2_ideation.md"
    response = run_claude(prompt, model=p["model"], effort=p["effort"], output_file=out,
                          label="macro-ideation")
    data = extract_json(response) or {}
    ideas = data.get("top_ideas", [])
    for idea in ideas:
        idea["model_class"] = detect_model_class(idea)
        idea.setdefault("identification_level", "MODEL")
        idea["feasibility"] = idea.get("tractability", idea.get("feasibility"))
    state["stages"]["stage2"] = {
        "status": "completed",
        "mode": "macro",
        "output_file": str(out),
        "top_ideas": ideas,
        "completed_at": datetime.now().isoformat(),
    }
    if rejected:
        state["stages"]["stage2"]["rejected_ideas"] = rejected
    state["current_stage"] = 2
    save_state(project_dir, state)
    print(f"  [ok] {len(ideas)} model-based ideas" if ideas
          else "  [warn] Could not parse ideas; check stage2_ideation.md")
    return state


def _print_idea(i: int, idea: dict):
    mc = idea.get("model_class", "?")
    meta = MODEL_CLASSES.get(mc, {})
    print(f"\n  == [{i}] {idea.get('title', 'Untitled')[:70]}")
    print(f"     Score {idea.get('total_score', '?')}  (N={idea.get('novelty', '?')} "
          f"M={idea.get('mechanism_score', '?')} D={idea.get('discipline', '?')} "
          f"T={idea.get('tractability', '?')} I={idea.get('impact', '?')})")
    print(f"     Model: {meta.get('name', mc)}  "
          f"[{'template solver' if meta.get('template') else 'CUSTOM SOLVER NEEDED'}]")
    for label, key in (("RQ", "research_question"), ("Mechanism", "mechanism"),
                       ("Equilibrium", "equilibrium"), ("Pitch", "pitch"),
                       ("Referee objection", "referee_objection")):
        if idea.get(key):
            print(textwrap.fill(str(idea[key]), 74, initial_indent=f"     {label}: ",
                                subsequent_indent="        "))
    for res in idea.get("analytical_results", [])[:3]:
        print(f"     Provable: {res}")
    tm = ", ".join(str(m.get("moment")) for m in idea.get("targeted_moments", []))
    if tm:
        print(f"     Targets: {tm}")
    if meta.get("required_tests"):
        print(f"     Tests it must pass: {len(meta['required_tests'])} "
              f"(incl. {', '.join(meta['required_tests'][:4])}, ...)")


def run_stage2_5(project_dir: Path, state: dict) -> dict:
    ideas = state["stages"].get("stage2", {}).get("top_ideas", [])[:3]
    if not ideas:
        print("  [error] No ideas from Stage 2.")
        state["stages"]["stage2_5"] = {"status": "completed", "action": "REJECT"}
        save_state(project_dir, state)
        return state
    print("\nSTAGE 2.5 - MODEL IDEA SELECTION (human checkpoint)")
    for i, idea in enumerate(ideas, 1):
        _print_idea(i, idea)
    print("\n  SELECT <n>  |  REJECT ALL")
    print("\a", end="", flush=True)
    action, selected = "SELECT", ideas[0]
    while True:
        try:
            choice = input("\n>> ").strip().upper()
        except EOFError:
            print(f"  [auto] No interactive input. Selected idea 1.")
            break
        parts = choice.split()
        if parts[:1] == ["SELECT"] and len(parts) == 2 and parts[1].isdigit() \
                and 1 <= int(parts[1]) <= len(ideas):
            selected = ideas[int(parts[1]) - 1]
            break
        if choice == "REJECT ALL":
            action, selected = "REJECT", None
            break
        print("  Type SELECT <n> or REJECT ALL.")
    state["stages"]["stage2_5"] = {"status": "completed", "action": action,
                                   "completed_at": datetime.now().isoformat()}
    if selected:
        state["stages"]["stage2_5"]["selected_idea"] = selected
        (project_dir / "selected_idea.md").write_text(
            "# Selected model idea\n\n```json\n" + json.dumps(selected, indent=2)
            + "\n```\n", encoding="utf-8")
        print(f"  [ok] Selected: {selected.get('title')}")
    state["current_stage"] = 2.5
    save_state(project_dir, state)
    return state
