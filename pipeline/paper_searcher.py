"""Paper search and download via paperdl + Semantic Scholar fallback.

Integrates paperdl (https://github.com/CharlesPikachu/paperdl) for:
  - arXiv, OpenReview, ACL Anthology, bioRxiv, medRxiv, PMLR, PMC
  - Async search + PDF download across all sources
  - Falls back to Semantic Scholar API when paperdl unavailable or disabled

Modes (controlled by --paperdl flag or PIPELINE_PAPERDL env var):
  "auto" — use paperdl if installed, fall back to Semantic Scholar (default)
  "on"   — require paperdl; fail if not installed
  "off"  — skip paperdl entirely, Semantic Scholar only

Typical usage:
    from pipeline.paper_searcher import search_papers, download_paper, PaperSearcher

    # Quick search
    papers = search_papers("minimum wage employment", max_results=10)

    # With specific sources
    papers = search_papers("causal inference", sources=["arxiv", "openreview"])

    # Download a paper PDF
    pdf_path = download_paper(papers[0], output_dir="./papers")

    # Reusable searcher (keeps clients warm across calls)
    searcher = PaperSearcher(sources=["arxiv", "semantic_scholar"], mode="auto")
    papers = searcher.search("difference in differences")
    path = searcher.download(papers[0])
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paper info dataclass (pipeline-compatible)
# ---------------------------------------------------------------------------


@dataclass
class PaperInfo:
    """Normalized paper metadata — compatible with pipeline's existing format."""

    title: str
    authors: str  # "Author1, Author2 et al."
    year: int | None
    venue: str
    citation_count: int
    abstract: str
    url: str
    open_access_pdf: str  # direct PDF URL if available
    external_ids: dict[str, str] = field(default_factory=dict)
    source: str = ""  # "arxiv", "semantic_scholar", "openreview", etc.

    # Extra fields from paperdl / Semantic Scholar
    doi: str = ""
    publication_date: str = ""
    categories: list[str] = field(default_factory=list)
    comment: str = ""
    journal_ref: str = ""

    def to_pipeline_dict(self) -> dict[str, Any]:
        """Convert to dict format expected by existing pipeline stages."""
        return {
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "venue": self.venue,
            "citationCount": self.citation_count,
            "abstract": self.abstract,
            "url": self.url,
            "openAccessPdf": {"url": self.open_access_pdf} if self.open_access_pdf else {},
            "externalIds": self.external_ids,
            "source": self.source,
            "doi": self.doi,
        }


# ---------------------------------------------------------------------------
# Paper source registry
# ---------------------------------------------------------------------------

# Sources supported by paperdl (canonical names)
PAPERDL_SOURCES = [
    "arxiv",
    "openreview",
    "acl",
    "aclanthology",
    "biorxiv",
    "medrxiv",
    "pmlr",
    "pmc",
    "pmcoa",
]

# Map paperdl source → our canonical name
PAPERDL_SOURCE_MAP: dict[str, str] = {
    "arxiv": "arxiv",
    "openreview": "openreview",
    "acl": "acl",
    "acl_anthology": "acl",
    "acl-anthology": "acl",
    "biorxiv": "biorxiv",
    "medrxiv": "medrxiv",
    "pmlr": "pmlr",
    "pmc": "pmc",
    "pmc_oa": "pmc",
    "pmcoa": "pmc",
}

# Map source → display label
SOURCE_LABELS: dict[str, str] = {
    "arxiv": "arXiv",
    "openreview": "OpenReview",
    "acl": "ACL Anthology",
    "biorxiv": "bioRxiv",
    "medrxiv": "medRxiv",
    "pmlr": "PMLR",
    "pmc": "PubMed Central",
    "semantic_scholar": "Semantic Scholar",
}

# Sources likely to have economics/social-science papers
ECON_RELEVANT_SOURCES = [
    "arxiv",       # econ.GN, econ.EM, stat.AP, stat.ME
    "openreview",  # conference papers (sometimes econ-adjacent)
    "pmlr",        # ML proceedings (causal ML, policy learning)
    "pmc",         # health economics, public health
]


# ---------------------------------------------------------------------------
# PaperSearcher — main interface
# ---------------------------------------------------------------------------


