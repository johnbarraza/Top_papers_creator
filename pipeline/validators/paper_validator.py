"""Stage 5 automated validator.

Checks objective facts about the generated paper:
section files exist, citations match bib entries, table/figure references
point to real files, word count is reasonable.
"""

import re
from pathlib import Path

from . import CheckLevel, ValidationResult


EXPECTED_SECTIONS = [
    "abstract.tex",
    "01_introduction.tex",
    "02_literature.tex",
    "03_data.tex",
    "04_empirical_strategy.tex",
    "05_results.tex",
    "06_robustness.tex",
    "07_conclusion.tex",
]


def validate(
    paper_dir: Path, project_dir: Path, compiled: bool = False
) -> ValidationResult:
    vr = ValidationResult()
    _check_section_files(vr, paper_dir)
    _check_references_bib(vr, paper_dir)
    _check_citation_keys(vr, paper_dir)
    _check_table_references(vr, paper_dir)
    _check_figure_references(vr, paper_dir)
    _check_compilation(vr, compiled)
    _check_word_count(vr, paper_dir)
    _check_number_consistency(vr, paper_dir, project_dir)
    return vr


# ── HARD checks ──────────────────────────────────────────────────────────────

def _check_section_files(vr: ValidationResult, paper_dir: Path):
    # main.tex
    main_exists = (paper_dir / "main.tex").exists()
    vr.add(
        "main_tex_exists", CheckLevel.HARD, main_exists,
        "main.tex found" if main_exists else "main.tex MISSING"
    )

    # Section content — accept either separate files in sections/ or
    # all content in a single main.tex (preferred)
    main_tex_content = ""
    if main_exists:
        main_tex_content = (paper_dir / "main.tex").read_text(encoding="utf-8")

    sections_dir = paper_dir / "sections"

    # Map section filenames to LaTeX markers that indicate presence in main.tex.
    # Each entry can have multiple alternative markers (OR logic) to handle
    # different naming conventions (e.g. "Literature" vs "Related Work").
    section_markers = {
        "abstract.tex": [r"\begin{abstract}"],
        "01_introduction.tex": [r"\section{Introduction"],
        "02_literature.tex": [r"\section{Literature", r"\section{Related",
                              r"\section{Background", r"\section{Prior"],
        "03_data.tex": [r"\section{Data", r"\section{Experimental Design",
                       r"\section{Research Design", r"\section{Sample",
                       r"\section{Study Design", r"\section{Experiment",
                       r"\section{Context"],
        "04_empirical_strategy.tex": [r"\section{Empirical", r"\section{Method",
                                      r"\section{Identification", r"\section{Estimation",
                                      r"\subsection{Estimation"],
        "05_results.tex": [r"\section{Results", r"\section{Findings"],
        "06_robustness.tex": [r"\section{Robustness", r"\section{Sensitivity"],
        "07_conclusion.tex": [r"\section{Conclusion", r"\section{Discussion"],
    }

    missing = []
    for name in EXPECTED_SECTIONS:
        # Accept if separate file exists
        if sections_dir.exists() and (sections_dir / name).exists():
            continue
        # Accept if any marker for this section is found in main.tex
        markers = section_markers.get(name, [])
        if any(m in main_tex_content for m in markers):
            continue
        missing.append(name)

    vr.add(
        "all_sections_exist", CheckLevel.HARD, len(missing) == 0,
        f"All {len(EXPECTED_SECTIONS)} sections found"
        if not missing else
        f"{len(missing)} section(s) MISSING: {', '.join(missing)}"
    )


def _check_references_bib(vr: ValidationResult, paper_dir: Path):
    bib_path = paper_dir / "references.bib"
    exists = bib_path.exists()
    if not exists:
        vr.add(
            "references_bib_exists", CheckLevel.HARD, False,
            "references.bib MISSING"
        )
        return

    text = bib_path.read_text(encoding="utf-8")
    entries = re.findall(r'@\w+\{', text)
    has_entries = len(entries) >= 1
    vr.add(
        "references_bib_exists", CheckLevel.HARD, has_entries,
        f"references.bib has {len(entries)} entries"
        if has_entries else
        "references.bib exists but has no @entries"
    )


def _check_citation_keys(vr: ValidationResult, paper_dir: Path):
    """Cross-reference \\cite keys in .tex files against references.bib."""
    bib_path = paper_dir / "references.bib"
    if not bib_path.exists():
        vr.add(
            "citation_keys_matched", CheckLevel.SOFT, False,
            "Cannot check — references.bib missing"
        )
        return

    bib_text = bib_path.read_text(encoding="utf-8")
    bib_keys = set(re.findall(r'@\w+\{([^,\s]+)', bib_text))

    # Collect all cite keys from .tex files
    cited_keys = set()
    tex_files = [paper_dir / "main.tex"]

    for tf in tex_files:
        if not tf.exists():
            continue
        text = tf.read_text(encoding="utf-8")
        # Handle \citet{}, \citep{}, \cite{}, \citeauthor{}, \citeyear{}, etc.
        for m in re.finditer(r'\\cite\w*\{([^}]+)\}', text):
            for key in m.group(1).split(","):
                stripped = key.strip()
                if stripped:
                    cited_keys.add(stripped)

    orphan_cites = cited_keys - bib_keys
    vr.add(
        "citation_keys_matched", CheckLevel.SOFT,
        len(orphan_cites) == 0,
        f"All {len(cited_keys)} citation keys found in .bib"
        if not orphan_cites else
        f"{len(orphan_cites)} orphan key(s) not in .bib: "
        f"{', '.join(sorted(orphan_cites)[:15])}"
    )


