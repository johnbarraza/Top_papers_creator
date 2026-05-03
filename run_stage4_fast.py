"""Fast Stage 4bc: Skip code generation, execute existing scripts + critic review.

Use this when scripts already exist and you just need to run them + get a critic score.
"""
import sys
import functools
print = functools.partial(print, flush=True)

from pathlib import Path
from datetime import datetime

from pipeline.state import load_state, save_state
from pipeline.config import CLO_AUTHOR, CRITIC_GATE, get_profile
from pipeline.json_utils import extract_json, smart_truncate
from pipeline.python_runner import run_with_retry, install_requirements
from pipeline.validators.code_validator import validate as validate_code
from pipeline.stages.stage4_code import (
    _execute_scripts, _gather_scripts_content, _run_critic, _read_file_or
)

PROJECT = Path(r"C:\Users\jesus\Documents\paper-HQ-sin API\projects\salud_en_el_peru_20260328_202427")
SCRIPTS_DIR = PROJECT / "scripts" / "python"
STRATEGY_DIR = PROJECT / "strategy"

state = load_state(PROJECT)

# Read strategy memo for critic context
strategy_memo = _read_file_or(STRATEGY_DIR / "strategy_memo.md", "")
print(f"Strategy memo: {len(strategy_memo)} chars")

# Gather existing scripts
py_scripts = sorted(SCRIPTS_DIR.glob("*.py"), key=lambda p: p.name)
py_scripts = [s for s in py_scripts if s.name.startswith(("00", "01", "02", "03"))]
print(f"Scripts found: {[s.name for s in py_scripts]}")

# Install deps
req_file = SCRIPTS_DIR / "requirements.txt"
if req_file.exists():
    install_requirements(req_file)

# Execute scripts
print("\n=== Executing scripts ===")
_, all_results, all_ok = _execute_scripts(py_scripts, SCRIPTS_DIR)

for name, result in all_results.items():
    status = "OK" if result["ok"] else "FAIL"
    files = len(result.get("generated_files", []))
    print(f"  {name}: {status} ({files} files generated)")

# Automated validation
print("\n=== Running automated validation ===")
validation = validate_code(SCRIPTS_DIR, PROJECT, all_results)
print(f"  {validation.format_for_log()}")
validation_text = validation.format_for_critic()

# Critic review
print("\n=== Running critic review ===")
critic_prompt_text = (CLO_AUTHOR / ".claude" / "agents" / "coder-critic.md").read_text(encoding="utf-8")
scripts_content = _gather_scripts_content(py_scripts, all_results)
_, critic_result, critic_score = _run_critic(
    critic_prompt_text, strategy_memo, scripts_content, PROJECT,
    validation_text
)

print(f"\n=== RESULT: Critic score = {critic_score}/100 (gate: {CRITIC_GATE}) ===")

# Save state
state["stages"]["stage4bc"] = {
    "status": "completed",
    "scripts_dir": str(SCRIPTS_DIR),
    "scripts": [s.name for s in py_scripts],
    "all_scripts_ok": all_ok,
    "critic_score": critic_score,
    "critic_result": critic_result,
    "validation": validation.summary_counts,
    "validation_hard_pass": validation.hard_pass,
    "completed_at": datetime.now().isoformat(),
}
state["current_stage"] = 4
save_state(PROJECT, state)
print("\nState saved. Ready for Stage 5+.")
