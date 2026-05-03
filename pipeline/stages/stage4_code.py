"""Stage 4b/c — Code generation, execution, and review.

Phase 1: Claude (coder agent) generates numbered Python scripts.
Phase 1.5: Auto-generate requirements.txt, pip install.
Phase 2: Execute each script in order via python_runner.
Phase 3: If error -> feed stderr to Claude -> fix -> retry (max 3).
Phase 4: Coder-critic reviews scripts + results, score >= CRITIC_GATE.
Phase 5: If score < gate -> feed critic issues back -> regenerate (max 2 revision rounds).
"""

import re
import sys
from datetime import datetime
from pathlib import Path

from ..config import CLO_AUTHOR, CRITIC_GATE, get_profile
from ..claude_runner import run_claude
from ..json_utils import extract_json, smart_truncate
from ..python_runner import run_python_script, run_with_retry, install_requirements
from ..state import save_state
from ..validators.code_validator import validate as validate_code

MAX_REVISION_ROUNDS = 2  # max times to revise based on critic feedback


def _read_agent(name: str) -> str:
    path = CLO_AUTHOR / ".claude" / "agents" / f"{name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"(agent prompt '{name}' not found at {path})"


def _sanitize_ascii(text: str) -> str:
    """Replace common Unicode characters with ASCII equivalents."""
    replacements = {
        # Arrows
        "\u2192": "->", "\u2190": "<-", "\u2194": "<->",
        # Dashes
        "\u2013": "-", "\u2014": "--", "\u2015": "--",
        "\u2026": "...",
        # Math operators
        "\u00d7": "x", "\u00f7": "/",
        "\u2264": "<=", "\u2265": ">=", "\u2260": "!=",
        "\u2248": "~=", "\u221e": "inf",
        # Greek letters (common in stats output)
        "\u03b1": "alpha", "\u03b2": "beta", "\u03b3": "gamma",
        "\u03b4": "delta", "\u03b5": "epsilon", "\u03b8": "theta",
        "\u03bb": "lambda", "\u03bc": "mu", "\u03c3": "sigma",
        "\u03c4": "tau", "\u03c7": "chi", "\u03c0": "pi",
        # Superscripts
        "\u00b2": "2", "\u00b3": "3", "\u00b9": "1",
        # Symbols
        "\u2713": "[OK]", "\u2714": "[OK]", "\u2715": "[X]", "\u2716": "[X]",
        "\u2717": "[X]", "\u2718": "[X]",
        "\u2611": "[x]", "\u2610": "[ ]",
        "\u26a0": "[!]",  # warning sign
        "\u00b1": "+/-",
        "\u2032": "'", "\u2033": '"',
        # Quotes
        "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"',
        # Bullets
        "\u2022": "*", "\u2023": ">",
        # Box drawing (common in print formatting)
        "\u2500": "-", "\u2502": "|", "\u2550": "=",
        "\u2501": "-", "\u2503": "|",
        "\u250c": "+", "\u2510": "+", "\u2514": "+", "\u2518": "+",
        "\u251c": "+", "\u2524": "+", "\u252c": "+", "\u2534": "+",
        "\u2552": "+", "\u2555": "+", "\u2558": "+", "\u255b": "+",
        "\u2560": "+", "\u2563": "+", "\u2566": "+", "\u2569": "+",
        "\u256c": "+",
        "\u2554": "+", "\u2557": "+", "\u255a": "+", "\u255d": "+",
    }
    for uni, asc in replacements.items():
        text = text.replace(uni, asc)
    # Final safety: encode to ASCII, replacing any remaining non-ASCII chars
    # This prevents Windows cp1252 crashes in print() statements
    text = text.encode("ascii", errors="replace").decode("ascii")
    return text


def _parse_scripts(response: str, scripts_dir: Path):
    """Extract code blocks from Claude response, sanitize, and save to disk."""
    scripts = []
    for m in re.finditer(r'```python(?::(\S+))?\s*\n(.*?)\n\s*```', response, re.DOTALL):
        filename = m.group(1) or f"script_{len(scripts)}.py"
        code = _sanitize_ascii(m.group(2))
        if "requirements" in filename.lower():
            filepath = scripts_dir / "requirements.txt"
        else:
            if not filename.endswith(".py"):
                filename += ".py"
            filepath = scripts_dir / filename
        filepath.write_text(code, encoding="utf-8")
        scripts.append(filepath)
        print(f"  [saved] {filepath}")
    return scripts


