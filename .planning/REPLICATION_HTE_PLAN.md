# Plan corregido: modo replicacion + HTE en el pipeline existente

**Fecha:** 2026-05-25  
**Autor:** JohnxBar  
**Estado:** Plan auditado y corregido contra el codigo real del repo.

---

## 0. Resumen ejecutivo

El objetivo sigue siendo correcto: permitir que el usuario, despues de Stage 1, elija entre generar ideas nuevas o replicar/extender un paper existente con metodos HTE como DML, Causal Forest y Causal Tree.

La version anterior del plan tenia tres problemas de contrato:

1. Stage 1 no guarda `seed_papers`; solo guarda datasets en `recommended_data_sources` y `stage1_5.downloaded_datasets`.
2. Stage 2.5 y Stage 3 no leen `ideas` ni `extension_angles`; esperan `top_ideas` con el schema actual.
3. Stage 4 no esta preparado para scripts `1_load.py`, `2_clean.py`, etc.; el executor y validators esperan el contrato `00_clean.py`, `01_main.py`, `02_robustness.py`, `03_output.py`.

Este plan corrige esos puntos y convierte el modo replicacion en una extension compatible con el pipeline actual.

---

## 1. Resultado deseado

Ejemplo:

```powershell
python run_pipeline.py --topic "informalidad en Peru" --mode replicate
```

Flujo esperado:

1. Stage 1 busca datasets como hoy, pero ademas guarda candidatos de papers/replication packages en `state["stages"]["stage1"]["seed_papers"]`.
2. Stage 2, en modo `replication`, muestra papers candidatos, el usuario elige uno, y el LLM genera 5-8 angulos de extension.
3. Esos angulos se guardan como `top_ideas`, usando el mismo schema que Stage 2.5/Stage 3 ya entienden.
4. Stage 2.5 permite seleccionar un angulo HTE sin romper el checkpoint humano actual.
5. Stage 3 valida factibilidad de replicacion/extension, no solo novedad.
6. Stage 4 genera scripts bajo el contrato actual de cuatro archivos, con contenido HTE dentro de esos archivos.

---

## 2. Principios de diseno

### 2.1 Mantener el pipeline actual

No crear un Path D completo. El modo replicacion vive dentro del Path A/B existente y solo cambia la semantica de Stage 2 en adelante.

### 2.2 Mantener schemas downstream

El pipeline ya tiene contratos implicitos:

```python
state["stages"]["stage2"]["top_ideas"]        # lista de ideas
state["stages"]["stage2_5"]["selected_idea"]  # una idea seleccionada
state["stages"]["stage3"]["result"]           # validacion
```

El modo replicacion debe producir esos mismos campos. Puede agregar metadata extra, pero no reemplazar las claves existentes.

### 2.3 Evitar input obligatorio en ejecucion no interactiva

Agregar `--mode {new,replicate,ask}` en `run_pipeline.py`.

- `--mode new`: comportamiento actual.
- `--mode replicate`: entra directo a modo replicacion.
- `--mode ask`: pregunta solo si `stdin` es interactivo.

Default recomendado: `ask` si hay TTY, `new` si no hay TTY.

---

## 3. Contratos de estado

### 3.1 Stage 1: nuevo campo `seed_papers`

Agregar a `state["stages"]["stage1"]`:

```python
"seed_papers": [
    {
        "title": "...",
        "authors": "...",
        "year": 2022,
        "venue": "...",
        "abstract": "...",
        "citationCount": 42,
        "url": "...",
        "openAccessPdf": {"url": "..."},
        "source": "semantic_scholar|github|journal|dataverse",
        "replication_package_url": "...",
        "dataset_candidate": {...}
    }
]
```

Reglas:

- `seed_papers` puede estar vacio, pero siempre debe existir en Path A.
- Si un resultado viene de GitHub/Dataverse y no tiene paper asociado, crear un candidato con `source="replication_package"` y usar `name`, `url`, `description`.
- Si Semantic Scholar falla, Stage 1 no falla; guarda `seed_papers=[]`.

### 3.2 Stage 2: modo replicacion compatible

Guardar:

```python
state["stages"]["stage2"] = {
    "status": "completed",
    "mode": "replication",
    "chosen_paper": {...},
    "paper_content": {
        "source": "pdf|abstract|metadata|local_pdf",
        "text_excerpt": "...",
        "local_path": "..."
    },
    "top_ideas": [
        {
            "rank": 1,
            "title": "[HTE-DML] ...",
            "research_question": "...",
            "method": "Double/debiased machine learning with cross-fitting",
            "identification_level": "A|B|C",
            "identification_source": "...",
            "sub_topic": "replication_hte",
            "data_sources": ["..."],
            "novelty": 3,
            "feasibility": 4,
            "impact": 4,
            "identification": 4,
            "expected_effect": 3,
            "total_score": 3.6,
            "pitch": "...",
            "first_experiment": "Replicate original ATE before estimating CATE.",
            "replication": {
                "base_paper_title": "...",
                "extension_type": "REPLICATE|HTE-DML|HTE-CF|HTE-CT|EXTEND-T|EXTEND-Y|EXTEND-X",
                "original_estimand": "...",
                "replication_target": "...",
                "hte_variables": ["..."]
            }
        }
    ],
    "output_file": "...",
    "completed_at": "..."
}
```

No usar `ideas` como clave primaria. Si se quiere compatibilidad adicional, puede duplicarse:

```python
state["stages"]["stage2"]["extension_angles"] = state["stages"]["stage2"]["top_ideas"]
```

---

## 4. Cambios por archivo

### 4.1 `run_pipeline.py`

Agregar argumento:

```python
parser.add_argument(
    "--mode",
    choices=["new", "replicate", "ask"],
    default="ask",
    help="Stage 2 mode: new ideas, replication/HTE, or ask interactively.",
)
```

Pasar el valor a `state` antes de Stage 2:

```python
state.setdefault("config", {})["stage2_mode"] = args.mode
```

Motivo: evita que `stage2_ideation.py` dependa siempre de `input()`, y permite reproducir corridas desde CLI.

### 4.2 `pipeline/stages/stage1_discovery.py`

Agregar busqueda liviana de papers:

```python
def _search_semantic_scholar_seed_papers(topic: str, max_results: int = 10) -> list[dict]:
    ...
```

Campos Semantic Scholar requeridos:

```text
title,authors,year,venue,citationCount,abstract,url,openAccessPdf,externalIds
```

No reutilizar `_search_semantic_scholar()` de Stage 3 porque trunca abstracts a 200 caracteres y no pide `openAccessPdf`.

En Path A topic-aware:

1. Buscar papers por `selected["variant"]` y por `topic`.
2. Convertir candidatos GitHub/journal/Dataverse relevantes en `seed_papers` si parecen replication packages.
3. Persistir `seed_papers` en `stage1_discovery.md` y en `state["stages"]["stage1"]`.

### 4.3 `pipeline/stages/stage2_ideation.py`

Refactor necesario:

```python
def run(project_dir: Path, state: dict) -> dict:
    mode = _resolve_stage2_mode(state)
    if mode == "replication":
        return _run_replication_mode(project_dir, state)
    return _run_ideation_normal(project_dir, state)
```

`_run_ideation_normal()` debe contener el cuerpo actual de `run()` sin cambios funcionales.

Funciones nuevas:

```python
def _resolve_stage2_mode(state: dict) -> str:
    """Return 'normal' or 'replication'."""
```

Reglas:

- `state["config"]["stage2_mode"] == "new"` -> `"normal"`.
- `state["config"]["stage2_mode"] == "replicate"` -> `"replication"`.
- `ask` + TTY -> preguntar.
- `ask` + no TTY -> `"normal"`.

```python
def _collect_replication_candidates(project_dir: Path, state: dict) -> list[dict]:
    """Merge Stage 1 seed_papers, replication packages, and extra S2 search."""
```

Fuentes:

- `state["stages"]["stage1"]["seed_papers"]`
- `state["stages"]["stage1"]["recommended_data_sources"]` si `source_api` es `github`, `journal`, `dataverse`
- busqueda Semantic Scholar adicional con campos completos

```python
def _fetch_paper_content(paper: dict, project_dir: Path) -> dict:
    """Fetch OA PDF when possible; otherwise use full abstract/metadata."""
```

Fallbacks:

1. `openAccessPdf.url` -> descargar a `project_dir / "papers"`.
2. `url` libre -> guardar URL y metadata; no prometer WebFetch automatico si no existe integracion.
3. abstract completo.
4. metadata minima.

