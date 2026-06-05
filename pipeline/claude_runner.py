"""Wrapper around Claude Code CLI for structured prompt execution.

Uses `claude -p` (headless mode) instead of the Anthropic API.
No API key required — runs on the Claude Code subscription.
Supports both sequential and parallel execution via subprocess.
Includes manual intervention signaling for Stages 4, 5, 6.
"""

import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from .config import CLAUDE_TIMEOUT, MAX_PARALLEL_AGENTS

# ── Force unbuffered stdout so log files show progress in real time ───────────
import functools
print = functools.partial(print, flush=True)  # type: ignore[assignment]

# ── Retry configuration ──────────────────────────────────────────────────────

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 10  # seconds; actual wait = base * attempt (10, 20, 30)

# ── Model aliases for --model flag ───────────────────────────────────────────

MODEL_MAP = {
    "sonnet": "sonnet",
    "haiku":  "haiku",
    "opus":   "opus",
}

# Effort levels supported by claude CLI: low, medium, high, max
EFFORT_MAP = {
    "low": "low",
    "medium": "medium",
    "high": "high",
}


def _build_cmd(
    *,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    allowed_tools: Optional[list[str]] = None,
    effort: Optional[str] = None,
) -> list[str]:
    """Build the `claude -p` command with appropriate flags."""
    cmd = ["claude", "-p", "--output-format", "text"]

    if model:
        cmd.extend(["--model", MODEL_MAP.get(model, model)])

    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    if effort:
        cli_effort = EFFORT_MAP.get(effort, "medium")
        cmd.extend(["--effort", cli_effort])

    # Tool restrictions:
    # - allowed_tools=None  → use default CLI tools
    # - allowed_tools=[]    → disallow all tools via --disallowedTools
    # - allowed_tools=[...] → allow only those tools
    if allowed_tools is not None:
        if len(allowed_tools) == 0:
            cmd.extend(["--disallowedTools", "Bash,Edit,Write,Read,Glob,Grep,NotebookEdit"])
        else:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])

    return cmd


def _parse_response(stdout: str) -> str:
    """Extract the text result from claude output."""
    text = stdout.strip()
    if not text:
        return ""
    if text.startswith("{"):
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "result" in data and data["result"]:
                return data["result"].strip()
            if isinstance(data, dict) and data.get("is_error"):
                return f"[error] {data.get('result', 'unknown error')}"
        except (json.JSONDecodeError, TypeError):
            pass
    return text


def run_claude(
    prompt: str,
    *,
    model: Optional[str] = None,
    allowed_tools: Optional[list[str]] = None,
    timeout: int = CLAUDE_TIMEOUT,
    cwd: Optional[str] = None,
    system_prompt: Optional[str] = None,
    output_file: Optional[Path] = None,
    append_output: bool = False,
    effort: Optional[str] = None,
    label: Optional[str] = None,
    max_retries: Optional[int] = None,
) -> str:
    """Execute a prompt via Claude Code CLI and return the response text."""
    tag = label or "prompt"
    chars = len(prompt)
    model_tag = f", model={model}" if model else ""
    effort_tag = f", effort={effort}" if effort else ""
    print(f"  [claude] {tag} ({chars} chars{model_tag}{effort_tag})...")

    cmd = _build_cmd(
        model=model,
        system_prompt=system_prompt,
        allowed_tools=allowed_tools,
        effort=effort,
    )

    last_error = None
    retries = max_retries if max_retries is not None else MAX_RETRIES

    for attempt in range(1, retries + 1):
        t0 = time.time()
        try:
            # Pass the prompt via stdin instead of shell redirection.
            # The previous implementation built a shell string with manual
            # quoting and used `shell=True`, which (a) is vulnerable to
            # shell-injection if any token in `cmd` contains shell metachars
            # and (b) misbehaves on Windows when the temp path contains
            # spaces or non-ASCII characters. Feeding stdin avoids both.
            import threading
            stop_heartbeat = threading.Event()

            def _heartbeat():
                while not stop_heartbeat.wait(30):
                    elapsed_so_far = time.time() - t0
                    print(f"  [working] {tag} ... {elapsed_so_far:.0f}s",
                          flush=True)

            hb = threading.Thread(target=_heartbeat, daemon=True)
            hb.start()

            try:
                result = subprocess.run(
                    cmd,
                    shell=False,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=cwd,
                    encoding="utf-8",
                    errors="replace",
                )

                stop_heartbeat.set()
                hb.join(timeout=2)

                stdout_data = result.stdout or ""
                stderr_data = result.stderr or ""
            finally:
                stop_heartbeat.set()

            if result.returncode != 0:
                stderr_preview = (stderr_data)[:500]
                raise RuntimeError(
                    f"claude exited with code {result.returncode}: {stderr_preview}"
                )

            response_text = _parse_response(stdout_data.strip())
            elapsed = time.time() - t0
            if attempt > 1:
                print(f"  [done] {tag} ({elapsed:.0f}s) — succeeded on attempt {attempt}")
            else:
                print(f"  [done] {tag} ({elapsed:.0f}s)")

            if output_file:
                output_file.parent.mkdir(parents=True, exist_ok=True)
                mode = "a" if append_output else "w"
                with open(output_file, mode, encoding="utf-8") as f:
                    if append_output:
                        f.write("\n\n---\n\n")
                    f.write(response_text)
                print(f"  [saved] {output_file}")

            return response_text

        except subprocess.TimeoutExpired:
            stop_heartbeat.set()
            hb.join(timeout=2)
            elapsed = time.time() - t0
            last_error = f"timed out after {elapsed:.0f}s"
        except Exception as e:
            stop_heartbeat.set()
            hb.join(timeout=2)
            elapsed = time.time() - t0
            last_error = str(e)

        if attempt < retries:
            wait = RETRY_BACKOFF_BASE * attempt
            print(f"  [retry] {tag} attempt {attempt}/{retries} failed: {last_error}")
            print(f"  [retry] Waiting {wait}s before retry...")
            time.sleep(wait)
        else:
            print(f"  [error] {tag} failed after {retries} attempts: {last_error}")
            raise RuntimeError(f"{tag} failed after {retries} attempts: {last_error}")

    raise RuntimeError(f"{tag} failed unexpectedly")


