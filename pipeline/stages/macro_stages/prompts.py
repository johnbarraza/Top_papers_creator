"""Macro-track prompt text for the shared stages (4.7, 5, 6).

The shared stages keep their mechanics (manual intervention, LaTeX compile,
6-agent review, R&R loop); only the substantive instructions change from
"identification discipline" to "model discipline".
"""

from ...json_utils import smart_truncate

# ── Stage 5: writing standards ─────────────────────────────────────────────

WRITING_STANDARDS = (
    "Stage 5 (macro) needs manual paper writing. Tell Claude: 'revisa el pipeline'. "
    "Claude will read strategy/strategy_memo.md (model memo), strategy/model_spec.json, "
    "data/model/*.json and paper/tables/results_summary.md, write main.tex following the "
    "MACRO structure below (Introduction, Related Literature, Model, Analytical Results, "
    "Calibration, Results, Sensitivity, Conclusion, Computational Appendix, Proofs), "
    "create references, compile to PDF, and signal completion. "
    "WORD COUNT: 6,000-12,000 words. "
    "NUMBERS: every number comes from data/clean/main_results.csv or data/model/*.json.\n"
    "\n*** WRITING STANDARDS FOR A MODEL-BASED PAPER ***\n"
    "1. MECHANISM FIRST: state the one mechanism by page 2 and show it with a decomposition "
    "(e.g. direct vs indirect effects, Kaplan-Moll-Violante 2018) or a benchmark comparison "
    "(HANK vs TANK vs RANK).\n"
    "2. EQUILIBRIUM DEFINITION: formal, complete (prices, policies, distribution, market "
    "clearing). Add a remark naming the market made redundant by Walras' law and report that "
    "its residual is numerically zero (Table tab:eqtests).\n"
    "3. MATH: write the HJB and KFE (or Bellman/Euler) equations, the state constraint at the "
    "borrowing limit, and define every symbol once. Notation must match the code's calibration "
    "table.\n"
    "4. CALIBRATION DISCIPLINE: separate external from internal parameters; for each internal "
    "parameter name the moment that pins it; report untargeted moments as validation and "
    "discuss misses honestly.\n"
    "5. QUANTITATIVE CLAIMS: 'in the calibrated model', 'the model implies' — never 'we find "
    "that X causes Y in the data'. No causal-inference vocabulary (treatment, identification, "
    "estimate, significant).\n"
    "6. SENSITIVITY: show how the main number moves with the parameters that drive it; discuss "
    "every SOFT equilibrium test that failed (results_summary.md lists them).\n"
    "7. COMPUTATIONAL APPENDIX: algorithm, grids, tolerances, and \\input{tables/"
    "tab_equilibrium_tests.tex}.\n"
    "8. PROPOSITIONS: state analytical results as propositions with proofs in the appendix. If "
    "lean/ exists (Stage 5.5), say exactly which results are machine-checked, citing its status "
    "report; never claim formal verification that the report does not show.\n"
    "9. VOICE: 'we' throughout; no hedging.\n"
    "10. LABELS: use the labels of the MACRO structure template (sec:model, sec:analytical, "
    "sec:calibration, sec:results, sec:sensitivity, app:computation) instead of sec:data / "
    "sec:strategy in the LaTeX rules below.\n"
    "\n*** REFEREE RED FLAGS FOR MACRO PAPERS ***\n"
    "RED FLAG 1 — 'Heterogeneity for its own sake': the paper must say why the answer differs "
    "from RANK/TANK, with numbers.\n"
    "RED FLAG 2 — Results mechanically pinned by calibration: show the result is not just the "
    "targeted moment restated.\n"
    "RED FLAG 3 — Unverified equilibrium: no Walras/market-clearing evidence.\n"
    "RED FLAG 4 — Inconsistent numbers between abstract, text, tables.\n"
    "RED FLAG 5 — Table notes missing units (per year/quarter), shock size, horizon.\n"
)


def writing_files(project_dir) -> list[str]:
    return [
        str(project_dir / "strategy" / "strategy_memo.md"),
        str(project_dir / "strategy" / "model_spec.json"),
        str(project_dir / "data" / "model"),
        str(project_dir / "paper" / "tables" / "results_summary.md"),
        str(project_dir / "scripts" / "python"),
    ]


