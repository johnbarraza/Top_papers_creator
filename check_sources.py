"""
Health-check for all pipeline data sources.
Run: python check_sources.py
Run (Peru only): python check_sources.py --peru
Run (fast HTTP-only): python check_sources.py --http
"""

import argparse
import sys
import time
import warnings
warnings.filterwarnings("ignore")  # suppress SSL InsecureRequestWarning

sys.path.insert(0, ".")

QUERY = "informalidad laboral Peru"

# ── source registry ────────────────────────────────────────────────────────────
# Each entry: (label, fn_name, import_path, kwargs)
ALL_SOURCES = [
    # International general
    ("dataverse",           "_search_dataverse",           {"max_results": 2}),
    ("zenodo",              "_search_zenodo",              {"max_results": 2}),
    ("github",              "_search_github",              {"max_results": 2}),
    ("openalex",            "_search_openalex_seed_papers",{"max_results": 2}),
    ("worldbank",           "_search_worldbank",           {"max_results": 2}),
    ("openicpsr",           "_search_openicpsr",           {"max_results": 2}),
    ("eu_opendata",         "_search_eu_opendata",         {"max_results": 2}),
    ("data_gov_uk",         "_search_data_gov_uk",         {"max_results": 2}),
    ("open_canada",         "_search_open_canada",         {"max_results": 2}),
    ("dati_gov_it",         "_search_dati_gov_it",         {"max_results": 2}),
    ("data_gouv_fr",        "_search_data_gouv_fr",        {"max_results": 2}),
    ("data_gov_au",         "_search_data_gov_au",         {"max_results": 2}),
    ("govdata_de",          "_search_govdata_de",          {"max_results": 2}),
    ("idb",                 "_search_idb",                 {"max_results": 2}),
    ("datagov_us",          "_search_datagov",             {"max_results": 2}),
    ("datos_gob_mx",        "_search_datos_gob_mx",        {"max_results": 2}),
    ("socrata",             "_search_socrata",             {"max_results": 2}),
    ("dbnomics",            "_search_dbnomics",            {"max_results": 2}),
    ("faostat",             "_search_faostat",             {"max_results": 2}),
    # Peru-specific
    ("inei",                "_search_inei",                {"max_results": 2}),
    ("bcrp",                "_search_bcrp",                {"max_results": 1}),
    ("bcrp_research",       "_search_bcrp_research",       {"max_results": 2}),
    ("minem",               "_search_minem",               {"max_results": 1}),
    ("datosabiertos_curated","_search_datosabiertos_curated",{"max_results": 2}),
    ("datosabiertos_peru",  "_search_datosabiertos_peru",  {"max_results": 2}),
    ("peru_replication",    "_search_peru_replication_packages",{"max_results": 2}),
    ("ocds",                "_search_ocds",                {"max_results": 2}),
    ("punku",               "_search_punku",               {"max_results": 1}),
    ("indecopi",            "_search_indecopi",            {"max_results": 2}),
    ("ingemmet",            "_search_ingemmet",            {"max_results": 2}),
    ("mef_consulta",        "_search_mef_consulta_amigable",{"max_results": 2}),
    ("alicia",              "_search_alicia",              {"max_results": 2}),
    ("up_repo",             "_search_up_repository",       {"max_results": 2}),
    ("concytec_repo",       None,                          {}),  # via _search_peru_dspace_repos
    ("semantic_scholar",    "_search_semantic_scholar_seed_papers", {"max_results": 2}),
    ("paperdl",             "_search_paperdl_seed_papers", {"max_results": 2}),
]

PERU_SOURCES = {
    "inei", "bcrp", "bcrp_research", "minem", "datosabiertos_curated",
    "datosabiertos_peru", "peru_replication", "ocds", "punku", "indecopi",
    "ingemmet", "mef_consulta", "alicia", "up_repo", "concytec_repo",
}

def _color(text, code):
    return f"\033[{code}m{text}\033[0m"

def ok(n):   return _color(f"OK ({n})", "32")
def warn(n): return _color(f"WARN ({n})", "33")
def fail(e): return _color(f"FAIL: {e}", "31")