class PaperSearcher:
    """Unified paper search across paperdl + Semantic Scholar.

    Caches client instances across calls. All methods are synchronous
    (async internals handled via asyncio.run).

    Parameters
    ----------
    sources : list[str]
        Which sources to search. Default: econ-relevant subset.
        Use "all" for all paperdl sources + Semantic Scholar.
    mode : str
        "auto" — use paperdl if installed (default)
        "on"   — require paperdl, fail if missing
        "off"  — skip paperdl, Semantic Scholar only
    paperdl_kwargs : dict
        Extra kwargs passed to paperdl.PaperClient.__init__.
    """

    def __init__(
        self,
        sources: list[str] | None = None,
        mode: str = "auto",
        paperdl_kwargs: dict[str, Any] | None = None,
    ):
        if sources is None:
            sources = list(ECON_RELEVANT_SOURCES)
        if "all" in sources:
            sources = PAPERDL_SOURCES + ["semantic_scholar"]

        self._mode = mode
        self._sources = sources
        self._paperdl_kwargs = paperdl_kwargs or {}
        self._paperdl_client: Any = None  # lazy
        self._use_semantic_scholar = "semantic_scholar" in sources
        self._paperdl_sources = [s for s in sources if s != "semantic_scholar"]

        # Enforce mode
        if mode == "off":
            self._paperdl_sources = []
        elif mode == "on":
            if not is_paperdl_installed():
                raise RuntimeError(
                    "paperdl mode is 'on' but paperdl is not installed. "
                    "Install with: pip install paperdl  "
                    "Or use --paperdl off to skip paperdl."
                )

    # -- Lazy paperdl client -------------------------------------------------

    @property
    def paperdl_client(self):
        """Lazy-initialize paperdl.PaperClient."""
        if self._paperdl_client is None and self._paperdl_sources:
            self._paperdl_client = _init_paperdl_client(
                self._paperdl_sources, self._paperdl_kwargs
            )
        return self._paperdl_client

    # -- Search ---------------------------------------------------------------

    def search(
        self,
        query: str,
        max_results: int = 20,
        sources: list[str] | None = None,
        deduplicate: bool = True,
    ) -> list[PaperInfo]:
        """Search papers across configured sources.

        Parameters
        ----------
        query : str
            Search query.
        max_results : int
            Max results per source. Total may be up to max_results × n_sources.
        sources : list[str] | None
            Override sources for this call. None = use configured sources.
        deduplicate : bool
            Remove duplicate papers (by title).

        Returns
        -------
        list[PaperInfo]
        """
        use_sources = sources or self._sources
        papers: list[PaperInfo] = []

        # 1. paperdl search (async → sync)
        paperdl_srcs = [s for s in use_sources if s != "semantic_scholar"]
        if paperdl_srcs and self.paperdl_client is not None:
            try:
                papers.extend(
                    _run_async(
                        _search_paperdl(
                            self.paperdl_client,
                            query,
                            max_results=max_results,
                            sources=paperdl_srcs,
                        )
                    )
                )
            except Exception as exc:
                print(f"  [paperdl] Search failed: {exc}")

        # 2. Semantic Scholar fallback
        if "semantic_scholar" in use_sources:
            try:
                ss_papers = _search_semantic_scholar(query, max_results=max_results)
                papers.extend(ss_papers)
            except Exception as exc:
                print(f"  [semantic-scholar] Search failed: {exc}")

        # 3. If everything failed, try Semantic Scholar as ultimate fallback
        if not papers and "semantic_scholar" not in use_sources:
            try:
                papers = _search_semantic_scholar(query, max_results=max_results)
            except Exception:
                pass

        # Deduplicate by title
        if deduplicate and papers:
            seen: set[str] = set()
            unique: list[PaperInfo] = []
            for p in papers:
                key = p.title.strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    unique.append(p)
            papers = unique

        return papers

    def download(
        self,
        paper: PaperInfo | dict,
        output_dir: str | Path = ".",
        overwrite: bool = False,
    ) -> str | None:
        """Download a paper PDF.

        Parameters
        ----------
        paper : PaperInfo | dict
            Paper to download (PaperInfo or pipeline dict).
        output_dir : str | Path
            Directory to save PDF.
        overwrite : bool
            Overwrite existing file.

        Returns
        -------
        str | None
            Path to downloaded PDF, or None if download failed.
        """
        if isinstance(paper, dict):
            paper = _dict_to_paper_info(paper)

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Try paperdl download
        if paper.source in PAPERDL_SOURCES and self.paperdl_client is not None:
            try:
                path = _run_async(
                    _download_paperdl(
                        self.paperdl_client,
                        paper,
                        str(output_dir),
                        overwrite,
                    )
                )
                if path:
                    return path
            except Exception as exc:
                print(f"  [paperdl] Download failed for {paper.title[:60]}: {exc}")

        # 2. Try direct PDF URL
        pdf_url = paper.open_access_pdf
        if not pdf_url and isinstance(paper, dict):
            pdf_url = (paper.get("openAccessPdf") or {}).get("url", "")

        if pdf_url:
            try:
                return _download_direct(pdf_url, paper.title, output_dir, overwrite)
            except Exception as exc:
                print(f"  [pdf] Direct download failed: {exc}")

        # 3. Try Semantic Scholar OA PDF
        if paper.external_ids:
            try:
                ss_pdf = _fetch_semantic_scholar_pdf(paper, output_dir)
                if ss_pdf:
                    return ss_pdf
            except Exception:
                pass

        return None

    def download_papers(
        self,
        papers: list[PaperInfo | dict],
        output_dir: str | Path = ".",
        overwrite: bool = False,
    ) -> dict[str, str | None]:
        """Download multiple papers. Returns {title: path_or_None}."""
        results: dict[str, str | None] = {}
        for paper in papers:
            title = paper.get("title", "") if isinstance(paper, dict) else paper.title
            path = self.download(paper, output_dir, overwrite)
            results[title] = path
        return results

    def list_sources(self) -> list[dict[str, str]]:
        """Return available sources with labels."""
        available = []
        for s in self._sources:
            available.append({
                "id": s,
                "label": SOURCE_LABELS.get(s, s),
                "type": "paperdl" if s in PAPERDL_SOURCES else "api",
            })
        return available