def model_results_block(project_dir) -> str:
    """Exact model outputs to embed in the Stage 5 prompt."""
    parts = []
    for rel in ("data/clean/main_results.csv", "data/model/steady_state.json",
                "data/model/experiment_summary.json"):
        p = project_dir / rel
        if p.exists():
            parts.append(f"\n--- {rel} ---\n{smart_truncate(p.read_text(encoding='utf-8'), 5000)}")
    tests = project_dir / "data" / "model" / "equilibrium_tests.json"
    if tests.exists():
        import json
        rep = json.loads(tests.read_text(encoding="utf-8"))
        failed = [t["id"] for t in rep.get("tests", []) if not t["passed"]]
        parts.append(f"\n--- equilibrium test summary ---\n{rep.get('summary')}\n"
                     f"Failed (SOFT, must be discussed): {failed}")
    if not parts:
        return ""
    return ("\n\n*** EXACT MODEL RESULTS (use ONLY these numbers) ***" + "".join(parts))


# ── Stage 4.7: paper-to-code mapping agent ─────────────────────────────────

def code_mapping_prompt(paper_summary: str, code_text: str) -> str:
    return f"""You are mapping a quantitative-macro model to its code implementation.

--- MODEL CONTEXT (model memo, spec, expected outputs) ---
{paper_summary}

--- CODE ---
{code_text}

The numbered scripts call ha_core.py (HJB-KFE solver) and equilibrium_checks.py (test
library); those two files are vetted pipeline code and are NOT shown. Check:
1. Every parameter in the model memo appears in 00_calibration.py with the same value/source.
2. Calibration targets: moment definitions match the memo (units: per year vs per quarter).
3. The experiment (shock size, persistence, horizon) matches the memo.
4. Every market in the equilibrium definition is either imposed or verified (Walras' law).
5. The test contract (quality_reports/model_contract.md) is fully reported.
6. Tables/figures promised in the memo are generated by 03_output.py.

Use labels HIGH / MEDIUM / LOW / NOT FOUND / MISMATCH.

## Verified Matches
## Items To Verify
## Likely Discrepancies
## Coverage Notes

Also output a JSON block at the end:
```json
{{
  "critical_mismatches": [
    {{"paper_element": "...", "code_evidence": "...", "fix": "concrete suggestion"}}
  ],
  "n_mismatches": 0,
  "n_not_found": 0,
  "overall_alignment": "GOOD|NEEDS_FIX"
}}
```
"""


# ── Stage 6: review agents that differ for model-based papers ──────────────

def agent3_prompt(paper_content: str, evidence_packet: str) -> str:
    return f"""You are a skeptical quantitative macroeconomist enforcing "model claim
discipline": claims must never exceed what the calibrated model and its verified
equilibrium support.

--- PAPER ---
{paper_content}

--- EVIDENCE PACKET (equilibrium tests, calibration audit, model outputs) ---
{evidence_packet}

**What to check:**
1. Empirical/causal language for model results ("we find in the data", "causes",
   "significant"). Quote sentences.
2. Mechanism claims without a decomposition or benchmark comparison backing them.
3. Results that restate a targeted moment (mechanically pinned by calibration).
4. Equilibrium claims without evidence: is Walras' law / market clearing reported?
   Use the evidence packet; flag any HARD test failure as CRITICAL.
5. Generalization beyond the calibration (other countries, periods, shock sizes —
   especially nonlinear shocks solved with linear methods).
6. Formal-verification overclaiming: claims that results are "proved"/"verified in
   Lean" beyond what the lean/ status report shows.
7. Missing caveats about abstractions (no aggregate risk, rigid prices, one asset...).

Tag every issue: [CRITICAL], [MAJOR], or [MINOR].

Output a JSON block at the end:
```json
{{
  "n_critical": 0,
  "n_major": 0,
  "n_minor": 0,
  "causal_overclaiming": ["quoted sentence"],
  "missing_caveats": ["caveat"]
}}
```
"""


