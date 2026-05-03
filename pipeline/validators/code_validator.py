"""Stage 4 automated validator.

Checks objective facts about generated scripts and their outputs:
script existence, execution success, output files, code patterns.
"""

import re
from pathlib import Path

from . import CheckLevel, ValidationResult


EXPECTED_SCRIPTS = ["00_clean.py", "01_main.py", "02_robustness.py", "03_output.py"]


def validate(
    scripts_dir: Path, project_dir: Path, all_results: dict
) -> ValidationResult:
    vr = ValidationResult()
    _check_scripts_exist(vr, scripts_dir)
    _check_scripts_ran(vr, all_results)
    _check_output_files(vr, scripts_dir, project_dir)
    _check_results_summary_content(vr, scripts_dir, project_dir)
    _check_code_patterns(vr, scripts_dir)
    _check_referee_checklist_coverage(vr, scripts_dir, project_dir)
    return vr


# ── HARD checks ──────────────────────────────────────────────────────────────

def _check_scripts_exist(vr: ValidationResult, scripts_dir: Path):
    for name in EXPECTED_SCRIPTS:
        exists = (scripts_dir / name).exists()
        vr.add(
            f"script_exists:{name}", CheckLevel.HARD, exists,
            f"{name} {'found' if exists else 'MISSING'}"
        )


def _check_scripts_ran(vr: ValidationResult, all_results: dict):
    for name in EXPECTED_SCRIPTS:
        result = all_results.get(name, {})
        ok = result.get("ok", False)
        if ok:
            detail = "ran OK"
        else:
            stderr = result.get("stderr", "unknown error")
            detail = f"FAILED: {stderr[:200]}"
        vr.add(f"script_ran:{name}", CheckLevel.HARD, ok, detail)


def _check_output_files(vr: ValidationResult, scripts_dir: Path, project_dir: Path):
    clean_dir = project_dir / "data" / "clean"
    tables_dir = project_dir / "paper" / "tables"
    figures_dir = project_dir / "paper" / "figures"

    # Clean data file
    clean_files = (
        list(clean_dir.glob("*.parquet"))
        + list(clean_dir.glob("*.csv"))
        if clean_dir.exists() else []
    )
    vr.add(
        "clean_data_exists", CheckLevel.HARD, len(clean_files) > 0,
        f"Found {len(clean_files)} data file(s) in data/clean/"
        if clean_files else "No .parquet or .csv in data/clean/"
    )

    # Tables — accept .tex files in tables/ OR tables embedded in main.tex
    tex_files = list(tables_dir.glob("*.tex")) if tables_dir.exists() else []
    # Also check for tables in main.tex or .md summary files
    other_table_files = (
        list(tables_dir.glob("*.md")) if tables_dir.exists() else []
    )
    main_tex = tables_dir.parent / "main.tex" if tables_dir.exists() else Path(".")
    has_inline_tables = False
    if main_tex.exists():
        main_content = main_tex.read_text(encoding="utf-8")
        has_inline_tables = r"\begin{table}" in main_content or r"\begin{tabular}" in main_content
    tables_found = len(tex_files) > 0 or len(other_table_files) > 0 or has_inline_tables
    vr.add(
        "tables_exist", CheckLevel.HARD, tables_found,
        f"Found {len(tex_files)} .tex table(s)" + (", inline tables in main.tex" if has_inline_tables else "")
        + (f", {len(other_table_files)} summary file(s)" if other_table_files else "")
        if tables_found else "No tables found in paper/tables/ or main.tex"
    )

    # Figures (SOFT — some papers are table-only)
    pdf_files = list(figures_dir.glob("*.pdf")) if figures_dir.exists() else []
    vr.add(
        "figures_exist", CheckLevel.SOFT, len(pdf_files) > 0,
        f"Found {len(pdf_files)} figure(s): {', '.join(f.name for f in pdf_files[:5])}"
        if pdf_files else "No .pdf files in paper/figures/"
    )

    # results_summary.md
    summary_path = _find_results_summary(scripts_dir, project_dir)
    vr.add(
        "results_summary_exists", CheckLevel.HARD, summary_path is not None,
        f"Found at {summary_path}" if summary_path else
        "results_summary.md not found in scripts/ or data/clean/"
    )

    # Non-empty check for all outputs
    all_outputs = tex_files + pdf_files + clean_files
    if summary_path:
        all_outputs.append(summary_path)
    empty_files = [f for f in all_outputs if f.stat().st_size == 0]
    vr.add(
        "outputs_non_empty", CheckLevel.HARD, len(empty_files) == 0,
        f"{len(empty_files)} empty file(s): {', '.join(f.name for f in empty_files)}"
        if empty_files else f"All {len(all_outputs)} output files are non-empty"
    )