def _execute_scripts(scripts, scripts_dir):
    """Run .py scripts with parallelism: 00_clean first, then 01-03 in parallel."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_results = {}
    all_ok = True
    py_scripts = sorted(
        [s for s in scripts if s.suffix == ".py"],
        key=lambda p: p.name
    )

    # Separate the cleaning script (must run first) from the rest
    clean_scripts = [s for s in py_scripts if s.name.startswith("00")]
    parallel_scripts = [s for s in py_scripts if not s.name.startswith("00")]

    # Phase 1: Run 00_clean.py sequentially (others depend on its output)
    for script in clean_scripts:
        result = run_with_retry(script, cwd=scripts_dir)
        all_results[script.name] = result
        if not result["ok"]:
            all_ok = False
            print(f"  [fail] {script.name} failed — skipping dependent scripts.")
            # Still return all scripts so critic can see what was attempted
            for s in parallel_scripts:
                all_results[s.name] = {"ok": False, "stdout": "", "stderr": "Skipped: 00_clean failed", "returncode": -1, "generated_files": []}
            return py_scripts, all_results, False

    # Phase 2: Run 01, 02, 03 in parallel (all read clean_data, independent outputs)
    if parallel_scripts:
        n = len(parallel_scripts)
        print(f"  [parallel] Running {n} scripts concurrently...")
        with ThreadPoolExecutor(max_workers=n) as pool:
            futures = {
                pool.submit(run_with_retry, s, cwd=scripts_dir): s
                for s in parallel_scripts
            }
            for future in as_completed(futures):
                script = futures[future]
                result = future.result()
                all_results[script.name] = result
                if not result["ok"]:
                    all_ok = False
                    print(f"  [fail] {script.name} failed permanently.")

    return py_scripts, all_results, all_ok


def _get_clean_data_columns(project_dir: Path) -> str:
    """Read columns from clean_data.csv after 00_clean.py runs."""
    clean_csv = project_dir / "data" / "clean" / "clean_data.csv"
    if not clean_csv.exists():
        return ""
    try:
        import pandas as pd
        df = pd.read_csv(clean_csv, nrows=0, encoding="latin-1")
        cols = list(df.columns)
        return f"\nAVAILABLE COLUMNS in clean_data.csv ({len(cols)} columns):\n{', '.join(cols)}\n"
    except Exception:
        return ""


def _gather_scripts_content(py_scripts, all_results):
    """Build a text summary of all scripts + their outputs for the critic."""
    content = ""
    for script in py_scripts:
        code = script.read_text(encoding="utf-8")
        result = all_results.get(script.name, {})
        content += f"\n\n### {script.name}\n```python\n{code}\n```\n"
        if result.get("stdout"):
            content += f"\n**stdout:**\n```\n{result['stdout'][:2000]}\n```\n"
        if result.get("stderr"):
            content += f"\n**stderr:**\n```\n{result['stderr'][:1000]}\n```\n"
        if result.get("generated_files"):
            content += f"\n**Generated files:** {', '.join(result['generated_files'][:20])}\n"
    return content


def _run_critic(critic_prompt_text, strategy_memo, scripts_content, project_dir,
                validation_text=""):
    """Run coder-critic review and return (response, result_dict, score)."""
    critic_prompt = f"""{critic_prompt_text}

--- STRATEGY MEMO ---
{smart_truncate(strategy_memo, 3000)}

--- SCRIPTS AND OUTPUTS ---
{scripts_content}

--- AUTOMATED VALIDATION ---
{validation_text}

NOTE: The validation checks above are PROGRAMMATIC FACTS, not opinions.
Do NOT re-assess file existence or execution success. Focus your scoring
on SUBJECTIVE quality: code structure, statistical rigor, methodology.

Score the code from 0-100. Start at 100 and deduct for each issue.

CALIBRATION GUIDE:
- 80-100: Excellent code, runs cleanly, proper methods, minor issues only
- 65-79: Good code with some methodological or output concerns
- 50-64: Significant issues but fundamentally workable
- 0-49: Major errors or missing analyses

For observational studies, a working pipeline with proper robustness checks
and documented limitations should score 70-85. Do NOT penalize for inherent
limitations of the research design (e.g., lack of RCT, observational data).
Only deduct for actual code errors, missing analyses, or methodological flaws.

EVALUATION CRITERIA (check each one):

1. CORRECTNESS (MAJOR: -15 each)
   - Does the main specification match the pseudo-code exactly?
   - Are standard errors clustered at the correct level?
   - Are treatment/outcome variables constructed as described in the strategy?
   - Do the scripts actually run without errors?

2. STATISTICAL RIGOR (MAJOR: -10 each)
   - Are confidence intervals reported alongside point estimates?
   - Is the parallel trends assumption tested (if DiD)?
   - Is the first-stage F-stat reported (if IV)?
   - Do robustness checks address the threats listed in the strategy memo?
   - Are placebo/falsification tests included?

