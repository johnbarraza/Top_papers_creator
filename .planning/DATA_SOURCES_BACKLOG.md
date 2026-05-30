# Data-Source Integration Backlog

Peru-focused repos to **review and possibly wire into Stage 1 discovery**, same
pattern as [INEI_INTEGRATION.md](INEI_INTEGRATION.md) and
[BCRP_INTEGRATION.md](BCRP_INTEGRATION.md) (`_search_*` in `stage1_discovery.py`
+ `_try_download_*` in `stage1_5_data_loading.py`, gated by `_is_peru_topic`).

Added 2026-05-30.

## Status
- ✅ **#2 Oncological-Diseases (FISSAL)** — integrated 2026-05-30 as a **Peru
  replication package** (seed paper). `_search_peru_replication_packages` →
  `_candidate_to_seed_paper`. Surfaces for health/oncology Peru topics; carries
  the FISSAL datosabiertos data link. (No auto CSV download — DKAN serves the
  resource behind JS; data_url is for manual/agent retrieval.)
- ✅ **#4 metalurgica-data (MINEM)** — integrated 2026-05-30 as a **curated data
  source** AND a replication package. `_search_minem` + `_try_download_minem`
  merge the 5 yearly CSVs → `data/external/minem/minem_produccion_metalica_peru.csv`
  (~47k rows × 16 cols, 2021-2025). High-confidence, tier-0 ranking.
- ⏳ **#1 geoidep**, **#3 Consulta-Amigable-MEF** — still pending review.

Integration points (both): `_count_quality_candidates_for_variant` Peru block;
`minem` added to `_likely_quality` + tier-0 ranking + download dispatch in
`_validate_path_a_candidates` (and the Stage 1.5 loop).

---

## 1. ambarja/geoidep
<https://github.com/ambarja/geoidep> · R · ★15 · updated 2026-03

- **What:** R package to download geographic/spatial layers from Peru's IDE
  (Infraestructura de Datos Espaciales — geoidep.gob.pe). Boundaries,
  cartography, thematic layers by `ubigeo`.
- **Unlocks:** spatial data for geo/regional econ papers (district/province
  boundaries, distance/treatment-geography designs).
- **Integration:** R, not Python → either port the catalog/URLs to a Python
  `_search_geoidep`, or call the underlying OGC/WFS endpoints directly. Likely
  GeoPackage/shapefile output — needs `geopandas`, not the CSV/.dta flow.
- **Effort:** Medium-High (geospatial formats + R→Python). **Keywords:**
  ubigeo, distrito, provincia, spatial, geográfico, mapa, cartografía.

## 2. haroldeustaquio/Analysis-of-Oncological-Diseases-in-Peru
<https://github.com/haroldeustaquio/Analysis-of-Oncological-Diseases-in-Peru> · R · ★8 · updated 2024-11

- **What:** Analysis (not a package) of the 7 most frequent cancers (2022)
  using **FISSAL** open data. Dashboard + SQL.
- **Unlocks:** the **FISSAL** open health dataset pointer (oncology consultations
  by department/age/sex/insurance) — a curated `datosabiertos`-style source.
- **Integration:** Low — add FISSAL CSV(s) to `_DATOSABIERTOS_CURATED`
  (health keywords). The repo's value is the data pointer + variable layout,
  not reusable code.
- **Effort:** Low. **Keywords:** cáncer, oncología, salud, fissal.

## 3. AlexEvanan/Web-Scraping-Consulta-Amigable-MEF
<https://github.com/AlexEvanan/Web-Scraping-Consulta-Amigable-MEF> · Python/Selenium · ★12 · updated 2025-11

- **What:** Selenium scraper for MEF **Consulta Amigable** — Peru public budget
  execution (presupuesto/gasto público) by year/sector/region/program.
- **Unlocks:** fiscal/budget panels — strong for public-spending impact papers
  (DiD on budget shocks, program rollouts).
- **Integration:** Highest-value but Selenium = heavy/brittle dependency. Prefer
  porting to the MEF SIAF/Consulta Amigable backend API if one exists; else
  gate a Selenium path behind an optional install.
- **Effort:** Medium (rework scraper → API). **Keywords:** presupuesto, gasto
  público, MEF, SIAF, consulta amigable, inversión pública.

## 4. elqvixote/metalurgica-data
<https://github.com/elqvixote/metalurgica-data> · Python · ★11 · updated 2026-05

- **What:** Open DB of metallurgical/mining processes (flotation, process
  control) + official **MINEM** Peruvian mining production 2021–2025. Synthetic
  + official datasets.
- **Unlocks:** MINEM mining production data; niche process-control datasets.
- **Integration:** Low-Medium — direct CSV/GitHub-raw download. MINEM
  production → curated source; synthetic process data less relevant (causal
  ID needs observational data).
