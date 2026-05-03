"""Stage 4.7 — Code Review (review-paper-code skill with correction loop).

Uses the review-paper-code skill logic to review scripts for reproducibility,
code quality, and paper-code alignment. If critical issues are found, Claude
auto-corrects the scripts and re-runs the review (max 3 iterations).

Runs between Stage 4.5 (data audit) and Stage 5 (writing).
"""

import shutil
from datetime import datetime
from pathlib import Path

from ..config import get_profile, PAPERS_HQ
from ..claude_runner import run_claude, run_claude_parallel
from ..json_utils import extract_json, smart_truncate
from ..state import save_state

MAX_CODE_REVIEW_ROUNDS = 3  # max correction iterations


def _backup_scripts(scripts_dir: Path, round_num: int) -> Path:
    """Create a backup of all scripts before correction.

    Returns the backup directory path.
    """
    backup_dir = scripts_dir.parent / f"backup_r{round_num}"
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    backup_dir.mkdir(parents=True)

    for script in sorted(scripts_dir.glob("[0-9]*.py")):
        shutil.copy2(script, backup_dir / script.name)

    print(f"  [4.7] Backed up {len(list(backup_dir.glob('*.py')))} scripts to {backup_dir.name}/")
    return backup_dir


def _rollback_scripts(scripts_dir: Path, backup_dir: Path) -> None:
    """Restore scripts from backup after a failed correction."""
    restored = 0
    for backup_file in sorted(backup_dir.glob("*.py")):
        target = scripts_dir / backup_file.name
        shutil.copy2(backup_file, target)
        restored += 1
    print(f"  [4.7] ROLLBACK: restored {restored} scripts from {backup_dir.name}/")


def _read_file_or(path: Path, default: str = "") -> str:
    return path.read_text(encoding="utf-8") if path.exists() else default


def _gather_code_files(scripts_dir: Path) -> dict[str, str]:
    """Read all Python scripts in the scripts directory."""
    files = {}
    for script in sorted(scripts_dir.glob("[0-9]*.py")):
        files[script.name] = script.read_text(encoding="utf-8")
    return files


def _gather_paper_summary(project_dir: Path) -> str:
    """Build a compact paper summary from available sources."""
    parts = []

    # Strategy memo (contains research question, method, variables)
    strategy = project_dir / "strategy" / "strategy_memo.md"
    if strategy.exists():
        parts.append(f"## Strategy Memo\n{smart_truncate(strategy.read_text(encoding='utf-8'), 3000)}")

    # Selected idea (contains research question)
    idea = project_dir / "selected_idea.md"
    if idea.exists():
        parts.append(f"## Selected Idea\n{smart_truncate(idea.read_text(encoding='utf-8'), 2000)}")

    # Referee checklist (contains expected outputs)
    checklist = project_dir / "strategy" / "referee_checklist.md"
    if checklist.exists():
        parts.append(f"## Referee Checklist\n{smart_truncate(checklist.read_text(encoding='utf-8'), 2000)}")

    # Results summary
    for loc in [
        project_dir / "scripts" / "python" / "results_summary.md",
        project_dir / "paper" / "tables" / "results_summary.md",
    ]:
        if loc.exists():
            parts.append(f"## Results Summary\n{smart_truncate(loc.read_text(encoding='utf-8'), 2000)}")
            break

    return "\n\n".join(parts) if parts else "(no paper context available)"


def _build_code_text(code_files: dict[str, str]) -> str:
    """Format code files for inclusion in prompts."""
    parts = []
    for name, content in code_files.items():
        parts.append(f"### {name}\n```python\n{content}\n```")
    return "\n\n".join(parts)


