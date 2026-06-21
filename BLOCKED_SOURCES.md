# Pipeline Data Sources — Status Audit
**Date:** 2026-06-20  
**Tested:** manual HTTP probe + `User-Agent: Mozilla/5.0 (compatible; DatosAbiertos-Lab/1.0)`

---

## FIXED ✅ (applied 2026-06-20)

| Source | Fix applied |
|--------|-------------|
| `datosabiertos_peru` | `package_search` (404/418) → `package_list` + token filter fallback (LAB11 pattern) |
| `_search_ckan` (all CKAN portals) | Added `User-Agent: Mozilla/5.0` header — avoids 418 bot-block |
| `eu_opendata` | Param `q=` → `query=` (400 → 200) |
| `alicia_concytec` | Added `verify=False` — SSL cert expired on alicia.concytec.gob.pe, endpoint alive |
| CONCYTEC DSpace | Disabled in `_PERU_DSPACE_PORTALS` — DSpace REST + OAI both 404 |
| PUCP Repositorio | Disabled in `_PERU_DSPACE_PORTALS` — OAI + REST both 404, site migrated CMS |
| `datagov_us` | Disabled — CKAN dead at catalog.data.gov (404) |
| `datos_gob_mx` | Disabled — SSLError + package_search 404 |
| PMLR (paperdl) | Removed from `ECON_RELEVANT_SOURCES` and all `econ_sources` — 15 min/search, 0 econ results |

---

## RATE-LIMITED (expected, not broken)

| Source | Error | Notes |
|--------|-------|-------|
| `semantic_scholar` | 429 | No API key → free tier limit. Set `SEMANTIC_SCHOLAR_API_KEY` env var to unlock. Pipeline falls back to OpenAlex. |
| `github` | 403 | No token → 60 req/h. Set `GITHUB_TOKEN` env var. Pipeline handles gracefully. |

---

## STILL BROKEN / TODO

| Source | Error | Root cause | TODO |
|--------|-------|------------|------|
| `datagov_us` | 404 (disabled) | CKAN API retired at catalog.data.gov | Find new endpoint (data.gov may have migrated) |
| `datos_gob_mx` | SSLError (disabled) | SSL cert on datos.gob.mx | Re-check cert; add `verify=False` if confirmed safe |
| `dbnomics` | ReadTimeout | `api.db.nomics.world/v22/search` slow or route changed | Check correct v22 route; reduce timeout |
| `faostat` | ReadTimeout | Fenix endpoint slow | Shorten timeout to 10s; skip on failure |
| `idb` | Was 404 in probe — **actually OK** | Probe tested wrong URL; `/api/3/action/package_search` = 200 | No fix needed |
| `data_gov_au` | Was 404 in probe — **actually OK** | Code already uses `/data` prefix; probe tested wrong URL | No fix needed |
| `govdata_de` | Was 404 in probe — **actually OK** | Code already uses `ckan.govdata.de`; probe tested wrong URL | No fix needed |

---

## WORKING ✓

| Source | Function |
|--------|----------|
| Harvard Dataverse | `_search_dataverse` |
| Zenodo | `_search_zenodo` |
| OpenAlex | `_search_openalex_seed_papers` |
| World Bank | `_search_worldbank` |
| OpenICPSR | `_search_openicpsr` |
| data.gov.uk | `_search_data_gov_uk` |
| open.canada.ca | `_search_open_canada` |
| dati.gov.it | `_search_dati_gov_it` |
| data.gouv.fr | `_search_data_gouv_fr` |
| Socrata | `_search_socrata` |
| UP Repositorio (OAI) | `_search_up_repository` |
| INGEMMET WFS | `_search_ingemmet` |
| INEI (curated) | `_search_inei` |
| BCRP | `_search_bcrp` |
| BCRP Research | `_search_bcrp_research` |
| datosabiertos curated | `_search_datosabiertos_curated` |
| datosabiertos_peru | `_search_datosabiertos_peru` *(fixed)* |
| paperdl (arxiv+pmc) | `_search_paperdl_seed_papers` *(PMLR removed)* |
| MINEM | `_search_minem` |
| Peru replication packages | `_search_peru_replication_packages` |
| ALICIA | `_search_alicia` *(fixed: verify=False)* |
| IDB | `_search_idb` |
| data.gov.au | `_search_data_gov_au` |
| GovData.de | `_search_govdata_de` |
| EU Open Data | `_search_eu_opendata` *(fixed: query param)* |
| DBnomics | `_search_dbnomics` *(timeout risk)* |
| FAOSTAT | `_search_faostat` *(timeout risk)* |
| PUNKU (curated) | `_search_punku` *(site down but search is curated, no network call)* |
