"""End-to-end integration validator for Stage 7.

Verifies cross-stage consistency: strategy -> code -> results -> paper.
This is the final audit before submission — it checks things that
per-stage validators cannot: that the pieces fit together correctly.
"""

import re
from pathlib import Path

from . import CheckLevel, ValidationResult


def validate(project_dir: Path) -> ValidationResult:
    vr = ValidationResult()
    _check_strategy_to_code(vr, project_dir)
    _check_code_to_results(vr, project_dir)
    _check_results_to_paper(vr, project_dir)
    _check_paper_integrity(vr, project_dir)
    _check_replication_outputs(vr, project_dir)
    return vr


# ── Strategy → Code consistency ──────────────────────────────────────────────

def _check_strategy_to_code(vr: ValidationResult, project_dir: Path):
    """Verify that the code implements what the strategy describes."""
    strategy_path = project_dir / "strategy" / "strategy_memo.md"
    scripts_dir = project_dir / "scripts" / "python"

    if not strategy_path.exists():
        vr.add("strategy_exists", CheckLevel.HARD, False,
               "strategy_memo.md not found")
        return

    strategy = strategy_path.read_text(encoding="utf-8").lower()

    # Check that main script exists
    main_script = scripts_dir / "01_main.py"
    if not main_script.exists():
        vr.add("main_script_exists", CheckLevel.HARD, False,
               "01_main.py not found")
        return

    code = main_script.read_text(encoding="utf-8").lower()

    # Check method alignment: if strategy says DiD, code should use DiD
    method_checks = {
        "difference-in-differences": ["did", "diff_in_diff", "difference",
                                       "att(", "callaway", "csdid",
                                       "pyfixest", "twfe"],
        "instrumental variable": ["iv", "2sls", "instrument", "first_stage",
                                   "ivreg", "iv2sls"],
        "regression discontinuity": ["rdd", "discontinuity", "bandwidth",
                                      "rdrobust", "cutoff"],
        "synthetic control": ["synthetic", "synth", "donor"],
        "event study": ["event_study", "event study", "leads", "lags",
                        "pre_treat", "post_treat"],
    }

    strategy_method = None
    for method_name, _ in method_checks.items():
        if method_name in strategy:
            strategy_method = method_name
            break

    if strategy_method:
        keywords = method_checks[strategy_method]
        found = [kw for kw in keywords if kw in code]
        vr.add(
            "method_alignment", CheckLevel.HARD,
            len(found) > 0,
            f"Strategy specifies '{strategy_method}' — "
            f"code contains: {', '.join(found)}"
            if found else
            f"Strategy specifies '{strategy_method}' but code has NONE of "
            f"the expected keywords: {', '.join(keywords)}"
        )

    # Check that robustness script exists if robustness plan exists
    robustness_plan = project_dir / "strategy" / "robustness_plan.md"
    robustness_script = scripts_dir / "02_robustness.py"
    if robustness_plan.exists():
        vr.add(
            "robustness_script_exists", CheckLevel.HARD,
            robustness_script.exists(),
            "02_robustness.py found"
            if robustness_script.exists() else
            "robustness_plan.md exists but 02_robustness.py is MISSING"
        )

    # Check clustering level: if strategy mentions cluster at X, code should too
    cluster_match = re.search(
        r'cluster.*(?:at|level|by)\s+(?:the\s+)?(\w+)', strategy
    )
    if cluster_match:
        cluster_level = cluster_match.group(1)
        code_has_cluster = cluster_level in code or "cluster" in code
        vr.add(
            "clustering_alignment", CheckLevel.SOFT,
            code_has_cluster,
            f"Strategy clusters at '{cluster_level}' — "
            f"{'found in code' if code_has_cluster else 'NOT found in code'}"
        )


# ── Code → Results consistency ───────────────────────────────────────────────

def _check_code_to_results(vr: ValidationResult, project_dir: Path):
    """Verify that code outputs match what's expected."""
    scripts_dir = project_dir / "scripts" / "python"
    tables_dir = project_dir / "paper" / "tables"
    figures_dir = project_dir / "paper" / "figures"

    # Check that 03_output.py references match actual files
    output_script = scripts_dir / "03_output.py"
    if not output_script.exists():
        vr.add("output_script_exists", CheckLevel.HARD, False,
               "03_output.py not found")
        return

    code = output_script.read_text(encoding="utf-8")

    # Extract table filenames from code
    code_tables = set(re.findall(r'["\']([^"\']*\.tex)["\']', code))
    # Extract figure filenames from code
    code_figures = set(re.findall(r'["\']([^"\']*\.pdf)["\']', code))

    # Check actual files on disk
    disk_tables = set(
        f.name for f in tables_dir.glob("*.tex")
    ) if tables_dir.exists() else set()
    disk_figures = set()
    if figures_dir.exists():
        for ext in ["*.pdf", "*.png", "*.jpg", "*.svg"]:
            disk_figures.update(f.name for f in figures_dir.glob(ext))

    # Tables in code but not on disk
    # Extract just the filename (basename) and filter out non-table files
    code_table_names = set()
    for t in code_tables:
        name = Path(t).name
        # Skip paths that are clearly not output tables (e.g., input files, section files)
        if name.startswith("table") or name.startswith("tab_"):
            code_table_names.add(name)

    missing_tables = code_table_names - disk_tables
    vr.add(
        "code_tables_produced", CheckLevel.HARD,
        len(missing_tables) == 0,
        f"All {len(code_table_names)} tables from 03_output.py found on disk"
        if not missing_tables else
        f"{len(missing_tables)} table(s) in code but NOT on disk: "
        f"{', '.join(sorted(missing_tables)[:5])}"
    )

    # results_summary.md should exist and have substance
    summary = _find_results_summary(project_dir)
    if summary:
        text = summary.read_text(encoding="utf-8")
        word_count = len(text.split())
        vr.add(
            "results_summary_substantive", CheckLevel.SOFT,
            word_count >= 50,
            f"results_summary.md has {word_count} words"
            if word_count >= 50 else
            f"results_summary.md has only {word_count} words — likely too sparse"
        )