def _run_code_review(project_dir: Path, code_files: dict[str, str],
                     paper_summary: str, round_num: int) -> tuple[str, dict]:
    """Run the 2-agent code review (reproducibility + paper-code mapping).

    Returns (full_report_text, parsed_result_dict).
    """
    scripts_dir = project_dir / "scripts" / "python"
    code_text = _build_code_text(code_files)
    code_file_list = ", ".join(code_files.keys())

    # ── Agent A: Code Reproducibility and Quality ─────────────────────────
    agent_a_prompt = f"""You are reviewing research code for reproducibility and code quality
in a social science / economics project.

Reviewed code files: {code_file_list}
Code directory: {scripts_dir}

--- CODE ---
{code_text}

Review the files and produce a compact report focused on the most decision-relevant findings.

Check:
1. Hardcoded absolute paths or machine-specific assumptions
2. Randomized procedures without an obvious seed
3. Outputs that appear to be consumed but not generated in the pipeline
4. Data inputs and path conventions consistency
5. Dependency management and software requirements
6. Run order and presence of a master script or documented pipeline
7. Large commented-out blocks, weak script structure, or hard-to-follow long files
8. Opaque transformations, unexplained filters, recodes, merges, or thresholds

Use these labels:
- PASS: looks solid
- NOTE: minor improvement opportunity
- VERIFY: worth human confirmation
- MISSING: expected file or documentation is absent
- CRITICAL: must be fixed before proceeding

Output exactly these sections:

## Overall
3-6 bullets on the overall state of the codebase.

## Top Findings
Up to 10 items total, ordered by importance.
Format each item as:
- [LABEL] Short finding title — file(s): line reference(s) — why it matters — what to fix

## Strengths
3-8 bullets with genuine positives.

## Reproducibility Checklist
One line each for: Relative paths, Random seed, Outputs generated, Dependency management, Run order, Documentation.
Format: - Check name: PASS / NOTE / VERIFY / MISSING / CRITICAL — brief note

Also output a JSON block at the end:
```json
{{
  "critical_issues": [
    {{"file": "filename.py", "description": "...", "fix": "concrete suggestion"}}
  ],
  "n_critical": 0,
  "n_notes": 0,
  "overall_status": "PASS|NEEDS_FIX"
}}
```
"""

    # ── Agent B: Paper-to-Code Mapping ────────────────────────────────────
    agent_b_prompt = f"""You are mapping a research project's empirical strategy to its code implementation.

--- PAPER CONTEXT (strategy, research question, expected outputs) ---
{paper_summary}

--- CODE ---
{code_text}

Read the code files and identify whether the paper's core empirical design appears in the code.

Focus on:
1. Main tables and figures: are they generated by the code?
2. Main variables and treatments: are they constructed correctly?
3. Main sample restrictions and time period: do they match?
4. Main estimation methods: are the right packages/functions used?
5. Fixed effects and clustering: do they match the strategy?
6. Output files: are all expected outputs actually produced?

Use these confidence labels:
- HIGH: clear and specific match
- MEDIUM: plausible match but not airtight
- LOW: weak or indirect match
- NOT FOUND: no plausible match found
- MISMATCH: paper and code appear to contradict each other

Output exactly these sections:

## Verified Matches
Up to 10 bullets. Format: - Paper element -> Code evidence -> HIGH/MEDIUM -> note

## Items To Verify
Up to 12 bullets. Format: - Paper element -> Code evidence/absence -> LOW/NOT FOUND/MEDIUM -> why

## Likely Discrepancies
Only items where paper and code appear to point in different directions. Up to 8 bullets.

## Coverage Notes
3-6 bullets on what was easy to match and what was ambiguous.

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

    # ── Run both agents in parallel ───────────────────────────────────────
    print(f"  [4.7] Running code review agents (round {round_num}/{MAX_CODE_REVIEW_ROUNDS})...")
    pr = get_profile("stage4_7_review")

    review_dir = project_dir / "quality_reports"
    review_dir.mkdir(exist_ok=True)
    suffix = f"_r{round_num}" if round_num > 1 else ""

    responses = run_claude_parallel([
        {
            "prompt": agent_a_prompt, "model": pr["model"], "effort": pr["effort"],
            "output_file": review_dir / f"code_reproducibility{suffix}.md",
            "label": "code-reproducibility",
            "allowed_tools": [],
        },
        {
            "prompt": agent_b_prompt, "model": pr["model"], "effort": pr["effort"],
            "output_file": review_dir / f"code_paper_mapping{suffix}.md",
            "label": "paper-code-mapping",
            "allowed_tools": [],
        },
    ], max_workers=2)

    # Parse results
    repro_result = extract_json(responses[0]) or {
        "critical_issues": [], "n_critical": 0, "overall_status": "PASS"
    }
    mapping_result = extract_json(responses[1]) or {
        "critical_mismatches": [], "n_mismatches": 0, "overall_alignment": "GOOD"
    }

    # Combine into a single result
    all_critical = (
        repro_result.get("critical_issues", [])
        + mapping_result.get("critical_mismatches", [])
    )

    combined = {
        "repro_result": repro_result,
        "mapping_result": mapping_result,
        "all_critical": all_critical,
        "n_critical": len(all_critical),
        "needs_fix": (
            repro_result.get("overall_status") == "NEEDS_FIX"
            or mapping_result.get("overall_alignment") == "NEEDS_FIX"
        ),
    }

    # Build full report text
    full_report = (
        f"# Code Review Report (Round {round_num})\n\n"
        f"## Reproducibility & Quality\n\n{responses[0]}\n\n"
        f"## Paper-Code Alignment\n\n{responses[1]}\n\n"
    )

    report_path = review_dir / f"code_review_report{suffix}.md"
    report_path.write_text(full_report, encoding="utf-8")
    print(f"  [saved] {report_path}")

    return full_report, combined


def _run_code_correction(project_dir: Path, code_files: dict[str, str],
                         review_report: str, critical_issues: list[dict]) -> bool:
    """Use Claude to fix critical issues in the scripts via targeted diffs.

    Instead of rewriting entire scripts (which risks breaking working code),
    outputs only the specific changes needed as search-replace pairs.

    Returns True if corrections were made, False otherwise.
    """
    scripts_dir = project_dir / "scripts" / "python"
    code_text = _build_code_text(code_files)

    # Gather data context so Claude knows actual column names
    clean_csv = project_dir / "data" / "clean" / "clean_data.csv"
    data_context = ""
    if clean_csv.exists():
        try:
            import pandas as pd
            df = pd.read_csv(clean_csv, nrows=0, encoding="latin-1")
            cols = list(df.columns)
            data_context = (
                f"\n--- DATA CONTEXT (actual columns in clean_data.csv) ---\n"
                f"Columns ({len(cols)}): {', '.join(cols[:80])}\n"
            )
            if len(cols) > 80:
                data_context += f"... and {len(cols) - 80} more\n"
        except Exception:
            pass

    issues_text = "\n".join(
        f"  {i+1}. [{issue.get('file', issue.get('paper_element', '?'))}] "
        f"{issue.get('description', issue.get('code_evidence', '?'))} "
        f"-> Fix: {issue.get('fix', 'N/A')}"
        for i, issue in enumerate(critical_issues)
    )

    fix_prompt = f"""You are fixing critical issues in Python research scripts.