# ---------------------------------------------------------------------------
# Convenience functions (module-level, session-less)
# ---------------------------------------------------------------------------


def search_papers(
    query: str,
    max_results: int = 20,
    sources: list[str] | None = None,
    mode: str = "auto",
) -> list[dict]:
    """Quick one-shot search. Returns pipeline-compatible dicts."""
    searcher = PaperSearcher(sources=sources, mode=mode)
    papers = searcher.search(query, max_results=max_results)
    return [p.to_pipeline_dict() for p in papers]


def download_paper(
    paper: dict | PaperInfo,
    output_dir: str | Path = ".",
    sources: list[str] | None = None,
    mode: str = "auto",
) -> str | None:
    """Quick one-shot download. Returns path or None."""
    searcher = PaperSearcher(sources=sources, mode=mode)
    return searcher.download(paper, output_dir)


# ---------------------------------------------------------------------------
# Internal: paperdl integration
# ---------------------------------------------------------------------------


def _init_paperdl_client(
    sources: list[str],
    kwargs: dict[str, Any],
) -> Any:
    """Initialize paperdl.PaperClient for given sources. Returns None if unavailable."""
    try:
        import paperdl  # type: ignore[import-untyped]
    except ImportError:
        print(
            "  [paperdl] Not installed. Install with: "
            "pip install paperdl  (or pip install git+https://github.com/CharlesPikachu/paperdl.git)"
        )
        return None

    # Map our canonical names to paperdl's expected names
    client_map = PAPERDL_SOURCE_MAP
    paperdl_names = []
    for s in sources:
        mapped = client_map.get(s, s)
        paperdl_names.append(mapped)

    if not paperdl_names:
        return None

    try:
        client = paperdl.PaperClient(
            clients=paperdl_names,
            concurrency=3,
            show_progress=False,
            verbose=False,
            **kwargs,
        )
        print(f"  [paperdl] Initialized: {', '.join(SOURCE_LABELS.get(s, s) for s in sources)}")
        return client
    except Exception as exc:
        print(f"  [paperdl] Init failed: {exc}")
        return None


