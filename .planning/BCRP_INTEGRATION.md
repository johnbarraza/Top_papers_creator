# BCRP + Datos Abiertos (Peru) Integration

**Date:** 2026-05-30
**Source:** [d2cml-ai/Data-Science-Python — LAB11](https://github.com/d2cml-ai/Data-Science-Python/tree/main/Labs/Python_Notebooks/LAB11)
**Packages:** none — `requests` + `pandas` only (no API key, no extra install)

---

## Why

Stage 1 (Discovery) already pulls Peru government **microdata** via INEI (see
[INEI_INTEGRATION.md](INEI_INTEGRATION.md)) but had no access to:

- **BCRP** (Banco Central de Reserva del Perú) — macro **monthly time series**
  (inflation, exchange rate, GDP, policy rate, trade balance). Ideal as
  outcomes/controls for macro, monetary, and trade papers.
- **Datos Abiertos Perú** (datosabiertos.gob.pe) — the national open-data portal.
  A generic CKAN searcher existed (`_search_datosabiertos_peru`) but the portal
  rarely loads resources into its DataStore, so `package_search` almost never
  returned a parseable `download_url`. Health/education datasets were therefore
  effectively unreachable.

LAB11 solves both with a BCRP REST feed and a curated CSV catalog. This
integration ports that capability into the Stage 1 / 1.5 discovery flow,
mirroring the existing INEI pattern.

---

## Files Changed

| File | Change |
|---|---|
| `pipeline/stages/stage1_discovery.py` | Added `_search_bcrp`, `_search_datosabiertos_curated`; wired both into `_count_quality_candidates_for_variant` (Peru block); marked `bcrp` + `datosabiertos_curated` high-confidence in `_likely_quality`; tier-0 ranking + download dispatch in `_validate_path_a_candidates` |
| `pipeline/stages/stage1_5_data_loading.py` | Added `_try_download_bcrp`, `_try_download_datosabiertos`; wired both into the Stage 1.5 download dispatch |

No new dependency. No change to downstream stages — BCRP/DatosAbiertos
candidates flow through the same `data_sources` shape as every other source.

---

## How it works

```
run_pipeline.py --topic "Inflation and monetary policy in Peru"
    │
    └─ Stage 1 (_run_path_a_topic_aware)
           │
           ├─ _expand_topic_variants(topic)
           │
           ├─ _count_quality_candidates_for_variant(variant)
           │       └─ if _is_peru_topic(variant):
           │              _search_inei                ← microdata
           │              _search_bcrp                ← NEW: macro panel
           │              _search_datosabiertos_curated ← NEW: curated CSVs
           │              _search_datosabiertos_peru   ← CKAN search
           │
           └─ _validate_path_a_candidates()
                   └─ dispatch by source_api:
                          "bcrp"                 → _try_download_bcrp        ← NEW
                          "datosabiertos_*"      → _try_download_datosabiertos ← NEW
                          "inei"                 → _try_download_inei
```

Peru official sources (`inei`, `bcrp`, `datosabiertos_curated`) are tried
first (rank tier 0) so they are not crowded out by high-ceiling international
replication archives.

---

## BCRP

### Verified monthly series codes

| Indicator | Code | Notes |
|---|---|---|
| Inflation (IPC Lima) | `PN01271PM` | Monthly % variation |
| Exchange rate | `PN01234PM` | Monthly average S/ per USD |
| GDP | `PN01773AM` | Seasonally adjusted index, base 2007 |
| Interest rate | `PN07819NM` | BCRP reference (policy) rate |
| Trade balance | `PN01781AM` | Accumulated exports, millions USD |

> **Dropped:** `reserves` (`PN01265GM` from the LAB11 README) returns **403**
> from the live API and is excluded. The other five are confirmed working.

### Download behavior

`_try_download_bcrp` always fetches **all five** series (regardless of which
keywords matched) and merges them by month into one wide panel:

```
period, year, month, inflation, exchange_rate, gdp, interest_rate, trade_balance
```

- **Span:** `2004-01` → current month (~268 rows) — guarantees the panel clears
  the Stage-1 gate (≥ 200 rows, ≥ 5 cols).
- **Output:** `data/external/bcrp/bcrp_macro_peru.csv`
- Months are parsed from BCRP's Spanish labels (`Ene.2024` … `Dic.2024`; note
  **`Set` = September**, not `Sep`) into `year`/`month` for sorting.
- A `User-Agent` header is sent; missing values (`n.d.` / empty) become `NaN`.

API base: `https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{code}/json/{start}/{end}`

---

## Datos Abiertos Perú

### Curated catalog (directly downloadable)

| Key | File | Encoding |
|---|---|---|
| health | `IPRESS.csv` (MINSA — establecimientos de salud / RENIPRESS) | latin-1 |
| education | `Matriculados_2016_al_2022.csv` (MINEDU — matrícula escolar) | utf-8 |

`_search_datosabiertos_curated` matches these by keyword (salud/health,
educación/education, …). `_try_download_datosabiertos` downloads the direct
CSV (`download_url`), falling back to the CKAN **DataStore API**
(`datastore_search?resource_id=…`) when only a `resource_id` is known.

- **Output:** `data/external/datosabiertos/<file>.csv`

---

## Topic detection

Both sources only run for Peru-related topics, reusing the existing
`_is_peru_topic()` gate (`peru`, `lima`, `enaho`, `bcrp`-adjacent keywords,
etc.). Non-Peru topics skip them entirely — no overhead.

---

## Known Limitations

- **BCRP reserves series unavailable** — `PN01265GM` 403s; net international
  reserves are not included. If a valid code is found, add it to `_BCRP_SERIES`.
- **BCRP fiscal/transfer series restricted** — All codes in the `02xxx` range
  (canon minero, transferencias, regalías) return HTTP 403 from the public API.
  These require authenticated access. For canon/transfer data, use **MEF Consulta
  Amigable** (manual download) or the curated MEF reference in Stage 1.
- **GDP/trade lag** — the most recent 1–2 months are often `NaN` (data not yet
  published). Expected; downstream cleaning should `dropna`/forward-handle.
- **Curated catalog is static** — only health + education are wired. Extend
  `_DATOSABIERTOS_CURATED` (mirrors LAB11 `catalog_curated.py`) for more.
- **No retry/backoff** — a single failed series is skipped with a log line; the
  panel proceeds with the remaining columns.
- **BCRP rate limiting** — bulk runs may intermittently 403; the `User-Agent`
  header mitigates but does not eliminate this.

---

## Future Work (tracked for audit)

- [ ] Find a working monthly net-international-reserves code to restore `reserves`.
- [ ] Surface the matched `primary` indicators in the Stage 2 ideation prompt
      (the candidate already carries `primary`).
- [ ] Merge BCRP macro series onto INEI/ENAHO panels by `year`/`month` as a
      ready-made macro-control join in Stage 4.
- [ ] Expand `_DATOSABIERTOS_CURATED` beyond health + education.
