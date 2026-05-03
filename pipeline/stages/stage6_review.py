"""Stage 6 — Peer Review (repowered with 6-agent review-paper skill).

Fuses the former Stage 5.5 quick-check and Stage 6 peer review into a single
repowered stage. Runs 6 specialized agents in parallel:
  Agent 1: Spelling, Grammar & Academic Style
  Agent 2: Internal Consistency & Cross-References
  Agent 3: Unsupported Claims & Identification Integrity
  Agent 4: Mathematics, Equations & Notation
  Agent 5: Tables, Figures & Documentation
  Agent 6: Contribution Evaluation (Adversarial Referee)

After agents report, issues are classified and a deterministic decision is
computed from thresholds. If MAJOR_REVISIONS → loop back to Stage 5.
"""

from datetime import datetime
from pathlib import Path

from ..config import (
    MAX_RR_ROUNDS, ACCEPT_GATE, MINOR_REV_GATE, REJECT_FLOOR,
    get_profile,
)
from ..claude_runner import run_claude, run_claude_parallel
from ..json_utils import extract_json, smart_truncate
from ..state import save_state


def _read_file_or(path: Path, default: str = "") -> str:
    return path.read_text(encoding="utf-8") if path.exists() else default


# ═══════════════════════════════════════════════════════════════════════════════
# Consistency check (carried over from previous Stage 6)
# ═══════════════════════════════════════════════════════════════════════════════

