"""Stage 4a — Strategy formalization (stub).

Checks if strategy_memo.md exists. If so, marks as completed.
The actual strategy work is handled in the unified Stage 4 intervention
(stage4_code.py).
"""

from datetime import datetime
from pathlib import Path

from ..state import save_state


def run(project_dir: Path, state: dict) -> dict:
    """Execute Stage 4a: check strategy exists, mark completed."""
    if state["stages"].get("stage4a", {}).get("status") == "completed":
        print("  [4a] Already completed — skipping.")
        return state

    strategy_dir = project_dir / "strategy"
    strategy_dir.mkdir(exist_ok=True)

    if (strategy_dir / "strategy_memo.md").exists():
        # Score identification quality based on the method's causal design
        ident_score = _score_identification(state)
        state["stages"]["stage4a"] = {
            "status": "completed",
            "strategy_dir": str(strategy_dir),
            "critic_score": ident_score,
            "completed_at": datetime.now().isoformat(),
        }
        save_state(project_dir, state)

    return state


def _score_identification(state: dict) -> int:
    """Score the identification strategy based on the causal design tier.

    First checks identification_level from Stage 2 (most reliable).
    Falls back to keyword matching on method string.

    Tier 1 (CAUSAL): DiD, IV, RDD, event study, RCT, synthetic control -> 75-90
    Tier 2 (PANEL-CAUSAL): TWFE + shock, Arellano-Bond, CRE -> 65-80
    Tier 3 (PANEL-DESCRIPTIVE): FE without identification -> 40-55
    Tier 4 (CROSS-SECTION): OLS, matching, decomposition -> 20-35
    """
    # First check: identification_level from Stage 2 (most reliable signal)
    selected = state["stages"].get("stage2_5", {}).get("selected_idea", {})
    id_level = selected.get("identification_level", "")
    id_score_raw = selected.get("identification", 0)

    if id_level == "A" or id_score_raw >= 5:
        return 90  # Level A: RCT, strong natural experiment
    elif id_level == "A" or id_score_raw == 4:
        return 80  # Strong Level A or Level B
    elif id_level == "B" or id_score_raw == 3:
        return 75  # Level B: dose variation

    # Second check: search method + title + RQ for RCT/experiment keywords
    method = ""
    strategy = state["stages"].get("stage3_5", {}).get("approved_strategy", {})
    if strategy:
        method = str(strategy.get("method", "")).lower()
    if not method:
        method = str(selected.get("method", "")).lower()
    if not method:
        validation = state["stages"].get("stage3", {}).get("result", {})
        method = str(validation.get("method", "")).lower()

    # Also check title and RQ for experiment keywords
    title = str(selected.get("title", "")).lower()
    rq = str(selected.get("research_question", "")).lower()
    all_text = method + " " + title + " " + rq

    # Tier 1: Strong causal identification
    tier1_keywords = [
        "did", "diff-in-diff", "difference-in-differences", "difference in differences",
        "event study", "event-study", "iv ", "iv,", "instrumental variable", "2sls",
        "rdd", "regression discontinuity", "rct", "randomized", "experiment",
        "synthetic control", "synth", "vignette", "survey experiment",
        "field experiment", "lab experiment", "natural experiment",
    ]
    # Tier 2: Panel-causal
    tier2_keywords = [
        "twfe", "two-way fixed effects", "arellano-bond", "arellano bond",
        "dynamic panel", "gmm", "correlated random effects", "cre",
        "individual fe", "individual fixed effects",
    ]
    # Tier 3: Panel-descriptive
    tier3_keywords = [
        "fixed effects", "panel fe", "within-estimator", "within estimator",
        "markov", "transition matrix", "survival", "hazard",
    ]
    # Tier 4: Cross-sectional
    tier4_keywords = [
        "ols", "wls", "oaxaca", "blinder", "quantile", "rif",
        "matching", "psm", "cem", "propensity", "heckman",
        "probit", "logit", "decomposition",
    ]

    for kw in tier1_keywords:
        if kw in all_text:
            return 80  # Strong causal

    for kw in tier2_keywords:
        if kw in all_text:
            return 70  # Panel-causal

    for kw in tier3_keywords:
        if kw in all_text:
            return 50  # Panel-descriptive

    for kw in tier4_keywords:
        if kw in all_text:
            return 30  # Cross-sectional

    return 40  # Unknown method — assume moderate
