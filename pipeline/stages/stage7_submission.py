"""Stage 7 — Submission (integration test).

Five phases:
  7a: Replication audit — re-run all scripts, compare outputs.
  7b: Integration validation — cross-stage consistency checks.
  7c: Final quality gate — validators + component scores must all pass.
  7d: Journal targeting (only if gate passes).
  7e: Feedback PDF — detailed diagnostics and improvement recommendations.
"""

import hashlib
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from ..config import (
    CLO_AUTHOR, SUBMISSION_GATE, COMPONENT_MIN, QUALITY_WEIGHTS,
    MAX_STAGE7_IMPROVE,
)
from ..python_runner import run_python_script
from ..state import save_state
from ..validators.code_validator import validate as validate_code
from ..validators.paper_validator import validate as validate_paper
from ..validators.integration_validator import validate as validate_integration


def _read_file_or(path: Path, default: str = "") -> str:
    return path.read_text(encoding="utf-8") if path.exists() else default


def _hash_file(path: Path) -> str:
    """MD5 hash of a file for output comparison."""
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()


def run(project_dir: Path, state: dict) -> dict:
    """Execute Stage 7: replication + integration test + final gate."""
    paper_dir = project_dir / "paper"
    scripts_dir = project_dir / "scripts" / "python"
    tables_dir = paper_dir / "tables"
    figures_dir = paper_dir / "figures"
    (project_dir / "quality_reports").mkdir(exist_ok=True)

    # ══════════════════════════════════════════════════════════════════════
    # 7a: REPLICATION AUDIT
    # ══════════════════════════════════════════════════════════════════════
    print("\n  [7a] Replication audit — re-running all scripts...")

    # Snapshot output files BEFORE replication
    pre_hashes = {}
    for d in [tables_dir, figures_dir]:
        if d.exists():
            for f in d.iterdir():
                pre_hashes[str(f.relative_to(project_dir))] = _hash_file(f)

    # Re-execute all scripts in order
    replication_ok = True
    replication_results = {}
    if scripts_dir.exists():
        py_scripts = sorted(scripts_dir.resolve().glob("[0-9]*.py"))
        for script in py_scripts:
            print(f"  [7a] Running {script.name}...")
            result = run_python_script(script, cwd=scripts_dir.resolve())
            replication_results[script.name] = {
                "ok": result["ok"],
                "returncode": result["returncode"],
            }
            if not result["ok"]:
                replication_ok = False
                print(f"  [7a] FAIL: {script.name}")
                stderr = result.get("stderr", "")
                if stderr:
                    print(f"        {stderr[:200]}")
    else:
        print("  [7a] No scripts directory found.")
        replication_ok = False

    # Snapshot output files AFTER replication and compare
    post_hashes = {}
    for d in [tables_dir, figures_dir]:
        if d.exists():
            for f in d.iterdir():
                post_hashes[str(f.relative_to(project_dir))] = _hash_file(f)

    changed_outputs = []
    for path, pre_hash in pre_hashes.items():
        post_hash = post_hashes.get(path, "")
        # Skip PDF figures — matplotlib PDFs have non-deterministic internal
        # metadata (font hashes, UUIDs) even with identical visual content.
        if path.endswith(".pdf") and "figures" in path:
            continue
        if pre_hash != post_hash:
            changed_outputs.append(path)

    disappeared = set(pre_hashes.keys()) - set(post_hashes.keys())
    new_files = set(post_hashes.keys()) - set(pre_hashes.keys())

    print(f"  [7a] Replication: {'PASS' if replication_ok else 'FAIL'}")
    if changed_outputs:
        print(f"  [7a] WARNING: {len(changed_outputs)} output(s) changed on re-run:")
        for c in changed_outputs[:5]:
            print(f"        - {c}")
    if disappeared:
        print(f"  [7a] WARNING: {len(disappeared)} output(s) disappeared on re-run")
    if not changed_outputs and not disappeared and replication_ok:
        print(f"  [7a] All outputs are reproducible (identical hashes).")

    # ══════════════════════════════════════════════════════════════════════
    # 7b: INTEGRATION VALIDATION
    # ══════════════════════════════════════════════════════════════════════
    print("\n  [7b] Running 3 validators in parallel...")

    # Run all three validators concurrently (pure Python, no Claude calls)
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_code = pool.submit(
            validate_code, scripts_dir, project_dir,
            {name: res for name, res in replication_results.items()},
        )
        f_paper = pool.submit(
            validate_paper, paper_dir, project_dir,
            compiled=(paper_dir / "main.pdf").exists(),
        )
        f_integration = pool.submit(validate_integration, project_dir)

    code_val = f_code.result()
    paper_val = f_paper.result()
    integration_val = f_integration.result()

    print(f"  [7b] Code validator:        {code_val.format_for_log()}")
    print(f"  [7b] Paper validator:       {paper_val.format_for_log()}")
    print(f"  [7b] Integration validator: {integration_val.format_for_log()}")

    # Collect all hard failures across validators
    all_hard_failures = (
        code_val.hard_failures
        + paper_val.hard_failures
        + integration_val.hard_failures
    )
    all_validators_pass = len(all_hard_failures) == 0

    if all_hard_failures:
        print(f"\n  [7b] HARD FAILURES ({len(all_hard_failures)}):")
        for fail in all_hard_failures:
            print(f"        - {fail.name}: {fail.detail}")

    # ══════════════════════════════════════════════════════════════════════
    # 7c: FINAL QUALITY GATE
    # ══════════════════════════════════════════════════════════════════════
    print("\n  [7c] Final quality gate...")

    # Gather component scores from previous stages
    stage4a = state["stages"].get("stage4a", {})
    stage4bc = state["stages"].get("stage4bc", {})
    stage5 = state["stages"].get("stage5", {})
    stage6 = state["stages"].get("stage6", {})

    # RECALCULATE code and paper scores from current validator results
    # instead of using frozen values from earlier stages
    # Note: frozen scores from earlier stages are ignored — we recalculate
    # from current validator results to reflect the actual state of code/paper

    # Recalculate code score from current validation
    code_counts = code_val.summary_counts
    code_hard = code_counts.get("hard_passed", code_counts.get("hard_pass", 0))
    code_hard_total = code_counts.get("hard_total", 1)
    code_soft = code_counts.get("soft_passed", code_counts.get("soft_pass", 0))
    code_soft_total = code_counts.get("soft_total", 1)
    if code_hard == code_hard_total:
        code_score = 60 + int((code_soft / max(code_soft_total, 1)) * 40)
    else:
        code_score = 40 + int((code_soft / max(code_soft_total, 1)) * 20)
    if replication_ok:
        code_score = min(100, code_score + 5)
    # Always use the recalculated score — it reflects the CURRENT state of the code
    # The frozen score may be stale from earlier stages with different scripts

    # Recalculate paper score from current validation
    paper_counts = paper_val.summary_counts
    paper_hard = paper_counts.get("hard_passed", paper_counts.get("hard_pass", 0))
    paper_hard_total = paper_counts.get("hard_total", 1)
    paper_soft = paper_counts.get("soft_passed", paper_counts.get("soft_pass", 0))
    paper_soft_total = paper_counts.get("soft_total", 1)
    compiled = stage5.get("compiled", False)
    if paper_hard == paper_hard_total:
        paper_score = 60 + int((paper_soft / max(paper_soft_total, 1)) * 40)
    else:
        paper_score = 40 + int((paper_soft / max(paper_soft_total, 1)) * 20)
    if compiled:
        paper_score = min(100, paper_score + 5)
    # Always use recalculated — frozen may be stale

    # Identification score
    from .stage4_strategy import _score_identification
    ident_score = stage4a.get("critic_score", 0)
    if ident_score == 0:
        ident_score = _score_identification(state)

    # Adjust identification based on peer review
    polish_score = stage6.get("avg_score", 0)
    if polish_score > 0 and ident_score > 0:
        if polish_score < ident_score - 15:
            ident_score = int(ident_score * 0.8 + polish_score * 0.2)

    components = {
        "identification": ident_score,
        "code": code_score,
        "paper": paper_score,
        "polish": stage6.get("avg_score", 0),
        "replication": 100 if (replication_ok and not changed_outputs) else
                       50 if replication_ok else 0,
    }

    # Weighted aggregate
    aggregate = sum(
        components.get(k, 0) * w
        for k, w in QUALITY_WEIGHTS.items()
    )

    # Component minimums
    below_min = {k: v for k, v in components.items() if v < COMPONENT_MIN}

    # Gate decision: ALL must pass
    gate_passed = (
        aggregate >= SUBMISSION_GATE
        and not below_min
        and all_validators_pass
        and replication_ok
        and not changed_outputs
    )

    # Print report
    print(f"\n  {'=' * 60}")
    print(f"  FINAL QUALITY REPORT")
    print(f"  {'=' * 60}")
    print(f"  Aggregate score:    {aggregate:.1f}/100 (gate: {SUBMISSION_GATE})")
    print(f"  Validators:         {'PASS' if all_validators_pass else 'FAIL'}"
          f" ({len(all_hard_failures)} hard failures)")
    print(f"  Replication:        {'PASS' if replication_ok else 'FAIL'}")
    print(f"  Reproducibility:    "
          f"{'PASS' if not changed_outputs else 'FAIL'}"
          f" ({len(changed_outputs)} changed outputs)")
    print(f"  {'-' * 60}")
    for k, v in components.items():
        weight = QUALITY_WEIGHTS.get(k, 0)
        status = "PASS" if v >= COMPONENT_MIN else "FAIL"
        print(f"  [{status}] {k:20s}: {v:5.1f}/100 (weight: {weight:.0%})")
    print(f"  {'-' * 60}")
    print(f"  GATE: {'PASSED' if gate_passed else 'FAILED'}")
    print(f"  {'=' * 60}")

    if not gate_passed:
        reasons = []
        if aggregate < SUBMISSION_GATE:
            reasons.append(f"aggregate {aggregate:.1f} < {SUBMISSION_GATE}")
        if below_min:
            reasons.append(
                f"below component minimum: "
                + ", ".join(f"{k}={v}" for k, v in below_min.items())
            )
        if not all_validators_pass:
            reasons.append(f"{len(all_hard_failures)} hard validation failure(s)")
        if not replication_ok:
            reasons.append("replication failed")
        if changed_outputs:
            reasons.append(f"{len(changed_outputs)} non-reproducible output(s)")
        print(f"\n  Reasons: {'; '.join(reasons)}")

    # Save detailed validation report
    report_lines = [
        "# Stage 7 — Integration Test Report",
        f"\nDate: {datetime.now().isoformat()}",
        f"\n## Gate: {'PASSED' if gate_passed else 'FAILED'}",
        f"Aggregate: {aggregate:.1f}/{SUBMISSION_GATE}",
        f"\n## Component Scores",
    ]
    for k, v in components.items():
        report_lines.append(f"- {k}: {v}/100")
    report_lines.append(f"\n## Replication")
    report_lines.append(f"- Scripts ran: {'Yes' if replication_ok else 'No'}")
    report_lines.append(f"- Outputs reproducible: {'Yes' if not changed_outputs else 'No'}")
    if changed_outputs:
        report_lines.append(f"- Changed: {', '.join(changed_outputs)}")
    report_lines.append(f"\n## Code Validation\n{code_val.format_for_critic()}")
    report_lines.append(f"\n## Paper Validation\n{paper_val.format_for_critic()}")
    report_lines.append(
        f"\n## Integration Validation\n{integration_val.format_for_critic()}"
    )

    report_path = project_dir / "quality_reports" / "integration_test_report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\n  [7] Full report: {report_path}")

    # ══════════════════════════════════════════════════════════════════════
    # 7e: USER DECISION — accept or improve
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n  {'=' * 60}")
    print(f"  What would you like to do?")
    print(f"  {'=' * 60}")
    print(f"  [1] Accept aggregate score ({aggregate:.1f}/100) — paper finished")
    print(f"  [2] Improve paper — manual intervention to raise score")
    print(f"  {'=' * 60}")
    print("\a", end="", flush=True)  # Terminal bell — user input needed

    user_choice = ""
    while user_choice not in ("1", "2"):
        user_choice = input("\n  Enter your choice (1 or 2): ").strip()
        if user_choice not in ("1", "2"):
            print("  Please enter 1 or 2.")

    if user_choice == "2":
        # Save improvement request for manual intervention
        improvement_file = project_dir / "quality_reports" / "improvement_request.md"
        improvement_lines = [
            "# Improvement Request",
            f"\nDate: {datetime.now().isoformat()}",
            f"Current aggregate: {aggregate:.1f}/100",
            f"\n## Current Component Scores",
        ]
        for k, v in components.items():
            improvement_lines.append(f"- {k}: {v}/100")
        improvement_lines.append(f"\n## Areas for Improvement")
        improvement_lines.append(
            "Review the issues in the following files and address them manually:"
        )
        improvement_lines.append(
            f"- Identification: quality_reports/identification_review.md"
        )
        improvement_lines.append(f"- Code: quality_reports/code_review.md")
        improvement_lines.append(f"- Paper: quality_reports/paper_review.md")
        improvement_lines.append(f"- Polish: quality_reports/peer_review.md")
        improvement_lines.append(
            f"\n## Instructions"
        )
        improvement_lines.append(
            "1. Claude (in conversation) will read the review files and make "
            "improvements to the paper sections, scripts, and tables."
        )
        improvement_lines.append(
            "2. After improvements, update the review files with new scores."
        )
        improvement_lines.append(
            "3. Re-run Stage 7 to get the updated Final Quality Report."
        )
        improvement_file.write_text(
            "\n".join(improvement_lines), encoding="utf-8"
        )

        # Signal manual intervention and WAIT
        from ..claude_runner import request_manual_intervention
        request_manual_intervention(
            stage="stage7_improvement",
            issue=(
                f"Stage 7: User chose to improve paper. Aggregate={aggregate:.1f}/100. "
                f"Tell Claude: 'revisa el pipeline'. Claude will read the review files, "
                f"improve the paper/scripts, update scores, and signal completion."
            ),
            files=[
                str(project_dir / "quality_reports" / "integration_test_report.md"),
                str(project_dir / "quality_reports"),
                str(project_dir / "paper" / "main.tex"),
                str(project_dir / "scripts" / "python"),
            ],
            project_dir=project_dir,
        )

        # After intervention: re-run Stage 7 (with depth limit)
        improve_count = state["stages"].get("stage7", {}).get("improve_count", 0) + 1
        state.setdefault("stages", {}).setdefault("stage7", {})["improve_count"] = improve_count

        if improve_count > MAX_STAGE7_IMPROVE:
            print(f"\n  [7] Maximum improvement rounds ({MAX_STAGE7_IMPROVE}) reached. Proceeding as-is.")
        else:
            print(f"\n  [7] Re-running Stage 7 after improvements (round {improve_count}/{MAX_STAGE7_IMPROVE})...")
            state = run(project_dir, state)
            return state

    # ══════════════════════════════════════════════════════════════════════
    # User chose [1] — Accept score, proceed to journal targeting
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n  Score accepted. Proceeding to finalize...")

    # ══════════════════════════════════════════════════════════════════════
    # 7d: JOURNAL TARGETING (only if gate passes)
    # ══════════════════════════════════════════════════════════════════════
    targeting_result = {}
    if gate_passed:
        print("\n  [7d] Journal targeting...")

        # Deterministic journal targeting based on score tiers
        # No Claude call needed — this is a simple lookup
        if aggregate >= 85:
            primary = {"name": "Journal of Political Economy", "fit_reason": "Top-5 general interest, strong empirical work", "turnaround_months": 6}
            backup = {"name": "Review of Economics and Statistics", "fit_reason": "Top field journal for empirical methods", "turnaround_months": 5}
            conferences = ["NBER Summer Institute", "AEA Annual Meeting", "ASSA"]
        elif aggregate >= 75:
            primary = {"name": "Journal of Economic Behavior & Organization", "fit_reason": "Strong fit for empirical tech/labor papers", "turnaround_months": 4}
            backup = {"name": "Information Economics and Policy", "fit_reason": "Specialized in technology and economics", "turnaround_months": 3}
            conferences = ["AEA Annual Meeting", "WEAI", "European Economic Association"]
        elif aggregate >= 70:
            primary = {"name": "Economics Letters", "fit_reason": "Fast turnaround, accepts concise empirical contributions", "turnaround_months": 2}
            backup = {"name": "Applied Economics Letters", "fit_reason": "Regional/applied journal, good for null results", "turnaround_months": 2}
            conferences = ["WEAI", "Southern Economic Association", "Midwest Economics Association"]
        else:
            primary = {"name": "Working Paper Series", "fit_reason": "Paper needs more work before journal submission", "turnaround_months": 0}
            backup = {"name": "SSRN / arXiv", "fit_reason": "Preprint to establish priority while revising", "turnaround_months": 0}
            conferences = ["Departmental seminar", "Brown bag lunch series"]

        targeting_result = {
            "primary_journal": primary,
            "backup_journal": backup,
            "conferences": conferences,
        }

        # Save to file
        targeting_file = project_dir / "quality_reports" / "journal_targeting.md"
        targeting_text = (
            f"# Journal Targeting\n\n"
            f"Aggregate score: {aggregate:.1f}/100\n\n"
            f"## Primary Target\n"
            f"**{primary['name']}** — {primary['fit_reason']} "
            f"(~{primary['turnaround_months']} months turnaround)\n\n"
            f"## Backup Target\n"
            f"**{backup['name']}** — {backup['fit_reason']}\n\n"
            f"## Conference Targets\n"
            + "\n".join(f"- {c}" for c in conferences)
        )
        targeting_file.write_text(targeting_text, encoding="utf-8")

        print(f"  [7d] Target journal: {primary['name']}")
    else:
        print("\n  [7d] Skipping journal targeting — gate not passed.")

    # ══════════════════════════════════════════════════════════════════════
    # 7e: FEEDBACK PDF
    # ══════════════════════════════════════════════════════════════════════
    print("\n  [7e] Generating feedback.pdf...")
    try:
        _generate_feedback_pdf(
            project_dir, state, components, aggregate, gate_passed,
            all_hard_failures, replication_ok, changed_outputs,
            code_val, paper_val, integration_val,
        )
    except Exception as e:
        print(f"  [7e] WARNING: feedback.pdf generation failed: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # SAVE STATE
    # ══════════════════════════════════════════════════════════════════════
    state["stages"]["stage7"] = {
        "status": "completed",
        "replication_ok": replication_ok,
        "replication_results": replication_results,
        "outputs_reproducible": len(changed_outputs) == 0,
        "changed_outputs": changed_outputs,
        "validation": {
            "code": code_val.summary_counts,
            "paper": paper_val.summary_counts,
            "integration": integration_val.summary_counts,
            "all_hard_pass": all_validators_pass,
            "total_hard_failures": len(all_hard_failures),
        },
        "components": components,
        "aggregate_score": round(aggregate, 1),
        "gate_passed": gate_passed,
        "below_minimum": below_min,
        "targeting": targeting_result,
        "user_choice": "accept",
        "completed_at": datetime.now().isoformat(),
    }

    state["current_stage"] = 7
    save_state(project_dir, state)

    # Final summary
    final_pdf = paper_dir / "main.pdf"
    if gate_passed:
        print(f"\n  Paper is submission-ready.")
        print(f"  PDF: {final_pdf}")
    else:
        print(f"\n  Paper needs more work before submission.")
        print(f"  Review: {report_path}")

    return state


# ══════════════════════════════════════════════════════════════════════════════
# FEEDBACK PDF GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def _generate_feedback_pdf(
    project_dir, state, components, aggregate, gate_passed,
    hard_failures, replication_ok, changed_outputs,
    code_val, paper_val, integration_val,
):
    """Generate feedback.pdf with detailed diagnostics and recommendations."""
    try:
        import csv
        import json as _json
        import math
        from fpdf import FPDF

        # ── helper: safe latin-1 text ──
        def _safe(text):
            if not isinstance(text, str):
                text = str(text)
            return text.encode("latin-1", errors="replace").decode("latin-1")

        # ── helper: find column value flexibly ──
        def _col(row, candidates, as_float=False):
            for c in candidates:
                if c in row and row[c] not in (None, ""):
                    if as_float:
                        try:
                            return float(row[c])
                        except (ValueError, TypeError):
                            continue
                    return row[c]
            return None

        # ── helper: read editorial decision must-address list ──
        def _read_must_issues(review_dir, limit=None):
            # Note: the previous implementation did
            #   dec_text.strip().strip("`").strip("json").strip()
            # which is broken: str.strip("json") strips the *characters*
            # j, s, o, n from each end, not the literal substring "json".
            # That truncated any decision starting with "j" or ending with
            # "n", and the surrounding `except Exception: pass` swallowed
            # the resulting JSONDecodeError silently — leaving must-issues
            # empty and the submission feedback PDF blank.  The shared
            # extract_json helper handles fenced blocks correctly.
            from ..json_utils import extract_json

            issues = []
            if review_dir.exists():
                for dec_file in sorted(
                    review_dir.glob("editorial_decision*.md"), reverse=True
                ):
                    try:
                        dec_text = dec_file.read_text(encoding="utf-8")
                        dec_data = extract_json(dec_text)
                        if dec_data is None:
                            print(
                                f"    [stage7] {dec_file.name}: could not "
                                f"extract JSON, skipping"
                            )
                            continue
                        issues = dec_data.get("must_address", [])
                        break
                    except Exception as exc:
                        print(
                            f"    [stage7] {dec_file.name}: read failed ({exc})"
                        )
            if limit:
                issues = issues[:limit]
            return issues

        # ── PDF subclass ──
        class FeedbackPDF(FPDF):
            def header(self):
                if self.page_no() == 1:
                    return  # title page has no header
                self.set_font("Helvetica", "I", 9)
                self.set_text_color(150, 150, 150)
                self.cell(0, 8, "Papers-HQ Feedback Report", align="R",
                          new_x="LMARGIN", new_y="NEXT")
                self.set_draw_color(200, 200, 200)
                self.line(10, self.get_y(), 200, self.get_y())
                self.ln(3)

            def footer(self):
                self.set_y(-15)
                self.set_font("Helvetica", "I", 8)
                self.set_text_color(160, 160, 160)
                self.cell(0, 10, "Page %d/{nb}" % self.page_no(), align="C")

            def section_title(self, title):
                if self.get_y() > 250:
                    self.add_page()
                self.set_font("Helvetica", "B", 14)
                self.set_text_color(0, 51, 102)
                self.ln(6)
                self.cell(0, 10, _safe(title), new_x="LMARGIN", new_y="NEXT")
                self.set_draw_color(0, 51, 102)
                self.set_line_width(0.5)
                self.line(10, self.get_y(), 200, self.get_y())
                self.set_line_width(0.2)
                self.ln(4)

            def sub_title(self, title):
                if self.get_y() > 265:
                    self.add_page()
                self.set_font("Helvetica", "B", 11)
                self.set_text_color(51, 51, 51)
                self.ln(3)
                self.cell(0, 8, _safe(title), new_x="LMARGIN", new_y="NEXT")
                self.ln(1)

            def body_text(self, text):
                self.set_font("Helvetica", "", 10)
                self.set_text_color(0, 0, 0)
                self.multi_cell(0, 5, _safe(text))
                self.ln(2)

            def score_bar(self, label, score, weight=None, explanation=""):
                """Wide colored bar with label, score, and optional one-liner."""
                if self.get_y() > 260:
                    self.add_page()
                x = self.get_x()
                y = self.get_y()
                # Label
                self.set_font("Helvetica", "", 10)
                self.set_text_color(0, 0, 0)
                lbl = label
                if weight:
                    lbl += " (%d%%)" % int(weight * 100)
                self.cell(50, 7, _safe(lbl))
                # Background bar
                bar_x = x + 50
                bar_w = 110
                bar_h = 7
                self.set_fill_color(230, 230, 230)
                self.rect(bar_x, y, bar_w, bar_h, "F")
                # Filled portion
                fill_w = max(0, min(bar_w, bar_w * score / 100))
                if score >= 80:
                    self.set_fill_color(76, 175, 80)       # green
                elif score >= 70:
                    self.set_fill_color(255, 193, 7)       # yellow
                else:
                    self.set_fill_color(244, 67, 54)       # red
                self.rect(bar_x, y, fill_w, bar_h, "F")
                # Score text
                self.set_xy(bar_x + bar_w + 3, y)
                self.set_font("Helvetica", "B", 10)
                self.cell(25, 7, "%.0f / 100" % score)
                self.ln(bar_h + 1)
                # One-line explanation beneath
                if explanation:
                    self.set_font("Helvetica", "I", 8)
                    self.set_text_color(100, 100, 100)
                    self.cell(0, 4, _safe(explanation), new_x="LMARGIN", new_y="NEXT")
                    self.ln(2)

            def color_badge(self, text, r, g, b, w=40, h=6):
                """Small colored rectangle with white text."""
                x = self.get_x()
                y = self.get_y()
                self.set_fill_color(r, g, b)
                self.rect(x, y, w, h, "F")
                self.set_xy(x, y)
                self.set_font("Helvetica", "B", 8)
                self.set_text_color(255, 255, 255)
                self.cell(w, h, _safe(text), align="C")
                self.set_text_color(0, 0, 0)

            def draw_pentagon_chart(self, labels, scores, cx, cy, radius):
                """Draw a radar/spider chart approximation with 5 axes."""
                n = len(labels)
                if n < 3:
                    return
                n = min(n, 5)
                labels = labels[:n]
                scores = scores[:n]
                angle_offset = -math.pi / 2  # start from top

                def polar(i, r):
                    angle = angle_offset + 2 * math.pi * i / n
                    return cx + r * math.cos(angle), cy + r * math.sin(angle)

                # Draw grid rings at 25, 50, 75, 100
                self.set_draw_color(210, 210, 210)
                self.set_line_width(0.15)
                for ring in [0.25, 0.5, 0.75, 1.0]:
                    r = radius * ring
                    for i in range(n):
                        x1, y1 = polar(i, r)
                        x2, y2 = polar((i + 1) % n, r)
                        self.line(x1, y1, x2, y2)

                # Draw axis lines
                self.set_draw_color(180, 180, 180)
                for i in range(n):
                    x1, y1 = polar(i, 0)
                    x2, y2 = polar(i, radius)
                    self.line(cx, cy, x2, y2)

                # Draw filled polygon for scores
                points = []
                for i in range(n):
                    s = max(0, min(100, scores[i]))
                    r = radius * s / 100
                    px, py = polar(i, r)
                    points.append((px, py))

                # Fill polygon with semi-transparent color using lines
                # fpdf2 does not support alpha, so draw filled outline
                if len(points) >= 3:
                    # Use a light fill color
                    self.set_fill_color(76, 175, 80)
                    self.set_draw_color(46, 125, 50)
                    self.set_line_width(0.6)
                    # Build point string for polygon
                    # fpdf2 polygon method
                    try:
                        self.polygon(points, style="DF")
                    except AttributeError:
                        # Fallback: draw lines connecting points
                        for i in range(len(points)):
                            x1, y1 = points[i]
                            x2, y2 = points[(i + 1) % len(points)]
                            self.line(x1, y1, x2, y2)

                self.set_line_width(0.2)

                # Draw axis labels
                self.set_font("Helvetica", "B", 7)
                self.set_text_color(0, 51, 102)
                for i in range(n):
                    lx, ly = polar(i, radius + 6)
                    # Center label on point
                    self.set_xy(lx - 12, ly - 2)
                    self.cell(24, 4, _safe("%s (%d)" % (labels[i][:8], scores[i])),
                              align="C")

        # ── Build PDF ──
        pdf = FeedbackPDF()
        pdf.alias_nb_pages()
        pdf.set_auto_page_break(auto=True, margin=20)

        # ================================================================
        # TITLE PAGE
        # ================================================================
        pdf.add_page()

        pdf.ln(30)
        # Paper title
        pdf.set_font("Helvetica", "B", 24)
        pdf.set_text_color(0, 51, 102)
        title = (state.get("stages", {}).get("stage3", {})
                 .get("result", {}).get("title", "Untitled"))
        pdf.multi_cell(0, 12, _safe(title), align="C")
        pdf.ln(8)

        # Subtitle
        pdf.set_font("Helvetica", "", 14)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 8, "Feedback & Improvement Report", align="C",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 6,
                 "Generated: %s" % datetime.now().strftime("%Y-%m-%d %H:%M"),
                 align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(12)

        # Aggregate score badge (large colored circle approximation)
        badge_x = 105  # center of page
        badge_y = pdf.get_y() + 15
        badge_r = 18
        if gate_passed:
            pdf.set_fill_color(76, 175, 80)
            pdf.set_draw_color(56, 142, 60)
        else:
            pdf.set_fill_color(244, 67, 54)
            pdf.set_draw_color(198, 40, 40)
        pdf.set_line_width(1.0)
        pdf.ellipse(badge_x - badge_r, badge_y - badge_r,
                    badge_r * 2, badge_r * 2, style="DF")
        pdf.set_line_width(0.2)
        # Score number inside badge
        pdf.set_font("Helvetica", "B", 22)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(badge_x - badge_r, badge_y - 7)
        pdf.cell(badge_r * 2, 10, "%.0f" % aggregate, align="C")
        pdf.set_xy(badge_x - badge_r, badge_y + 3)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(badge_r * 2, 6, "/ 100", align="C")
        pdf.ln(badge_r * 2 + 8)

        # Gate status with clear explanation
        pdf.set_font("Helvetica", "B", 13)
        if gate_passed:
            pdf.set_text_color(56, 142, 60)
            pdf.cell(0, 8, "GATE: PASSED",
                     align="C", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 6, "All components above minimum (%d) and aggregate above %d"
                     % (COMPONENT_MIN, SUBMISSION_GATE),
                     align="C", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_text_color(198, 40, 40)
            pdf.cell(0, 8, "GATE: FAILED",
                     align="C", new_x="LMARGIN", new_y="NEXT")
            # Explain WHY it failed
            pdf.set_font("Helvetica", "", 10)
            reasons = []
            if aggregate < SUBMISSION_GATE:
                reasons.append("aggregate %.1f < %d threshold" % (aggregate, SUBMISSION_GATE))
            below = {k: v for k, v in components.items() if v < COMPONENT_MIN}
            if below:
                for k, v in below.items():
                    reasons.append("%s = %.0f (below minimum %d)" % (k, v, COMPONENT_MIN))
            reason_text = "Reason: " + "; ".join(reasons) if reasons else "See details below"
            pdf.cell(0, 6, reason_text,
                     align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

        # ================================================================
        # SECTION 1: SCORE BREAKDOWN
        # ================================================================
        pdf.add_page()
        pdf.section_title("1. Score Breakdown")

        pdf.body_text(
            "Aggregate score: %.1f/100  |  Gate: %s  |  Threshold: %d/100" % (
                aggregate, "PASSED" if gate_passed else "FAILED", SUBMISSION_GATE
            )
        )

        explanations = {
            "identification": "Credibility of causal design: control group, pre-trends, exogeneity.",
            "code": "Scripts run cleanly, outputs exist, SE clustering, robustness checks.",
            "paper": "All sections present, references resolve, tables/figures, word count.",
            "polish": "Average referee score from peer review. Hardest to improve.",
            "replication": "All scripts reproduce identical outputs when re-run.",
        }

        for comp_name, comp_score in components.items():
            weight = QUALITY_WEIGHTS.get(comp_name, 0)
            expl = explanations.get(comp_name, "")
            pdf.score_bar(comp_name.title(), comp_score, weight, explanation=expl)

        # ── Radar / spider chart ──
        pdf.ln(4)
        pdf.sub_title("Score Profile (radar chart)")
        chart_labels = []
        chart_scores = []
        for comp_name, comp_score in list(components.items())[:5]:
            chart_labels.append(comp_name.title())
            chart_scores.append(comp_score)
        if len(chart_labels) >= 3:
            chart_cy = pdf.get_y() + 38
            chart_cx = 105
            chart_r = 30
            pdf.draw_pentagon_chart(chart_labels, chart_scores,
                                   chart_cx, chart_cy, chart_r)
            pdf.set_y(chart_cy + chart_r + 12)

        # ── Detailed explanations ──
        pdf.ln(4)
        pdf.sub_title("What each score means")
        long_explanations = {
            "identification": (
                "How credible is the causal claim? A high score means the study has a "
                "valid control group, clean pre-trends, and addresses confounders. "
                "Studies without a control group (e.g., before-after designs) score below 85. "
                "RCTs and strong natural experiments score 90+."
            ),
            "code": (
                "Do the scripts run correctly and implement the required analyses? "
                "Checks include: all 4 scripts exist and execute, output files are "
                "non-empty, standard errors are appropriate, and the referee checklist "
                "requirements are addressed in the code."
            ),
            "paper": (
                "Is the paper complete and well-structured? Checks include: all sections "
                "present (intro through conclusion), references resolve, tables and "
                "figures included, word count between 5,000-12,000, and key numbers "
                "in the abstract match the actual results."
            ),
            "polish": (
                "How did the simulated referees rate the paper? This is the average "
                "score from the peer review stage. It reflects how well the paper "
                "presents its findings, handles robustness checks, and addresses "
                "identification concerns. This is the hardest score to improve "
                "because it depends on data quality and research design."
            ),
            "replication": (
                "Can the results be reproduced? The pipeline re-runs all scripts "
                "and checks that outputs are identical. A score of 100 means "
                "perfect reproducibility."
            ),
        }
        for comp_name in components:
            exp = long_explanations.get(comp_name, "")
            if exp:
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(0, 0, 0)
                pdf.cell(0, 5,
                         "%s (%.0f/100):" % (comp_name.title(), components[comp_name]),
                         new_x="LMARGIN", new_y="NEXT")
                pdf.body_text(exp)

        # ================================================================
        # SECTION 2: RESULTS DIAGNOSTICS
        # ================================================================
        pdf.add_page()
        pdf.section_title("2. Results Diagnostics")

        spec_cols = ["specification", "model", "estimator", "label", "test"]
        coef_cols = ["coef", "att", "ATT", "estimate", "coefficient"]
        p_cols = ["p_value", "p", "pval", "Pr(>|t|)", "pvalue"]

        main_path = project_dir / "data" / "clean" / "main_results.csv"
        if main_path.exists():
            with open(main_path, encoding="utf-8") as f:
                main_rows = list(csv.DictReader(f))
            if main_rows:
                pdf.sub_title("Main findings")
                for r in main_rows[:8]:
                    spec = _col(r, spec_cols) or "?"
                    coef = _col(r, coef_cols, as_float=True)
                    p_val = _col(r, p_cols, as_float=True)
                    if coef is not None:
                        sig = ""
                        if p_val is not None:
                            if p_val < 0.01:
                                sig = " ***"
                            elif p_val < 0.05:
                                sig = " **"
                            elif p_val < 0.1:
                                sig = " *"
                            sig = " (p=%.4f)%s" % (p_val, sig)
                        pdf.body_text("  %s: coef = %+.4f%s" % (
                            str(spec)[:60], coef, sig))

        robustness_path = project_dir / "data" / "clean" / "robustness_results.csv"
        if robustness_path.exists():
            with open(robustness_path, encoding="utf-8") as f:
                rob_rows = list(csv.DictReader(f))
            if rob_rows:
                pdf.sub_title("Robustness summary")
                sig_count = 0
                insig_count = 0
                for r in rob_rows:
                    p_val = _col(r, p_cols, as_float=True)
                    if p_val is not None:
                        if p_val < 0.05:
                            sig_count += 1
                        else:
                            insig_count += 1
                total = sig_count + insig_count
                if total > 0:
                    pdf.body_text(
                        "%d of %d robustness specifications significant (p<0.05)." % (
                            sig_count, total)
                    )
                    if sig_count == 0:
                        pdf.body_text(
                            "No specification achieves significance. Consistent with "
                            "a genuine null result or an underpowered study."
                        )
                    elif insig_count == 0:
                        pdf.body_text(
                            "All specifications are significant. The result is robust "
                            "across all tested variations."
                        )
                    elif sig_count < insig_count:
                        pdf.body_text(
                            "Most specifications are insignificant. Significant results "
                            "may reflect specific subgroups rather than a general effect."
                        )

                # Mini-table of key robustness checks
                pdf.sub_title("Key robustness checks")
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(100, 100, 100)
                pdf.cell(0, 4,
                         "Each row tests if the main result holds under different conditions. "
                         "*** = p<0.01, ** = p<0.05, * = p<0.10.",
                         new_x="LMARGIN", new_y="NEXT")
                pdf.ln(2)
                # Table header
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_fill_color(0, 51, 102)
                pdf.set_text_color(255, 255, 255)
                col_w = [70, 30, 30, 30]
                headers = ["Specification", "Coef", "p-value", "Sig"]
                for i, h in enumerate(headers):
                    pdf.cell(col_w[i], 6, h, border=1, fill=True, align="C")
                pdf.ln(6)
                pdf.set_text_color(0, 0, 0)
                pdf.set_font("Helvetica", "", 8)
                for idx, r in enumerate(rob_rows[:10]):
                    label = _col(r, spec_cols) or "?"
                    att = _col(r, coef_cols, as_float=True)
                    p_val = _col(r, p_cols, as_float=True)
                    if att is None:
                        continue
                    sig_str = ""
                    if p_val is not None:
                        if p_val < 0.01:
                            sig_str = "***"
                        elif p_val < 0.05:
                            sig_str = "**"
                        elif p_val < 0.1:
                            sig_str = "*"
                    # Alternate row colors
                    if idx % 2 == 0:
                        pdf.set_fill_color(245, 245, 245)
                    else:
                        pdf.set_fill_color(255, 255, 255)
                    pdf.cell(col_w[0], 5, _safe(str(label)[:35]),
                             border=1, fill=True)
                    pdf.cell(col_w[1], 5, "%+.4f" % att,
                             border=1, fill=True, align="R")
                    pdf.cell(col_w[2], 5,
                             "%.4f" % p_val if p_val is not None else "N/A",
                             border=1, fill=True, align="R")
                    pdf.cell(col_w[3], 5, sig_str,
                             border=1, fill=True, align="C")
                    pdf.ln(5)

        if not main_path.exists() and not robustness_path.exists():
            pdf.body_text("No main_results.csv or robustness_results.csv found.")

        # ================================================================
        # SECTION 3: DATA LIMITATIONS
        # ================================================================
        pdf.add_page()
        pdf.section_title("3. Data Limitations")

        stage1 = state.get("stages", {}).get("stage1", {})
        data_profile = stage1.get("data_profile", {})
        structure = data_profile.get("structure", "unknown")

        pdf.sub_title("Data summary")
        rows_val = data_profile.get("rows", 0)
        pdf.body_text(
            "Rows: %s  |  Columns: %s  |  Structure: %s" % (
                "{:,}".format(rows_val) if rows_val else "?",
                data_profile.get("cols", "?"),
                structure,
            )
        )

        # Detect design type
        selected_idea = (state.get("stages", {}).get("stage2_5", {})
                         .get("selected_idea", {}))
        id_level = selected_idea.get("identification_level", "")
        method = selected_idea.get("method", "").lower()

        limitations = []

        # Structure-specific
        if structure == "cross-sectional":
            limitations.append((
                "Cross-sectional data",
                "Single time snapshot. Cannot control for time-invariant unobservables "
                "or track changes over time. Causal claims rely entirely on "
                "randomization or instrumental variable assumptions."
            ))
        elif structure in ("panel", "wide-panel"):
            limitations.append((
                "Panel attrition",
                "If units drop out of the panel over time, the remaining sample may "
                "be non-representative. Check attrition rates and Lee bounds."
            ))

        # Design-specific
        is_rct = any(kw in method for kw in [
            "rct", "experiment", "randomiz", "vignette", "factorial"])
        is_did = any(kw in method for kw in [
            "did", "diff", "synthetic", "ban", "restriction", "natural experiment"])
        is_iv = any(kw in method for kw in ["iv", "instrumental", "2sls"])

        if is_rct and not is_did:
            limitations.append((
                "External validity",
                "Experimental results may not generalize beyond the study sample. "
                "The specific population, setting, and time period limit extrapolation."
            ))
            limitations.append((
                "Demand effects",
                "Survey/lab experiments may be subject to demand effects where "
                "respondents guess the hypothesis and adjust their responses."
            ))
        elif is_did:
            limitations.append((
                "Parallel trends assumption",
                "DiD identification relies on treated and control units following "
                "the same trajectory absent treatment. Violated pre-trends bias "
                "the estimate."
            ))
            limitations.append((
                "Confounders concurrent with treatment",
                "Other events at the same time as treatment (wars, policy changes, "
                "economic shocks) may confound the estimated effect."
            ))
        elif is_iv:
            limitations.append((
                "Exclusion restriction",
                "IV validity requires the instrument affects the outcome ONLY "
                "through the treatment. Violations bias the estimate."
            ))
        elif id_level == "C" or "simultaneous" in method:
            limitations.append((
                "No control group",
                "All units received the same treatment simultaneously. Cannot "
                "separate the treatment effect from other concurrent shocks."
            ))

        # Sample size
        if rows_val and rows_val < 1000:
            limitations.append((
                "Small sample",
                "With N=%d, the study may be underpowered to detect small but "
                "meaningful effects. Report minimum detectable effect (MDE)." % rows_val
            ))

        # Unresolved referee concerns
        review_dir = project_dir / "reviews"
        must_issues_lim = _read_must_issues(review_dir, limit=3)
        if must_issues_lim:
            limitations.append((
                "Unresolved referee concerns",
                "The following issues were flagged by referees and may limit "
                "publishability: " + "; ".join(
                    str(m)[:150] for m in must_issues_lim)
            ))

        if not limitations:
            limitations.append((
                "General",
                "All empirical studies have limitations. Consult referee feedback "
                "for specific concerns about this paper."
            ))

        for lim_title, lim_text in limitations:
            pdf.sub_title(lim_title)
            pdf.body_text(lim_text)

        # ================================================================
        # SECTION 4: VALIDATOR RESULTS
        # ================================================================
        pdf.section_title("4. Validator Results")

        for val_name, val_obj in [("Code", code_val),
                                  ("Paper", paper_val),
                                  ("Integration", integration_val)]:
            counts = val_obj.summary_counts
            h_pass = counts.get("hard_passed", counts.get("hard_pass", 0))
            h_total = counts.get("hard_total", 0)
            s_pass = counts.get("soft_passed", counts.get("soft_pass", 0))
            s_total = counts.get("soft_total", 0)

            # Color badge for validator
            if h_pass == h_total and h_total > 0:
                badge_r, badge_g, badge_b = 76, 175, 80
            elif h_pass >= h_total * 0.7:
                badge_r, badge_g, badge_b = 255, 193, 7
            else:
                badge_r, badge_g, badge_b = 244, 67, 54

            pdf.ln(2)
            pdf.color_badge(
                "%s: %d/%d hard, %d/%d soft" % (
                    val_name, h_pass, h_total, s_pass, s_total),
                badge_r, badge_g, badge_b, w=90, h=7)
            pdf.ln(9)

            # List only FAIL items
            fail_items = [c for c in val_obj.checks if not c.passed]
            if fail_items:
                for check in fail_items:
                    pdf.set_font("Helvetica", "", 9)
                    pdf.set_text_color(198, 40, 40)
                    pdf.cell(8, 5, "X", new_x="END")
                    pdf.set_text_color(0, 0, 0)
                    detail_text = "%s: %s" % (check.name, check.detail)
                    pdf.multi_cell(0, 5, _safe(detail_text[:200]))
                    pdf.ln(1)
            else:
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(76, 175, 80)
                pdf.cell(0, 5, "All checks passed.", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(0, 0, 0)
                pdf.ln(2)

        # ================================================================
        # SECTION 5: RECOMMENDATIONS
        # ================================================================
        pdf.add_page()
        pdf.section_title("5. Recommendations")

        # Referee must-address issues first
        must_issues = _read_must_issues(review_dir)
        if must_issues:
            pdf.sub_title("Referee must-address issues")
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(0, 5, "These issues were flagged by simulated referees during peer review.",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
            for i, issue in enumerate(must_issues[:8], 1):
                # Priority badge
                pdf.set_fill_color(244, 67, 54)
                pdf.set_text_color(255, 255, 255)
                pdf.set_font("Helvetica", "B", 7)
                badge_w = 28
                pdf.rect(pdf.get_x(), pdf.get_y(), badge_w, 5, "F")
                pdf.cell(badge_w, 5, "ISSUE #%d" % i, align="C")
                pdf.set_text_color(0, 0, 0)
                pdf.set_font("Helvetica", "", 9)
                pdf.cell(2, 5, " ")
                # Don't truncate — let multi_cell wrap the full text
                pdf.multi_cell(0, 4.5, _safe(str(issue)))
                pdf.ln(2)

        # Generic recommendations based on scores
        pdf.sub_title("Score-based recommendations")
        recs = []
        if components.get("identification", 0) < 90:
            recs.append((
                "HIGH IMPACT", 244, 67, 54,
                "Improve identification strategy",
                "Add exogenous variation: natural experiments, policy "
                "discontinuities, staggered rollout, or IVs. RCTs score highest."
            ))
        if components.get("code", 0) < 90:
            recs.append((
                "MEDIUM", 255, 193, 7,
                "Improve code quality",
                "Address referee checklist gaps. Use validated packages (pyfixest, "
                "linearmodels). Add missing robustness checks."
            ))
        if components.get("paper", 0) < 90:
            recs.append((
                "MEDIUM", 255, 193, 7,
                "Expand paper content",
                "Target 8,000-12,000 words. Ensure abstract numbers match "
                "results_summary. Add data appendix."
            ))
        if components.get("polish", 0) < 80:
            recs.append((
                "LOW", 180, 180, 180,
                "Address referee feedback",
                "Polish improves when identification and code improve. "
                "Focus on must-address issues listed above."
            ))

        for priority_tag, pr, pg, pb, rec_title, detail in recs:
            # Color-coded priority tag
            pdf.set_fill_color(pr, pg, pb)
            tw = 32 if priority_tag != "HIGH IMPACT" else 38
            pdf.rect(pdf.get_x(), pdf.get_y(), tw, 5, "F")
            pdf.set_font("Helvetica", "B", 7)
            if pr < 200 and pg < 200:
                pdf.set_text_color(255, 255, 255)
            else:
                pdf.set_text_color(0, 0, 0)
            pdf.cell(tw, 5, "[%s]" % priority_tag, align="C")
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(2, 5, " ")
            pdf.cell(0, 5, _safe(rec_title), new_x="LMARGIN", new_y="NEXT")
            pdf.body_text(detail)

        # ================================================================
        # SECTION 6: SCORE IMPACT ESTIMATES
        # ================================================================
        pdf.section_title("6. Score Impact Estimates")

        # Estimate ceiling based on identification
        id_score = components.get("identification", 0)
        if id_score >= 90:
            ceiling = 92
        elif id_score >= 80:
            ceiling = 88
        elif id_score >= 70:
            ceiling = 82
        else:
            ceiling = 75

        pdf.sub_title("Estimated ceiling: ~%d / 100" % ceiling)
        pdf.body_text(
            "Current aggregate: %.1f. With the current identification strategy, "
            "the practical ceiling is ~%d. Reaching 90+ requires RCT or strong "
            "natural experiment data." % (aggregate, ceiling)
        )

        pdf.sub_title("Improvement estimates")
        improvements = []
        if components.get("identification", 0) < 90:
            improvements.append((
                "Stronger identification (RCT or natural experiment)",
                "+10 to +20 identification"
            ))
        if components.get("code", 0) < 85:
            improvements.append((
                "Fix code validator soft failures",
                "+5 to +10 code"
            ))
        if components.get("paper", 0) < 85:
            improvements.append((
                "Expand paper to 8,000+ words",
                "+5 paper"
            ))
            improvements.append((
                "Ensure abstract numbers match results",
                "+3 paper, +3 integration"
            ))
        if components.get("polish", 0) < 80:
            improvements.append((
                "Address all referee must-address issues",
                "+5 to +10 polish"
            ))
        improvements.append((
            "Address all SHOULD-address issues",
            "+3 to +5 polish"
        ))

        # Show as mini-table
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(0, 51, 102)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(120, 6, "Improvement", border=1, fill=True)
        pdf.cell(50, 6, "Estimated Impact", border=1, fill=True, align="C")
        pdf.ln(6)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 9)
        for idx, (improvement, impact) in enumerate(improvements):
            if idx % 2 == 0:
                pdf.set_fill_color(245, 245, 245)
            else:
                pdf.set_fill_color(255, 255, 255)
            pdf.cell(120, 5, _safe(improvement[:60]), border=1, fill=True)
            pdf.cell(50, 5, _safe(impact), border=1, fill=True, align="C")
            pdf.ln(5)

        # ── Save ──
        output_path = project_dir / "feedback.pdf"
        pdf.output(str(output_path))
        print("  [7e] Saved: %s" % output_path)

    except Exception as exc:
        print("  [7e] Feedback PDF generation failed: %s" % str(exc))
