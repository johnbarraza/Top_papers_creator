"""Journal-targeted literature search for the macro track (OpenAlex, free).

Searches only works that have a version in the selected venues, so seed
papers and the Stage 3 literature review come from the macro journal
frontier and the working-paper series where macro papers circulate first.

Venue tiers (OpenAlex source ids verified against api.openalex.org):
  top5            AER, Econometrica, JPE, QJE, REStud
  macro_field     JME, RED, AEJ:Macro, JEDC, JMCB, QE, JET, JEEA, NBER Macro
                  Annual, BPEA, IMF Economic Review, EER, JIE, EJ
  working_papers  NBER, Fed FEDS, IMF WP, FRB San Francisco, FRB Dallas
  preprints       arXiv
Extra journals can be added by name (resolved through /sources?search=).
"""

from __future__ import annotations

import json
from pathlib import Path

OPENALEX = "https://api.openalex.org"
MAILTO = "pipeline@local"
_CACHE = Path(__file__).resolve().parent / ".journal_cache.json"

VENUES: dict[str, dict[str, str]] = {
    "top5": {
        "S23254222": "American Economic Review",
        "S95464858": "Econometrica",
        "S95323914": "Journal of Political Economy",
        "S203860005": "Quarterly Journal of Economics",
        "S88935262": "Review of Economic Studies",
    },
    "macro_field": {
        "S6711363": "Journal of Monetary Economics",
        "S163499366": "Review of Economic Dynamics",
        "S170166683": "American Economic Journal: Macroeconomics",
        "S44585919": "Journal of Economic Dynamics and Control",
        "S2058785": "Journal of Money, Credit and Banking",
        "S156003414": "Quantitative Economics",
        "S149131268": "Journal of Economic Theory",
        "S165087003": "Journal of the European Economic Association",
        "S127060114": "NBER Macroeconomics Annual",
        "S4210173904": "Brookings Papers on Economic Activity",
        "S21260181": "IMF Economic Review",
        "S69338747": "European Economic Review",
        "S198098467": "Journal of International Economics",
        "S45992627": "The Economic Journal",
    },
    "working_papers": {
        "S2809516038": "NBER Working Papers",
        "S4210212089": "Fed Finance and Economics Discussion Series",
        "S4210171147": "IMF Working Papers",
        "S4306510381": "FRB San Francisco Working Papers",
        "S4363607558": "FRB Dallas Working Papers",
    },
    "preprints": {
        "S4306400194": "arXiv",
    },
}
DEFAULT_SCOPES = ("top5", "macro_field", "working_papers")
TIER_WEIGHT = {"top5": 3.0, "macro_field": 2.0, "custom": 2.0, "working_papers": 1.5,
               "preprints": 1.0}


def _get(path: str, params: dict) -> dict:
    import requests
    params = dict(params, mailto=MAILTO)
    r = requests.get(f"{OPENALEX}/{path}", params=params, timeout=25)
    r.raise_for_status()
    return r.json()


def resolve_journal(name: str) -> tuple[str, str] | None:
    """OpenAlex source id for a journal name (exact display-name match, cached)."""
    key = name.strip().lower()
    cache = {}
    if _CACHE.exists():
        try:
            cache = json.loads(_CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cache = {}
    if key in cache:
        return tuple(cache[key]) if cache[key] else None
    norm = lambda s: "".join(ch for ch in s.lower().removeprefix("the ") if ch.isalnum())  # noqa: E731
    found = None
    try:
        for s in _get("sources", {"search": name, "per-page": 5,
                                  "select": "id,display_name,works_count"})["results"]:
            if norm(s["display_name"]) == norm(name):
                found = (s["id"].rsplit("/", 1)[-1], s["display_name"])
                break
    except Exception as e:  # network errors are non-fatal
        print(f"  [journals] could not resolve '{name}': {e}")
        return None
    cache[key] = list(found) if found else None
    try:
        _CACHE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except OSError:
        pass
    if not found:
        print(f"  [journals] '{name}' not found in OpenAlex (use its exact title)")
    return found


def venue_map(scopes=DEFAULT_SCOPES, extra_journals=()) -> dict[str, tuple[str, str]]:
    """{source_id: (tier, display name)} for the selected scopes + extra journals."""
    out = {}
    for scope in scopes:
        for sid, name in VENUES.get(scope, {}).items():
            out[sid] = (scope, name)
    for name in extra_journals or ():
        res = resolve_journal(name)
        if res:
            out.setdefault(res[0], ("custom", res[1]))
    return out


def _abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    words = sorted((pos, w) for w, ps in inv.items() for pos in ps)
    return " ".join(w for _, w in words)


def search_journals(query: str, scopes=DEFAULT_SCOPES, extra_journals=(), max_results=25,
                    year_from: int | None = None) -> list[dict]:
    """Works matching `query` with a version in the selected venues, ranked by
    venue tier, citations and recency. Returns seed-paper-shaped dicts."""
    venues = venue_map(scopes, extra_journals)
    if not venues:
        return []
    filters = ["locations.source.id:" + "|".join(venues)]
    if year_from:
        filters.append(f"publication_year:>{year_from - 1}")
    print(f"  [journals] '{query[:60]}' in {len(venues)} venues ({', '.join(scopes)})...")
    try:
        data = _get("works", {
            "search": query, "filter": ",".join(filters), "per-page": min(50, max_results * 2),
            "select": "id,title,authorships,publication_year,cited_by_count,doi,"
                      "abstract_inverted_index,locations,best_oa_location",
        })
    except Exception as e:
        print(f"  [journals] search failed: {e}")
        return []

    papers, seen = [], set()
    for w in data.get("results", []):
        title = (w.get("title") or "").strip()
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        hits = [venues[sid] for loc in w.get("locations") or []
                if (sid := ((loc.get("source") or {}).get("id") or "").rsplit("/", 1)[-1]) in venues]
        if not hits:
            continue
        tier, venue = max(hits, key=lambda h: TIER_WEIGHT[h[0]])
        authors = [(a.get("author") or {}).get("display_name", "") for a in w.get("authorships") or []]
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        papers.append({
            "title": title,
            "authors": ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else ""),
            "year": w.get("publication_year"),
            "venue": venue,
            "venue_tier": tier,
            "citationCount": w.get("cited_by_count") or 0,
            "abstract": _abstract(w.get("abstract_inverted_index")),
            "doi": doi,
            "url": w.get("doi") or w.get("id"),
            "openAccessPdf": {"url": (w.get("best_oa_location") or {}).get("pdf_url") or ""},
            "source": "openalex_journals",
        })

    import math
    def rank(p):
        age = max(1, 2027 - (p["year"] or 2000))
        return TIER_WEIGHT[p["venue_tier"]] * math.log1p(p["citationCount"]) + 3.0 / age
    papers.sort(key=rank, reverse=True)
    print(f"  [journals] {len(papers)} papers "
          f"({sum(p['venue_tier'] == 'top5' for p in papers)} top-5)")
    return papers[:max_results]


def scopes_from_state(state: dict) -> tuple[tuple[str, ...], list[str]]:
    cfg = state.get("config", {})
    scopes = tuple(s.strip() for s in (cfg.get("lit_scope") or ",".join(DEFAULT_SCOPES)).split(",")
                   if s.strip() in VENUES)
    extra = [j.strip() for j in (cfg.get("journals") or "").split(";") if j.strip()]
    return scopes or DEFAULT_SCOPES, extra