# ── Parallel execution via subprocess ────────────────────────────────────────

def run_claude_parallel(
    tasks: list[dict], *, max_workers: int = MAX_PARALLEL_AGENTS
) -> list[str]:
    """Run multiple Claude prompts in parallel using subprocesses."""
    if not tasks:
        return []

    n = len(tasks)
    print(f"\n  [parallel] Launching {n} agents (max {max_workers} concurrent)...")
    t0 = time.time()

    results: list[str] = [""] * n

    def _run(idx, kwargs):
        return idx, run_claude(**kwargs)

    errors = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_run, i, task): i
            for i, task in enumerate(tasks)
        }
        for future in as_completed(futures):
            try:
                idx, resp = future.result()
                results[idx] = resp
            except Exception as e:
                idx = futures[future]
                label = tasks[idx].get("label", f"task-{idx}")
                print(f"  [parallel] {label} failed: {e}")
                results[idx] = f"[error] {e}"
                errors.append((idx, str(e)))

    elapsed = time.time() - t0
    failed = f" ({len(errors)} failed)" if errors else ""
    print(f"  [parallel] All {n} agents done ({elapsed:.0f}s total){failed}")
    return results


# ── Manual intervention signaling ─────────────────────────────────────────────

INTERVENTION_REQUEST = "intervention_needed.json"
INTERVENTION_DONE = "intervention_done.json"
POLL_INTERVAL = 30  # seconds between checks
INTERVENTION_MAX_WAIT_SECONDS = 6 * 60 * 60  # 6 hours; abort poll after this