# ── SOFT checks ──────────────────────────────────────────────────────────────

def _check_results_summary_content(
    vr: ValidationResult, scripts_dir: Path, project_dir: Path
):
    summary_path = _find_results_summary(scripts_dir, project_dir)
    if not summary_path:
        return  # already flagged by _check_output_files

    text = summary_path.read_text(encoding="utf-8")
    numbers = re.findall(r'-?\d+\.?\d*', text)
    has_numbers = len(numbers) >= 3
    vr.add(
        "results_summary_has_numbers", CheckLevel.SOFT, has_numbers,
        f"Found {len(numbers)} numeric values"
        if has_numbers else
        f"Only {len(numbers)} numbers found — likely placeholder text"
    )


def _check_code_patterns(vr: ValidationResult, scripts_dir: Path):
    # Seed setting
    for name in EXPECTED_SCRIPTS:
        path = scripts_dir / name
        if not path.exists():
            continue
        code = path.read_text(encoding="utf-8")

        if name == "00_clean.py":
            has_seed = bool(re.search(r'(np\.random\.seed|random\.seed|seed\s*=)', code))
            vr.add(
                f"seed_set:{name}", CheckLevel.SOFT, has_seed,
                "Random seed found" if has_seed else "No random seed set"
            )

    # SE robustness in regression scripts (design-aware)
    for name in ["01_main.py", "02_robustness.py"]:
        path = scripts_dir / name
        if not path.exists():
            continue
        code = path.read_text(encoding="utf-8")
        code_lower = code.lower()

        # Detect if this is an RCT/experiment (individual-level, no clustering needed)
        is_rct_design = bool(re.search(
            r'(rct|randomiz|experiment|vignette|treatment.*assign|balance.*table)',
            code_lower
        ))

        if is_rct_design:
            # For RCTs: check for HC2 robust SEs (not clustering)
            has_robust_se = bool(re.search(
                r'(HC[0-9]|hc2|heteroskedast.*robust|cov_type.*HC|robust.*se)',
                code, re.IGNORECASE
            ))
            vr.add(
                f"se_robust:{name}", CheckLevel.SOFT, has_robust_se,
                "HC robust SEs found (appropriate for individual-level RCT)"
                if has_robust_se else
                "No robust SEs detected -- HC2 recommended for RCT"
            )
        else:
            # For panel/DiD: check for clustering
            has_cluster = bool(re.search(
                r'(cov_type.*cluster|\.fit\(.*cluster|get_robustcov|ClusteredSE|cluster.*se)',
                code, re.IGNORECASE
            ))
            vr.add(
                f"se_clustering:{name}", CheckLevel.SOFT, has_cluster,
                "Clustering pattern found" if has_cluster else
                "No SE clustering detected -- verify this is intentional"
            )

    # Imports in 01_main.py
    main_path = scripts_dir / "01_main.py"
    if main_path.exists():
        code = main_path.read_text(encoding="utf-8")
        has_stats = bool(re.search(
            r'(import statsmodels|import linearmodels|from statsmodels|from linearmodels'
            r'|import pyfixest|from pyfixest|import did|from csdid)',
            code
        ))
        vr.add(
            "stats_library_imported", CheckLevel.SOFT, has_stats,
            "Statistical library imported"
            if has_stats else
            "No statsmodels/linearmodels/pyfixest import found in 01_main.py"
        )

    # ── Causal method checks ──────────────────────────────────────────────
    # Check if scripts implement key causal inference requirements
    all_code = ""
    for name in ["01_main.py", "02_robustness.py"]:
        path = scripts_dir / name
        if path.exists():
            all_code += path.read_text(encoding="utf-8") + "\n"

    if all_code:
        # ── Check for manual implementations of complex estimators ────
        # These are fragile and produce bugs that referees detect
        manual_patterns = [
            (r'def\s+two_by_two_did|def\s+manual.*cs|def\s+manual.*did',
             "Manual 2x2 DiD implementation detected -- use pyfixest or csdid package instead"),
            (r'def\s+.*bacon.*decomp|# Manual Bacon',
             "Manual Bacon decomposition detected -- use validated package or omit"),
            (r'for\s+g\s+in\s+cohorts.*for\s+t\s+in.*years',
             "Manual cohort x time loop detected -- likely manual CS, use pyfixest instead"),
        ]
        for pat, msg in manual_patterns:
            if re.search(pat, all_code, re.IGNORECASE):
                vr.add("no_manual_estimators", CheckLevel.SOFT, False, msg)

        # Check for validated package usage
        uses_validated = bool(re.search(
            r'(import pyfixest|from pyfixest|import csdid|from csdid'
            r'|pf\.did|ATTgt|feols|event_study)',
            all_code
        ))
        if not uses_validated:
            # Check if it at least uses linearmodels (acceptable for simple TWFE)
            uses_linearmodels = bool(re.search(r'(import linearmodels|from linearmodels|PanelOLS)', all_code))
            if not uses_linearmodels:
                vr.add("validated_package", CheckLevel.SOFT, False,
                       "No validated econometrics package (pyfixest/csdid/linearmodels) detected")

        # Detect if this is a DiD/event study design
        is_did = bool(re.search(
            r'(did|diff.*in.*diff|event.study|twfe|two.way.*fixed)',
            all_code, re.IGNORECASE
        ))

        if is_did:
            # Pre-trend test
            has_pretrend = bool(re.search(
                r'(pre.?trend|pre.?period|parallel.*trend|f.?test.*pre|joint.*test.*pre'
                r'|placebo.*test|false.*treatment)',
                all_code, re.IGNORECASE
            ))
            vr.add(
                "pretrend_test", CheckLevel.SOFT, has_pretrend,
                "Pre-trend or placebo test found"
                if has_pretrend else
                "No pre-trend/placebo test detected — required for DiD/event study"
            )

            # Wild cluster bootstrap
            has_wcb = bool(re.search(
                r'(wild.*cluster.*bootstrap|wildboottest|boottest|wcb|rademacher'
                r'|bootstrap.*cluster)',
                all_code, re.IGNORECASE
            ))
            vr.add(
                "wild_cluster_bootstrap", CheckLevel.SOFT, has_wcb,
                "Wild cluster bootstrap found"
                if has_wcb else
                "No wild cluster bootstrap detected — recommended for <50 clusters"
            )

            # Heterogeneity-robust estimator — only flag if staggered treatment
            is_staggered = bool(re.search(
                r'(stagger|cohort.*treat|treatment.*timing|adoption.*year'
                r'|treat.*year.*var|first.*treat)',
                all_code, re.IGNORECASE
            ))
            is_common_shock = bool(re.search(
                r'(common.*shock|simultaneous|all.*units.*treat|universal.*treat'
                r'|covid.*shock|pandemic.*shock)',
                all_code, re.IGNORECASE
            ))

            if is_staggered and not is_common_shock:
                # Staggered treatment: Sun-Abraham/CS is essential
                has_het_robust = bool(re.search(
                    r'(sun.*abraham|callaway.*sant|de.*chaisemartin|bacon.*decomp'
                    r'|interaction.weighted|SA.*estimator|CS.*estimator|DIDM)',
                    all_code, re.IGNORECASE
                ))
                vr.add(
                    "het_robust_estimator", CheckLevel.SOFT, has_het_robust,
                    "Heterogeneity-robust estimator found (Sun-Abraham/CS/DIDM)"
                    if has_het_robust else
                    "STAGGERED DiD detected but no Sun-Abraham/Callaway-Sant'Anna — "
                    "TWFE may produce biased estimates with negative weights"
                )
            elif not is_common_shock:
                # Unknown treatment structure: soft recommendation
                has_het_robust = bool(re.search(
                    r'(sun.*abraham|callaway.*sant|de.*chaisemartin|bacon.*decomp'
                    r'|interaction.weighted|SA.*estimator|CS.*estimator|DIDM)',
                    all_code, re.IGNORECASE
                ))
                if has_het_robust:
                    vr.add(
                        "het_robust_estimator", CheckLevel.SOFT, True,
                        "Heterogeneity-robust estimator found"
                    )


