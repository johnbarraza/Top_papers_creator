"""Execute Python scripts with error capture, timeout, and retry via Claude."""

import subprocess
import sys
from pathlib import Path
from typing import Optional

from .config import PYTHON_TIMEOUT, MAX_CODE_RETRIES, get_profile
from .claude_runner import run_claude


def run_python_script(
    script_path: Path,
    *,
    cwd: Optional[Path] = None,
    timeout: int = PYTHON_TIMEOUT,
    env: Optional[dict] = None,
) -> dict:
    """Execute a Python script and return structured results.

    Returns
    -------
    dict
        Keys: ``ok`` (bool), ``stdout``, ``stderr``, ``returncode``,
        ``generated_files`` (list of new/modified files in cwd after execution).
    """
    cwd = cwd or script_path.parent

    # Snapshot only output directories (tables, figures, data/clean) instead
    # of the entire tree — avoids O(n) rglob on large working directories.
    _OUTPUT_DIRS = ["paper/tables", "paper/figures", "data/clean", "."]
    project_root = cwd.parent.parent if cwd.name == "python" else cwd

    def _snapshot_outputs():
        files = set()
        for rel in _OUTPUT_DIRS:
            d = project_root / rel if rel != "." else cwd
            if d.exists():
                for f in d.iterdir():
                    if f.is_file():
                        files.add(f)
        return files

    before = _snapshot_outputs()

    print(f"  [python] Running {script_path.name} (timeout={timeout}s)...")

    # Force UTF-8 for subprocess stdout/stderr to avoid Windows cp1252 crashes
    # when scripts print Unicode characters (checkmarks, Greek letters, etc.)
    run_env = dict(env) if env else dict(__import__("os").environ)
    run_env["PYTHONIOENCODING"] = "utf-8"
    run_env["PYTHONUTF8"] = "1"

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout,
            env=run_env,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "stdout": "",
            "stderr": f"Script timed out after {timeout}s",
            "returncode": -1,
            "generated_files": [],
        }

    after = _snapshot_outputs()
    new_files = sorted(str(f.relative_to(project_root)) for f in (after - before) if f.is_file())

    ok = result.returncode == 0

    if ok:
        print(f"  [python] {script_path.name} completed OK")
        if new_files:
            print(f"  [python] Generated: {', '.join(new_files[:10])}")
    else:
        stderr_preview = result.stderr[:300] if result.stderr else "(no stderr)"
        print(f"  [python] {script_path.name} FAILED (rc={result.returncode})")
        print(f"  [python] {stderr_preview}")

    return {
        "ok": ok,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
        "generated_files": new_files,
    }


def run_with_retry(
    script_path: Path,
    *,
    cwd: Optional[Path] = None,
    max_retries: int = MAX_CODE_RETRIES,
    fix_model: Optional[str] = None,
) -> dict:
    """Execute a script, and if it fails, feed stderr to Claude for a fix.

    Up to *max_retries* fix-and-rerun cycles.  Returns the final run result.
    """
    result = run_python_script(script_path, cwd=cwd)

    for attempt in range(1, max_retries + 1):
        if result["ok"]:
            return result

        print(f"  [retry] Attempt {attempt}/{max_retries} - asking Claude to fix...")

        code = script_path.read_text(encoding="utf-8")
        fix_prompt = f"""The following Python script failed. Fix the error and return the COMPLETE corrected script.

## Script: {script_path.name}
```python
{code}
```

## Error output:
```
{result['stderr'][:2000]}
```

## stdout (partial):
```
{result['stdout'][:1000]}
```

IMPORTANT RULES:
- NEVER use pickle to save/load statsmodels objects (they fail across Python versions)
- Instead, extract coefs/SE/pvalues into a DataFrame and save as .parquet
- If the error is about pickle.load of statsmodels, replace it with pd.read_parquet of the corresponding .parquet file
- Use ONLY ASCII characters in print statements (no Unicode arrows, dashes, etc.)
- Do NOT change file paths that are working correctly

Return ONLY the corrected Python code inside a single ```python ... ``` block. No explanations."""

        pf = get_profile("stage4_fix")
        fixed_code = run_claude(fix_prompt, model=fix_model or pf["model"], effort=pf["effort"])

        # Extract the code block
        import re
        m = re.search(r'```python\s*\n(.*?)\n\s*```', fixed_code, re.DOTALL)
        if m:
            new_code = m.group(1)
            original_code = script_path.read_text(encoding="utf-8") \
                if script_path.exists() else ""

            # Validate the LLM patch before overwriting the script:
            # 1. Reject if shorter than 50 chars or shorter than half the
            #    original (catches truncated / partial code blocks).
            # 2. Reject if it doesn't parse as Python (catches garbled output).
            # On failure, keep the original and abort the retry loop so
            # downstream stages don't run a wiped-out script.
            import ast as _ast_pr
            reject_reason = None
            if len(new_code) < max(50, len(original_code) // 2):
                reject_reason = (
                    f"patch too short ({len(new_code)} bytes, original was "
                    f"{len(original_code)})"
                )
            else:
                try:
                    _ast_pr.parse(new_code)
                except SyntaxError as exc:
                    reject_reason = (
                        f"patch did not parse: {exc.msg} at line {exc.lineno}"
                    )

            if reject_reason:
                rej = script_path.with_suffix(script_path.suffix + ".rejected")
                try:
                    rej.write_text(new_code, encoding="utf-8")
                except OSError:
                    pass
                print(
                    f"  [retry] REJECTED LLM patch — {reject_reason}. "
                    f"Original kept; rejected payload at {rej.name}"
                )
                break

            try:
                script_path.with_suffix(script_path.suffix + ".bak").write_text(
                    original_code, encoding="utf-8")
            except OSError:
                pass
            script_path.write_text(new_code, encoding="utf-8")
            print(f"  [retry] Script patched, re-running...")
            result = run_python_script(script_path, cwd=cwd)
        else:
            print(f"  [retry] Could not extract code block from fix response.")
            break

    if not result["ok"]:
        print(f"  [fail] Script {script_path.name} failed after {max_retries} retries.")

    return result


def install_requirements(requirements_path: Path) -> bool:
    """Run pip install -r on a requirements file.  Returns True on success."""
    if not requirements_path.exists():
        return True

    print(f"  [pip] Installing {requirements_path}...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(requirements_path), "-q"],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        print(f"  [pip] FAILED: {result.stderr[:300]}")
        return False

    print(f"  [pip] Dependencies installed.")
    return True