def request_manual_intervention(
    stage: str,
    issue: str,
    files: list[str],
    project_dir: Path,
    script_results: Optional[dict] = None,
) -> bool:
    """Signal that manual intervention is needed and WAIT for completion.

    Protocol:
    ─────────
    1. Pipeline writes ``quality_reports/intervention_needed.json`` with:
       - stage: which stage needs help
       - issue: description of what's needed
       - files: list of relevant file paths
       - script_results: optional dict with extra context

    2. Pipeline prints a banner and polls every 30s for
       ``quality_reports/intervention_done.json``.

    3. The user tells Claude (in conversation): "revisa el pipeline".
       Claude then:
       a) Reads intervention_needed.json to understand what's needed
       b) Reads/modifies the files listed in the request
       c) Writes intervention_done.json with:
          {
            "action": "fixed",
            "stage": "<stage_name>",
            "summary": "<what was done>",
            "completed_at": "<ISO timestamp>"
          }

    4. Pipeline detects intervention_done.json, cleans up both signal
       files, and continues execution.

    Note: If Claude doesn't write intervention_done.json (or writes it
    with the wrong format), the pipeline will poll indefinitely. The user
    can also manually create the file to unblock the pipeline.
    """
    signals_dir = project_dir / "quality_reports"
    signals_dir.mkdir(exist_ok=True)
    request_file = signals_dir / INTERVENTION_REQUEST
    done_file = signals_dir / INTERVENTION_DONE

    # Clear any old done signal
    if done_file.exists():
        done_file.unlink()

    # Write the intervention request
    from datetime import datetime

    request_data = {
        "stage": stage,
        "issue": issue,
        "files": files,
        "project_dir": str(project_dir),
        "script_results": script_results or {},
        "requested_at": datetime.now().isoformat(),
    }
    # Atomic write: a polling reader must never see a half-written request
    # file (the read-side parses JSON and would crash on a partial doc).
    from .state import atomic_write_text

    atomic_write_text(
        request_file,
        json.dumps(request_data, indent=2, ensure_ascii=False),
    )

    # Print clear message for the user (with audible alert)
    print("\a", end="", flush=True)  # Terminal bell — attention needed
    print(f"\n  {'=' * 60}")
    print(f"  MANUAL INTERVENTION NEEDED")
    print(f"  {'=' * 60}")
    print(f"  Stage: {stage}")
    print(f"  Issue: {issue}".encode("ascii", errors="replace").decode("ascii"))
    print(f"  Files: {', '.join(files)}")
    print(f"  {'=' * 60}")
    print(f"  Tell Claude in conversation: 'revisa el pipeline'")
    print(f"  Pipeline will resume automatically when done.")
    print(f"  {'=' * 60}")
    print(f"  Waiting", end="", flush=True)

    # Poll for completion with a hard wall-clock cap so the pipeline can
    # never hang forever on a missing or persistently malformed signal
    # file.  We also count consecutive parse failures: if the done file
    # exists but cannot be parsed as JSON for many ticks in a row we surface
    # the error rather than spinning silently.
    poll_start = time.time()
    parse_failures = 0
    max_parse_failures = 5

    while True:
        if time.time() - poll_start > INTERVENTION_MAX_WAIT_SECONDS:
            print(
                f"\n  [INTERVENTION] TIMED OUT after "
                f"{INTERVENTION_MAX_WAIT_SECONDS // 3600}h waiting on "
                f"{done_file.name}. Aborting poll."
            )
            return False

        time.sleep(POLL_INTERVAL)
        print(".", end="", flush=True)

        if done_file.exists():
            try:
                done_data = json.loads(
                    done_file.read_text(encoding="utf-8")
                )
                action = done_data.get("action", "fixed")
                print("\a", end="", flush=True)  # Terminal bell — intervention done
                print(f"\n  [INTERVENTION] Complete! Action: {action}")

                # Clean up signal files
                request_file.unlink(missing_ok=True)
                done_file.unlink(missing_ok=True)
                return True
            except json.JSONDecodeError as exc:
                parse_failures += 1
                if parse_failures >= max_parse_failures:
                    print(
                        f"\n  [INTERVENTION] {done_file.name} keeps failing "
                        f"to parse ({exc}). Aborting poll so a human can "
                        f"inspect the file."
                    )
                    return False
                continue


def check_intervention_needed(project_dir: Path) -> Optional[dict]:
    """Check if there's a pending intervention request for a specific project."""
    request_file = project_dir / "quality_reports" / INTERVENTION_REQUEST
    if not request_file.exists():
        return None
    try:
        return json.loads(request_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def find_all_interventions() -> list[dict]:
    """Scan ALL projects for pending intervention requests.

    Used by Claude in conversation when user says 'revisa el pipeline'.
    Returns a list of dicts with project name, stage, issue, and files.
    """
    from .config import PAPERS_HQ

    projects_dir = PAPERS_HQ / "projects"
    if not projects_dir.exists():
        return []

    pending = []
    for project in sorted(projects_dir.iterdir()):
        if not project.is_dir():
            continue
        request_file = project / "quality_reports" / INTERVENTION_REQUEST
        if request_file.exists():
            try:
                data = json.loads(request_file.read_text(encoding="utf-8"))
                data["project_name"] = project.name
                data["project_path"] = str(project)
                pending.append(data)
            except Exception:
                continue

    return pending


def signal_intervention_done(project_dir: Path, action: str = "fixed", notes: str = ""):
    """Signal that manual intervention is complete. Called by Claude in conversation."""
    from datetime import datetime

    done_file = project_dir / "quality_reports" / INTERVENTION_DONE
    done_data = {
        "action": action,
        "notes": notes,
        "completed_at": datetime.now().isoformat(),
    }
    # Atomic write so the polling reader can never observe a half-written
    # JSON file (race that previously caused parse failures + retry loops).
    from .state import atomic_write_text

    atomic_write_text(
        done_file,
        json.dumps(done_data, indent=2, ensure_ascii=False),
    )
    print(f"  [signal] Intervention done signal sent: {action}")