# ── Referee checklist coverage ────────────────────────────────────────────────

# Keywords that indicate a MUST requirement is addressed in the code.
# Each tuple: (checklist keyword pattern, code keyword patterns)
# Generic (works for any design)
_CHECKLIST_CODE_MAP_GENERIC = [
    (r"summary.*statistic", [r"summary.*stat|describe|mean.*sd|\.describe\("]),
    (r"missingness|missing.*data", [r"miss|isnull|dropna|MCAR|MAR"]),
    (r"data.*provenance|document.*construct", [r"provenance|source.*log|construct|document"]),
    (r"winsoriz", [r"winsoriz|clip|percentile.*trim"]),
    (r"robust.*standard|heteroskedast", [r"HC[0-9]|robust|cov_type|hc2|heteroskedast"]),
    (r"placebo.*test|permutation|reshuffle", [r"placebo|permut|shuffle|fake.*treat|randomiz.*infer|reshuffle"]),
    (r"heterogeneity.*interact|subgroup|CATE", [r"interact|subgroup|CATE|quintile|tercile|_x_"]),
    (r"power.*analys|MDE|minimum.*detect", [r"power|MDE|minimum.*detect|effect.*size"]),
    (r"multiple.*test.*correct|benjamini|FDR", [r"benjamini|hochberg|FDR|bonferroni|multiple.*test"]),
    # Presentation / reporting requirements
    (r"report.*three.*spec|three.*specification", [r"spec.*1|spec.*2|spec.*3|raw.*diff|baseline.*control|lasso"]),
    (r"main.*results.*table|treatment.*coefficient", [r"table|to_csv|to_latex|result"]),
    (r"confidence.*interval|95.*CI", [r"ci_|conf.*int|1\.96|ci_lower|ci_upper"]),
    (r"joint.*f.?test|wald.*test|chi.*squared", [r"f_test|f.?stat|wald|chi2|joint.*test|fvalue"]),
    (r"continuous.*interact|linear.*interact", [r"continuous.*inter|treat.*score|_x_.*score"]),
    (r"cell.*N|report.*N.*per|sample.*size.*per", [r"cell.*n|group.*count|value_counts|crosstab|n_per"]),
    # Additional generic requirements
    (r"r.?squared|within.?r2|goodness.*fit", [r"r.?squared|r2|rsquared|r_sq"]),
    (r"n.*observat|sample.*size|number.*obs", [r"nobs|n_obs|len\(|shape\[0\]|\.nobs"]),
    (r"standard.*error.*parenthes|SE.*parenthes", [r"se.*paren|\(.*se\)|std.*error"]),
    (r"sensitivity.*analys|sensitivity.*check", [r"sensitiv|alternative|robust"]),
    (r"save.*result|export.*result|write.*csv", [r"to_csv|to_parquet|to_excel|save|write"]),
    (r"figure.*plot|generate.*figure", [r"plt\.|savefig|figure|\.plot\("]),
    (r"latex.*table|tex.*table|generate.*table", [r"to_latex|\\\\begin\{tab|\.tex|tabular"]),
    (r"log.*transform|logarithm", [r"np\.log|log_|log\("]),
    (r"seed|reproducib", [r"random\.seed|np\.random\.seed|rng|default_rng"]),
]

