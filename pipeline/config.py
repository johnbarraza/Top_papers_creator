"""Centralized paths, constants, and timeouts for the pipeline."""

from pathlib import Path

# ── Directory layout ─────────────────────────────────────────────────────────
PAPERS_HQ     = Path(__file__).resolve().parent.parent
PIPELINE_ROOT = PAPERS_HQ.parent

SEARCH_REPO   = PIPELINE_ROOT / "search-repositories"
JUNSHI_REPO   = PIPELINE_ROOT / "research-junshi"
EVAL_REPO     = PAPERS_HQ / "idea-evaluation-pipeline"
CLO_AUTHOR    = PAPERS_HQ / "clo-author"

# ── Stage constants ──────────────────────────────────────────────────────────
MAX_STAGE3_PIVOTS   = 2      # Stage 3: max pivot iterations before stall warning
MAX_RR_ROUNDS       = 3      # Stage 6: max revise-and-resubmit rounds
MAX_CODE_RETRIES    = 1      # Stage 4b: max error→fix→retry cycles
MAX_CODE_REVIEW_ROUNDS = 3  # Stage 4.7: max code review correction iterations
MAX_STAGE7_IMPROVE  = 3      # Stage 7: max improvement rounds
CRITIC_GATE         = 70     # Minimum critic score to pass a quality gate
SUBMISSION_GATE     = 85     # Final aggregate score for submission
COMPONENT_MIN       = 70     # Every component must be >= this

# Stage 6: Peer Review decision thresholds (based on avg referee score)
ACCEPT_GATE         = 75     # avg >= 75 and no fatal issues -> ACCEPT
MINOR_REV_GATE      = 60     # avg >= 60 -> MINOR_REVISIONS (no re-review)
REJECT_FLOOR        = 40     # avg < 40 with fatal issues -> REJECT

# Backwards compatibility aliases
MAX_EVAL_LOOPS = MAX_STAGE3_PIVOTS

# ── Claude Code CLI defaults ─────────────────────────────────────────────────
# No API key needed — uses `claude -p` (headless mode) via subprocess.
import os
CLAUDE_TIMEOUT      = int(os.environ.get("PIPELINE_CLAUDE_TIMEOUT", 600))
PYTHON_TIMEOUT      = int(os.environ.get("PIPELINE_PYTHON_TIMEOUT", 600))
MAX_PARALLEL_AGENTS = int(os.environ.get("PIPELINE_MAX_PARALLEL", 2))

# ── Speed profiles per stage ─────────────────────────────────────────────────
# model: "sonnet" (fast+good), "haiku" (fastest), "opus" (best, slow)
# effort: advisory hint only — Claude Code CLI manages its own reasoning depth
STAGE_PROFILES = {
    # ── Active profiles (used in run_claude calls) ──
    "stage1":           {"model": "sonnet", "effort": "medium"},   # Discovery — dataset search (Path A)
    "stage1_b":         {"model": "haiku",  "effort": "medium"},   # Discovery — data profiling (Path B)
    "stage2":           {"model": "sonnet", "effort": "medium"},   # Ideation
    "stage3_eval":      {"model": "sonnet", "effort": "medium"},   # Validation steps 1-4
    "stage3_lit":       {"model": "sonnet", "effort": "medium"},   # Validation steps 5-6 (web search)
    "stage3_verdict":   {"model": "sonnet", "effort": "high"},     # Validation step 7 (final verdict)
    "stage3_3_test":    {"model": "sonnet", "effort": "medium"},   # Quick empirical validation
    "stage3_5_justify": {"model": "sonnet", "effort": "medium"},   # External source justification
    "stage3_5_merge":   {"model": "sonnet", "effort": "medium"},   # Merge feasibility assessment
    "stage4_critic":    {"model": "sonnet", "effort": "medium"},   # Critic reviews + consistency checks
    "stage4_7_review":  {"model": "sonnet", "effort": "high"},     # Code review (2 agents)
    "stage4_7_fix":     {"model": "sonnet", "effort": "medium"},   # Code correction
    "stage6_consistency": {"model": "sonnet", "effort": "medium"}, # Pre-review consistency check
    "stage6_referee":   {"model": "sonnet", "effort": "high"},     # 6-agent review
    "stage7_targeting": {"model": "sonnet", "effort": "low"},      # Journal targeting
    # ── Manual intervention stages (profile used by claude agents) ──
    "stage4_strategy":  {"model": "sonnet", "effort": "medium"},   # Strategy memo (agent)
    "stage4_code":      {"model": "sonnet", "effort": "medium"},   # Code generation (agent)
    "stage4_fix":       {"model": "sonnet", "effort": "medium"},   # Error fixes (agent)
    "stage5_write":     {"model": "sonnet", "effort": "high"},     # Paper drafting (agent)
    "stage5_critic":    {"model": "sonnet", "effort": "high"},     # Writer-critic (agent)
}

def get_profile(key: str) -> dict:
    """Return model + effort for a pipeline step."""
    return STAGE_PROFILES.get(key, {"model": "sonnet", "effort": "medium"})

# ── Quality weights (clo-author v2) ─────────────────────────────────────────
QUALITY_WEIGHTS = {
    "identification": 0.30,
    "code":           0.20,
    "paper":          0.25,
    "polish":         0.15,
    "replication":    0.10,
}

# ── All stages in execution order ────────────────────────────────────────────
STAGE_ORDER = [1, 1.5, 2, 2.5, 3.3, 3, 3.5, 3.7, 4, 4.5, 4.7, 5, 6, 7]

STAGE_NAMES = {
    1:   "Discovery",
    1.5: "Data Loading",
    2:   "Ideation",
    2.5: "Idea Selection (human)",
    3:   "Validation",
    3.3: "Quick Empirical Test",
    3.5: "Strategy Review (human)",
    3.7: "Referee Preview",
    4:   "Strategy & Code",
    4.5: "Data Audit",
    4.7: "Code Review",
    5:   "Writing",
    6:   "Peer Review (6-agent)",
    7:   "Submission",
}