You must output ONLY the minimal changes needed — do NOT rewrite entire scripts.

--- CRITICAL ISSUES TO FIX ---
{issues_text}
{data_context}
--- CURRENT CODE ---
{code_text}

For each fix, output a SEARCH-REPLACE block. The SEARCH block must match the
existing code EXACTLY (including whitespace). The REPLACE block contains the
corrected code. Format:

### Fix N: [description]
File: [filename.py]
```search
exact existing code to find
```
```replace
corrected code
```

RULES:
- Output ONLY the lines that need to change, with enough surrounding context
  to match uniquely (3-5 lines before/after)
- NEVER change lines that are not related to the critical issue
- Use validated packages (pyfixest, linearmodels, etc.)
- Use ONLY column names that exist in the data context above
- Add a "# FIX: " comment on the changed line explaining the change
- If you are unsure about a fix, output it as a SUGGESTION instead of a fix:
  ### Suggestion N: [description] — NEEDS HUMAN REVIEW

After all fixes, output a JSON block:
```json
{{
  "files_modified": ["00_clean.py"],
  "fixes_applied": [
    {{"file": "filename.py", "description": "what was fixed", "confidence": "high|medium"}}
  ],
  "suggestions": [
    {{"file": "filename.py", "description": "what might need changing", "reason": "why unsure"}}
  ],
  "n_fixes": 1,
  "n_suggestions": 0
}}
```
"""

    print(f"  [4.7] Correcting {len(critical_issues)} critical issues (targeted diffs)...")
    pr = get_profile("stage4_7_fix")

    response = run_claude(
        fix_prompt, model=pr["model"], effort=pr["effort"],
        output_file=project_dir / "quality_reports" / "code_fixes_applied.md",
        label="code-correction",
        allowed_tools=[],
    )

    # Parse and apply search-replace corrections
    import re
    corrections_applied = 0
    corrections_failed = 0

    # Find all File: lines followed by search/replace blocks
    file_pattern = re.compile(r'File:\s*(\S+\.py)')
    search_pattern = re.compile(r'```search\s*\n(.*?)\n```', re.DOTALL)
    replace_pattern = re.compile(r'```replace\s*\n(.*?)\n```', re.DOTALL)

    # Split response into fix blocks
    fix_blocks = re.split(r'###\s+(?:Fix|Suggestion)\s+\d+', response)

    for block in fix_blocks:
        file_match = file_pattern.search(block)
        search_match = search_pattern.search(block)
        replace_match = replace_pattern.search(block)

        if not (file_match and search_match and replace_match):
            continue

        # Skip suggestions (need human review)
        if "NEEDS HUMAN REVIEW" in block:
            print(f"  [suggestion] {file_match.group(1)}: needs human review — skipped")
            continue

        filename = file_match.group(1)
        search_text = search_match.group(1)
        replace_text = replace_match.group(1)

        if search_text == replace_text:
            continue

        target = scripts_dir / filename
        if not target.exists():
            print(f"  [skip] {filename}: file not found")
            corrections_failed += 1
            continue

        content = target.read_text(encoding="utf-8")
        if search_text in content:
            new_content = content.replace(search_text, replace_text, 1)

            # Validate the patched script before overwriting:
            # 1. Must be parseable Python (catches truncated/garbled LLM output).
            # 2. Must not shrink by more than half (catches accidental wipes).
            # On failure, write the rejected payload to a sibling .rejected
            # file for forensics and keep the original intact.
            import ast as _ast_v
            ok = True
            reason = ""
            if len(new_content) < max(50, len(content) // 2):
                ok = False
                reason = (
                    f"shrank from {len(content)} to {len(new_content)} bytes"
                )
            else:
                try:
                    _ast_v.parse(new_content)
                except SyntaxError as exc:
                    ok = False
                    reason = f"SyntaxError after patch: {exc.msg} at line {exc.lineno}"

            if not ok:
                rej = target.with_suffix(target.suffix + ".rejected")
                try:
                    rej.write_text(new_content, encoding="utf-8")
                except OSError:
                    pass
                print(
                    f"  [skip] {filename}: REJECTED auto-fix — {reason}. "
                    f"Original kept; rejected payload at {rej.name}"
                )
                corrections_failed += 1
                continue

            try:
                target.with_suffix(target.suffix + ".bak").write_text(
                    content, encoding="utf-8")
            except OSError:
                pass
            target.write_text(new_content, encoding="utf-8")
            corrections_applied += 1
            print(f"  [fix] {filename}: applied targeted fix")
        else:
            print(f"  [skip] {filename}: search text not found in file (code may have changed)")
            corrections_failed += 1

    fix_result = extract_json(response) or {}
    n_suggestions = len(fix_result.get("suggestions", []))
    print(f"  [4.7] Applied {corrections_applied} fixes, "
          f"{corrections_failed} failed, {n_suggestions} suggestions for human review")

    if n_suggestions > 0:
        print(f"  [4.7] Suggestions (need human review):")
        for s in fix_result.get("suggestions", []):
            print(f"    - {s.get('file', '?')}: {s.get('description', '?')}")

    return corrections_applied > 0


def _validate_figures(project_dir: Path) -> list[dict]:
    """Validate all generated figures for common problems.

    Checks:
    1. File exists and is non-trivially small (empty/blank plot)
    2. Image has sufficient color variance (not a flat line or blank canvas)
    3. No duplicate figures (identical content)

    Returns list of issues found.
    """
    import hashlib

    figures_dir = project_dir / "paper" / "figures"
    if not figures_dir.exists():
        return []

    issues = []
    fig_hashes = {}  # hash -> filename

    for fig_path in sorted(figures_dir.glob("*")):
        if fig_path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".pdf", ".svg"):
            continue

        name = fig_path.name
        size = fig_path.stat().st_size

        # Check 1: File too small (likely empty/broken)
        if size < 1000:
            issues.append({
                "file": name,
                "issue": f"File is only {size} bytes — likely empty or broken",
                "severity": "CRITICAL",
            })
            print(f"  [fig] CRITICAL: {name} is only {size} bytes (empty/broken)")
            continue

        # Check 2: For PNG files, verify image has content variance
        if fig_path.suffix.lower() == ".png":
            try:
                from PIL import Image
                import numpy as _np
                img = Image.open(fig_path).convert("L")  # grayscale
                pixels = _np.array(img)
                std = pixels.std()
                if std < 5.0:
                    issues.append({
                        "file": name,
                        "issue": f"Image appears blank or flat (pixel std={std:.1f})",
                        "severity": "CRITICAL",
                    })
                    print(f"  [fig] CRITICAL: {name} appears blank (std={std:.1f})")
            except ImportError:
                # PIL not available, skip pixel check but still check size + hash
                pass
            except Exception:
                pass

        # Check 3: Hash for duplicate detection
        content_hash = hashlib.md5(fig_path.read_bytes()).hexdigest()
        if content_hash in fig_hashes:
            other = fig_hashes[content_hash]
            issues.append({
                "file": name,
                "issue": f"Duplicate of {other} (identical content)",
                "severity": "CRITICAL",
            })
            print(f"  [fig] CRITICAL: {name} is a duplicate of {other}")
        else:
            fig_hashes[content_hash] = name

    if not issues:
        n_figs = len(fig_hashes)
        print(f"  [fig] All {n_figs} figures validated OK (no blanks, no duplicates)")

    return issues


def _validate_tables(project_dir: Path) -> list[dict]:
    """Validate all generated LaTeX tables for common problems.

    Checks:
    1. Tables don't have empty/NaN cells (from failed estimators)
    2. Tables are not trivially small
    3. Tables have required structural elements (booktabs, notes)

    Returns list of issues found.
    """
    import re

    tables_dir = project_dir / "paper" / "tables"
    if not tables_dir.exists():
        return []

    issues = []

    for tex_path in sorted(tables_dir.glob("*.tex")):
        name = tex_path.name
        content = tex_path.read_text(encoding="utf-8")

        # Check 1: Empty/NaN cells — look for empty & cells or NaN in content
        # Pattern: "& &" or "& \\" means empty cell
        empty_cells = len(re.findall(r'&\s*&', content))
        empty_cells += len(re.findall(r'&\s*\\\\', content))  # also count empty last column
        nan_cells = content.lower().count("nan")

        if nan_cells > 0:
            issues.append({
                "file": name,
                "issue": f"Contains {nan_cells} NaN value(s) — estimator likely failed",
                "severity": "CRITICAL",
            })
            print(f"  [tab] CRITICAL: {name} has {nan_cells} NaN cells")

        if empty_cells > 3:
            issues.append({
                "file": name,
                "issue": f"{empty_cells} empty cells — results may be missing",
                "severity": "CRITICAL",
            })
            print(f"  [tab] CRITICAL: {name} has {empty_cells} empty cells")

        # Check 2: File too small (likely stub/broken)
        if len(content.strip()) < 100:
            issues.append({
                "file": name,
                "issue": "Table file is nearly empty (<100 chars)",
                "severity": "CRITICAL",
            })
            print(f"  [tab] CRITICAL: {name} is nearly empty")

        # Check 3: Missing booktabs structure
        if "\\toprule" not in content and "\\hline" not in content:
            issues.append({
                "file": name,
                "issue": "No \\toprule or \\hline — table may lack structure",
                "severity": "WARNING",
            })

    if not issues:
        n_tabs = len(list(tables_dir.glob("*.tex")))
        print(f"  [tab] All {n_tabs} tables validated OK (no NaN, no empty cells)")

    return issues


def _rerun_validation(project_dir: Path, state: dict,
                      backup_dir: Path | None = None) -> bool:
    """Re-execute scripts and re-run data audit after corrections.

    If scripts fail and a backup_dir is provided, automatically rolls back.
    Returns True if validation passed, False if rolled back or failed.
    """
    from .stage4_5_data_audit import run as run_data_audit
    from ..python_runner import run_with_retry

    scripts_dir = project_dir / "scripts" / "python"

    # Step 1: Re-execute scripts to verify they still run
    py_scripts = sorted(scripts_dir.glob("[0-9]*.py"))
    if py_scripts:
        print(f"  [4.7] Re-executing {len(py_scripts)} scripts after correction...")
        all_ok = True
        for script in py_scripts:
            result = run_with_retry(script, cwd=scripts_dir)
            if not result["ok"]:
                print(f"  [FAIL] {script.name} broke after correction!")
                all_ok = False
            else:
                print(f"  [ok] {script.name} runs successfully")

        if not all_ok:
            if backup_dir and backup_dir.exists():
                _rollback_scripts(scripts_dir, backup_dir)
                print(f"  [4.7] Scripts restored to pre-correction state.")
            else:
                print(f"  [4.7] WARNING: Corrections broke scripts and no backup available!")
            return False

    # Step 2: Validate figures and tables
    print(f"  [4.7] Validating generated figures and tables...")
    fig_issues = _validate_figures(project_dir)
    tab_issues = _validate_tables(project_dir)
    all_output_issues = fig_issues + tab_issues
    critical_output = [i for i in all_output_issues if i["severity"] == "CRITICAL"]
    if critical_output:
        print(f"  [4.7] {len(critical_output)} output problem(s) detected after correction.")
        # Don't rollback — these need code fixes in the next review round

    # Step 3: Re-run data audit
    state["stages"]["stage4_5"] = {}
    print(f"  [4.7] Re-running data audit after corrections...")
    state = run_data_audit(project_dir, state)

    n_critical = state["stages"].get("stage4_5", {}).get("n_critical", 0)
    if n_critical > 0 and backup_dir and backup_dir.exists():
        print(f"  [4.7] Data audit found {n_critical} new critical issues after correction.")
        _rollback_scripts(scripts_dir, backup_dir)
        print(f"  [4.7] Scripts restored — correction caused data issues.")
        return False

    return n_critical == 0


def run(project_dir: Path, state: dict) -> dict:
    """Execute Stage 4.7: code review with correction loop."""

    # Skip if already completed
    if state["stages"].get("stage4_7", {}).get("status") == "completed":
        print("  [4.7] Already completed — skipping.")
        return state

    scripts_dir = project_dir / "scripts" / "python"

    # Check scripts exist
    code_files = _gather_code_files(scripts_dir)
    if not code_files:
        print("  [4.7] No scripts found — skipping code review.")
        state["stages"]["stage4_7"] = {
            "status": "completed",
            "reason": "no_scripts",
            "completed_at": datetime.now().isoformat(),
        }
        save_state(project_dir, state)
        return state

    print(f"  [4.7] Reviewing {len(code_files)} scripts: {', '.join(code_files.keys())}")

    # Gather paper context for mapping agent
    paper_summary = _gather_paper_summary(project_dir)

    # ── Validate figures and tables before review ──────────────────────
    print(f"\n  [4.7] Validating generated figures...")
    fig_issues = _validate_figures(project_dir)
    if fig_issues:
        for fi in fig_issues:
            print(f"  [4.7] Figure issue: {fi['file']} — {fi['issue']}")

    print(f"  [4.7] Validating generated tables...")
    tab_issues = _validate_tables(project_dir)
    if tab_issues:
        for ti in tab_issues:
            print(f"  [4.7] Table issue: {ti['file']} — {ti['issue']}")

    # ── Correction loop ─────────────────────────────────────────────────
    round_num = 0
    final_result = {}
    failed_fixes: list[str] = []  # Track issues that failed to fix (avoid retrying)

    for round_num in range(1, MAX_CODE_REVIEW_ROUNDS + 1):
        # Re-read code files (may have been corrected in previous round)
        code_files = _gather_code_files(scripts_dir)

        # Run review
        report_text, result = _run_code_review(
            project_dir, code_files, paper_summary, round_num
        )
        final_result = result

        n_critical = result.get("n_critical", 0)
        needs_fix = result.get("needs_fix", False)

        print(f"  [4.7] Round {round_num}: {n_critical} critical issues, "
              f"needs_fix={needs_fix}")

        # If no critical issues, we're done
        if n_critical == 0 and not needs_fix:
            print(f"  [4.7] PASS — no critical issues found.")
            break

        # If this is the last round, don't try to fix
        if round_num == MAX_CODE_REVIEW_ROUNDS:
            print(f"  [4.7] Max rounds reached ({MAX_CODE_REVIEW_ROUNDS}). "
                  f"Flagging {n_critical} unresolved issues for user.")
            break

        # Try to auto-correct
        critical_issues = result.get("all_critical", [])
        if critical_issues:
            # Filter out issues that already failed in a previous round
            def _issue_key(issue: dict) -> str:
                return (issue.get("file", issue.get("paper_element", ""))
                        + ":" + issue.get("description", issue.get("code_evidence", ""))[:80])

            new_issues = [
                iss for iss in critical_issues
                if _issue_key(iss) not in failed_fixes
            ]

            if not new_issues:
                print(f"  [4.7] All {len(critical_issues)} critical issues already "
                      f"failed to fix in previous rounds — stopping loop.")
                break

            if len(new_issues) < len(critical_issues):
                skipped = len(critical_issues) - len(new_issues)
                print(f"  [4.7] Skipping {skipped} issues that failed before. "
                      f"Attempting {len(new_issues)} new/different issues.")

            # Backup scripts before any correction attempt
            backup_dir = _backup_scripts(scripts_dir, round_num)

            corrected = _run_code_correction(
                project_dir, code_files, report_text, new_issues
            )

            if corrected:
                # Re-execute + data audit; rollback automatically if broken
                validation_ok = _rerun_validation(project_dir, state, backup_dir)
                if not validation_ok:
                    # Correction broke something — record these issues as failed
                    for iss in new_issues:
                        failed_fixes.append(_issue_key(iss))
                    print(f"  [4.7] Correction rolled back — {len(new_issues)} "
                          f"issues marked as unfixable automatically.")
            else:
                # No corrections applied — record issues as failed
                for iss in new_issues:
                    failed_fixes.append(_issue_key(iss))
                print(f"  [4.7] No corrections applied — stopping loop.")
                break
        else:
            # needs_fix but no parseable critical issues
            print(f"  [4.7] Review flagged issues but couldn't parse specifics — "
                  f"continuing to Stage 5.")
            break

    # ── Save state ────────────────────────────────────────────────────────
    n_critical = final_result.get("n_critical", 0)
    needs_fix = final_result.get("needs_fix", False)

    # Determine if we need human intervention
    needs_human = n_critical > 0 and round_num == MAX_CODE_REVIEW_ROUNDS

    # Final figure + table validation
    final_fig_issues = _validate_figures(project_dir)
    final_tab_issues = _validate_tables(project_dir)
    n_fig_issues = len([f for f in final_fig_issues if f["severity"] == "CRITICAL"])
    n_tab_issues = len([t for t in final_tab_issues if t["severity"] == "CRITICAL"])

    state["stages"]["stage4_7"] = {
        "status": "completed",
        "rounds": round_num,
        "n_critical_remaining": n_critical,
        "n_figure_issues": n_fig_issues,
        "n_table_issues": n_tab_issues,
        "figure_issues": final_fig_issues,
        "table_issues": final_tab_issues,
        "needs_human_review": needs_human,
        "repro_status": final_result.get("repro_result", {}).get("overall_status", "?"),
        "alignment_status": final_result.get("mapping_result", {}).get("overall_alignment", "?"),
        "completed_at": datetime.now().isoformat(),
    }

    if needs_human:
        print(f"\n  {'=' * 60}")
        print(f"  CODE REVIEW: {n_critical} UNRESOLVED CRITICAL ISSUE(S)")
        print(f"  {'=' * 60}")
        print(f"  After {round_num} auto-correction rounds, some issues remain.")
        print(f"  Review: {project_dir / 'quality_reports' / f'code_review_report_r{round_num}.md'}")
        print(f"  You may want to fix these manually before proceeding to writing.")
        print(f"  {'=' * 60}")

        # Ask user whether to continue or fix manually
        print(f"\n  Options:")
        print(f"  [1] Continue to Stage 5 (issues will be noted in peer review)")
        print(f"  [2] Stop — fix scripts manually and re-run from Stage 4.7")
        print("\a", end="", flush=True)

        choice = ""
        while choice not in ("1", "2"):
            choice = input("\n  Enter your choice (1 or 2): ").strip()

        if choice == "2":
            state["stages"]["stage4_7"]["status"] = "needs_retry"
            save_state(project_dir, state)
            print(f"\n  [4.7] Pipeline stopped. Fix scripts and re-run with:")
            print(f"  python run_pipeline.py --from-stage 4.7 --project {project_dir.name}")
            import sys
            sys.exit(0)

    state["current_stage"] = 4.7
    save_state(project_dir, state)
    return state