async def _search_paperdl(
    client: Any,
    query: str,
    max_results: int = 20,
    sources: list[str] | None = None,
) -> list[PaperInfo]:
    """Run paperdl search asynchronously."""
    results: list[PaperInfo] = []

    async with client:
        raw_results = await client.search(
            query,
            total_results=max_results,
            clients=sources,
            deduplicate=True,
        )

        if isinstance(raw_results, list):
            for r in raw_results:
                results.append(_paperdl_to_paper_info(r))

    return results


async def _download_paperdl(
    client: Any,
    paper: PaperInfo,
    output_dir: str,
    overwrite: bool = False,
) -> str | None:
    """Download via paperdl client."""
    async with client:
        # paperdl expects PaperInfo namedtuples — we pass our dataclass;
        # try mapping back or passing the URL/ID
        result = await client.download(
            [paper],
            output_dir=output_dir,
            overwrite=overwrite,
        )
        if isinstance(result, list) and result:
            return str(result[0]) if result[0] else None
        if isinstance(result, (str, Path)):
            return str(result)
    return None


def _paperdl_to_paper_info(raw: Any) -> PaperInfo:
    """Convert paperdl PaperInfo namedtuple to our dataclass."""
    # paperdl uses a namedtuple/dataclass with fields like:
    # title, authors, year, venue, source, identity_key, download_url, ...
    authors_raw = getattr(raw, "authors", "") or ""
    if isinstance(authors_raw, list):
        authors_str = ", ".join(authors_raw[:5])
        if len(authors_raw) > 5:
            authors_str += " et al."
    else:
        authors_str = str(authors_raw)

    return PaperInfo(
        title=getattr(raw, "title", "") or "",
        authors=authors_str,
        year=_safe_int(getattr(raw, "year", None)),
        venue=getattr(raw, "venue", "") or "",
        citation_count=_safe_int(getattr(raw, "citation_count", 0)),
        abstract=getattr(raw, "abstract", "") or "",
        url=getattr(raw, "url", "") or "",
        open_access_pdf=getattr(raw, "download_url", "") or "",
        external_ids={"doi": getattr(raw, "doi", "") or ""},
        source=getattr(raw, "source", "paperdl") or "paperdl",
        doi=getattr(raw, "doi", "") or "",
        publication_date=str(getattr(raw, "publication_date", "") or ""),
        categories=list(getattr(raw, "categories", []) or []),
        comment=getattr(raw, "comment", "") or "",
        journal_ref=getattr(raw, "journal_ref", "") or "",
    )


# ---------------------------------------------------------------------------
# Internal: Semantic Scholar API
# ---------------------------------------------------------------------------


def _search_semantic_scholar(
    query: str,
    max_results: int = 20,
) -> list[PaperInfo]:
    """Search Semantic Scholar API. Pure sync, no auth required."""
    try:
        import requests
    except ImportError:
        return []

    print(f"  [semantic-scholar] Searching '{query[:60]}'...")
    try:
        r = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": query,
                "limit": max_results,
                "fields": (
                    "title,authors,year,venue,citationCount,abstract,"
                    "url,openAccessPdf,externalIds,publicationDate"
                ),
            },
            timeout=20,
        )
        r.raise_for_status()
        results: list[PaperInfo] = []
        seen: set[str] = set()
        for p in r.json().get("data", []) or []:
            title = (p.get("title") or "").strip()
            if not title or title.lower() in seen:
                continue
            seen.add(title.lower())

            authors_raw = p.get("authors") or []
            authors_str = ", ".join(a.get("name", "") for a in authors_raw[:3])
            if len(authors_raw) > 3:
                authors_str += " et al."

            oa = p.get("openAccessPdf") or {}

            results.append(PaperInfo(
                title=title,
                authors=authors_str,
                year=p.get("year"),
                venue=p.get("venue", "") or "",
                citation_count=p.get("citationCount", 0) or 0,
                abstract=p.get("abstract") or "",
                url=p.get("url") or "",
                open_access_pdf=oa.get("url", ""),
                external_ids=p.get("externalIds") or {},
                source="semantic_scholar",
                doi=(p.get("externalIds") or {}).get("DOI", ""),
                publication_date=p.get("publicationDate", "") or "",
            ))

        print(f"  [semantic-scholar] Found {len(results)} papers")
        return results
    except Exception as exc:
        print(f"  [semantic-scholar] Error: {exc}")
        return []