```python
def _generate_replication_top_ideas(paper_content: dict, state: dict) -> list[dict]:
    """Return top_ideas compatible with Stage 2.5 and Stage 3."""
```

El prompt debe exigir JSON con `top_ideas`, no `angles`.

### 4.4 `pipeline/stages/stage2_5_selection.py`

Cambio minimo recomendado: no crear `_run_selection_replication()` si no es necesario.

Como el modo R ya produce `top_ideas` con el schema actual, `idea_selection(top_ideas)` puede seguir funcionando. Solo ajustar display si `mode == "replication"` para que sea mas claro.

Opciones:

1. Simple: no tocar Stage 2.5 en Fase 1.
2. Mejor: pasar `mode` a un helper de display o agregar tags en `_print_idea()`.

Si se toca, mantener `SELECT`, `COMBINE`, `REJECT ALL` intactos.

### 4.5 `pipeline/human_checkpoint.py`

Agregar DML/HTE a clasificacion:

```python
CAUSAL_METHODS.update({
    "debiased machine learning",
    "double machine learning",
    "doubleml",
    "dml",
    "causal forest",
    "generalized random forest",
    "grf",
    "causal tree",
    "cate",
    "heterogeneous treatment",
})
```

Agregar template de display para HTE en `_design_template_for_method()`:

- Modelo: ATE/CATE con nuisance models y cross-fitting.
- Pasos: replicar ATE original, definir tratamiento/outcome/controles, correr DML, estimar CATE, validar overlap/calibration.
- Tests: overlap, balance, sensibilidad de learners, honest splitting/cross-fitting, comparacion ATE vs paper original.

### 4.6 `pipeline/templates/__init__.py`

Agregar design type:

```python
"hte": {
    "name": "Replication + heterogeneous treatment effects",
    "scripts": [
        "hte_00_clean.py",
        "hte_01_main.py",
        "hte_02_robustness.py",
        "hte_03_output.py",
    ],
    "variables": [...]
}
```

Actualizar `detect_design()`:

```python
if any(k in method for k in ["dml", "double machine", "causal forest", "grf", "causal tree", "cate", "heterogeneous"]):
    return "hte"
```

Importante: los templates nuevos deben generar los nombres esperados por Stage 4:

- `00_clean.py`
- `01_main.py`
- `02_robustness.py`
- `03_output.py`

No usar `1_load.py`, `2_clean.py`, etc. a menos que se cambie tambien el executor.

### 4.7 `pipeline/stages/stage3_validation.py`

Agregar contexto si `stage2.mode == "replication"`:

```text
This is a replication/extension proposal.
Evaluate:
1. Is the original paper clearly identified?
2. Is the original estimand recoverable with available data?
3. Is the HTE extension a valid extension rather than a disconnected new paper?
4. Does the plan replicate the baseline ATE before CATE?
5. Are overlap, sample size, and treatment variation sufficient for HTE?
```

Tambien incluir `chosen_paper` en `idea_text`.

### 4.8 `pipeline/stages/stage3_3_quick_test.py`

Agregar disponibilidad de HTE:

```python
try:
    import econml
    available_estimators["econml"] = True
except Exception:
    available_estimators["econml"] = False

try:
    import sklearn
    available_estimators["sklearn"] = True
except Exception:
    available_estimators["sklearn"] = False
```

Agregar checks minimos para `design == "hte"`:

- tratamiento con al menos 2 grupos;
- outcome no mayormente missing;
- n total suficiente para cross-fitting;
- al menos 5-10 covariables candidatas si se promete CATE;
- overlap basico: propensity no colapsa a 0/1;
- clusters suficientes si hay inferencia clusterizada.

### 4.9 `pipeline/stages/stage4_strategy.py`

Agregar keywords HTE a `tier1_keywords`, pero no usar `"replication"` como pase automatico.

Correcto:

```python
"debiased machine learning", "double machine learning", "double ml",
"doubleml", "dml", "causal forest", "causal_forest",
"generalized random forest", "grf", "causal tree",
"heterogeneous treatment", "cate", "honest tree",
"partially linear"
```

No correcto:

```python
"replication", "replicate"
```

Razon: replicar un paper puede ser excelente, pero la palabra "replication" no garantiza identificacion causal. Debe pasar por el metodo concreto y por la validacion Stage 3/3.3.

### 4.10 `pipeline/stages/stage4_code.py`

