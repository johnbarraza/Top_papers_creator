
"""
Papers-HQ: Automated Academic Paper Production Pipeline v2
==========================================================
Hybrid orchestrator — Claude handles reasoning, Python handles execution.

7 stages + 2 human checkpoints:
  Stage 1:   Discovery        (Path A: repos  |  Path B: user data)
  Stage 2:   Ideation         (research-junshi)
  Stage 2.5: Idea Selection   (human checkpoint)
  Stage 3:   Validation       (8-step evaluation, 1 call per step)
  Stage 3.5: Strategy Review  (human checkpoint)
  Stage 4:   Strategy & Code  (generate + execute Python scripts)
  Stage 4.7: Code Review      (review-paper-code skill + correction loop)
  Stage 5:   Writing          (LaTeX paper draft + compile)
  Stage 6:   Peer Review      (6-agent review-paper skill, R&R loop)
  Stage 7:   Submission       (journal targeting + replication audit)

Usage:
  python run_pipeline.py --topic "Economics"
  python run_pipeline.py --topic "Labor" --data "./panel.csv"
  python run_pipeline.py --from-stage 2 --project my_project
  python run_pipeline.py --from-stage 2.5 --project my_project
  python run_pipeline.py --status my_project
"""

import argparse
import sys
from datetime import datetime

from pipeline.config import PAPERS_HQ, STAGE_ORDER, STAGE_NAMES
from pipeline.state import ensure_project_dir, load_state, save_state


# ═══════════════════════════════════════════════════════════════════════════════
# Status display
# ═══════════════════════════════════════════════════════════════════════════════

def print_status(project_dir):
    state = load_state(project_dir)
    print(f"\nProject: {state['project']}")
    print(f"Created: {state.get('created_at', 'N/A')}")
    print(f"Updated: {state.get('updated_at', 'N/A')}")
    print(f"Current Stage: {state.get('current_stage', 0)}")
    print()

    for stage_num in STAGE_ORDER:
        name = STAGE_NAMES[stage_num]
        key = f"stage{stage_num}"
        info = state.get("stages", {}).get(key, {})
        status = info.get("status", "pending")
        icon = "[x]" if status == "completed" else "[ ]"

        extra = ""
        if stage_num == 1 and "topic" in info:
            extra = f" (topic: {info['topic']})"
        elif stage_num == 2.5 and "action" in info:
            extra = f" ({info['action']})"
        elif stage_num == 3 and "result" in info:
            r = info["result"]
            extra = f" ({r.get('status', '?')}, score: {r.get('final_score', '?')})"
        elif stage_num == 3.5 and "action" in info:
            extra = f" ({info['action']})"
        elif stage_num == 4 and "result" in info:
            extra = f" ({info['result'].get('decision', '?')})"

        print(f"  {icon} Stage {stage_num}: {name}{extra}")

    print()


# ═══════════════════════════════════════════════════════════════════════════════
# Stage header
# ═══════════════════════════════════════════════════════════════════════════════

def _stage_header(stage_num):
    name = STAGE_NAMES.get(stage_num, "Unknown")
    print(f"\n{'=' * 60}")
    print(f"STAGE {stage_num}: {name}")
    print("=" * 60)


