"""Stage 3 — Granular Validation (8-step evaluation pipeline).

Each evaluation step gets its own Claude call with appropriate model and tool
permissions.  History accumulates in a master file so pivots see full context.

Loop logic:
  - Step 2 finds critique unfair  → re-run Step 1
  - Step 4 score < 6              → back to Step 3
  - Step 8 score < 6              → back to Step 3
  - Max 5 pivot iterations        → stall warning, mark STALLED
"""

import sys
from datetime import datetime
from pathlib import Path

from ..config import EVAL_REPO, get_profile
from ..claude_runner import run_claude
from ..json_utils import extract_json
from ..state import save_state


# ── Step definitions ─────────────────────────────────────────────────────────
# Combined steps to reduce Claude calls:
#   A  = Steps 1+2 (evaluate + review in one call)
#   B  = Steps 3+4 (pivot + re-evaluate, only on loop)
#   5  = Lit review (needs WebSearch — CLI only)
#   6  = Verify lit review (needs WebSearch — CLI only)
#   C  = Steps 7+8 (verdict + review in one call)
#
# Happy path: A → 5 → 6 → C  (4 calls instead of 8)

COMBINED_STEPS = {
    "A": {
        "prompts": ["prompt_ideas.txt", "review_eval_prompt.txt"],
        "profile": "stage3_eval",
        "tools": None,
        "suffix": "eval_and_review",
        "label": "Steps 1+2: Evaluate + Review",
    },
    "B": {
        "prompts": ["pivot_prompt.txt", "prompt_ideas.txt"],
        "profile": "stage3_eval",
        "tools": None,
        "suffix": "pivot_and_eval",
        "label": "Steps 3+4: Pivot + Re-evaluate",
    },
    "5": {
        "prompts": ["lit_review_prompt.txt"],
        "profile": "stage3_lit",
        "tools": None,
        "suffix": "lit_review",
        "label": "Step 5: Literature Review (Semantic Scholar)",
        "use_semantic_scholar": True,  # Use API instead of Claude web search
    },
    "6": {
        "prompts": ["verify_lit_review_prompt.txt"],
        "profile": "stage3_lit",
        "tools": None,
        "suffix": "verify_lit",
        "label": "Step 6: Verify Literature",
    },
    "C": {
        "prompts": ["final_verdict_prompt.txt", "review_final_verdict_prompt.txt"],
        "profile": "stage3_verdict",
        "tools": None,
        "suffix": "verdict_and_review",
        "label": "Steps 7+8: Verdict + Review",
    },
}


def _search_semantic_scholar(query: str, max_results: int = 10) -> list[dict]:
    """Search Semantic Scholar API for related papers.

    Returns verified, real papers (no hallucination risk).
    Free API, no key required, fast (~2s).
    """
    try:
        import requests
        r = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": query,
                "limit": max_results,
                "fields": "title,authors,year,venue,citationCount,abstract",
            },
            timeout=15,
        )
        r.raise_for_status()
        papers = r.json().get("data", [])
        results = []
        for p in papers:
            authors = ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:3])
            if len((p.get("authors") or [])) > 3:
                authors += " et al."
            results.append({
                "title": p.get("title", ""),
                "authors": authors,
                "year": p.get("year"),
                "venue": p.get("venue", ""),
                "citations": p.get("citationCount", 0),
                "abstract": (p.get("abstract") or "")[:200],
            })
        return results
    except Exception as e:
        print(f"  [semantic-scholar] Search failed: {e}")
        return []


def _read_prompt(filename: str) -> str:
    """Read a prompt template from the idea-evaluation-pipeline repo."""
    path = EVAL_REPO / filename
    if not path.exists():
        print(f"  [error] Prompt file not found: {path}")
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def _build_history(eval_dir: Path) -> str:
    """Concatenate all step output files into a chronological history string."""
    master = eval_dir / "master.md"
    if master.exists():
        return master.read_text(encoding="utf-8")
    return ""


def _append_master(eval_dir: Path, step_id: str, step_name: str, content: str):
    """Append a step's output to the master history file."""
    master = eval_dir / "master.md"
    header = f"\n\n{'='*60}\n## Step {step_id}: {step_name}\n{'='*60}\n\n"
    with open(master, "a", encoding="utf-8") as f:
        f.write(header + content)


