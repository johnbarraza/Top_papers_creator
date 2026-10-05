"""Stage 5.5 — Optional Lean formalization (AppliedModelingLib workflow).

Off by default (--lean off). When enabled it:
  1. writes the formalization task (paper source + paper folder name +
     the propositions to target) to quality_reports/lean_task.md;
  2. runs the coding agent from the root of a local AppliedModelingLib
     clone — either you run it yourself (--lean manual: the pipeline waits
     on the usual intervention signal) or the pipeline runs the command in
     PIPELINE_LEAN_AGENT_CMD (--lean auto);
  3. runs the paper-scoped check BEFORE copying
     (scripts/paper_contribution.py check <Folder> --fast) and records the
     result in quality_reports/lean_check.md;
  4. copies papers/<Folder>/ exactly as generated into <project>/lean/
     (and optionally into --lean-export <repo>/lean/). Nothing is written
     inside lean/: partial results and audit/status artifacts are kept as is.

A failed or partial formalization never stops the pipeline; it is reported
with the precise blocker so Stage 5/6 can state it honestly.
"""

import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from ..config import LEAN_AGENT_CMD, LEAN_LIB_PATH, LEAN_MODE, LEAN_TIMEOUT, get_profile
from ..state import save_state

WORKFLOW_URL = "https://gargnikhil.com/AppliedModelingLib/"
EXAMPLE_URL = "https://github.com/alexanderquispe/QX26AgenticDelegation"


def _cfg(state: dict, key: str, default=""):
    return state.get("config", {}).get(key) or default


def _default_folder(state: dict) -> str:
    """AppliedModelingLib-style folder name: <Initials><YY><TitleWords>."""
    title = (state["stages"].get("stage2_5", {}).get("selected_idea", {}) or {}).get("title") \
        or state.get("project", "Paper")
    words = [w for w in re.findall(r"[A-Za-z0-9]+", title)
             if w.lower() not in {"the", "a", "an", "of", "and", "in", "on", "for", "with"}]
    camel = "".join(w[:1].upper() + w[1:] for w in words[:3]) or "Paper"
    initials = _cfg(state, "lean_initials", "PH")
    return f"{initials}{datetime.now():%y}{camel}"


def _propositions(project_dir: Path, state: dict) -> list[str]:
    spec = state["stages"].get("stage3_5", {}).get("approved_strategy") or {}
    props = list(spec.get("analytical_results") or [])
    idea = state["stages"].get("stage2_5", {}).get("selected_idea", {}) or {}
    props += [p for p in idea.get("analytical_results", []) if p not in props]
    return props


def _task_prompt(source: str, folder: str, props: list[str]) -> str:
    targets = "\n".join(f"  - {p}" for p in props) or "  - (use the paper's own theorem inventory)"
    return (
        f"Please formalize {source} using the paper-formalization skill and workflow in this "
        f"repository.\nUse {folder} as the paper folder.\n\n"
        "Follow the workflow end to end: source pinning, theorem inventory, source-facing Spec "
        "declarations, proof files, audits, dependency graph, and an honest status report.\n"
        "Priority targets (analytical results of the paper):\n"
        f"{targets}\n\n"
        "Rules: keep incomplete or partial results and every audit/status artifact; never hide "
        "unproved statements; report the precise blocker for anything not formalized.\n"
        f"Workflow reference: {WORKFLOW_URL}\nWorked example (different paper): {EXAMPLE_URL}\n"
    )


def _paper_source(project_dir: Path, state: dict) -> str:
    src = _cfg(state, "lean_source")
    if src:
        return src
    for rel in ("paper/main.pdf", "paper/main.tex"):
        if (project_dir / rel).exists():
            return str((project_dir / rel).resolve())
    return ""


