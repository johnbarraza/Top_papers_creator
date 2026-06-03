"""Stage 1 - Discovery.

Path A (--topic only):  Multi-agent dataset search (web + APIs + GitHub).
                        Consolidator evaluates and ranks by causal potential.
Path B (--data given):  Profile user dataset, early warning, recommend methods.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import functools
print = functools.partial(print, flush=True)  # type: ignore[assignment]

from ..config import get_profile
from ..claude_runner import run_claude
from ..json_utils import extract_json
from ..state import save_state


# ── Path A: API-based dataset searchers ───────────────────────────────────────

def _search_dataverse(topic: str, max_results: int = 5) -> list[dict]:
    """Search Harvard Dataverse for datasets related to the topic."""
    try:
        import requests
    except ImportError:
        return []

    print(f"  [dataverse] Searching for '{topic}'...")
    try:
        r = requests.get(
            "https://dataverse.harvard.edu/api/search",
            params={
                "q": topic,
                "type": "dataset",
                "per_page": max_results,
                "sort": "date",
                "order": "desc",
                "fq": 'subject_ss:"Social Sciences"',
            },
            timeout=20,
        )
        r.raise_for_status()
        items = r.json().get("data", {}).get("items", [])
        results = []
        for item in items:
            results.append({
                "name": item.get("name", ""),
                "provider": "Harvard Dataverse",
                "url": item.get("url", ""),
                "description": (item.get("description", "") or "")[:300],
                "published": item.get("published_at", "")[:10],
                "source_api": "dataverse",
            })
        print(f"  [dataverse] Found {len(results)} datasets")
        return results
    except Exception as e:
        print(f"  [dataverse] Error: {e}")
        return []


def _search_zenodo(topic: str, max_results: int = 5) -> list[dict]:
    """Search Zenodo for datasets related to the topic."""
    try:
        import requests
    except ImportError:
        return []

    print(f"  [zenodo] Searching for '{topic}'...")
    try:
        r = requests.get(
            "https://zenodo.org/api/records",
            params={
                "q": f"{topic} econometrics OR panel OR causal",
                "type": "dataset",
                "size": max_results,
                "sort": "mostrecent",
            },
            timeout=20,
        )
        r.raise_for_status()
        hits = r.json().get("hits", {}).get("hits", [])
        results = []
        for item in hits:
            meta = item.get("metadata", {})
            files = [f.get("key", "") for f in item.get("files", [])[:5]]
            results.append({
                "name": meta.get("title", ""),
                "provider": "Zenodo",
                "url": f"https://zenodo.org/records/{item.get('id', '')}",
                "doi": meta.get("doi", ""),
                "description": (meta.get("description", "") or "")[:300],
                "files": files,
                "published": meta.get("publication_date", ""),
                "source_api": "zenodo",
            })
        print(f"  [zenodo] Found {len(results)} datasets")
        return results
    except Exception as e:
        print(f"  [zenodo] Error: {e}")
        return []


def _search_github(topic: str, max_results: int = 5) -> list[dict]:
    """Search GitHub for replication packages related to the topic."""
    try:
        import requests
    except ImportError:
        return []

    print(f"  [github] Searching for '{topic}'...")
    try:
        # Build queries in English for better GitHub coverage
        # Extract key English terms from topic
        _translations = {
            "educación": "education", "salud": "health", "empleo": "employment",
            "trabajo": "labor", "pobreza": "poverty", "comercio": "trade",
            "migración": "migration", "desigualdad": "inequality",
            "agricultura": "agriculture", "clima": "climate",
            "vivienda": "housing", "criminalidad": "crime",
            "género": "gender", "desarrollo": "development",
        }
        topic_en = topic.lower()
        for es, en in _translations.items():
            topic_en = topic_en.replace(es, en)

        queries = [
            f"{topic_en} replication data",
            f"{topic_en} dataset causal",
            f"{topic} replication",
        ]
        seen_repos = set()
        results = []

        for q in queries:
            if len(results) >= max_results:
                break
            r = requests.get(
                "https://api.github.com/search/repositories",
                params={"q": q, "sort": "stars", "per_page": max_results},
                timeout=20,
            )
            r.raise_for_status()
            for item in r.json().get("items", []):
                repo_name = item.get("full_name", "")
                if repo_name in seen_repos:
                    continue
                seen_repos.add(repo_name)
                results.append({
                    "name": repo_name,
                    "provider": "GitHub",
                    "url": item.get("html_url", ""),
                    "description": (item.get("description", "") or "")[:300],
                    "stars": item.get("stargazers_count", 0),
                    "language": item.get("language", ""),
                    "updated": (item.get("updated_at", "") or "")[:10],
                    "source_api": "github",
                })

        print(f"  [github] Found {len(results)} repos")
        return results
    except Exception as e:
        print(f"  [github] Error: {e}")
        return []


def _search_semantic_scholar_seed_papers(topic: str, max_results: int = 10) -> list[dict]:
    """Search Semantic Scholar for paper candidates usable in replication mode."""
    try:
        import requests
    except ImportError:
        return []

    print(f"  [semantic-scholar] Searching seed papers for '{topic}'...")
    try:
        r = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": topic,
                "limit": max_results,
                "fields": (
                    "title,authors,year,venue,citationCount,abstract,"
                    "url,openAccessPdf,externalIds"
                ),
            },
            timeout=15,
        )
        r.raise_for_status()
        results = []
        seen = set()
        for p in r.json().get("data", []) or []:
            title = (p.get("title") or "").strip()
            if not title or title.lower() in seen:
                continue
            seen.add(title.lower())
            authors = ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:3])
            if len(p.get("authors") or []) > 3:
                authors += " et al."
            results.append({
                "title": title,
                "authors": authors,
                "year": p.get("year"),
                "venue": p.get("venue", ""),
                "citationCount": p.get("citationCount", 0),
                "abstract": p.get("abstract") or "",
                "url": p.get("url") or "",
                "openAccessPdf": p.get("openAccessPdf") or {},
                "externalIds": p.get("externalIds") or {},
                "source": "semantic_scholar",
            })
        print(f"  [semantic-scholar] Found {len(results)} seed papers")
        return results
    except Exception as e:
        print(f"  [semantic-scholar] Error: {e}")
        return []


def _resolve_paperdl_mode(state: dict | None = None) -> str:
    """Resolve paperdl mode: state config → config.py → env → 'auto'."""
    if state:
        mode = state.get("config", {}).get("paperdl", "")
        if mode in ("auto", "on", "off"):
            return mode
    try:
        from ..paper_searcher import _resolve_paperdl_mode as _rm
        return _rm()
    except ImportError:
        import os
        return os.environ.get("PIPELINE_PAPERDL", "auto")


def _candidate_to_seed_paper(candidate: dict) -> dict | None:
    """Convert a dataset/replication-package candidate into a paper-like record."""
    source = (candidate.get("source_api") or "").lower()
    provider = (candidate.get("provider") or "").lower()
    haystack = " ".join([
        str(candidate.get("name", "")),
        str(candidate.get("description", "")),
        str(candidate.get("url", "")),
        source,
        provider,
    ]).lower()

    if not any(k in haystack for k in ("replication", "paper", "journal", "dataverse", "github")):
        return None
    if source not in {"github", "journal", "dataverse"} and "replication" not in haystack:
        return None

    return {
        "title": candidate.get("name", "Untitled replication package"),
        "authors": "",
        "year": str(candidate.get("published", ""))[:4] or None,
        "venue": candidate.get("provider", ""),
        "citationCount": 0,
        "abstract": candidate.get("description", ""),
        "url": candidate.get("url", ""),
        "openAccessPdf": {},
        "externalIds": {},
        "source": "replication_package",
        "replication_package_url": candidate.get("url", ""),
        "dataset_candidate": candidate,
    }


def _dedupe_seed_papers(papers: list[dict]) -> list[dict]:
    """Deduplicate paper candidates by title/url while preserving order."""
    seen = set()
    deduped = []
    for p in papers:
        key = (p.get("title") or p.get("url") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(p)
    return deduped


def _search_paperdl_seed_papers(topic: str, max_results: int = 10,
                                mode: str = "auto") -> list[dict]:
    """Search paperdl (arXiv, OpenReview, PMLR, PMC) for seed papers.

    Respects paperdl mode: "auto" (use if installed), "on" (require), "off" (skip).
    Falls back gracefully if paperdl unavailable and mode is "auto".
    """
    if mode == "off":
        return []

    try:
        from ..paper_searcher import PaperSearcher, is_paperdl_available
    except ImportError:
        return []

    if not is_paperdl_available():
        if mode == "on":
            print("  [paperdl] Mode is 'on' but paperdl not installed. "
                  "Install with: pip install paperdl")
        return []

    print(f"  [paperdl] Searching seed papers for '{topic}'...")
    try:
        econ_sources = ["arxiv", "pmlr", "pmc"]
        searcher = PaperSearcher(sources=econ_sources, mode=mode)
        results = searcher.search(topic, max_results=max_results)
        papers = []
        for pi in results:
            papers.append(pi.to_pipeline_dict())
        print(f"  [paperdl] Found {len(papers)} seed papers")
        return papers
    except Exception as e:
        print(f"  [paperdl] Error: {e}")
        return []


def _search_dbnomics(topic: str, max_results: int = 5) -> list[dict]:
    """Search DBnomics meta-aggregator (covers FRED, IMF, ECB, OECD, BIS, Eurostat, WB).

    DBnomics indexes ~750M economic time series from ~93 official providers.
    Free, no API key required.
    """
    try:
        import requests
    except ImportError:
        return []

    print(f"  [dbnomics] Searching for '{topic}'...")
    try:
        r = requests.get(
            "https://api.db.nomics.world/v22/search",
            params={"q": topic, "limit": max_results},
            timeout=20,
        )
        r.raise_for_status()
        docs = r.json().get("results", {}).get("docs", [])
        results = []
        for d in docs:
            provider = d.get("provider_name", d.get("provider_code", ""))
            dataset_code = d.get("code", "")
            results.append({
                "name": d.get("name", "")[:200],
                "provider": f"DBnomics ({provider})",
                "url": f"https://db.nomics.world/{d.get('provider_code', '')}/{dataset_code}",
                "description": (d.get("description", "") or "")[:300],
                "n_series": d.get("nb_series", 0),
                "source_api": "dbnomics",
            })
        print(f"  [dbnomics] Found {len(results)} datasets")
        return results
    except Exception as e:
        print(f"  [dbnomics] Error: {e}")
        return []


def _search_ckan(api_root: str, portal_label: str, topic: str,
                 max_results: int = 5,
                 use_format_filter: bool = True,
                 source_api: str | None = None,
                 dataset_url_template: str | None = None) -> list[dict]:
    """Generic CKAN package_search adapter.

    Most national open-data portals (data.gov, data.gov.uk, IDB, data.gov.au,
    open.canada.ca, datos.gob.mx, govdata.de, dati.gov.it, ...) expose the same
    CKAN action API at `/api/3/action/package_search`. This single helper
    handles all of them with one consistent extraction of `download_url`.

    Args:
        api_root: base URL of the CKAN install (without trailing slash)
                  — the helper appends /api/3/action/package_search
        portal_label: human-readable name shown in logs and `provider`
        topic: free-text search query
        max_results: rows to request
        use_format_filter: if True, restricts results to those with at least
                           one CSV/TSV/JSON/XLSX/ZIP resource (faster + higher
                           yield for Path C). Some portals don't support this
                           facet — set False to disable.
        source_api: short identifier stored in candidate dicts (defaults to
                    a slugified portal_label).
        dataset_url_template: optional Python format string for landing-page
                              URLs (gets `{name}` substituted from CKAN
                              package name). Defaults to `{api_root}/dataset/{name}`.
    """
    try:
        import requests
    except ImportError:
        return []

    label = portal_label
    src = source_api or label.replace(".", "_").replace(" ", "_").lower()
    print(f"  [{label}] Searching for '{topic}'...")

    _DL_EXTS = (".csv", ".tsv", ".tab", ".dta", ".parquet", ".xlsx", ".zip", ".json")
    _DL_FMTS = {"csv", "tsv", "dta", "parquet", "xlsx", "zip", "json"}

    params: dict = {"q": topic, "rows": max_results}
    if use_format_filter:
        params["fq"] = "res_format:(CSV OR TSV OR JSON OR XLSX OR ZIP)"

    try:
        r = requests.get(
            f"{api_root.rstrip('/')}/api/3/action/package_search",
            params=params,
            timeout=20,
        )
        r.raise_for_status()
        items = r.json().get("result", {}).get("results", [])
        results = []

        def _flatten(value):
            """Some CKAN installs return multilingual title/notes as dicts."""
            if isinstance(value, dict):
                return value.get("en") or value.get("es") or value.get("it") \
                    or next(iter(value.values()), "") or ""
            return value or ""

        for item in items:
            org = item.get("organization") or {}
            if isinstance(org, dict):
                org_name = _flatten(org.get("title")) or org.get("name") or label
            else:
                org_name = label

            download_url = ""
            download_format = ""
            for res in (item.get("resources") or []):
                fmt = (_flatten(res.get("format")) or "").lower()
                ru = _flatten(res.get("url"))
                if (ru and (ru.lower().endswith(_DL_EXTS) or fmt in _DL_FMTS)):
                    download_url = ru
                    download_format = fmt or Path(ru).suffix.lstrip(".")
                    break

            name_slug = item.get("name", "")
            if dataset_url_template:
                landing = dataset_url_template.format(name=name_slug, api_root=api_root)
            else:
                landing = f"{api_root.rstrip('/')}/dataset/{name_slug}"

            results.append({
                "name": _flatten(item.get("title"))[:200],
                "provider": f"{label} ({org_name})" if org_name and org_name != label else label,
                "url": landing,
                "download_url": download_url,
                "download_format": download_format,
                "description": _flatten(item.get("notes"))[:300],
                "published": (item.get("metadata_created") or "")[:10],
                "source_api": src,
            })
        n_dl = sum(1 for r in results if r["download_url"])
        print(f"  [{label}] Found {len(results)} datasets ({n_dl} directly downloadable)")
        return results
    except Exception as e:
        print(f"  [{label}] Error: {e}")
        return []


def _search_datagov(topic: str, max_results: int = 5) -> list[dict]:
    """Search US data.gov (CKAN) for datasets with directly-downloadable files.

    Uses CKAN's `res_format` facet filter (via _search_ckan helper) to require
    at least one resource in a parseable format. This is far more reliable
    than filtering by organization, because data.gov indexes many federal/
    state/municipal portals where most "datasets" are actually HTML landing
    pages. Downstream Q1-Q8 quality filters reject low-quality files so this
    function does NOT need to gate on causal structure.
    """
    return _search_ckan(
        api_root="https://catalog.data.gov",
        portal_label="data.gov",
        topic=topic,
        max_results=max_results,
        source_api="datagov",
    )


def _search_worldbank(topic: str, max_results: int = 5) -> list[dict]:
    """Search World Bank Indicators API for indicators matching topic keywords.

    The WB Indicators API has no full-text search, so we fetch the indicator
    catalog and filter by topic keywords client-side. Returns indicator metadata
    pointing at the country-year panel data accessible via the same API.
    Free, no API key required.
    """
    try:
        import requests
    except ImportError:
        return []

    print(f"  [worldbank] Searching for '{topic}'...")
    try:
        # WB indicator search: fetch a page of indicators and filter by topic terms
        r = requests.get(
            "https://api.worldbank.org/v2/indicator",
            params={"format": "json", "per_page": 500, "page": 1},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list) or len(data) < 2:
            return []
        indicators = data[1] or []

        terms = [t.lower() for t in topic.split() if len(t) > 3]
        scored = []
        for ind in indicators:
            name = (ind.get("name") or "").lower()
            note = (ind.get("sourceNote") or "").lower()
            score = sum(1 for t in terms if t in name or t in note)
            if score > 0:
                scored.append((score, ind))
        scored.sort(key=lambda x: -x[0])

        results = []
        for _, ind in scored[:max_results]:
            code = ind.get("id", "")
            results.append({
                "name": ind.get("name", "")[:200],
                "provider": f"World Bank ({(ind.get('source') or {}).get('value', 'WDI')})",
                "url": f"https://data.worldbank.org/indicator/{code}",
                "description": (ind.get("sourceNote", "") or "")[:300],
                "indicator_code": code,
                "source_api": "worldbank",
            })
        print(f"  [worldbank] Found {len(results)} indicators")
        return results
    except Exception as e:
        print(f"  [worldbank] Error: {e}")
        return []


def _search_idb(topic: str, max_results: int = 5) -> list[dict]:
    """Search IDB (Inter-American Development Bank) Numbers for Development.

    LatAm-focused open data: impact evaluations, household surveys, and
    country indicators. Uses CKAN but does NOT support the res_format facet
    filter, so we disable it here. Multilingual title/notes are handled by
    the helper's `_flatten` adapter.
    """
    return _search_ckan(
        api_root="https://data.iadb.org",
        portal_label="IDB Numbers for Development",
        topic=topic,
        max_results=max_results,
        use_format_filter=False,
        source_api="idb",
    )


def _search_eu_opendata(topic: str, max_results: int = 5) -> list[dict]:
    """Search EU Open Data Portal (data.europa.eu) — pan-European catalog.

    Aggregates Eurostat + national portals across all EU member states. Uses
    the EDP search API (NOT plain CKAN) which returns DCAT distributions
    rather than CKAN resources, so the schema adapter is different from
    data.gov / IDB.
    """
    try:
        import requests
    except ImportError:
        return []

    print(f"  [eu_opendata] Searching for '{topic}'...")
    _DL_FORMATS = {"CSV", "TSV", "JSON", "XLSX", "XLS", "ZIP", "TAB"}
    _DL_EXTS = (".csv", ".tsv", ".tab", ".dta", ".parquet", ".xlsx", ".zip", ".json")
    try:
        r = requests.get(
            "https://data.europa.eu/api/hub/search/search",
            params={"q": topic, "limit": max_results},
            timeout=20,
        )
        r.raise_for_status()
        items = r.json().get("result", {}).get("results", [])
        results = []
        for item in items:
            # EDP returns title/description as multilingual dicts keyed by lang
            def _i18n(v):
                if isinstance(v, dict):
                    return v.get("en") or next(iter(v.values()), "") or ""
                return v or ""

            title = _i18n(item.get("title", ""))
            desc = _i18n(item.get("description", ""))

            # Walk distributions for the first downloadable file. EU EDP often
            # mislabels formats (e.g. format=HTML for what is actually a CSV
            # endpoint), so we accept either a known download format OR a URL
            # whose extension matches a parseable format.
            download_url = ""
            download_format = ""
            for dist in (item.get("distributions") or []):
                fmt_obj = dist.get("format") or {}
                fmt_id = (fmt_obj.get("id") or "").upper() if isinstance(fmt_obj, dict) else ""

                # Collect candidate URLs from both download_url and access_url
                # (each can be list, string, or missing). Skip empty strings.
                cand_urls = []
                for key in ("download_url", "access_url"):
                    val = dist.get(key)
                    if isinstance(val, list):
                        cand_urls.extend(u for u in val if u)
                    elif isinstance(val, str) and val:
                        cand_urls.append(val)

                for cand_url in cand_urls:
                    if fmt_id in _DL_FORMATS or cand_url.lower().endswith(_DL_EXTS):
                        download_url = cand_url
                        download_format = fmt_id.lower() or Path(cand_url).suffix.lstrip(".").lower()
                        break
                if download_url:
                    break

            country = (item.get("country") or {}).get("label", "EU")
            results.append({
                "name": title[:200],
                "provider": f"EU Open Data ({country})",
                "url": (item.get("resource") or "").strip(),
                "download_url": download_url,
                "download_format": download_format,
                "description": desc[:300],
                "source_api": "eu_opendata",
            })
        print(f"  [eu_opendata] Found {len(results)} datasets "
              f"({sum(1 for r in results if r['download_url'])} directly downloadable)")
        return results
    except Exception as e:
        print(f"  [eu_opendata] Error: {e}")
        return []


def _search_data_gov_uk(topic: str, max_results: int = 5) -> list[dict]:
    """Search UK government open data portal (data.gov.uk) — CKAN."""
    return _search_ckan(
        api_root="https://data.gov.uk",
        portal_label="data.gov.uk",
        topic=topic,
        max_results=max_results,
        source_api="data_gov_uk",
    )


# ── Additional national CKAN portals (added 2026-04-10) ───────────────────────
# All 5 use the same generic _search_ckan helper. Adding more portals in the
# future requires only one new wrapper function (not a new schema adapter).

def _search_data_gov_au(topic: str, max_results: int = 5) -> list[dict]:
    """Australia federal open data portal (data.gov.au) — CKAN."""
    return _search_ckan(
        api_root="https://data.gov.au/data",
        portal_label="data.gov.au",
        topic=topic,
        max_results=max_results,
        source_api="data_gov_au",
        dataset_url_template="https://data.gov.au/data/dataset/{name}",
    )


def _search_open_canada(topic: str, max_results: int = 5) -> list[dict]:
    """Canada federal open data portal (open.canada.ca) — CKAN."""
    return _search_ckan(
        api_root="https://open.canada.ca/data",
        portal_label="open.canada.ca",
        topic=topic,
        max_results=max_results,
        source_api="open_canada",
        dataset_url_template="https://open.canada.ca/data/en/dataset/{name}",
    )


def _search_datos_gob_mx(topic: str, max_results: int = 5) -> list[dict]:
    """México federal open data portal (datos.gob.mx) — CKAN.

    Spanish-language portal — for best results pass Spanish keywords.
    Format facet filter is disabled because the install behaves erratically
    when it's enabled; the post-walk filter still extracts download_url.
    """
    return _search_ckan(
        api_root="https://datos.gob.mx",
        portal_label="datos.gob.mx",
        topic=topic,
        max_results=max_results,
        use_format_filter=False,
        source_api="datos_gob_mx",
        dataset_url_template="https://datos.gob.mx/busca/dataset/{name}",
    )


def _search_datosabiertos_peru(topic: str, max_results: int = 5) -> list[dict]:
    """Peru federal open data portal (datosabiertos.gob.pe) - CKAN."""
    return _search_ckan(
        api_root="https://www.datosabiertos.gob.pe",
        portal_label="datosabiertos.gob.pe",
        topic=topic,
        max_results=max_results,
        source_api="datosabiertos_peru",
    )


def _search_govdata_de(topic: str, max_results: int = 5) -> list[dict]:
    """Germany federal open data portal (govdata.de) — CKAN.

    German-language portal — for best results pass German keywords.
    """
    return _search_ckan(
        api_root="https://ckan.govdata.de",
        portal_label="govdata.de",
        topic=topic,
        max_results=max_results,
        source_api="govdata_de",
        dataset_url_template="https://www.govdata.de/web/guest/suchen/-/details/{name}",
    )


def _search_dati_gov_it(topic: str, max_results: int = 5) -> list[dict]:
    """Italy federal open data portal (dati.gov.it) — CKAN.

    Italian-language portal — for best results pass Italian keywords.
    Format facet filter is disabled because the install does not support it
    reliably; we still walk resources to extract download_url.
    """
    return _search_ckan(
        api_root="https://www.dati.gov.it/opendata",
        portal_label="dati.gov.it",
        topic=topic,
        max_results=max_results,
        use_format_filter=False,
        source_api="dati_gov_it",
        dataset_url_template="https://www.dati.gov.it/view-dataset/dataset?id={name}",
    )


# ── Non-CKAN sources (Phase 2: Socrata + FAOSTAT) ─────────────────────────────

def _search_socrata(topic: str, max_results: int = 5) -> list[dict]:
    """Search the Socrata federated catalog (api.us.socrata.com).

    A SINGLE searcher covers ~30 US city/state Socrata installs (NYC Open
    Data, Chicago, San Francisco, LA, Seattle, Austin, California, Texas,
    Missouri, ...). For each result we construct the canonical CSV download
    URL via the standard Socrata pattern:
        https://{domain}/api/views/{id}/rows.csv?accessType=DOWNLOAD
    Free, no API key, generous rate limits.
    """
    try:
        import requests
    except ImportError:
        return []

    print(f"  [socrata] Searching for '{topic}'...")
    try:
        r = requests.get(
            "https://api.us.socrata.com/api/catalog/v1",
            params={"q": topic, "only": "dataset", "limit": max_results},
            timeout=20,
        )
        r.raise_for_status()
        items = r.json().get("results") or []
        results = []
        for it in items:
            res = it.get("resource") or {}
            md = it.get("metadata") or {}
            dataset_id = res.get("id") or ""
            domain = md.get("domain") or ""
            if not dataset_id or not domain:
                continue
            # Standard Socrata CSV export endpoint — works on every install
            download_url = f"https://{domain}/api/views/{dataset_id}/rows.csv?accessType=DOWNLOAD"
            results.append({
                "name": (res.get("name") or "")[:200],
                "provider": f"Socrata ({domain})",
                "url": it.get("permalink", "") or it.get("link", ""),
                "download_url": download_url,
                "download_format": "csv",
                "description": (res.get("description") or "")[:300],
                "published": (res.get("createdAt") or "")[:10],
                "source_api": "socrata",
            })
        n_dl = sum(1 for x in results if x["download_url"])
        print(f"  [socrata] Found {len(results)} datasets ({n_dl} directly downloadable)")
        return results
    except Exception as e:
        print(f"  [socrata] Error: {e}")
        return []


# ── FAOSTAT bulk catalog cache ────────────────────────────────────────────────
# The full catalog is small (~68 entries, ~30KB JSON) and rarely changes, so
# we fetch it once per process and filter client-side.
_FAOSTAT_CATALOG_CACHE: list[dict] = []


def _faostat_catalog() -> list[dict]:
    """Lazy-load the FAOSTAT bulk dataset catalog (cached in-process)."""
    global _FAOSTAT_CATALOG_CACHE
    if _FAOSTAT_CATALOG_CACHE:
        return _FAOSTAT_CATALOG_CACHE
    try:
        import requests
        r = requests.get(
            "https://bulks-faostat.fao.org/production/datasets_E.json",
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        _FAOSTAT_CATALOG_CACHE = data.get("Datasets", {}).get("Dataset", []) or []
    except Exception as e:
        print(f"  [faostat] Catalog fetch failed: {e}")
        _FAOSTAT_CATALOG_CACHE = []
    return _FAOSTAT_CATALOG_CACHE


def _search_faostat(topic: str, max_results: int = 5) -> list[dict]:
    """Search FAOSTAT bulk catalog by client-side keyword overlap.

    FAOSTAT publishes ~68 thematic country-year panel datasets (production,
    trade, prices, land use, food security, emissions, etc.) as direct ZIP
    bulk downloads. Each ZIP contains a normalized CSV with country × year ×
    item × value records — ideal for development / agriculture / environment
    econ papers using cross-country panels.

    Strategy: fetch the catalog (cached) and rank entries by keyword overlap
    against name + topic + description. Returns ZIPs that the existing
    `_try_download_direct` flow can fetch and unzip.
    """
    catalog = _faostat_catalog()
    if not catalog:
        return []
    print(f"  [faostat] Searching catalog for '{topic}'...")

    terms = [t.lower() for t in topic.split() if len(t) > 2]
    scored = []
    for d in catalog:
        haystack = " ".join([
            d.get("DatasetName", "") or "",
            d.get("Topic", "") or "",
            d.get("DatasetDescription", "") or "",
        ]).lower()
        if not terms:
            score = 0
        else:
            score = sum(1 for t in terms if t in haystack)
            if score == 0:
                continue

        url = d.get("FileLocation") or ""
        if not url:
            continue
        scored.append((score, d, url))

    scored.sort(key=lambda x: -x[0])
    results = []
    for _, d, url in scored[:max_results]:
        results.append({
            "name": (d.get("DatasetName") or "")[:200],
            "provider": f"FAOSTAT ({d.get('Topic') or 'agriculture'})",
            "url": "https://www.fao.org/faostat/en/#data/" + (d.get("DatasetCode") or ""),
            "download_url": url,
            "download_format": "zip",
            "description": (d.get("DatasetDescription") or "")[:300],
            "published": (d.get("DateUpdate") or "")[:10],
            "source_api": "faostat",
        })
    n_dl = sum(1 for x in results if x["download_url"])
    print(f"  [faostat] Found {len(results)} datasets ({n_dl} directly downloadable)")
    return results


def _search_data_gouv_fr(topic: str, max_results: int = 5) -> list[dict]:
    """Search French government open data portal (data.gouv.fr).

    Uses data.gouv.fr's native API (not CKAN) — different schema:
    `data` instead of `result.results`, and resources have lowercase keys.
    """
    try:
        import requests
    except ImportError:
        return []

    print(f"  [data.gouv.fr] Searching for '{topic}'...")
    _DL_EXTS = (".csv", ".tsv", ".tab", ".dta", ".parquet", ".xlsx", ".zip", ".json")
    try:
        r = requests.get(
            "https://www.data.gouv.fr/api/1/datasets/",
            params={"q": topic, "page_size": max_results},
            timeout=20,
        )
        r.raise_for_status()
        items = r.json().get("data") or []
        results = []
        for item in items:
            download_url = ""
            download_format = ""
            for res in (item.get("resources") or []):
                fmt = (res.get("format") or "").lower()
                ru = res.get("url") or ""
                if ru.lower().endswith(_DL_EXTS) or fmt in {"csv", "tsv", "dta", "parquet", "xlsx", "zip", "json"}:
                    download_url = ru
                    download_format = fmt or Path(ru).suffix.lstrip(".")
                    break
            org = (item.get("organization") or {}).get("name", "data.gouv.fr")
            results.append({
                "name": (item.get("title") or "")[:200],
                "provider": f"data.gouv.fr ({org})",
                "url": item.get("page", "") or item.get("uri", ""),
                "download_url": download_url,
                "download_format": download_format,
                "description": (item.get("description") or "")[:300],
                "published": (item.get("created_at") or "")[:10],
                "source_api": "data_gouv_fr",
            })
        print(f"  [data.gouv.fr] Found {len(results)} datasets "
              f"({sum(1 for r in results if r['download_url'])} directly downloadable)")
        return results
    except Exception as e:
        print(f"  [data.gouv.fr] Error: {e}")
        return []


# ── Path A: download dataset from repo (legacy, kept for reference) ───────────

def _download_repo_dataset(repos: list[dict], project_dir: Path) -> Optional[str]:
    """Try to download a dataset from the best GitHub repo.

    Attempts each repo in order. Returns the local path if successful, None otherwise.
    """
    try:
        import requests
    except ImportError:
        print("  [warn] requests not installed — skipping repo dataset download")
        return None

    data_dir = project_dir / "data" / "raw"
    data_dir.mkdir(parents=True, exist_ok=True)

    SUPPORTED_EXTS = {".csv", ".dta", ".xlsx", ".xls", ".parquet", ".json"}

    for repo in repos[:3]:  # Try top 3 repos
        url = repo.get("url", "")
        dataset_url = repo.get("dataset_url", "")

        # If Claude provided a direct dataset URL, use it
        if dataset_url:
            try:
                print(f"  [download] Trying direct URL: {dataset_url[:80]}...")
                resp = requests.get(dataset_url, timeout=60, allow_redirects=True)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    # Guess extension from URL or content-type
                    from urllib.parse import urlparse
                    parsed = urlparse(dataset_url)
                    ext = Path(parsed.path).suffix.lower()
                    if ext not in SUPPORTED_EXTS:
                        ext = ".csv"  # default
                    local_path = data_dir / f"repo_dataset{ext}"
                    local_path.write_bytes(resp.content)
                    size_mb = len(resp.content) / (1024 * 1024)
                    print(f"  [download] Saved {local_path.name} ({size_mb:.1f} MB)")
                    return str(local_path)
            except Exception as e:
                print(f"  [download] Direct URL failed: {e}")

        # Try GitHub API to find dataset files in the repo
        if "github.com" in url:
            try:
                # Extract owner/repo from URL
                parts = url.rstrip("/").split("github.com/")[-1].split("/")
                if len(parts) >= 2:
                    owner, repo_name = parts[0], parts[1]
                    api_url = f"https://api.github.com/repos/{owner}/{repo_name}/git/trees/main?recursive=1"
                    resp = requests.get(api_url, timeout=30)
                    if resp.status_code != 200:
                        # Try 'master' branch
                        api_url = api_url.replace("/main?", "/master?")
                        resp = requests.get(api_url, timeout=30)

                    if resp.status_code == 200:
                        tree = resp.json().get("tree", [])
                        # Find data files, prefer .csv and .dta
                        data_files = []
                        for item in tree:
                            if item["type"] == "blob":
                                fpath = item["path"]
                                ext = Path(fpath).suffix.lower()
                                if ext in SUPPORTED_EXTS:
                                    # Prioritize files in data/ directories or with data-like names
                                    priority = 0
                                    fl = fpath.lower()
                                    if "data" in fl:
                                        priority += 2
                                    if ext == ".dta":
                                        priority += 1  # Stata files more likely to be analysis-ready
                                    if ext == ".csv":
                                        priority += 1
                                    data_files.append((priority, fpath, ext))

                        if data_files:
                            data_files.sort(key=lambda x: -x[0])
                            best_priority, best_path, best_ext = data_files[0]
                            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/main/{best_path}"
                            print(f"  [download] Found {best_path} in {owner}/{repo_name}...")
                            resp = requests.get(raw_url, timeout=120)
                            if resp.status_code != 200:
                                raw_url = raw_url.replace("/main/", "/master/")
                                resp = requests.get(raw_url, timeout=120)

                            if resp.status_code == 200 and len(resp.content) > 500:
                                local_path = data_dir / f"repo_dataset{best_ext}"
                                local_path.write_bytes(resp.content)
                                size_mb = len(resp.content) / (1024 * 1024)
                                print(f"  [download] Saved {local_path.name} ({size_mb:.1f} MB)")
                                return str(local_path)
            except Exception as e:
                print(f"  [download] GitHub API failed for {url}: {e}")

    print("  [download] Could not download dataset from any repo")
    return None


# ── Path B: data profiling ───────────────────────────────────────────────────

def _load_dataframe(data_path: str):
    """Load a dataset into a pandas DataFrame."""
    import pandas as pd

    p = Path(data_path)
    if not p.exists():
        print(f"  [error] Dataset not found: {data_path}")
        sys.exit(1)

    ext = p.suffix.lower()
    if ext == ".csv":
        try:
            df = pd.read_csv(p, encoding="utf-8", low_memory=False)
        except UnicodeDecodeError:
            df = pd.read_csv(p, encoding="latin-1", low_memory=False)
    elif ext in (".xls", ".xlsx"):
        df = pd.read_excel(p)
    elif ext == ".dta":
        df = pd.read_stata(p)
    elif ext == ".parquet":
        df = pd.read_parquet(p)
    elif ext == ".json":
        df = pd.read_json(p)
    elif ext in (".tab", ".tsv"):
        try:
            df = pd.read_csv(p, sep="\t", encoding="utf-8", low_memory=False)
        except UnicodeDecodeError:
            df = pd.read_csv(p, sep="\t", encoding="latin-1", low_memory=False)
    else:
        raise ValueError(f"Unsupported format: {ext}. Use .csv, .xlsx, .dta, .parquet, .tab, or .json")

    return df


def _detect_wide_panel_suffixes(df) -> dict:
    """Detect wide-format panel data where time is encoded in column name suffixes.

    Common patterns:
      - variable_20, variable_21, variable_22  (2-digit year suffixes)
      - variable_2020, variable_2021           (4-digit year suffixes)
      - variable_t1, variable_t2               (wave suffixes)

    Returns dict with keys: detected (bool), year_suffixes, n_periods,
    suffix_pattern, base_variables, suffix_to_year_map.
    """
    import re
    from collections import Counter

    cols = list(df.columns)
    result = {"detected": False}

    # ── Pattern 1: 2-digit year suffixes (_20, _21, _22, etc.) ─────────
    # Match columns ending in _DD where DD is a plausible 2-digit year
    suffix_2d = re.compile(r'^(.+?)[_](\d{2})$')
    two_digit_suffixes = Counter()
    two_digit_bases = {}
    for col in cols:
        m = suffix_2d.match(col)
        if m:
            base, suffix = m.group(1), m.group(2)
            year_int = int(suffix)
            # Plausible 2-digit years: 00-30 (2000-2030) or 80-99 (1980-1999)
            if (0 <= year_int <= 30) or (80 <= year_int <= 99):
                two_digit_suffixes[suffix] += 1
                if suffix not in two_digit_bases:
                    two_digit_bases[suffix] = []
                two_digit_bases[suffix].append(base)

    # ── Pattern 2: 4-digit year suffixes (_2020, _2021, etc.) ──────────
    suffix_4d = re.compile(r'^(.+?)[_](\d{4})$')
    four_digit_suffixes = Counter()
    four_digit_bases = {}
    for col in cols:
        m = suffix_4d.match(col)
        if m:
            base, suffix = m.group(1), m.group(2)
            year_int = int(suffix)
            if 1980 <= year_int <= 2030:
                four_digit_suffixes[suffix] += 1
                if suffix not in four_digit_bases:
                    four_digit_bases[suffix] = []
                four_digit_bases[suffix].append(base)

    # ── Decide which pattern is dominant ───────────────────────────────
    # A suffix group is "real" if at least 3 different suffixes share many
    # base variable names, indicating the same variables across years
    best_pattern = None
    best_suffixes = {}
    best_bases = {}

    for label, sfx_counts, sfx_bases in [
        ("2-digit-year", two_digit_suffixes, two_digit_bases),
        ("4-digit-year", four_digit_suffixes, four_digit_bases),
    ]:
        if len(sfx_counts) < 2:
            continue
        # Check how many bases are shared across at least 2 suffixes
        all_base_sets = {s: set(bases) for s, bases in sfx_bases.items()}
        suffix_list = sorted(all_base_sets.keys())
        # Count bases that appear in 2+ suffix groups
        base_counter = Counter()
        for s in suffix_list:
            for b in all_base_sets[s]:
                base_counter[b] += 1
        shared_bases = sum(1 for b, c in base_counter.items() if c >= 2)

        # Need a meaningful number of shared bases (at least 10 or 5% of columns)
        min_shared = max(10, len(cols) * 0.02)
        if shared_bases >= min_shared:
            # This pattern is stronger than current best?
            if best_pattern is None or shared_bases > sum(1 for b, c in Counter(
                b for bases in best_bases.values() for b in bases
            ).items() if c >= 2):
                best_pattern = label
                best_suffixes = sfx_counts
                best_bases = sfx_bases

    if best_pattern is None:
        return result

    # ── Build the result ───────────────────────────────────────────────
    sorted_suffixes = sorted(best_suffixes.keys())
    n_periods = len(sorted_suffixes)

    # Map suffixes to full years
    if best_pattern == "2-digit-year":
        suffix_to_year = {}
        for s in sorted_suffixes:
            y = int(s)
            suffix_to_year[s] = 2000 + y if y <= 30 else 1900 + y
    else:
        suffix_to_year = {s: int(s) for s in sorted_suffixes}

    # Find base variables shared across ALL suffixes (core panel vars)
    all_base_sets = {s: set(bases) for s, bases in best_bases.items()}
    core_bases = set.intersection(*all_base_sets.values()) if all_base_sets else set()

    # Find columns that DON'T have any year suffix (time-invariant / IDs)
    suffixed_cols = set()
    for bases in best_bases.values():
        for b in bases:
            for s in sorted_suffixes:
                cand = f"{b}_{s}"
                if cand in df.columns:
                    suffixed_cols.add(cand)
    unsuffixed_cols = [c for c in cols if c not in suffixed_cols]

    result = {
        "detected": True,
        "pattern": best_pattern,
        "year_suffixes": sorted_suffixes,
        "year_values": [suffix_to_year[s] for s in sorted_suffixes],
        "n_periods": n_periods,
        "n_suffixed_vars_per_period": {s: best_suffixes[s] for s in sorted_suffixes},
        "n_core_base_vars": len(core_bases),
        "core_base_vars_sample": sorted(list(core_bases))[:20],
        "unsuffixed_cols": unsuffixed_cols[:30],
        "suffix_to_year": suffix_to_year,
    }
    return result


def _detect_id_and_time_columns(df) -> dict:
    """Detect likely ID columns and time columns using heuristics.

    Handles both long-format (time in a column) and wide-format (time encoded
    in column name suffixes like variable_20, variable_21).

    Returns dict with keys: id_cols, time_cols, structure, panel_details,
    wide_panel (optional).
    """
    rows = len(df)
    cols_lower = {c: c.lower() for c in df.columns}

    # ── Check for wide-format panel first ──────────────────────────────
    wide_info = _detect_wide_panel_suffixes(df)

    # ── Candidate ID columns ────────────────────────────────────────────
    # Common ID column name patterns
    id_patterns = [
        "id", "codigo", "codperso", "cod_perso", "conglome", "vivienda",
        "hogar", "nconglom", "ubigeo", "folio", "ident", "person",
        "household", "hh_id", "pid", "hhid", "indiv",
    ]
    id_candidates = []
    for col in df.columns:
        cl = cols_lower[col]
        if any(pat in cl for pat in id_patterns):
            id_candidates.append(col)

    # ── Candidate time columns ──────────────────────────────────────────
    time_patterns = [
        "año", "anio", "year", "mes", "month", "periodo", "period",
        "trimestre", "quarter", "fecha", "date", "wave", "round",
    ]
    time_candidates = []
    for col in df.columns:
        cl = cols_lower[col]
        if any(pat in cl for pat in time_patterns):
            time_candidates.append(col)

    # Also check for datetime dtype columns
    for col in df.columns:
        if str(df[col].dtype).startswith("datetime"):
            if col not in time_candidates:
                time_candidates.append(col)

    # ── If wide panel detected, filter out suffixed false positives ────
    # Columns like aÑo_20, aÑo_21 are NOT real time columns — they are
    # year-suffixed variants of the same variable
    if wide_info["detected"]:
        import re
        suffixes = wide_info["year_suffixes"]
        suffix_pattern = re.compile(r'^(.+?)[_](' + '|'.join(suffixes) + r')$')
        # Remove time candidates that are actually suffixed columns
        time_candidates_clean = []
        for col in time_candidates:
            if not suffix_pattern.match(col):
                time_candidates_clean.append(col)
        time_candidates = time_candidates_clean

        # Similarly clean ID candidates — remove suffixed versions
        id_candidates_clean = []
        for col in id_candidates:
            if not suffix_pattern.match(col):
                id_candidates_clean.append(col)
        id_candidates = id_candidates_clean

    # ── Determine data structure ────────────────────────────────────────
    structure = "cross-sectional"  # default
    panel_details = {}

    # ── Wide-format panel takes priority if detected ───────────────────
    if wide_info["detected"] and wide_info["n_periods"] >= 2:
        structure = "wide-panel"
        panel_details = {
            "format": "wide",
            "n_time_periods": wide_info["n_periods"],
            "time_values": wide_info["year_values"],
            "year_suffixes": wide_info["year_suffixes"],
            "suffix_pattern": wide_info["pattern"],
            "n_core_vars": wide_info["n_core_base_vars"],
            "core_vars_sample": wide_info["core_base_vars_sample"],
            "unsuffixed_cols": wide_info["unsuffixed_cols"],
            "vars_per_period": wide_info["n_suffixed_vars_per_period"],
            "note": (
                "Data is in WIDE format — each time period's variables have a year suffix "
                f"(e.g., {wide_info['core_base_vars_sample'][0]}_{wide_info['year_suffixes'][0]}, "
                f"{wide_info['core_base_vars_sample'][0]}_{wide_info['year_suffixes'][-1]}). "
                "Must reshape to long format for panel econometrics."
            ) if wide_info["core_base_vars_sample"] else "Wide-format panel detected.",
        }
        # Also try long-format detection as secondary info
        if id_candidates and time_candidates:
            panel_details["long_format_id_candidates"] = id_candidates[:5]
            panel_details["long_format_time_candidates"] = time_candidates[:5]

    elif id_candidates and time_candidates:
        # Standard long-format detection
        best_id = id_candidates[0]
        best_time = time_candidates[0]

        n_unique_ids = df[best_id].nunique()
        n_unique_times = df[best_time].nunique()

        # Panel = same IDs appear across multiple time periods
        # Key test: group by ID, count distinct time values per ID
        if n_unique_times >= 2:
            times_per_id = df.groupby(best_id)[best_time].nunique()
            ids_with_multiple_times = (times_per_id > 1).sum()
            pct_panel = ids_with_multiple_times / n_unique_ids * 100

            if pct_panel >= 30:
                structure = "panel"
                panel_details = {
                    "format": "long",
                    "id_column": best_id,
                    "time_column": best_time,
                    "n_unique_ids": int(n_unique_ids),
                    "n_time_periods": int(n_unique_times),
                    "time_values": sorted(df[best_time].dropna().unique().tolist())[:20],
                    "pct_ids_multiple_periods": round(pct_panel, 1),
                    "avg_obs_per_id": round(rows / n_unique_ids, 1),
                }
            else:
                structure = "pooled-cross-sections"
                panel_details = {
                    "format": "long",
                    "id_column": best_id,
                    "time_column": best_time,
                    "n_unique_ids": int(n_unique_ids),
                    "n_time_periods": int(n_unique_times),
                    "time_values": sorted(df[best_time].dropna().unique().tolist())[:20],
                    "pct_ids_multiple_periods": round(pct_panel, 1),
                    "note": "Different individuals sampled each period — NOT panel tracking",
                }
        elif n_unique_times == 1:
            structure = "cross-sectional"
            panel_details = {
                "time_column": best_time,
                "single_period": str(df[best_time].iloc[0]),
            }
    elif time_candidates and not id_candidates:
        best_time = time_candidates[0]
        n_unique_times = df[best_time].nunique()
        if n_unique_times >= 2:
            structure = "repeated-cross-sections"
            panel_details = {
                "time_column": best_time,
                "n_time_periods": int(n_unique_times),
                "time_values": sorted(df[best_time].dropna().unique().tolist())[:20],
                "note": "Multiple time periods but no individual ID for tracking",
            }

    return {
        "id_cols": id_candidates,
        "time_cols": time_candidates,
        "structure": structure,
        "panel_details": panel_details,
        "wide_panel": wide_info if wide_info["detected"] else None,
    }


def _generate_data_summary(df) -> str:
    """Generate a compact, structured summary of the dataset for Claude.

    Groups variables by prefix to keep the summary under ~3K chars even for
    datasets with 1000+ columns (e.g., ENAHO with 1425 variables).
    """
    import re
    rows, cols = df.shape

    lines = [
        f"Rows: {rows:,}",
        f"Columns: {cols}",
        f"Numeric: {len(df.select_dtypes(include='number').columns)} | "
        f"Categorical: {len(df.select_dtypes(include='object').columns)} | "
        f"Datetime: {len(df.select_dtypes(include='datetime').columns)}",
    ]

    # ── Group variables by prefix ─────────────────────────────────────
    # Extract prefix: letters before digits (P500 -> P5, UBIGEO -> UBIGEO)
    prefix_groups = {}
    for col in df.columns:
        match = re.match(r'^([A-Za-z]+\d{0,2})', col)
        prefix = match.group(1) if match else col[:6]
        if prefix not in prefix_groups:
            prefix_groups[prefix] = []
        prefix_groups[prefix].append(col)

    # Sort by prefix, merge small groups
    lines.append("\n## Variable Groups (by prefix)")
    sorted_prefixes = sorted(prefix_groups.keys())
    for prefix in sorted_prefixes:
        group_cols = prefix_groups[prefix]
        n_vars = len(group_cols)
        if n_vars == 1:
            # Single variable — show inline stats
            col = group_cols[0]
            nuniq = df[col].nunique()
            miss_pct = df[col].isnull().mean() * 100
            if df[col].dtype in ("float64", "int64", "float32", "int32"):
                lines.append(
                    f"  {col}: numeric, {nuniq} unique, "
                    f"mean={df[col].mean():.2f}, miss={miss_pct:.0f}%"
                )
            else:
                vals = df[col].dropna().unique().tolist()[:5]
                lines.append(
                    f"  {col}: {nuniq} unique vals, miss={miss_pct:.0f}% — {vals}"
                )
        else:
            # Group of variables — show summary
            col_range = f"{group_cols[0]}..{group_cols[-1]}" if n_vars > 2 else ", ".join(group_cols)
            avg_miss = df[group_cols].isnull().mean().mean() * 100
            n_numeric = sum(1 for c in group_cols if df[c].dtype in ("float64", "int64", "float32", "int32"))
            lines.append(
                f"  {prefix}* ({n_vars} vars): {col_range} | "
                f"{n_numeric} numeric, {n_vars - n_numeric} categorical | "
                f"avg miss={avg_miss:.0f}%"
            )

    # ── Key variables: show detailed stats for top 20 most relevant ───
    # Heuristic: low missingness + high variance = more useful
    lines.append("\n## Key Variables (detailed stats, top 20)")
    numeric_cols = df.select_dtypes(include="number").columns
    if len(numeric_cols) > 0:
        # Score by: low missingness + moderate-to-high unique count
        col_scores = {}
        for col in numeric_cols:
            miss = df[col].isnull().mean()
            nuniq = df[col].nunique()
            # Prefer columns with low missingness and decent variation
            col_scores[col] = (1 - miss) * min(nuniq / 20, 1.0)
        top_cols = sorted(col_scores, key=col_scores.get, reverse=True)[:20]

        for col in top_cols:
            s = df[col]
            miss_pct = s.isnull().mean() * 100
            lines.append(
                f"  {col}: mean={s.mean():.2f}, median={s.median():.2f}, "
                f"std={s.std():.2f}, min={s.min()}, max={s.max()}, "
                f"unique={s.nunique()}, miss={miss_pct:.0f}%"
            )

    # ── Categorical variables with few unique values ──────────────────
    cat_cols = df.select_dtypes(include="object").columns
    useful_cats = [(c, df[c].nunique()) for c in cat_cols if df[c].nunique() <= 20]
    if useful_cats:
        lines.append("\n## Categorical Variables (<=20 unique)")
        for col, nuniq in sorted(useful_cats, key=lambda x: x[1])[:15]:
            vals = df[col].dropna().unique().tolist()[:10]
            lines.append(f"  {col}: {nuniq} unique — {vals}")

    # ── High missingness warning ──────────────────────────────────────
    miss = df.isnull().mean()
    high_miss = miss[miss > 0.5].sort_values(ascending=False)
    if len(high_miss) > 0:
        lines.append(f"\n## High Missingness (>50%): {len(high_miss)} variables")
        for col, pct in high_miss.head(5).items():
            lines.append(f"  {col}: {pct:.0%} missing")

    return "\n".join(lines)


def _profile_directory(data_path: str) -> dict:
    """Profile a folder of datasets instead of a single file.

    Detects main data files, reads README if present, profiles the most
    important file. Returns same dict shape as _profile_dataset plus
    extra key 'folder_context' with human-readable folder description.
    """
    import pandas as pd

    p = Path(data_path)
    DATA_EXTS = {".dta", ".csv", ".xlsx", ".xls", ".parquet", ".tab", ".tsv", ".json"}

    # ── 1. Collect all data files ──────────────────────────────────────────
    all_files: list[Path] = []
    for ext in DATA_EXTS:
        all_files.extend(p.rglob(f"*{ext}"))
    all_files.sort(key=lambda f: f.stat().st_size, reverse=True)

    if not all_files:
        print(f"  [data-dir] No data files found in {data_path}")
        sys.exit(1)

    print(f"  [data-dir] Found {len(all_files)} data file(s) in folder")

    # ── 2. Heuristic: pick main file ───────────────────────────────────────
    MAIN_KEYWORDS = ("final", "main", "analysis", "master", "base", "panel")
    MAIN_FOLDERS  = ("finales", "final", "clean", "processed", "analysis")

    def _score(f: Path) -> int:
        score = 0
        if any(k in f.stem.lower() for k in MAIN_KEYWORDS):
            score += 10
        if any(k in f.parts[-2].lower() for k in MAIN_FOLDERS):
            score += 8
        if f.suffix == ".dta":
            score += 3
        score += min(5, f.stat().st_size // (1024 * 1024))  # MB bonus, cap 5
        return score

    scored = sorted(all_files, key=_score, reverse=True)
    main_file = scored[0]
    print(f"  [data-dir] Primary file selected: {main_file.relative_to(p)}")

    # ── 3. Read README ─────────────────────────────────────────────────────
    readme_text = ""
    for readme_name in ("README.txt", "readme.txt", "README.md", "readme.md"):
        readme_path = p / readme_name
        if readme_path.exists():
            try:
                readme_text = readme_path.read_text(encoding="utf-8", errors="replace")[:3000]
                print(f"  [data-dir] README found: {readme_name}")
                break
            except Exception:
                pass

    # ── 4. Build folder manifest ───────────────────────────────────────────
    manifest_lines = []
    for f in all_files[:30]:
        rel = f.relative_to(p)
        size_kb = f.stat().st_size / 1024
        marker = " ← [PRIMARY]" if f == main_file else ""
        manifest_lines.append(f"  {rel}  ({size_kb:.0f} KB){marker}")
    manifest = "\n".join(manifest_lines)
    if len(all_files) > 30:
        manifest += f"\n  ... and {len(all_files) - 30} more files"

    folder_context = (
        f"FOLDER INPUT — {len(all_files)} data file(s) detected.\n"
        f"Folder: {p.name}\n\n"
        f"Files:\n{manifest}\n"
    )
    if readme_text:
        folder_context += f"\nREADME:\n{readme_text}\n"

    # ── 5. Profile main file ───────────────────────────────────────────────
    df = _load_dataframe(str(main_file))
    rows, cols = df.shape
    missing = df.isnull().mean().to_dict()
    structure_info = _detect_id_and_time_columns(df)
    data_summary = _generate_data_summary(df)

    print(f"  [data-dir] Primary file: {rows} rows x {cols} cols "
          f"({structure_info['structure']})")

    profile = {
        "rows": rows,
        "cols": cols,
        "columns": list(df.columns),
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "missing_pct": {c: round(v * 100, 1) for c, v in missing.items()},
        "structure": structure_info["structure"],
        "panel_flag": structure_info["structure"] in ("panel", "wide-panel"),
        "panel_details": structure_info["panel_details"],
        "id_cols": structure_info["id_cols"],
        "time_cols": structure_info["time_cols"],
        "wide_panel": structure_info.get("wide_panel"),
        "data_summary": data_summary,
        "sample_rows": df.head(5).to_string(),
        "folder_context": folder_context,
        "all_files": [str(f.relative_to(p)) for f in all_files],
        "primary_file": str(main_file.relative_to(p)),
    }
    return profile


def _profile_dataset(data_path: str) -> dict:
    """Run deep profiling on the user's dataset.

    Returns keys: rows, cols, columns, dtypes, missing_pct, structure,
    panel_details, data_summary, sample_rows.
    Accepts a single file OR a directory (auto-detects main file).
    """
    try:
        import pandas as pd
    except ImportError:
        print("  [error] pandas is required for Path B. Run: pip install pandas")
        sys.exit(1)

    if Path(data_path).is_dir():
        return _profile_directory(data_path)

    df = _load_dataframe(data_path)
    rows, cols = df.shape
    missing = df.isnull().mean().to_dict()

    # Deep structure detection
    structure_info = _detect_id_and_time_columns(df)
    data_summary = _generate_data_summary(df)

    print(f"  [data] Structure detected: {structure_info['structure']}")
    if structure_info["id_cols"]:
        print(f"  [data] ID columns: {', '.join(structure_info['id_cols'][:5])}")
    if structure_info["time_cols"]:
        print(f"  [data] Time columns: {', '.join(structure_info['time_cols'][:5])}")
    if structure_info.get("wide_panel"):
        wp = structure_info["wide_panel"]
        print(f"  [data] Wide-format panel detected: {wp['n_periods']} periods")
        print(f"  [data] Year suffixes: {', '.join(wp['year_suffixes'])}")
        print(f"  [data] Years: {wp['year_values']}")
        print(f"  [data] Core variables across periods: {wp['n_core_base_vars']}")
        if wp["core_base_vars_sample"]:
            sample = ', '.join(wp['core_base_vars_sample'][:10])
            print(f"  [data] Sample base vars: {sample}")
    elif structure_info["panel_details"]:
        pd_info = structure_info["panel_details"]
        if "pct_ids_multiple_periods" in pd_info:
            print(f"  [data] IDs in multiple periods: {pd_info['pct_ids_multiple_periods']}%")
        if "n_time_periods" in pd_info:
            print(f"  [data] Time periods: {pd_info['n_time_periods']}")

    profile = {
        "rows": rows,
        "cols": cols,
        "columns": list(df.columns),
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "missing_pct": {c: round(v * 100, 1) for c, v in missing.items()},
        "structure": structure_info["structure"],
        "panel_flag": structure_info["structure"] in ("panel", "wide-panel"),
        "panel_details": structure_info["panel_details"],
        "id_cols": structure_info["id_cols"],
        "time_cols": structure_info["time_cols"],
        "wide_panel": structure_info.get("wide_panel"),
        "data_summary": data_summary,
        "sample_rows": df.head(5).to_string(),
    }

    return profile


def _early_warning(profile: dict) -> list[str]:
    """Check if the dataset is likely inadequate.  Returns a list of warnings."""
    warnings = []
    if profile["rows"] < 100:
        warnings.append(f"Very small sample: {profile['rows']} rows (< 100). Econometric power may be insufficient.")
    if profile["cols"] < 5:
        warnings.append(f"Very few variables: {profile['cols']} columns (< 5). Limited scope for controls / heterogeneity.")
    high_miss = [c for c, v in profile["missing_pct"].items() if v > 50]
    if high_miss:
        warnings.append(f"High missingness (>50%): {', '.join(high_miss[:5])}")
    return warnings


def _causal_design_warning(profile: dict) -> None:
    """Detect limitations in the data structure that will cap the paper's score.

    Prints warnings about missing pre-treatment data, limited time dimension,
    or cross-sectional design — BEFORE the user invests hours in the pipeline.
    """
    structure = profile.get("structure", "cross-sectional")
    panel_details = profile.get("panel_details", {})
    wide_panel = profile.get("wide_panel")

    # Determine time coverage
    time_values = panel_details.get("time_values", [])
    year_suffixes = panel_details.get("year_suffixes", [])
    n_periods = panel_details.get("n_time_periods", len(time_values) or len(year_suffixes))

    # Try to determine the earliest year in the data
    earliest_year = None
    if time_values:
        try:
            earliest_year = min(int(y) for y in time_values if str(y).isdigit())
        except (ValueError, TypeError):
            pass
    if not earliest_year and year_suffixes:
        try:
            raw = min(int(s) for s in year_suffixes)
            earliest_year = 2000 + raw if raw < 100 else raw
        except (ValueError, TypeError):
            pass

    # ── Print causal design assessment ─────────────────────────────────
    print(f"\n  {'=' * 60}")
    print(f"  CAUSAL DESIGN ASSESSMENT")
    print(f"  {'=' * 60}")

    issues = []
    score_ceiling = 95

    # Check 1: No time dimension at all
    if structure == "cross-sectional":
        score_ceiling = min(score_ceiling, 70)
        issues.append({
            "issue": "CROSS-SECTIONAL DATA (no time dimension)",
            "impact": "Cannot use DiD, event study, or individual FE. Score ceiling: ~70/100.",
            "fix": "Provide panel or repeated cross-section data spanning multiple years.",
        })

    # Check 2: Panel/temporal data but no pre-treatment period
    if structure in ("panel", "wide-panel", "pooled-cross-sections", "repeated-cross-sections"):
        # Detect if all data is post-2020 (COVID shock)
        if earliest_year and earliest_year >= 2020:
            score_ceiling = min(score_ceiling, 75)
            issues.append({
                "issue": f"NO PRE-TREATMENT DATA (earliest year: {earliest_year})",
                "impact": (
                    "Cannot test parallel trends or establish a clean pre-shock baseline. "
                    "Referees WILL ask for pre-trends. Score ceiling: ~75/100."
                ),
                "fix": (
                    "Provide data from 2017-2019 (at least 2-3 pre-treatment years). "
                    "For ENAHO: https://proyectos.inei.gob.pe/microdatos/"
                ),
            })

        # Check if only 1-2 pre-treatment years (weak pre-trends)
        elif earliest_year and earliest_year >= 2019 and n_periods <= 3:
            score_ceiling = min(score_ceiling, 80)
            issues.append({
                "issue": f"LIMITED PRE-TREATMENT DATA (only from {earliest_year}, {n_periods} periods)",
                "impact": "Pre-trend test possible but weak (only 1-2 pre-periods). Score ceiling: ~80/100.",
                "fix": "Add 1-2 more pre-treatment years for robust pre-trend testing.",
            })

    # Check 3: Short panel (few periods)
    if n_periods and n_periods < 3 and structure in ("panel", "wide-panel"):
        score_ceiling = min(score_ceiling, 80)
        issues.append({
            "issue": f"SHORT PANEL ({n_periods} periods only)",
            "impact": "Limited power for event study dynamics. Cannot show pre/post trajectory.",
            "fix": "Extend the panel to at least 4-5 periods (2+ pre, 2+ post treatment).",
        })

    # Check 4: Panel with very few time periods for dynamic effects
    if structure in ("panel", "wide-panel") and n_periods and n_periods >= 3:
        pre_periods = sum(1 for y in (time_values or []) if isinstance(y, (int, float)) and y < 2020)
        if wide_panel and year_suffixes:
            pre_periods = sum(1 for s in year_suffixes
                              if (2000 + int(s) if int(s) < 100 else int(s)) < 2020)
        post_periods = n_periods - pre_periods - 1  # -1 for treatment year
        if pre_periods == 0 and post_periods >= 2:
            # Already covered by Check 2, but add specific note
            pass
        elif pre_periods >= 2 and post_periods >= 2:
            print(f"\n  [ok] STRONG DESIGN POTENTIAL")
            print(f"       {pre_periods} pre-treatment + {post_periods} post-treatment periods")
            print(f"       Enables: DiD, event study with pre-trends, individual FE")
            print(f"       Score ceiling: ~90-95/100")

    # Print issues
    if issues:
        print(f"\n  Score ceiling with current data: ~{score_ceiling}/100\n")
        for i, w in enumerate(issues, 1):
            print(f"  [{i}] {w['issue']}")
            print(f"      Impact: {w['impact']}")
            print(f"      To fix: {w['fix']}")
            print()

        print(f"  These limitations are inherent to the DATA, not the methodology.")
        print(f"  The pipeline will proceed, but the final score will be capped")
        print(f"  regardless of how well the paper is written.")
    else:
        if score_ceiling >= 85:
            print(f"\n  [ok] Data structure supports strong causal designs.")
            print(f"       Score ceiling: ~{score_ceiling}/100")
        else:
            print(f"\n  [ok] No major structural limitations detected.")
            print(f"       Score ceiling: ~{score_ceiling}/100")

    print(f"  {'=' * 60}")


# ── Path C: data-first discovery ──────────────────────────────────────────────

def _run_path_c(project_dir: Path, state: dict) -> dict:
    """Path C: Search for high-quality datasets first, then suggest topics.

    1. Search APIs with broad queries for panel/causal datasets
    2. Download and profile top candidates
    3. Run feasibility assessment — keep only score_ceiling >= 85
    4. For qualifying datasets, ask Claude to suggest research topics
    5. User picks dataset + topic
    """
    from concurrent.futures import ThreadPoolExecutor
    from .stage1_5_data_loading import (
        _profile_dataset, _early_warning, _assess_feasibility,
        _try_download_dataverse, _try_download_zenodo, _try_download_direct,
    )
    import time as _time

    print(f"\n{'=' * 60}")
    print(f"STAGE 1: Discovery - Path C (data-first)")
    print("=" * 60)
    print("  Searching for high-quality datasets worldwide...")
    print("  Goal: find datasets that can support a 85+ score paper\n")

    t0 = _time.time()

    # ── Phase 1: Search for datasets using registry + journal search ────
    all_candidates = []

    # ── Detect datasets already used in previous projects ─────────────
    from ..config import PAPERS_HQ
    from ..dataset_registry import (
        get_curated_datasets, search_multiple_journals,
        build_search_plan, JOURNAL_COLLECTIONS,
    )

    projects_dir = PAPERS_HQ / "projects"
    used_datasets = set()
    if projects_dir.exists():
        for proj in projects_dir.iterdir():
            if not proj.is_dir():
                continue
            state_file = proj / "pipeline_state.json"
            if state_file.exists():
                try:
                    prev_state = json.loads(state_file.read_text(encoding="utf-8"))
                    prev_data = prev_state.get("stages", {}).get("stage1", {}).get("data_path", "")
                    if prev_data:
                        used_datasets.add(Path(prev_data).name.lower())
                except Exception:
                    pass
    if used_datasets:
        print(f"  [search] Excluding {len(used_datasets)} datasets from previous projects:")
        for d in sorted(used_datasets):
            print(f"    - {d}")

    # ── Strategy: Curated registry + journal-directed search ──────────
    # Phase 1a: Get curated datasets (verified, with metadata)
    # Phase 1b: Search journal Dataverse/Zenodo collections (new datasets)
    # Phase 1c: Optional Claude web search (slow, used as supplement)

    print("  [search] Phase 1a: Loading curated datasets from registry...")

    # ── Phase 1a: Get curated datasets (verified, with metadata) ──────
    curated = get_curated_datasets(exclude_names=used_datasets)
    print(f"  [search] Curated registry: {len(curated)} datasets available")
    for ds in curated[:5]:
        print(f"    - [Tier {ds.get('design_tier', '?')}] {ds.get('title', '?')[:60]}")

    # ── Phase 1b: Search journal Dataverse/Zenodo collections ─────────
    print(f"\n  [search] Phase 1b: Searching journal collections...")
    import random
    random.seed(int(_time.time()) % 100000)

    # Pick journals to search (rotate for diversity)
    top_journals = ["QJE", "REStat", "JPE"]
    other_journals = [k for k in JOURNAL_COLLECTIONS if k not in top_journals]
    random.shuffle(other_journals)
    search_journals = top_journals[:2] + other_journals[:2]

    journal_results = search_multiple_journals(
        journal_keys=search_journals, max_per_journal=3
    )

    # Filter out already-used datasets
    journal_results = [
        r for r in journal_results
        if not any(used in r.get("name", "").lower() for used in used_datasets)
    ]
    print(f"  [search] Journal search: {len(journal_results)} new datasets")

    # ── Phase 1c: open-data portals with downloadable file resources ──
    # All sources here expose direct file URLs (no auth, no licensing) so
    # they fit Path C's download-and-validate flow. DBnomics and World Bank
    # are excluded because they return JSON APIs not files. The downstream
    # quality filter (Q1-Q8) + _MIN_ROWS / _MIN_COLS / _MIN_SCORE_CEILING
    # thresholds reject anything below paper-quality, so no need to gate
    # on causal structure here — bad candidates are filtered post-download.
    print(f"\n  [search] Phase 1c: Searching 12 open-data portals...")
    portal_results = []
    # English queries hit the anglo + EU/IDB portals + Socrata; native-language
    # queries hit the FR/DE/IT/MX portals (English barely matches anything).
    # FAOSTAT uses agriculture/development-themed queries since it's domain
    # specific.
    en_queries = [
        "panel survey",
        "longitudinal household",
        "policy evaluation",
        "impact evaluation",
    ]
    fr_queries = ["enquête ménages", "panel santé"]
    de_queries = ["arbeitslosigkeit", "haushaltsbefragung"]
    it_queries = ["occupazione", "famiglia panel"]
    es_queries = ["encuesta hogares", "evaluación impacto"]
    fao_queries = ["food security", "agricultural production",
                   "emissions agriculture", "land use crops"]

    random.shuffle(en_queries)
    for q in en_queries[:2]:
        portal_results.extend(_search_datagov(q, max_results=3))
        portal_results.extend(_search_idb(q, max_results=3))
        portal_results.extend(_search_eu_opendata(q, max_results=3))
        portal_results.extend(_search_data_gov_uk(q, max_results=3))
        portal_results.extend(_search_data_gov_au(q, max_results=3))
        portal_results.extend(_search_open_canada(q, max_results=3))
        # Socrata federated catalog responds well to English queries
        portal_results.extend(_search_socrata(q, max_results=3))

    # Native-language portals: 1 query each (they only contribute when the
    # topic happens to match their language anyway)
    portal_results.extend(_search_data_gouv_fr(random.choice(fr_queries), max_results=3))
    portal_results.extend(_search_govdata_de(random.choice(de_queries), max_results=3))
    portal_results.extend(_search_dati_gov_it(random.choice(it_queries), max_results=3))
    portal_results.extend(_search_datos_gob_mx(random.choice(es_queries), max_results=3))

    # FAOSTAT bulk catalog (agriculture / food / environment country panels)
    portal_results.extend(_search_faostat(random.choice(fao_queries), max_results=3))

    # Keep only candidates that actually expose a downloadable file —
    # Path C cannot profile metadata-only entries.
    downloadable_portal = [r for r in portal_results if r.get("download_url")]

    # Filter out already-used and dedupe by download URL
    seen_dl = set()
    filtered_portal = []
    for r in downloadable_portal:
        dl = r.get("download_url", "")
        if dl in seen_dl:
            continue
        seen_dl.add(dl)
        if any(used in r.get("name", "").lower() for used in used_datasets):
            continue
        filtered_portal.append(r)
    print(f"  [search] Open-data portals: {len(filtered_portal)} downloadable candidates "
          f"(from {len(portal_results)} total metadata hits)")

    # ── Combine: curated first, then journal results ──────────────────
    CURATED_PACKAGES = []

    for ds in curated:
        CURATED_PACKAGES.append({
            "title": ds.get("title", ""),
            "dataverse_doi": ds.get("dataverse_doi", ""),
            "url": ds.get("url", ""),
            "method": ds.get("design", "unknown"),
            "area": ds.get("area", "mixed"),
            "design_tier": ds.get("design_tier", 3),
            "provider": f"Registry ({ds.get('journal', '?')})",
            "score_ceiling": ds.get("score_ceiling", 80),
        })

    for jr in journal_results:
        CURATED_PACKAGES.append({
            "title": jr.get("name", "")[:70],
            "dataverse_doi": jr.get("doi", ""),
            "url": jr.get("url", ""),
            "method": "unknown",
            "area": "mixed",
            "design_tier": 2,
            "provider": jr.get("provider", "Journal Search"),
        })

    # Phase 1c contributions: open-data portals (data.gov + IDB)
    # Use download_url as the primary URL so the existing download loop
    # (which calls _try_download_direct as fallback) hits the file directly.
    # design_tier=3 by default — these are unverified for causal structure;
    # the post-download Q1-Q8 quality filter is the real gate.
    for pr in filtered_portal:
        CURATED_PACKAGES.append({
            "title": pr.get("name", "")[:70],
            "dataverse_doi": "",
            "url": pr.get("download_url") or pr.get("url", ""),
            "method": "unknown",
            "area": "mixed",
            "design_tier": 3,
            "provider": pr.get("provider", "Open Data Portal"),
        })

    # Sort by tier
    packages = sorted(CURATED_PACKAGES, key=lambda x: x.get("design_tier", 9))

    n_t1 = sum(1 for p in packages if p.get("design_tier") == 1)
    n_t2 = sum(1 for p in packages if p.get("design_tier") == 2)
    n_t3 = sum(1 for p in packages if p.get("design_tier", 9) >= 3)
    print(f"\n  [search] Combined: {n_t1} tier-1 (RCT), {n_t2} tier-2, {n_t3} tier-3+")

    replication_papers = packages
    print(f"  [search] {len(replication_papers)} total candidates")

    # Convert packages to candidates with DOIs or URLs
    for paper in replication_papers:
        doi = paper.get("dataverse_doi", "")
        direct_url = paper.get("url", "")

        if doi:
            url = f"https://doi.org/{doi}" if not doi.startswith("http") else doi
        elif direct_url:
            url = direct_url
        else:
            continue

        all_candidates.append({
            "name": paper.get("title", "Unknown"),
            "provider": paper.get("provider", "Harvard Dataverse"),
            "url": url,
            "description": paper.get("data_description", ""),
            "method": paper.get("method", ""),
            "area": paper.get("area", ""),
        })

    # ── Fallback: also search APIs directly if curated list somehow empty
    if len(all_candidates) < 3:
        print("  [search] Phase 2: Supplementing with direct API search...")
        for q in ["replication wages panel", "replication education RCT"]:
            results = _search_dataverse(q, max_results=2)
            all_candidates.extend(results)

    # Deduplicate by URL
    seen_urls = set()
    unique_candidates = []
    for c in all_candidates:
        url = c.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_candidates.append(c)

    elapsed = _time.time() - t0
    print(f"\n  [search] Found {len(unique_candidates)} unique candidates ({elapsed:.0f}s)")

    # ── Phase 2: Download and profile ─────────────────────────────────
    print(f"\n  [download] Attempting to download top candidates...\n")
    data_dir = project_dir / "data" / "external"
    data_dir.mkdir(parents=True, exist_ok=True)

    qualified = []  # datasets with score_ceiling >= 85
    attempted = 0
    MAX_ATTEMPTS = 15  # try more candidates to find qualifying datasets

    # Pre-filter: remove candidates with known-bad DOIs.
    # Budget split: 7 slots for curated/journal (tier 1-2 priority) + 8
    # reserved slots for open-data portals so they get a fair chance to be
    # tried even though they sort last by design_tier. Increased from 7 to 8
    # because Phase 1c now queries 12 portals (added Socrata + FAOSTAT).
    from ..dataset_registry import _KNOWN_BAD_DOIS
    PORTAL_RESERVED = 8
    MAIN_BUDGET = MAX_ATTEMPTS - PORTAL_RESERVED

    portal_provider_marks = (
        "data.gov", "idb numbers", "open data portal",
        "eu open data", "data.gov.uk", "data.gouv.fr",
        "data.gov.au", "open.canada.ca", "datos.gob.mx",
        "govdata.de", "dati.gov.it",
        "socrata", "faostat",
    )
    is_portal = lambda c: any(m in c.get("provider", "").lower() for m in portal_provider_marks)

    pre_filtered = []
    portal_pool = []
    n_skipped_bad = 0
    for c in unique_candidates[:MAX_ATTEMPTS * 3]:
        doi = ""
        c_url = c.get("url", "")
        if "10.7910/DVN/" in c_url:
            import re as _re_doi
            m = _re_doi.search(r'(10\.7910/DVN/\w+)', c_url)
            if m:
                doi = m.group(1)
        if doi and doi in _KNOWN_BAD_DOIS:
            n_skipped_bad += 1
            continue

        if is_portal(c):
            if len(portal_pool) < PORTAL_RESERVED:
                portal_pool.append(c)
        else:
            if len(pre_filtered) < MAIN_BUDGET:
                pre_filtered.append(c)

        if len(pre_filtered) >= MAIN_BUDGET and len(portal_pool) >= PORTAL_RESERVED:
            break

    # Append portal candidates after the main pool so registry/journal entries
    # are still tried first (preserving Path C's "validated first" priority).
    pre_filtered.extend(portal_pool)

    if n_skipped_bad > 0:
        print(f"  [filter] Skipped {n_skipped_bad} known-bad DOIs from previous validation runs")
    if portal_pool:
        print(f"  [filter] Reserved {len(portal_pool)} slots for open-data portal candidates")

    for i, candidate in enumerate(pre_filtered):
        attempted += 1
        name = candidate.get("name", "Unknown")[:60]
        url = candidate.get("url", "")
        provider = candidate.get("provider", "").lower()
        print(f"  [{attempted}/{min(len(pre_filtered), MAX_ATTEMPTS)}] {name}")

        # Try to download
        local_path = None
        if "dataverse" in provider or "doi.org/10.7910" in url or "dataverse" in url:
            local_path = _try_download_dataverse(url, data_dir)
        elif "zenodo" in provider or "zenodo.org" in url:
            local_path = _try_download_zenodo(url, data_dir)
        if not local_path:
            local_path = _try_download_direct(url, data_dir)

        if not local_path:
            print(f"       [skip] Could not download")
            continue

        # Quick pre-check: read just the header + first 10 rows to validate
        # before expensive full profiling
        try:
            import pandas as _pd_quick
            _lp = str(local_path)
            if _lp.endswith(".dta"):
                _df_quick = _pd_quick.read_stata(_lp, iterator=True).read(10)
            elif _lp.endswith(".tab"):
                _df_quick = _pd_quick.read_csv(_lp, sep="\t", encoding="utf-8",
                                                nrows=10, low_memory=False)
            elif _lp.endswith((".csv", ".tsv")):
                _df_quick = _pd_quick.read_csv(_lp, encoding="latin-1",
                                                nrows=10, low_memory=False)
            else:
                _df_quick = None

            if _df_quick is not None:
                n_cols_quick = len(_df_quick.columns)
                if n_cols_quick < 5:
                    print(f"       [skip] Only {n_cols_quick} columns — too few for analysis")
                    continue
            del _df_quick
        except Exception:
            pass  # If quick check fails, proceed to full profiling

        # Profile
        try:
            profile = _profile_dataset(local_path)
            warnings = _early_warning(profile)
            feasibility = _assess_feasibility(
                [{"profile": profile, "dataset": candidate, "local_path": local_path, "warnings": warnings}],
                [],
            )
            ceiling = feasibility["score_ceiling"]
            tier = feasibility["max_tier"]

            # Boost ceiling for RCTs/experiments (identification is built-in)
            method_lower = candidate.get("method", "").lower()
            design_tier = candidate.get("design_tier", 9)
            if design_tier == 1 or any(k in method_lower for k in ["rct", "experiment", "randomiz"]):
                ceiling = max(ceiling, 90)  # RCTs have minimum 90 ceiling
                tier = min(tier, 1)
            elif design_tier == 2 or any(k in method_lower for k in ["natural experiment", "stagger", "did"]):
                ceiling = max(ceiling, 85)

            print(f"       [ok] {profile['rows']:,} rows x {profile['cols']} cols | "
                  f"Structure: {profile['structure']} | "
                  f"Ceiling: {ceiling}/100 | Tier: {tier}"
                  + (" [RCT BOOST]" if design_tier == 1 else ""))

            # ── Data quality filter ───────────────────────────────────
            # Reject datasets that look bad even if ceiling is high
            quality_reject = False
            quality_reasons = []

            try:
                import pandas as _pd_check

                # Load sample for quality checks
                ext = Path(local_path).suffix.lower()
                if ext == ".dta":
                    _df_q = _pd_check.read_stata(local_path)
                elif ext == ".tab":
                    _df_q = _pd_check.read_csv(local_path, sep="\t",
                                                encoding="latin-1", low_memory=False)
                elif ext == ".parquet":
                    _df_q = _pd_check.read_parquet(local_path)
                else:
                    _df_q = _pd_check.read_csv(local_path, encoding="latin-1",
                                                low_memory=False)

                n_rows, n_cols = _df_q.shape

                # Q1: Columns with >20% missing
                missing_pcts = _df_q.isnull().mean()
                high_missing_cols = (missing_pcts > 0.20).sum()
                high_missing_pct = 100 * high_missing_cols / max(n_cols, 1)

                if high_missing_pct > 20:
                    quality_reasons.append(
                        f"{high_missing_pct:.0f}% of columns have >20% missing data "
                        f"(threshold: 20%)"
                    )
                    quality_reject = True

                # Q2: No identifiable treatment variable
                treat_keywords = ["treat", "treatment", "arm", "group", "condition",
                                  "assigned", "randomiz", "intervent", "program"]
                has_treat_var = any(
                    any(kw in col.lower() for kw in treat_keywords)
                    for col in _df_q.columns
                )
                if not has_treat_var:
                    quality_reasons.append(
                        "No variable name suggests treatment assignment"
                    )
                    # Warning, not rejection — treatment could have non-obvious name

                # Q3: Column names are codes without meaning
                code_pattern_cols = sum(
                    1 for col in _df_q.columns
                    if len(col) <= 6 and any(c.isdigit() for c in col)
                    and not col.lower() in ("year", "age", "id", "n", "sex")
                )
                code_pct = 100 * code_pattern_cols / max(n_cols, 1)
                if code_pct > 60:
                    # Check if there's a README
                    data_dir = Path(local_path).parent
                    has_readme = any(
                        (data_dir / f).exists()
                        for f in ["README.md", "README.txt", "readme.md",
                                  "codebook.txt", "codebook.pdf", "CODEBOOK.md"]
                    )
                    if not has_readme:
                        quality_reasons.append(
                            f"{code_pct:.0f}% of columns are coded names "
                            f"(e.g., Q49, VAR001) with no codebook"
                        )
                        quality_reject = True

                # Q4: Column/row ratio too high AND high missing = survey arms as columns
                # Only reject if BOTH ratio is high AND most columns are mostly empty
                # This avoids rejecting legitimate datasets with many baseline covariates
                col_row_ratio = n_cols / max(n_rows, 1)
                if col_row_ratio > 0.40 and high_missing_pct > 20:
                    quality_reasons.append(
                        f"Column/row ratio = {col_row_ratio:.0%} ({n_cols} cols / {n_rows} rows) "
                        f"AND {high_missing_pct:.0f}% columns >20% missing — "
                        f"likely survey with treatment arms encoded as columns"
                    )
                    quality_reject = True

                # Q5: Missing data treatment plan
                # For datasets that pass, document the missing data situation
                if not quality_reject:
                    avg_missing = missing_pcts.mean() * 100
                    cols_over_20 = high_missing_cols
                    if cols_over_20 > 0:
                        print(f"       [missing] {cols_over_20}/{n_cols} columns "
                              f"have >20% missing (avg: {avg_missing:.1f}%)")
                        print(f"       [missing] Strategy: listwise deletion for "
                              f"<5% missing outcomes; multiple imputation or "
                              f"bounds for 5-20% missing")

                # Q6: Variable usability — check that string variables have
                # classifiable values (not corrupted encoding)
                str_cols = _df_q.select_dtypes(include=["object"]).columns
                n_corrupted_cols = 0
                for sc in str_cols[:20]:  # check first 20 string columns
                    vals = _df_q[sc].dropna()
                    if len(vals) == 0:
                        continue
                    # Check if majority of values are replacement characters (U+FFFD)
                    try:
                        sample = vals.astype(str).head(100)
                        n_replacement = sample.str.contains('\ufffd', na=False).sum()
                        if n_replacement > len(sample) * 0.5:
                            n_corrupted_cols += 1
                    except Exception:
                        pass

                if n_corrupted_cols > 0:
                    quality_reasons.append(
                        f"{n_corrupted_cols} string columns have >50% corrupted encoding "
                        f"(replacement characters). Key variables may be unreadable."
                    )
                    print(f"       [warn] {n_corrupted_cols} columns with corrupted encoding")

                # Q7: Treatment variable detectability — check if any column
                # looks like a treatment assignment with enough classifiable values
                treatment_candidates = [c for c in _df_q.columns
                                       if any(kw in c.lower() for kw in
                                              ["treat", "assign", "group", "arm",
                                               "condition", "interv", "random",
                                               "control", "placebo"])]
                if not treatment_candidates:
                    # No obvious treatment column — check if there's a binary/few-valued
                    # column with balanced groups (potential treatment)
                    for c in _df_q.select_dtypes(include=["number"]).columns:
                        nuniq = _df_q[c].nunique()
                        if 2 <= nuniq <= 5:
                            val_counts = _df_q[c].value_counts()
                            min_pct = val_counts.min() / val_counts.sum()
                            if min_pct >= 0.15:  # at least 15% in smallest group
                                treatment_candidates.append(c)
                                break

                if not treatment_candidates:
                    quality_reasons.append(
                        "No variable name suggests treatment assignment"
                    )

                # Q8: Effective N — if treatment column found, check usable N
                effective_n = n_rows
                if treatment_candidates:
                    tc = treatment_candidates[0]
                    tc_valid = _df_q[tc].dropna()
                    # Check for encoding issues in string treatment vars
                    if tc_valid.dtype == "object":
                        try:
                            n_readable = tc_valid.astype(str).apply(
                                lambda x: not any(ord(c) == 0xFFFD for c in x)
                            ).sum()
                            effective_n = int(n_readable)
                            if effective_n < n_rows * 0.5:
                                quality_reasons.append(
                                    f"Treatment variable '{tc}' has only "
                                    f"{effective_n}/{n_rows} ({100*effective_n/n_rows:.0f}%) "
                                    f"readable values — encoding corruption"
                                )
                                if effective_n < 100:
                                    quality_reasons.append(
                                        f"Effective N = {effective_n} after encoding filter "
                                        f"(too small for reliable inference)"
                                    )
                                    quality_reject = True
                        except Exception:
                            pass

                del _df_q

            except Exception as q_err:
                print(f"       [quality] Could not run quality checks: {q_err}")

            if quality_reject:
                print(f"       [REJECT] Data quality too low:")
                for reason in quality_reasons:
                    print(f"         - {reason}")
                continue  # skip this dataset

            if quality_reasons and not quality_reject:
                print(f"       [warn] Quality concerns:")
                for reason in quality_reasons:
                    print(f"         - {reason}")

            if ceiling >= 85:
                qualified.append({
                    "candidate": candidate,
                    "local_path": local_path,
                    "profile": profile,
                    "feasibility": feasibility,
                    "warnings": warnings,
                })
                print(f"       *** QUALIFIES (score ceiling >= 85) ***")

        except Exception as e:
            print(f"       [error] Could not profile: {e}")

        # Stop early if we have 3+ qualified datasets
        if len(qualified) >= 3:
            print(f"\n  [ok] Found {len(qualified)} qualifying datasets, stopping search")
            break

    # ── Phase 3: If no qualified datasets, let user provide ───────────
    if not qualified:
        print(f"\n  No datasets with score ceiling >= 85 found automatically.")
        print(f"  You can provide a dataset path, or try Path A with a specific topic.\n")
        print("\a", end="", flush=True)
        while True:
            choice = input("  Enter dataset path (or 'quit' to exit): ").strip().strip('"')
            if choice.lower() == "quit":
                import sys
                sys.exit(0)
            elif choice and Path(choice).exists():
                try:
                    profile = _profile_dataset(choice)
                    warnings = _early_warning(profile)
                    feasibility = _assess_feasibility(
                        [{"profile": profile, "dataset": {"name": Path(choice).name},
                          "local_path": choice, "warnings": warnings}],
                        [],
                    )
                    qualified.append({
                        "candidate": {"name": Path(choice).name, "url": "user-provided"},
                        "local_path": choice,
                        "profile": profile,
                        "feasibility": feasibility,
                        "warnings": warnings,
                    })
                    print(f"  [ok] Profiled: {profile['rows']:,} rows x {profile['cols']} cols "
                          f"(ceiling: {feasibility['score_ceiling']})")
                    break
                except Exception as e:
                    print(f"  [error] {e}")
            else:
                print(f"  File not found: {choice}")

    # ── Phase 4: Show qualifying datasets and suggest topics ──────────
    print(f"\n  {'=' * 60}")
    print(f"  QUALIFYING DATASETS (score ceiling >= 85)")
    print(f"  {'=' * 60}")

    for i, q in enumerate(qualified, 1):
        f = q["feasibility"]
        p = q["profile"]
        print(f"\n  [{i}] {q['candidate'].get('name', '?')[:70]}")
        print(f"      File:      {Path(q['local_path']).name}")
        print(f"      Rows:      {p['rows']:,}")
        print(f"      Columns:   {p['cols']}")
        print(f"      Structure: {p['structure']}")
        print(f"      Ceiling:   {f['score_ceiling']}/100")
        print(f"      Max tier:  {f['max_tier']} ({f['tier_label']})")
        print(f"      Methods:   {', '.join(f['allowed_methods'][:5])}")
        if p.get("columns"):
            vars_preview = ", ".join(p["columns"][:15])
            print(f"      Variables: {vars_preview}")
            if len(p["columns"]) > 15:
                print(f"                 ... ({p['cols']} total)")

    # ── Phase 5: Ask Claude to suggest topics ─────────────────────────
    print(f"\n  [topics] Generating research topic suggestions...")

    # Build data summary for Claude
    data_summaries = []
    for i, q in enumerate(qualified, 1):
        p = q["profile"]
        f = q["feasibility"]
        cols = ", ".join(p.get("columns", [])[:30])
        data_summaries.append(
            f"Dataset {i}: {q['candidate'].get('name', '?')}\n"
            f"  Rows: {p['rows']:,}, Cols: {p['cols']}\n"
            f"  Structure: {p['structure']}\n"
            f"  Max tier: {f['max_tier']} ({f['tier_label']})\n"
            f"  Allowed methods: {', '.join(f['allowed_methods'])}\n"
            f"  Variables: {cols}\n"
            f"  Data summary: {p.get('data_summary', 'N/A')[:500]}\n"
        )

    topic_prompt = f"""You are a research advisor specializing in CAUSAL IDENTIFICATION.
