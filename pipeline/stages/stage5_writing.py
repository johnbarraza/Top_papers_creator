"""Stage 5 — Writing.

Manual intervention model: Claude (in conversation) drafts the LaTeX paper
from results, then the pipeline compiles and validates.
"""

import subprocess
from datetime import datetime
from pathlib import Path

from ..config import CRITIC_GATE  # noqa: F401 — used by validator
from ..state import save_state
from ..validators.paper_validator import validate as validate_paper


def _read_file_or(path: Path, default: str = "") -> str:
    return path.read_text(encoding="utf-8") if path.exists() else default


# ── Structural-integrity guard for main.tex writes ─────────────────────────
# Background: the citation auto-fix regexes below operate on the full file
# with re.DOTALL.  In the past, a single misfired pattern (e.g. matching a
# `\bibitem[...]{key}` literal that lived inside a preamble comment) was able
# to silently consume the entire body of the paper, leaving only the preamble
# and a partial bibliography on disk.  Recovery from those events is painful.
#
# `_safe_write_main_tex` wraps every write with: (1) a sibling .bak snapshot
# of the previous good content, (2) the write itself, and (3) a structural
# integrity check.  If the post-write file is missing `\begin{document}`,
# `\end{document}`, or shrank to under half the previous size, we restore
# from the backup and surface a clear diagnostic.  Callers should use this
# wrapper instead of `main_tex.write_text(...)` for any auto-fix that can,
# in principle, delete content it didn't intend to.
def _bib_block_replace(tex: str, sub_fn) -> str:
    """Apply `sub_fn(bib_block) -> new_bib_block` only to the substring between
    \\begin{thebibliography} and \\end{thebibliography} (inclusive of neither
    delimiter).  Outside that window, including preamble comments that may
    legitimately contain literal `\\bibitem[Author(Year)]{key}` placeholder
    text, the input is returned untouched.

    This is the targeted fix for a corruption bug where bibitem-rewriting
    regexes with `re.DOTALL` matched commented-out placeholder text in the
    preamble and silently consumed the entire paper body up to the next real
    bibitem.  Restricting the operation to the bibliography window guarantees
    that the body of the document is never an eligible match.
    """
    import re as _re_sb
    open_tag = r"\begin{thebibliography}"
    close_tag = r"\end{thebibliography}"
    i = tex.find(open_tag)
    j = tex.find(close_tag)
    if i < 0 or j < 0 or j <= i:
        # No well-formed bibliography window — refuse to touch anything.
        return tex
    head = tex[: i + len(open_tag)]
    block = tex[i + len(open_tag) : j]
    tail = tex[j:]
    return head + sub_fn(block) + tail


def _validate_main_tex_structure(content: str) -> tuple[bool, str]:
    """Return (ok, reason). Cheap structural sanity checks for main.tex."""
    if r"\begin{document}" not in content:
        return False, "missing \\begin{document}"
    if r"\end{document}" not in content:
        return False, "missing \\end{document}"
    if r"\begin{thebibliography}" in content and r"\end{thebibliography}" not in content:
        return False, "open \\begin{thebibliography} without matching close"
    if r"\end{thebibliography}" in content and r"\begin{thebibliography}" not in content:
        return False, "stray \\end{thebibliography} without matching open"
    if len(content) < 1000:
        return False, f"content suspiciously small ({len(content)} bytes)"
    return True, "ok"


def _safe_write_main_tex(main_tex: Path, new_content: str, *, label: str = "auto-fix") -> bool:
    """Write `new_content` to `main_tex` with a backup + structural guard.

    Returns True on success, False if the new content failed validation and
    the original was kept (a `.bak` snapshot is left behind for forensics).
    """
    prev = main_tex.read_text(encoding="utf-8") if main_tex.exists() else ""
    ok_new, reason_new = _validate_main_tex_structure(new_content)
    if not ok_new:
        bak = main_tex.with_suffix(main_tex.suffix + ".rejected")
        bak.write_text(new_content, encoding="utf-8")
        print(
            f"  [safe-write] REJECTED {label}: {reason_new}. "
            f"Original kept; rejected payload at {bak.name}"
        )
        return False

    # Catch silent-truncation: shrank to less than half of previous good size.
    if prev and len(new_content) < len(prev) / 2:
        bak = main_tex.with_suffix(main_tex.suffix + ".rejected")
        bak.write_text(new_content, encoding="utf-8")
        print(
            f"  [safe-write] REJECTED {label}: shrank from "
            f"{len(prev)} to {len(new_content)} bytes (>50% loss). "
            f"Original kept; rejected payload at {bak.name}"
        )
        return False

    # Snapshot the previous good content so we can roll back if a later
    # stage corrupts the file.  We keep only the most-recent backup.
    if prev:
        try:
            main_tex.with_suffix(main_tex.suffix + ".bak").write_text(prev, encoding="utf-8")
        except Exception:
            pass

    main_tex.write_text(new_content, encoding="utf-8")
    return True


def _compile_latex(paper_dir: Path) -> bool:
    """Run pdflatex (3 passes) + bibtex.  Falls back to Python PDF if pdflatex missing."""
    main_tex = paper_dir / "main.tex"
    if not main_tex.exists():
        print("  [latex] main.tex not found, skipping compilation.")
        return False

    print("  [latex] Compiling (pdflatex x 3 + bibtex)...")
    cwd = str(paper_dir)

    latex_errors = []

    for i in range(1, 4):
        label = f"pdflatex pass {i}/3"
        try:
            r = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "main.tex"],
                capture_output=True, text=True, cwd=cwd, timeout=120,
                encoding="utf-8", errors="replace",
            )
        except FileNotFoundError:
            print("  [latex] pdflatex not found, using Python PDF fallback...")
            return _compile_pdf_fallback(paper_dir)
        if r.returncode != 0 and i == 1:
            print(f"  [latex] {label} failed, trying Python fallback...")
            return _compile_pdf_fallback(paper_dir)

        # Collect LaTeX errors from stdout (pdflatex reports errors there)
        if i == 1:
            for line in (r.stdout or "").splitlines():
                if line.startswith("! "):
                    latex_errors.append(line)

            try:
                subprocess.run(
                    ["bibtex", "main"],
                    capture_output=True, text=True, cwd=cwd, timeout=60,
                )
            except FileNotFoundError:
                print("  [latex] bibtex not found, skipping bibliography.")

    # Check for LaTeX errors that produce broken PDFs
    if latex_errors:
        print(f"  [latex] WARNING: {len(latex_errors)} LaTeX error(s) detected:")
        for err in latex_errors[:10]:
            print(f"    {err}")
        # Check for undefined environments / missing packages
        undefined = [e for e in latex_errors if "undefined" in e.lower()]
        if undefined:
            print(f"  [latex] FATAL: Undefined environments/commands detected.")
            print(f"  [latex] PDF may be incomplete -- sections after the error are missing.")
            return False

    pdf = paper_dir / "main.pdf"
    if pdf.exists():
        print(f"  [latex] Compiled: {pdf}")
        return True
    else:
        print("  [latex] Compilation finished but no PDF produced, trying fallback...")
        return _compile_pdf_fallback(paper_dir)


def _compile_pdf_fallback(paper_dir: Path) -> bool:
    """Generate PDF from LaTeX sections using the academic PDF builder (fpdf2)."""
    from ..pdf_fallback import compile_pdf
    return compile_pdf(paper_dir)


