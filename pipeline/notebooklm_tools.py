"""NotebookLM integration for paper synthesis and dissemination.

Wraps notebooklm-py (https://github.com/teng-lin/notebooklm-py) for:
  - Literature synthesis: feed seed papers → briefing doc / study guide
  - Gap analysis: mind map from papers → identify replication angles
  - Dissemination: audio overview, slide deck, infographic from final paper

*** HUMAN-IN-THE-LOOP DESIGN ***
Every action that creates, modifies, or downloads requires explicit user
confirmation. Nothing happens automatically — this is by design. NotebookLM
uses undocumented Google APIs that can break, rate-limit, or produce
low-quality output. Human judgment is mandatory before every action.

Modes (controlled by --notebooklm flag or PIPELINE_NOTEBOOKLM env var):
  "off" — skip entirely (default in non-interactive runs)
  "auto" — offer NotebookLM actions at checkpoints, require confirmation
  "on" — same as auto but fail if notebooklm-py not installed/logged in

Requires:
  pip install "notebooklm-py[browser]"
  playwright install chromium
  notebooklm login

Typical usage:
    from pipeline.notebooklm_tools import NotebookLMHelper

    helper = NotebookLMHelper(project_dir="./projects/my_paper", mode="auto")
    if helper.available:
        nb_id = helper.create_research_notebook("Labor Economics")
        helper.add_papers(nb_id, ["paper1.pdf", "paper2.pdf"])
        helper.generate_briefing_doc(nb_id)
        helper.generate_mind_map(nb_id)
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

_notebooklm_installed: bool | None = None
_notebooklm_logged_in: bool | None = None


def is_notebooklm_installed() -> bool:
    """Raw check: is the notebooklm package importable?"""
    global _notebooklm_installed
    if _notebooklm_installed is None:
        try:
            import notebooklm  # noqa: F401
            _notebooklm_installed = True
        except ImportError:
            _notebooklm_installed = False
    return _notebooklm_installed


def is_notebooklm_logged_in() -> bool:
    """Check if notebooklm has valid auth storage."""
    global _notebooklm_logged_in
    if _notebooklm_logged_in is not None:
        return _notebooklm_logged_in
    if not is_notebooklm_installed():
        _notebooklm_logged_in = False
        return False
    try:
        from notebooklm import DEFAULT_STORAGE_PATH
        storage = Path(DEFAULT_STORAGE_PATH)
        if storage.exists() and storage.stat().st_size > 100:
            _notebooklm_logged_in = True
            return True
    except Exception:
        pass
    _notebooklm_logged_in = False
    return False


def _resolve_notebooklm_mode() -> str:
    """Resolve effective notebooklm mode: config → env → default 'auto'."""
    try:
        from .config import NOTEBOOKLM_MODE
        return NOTEBOOKLM_MODE
    except ImportError:
        import os
        return os.environ.get("PIPELINE_NOTEBOOKLM", "auto")


def is_notebooklm_available() -> bool:
    """Mode-aware check: should NotebookLM be used?"""
    mode = _resolve_notebooklm_mode()
    if mode == "off":
        return False
    if not is_notebooklm_installed():
        return False
    if not is_notebooklm_logged_in():
        return False
    return True


# ---------------------------------------------------------------------------
# Human-in-the-loop confirmation
# ---------------------------------------------------------------------------

def _confirm(action: str, detail: str = "") -> bool:
    """Ask user to confirm a NotebookLM action. Returns True if approved."""
    if not sys.stdin.isatty():
        print(f"  [notebooklm] Non-interactive: skipping '{action}'")
        return False

    print(f"\n  [notebooklm] ── ACTION REQUIRES CONFIRMATION ──")
    print(f"  Action: {action}")
    if detail:
        for line in detail.strip().split("\n"):
            print(f"  {line}")
    print()

    while True:
        choice = input(f"  Proceed? [y/N]: ").strip().lower()
        if choice in ("y", "yes"):
            return True
        if choice in ("", "n", "no"):
            print(f"  [notebooklm] Skipped: '{action}'")
            return False
        print("  Enter y or n.")


# ---------------------------------------------------------------------------
# Helper: async → sync
# ---------------------------------------------------------------------------

def _run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=1800)  # up to 30 min
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ---------------------------------------------------------------------------
# NotebookLMHelper
# ---------------------------------------------------------------------------

class NotebookLMHelper:
    """Programmatic NotebookLM with mandatory human confirmation.

    Parameters
    ----------
    project_dir : str | Path
        Project directory for saving downloaded artifacts.
    mode : str
        "auto" (default), "on" (require), "off" (skip).
    verbose : bool
        Print progress messages.
    """

    def __init__(
        self,
        project_dir: str | Path = ".",
        mode: str = "auto",
        verbose: bool = True,
    ):
        self.project_dir = Path(project_dir)
        self.mode = mode
        self.verbose = verbose
        self._client: Any = None
        self._available: bool | None = None

    # -- Properties -----------------------------------------------------------

    @property
    def available(self) -> bool:
        """Is NotebookLM ready to use? (installed + logged in + mode allows)."""
        if self._available is None:
            if self.mode == "off":
                self._available = False
            elif not is_notebooklm_installed():
                if self.mode == "on":
                    print(
                        "  [notebooklm] Mode is 'on' but notebooklm-py not installed.\n"
                        "  Install: pip install \"notebooklm-py[browser]\"\n"
                        "           playwright install chromium\n"
                        "           notebooklm login"
                    )
                self._available = False
            elif not is_notebooklm_logged_in():
                if self.mode == "on":
                    print(
                        "  [notebooklm] Mode is 'on' but not logged in.\n"
                        "  Run: notebooklm login"
                    )
                self._available = False
            else:
                self._available = True
        return self._available

    @property
    def client(self):
        """Lazy-init the NotebookLMClient."""
        if self._client is None and self.available:
            try:
                from notebooklm import NotebookLMClient

                async def _init():
                    return await NotebookLMClient.from_storage()

                ctx = _run_async(_init())
                # __aenter__ returns the client
                self._client = _run_async(ctx.__aenter__())
                if self.verbose:
                    print("  [notebooklm] Client initialized.")
            except Exception as exc:
                print(f"  [notebooklm] Init failed: {exc}")
                self._available = False
        return self._client

    def close(self):
        """Close the client connection."""
        if self._client is not None:
            try:

                async def _close():
                    await self._client.__aexit__(None, None, None)

                _run_async(_close())
            except Exception:
                pass
            self._client = None

    # -- Notebook management --------------------------------------------------

    def create_research_notebook(
        self,
        topic: str,
        auto_confirm: bool = False,
    ) -> str | None:
        """Create a NotebookLM notebook for a research topic.

        Requires human confirmation unless auto_confirm=True.
        Returns notebook_id or None if skipped/failed.
        """
        if not self.client:
            return None

        action = f"Create NotebookLM notebook for topic: '{topic}'"
        detail = (
            "This creates a new Google NotebookLM notebook. You can add paper\n"
            "PDFs as sources and generate briefing docs, mind maps, and more.\n"
            "Requires: Google account, NotebookLM access."
        )

        if not auto_confirm and not _confirm(action, detail):
            return None

        try:

            async def _create():
                nb = await self.client.notebooks.create(
                    f"[Papers-HQ] {topic}"
                )
                return nb.id

            nb_id = _run_async(_create())
            if self.verbose:
                print(f"  [notebooklm] Created notebook: {nb_id}")
            return nb_id
        except Exception as exc:
            print(f"  [notebooklm] Create notebook failed: {exc}")
            return None

    def get_or_create_notebook(
        self,
        topic: str,
        auto_confirm: bool = False,
    ) -> str | None:
        """Get existing matching notebook or create a new one."""
        if not self.client:
            return None

        # Try to find an existing notebook first
        try:

            async def _list():
                return await self.client.notebooks.list()

            notebooks = _run_async(_list())
            for nb in notebooks:
                if f"[Papers-HQ] {topic}" in (nb.title or ""):
                    if self.verbose:
                        print(f"  [notebooklm] Reusing notebook: {nb.id}")
                    return nb.id
        except Exception:
            pass

        return self.create_research_notebook(topic, auto_confirm=auto_confirm)

    # -- Source management ----------------------------------------------------

    def add_paper_pdf(
        self,
        notebook_id: str,
        pdf_path: str | Path,
        title: str | None = None,
        auto_confirm: bool = False,
    ) -> bool:
        """Add a paper PDF as a source to a notebook.

        Requires confirmation for each file unless auto_confirm=True.
        """
        if not self.client:
            return False

        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            print(f"  [notebooklm] PDF not found: {pdf_path}")
            return False

        title = title or pdf_path.stem

        if not auto_confirm and not _confirm(
            f"Add PDF to notebook: {title}",
            f"File: {pdf_path}\nSize: {pdf_path.stat().st_size / 1024:.0f} KB"
        ):
            return False

        try:

            async def _add():
                return await self.client.sources.add_file(
                    notebook_id,
                    str(pdf_path),
                    title=title,
                    wait=True,
                    wait_timeout=120,
                )

            source = _run_async(_add())
            if self.verbose:
                print(f"  [notebooklm] Added source: {title}")
            return True
        except Exception as exc:
            print(f"  [notebooklm] Add PDF failed for '{title}': {exc}")
            return False

    def add_papers_batch(
        self,
        notebook_id: str,
        pdf_paths: list[str | Path],
        auto_confirm_all: bool = False,
    ) -> int:
        """Add multiple paper PDFs. Returns count of successful uploads.

        First asks for batch confirmation, then uploads each file.
        Individual file confirmations skipped if auto_confirm_all=True.
        """
        if not self.client or not pdf_paths:
            return 0

        valid_paths = [Path(p) for p in pdf_paths if Path(p).exists()]
        if not valid_paths:
            print("  [notebooklm] No valid PDF files found.")
            return 0

        if not auto_confirm_all and not _confirm(
            f"Add {len(valid_paths)} paper PDF(s) to notebook",
            "Files:\n" + "\n".join(f"  - {p.name}" for p in valid_paths[:10])
        ):
            return 0

        count = 0
        for pdf_path in valid_paths:
            if self.add_paper_pdf(
                notebook_id, pdf_path, auto_confirm=True
            ):
                count += 1

        if self.verbose:
            print(f"  [notebooklm] Added {count}/{len(valid_paths)} PDFs")
        return count

    def add_url(
        self,
        notebook_id: str,
        url: str,
        title: str | None = None,
        auto_confirm: bool = False,
    ) -> bool:
        """Add a URL (paper link, dataset, etc.) as a source."""
        if not self.client:
            return False

        if not auto_confirm and not _confirm(
            f"Add URL to notebook: {title or url[:60]}",
            f"URL: {url}"
        ):
            return False

        try:

            async def _add():
                return await self.client.sources.add_url(
                    notebook_id, url, wait=True, wait_timeout=120
                )

            source = _run_async(_add())
            if self.verbose:
                print(f"  [notebooklm] Added URL: {url[:80]}")
            return True
        except Exception as exc:
            print(f"  [notebooklm] Add URL failed: {exc}")
            return False

    def add_text(
        self,
        notebook_id: str,
        title: str,
        content: str,
        auto_confirm: bool = False,
    ) -> bool:
        """Add text content (abstract, notes, literature summary) as a source."""
        if not self.client:
            return False

        if not auto_confirm and not _confirm(
            f"Add text note to notebook: {title}",
            f"Content preview: {content[:200]}..."
        ):
            return False

        try:

            async def _add():
                return await self.client.sources.add_text(
                    notebook_id, title=title, content=content, wait=True
                )

            source = _run_async(_add())
            if self.verbose:
                print(f"  [notebooklm] Added text: {title}")
            return True
        except Exception as exc:
            print(f"  [notebooklm] Add text failed: {exc}")
            return False

    # -- Artifact generation --------------------------------------------------

    def generate_briefing_doc(
        self,
        notebook_id: str,
        auto_confirm: bool = False,
    ) -> str | None:
        """Generate a briefing document from notebook sources.

        This synthesizes all sources into a structured literature review.
        Saves as Markdown in project_dir/notebooklm/.

        Returns path to downloaded file, or None.
        """
        if not self.client:
            return None

        action = "Generate briefing document (literature synthesis)"
        detail = (
            "NotebookLM will synthesize all sources into a structured document.\n"
            "This takes 1-5 minutes. The result will be saved as Markdown."
        )

        if not auto_confirm and not _confirm(action, detail):
            return None

        try:
            if self.verbose:
                print("  [notebooklm] Generating briefing doc...")

            async def _generate():
                status = await self.client.artifacts.generate_report(
                    notebook_id,
                    report_format="briefing_doc",
                )
                await self.client.artifacts.wait_for_completion(
                    notebook_id, status.task_id, timeout=600
                )
                return status

            _run_async(_generate())
            return self._download_artifact(
                notebook_id, "report", "briefing_doc.md"
            )
        except Exception as exc:
            print(f"  [notebooklm] Briefing doc failed: {exc}")
            return None

    def generate_study_guide(
        self,
        notebook_id: str,
        auto_confirm: bool = False,
    ) -> str | None:
        """Generate a study guide — structured deep-dive into sources.

        More detailed than briefing doc. Good for understanding methodology.
        """
        if not self.client:
            return None

        if not auto_confirm and not _confirm(
            "Generate study guide (deep-dive into paper methodology)",
            "This creates a detailed study guide from all sources.\n"
            "Useful for understanding methods, data, and identification."
        ):
            return None

        try:
            if self.verbose:
                print("  [notebooklm] Generating study guide...")

            async def _generate():
                status = await self.client.artifacts.generate_report(
                    notebook_id,
                    report_format="study_guide",
                )
                await self.client.artifacts.wait_for_completion(
                    notebook_id, status.task_id, timeout=600
                )
                return status

            _run_async(_generate())
            return self._download_artifact(
                notebook_id, "report", "study_guide.md"
            )
        except Exception as exc:
            print(f"  [notebooklm] Study guide failed: {exc}")
            return None

    def generate_mind_map(
        self,
        notebook_id: str,
        auto_confirm: bool = False,
    ) -> str | None:
        """Generate an interactive mind map from all sources.

        Excellent for gap analysis — reveals connections between papers
        and identifies unexplored research angles.

        Returns path to JSON file.
        """
        if not self.client:
            return None

        if not auto_confirm and not _confirm(
            "Generate mind map (literature gap analysis)",
            "Creates a hierarchical map of concepts across all sources.\n"
            "Useful for identifying research gaps and replication angles."
        ):
            return None

        try:
            if self.verbose:
                print("  [notebooklm] Generating mind map...")

            async def _generate():
                return await self.client.mind_maps.generate(
                    notebook_id,
                    kind="interactive",
                    wait=True,
                )

            _run_async(_generate())
            return self._download_artifact(
                notebook_id, "mind_map", "mind_map.json"
            )
        except Exception as exc:
            print(f"  [notebooklm] Mind map failed: {exc}")
            return None

    def generate_audio_overview(
        self,
        notebook_id: str,
        instructions: str = "",
        auto_confirm: bool = False,
    ) -> str | None:
        """Generate an audio overview (podcast-style) from notebook sources.

        Great for dissemination — share the podcast version of the paper.
        Takes 3-10 minutes. Returns path to MP3.
        """
        if not self.client:
            return None

        action = "Generate audio overview (podcast-style paper summary)"
        detail = (
            "NotebookLM will create a conversational audio summary of all sources.\n"
            "This takes 3-10 minutes. Output: MP3 file.\n"
            "Great for sharing on social media or listening to your literature."
        )
        if instructions:
            detail += f"\nCustom instructions: {instructions}"

        if not auto_confirm and not _confirm(action, detail):
            return None

        try:
            if self.verbose:
                print("  [notebooklm] Generating audio overview (this may take several minutes)...")

            async def _generate():
                status = await self.client.artifacts.generate_audio(
                    notebook_id,
                    instructions=instructions or None,
                    language="en",
                )
                await self.client.artifacts.wait_for_completion(
                    notebook_id, status.task_id, timeout=1200
                )
                return status

            _run_async(_generate())
            return self._download_artifact(
                notebook_id, "audio", "audio_overview.mp3"
            )
        except Exception as exc:
            print(f"  [notebooklm] Audio overview failed: {exc}")
            return None

    def generate_slide_deck(
        self,
        notebook_id: str,
        auto_confirm: bool = False,
    ) -> str | None:
        """Generate a slide deck (presentation) from notebook sources.

        Returns path to PDF (or PPTX if available).
        """
        if not self.client:
            return None

        if not auto_confirm and not _confirm(
            "Generate slide deck (conference presentation)",
            "Creates presentation slides from all sources.\n"
            "Output: PDF. Good starting point for conference talks."
        ):
            return None

        try:
            if self.verbose:
                print("  [notebooklm] Generating slide deck...")

            async def _generate():
                status = await self.client.artifacts.generate_slide_deck(
                    notebook_id,
                )
                await self.client.artifacts.wait_for_completion(
                    notebook_id, status.task_id, timeout=600
                )
                return status

            _run_async(_generate())
            return self._download_artifact(
                notebook_id, "slide_deck", "slide_deck.pdf"
            )
        except Exception as exc:
            print(f"  [notebooklm] Slide deck failed: {exc}")
            return None

    def generate_infographic(
        self,
        notebook_id: str,
        auto_confirm: bool = False,
    ) -> str | None:
        """Generate an infographic summarizing key findings.

        Returns path to PNG.
        """
        if not self.client:
            return None

        if not auto_confirm and not _confirm(
            "Generate infographic (visual summary of findings)",
            "Creates a visual summary infographic. Output: PNG."
        ):
            return None

        try:
            if self.verbose:
                print("  [notebooklm] Generating infographic...")

            async def _generate():
                status = await self.client.artifacts.generate_infographic(
                    notebook_id,
                )
                await self.client.artifacts.wait_for_completion(
                    notebook_id, status.task_id, timeout=600
                )
                return status

            _run_async(_generate())
            return self._download_artifact(
                notebook_id, "infographic", "infographic.png"
            )
        except Exception as exc:
            print(f"  [notebooklm] Infographic failed: {exc}")
            return None

    def generate_blog_post(
        self,
        notebook_id: str,
        custom_prompt: str = "",
        auto_confirm: bool = False,
    ) -> str | None:
        """Generate a blog post from notebook sources.

        Useful for science communication / public dissemination.
        """
        if not self.client:
            return None

        if not auto_confirm and not _confirm(
            "Generate blog post (public dissemination)",
            "Creates a blog-post-style summary. Output: Markdown."
        ):
            return None

        try:
            if self.verbose:
                print("  [notebooklm] Generating blog post...")

            async def _generate():
                kwargs = {"report_format": "blog_post"}
                if custom_prompt:
                    kwargs["custom_prompt"] = custom_prompt
                    kwargs["extra_instructions"] = custom_prompt
                status = await self.client.artifacts.generate_report(
                    notebook_id, **kwargs
                )
                await self.client.artifacts.wait_for_completion(
                    notebook_id, status.task_id, timeout=600
                )
                return status

            _run_async(_generate())
            return self._download_artifact(
                notebook_id, "report", "blog_post.md"
            )
        except Exception as exc:
            print(f"  [notebooklm] Blog post failed: {exc}")
            return None

    # -- Chat / Q&A -----------------------------------------------------------

    def ask(
        self,
        notebook_id: str,
        question: str,
        auto_confirm: bool = False,
    ) -> str | None:
        """Ask a question about the notebook sources.

        Uses NotebookLM's RAG over all uploaded sources.
        """
        if not self.client:
            return None

        if not auto_confirm and not _confirm(
            f"Ask NotebookLM: {question[:80]}...",
            "NotebookLM will answer using RAG over all uploaded sources."
        ):
            return None

        try:

            async def _ask():
                result = await self.client.chat.ask(
                    notebook_id, question
                )
                return result.answer

            answer = _run_async(_ask())
            if self.verbose:
                print(f"  [notebooklm] Answer: {answer[:200]}...")
            return answer
        except Exception as exc:
            print(f"  [notebooklm] Chat failed: {exc}")
            return None

    # -- Internal: download helpers -------------------------------------------

    def _download_artifact(
        self,
        notebook_id: str,
        artifact_type: str,
        filename: str,
    ) -> str | None:
        """Download the latest artifact of given type. Returns path or None."""
        output_dir = self.project_dir / "notebooklm"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = Path(filename).stem
        ext = Path(filename).suffix
        output_path = output_dir / f"{stem}_{timestamp}{ext}"

        try:
            download_map = {
                "report": self.client.artifacts.download_report,
                "audio": self.client.artifacts.download_audio,
                "slide_deck": self.client.artifacts.download_slide_deck,
                "infographic": self.client.artifacts.download_infographic,
                "mind_map": self.client.artifacts.download_mind_map,
                "quiz": self.client.artifacts.download_quiz,
                "flashcards": self.client.artifacts.download_flashcards,
                "data_table": self.client.artifacts.download_data_table,
            }

            download_fn = download_map.get(artifact_type)
            if download_fn is None:
                print(f"  [notebooklm] Unknown artifact type: {artifact_type}")
                return None

            async def _download():
                return await download_fn(
                    notebook_id, str(output_path)
                )

            result = _run_async(_download())
            if self.verbose:
                print(f"  [notebooklm] Downloaded: {output_path.name}")
            return str(output_path)
        except Exception as exc:
            print(f"  [notebooklm] Download {artifact_type} failed: {exc}")
            return None


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def create_research_notebook(
    topic: str,
    pdf_paths: list[str | Path] | None = None,
    project_dir: str | Path = ".",
    mode: str = "auto",
    auto_confirm_all: bool = False,
) -> tuple[str | None, NotebookLMHelper | None]:
    """One-shot: create notebook + add papers. Returns (notebook_id, helper).

    If auto_confirm_all=False (default), each step requires human confirmation.
    """
    helper = NotebookLMHelper(project_dir=project_dir, mode=mode)
    if not helper.available:
        return None, helper

    nb_id = helper.create_research_notebook(topic, auto_confirm=auto_confirm_all)
    if not nb_id:
        return None, helper

    if pdf_paths:
        helper.add_papers_batch(
            nb_id, pdf_paths, auto_confirm_all=auto_confirm_all
        )

    return nb_id, helper
