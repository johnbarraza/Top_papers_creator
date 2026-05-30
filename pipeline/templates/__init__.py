"""Script templates by research design type.

Each design (RDD, DiD, RCT, IV) has 4 template scripts:
  - 00_clean.py: data loading, cleaning, validation
  - 01_main.py: main estimation
  - 02_robustness.py: robustness checks
  - 03_output.py: tables and figures

Templates have {{VARIABLE}} placeholders that Claude fills with
project-specific values. The fixed code handles known pitfalls
(NaN handling, fallback estimators, table validation, etc.)
"""

from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent

AVAILABLE_DESIGNS = {
    "rdd": {
        "name": "Regression Discontinuity Design",
        "scripts": [
            "rdd_00_clean.py",
            "rdd_01_main.py",
            "rdd_02_robustness.py",
            "rdd_03_output.py",
        ],
        "variables": [
            "DATA_FILE", "DATA_FORMAT", "RUNNING_VAR", "THRESHOLD",
            "TREATMENT_VAR", "OUTCOME_VARS", "CLUSTER_VAR", "TIME_VAR",
            "COVARIATES", "PLACEBO_OUTCOMES", "COVARIATES_BASIC",
            "COVARIATES_EXT", "EXPECTED_SIGNS", "PRIMARY_OUTCOME",
        ],
    },
    "did": {
        "name": "Difference-in-Differences",
        "scripts": [
            "did_00_clean.py",
            "did_01_main.py",
            "did_02_robustness.py",
            "did_03_output.py",
        ],
        "variables": [
            "DATA_FILE", "DATA_FORMAT", "ENTITY_VAR", "TIME_VAR",
            "TREATMENT_VAR", "OUTCOME_VARS", "CLUSTER_VAR", "COVARIATES",
            "FIRST_TREAT_VAR", "EXPECTED_SIGNS", "PRIMARY_OUTCOME",
            "PLACEBO_OUTCOMES",
        ],
    },
    "rct": {
        "name": "Randomized Controlled Trial",
        "scripts": [
            "rct_00_clean.py",
            "rct_01_main.py",
            "rct_02_robustness.py",
            "rct_03_output.py",
        ],
        "variables": [
            "DATA_FILE", "DATA_FORMAT", "TREATMENT_VAR", "TREATMENT_ARMS",
            "OUTCOME_VARS", "CLUSTER_VAR", "COVARIATES", "STRATA_VAR",
            "EXPECTED_SIGNS", "HETEROGENEITY_VARS", "PRIMARY_OUTCOME",
            "PLACEBO_OUTCOMES",
        ],
    },
    "iv": {
        "name": "Instrumental Variables / 2SLS",
        "scripts": [
            "iv_00_clean.py",
            "iv_01_main.py",
            "iv_02_robustness.py",
            "iv_03_output.py",
        ],
        "variables": [
            "DATA_FILE", "DATA_FORMAT", "ENDOGENOUS_VAR", "INSTRUMENT_VARS",
            "OUTCOME_VARS", "ENTITY_VAR", "TIME_VAR", "CLUSTER_VAR",
            "COVARIATES", "EXPECTED_SIGNS", "PRIMARY_OUTCOME",
            "PLACEBO_OUTCOMES",
        ],
    },
}


def get_template(design: str, script_num: int) -> str | None:
    """Load a template file for a given design and script number.

    Args:
        design: "rdd", "did", "rct", or "iv"
        script_num: 0, 1, 2, or 3

    Returns:
        Template content as string, or None if not found.
    """
    if design not in AVAILABLE_DESIGNS:
        return None

    scripts = AVAILABLE_DESIGNS[design]["scripts"]
    if script_num >= len(scripts):
        return None

    path = TEMPLATE_DIR / scripts[script_num]
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def get_all_templates(design: str) -> dict[str, str]:
    """Load all 4 templates for a design. Returns {filename: content}."""
    result = {}
    if design not in AVAILABLE_DESIGNS:
        return result

    target_names = ["00_clean.py", "01_main.py", "02_robustness.py", "03_output.py"]
    for i, target in enumerate(target_names):
        content = get_template(design, i)
        if content:
            result[target] = content

    return result


def detect_design(idea: dict) -> str:
    """Detect the research design from the idea metadata."""
    method = (idea.get("method", "") + " " + idea.get("identification_source", "")).lower()

    if any(k in method for k in [
        "dml", "double machine", "debiased machine", "causal forest",
        "generalized random forest", "grf", "causal tree", "cate",
        "heterogeneous treatment",
    ]):
        return "hte"
    elif any(k in method for k in ["rdd", "discontinuity", "threshold", "cutoff"]):
        return "rdd"
    elif any(k in method for k in ["stagger", "callaway", "did", "diff-in-diff", "event study"]):
        return "did"
    elif any(k in method for k in ["rct", "randomiz", "experiment", "treatment arm"]):
        return "rct"
    elif any(k in method for k in ["iv", "instrumental", "2sls"]):
        return "iv"
    else:
        return "unknown"