def _check_table_references(vr: ValidationResult, paper_dir: Path):
    """Check that \\input{tables/X} references point to existing files."""
    tables_dir = paper_dir / "tables"
    all_tex = _gather_tex_text(paper_dir)

    refs = re.findall(r'\\input\{tables/([^}]+)\}', all_tex)
    missing = []
    for ref in refs:
        # Add .tex extension if not present
        fname = ref if ref.endswith(".tex") else ref + ".tex"
        if not (tables_dir / fname).exists():
            missing.append(ref)

    if not refs:
        vr.add(
            "table_references_valid", CheckLevel.SOFT, True,
            "No \\input{tables/...} references found"
        )
    else:
        vr.add(
            "table_references_valid", CheckLevel.HARD,
            len(missing) == 0,
            f"All {len(refs)} table references resolved"
            if not missing else
            f"{len(missing)} table(s) referenced but MISSING: {', '.join(missing)}"
        )


def _check_figure_references(vr: ValidationResult, paper_dir: Path):
    """Check that \\includegraphics{figures/X} references point to existing files."""
    figures_dir = paper_dir / "figures"
    all_tex = _gather_tex_text(paper_dir)

    # Handle optional [...] arguments
    refs = re.findall(
        r'\\includegraphics(?:\[[^\]]*\])?\{figures/([^}]+)\}', all_tex
    )
    missing = []
    for ref in refs:
        # Try exact name, then with .pdf extension
        candidates = [
            figures_dir / ref,
            figures_dir / (ref + ".pdf"),
            figures_dir / (ref + ".png"),
        ]
        if not any(c.exists() for c in candidates):
            missing.append(ref)

    if not refs:
        vr.add(
            "figure_references_valid", CheckLevel.SOFT, True,
            "No \\includegraphics{figures/...} references found"
        )
    else:
        vr.add(
            "figure_references_valid", CheckLevel.HARD,
            len(missing) == 0,
            f"All {len(refs)} figure references resolved"
            if not missing else
            f"{len(missing)} figure(s) referenced but MISSING: {', '.join(missing)}"
        )


# ── SOFT checks ──────────────────────────────────────────────────────────────

def _check_compilation(vr: ValidationResult, compiled: bool):
    vr.add(
        "latex_compiled", CheckLevel.SOFT, compiled,
        "PDF compiled successfully"
        if compiled else
        "LaTeX compilation failed or was not attempted"
    )


def _check_word_count(vr: ValidationResult, paper_dir: Path):
    text = _gather_tex_text(paper_dir)
    # Strip comments
    text = re.sub(r'%.*', '', text)
    # Strip LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?', '', text)
    # Strip braces, brackets
    text = re.sub(r'[{}\[\]]', ' ', text)
    # Strip math
    text = re.sub(r'\$[^$]*\$', ' ', text)
    # Strip begin/end environments
    text = re.sub(r'\\begin\{[^}]*\}|\\end\{[^}]*\}', '', text)
    total_words = len(text.split())

    in_range = 5000 <= total_words <= 15000
    vr.add(
        "word_count", CheckLevel.SOFT, in_range,
        f"{total_words} words"
        if in_range else
        f"{total_words} words (outside 5000-15000 range)"
    )


def _check_number_consistency(
    vr: ValidationResult, paper_dir: Path, project_dir: Path
):
    """Check that key numbers in abstract appear in results_summary."""
    summary_path = _find_results_summary(project_dir)

    # Extract abstract from main.tex
    abstract_text = ""
    main_tex = paper_dir / "main.tex"
    if main_tex.exists():
            import re as _re
            main_content = main_tex.read_text(encoding="utf-8")
            m = _re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', main_content, _re.DOTALL)
            if m:
                abstract_text = m.group(1)

    if not abstract_text or not summary_path:
        vr.add(
            "numbers_consistent", CheckLevel.SOFT, False,
            "Cannot check — abstract or results_summary missing"
        )
        return
    summary_text = summary_path.read_text(encoding="utf-8")

    # Extract numbers with at least one decimal (likely effect sizes / stats)
    # Normalize: strip trailing zeros, handle sign variations
    def _normalize_nums(text):
        raw = re.findall(r'-?\d+\.\d+', text)
        normalized = set()
        for n in raw:
            try:
                val = float(n)
                # Store as rounded to 3 decimals (handles 0.0700 vs 0.070 vs 0.07)
                normalized.add(round(val, 3))
            except ValueError:
                pass
        return normalized

    abstract_nums = _normalize_nums(abstract_text)
    summary_nums = _normalize_nums(summary_text)

    if not abstract_nums:
        vr.add(
            "numbers_consistent", CheckLevel.SOFT, False,
            "No decimal numbers found in abstract -- likely missing exact results"
        )
        return

    overlap = abstract_nums & summary_nums
    vr.add(
        "numbers_consistent", CheckLevel.SOFT, len(overlap) >= 1,
        f"{len(overlap)} number(s) in abstract match results_summary: "
        f"{', '.join(str(x) for x in sorted(overlap)[:5])}"
        if overlap else
        f"No numeric overlap between abstract ({len(abstract_nums)} numbers) "
        f"and results_summary ({len(summary_nums)} numbers)"
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _gather_tex_text(paper_dir: Path) -> str:
    """Read all paper LaTeX content from main.tex."""
    main = paper_dir / "main.tex"
    if main.exists():
        return main.read_text(encoding="utf-8")
    return ""


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