def agent4_prompt(paper_content: str) -> str:
    return f"""You are a mathematical economist reviewing the formal content of a
model-based macro paper.

--- PAPER ---
{paper_content}

**What to check:**
1. HJB and KFE (or Bellman/Euler): correct form, boundary/state constraints, the KFE
   is the adjoint of the HJB generator, income process generator rows sum to zero.
2. Equilibrium definition: complete (all prices, policies, distribution, every market),
   consistent with the government budget and the aggregate resource constraint; the
   Walras' law remark names the right redundant market.
3. Propositions: hypotheses stated, proofs correct, no circularity.
4. Notation consistency with the calibration table (same symbols and units).
5. Undefined notation, equation numbering, LaTeX math formatting.

Tag every issue: [CRITICAL], [MAJOR], or [MINOR].

Output a JSON block at the end:
```json
{{
  "n_critical": 0,
  "n_major": 0,
  "n_minor": 0,
  "top_issues": ["issue1", "issue2"]
}}
```
"""


def agent6_prompt(paper_content: str, strategy_memo: str, evidence_packet: str,
                  target_journal: str) -> str:
    return f"""The target journal is {target_journal}.

You are an experienced referee for a macroeconomics journal (JME, AEJ:Macro, RED,
REStud). You are fair but rigorous and judge the paper as a MODEL-BASED contribution:
there is no causal identification to evaluate.

--- PAPER ---
{paper_content}

--- MODEL MEMO ---
{smart_truncate(strategy_memo, 3000)}

--- EVIDENCE PACKET ---
{evidence_packet}

SCORING CALIBRATION:
- 85-100: sharp mechanism, verified equilibrium, strong data discipline, clear
  benchmark comparison. Rare.
- 75-84: solid quantitative paper with honest limitations.
- 65-74: contribution exists but mechanism not cleanly isolated or calibration thin.
- 55-64: heterogeneity/GE adds little, or results look pinned by calibration.
- Below 55: equilibrium not verified, wrong model for the question.
Start from 72 (the paper passed earlier gates) and adjust. Only desk-reject issues are
[CRITICAL]. Standard practice is not a flaw (one-asset HANK, rigid prices, MIT shocks,
two-state income) if acknowledged.

**Your evaluation has 6 parts:**
1. Central contribution [Transformative | Significant | Incremental | Insufficient]
2. Model credibility: is the mechanism isolated (vs TANK/RANK)? Is the equilibrium
   verified (evidence packet)? Is the calibration disciplined by the right moments?
3. Required (max 3, [CRITICAL] only if results are uninterpretable) and suggested
   (max 5, [MAJOR]) analyses
4. Literature positioning
5. Recommendation [Send to referees | Revise before sending | Desk reject]
6. Questions to the authors (4-7)

Output a JSON block at the end:
```json
{{
  "score": 75,
  "contribution_rating": "Incremental",
  "recommendation": "Revise before sending",
  "dimension_scores": {{
    "contribution_novelty": 70,
    "model_credibility": 75,
    "quantitative_execution": 80,
    "writing_presentation": 78,
    "literature_positioning": 72
  }},
  "required_analyses": ["analysis1"],
  "suggested_analyses": ["analysis1", "analysis2"],
  "questions_to_authors": ["q1", "q2", "q3", "q4"],
  "n_critical": 0,
  "n_major": 3
}}
```
"""


def evidence_extras(project_dir) -> str:
    """Model-specific evidence for the referees (tests + Lean status)."""
    import json
    parts = []
    tests = project_dir / "data" / "model" / "equilibrium_tests.json"
    if tests.exists():
        rep = json.loads(tests.read_text(encoding="utf-8"))
        lines = [f"- [{t['level']}] {'PASS' if t['passed'] else 'FAIL'} {t['id']}: {t['detail']}"
                 for t in rep.get("tests", [])]
        parts.append("## Equilibrium tests (data/model/equilibrium_tests.json)\n"
                     + smart_truncate("\n".join(lines), 4000))
    lean_status = project_dir / "quality_reports" / "lean_status.md"
    if lean_status.exists():
        parts.append("## Lean formalization status (Stage 5.5)\n"
                     + smart_truncate(lean_status.read_text(encoding="utf-8"), 2000))
    return "\n\n".join(parts)