Below are datasets that have been downloaded and profiled.

YOUR #1 PRIORITY: Find the EXOGENOUS VARIATION in each dataset.
Before suggesting any topic, ask: "What in this data creates a situation where
some units are treated and others are not, for reasons outside their control?"

IDENTIFICATION-FIRST APPROACH:
1. Look at the variables. Is there a POLICY CHANGE that affected some units first?
   (staggered rollout, regional reform, age threshold, income cutoff)
2. Is there a GEOGRAPHIC BOUNDARY that creates a discontinuity?
   (state borders, district lines, distance to something)
3. Is there a THRESHOLD that creates a sharp cutoff?
   (eligibility criteria, test scores, age limits, income limits)
4. Is there a NATURAL EXPERIMENT embedded in the data?
   (weather shock, unexpected policy, legal change, natural disaster)
5. Is there CROSS-SECTIONAL VARIATION in treatment intensity?
   (some regions more exposed than others for pre-determined reasons)

If you CANNOT find exogenous variation in a dataset, say so explicitly.
Do NOT propose a before-after design with universal treatment — these always
score below 80 and are rejected by referees.

DATASETS:
{"".join(data_summaries)}

For each dataset, suggest 2 specific research topics. Each MUST have:
- A source of exogenous variation that creates a credible comparison group
- Identification level A (control group) or B (dose variation) — NEVER level C
- A method that is compatible with the data structure