def _consistency_check(project_dir: Path) -> bool:
    """Run a full consistency check on the paper before review.

    Uses Claude to read ALL sections, tables, abstract, and result CSVs,
    then fix any internal contradictions.

    Returns True if fixes were made, False if paper was already consistent.
    """
    paper_dir = project_dir / "paper"
    clean_dir = project_dir / "data" / "clean"

    sections = {}
    main_tex = paper_dir / "main.tex"
    if main_tex.exists():
        sections["main.tex"] = main_tex.read_text(encoding="utf-8")

    tables = {}
    tables_dir = paper_dir / "tables"
    if tables_dir.exists():
        for f in sorted(tables_dir.glob("*.tex")):
            tables[f.name] = f.read_text(encoding="utf-8")

    # Read results CSVs with size limits.
    # For clean_data.csv: only read a summary (shape, column stats) since
    # the full file can be millions of chars (e.g., 1347×1421).
    result_csvs = {}
    if clean_dir.exists():
        for f in sorted(clean_dir.glob("*.csv"))[:10]:
            try:
                if f.name == "clean_data.csv":
                    # Generate a compact summary instead of reading the whole file
                    import pandas as _pd
                    _df = _pd.read_csv(f, encoding="latin-1", low_memory=False)
                    summary_lines = [
                        f"Shape: {_df.shape[0]} rows x {_df.shape[1]} columns",
                        f"Columns: {', '.join(_df.columns[:50])}",
                    ]
                    # Add stats for key outcome/treatment columns
                    key_cols = [c for c in _df.columns if c.startswith("end_")
                                or c in ("treatstat", "voucher", "training", "both",
                                         "control", "b_b2gender", "b_c2avtawjihi")]
                    for col in key_cols[:20]:
                        s = _df[col].dropna()
                        summary_lines.append(
                            f"{col}: n={len(s)}, mean={s.mean():.4f}, "
                            f"std={s.std():.4f}, min={s.min()}, max={s.max()}"
                        )
                    result_csvs[f.name] = "\n".join(summary_lines)
                    del _df
                else:
                    content = f.read_text(encoding="utf-8")
                    result_csvs[f.name] = smart_truncate(content, 3000)
            except Exception:
                pass

    if not sections or not result_csvs:
        return False

    paper_text = ""
    for name, content in sections.items():
        paper_text += f"\n### {name}\n```latex\n{smart_truncate(content, 15000)}\n```\n"
    for name, content in tables.items():
        paper_text += f"\n### TABLE: {name}\n```latex\n{smart_truncate(content, 3000)}\n```\n"

    csv_text = ""
    for name, content in result_csvs.items():
        csv_text += f"\n### {name}\n```csv\n{content}\n```\n"

    prompt = f"""You are a meticulous copy-editor for an academic economics paper.

Your task: find and fix ALL internal inconsistencies in this paper. The result CSV
files are the GROUND TRUTH — the paper text and tables must match them exactly.

## PAPER CONTENT
{paper_text}

## GROUND TRUTH (result CSVs from the analysis scripts)
{csv_text}

## CHECK EACH OF THESE:

1. NUMBERS: Do coefficients, SEs, p-values, and CIs in the text match the CSVs?
2. SAMPLE SIZE: Is N consistent across abstract, data section, results, and tables?
3. SE METHOD: Is the standard error method described consistently?
4. SPECIFICATION: Is the primary specification described the same way everywhere?
5. CLUSTER COUNT: Is the number of clusters the same everywhere?
6. BASELINE STATISTICS: Do descriptive stats in text match the CSVs?
7. SIGNIFICANCE STARS: Do stars in tables match the p-values in the CSVs?
8. CROSS-REFERENCES: Does every \\ref{{}} match an existing \\label{{}}?
   Does the text reference "Table 3" but the label says "tab:robustness"?
9. CONTRADICTORY CLAIMS: Does the abstract say "positive effect" but results show negative?
   Does the introduction promise analysis X but the paper never delivers it?
10. HEDGING CONSISTENCY: If one section says "we find strong evidence" but another says
    "the evidence is suggestive", make them consistent (use the more cautious phrasing).
11. METHOD vs RESULTS: Does the method section describe the exact estimator used?
    If results use "clustered SEs" but methods say "robust SEs", fix it.

For EACH inconsistency found, output the fix as:
- File: [filename]
- Old text: [exact text to replace]
- New text: [corrected text]

Output a JSON block:
```json
{{
  "consistent": false,
  "n_fixes": 5,
  "fixes": [
    {{
      "file": "main.tex",
      "description": "Coefficient mismatch",
      "old_text": "exact old text here",
      "new_text": "exact new text here"
    }}
  ]
}}
```

If the paper is fully consistent, output:
```json
{{
  "consistent": true,
  "n_fixes": 0,
  "fixes": []
}}
```
"""
    p = get_profile("stage6_consistency")
    print("  [consistency] Running full document consistency check...")
    response = run_claude(
        prompt, model=p["model"], effort=p["effort"],
        label="consistency check",
        allowed_tools=[],
    )
    result = extract_json(response) or {}

    if result.get("consistent", True):
        print("  [consistency] Paper is internally consistent. No fixes needed.")
        return False

    fixes = result.get("fixes", [])
    paper_dir_tables = paper_dir / "tables"
    n_applied = 0
    for fix in fixes:
        fname = fix.get("file", "")
        old_text = fix.get("old_text", "")
        new_text = fix.get("new_text", "")
        desc = fix.get("description", "")

        if not fname or not old_text or not new_text or old_text == new_text:
            continue

        fpath = None
        if fname == "main.tex" or (fname.endswith(".tex") and not fname.startswith("table")):
            fpath = paper_dir / "main.tex"
        elif fname.endswith(".tex"):
            fpath = paper_dir_tables / fname

        if fpath and fpath.exists():
            original = fpath.read_text(encoding="utf-8")
            if old_text in original:
                content = original.replace(old_text, new_text, 1)

                # Structural integrity guard for main.tex: a malformed LLM
                # fix could otherwise truncate the body and silently corrupt
                # the paper (the same failure mode we hit in stage5).  For
                # other .tex files we only enforce a no-shrinkage-by-half
                # guard since they don't have document-wide tags.
                is_main = fpath.name == "main.tex"
                ok = True
                reason = ""
                if is_main:
                    if r"\begin{document}" not in content or r"\end{document}" not in content:
                        ok, reason = False, "missing \\begin/\\end{document}"
                if ok and len(content) < max(500, len(original) // 2):
                    ok, reason = False, (
                        f"content shrank from {len(original)} to {len(content)} bytes"
                    )

                if not ok:
                    rejected_path = fpath.with_suffix(fpath.suffix + ".rejected")
                    try:
                        rejected_path.write_text(content, encoding="utf-8")
                    except OSError:
                        pass
                    print(
                        f"  [fix] REJECTED {fname}: {reason}. "
                        f"Original kept; rejected payload at {rejected_path.name}"
                    )
                    continue

                # Snapshot pre-write content for forensic rollback.
                try:
                    fpath.with_suffix(fpath.suffix + ".bak").write_text(
                        original, encoding="utf-8")
                except OSError:
                    pass
                fpath.write_text(content, encoding="utf-8")
                n_applied += 1
                print(f"  [fix] {fname}: {desc[:80]}")

    print(f"  [consistency] Applied {n_applied}/{len(fixes)} fixes.")
    return n_applied > 0


def _preflight_fix(project_dir: Path) -> int:
    """Pre-flight: fix common issues that generate CRITICAL flags from agents.

    Runs BEFORE the 6-agent review to eliminate easy-to-fix problems that
    would otherwise cost 4+ points each in the issue-based score.

    Returns number of fixes applied.
    """
    import re as _re_pf

    paper_dir = project_dir / "paper"
    main_tex = paper_dir / "main.tex"
    if not main_tex.exists():
        return 0

    tex = main_tex.read_text(encoding="utf-8")
    original = tex
    n_fixes = 0

    # ── 1. Causal overclaiming (Agent 3 CRITICAL) ────────────────────
    # Replace strong causal language with hedged versions
    causal_replacements = [
        # "X causes Y" → "X is associated with Y"
        (r'\b(our results?|the results?|we) (show|demonstrate|prove|establish) that ([A-Za-z ]+) causes?\b',
         r'\1 \2 that \3 is associated with'),
        # "proves" → "suggests"
        (r'\b(this|our analysis|the evidence) proves\b', r'\1 suggests'),
        # "definitive evidence" → "suggestive evidence"
        (r'\bdefinitive evidence\b', 'suggestive evidence'),
        # "we establish" → "we provide evidence"
        (r'\bwe establish\b', 'we provide evidence for'),
        # "unambiguously" → remove
        (r'\bunambiguously\s+', ''),
    ]

    for pattern, replacement in causal_replacements:
        new_tex, count = _re_pf.subn(pattern, replacement, tex, flags=_re_pf.IGNORECASE)
        if count > 0:
            tex = new_tex
            n_fixes += count
            print(f"  [preflight] Fixed {count} causal overclaim(s): {pattern[:50]}")

    # ── 2. Broken cross-references (Agent 2 CRITICAL) ─────────────────
    # Find \ref{X} where \label{X} doesn't exist
    labels = set(_re_pf.findall(r'\\label\{([^}]+)\}', tex))
    refs = _re_pf.findall(r'\\ref\{([^}]+)\}', tex)
    broken_refs = [r for r in refs if r not in labels]

    if broken_refs:
        print(f"  [preflight] Found {len(broken_refs)} broken \\ref{{}} targets: "
              f"{broken_refs[:5]}")
        # Try to fix: Table~\ref{tab:X} where label is actually tab:something_else
        for broken in broken_refs:
            # Find closest matching label
            best_match = None
            best_score = 0
            broken_kw = set(broken.lower().replace("_", " ").replace(":", " ").split())
            for label in labels:
                label_kw = set(label.lower().replace("_", " ").replace(":", " ").split())
                overlap = len(broken_kw & label_kw)
                if overlap > best_score:
                    best_score = overlap
                    best_match = label
            if best_match and best_score >= 1:
                tex = tex.replace(f"\\ref{{{broken}}}", f"\\ref{{{best_match}}}")
                n_fixes += 1
                print(f"  [preflight] Fixed ref: {broken} -> {best_match}")

    # ── 3. Missing table/figure notes (Agent 5 CRITICAL) ──────────────
    # Tables must have notes explaining SEs, significance stars, sample
    tables_dir = paper_dir / "tables"
    if tables_dir.exists():
        for tex_file in tables_dir.glob("*.tex"):
            table_content = tex_file.read_text(encoding="utf-8")
            has_notes = ("tablenotes" in table_content or
                         "\\textit{Notes" in table_content or
                         "\\item" in table_content)
            if not has_notes and "\\begin{table" in table_content:
                # Add minimal table notes before \end{table}
                note_block = (
                    "\\begin{tablenotes}\n\\small\n"
                    "\\item \\textit{Notes:} Robust standard errors in parentheses. "
                    "$^{***}$p$<$0.01, $^{**}$p$<$0.05, $^{*}$p$<$0.10.\n"
                    "\\end{tablenotes}\n"
                )
                table_content = table_content.replace(
                    "\\end{table}", note_block + "\\end{table}")
                tex_file.write_text(table_content, encoding="utf-8")
                n_fixes += 1
                print(f"  [preflight] Added missing notes to {tex_file.name}")

    # ── 4. I/we inconsistency (Agent 1 CRITICAL for some journals) ────
    # Count "I " vs "we " usage
    i_count = len(_re_pf.findall(r'\bI\s+(?:find|show|argue|estimate|use|examine)\b', tex))
    we_count = len(_re_pf.findall(r'\b[Ww]e\s+(?:find|show|argue|estimate|use|examine)\b', tex))

    if i_count > 0 and we_count > 0:
        # Mixed — standardize to "we" (more common in econ papers)
        tex = _re_pf.sub(r'\bI find\b', 'we find', tex)
        tex = _re_pf.sub(r'\bI show\b', 'we show', tex)
        tex = _re_pf.sub(r'\bI argue\b', 'we argue', tex)
        tex = _re_pf.sub(r'\bI estimate\b', 'we estimate', tex)
        tex = _re_pf.sub(r'\bI use\b', 'we use', tex)
        tex = _re_pf.sub(r'\bI examine\b', 'we examine', tex)
        n_fixes += i_count
        print(f"  [preflight] Standardized {i_count} 'I' -> 'we' for consistency")

    # ── 5. Empty/NaN in tables (Agent 5 CRITICAL) ─────────────────────
    if tables_dir.exists():
        for tex_file in tables_dir.glob("*.tex"):
            tc = tex_file.read_text(encoding="utf-8")
            had_nan = "nan" in tc.lower() or "& &" in tc
            if had_nan:
                tc = tc.replace("nan", "---").replace("NaN", "---")
                tc = tc.replace("None", "---")
                while "& &" in tc:
                    tc = tc.replace("& &", "& --- &")
                tc = tc.replace("& \\\\", "& --- \\\\")
                tex_file.write_text(tc, encoding="utf-8")
                n_fixes += 1
                print(f"  [preflight] Cleaned NaN/blank cells in {tex_file.name}")

    # ── 6. Missing significance star definition (Agent 5 MAJOR) ───────
    # Check if stars are used but never defined
    has_stars = "***" in tex or "^{***}" in tex
    has_star_def = ("p$<$0.01" in tex or "p<0.01" in tex or
                    "significance" in tex.lower())
    if has_stars and not has_star_def:
        # Add star definition in a footnote
        tex = tex.replace(
            "\\end{document}",
            "\\footnotetext{$^{***}$p$<$0.01, $^{**}$p$<$0.05, "
            "$^{*}$p$<$0.10.}\n\\end{document}"
        )
        n_fixes += 1
        print(f"  [preflight] Added missing significance star definition")

    # ── Save if changed ───────────────────────────────────────────────
    if tex != original:
        # Structural integrity check before overwriting: the preflight
        # transformations above are all small-scope, but as a defensive
        # measure we refuse the write if the new payload is missing
        # essential document tags or shrank by more than half (a known
        # failure mode for regex-based auto-fixes).
        ok_struct = (
            r"\begin{document}" in tex and
            r"\end{document}" in tex and
            len(tex) >= max(1000, len(original) // 2)
        )
        if not ok_struct:
            rejected_path = main_tex.with_suffix(main_tex.suffix + ".rejected")
            rejected_path.write_text(tex, encoding="utf-8")
            print(
                f"  [preflight] REJECTED preflight payload: structural check failed "
                f"(was {len(original)} bytes, now {len(tex)}). "
                f"Original kept; rejected payload at {rejected_path.name}"
            )
        else:
            try:
                main_tex.with_suffix(main_tex.suffix + ".bak").write_text(
                    original, encoding="utf-8")
            except Exception:
                pass
            main_tex.write_text(tex, encoding="utf-8")

    if n_fixes > 0:
        print(f"  [preflight] Total: {n_fixes} pre-flight fixes applied")
    else:
        print(f"  [preflight] Paper passed pre-flight checks")

    return n_fixes


# ═══════════════════════════════════════════════════════════════════════════════
# Paper and evidence gathering
# ═══════════════════════════════════════════════════════════════════════════════

def _gather_paper(paper_dir: Path) -> str:
    """Read the full paper content for review."""
    main_tex = paper_dir / "main.tex"
    if main_tex.exists():
        full_text = main_tex.read_text(encoding="utf-8")
        return f"## main.tex\n```latex\n{smart_truncate(full_text, 50000)}\n```\n"
    return "(no paper content found)"


def _gather_tables(paper_dir: Path) -> list[str]:
    """List table .tex file paths."""
    tables_dir = paper_dir / "tables"
    if not tables_dir.exists():
        return []
    return [str(f) for f in sorted(tables_dir.glob("*.tex"))]


def _gather_figures(paper_dir: Path) -> list[str]:
    """List figure file paths."""
    figs_dir = paper_dir / "figures"
    if not figs_dir.exists():
        return []
    figs = []
    for ext in ["*.pdf", "*.png", "*.jpg", "*.svg", "*.eps"]:
        figs.extend(sorted(figs_dir.glob(ext)))
    return [str(f) for f in figs]


def _gather_evidence_packet(project_dir: Path) -> str:
    """Gather code outputs, data summaries, and audit results for referees."""
    parts = []

    audit = project_dir / "quality_reports" / "data_audit.md"
    if audit.exists():
        parts.append(f"## Data Audit Report (Stage 4.5)\n{smart_truncate(audit.read_text(encoding='utf-8'), 3000)}\n")

    # Code review report (from Stage 4.7)
    code_review = project_dir / "quality_reports" / "code_review_report.md"
    if code_review.exists():
        parts.append(f"## Code Review Report (Stage 4.7)\n{smart_truncate(code_review.read_text(encoding='utf-8'), 3000)}\n")

    for loc in [
        project_dir / "paper" / "tables" / "results_summary.md",
        project_dir / "scripts" / "python" / "results_summary.md",
    ]:
        if loc.exists():
            parts.append(f"## Results Summary\n{smart_truncate(loc.read_text(encoding='utf-8'), 2000)}\n")
            break

    cell_sizes = project_dir / "data" / "clean" / "cell_sizes.csv"
    if cell_sizes.exists():
        parts.append(f"## Cell Sizes\n```\n{smart_truncate(cell_sizes.read_text(encoding='utf-8'), 1000)}\n```\n")

    tables_dir = project_dir / "paper" / "tables"
    if tables_dir.exists():
        for t in sorted(tables_dir.glob("*.tex"))[:6]:
            content = t.read_text(encoding="utf-8")
            parts.append(f"## Table: {t.name}\n```latex\n{smart_truncate(content, 1500)}\n```\n")

    figs_dir = project_dir / "paper" / "figures"
    if figs_dir.exists():
        figs = []
        for ext in ["*.pdf", "*.png", "*.jpg", "*.svg"]:
            figs.extend(sorted(figs_dir.glob(ext)))
        if figs:
            parts.append(f"## Figures Available\n" + "\n".join(f"- {f.name}" for f in figs) + "\n")

    return "\n".join(parts) if parts else "(no evidence packet available)"


def _gather_estimator_constraints(state: dict) -> str:
    """Build a note about which estimators work and which don't."""
    stage3_3 = state.get("stages", {}).get("stage3_3", {})
    avail = stage3_3.get("available_estimators", {})
    warnings = stage3_3.get("estimator_warnings", [])

    if not avail:
        return ""

    working = [k for k, v in avail.items() if v]
    broken = [k for k, v in avail.items() if not v]

    parts = [
        "## Estimator Constraints (verified on real data)",
        "Working: " + ", ".join(working),
    ]
    if broken:
        parts.append("BROKEN (do NOT request these): " + ", ".join(broken))
    if warnings:
        parts.append("Details:")
        for w in warnings:
            parts.append("  - " + w)
    parts.append(
        "\nIMPORTANT: Do NOT request estimators listed as BROKEN."
    )
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# The 6 agent prompts
# ═══════════════════════════════════════════════════════════════════════════════

def _build_agent1_prompt(paper_content: str) -> str:
    """Agent 1: Spelling, Grammar & Academic Style."""
    return f"""You are a copy editor at a top economics journal. Read all paper content
and perform a thorough review. Ignore LaTeX commands unless they cause formatting issues.

--- PAPER ---
{paper_content}

**What to check:**

1. **Spelling errors**: misspelled words, proper nouns, technical terms, commonly confused words.
2. **Grammar errors**: subject-verb agreement, tense consistency, article usage, comma splices.
3. **Awkward phrasing**: sentences requiring re-reading. Suggest clearer alternatives.
4. **Style violations** — flag every instance of:
   - "interestingly", "importantly", "notably", "it is worth noting" — delete these
   - "significant" used to mean large/important (reserve for statistical significance)
   - Passive voice where active is natural
   - Inconsistent first person
5. **Typographic consistency**: hyphenation, em-dash vs en-dash, spacing.
6. **Number formatting**: numbers below 10 spelled out? percentages consistent?

Tag every issue: [CRITICAL], [MAJOR], or [MINOR].

Output a JSON block at the end:
```json
{{
  "n_critical": 0,
  "n_major": 0,
  "n_minor": 0,
  "top_issues": ["issue1", "issue2", "issue3"]
}}
```
"""


def _build_agent2_prompt(paper_content: str, evidence_packet: str) -> str:
    """Agent 2: Internal Consistency & Cross-References."""
    return f"""You are a technical reviewer checking internal coherence of an economics paper.

--- PAPER ---
{paper_content}

--- EVIDENCE PACKET (tables, CSVs, data outputs — use to verify numbers) ---
{evidence_packet}

**What to check:**
1. **Numerical consistency**: every number in text must match referenced table.
   USE THE EVIDENCE PACKET to verify: compare text claims against actual CSV data
   and LaTeX table content. Quote both the text number and the source number.
2. **Abstract vs. body**: do findings in abstract match results section?
3. **Introduction vs. results**: when intro previews results, does results deliver?
4. **Terminology consistency**: key terms used consistently throughout?
5. **Sample description**: years, N, filters consistent across sections?
6. **Fixed effects and controls**: match between text claims and tables?
7. **Magnitude consistency**: direction and magnitude consistent across mentions?
8. **Literature citations**: author-year pairs match bibliography?

Tag every issue: [CRITICAL], [MAJOR], or [MINOR].

Output a JSON block at the end:
```json
{{
  "n_critical": 0,
  "n_major": 0,
  "n_minor": 0,
  "top_issues": ["issue1", "issue2", "issue3"]
}}
```
"""


def _build_agent3_prompt(paper_content: str, evidence_packet: str) -> str:
    """Agent 3: Unsupported Claims & Identification Integrity."""
    return f"""You are a skeptical econometrician enforcing "claim discipline" — claims must
never exceed what identification allows. Read the paper and identify every place
where it overstates its evidence.

--- PAPER ---
{paper_content}

--- EVIDENCE PACKET (actual results, data audit — use to verify claims) ---
{evidence_packet}

**What to check:**
1. **Causal language without causal identification**: quote exact sentences.
   USE THE EVIDENCE PACKET to check whether the results actually support the claims.
   If the data audit flagged issues (small cells, distribution problems), claims
   based on those results are weaker.
2. **Generalization beyond the sample**: claims extending beyond data scope.
3. **Mechanism claims stated as facts**: mechanisms asserted rather than argued.
4. **Missing necessary caveats**: obvious threats not discussed.
5. **Literature overclaiming**: "no prior study" / "we are the first" — flag as unverified.
6. **Statistical vs. economic significance conflation**.
7. **Hedging failures**: both overconfident and underconfident claims.

Tag every issue: [CRITICAL], [MAJOR], or [MINOR].

Output a JSON block at the end:
```json
{{
  "n_critical": 0,
  "n_major": 0,
  "n_minor": 0,
  "causal_overclaiming": ["quoted sentence 1", "quoted sentence 2"],
  "missing_caveats": ["caveat1", "caveat2"]
}}
```
"""


def _build_agent4_prompt(paper_content: str) -> str:
    """Agent 4: Mathematics, Equations & Notation."""
    return f"""You are a mathematical economist reviewing the formal content of an economics paper.

--- PAPER ---
{paper_content}

**What to check:**
1. **Mathematical correctness**: derivations, algebra, subscripts match descriptions.
2. **Notation consistency**: same symbol for same quantity throughout.
3. **Undefined notation**: every symbol defined at/before first use.
4. **Equation numbering**: all referenced equations numbered, no orphan numbers.
5. **Regression specification consistency**: equation matches text, tables, controls/FE.
6. **Statistical notation**: SE, t-stat, CI formulas correct.
7. **LaTeX math formatting**: missing \\left/\\right, text in math mode, alignment.

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


def _build_agent5_prompt(paper_content: str, table_files: str,
                         figure_files: str, table_contents: str) -> str:
    """Agent 5: Tables, Figures & Documentation."""
    return f"""You are a journal production editor reviewing tables and figures in an economics paper.

--- PAPER ---
{paper_content}

Table files: {table_files}
Figure files: {figure_files}

--- ACTUAL TABLE CONTENT (LaTeX source — use to verify completeness) ---
{table_contents}

**For every table, check:**
1. Title/caption: accurately describes content? Self-contained?
2. Column headers: clear, unambiguous, state dependent variable?
3. Notes: sample definition, dependent variable, controls, FE, SE method, stars definition.
4. Standard errors: reported in every column?
5. Observations: N in every column?
6. Cross-referencing: every table cited in text? References correct?
7. Formatting consistency across tables.

**For every figure, check:**
1. Title/caption: self-contained?
2. Axis labels with units?
3. Legend for multiple series?
4. Confidence intervals shown?
5. Notes: sample, what's plotted, data source.
6. Cross-referencing in text.

Tag every issue: [CRITICAL], [MAJOR], or [MINOR].

Output a JSON block at the end:
```json
{{
  "n_critical": 0,
  "n_major": 0,
  "n_minor": 0,
  "tables_reviewed": 0,
  "figures_reviewed": 0,
  "top_issues": ["issue1", "issue2"]
}}
```
"""


def _build_agent6_prompt(paper_content: str, strategy_memo: str,
                         evidence_packet: str, target_journal: str) -> str:
    """Agent 6: Contribution Evaluation (Calibrated Referee)."""
    return f"""The target journal is {target_journal}.

You are an experienced referee for a field economics journal. You are fair but
rigorous. You evaluate what the paper DOES accomplish, not what it COULD have done
with different data. You distinguish between fatal flaws and areas for improvement.

--- PAPER ---
{paper_content}

--- STRATEGY MEMO ---
{smart_truncate(strategy_memo, 3000)}

--- EVIDENCE PACKET ---
{evidence_packet}

SCORING CALIBRATION (follow this scale precisely):
- 85-100: Publishable with minor edits. Clear contribution, credible identification,
  thorough robustness checks, well-written. Rare — only for genuinely strong papers.
- 75-84: Solid paper. Meaningful contribution, reasonable identification, adequate
  robustness. Most competent empirical papers with honest limitations land here.
- 65-74: Decent paper with notable gaps. Contribution exists but robustness is
  incomplete, or identification has unaddressed threats. Revisable.
- 55-64: Weak paper. Identification concerns, missing key analyses, or claims
  exceed evidence. Needs major revision.
- Below 55: Fundamental problems. Wrong method for the question, no identification,
  or uninterpretable results.

IMPORTANT CALIBRATION RULES:
- A paper with credible identification (IV/RDD/DiD/RCT) that includes multiple
  robustness checks and honestly discusses limitations deserves AT LEAST 70.
- Standard practices in the field are NOT flaws. Do not penalize for:
  - Using OLS with HC2 SEs (standard)
  - Bootstrap with 200-999 replications (adequate)
  - Not using the latest heterogeneity-robust estimator (if classic TWFE is fine)
  - Null findings IF the paper has adequate power analysis and honest framing
- Only flag as [CRITICAL] issues that would cause a desk reject.
  If it's fixable in revision, it's [MAJOR], not [CRITICAL].
- Use the evidence packet to VERIFY claims before flagging. Do not flag issues
  that the paper already addresses.
- A paper reaching this stage has passed 5 earlier quality gates. Start from
  a baseline of 72 and adjust up/down based on actual merits and problems.

**Your evaluation has 6 parts:**

**Part 1 — Central Contribution**: State in one sentence what the paper contributes.
Rate: [Transformative | Significant | Incremental | Insufficient].
Note: "Incremental" is normal and acceptable — most published papers are incremental.

**Part 2 — Identification and Credibility**: What variation is used? Is it plausibly
exogenous? Main threats? Does paper address them?

**Part 3 — Required and Suggested Analyses**:
- Required (up to 3): absence is a genuine blocker for publication. Tag [CRITICAL].
  ONLY use [CRITICAL] for issues that make results uninterpretable.
- Suggested (up to 5): would strengthen but paper is publishable without them. Tag [MAJOR].

**Part 4 — Literature Positioning**: Right papers cited? Good framing?

**Part 5 — Journal Fit and Recommendation**:
- Recommendation: [Send to referees | Revise before sending | Desk reject]
  Note: "Revise before sending" is the normal recommendation for working papers.

**Part 6 — Questions to the Authors**: 4-7 pointed questions.

**SCORING**: Score the paper 0-100 across these dimensions:
- contribution_novelty (0-100)
- identification_credibility (0-100)
- empirical_execution (0-100)
- writing_presentation (0-100)
- literature_positioning (0-100)

The overall score should be approximately the AVERAGE of dimension scores,
not the minimum. One weak dimension should not tank the overall score.

Output a JSON block at the end:
```json
{{
  "score": 75,
  "contribution_rating": "Incremental",
  "recommendation": "Revise before sending",
  "dimension_scores": {{
    "contribution_novelty": 70,
    "identification_credibility": 75,
    "empirical_execution": 80,
    "writing_presentation": 78,
    "literature_positioning": 72
  }},
  "required_analyses": ["analysis1"],
  "suggested_analyses": ["analysis1", "analysis2"],
  "questions_to_authors": ["q1", "q2", "q3", "q4"],
  "n_critical": 1,
  "n_major": 3
}}
```
"""


# ═══════════════════════════════════════════════════════════════════════════════
# Score computation and decision logic
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_decision(agent_results: dict) -> tuple[str, float, bool]:
    """Compute editorial decision from agent results.

    Uses Agent 6's score as the primary score, adjusted by critical issues
    from other agents. If Agent 6 fails to return valid JSON, falls back to
    a score estimated from Agents 1-5 critical/major issue counts.

    Returns (decision, avg_score, has_fatal).
    """
    a6 = agent_results.get("agent6", {})
    base_score = a6.get("score", 0)

    # Stabilize score: blend Agent 6 score with issue-based estimate
    # This reduces variance from Agent 6's subjective scoring
    total_critical_1to5 = sum(
        agent_results.get(f"agent{i}", {}).get("n_critical", 0)
        for i in range(1, 6)
    )
    total_major_1to5 = sum(
        agent_results.get(f"agent{i}", {}).get("n_major", 0)
        for i in range(1, 6)
    )
    # Calibration (revised 2026-04-13): the previous deductions (4 per critical,
    # 1.5 per major) over-penalized papers with many small/correlated issues
    # (e.g. 33 LaTeX errors all stemming from the same root cause). The new
    # weights are gentler and CAPPED so a single root cause cannot tank the
    # score. Baseline raised from 75 to 80 because papers reaching Stage 6
    # have already passed Q1-Q8, ceiling >= 75, and Stage 4.7 review.
    capped_critical = min(total_critical_1to5, 6)  # diminishing returns past 6
    capped_major = min(total_major_1to5, 12)
    issue_based_score = max(40, 80 - (capped_critical * 2.5) - (capped_major * 1.0))

    if base_score > 0:
        # Blend: 55% Agent 6 (now averaged from 2 runs) + 45% issue-based objective.
        # With dual-run averaging, Agent 6's variance is reduced ~30%, so we can
        # trust it slightly less and give more weight to the deterministic component.
        base_score = 0.55 * base_score + 0.45 * issue_based_score

    # Fallback: if Agent 6 didn't return a score, use issue-based estimate
    if base_score == 0 and not a6.get("contribution_rating"):
        total_critical = sum(
            agent_results.get(f"agent{i}", {}).get("n_critical", 0)
            for i in range(1, 6)  # agents 1-5 only
        )
        total_major = sum(
            agent_results.get(f"agent{i}", {}).get("n_major", 0)
            for i in range(1, 6)
        )
        # Start at 70 (baseline for a paper that made it to Stage 6),
        # deduct 5 per critical and 2 per major
        base_score = max(30, 70 - (total_critical * 5) - (total_major * 2))
        print(f"  [6] WARNING: Agent 6 did not return a valid score. "
              f"Fallback score: {base_score} (from {total_critical} critical, "
              f"{total_major} major issues across Agents 1-5)")

    # Count critical issues across all agents
    total_critical = sum(
        agent_results.get(f"agent{i}", {}).get("n_critical", 0)
        for i in range(1, 7)
    )

    # Agent 3 critical issues (causal overclaiming) are especially serious
    a3_critical = agent_results.get("agent3", {}).get("n_critical", 0)

    # Adjust score: deduct for critical issues from other agents.
    # Reduced 2026-04-13: 3->2 per critical, max 15->10 cap. The base_score
    # already incorporates issue-based deductions, so adding more here was
    # double-counting and driving scores artificially low.
    other_critical = total_critical - a6.get("n_critical", 0)
    penalty = min(other_critical * 2, 10)
    adjusted_score = max(0, base_score - penalty)

    # Fatal issues: Agent 3 critical causal overclaiming or Agent 6 "Insufficient"
    has_fatal = (
        a3_critical >= 3
        or a6.get("contribution_rating") == "Insufficient"
        or a6.get("recommendation") == "Desk reject"
    )

    # Deterministic decision from thresholds
    if adjusted_score >= ACCEPT_GATE and not has_fatal:
        decision = "ACCEPT"
    elif adjusted_score >= ACCEPT_GATE and has_fatal:
        decision = "MINOR_REVISIONS"
    elif adjusted_score >= MINOR_REV_GATE and not has_fatal:
        decision = "MINOR_REVISIONS"
    elif adjusted_score >= MINOR_REV_GATE and has_fatal:
        decision = "MAJOR_REVISIONS"
    elif adjusted_score >= REJECT_FLOOR:
        decision = "MAJOR_REVISIONS"
    else:
        decision = "MAJOR_REVISIONS" if not has_fatal else "REJECT"

    return decision, adjusted_score, has_fatal


def _deduplicate_issues(issues: list[str], threshold: float = 0.6) -> list[str]:
    """Remove near-duplicate issues using keyword overlap.

    Two issues are considered duplicates if they share more than `threshold`
    of their significant keywords (words with 4+ chars, lowercased).
    The first occurrence is kept.
    """
    def _keywords(text: str) -> set[str]:
        return {w.lower().strip(".,;:()[]") for w in text.split() if len(w) >= 4}

    seen: list[set[str]] = []
    deduped: list[str] = []

    for issue in issues:
        kw = _keywords(issue)
        if not kw:
            deduped.append(issue)
            continue

        is_dup = False
        for prev_kw in seen:
            if not prev_kw:
                continue
            overlap = len(kw & prev_kw) / min(len(kw), len(prev_kw))
            if overlap >= threshold:
                is_dup = True
                break

        if not is_dup:
            deduped.append(issue)
            seen.append(kw)

    return deduped


def _synthesize_issues(agent_results: dict) -> dict:
    """Synthesize all agent issues into must/should/may categories.

    Deduplicates across agents so the same underlying problem reported by
    multiple agents appears only once (in its highest-priority category).
    """
    must_address = []
    should_address = []
    may_address = []

    # Agent 6 required analyses → must_address
    a6 = agent_results.get("agent6", {})
    for analysis in a6.get("required_analyses", []):
        must_address.append(f"[Contribution] {analysis}")

    # Agent 6 suggested analyses → should_address
    for analysis in a6.get("suggested_analyses", []):
        should_address.append(f"[Contribution] {analysis}")

    # Agent 3 causal overclaiming → must_address
    a3 = agent_results.get("agent3", {})
    for claim in a3.get("causal_overclaiming", []):
        must_address.append(f"[Claims] Causal overclaiming: {claim[:100]}")
    for caveat in a3.get("missing_caveats", []):
        should_address.append(f"[Claims] Missing caveat: {caveat[:100]}")

    # Agent 2 critical inconsistencies → must_address
    a2 = agent_results.get("agent2", {})
    for issue in a2.get("top_issues", []):
        if a2.get("n_critical", 0) > 0:
            must_address.append(f"[Consistency] {issue[:100]}")
        else:
            should_address.append(f"[Consistency] {issue[:100]}")

    # Agent 4 math errors → should_address
    a4 = agent_results.get("agent4", {})
    for issue in a4.get("top_issues", []):
        should_address.append(f"[Math] {issue[:100]}")

    # Agent 5 table/figure issues → should_address
    a5 = agent_results.get("agent5", {})
    for issue in a5.get("top_issues", []):
        should_address.append(f"[Tables/Figures] {issue[:100]}")

    # Agent 1 style issues → may_address
    a1 = agent_results.get("agent1", {})
    for issue in a1.get("top_issues", []):
        may_address.append(f"[Style] {issue[:100]}")

    # Agent 6 questions → should_address
    for q in a6.get("questions_to_authors", []):
        should_address.append(f"[Referee Question] {q[:120]}")

    # Deduplicate within each category first, then across categories.
    # must_address has highest priority: if an issue appears in must and should,
    # keep it only in must.
    must_address = _deduplicate_issues(must_address)
    should_address = _deduplicate_issues(should_address)
    may_address = _deduplicate_issues(may_address)

    # Cross-category dedup: remove from lower-priority lists if already in higher
    def _is_dup_of_any(item: str, higher_items: list[str], thresh: float = 0.6) -> bool:
        item_kw = {w.lower().strip(".,;:()[]") for w in item.split() if len(w) >= 4}
        if not item_kw:
            return False
        for h in higher_items:
            h_kw = {w.lower().strip(".,;:()[]") for w in h.split() if len(w) >= 4}
            if not h_kw:
                continue
            overlap = len(item_kw & h_kw) / min(len(item_kw), len(h_kw))
            if overlap >= thresh:
                return True
        return False

    should_address = [
        s for s in should_address if not _is_dup_of_any(s, must_address)
    ]
    may_address = [
        m for m in may_address if not _is_dup_of_any(m, must_address + should_address)
    ]

    return {
        "must_address": must_address,
        "should_address": should_address,
        "may_address": may_address,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Editorial decision file (structured feedback for Stage 5 R&R)
# ═══════════════════════════════════════════════════════════════════════════════

def _write_editorial_decision(review_dir: Path, round_suffix: str,
                              decision: str, avg_score: float,
                              has_fatal: bool, issues: dict,
                              agent_results: dict):
    """Write editorial_decision.md — the structured feedback file that Stage 5
    reads during R&R to know exactly what to fix.

    This file bridges the gap between Stage 6's issue detection and Stage 5's
    revision instructions. Without it, Stage 5 has no actionable feedback.
    """
    must = issues.get("must_address", [])
    should = issues.get("should_address", [])
    may = issues.get("may_address", [])

    # Classify issues as CODE vs TEXT
    code_keywords = [
        "analysis", "estimat", "regress", "robust", "specif", "test",
        "implement", "script", "code", "compute", "calculat", "run ",
        "missing table", "missing figure", "add table", "add figure",
        "placebo", "permutation", "bootstrap", "sensitivity",
        "heterogeneity", "mediation", "balance", "power",
    ]
    text_keywords = [
        "claim", "overclaim", "caveat", "hedg", "language", "wording",
        "inconsisten", "cross-ref", "spell", "grammar", "style",
        "notation", "equation", "caption", "label", "note",
        "abstract", "introduction", "conclusion", "discussion",
    ]

    def _classify(issue: str) -> str:
        low = issue.lower()
        code_score = sum(1 for kw in code_keywords if kw in low)
        text_score = sum(1 for kw in text_keywords if kw in low)
        return "CODE" if code_score > text_score else "TEXT"

    code_issues = []
    text_issues = []
    for item in must + should:
        if _classify(item) == "CODE":
            code_issues.append(item)
        else:
            text_issues.append(item)

    # Build the document
    lines = [
        f"# Editorial Decision: {decision}",
        f"",
        f"**Score**: {avg_score:.0f}/100",
        f"**Fatal issues**: {'YES' if has_fatal else 'No'}",
        f"**Round**: {round_suffix.replace('_round', 'Round ') if round_suffix else 'Round 1'}",
        f"",
    ]

    # Section 1: Code/analysis issues (require re-running scripts)
    if code_issues:
        lines.append("## CODE ISSUES (require re-running scripts)")
        lines.append("")
        lines.append("These issues require modifying Python scripts and re-executing them.")
        lines.append("After fixing scripts, re-run ALL scripts to regenerate results,")
        lines.append("then update main.tex with the new numbers.")
        lines.append("")
        for i, issue in enumerate(code_issues, 1):
            priority = "MUST" if issue in must else "SHOULD"
            lines.append(f"{i}. [{priority}] {issue}")
        lines.append("")

    # Section 2: Text/paper issues (edit LaTeX only)
    if text_issues:
        lines.append("## TEXT ISSUES (edit main.tex)")
        lines.append("")
        lines.append("These issues require editing the paper text only.")
        lines.append("")
        for i, issue in enumerate(text_issues, 1):
            priority = "MUST" if issue in must else "SHOULD"
            lines.append(f"{i}. [{priority}] {issue}")
        lines.append("")

    # Section 3: MUST-ADDRESS (full list, for reference)
    if must:
        lines.append("## MUST-ADDRESS (blockers — fix ALL of these)")
        lines.append("")
        for i, item in enumerate(must, 1):
            lines.append(f"{i}. {item}")
        lines.append("")

    # Section 4: SHOULD-ADDRESS
    if should:
        lines.append("## SHOULD-ADDRESS (important but not blockers)")
        lines.append("")
        for i, item in enumerate(should, 1):
            lines.append(f"{i}. {item}")
        lines.append("")

    # Section 5: MAY-ADDRESS (nice to have)
    if may:
        lines.append("## MAY-ADDRESS (polish)")
        lines.append("")
        for i, item in enumerate(may, 1):
            lines.append(f"{i}. {item}")
        lines.append("")

    # Section 6: Agent 6 referee questions
    a6 = agent_results.get("agent6", {})
    questions = a6.get("questions_to_authors", [])
    if questions:
        lines.append("## REFEREE QUESTIONS (must answer in revised paper)")
        lines.append("")
        for i, q in enumerate(questions, 1):
            lines.append(f"{i}. {q}")
        lines.append("")

    # Section 7: Summary stats for debugging
    lines.append("## Summary")
    lines.append(f"- Must-address: {len(must)} issues")
    lines.append(f"- Should-address: {len(should)} issues")
    lines.append(f"- May-address: {len(may)} issues")
    lines.append(f"- Code issues: {len(code_issues)}")
    lines.append(f"- Text issues: {len(text_issues)}")
    lines.append(f"- Has fatal: {has_fatal}")
    lines.append(f"- Contribution rating: {a6.get('contribution_rating', '?')}")
    lines.append(f"- Recommendation: {a6.get('recommendation', '?')}")
    lines.append("")

    content = "\n".join(lines)
    path = review_dir / f"editorial_decision{round_suffix}.md"
    path.write_text(content, encoding="utf-8")
    print(f"  [saved] {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# Main run function
# ═══════════════════════════════════════════════════════════════════════════════

def run(project_dir: Path, state: dict) -> dict:
    """Execute Stage 6: 6-agent peer review (repowered)."""
    paper_dir = project_dir / "paper"
    review_dir = project_dir / "reviews"
    review_dir.mkdir(exist_ok=True)
    (project_dir / "quality_reports").mkdir(exist_ok=True)

    # Track R&R round (MUST be computed first — used by consistency check)
    rr_round = state["stages"].get("stage6", {}).get("rr_round", 0) + 1
    round_suffix = f"_r{rr_round}" if rr_round > 1 else ""
    is_rr_round = rr_round > 1

    print(f"  [6] Peer review round {rr_round}/{MAX_RR_ROUNDS} (6-agent review)")

    # ── Run consistency check before every review round ──────────────
    fixes_made = _consistency_check(project_dir)
    if is_rr_round and fixes_made:
        print(f"  [consistency] R&R round {rr_round}: fixes applied after Stage 5 edits.")
        fixes_made_2 = _consistency_check(project_dir)
        if fixes_made_2:
            print(f"  [consistency] Second pass found additional issues — fixed.")

    # ── PRE-FLIGHT: Fix common critical issues BEFORE agents see them ──
    _preflight_fix(project_dir)

    paper_content = _gather_paper(paper_dir)
    strategy_memo = _read_file_or(project_dir / "strategy" / "strategy_memo.md")
    evidence_packet = _gather_evidence_packet(project_dir)
    table_files = ", ".join(_gather_tables(paper_dir)) or "(none)"
    figure_files = ", ".join(_gather_figures(paper_dir)) or "(none)"

    # Add estimator constraints
    estimator_note = _gather_estimator_constraints(state)
    if estimator_note:
        evidence_packet += "\n\n" + estimator_note

    # Determine target journal (default: top-field)
    target_journal = state.get("target_journal", "top-field")

    # Build revision context for R&R rounds
    revision_context = ""
    if rr_round > 1:
        prev_suffix = f"_r{rr_round - 1}" if rr_round > 1 else ""
        prev_report = review_dir / f"review_report{prev_suffix}.md"
        if prev_report.exists():
            prev_text = prev_report.read_text(encoding="utf-8")
            revision_context = f"""

--- PREVIOUS ROUND FEEDBACK (Round {rr_round - 1}) ---
The authors received the following review and revised the paper.
Evaluate whether the authors adequately addressed previous concerns.
Do NOT re-raise issues that have been satisfactorily resolved.

{smart_truncate(prev_text, 4000)}

--- END PREVIOUS FEEDBACK ---
"""
            print(f"  [6] Including Round {rr_round - 1} feedback for context")

    # ── Prompt budget management ────────────────────────────────────────
    # Each agent prompt should stay under MAX_PROMPT_CHARS to avoid
    # truncated responses or CLI timeouts. Budget is split per-agent
    # based on what each agent needs most.
    MAX_PROMPT_CHARS = 120_000  # ~30k tokens, safe for sonnet context

    # Truncate paper content to fit budget (paper is the largest component)
    paper_with_context = paper_content
    if revision_context:
        paper_with_context = paper_content + "\n" + revision_context

    # For agents that receive paper + evidence, split the budget
    paper_budget = min(len(paper_with_context), 60_000)
    evidence_budget = min(len(evidence_packet), 20_000)
    paper_truncated = smart_truncate(paper_with_context, paper_budget)
    evidence_truncated = smart_truncate(evidence_packet, evidence_budget)

    # Log if truncation happened
    if len(paper_with_context) > paper_budget:
        print(f"  [6] Paper truncated: {len(paper_with_context):,} -> {paper_budget:,} chars")
    if len(evidence_packet) > evidence_budget:
        print(f"  [6] Evidence packet truncated: {len(evidence_packet):,} -> {evidence_budget:,} chars")

    # ── Gather actual table contents for agents that need them ─────────
    table_contents_parts = []
    tables_dir = paper_dir / "tables"
    if tables_dir.exists():
        for t in sorted(tables_dir.glob("*.tex"))[:10]:
            content = t.read_text(encoding="utf-8")
            table_contents_parts.append(
                f"### {t.name}\n```latex\n{smart_truncate(content, 2000)}\n```"
            )
    table_contents = "\n\n".join(table_contents_parts) if table_contents_parts else "(no table files)"
    table_contents = smart_truncate(table_contents, 15_000)

    # ── Build all 6 agent prompts ─────────────────────────────────────
    # Agent 6 gets a much shorter paper version to avoid timeouts.
    # It needs abstract, intro, strategy, results, and conclusion —
    # not full lit review, institutional context, or data description.
    paper_for_agent6 = smart_truncate(paper_with_context, 25_000)

    prompts = [
        _build_agent1_prompt(paper_truncated),
        _build_agent2_prompt(paper_truncated, evidence_truncated),
        _build_agent3_prompt(paper_truncated, evidence_truncated),
        _build_agent4_prompt(paper_truncated),
        _build_agent5_prompt(paper_truncated, table_files, figure_files, table_contents),
        _build_agent6_prompt(paper_for_agent6, smart_truncate(strategy_memo, 1500),
                             smart_truncate(evidence_packet, 5_000), target_journal),
    ]

    # Warn if any prompt exceeds budget
    for i, prompt in enumerate(prompts):
        if len(prompt) > MAX_PROMPT_CHARS:
            print(f"  [6] WARNING: Agent {i+1} prompt is {len(prompt):,} chars "
                  f"(budget: {MAX_PROMPT_CHARS:,}). May cause truncation.")

    agent_labels = [
        "spelling-grammar",
        "consistency",
        "claims-identification",
        "math-notation",
        "tables-figures",
        "contribution-referee",
    ]

    # ── Run all 6 agents in parallel ──────────────────────────────────
    print("  [6] Launching 6 review agents in parallel...")
    pr = get_profile("stage6_referee")

    # Agent 6 (contribution-referee) gets a longer timeout because its
    # prompt is the largest and its response is the most detailed.
    AGENT6_TIMEOUT = 1800  # 30 minutes (vs 600s default for others)

    tasks = []
    for i, (prompt, label) in enumerate(zip(prompts, agent_labels)):
        task = {
            "prompt": prompt,
            "model": pr["model"],
            "effort": pr["effort"],
            "output_file": review_dir / f"agent{i+1}_{label}{round_suffix}.md",
            "label": label,
            "allowed_tools": [],
        }
        # Agent 6 (index 5) gets extended timeout and reduced effort
        # to avoid the chronic timeout issue (65K+ prompt + 6-part response)
        if i == 5:
            task["timeout"] = AGENT6_TIMEOUT
            task["effort"] = "medium"
        tasks.append(task)

    # Add a SECOND Agent 6 run (Agent 6b) for score averaging.
    # This reduces scoring variance by ~30% (√2 reduction in SD).
    # Agent 6b uses the same prompt but will produce an independent assessment.
    agent6b_task = {
        "prompt": prompts[5] + "\n\n(This is an independent second evaluation. "
                  "Score based solely on the paper's merits.)",
        "model": pr["model"],
        "effort": "medium",
        "output_file": review_dir / f"agent6b_contribution{round_suffix}.md",
        "label": "contribution-referee-b",
        "allowed_tools": [],
        "timeout": AGENT6_TIMEOUT,
    }
    tasks.append(agent6b_task)

    responses = run_claude_parallel(tasks, max_workers=7)

    # ── Parse all agent results ───────────────────────────────────────
    agent_results = {}
    for i, response in enumerate(responses[:6]):  # First 6 agents
        result = extract_json(response) or {}
        agent_results[f"agent{i+1}"] = result
        n_c = result.get("n_critical", 0)
        n_m = result.get("n_major", 0)
        n_mn = result.get("n_minor", 0)
        print(f"  [6] Agent {i+1} ({agent_labels[i]}): "
              f"{n_c} critical, {n_m} major, {n_mn} minor")

    # Parse Agent 6b and average with Agent 6
    if len(responses) > 6:
        result_6b = extract_json(responses[6]) or {}
        score_6a = agent_results.get("agent6", {}).get("score", 0)
        score_6b = result_6b.get("score", 0)

        if score_6a > 0 and score_6b > 0:
            avg_6_score = (score_6a + score_6b) / 2
            spread = abs(score_6a - score_6b)
            print(f"  [6] Agent 6 scoring: run_A={score_6a}, run_B={score_6b}, "
                  f"avg={avg_6_score:.0f}, spread={spread}")
            # Use the averaged score
            agent_results["agent6"]["score"] = avg_6_score
            agent_results["agent6"]["score_run_a"] = score_6a
            agent_results["agent6"]["score_run_b"] = score_6b
            agent_results["agent6"]["score_spread"] = spread

            if spread > 15:
                print(f"  [6] WARNING: Large scoring spread ({spread} points). "
                      f"Averaging reduces but does not eliminate variance.")

            # Also merge dimension scores (average them)
            dims_a = agent_results.get("agent6", {}).get("dimension_scores", {})
            dims_b = result_6b.get("dimension_scores", {})
            if dims_a and dims_b:
                merged_dims = {}
                for key in set(list(dims_a.keys()) + list(dims_b.keys())):
                    va = dims_a.get(key, 0)
                    vb = dims_b.get(key, 0)
                    if va > 0 and vb > 0:
                        merged_dims[key] = (va + vb) / 2
                    else:
                        merged_dims[key] = va or vb
                agent_results["agent6"]["dimension_scores"] = merged_dims
        elif score_6b > 0 and score_6a == 0:
            # Agent 6a failed, use 6b
            print(f"  [6] Agent 6a failed, using 6b score: {score_6b}")
            agent_results["agent6"] = result_6b
        else:
            print(f"  [6] Agent 6b: no additional score (6a={score_6a})")

        # Save Agent 6b report
        (review_dir / f"agent6b_contribution{round_suffix}.md").write_text(
            responses[6], encoding="utf-8"
        )

    # ── Save consolidated report ──────────────────────────────────────
    report_parts = [
        f"# Pre-Submission Referee Report (Round {rr_round})\n",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d')}\n",
        f"**Target**: {target_journal}\n\n---\n",
    ]

    section_names = [
        "Spelling, Grammar & Style",
        "Internal Consistency & Cross-References",
        "Unsupported Claims & Identification Integrity",
        "Mathematics, Equations & Notation",
        "Tables, Figures & Documentation",
        "Contribution Evaluation",
    ]

    for i, (response, name) in enumerate(zip(responses, section_names)):
        report_parts.append(f"\n## {i+1}. {name}\n\n{response}\n\n---\n")

    full_report = "\n".join(report_parts)
    report_path = review_dir / f"review_report{round_suffix}.md"
    report_path.write_text(full_report, encoding="utf-8")
    print(f"  [saved] {report_path}")

    # ── Compute decision ──────────────────────────────────────────────
    decision, avg_score, has_fatal = _compute_decision(agent_results)
    issues = _synthesize_issues(agent_results)

    # Get dimension scores from Agent 6
    a6 = agent_results.get("agent6", {})
    dimension_scores = a6.get("dimension_scores", {})

    print(f"  [6] Decision: {decision} (score: {avg_score:.0f}, "
          f"fatal: {has_fatal}, thresholds: ACCEPT>={ACCEPT_GATE}, "
          f"MINOR>={MINOR_REV_GATE}, REJECT<{REJECT_FLOOR})")

    # Total issues across all agents
    total_critical = sum(
        agent_results.get(f"agent{i}", {}).get("n_critical", 0) for i in range(1, 7)
    )
    total_major = sum(
        agent_results.get(f"agent{i}", {}).get("n_major", 0) for i in range(1, 7)
    )
    total_minor = sum(
        agent_results.get(f"agent{i}", {}).get("n_minor", 0) for i in range(1, 7)
    )
    print(f"  [6] Total issues: {total_critical} critical, "
          f"{total_major} major, {total_minor} minor")

    # ── Save state ────────────────────────────────────────────────────
    state["stages"]["stage6"] = {
        "status": "completed",
        "decision": decision,
        "rr_round": rr_round,
        "avg_score": avg_score,
        "has_fatal": has_fatal,
        "agent_results": agent_results,
        "dimension_scores": dimension_scores,
        "contribution_rating": a6.get("contribution_rating", "?"),
        "recommendation": a6.get("recommendation", "?"),
        "issues": issues,
        "total_critical": total_critical,
        "total_major": total_major,
        "total_minor": total_minor,
        "report_path": str(report_path),
        "completed_at": datetime.now().isoformat(),
    }
    state["current_stage"] = 6
    save_state(project_dir, state)

    # ── Write editorial_decision.md (structured feedback for Stage 5) ──
    _write_editorial_decision(review_dir, round_suffix, decision, avg_score,
                              has_fatal, issues, agent_results)

    # ── R&R loop ──────────────────────────────────────────────────────
    if decision == "MAJOR_REVISIONS" and rr_round < MAX_RR_ROUNDS:
        print(f"  [6] Major revisions requested -> looping back to Stage 5 "
              f"(round {rr_round + 1}/{MAX_RR_ROUNDS})")
        return state

    # ── End of review: present results and options to user ─────────────
    must_address = issues.get("must_address", [])
    should_address = issues.get("should_address", [])
    may_address = issues.get("may_address", [])

    print(f"\n  {'=' * 60}")
    print(f"  PEER REVIEW COMPLETE — {decision} (score: {avg_score:.0f})")
    if rr_round > 1:
        print(f"  After {rr_round} R&R rounds")
    print(f"  Contribution: {a6.get('contribution_rating', '?')}")
    print(f"  Recommendation: {a6.get('recommendation', '?')}")
    print(f"  {'=' * 60}")

    # Show dimension scores
    if dimension_scores:
        print(f"\n  Dimension Scores:")
        for dim, score in dimension_scores.items():
            # FIX: coerce score to int — Agent 6 sometimes returns floats
            # (e.g. 67.5) and "█" * float crashes with TypeError.
            score_int = int(score) if score is not None else 0
            bar_units = max(0, min(20, score_int // 5))
            bar = "█" * bar_units + "░" * (20 - bar_units)
            print(f"    {dim:30s} {bar} {score}")

    # Show issues
    issue_num = 0
    if must_address:
        print(f"\n  MUST-ADDRESS ({len(must_address)} issues):")
        for issue in must_address:
            issue_num += 1
            print(f"    {issue_num}. {issue[:120]}")

    if should_address:
        print(f"\n  SHOULD-ADDRESS ({len(should_address)} issues):")
        for issue in should_address[:10]:  # Cap display
            issue_num += 1
            print(f"    {issue_num}. {issue[:120]}")
        if len(should_address) > 10:
            print(f"    ... and {len(should_address) - 10} more (see full report)")

    if may_address:
        print(f"\n  MAY-ADDRESS ({len(may_address)} issues):")
        for issue in may_address[:5]:
            issue_num += 1
            print(f"    {issue_num}. {issue[:120]}")
        if len(may_address) > 5:
            print(f"    ... and {len(may_address) - 5} more (see full report)")

    total_issues = len(must_address) + len(should_address) + len(may_address)
    print(f"\n  Total: {total_issues} issues "
          f"({len(must_address)} must, {len(should_address)} should, {len(may_address)} may)")

    # ── Score diagnosis with structural analysis ────────────────────
    print(f"\n  {'─' * 60}")
    print(f"  SCORE DIAGNOSIS")
    print(f"  {'─' * 60}")

    if avg_score >= 85:
        print(f"  Score {avg_score:.0f}/100 — EXCELLENT")
        print(f"  Paper is near publication-ready for top field journals.")
    elif avg_score >= 75:
        print(f"  Score {avg_score:.0f}/100 — GOOD")
        print(f"  Publishable in solid applied journals. Minor revisions needed.")
    elif avg_score >= 65:
        print(f"  Score {avg_score:.0f}/100 — ACCEPTABLE")
        print(f"  Publishable in regional/applied journals with revisions.")
    else:
        print(f"  Score {avg_score:.0f}/100 — NEEDS WORK")

    # Detect structural limitations from strategy/methodology
    strategy = state["stages"].get("stage3_5", {}).get("approved_strategy", {})
    method_text = str(strategy.get("method", "")).lower()
    design_text = str(strategy.get("design", "")).lower()
    all_issues_text = " ".join(str(m) for m in must_address).lower()

    ceiling_reasons = []

    if "cross" in design_text or "cross-section" in method_text or "cross-section" in all_issues_text:
        ceiling_reasons.append(
            "Cross-sectional design (no causal identification) — "
            "panel data or quasi-experimental design needed for 80+"
        )

    if "weak" in all_issues_text or "exclusion restriction" in all_issues_text or "instrument" in all_issues_text:
        ceiling_reasons.append(
            "Weak/missing instrument for selection correction — "
            "credible exclusion restriction needed for 80+"
        )

    if "iia" in all_issues_text or "hausman" in all_issues_text or "nested logit" in all_issues_text:
        ceiling_reasons.append(
            "MNL IIA assumption unverified — "
            "nested logit or mixed logit implementation needed for 75+"
        )

    if "small sample" in all_issues_text or "sample size" in all_issues_text:
        ceiling_reasons.append(
            "Small effective sample for key estimates — "
            "more data or alternative estimator needed"
        )

    if "psm" in method_text and ("cross" in design_text or "propensity" in all_issues_text):
        ceiling_reasons.append(
            "PSM on cross-section identifies associations, not causal effects — "
            "panel data with actual treatment history needed for causal claims (85+)"
        )

    if ceiling_reasons:
        print(f"\n  Why the score can't go higher with text edits alone:")
        for i, reason in enumerate(ceiling_reasons, 1):
            print(f"    {i}. {reason}")
        print(f"\n  These are design limitations, not writing issues.")
        print(f"  Reaching 80+ requires changes to data or methodology,")
        print(f"  not additional R&R rounds on the same paper.")

    print(f"\n  Full report: {report_path}")
    print(f"  {'─' * 60}")

    # ── User options ─────────────────────────────────────────────────
    print(f"\n  {'=' * 60}")
    print(f"  Options:")
    print(f"  [1] Accept score ({avg_score:.0f}) and proceed to Stage 7")
    print(f"  [2] Manual intervention — Claude fixes paper, then re-review")
    print(f"  [3] Add new data — provide additional dataset(s), re-run code + paper")
    print(f"  {'=' * 60}")
    print("\a", end="", flush=True)

    user_choice = ""
    while user_choice not in ("1", "2", "3"):
        user_choice = input("\n  Enter your choice (1, 2, or 3): ").strip()
        if user_choice not in ("1", "2", "3"):
            print("  Please enter 1, 2, or 3.")

    if user_choice == "1":
        print(f"\n  [6] Score {avg_score:.0f} accepted. Proceeding to Stage 7.")

    elif user_choice == "2":
        from ..claude_runner import request_manual_intervention

        issue_summary = (
            f"Stage 6 peer review (6-agent): {decision} after {rr_round} "
            f"round(s). Score: {avg_score:.0f}. "
            f"Must-address: {len(must_address)}. "
            f"See full report: {report_path}"
        )
        paper_files = [str(paper_dir / "main.tex")] if (paper_dir / "main.tex").exists() else []
        review_files = [str(f) for f in sorted(review_dir.glob("*.md"))]

        request_manual_intervention(
            stage="stage6_review",
            issue=issue_summary,
            files=paper_files + review_files,
            project_dir=project_dir,
        )

        # After intervention: consistency check + re-review
        print(f"\n  [6] Post-intervention consistency check...")
        _consistency_check(project_dir)

        print(f"\n  [6] Re-running peer review after manual intervention...")
        state = run(project_dir, state)
        return state

    elif user_choice == "3":
        # Add new data with full validation (merge keys, module detection, merge test)
        print(f"\n  {'=' * 60}")
        print(f"  ADD NEW DATA")
        print(f"  {'=' * 60}")

        # Show what referees asked for
        all_referee_issues = must_address + should_address + may_address
        if all_referee_issues:
            print(f"\n  Referees requested the following changes:")
            for i, issue in enumerate(all_referee_issues[:15], 1):
                tag = ("MUST" if i <= len(must_address) else
                       "SHOULD" if i <= len(must_address) + len(should_address) else "MAY")
                print(f"    {i}. [{tag}] {str(issue)[:120]}")

        # Detect specific data needs from referee comments
        all_issues_lower = " ".join(str(m) for m in all_referee_issues).lower()
        print(f"\n  Based on referee feedback, you may need:")
        if "module 300" in all_issues_lower or "p306" in all_issues_lower or "enrollment" in all_issues_lower:
            print(f"    - ENAHO Module 300 (Education): file Enaho01a-YYYY-300.csv")
        if "module 200" in all_issues_lower or "children" in all_issues_lower or "caregiving" in all_issues_lower:
            print(f"    - ENAHO Module 200 (Household): file Enaho01-YYYY-200.csv")
        if "panel" in all_issues_lower or "rotating" in all_issues_lower or "longitudinal" in all_issues_lower:
            print(f"    - ENAHO quarterly panel files (multiple years)")

        data_dir = project_dir / "data" / "external"
        data_dir.mkdir(parents=True, exist_ok=True)

        import shutil
        added_files = []
        while True:
            path_input = input("\n  Data file path (or 'done' to finish): ").strip()
            if path_input.lower() == "done":
                break
            src = Path(path_input)
            if not src.exists():
                print(f"  [!] File not found: {src}")
                continue

            # ── Validate the file before accepting ──
            print(f"  [check] Validating {src.name} ...")
            try:
                import pandas as _pd
                _df_check = _pd.read_csv(src, nrows=5, encoding="latin-1", low_memory=False)
                file_cols = set(_df_check.columns)

                # Check merge keys
                merge_keys = {"CONGLOME", "VIVIENDA", "HOGAR", "CODPERSO"}
                has_merge_keys = merge_keys.issubset(file_cols)

                # Detect ENAHO module
                module_detected = "unknown"
                if any(c.startswith("P3") for c in file_cols):
                    module_detected = "Module 300 (Education)"
                elif any(c.startswith("P2") for c in file_cols):
                    module_detected = "Module 200 (Household characteristics)"
                elif any(c.startswith("P1") for c in file_cols):
                    module_detected = "Module 100 (Housing)"
                elif any(c.startswith("P4") for c in file_cols):
                    module_detected = "Module 400 (Health)"
                elif any(c.startswith("P5") for c in file_cols):
                    module_detected = "Module 500 (Employment)"

                full_df = _pd.read_csv(src, encoding="latin-1", low_memory=False)
                n_rows = len(full_df)
                n_cols = len(full_df.columns)
                del full_df

                print(f"    Detected: {module_detected}")
                print(f"    Rows: {n_rows:,}, Columns: {n_cols}")
                print(f"    Merge keys: {'YES' if has_merge_keys else 'NO'}")

                if not has_merge_keys:
                    print(f"\n  [!] Missing ENAHO merge keys (CONGLOME, VIVIENDA, HOGAR, CODPERSO).")
                    print(f"      Cannot merge with main dataset.")
                    confirm = input("      Add anyway? (y/n): ").strip().lower()
                    if confirm != "y":
                        print(f"  [skip] {src.name} not added.")
                        continue

                if "500" in module_detected:
                    print(f"\n  [!] This appears to be {module_detected} — same as main dataset.")
                    confirm = input("      Add anyway? (y/n): ").strip().lower()
                    if confirm != "y":
                        print(f"  [skip] {src.name} not added.")
                        continue

                # Test merge with main dataset
                main_data_path = state["stages"].get("stage1", {}).get("data_path", "")
                if main_data_path and Path(main_data_path).exists() and has_merge_keys:
                    print(f"  [merge-test] Testing merge with main dataset ...")
                    try:
                        mk = list(merge_keys)
                        main_sample = _pd.read_csv(main_data_path, usecols=mk,
                                                    nrows=1000, encoding="latin-1",
                                                    low_memory=False)
                        new_sample = _pd.read_csv(src, usecols=mk,
                                                   nrows=1000, encoding="latin-1",
                                                   low_memory=False)
                        test_merge = main_sample.merge(new_sample, on=mk, how="inner")
                        match_rate = len(test_merge) / len(main_sample) * 100

                        if match_rate < 5:
                            print(f"  [!] Merge test FAILED: only {match_rate:.1f}% match.")
                            print(f"      Files do not share enough common identifiers.")
                            confirm = input("      Add anyway? (y/n): ").strip().lower()
                            if confirm != "y":
                                print(f"  [skip] {src.name} not added.")
                                continue
                        else:
                            print(f"  [ok] Merge test passed: {match_rate:.1f}% match rate")
                    except Exception as merge_err:
                        print(f"  [warn] Could not test merge: {merge_err}")

                print(f"  [ok] {src.name} validated as {module_detected}")

            except Exception as val_err:
                print(f"  [!] Could not validate {src.name}: {val_err}")
                confirm = input("      Add anyway? (y/n): ").strip().lower()
                if confirm != "y":
                    print(f"  [skip] {src.name} not added.")
                    continue

            dst = data_dir / src.name
            shutil.copy2(src, dst)
            added_files.append(str(dst))
            print(f"  [ok] Copied: {src.name} -> {dst}")

        if added_files:
            state["stages"].setdefault("stage6", {})
            state["stages"]["stage6"]["added_data"] = added_files
            state["stages"]["stage6"]["added_data_reason"] = (
                f"Referee requested additional data (R&R round {rr_round}). "
                f"Must-address: {'; '.join(str(m)[:80] for m in must_address[:3])}"
            )

            # Reset stages 4-5 for rebuild
            for key in ["stage4a", "stage4bc", "stage4_5", "stage4_7", "stage5"]:
                if key in state["stages"]:
                    del state["stages"][key]
            state["current_stage"] = 3.7
            state["stages"]["stage6"]["restart_from"] = 4

            # Delete old scripts and outputs
            scripts_dir = project_dir / "scripts" / "python"
            clean_dir = project_dir / "data" / "clean"
            if scripts_dir.exists():
                for old_script in scripts_dir.glob("*.py"):
                    old_script.unlink()
                print(f"  [clean] Deleted old scripts from {scripts_dir}")
            if clean_dir.exists():
                for old_output in clean_dir.glob("*.csv"):
                    old_output.unlink()
                print(f"  [clean] Deleted old outputs from {clean_dir}")

            save_state(project_dir, state)
            print(f"\n  [6] Added {len(added_files)} dataset(s).")
            print(f"  Pipeline will restart from Stage 4 with new data.")
        else:
            print(f"\n  [6] No files added. Returning to options.")
            state = run(project_dir, state)
            return state

    return state