# ── Results → Paper consistency ──────────────────────────────────────────────

def _check_results_to_paper(vr: ValidationResult, project_dir: Path):
    """Verify that the paper accurately reflects the code results."""
    paper_dir = project_dir / "paper"
    summary = _find_results_summary(project_dir)

    if not summary:
        vr.add("results_summary_for_paper", CheckLevel.HARD, False,
               "results_summary.md not found — paper may not reflect actual results")
        return

    summary_text = summary.read_text(encoding="utf-8")

    # Normalize numbers for comparison (handles 0.0700 vs 0.070 vs 0.07)
    def _norm_nums(text):
        raw = re.findall(r'-?\d+\.\d+', text)
        normalized = set()
        for n in raw:
            try:
                normalized.add(round(float(n), 3))
            except ValueError:
                pass
        return normalized

    summary_nums = _norm_nums(summary_text)

    # Check if these numbers appear in the paper (main.tex)
    main_tex = paper_dir / "main.tex"
    if not main_tex.exists():
        vr.add("paper_main_tex_exist", CheckLevel.HARD, False,
               "paper/main.tex not found")
        return

    paper_text = main_tex.read_text(encoding="utf-8")
    paper_nums = _norm_nums(paper_text)

    if not summary_nums:
        vr.add("results_in_paper", CheckLevel.SOFT, False,
               "No decimal numbers found in results_summary.md")
        return

    overlap = summary_nums & paper_nums
    overlap_pct = len(overlap) / len(summary_nums) * 100 if summary_nums else 0

    vr.add(
        "results_in_paper", CheckLevel.SOFT,
        overlap_pct >= 30,
        f"{len(overlap)}/{len(summary_nums)} key numbers from results appear "
        f"in paper ({overlap_pct:.0f}%)"
    )

    # Check that abstract has at least one result number
    abstract_text = ""
    m = re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', paper_text, re.DOTALL)
    if m:
        abstract_text = m.group(1)

    if abstract_text:
        abstract_nums = _norm_nums(abstract_text)
        abstract_overlap = abstract_nums & summary_nums
        vr.add(
            "abstract_has_results", CheckLevel.SOFT,
            len(abstract_overlap) >= 1,
            f"Abstract contains {len(abstract_overlap)} numbers from results"
            if abstract_overlap else
            "Abstract contains NO numbers from results_summary -- "
            "main finding may be missing or fabricated"
        )


# ── Paper integrity ──────────────────────────────────────────────────────────

