# AGENTS.md — LLM Agent Instructions for Papers-HQ

## What this is

Papers-HQ is an automated academic paper pipeline. Claude does reasoning
(ideation, validation, writing, review); Python does execution
(data loading, code generation, statistics, LaTeX).

An LLM agent can **install**, **run**, and **debug** this pipeline by
following the instructions below.

## Quick install (copy-paste)

```bash
# 1. Clone
git clone https://github.com/johnbarraza/Top_papers_creator.git
cd Top_papers_creator

# 2. Virtual env
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

# 3. Dependencies
pip install -r requirements.txt

# 4. Optional extras (paperdl, owslib, rarfile)
pip install paperdl owslib rarfile

# 5. Verify install
python check_sources.py --http
```

## Prerequisites the agent must verify

| Thing | Check | Fix if missing |
|---|---|---|
| Python 3.11+ | `python --version` | Install from python.org |
| Claude Code CLI | `claude --version` | `npm install -g @anthropic-ai/claude-code` then `claude login` |
| LaTeX (pdflatex) | `pdflatex --version` | Install TeX Live or MiKTeX |
| Git | `git --version` | Install from git-scm.com |

## Run the pipeline

```bash
# Path A — search by topic
python run_pipeline.py --topic "Your research topic here"

# Path B — bring your own dataset
python run_pipeline.py --topic "Labor Markets" --data "./panel.csv"

# Path C — data-first (find best datasets, then suggest topics)
python run_pipeline.py --path-c

# Replication mode (student assignment)
python run_pipeline.py --topic "cash transfers Peru" --mode replicate

# Resume from a stage
python run_pipeline.py --from-stage 4 --project my_project_20260502_145708

# Check status
python run_pipeline.py --status my_project_20260502_145708
```

## Key files an agent should know

| File | Purpose |
|---|---|
| `run_pipeline.py` | Main entry point — orchestrates all stages |
| `pipeline/config.py` | Paths, thresholds, timeouts, stage profiles |
| `pipeline/state.py` | Project state load/save (atomic writes) |
| `pipeline/claude_runner.py` | Subprocess wrapper for `claude -p` calls |
| `pipeline/paper_searcher.py` | Paper candidate search + ranking |
| `pipeline/human_checkpoint.py` | Interactive prompts at Stages 2.5, 3.5 |
| `pipeline/stages/` | One file per pipeline stage |
| `check_sources.py` | Health-check all 38 data sources |
| `requirements.txt` | Python dependencies |
| `Skills/` | review-paper and review-paper-code skill definitions |

## Path architecture

All paths derive from `PAPERS_HQ` in `pipeline/config.py`:
- `PAPERS_HQ` = root of this repo (where `run_pipeline.py` lives)
- `PAPERS_HQ / "projects" / <name>` = project output directory
- `PAPERS_HQ / "clo-author"` = agent prompt templates
- `PAPERS_HQ / "idea-evaluation-pipeline"` = validation prompts

The pipeline must be run from `PAPERS_HQ` (the repo root) so relative
imports resolve correctly.

## Environment variables (optional)

```bash
# Override paperdl mode: auto (default), on (require), off (skip)
export PIPELINE_PAPERDL=auto

# Override NotebookLM mode: auto (default), on, off
export PIPELINE_NOTEBOOKLM=auto

# Timeouts (seconds)
export PIPELINE_CLAUDE_TIMEOUT=600
export PIPELINE_PYTHON_TIMEOUT=600

# DeepSeek backend (alternative to Anthropic)
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="<your DeepSeek API key>"
export ANTHROPIC_MODEL="deepseek-v4-pro[1m]"
```

## Troubleshooting common failures

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: pipeline` | Not running from repo root | `cd Top_papers_creator` first |
| `claude: command not found` | Claude Code CLI not installed | `npm install -g @anthropic-ai/claude-code` |
| Stage 3 validation hangs | Semantic Scholar rate limit | Wait 60s, retry from `--from-stage 3` |
| `pdflatex: command not found` | LaTeX not on PATH | Install MiKTeX or TeX Live |
| `.venv\Scripts\activate` fails | Windows execution policy | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Corrupt state file | Pipeline killed mid-write | Auto-quarantined as `.corrupt-<ts>.json`, pipeline starts fresh |

## For agents: how to debug a failed stage

1. Read `projects/<name>/pipeline_state.json` — check `stages.stage<N>.status`
2. If `failed`, read the `reason` field for the error message
3. Check `projects/<name>/` for partial outputs (scripts, data, logs)
4. Re-run from the failed stage: `python run_pipeline.py --from-stage <N> --project <name>`
5. If a script failed in Stage 4, check `projects/<name>/scripts/python/` — fix the script, then re-run Stage 4

## Notes for agents

- This pipeline runs `claude -p` (headless) as a subprocess for every LLM call.
  The calling agent does NOT need to replicate the LLM reasoning — it only
  needs to run the Python orchestrator and handle errors.
- Stage 2.5 and 3.5 are human checkpoints. In non-interactive mode, they will
  block waiting for input. Agents should warn the user about this.
- The `check_sources.py` script is safe to run any time — it only does
  read-only API probes.
- All state is in `projects/<name>/pipeline_state.json`. Back it up before
  risky operations.
