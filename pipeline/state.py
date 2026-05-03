"""Pipeline state management — load, save, and query project state."""

import json
import os
from datetime import datetime
from pathlib import Path

from .config import PAPERS_HQ


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write `content` to `path` atomically: write to a sibling tempfile,
    then `os.replace` to the final name.  This guarantees that a concurrent
    reader either sees the previous good content or the new full content,
    never a half-written file.  Critical for state and intervention JSON
    files that block the entire pipeline if they end up truncated.
    """
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding=encoding)
    os.replace(tmp, path)


def ensure_project_dir(project_name: str) -> Path:
    """Create and return the project workspace inside papers-HQ/projects/."""
    project_dir = PAPERS_HQ / "projects" / project_name
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


def load_state(project_dir: Path) -> dict:
    """Load pipeline state for a project, or return a fresh skeleton.

    If the state file exists but is corrupt (e.g. truncated by a Ctrl-C
    during a non-atomic save in an older pipeline version), fall back to
    a fresh skeleton instead of crashing the entire pipeline. The corrupt
    file is renamed to `pipeline_state.json.corrupt-<timestamp>` so it
    can be inspected after the fact.
    """
    state_file = project_dir / "pipeline_state.json"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            corrupt_path = state_file.with_name(
                f"pipeline_state.json.corrupt-{ts}"
            )
            try:
                state_file.rename(corrupt_path)
            except OSError:
                pass
            print(
                f"[state] WARNING: pipeline_state.json was corrupt ({exc}). "
                f"Quarantined to {corrupt_path.name}; starting fresh skeleton."
            )
    return {
        "project": project_dir.name,
        "created_at": datetime.now().isoformat(),
        "current_stage": 0,
        "stages": {},
    }


def save_state(project_dir: Path, state: dict):
    """Persist pipeline state to disk.  Called before every human checkpoint
    so that Ctrl-C never loses progress.

    Uses an atomic write (tempfile + os.replace) so a process kill
    mid-save never leaves the JSON file truncated.
    """
    state["updated_at"] = datetime.now().isoformat()
    atomic_write_text(
        project_dir / "pipeline_state.json",
        json.dumps(state, indent=2, ensure_ascii=False),
    )


def mark_stage(state: dict, stage_key: str, *, status: str = "completed", **extra) -> dict:
    """Helper to mark a stage as completed (or failed/skipped) and attach extra metadata."""
    entry = {"status": status, "completed_at": datetime.now().isoformat()}
    entry.update(extra)
    state["stages"][stage_key] = entry
    return state
