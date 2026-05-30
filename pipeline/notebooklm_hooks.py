"""NotebookLM integration hooks for pipeline stages.

Each hook is a lightweight, optional checkpoint. They:
  1. Check if notebooklm mode allows the action (from state config)
  2. Create a NotebookLMHelper
  3. Offer the action with human confirmation
  4. Never block the pipeline — failures are warnings, not errors
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _resolve_mode(state: dict) -> str:
    """Resolve notebooklm mode from pipeline state."""
    mode = state.get("config", {}).get("notebooklm", "")
    if mode in ("auto", "on", "off"):
        return mode
    try:
        from .config import NOTEBOOKLM_MODE
        return NOTEBOOKLM_MODE
    except ImportError:
        import os
        return os.environ.get("PIPELINE_NOTEBOOKLM", "auto")


# ── Stage 1 hook: Literature synthesis ─────────────────────────────────────

def stage1_notebooklm_checkpoint(
    project_dir: Path,
    state: dict,
    topic: str,
    seed_papers: list[dict] | None = None,
) -> None:
    """After Stage 1 discovery: offer to create NotebookLM + synthesize literature.

    Call this at the end of Stage 1's run(). If the user says yes:
      1. Create a notebook for the topic
      2. Add seed paper URLs/abstracts as sources
      3. Generate a briefing doc (literature synthesis)
    """
    mode = _resolve_mode(state)
    if mode == "off":
        return

    try:
        from .notebooklm_tools import NotebookLMHelper
    except ImportError:
        return

    helper = NotebookLMHelper(project_dir=project_dir, mode=mode)
    if not helper.available:
        return

    print(f"\n  [notebooklm] ── OPTIONAL: Literature Synthesis ──")
    print(f"  NotebookLM can synthesize your seed papers into a briefing doc.")
    print(f"  This helps you understand the literature landscape before ideation.")
    print(f"  Requires: Google account + notebooklm login.\n")

    try:
        # Step 1: Create notebook
        nb_id = helper.create_research_notebook(topic)
        if not nb_id:
            helper.close()
            return

        # Step 2: Add seed papers as sources (URLs + text)
        if seed_papers:
            for paper in seed_papers[:15]:  # max 15 to avoid rate limits
                url = paper.get("url", "")
                abstract = paper.get("abstract", "")
                title = paper.get("title", "")

                if url and "arxiv.org" in url:
                    helper.add_url(nb_id, url, title=title, auto_confirm=True)
                elif abstract:
                    helper.add_text(
                        nb_id,
                        title=title or "Paper abstract",
                        content=abstract[:3000],
                        auto_confirm=True,
                    )

        # Step 3: Generate briefing doc
        helper.generate_briefing_doc(nb_id)
        helper.close()

    except Exception as exc:
        print(f"  [notebooklm] Stage 1 checkpoint failed (non-blocking): {exc}")
        try:
            helper.close()
        except Exception:
            pass


# ── Stage 2 hook: Gap analysis ─────────────────────────────────────────────

def stage2_notebooklm_checkpoint(
    project_dir: Path,
    state: dict,
    topic: str,
    top_ideas: list[dict] | None = None,
) -> None:
    """After Stage 2 ideation: offer mind map for gap analysis.

    Creates a mind map from all uploaded papers to identify:
      - Connections between papers
      - Unexplored research angles
      - Potential replication targets
    """
    mode = _resolve_mode(state)
    if mode == "off":
        return

    try:
        from .notebooklm_tools import NotebookLMHelper
    except ImportError:
        return

    helper = NotebookLMHelper(project_dir=project_dir, mode=mode)
    if not helper.available:
        return

    print(f"\n  [notebooklm] ── OPTIONAL: Literature Gap Analysis ──")
    print(f"  NotebookLM can generate a mind map from your literature sources.")
    print(f"  This reveals connections and gaps — useful for refining ideas.\n")

    try:
        # Reuse or create notebook for this topic
        nb_id = helper.get_or_create_notebook(topic)
        if not nb_id:
            helper.close()
            return

        # Add generated ideas as text
        if top_ideas:
            ideas_text = "# Generated Research Ideas\n\n"
            for idea in top_ideas[:5]:
                ideas_text += f"## {idea.get('title', '?')}\n"
                ideas_text += f"- Method: {idea.get('method', '?')}\n"
                ideas_text += f"- ID level: {idea.get('identification_level', '?')}\n"
                ideas_text += f"- Pitch: {idea.get('pitch', '?')}\n\n"

            helper.add_text(
                nb_id,
                "Generated Research Ideas",
                ideas_text,
                auto_confirm=True,
            )

        # Generate mind map for gap analysis
        helper.generate_mind_map(nb_id)
        helper.close()

    except Exception as exc:
        print(f"  [notebooklm] Stage 2 checkpoint failed (non-blocking): {exc}")
        try:
            helper.close()
        except Exception:
            pass


# ── Stage 5 hook: Dissemination ────────────────────────────────────────────

def stage5_notebooklm_checkpoint(
    project_dir: Path,
    state: dict,
    topic: str,
    paper_pdf: str | Path | None = None,
) -> None:
    """After Stage 5 writing: offer audio overview + slides for dissemination.

    Call after paper is compiled. If paper_pdf exists, uploads it as source.
    Offers:
      1. Audio overview (podcast-style paper summary)
      2. Slide deck (conference presentation)
      3. Blog post (public dissemination)
    """
    mode = _resolve_mode(state)
    if mode == "off":
        return

    try:
        from .notebooklm_tools import NotebookLMHelper
    except ImportError:
        return

    helper = NotebookLMHelper(project_dir=project_dir, mode=mode)
    if not helper.available:
        return

    print(f"\n  [notebooklm] ── OPTIONAL: Paper Dissemination ──")
    print(f"  NotebookLM can generate dissemination materials from your paper:")
    print(f"    - Audio overview (podcast-style, great for social media)")
    print(f"    - Slide deck (conference presentation)")
    print(f"    - Blog post (public summary)")
    print(f"    - Infographic (visual summary)\n")

    try:
        nb_id = helper.get_or_create_notebook(topic)
        if not nb_id:
            helper.close()
            return

        # Upload the compiled paper PDF if available
        if paper_pdf:
            pdf_path = Path(paper_pdf)
            if pdf_path.exists():
                helper.add_paper_pdf(
                    nb_id, pdf_path,
                    title=f"Final Paper: {topic}",
                    auto_confirm=True,
                )

        # Offer each artifact independently (user picks)
        print(f"  Which artifact(s) would you like to generate?")
        print(f"  [1] Audio overview (podcast)")
        print(f"  [2] Slide deck (presentation)")
        print(f"  [3] Blog post")
        print(f"  [4] Infographic")
        print(f"  [5] All of the above")
        print(f"  [Enter] Skip all")

        import sys
        if sys.stdin.isatty():
            choice = input("  Choose [1-5/Enter]: ").strip()
        else:
            choice = ""

        if choice == "1":
            helper.generate_audio_overview(nb_id, auto_confirm=True)
        elif choice == "2":
            helper.generate_slide_deck(nb_id, auto_confirm=True)
        elif choice == "3":
            helper.generate_blog_post(nb_id, auto_confirm=True)
        elif choice == "4":
            helper.generate_infographic(nb_id, auto_confirm=True)
        elif choice == "5":
            helper.generate_audio_overview(nb_id, auto_confirm=True)
            helper.generate_slide_deck(nb_id, auto_confirm=True)
            helper.generate_blog_post(nb_id, auto_confirm=True)
            helper.generate_infographic(nb_id, auto_confirm=True)
        else:
            print("  [notebooklm] Skipped dissemination artifacts.")

        helper.close()

    except Exception as exc:
        print(f"  [notebooklm] Stage 5 checkpoint failed (non-blocking): {exc}")
        try:
            helper.close()
        except Exception:
            pass