# ═══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Papers-HQ v2: End-to-end academic paper production pipeline"
    )
    parser.add_argument("--topic", type=str, help="Research topic for Stage 1")
    parser.add_argument("--data", type=str, help="Path or URL to user dataset (Path B)")
    parser.add_argument("--project", type=str, help="Project name (default: auto-generated)")
    parser.add_argument("--from-stage", type=float, default=1,
                        help="Start from a specific stage (e.g. 1, 2, 2.5, 3, 3.5, 4)")
    parser.add_argument("--to-stage", type=float, default=7,
                        help="Stop after a specific stage (default: 7)")
    parser.add_argument("--mode", choices=["new", "replicate", "ask"], default="ask",
                        help="Stage 2 mode: new ideas, replication/HTE, or ask interactively")
    parser.add_argument("--status", type=str, metavar="PROJECT",
                        help="Show status of a project")

    args = parser.parse_args()

    # ── Status mode ──────────────────────────────────────────────────────
    if args.status:
        project_dir = PAPERS_HQ / "projects" / args.status
        if not project_dir.exists():
            print(f"Project not found: {args.status}")
            sys.exit(1)
        print_status(project_dir)
        return

    if args.from_stage not in STAGE_ORDER:
        parser.error(f"--from-stage must be one of {STAGE_ORDER}")
    if args.to_stage not in STAGE_ORDER:
        parser.error(f"--to-stage must be one of {STAGE_ORDER}")

    # ── Interactive setup (when starting from Stage 1 without --topic) ──
    if args.from_stage == 1 and not args.topic:
        print()
        print("=" * 60)
        print("  PAPERS-HQ v2 - Automated Academic Paper Pipeline")
        print("=" * 60)

        # 1. Ask for path first
        print()
        print("  How would you like to start?")
        print()
        print("  [A] Search by topic - Find datasets for a specific research topic")
        print()
        print("  [B] Use my own dataset - Provide a dataset file (.csv, .xlsx,")
        print("      .dta, .parquet) for data-driven idea generation")
        print()
        print("  [C] Data-first (recommended for 90+ scores) - Search for the")
        print("      best available datasets worldwide, then suggest viable")
        print("      research topics based on what the data can actually support")
        print()

        while True:
            path_choice = input("  Choose path [A/B/C]: ").strip().upper()
            if path_choice in ("A", "B", "C"):
                break
            print("  Please enter A, B, or C.")

        # 2. Ask for topic only if Path A or B
        if path_choice in ("A", "B"):
            print()
            topic = ""
            while not topic.strip():
                topic = input("  Research topic (e.g. Labor Economics, Trade Policy): ").strip()
                if not topic:
                    print("  Topic cannot be empty. Try again.")
            args.topic = topic

        if path_choice == "B":
            while True:
                data_input = input("  Dataset path (e.g. ./data/panel.csv): ").strip()
                if data_input:
                    from pathlib import Path as P
                    if P(data_input).exists():
                        args.data = data_input
                        break
                    else:
                        print(f"  File not found: {data_input}. Try again.")
                else:
                    print("  Path cannot be empty.")

        if path_choice == "C":
            args.topic = "__PATH_C__"
            args.path_c = True
        else:
            args.path_c = False

        print()

    # ── Ensure path_c attribute exists ──────────────────────────────────
    if not hasattr(args, "path_c"):
        args.path_c = False

    # ── Validate topic for Stage 1 ────────────────────────────────────────
    if args.from_stage == 1 and not args.topic and not args.path_c:
        parser.error("--topic is required when starting from Stage 1 (or run without --topic for interactive mode)")

    # ── Project name ─────────────────────────────────────────────────────
    if args.project:
        project_name = args.project
    elif args.topic and args.topic != "__PATH_C__":
        import unicodedata
        import re as _re_proj
        # Strip accents
        safe_topic = unicodedata.normalize("NFKD", args.topic).encode("ascii", "ignore").decode("ascii")
        # Remove Windows-invalid path characters: : ? * / \ " < > |
        safe_topic = _re_proj.sub(r'[:?*/\\"<>|]', '', safe_topic)
        # Collapse whitespace -> single underscore
        safe_topic = _re_proj.sub(r'\s+', '_', safe_topic.lower().strip())
        # Cap at 80 chars to stay well under Windows 260-char path limit
        safe_topic = safe_topic[:80].rstrip('_')
        project_name = f"{safe_topic}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    elif args.path_c:
        project_name = f"data_first_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    else:
        parser.error("--project is required when --topic is not provided")

    project_dir = ensure_project_dir(project_name)
    state = load_state(project_dir)

    if args.data:
        state["data_path"] = args.data
    if args.path_c:
        state["path_c"] = True
    state.setdefault("config", {})["stage2_mode"] = args.mode

    print(f"Project: {project_name}")
    print(f"Directory: {project_dir}")
    print(f"Stages: {args.from_stage} -> {args.to_stage}")
    if args.path_c:
        print(f"Path: C (data-first, topic from data)")
    elif args.data:
        print(f"User data: {args.data} (Path B)")
    else:
        print(f"Path: A (repository search)")

    # ── Lazy imports for stage modules ───────────────────────────────────
    from pipeline.stages import stage1_discovery
    from pipeline.stages import stage1_5_data_loading
    from pipeline.stages import stage2_ideation
    from pipeline.stages import stage2_5_selection
    from pipeline.stages import stage3_validation
    from pipeline.stages import stage3_3_quick_test
    from pipeline.stages import stage3_5_review
    from pipeline.stages import stage3_7_referee_preview
    from pipeline.stages import stage4_strategy
    from pipeline.stages import stage4_code
    from pipeline.stages import stage4_5_data_audit
    from pipeline.stages import stage4_7_code_review
    from pipeline.stages import stage5_writing
    from pipeline.stages import stage6_review
    from pipeline.stages import stage7_submission

    def _run_stage_4(project_dir, state):
        """Stage 4 = 4a (strategy) + 4b/c (code generation + execution)."""
        state = stage4_strategy.run(project_dir, state)
        state = stage4_code.run(project_dir, state)
        return state

    # ── Stage dispatch table ─────────────────────────────────────────────
    stage_runners = {
        1:   lambda: (_stage_header(1),   stage1_discovery.run(project_dir, args.topic, state, data_path=args.data, path_c=args.path_c))[-1],
        1.5: lambda: (_stage_header(1.5), stage1_5_data_loading.run(project_dir, state))[-1],
        2:   lambda: (_stage_header(2),   stage2_ideation.run(project_dir, state))[-1],
        2.5: lambda: (_stage_header(2.5), stage2_5_selection.run(project_dir, state))[-1],
        3:   lambda: (_stage_header(3),   stage3_validation.run(project_dir, state))[-1],
        3.3: lambda: (_stage_header(3.3), stage3_3_quick_test.run(project_dir, state))[-1],
        3.5: lambda: (_stage_header(3.5), stage3_5_review.run(project_dir, state))[-1],
        3.7: lambda: (_stage_header(3.7), stage3_7_referee_preview.run(project_dir, state))[-1],
        4:   lambda: (_stage_header(4),   _run_stage_4(project_dir, state))[-1],
        4.5: lambda: (_stage_header(4.5), stage4_5_data_audit.run(project_dir, state))[-1],
        4.7: lambda: (_stage_header(4.7), stage4_7_code_review.run(project_dir, state))[-1],
        5:   lambda: (_stage_header(5),   stage5_writing.run(project_dir, state))[-1],
        6:   lambda: (_stage_header(6),   stage6_review.run(project_dir, state))[-1],
        7:   lambda: (_stage_header(7),   stage7_submission.run(project_dir, state))[-1],
    }

    # ── Run stages in order ──────────────────────────────────────────────
    from pipeline.config import MAX_RR_ROUNDS

    start_idx = STAGE_ORDER.index(args.from_stage)
    end_idx = STAGE_ORDER.index(args.to_stage)

    stage_idx = start_idx
    while stage_idx <= end_idx:
        stage_num = STAGE_ORDER[stage_idx]
        runner = stage_runners.get(stage_num)
        if runner:
            state = runner()

            # Stop pipeline if a critical stage failed
            for check_key in ("stage4bc", "stage4a"):
                stage_info = state["stages"].get(check_key, {})
                if stage_info.get("status") == "failed":
                    print(f"\n  [STOP] {check_key} failed: {stage_info.get('reason', '?')}")
                    print(f"  Pipeline cannot continue. Fix the issue and re-run from --from-stage 4")
                    print_status(project_dir)
                    sys.exit(1)

            # Handle REJECT in Stage 2.5 — loop back to Stage 2
            if stage_num == 2.5:
                action = state["stages"].get("stage2_5", {}).get("action", "")
                if action == "REJECT":
                    print(f"\n  [loop] User rejected all ideas. Returning to Stage 2.")
                    stage_idx = STAGE_ORDER.index(2)
                    continue

            # Handle REJECTED_WEAK_ID in Stage 3 — loop back to Stage 2.5
            if stage_num == 3:
                s3_result = state["stages"].get("stage3", {}).get("result", {})
                if s3_result.get("status") == "REJECTED_WEAK_ID":
                    print(f"\n  [REJECT] Identification too weak (Level C/Tier 4, score < 5).")
                    print(f"  Returning to Stage 2.5 to select a different idea.")
                    # Reset stages 3 and 3.3 so they re-run
                    state["stages"]["stage3"] = {}
                    state["stages"]["stage3_3"] = {}
                    save_state(project_dir, state)
                    stage_idx = STAGE_ORDER.index(2.5)
                    continue

            # Handle FAIL in Stage 3.3 — loop back to Stage 2.5
            if stage_num == 3.3:
                s33 = state["stages"].get("stage3_3", {})
                if s33.get("action") == "retry_idea":
                    print(f"\n  [loop] Quick test failed. Returning to Stage 2.5.")
                    stage_idx = STAGE_ORDER.index(2.5)
                    continue

            # Handle REJECT in Stage 3.5 — loop back to Stage 2.5
            if stage_num == 3.5:
                action = state["stages"].get("stage3_5", {}).get("action", "")
                if action == "REJECT":
                    print(f"\n  [loop] User rejected strategy. Returning to Stage 2.5.")
                    stage_idx = STAGE_ORDER.index(2.5)
                    continue

            # Handle VETO in Stage 3.7 — loop back to Stage 2.5
            if stage_num == 3.7:
                status_37 = state["stages"].get("stage3_7", {}).get("status", "")
                if status_37 == "vetoed":
                    print(f"\n  [veto] Referee preview vetoed the design. Returning to Stage 2.5.")
                    # Reset stage3_7 so it re-runs after new idea selection
                    state["stages"]["stage3_7"] = {}
                    state["stages"]["stage3"] = {}
                    state["stages"]["stage3_5"] = {}
                    from pipeline.state import save_state
                    save_state(project_dir, state)
                    stage_idx = STAGE_ORDER.index(2.5)
                    continue

            # R&R loop: if Stage 6 says MAJOR_REVISIONS, re-run 5->6
            if stage_num == 6:
                rr_round = state["stages"].get("stage6", {}).get("rr_round", 1)
                decision = state["stages"].get("stage6", {}).get("decision", "")
                while decision == "MAJOR_REVISIONS" and rr_round < MAX_RR_ROUNDS:
                    print(f"\n  [R&R] Round {rr_round + 1}/{MAX_RR_ROUNDS}")
                    state = (_stage_header(5), stage5_writing.run(project_dir, state))[-1]
                    state = (_stage_header(6), stage6_review.run(project_dir, state))[-1]
                    rr_round = state["stages"].get("stage6", {}).get("rr_round", rr_round + 1)
                    decision = state["stages"].get("stage6", {}).get("decision", "")

                # Handle restart request from Stage 6 user choice "3"
                restart_from = state["stages"].get("stage6", {}).get("restart_from")
                if restart_from:
                    print(f"\n  [restart] Restarting pipeline from Stage {restart_from}")
                    # Clear the restart flag
                    state["stages"]["stage6"].pop("restart_from", None)
                    save_state(project_dir, state)
                    stage_idx = STAGE_ORDER.index(restart_from)
                    continue
        else:
            print(f"\n  [skip] Stage {stage_num} ({STAGE_NAMES[stage_num]}) - not yet implemented")

        stage_idx += 1

    # ── Final status ─────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print_status(project_dir)


if __name__ == "__main__":
    main()