def _run_check(lib: Path, folder: str) -> tuple[int, str]:
    cmd = [sys.executable, "scripts/paper_contribution.py", "check", folder, "--fast"]
    try:
        r = subprocess.run(cmd, cwd=lib, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=3600)
        return r.returncode, (r.stdout + "\n" + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, f"check could not run: {e}"


def _finish(project_dir: Path, state: dict, info: dict) -> dict:
    info.setdefault("completed_at", datetime.now().isoformat())
    state["stages"]["stage5_5"] = info
    save_state(project_dir, state)
    return state


def run(project_dir: Path, state: dict) -> dict:
    mode = _cfg(state, "lean", LEAN_MODE)
    if mode not in ("manual", "auto"):
        print("  [5.5] Lean formalization disabled (--lean manual|auto to enable).")
        return _finish(project_dir, state, {"status": "skipped", "reason": "disabled"})

    qr = project_dir / "quality_reports"
    qr.mkdir(exist_ok=True)
    lib = Path(_cfg(state, "lean_lib", LEAN_LIB_PATH) or ".").expanduser()
    if not (lib / "scripts" / "paper_contribution.py").exists():
        msg = (f"AppliedModelingLib clone not found at '{lib}'. Clone it (see {WORKFLOW_URL}; "
               "if you cloned it before, `git pull` inside the clone) and pass --lean-lib PATH.")
        print(f"  [5.5] {msg}")
        (qr / "lean_status.md").write_text(f"# Lean formalization: SKIPPED\n\n{msg}\n",
                                           encoding="utf-8")
        return _finish(project_dir, state, {"status": "skipped", "reason": msg})

    source = _paper_source(project_dir, state)
    if not source:
        msg = "No paper source: pass --lean-source <arXiv URL or PDF> or run Stage 5 first."
        print(f"  [5.5] {msg}")
        return _finish(project_dir, state, {"status": "skipped", "reason": msg})

    folder = _cfg(state, "lean_folder") or _default_folder(state)
    prompt = _task_prompt(source, folder, _propositions(project_dir, state))
    task_file = qr / "lean_task.md"
    task_file.write_text(prompt, encoding="utf-8")
    print(f"  [5.5] Lean task -> {task_file}  (folder: {folder}, lib: {lib})")

    if mode == "manual":
        from ..claude_runner import request_manual_intervention
        request_manual_intervention(
            stage="stage5_5_lean",
            issue=(
                f"Run your coding agent FROM THE ROOT of {lib} with the long, proof-intensive "
                f"configuration you use for formalization, and give it the task in {task_file}. "
                f"When the workflow finishes (even partially), write "
                f"quality_reports/intervention_done.json. The pipeline will then run "
                f"`scripts/paper_contribution.py check {folder} --fast`, record the result, and "
                f"copy papers/{folder}/ to lean/ exactly as generated."
            ),
            files=[str(task_file), str(lib)],
            project_dir=project_dir,
        )
        agent_rc, agent_tail = None, "(run manually)"
    else:
        if LEAN_AGENT_CMD:
            cmd = LEAN_AGENT_CMD.format(prompt_file=shlex.quote(str(task_file)), folder=folder)
            shell = True
        else:
            from ..config import resolve_model
            p = get_profile("lean_formalize")
            from ..claude_runner import claude_executable
            cmd = [claude_executable(), "-p", "--model", resolve_model(p["model"]),
                   "--effort", p["effort"], "--output-format", "text"]
            shell = False
        print(f"  [5.5] Running formalization agent (timeout {LEAN_TIMEOUT // 3600}h)...")
        try:
            r = subprocess.run(cmd, cwd=lib, shell=shell, input=None if shell else prompt,
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=LEAN_TIMEOUT)
            agent_rc, agent_tail = r.returncode, (r.stdout + r.stderr)[-3000:]
        except (OSError, subprocess.TimeoutExpired) as e:
            agent_rc, agent_tail = -1, str(e)
        (qr / "lean_agent_log.md").write_text(f"rc={agent_rc}\n\n{agent_tail}", encoding="utf-8")

    src_dir = lib / "papers" / folder
    if not src_dir.exists():
        msg = f"Workflow produced no papers/{folder}/ folder (agent rc={agent_rc})."
        print(f"  [5.5] {msg}")
        (qr / "lean_status.md").write_text(f"# Lean formalization: FAILED\n\n{msg}\n\n"
                                           f"Agent output tail:\n```\n{agent_tail}\n```\n",
                                           encoding="utf-8")
        return _finish(project_dir, state, {"status": "failed", "reason": msg,
                                            "folder": folder, "agent_rc": agent_rc})

    # Paper-scoped check BEFORE copying, recorded outside lean/
    check_rc, check_out = _run_check(lib, folder)
    verdict = "PASS" if check_rc == 0 else "FAILED/PARTIAL"
    check_md = (f"# Lean paper check: {verdict}\n\n"
                f"- Command (from AppliedModelingLib root): "
                f"`python3 scripts/paper_contribution.py check {folder} --fast`\n"
                f"- Return code: {check_rc}\n- Run at: {datetime.now().isoformat()}\n\n"
                f"```\n{check_out[-6000:]}\n```\n")
    if check_rc != 0:
        check_md += ("\n## Blocker\nThe folder is submitted exactly as generated. The precise "
                     "blocker is the first failing item in the check output above; summarize "
                     "it here before publishing.\n")
    (qr / "lean_check.md").write_text(check_md, encoding="utf-8")
    print(f"  [5.5] Paper check: {verdict} (rc={check_rc}) -> quality_reports/lean_check.md")

    # Copy the entire folder exactly as generated
    targets = [project_dir / "lean"]
    export = _cfg(state, "lean_export")
    if export:
        targets.append(Path(export).expanduser() / "lean")
    for dst in targets:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src_dir, dst, symlinks=True)
        print(f"  [5.5] Copied papers/{folder}/ -> {dst}")
    if export:
        shutil.copy2(qr / "lean_check.md", Path(export).expanduser() / "lean_check.md")
        print(f"  [5.5] In {export}: `git add lean/ lean_check.md` (respect lean/.gitignore; "
              "never `git add -f`).")

    (qr / "lean_status.md").write_text(
        f"# Lean formalization: {verdict}\n\n- Source: {source}\n- Folder: {folder}\n"
        f"- Mode: {mode}\n- Check rc: {check_rc}\n- Copied to: "
        + ", ".join(str(t) for t in targets)
        + "\n\nSee quality_reports/lean_check.md and the status/audit files inside lean/ for "
          "which statements are formalized, partial, or blocked.\n", encoding="utf-8")
    return _finish(project_dir, state, {
        "status": "completed", "verdict": verdict, "folder": folder, "source": source,
        "check_rc": check_rc, "agent_rc": agent_rc, "copied_to": [str(t) for t in targets],
    })