def _check_paper_integrity(vr: ValidationResult, project_dir: Path):
    """Final checks on the paper as a whole."""
    paper_dir = project_dir / "paper"

    # PDF exists and is non-trivial
    pdf = paper_dir / "main.pdf"
    if pdf.exists():
        size_kb = pdf.stat().st_size / 1024
        vr.add(
            "pdf_exists", CheckLevel.HARD, size_kb > 10,
            f"main.pdf exists ({size_kb:.0f} KB)"
            if size_kb > 10 else
            f"main.pdf exists but is only {size_kb:.0f} KB — likely empty/broken"
        )
    else:
        vr.add("pdf_exists", CheckLevel.HARD, False, "main.pdf not found")

    # All sections present in main.tex
    main_tex = paper_dir / "main.tex"
    main_content = main_tex.read_text(encoding="utf-8") if main_tex.exists() else ""
    section_markers = {
        "abstract": [r"\begin{abstract}"],
        "introduction": [r"\section{Introduction"],
        "literature": [r"\section{Literature", r"\section{Related",
                       r"\section{Background", r"\section{Prior"],
        "data": [r"\section{Data", r"\section{Experimental Design",
                r"\section{Research Design", r"\section{Sample",
                r"\section{Study Design", r"\section{Experiment",
                r"\section{Context"],
        "empirical_strategy": [r"\section{Empirical", r"\section{Method",
                               r"\section{Identification", r"\section{Estimation",
                               r"\subsection{Estimation"],
        "results": [r"\section{Results", r"\section{Findings"],
        "robustness": [r"\section{Robustness", r"\section{Sensitivity"],
        "conclusion": [r"\section{Conclusion", r"\section{Discussion"],
    }
    missing = [name for name, markers in section_markers.items()
               if not any(m in main_content for m in markers)]
    vr.add(
        "all_sections_present", CheckLevel.HARD,
        len(missing) == 0,
        f"All {len(section_markers)} sections found in main.tex"
        if not missing else
        f"{len(missing)} section(s) MISSING in main.tex: {', '.join(missing)}"
    )

    # references.bib exists and all citations resolve
    bib_path = paper_dir / "references.bib"
    if bib_path.exists():
        bib_text = bib_path.read_text(encoding="utf-8")
        bib_keys = set(re.findall(r'@\w+\{([^,\s]+)', bib_text))

        cited_keys = set()
        tex_files = [paper_dir / "main.tex"]
        for tf in tex_files:
            if not tf.exists():
                continue
            text = tf.read_text(encoding="utf-8")
            for m in re.finditer(r'\\cite\w*\{([^}]+)\}', text):
                for key in m.group(1).split(","):
                    stripped = key.strip()
                    if stripped:
                        cited_keys.add(stripped)

        orphans = cited_keys - bib_keys
        vr.add(
            "all_citations_resolved", CheckLevel.HARD,
            len(orphans) == 0,
            f"All {len(cited_keys)} citations have .bib entries"
            if not orphans else
            f"{len(orphans)} citation(s) WITHOUT .bib entry: "
            f"{', '.join(sorted(orphans)[:10])}"
        )
    else:
        vr.add("all_citations_resolved", CheckLevel.HARD, False,
               "references.bib not found")

    # Table and figure references point to real files
    all_tex = ""
    if (paper_dir / "main.tex").exists():
        all_tex = (paper_dir / "main.tex").read_text(encoding="utf-8")

    tables_dir = paper_dir / "tables"
    table_refs = re.findall(r'\\input\{tables/([^}]+)\}', all_tex)
    missing_tables = []
    for ref in table_refs:
        fname = ref if ref.endswith(".tex") else ref + ".tex"
        if not (tables_dir / fname).exists():
            missing_tables.append(ref)
    vr.add(
        "table_refs_valid", CheckLevel.HARD,
        len(missing_tables) == 0,
        f"All {len(table_refs)} table references valid"
        if not missing_tables else
        f"{len(missing_tables)} table ref(s) broken: {', '.join(missing_tables)}"
    )

    figures_dir = paper_dir / "figures"
    fig_refs = re.findall(
        r'\\includegraphics(?:\[[^\]]*\])?\{figures/([^}]+)\}', all_tex
    )
    missing_figs = []
    for ref in fig_refs:
        candidates = [
            figures_dir / ref,
            figures_dir / (ref + ".pdf"),
            figures_dir / (ref + ".png"),
        ]
        if not any(c.exists() for c in candidates):
            missing_figs.append(ref)
    vr.add(
        "figure_refs_valid", CheckLevel.HARD,
        len(missing_figs) == 0,
        f"All {len(fig_refs)} figure references valid"
        if not missing_figs else
        f"{len(missing_figs)} figure ref(s) broken: {', '.join(missing_figs)}"
    )


# ── Replication output comparison ────────────────────────────────────────────

def _check_replication_outputs(vr: ValidationResult, project_dir: Path):
    """Check that replication produces consistent outputs."""
    tables_dir = project_dir / "paper" / "tables"
    figures_dir = project_dir / "paper" / "figures"

    # Check that tables are non-empty and contain actual data
    if tables_dir.exists():
        for tex_file in sorted(tables_dir.glob("*.tex")):
            content = tex_file.read_text(encoding="utf-8")
            has_numbers = bool(re.search(r'\d+\.\d+', content))
            has_tabular = "tabular" in content or "booktabs" in content.lower()
            vr.add(
                f"table_has_data:{tex_file.name}", CheckLevel.SOFT,
                has_numbers and has_tabular,
                f"Contains numbers and tabular structure"
                if (has_numbers and has_tabular) else
                f"{'No numbers found' if not has_numbers else ''}"
                f"{'No tabular structure' if not has_tabular else ''}"
            )

    # Check that figures are non-trivial (> 5KB typically means real content)
    if figures_dir.exists():
        for pdf_file in sorted(figures_dir.glob("*.pdf")):
            size_kb = pdf_file.stat().st_size / 1024
            vr.add(
                f"figure_non_trivial:{pdf_file.name}", CheckLevel.SOFT,
                size_kb > 5,
                f"{size_kb:.0f} KB"
                if size_kb > 5 else
                f"Only {size_kb:.1f} KB — likely blank or broken"
            )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _find_results_summary(project_dir: Path):
    for candidate in [
        project_dir / "scripts" / "python" / "results_summary.md",
        project_dir / "data" / "clean" / "results_summary.md",
        project_dir / "paper" / "results_summary.md",
        project_dir / "paper" / "tables" / "results_summary.md",
        project_dir / "results_summary.md",
    ]:
        if candidate.exists():
            return candidate
    return None