No cambiar el executor en Fase 1.

Para modo HTE, usar el contrato actual:

```text
00_clean.py       - carga datos, reproduce sample restrictions del paper, construye Y/D/X
01_main.py        - replica ATE original y estima DML/CATE principal
02_robustness.py  - learners alternativos, overlap, placebo, sample restrictions
03_output.py      - tablas/figuras: ATE replication, DML ATE, CATE summaries, tree splits
```

Agregar instrucciones HTE al prompt solo cuando:

```python
state["stages"]["stage2"].get("mode") == "replication"
```

Gate obligatorio:

1. `01_main.py` debe calcular el ATE de replicacion antes de HTE.
2. Si el paper reporta ATE numerico, comparar contra el target.
3. Si la diferencia absoluta relativa supera 30%, escribir warning en `results_summary.md`.
4. No bloquear automaticamente si no hay ATE reportado; marcar `replication_target_unavailable`.

---

## 5. Templates HTE propuestos

### 5.1 `hte_00_clean.py`

Responsabilidades:

- cargar dataset principal desde Stage 1/1.5;
- loggear rows iniciales;
- aplicar restricciones del paper original si son conocidas;
- construir `treatment`, `outcome`, `covariates`, `cluster`;
- guardar `data/clean/clean_data.csv`;
- guardar `data/clean/replication_sample_log.csv`;
- reportar missingness.

### 5.2 `hte_01_main.py`

Responsabilidades:

- OLS/estimator base para replicar ATE original;
- DML ATE con cross-fitting;
- CATE/Causal Forest si `econml` esta disponible;
- guardar `main_results.csv`;
- guardar `cate_estimates.csv` si aplica;
- escribir `results_summary.md`.

### 5.3 `hte_02_robustness.py`

Responsabilidades:

- learners alternativos para nuisance models;
- sensibilidad a covariates;
- overlap/propensity diagnostics;
- placebo outcome/treatment si existe;
- honest sample split si aplica;
- guardar `robustness_results.csv`.

### 5.4 `hte_03_output.py`

Responsabilidades:

- tablas LaTeX:
  - `table_1_summary.tex`
  - `table_2_replication_ate.tex`
  - `table_3_dml_hte.tex`
  - `table_4_robustness.tex`
- figuras:
  - CATE distribution;
  - top heterogeneity splits;
  - overlap plot;
  - optional map if geography exists.

---

## 6. Dependencias

No poner dependencias globales obligatorias para todo el pipeline si solo sirven a HTE.

Stage 3.3 debe detectar disponibilidad. Stage 4 debe generar `requirements.txt` del proyecto cuando use HTE:

```text
econml
scikit-learn
statsmodels
pandas
numpy
matplotlib
seaborn
```

Opcionales:

```text
geopandas
shapely
```

Regla: solo agregar `geopandas` si se genera mapa CATE. Evitar instalarlo por defecto porque suele tener friccion de entorno.

---

## 7. Datos Peru adicionales

Esto es mejora de descubrimiento, no requisito para que modo R funcione.

### 7.1 `datosabiertos.gob.pe`

Agregar CKAN searcher:

```python
def _search_datosabiertos_peru(topic: str, max_results: int = 5) -> list[dict]:
    return _search_ckan(
        api_root="https://www.datosabiertos.gob.pe",
        portal_label="datosabiertos.gob.pe",
        topic=topic,
        max_results=max_results,
        source_api="datosabiertos_peru",
    )
```

En `_count_quality_candidates_for_variant()`:

```python
if _is_peru_topic(variant):
    candidates.extend(_search_inei(variant, max_results=5))
    candidates.extend(_search_datosabiertos_peru(variant, max_results=5))
```

### 7.2 Fuentes posteriores

- `datos.susalud.gob.pe`: verificar primero si expone CKAN/API estable.
- NASA VNP46A4: modulo separado, no meter en Fase 1; requiere manejo geoespacial y probablemente credenciales/earthaccess.

---

## 8. Orden de implementacion

### Fase 1 - Contratos y modo R funcional

1. `run_pipeline.py`: agregar `--mode`.
2. `stage1_discovery.py`: persistir `seed_papers`.
3. `stage2_ideation.py`: refactor normal/replication y generar `top_ideas` compatible.
4. `stage3_validation.py`: incluir contexto de replicacion en `idea_text`.
5. Smoke test: correr hasta Stage 2.5 y verificar que `SELECT 1` funciona.

