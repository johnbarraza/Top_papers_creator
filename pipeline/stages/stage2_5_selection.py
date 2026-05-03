"""Stage 2.5 — Human Idea Selection.

Presents the top 3 ideas from Stage 2 and lets the researcher SELECT one,
COMBINE two, or REJECT ALL (which loops back to Stage 2).
"""

import sys
from datetime import datetime
from pathlib import Path

from ..json_utils import extract_json
from ..state import save_state
from ..human_checkpoint import idea_selection


def run(project_dir: Path, state: dict) -> dict:
    """Execute Stage 2.5: human idea selection checkpoint."""
    stage2 = state["stages"].get("stage2", {})
    top_ideas = stage2.get("top_ideas", [])

    if not top_ideas:
        ideation_file = project_dir / "stage2_ideation.md"
        if ideation_file.exists():
            content = ideation_file.read_text(encoding="utf-8")
            ideas_data = extract_json(content)
            if ideas_data and "top_ideas" in ideas_data:
                top_ideas = ideas_data["top_ideas"]

    if not top_ideas:
        print("  [error] No ideas found from Stage 2. Run Stage 2 first.")
        sys.exit(1)

    # Save state before prompting (Ctrl-C safe)
    save_state(project_dir, state)

    result = idea_selection(top_ideas)

    state["stages"]["stage2_5"] = {
        "status": "completed",
        "action": result["action"],
        "completed_at": datetime.now().isoformat(),
    }

    if result["selected_idea"]:
        state["stages"]["stage2_5"]["selected_idea"] = result["selected_idea"]

    state["current_stage"] = 2.5
    save_state(project_dir, state)

    if result["action"] == "REJECT":
        print("  [loop] Returning to Stage 2 for new ideas.")

    return state