def run_check(label, fn_name, kwargs, topic):
    from pipeline.stages import stage1_discovery as s1
    t0 = time.time()
    try:
        if fn_name is None:
            # Special case: CONCYTEC via _search_dspace_portal
            from pipeline.stages.stage1_discovery import _search_dspace_portal
            results = _search_dspace_portal(
                "https://repositorio.concytec.gob.pe",
                "Repositorio CONCYTEC", topic, max_results=2
            )
        else:
            fn = getattr(s1, fn_name)
            results = fn(topic, **kwargs)
        elapsed = time.time() - t0
        n = len(results)
        if n == 0:
            return warn(0), elapsed
        return ok(n), elapsed
    except Exception as e:
        elapsed = time.time() - t0
        return fail(str(e)[:60]), elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--peru", action="store_true", help="Only Peru sources")
    parser.add_argument("--http", action="store_true", help="HTTP probe only (no full search)")
    args = parser.parse_args()

    sources = ALL_SOURCES
    if args.peru:
        sources = [(l, f, k) for l, f, k in ALL_SOURCES if l in PERU_SOURCES]

    if args.http:
        _run_http_probe(sources)
        return

    print(f"\nPipeline source health-check — query: '{QUERY}'")
    print("=" * 60)

    results_log = []
    for label, fn_name, kwargs in sources:
        sys.stdout.write(f"  {label:<25} ... ")
        sys.stdout.flush()
        status, elapsed = run_check(label, fn_name, kwargs, QUERY)
        print(f"{status}  ({elapsed:.1f}s)")
        results_log.append((label, status, elapsed))

    print("=" * 60)
    ok_count   = sum(1 for _, s, _ in results_log if "OK"   in s)
    warn_count = sum(1 for _, s, _ in results_log if "WARN" in s)
    fail_count = sum(1 for _, s, _ in results_log if "FAIL" in s)
    total_t    = sum(e for _, _, e in results_log)
    print(f"  OK={ok_count}  WARN(0 results)={warn_count}  FAIL={fail_count}  total={total_t:.0f}s")


def _run_http_probe(sources):
    """Quick HTTP probe without importing pipeline — tests raw API reachability."""
    import requests

    PROBE_URLS = {
        "dataverse":       "https://dataverse.harvard.edu/api/search?q=peru&type=dataset&per_page=1",
        "zenodo":          "https://zenodo.org/api/records?q=peru&type=dataset&size=1",
        "github":          "https://api.github.com/search/repositories?q=peru+replication&per_page=1",
        "openalex":        "https://api.openalex.org/works?search=peru&per-page=1&mailto=test@test.com",
        "worldbank":       "https://search.worldbank.org/api/v2/wds?format=json&qterm=peru&rows=1",
        "openicpsr":       "https://www.openicpsr.org/openicpsr/search/studies?q=peru&start=0&RESTRICTED=false",
        "eu_opendata":     "https://data.europa.eu/api/hub/search/search?query=employment&limit=1",
        "data_gov_uk":     "https://data.gov.uk/api/3/action/package_search?q=employment&rows=1",
        "open_canada":     "https://open.canada.ca/data/api/3/action/package_search?q=labour&rows=1",
        "dati_gov_it":     "https://www.dati.gov.it/opendata/api/3/action/package_search?q=lavoro&rows=1",
        "data_gouv_fr":    "https://www.data.gouv.fr/api/1/datasets/?q=emploi&page_size=1",
        "data_gov_au":     "https://data.gov.au/data/api/3/action/package_search?q=employment&rows=1",
        "govdata_de":      "https://ckan.govdata.de/api/3/action/package_search?q=arbeit&rows=1",
        "idb":             "https://data.iadb.org/api/3/action/package_search?q=peru&rows=1",
        "datagov_us":      "https://catalog.data.gov/api/3/action/package_search?q=employment&rows=1",
        "socrata":         "https://api.us.socrata.com/api/catalog/v1?q=employment&limit=1",
        "dbnomics":        "https://api.db.nomics.world/v22/search?q=peru&limit=1",
        "inei":            "https://iinei.inei.gob.pe/microdatos/",
        "bcrp_research":   "https://www.bcrp.gob.pe/docs/Publicaciones/Documentos-de-Trabajo/",
        "datosabiertos":   "https://www.datosabiertos.gob.pe/api/3/action/package_list",
        "alicia":          "https://alicia.concytec.gob.pe/vufind/api/v1/search?q=peru&limit=1",
        "up_repo":         "https://repositorio.up.edu.pe/oai/request?verb=Identify",
        "concytec_repo":   "https://repositorio.concytec.gob.pe/server/api/discover/search/objects?query=peru&size=1",
        "semantic_scholar":"https://api.semanticscholar.org/graph/v1/paper/search?query=peru&limit=1&fields=title",
        "ingemmet":        "https://geocatmin.ingemmet.gob.pe/arcgis/rest/services/SERV_UNIDADES_MINERAS/MapServer/0/query?where=1%3D1&f=json&resultRecordCount=1",
    }

    H = {"User-Agent": "Mozilla/5.0 (compatible; DatosAbiertos-Lab/1.0)", "Accept": "application/json"}
    print(f"\nHTTP probe — {len(PROBE_URLS)} endpoints")
    print("=" * 60)
    ok_n = fail_n = 0
    for name, url in PROBE_URLS.items():
        try:
            r = requests.get(url, headers=H, timeout=8, verify=False)
            s = r.status_code
            status = _color(f"OK ({s})", "32") if s == 200 else _color(f"BLOCKED ({s})", "31")
            if s == 200: ok_n += 1
            else: fail_n += 1
        except Exception as e:
            status = _color(f"ERROR ({type(e).__name__})", "31")
            fail_n += 1
        print(f"  {name:<25} {status}")
    print("=" * 60)
    print(f"  OK={ok_n}  FAIL/BLOCKED={fail_n}")


if __name__ == "__main__":
    main()
