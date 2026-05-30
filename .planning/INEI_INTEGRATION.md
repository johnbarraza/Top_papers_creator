# INEI Microdatos Integration

**Date:** 2026-05-21  
**Package:** `inei-microdatos==0.2.3` (`pip install inei-microdatos`)  
**Repo source:** https://github.com/fiorellarmartins/inei-microdatos

---

## Why

Stage 1 (Discovery) searched Dataverse, Zenodo, GitHub, DBnomics, and 12+ open-data portals but had no access to Peruvian government microdata. The INEI portal (https://proyectos.inei.gob.pe/microdatos/) hosts 67 surveys, 5,900+ modules, and 551,000+ variables from 1994–2025 — but its ASP/AJAX interface requires 4+ clicks per module and has no public API. `inei-microdatos` solves this with a bundled catalog and programmatic download.

---

## Files Changed

| File | Type of change |
|---|---|
| `pipeline/stages/stage1_discovery.py` | Added INEI searcher, Peru topic detector, quality signal |
| `pipeline/stages/stage1_5_data_loading.py` | Added INEI downloader |

---

## Key Decisions

### 1. Catalog is `list[dict]`, not DataFrame
The `load_catalog()` returns a list of 67 survey entries. Each entry:
```python
{
    "category": "ENAHO Anterior",
    "value": "Condiciones de Vida y Pobreza - ENAHO",
    "label": "...",
    "years": {
        "2024": {
            "Anual - (Ene-Dic)": {
                "period_value": "...",
                "modules": [{"survey_code": "...", "module_code": "...", "stata_code": "..."}]
            }
        }
    }
}
```
`filter_catalog(cat, survey="enaho", year_min=2022, year_max=2022)` returns a filtered list of the same structure, with the `years` dict trimmed to matching years only.

### 2. Download limited to 5 modules in Stage 1
Full ENAHO 2024 = 64 modules. Downloading all in Stage 1 Discovery would be slow and wasteful. `_try_download_inei` deep-copies the filtered catalog and trims each period's `modules` list to a max of 5 total. This gives a representative .dta sample for profiling without blocking the pipeline for minutes.

**Audit note:** If a project needs the full survey, the user should run `download_modules()` manually or via Stage 1.5 Path B (`--data ./your_enaho.dta`).

### 3. Topic→Survey mapping (keyword-based)
```
digital / fintech / wallet / pobreza / hogar / ingreso  → ENAHO
empleo / trabajo / desempleo / salario                   → EPEN
salud / mortalidad / fecundidad                          → ENDES
agricultura / agro / cultivo / cenagro                   → CENAGRO
empresa / manufactura                                    → EEA
(no match)                                               → ENAHO (fallback)
```
This is keyword matching, not semantic search. Topics with unusual phrasing may land on the wrong survey. Auditor should verify that `stage1_discovery.md` shows the expected survey for the project topic.

### 4. `source_api: "inei"` signals in `_likely_quality()`
INEI candidates are marked high-confidence (same tier as `curated_registry` and `journal`). Rationale: they are official government surveys with known structure. This means they are prioritized in the variant-counting phase even before download validation.

### 5. Peru detection via `_is_peru_topic()`
Triggers INEI search when topic contains any of:
`peru`, `perú`, `peruana/o/s`, `enaho`, `endes`, `epen`, `cenagro`, `inei`, `eea`, `enapres`, `lima`, `arequipa`, `cusco`, `puno`, `cajamarca`, `microdata peru`

Non-Peru topics skip INEI entirely — no overhead.

### 6. Download format: STATA (.dta)
`fmt="STATA"` chosen over CSV because downstream stages use `pyreadstat`/pandas and .dta files preserve variable labels (needed for Stage 2 ideation with real variable names). CSV available as fallback if stata_code is None for older surveys.

---

## Integration Points

```
run_pipeline.py --topic "Digital Wallets in Peru"
    │
    └─ Stage 1 (_run_path_a_topic_aware)
           │
           ├─ _expand_topic_variants(topic)       [LLM generates 8 variants]
           │
           ├─ _count_quality_candidates_for_variant(variant)
           │       │
           │       └─ _search_inei(variant)       ← NEW (runs if _is_peru_topic)
           │               returns candidates with source_api="inei"
           │
           ├─ _rank_and_select_variant()           [INEI = high-confidence → boosts rank]
           │
           └─ _validate_path_a_candidates()
                   │
                   └─ _try_download_inei(c, data_dir)  ← NEW (branch for source_api="inei")
                           │
                           ├─ filter_catalog(year_min=year, year_max=year)
                           ├─ trim to 5 modules
                           ├─ download_modules(..., fmt="STATA")
                           └─ extract largest .dta → return path
```

---

## Known Limitations

- **5-module cap:** Only profiles a sample. Module ordering is arbitrary (first 5 in catalog). For ENAHO, the `Sumaria` (main aggregate) module is not guaranteed to be in the first 5.
- **No offline fallback for download:** `download_modules()` hits the INEI portal directly. If the portal is down or slow, Stage 1 will timeout and skip the INEI candidates.
- **Old surveys (pre-2004) may lack STATA codes:** `stata_code: None` → `download_modules` falls back to SPSS or CSV per the package's `fallback=True` default. The resulting file may be `.sav` instead of `.dta`, which the existing `_try_extract` won't recognize. Mitigation: only filter `year_min=2015` in `_search_inei` so only modern surveys are surfaced.
- **Encoding:** INEI data uses Windows-1252 with JS escape sequences. `inei-microdatos` handles this internally. Downstream `_profile_dataset` uses `encoding="latin-1"` fallback which covers cp1252.

---

## Future Work (not done, tracked here for audit)

- [ ] Prioritize the `Sumaria` module for ENAHO downloads (module_name contains "Sumaria")
- [ ] Add `search_variables()` integration to surface matching variable labels in Stage 2 ideation prompt
- [ ] Support Path C (data-first) for INEI: auto-scan all recent ENAHO years and rank by feasibility
- [ ] academic-research-skills citation verification (deferred — see conversation 2026-05-21)