# DiD / event study specific
_CHECKLIST_CODE_MAP_DID = [
    (r"event.study|distributed.lag", [r"event.?time|event.?study|distributed.?lag"]),
    (r"cluster.*standard.*error", [r"cluster|cov_type.*cluster"]),
    (r"wild.*cluster.*bootstrap", [r"wildboot|wild.*cluster.*bootstrap|boottest|rademacher"]),
    (r"pre.?trend.*test|joint.*f.?test", [r"pre.?trend|f.?test|wald.*test|joint.*test"]),
    (r"country.*specific.*trend|unit.*trend", [r"country.*trend|t_trend|linear.*trend|unit.*trend"]),
    (r"balanced.*panel", [r"balanced|balance"]),
    (r"composition.*effect", [r"composition|n_language|balanced.*lang"]),
    (r"stagger|callaway|sun.*abraham", [r"callaway|sun.*abraham|stagger|csdid|pyfixest.*did"]),
    (r"bacon.*decomp|goodman", [r"bacon|decomp|goodman"]),
    (r"anticipat|lead.*period", [r"anticipat|lead|k.*=.*1|k.*=.*2"]),
    (r"alternative.*treat.*timing|treatment.*defin", [r"alt.*treat|threshold|alternative.*def"]),
    # Additional DiD requirements
    (r"alternative.*outcome|different.*outcome|robustness.*outcome", [r"alt.*outcome|alternative.*outcome|outcome.*2|_alt|v2x|freedom.*house"]),
    (r"power.*analys.*cohort|MDE.*cohort|minimum.*detect.*cohort", [r"power|MDE|minimum.*detect|n_g.*<"]),
    (r"overlap|common.*support|covariate.*distribut", [r"overlap|common.*support|propensity|covariate.*dist"]),
    (r"honest.*did|rambachan|roth.*2022|sensitivity.*pre.?trend", [r"honest.*did|rambachan|roth|sensitivity.*pre|breakdown"]),
    (r"permutation.*fake.*timing|randomize.*treatment.*onset", [r"permut.*timing|shuffle.*first|fake.*onset|random.*assign.*cohort"]),
    (r"never.?treated|not.?yet.?treated|control.*group.*type", [r"never.*treat|not.*yet.*treat|control.*group"]),
    (r"simultaneous.*confidence|pointwise.*confidence", [r"simultaneous|pointwise|bonferroni.*ci"]),
    (r"cohort.*table|cohort.*composition", [r"cohort.*table|cohort.*compos|n_countries.*cohort|groupby.*cohort"]),
    (r"normalize.*reference|omit.*period|reference.*period", [r"ref.*period|omit|normalize|t.*=.*-1"]),
    (r"aggregate.*ATT|simple.*ATT|calendar.*time.*ATT", [r"simple.*att|aggregate|calendar.*att|att_simple"]),
]