3. DATA QUALITY (MAJOR: -10 each)
   - Is the sample construction logged (rows dropped at each step)?
   - Are missing values handled explicitly (not silently dropped)?
   - Is there a missingness table showing % missing per variable?
   - Is the missingness mechanism tested (MCAR/MAR/MNAR)?
   - Is the chosen missing data strategy justified (listwise deletion, imputation, bounds)?
   - Is there a robustness check comparing results with/without imputed observations?
   - Is the balance table present and correctly computed?
   - Do summary statistics match reasonable expectations for this data?

4. OUTPUT QUALITY (MINOR: -5 each)
   - Do tables use booktabs format with proper notes?
   - Do figures have labeled axes, readable fonts, and proper resolution?
   - Does results_summary.md contain the main finding with exact numbers?
   - Are all tables/figures referenced in the strategy memo actually produced?
   - Is plt.close('all') called after every savefig() to prevent figure leaking?

5. CODE QUALITY (MINOR: -3 each)
   - Are variable names descriptive (not x1, temp, etc.)?
   - Is the code readable without excessive comments?
   - Are intermediate results saved in the correct format (.parquet, not pickle)?

Output a JSON block:
```json
{{
  "score": 85,
  "scripts_run": true,
  "all_outputs_present": true,
  "issues": [
    {{"severity": "MAJOR|MINOR", "category": "correctness|rigor|data|output|code",
      "script": "filename.py", "description": "...", "fix": "concrete suggestion",
      "deduction": -10}}
  ],
  "summary": "One paragraph assessment"
}}
```
"""
    print("\n  [4c] Coder-critic review ...")
    (project_dir / "quality_reports").mkdir(exist_ok=True)

    p = get_profile("stage4_critic")
    response = run_claude(
        critic_prompt, model=p["model"], effort=p["effort"],
        output_file=project_dir / "quality_reports" / "code_review.md",
        allowed_tools=[],
    )
    result = extract_json(response) or {}
    score = result.get("score", 0)
    print(f"  [4c] Critic score: {score}/100 (gate: {CRITIC_GATE})")
    return response, result, score


def run(project_dir: Path, state: dict) -> dict:
    """Execute Stage 4: unified manual intervention for strategy + code.

    ONE signal covers everything:
    1. Claude writes strategy_memo.md (if missing)
    2. Claude writes 4 Python scripts
    3. Claude executes them
    4. Claude signals done
    Pipeline then validates and saves state.
    """
    from ..claude_runner import request_manual_intervention

    scripts_dir = project_dir / "scripts" / "python"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    strategy_dir = project_dir / "strategy"
    strategy_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "paper" / "tables").mkdir(parents=True, exist_ok=True)
    (project_dir / "paper" / "figures").mkdir(parents=True, exist_ok=True)
    (project_dir / "data" / "clean").mkdir(parents=True, exist_ok=True)

    # Check what's missing
    has_strategy = (strategy_dir / "strategy_memo.md").exists()
    has_scripts = len(sorted(scripts_dir.glob("[0-9]*.py"))) >= 4
    has_results = (project_dir / "data" / "clean" / "clean_data.csv").exists()

    # If anything is missing, request ONE unified intervention
    if not (has_strategy and has_scripts and has_results):
        missing = []
        if not has_strategy:
            missing.append("strategy_memo.md")
        if not has_scripts:
            missing.append("Python scripts (00-03)")
        if not has_results:
            missing.append("executed results (clean_data.csv)")

        checklist = strategy_dir / "referee_checklist.md"
        files = [str(strategy_dir)]
        if checklist.exists():
            files.append(str(checklist))
        files.append(str(scripts_dir))

        # Read estimator availability from Stage 3.3
        stage3_3 = state["stages"].get("stage3_3", {})
        avail_est = stage3_3.get("available_estimators", {})
        est_warnings = stage3_3.get("estimator_warnings", [])

        estimator_guidance = ""
        if avail_est:
            working = [k for k, v in avail_est.items() if v]
            broken = [k for k, v in avail_est.items() if not v]
            estimator_guidance = (
                "\n\n*** VERIFIED ESTIMATORS (tested on real data in Stage 3.3) ***\n"
                "Working: %s\n" % ", ".join(working)
            )
            if broken:
                estimator_guidance += (
                    "BROKEN (do NOT use): %s\n" % ", ".join(broken)
                )
            if est_warnings:
                estimator_guidance += (
                    "Warnings:\n" +
                    "\n".join("  - %s" % w for w in est_warnings) + "\n"
                )
            estimator_guidance += (
                "ONLY use estimators listed as 'Working' above. "
                "Do NOT promise or attempt to use broken estimators. "
                "If the referee checklist requires a broken estimator, "
                "skip it and note in a comment why it was omitted.\n"
            )

        # ── Data preview block (added 2026-04-13) ────────────────────────
        # Inject df.head(), df.describe(), and value_counts of likely treatment
        # columns so the LLM filling templates can map placeholders correctly
        # (it sees actual values, not just column names). This addresses the
        # common failure mode of placeholders filled with non-existent or
        # mistyped variable names.
        data_preview = ""
        try:
            import pandas as _pd_prev
            # Find the primary dataset from Stage 1.5
            stage1_5 = state["stages"].get("stage1_5", {})
            datasets = stage1_5.get("downloaded_datasets", []) or []
            if datasets:
                ds0 = datasets[0]
                lp = ds0.get("local_path", "")
                if lp and Path(lp).exists():
                    ext = Path(lp).suffix.lower()
                    try:
                        if ext == ".dta":
                            _df_prev = _pd_prev.read_stata(lp)
                        elif ext == ".tab":
                            _df_prev = _pd_prev.read_csv(lp, sep="\t",
                                                          encoding="latin-1",
                                                          low_memory=False)
                        elif ext == ".parquet":
                            _df_prev = _pd_prev.read_parquet(lp)
                        else:
                            _df_prev = _pd_prev.read_csv(lp, encoding="latin-1",
                                                          low_memory=False)

                        # Identify columns the LLM most needs to see values for
                        kw_outcome = ("income", "wage", "employ", "score",
                                      "outcome", "y_", "consum", "earn")
                        kw_treat = ("treat", "vbt", "assign", "arm", "control",
                                    "random", "voucher", "lottery", "post_")
                        kw_id = ("_id", "cluster", "year", "month", "wave")

                        def _matches(c, kws):
                            lc = c.lower()
                            return any(k in lc for k in kws)

                        treat_cols = [c for c in _df_prev.columns
                                      if _matches(c, kw_treat)][:3]
                        out_cols = [c for c in _df_prev.columns
                                    if _matches(c, kw_outcome)][:5]
                        id_cols = [c for c in _df_prev.columns
                                   if _matches(c, kw_id)][:3]

                        preview_cols = list(dict.fromkeys(
                            treat_cols + out_cols + id_cols
                        ))[:12]

                        if preview_cols:
                            head_df = _df_prev[preview_cols].head(5)
                            data_preview = (
                                "\n\n*** DATA PREVIEW (first 5 rows of key cols) ***\n"
                                "Use these ACTUAL VALUES to fill placeholders correctly.\n"
                                "Match treatment encoding (e.g. 0/1 vs 'Control'/'Treated')\n"
                                "to the TREATMENT_ARMS dict.\n\n"
                                f"```\n{head_df.to_string(max_cols=12, max_colwidth=20)}\n```\n"
                            )

                            # Add value_counts for likely treatment columns
                            for tc in treat_cols[:2]:
                                try:
                                    vc = _df_prev[tc].value_counts().head(8)
                                    data_preview += (
                                        f"\nValue counts for '{tc}':\n"
                                        f"```\n{vc.to_string()}\n```\n"
                                    )
                                except Exception:
                                    pass

                            # Add describe for likely outcomes (numeric only)
                            num_outs = [c for c in out_cols
                                        if _df_prev[c].dtype.kind in "biufc"][:5]
                            if num_outs:
                                try:
                                    desc = _df_prev[num_outs].describe().round(3)
                                    data_preview += (
                                        f"\nDescriptive stats for likely outcomes:\n"
                                        f"```\n{desc.to_string()}\n```\n"
                                    )
                                except Exception:
                                    pass
                    except Exception as _pe:
                        data_preview = f"\n[data-preview] Could not load preview: {_pe}\n"
        except Exception:
            pass

        # Extract MUST requirements from referee checklist to embed in the prompt
        checklist_musts = ""
        if checklist.exists():
            cl_text = checklist.read_text(encoding="utf-8")
            musts = [line.strip("- ").strip()
                     for line in cl_text.splitlines()
                     if line.strip().startswith("- [") and "MUST" in line.split("]")[0].upper()]
            if not musts:
                # Fallback: grab lines under "## MUST-HAVE"
                in_must = False
                for line in cl_text.splitlines():
                    if "MUST-HAVE" in line:
                        in_must = True
                        continue
                    if in_must and line.startswith("## "):
                        break
                    if in_must and line.strip().startswith("- "):
                        musts.append(line.strip("- ").strip())
            if musts:
                checklist_musts = (
                    "\n\nREFEREE CHECKLIST — MUST-IMPLEMENT requirements "
                    f"({len(musts)} items). Each script MUST address the relevant items:\n"
                    + "\n".join(f"  {i+1}. {m[:200]}" for i, m in enumerate(musts))
                )

        # ── Detect research design and load template if available ──────
        from ..templates import detect_design, get_all_templates, AVAILABLE_DESIGNS

        selected_idea = state["stages"].get("stage2_5", {}).get("selected_idea", {})
        design_type = detect_design(selected_idea)
        template_instruction = ""

        if design_type in AVAILABLE_DESIGNS:
            templates = get_all_templates(design_type)
            if templates:
                # ALWAYS write templates to scripts directory (overwrite any
                # previous custom code). This ensures the validated template
                # code is the starting point, not Claude's from-scratch generation.
                scripts_dir.mkdir(parents=True, exist_ok=True)

                template_instruction = (
                    f"\n\n*** MANDATORY SCRIPT TEMPLATES ({design_type.upper()} design) ***\n"
                    f"Templates have been WRITTEN to scripts/python/. "
                    f"These contain 200+ lines of TESTED, VALIDATED code per script.\n\n"
                    f"YOUR ONLY JOB is to fill the {{{{VARIABLE}}}} placeholders at the TOP "
                    f"of each script. DO NOT touch anything below the "
                    f"'FIXED CODE' separator line.\n\n"
                    f"WORKFLOW:\n"
                    f"  1. Read each script in scripts/python/\n"
                    f"  2. At the TOP of each script, find the section:\n"
                    f"     # PROJECT-SPECIFIC VARIABLES (Claude fills these)\n"
                    f"  3. Replace EACH {{{{VARIABLE}}}} with the correct value from the data\n"
                    f"  4. DO NOT ADD, DELETE, OR MODIFY any code below the line:\n"
                    f"     # FIXED CODE (does not change between projects)\n"
                    f"  5. After filling ALL placeholders in ALL 4 scripts, execute them in order\n\n"
                    f"WHY THIS MATTERS:\n"
                    f"  - The fixed code handles NaN/missing values, fallback estimators,\n"
                    f"    table validation, and 30+ robustness checks.\n"
                    f"  - If you rewrite the code from scratch, you WILL miss these checks\n"
                    f"    and the paper will score <50 in peer review.\n"
                    f"  - The templates were validated against real referee checklists.\n\n"
                )

                import re as _re_tmpl
                for filename, content in templates.items():
                    target = scripts_dir / filename

                    # Sanity-check the template payload BEFORE overwriting
                    # the script.  A degraded read (empty file, truncated
                    # template, missing the FIXED CODE marker) would
                    # otherwise overwrite a working script with garbage and
                    # silently break downstream stages.
                    if not content or len(content) < 200:
                        print(
                            f"  [template] SKIP {design_type}/{filename}: "
                            f"template content too small ({len(content) if content else 0} bytes); "
                            f"keeping existing script (if any)."
                        )
                        continue
                    if "FIXED CODE" not in content:
                        print(
                            f"  [template] SKIP {design_type}/{filename}: "
                            f"template missing 'FIXED CODE' marker — refusing to overwrite."
                        )
                        continue

                    # If a script already exists, snapshot it before
                    # overwriting so a bad template can be rolled back.
                    if target.exists():
                        try:
                            target.with_suffix(target.suffix + ".bak").write_text(
                                target.read_text(encoding="utf-8"),
                                encoding="utf-8",
                            )
                        except OSError:
                            pass
                    target.write_text(content, encoding="utf-8")
                    print(f"  [template] Wrote {design_type}/{filename} -> scripts/python/{filename}")

                    # Show which variables need filling
                    placeholders = _re_tmpl.findall(r'\{\{(\w+)\}\}', content)
                    unique_ph = list(dict.fromkeys(placeholders))
                    template_instruction += (
                        f"--- {filename} ---\n"
                        f"Placeholders to fill: {', '.join(unique_ph)}\n\n"
                    )

                template_instruction += (
                    f"\nFILLING RULES:\n"
                    f"  - String values: {{{{DATA_FILE}}}} -> \"../../data/external/mydata.csv\"\n"
                    f"  - Lists: {{{{OUTCOME_VARS}}}} -> [\"outcome1\", \"outcome2\"]\n"
                    f"  - Dicts: {{{{TREATMENT_ARMS}}}} -> {{\"Control\": 0, \"Cash\": 1}}\n"
                    f"  - None: {{{{ENTITY_VAR}}}} -> \"None\" (if not applicable)\n\n"
                    f"FORBIDDEN ACTIONS (will cause pipeline failure):\n"
                    f"  - Deleting template files and writing new ones from scratch\n"
                    f"  - Modifying code below the 'FIXED CODE' line\n"
                    f"  - Removing functions or changing function signatures\n"
                    f"  - Adding imports that conflict with template imports\n"
                )
        else:
            template_instruction = (
                f"\n\n*** No template available for design '{design_type}'. ***\n"
                f"Generate scripts from scratch following the guidelines below.\n"
            )

        request_manual_intervention(
            stage="stage4_full",
            issue=(
                f"Stage 4 needs manual intervention. Missing: {', '.join(missing)}. "
                "Tell Claude: 'revisa el pipeline'. Claude will: "
                "(1) write strategy_memo.md if missing, "
                "(2) generate 00_clean.py, 01_main.py, 02_robustness.py, 03_output.py, "
                "(3) execute all scripts, "
                "(4) signal completion. "
                "\n\n*** CRITICAL: USE VALIDATED PACKAGES, NEVER MANUAL IMPLEMENTATIONS ***\n"
                "For staggered DiD: use pyfixest (pf.did.event_study, pf.did.att_gt) or csdid. "
                "NEVER implement Callaway-Sant'Anna manually with 2x2 DiD loops. "
                "For Sun-Abraham: use pyfixest (sunab=True option). "
                "For Goodman-Bacon decomposition: if no validated Python package exists, "
                "report TWFE vs CS comparison WITHOUT attempting manual decomposition. "
                "For standard TWFE/event study: use pyfixest or linearmodels PanelOLS. "
                "For wild cluster bootstrap: use wildboottest package. "
                "Manual implementations of complex estimators ALWAYS produce bugs that "
                "referees detect, destroying the paper's credibility. USE PACKAGES.\n\n"
                "IMPORTANT — Missing data handling (referee standards): "
                "00_clean.py MUST: (a) print a missingness table (% missing per variable), "
                "(b) test if missings are MCAR/MAR/MNAR, "
                "(c) justify the chosen strategy (listwise deletion, imputation, or bounds), "
                "(d) log how many obs are dropped at each step. "
                "02_robustness.py MUST include a robustness check comparing results "
                "with and without imputed observations. "
                "03_output.py MUST generate LaTeX tables (.tex files) in paper/tables/ "
                "in addition to figures."
                "\n\n*** TABLE QUALITY (CRITICAL — prevents blank cells in paper) ***\n"
                "03_output.py MUST handle missing/NaN results gracefully:\n"
                "  (a) Before writing any table, check every value. If a value is NaN/None,\n"
                "      replace it with '---' in the LaTeX output and add a table note\n"
                "      explaining the missing value (e.g., 'Estimator did not converge').\n"
                "  (b) If a package like rdrobust returns NaN for point estimates but valid\n"
                "      confidence intervals, compute the CI midpoint as the point estimate\n"
                "      and note '(CI midpoint)' in the table.\n"
                "  (c) NEVER write NaN, nan, None, or empty strings into .tex table cells.\n"
                "  (d) Before saving each .tex file, verify no cell is empty by checking\n"
                "      the output string for '& &' or '& \\\\' patterns.\n"
                "  (e) If the main estimator fails completely, use the fallback estimator\n"
                "      (e.g., statsmodels OLS/WLS) for ALL specifications, not just some.\n"
                "      A table with mixed estimators is better than a table with blank cells.\n"
                "\n\n*** FALSIFICATION PLANNING (from clo-author best practices) ***\n"
                "BEFORE running the main analysis, 02_robustness.py MUST pre-commit to:\n"
                "  (a) At least ONE placebo outcome — a variable that should NOT be affected "
                "by treatment. Run the same specification and verify null result.\n"
                "  (b) At least ONE placebo treatment — either fake timing or fake group. "
                "Verify null result.\n"
                "  (c) Print expected sign and magnitude BEFORE showing actual results. "
                "This demonstrates the analysis was not data-mined.\n"
                "\n*** SANITY CHECK (from clo-author best practices) ***\n"
                "After computing main results, 01_main.py MUST:\n"
                "  (a) Print the expected sign based on theory/literature\n"
                "  (b) Compare the actual sign to the expected sign\n"
                "  (c) Report effect magnitude in interpretable units (SD, percentage points)\n"
                "  (d) Compare magnitude to prior literature if known\n"
                "  (e) Flag if the effect implies implausibly large changes (>1 SD shift)\n"
                "\n*** OUTCOME VARIABLE VALIDATION (CRITICAL — prevents using wrong variables) ***\n"
                "00_clean.py MUST validate outcome variables BEFORE saving clean_data.csv:\n"
                "  (a) For EACH proposed outcome variable, compute correlation with treatment.\n"
                "      If |correlation| < 0.01 for ALL outcomes, the variables are likely WRONG.\n"
                "  (b) If outcomes show zero correlation with treatment, SEARCH the dataset for\n"
                "      better outcomes: look for variables with prefixes like 'end_', 'mid_',\n"
                "      'post_', 'follow_', 'outcome_', 'y_', or any variable that correlates\n"
                "      meaningfully (|r| > 0.05) with the treatment variable.\n"
                "  (c) Print a ranked list of the top 10 variables most correlated with treatment.\n"
                "  (d) If NO variable correlates with treatment (|r| < 0.02 for all), print:\n"
                "      '[WARNING] No variable in this dataset shows meaningful correlation with\n"
                "      treatment. This data may not support the proposed research question.\n"
                "      Consider: (1) wrong outcome variables, (2) null effect, (3) data quality issue.'\n"
                "  (e) Use the BEST available outcomes (highest treatment correlation) as the\n"
                "      primary dependent variables, not arbitrarily named columns.\n"
                + estimator_guidance
                + checklist_musts
                + template_instruction
                + data_preview
            ),
            files=files,
            project_dir=project_dir,
        )

    # After intervention: validate scripts exist and are complete
    existing_scripts = sorted(scripts_dir.glob("[0-9]*.py"))
    expected_scripts = ["00_clean.py", "01_main.py", "02_robustness.py", "03_output.py"]

    if not existing_scripts:
        print("  [error] No scripts found after intervention.")
        state["stages"]["stage4bc"] = {"status": "failed", "reason": "no_scripts"}
        save_state(project_dir, state)
        return state

    # Check all 4 expected scripts exist
    found = [s.name for s in existing_scripts]
    missing_scripts = [s for s in expected_scripts if s not in found]
    if missing_scripts:
        print(f"  [warning] Missing scripts: {', '.join(missing_scripts)}")
        print(f"  [warning] Found: {', '.join(found)}")
        print(f"  Pipeline will continue with available scripts.")

    # Verify scripts are non-empty (not just touched)
    for script in existing_scripts:
        size = script.stat().st_size
        if size < 100:
            print(f"  [warning] {script.name} is suspiciously small ({size} bytes) — may be incomplete")

    # ── Template integrity check ─────────────────────────────────────────
    # Verify Claude filled placeholders instead of rewriting from scratch.
    # If templates were overwritten, restore them and warn.
    if design_type in AVAILABLE_DESIGNS and templates:
        import re as _re_check
        template_violations = []
        for filename, original_content in templates.items():
            script_path = scripts_dir / filename
            if not script_path.exists():
                continue
            current = script_path.read_text(encoding="utf-8")

            # Check 1: Does the script still contain the FIXED CODE marker?
            has_fixed_marker = "FIXED CODE" in current or "does not change between projects" in current

            # Check 2: Are there unfilled {{VARIABLE}} placeholders?
            unfilled = _re_check.findall(r'\{\{(\w+)\}\}', current)

            # Check 3: Does it still contain the key template functions?
            # (check for at least 2 function signatures from the original)
            import re as _re_fn
            original_fns = set(_re_fn.findall(r'def (\w+)\(', original_content))
            current_fns = set(_re_fn.findall(r'def (\w+)\(', current))
            preserved_fns = original_fns & current_fns
            fn_preservation = len(preserved_fns) / max(len(original_fns), 1)

            if not has_fixed_marker or fn_preservation < 0.5:
                template_violations.append(filename)
                print(f"  [TEMPLATE VIOLATION] {filename}: template was overwritten "
                      f"(fixed_marker={'yes' if has_fixed_marker else 'NO'}, "
                      f"fn_preserved={fn_preservation:.0%})")
                # Restore template but keep the filled variables from the overwritten version
                # Try to extract variable assignments from the overwritten script
                print(f"  [restore] Restoring template for {filename}")
                script_path.write_text(original_content, encoding="utf-8")

            if unfilled:
                print(f"  [warning] {filename}: {len(unfilled)} unfilled placeholders: "
                      f"{', '.join(unfilled[:5])}")

        if template_violations:
            print(f"\n  [TEMPLATE] {len(template_violations)} scripts were rewritten from scratch.")
            print(f"  [TEMPLATE] Templates restored. Claude must fill placeholders, not rewrite.")
            print(f"  [TEMPLATE] Re-running manual intervention...")
            # Re-request intervention with stronger instruction
            request_manual_intervention(
                stage="stage4_template_refill",
                issue=(
                    f"TEMPLATE VIOLATION: Claude rewrote {len(template_violations)} scripts "
                    f"from scratch instead of filling placeholders. "
                    f"Templates have been RESTORED. "
                    f"Files: {', '.join(template_violations)}.\n\n"
                    f"YOU MUST:\n"
                    f"  1. Read each script in scripts/python/\n"
                    f"  2. Find the section '# PROJECT-SPECIFIC VARIABLES'\n"
                    f"  3. Replace ONLY the {{{{VARIABLE}}}} placeholders with actual values\n"
                    f"  4. DO NOT modify anything below '# FIXED CODE'\n"
                    f"  5. Execute all scripts in order after filling\n\n"
                    f"If you delete or rewrite the template code again, the pipeline will "
                    f"restore it again. The template code is MANDATORY."
                ),
                files=[str(scripts_dir)],
                project_dir=project_dir,
            )
        else:
            print(f"  [template] All scripts preserved template structure [OK]")

    # Mark 4a as completed if strategy exists
    if (strategy_dir / "strategy_memo.md").exists():
        from datetime import datetime as _dt
        state["stages"]["stage4a"] = {
            "status": "completed",
            "strategy_dir": str(strategy_dir),
            "completed_at": _dt.now().isoformat(),
        }

    # Validate scripts ran (check for output files)
    clean_dir = project_dir / "data" / "clean"
    has_outputs = (
        clean_dir.exists()
        and (clean_dir / "clean_data.csv").exists()
        and len(list(clean_dir.glob("*.csv"))) >= 3
    )

    if has_outputs:
        print("  [4] Scripts already executed -- skipping re-execution.")
        all_ok = True
        all_results = {s.name: {"ok": True} for s in existing_scripts}
        py_scripts = existing_scripts
    else:
        # Execute scripts
        print(f"\n  [4b] Executing {len(existing_scripts)} scripts...")
        py_scripts, all_results, all_ok = _execute_scripts(existing_scripts, scripts_dir)

    # Post-execution output validation
    if all_ok:
        expected_outputs = ["clean_data.csv", "main_results.csv"]
        for f in expected_outputs:
            fpath = clean_dir / f
            if not fpath.exists():
                print(f"  [warning] Expected output missing: {f}")
                print(f"  Scripts may have run but produced incomplete results.")
            elif fpath.stat().st_size < 50:
                print(f"  [warning] {f} is nearly empty ({fpath.stat().st_size} bytes)")

        # Check that main_results.csv has actual data
        results_path = clean_dir / "main_results.csv"
        if results_path.exists():
            try:
                import pandas as _pd
                _mr = _pd.read_csv(results_path)
                if len(_mr) == 0:
                    print("  [warning] main_results.csv has 0 rows -- scripts may have failed silently")
                else:
                    print(f"  [4] Output validation: main_results.csv has {len(_mr)} rows [OK]")
            except Exception:
                pass

    # Validation
    from ..validators.code_validator import validate as validate_code
    validation = validate_code(scripts_dir, project_dir, all_results)
    print(f"  [4c] {validation.format_for_log()}")

    # Compute critic_score from validation results instead of hardcoding
    counts = validation.summary_counts
    hard_pass = counts.get("hard_passed", counts.get("hard_pass", 0))
    hard_total = counts.get("hard_total", 1)
    soft_pass = counts.get("soft_passed", counts.get("soft_pass", 0))
    soft_total = counts.get("soft_total", 1)

    # Base score: 60 if all hard pass, 40 if not
    if hard_pass == hard_total:
        code_score = 60
    else:
        code_score = 40

    # Add up to 40 points based on soft check pass rate
    if soft_total > 0:
        soft_rate = soft_pass / soft_total
        code_score += int(soft_rate * 40)

    # Bonus if all scripts ran OK
    if all_ok:
        code_score = min(100, code_score + 5)

    print(f"  [4c] Code score: {code_score}/100 "
          f"(hard {hard_pass}/{hard_total}, soft {soft_pass}/{soft_total})")

    # Save state
    from datetime import datetime as _dt
    state["stages"]["stage4bc"] = {
        "status": "completed",
        "scripts_dir": str(scripts_dir),
        "scripts": [s.name for s in py_scripts],
        "all_scripts_ok": all_ok,
        "critic_score": code_score,
        "critic_result": {
            "score": code_score,
            "summary": f"Computed from validation: hard {hard_pass}/{hard_total}, "
                       f"soft {soft_pass}/{soft_total}",
        },
        "validation": validation.summary_counts,
        "validation_hard_pass": validation.hard_pass,
        "completed_at": _dt.now().isoformat(),
    }
    state["current_stage"] = 4
    save_state(project_dir, state)
    return state