def _load_latex_template() -> str:
    """Load the LaTeX preamble template from pipeline/example.tex.

    Extracts everything from \\documentclass to \\begin{document} (exclusive)
    so it can be included as a mandatory format reference in writing prompts.
    """
    from ..config import PAPERS_HQ
    template_path = PAPERS_HQ / "pipeline" / "example.tex"
    if not template_path.exists():
        return ""

    content = template_path.read_text(encoding="utf-8")

    # Extract preamble (everything before \begin{document})
    marker = r"\begin{document}"
    idx = content.find(marker)
    if idx > 0:
        preamble = content[:idx].strip()
    else:
        # Fallback: take first 2000 chars
        preamble = content[:2000]

    return preamble


def _load_paper_structure_template() -> str:
    """Load the paper structure template with mandatory sections.

    Returns the body template (after \\begin{document}) that defines
    the section order and content requirements with {{PLACEHOLDER}} blocks.
    """
    from ..config import PAPERS_HQ
    template_path = PAPERS_HQ / "pipeline" / "templates" / "paper_structure.tex"
    if not template_path.exists():
        return ""

    content = template_path.read_text(encoding="utf-8")
    return content


def run(project_dir: Path, state: dict) -> dict:
    """Execute Stage 5: manual paper writing + compile LaTeX."""

    from ..claude_runner import request_manual_intervention
    from ..json_utils import smart_truncate

    paper_dir = project_dir / "paper"
    review_dir = project_dir / "reviews"
    main_tex = paper_dir / "main.tex"

    # Load the mandatory LaTeX template preamble
    latex_template = _load_latex_template()
    template_instruction = ""
    if latex_template:
        template_instruction = (
            "\n\n*** MANDATORY LATEX FORMAT ***\n"
            "The paper MUST use EXACTLY this preamble (packages, spacing, formatting).\n"
            "Do NOT change the document class, spacing, section formatting, or packages.\n"
            "Copy this preamble exactly, then add your content after \\begin{document}.\n\n"
            f"```latex\n{latex_template}\n```\n"
            "\nKey format rules from this template:\n"
            "- \\onehalfspacing (NOT \\doublespacing)\n"
            "- \\bibliographystyle{aer}\n"
            "- \\captionsetup{font=small,labelfont=bf}\n"
            "- Section formatting via titlesec: \\large\\bfseries with number and period\n"
            "- Author format: APEP Autonomous Research\\thanks{...}\n"
            "- \\date{\\today}\n"
        )

    # Load the mandatory paper structure template
    structure_template = _load_paper_structure_template()
    structure_instruction = ""
    if structure_template:
        structure_instruction = (
            "\n\n*** MANDATORY PAPER STRUCTURE ***\n"
            "The paper MUST follow this exact section order. Each {{PLACEHOLDER}} must be\n"
            "replaced with actual content. Do NOT reorder, skip, or merge sections.\n\n"
            "```latex\n" + structure_template + "\n```\n\n"
            "INSTRUCTIONS:\n"
            "1. Use the preamble from MANDATORY LATEX FORMAT above\n"
            "2. Follow the section order from this structure template\n"
            "3. Replace every {{PLACEHOLDER}} with project-specific content\n"
            "4. For results sections: use EXACT numbers from the result CSVs below\n"
            "5. For \\input{tables/...}: include ALL .tex files from paper/tables/\n"
            "6. For figures: include ALL .pdf/.png files from paper/figures/\n"
            "7. Do NOT invent section headings — use the ones in the template\n"
            "8. Minimum 5,000 words. Expand literature review and discussion if short.\n"
        )

    # Build figure instructions — list available figures and prevent duplicates
    figures_instruction = ""
    figures_dir = paper_dir / "figures"
    if figures_dir.exists():
        fig_files = sorted(
            f.name for f in figures_dir.iterdir()
            if f.suffix.lower() in (".png", ".pdf", ".jpg", ".jpeg", ".svg")
        )
        if fig_files:
            # Group by base name (same figure may have .pdf and .png)
            seen_bases = set()
            unique_figs = []
            for f in fig_files:
                base = f.rsplit(".", 1)[0]
                if base not in seen_bases:
                    seen_bases.add(base)
                    unique_figs.append(f)

            figures_instruction = (
                "\n\n*** FIGURES ***\n"
                f"Available figures ({len(unique_figs)} unique):\n"
                + "\n".join(f"  - {f}" for f in unique_figs) + "\n"
                "\nRULES for figures:\n"
                "- Include EACH figure EXACTLY ONCE with \\includegraphics\n"
                "- Do NOT include the same figure in multiple places\n"
                "- Do NOT include both .pdf and .png versions of the same figure\n"
                "- Prefer .png for \\includegraphics (better compatibility)\n"
                "- Every \\includegraphics MUST have a corresponding \\caption and \\label\n"
                "- Every figure MUST be referenced at least once with \\ref{} in the text\n"
            )

    # Detect R&R mode
    stage6 = state["stages"].get("stage6", {})
    is_rr = stage6.get("decision") == "MAJOR_REVISIONS"
    rr_round = stage6.get("rr_round", 0)

    if not main_tex.exists():
        # Inventory what outputs actually exist from Stage 4
        clean_dir = project_dir / "data" / "clean"
        existing_outputs = []
        if clean_dir.exists():
            existing_outputs = [f.name for f in clean_dir.glob("*.csv")]

        output_note = ""
        if existing_outputs:
            output_note = (
                "\n\nAVAILABLE OUTPUT FILES (from scripts): "
                + ", ".join(existing_outputs)
                + "\nONLY reference results that exist in these files. "
                "Do NOT claim to have run estimators whose outputs are missing. "
                "If a CSV is missing or contains NaN, do NOT report that result."
            )

        # CRITICAL: Embed actual CSV content in the prompt so Claude uses
        # exact numbers instead of hallucinating them
        results_content = ""
        key_files = ["main_results.csv", "robustness_results.csv",
                     "summary_stats.csv", "arm_means.csv", "balance_table.csv",
                     "cohort_table.csv", "cate_results.csv"]
        truncated_files = []
        for fname in key_files:
            fpath = clean_dir / fname if clean_dir.exists() else None
            if fpath and fpath.exists():
                try:
                    content = fpath.read_text(encoding="utf-8")
                    # Smart truncation: keep complete rows, never cut mid-line
                    if len(content) > 4000:
                        lines = content.splitlines()
                        header = lines[0] if lines else ""
                        # Keep header + first 50 data rows
                        kept = [header] + lines[1:51]
                        content = "\n".join(kept)
                        truncated_files.append(
                            "%s (showing 50 of %d rows)" % (fname, len(lines) - 1)
                        )
                    results_content += (
                        "\n\n--- %s ---\n%s" % (fname, content)
                    )
                except Exception:
                    pass

        if truncated_files:
            results_content += (
                "\n\nNOTE: The following files were truncated to fit: %s. "
                "All key results should be in the first 50 rows. "
                "If you need a number not shown, state it is unavailable."
                % ", ".join(truncated_files)
            )

        if results_content:
            output_note += (
                "\n\n*** EXACT RESULTS FROM SCRIPTS (use ONLY these numbers) ***"
                "\nEvery number in the paper MUST come from the data below."
                "\nDo NOT round differently, do NOT use different decimal places,"
                "\ndo NOT invent numbers that are not in these files."
                + results_content
            )

        # Check what information is NOT available in the dataset
        data_profile = state["stages"].get("stage1", {}).get("data_profile", {})
        columns = data_profile.get("columns", [])
        data_disclaimer = ""
        missing_info = []
        # Check for common referee requests that may not be in the data
        col_lower = [c.lower() for c in columns]
        if not any("comply" in c or "takeup" in c or "take_up" in c for c in col_lower):
            missing_info.append("compliance/take-up rates")
        if not any("attrit" in c for c in col_lower):
            missing_info.append("attrition tracking variables")
        if not any("cost" in c for c in col_lower):
            missing_info.append("program cost data")
        if not any("follow" in c or "wave" in c or "round" in c for c in col_lower):
            missing_info.append("follow-up wave identifiers")

        if missing_info:
            data_disclaimer = (
                "\n\n*** DATA AVAILABILITY DISCLAIMER ***\n"
                "The following information is NOT available in this dataset:\n"
                + "\n".join("  - %s" % m for m in missing_info)
                + "\nDo NOT claim these exist. If referees ask for them, state "
                "explicitly: 'This information is not available in the dataset.'\n"
            )
        output_note += data_disclaimer

        # Check estimator constraints
        stage3_3 = state["stages"].get("stage3_3", {})
        avail_est = stage3_3.get("available_estimators", {})
        broken = [k for k, v in avail_est.items() if not v] if avail_est else []
        if broken:
            output_note += (
                "\n\nBROKEN ESTIMATORS (do NOT mention in paper): "
                + ", ".join(broken)
                + "\nThese were tested and failed. Do not claim they were used."
            )

        # First draft — main.tex does not exist yet
        request_manual_intervention(
            stage="stage5_writing",
            issue=(
                "Stage 5 needs manual paper writing. "
                "Tell Claude: 'revisa el pipeline'. Claude will read the strategy memo "
                "and results, write a single main.tex with all sections (intro, literature, "
                "data, empirical strategy, results, robustness, conclusion), create "
                "references.bib, compile to PDF, and signal completion. "
                "WORD COUNT: The paper MUST be between 5,000 and 12,000 words. "
                "Papers under 5,000 words fail validation. Expand the introduction, "
                "literature review, and discussion sections to reach this target. "
                "NUMBERS: The abstract MUST contain the exact key results (coefficients, "
                "p-values) matching the numbers in results_summary.md. "
                "\n\n*** WRITING STANDARDS (from clo-author best practices) ***\n"
                "1. NO HEDGING: Avoid 'might', 'could potentially', 'seems to suggest'. "
                "State findings directly: 'We find X' not 'Our results seem to indicate X'.\n"
                "2. CONTRIBUTION in first 2 pages: The reader must know what is new by page 2.\n"
                "3. CONSISTENT NOTATION: Define every variable in every equation. "
                "Use the same symbol throughout (do not switch between beta and b).\n"
                "4. EFFECT SIZES: Report Cohen's d or percentage change alongside p-values. "
                "Editors increasingly require standardized effect sizes.\n"
                "5. IDENTIFICATION section must state assumptions FORMALLY and in plain language. "
                "List each assumption, its testable implications, and how you test them.\n"
                "6. TABLES: Three-line booktabs format. No vertical lines. "
                "SEs in parentheses, 95% CIs in brackets. N, R2, FE indicators in footer.\n"
                "7. LIMITATIONS: Honest subsection. State what the data CANNOT answer.\n"
                "8. REPLICATION: Note that all code and data are available. "
                "Include a data availability statement.\n"
                "9. VOICE: Use 'we' consistently throughout. Never switch between "
                "'I' and 'we' in the same paper.\n"
                "10. CROSS-REFERENCES: Every \\ref{} MUST point to a \\label{} that "
                "exists in the document. Every \\input{tables/X.tex} MUST reference "
                "a file that exists. Do NOT reference tables or figures that were not "
                "generated by the scripts.\n"
                "\n\n*** CRITICAL: AVOID THESE REFEREE RED FLAGS ***\n"
                "These are the top reasons papers get scored below 60 in peer review. "
                "Avoiding ALL of them is worth 15-20 points.\n\n"
                "RED FLAG 1 — CAUSAL OVERCLAIMING (instant CRITICAL from referees):\n"
                "  NEVER write: 'X causes Y', 'we prove', 'we establish causally',\n"
                "  'definitive evidence', 'unambiguous effect'.\n"
                "  INSTEAD write: 'we find evidence that X is associated with Y',\n"
                "  'our estimates suggest', 'the results are consistent with'.\n"
                "  If using IV/RDD/DiD: you may say 'causal' ONLY with the correct\n"
                "  qualifier: 'under the assumption that [assumption], we estimate\n"
                "  the causal effect of X on Y'.\n\n"
                "RED FLAG 2 — CLAIMS WITHOUT NUMBERS:\n"
                "  Every claim in the abstract and results section MUST have a number.\n"
                "  BAD: 'Treatment significantly increases outcomes.'\n"
                "  GOOD: 'Treatment increases outcomes by 0.15 SD (p=0.003, 95% CI [0.05, 0.25]).'\n\n"
                "RED FLAG 3 — MISSING LIMITATIONS:\n"
                "  The Limitations subsection must discuss:\n"
                "  (a) External validity — who does this NOT apply to?\n"
                "  (b) Data limitations — what can't we measure?\n"
                "  (c) Identification threats — what could bias results?\n"
                "  Papers without honest limitations get scored 10+ points lower.\n\n"
                "RED FLAG 4 — INCONSISTENT NUMBERS:\n"
                "  The coefficient in the abstract, introduction, results section, and\n"
                "  conclusion MUST be IDENTICAL. Copy-paste the exact number.\n"
                "  Inconsistent numbers are flagged as CRITICAL by consistency agents.\n\n"
                "RED FLAG 5 — MISSING TABLE NOTES:\n"
                "  Every table MUST have: (a) what the dependent variable is,\n"
                "  (b) SE type (HC2/clustered/bootstrap), (c) significance stars defined,\n"
                "  (d) sample description, (e) controls/FE listed.\n"
                "\n\n*** LATEX COMPILATION RULES (avoids 30+ pdflatex errors) ***\n"
                "These rules prevent the most common pdflatex compilation failures.\n"
                "Following them strictly raises the Paper score from ~50 to ~80.\n\n"
                "RULE 1 - ESCAPE SPECIAL CHARS IN TEXT MODE:\n"
                "  Outside math mode ($...$ or \\(...\\)), these chars MUST be escaped:\n"
                "    _  -> \\_       (e.g. has\\_formal, log\\_income)\n"
                "    %  -> \\%       (e.g. 95\\% CI, 5\\% level)\n"
                "    &  -> \\&       (e.g. R\\&D, A\\&B)\n"
                "    #  -> \\#\n"
                "    $  -> \\$       (when used as currency, NOT math mode)\n"
                "  In math mode, these chars are fine: $r_{ic}$, $\\beta_1$, etc.\n\n"
                "RULE 2 - BIBLIOGRAPHY: USE thebibliography ONLY (NOT \\bibliography{}):\n"
                "  CORRECT (use this exact pattern):\n"
                "    \\begin{thebibliography}{99}\n"
                "    \\bibitem[Smith(2020)]{smith2020}\n"
                "    Smith, J. (2020). Title. Journal, 10(2):1-20.\n"
                "    \\end{thebibliography}\n"
                "  Then cite with \\citet{smith2020} or \\citep{smith2020}.\n"
                "  WRONG: \\bibliography{refs} or \\bibliographystyle{aer} -- these conflict\n"
                "  with thebibliography environment and will fail to compile.\n\n"
                "RULE 3 - EVERY \\citet/\\citep MUST HAVE A MATCHING \\bibitem:\n"
                "  If you cite Smith2020 in text, the bibliography MUST contain\n"
                "  \\bibitem[...]{smith2020}. Missing bibitems cause 'undefined citation'.\n"
                "  Cross-check every \\cite{} call against your \\bibitem entries.\n\n"
                "RULE 4 - EVERY \\ref{} MUST HAVE A MATCHING \\label{}:\n"
                "  If you write \\ref{tab:main}, you MUST have \\label{tab:main} on the\n"
                "  table. The pipeline auto-validates this -- missing labels fail compile.\n"
                "  Use these EXACT labels for the standard sections:\n"
                "    \\label{sec:introduction}, \\label{sec:literature}, \\label{sec:data},\n"
                "    \\label{sec:strategy}, \\label{sec:results}, \\label{sec:discussion},\n"
                "    \\label{sec:conclusion}\n\n"
                "RULE 5 - URLS IN \\thanks{}: KEEP SIMPLE OR OMIT:\n"
                "  URLs in footnotes break easily. If including a URL in \\thanks{},\n"
                "  use \\url{https://example.com} only -- no spaces, no @ signs, no\n"
                "  trailing text after the URL. Better: omit URLs from \\thanks{} entirely.\n\n"
                "RULE 6 - TABLE \\input PATHS MUST EXIST:\n"
                "  Only \\input{tables/X.tex} files that ACTUALLY EXIST in paper/tables/.\n"
                "  The available tables are listed in the FIGURES section below -- check\n"
                "  the same dir for tables. Do NOT invent table filenames.\n\n"
                "RULE 7 - NEVER USE 'thebibliography' INSIDE A SECTION:\n"
                "  thebibliography goes AFTER \\appendix or at the very end, before\n"
                "  \\end{document}. Putting it inside a \\section{} causes 'Not in outer\n"
                "  par mode' errors.\n\n"
                "RULE 8 - VERIFICATION CHECKLIST BEFORE SAVING main.tex:\n"
                "  Before signaling completion, mentally verify:\n"
                "  [ ] Every _ outside math mode is \\_\n"
                "  [ ] Every % outside math mode is \\%\n"
                "  [ ] Every \\citet{key} has a matching \\bibitem[...]{key}\n"
                "  [ ] Every \\ref{label} has a matching \\label{label}\n"
                "  [ ] No \\bibliography{} or \\bibliographystyle if using thebibliography\n"
                "  [ ] thebibliography is at end of doc, not inside a section\n"
                "  [ ] All \\input{tables/X.tex} files exist in paper/tables/\n"
                + template_instruction
                + structure_instruction
                + figures_instruction
                + output_note
            ),
            files=[
                str(project_dir / "strategy" / "strategy_memo.md"),
                str(project_dir / "paper" / "tables" / "results_summary.md"),
                str(project_dir / "scripts" / "python"),
            ],
            project_dir=project_dir,
        )
    elif is_rr:
        # ══════════════════════════════════════════════════════════════════
        # R&R MODE — referees requested changes
        # Read structured feedback from editorial_decision.md AND state
        # ══════════════════════════════════════════════════════════════════

        # 1. Read editorial_decision.md (structured feedback from Stage 6)
        latest_decision = ""
        decision_files = sorted(review_dir.glob("editorial_decision*.md"), reverse=True)
        if decision_files:
            latest_decision = decision_files[0].read_text(encoding="utf-8")
            print(f"  [5] Found editorial decision: {decision_files[0].name}")

        # 2. Fallback: read review_report.md if editorial_decision not found
        if not latest_decision:
            report_files = sorted(review_dir.glob("review_report*.md"), reverse=True)
            if report_files:
                latest_decision = report_files[0].read_text(encoding="utf-8")
                print(f"  [5] Fallback: using review_report: {report_files[0].name}")

        # 3. Also read structured issues from state (most reliable source)
        stage6_issues = stage6.get("issues", {})
        must_address = stage6_issues.get("must_address", [])
        should_address = stage6_issues.get("should_address", [])

        # 4. Classify: CODE issues vs TEXT issues
        code_keywords = [
            "analysis", "estimat", "regress", "robust", "specif", "test",
            "implement", "script", "code", "compute", "calculat",
            "missing table", "missing figure", "add table", "add figure",
            "placebo", "permutation", "bootstrap", "sensitivity",
            "heterogeneity", "mediation", "balance", "power",
            "misimplemented", "bug", "coding error", "reimplement",
            "SE underestimat", "arithmetically", "impossible",
        ]
        all_issues = must_address + should_address
        has_code_issues = any(
            any(kw in issue.lower() for kw in code_keywords)
            for issue in all_issues
        ) if all_issues else ("CODE ISSUES" in latest_decision.upper())

        scripts_dir = project_dir / "scripts" / "python"

        # 5. Build explicit, actionable instructions for Claude
        issue_instructions = []

        if must_address:
            issue_instructions.append(
                "## MUST-ADDRESS ISSUES (fix ALL of these — they are blockers):\n"
                + "\n".join(f"  {i}. {item}" for i, item in enumerate(must_address, 1))
            )

        if should_address:
            issue_instructions.append(
                "\n## SHOULD-ADDRESS ISSUES (fix as many as possible):\n"
                + "\n".join(f"  {i}. {item}" for i, item in enumerate(should_address, 1))
            )

        if not must_address and not should_address and latest_decision:
            # No structured issues — fall back to the full decision text
            issue_instructions.append(
                "## REFEREE FEEDBACK (read and address all issues):\n"
                + smart_truncate(latest_decision, 4000)
            )

        issue_block = "\n".join(issue_instructions)

        # 6. Build the intervention instruction
        if has_code_issues:
            code_instruction = (
                "CRITICAL: Some issues require CODE CHANGES, not just paper text edits.\n"
                "WORKFLOW:\n"
                "  Step 1: Read the issue list below carefully\n"
                "  Step 2: For CODE issues → modify the Python scripts in scripts/python/\n"
                "  Step 3: Re-execute ALL scripts (python 00_clean.py, 01_main.py, etc.)\n"
                "  Step 4: Verify new results in data/clean/*.csv\n"
                "  Step 5: Update main.tex with corrected numbers from new results\n"
                "  Step 6: For TEXT issues → edit main.tex directly\n"
                "Do NOT just edit paper text if the underlying analysis is wrong."
            )
        else:
            code_instruction = (
                "These issues are TEXT-ONLY. Edit main.tex to address each one.\n"
                "WORKFLOW:\n"
                "  Step 1: Read the issue list below\n"
                "  Step 2: For each MUST-ADDRESS issue, find and fix it in main.tex\n"
                "  Step 3: For SHOULD-ADDRESS issues, fix as many as possible\n"
                "  Step 4: Verify cross-references and numbers are still consistent"
            )

        # Remind Claude to preserve the LaTeX format during R&R revisions
        format_reminder = ""
        if latex_template:
            format_reminder = (
                "\n\nIMPORTANT: Do NOT change the LaTeX preamble (packages, spacing, "
                "section formatting). The paper must keep \\onehalfspacing, "
                "\\bibliographystyle{aer}, titlesec section formatting, and "
                "\\captionsetup{font=small,labelfont=bf}. Only modify content, "
                "not formatting."
            )

        files = [str(main_tex)]
        if decision_files:
            files.insert(0, str(decision_files[0]))
        if has_code_issues:
            files.append(str(scripts_dir))

        # 7. Pass structured data to Claude via script_results
        script_results_payload = {
            "referee_feedback": smart_truncate(latest_decision, 5000),
            "must_address": must_address,
            "should_address": should_address,
            "has_code_issues": has_code_issues,
            "avg_score": stage6.get("avg_score", "?"),
            "n_must": len(must_address),
            "n_should": len(should_address),
        }

        print(f"  [5] R&R revision: {len(must_address)} must-address, "
              f"{len(should_address)} should-address, "
              f"code_issues={'YES' if has_code_issues else 'no'}")

        request_manual_intervention(
            stage="stage5_rr_revision",
            issue=(
                f"Stage 5 R&R revision (round {rr_round + 1}). "
                f"Score: {stage6.get('avg_score', '?')}/100. "
                f"Issues: {len(must_address)} MUST-fix, {len(should_address)} SHOULD-fix.\n\n"
                f"{code_instruction}\n\n"
                f"{issue_block}"
                f"{format_reminder}"
            ),
            files=files,
            project_dir=project_dir,
            script_results=script_results_payload,
        )

    # After intervention: verify main.tex exists, compile, validate
    main_tex = paper_dir / "main.tex"
    if not main_tex.exists():
        print("  [5] WARNING: main.tex not found after intervention!")
        print("  [5] The paper was not written. Check intervention logs.")
        compiled = False
    else:
        tex_size = main_tex.stat().st_size
        if tex_size < 1000:
            print(f"  [5] WARNING: main.tex is only {tex_size} bytes -- likely incomplete")

        print("\n  [5] Compiling paper after manual intervention...")
        compiled = _compile_latex(paper_dir)

        # Verify PDF actually exists and is non-trivial
        pdf_path = paper_dir / "main.pdf"
        if compiled and pdf_path.exists():
            pdf_size = pdf_path.stat().st_size
            if pdf_size < 5000:
                print(f"  [5] WARNING: main.pdf is only {pdf_size} bytes -- may be empty/broken")
                compiled = False
            else:
                print(f"  [5] PDF verified: {pdf_size:,} bytes")
        elif compiled:
            print("  [5] WARNING: Compilation reported success but main.pdf not found!")
            compiled = False

    # ── Check LaTeX log for common problems ────────────────────────────
    log_path = paper_dir / "main.log"
    latex_warnings = []
    if log_path.exists() and compiled:
        log_content = log_path.read_text(encoding="utf-8", errors="replace")

        # Undefined references (\ref{} pointing to non-existent labels)
        import re as _re
        undef_refs = _re.findall(r"Reference `(.+?)' on page \d+ undefined", log_content)
        if undef_refs:
            for ref in set(undef_refs):
                latex_warnings.append(f"Undefined reference: \\ref{{{ref}}}")
            print(f"  [5] WARNING: {len(set(undef_refs))} undefined reference(s):")
            for ref in set(undef_refs):
                print(f"    - \\ref{{{ref}}}")

        # Undefined citations
        undef_cites = _re.findall(r"Citation `(.+?)' on page \d+ undefined", log_content)
        if undef_cites:
            for cite in set(undef_cites):
                latex_warnings.append(f"Undefined citation: \\cite{{{cite}}}")
            print(f"  [5] WARNING: {len(set(undef_cites))} undefined citation(s)")

        # LaTeX errors (environment undefined, etc.)
        latex_errors = _re.findall(r"^! (.+)$", log_content, _re.MULTILINE)
        if latex_errors:
            unique_errors = list(set(latex_errors))[:5]
            for err in unique_errors:
                latex_warnings.append(f"LaTeX error: {err}")
            print(f"  [5] WARNING: {len(latex_errors)} LaTeX error(s):")
            for err in unique_errors:
                print(f"    - {err}")

        if not latex_warnings:
            print(f"  [5] LaTeX log clean: no undefined refs, citations, or errors.")

    # ── Auto-fix critical LaTeX issues before proceeding ──────────────
    # If there are undefined references or LaTeX errors, attempt a quick
    # programmatic fix rather than requiring another full intervention.
    if latex_warnings and main_tex.exists():
        import re as _re2
        tex_content = main_tex.read_text(encoding="utf-8")
        fixes_applied = 0

        # Fix undefined references: find \ref{X} where X doesn't have a \label{X}
        all_labels = set(_re2.findall(r'\\label\{(.+?)\}', tex_content))
        all_refs = set(_re2.findall(r'\\ref\{(.+?)\}', tex_content))
        broken_refs = all_refs - all_labels

        for broken_ref in broken_refs:
            # Try to find a similar label
            candidates = [l for l in all_labels if broken_ref.split(":")[-1] in l
                          or l.split(":")[-1] in broken_ref]
            if candidates:
                # Replace with the closest match
                best = candidates[0]
                tex_content = tex_content.replace(
                    f"\\ref{{{broken_ref}}}", f"\\ref{{{best}}}"
                )
                fixes_applied += 1
                print(f"  [5] Auto-fixed: \\ref{{{broken_ref}}} -> \\ref{{{best}}}")
            else:
                # Remove the reference entirely (replace with "[?]")
                tex_content = tex_content.replace(
                    f"\\ref{{{broken_ref}}}", "[?]"
                )
                fixes_applied += 1
                print(f"  [5] Auto-fixed: removed broken \\ref{{{broken_ref}}}")

        # ── Auto-fix undefined citations (added 2026-04-13) ──────────────
        # Extract all \citet{}, \citep{}, \cite{} keys vs all \bibitem{} keys.
        # For undefined citations: try to match by partial key, otherwise
        # replace \citet{bad} with "the literature" to avoid 'undefined
        # citation' compilation errors that drag down the Paper score.
        all_cites = set(_re2.findall(
            r'\\cite[tp]?\*?\{([^}]+)\}', tex_content
        ))
        # Citation calls can include multiple keys: \citet{a,b,c}
        cite_keys = set()
        for c in all_cites:
            for k in c.split(","):
                k = k.strip()
                if k:
                    cite_keys.add(k)

        all_bibitems = set(_re2.findall(
            r'\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}', tex_content
        ))
        broken_cites = cite_keys - all_bibitems

        if broken_cites:
            print(f"  [5] Found {len(broken_cites)} undefined citation key(s) — fixing...")
            for bad_key in broken_cites:
                # Try to find a bibitem with similar key
                candidates = [b for b in all_bibitems
                              if bad_key.lower() in b.lower()
                              or b.lower() in bad_key.lower()]
                if candidates:
                    best = candidates[0]
                    # Replace bad_key with best inside any \cite*{} call.
                    # Use word-boundary regex so we only replace whole keys.
                    pat = _re2.compile(
                        r'(\\cite[tp]?\*?\{[^}]*?)\b' + _re2.escape(bad_key) + r'\b'
                    )
                    new_content, n_repl = pat.subn(r'\1' + best, tex_content)
                    if n_repl:
                        tex_content = new_content
                        fixes_applied += n_repl
                        print(f"  [5] Auto-fixed: \\cite{{{bad_key}}} -> \\cite{{{best}}} ({n_repl}x)")
                else:
                    # No matching bibitem — replace the entire \cite*{...bad_key...}
                    # call with neutral placeholder text. This avoids compile
                    # failures and is honest (we don't have a real source).
                    pat = _re2.compile(
                        r'\\cite[tp]?\*?\{[^}]*?\b' + _re2.escape(bad_key) + r'\b[^}]*?\}'
                    )
                    new_content, n_repl = pat.subn("the literature", tex_content)
                    if n_repl:
                        tex_content = new_content
                        fixes_applied += n_repl
                        print(f"  [5] Auto-fixed: removed unmatched \\cite{{{bad_key}}} ({n_repl}x)")

        # Fix I/we inconsistency: standardize to "we"
        # Only fix clear first-person cases, not within quotes or citations
        i_patterns = [
            (r'\bI find\b', 'we find'),
            (r'\bI show\b', 'we show'),
            (r'\bI use\b', 'we use'),
            (r'\bI estimate\b', 'we estimate'),
            (r'\bI report\b', 'we report'),
            (r'\bI include\b', 'we include'),
            (r'\bI restrict\b', 'we restrict'),
            (r'\bI employ\b', 'we employ'),
            (r'\bI examine\b', 'we examine'),
            (r'\bI test\b', 'we test'),
            (r'\bI note\b', 'we note'),
            (r'\bI focus\b', 'we focus'),
        ]
        for pattern, replacement in i_patterns:
            matches = _re2.findall(pattern, tex_content)
            if matches:
                tex_content = _re2.sub(pattern, replacement, tex_content)
                fixes_applied += len(matches)

        if fixes_applied > 0:
            if _safe_write_main_tex(main_tex, tex_content, label=f"auto-fix x{fixes_applied}"):
                print(f"  [5] Applied {fixes_applied} auto-fixes. Recompiling...")
                _compile_latex(paper_dir)
            else:
                print(f"  [5] Auto-fix payload rejected by integrity guard; original main.tex kept.")

    # ── Verify citations are real (not hallucinated) ────────────────────
    # Extract all \bibitem entries and verify each exists via web search.
    # Hallucinated citations are a known LLM problem and will be caught
    # by referees immediately.
    if main_tex.exists():
        import re as _re_cite
        tex_content_cite = main_tex.read_text(encoding="utf-8")

        # Extract bibitem entries: \bibitem[Author(Year)]{key} followed by text
        bibitems = _re_cite.findall(
            r'\\bibitem\[(.+?)\]\{(.+?)\}\s*\n(.+?)(?=\\bibitem|\n\\end\{thebibliography\})',
            tex_content_cite, _re_cite.DOTALL
        )

        if bibitems:
            # Cap at 10 most-cited entries to keep WebSearch under timeout.
            # Earlier runs (with 15+ citations) hit the 330s timeout
            # consistently. Verifying the 10 most-used citations covers the
            # ones most likely to be flagged in peer review.
            MAX_CITES_TO_VERIFY = 10
            citation_use_count = {}
            for _, key, _ in bibitems:
                # Count how often this key is cited in the body
                citation_use_count[key] = len(_re_cite.findall(
                    r'\\cite[tp]?\*?\{[^}]*?\b' + _re_cite.escape(key) + r'\b',
                    tex_content_cite
                ))

            # Sort bibitems by use count (most-used first)
            bibitems_sorted = sorted(
                bibitems,
                key=lambda b: -citation_use_count.get(b[1], 0)
            )
            bibitems_to_verify = bibitems_sorted[:MAX_CITES_TO_VERIFY]
            n_skipped = len(bibitems) - len(bibitems_to_verify)
            if n_skipped > 0:
                print(f"\n  [5] Verifying top {len(bibitems_to_verify)} of "
                      f"{len(bibitems)} citations (skipping {n_skipped} "
                      f"least-used to avoid timeout)...")
            else:
                print(f"\n  [5] Verifying {len(bibitems_to_verify)} citations via web search...")

            from ..claude_runner import run_claude
            from ..json_utils import extract_json

            # Build a batch of citations to verify
            cite_list = []
            for author_year, key, full_text in bibitems_to_verify:
                # Clean up the full text
                clean_text = full_text.strip()[:200].replace("\n", " ")
                cite_list.append(f"  - [{key}] {author_year}: {clean_text}")

            # Send all citations to Claude for batch verification
            verify_prompt = f"""You are verifying whether academic citations are real or hallucinated.
For each citation below, search the web to determine if it exists.

CITATIONS TO VERIFY:
{chr(10).join(cite_list)}

For each citation, check:
1. Does a paper by this author(s) from this year exist?
2. Does the journal/outlet match?
3. Is the described content roughly correct?

Return a JSON block:
```json
{{
  "verified": [
    {{"key": "Smith2020", "status": "REAL", "note": "Verified in Google Scholar"}},
    {{"key": "Jones2019", "status": "SUSPICIOUS", "note": "Author exists but paper title doesn't match"}},
    {{"key": "Doe2021", "status": "HALLUCINATED", "note": "No such paper found by this author"}}
  ]
}}
```

Status must be: REAL, SUSPICIOUS, or HALLUCINATED.
Only mark HALLUCINATED if you are confident the paper does not exist.
Mark SUSPICIOUS if the author exists but details don't match.
"""

            try:
                from ..config import get_profile
                p_verify = get_profile("stage5_critic")
                verify_resp = run_claude(
                    verify_prompt,
                    model=p_verify["model"], effort=p_verify["effort"],
                    allowed_tools=["WebSearch"],
                    timeout=480, max_retries=1,
                    label="citation-verification",
                )
                verify_result = extract_json(verify_resp)

                if verify_result and "verified" in verify_result:
                    hallucinated = [c for c in verify_result["verified"]
                                    if c.get("status") == "HALLUCINATED"]
                    suspicious = [c for c in verify_result["verified"]
                                  if c.get("status") == "SUSPICIOUS"]
                    real = [c for c in verify_result["verified"]
                            if c.get("status") == "REAL"]

                    print(f"  [5] Citations: {len(real)} real, "
                          f"{len(suspicious)} suspicious, {len(hallucinated)} hallucinated")

                    if hallucinated:
                        print(f"  [5] HALLUCINATED CITATIONS — finding real replacements:")
                        for h in hallucinated:
                            print(f"    - {h['key']}: {h.get('note', '?')}")

                        # For each hallucinated citation, find the paragraph context
                        # and ask Claude to find a REAL paper that supports the same point
                        tex_fixed = tex_content_cite
                        replacements = {}

                        for h in hallucinated:
                            key = h["key"]

                            # Find the paragraph(s) where this citation is used
                            # Get ~200 chars of context around each \cite{key}
                            cite_contexts = []
                            for match in _re_cite.finditer(
                                r'.{0,200}\\cite[pt]?\{' + _re_cite.escape(key) + r'\}.{0,200}',
                                tex_fixed
                            ):
                                cite_contexts.append(match.group().replace("\n", " ").strip())

                            # Also get the original bibitem text
                            bib_match = _re_cite.search(
                                r'\\bibitem\[(.+?)\]\{' + _re_cite.escape(key) +
                                r'\}\s*\n(.+?)(?=\\bibitem|\\end\{thebibliography\})',
                                tex_fixed, _re_cite.DOTALL
                            )
                            original_bib = bib_match.group(2).strip()[:200] if bib_match else "unknown"

                            context_text = "\n".join(cite_contexts[:3]) if cite_contexts else "no context"

                            replace_prompt = f"""A citation in an academic paper was identified as HALLUCINATED
(the paper does not exist). Find a REAL replacement.

HALLUCINATED CITATION:
  Key: {key}
  Original: {original_bib}

CONTEXT WHERE IT'S USED IN THE PAPER:
{context_text}

Search the web for a REAL paper that:
1. Supports the same argument being made in the paragraph
2. Is by a real author, published in a real journal
3. Has a similar topic/finding to what the hallucinated citation claimed

Return a JSON block:
```json
{{
  "found": true,
  "new_key": "AuthorYear",
  "author_year_label": "Author(Year)",
  "bibitem_text": "Author, A. B. (Year). Real paper title. \\\\textit{{Real Journal}}, volume(issue), pages.",
  "note": "Why this paper is a good replacement"
}}
```

If you CANNOT find a suitable replacement, return:
```json
{{
  "found": false,
  "note": "No suitable replacement found"
}}
```
"""
                            try:
                                replace_resp = run_claude(
                                    replace_prompt,
                                    model=p_verify["model"], effort=p_verify["effort"],
                                    allowed_tools=["WebSearch"],
                                    timeout=120, max_retries=1,
                                    label=f"replace-cite-{key}",
                                )
                                replace_result = extract_json(replace_resp)

                                if replace_result and replace_result.get("found"):
                                    replacements[key] = replace_result
                                    print(f"    [{key}] -> {replace_result['new_key']}: "
                                          f"{replace_result.get('note', '')[:80]}")
                                else:
                                    replacements[key] = None
                                    print(f"    [{key}] -> no replacement found, will remove")
                            except Exception as e:
                                replacements[key] = None
                                print(f"    [{key}] -> search failed ({e}), will remove")

                        # Apply replacements.  Bibitem rewrites are confined
                        # to the \begin{thebibliography}...\end{thebibliography}
                        # window (see _bib_block_replace); in-text \cite{}
                        # rewrites are full-document since they have no
                        # multiline DOTALL component and are key-exact.
                        for h in hallucinated:
                            key = h["key"]
                            replacement = replacements.get(key)

                            if replacement:
                                new_key = replacement["new_key"]
                                new_label = replacement["author_year_label"]
                                new_bib = replacement["bibitem_text"]
                                new_bibitem = (
                                    f"\\bibitem[{new_label}]{{{new_key}}}\n"
                                    f"{new_bib}\n\n"
                                )
                                bib_pat = _re_cite.compile(
                                    r'\\bibitem\[.*?\]\{' + _re_cite.escape(key) +
                                    r'\}.*?(?=\\bibitem|\Z)',
                                    _re_cite.DOTALL
                                )
                                tex_fixed = _bib_block_replace(
                                    tex_fixed,
                                    lambda blk, _p=bib_pat, _r=new_bibitem: _p.sub(
                                        lambda _m, _rr=_r: _rr, blk
                                    ),
                                )

                                # Replace in-text citations (key-exact, no DOTALL)
                                tex_fixed = _re_cite.sub(
                                    r'\\cite\{' + _re_cite.escape(key) + r'\}',
                                    f"\\\\cite{{{new_key}}}", tex_fixed
                                )
                                tex_fixed = _re_cite.sub(
                                    r'\\citep\{' + _re_cite.escape(key) + r'\}',
                                    f"\\\\citep{{{new_key}}}", tex_fixed
                                )
                                tex_fixed = _re_cite.sub(
                                    r'\\citet\{' + _re_cite.escape(key) + r'\}',
                                    f"\\\\citet{{{new_key}}}", tex_fixed
                                )
                            else:
                                # No replacement — remove citation entirely.
                                bib_pat = _re_cite.compile(
                                    r'\\bibitem\[.*?\]\{' + _re_cite.escape(key) +
                                    r'\}.*?(?=\\bibitem|\Z)',
                                    _re_cite.DOTALL
                                )
                                tex_fixed = _bib_block_replace(
                                    tex_fixed,
                                    lambda blk, _p=bib_pat: _p.sub("", blk),
                                )
                                tex_fixed = _re_cite.sub(
                                    r'\\cite[pt]?\{' + _re_cite.escape(key) + r'\}',
                                    "", tex_fixed
                                )

                        n_replaced = sum(1 for v in replacements.values() if v)
                        n_removed = sum(1 for v in replacements.values() if not v)
                        if _safe_write_main_tex(
                            main_tex, tex_fixed,
                            label=f"hallucination-fix replaced={n_replaced} removed={n_removed}",
                        ):
                            print(f"  [5] Citations: {n_replaced} replaced with real papers, "
                                  f"{n_removed} removed. Recompiling...")
                            _compile_latex(paper_dir)
                        else:
                            print("  [5] Hallucination-fix payload rejected by integrity guard; original main.tex kept.")

                    if suspicious:
                        print(f"  [5] SUSPICIOUS CITATIONS — attempting auto-correction:")
                        tex_sus = main_tex.read_text(encoding="utf-8")
                        sus_fixes = 0
                        import re as _re_sus

                        for s in suspicious:
                            note = s.get("note", "")
                            key = s["key"]

                            # Extract correct year from verification note
                            year_match = _re_sus.search(
                                r'published\s+(?:in\s+)?(\d{4})', note)
                            if not year_match:
                                # Try "actual year is YYYY" or "correct year: YYYY"
                                year_match = _re_sus.search(
                                    r'(?:actual|correct|real)\s+(?:year\s+(?:is\s+)?)?(\d{4})', note)
                            if not year_match:
                                # Fallback: any 4-digit year in the note
                                year_match = _re_sus.search(r'(\d{4})', note)

                            if year_match:
                                correct_year = year_match.group(1)

                                # Strategy 1: Match \bibitem[Author(YYYY)]{key}
                                # The year is inside parens within the optional arg
                                bib_pattern = _re_sus.compile(
                                    r'(\\bibitem\[[^\]]*?)\((\d{4})\)([^\]]*?\]\{' +
                                    _re_sus.escape(key) + r'\})',
                                    _re_sus.DOTALL
                                )
                                match = bib_pattern.search(tex_sus)

                                if not match:
                                    # Strategy 2: Match \bibitem[Author, YYYY]{key}
                                    bib_pattern = _re_sus.compile(
                                        r'(\\bibitem\[[^\]]*?,\s*)(\d{4})(\s*\]\{' +
                                        _re_sus.escape(key) + r'\})',
                                        _re_sus.DOTALL
                                    )
                                    match = bib_pattern.search(tex_sus)

                                if not match:
                                    # Strategy 3: Find ANY 4-digit year near the bibitem
                                    # Broader search: bibitem line containing key
                                    bib_line_pattern = _re_sus.compile(
                                        r'(\\bibitem\[[^\]]*?)(\d{4})([^\]]*?\]\{' +
                                        _re_sus.escape(key) + r'\})',
                                        _re_sus.DOTALL
                                    )
                                    match = bib_line_pattern.search(tex_sus)

                                if match and match.group(2) != correct_year:
                                    old_year = match.group(2)
                                    tex_sus = tex_sus[:match.start()] + \
                                        match.group(1) + correct_year + match.group(3) + \
                                        tex_sus[match.end():]
                                    sus_fixes += 1
                                    print(f"    [{key}] Fixed year: {old_year} -> {correct_year}")
                                elif match and match.group(2) == correct_year:
                                    print(f"    [{key}] Year already correct ({correct_year})")
                                else:
                                    # Strategy 4: Brute-force replacement of any wrong year
                                    # in the bibitem block for this key.  Search ONLY
                                    # within the bibliography window so a stray
                                    # `\bibitem[...]{key}` placeholder in a preamble
                                    # comment cannot match.
                                    open_tag = r"\begin{thebibliography}"
                                    close_tag = r"\end{thebibliography}"
                                    bi = tex_sus.find(open_tag)
                                    bj = tex_sus.find(close_tag)
                                    if bi < 0 or bj < 0 or bj <= bi:
                                        print(f"    [{key}] bibliography window missing")
                                    else:
                                        bib_window = tex_sus[bi + len(open_tag): bj]
                                        block_pattern = _re_sus.compile(
                                            r'(\\bibitem\[[^\]]*\]\{' + _re_sus.escape(key) +
                                            r'\}.*?)(?=\\bibitem|\Z)',
                                            _re_sus.DOTALL
                                        )
                                        block_match = block_pattern.search(bib_window)
                                        if block_match:
                                            block = block_match.group(0)
                                            years_in_block = _re_sus.findall(r'\b(\d{4})\b', block)
                                            wrong_years = [y for y in years_in_block
                                                           if y != correct_year
                                                           and 1900 <= int(y) <= 2030]
                                            if wrong_years:
                                                old_year = wrong_years[0]
                                                new_block = block.replace(old_year, correct_year, 1)
                                                tex_sus = tex_sus.replace(block, new_block, 1)
                                                sus_fixes += 1
                                                print(f"    [{key}] Fixed year (brute): "
                                                      f"{old_year} -> {correct_year}")
                                            else:
                                                print(f"    [{key}] Could not auto-fix: {note[:80]}")
                                        else:
                                            print(f"    [{key}] bibitem not found for key")
                            else:
                                print(f"    [{key}] No year correction found: {note[:80]}")

                        # Additional pass: validate ALL years in bibliography
                        bib_section = _re_sus.search(
                            r'\\begin\{thebibliography\}.*?\\end\{thebibliography\}',
                            tex_sus, _re_sus.DOTALL
                        )
                        if bib_section:
                            bib_text = bib_section.group(0)
                            import datetime as _dt_cite
                            current_year = _dt_cite.datetime.now().year
                            # Find impossible years
                            for ym in _re_sus.finditer(r'\((\d{4})\)', bib_text):
                                year_val = int(ym.group(1))
                                if year_val > current_year + 1 or year_val < 1800:
                                    print(f"    [WARNING] Impossible citation year: {year_val}")

                        if sus_fixes > 0:
                            if _safe_write_main_tex(
                                main_tex, tex_sus,
                                label=f"suspicious-year-fix x{sus_fixes}",
                            ):
                                print(f"  [5] Fixed {sus_fixes} suspicious citation year(s). Recompiling...")
                                _compile_latex(paper_dir)
                            else:
                                print("  [5] Suspicious-year-fix payload rejected by integrity guard; original main.tex kept.")

            except Exception as e:
                print(f"  [5] Citation verification failed: {e}. Continuing without.")

    # ── Check for internal text contradictions ─────────────────────────
    # Common after multiple R&R rounds: one section says X, another says NOT X
    if main_tex.exists():
        import re as _re_contra
        tex_check = main_tex.read_text(encoding="utf-8")
        contradictions = []

        # Check preregistration contradiction
        has_prereg_yes = bool(_re_contra.search(
            r'pre.?regist(?:er|ration|ered)', tex_check, _re_contra.IGNORECASE))
        has_prereg_no = bool(_re_contra.search(
            r'(?:not|was not|weren.t)\s+pre.?regist', tex_check, _re_contra.IGNORECASE))
        if has_prereg_yes and has_prereg_no:
            contradictions.append("preregistration (both 'preregistered' and 'not preregistered' found)")
            # Auto-fix: keep "not pre-registered" (more honest)
            tex_check = _re_contra.sub(
                r'(?:was|is|were)\s+pre.?registered',
                'was not pre-registered',
                tex_check
            )

        # Check Table~[?] placeholders
        broken_refs_count = tex_check.count("[?]")
        if broken_refs_count > 0:
            contradictions.append(f"{broken_refs_count} broken references ([?]) in text")

        if contradictions:
            print(f"  [5] Text contradictions found:")
            for c in contradictions:
                print(f"    - {c}")
            if _safe_write_main_tex(main_tex, tex_check, label="contradiction-fix"):
                print(f"  [5] Auto-fixed contradictions. Recompiling...")
                _compile_latex(paper_dir)
            else:
                print("  [5] Contradiction-fix payload rejected by integrity guard; original main.tex kept.")
        else:
            print(f"  [5] No text contradictions found.")

    validation = validate_paper(paper_dir, project_dir, compiled=compiled)
    print(f"  [5] {validation.format_for_log()}")

    # Compute paper score from validation results
    counts = validation.summary_counts
    hard_pass = counts.get("hard_passed", counts.get("hard_pass", 0))
    hard_total = counts.get("hard_total", 1)
    soft_pass = counts.get("soft_passed", counts.get("soft_pass", 0))
    soft_total = counts.get("soft_total", 1)

    if hard_pass == hard_total:
        paper_score = 60
    else:
        paper_score = 40

    if soft_total > 0:
        soft_rate = soft_pass / soft_total
        paper_score += int(soft_rate * 40)

    if compiled:
        paper_score = min(100, paper_score + 5)

    print(f"  [5] Paper score: {paper_score}/100 "
          f"(hard {hard_pass}/{hard_total}, soft {soft_pass}/{soft_total}, "
          f"compiled={'yes' if compiled else 'no'})")

    # Save state
    saved_files = []
    if main_tex.exists():
        saved_files.append(str(main_tex))

    state["stages"]["stage5"] = {
        "status": "completed",
        "paper_dir": str(paper_dir),
        "saved_files": saved_files,
        "compiled": compiled,
        "critic_score": paper_score,
        "critic_result": {
            "score": paper_score,
            "summary": f"Computed from validation: hard {hard_pass}/{hard_total}, "
                       f"soft {soft_pass}/{soft_total}",
        },
        "validation": validation.summary_counts,
        "validation_hard_pass": validation.hard_pass,
        "completed_at": datetime.now().isoformat(),
    }

    state["current_stage"] = 5
    save_state(project_dir, state)

    # ── NotebookLM checkpoint (optional, human-confirmed) ──────────────────
    try:
        from ..notebooklm_hooks import stage5_notebooklm_checkpoint
        stage1 = state["stages"].get("stage1", {})
        topic = stage1.get("topic", "academic research")
        paper_pdf = paper_dir / "main.pdf"
        stage5_notebooklm_checkpoint(
            project_dir, state, topic,
            paper_pdf=str(paper_pdf) if paper_pdf.exists() else None,
        )
    except Exception:
        pass

    return state