def _fetch_semantic_scholar_pdf(
    paper: PaperInfo,
    output_dir: Path,
) -> str | None:
    """Try to fetch OA PDF from Semantic Scholar URL."""
    pdf_url = paper.open_access_pdf
    if not pdf_url:
        return None
    return _download_direct(pdf_url, paper.title, output_dir)


# ---------------------------------------------------------------------------
# Internal: direct download
# ---------------------------------------------------------------------------


def _download_direct(
    url: str,
    title: str,
    output_dir: Path,
    overwrite: bool = False,
) -> str | None:
    """Download PDF from a direct URL."""
    try:
        import re
        import requests
    except ImportError:
        return None

    safe_title = re.sub(r"[^A-Za-z0-9_.-]+", "_", title)[:80]
    pdf_path = output_dir / f"{safe_title}.pdf"

    if pdf_path.exists() and not overwrite:
        print(f"  [pdf] Already exists: {pdf_path}")
        return str(pdf_path)

    try:
        r = requests.get(url, timeout=60, allow_redirects=True)
        r.raise_for_status()
        if len(r.content) < 4096:  # min 4KB
            print(f"  [pdf] Downloaded file too small ({len(r.content)} bytes)")
            return None
        pdf_path.write_bytes(r.content)
        size_kb = len(r.content) / 1024
        print(f"  [pdf] Downloaded: {pdf_path.name} ({size_kb:.0f} KB)")
        return str(pdf_path)
    except Exception as exc:
        print(f"  [pdf] Download error: {exc}")
        return None


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already in async context — create new loop in thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=120)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _dict_to_paper_info(d: dict) -> PaperInfo:
    """Convert pipeline dict to PaperInfo."""
    oa = d.get("openAccessPdf") or {}
    ext_ids = d.get("externalIds") or {}
    return PaperInfo(
        title=d.get("title", ""),
        authors=d.get("authors", ""),
        year=d.get("year"),
        venue=d.get("venue", ""),
        citation_count=d.get("citationCount", d.get("citations", 0)) or 0,
        abstract=d.get("abstract", ""),
        url=d.get("url", ""),
        open_access_pdf=oa.get("url", "") if isinstance(oa, dict) else str(oa),
        external_ids=ext_ids,
        source=d.get("source", ""),
        doi=d.get("doi", ext_ids.get("DOI", ext_ids.get("doi", ""))),
    )


def _safe_int(value: Any) -> int | None:
    """Convert to int, returning None for non-numeric values."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# paperdl availability check
# ---------------------------------------------------------------------------

_paperdl_installed: bool | None = None


def is_paperdl_installed() -> bool:
    """Raw check: is the paperdl package importable?"""
    global _paperdl_installed
    if _paperdl_installed is None:
        try:
            import paperdl  # noqa: F401
            _paperdl_installed = True
        except ImportError:
            _paperdl_installed = False
    return _paperdl_installed


def _resolve_paperdl_mode() -> str:
    """Resolve effective paperdl mode: config → env → default 'auto'."""
    try:
        from .config import PAPERDL_MODE
        return PAPERDL_MODE
    except ImportError:
        import os
        return os.environ.get("PIPELINE_PAPERDL", "auto")


def is_paperdl_available() -> bool:
    """Mode-aware check: should paperdl be used?

    "auto" → True if installed
    "on"   → True (caller should have verified install)
    "off"  → False
    """
    mode = _resolve_paperdl_mode()
    if mode == "off":
        return False
    if mode == "on":
        return True
    return is_paperdl_installed()


def get_available_sources() -> list[str]:
    """Return sources available right now (respects mode)."""
    sources = ["semantic_scholar"]  # always available (uses requests)
    if is_paperdl_available():
        sources = PAPERDL_SOURCES + sources
    return sources