# RCT / experiment specific
_CHECKLIST_CODE_MAP_RCT = [
    # Balance and randomization
    (r"balance.*table|covariate.*balance|randomiz.*check", [r"balance|smd|standardized.*mean|t.?test"]),
    (r"regress.*treatment.*covariate|joint.*f.*balance", [r"joint.*f|ols.*treat.*covar|f_test.*balance|fvalue"]),
    (r"casualty.*salient|held.*constant|balanced.*between", [r"balance|t.?test|smd"]),
    # Effect sizes
    (r"cohen.*d|effect.*size|standardized.*effect", [r"cohen|effect.*size|cohens_d"]),
    # Standard errors
    (r"HC2|heteroskedast.*robust", [r"HC2|hc2|heteroskedast|cov_type.*HC"]),
    # LASSO
    (r"LASSO|double.*select|post.*selection|cross.*valid.*lambda", [r"lasso|LassoCV|double.*select|debiased|cross_val"]),
    (r"lambda.*select|cv\.glmnet|sklearn.*CV", [r"lambda|alpha|LassoCV|cross_val"]),
    # CATE
    (r"CATE.*quintile|treatment.*within.*quintile", [r"CATE|quintile|qcut|treatment.*quintile|cate"]),
    (r"quintile.*treatment.*interact", [r"quintile.*inter|q\d.*treat|quintile_x"]),
    # Attrition
    (r"attrition|non.?response|differential.*dropout|completion.*rate", [r"attrition|non.?response|dropout|lee.*bound|missing.*treat"]),
    (r"lee.*bound", [r"lee.*bound|trim|attrition.*bound"]),
    # Treatment verification
    (r"treatment.*binary|assert.*treatment|no.*partial", [r"treat.*binary|assert|unique.*treat|nunique.*treat|value_counts.*treat"]),
    # Specifications
    (r"unadjusted.*effect|raw.*difference|no.*control|without.*covariate", [r"unadjust|raw.*diff|no.*control|without.*control|spec.*1"]),
    (r"ordered.*probit|ordinal|likert", [r"ordered.*probit|ordinal|OrderedModel|likert"]),
    (r"logit|binary.*outcome", [r"logit|Logit|binary|_binary"]),
    # Reporting
    (r"manipulation.*check|attention.*check|comprehension", [r"manipulation|attention.*check|comprehension"]),
    (r"report.*wording|exact.*wording|treatment.*condition", [r"wording|vignette|condition|label"]),
    # Pitfalls (these match if the code avoids the pitfall)
    (r"do not.*naive.*post.*lasso|not.*naive", [r"double|debiased|two.*step"]),
    (r"do not.*independent.*hypothesis|without.*correction", [r"benjamini|hochberg|FDR|bonferroni"]),
    (r"do not.*post.*treatment.*control", [r"pre.*treatment|baseline|pre_treat"]),
]


