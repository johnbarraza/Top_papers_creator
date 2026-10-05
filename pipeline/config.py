"""Centralized paths, constants, and timeouts for the pipeline."""

from pathlib import Path

# ── Directory layout ─────────────────────────────────────────────────────────
PAPERS_HQ     = Path(__file__).resolve().parent.parent  # Top_papers_creator/

EVAL_REPO     = PAPERS_HQ / "idea-evaluation-pipeline"
CLO_AUTHOR    = PAPERS_HQ / "clo-author"

# External companion repos (clone alongside Top_papers_creator/ if needed)
# These are NOT required for the pipeline to run — only Stage 1 optional enrichment.
# SEARCH_REPO   = PAPERS_HQ.parent / "search-repositories"
# JUNSHI_REPO   = PAPERS_HQ.parent / "research-junshi"

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

# ── paperdl integration ──────────────────────────────────────────────────────
# "auto": use paperdl if installed, fall back to Semantic Scholar
# "on":   require paperdl — fail loudly if not installed
# "off":  skip paperdl entirely, use only Semantic Scholar
# Can be overridden via env: PIPELINE_PAPERDL=on|off|auto
import os
PAPERDL_MODE = os.environ.get("PIPELINE_PAPERDL", "auto")

# ── NotebookLM integration ───────────────────────────────────────────────────
# "auto": offer NotebookLM at checkpoints, require human confirmation
# "on":   same as auto, but fail if notebooklm-py not installed/logged in
# "off":  skip NotebookLM entirely
# Can be overridden via env: PIPELINE_NOTEBOOKLM=on|off|auto
NOTEBOOKLM_MODE = os.environ.get("PIPELINE_NOTEBOOKLM", "auto")

# ── Claude Code CLI defaults ─────────────────────────────────────────────────
# No API key needed — uses `claude -p` (headless mode) via subprocess.
CLAUDE_TIMEOUT      = int(os.environ.get("PIPELINE_CLAUDE_TIMEOUT", 600))
PYTHON_TIMEOUT      = int(os.environ.get("PIPELINE_PYTHON_TIMEOUT", 600))
MAX_PARALLEL_AGENTS = int(os.environ.get("PIPELINE_MAX_PARALLEL", 2))

# ── Models ───────────────────────────────────────────────────────────────────
# Stage profiles name a TIER ("opus" | "sonnet" | "haiku" | "fable"); the tier
# resolves to a pinned model id so runs are reproducible. Override per tier
# with PIPELINE_MODEL_<TIER>=<id>. When ANTHROPIC_BASE_URL points to another
# backend (e.g. DeepSeek) and no override is set, the bare alias is passed so
# ANTHROPIC_DEFAULT_<TIER>_MODEL mappings keep working.
MODEL_IDS = {
    "opus":   "claude-opus-5-5",     # deep reasoning: verdicts, referees, model design
    "sonnet": "claude-sonnet-5-5",   # default workhorse
    "haiku":  "claude-haiku-4-5",    # cheap batch enrichment / profiling
    "fable":  "claude-fable-5-1",    # most capable; opt-in via PIPELINE_MODEL_OPUS
}


def resolve_model(tier: str | None) -> str | None:
    """Map a profile tier to the model id passed to `claude --model`."""
    if not tier:
        return None
    override = os.environ.get(f"PIPELINE_MODEL_{tier.upper()}")
    if override:
        return override
    if tier not in MODEL_IDS:
        return tier                       # already a full model id
    if os.environ.get("ANTHROPIC_BASE_URL"):
        return tier                       # third-party backend: keep alias mapping
    return MODEL_IDS[tier]