Return a JSON block:
```json
{{
  "suggestions": [
    {{
      "dataset_index": 1,
      "topic": "Short topic name",
      "research_question": "...",
      "method": "DiD with staggered adoption",
      "identification_level": "A",
      "identification": "Policy X was adopted by states at different times (2010-2015), creating staggered treatment variation",
      "control_group": "States that adopted later serve as controls for early adopters",
      "score_potential": "Level A identification + panel data + 5 pre-treatment years = 90+ potential"
    }}
  ]
}}
```
"""
    p_profile = get_profile("stage1")
    topic_response = run_claude(
        topic_prompt,
        model=p_profile["model"], effort=p_profile["effort"],
        allowed_tools=[],
        timeout=120,
        label="topic-suggestion",
    )
    suggestions = extract_json(topic_response)
    topic_list = suggestions.get("suggestions", []) if suggestions else []

    if topic_list:
        print(f"\n  {'=' * 60}")
        print(f"  SUGGESTED RESEARCH TOPICS")
        print(f"  {'=' * 60}")
        for i, s in enumerate(topic_list, 1):
            ds_idx = s.get("dataset_index", 1)
            ds_name = qualified[ds_idx - 1]["candidate"].get("name", "?")[:40] if ds_idx <= len(qualified) else "?"
            id_level = s.get("identification_level", "?")
            print(f"\n  [{i}] {s.get('topic', '?')}")
            print(f"      Dataset:  {ds_name}")
            print(f"      RQ:       {s.get('research_question', '?')}")
            print(f"      Method:   {s.get('method', '?')}  [ID Level: {id_level}]")
            print(f"      ID:       {s.get('identification', '?')[:120]}")
            control = s.get("control_group", "")
            if control:
                print(f"      Control:  {control[:120]}")
            print(f"      Score:    {s.get('score_potential', '?')[:120]}")
    else:
        print("  [warn] Could not generate topic suggestions")

    # ── Phase 6: User selects ─────────────────────────────────────────
    print(f"\n  {'=' * 60}")
    print(f"  Select a topic by number, or enter your own topic.")
    print(f"  {'=' * 60}")
    print("\a", end="", flush=True)

    selected_topic = None
    selected_dataset_idx = 0

    while True:
        choice = input("\n  >> ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(topic_list):
            sel = topic_list[int(choice) - 1]
            selected_topic = sel.get("topic", "research")
            selected_dataset_idx = sel.get("dataset_index", 1) - 1
            print(f"  [ok] Selected: {selected_topic}")
            break
        elif choice:
            selected_topic = choice
            if len(qualified) > 1:
                ds_choice = input(f"  Which dataset? [1-{len(qualified)}]: ").strip()
                selected_dataset_idx = int(ds_choice) - 1 if ds_choice.isdigit() else 0
            print(f"  [ok] Custom topic: {selected_topic}")
            break

    # ── Phase 7: Save state ───────────────────────────────────────────
    selected = qualified[min(selected_dataset_idx, len(qualified) - 1)]
    profile = selected["profile"]
    feasibility = selected["feasibility"]

    state["stages"]["stage1"] = {
        "status": "completed",
        "topic": selected_topic,
        "path": "C",
        "output_file": str(project_dir / "stage1_discovery.md"),
        "completed_at": datetime.now().isoformat(),
        "data_path": selected["local_path"],
        "data_profile": {
            "rows": profile["rows"],
            "cols": profile["cols"],
            "columns": profile["columns"],
            "structure": profile["structure"],
            "panel_flag": profile["panel_flag"],
            "panel_details": profile.get("panel_details", {}),
            "id_cols": profile.get("id_cols", []),
            "time_cols": profile.get("time_cols", []),
            "wide_panel": profile.get("wide_panel"),
        },
        "recommended_data_sources": [q["candidate"] for q in qualified],
    }

    # Also save Stage 1.5 as completed (data already profiled)
    state["stages"]["stage1_5"] = {
        "status": "completed",
        "completed_at": datetime.now().isoformat(),
        "n_downloaded": len(qualified),
        "n_not_downloaded": 0,
        "feasibility": feasibility,
        "downloaded_datasets": [
            {
                "name": q["candidate"].get("name", ""),
                "local_path": q["local_path"],
                "warnings": q["warnings"],
                "profile": {
                    "rows": q["profile"]["rows"],
                    "cols": q["profile"]["cols"],
                    "columns": q["profile"]["columns"],
                    "structure": q["profile"]["structure"],
                    "panel_flag": q["profile"]["panel_flag"],
                    "panel_details": q["profile"].get("panel_details", {}),
                    "id_cols": q["profile"].get("id_cols", []),
                    "time_cols": q["profile"].get("time_cols", []),
                    "wide_panel": q["profile"].get("wide_panel"),
                    "data_summary": q["profile"].get("data_summary", ""),
                },
            }
            for q in qualified
        ],
    }

    # Save discovery output
    output_file = project_dir / "stage1_discovery.md"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps({
            "path": "C",
            "topic": selected_topic,
            "qualified_datasets": len(qualified),
            "selected_dataset": selected["candidate"].get("name", ""),
            "feasibility": feasibility,
            "suggestions": topic_list,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    save_state(project_dir, state)

    print(f"\n  {'=' * 60}")
    print(f"  STAGE 1 PATH C — COMPLETE")
    print(f"  {'=' * 60}")
    print(f"  Topic:     {selected_topic}")
    print(f"  Dataset:   {Path(selected['local_path']).name}")
    print(f"  Rows:      {profile['rows']:,}")
    print(f"  Columns:   {profile['cols']}")
    print(f"  Structure: {profile['structure']}")
    print(f"  Ceiling:   {feasibility['score_ceiling']}/100")
    print(f"  Tier:      {feasibility['max_tier']} ({feasibility['tier_label']})")
    print(f"  {'=' * 60}")

    return state


# ═══════════════════════════════════════════════════════════════════════════════
# Path A topic-aware discovery (added 2026-04-10)
# ═══════════════════════════════════════════════════════════════════════════════
# Replaces the old "WebSearch + 17 searchers + LLM consolidator" Path A with a
# topic-suggestion architecture:
#
#   1. Expand the user's topic into 8 related variants (LLM)
#   2. For each variant, count quality candidates from 5 replication-grade
#      sources, applying a metadata proxy filter
#   3. Display variants ranked by high-confidence count, auto-select winner
#   4. Download + validate top candidates of the winning variant
#   5. Return only datasets that pass the quality gate
#
# This honors the principle "all returned datasets must meet the criteria":
# the proxy filter narrows the search; the actual download + Q1-Q8 + ceiling
# gate validates that the returned datasets are usable for a 75+ paper.

# ── INEI (Peru) microdata integration ────────────────────────────────────────

_PERU_KEYWORDS = {
    "peru", "perú", "peruana", "peruano", "peruanos", "peruanas",
    "enaho", "endes", "epen", "cenagro", "inei", "eea", "enapres",
    "lima", "arequipa", "cusco", "puno", "cajamarca", "microdata peru",
    "tambo", "tambos", "tambobook", "midis", "juntos", "pension 65",
    "ubigeo", "reniec", "sisfoh",
    # Procurement / contracting
    "seace", "osce", "oece", "contratacion", "contratación", "licitacion",
    "licitación", "contrataciones", "ocds", "contrataciones abiertas",
    # Telecom
    "osiptel", "punku", "telecom", "telecomunicaciones",
    # Geology / mining spatial data
    "ingemmet", "geocatmin", "geologia", "geología", "geologico",
    "geológico", "deposito mineral", "depósito mineral", "catastro minero",
    "yacimiento",
    # Fiscal / canon / transfers
    "canon minero", "canon y sobrecanon", "regalias mineras", "regalías",
    "mef", "consulta amigable", "transferencias", "sobrecanon",
    "ingresos fiscales mineros",
    # Competition / IP / consumer
    "indecopi", "competencia", "antitrust", "propiedad intelectual",
    "proteccion al consumidor", "protección al consumidor",
}


def _is_peru_topic(topic: str) -> bool:
    """Return True if topic likely refers to Peru or Peruvian data."""
    topic_lower = topic.lower()
    return any(kw in topic_lower for kw in _PERU_KEYWORDS)


def _search_inei(topic: str, max_results: int = 5) -> list[dict]:
    """Search INEI microdata catalog via the inei-microdatos package.

    Returns candidates for Peru surveys (ENAHO, ENDES, EPEN, etc.) matching
    the topic. Each candidate stores survey/year so Stage 1.5 can call
    download_modules() directly instead of scraping the INEI portal.
    Only runs when inei-microdatos is installed; fails silently otherwise.
    """
    try:
        from inei_microdatos import load_catalog, search_variables
        from inei_microdatos.catalog import filter_catalog
    except ImportError:
        print("  [inei] inei-microdatos not installed. Run: pip install inei-microdatos")
        return []

    print(f"  [inei] Searching INEI catalog for '{topic}'...")

    # Map topic keywords to the most relevant INEI surveys
    topic_lower = topic.lower()
    survey_priority = []
    _survey_keywords = [
        (["pobreza", "poverty", "hogar", "household", "ingreso", "income",
          "consumo", "consumption", "bienestar", "welfare",
          "digital", "fintech", "wallet", "movil", "internet", "tecnologia",
          "tambo", "tambos", "tambobook", "rural", "service platform",
          "midis", "juntos", "pension 65", "social program", "public service",
          "remote", "acceso", "access"], "enaho"),
        (["empleo", "employment", "labor", "trabajo", "desempleo",
          "unemployment", "salario", "wage", "ocupacion", "occupation"], "epen"),
        (["salud", "health", "mortalidad", "mortality", "nutricion",
          "nutrition", "fecundidad", "fertility", "demografica"], "endes"),
        (["agro", "agricultura", "agriculture", "cultivo", "crop",
          "ganaderia", "livestock", "cenagro"], "cenagro"),
        (["empresa", "firm", "manufactura", "manufacturing",
          "produccion economica", "economic production"], "eea"),
    ]
    for keywords, survey in _survey_keywords:
        if any(kw in topic_lower for kw in keywords):
            if survey not in survey_priority:
                survey_priority.append(survey)

    if not survey_priority:
        survey_priority = ["enaho"]  # ENAHO is the most comprehensive fallback

    try:
        catalog = load_catalog()
    except Exception as e:
        print(f"  [inei] Could not load catalog: {e}")
        return []

    results = []
    seen_keys: set = set()

    # catalog is a list[dict]; each entry has 'years': {year_str: {period: {modules:[...]}}}
    for survey in survey_priority[:2]:
        try:
            filtered = filter_catalog(catalog, survey=survey, year_min=2015)
            # filtered is a list of survey entry dicts; collect all available years
            all_years: set = set()
            n_modules_by_year: dict = {}
            for entry in filtered:
                for yr_str, periods in (entry.get("years") or {}).items():
                    try:
                        yr_int = int(yr_str)
                    except (ValueError, TypeError):
                        continue
                    all_years.add(yr_int)
                    # count modules across all periods for this year
                    mods = sum(
                        len(p.get("modules", [])) for p in periods.values()
                        if isinstance(p, dict)
                    )
                    n_modules_by_year[yr_int] = n_modules_by_year.get(yr_int, 0) + mods

            for year in sorted(all_years, reverse=True)[:max_results]:
                key = (survey, year)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                n_mods = n_modules_by_year.get(year, 0)
                results.append({
                    "name": f"INEI {survey.upper()} {year}",
                    "provider": "INEI (inei-microdatos)",
                    "url": "https://proyectos.inei.gob.pe/microdatos/",
                    "description": (
                        f"Encuesta {survey.upper()} año {year} — "
                        f"{n_mods} módulos disponibles"
                    ),
                    "survey": survey,
                    "year": year,
                    "n_modules": n_mods,
                    "source_api": "inei",
                    "country": "Peru",
                })
                if len(results) >= max_results:
                    break
        except Exception as e:
            print(f"  [inei] Error filtering {survey}: {e}")

    print(f"  [inei] Found {len(results)} INEI datasets")
    return results


# ── BCRP (Peru central bank) macro time-series integration ───────────────────
#
# The Banco Central de Reserva del Perú publishes macro series through a free,
# no-auth REST API. Unlike INEI (microdata cross-sections) BCRP gives a
# country-level MONTHLY panel — ideal as outcome/control series for macro,
# monetary, and trade papers. We always materialise the full six-indicator
# snapshot so the resulting CSV clears the Stage-1 column gate; topic keywords
# only steer the candidate label/description. No extra package — requests only.
#
# Verified monthly series codes (see Skills_Claude/mcp_bcrp_server.py, LAB11).
# NOTE: Fiscal/transfer series (02xxx range, e.g. PN02832AM canon minero) all
# return HTTP 403 from the public API — BCRP restricts these to authenticated
# users. For canon/transfer data, use MEF Consulta Amigable (manual) instead.
# The 5 series below cover macro outcomes/controls; they are confirmed working.
_BCRP_SERIES: dict[str, dict] = {
    "inflation":     {"code": "PN01271PM", "label": "Inflación IPC Lima (var% mensual)"},
    "exchange_rate": {"code": "PN01234PM", "label": "Tipo de cambio promedio (S/ por USD)"},
    "gdp":           {"code": "PN01773AM", "label": "PBI desestacionalizado (índice 2007=100)"},
    "interest_rate": {"code": "PN07819NM", "label": "Tasa de referencia BCRP (% anual)"},
    "trade_balance": {"code": "PN01781AM", "label": "Exportaciones acumuladas (millones USD)"},
}

_BCRP_KEYWORDS: list[tuple[list[str], str]] = [
    (["inflation", "inflación", "inflacion", "ipc", "cpi", "precios", "prices"], "inflation"),
    (["exchange", "cambio", "fx", "soles", "usd", "dollar", "dólar", "dolar"], "exchange_rate"),
    (["gdp", "pbi", "pib", "growth", "crecimiento", "producto", "output", "actividad economica"], "gdp"),
    (["interest", "interés", "interes", "tasa", "monetary", "monetaria", "policy rate"], "interest_rate"),
    (["trade", "comercio", "exportaci", "import", "balanza", "exports"], "trade_balance"),
]


def _search_bcrp(topic: str, max_results: int = 1) -> list[dict]:
    """Return a BCRP macro time-series candidate for Peru-related topics.

    Always carries the full six-indicator monthly snapshot (so the downloaded
    panel is wide enough for the Stage-1 quality gate). Topic keywords are used
    only to highlight the most relevant indicators in the candidate label.
    Stage 1.5 (`_try_download_bcrp`) fetches and merges the series into a CSV.
    """
    topic_lower = topic.lower()
    matched = [ind for kws, ind in _BCRP_KEYWORDS if any(k in topic_lower for k in kws)]
    series = {name: meta["code"] for name, meta in _BCRP_SERIES.items()}
    if matched:
        label = "BCRP Macro Panel (" + ", ".join(matched) + ", Peru)"
    else:
        label = "BCRP Macro Panel (Peru)"
    desc = (
        "Panel mensual de series macroeconómicas del BCRP: "
        + ", ".join(m["label"] for m in _BCRP_SERIES.values())
        + ". Fuente: estadisticas.bcrp.gob.pe (API pública, sin autenticación)."
    )
    print(f"  [bcrp] Macro panel candidate ({len(matched)} keyword match) for '{topic}'")
    return [{
        "name": label,
        "provider": "BCRP (Banco Central de Reserva del Perú)",
        "url": "https://estadisticas.bcrp.gob.pe/estadisticas/series/",
        "description": desc[:300],
        "series": series,
        "primary": matched,
        "start": "2004-01",
        "source_api": "bcrp",
        "country": "Peru",
    }][:max_results]


# ── Datos Abiertos Perú — curated downloadable datasets ──────────────────────
#
# datosabiertos.gob.pe is CKAN-based but most resources are NOT loaded into its
# DataStore, so plain package_search rarely returns a parseable download_url
# (see LAB11/DatosAbiertos/README.md). These curated entries point straight at
# the CSV file so health/education topics surface ready-to-download data.
# Mirrors LAB11/DatosAbiertos/catalog_curated.py.
_DATOSABIERTOS_CURATED: list[dict] = [
    {
        "name": "MINSA - IPRESS (establecimientos de salud, RENIPRESS)",
        "keywords": ["salud", "health", "ipress", "establecimiento", "hospital",
                     "minsa", "renipress", "clinica", "centro de salud", "medico"],
        "download_url": "https://www.datosabiertos.gob.pe/sites/default/files/recursos/2017/09/IPRESS.csv",
        "encoding": "latin-1",
    },
    {
        # LAB11 verified CKAN resource_id — more stable than direct file URL above
        "name": "MINSA - IPRESS RENIPRESS (CKAN datastore, LAB11 verified)",
        "keywords": ["salud", "health", "ipress", "establecimiento", "hospital",
                     "minsa", "renipress", "clinica", "centro de salud", "medico"],
        "download_url": (
            "https://www.datosabiertos.gob.pe/api/3/action/datastore_search"
            "?resource_id=7cf96151-5ddf-4281-90ba-b2b0407447ab&limit=500000"
        ),
        "encoding": "utf-8",
        "ckan_resource_id": "7cf96151-5ddf-4281-90ba-b2b0407447ab",
    },
    {
        "name": "Alumnos matriculados 2016-2022 (MINEDU)",
        "keywords": ["educacion", "educación", "matricula", "matrícula", "alumno",
                     "estudiante", "escolar", "minedu", "colegio", "enrollment", "education", "school"],
        "download_url": "https://www.datosabiertos.gob.pe/sites/default/files/Matriculados_2016_al_2022.csv",
        "encoding": "utf-8",
    },
    {
        # LAB11 verified CKAN resource_id for MINEDU matrícula
        "name": "MINEDU - Matrícula escolar (CKAN datastore, LAB11 verified)",
        "keywords": ["educacion", "educación", "matricula", "matrícula", "alumno",
                     "estudiante", "escolar", "minedu", "colegio", "enrollment", "education", "school"],
        "download_url": (
            "https://www.datosabiertos.gob.pe/api/3/action/datastore_search"
            "?resource_id=e276da3f-a009-4547-9e76-c814e14fc574&limit=500000"
        ),
        "encoding": "utf-8",
        "ckan_resource_id": "e276da3f-a009-4547-9e76-c814e14fc574",
    },
]


def _search_datosabiertos_curated(topic: str, max_results: int = 5) -> list[dict]:
    """Match curated, directly-downloadable Datos Abiertos Perú CSVs by keyword.

    Complements the generic CKAN `_search_datosabiertos_peru` searcher, which
    rarely yields a usable download_url on this portal.
    """
    topic_lower = topic.lower()
    results = []
    for ds in _DATOSABIERTOS_CURATED:
        if any(kw in topic_lower for kw in ds["keywords"]):
            results.append({
                "name": ds["name"],
                "provider": "Datos Abiertos Perú (curado)",
                "url": "https://www.datosabiertos.gob.pe/",
                "download_url": ds["download_url"],
                "download_format": "csv",
                "description": ds["name"],
                "encoding": ds.get("encoding", "utf-8"),
                "source_api": "datosabiertos_curated",
                "country": "Peru",
            })
            if len(results) >= max_results:
                break
    if results:
        print(f"  [datosabiertos] Matched {len(results)} curated dataset(s) for '{topic}'")
    return results


# ── MINEM (Peru mining production) — curated GitHub-hosted CSVs ───────────────
#
# Official Peruvian metallic-mining production 2021–2025 (MINEM), mirrored as
# clean CSVs in elqvixote/metalurgica-data. One row per district × mineral ×
# month with a production `Valor` — a usable geographic/temporal panel for
# mining, natural-resource, and regional-econ papers. Files are on GitHub raw
# (direct, no auth); `_try_download_minem` concatenates the years.
_MINEM_YEARS = [2021, 2022, 2023, 2024, 2025]
_MINEM_RAW = (
    "https://raw.githubusercontent.com/elqvixote/metalurgica-data/main/"
    "datasets/government-metal-production-data/Peru/PRODUCCION%20METALICA%20{year}.csv"
)
_MINEM_KEYWORDS = [
    "mineria", "minería", "minero", "minera", "minem", "mining", "metal",
    "metalurgia", "metallurgy", "cobre", "copper", "oro", "gold", "zinc",
    "produccion minera", "producción minera", "extractive", "extractiva",
]


def _search_minem(topic: str, max_results: int = 1) -> list[dict]:
    """Return a MINEM mining-production panel candidate for mining-related topics."""
    topic_lower = topic.lower()
    if not any(k in topic_lower for k in _MINEM_KEYWORDS):
        return []
    urls = [_MINEM_RAW.format(year=y) for y in _MINEM_YEARS]
    print(f"  [minem] Mining-production panel candidate for '{topic}'")
    return [{
        "name": f"MINEM Producción Metálica Perú {_MINEM_YEARS[0]}-{_MINEM_YEARS[-1]}",
        "provider": "MINEM (vía elqvixote/metalurgica-data)",
        "url": "https://github.com/elqvixote/metalurgica-data/tree/main/datasets/government-metal-production-data/Peru",
        "description": (
            "Producción minera metálica oficial del Perú por distrito, mineral y mes "
            f"({_MINEM_YEARS[0]}–{_MINEM_YEARS[-1]}). Fuente: MINEM. Panel geográfico-temporal."
        ),
        "download_urls": urls,
        "download_format": "csv",
        "source_api": "minem",
        "country": "Peru",
    }][:max_results]


# ── Peru replication packages ("replicar papers") ────────────────────────────
#
# Public Peru-focused analysis repos registered as replication seed candidates.
# They surface as GitHub replication packages in discovery (via
# `_candidate_to_seed_paper`, which keys on a GitHub URL + the word
# "replication") so the pipeline can replicate / extend their analysis. The
# `data_url` points at the underlying open dataset for manual retrieval.
_PERU_REPLICATION_PACKAGES = [
    {
        "name": "Atenciones de cobertura oncológica en Perú 2022 (FISSAL) — replication",
        "repo": "https://github.com/haroldeustaquio/Analysis-of-Oncological-Diseases-in-Peru",
        "data_url": "https://www.datosabiertos.gob.pe/dataset/atenciones-de-cobertura-oncol%C3%B3gica-2022-fondo-intangible-solidario-de-salud",
        "year": 2024,
        "keywords": ["cancer", "cáncer", "oncolog", "salud", "health", "fissal",
                     "enfermedad", "disease", "morbilidad", "atencion", "atención",
                     "tumor", "neoplasia"],
        "area": "health / oncology",
    },
    {
        "name": "Producción minera/metalúrgica Perú (MINEM 2021-2025) — replication / datasets",
        "repo": "https://github.com/elqvixote/metalurgica-data",
        "data_url": "https://github.com/elqvixote/metalurgica-data/tree/main/datasets/government-metal-production-data/Peru",
        "year": 2026,
        "keywords": _MINEM_KEYWORDS,
        "area": "mining / metallurgy",
    },
]


def _search_peru_replication_packages(topic: str, max_results: int = 5) -> list[dict]:
    """Surface curated Peru analysis repos as replication seed candidates.

    Returned candidates carry a GitHub repo URL and the word "replication" so
    `_candidate_to_seed_paper` converts them into replication packages the
    pipeline can replicate or extend.
    """
    topic_lower = topic.lower()
    results = []
    for pkg in _PERU_REPLICATION_PACKAGES:
        if any(kw in topic_lower for kw in pkg["keywords"]):
            results.append({
                "name": pkg["name"],
                "provider": "Peru Replication Package (GitHub)",
                "url": pkg["repo"],
                "description": (
                    f"Replication package. Open data: {pkg['data_url']} "
                    f"(area: {pkg['area']})."
                ),
                "published": str(pkg["year"]),
                "replication_package_url": pkg["repo"],
                "data_url": pkg["data_url"],
                "source_api": "peru_replication",
                "country": "Peru",
            })
            if len(results) >= max_results:
                break
    if results:
        print(f"  [peru-repl] Matched {len(results)} replication package(s) for '{topic}'")
    return results


# ── i4replication.org catalog ─────────────────────────────────────────────────
#
# SOURCE:  Institute for Replication (i4replication.org) — 293+ replicated papers
# URL:     https://www.i4replication.org/papers
# NOTES:   Static HTML page, no API. Scrape titles/authors, enrich via S2.
#          All entries are published replications → has_public_data = True.
#          Only activated when stage2_mode == "replicate".
# ─────────────────────────────────────────────────────────────────────────────

def _search_i4replication(topic: str, max_results: int = 10) -> list[dict]:
    """Scrape i4replication.org/papers for replication-verified papers matching topic.

    Fetches the static HTML catalog, extracts titles/authors,
    filters by topic relevance, then enriches via Semantic Scholar.
    Returns up to max_results candidates with source="i4replication".
    """
    import re
    try:
        import requests
    except ImportError:
        return []

    catalog_url = "https://www.i4replication.org/papers"
    print(f"  [i4replication] Fetching catalog: {catalog_url}")

    try:
        resp = requests.get(catalog_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"  [i4replication] Fetch failed: {e}")
        return []

    # ── Parse paper entries ────────────────────────────────────────────────
    # i4replication.org uses <tr> rows or <div> cards — try both patterns
    entries = []

    # Pattern 1: table rows with paper title as link text
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    for row in rows:
        # Strip tags
        text = re.sub(r"<[^>]+>", " ", row)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 20:
            entries.append(text)

    # Pattern 2: any <a> tag that looks like a paper title (>30 chars, no menu words)
    if len(entries) < 10:
        links = re.findall(r'<a[^>]*>([^<]{30,200})</a>', html)
        skip = {"home", "papers", "about", "team", "contact", "donate", "blog",
                "login", "signup", "register", "search", "filter", "sort"}
        for link_text in links:
            clean = re.sub(r"\s+", " ", link_text).strip()
            if clean.lower() not in skip and len(clean) > 30:
                entries.append(clean)

    if not entries:
        print("  [i4replication] Could not parse any entries from catalog page.")
        return []

    print(f"  [i4replication] Parsed {len(entries)} catalog entries")

    # ── Filter by topic ────────────────────────────────────────────────────
    topic_tokens = set(re.sub(r"[^a-z0-9 ]", "", topic.lower()).split())
    topic_tokens.discard("")

    scored = []
    for entry in entries:
        entry_lower = entry.lower()
        hits = sum(1 for t in topic_tokens if t in entry_lower)
        if hits > 0:
            scored.append((hits, entry))

    scored.sort(key=lambda x: -x[0])
    top_entries = [e for _, e in scored[:max_results * 3]]

    if not top_entries:
        print(f"  [i4replication] No topic matches for '{topic}' in catalog.")
        return []

    print(f"  [i4replication] {len(top_entries)} topic-relevant entries — enriching via Semantic Scholar")

    # ── Enrich via Semantic Scholar ────────────────────────────────────────
    results = []
    for entry in top_entries[:max_results * 2]:
        # Use first 100 chars as query (titles extracted from HTML can be noisy)
        query = entry[:100].strip()
        try:
            r = requests.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={
                    "query": query,
                    "limit": 1,
                    "fields": "title,authors,year,venue,citationCount,abstract,url,openAccessPdf,externalIds",
                },
                timeout=10,
            )
            r.raise_for_status()
            data = r.json().get("data", [])
            if not data:
                continue
            p = data[0]
            title = (p.get("title") or "").strip()
            if not title:
                continue
            authors = ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:3])
            if len(p.get("authors") or []) > 3:
                authors += " et al."
            results.append({
                "title": title,
                "authors": authors,
                "year": p.get("year"),
                "venue": p.get("venue", ""),
                "citationCount": p.get("citationCount", 0),
                "abstract": p.get("abstract") or "",
                "url": p.get("url") or "",
                "openAccessPdf": p.get("openAccessPdf") or {},
                "externalIds": p.get("externalIds") or {},
                "source": "i4replication",
                "has_public_data": True,
                "_data_public": True,
                "_data_source_kw": "i4replication verified",
            })
            if len(results) >= max_results:
                break
        except Exception:
            continue

    print(f"  [i4replication] {len(results)} enriched candidates")
    return results


# ── OpenICPSR replication packages ───────────────────────────────────────────
#
# SOURCE:  openicpsr.org — AEA, NBER, and journal replication packages
# API:     Dataverse-based instance; search via /openicpsr/api/search
# NOTES:   Free, no auth required. Returns dataset-level metadata including
#          DOI, description, and direct download links where available.
#          Only activated when stage2_mode == "replicate".
# ─────────────────────────────────────────────────────────────────────────────

def _search_openicpsr(topic: str, max_results: int = 8) -> list[dict]:
    """Search OpenICPSR for replication packages matching topic.

    OpenICPSR is a Dataverse instance hosting AEA and journal replication
    packages. Returns candidates with source="openicpsr" and has_public_data=True.
    """
    try:
        import requests
    except ImportError:
        return []

    print(f"  [openicpsr] Searching replication packages for '{topic[:60]}'...")
    try:
        r = requests.get(
            "https://www.openicpsr.org/openicpsr/api/search",
            params={
                "q": topic,
                "type": "dataset",
                "per_page": max_results,
                "sort": "score",
                "order": "desc",
            },
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        print(f"  [openicpsr] Search failed: {exc}")
        return []

    items = data.get("data", {}).get("items", []) or []
    if not items:
        # Some Dataverse installs wrap differently
        items = data.get("items", data.get("data", []))
        if not isinstance(items, list):
            items = []

    results = []
    for item in items[:max_results]:
        name = item.get("name", "") or item.get("title", "") or ""
        if not name:
            continue
        doi = item.get("global_id", "") or item.get("identifier", "") or ""
        url = item.get("url", "") or (f"https://doi.org/{doi}" if doi else "")
        description = item.get("description", "") or ""
        authors_raw = item.get("authors", []) or []
        if isinstance(authors_raw, list):
            authors_str = ", ".join(
                (a.get("name", a) if isinstance(a, dict) else str(a))
                for a in authors_raw[:3]
            )
            if len(authors_raw) > 3:
                authors_str += " et al."
        else:
            authors_str = str(authors_raw)

        pub_date = item.get("published_at", "") or item.get("createdAt", "") or ""
        year = pub_date[:4] if pub_date else None

        results.append({
            "title": name,
            "authors": authors_str,
            "year": year,
            "venue": "OpenICPSR",
            "citationCount": 0,
            "abstract": description[:500],
            "url": url,
            "openAccessPdf": {},
            "externalIds": {"DOI": doi} if doi else {},
            "source": "openicpsr",
            "has_public_data": True,
            "_data_public": True,
            "_data_source_kw": "openicpsr replication package",
        })

    print(f"  [openicpsr] Found {len(results)} replication package(s)")
    return results


# ── ALICIA — Peru national open access repository ────────────────────────────
#
# SOURCE:  alicia.concytec.gob.pe — Acceso Libre a Información Científica
# API:     VuFind REST API v1 at /vufind/api/v1/search
# NOTES:   Free, no auth. Indexes Peruvian university and research papers.
#          Enriched via Semantic Scholar for citation counts + abstracts.
# ─────────────────────────────────────────────────────────────────────────────

def _search_alicia(topic: str, max_results: int = 8) -> list[dict]:
    """Search ALICIA (CONCYTEC Peru) for Peruvian academic papers matching topic.

    Uses VuFind REST API. Returns candidates with source="alicia".
    Enriches found titles via Semantic Scholar for richer metadata.
    """
    try:
        import requests
    except ImportError:
        return []

    print(f"  [alicia] Searching Peruvian papers for '{topic[:60]}'...")
    raw_titles: list[tuple[str, str, str]] = []  # (title, authors, url)

    try:
        r = requests.get(
            "https://alicia.concytec.gob.pe/vufind/api/v1/search",
            params={
                "q": topic,
                "type": "AllFields",
                "limit": max_results,
                "field[]": ["title", "author", "id", "urls", "publishDate"],
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        for rec in data.get("records", []) or []:
            title = rec.get("title", "") or ""
            if not title:
                continue
            authors_list = rec.get("author", []) or []
            if isinstance(authors_list, str):
                authors_list = [authors_list]
            authors_str = ", ".join(authors_list[:3])
            if len(authors_list) > 3:
                authors_str += " et al."
            urls = rec.get("urls", []) or []
            url = urls[0].get("url", "") if urls and isinstance(urls[0], dict) else (urls[0] if urls else "")
            raw_titles.append((title, authors_str, url))
    except Exception as exc:
        print(f"  [alicia] API failed: {exc}")

    if not raw_titles:
        print(f"  [alicia] No results")
        return []

    print(f"  [alicia] {len(raw_titles)} raw hits — enriching via Semantic Scholar")

    results = []
    for title, authors_str, url in raw_titles[:max_results]:
        try:
            r2 = requests.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={
                    "query": title,
                    "limit": 1,
                    "fields": "title,authors,year,venue,citationCount,abstract,url,openAccessPdf,externalIds",
                },
                timeout=15,
            )
            r2.raise_for_status()
            hits = r2.json().get("data", []) or []
            if hits:
                p = hits[0]
                oa = p.get("openAccessPdf") or {}
                a_list = p.get("authors", []) or []
                a_str = ", ".join(a.get("name", "") for a in a_list[:3])
                if len(a_list) > 3:
                    a_str += " et al."
                results.append({
                    "title": p.get("title") or title,
                    "authors": a_str or authors_str,
                    "year": p.get("year"),
                    "venue": p.get("venue", "") or "ALICIA",
                    "citationCount": p.get("citationCount", 0) or 0,
                    "abstract": p.get("abstract") or "",
                    "url": p.get("url") or url,
                    "openAccessPdf": oa,
                    "externalIds": p.get("externalIds") or {},
                    "source": "alicia",
                    "_peru_repo": True,
                    "_data_source_kw": "alicia concytec peru",
                })
                continue
        except Exception:
            pass
        # Fallback: return raw ALICIA metadata without S2 enrichment
        results.append({
            "title": title,
            "authors": authors_str,
            "year": None,
            "venue": "ALICIA",
            "citationCount": 0,
            "abstract": "",
            "url": url,
            "openAccessPdf": {},
            "externalIds": {},
            "source": "alicia",
            "_peru_repo": True,
            "_data_source_kw": "alicia concytec peru",
        })

    print(f"  [alicia] {len(results)} enriched candidates")
    return results


# ── DSpace Peru repositories (PUCP, UP, repositorio.concytec) ────────────────
#
# SOURCE:  University and CONCYTEC DSpace repositories
# API:     DSpace 7 REST: /server/api/discover/search/objects?query=...
#          DSpace 6 REST: /rest/items?q=...  (fallback)
# NOTES:   Free, no auth. Search is full-text over metadata fields.
#          Used for seed-paper discovery in replicate mode for Peru-focused work.
# ─────────────────────────────────────────────────────────────────────────────

_PERU_DSPACE_PORTALS = [
    {
        "label": "PUCP Repositorio",
        "base": "https://repositorio.pucp.edu.pe",
        "search_path": "/search",  # web search fallback
    },
    {
        "label": "UP Repositorio",
        "base": "https://repositorio.up.edu.pe",
        "search_path": "/search",
    },
    {
        "label": "Repositorio CONCYTEC",
        "base": "https://repositorio.concytec.gob.pe",
        "search_path": "/search",
    },
]


def _search_dspace_portal(base_url: str, portal_label: str,
                           topic: str, max_results: int = 5) -> list[dict]:
    """Search a single DSpace 7 repository for papers matching topic.

    Tries DSpace 7 REST API first, falls back to DSpace 6, returns [] on failure.
    """
    try:
        import requests
    except ImportError:
        return []

    print(f"  [{portal_label}] Searching for '{topic[:50]}'...")

    # DSpace 7 REST API
    results = []
    try:
        r = requests.get(
            f"{base_url.rstrip('/')}/server/api/discover/search/objects",
            params={
                "query": topic,
                "dsoType": "ITEM",
                "size": max_results,
                "embed": "item",
            },
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        embedded = (data.get("_embedded", {}) or {}).get("searchResult", {}) or {}
        items_wrap = (embedded.get("_embedded", {}) or {}).get("objects", []) or []
        for obj in items_wrap[:max_results]:
            item = (obj.get("_embedded", {}) or {}).get("indexableObject", {}) or {}
            name = item.get("name", "") or ""
            if not name:
                continue
            handle = item.get("handle", "") or ""
            item_url = f"{base_url.rstrip('/')}/handle/{handle}" if handle else base_url
            metadata = item.get("metadata", {}) or {}

            def _meta(field: str) -> str:
                vals = metadata.get(field, []) or []
                return vals[0].get("value", "") if vals else ""

            authors_str = _meta("dc.contributor.author") or _meta("dc.creator")
            year_str = (_meta("dc.date.issued") or _meta("dc.date.created") or "")[:4]

            results.append({
                "title": name,
                "authors": authors_str,
                "year": int(year_str) if year_str.isdigit() else None,
                "venue": portal_label,
                "citationCount": 0,
                "abstract": _meta("dc.description.abstract")[:400],
                "url": item_url,
                "openAccessPdf": {},
                "externalIds": {},
                "source": "dspace_peru",
                "_peru_repo": True,
                "_portal": portal_label,
                "_data_source_kw": f"{portal_label.lower()} peru",
            })
    except Exception as exc:
        print(f"  [{portal_label}] DSpace 7 API failed: {exc}")

    if not results:
        # DSpace 6 fallback
        try:
            r6 = requests.get(
                f"{base_url.rstrip('/')}/rest/items",
                params={"q": topic, "limit": max_results, "expand": "metadata"},
                headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
            r6.raise_for_status()
            for item in (r6.json() or [])[:max_results]:
                name = item.get("name", "") or ""
                if not name:
                    continue
                handle = item.get("handle", "") or ""
                item_url = f"{base_url.rstrip('/')}/handle/{handle}" if handle else base_url
                meta_list = item.get("metadata", []) or []

                def _meta6(key: str) -> str:
                    for m in meta_list:
                        if m.get("key") == key:
                            return m.get("value", "")
                    return ""

                authors_str = _meta6("dc.contributor.author") or _meta6("dc.creator")
                year_str = (_meta6("dc.date.issued") or "")[:4]
                results.append({
                    "title": name,
                    "authors": authors_str,
                    "year": int(year_str) if year_str.isdigit() else None,
                    "venue": portal_label,
                    "citationCount": 0,
                    "abstract": _meta6("dc.description.abstract")[:400],
                    "url": item_url,
                    "openAccessPdf": {},
                    "externalIds": {},
                    "source": "dspace_peru",
                    "_peru_repo": True,
                    "_portal": portal_label,
                    "_data_source_kw": f"{portal_label.lower()} peru",
                })
        except Exception as exc2:
            print(f"  [{portal_label}] DSpace 6 fallback failed: {exc2}")

    print(f"  [{portal_label}] {len(results)} result(s)")
    return results


def _search_peru_dspace_repos(topic: str, max_results_each: int = 4) -> list[dict]:
    """Search all configured Peru DSpace portals (PUCP, UP, CONCYTEC)."""
    all_results: list[dict] = []
    for portal in _PERU_DSPACE_PORTALS:
        try:
            all_results.extend(
                _search_dspace_portal(
                    portal["base"], portal["label"], topic, max_results_each
                )
            )
        except Exception:
            continue
    return all_results


# ═══════════════════════════════════════════════════════════════════════════════
# Peru government data portals — integrated searchers [EXPERIMENTAL]
# ═══════════════════════════════════════════════════════════════════════════════
#
# STATUS: EXPERIMENTAL — integración inicial, sujeta a validación.
#   - APIs verificadas funcionales (HTTP 200, datos reales) al 2026-05-30.
#   - URLs de descarga directa verificadas (HTTP HEAD).
#   - Cobertura de años estimada con datos reales del /api/v1/indexCountData.
#   - NO probado end-to-end en Path C. Puede requerir ajustes de encoding,
#     tamaño de archivo, o estructura de datos no anticipada.
#   - INDECOPI sin API: solo referencias curadas, requiere scraping manual.
#   TODO: validar que los archivos descargados son parseables por pandas.
#   TODO: verificar encoding real de cada fuente (UTF-8 asumido).
#   TODO: probar con --paperdl off --notebooklm off para aislar.
#
# All follow the same anti-hallucination pattern:
#   Python function → real HTTP/API call → structured dict → Claude sees output
#
# 1. OSCE OCDS API  —  contratacionesabiertas.oece.gob.pe/api/v1/
# 2. PUNKU OSIPTEL  —  punku.osiptel.gob.pe (ZIP directo, ~182 MB)
# 3. INDECOPI       —  iasearch.io + buscadorResoluciones (sin API pública)
#
# ═══════════════════════════════════════════════════════════════════════════════

# ── 1. OSCE Contrataciones Abiertas (OCDS API) ───────────────────────────────
#
# SOURCE:     Organismo Especializado para las Contrataciones Públicas Eficientes
#             (OECE), formerly OSCE. Data extracted from SEACE v1, v2, and v3.
# API:        REST, no auth required. Base: contratacionesabiertas.oece.gob.pe
# STANDARD:   Open Contracting Data Standard (OCDS) — JSON structured releases.
# COVERAGE:   2003–present (verified via /api/v1/indexCountData).
#             Bulk starts 2004: 95K contracts/year, peaks at 313K (2008).
#             Steady state 2010+: ~130-170K contracts/year.
# VOLUME:     2,731,604 OCDS records, 493,807 suppliers, 3,314 buyers.
# UPDATE:     Daily (records appear within 24h of SEACE publication).
#             Monthly bulk exports at /api/v1/files (CSV + JSON).
# DATA TYPES: Panel (entity × supplier × time), cross-section (per contract).
#             Each OCDS record = one procurement process with full timeline:
#             tender → award → contract → implementation milestones.
# FIELDS:     ocid, tender (title, description, procurementMethod, value{amount,
#             currency}, procuringEntity{name,id}, mainProcurementCategory),
#             buyer{name,id}, awards, contracts, releases[{date,url}],
#             dataSegmentation{id (YYYY-MM)}, sources[{name,id,url}].
# METHODS:    procurementMethod values: "direct", "limited", "open",
#             "selective", "competitive" — maps to: contratación directa,
#             licitación pública, concurso público, adjudicación simplificada,
#             subasta inversa electrónica.
# VALUE:      For econ research — natural experiments in procurement reform,
#             DiD with staggered policy adoption across entities, collusion/
#             corruption detection, supplier dynamics, price dispersion analysis,
#             political connections (entity × supplier network panels).
#
# Endpoints (all GET, no auth):
#   /api/v1/search?format=json&paginateBy=N&page=N     paginated search
#   /api/v1/records?format=json&source=X&year=Y&month=M filtered records
#   /api/v1/files?format=json                           monthly bulk exports
#   /api/v1/indexCountData?format=json                  aggregate stats
#   /api/v1/buyers?format=json&source=X                 procuring entities
#   /api/v1/suppliers?format=json&source=X              suppliers
#   /api/v1/release/{ocid}                              full OCDS JSON release

_OCDS_API_BASE = "https://contratacionesabiertas.oece.gob.pe/api/v1"

_OCDS_KEYWORDS = [
    "contratacion", "contratación", "contrato", "contract", "procurement",
    "adquisicion", "adquisición", "licitacion", "licitación", "seace",
    "osce", "oece", "proveedor", "proveedores", "adjudicacion", "adjudicación",
    "compra publica", "compra pública", "public procurement",
    "gobierno", "government", "estado", "municipalidad", "ministerio",
    "gasto publico", "gasto público", "public spending",
    "corrupcion", "corrupción", "corruption",
    "transparencia", "transparency", "fiscalizacion", "fiscalización",
    "concurso", "subasta", "obras publicas", "obras públicas",
    "ejecucion contractual", "ejecución contractual", "infraestructura",
    "ocds", "open contracting", "contratacion abierta", "contratación abierta",
]


def _search_ocds(topic: str, max_results: int = 5) -> list[dict]:
    """Search OSCE OCDS API for procurement contracts matching topic keywords.

    Hits the real /api/v1/search endpoint. Returns structured candidates with
    entity, amount, method, and OCDS metadata. Claude never touches the API.
    """
    topic_lower = topic.lower()
    if not any(k in topic_lower for k in _OCDS_KEYWORDS):
        return []

    try:
        import requests
    except ImportError:
        return []

    print(f"  [ocds] Searching contratacionesabiertas.oece.gob.pe for '{topic}'...")
    try:
        r = requests.get(
            f"{_OCDS_API_BASE}/search",
            params={"format": "json", "paginateBy": max_results, "page": 1},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        records = data.get("results", []) or []

        results = []
        for rec in records:
            release = rec.get("compiledRelease", {})
            tender = release.get("tender", {})
            buyer = release.get("buyer", {})
            entity = tender.get("procuringEntity", {})
            seg = rec.get("dataSegmentation", {})

            title = tender.get("title", "Sin título")[:120]
            desc = tender.get("description", "")[:300]
            amount = tender.get("value", {}).get("amount", 0)
            currency = tender.get("value", {}).get("currency", "PEN")
            method = tender.get("procurementMethod", "?")
            period = seg.get("id", "?") if isinstance(seg, dict) else str(seg or "?")

            results.append({
                "name": f"OSCE OCDS: {title}",
                "provider": f"OSCE OCDS ({entity.get('name', buyer.get('name', 'Perú'))})",
                "url": f"{_OCDS_API_BASE}/release/{rec.get('ocid', '')}",
                "download_url": f"{_OCDS_API_BASE}/release/{rec.get('ocid', '')}?format=json",
                "download_format": "json",
                "description": (
                    f"[{method}] {period} | {desc}. "
                    f"Monto: {currency} {amount:,.2f}. "
                    f"Entidad: {entity.get('name', '?')}. "
                    f"OCID: {rec.get('ocid', '?')}"
                ),
                "source_api": "ocds",
                "country": "Peru",
                "data_years": "2003–present",
                "data_types": ["panel", "cross-section"],
                "n_records_total": 2731604,
                "pipeline_status": "experimental",
            })

        print(f"  [ocds] Found {len(results)} contracts for '{topic}'")
        return results[:max_results]
    except Exception as exc:
        print(f"  [ocds] API error: {exc}")
        return []


def _try_download_ocds(ocid_or_url: str, data_dir: Path) -> str | None:
    """Download a full OCDS release as JSON. Returns path or None."""
    try:
        import requests
        url = ocid_or_url if ocid_or_url.startswith("http") else \
              f"{_OCDS_API_BASE}/release/{ocid_or_url}"
        r = requests.get(url, params={"format": "json"}, timeout=30)
        r.raise_for_status()
        data = r.json()
        ocid = data.get("ocid", "release") if isinstance(data, dict) else "release"
        safe_name = ocid.replace("/", "_").replace(":", "-")[:100]
        out_path = data_dir / f"ocds_{safe_name}.json"
        import json
        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        size_kb = out_path.stat().st_size / 1024
        print(f"  [ocds] Downloaded: {out_path.name} ({size_kb:.0f} KB)")
        return str(out_path)
    except Exception as exc:
        print(f"  [ocds] Download failed: {exc}")
        return None


# ── 2. PUNKU OSIPTEL (telecom regulator open data) ──────────────────────────
#
# SOURCE:     OSIPTEL — Organismo Supervisor de Inversión Privada en
#             Telecomunicaciones. Peru's telecom regulator since 1994.
# PORTAL:     PUNKU = Plataforma de Datos Abiertos de OSIPTEL
#             https://punku.osiptel.gob.pe/
# ACCESS:     Direct ZIP download, no auth. Single archive with all datasets.
#             URL: https://punku.osiptel.gob.pe/Archivos/Datasets-PUNKU-OSIPTEL.zip
# SIZE:       ~182 MB compressed (verified 2026-05-21 via HTTP HEAD).
# UPDATE:     Monthly (verified Last-Modified header: 2026-05-21).
# COVERAGE:   Estimated 2014–present based on OSIPTEL's digital data program.
#             Exact range determined by ZIP contents at download time.
# CONTENTS:   Multiple CSV datasets inside the ZIP. Based on PUNKU portal:
#             - Calidad de servicio móvil (mobile QoS by district/operator)
#             - Internet móvil (mobile internet speed tests, latency, coverage)
#             - Cobertura móvil 2G/3G/4G/5G (coverage maps by technology)
#             - Reclamos de usuarios (complaints: operator, region, type, outcome)
#             - Tarifas y planes (tariff plans by operator/service)
#             - Despliegue de infraestructura (towers, fiber, spectrum assignments)
#             - Indicadores de conectividad (household/business internet penetration)
# DATA TYPES: Panel (district × operator × month), cross-section (coverage snapshots).
# VALUE:      Natural experiments in telecom regulation, DiD with staggered 4G/5G
#             deployment, digital divide analysis, competition in mobile markets,
#             regulatory impact evaluation, consumer complaint dynamics.
# NOTE:       ZIP filename is stable but contents may change. Unzip at download
#             time and profile with pandas before use in pipeline.

_PUNKU_KEYWORDS = [
    "telecom", "telecomunicacion", "telecomunicación", "telecomunicaciones",
    "osiptel", "punku", "internet", "banda ancha", "broadband",
    "celular", "movil", "móvil", "telefonia", "telefonía", "phone",
    "cobertura", "coverage", "velocidad", "speed", "speedtest",
    "fibra optica", "fibra óptica", "fiber", "4g", "5g", "lte",
    "operador", "operator", "movistar", "claro", "entel", "bitel",
    "reclamo", "reclamos", "queja", "quejas", "complaint", "complaints",
    "tarifa", "tarifas", "plan", "planes", "tariff",
    "conectividad", "connectivity", "brecha digital", "digital divide",
    "regulacion", "regulación", "regulation", "regulator",
]


def _search_punku(topic: str, max_results: int = 1) -> list[dict]:
    """Surface PUNKU OSIPTEL telecom dataset for telecom/digital economy topics.

    Returns curated candidate with verified direct ZIP download URL.
    Anti-hallucination: deterministic keyword matching, HTTP-verified ZIP URL.
    """
    topic_lower = topic.lower()
    if not any(k in topic_lower for k in _PUNKU_KEYWORDS):
        return []

    print(f"  [punku] OSIPTEL telecom dataset candidate for '{topic}'")
    return [{
        "name": "PUNKU OSIPTEL — Datos Abiertos de Telecomunicaciones Perú",
        "provider": "OSIPTEL / PUNKU",
        "url": "https://punku.osiptel.gob.pe/",
        "download_url": (
            "https://punku.osiptel.gob.pe/Archivos/Datasets-PUNKU-OSIPTEL.zip"
        ),
        "download_format": "zip",
        "description": (
            "Datasets completos del regulador de telecomunicaciones peruano OSIPTEL. "
            "Incluye: calidad de servicio móvil por distrito y operador, mediciones "
            "de velocidad de internet (Speedtest), cobertura móvil 2G/3G/4G/5G, "
            "reclamos de usuarios por operador/región/tipo, tarifas y planes, "
            "despliegue de infraestructura (torres, fibra, espectro), e indicadores "
            "de conectividad (penetración de internet en hogares/empresas). "
            "ZIP ~182 MB con múltiples CSVs. Panel geográfico: distrito × indicador "
            "× período. Cobertura estimada: 2014–present. Actualización mensual."
        ),
        "source_api": "punku",
        "country": "Peru",
        "data_years": "2014–present (estimated, verified by ZIP contents at download)",
        "data_types": ["panel", "cross-section", "time-series"],
        "pipeline_status": "experimental",
    }][:max_results]


# ── 3. INDECOPI (competition, consumer protection, intellectual property) ───
#
# SOURCE:     INDECOPI — Instituto Nacional de Defensa de la Competencia y de
#             la Protección de la Propiedad Intelectual. Created 1992 (D.L. 25868).
#             Peru's multi-sector regulator: antitrust, consumer protection,
#             IP (patents, trademarks, copyright), dumping/subsidies, bureaucratic
#             barriers, bankruptcy (disolved 2025 → new entity).
# PORTALS:    a) Buscador Avanzado de Resoluciones (AI semantic search)
#                https://indecopi.iasearch.io/
#                Semantic + structured search over resolutions, sanctions, precedents.
#                Underlying tech: iasearch.io platform. No public API.
#             b) Buscador de Resoluciones (JBoss Seam, legacy)
#                https://servicio.indecopi.gob.pe/buscadorResoluciones/
#                6 category sub-portals: Tribunal, Propiedad Intelectual,
#                Protección al Consumidor, Defensa de la Competencia,
#                Sentencias del Poder Judicial, LAUDOS (arbitration).
#                Each at {category}.seam — server-rendered HTML, no API.
# COVERAGE:   Estimated 1993–present. Digital records sparse pre-2000;
#             consistent coverage from ~2005 (case management system adoption).
#             Each category may have different start dates.
# DATA TYPES: Cross-section (per resolution). Fields: case number, date,
#             parties (plaintiff, defendant), sector/industry, legal basis,
#             resolution type (sanction, precedent, ruling, dismissal),
#             outcome (fine amount, corrective measure, absolved), chamber/sala.
# VALUE:      Antitrust enforcement dynamics, consumer protection effectiveness,
#             IP litigation as innovation proxy, regulatory capture tests,
#             bureaucratic barriers as trade costs, arbitration outcomes.
# STRATEGY:   Curated reference entries. NO automated download — pipeline skips
#             these in Path C (requires_manual_fetch: True). Data retrieval
#             needs Firecrawl scraping or manual browser export. These entries
#             exist so Claude KNOWS the data exists and can tell the researcher
#             "INDECOPI has this — go download it manually from [URL]."

_INDECOPI_KEYWORDS = [
    "indecopi", "competencia", "competition", "antitrust", "antimonopolio",
    "propiedad intelectual", "intellectual property", "patente", "patent",
    "marca", "trademark", "derechos de autor", "copyright",
    "proteccion al consumidor", "protección al consumidor",
    "consumer protection", "consumidor", "consumer",
    "sancion", "sanción", "sanction", "multa", "fine",
    "precedente", "precedent", "resolucion", "resolución", "resolution",
    "tribunal", "court", "arbitration", "arbitraje", "laudo",
    "defensa de la competencia", "competition defense",
    "barreras burocraticas", "barreras burocráticas", "bureaucratic barriers",
    "dumping", "subsidios", "subsidy", "competencia desleal", "unfair competition",
]


def _search_indecopi(topic: str, max_results: int = 2) -> list[dict]:
    """Surface INDECOPI as a data source for competition/consumer/IP topics.

    No public API — curated reference entries. Pipeline skips automated
    download; user must scrape manually or use Firecrawl.
    """
    topic_lower = topic.lower()
    if not any(k in topic_lower for k in _INDECOPI_KEYWORDS):
        return []

    results = []

    # ── Competition / antitrust ──────────────────────────────────────────
    if any(k in topic_lower for k in ["competencia", "competition", "antitrust",
                                        "antimonopolio", "defensa de la competencia",
                                        "barreras burocraticas", "barreras burocráticas"]):
        results.append({
            "name": "INDECOPI — Resoluciones de Defensa de la Competencia",
            "provider": "INDECOPI (buscadorResoluciones)",
            "url": "https://servicio.indecopi.gob.pe/buscadorResoluciones/competencia.seam",
            "download_url": "",
            "download_format": "html",
            "description": (
                "Resoluciones de la Sala de Defensa de la Competencia del INDECOPI "
                "(1993–present). Incluye: abuso de posición de dominio, carteles y "
                "prácticas colusorias, barreras burocráticas, competencia desleal, "
                "dumping y subsidios. ~300-500 resoluciones/año. Campos: expediente, "
                "fecha, denunciante, denunciado, sector, conducta, resolución, multa. "
                "Sin API pública — requiere scraping con Firecrawl o descarga manual "
                "desde el buscador JBoss Seam."
            ),
            "source_api": "indecopi",
            "country": "Peru",
            "data_years": "1993–present",
            "data_types": ["cross-section"],
            "pipeline_status": "experimental",
            "requires_manual_fetch": True,
        })

    # ── Consumer protection ──────────────────────────────────────────────
    if any(k in topic_lower for k in ["consumidor", "consumer", "proteccion",
                                        "protección"]):
        results.append({
            "name": "INDECOPI — Resoluciones de Protección al Consumidor",
            "provider": "INDECOPI (buscadorResoluciones)",
            "url": "https://servicio.indecopi.gob.pe/buscadorResoluciones/proteccion-consumidor.seam",
            "download_url": "",
            "download_format": "html",
            "description": (
                "Resoluciones de la Sala de Protección al Consumidor del INDECOPI "
                "(1993–present). Incluye: idoneidad de productos/servicios, información "
                "adecuada, métodos abusivos de cobranza, discriminación en el consumo, "
                "incumplimiento de garantías. ~2000+ resoluciones/año. Mayor volumen "
                "de casos del INDECOPI. Campos: expediente, fecha, consumidor, "
                "proveedor, sector, infracción, medida correctiva, multa. "
                "Sin API pública — requiere scraping o descarga manual."
            ),
            "source_api": "indecopi",
            "country": "Peru",
            "data_years": "1993–present",
            "data_types": ["cross-section"],
            "requires_manual_fetch": True,
        })

    # ── Intellectual property ────────────────────────────────────────────
    if any(k in topic_lower for k in ["propiedad intelectual", "intellectual property",
                                        "patente", "patent", "marca", "trademark",
                                        "derechos de autor", "copyright"]):
        results.append({
            "name": "INDECOPI — Resoluciones de Propiedad Intelectual",
            "provider": "INDECOPI (buscadorResoluciones)",
            "url": "https://servicio.indecopi.gob.pe/buscadorResoluciones/propiedad-intelectual.seam",
            "download_url": "",
            "download_format": "html",
            "description": (
                "Resoluciones de la Sala de Propiedad Intelectual del INDECOPI "
                "(1993–present). Incluye: registro y oposición de marcas, patentes "
                "farmacéuticas y biotecnológicas, derechos de autor, infracciones de "
                "PI, nombres comerciales y denominaciones de origen. Relevante para "
                "economía de la innovación: patentes como proxy de I+D, litigios de "
                "marcas como barreras de entrada. ~500-800 resoluciones/año. "
                "Sin API pública — requiere scraping o descarga manual."
            ),
            "source_api": "indecopi",
            "country": "Peru",
            "data_years": "1993–present",
            "data_types": ["cross-section"],
            "requires_manual_fetch": True,
        })

    if results:
        print(f"  [indecopi] Matched {len(results)} INDECOPI reference(s) for '{topic}'")
    return results[:max_results]


# ── INGEMMET GEOCATMIN (Peru geology/mining spatial data) integration ─────────
#
# GEOCATMIN exposes OGC WMS/WFS services with 245+ layers including mineral
# deposits, mining cadastre, geological maps, and geochemistry. WFS endpoints
# return vector data (points/polygons) consumable by geopandas for spatial
# instruments (e.g. distance-to-deposit IVs). No auth required.
#
# Layers used (verified live 2026-05-30):
#   SERV_GEOLOGIA_M/MapServer/WFSServer — geology 1:1M (mineral deposits)
#   SERV_CATASTRO_MINERO/MapServer/WFSServer — mining cadastre (concessions)
#
# Download uses owslib if installed, else raw requests + manual GeoJSON parse.
_INGEMMET_WFS_BASE = (
    "http://geocatmin.ingemmet.gob.pe/arcgis/services"
)
_INGEMMET_LAYERS: list[dict] = [
    {
        "name": "GEOCATMIN — Depósitos Minerales (Geología 1:1M)",
        "service": "SERV_GEOLOGIA_M/MapServer/WFSServer",
        "type": "wfs",
        "description": (
            "Yacimientos y depósitos minerales del Perú a escala 1:1,000,000. "
            "Incluye: tipo de depósito, commodity principal, estatus, geometría "
            "(puntos/polígonos). Fuente: INGEMMET GEOCATMIN. "
            "Útil como instrumento espacial: distancia/proximidad a depósitos, "
            "densidad de yacimientos por distrito, índice de potencial minero."
        ),
    },
    {
        "name": "GEOCATMIN — Catastro Minero (Concesiones)",
        "service": "PSAD56_18/SERV_CATASTRO_MINERO_18/MapServer/WFSServer",
        "type": "wfs",
        "description": (
            "Derechos mineros y concesiones vigentes en Perú. Incluye: titular, "
            "área, fecha de otorgamiento, tipo de derecho, estado. "
            "Fuente: INGEMMET GEOCATMIN."
        ),
    },
]
_INGEMMET_KEYWORDS = [
    "mineria", "minería", "minero", "minera", "mineral", "mining",
    "geologia", "geología", "geologico", "geológico", "yacimiento",
    "deposito", "depósito", "metal", "cobre", "oro", "zinc", "plata",
    "concesion", "concesión", "catastro minero", "ingemmet", "geocatmin",
    "extractivo", "extractive", "recursos naturales", "natural resources",
]


def _search_ingemmet(topic: str, max_results: int = 2) -> list[dict]:
    """Return INGEMMET GEOCATMIN spatial data candidates for mining/geology topics.

    WFS endpoints serve vector layers consumable by geopandas/QGIS.
    No API key — open OGC services. Requires `owslib` for download;
    discovery works with requests alone.
    """
    topic_lower = topic.lower()
    if not any(k in topic_lower for k in _INGEMMET_KEYWORDS):
        return []

    results = []
    for layer in _INGEMMET_LAYERS:
        wfs_url = f"{_INGEMMET_WFS_BASE}/{layer['service']}"
        results.append({
            "name": layer["name"],
            "provider": "INGEMMET GEOCATMIN (WFS)",
            "url": "https://geocatmin.ingemmet.gob.pe/",
            "download_url": wfs_url,
            "download_format": "geojson",
            "description": layer["description"][:300],
            "source_api": "ingemmet",
            "country": "Peru",
            "data_types": ["spatial"],
            "wfs_layer": layer["service"],
            "requires_manual_acquisition": False,  # WFS is auto-downloadable
            "extraction_tool": "owslib.wfs.WebFeatureService",
        })
        if len(results) >= max_results:
            break

    if results:
        print(f"  [ingemmet] Spatial data candidates for '{topic}': {len(results)} layer(s)")
    return results


# ── MEF Consulta Amigable — manual reference catalog ─────────────────────────
#
# The MEF "Consulta Amigable" web portal (Consulta de Transferencias a los
# Gobiernos Locales, Regionales y Nacionales) is the authoritative source for
# mining canon, royalties, and fiscal transfers in Peru. It has NO public API
# — data must be exported manually through the web UI.
#
# These curated references surface the portal URL and export instructions so
# the pipeline can tell researchers exactly what to do. The entries carry
# `requires_manual_acquisition: true` so Stage 1.5 / Stage 3.5 know to show
# instructions rather than attempt automated download.
_MEF_CONSULTA_AMIGABLE_REFERENCES: list[dict] = [
    {
        "name": "MEF Consulta Amigable — Canon Minero (Transferencias a Gobiernos Locales)",
        "url": "https://apps5.mineco.gob.pe/transparencia/Navegador/default.aspx",
        "description": (
            "Transferencias de canon minero a municipalidades distritales y provinciales "
            "del Perú. Datos anuales por distrito. Incluye: canon minero, canon "
            "hidroenergético, canon pesquero, canon gasífero, canon forestal, "
            "regalías mineras, FONCOMUN, FOCAM. "
            "Exportar: seleccionar año → Gobiernos Locales → Canon Minero → "
            "todos los departamentos → Exportar a Excel/CSV."
        ),
        "requires_manual_acquisition": True,
        "export_instructions": (
            "1. Ir a https://apps5.mineco.gob.pe/transparencia/Navegador/default.aspx\n"
            "2. Seleccionar 'Gobiernos Locales' como nivel de gobierno\n"
            "3. En 'Tipo de Transferencia', marcar 'Canon Minero'\n"
            "4. Seleccionar el año deseado (repetir para cada año del panel)\n"
            "5. En 'Departamento', seleccionar 'Todos'\n"
            "6. Hacer clic en 'Consultar' y luego 'Exportar' → CSV/Excel\n"
            "7. Guardar en data/external/mef/canon_minero_YYYY.csv"
        ),
    },
    {
        "name": "MEF Consulta Amigable — Canon y Sobrecanon (todos los tipos)",
        "url": "https://apps5.mineco.gob.pe/transparencia/Navegador/default.aspx",
        "description": (
            "Transferencias totales por canon y sobrecanon a gobiernos subnacionales. "
            "Incluye canon minero, gasífero, hidroenergético, pesquero, forestal, "
            "y sobrecanon petrolero. Datos anuales por distrito/provincia/región. "
            "Exportar como CSV desde el portal web."
        ),
        "requires_manual_acquisition": True,
        "export_instructions": (
            "1. Ir a https://apps5.mineco.gob.pe/transparencia/Navegador/default.aspx\n"
            "2. Seleccionar nivel de gobierno (Local/Regional)\n"
            "3. Marcar todos los tipos de canon y sobrecanon requeridos\n"
            "4. Seleccionar año → Todos los departamentos → Consultar → Exportar CSV"
        ),
    },
]
_MEF_KEYWORDS = [
    "canon", "transferencia", "mef", "consulta amigable", "regalias",
    "regalías", "sobrecanon", "sobrecanón", "foncomun", "focam",
    "ingresos fiscales", "fiscal transfers", "mining revenue",
    "gobierno local", "municipalidad", "gobierno regional",
]


def _search_mef_consulta_amigable(topic: str, max_results: int = 2) -> list[dict]:
    """Return MEF Consulta Amigable references for canon/transfer topics.

    No API exists — these are manual-download references with export instructions.
    Pipeline shows the link and instructions; user must download CSV manually.
    """
    topic_lower = topic.lower()
    if not any(k in topic_lower for k in _MEF_KEYWORDS):
        return []

    results = []
    for ref in _MEF_CONSULTA_AMIGABLE_REFERENCES:
        if any(k in topic_lower for k in _MEF_KEYWORDS):
            results.append({
                "name": ref["name"],
                "provider": "MEF Consulta Amigable (manual)",
                "url": ref["url"],
                "download_url": "",  # no API
                "download_format": "csv",
                "description": ref["description"][:300],
                "source_api": "mef_consulta_amigable",
                "country": "Peru",
                "data_types": ["panel"],
                "requires_manual_acquisition": True,
                "export_instructions": ref.get("export_instructions", ""),
            })
            if len(results) >= max_results:
                break

    if results:
        print(f"  [mef] Canon/transfer references for '{topic}': {len(results)} "
              f"source(s) — manual download (no API)")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# (End of Peru government data block)
# ═══════════════════════════════════════════════════════════════════════════════


def _infer_country(candidate: dict) -> str:
    """Infer country from dataset name/description when not explicitly set."""
    if candidate.get("country"):
        return candidate["country"]
    text = ((candidate.get("name") or "") + " " + (candidate.get("description") or "")).lower()
    _MAP = [
        (["peru", "perú", "enaho", "inei", "tambo", "midis", "juntos", "pension 65"], "Peru"),
        (["mexico", "méxico", "mexican", "progresa", "oportunidades"], "Mexico"),
        (["brazil", "brasil", "brazilian"], "Brazil"),
        (["spain", "spanish", "españa"], "Spain"),
        (["india", "indian"], "India"),
        (["china", "chinese"], "China"),
        (["kenya", "kenyan"], "Kenya"),
        (["indonesia", "indonesian"], "Indonesia"),
        (["ethiopia", "ethiopian"], "Ethiopia"),
        (["colombia", "colombian"], "Colombia"),
        (["cameroon", "cameroonian"], "Cameroon"),
        (["sri lanka"], "Sri Lanka"),
        (["rwanda", "rwandan"], "Rwanda"),
        (["hiroshima", "japan", "japanese"], "Japan"),
        (["oregon", "u.s.", " usa", "united states", "american"], "USA"),
        (["uk ", "united kingdom", "britain", "british"], "UK"),
    ]
    for keywords, country in _MAP:
        if any(kw in text for kw in keywords):
            return country
    return ""


def _likely_quality(candidate: dict) -> bool:
    """Heuristic metadata-only proxy for whether a candidate is likely to
    pass the full Q1-Q8 + ceiling >= 75 gate.

    Cannot replace the real validation (which requires downloading the file),
    but is highly correlated with it. Used during the variant-counting phase
    to give the user a meaningful 'high-confidence' count without paying the
    download cost for every variant.
    """
    src = candidate.get("source_api", "")
    name = (candidate.get("name") or "").lower()

    # Strong positive signals: pre-validated provenance
    # bcrp + datosabiertos_curated are official Peruvian sources with known,
    # directly-downloadable structure (same tier as INEI government microdata).
    # ingemmet is INGEMMET GEOCATMIN WFS — official Peruvian geological survey.
    if src in ("curated_registry", "journal", "inei", "bcrp",
               "datosabiertos_curated", "minem", "ingemmet"):
        return True

    # Dataverse: title must signal an academic replication archive
    if src == "dataverse":
        return any(k in name for k in [
            "replication", "data for", "replication data", "supplementary"
        ])

    # Zenodo: must have actual data files attached (not metadata-only)
    if src == "zenodo":
        if candidate.get("has_data_files"):
            return True
        files = candidate.get("files") or []
        return any(
            f.lower().endswith((".csv", ".dta", ".tab", ".parquet", ".xlsx", ".zip"))
            for f in files
        )

    # GitHub: stars + replication wording is a strong proxy for academic value
    if src == "github":
        if candidate.get("stars", 0) >= 10 and "replication" in name:
            return True
        return candidate.get("stars", 0) >= 50

    return False


def _expand_topic_variants(topic: str, n: int = 8) -> list[str]:
    """Generate N related topic queries via Claude.

    Returns the original topic plus N-1 LLM-generated variants. If the LLM
    call fails, falls back to a hardcoded suffix expansion so Path A still
    works without network/LLM access.
    """
    print(f"  [expand] Generating {n} topic variants for '{topic}'...")
    fallback = [
        topic,
        f"{topic} policy reform",
        f"{topic} natural experiment",
        f"{topic} randomized controlled trial",
        f"{topic} difference in differences",
        f"{topic} regression discontinuity",
        f"{topic} instrumental variable",
        f"{topic} impact evaluation",
    ][:n]

    try:
        p = get_profile("stage1")
        prompt = (
            f'You are an empirical economist looking for replication archives '
            f'related to "{topic}".\n\n'
            f'Generate {n - 1} concrete search queries an economist would use '
            f'to find datasets supporting causal identification on this topic. '
            f'Mix:\n'
            f'  - Specific policy/intervention angles (e.g., "minimum wage reform")\n'
            f'  - Methodological angles (e.g., "RCT", "natural experiment")\n'
            f'  - Related sub-fields (e.g., "labor market frictions")\n\n'
            f'Return ONLY a JSON array of {n - 1} short query strings (3-6 words each), '
            f'no commentary.\n'
            f'Example: ["minimum wage RCT", "unemployment insurance reform DiD", ...]'
        )
        response = run_claude(
            prompt,
            model=p["model"], effort="low",
            allowed_tools=[],
            timeout=30,
            max_retries=1,
            label="topic-expand",
        )
        parsed = extract_json(response)
        if isinstance(parsed, list) and parsed:
            variants = [topic] + [str(v) for v in parsed if isinstance(v, str)][: n - 1]
            print(f"  [expand] Generated {len(variants)} variants")
            return variants
    except Exception as e:
        print(f"  [expand] LLM failed ({e}), using heuristic fallback")
    return fallback


def _count_quality_candidates_for_variant(variant: str) -> dict:
    """Count metadata hits across replication-grade sources for one variant.

    Sources: Dataverse, Zenodo, GitHub, curated registry, journal collections.
    Skips portal sources (data.gov, IDB, etc.) because they don't reliably
    produce data that passes Q1-Q8.

    Returns dict with:
        variant     — the query string
        n_total     — total metadata hits (raw count)
        n_high_conf — hits passing the _likely_quality proxy filter
        candidates  — full candidate list (for downstream download)
    """
    candidates = []

    # Dataverse + Zenodo + GitHub (live searches)
    candidates.extend(_search_dataverse(variant, max_results=8))
    candidates.extend(_search_zenodo(variant, max_results=8))
    candidates.extend(_search_github(variant, max_results=4))

    # Curated registry: keyword overlap
    try:
        from ..dataset_registry import CURATED_DATASETS, search_multiple_journals
    except Exception:
        CURATED_DATASETS, search_multiple_journals = [], None

    terms = [t.lower() for t in variant.split() if len(t) > 2]
    for ds in CURATED_DATASETS:
        title = (ds.get("title") or "").lower()
        if terms and any(t in title for t in terms):
            # Some curated entries store DOIs with the "doi:" prefix; strip it
            # so the resulting URL is well-formed.
            raw_doi = ds.get("dataverse_doi", "") or ""
            clean_doi = raw_doi[4:] if raw_doi.startswith("doi:") else raw_doi
            candidates.append({
                "name": ds.get("title", ""),
                "provider": f"Curated Registry ({ds.get('journal', '?')})",
                "url": f"https://doi.org/{clean_doi}" if clean_doi else "",
                "design_tier": ds.get("design_tier", 3),
                "score_ceiling": ds.get("score_ceiling", 80),
                "method": ds.get("design", ""),
                "source_api": "curated_registry",
            })

    # Journal collections: 1 quick query
    if search_multiple_journals is not None:
        try:
            jr = search_multiple_journals(
                journal_keys=["QJE", "REStat"], query=variant, max_per_journal=2
            )
            for r in jr:
                r["source_api"] = "journal"
            candidates.extend(jr)
        except Exception:
            pass

    # Peru-specific official sources when topic is Peru-related:
    #   INEI    — survey microdata (cross-sections / panels)
    #   BCRP    — macro monthly time series (inflation, FX, GDP, rates, trade)
    #   Datos Abiertos — national open-data portal (CKAN search + curated CSVs)
    #   INGEMMET — mining/geology spatial data (WFS)
    #   MEF     — canon/transfer references (manual download, no API)
    if _is_peru_topic(variant):
        candidates.extend(_search_inei(variant, max_results=5))
        candidates.extend(_search_bcrp(variant, max_results=1))
        candidates.extend(_search_minem(variant, max_results=1))
        candidates.extend(_search_datosabiertos_curated(variant, max_results=5))
        candidates.extend(_search_datosabiertos_peru(variant, max_results=5))
        candidates.extend(_search_peru_replication_packages(variant, max_results=5))
        candidates.extend(_search_ocds(variant, max_results=5))
        candidates.extend(_search_punku(variant, max_results=1))
        candidates.extend(_search_indecopi(variant, max_results=3))
        candidates.extend(_search_ingemmet(variant, max_results=2))
        candidates.extend(_search_mef_consulta_amigable(variant, max_results=2))

    n_total = len(candidates)
    n_high = sum(1 for c in candidates if _likely_quality(c))
    return {
        "variant": variant,
        "n_total": n_total,
        "n_high_conf": n_high,
        "candidates": candidates,
    }


def _rank_and_select_variant(counts: list[dict], original_topic: str) -> dict:
    """Display variants ranked by high-confidence count and select the winner.

    Auto-selection rule: pick the variant with the highest n_high_conf. If
    multiple variants tie at 0, fall back to the original topic.
    """
    sorted_counts = sorted(counts, key=lambda c: c["n_high_conf"], reverse=True)

    print(f"\n  TOPIC SUGGESTIONS (ranked by high-confidence quality datasets):")
    print(f"  {'-' * 70}")
    max_high = max((c["n_high_conf"] for c in sorted_counts), default=1) or 1
    for i, c in enumerate(sorted_counts, 1):
        bar_width = int(20 * c["n_high_conf"] / max_high)
        bar = "#" * bar_width + " " * (20 - bar_width)
        marker = " <-- original" if c["variant"] == original_topic else ""
        print(f"  {i}. [{bar}] {c['n_high_conf']:>3} hi-conf "
              f"({c['n_total']:>3} total) — {c['variant'][:50]}{marker}")
    print()

    # Auto-select: best by high-confidence
    best = sorted_counts[0]
    if best["n_high_conf"] == 0:
        # Nothing passes proxy — fall back to the variant with most total hits
        best = sorted(counts, key=lambda c: c["n_total"], reverse=True)[0]
        print(f"  [select] No high-confidence variants. Picking by total hits: '{best['variant']}'")
    else:
        print(f"  [select] Auto-selected: '{best['variant']}' "
              f"({best['n_high_conf']} high-confidence, {best['n_total']} total)")
    return best


def _validate_path_a_candidates(candidates: list[dict],
                                project_dir: Path,
                                max_attempts: int = 8,
                                peru_topic: bool = False) -> list[dict]:
    """Download top candidates and apply Q1-Q8-style validation.

    Reuses the Stage 1.5 download/profile/feasibility helpers. Returns
    qualified datasets only (those passing _MIN_ROWS, _MIN_COLS, ceiling
    threshold, and basic missing-data check).

    When peru_topic=True, INEI datasets are tried first so they are not
    crowded out by high-ceiling international datasets.
    """
    from .stage1_5_data_loading import (
        _try_download_dataverse, _try_download_zenodo, _try_download_direct,
    )

    data_dir = project_dir / "data" / "external"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Sort: for Peru topics INEI goes first (tier 0); otherwise sort by
    # quality proxy then score_ceiling descending.
    def _rank_key(c):
        src = c.get("source_api", "")
        if peru_topic and src in ("inei", "bcrp", "datosabiertos_curated", "minem", "ingemmet"):
            return (0, 0)
        hi = 1 if _likely_quality(c) else 2
        return (hi, -(c.get("score_ceiling", 0) or 0))
    sorted_candidates = sorted(candidates, key=_rank_key)

    qualified = []
    attempted = 0
    for c in sorted_candidates:
        if attempted >= max_attempts:
            break
        if len(qualified) >= 3:
            break  # We only need 3 validated datasets for Stage 2
        attempted += 1

        url = c.get("download_url") or c.get("url", "")
        provider = (c.get("provider") or "").lower()
        name = (c.get("name") or "Unknown")[:60]
        if not url:
            continue

        print(f"  [{attempted}/{max_attempts}] Downloading: {name}")

        # Reuse Stage 1.5 download helpers based on URL/provider
        local_path = None
        src_api = c.get("source_api", "")
        if src_api == "inei" or "inei" in provider:
            from .stage1_5_data_loading import _try_download_inei
            local_path = _try_download_inei(c, data_dir)
        elif src_api == "bcrp":
            from .stage1_5_data_loading import _try_download_bcrp
            local_path = _try_download_bcrp(c, data_dir)
        elif src_api == "minem":
            from .stage1_5_data_loading import _try_download_minem
            local_path = _try_download_minem(c, data_dir)
        elif src_api == "ocds":
            ocds_url = c.get("download_url", "")
            local_path = _try_download_ocds(ocds_url, data_dir) if ocds_url else None
        elif src_api == "punku":
            punku_url = c.get("download_url", "")
            local_path = _try_download_direct(punku_url, data_dir) if punku_url else None
        elif src_api == "indecopi":
            print(f"       [indecopi] Manual fetch required — skipping automated download")
            continue  # no automated download; user must scrape manually
        elif src_api == "ingemmet":
            from .stage1_5_data_loading import _try_download_ingemmet
            local_path = _try_download_ingemmet(c, data_dir)
        elif src_api == "mef_consulta_amigable":
            print(f"       [mef] Manual download — see export instructions")
            instructions = c.get("export_instructions", "")
            if instructions:
                for line in instructions.split("\n"):
                    print(f"       {line}")
            continue  # manual download only
        elif src_api in ("datosabiertos_curated", "datosabiertos_peru") or "datosabiertos" in provider:
            from .stage1_5_data_loading import _try_download_datosabiertos
            local_path = _try_download_datosabiertos(c, data_dir)
        elif "dataverse" in provider or "doi.org/10.7910" in url or "dataverse" in url:
            local_path = _try_download_dataverse(url, data_dir)
        elif "zenodo" in provider or "zenodo.org" in url:
            local_path = _try_download_zenodo(url, data_dir)
        if not local_path:
            local_path = _try_download_direct(url, data_dir)
        if not local_path:
            print(f"       [skip] Could not download")
            continue

        # Skip files > 300 MB — too slow/risky to load fully at Stage 1.
        _file_mb = Path(local_path).stat().st_size / (1024 * 1024)
        if _file_mb > 300:
            print(f"       [skip] File too large for Stage 1 profiling ({_file_mb:.0f} MB > 300 MB limit)")
            continue

        # Profile + minimal Q-checks
        try:
            profile = _profile_dataset(local_path)
            if profile["rows"] < 200:
                print(f"       [skip] Only {profile['rows']} rows (need >=200)")
                continue
            if profile["cols"] < 5:
                print(f"       [skip] Only {profile['cols']} cols (need >=5)")
                continue

            # Quick missing-data check (simplified Q1)
            try:
                import pandas as _pd_chk
                ext = Path(local_path).suffix.lower()
                if ext == ".dta":
                    _df = _pd_chk.read_stata(local_path)
                elif ext == ".tab":
                    _df = _pd_chk.read_csv(local_path, sep="\t",
                                           encoding="latin-1", low_memory=False)
                elif ext == ".parquet":
                    _df = _pd_chk.read_parquet(local_path)
                else:
                    _df = _pd_chk.read_csv(local_path, encoding="latin-1",
                                           low_memory=False)
                missing_pcts = _df.isnull().mean()
                high_missing = (missing_pcts > 0.20).sum()
                if high_missing / max(len(_df.columns), 1) > 0.20:
                    print(f"       [skip] {high_missing}/{len(_df.columns)} cols >20% missing")
                    continue
            except Exception as e:
                print(f"       [warn] Missing-data check failed: {e}")

            # Feasibility / ceiling check
            from .stage1_5_data_loading import _assess_feasibility
            feasibility = _assess_feasibility(
                [{"profile": profile, "dataset": c, "local_path": local_path, "warnings": []}],
                [],
            )
            ceiling = feasibility.get("score_ceiling", 0)
            tier = feasibility.get("max_tier", 9)

            # RCT / experiment boost — same logic as Path C. If the dataset
            # title or design hint signals an RCT or natural experiment, raise
            # the ceiling because identification is built into the design.
            name_lower = (c.get("name") or "").lower()
            method_lower = (c.get("method") or "").lower()
            design_tier_hint = c.get("design_tier", 9)
            rct_keywords = ["rct", "experiment", "randomiz", "trial"]
            ne_keywords = ["natural experiment", "stagger", "did",
                           "difference-in-difference", "difference in difference",
                           "regression discontinuity", "rdd", "instrumental"]
            if design_tier_hint == 1 or any(k in name_lower or k in method_lower
                                            for k in rct_keywords):
                ceiling = max(ceiling, 90)
                tier = min(tier, 1)
            elif design_tier_hint == 2 or any(k in name_lower or k in method_lower
                                              for k in ne_keywords):
                ceiling = max(ceiling, 85)

            # Path A threshold: 75 (vs Path C's 85). Path A is more permissive
            # because it filters by topic, not by broad availability — a
            # topic-relevant 75 ceiling is preferable to a generic 85.
            if ceiling < 75:
                print(f"       [skip] Ceiling {ceiling}/100 < 75 threshold")
                continue

            # ── Treatment-outcome correlation check ───────────────────────
            # Even if a dataset has a great causal design (RCT tier 1) and
            # passes Q1-Q8, it may still produce a NULL paper if treatment
            # has no detectable correlation with any outcome. We reject
            # candidates where NO numeric variable shows |corr| > 0.03 with
            # the most plausible treatment column. This prevents the
            # pipeline from spending resources producing a paper with
            # uniformly null effects on a topic the data does not address.
            try:
                import numpy as _np_corr
                # Detect treatment column: prefer binary balanced columns
                # whose name suggests treatment. If none found, skip the
                # check (don't reject — corr check is a positive signal,
                # not a hard requirement).
                treat_keywords = ("treat", "vbt", "assign", "arm", "random",
                                  "intervent", "voucher", "lottery")
                treat_cols = [
                    col for col in _df.columns
                    if any(k in col.lower() for k in treat_keywords)
                    and _df[col].nunique() <= 8
                ]
                # Prefer the first binary column with balanced groups
                treat_col = None
                for tc in treat_cols:
                    s = _df[tc].dropna()
                    if s.dtype.kind in "biufc" and 2 <= s.nunique() <= 5:
                        vc = s.value_counts(normalize=True)
                        if vc.min() >= 0.10:  # at least 10% in smallest group
                            treat_col = tc
                            break

                if treat_col is not None:
                    # Find numeric outcome candidates: high cardinality, std>0
                    max_corr = 0.0
                    best_outcome = None
                    for col in _df.select_dtypes(include=[_np_corr.number]).columns:
                        if col == treat_col:
                            continue
                        s = _df[col].dropna()
                        if len(s) < 100 or s.nunique() < 5 or s.std() < 1e-8:
                            continue
                        try:
                            common = _df[[treat_col, col]].dropna()
                            if len(common) < 100:
                                continue
                            corr = abs(common[treat_col].corr(common[col]))
                            if not _np_corr.isnan(corr) and corr > max_corr:
                                max_corr = corr
                                best_outcome = col
                        except Exception:
                            continue

                    # Dynamic threshold: 2 SE for a correlation coefficient =
                    # 2 / sqrt(n - 2). Floor at 0.05 to avoid trivial signals
                    # in very large samples. Using 2 SE means we require the
                    # max correlation to be at least nominally significant
                    # — a real association, not noise from many comparisons.
                    n_obs = len(_df)
                    sample_thresh = 2.0 / max(_np_corr.sqrt(n_obs - 2), 1.0)
                    CORR_THRESHOLD = max(0.05, float(sample_thresh))
                    if max_corr < CORR_THRESHOLD:
                        print(f"       [skip] Max treatment-outcome correlation "
                              f"({max_corr:.3f}) below threshold ({CORR_THRESHOLD:.3f}, "
                              f"n={n_obs}) — data likely produces null paper")
                        continue
                    else:
                        print(f"       [corr] {treat_col} <-> {best_outcome}: "
                              f"|r|={max_corr:.3f} (>{CORR_THRESHOLD:.3f}, n={n_obs})")
            except Exception as _ce:
                print(f"       [warn] Corr check failed (continuing): {_ce}")

            # ── Balance-test-passing check ───────────────────────────────
            # If the dataset is an RCT/quasi-experiment, randomization should
            # produce balanced covariates. A severe balance failure (omnibus
            # F-test p < 0.01) signals broken randomization or a non-random
            # treatment assignment, which caps the identification score and
            # makes peer reviewers immediately suspicious. We reject datasets
            # where balance fails CATASTROPHICALLY (p < 0.001) — moderate
            # imbalance (p in [0.001, 0.05]) is allowed because controls can
            # absorb it. This check is skipped if no treatment column was
            # found earlier (treat_col is None from the corr check block).
            try:
                if 'treat_col' in dir() and treat_col is not None:
                    import numpy as _np_bal
                    # Pick up to 6 numeric covariates with std>0 (excluding
                    # treatment itself and the best_outcome to avoid
                    # tautology). Use a simple OLS F-test for joint
                    # significance of covariates predicting treatment.
                    cov_candidates = []
                    for col in _df.select_dtypes(include=[_np_bal.number]).columns:
                        if col == treat_col or col == best_outcome:
                            continue
                        s = _df[col].dropna()
                        if len(s) < 100 or s.nunique() < 3 or s.std() < 1e-8:
                            continue
                        cov_candidates.append(col)
                        if len(cov_candidates) >= 6:
                            break

                    if len(cov_candidates) >= 2:
                        bal_df = _df[[treat_col] + cov_candidates].dropna()
                        if len(bal_df) >= 100:
                            try:
                                import statsmodels.api as _sm_bal
                                X_bal = _sm_bal.add_constant(
                                    bal_df[cov_candidates].astype(float).values
                                )
                                y_bal = bal_df[treat_col].astype(float).values
                                bal_fit = _sm_bal.OLS(y_bal, X_bal).fit()
                                f_pval = float(bal_fit.f_pvalue)
                                BAL_THRESH = 0.001
                                if f_pval < BAL_THRESH:
                                    print(f"       [skip] Balance test FAILED "
                                          f"(F-test p={f_pval:.5f} < {BAL_THRESH}) — "
                                          f"randomization likely broken")
                                    continue
                                else:
                                    print(f"       [balance] F-test p={f_pval:.3f} "
                                          f"(>{BAL_THRESH}, balance OK)")
                            except Exception as _be:
                                print(f"       [warn] Balance F-test failed: {_be}")
            except Exception as _be:
                print(f"       [warn] Balance check failed (continuing): {_be}")

            print(f"       [ok] {profile['rows']:,} rows × {profile['cols']} cols | "
                  f"ceiling={ceiling}/100 | tier={tier}")
            qualified.append({
                "dataset": c,
                "local_path": str(local_path),
                "profile": profile,
                "ceiling": ceiling,
                "tier": tier,
            })
        except Exception as e:
            print(f"       [error] Validation failed: {e}")
            continue

    return qualified


def _run_path_a_topic_aware(project_dir: Path, topic: str, state: dict) -> dict:
    """New Path A: topic-aware discovery with quality validation.

    Replaces the old WebSearch + LLM consolidator flow with:
      1. Expand topic into 8 variants (LLM)
      2. Count quality candidates per variant (proxy filter)
      3. Display ranking, auto-select winner
      4. Download + validate top candidates of the winning variant
      5. Return only datasets that pass the quality gate

    The returned `papers_data` is in the same shape that the rest of the
    pipeline expects — `{"topic": ..., "data_sources": [...]}` — so
    downstream stages don't need to change.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import time as _time

    print(f"\n{'=' * 60}")
    print(f"STAGE 1: Discovery - Path A (topic-aware)")
    print("=" * 60)
    print(f"  Original topic: '{topic}'")

    t0 = _time.time()

    # ── Phase 1: Expand topic into variants ─────────────────────────────
    variants = _expand_topic_variants(topic, n=8)
    for i, v in enumerate(variants, 1):
        print(f"    {i}. {v}")

    # ── Phase 2: Count quality candidates per variant in parallel ──────
    print(f"\n  [count] Searching 5 quality sources per variant in parallel...")
    counts = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_count_quality_candidates_for_variant, v): v
                   for v in variants}
        for f in as_completed(futures):
            try:
                counts.append(f.result())
            except Exception as e:
                v = futures[f]
                print(f"  [count] Variant '{v}' failed: {e}")
                counts.append({"variant": v, "n_total": 0, "n_high_conf": 0,
                               "candidates": []})

    elapsed_count = _time.time() - t0
    print(f"  [count] All variants counted ({elapsed_count:.0f}s)")

    # ── Phase 3: Rank + select winner ──────────────────────────────────
    selected = _rank_and_select_variant(counts, topic)

    # ── Remove candidates whose datasets were already used in other projects ──
    # INEI surveys are reused (same data, different questions) — only exclude
    # Dataverse/journal replication packages to avoid duplicate papers.
    try:
        from ..config import PAPERS_HQ
        _used_names: set[str] = set()
        for _proj in (PAPERS_HQ / "projects").iterdir():
            if not _proj.is_dir() or _proj == project_dir:
                continue
            _sf = _proj / "pipeline_state.json"
            if not _sf.exists():
                continue
            try:
                _ps = json.loads(_sf.read_text(encoding="utf-8"))
                for _ds in _ps.get("stages", {}).get("stage1_5", {}).get(
                        "downloaded_datasets", []):
                    _n = Path(_ds.get("local_path", "")).name.lower()
                    if _n and not _n.startswith("enaho") and not _n.startswith("inei"):
                        _used_names.add(_n)
            except Exception:
                pass
        if _used_names:
            before = len(selected["candidates"])
            selected["candidates"] = [
                c for c in selected["candidates"]
                if c.get("source_api") == "inei"
                or Path(c.get("url", "")).name.lower() not in _used_names
            ]
            removed = before - len(selected["candidates"])
            if removed:
                print(f"  [dedup] Excluded {removed} datasets already used in previous projects")
    except Exception:
        pass

    # ── Phase 4: Download + validate top candidates of winner ──────────
    print(f"\n  [validate] Downloading + validating candidates of winning variant...")
    qualified = _validate_path_a_candidates(
        selected["candidates"], project_dir, max_attempts=8,
        peru_topic=_is_peru_topic(topic),
    )

    elapsed_total = _time.time() - t0
    print(f"\n  [done] Path A complete ({elapsed_total:.0f}s) — "
          f"{len(qualified)} datasets passed quality gate")

    if not qualified:
        print(f"  [warn] No datasets passed Q1-Q8 + ceiling >= 75 for any variant")
        print(f"         Topic may be too narrow. Consider:")
        print(f"           - Broader keywords")
        print(f"           - Running --path-c for dataset-first discovery")
        print(f"           - Providing your own data with --data")

    # ── Phase 5: Format output for downstream stages ────────────────────
    data_sources = []
    for q in qualified:
        ds = q["dataset"]
        prof = q["profile"]
        data_sources.append({
            "name": ds.get("name", "Unknown"),
            "provider": ds.get("provider", "?"),
            "url": ds.get("url", ""),
            "local_path": q["local_path"],
            "data_structure": prof.get("structure", "unknown"),
            "n_rows": prof["rows"],
            "n_cols": prof["cols"],
            "score_ceiling": q["ceiling"],
            "tier": q["tier"],
            "source_api": ds.get("source_api", "?"),
            "selected_variant": selected["variant"],
            "country": _infer_country(ds),
        })

    seed_papers = []
    paperdl_mode = _resolve_paperdl_mode(state)
    stage2_mode = state.get("config", {}).get("stage2_mode", "ask")

    # i4replication.org catalog — only in replicate mode (293 verified papers)
    if stage2_mode == "replicate":
        seed_papers.extend(_search_i4replication(selected["variant"], max_results=10))
        if selected["variant"] != topic:
            seed_papers.extend(_search_i4replication(topic, max_results=5))

        # OpenICPSR replication packages (AEA, NBER, journals) — replicate only
        seed_papers.extend(_search_openicpsr(selected["variant"], max_results=8))
        if selected["variant"] != topic:
            seed_papers.extend(_search_openicpsr(topic, max_results=4))

        # Peru DSpace repositories (PUCP, UP, CONCYTEC) — replicate only
        seed_papers.extend(_search_peru_dspace_repos(selected["variant"], max_results_each=4))
        if selected["variant"] != topic:
            seed_papers.extend(_search_peru_dspace_repos(topic, max_results_each=2))

    # ALICIA (Peru national OA repo) — always, not just replicate mode
    seed_papers.extend(_search_alicia(selected["variant"], max_results=6))
    if selected["variant"] != topic:
        seed_papers.extend(_search_alicia(topic, max_results=4))

    # paperdl (arXiv, OpenReview, PMLR, PMC) — richer metadata than SS alone
    seed_papers.extend(_search_paperdl_seed_papers(selected["variant"], max_results=8, mode=paperdl_mode))
    seed_papers.extend(_search_semantic_scholar_seed_papers(selected["variant"], max_results=8))
    if selected["variant"] != topic:
        seed_papers.extend(_search_paperdl_seed_papers(topic, max_results=5, mode=paperdl_mode))
        seed_papers.extend(_search_semantic_scholar_seed_papers(topic, max_results=5))
    for c in selected.get("candidates", []):
        p = _candidate_to_seed_paper(c)
        if p:
            seed_papers.append(p)
    seed_papers = _dedupe_seed_papers(seed_papers)

    papers_data = {
        "topic": topic,
        "selected_variant": selected["variant"],
        "all_variants": [
            {"variant": c["variant"], "n_high_conf": c["n_high_conf"],
             "n_total": c["n_total"]}
            for c in counts
        ],
        "data_sources": data_sources,
        "seed_papers": seed_papers,
    }

    output_file = project_dir / "stage1_discovery.md"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(papers_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  [saved] {output_file}")

    state["stages"]["stage1"] = {
        "status": "completed",
        "topic": topic,
        "selected_variant": selected["variant"],
        "path": "A",
        "output_file": str(output_file),
        "completed_at": datetime.now().isoformat(),
        "recommended_data_sources": data_sources,
        "seed_papers": seed_papers,
    }

    # Path A now downloads + validates in Stage 1 itself, so populate the
    # Stage 1.5 slot too. Stage 2 prefers stage1_5.downloaded_datasets (rich
    # profile with real variable names) over stage1.recommended_data_sources
    # (metadata-only fallback). Without this, Stage 2 would lose access to
    # the actual column names and structure details.
    downloaded_for_stage_1_5 = []
    for q in qualified:
        ds = q["dataset"]
        prof = q["profile"]
        downloaded_for_stage_1_5.append({
            "name": ds.get("name", "Unknown"),
            "provider": ds.get("provider", "?"),
            "url": ds.get("url", ""),
            "local_path": q["local_path"],
            "country": _infer_country(ds),
            "profile": {
                "rows": prof.get("rows", 0),
                "cols": prof.get("cols", 0),
                "structure": prof.get("structure", "unknown"),
                "id_cols": prof.get("id_cols", []),
                "time_cols": prof.get("time_cols", []),
                "columns": prof.get("columns", []),
                "panel_details": prof.get("panel_details", {}),
                "panel_flag": prof.get("panel_flag", False),
                "data_summary": prof.get("data_summary", ""),
                "wide_panel": prof.get("wide_panel"),
            },
            "score_ceiling": q["ceiling"],
            "tier": q["tier"],
        })
    state["stages"]["stage1_5"] = {
        "status": "completed",
        "completed_at": datetime.now().isoformat(),
        "downloaded_datasets": downloaded_for_stage_1_5,
        "not_downloaded": [],
        "feasibility": {
            "score_ceiling": max(
                (q["ceiling"] for q in qualified), default=0
            ),
            "max_tier": min(
                (q["tier"] for q in qualified), default=9
            ),
        },
    }

    state["current_stage"] = 1
    save_state(project_dir, state)

    print(f"\n  {'=' * 60}")
    print(f"  STAGE 1 PATH A — COMPLETE")
    print(f"  {'=' * 60}")
    print(f"  Original topic:    {topic}")
    print(f"  Selected variant:  {selected['variant']}")
    print(f"  Validated datasets: {len(data_sources)}")
    if data_sources:
        for i, ds in enumerate(data_sources, 1):
            print(f"\n    [{i}] {ds['name'][:60]}")
            print(f"        Provider:  {ds['provider']}")
            country = ds.get("country", "")
            if country:
                print(f"        Country:   {country}")
            print(f"        Structure: {ds['data_structure']}")
            print(f"        Size:      {ds['n_rows']:,} rows × {ds['n_cols']} cols")
            print(f"        Ceiling:   {ds['score_ceiling']}/100")
    print(f"  {'=' * 60}")

    return state


# ── Public runner ────────────────────────────────────────────────────────────

def run(project_dir: Path, topic: str, state: dict, data_path: Optional[str] = None, path_c: bool = False) -> dict:
    """Execute Stage 1 Discovery - Path A, B, or C."""
    if path_c:
        return _run_path_c(project_dir, state)

    # Path A (no --data): topic-aware discovery with quality validation.
    # Self-contained — handles its own output file, state save, and summary.
    if not data_path:
        return _run_path_a_topic_aware(project_dir, topic, state)

    path = "B"
    print(f"\n{'=' * 60}")
    print(f"STAGE 1: Discovery - Path {path}")
    print("=" * 60)

    profile = None
    early_warnings = []

    # ── Path B: profile the user dataset first ──────────────────────────
    if data_path:
        print("  [data] Profiling user dataset...")
        profile = _profile_dataset(data_path)
        print(f"  [data] {profile['rows']} rows x {profile['cols']} cols")
        if profile["panel_flag"]:
            print("  [data] Panel structure detected")

        early_warnings = _early_warning(profile)
        if early_warnings:
            print()
            for w in early_warnings:
                print(f"  [!] {w}")
            print()
            print("\a", end="", flush=True)  # Terminal bell — user input needed
            proceed = input("  Continue despite warnings? [y/N] ").strip().lower()
            if proceed != "y":
                print("  [stop] Aborted by user.")
                sys.exit(0)

        # Causal design assessment — warn early about score ceiling
        _causal_design_warning(profile)

        # Build a Path B prompt with rich data context
        folder_ctx = profile.get("folder_context", "")
        primary_file_note = (
            f"\nPrimary file profiled: {profile['primary_file']}\n"
            f"Other files in folder (not loaded): {', '.join(profile.get('all_files', [])[1:10])}\n"
            if profile.get("primary_file") else ""
        )
        cols_summary = ", ".join(profile["columns"][:30])
        if len(profile["columns"]) > 30:
            cols_summary += f", ... ({len(profile['columns'])} total)"

        # Structure-specific method guidance
        structure = profile["structure"]
        if structure == "wide-panel":
            pd_info = profile["panel_details"]
            core_sample = ", ".join(pd_info.get("core_vars_sample", [])[:10])
            suffixes = pd_info.get("year_suffixes", [])
            years = pd_info.get("time_values", [])
            unsuffixed = ", ".join(pd_info.get("unsuffixed_cols", [])[:15])
            vars_per = pd_info.get("vars_per_period", {})
            vars_per_str = ", ".join(f"{s}: {n} vars" for s, n in vars_per.items())
            structure_desc = (
                f"WIDE-FORMAT PANEL DATA — time is encoded in column name suffixes.\n"
                f"  Year suffixes: {', '.join(suffixes)}\n"
                f"  Corresponding years: {years}\n"
                f"  Time periods: {pd_info.get('n_time_periods', '?')}\n"
                f"  Variables per period: {vars_per_str}\n"
                f"  Core variables (shared across all periods): {pd_info.get('n_core_vars', '?')}\n"
                f"  Sample core vars: {core_sample}\n"
                f"  Time-invariant/ID columns: {unsuffixed}\n"
                f"\n"
                f"  IMPORTANT: Each variable appears once per year with a suffix "
                f"(e.g., {core_sample.split(',')[0].strip()}_{suffixes[0]}, "
                f"{core_sample.split(',')[0].strip()}_{suffixes[-1]}).\n"
                f"  The data MUST be reshaped from wide to long format before panel analysis.\n"
                f"  After reshaping, each row = one individual-year observation."
            )
            method_guidance = (
                "Applicable methods (after reshaping to long): DiD, event study, TWFE, "
                "individual fixed effects, dynamic panel (Arellano-Bond), Markov transition "
                "matrices, survival models, correlated random effects. "
                "The script generation stage MUST include a reshape step (wide_to_long or melt) "
                "before any econometric estimation."
            )
        elif structure == "panel":
            pd_info = profile["panel_details"]
            structure_desc = (
                f"TRUE PANEL DATA — the same individuals are tracked over time.\n"
                f"  ID column: {pd_info.get('id_column', '?')}\n"
                f"  Time column: {pd_info.get('time_column', '?')}\n"
                f"  Unique individuals: {pd_info.get('n_unique_ids', '?'):,}\n"
                f"  Time periods: {pd_info.get('n_time_periods', '?')}\n"
                f"  % IDs in 2+ periods: {pd_info.get('pct_ids_multiple_periods', '?')}%\n"
                f"  Avg obs per individual: {pd_info.get('avg_obs_per_id', '?')}"
            )
            method_guidance = (
                "Applicable methods: DiD, event study, TWFE, individual fixed effects, "
                "dynamic panel (Arellano-Bond), Markov transition matrices, survival models."
            )
        elif structure == "pooled-cross-sections":
            pd_info = profile["panel_details"]
            structure_desc = (
                f"POOLED CROSS-SECTIONS — different individuals sampled each period.\n"
                f"  ID column: {pd_info.get('id_column', '?')} (does NOT repeat across time)\n"
                f"  Time column: {pd_info.get('time_column', '?')}\n"
                f"  Time periods: {pd_info.get('n_time_periods', '?')}\n"
                f"  Time values: {pd_info.get('time_values', [])}\n"
                f"  CRITICAL: You CANNOT track individuals over time. "
                f"Only {pd_info.get('pct_ids_multiple_periods', 0)}% of IDs appear in 2+ periods."
            )
            method_guidance = (
                "Applicable methods: DiD at GROUP level (not individual), repeated cross-section DiD, "
                "IV, RDD, propensity score matching, Oaxaca-Blinder decomposition, "
                "synthetic control (aggregate), cohort analysis. "
                "NOT applicable: individual fixed effects, individual-level event study, "
                "Markov transition matrices, survival/hazard models tracking individuals."
            )
        elif structure == "repeated-cross-sections":
            pd_info = profile["panel_details"]
            structure_desc = (
                f"REPEATED CROSS-SECTIONS — multiple survey waves, no individual tracking.\n"
                f"  Time column: {pd_info.get('time_column', '?')}\n"
                f"  Time periods: {pd_info.get('n_time_periods', '?')}\n"
                f"  No individual ID column found."
            )
            method_guidance = (
                "Applicable methods: group-level DiD, repeated cross-section DiD, "
                "IV, RDD, decompositions, cohort/pseudo-panel analysis. "
                "NOT applicable: individual FE, individual event study, transition matrices."
            )
        else:
            structure_desc = (
                f"SINGLE CROSS-SECTION — one snapshot in time, no panel dimension."
            )
            method_guidance = (
                "Applicable methods: IV, RDD, matching (PSM, CEM), "
                "Oaxaca-Blinder decomposition, Heckman selection model, "
                "quantile regression, LASSO for variable selection. "
                "NOT applicable: DiD, event study, fixed effects, transition matrices."
            )

        prompt = f"""You are a research discovery assistant (Path B - user-provided data).

The researcher works in: **{topic}**
{folder_ctx if folder_ctx else ""}
{primary_file_note}
## Dataset Structure Analysis

{structure_desc}

{method_guidance}

## Dataset Details

- Rows: {profile['rows']:,}
- Columns: {profile['cols']}
- Variables: {cols_summary}
- ID columns detected: {', '.join(profile['id_cols'][:5]) if profile['id_cols'] else 'None'}
- Time columns detected: {', '.join(profile['time_cols'][:5]) if profile['time_cols'] else 'None'}

## Data Sample

{profile.get('data_summary', profile.get('sample_rows', 'N/A'))}

## CRITICAL RULES

1. You MUST respect the data structure classification above. If the data is
   "pooled cross-sections" or "cross-sectional", do NOT suggest methods that
   require tracking the same individual over time (panel FE, Markov transitions,
   individual event study, survival models).
2. Only suggest methods that are IMPLEMENTABLE with the actual variables present.
3. If the data has a time dimension but is NOT panel, you can use group-level
   variation over time (e.g., regional DiD, cohort DiD) but NOT individual-level.

## TASK

Based on the dataset structure above, summarize the key characteristics and
recommend the most promising causal methods for this data.

Output a JSON block:
```json
{{
  "topic": "{topic}",
  "data_profile": {{
    "rows": {profile['rows']},
    "cols": {profile['cols']},
    "structure": "{structure}",
    "panel": {str(profile['panel_flag']).lower()},
    "id_cols": {profile['id_cols'][:5]},
    "time_cols": {profile['time_cols'][:5]},
    "warnings": {early_warnings},
    "recommended_methods": ["method1", "method2", "method3"]
  }}
}}
```
"""

    # ── Path A is handled above by _run_path_a_topic_aware() ────────────
    # The legacy multi-agent search + LLM consolidator code below is kept
    # in place but unreachable (the early-return at the top of run()
    # handles Path A). It is preserved for reference and in case we want
    # to revive specific subagents (e.g. WebSearch) as opt-in features.
    if False:  # legacy Path A — unreachable
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time as _time

        print(f"\n  [search] Launching 3 parallel searches...")
        t0 = _time.time()

        # ── Subagent 1: Claude web search (identification-first) ──────
        web_prompt = (
            f'You are searching for datasets to study "{topic}" with CAUSAL identification.\n'
            f'\n'
            f'IDENTIFICATION-FIRST APPROACH: Do NOT just search for data about {topic}.\n'
            f'Instead, search for NATURAL EXPERIMENTS related to {topic}:\n'
            f'  1. Policy reforms that were adopted at different times in different regions\n'
            f'     (staggered rollout = DiD with clean control group)\n'
            f'  2. Eligibility thresholds or cutoffs (age, income, score = RDD)\n'
            f'  3. Bans, restrictions, or access limitations that varied by jurisdiction\n'
            f'  4. Exogenous shocks that affected some units more than others\n'
            f'  5. Replication packages from TOP JOURNAL papers that used causal designs\n'
            f'     on topics related to "{topic}"\n'
            f'\n'
            f'Search: government microdata portals (IPUMS, DHS, LSMS, EU-SILC, CFPS),\n'
            f'international orgs (World Bank, OECD, UNESCO, ILO), Harvard Dataverse,\n'
            f'or any national statistics office worldwide.\n'
            f'Prefer panel data with staggered treatment or discontinuities.\n'
            f'Do NOT default to any specific country.\n'
            f'\n'
            f'CRITICAL: If the topic involves a UNIVERSAL SHOCK (e.g., a global product\n'
            f'launch, a pandemic), search for data where ACCESS or EXPOSURE varied across\n'
            f'units (country bans, regional restrictions, infrastructure differences).\n'
            f'A dataset with treatment variation is worth 10x a dataset without it.\n'
            f'\n'
            f'Return ONLY a JSON object:\n'
            f'{{"name": "...", "provider": "...", "url": "https://...",'
            f' "data_structure": "panel|cross-section|repeated-cross-sections",'
            f' "time_span": "...", "n_years": 0,'
            f' "natural_experiment": "SPECIFIC description of what creates treatment variation",'
            f' "control_group": "WHO is untreated and WHY",'
            f' "causal_methods_enabled": ["DiD"], "causal_score": 0,'
            f' "format": ".csv", "access": "free_direct|free_registration|restricted",'
            f' "files_needed": ["file.csv"], "limitations": "..."}}'
        )
        p = get_profile("stage1")

        # Run all sources in parallel: Claude web search + Dataverse + Zenodo + GitHub
        # + DBnomics (macro meta-aggregator) + data.gov + World Bank + IDB
        # + EU Open Data + data.gov.uk + data.gouv.fr
        # + national CKAN portals: data.gov.au, open.canada.ca, datos.gob.mx,
        #   govdata.de, dati.gov.it
        # + Socrata federated catalog (~30 US city/state portals)
        # + FAOSTAT bulk catalog (agriculture / food / environment panels)
        api_results = {
            "dataverse": [], "zenodo": [], "github": [],
            "dbnomics": [], "datagov": [], "worldbank": [], "idb": [],
            "eu_opendata": [], "data_gov_uk": [], "data_gouv_fr": [],
            "data_gov_au": [], "open_canada": [], "datos_gob_mx": [],
            "govdata_de": [], "dati_gov_it": [],
            "socrata": [], "faostat": [],
        }
        web_result = ""

        def _run_web_search():
            return run_claude(
                web_prompt,
                model=p["model"], effort=p["effort"],
                allowed_tools=["WebSearch", "WebFetch"],
                timeout=120,
                max_retries=1,
                label="web-search",
            )

        def _run_api_searches():
            # Search both the topic directly AND natural experiment variants
            api_results["dataverse"] = _search_dataverse(topic)
            api_results["dataverse"] += _search_dataverse(f"{topic} replication natural experiment")
            api_results["zenodo"] = _search_zenodo(topic)
            api_results["zenodo"] += _search_zenodo(f"{topic} policy reform panel")
            api_results["github"] = _search_github(topic)
            # New sources (added 2026-04-10): cover macro time series, US admin
            # data, World Bank country panels, and Latin American impact evals.
            api_results["dbnomics"] = _search_dbnomics(topic)
            api_results["datagov"] = _search_datagov(topic)
            api_results["worldbank"] = _search_worldbank(topic)
            api_results["idb"] = _search_idb(topic)
            # Pan-European + UK + France open-data portals
            api_results["eu_opendata"] = _search_eu_opendata(topic)
            api_results["data_gov_uk"] = _search_data_gov_uk(topic)
            api_results["data_gouv_fr"] = _search_data_gouv_fr(topic)
            # National CKAN portals (one helper, five wrappers)
            api_results["data_gov_au"]  = _search_data_gov_au(topic)
            api_results["open_canada"]  = _search_open_canada(topic)
            api_results["datos_gob_mx"] = _search_datos_gob_mx(topic)
            api_results["govdata_de"]   = _search_govdata_de(topic)
            api_results["dati_gov_it"]  = _search_dati_gov_it(topic)
            # Phase 2: Socrata federated (~30 US portals) + FAOSTAT bulk catalog
            api_results["socrata"] = _search_socrata(topic)
            api_results["faostat"] = _search_faostat(topic)

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_web = pool.submit(_run_web_search)
            future_api = pool.submit(_run_api_searches)

            for future in as_completed([future_web, future_api]):
                try:
                    result = future.result()
                    if future == future_web:
                        web_result = result
                except Exception as e:
                    if future == future_web:
                        print(f"  [web-search] Timed out or failed — continuing with API results only")
                    else:
                        print(f"  [error] API search failed: {e}")

        elapsed = _time.time() - t0
        print(f"  [search] All searches done ({elapsed:.0f}s)")

        # ── Collect raw results from all sources ──────────────────────
        raw_web = []
        parsed = extract_json(web_result) if web_result else None
        if parsed:
            if isinstance(parsed, dict) and "name" in parsed:
                raw_web.append(parsed)
            elif isinstance(parsed, dict) and "data_sources" in parsed:
                raw_web.extend(parsed["data_sources"])
            elif isinstance(parsed, list):
                raw_web.extend(parsed)

        n_dv = len(api_results["dataverse"])
        n_zn = len(api_results["zenodo"])
        n_gh = len(api_results["github"])
        n_db = len(api_results["dbnomics"])
        n_dg = len(api_results["datagov"])
        n_wb = len(api_results["worldbank"])
        n_idb = len(api_results["idb"])
        n_eu = len(api_results["eu_opendata"])
        n_uk = len(api_results["data_gov_uk"])
        n_fr = len(api_results["data_gouv_fr"])
        n_au = len(api_results["data_gov_au"])
        n_ca = len(api_results["open_canada"])
        n_mx = len(api_results["datos_gob_mx"])
        n_de = len(api_results["govdata_de"])
        n_it = len(api_results["dati_gov_it"])
        n_soc = len(api_results["socrata"])
        n_fao = len(api_results["faostat"])
        n_web = len(raw_web)
        print(
            f"  [search] Results: web={n_web}, dataverse={n_dv}, zenodo={n_zn}, "
            f"github={n_gh}, dbnomics={n_db}, datagov={n_dg}, worldbank={n_wb}, "
            f"idb={n_idb}, eu={n_eu}, uk={n_uk}, fr={n_fr}, "
            f"au={n_au}, ca={n_ca}, mx={n_mx}, de={n_de}, it={n_it}, "
            f"socrata={n_soc}, faostat={n_fao}"
        )

        # ── External curated datasets (Group B: high-value but restricted access)
        # These are offered to the consolidator alongside search results so it can
        # recommend them when relevant, even though they require manual acquisition.
        try:
            from ..dataset_registry import get_external_datasets
            external_curated = get_external_datasets(topic=topic, max_results=10)
        except Exception as e:
            print(f"  [external] Could not load external registry: {e}")
            external_curated = []
        if external_curated:
            print(f"  [external] {len(external_curated)} curated external sources matched topic")

        # ── Subagent 4: Consolidator — evaluate and rank ──────────────
        all_candidates = json.dumps({
            "web_search_results": raw_web,
            "dataverse_results": api_results["dataverse"],
            "zenodo_results": api_results["zenodo"],
            "github_results": api_results["github"],
            "dbnomics_results": api_results["dbnomics"],
            "datagov_results": api_results["datagov"],
            "worldbank_results": api_results["worldbank"],
            "idb_results": api_results["idb"],
            "eu_opendata_results": api_results["eu_opendata"],
            "data_gov_uk_results": api_results["data_gov_uk"],
            "data_gouv_fr_results": api_results["data_gouv_fr"],
            "data_gov_au_results": api_results["data_gov_au"],
            "open_canada_results": api_results["open_canada"],
            "datos_gob_mx_results": api_results["datos_gob_mx"],
            "govdata_de_results": api_results["govdata_de"],
            "dati_gov_it_results": api_results["dati_gov_it"],
            "socrata_results": api_results["socrata"],
            "faostat_results": api_results["faostat"],
            "external_curated_restricted": external_curated,
        }, indent=2, ensure_ascii=False)

        consolidator_prompt = f"""You are a dataset evaluator for causal empirical research.
Your #1 job: find datasets where TREATMENT VARIES ACROSS UNITS.

TOPIC: "{topic}"

Below are candidate datasets found from multiple sources. Select the TOP 3 datasets
that can produce a paper scoring 85+/100. The binding constraint is ALWAYS identification
— a dataset with treatment variation beats a bigger/cleaner dataset without it.

EVALUATION CRITERIA (RANKED BY IMPORTANCE):

1. EXOGENOUS VARIATION (most important — 50% of evaluation):
   Does the data contain a situation where some units are treated and others are not?
   - BEST: Staggered policy rollout (different regions treated at different times)
   - GOOD: Eligibility threshold creating a discontinuity (RDD)
   - OK: Universal treatment but intensity varies cross-sectionally (dose-response)
   - WEAK: Universal simultaneous treatment (before-after only = Level C)

   *** A dataset with clear treatment variation but only 5,000 obs is BETTER than
   a dataset with 500,000 obs but no treatment variation. ***

2. DATA STRUCTURE:
   - Panel data (same units tracked over time) >> repeated cross-sections >> cross-section
   - Pre-treatment periods: at least 3 years before treatment for credible pre-trends

3. STATISTICAL POWER:
   - Enough clusters for cluster-robust inference (30+ clusters)
   - Treatment/control groups large enough to detect meaningful effects

4. DATA QUALITY & ACCESS:
   - Publicly accessible, well-documented
   - Low attrition, consistent variable definitions

CAUSAL SCORE (1-5):
  5 = Staggered treatment + panel + 3+ pre-years + clear control group + accessible
  4 = Cross-sectional treatment variation + panel + plausible ID
  3 = Dose variation (continuous treatment) + panel + some pre-periods
  2 = Panel but universal treatment, or cross-section with strong IV/RDD
  1 = Universal simultaneous treatment with no control group

*** REJECT any dataset that can only support Level C identification (causal_score=1)
unless no better option exists. ***

CANDIDATE DATASETS:
{all_candidates}

Select the TOP 3 and return ONLY a JSON block:
```json
{{
  "topic": "{topic}",
  "data_sources": [
    {{
      "name": "Full dataset name",
      "provider": "Organization",
      "url": "https://...",
      "data_structure": "panel",
      "time_span": "2010-2024",
      "n_years": 15,
      "natural_experiment": "Description of exogenous variation",
      "causal_methods_enabled": ["DiD", "event study", "TWFE"],
      "causal_score": 4,
      "format": ".csv",
      "access": "free_direct",
      "files_needed": ["file1.csv"],
      "limitations": "Brief limitation"
    }}
  ]
}}
```
"""
        print(f"\n  [consolidator] Evaluating and ranking datasets...")
        consolidator_response = run_claude(
            consolidator_prompt,
            model=p["model"], effort=p["effort"],
            allowed_tools=[],
            timeout=120,
            label="consolidator",
        )
        papers_data = extract_json(consolidator_response)
        if not papers_data:
            # Fallback: use web search results directly
            papers_data = {"topic": topic, "data_sources": raw_web}

    output_file = project_dir / "stage1_discovery.md"

    if data_path:
        # Path B: single call with haiku, no web search
        p_b = get_profile("stage1_b")
        response = run_claude(
            prompt,
            model=p_b["model"], effort=p_b["effort"],
            allowed_tools=[],
            output_file=output_file,
        )
        papers_data = extract_json(response)
    else:
        # Path A: save consolidated results to output file
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(
            json.dumps(papers_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  [saved] {output_file}")

    state["stages"]["stage1"] = {
        "status": "completed",
        "topic": topic,
        "path": path,
        "output_file": str(output_file),
        "completed_at": datetime.now().isoformat(),
    }

    if data_path:
        state["stages"]["stage1"]["data_path"] = data_path
    if profile:
        state["stages"]["stage1"]["data_profile"] = {
            "rows": profile["rows"],
            "cols": profile["cols"],
            "columns": profile["columns"],
            "structure": profile["structure"],
            "panel_flag": profile["panel_flag"],
            "panel_details": profile.get("panel_details", {}),
            "id_cols": profile.get("id_cols", []),
            "time_cols": profile.get("time_cols", []),
            "wide_panel": profile.get("wide_panel"),
            "warnings": early_warnings,
        }

    # Save recommended data sources (Path A)
    if papers_data and "data_sources" in papers_data:
        state["stages"]["stage1"]["recommended_data_sources"] = papers_data["data_sources"]
        n_sources = len(papers_data["data_sources"])
        best_score = max((ds.get("causal_score", 0) for ds in papers_data["data_sources"]), default=0)
        print(f"  [ok] Found {n_sources} data sources (best causal score: {best_score}/5)")
    if papers_data and "seed_papers" in papers_data:
        state["stages"]["stage1"]["seed_papers"] = papers_data.get("seed_papers", [])
    elif not data_path:
        paperdl_mode = _resolve_paperdl_mode(state)
        seed_papers = _search_paperdl_seed_papers(topic, max_results=8, mode=paperdl_mode)
        seed_papers.extend(_search_semantic_scholar_seed_papers(topic, max_results=8))
        seed_papers = _dedupe_seed_papers(seed_papers)
        state["stages"]["stage1"]["seed_papers"] = seed_papers

    if not papers_data:
        print("  [warn] Could not parse structured JSON. Check stage1_discovery.md manually.")

    # ── Final summary: show user what data is available ────────────────
    print(f"\n  {'=' * 60}")
    print(f"  STAGE 1 DISCOVERY — SUMMARY")
    print(f"  {'=' * 60}")
    print(f"  Topic: {topic}")
    print(f"  Path:  {'B (user data)' if path == 'B' else 'A (dataset search)'}")

    if profile:
        print(f"\n  DATA LOADED:")
        print(f"    File:      {Path(data_path).name}")
        print(f"    Location:  {data_path}")
        print(f"    Rows:      {profile['rows']:,}")
        print(f"    Columns:   {profile['cols']}")
        print(f"    Structure: {profile['structure']}")
        if profile.get("id_cols"):
            print(f"    ID cols:   {', '.join(profile['id_cols'][:5])}")
        if profile.get("time_cols"):
            print(f"    Time cols: {', '.join(profile['time_cols'][:5])}")
        if early_warnings:
            print(f"\n  WARNINGS:")
            for w in early_warnings:
                print(f"    - {w}")
    elif papers_data and papers_data.get("data_sources"):
        sources = papers_data["data_sources"]
        sources.sort(key=lambda x: x.get("causal_score", 0), reverse=True)
        print(f"\n  RECOMMENDED DATASETS ({len(sources)} found):")
        for i, ds in enumerate(sources[:3], 1):
            print(f"\n    [{i}] {ds.get('name', '?')}")
            print(f"        URL:       {ds.get('url', 'N/A')}")
            fmt = ds.get("format", "N/A")
            files = ds.get("files_needed", [])
            if files:
                print(f"        Files:     {', '.join(files[:3])}")
                if len(files) > 3:
                    print(f"                   ... ({len(files)} total)")
            elif fmt:
                print(f"        Format:    {fmt}")
            print(f"        Structure: {ds.get('data_structure', 'N/A')}")
            print(f"        Time span: {ds.get('time_span', 'N/A')}")
            score = ds.get("causal_score", 0)
            print(f"        Causal:    {'*' * score}{'.' * (5 - score)} ({score}/5)")
            access = ds.get("access", "unknown")
            print(f"        Access:    {access}")
        print(f"\n  To use a dataset, re-run with:")
        print(f"  python run_pipeline.py --topic \"{topic}\" --data \"path/to/data.csv\"")
    else:
        print(f"\n  No structured data found. Check stage1_discovery.md for details.")

    print(f"  {'=' * 60}")

    state["current_stage"] = 1
    save_state(project_dir, state)

    # ── NotebookLM checkpoint (optional, human-confirmed) ──────────────────
    try:
        from ..notebooklm_hooks import stage1_notebooklm_checkpoint
        seed_papers = state["stages"]["stage1"].get("seed_papers", [])
        stage1_notebooklm_checkpoint(project_dir, state, topic, seed_papers)
    except Exception:
        pass

    return state