def _extract_score(text: str) -> float | None:
    """Try to extract a numeric score from step output."""
    import re
    # Look for patterns like "Score: 7.5" or "score: 8/10" or "Final score: 6"
    patterns = [
        r'(?:final\s+)?score[:\s]+(\d+(?:\.\d+)?)\s*/\s*10',
        r'(?:final\s+)?score[:\s]+(\d+(?:\.\d+)?)',
        r'rating[:\s]+(\d+(?:\.\d+)?)\s*/\s*10',
        r'rating[:\s]+(\d+(?:\.\d+)?)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return float(m.group(1))
    # Try JSON
    data = extract_json(text)
    if data and isinstance(data, dict):
        for key in ("final_score", "score", "rating", "composite_score"):
            if key in data:
                try:
                    return float(data[key])
                except (TypeError, ValueError):
                    pass
    return None


def _check_review_disagrees(text: str) -> bool:
    """Check if Step 2 (review) disagrees with the evaluation."""
    import re
    return bool(re.search(r'\bDISAGREE\b', text, re.IGNORECASE))


# ── Main runner ──────────────────────────────────────────────────────────────

def run(project_dir: Path, state: dict) -> dict:
    """Execute Stage 3: granular 8-step evaluation with per-step Claude calls."""
    stage2 = state["stages"].get("stage2", {})
    top_ideas = stage2.get("top_ideas", [])
    stage1 = state["stages"].get("stage1", {})

    # Use Stage 2.5 selection if available
    stage2_5 = state["stages"].get("stage2_5", {})
    selected_idea = stage2_5.get("selected_idea")

    if not top_ideas and not selected_idea:
        ideation_file = project_dir / "stage2_ideation.md"
        if ideation_file.exists():
            content = ideation_file.read_text(encoding="utf-8")
            ideas_data = extract_json(content)
            if ideas_data and "top_ideas" in ideas_data:
                top_ideas = ideas_data["top_ideas"]

    if not top_ideas and not selected_idea:
        print("  [error] No ideas found from Stage 2. Run Stage 2 first.")
        sys.exit(1)

    best_idea = selected_idea if selected_idea else top_ideas[0]

    # Format the idea text

    # Build data structure context for identification assessment
    data_profile = stage1.get("data_profile", {})
    data_structure = data_profile.get("structure", "unknown")
    panel_details = data_profile.get("panel_details", {})
    time_values = panel_details.get("time_values", [])
    wide_panel = data_profile.get("wide_panel")

    # Detect pre-treatment availability
    earliest_year = None
    if time_values:
        try:
            earliest_year = min(int(y) for y in time_values if str(y).isdigit())
        except (ValueError, TypeError):
            pass
    if not earliest_year and wide_panel:
        suffixes = wide_panel.get("year_suffixes", [])
        if suffixes:
            try:
                raw = min(int(s) for s in suffixes)
                earliest_year = 2000 + raw if raw < 100 else raw
            except (ValueError, TypeError):
                pass

    pre_treatment_note = ""
    if earliest_year and earliest_year >= 2020:
        pre_treatment_note = (
            "\n*** DATA LIMITATION: No pre-2020 data available. "
            "Parallel trends CANNOT be tested. This caps the score. ***\n"
        )
    elif earliest_year and earliest_year >= 2018:
        n_pre = 2020 - earliest_year
        pre_treatment_note = (
            f"\nDATA NOTE: {n_pre} pre-treatment year(s) available ({earliest_year}-2019). "
            f"Pre-trend testing is {'possible but limited' if n_pre < 3 else 'feasible'}.\n"
        )

    replication_context = ""
    if stage2.get("mode") == "replication":
        chosen_paper = stage2.get("chosen_paper", {})
        replication_context = f"""
PAPER MODE: Replication / HTE extension

BASE PAPER:
Title: {chosen_paper.get('title', 'N/A')}
Authors: {chosen_paper.get('authors', 'N/A')}
Year: {chosen_paper.get('year', 'N/A')}
Venue: {chosen_paper.get('venue', 'N/A')}
URL: {chosen_paper.get('url', 'N/A')}

REPLICATION-SPECIFIC VALIDATION:
You MUST evaluate whether:
1. The original paper's estimand is clear enough to replicate.
2. The available data can reproduce the original sample and baseline ATE.
3. The HTE extension is connected to the original paper rather than a new unrelated project.
4. Baseline ATE replication happens before CATE/heterogeneity claims.
5. Overlap, treatment variation, sample size, and pre-treatment covariates are sufficient for HTE.
"""

    idea_text = f"""RESEARCH IDEA SUBMISSION
========================

{replication_context}

IDEA TITLE:
{best_idea.get('title', 'Untitled')}

PAPER TYPE: Empirical

RESEARCH QUESTION:
{best_idea.get('research_question', 'N/A')}

HYPOTHESIS / MECHANISM:
{best_idea.get('pitch', 'N/A')}

IDENTIFICATION STRATEGY:
{best_idea.get('method', 'N/A')} — {best_idea.get('first_experiment', 'N/A')}

DATA SOURCES:
{chr(10).join('- ' + ds for ds in best_idea.get('data_sources', ['N/A']))}

DATA STRUCTURE: {data_structure}
TIME COVERAGE: {time_values if time_values else 'unknown'}
{pre_treatment_note}

*** IDENTIFICATION ASSESSMENT (MANDATORY) ***
You MUST explicitly evaluate the following in your assessment:

1. SOURCE OF EXOGENOUS VARIATION: What is the specific source of identifying
   variation? (e.g., "policy reform in year X", "geographic discontinuity at
   threshold Y", "instrument Z correlated with treatment but not outcome").
   Is it clearly stated? Is it plausible?

2. IDENTIFICATION THREATS: What are the main threats to identification?
   (e.g., selection bias, reverse causality, omitted variables, violation of
   exclusion restriction, non-parallel trends).

3. PRE-TRENDS: Can parallel trends be tested with the available data?
   If not, how does this affect credibility?

4. IDENTIFICATION TIER: Classify the identification strategy:
   - Tier 1 (STRONG): RCT, natural experiment, sharp RDD, DiD with pre-trends
   - Tier 2 (GOOD): IV with strong first stage, fuzzy RDD, DiD without pre-trends
   - Tier 3 (MODERATE): Panel FE exploiting within-variation, CRE
   - Tier 4 (WEAK): Cross-sectional matching, OLS with controls, decompositions

Include these assessments in your evaluation and factor them into your score.
A Tier 4 identification strategy should not score above 6/10 regardless of novelty.
"""

    # Set up evaluation directory
    eval_dir = project_dir / "evaluation"
    eval_dir.mkdir(exist_ok=True)
    idea_file = eval_dir / "idea.txt"
    idea_file.write_text(idea_text, encoding="utf-8")
    print(f"  [saved] {idea_file}")

    # ── Run combined-step pipeline (4 calls happy path instead of 8) ─────
    # Sequence: A(1+2) → 5 → 6 → C(7+8)
    # On loop:  B(3+4) replaces A, then continues 5 → 6 → C
    STEP_SEQUENCE = ["A", "5", "6", "C"]

    pivot_count = 0
    step_idx = 0
    final_score = None
    final_status = "UNKNOWN"
    response = ""

    # Cache history to avoid re-reading master.md on every step
    _history_cache = {"text": _build_history(eval_dir), "dirty": False}

    def _run_combined_step(step_key: str) -> str:
        """Run a combined step, merging prompts if needed."""
        step_def = COMBINED_STEPS[step_key]
        prompts = [_read_prompt(pf) for pf in step_def["prompts"]]
        if _history_cache["dirty"]:
            _history_cache["text"] = _build_history(eval_dir)
            _history_cache["dirty"] = False
        history = _history_cache["text"]
        version = f"_v{pivot_count + 1}" if pivot_count > 0 else ""

        if step_key == "A":
            # Steps 1+2: evaluate idea + self-review in one call
            full_prompt = (
                f"{prompts[0]}\n\n--- IDEA ---\n{idea_text}\n\n"
                f"After your evaluation, also perform the following review:\n\n"
                f"{prompts[1]}\n\n"
                f"Clearly separate your EVALUATION and REVIEW sections. "
                f"If the review DISAGREES with the evaluation, end with: DISAGREE."
            )
        elif step_key == "B":
            # Steps 3+4: pivot + re-evaluate in one call
            full_prompt = (
                f"{prompts[0]}\n\n--- IDEA ---\n{idea_text}\n\n"
                f"--- FULL HISTORY ---\n{history}\n\n"
                f"After the pivot, immediately re-evaluate:\n\n"
                f"{prompts[1]}\n\n"
                f"End with a score from 0-10."
            )
        elif step_key == "5":
            # Use Semantic Scholar API for real papers instead of Claude's memory
            idea_title = best_idea.get("title", "")
            idea_rq = best_idea.get("research_question", "")
            search_query = f"{idea_title} {idea_rq}"[:200]

            print(f"  [semantic-scholar] Searching for related papers...")
            ss_papers = _search_semantic_scholar(search_query, max_results=10)

            if ss_papers:
                papers_text = "\n".join(
                    f"  {i+1}. {p['authors']} ({p['year']}). \"{p['title']}\". "
                    f"{p['venue']}. Citations: {p['citations']}."
                    f"\n     Abstract: {p['abstract']}"
                    for i, p in enumerate(ss_papers)
                )
                print(f"  [semantic-scholar] Found {len(ss_papers)} real papers")
            else:
                papers_text = "(Semantic Scholar search returned no results)"

            full_prompt = (
                f"{prompts[0]}\n\n--- IDEA ---\n{idea_text}\n\n"
                f"--- RELATED PAPERS (from Semantic Scholar — these are REAL, verified papers) ---\n"
                f"{papers_text}\n\n"
                f"Using ONLY the papers listed above (they are verified to exist), "
                f"assess how this idea positions relative to existing literature. "
                f"Do NOT invent or hallucinate any additional papers."
            )
        elif step_key == "6":
            lit_file = eval_dir / "stepA_eval_and_review.md"
            if not lit_file.exists():
                lit_file = eval_dir / "step5_lit_review.md"
            lit_text = lit_file.read_text(encoding="utf-8") if lit_file.exists() else history
            full_prompt = f"{prompts[0]}\n\n--- LITERATURE REVIEW TO VERIFY ---\n{lit_text}"
        elif step_key == "C":
            # Steps 7+8: verdict + review in one call
            full_prompt = (
                f"{prompts[0]}\n\n--- FULL HISTORY ---\n{history}\n\n"
                f"After your verdict, also perform the following review:\n\n"
                f"{prompts[1]}\n\n"
                f"End with a final score from 0-10."
            )
        else:
            full_prompt = f"{prompts[0]}\n\n--- FULL HISTORY ---\n{history}"

        out_file = eval_dir / f"step{step_key}_{step_def['suffix']}{version}.md"
        print(f"\n  -- {step_def['label']} --")
        prof = get_profile(step_def["profile"])
        resp = run_claude(
            full_prompt,
            model=prof["model"],
            effort=prof["effort"],
            allowed_tools=step_def["tools"],
            cwd=str(eval_dir),
            output_file=out_file,
        )
        _append_master(eval_dir, step_key, step_def["suffix"], resp)
        _history_cache["dirty"] = True
        return resp

    while step_idx < len(STEP_SEQUENCE):
        step_key = STEP_SEQUENCE[step_idx]
        response = _run_combined_step(step_key)

        # ── Decision logic ───────────────────────────────────────────────
        if step_key == "A":
            if _check_review_disagrees(response):
                print("  [loop] Review disagrees -> re-running evaluation")
                continue  # retry step A

        elif step_key == "B":
            score = _extract_score(response)
            final_score = score
            # No more pivot loops — one attempt is enough.
            # The real quality gates are Stage 3.3 (data feasibility)
            # and Stage 6 (peer review).

        elif step_key == "C":
            score = _extract_score(response)
            final_score = score
            # Pass threshold: 6+ (was 8, which almost never passed)
            # Ideas with Level A/B identification and score >= 6 proceed.
            # Ideas below 6 get one pivot attempt, then proceed anyway.
            if score is not None and score < 6 and pivot_count == 0:
                pivot_count += 1
                print(f"  [loop] Final score {score} < 6 -> one pivot attempt")
                STEP_SEQUENCE[0] = "B"
                step_idx = 0
                continue
            elif score is not None and score >= 6:
                final_status = "APPROVED"
            else:
                # Score < 6 after pivot — check identification level before proceeding
                id_level = best_idea.get("identification_level", "").upper()
                id_score = best_idea.get("identification", 0)

                # Hard reject: Tier 4 / Level C designs with score < 5
                if (score is not None and score < 5 and
                        (id_level in ("C", "D") or id_score <= 1)):
                    final_status = "REJECTED_WEAK_ID"
                    print(f"  [REJECT] Score {score} < 5 with Level {id_level} identification.")
                    print(f"  This design has no credible source of exogenous variation.")
                    print(f"  Returning to Stage 2.5 to select a different idea.")
                elif (score is not None and score < 4):
                    final_status = "REJECTED_WEAK_ID"
                    print(f"  [REJECT] Score {score} < 4. Design is too weak to proceed.")
                else:
                    final_status = "APPROVED_WITH_CAVEATS"
                    print(f"  [ok] Score {score} is below 6 but identification "
                          f"(level={id_level or '?'}) is salvageable — "
                          f"Stage 3.3 will validate against real data.")

        step_idx += 1

    # ── Extract structured result from last step ─────────────────────────
    result_data = extract_json(response) or {}
    if final_score is not None:
        result_data["final_score"] = final_score
    result_data["status"] = final_status
    result_data["iterations"] = pivot_count + 1
    result_data["title"] = best_idea.get("title", "Untitled")

    # Try to pull refined question/method from pivots
    if "refined_question" not in result_data:
        result_data["refined_question"] = best_idea.get("research_question", "")
    if "method" not in result_data:
        result_data["method"] = best_idea.get("method", "")
    if "data_sources" not in result_data:
        result_data["data_sources"] = best_idea.get("data_sources", [])

    state["stages"]["stage3"] = {
        "status": "completed",
        "output_file": str(eval_dir / "master.md"),
        "idea_file": str(idea_file),
        "result": result_data,
        "completed_at": datetime.now().isoformat(),
    }

    state["current_stage"] = 3
    save_state(project_dir, state)

    print(f"\n  [ok] Evaluation complete: {final_status} "
          f"(score: {final_score}, iterations: {pivot_count + 1})")

    return state