- **Effort:** Low. **Keywords:** minería, MINEM, metalurgia, producción minera,
  flotación.

---

# Spatial / satellite data — FUTURE DIRECTION

> **Goal (user, 2026-05-30):** be able to pull spatial data from **Google Earth
> Engine / satellite** and **maps (Google Maps / OSM)** for geo-causal designs
> (RDD on borders/buffers, distance-to-X, deforestation, land cover). The repos
> below are the seeds for that capability. None integrated yet.

## 5. Daf1807/Spatial_Analysis_of_Peru_Protected_Areas
<https://github.com/Daf1807/Spatial_Analysis_of_Peru_Protected_Areas> · Python/Jupyter · ★1 · updated 2025-07

- **What:** Tree-cover analysis of Peru's protected areas using **MODIS VCF**
  satellite rasters (2024) + **OSM** protected-area polygons; **RDD** on buffer
  zones around park boundaries. Ships `areas_protegidas_solo_peru.gpkg`,
  `estadisticas_buffers_forest_cover.csv`, MODIS download/convert scripts
  (`py/download_modis_lads.py`, `convert_hdf_to_tif.py`), EPSG:4326 reproject.
- **Unlocks:** satellite forest/land-cover + a worked **geo-RDD** template
  (boundary buffers) — strong causal design. The MODIS LAADS download script is
  the reusable core for an Earth-data fetcher.
- **Integration:** Medium-High — needs `rasterio`/`geopandas`, NASA Earthdata
  `.netrc` auth (a `py/.netrc` placeholder is in the repo — **do not** copy
  secrets). Output is `.gpkg`/raster, not the CSV/.dta flow.
- **Effort:** Med-High. **Keywords:** forest, deforestación, área protegida,
  MODIS, satellite, land cover, RDD frontera, buffer.

## 6. anzonyquispe/Forest_Peru
<https://github.com/anzonyquispe/Forest_Peru> · Python/Jupyter · ★0 · updated 2026-05

- **What:** Spatial identification at **district/municipality** level for Peru.
  Carries a distrital **panel 2018–2022** (`base_distrital_2018_2022_*.csv/.xlsx`)
  joining electoral results, candidates, turnover, and `denuncias` (criminality).
- **Unlocks:** a ready district-level political-economy panel (forest × elections
  × crime) keyed by `ubigeo` — mergeable with INEI/MINEM/geoidep layers.
- **Integration:** Low-Medium — the xlsx/csv are directly downloadable from
  GitHub raw; register as a curated source and/or replication package.
- **Effort:** Low-Med. **Keywords:** distrital, municipal, ubigeo, electoral,
  denuncias, deforestation, turnover.

## 7. cablate/mcp-google-map
<https://github.com/cablate/mcp-google-map> · TypeScript · ★319 · updated 2026-04

- **What:** **MCP server** for the Google Maps API — geocoding, Places,
  directions, distance matrix, geospatial helpers (LLM-ready).
- **Unlocks:** the "data espacial de maps" goal — geocode place names → lat/lon,
  distance/travel-time covariates, place lookups, directly from agent tools.
- **Integration:** Standalone MCP (Node/TS) — register with Claude Code like the
  LAB11 BCRP MCP, **not** a Stage-1 Python searcher. Needs a `GOOGLE_MAPS_API_KEY`
  (billed). Best as an agent tool for geocoding/enrichment, not bulk discovery.
- **Effort:** Low to stand up (MCP), but requires a paid Google Maps key.
  **Keywords:** geocode, coordinates, distance, places, maps.

### Future-capability sketch (Earth Engine / Maps)
- **Earth Engine:** add a `_search_earthengine` / fetcher using the `earthengine-api`
  (needs a Google Cloud EE project + service-account auth) or, lighter, the
  **MODIS LAADS** / **Microsoft Planetary Computer (STAC)** / **Sentinel** open
  endpoints (no GEE account) — reuse #5's download script as the seed.
- **Maps/geocoding:** wire #7 (or OSM **Nominatim**, free) as an enrichment MCP
  to attach coordinates/distance covariates to `ubigeo`-keyed panels.
- **Common output:** GeoPackage/GeoTIFF → needs `geopandas`/`rasterio` in the
  pipeline; a new geo-profiling branch alongside the CSV/.dta profiler.

---

## Notes
- All four are Peru sources → fit the existing `_is_peru_topic` gate.
- Easiest wins first: **#2 FISSAL** and **#4 MINEM** (curated CSV, mirror BCRP
  curated pattern). **#3 MEF** is highest analytical value but most work.
  **#1 geoidep** only matters once a spatial/geo design is in scope.