# ── Speed profiles per stage ─────────────────────────────────────────────────
# model: tier from MODEL_IDS. effort: low | medium | high | xhigh | max
# (passed to `claude --effort`; Opus 5.5 defaults to medium, so set it).
STAGE_PROFILES = {
    # ── Active profiles (used in run_claude calls) ──
    "stage1":           {"model": "sonnet", "effort": "medium"},   # Discovery — dataset search (Path A)
    "stage1_b":         {"model": "haiku",  "effort": "medium"},   # Discovery — data profiling (Path B)
    "stage2":           {"model": "sonnet", "effort": "high"},     # Ideation
    "stage3_eval":      {"model": "sonnet", "effort": "medium"},   # Validation steps 1-4
    "stage3_lit":       {"model": "sonnet", "effort": "medium"},   # Validation steps 5-6 (web search)
    "stage3_verdict":   {"model": "opus",   "effort": "high"},     # Validation step 7 (final verdict)
    "stage3_3_test":    {"model": "sonnet", "effort": "medium"},   # Quick empirical validation
    "stage3_5_justify": {"model": "sonnet", "effort": "medium"},   # External source justification
    "stage3_5_merge":   {"model": "sonnet", "effort": "medium"},   # Merge feasibility assessment
    "stage4_critic":    {"model": "sonnet", "effort": "high"},     # Critic reviews + consistency checks
    "stage4_7_review":  {"model": "opus",   "effort": "high"},     # Code review (2 agents)
    "stage4_7_fix":     {"model": "sonnet", "effort": "high"},     # Code correction
    "stage6_consistency": {"model": "sonnet", "effort": "medium"}, # Pre-review consistency check
    "stage6_referee":   {"model": "sonnet", "effort": "high"},     # 6-agent review (agents 1-5)
    "stage6_contribution": {"model": "opus", "effort": "high"},    # Agent 6 (contribution referee)
    "stage7_targeting": {"model": "sonnet", "effort": "low"},      # Journal targeting
    # ── Macro track ──
    "macro_discovery":  {"model": "sonnet", "effort": "medium"},   # Seed papers + calibration data plan
    "macro_ideation":   {"model": "opus",   "effort": "high"},     # Model-based ideas
    "macro_referee":    {"model": "opus",   "effort": "high"},     # Theory/computation referee previews
    # ── Optional Lean formalization (Stage 5.5) ──
    "lean_formalize":   {"model": "opus",   "effort": "xhigh"},    # Proof-intensive, long-running
    # ── Manual intervention stages (profile used by claude agents) ──
    "stage4_strategy":  {"model": "sonnet", "effort": "high"},     # Strategy memo (agent)
    "stage4_code":      {"model": "sonnet", "effort": "high"},     # Code generation (agent)
    "stage4_fix":       {"model": "sonnet", "effort": "high"},     # Error fixes (agent)
    "stage5_write":     {"model": "opus",   "effort": "high"},     # Paper drafting (agent)
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
STAGE_ORDER = [1, 1.5, 2, 2.5, 3.3, 3, 3.5, 3.7, 4, 4.5, 4.7, 5, 5.5, 6, 7]

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
    5.5: "Lean Formalization (optional)",
    6:   "Peer Review (6-agent)",
    7:   "Submission",
}

# ── Paper types ──────────────────────────────────────────────────────────────
# "empirical": identification-first applied micro (DiD/IV/RDD/RCT/HTE).
# "macro":     quantitative macro / general equilibrium (HA, HANK, TANK, RANK).
PAPER_TYPES = ("empirical", "macro")
DEFAULT_PAPER_TYPE = os.environ.get("PIPELINE_PAPER_TYPE", "empirical")

# Stage names that change meaning in the macro track
MACRO_STAGE_NAMES = {
    1:   "Discovery (seed papers + calibration data plan)",
    1.5: "Calibration Data",
    2:   "Ideation (model-based)",
    3:   "Validation (theory + quantitative discipline)",
    3.3: "Model Smoke Test",
    3.5: "Model Specification Review (human)",
    3.7: "Referee Preview (macro)",
    4:   "Model, Calibration & Solution Code",
    4.5: "Equilibrium & Calibration Audit",
}

# ── Optional Lean formalization (Stage 5.5) ─────────────────────────────────
# "off" (default) | "on". Needs a local AppliedModelingLib clone
# (https://gargnikhil.com/AppliedModelingLib/), set via --lean-lib or env.
LEAN_MODE = os.environ.get("PIPELINE_LEAN", "off")
LEAN_LIB_PATH = os.environ.get("PIPELINE_LEAN_LIB", "")
# Command template run from the library root; {prompt_file} is replaced by the
# path of the task prompt. Empty = Claude Code headless with the
# lean_formalize profile. Any other coding-agent CLI can be plugged in.
LEAN_AGENT_CMD = os.environ.get("PIPELINE_LEAN_AGENT_CMD", "")
LEAN_TIMEOUT = int(os.environ.get("PIPELINE_LEAN_TIMEOUT", 6 * 60 * 60))