Criterio de exito:

- `pipeline_state.json` contiene `stage1.seed_papers`.
- `stage2.mode == "replication"`.
- `stage2.top_ideas` existe y tiene 3+ items.
- Stage 2.5 no falla.

### Fase 2 - HTE como first-class design

1. `human_checkpoint.py`: clasificacion/display HTE.
2. `templates/__init__.py`: agregar `hte`.
3. Crear templates `hte_00_clean.py` a `hte_03_output.py`.
4. `stage3_3_quick_test.py`: checks y disponibilidad `econml/sklearn`.
5. `stage4_strategy.py`: keywords HTE sin pase automatico por "replication".
6. `stage4_code.py`: prompt HTE y gate de replicacion.

Criterio de exito:

- `detect_design(selected_idea)` devuelve `"hte"`.
- Stage 4 escribe `00_clean.py` a `03_output.py`.
- Scripts generan `clean_data.csv`, `main_results.csv`, `robustness_results.csv`.

### Fase 3 - Calidad de contenido y datos Peru

1. Agregar `datosabiertos.gob.pe`.
2. Mejorar paper content extraction.
3. Agregar soporte opcional `--paper path/to/file.pdf`.
4. Agregar pruebas unitarias/smoke tests.

---

## 9. Pruebas recomendadas

### Test unitario: schema Stage 2 replication

Crear estado minimo con:

```python
state = {
    "config": {"stage2_mode": "replicate"},
    "stages": {
        "stage1": {
            "topic": "informalidad en Peru",
            "seed_papers": [...],
            "recommended_data_sources": [...]
        },
        "stage1_5": {"downloaded_datasets": [...]}
    }
}
```

Verificar:

- `_run_replication_mode()` retorna `stage2.top_ideas`.
- Cada idea tiene `title`, `research_question`, `method`, `data_sources`, `total_score`.

### Smoke test CLI

```powershell
python run_pipeline.py --topic "informalidad en Peru" --mode replicate --to-stage 2.5
```

Verificar:

- muestra papers candidatos;
- permite elegir paper;
- genera angulos;
- Stage 2.5 permite `SELECT 1`.

### Smoke test no interactivo

```powershell
python run_pipeline.py --topic "informalidad en Peru" --mode new --to-stage 2
```

Verificar:

- no llama `input()`;
- comportamiento actual sigue funcionando.

---

## 10. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigacion |
|---|---|---|
| No hay `seed_papers` utiles | Modo R no tiene papers buenos | Stage 2 hace busqueda Semantic Scholar adicional |
| PDF no se puede leer | Angulos pobres | Usar abstract completo + metadata; permitir `--paper` en Fase 3 |
| `econml` no instalado | Stage 4 falla | Stage 3.3 detecta y Stage 4 genera fallback o requirements |
| HTE sin overlap | Resultados no creibles | Quick test de propensity/overlap antes de Stage 4 |
| Replicacion no reproduce ATE | Paper debil | Gate de warning y revision de sample restrictions |
| Cambios rompen Stage 2 normal | Regresion grave | Refactor con `_run_ideation_normal()` y smoke test `--mode new` |

---

## 11. Lo que no se debe hacer

- No guardar angulos solo en `ideas`; usar `top_ideas`.
- No asumir que Stage 1 ya tiene `seed_papers`.
- No truncar abstracts a 200 caracteres para modo R.
- No usar `"replication"` como keyword suficiente para aprobar identificacion.
- No cambiar a scripts `1_load.py`, `2_clean.py`, etc. sin cambiar executor y validators.
- No instalar `geopandas` por defecto.
- No hacer `input()` obligatorio en corridas no interactivas.

---

## 12. Definicion de terminado

Modo replicacion se considera implementado cuando:

1. `--mode replicate` corre Stage 1 -> Stage 2.5 sin errores.
2. El estado contiene `seed_papers`, `chosen_paper` y `top_ideas`.
3. Stage 2.5 puede seleccionar un angulo HTE usando el checkpoint actual.
4. Stage 3 evalua replicacion y HTE con criterios explicitos.
5. Stage 4 puede generar y ejecutar scripts HTE bajo el contrato `00_clean.py` a `03_output.py`.
6. El modo normal `--mode new` sigue funcionando sin cambios visibles para el usuario.