def _check_referee_checklist_coverage(
    vr: ValidationResult, scripts_dir: Path, project_dir: Path
):
    """Cross-check referee MUST requirements against generated code."""
    checklist_path = project_dir / "strategy" / "referee_checklist.md"
    if not checklist_path.exists():
        return

    cl_text = checklist_path.read_text(encoding="utf-8")

    # Extract MUST requirements
    musts = []
    in_must = False
    for line in cl_text.splitlines():
        if "MUST-HAVE" in line or "MUST" in line and "##" in line:
            in_must = True
            continue
        if in_must and line.startswith("## "):
            break
        if in_must and line.strip().startswith("- "):
            musts.append(line.strip("- ").strip())

    if not musts:
        return

    # Read all script code
    all_code = ""
    for name in EXPECTED_SCRIPTS:
        path = scripts_dir / name
        if path.exists():
            all_code += path.read_text(encoding="utf-8") + "\n"

    if not all_code:
        return

    all_code_lower = all_code.lower()

    # Detect design type to use appropriate keyword map
    is_rct = bool(re.search(
        r'(rct|randomiz|experiment|vignette|treatment.*assign|balance.*table)',
        all_code_lower
    ))
    is_did = bool(re.search(
        r'(did|event.study|stagger|twfe|diff.*in.*diff)',
        all_code_lower
    ))

    # Build keyword map: generic + design-specific
    checklist_map = list(_CHECKLIST_CODE_MAP_GENERIC)
    if is_rct:
        checklist_map.extend(_CHECKLIST_CODE_MAP_RCT)
    if is_did:
        checklist_map.extend(_CHECKLIST_CODE_MAP_DID)

    # Check each MUST against code
    implemented = 0
    not_implemented = []
    for must in musts:
        must_lower = must.lower()
        found = False
        for checklist_pat, code_pats in checklist_map:
            if re.search(checklist_pat, must_lower):
                if any(re.search(cp, all_code_lower) for cp in code_pats):
                    found = True
                    break
        if found:
            implemented += 1
        else:
            not_implemented.append(must[:80])

    total = len(musts)
    coverage_pct = (implemented / total * 100) if total > 0 else 0

    vr.add(
        "referee_checklist_coverage", CheckLevel.SOFT,
        coverage_pct >= 60,
        f"Referee checklist: {implemented}/{total} MUST requirements detected in code "
        f"({coverage_pct:.0f}%)"
    )

    if not_implemented:
        # Log first few missing for the report
        missing_preview = "; ".join(not_implemented[:5])
        if len(not_implemented) > 5:
            missing_preview += f" ... and {len(not_implemented) - 5} more"
        vr.add(
            "referee_checklist_missing", CheckLevel.SOFT,
            len(not_implemented) <= total * 0.4,
            f"Possibly unimplemented: {missing_preview}"
        )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _find_results_summary(scripts_dir: Path, project_dir: Path):
    for candidate in [
        scripts_dir / "results_summary.md",
        project_dir / "data" / "clean" / "results_summary.md",
        project_dir / "paper" / "results_summary.md",
        project_dir / "paper" / "tables" / "results_summary.md",
        project_dir / "results_summary.md",
    ]:
        if candidate.exists():
            return candidate
    return None
