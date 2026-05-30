"""Stage 3.5 — Human Strategy Review.

Two-phase checkpoint:
  Phase 1: Data source selection — work with main dataset only or also external?
  Phase 2: Strategy review — APPROVE, REFORMULATE, or REJECT the strategy.

If external data is requested, the pipeline searches for, downloads, and verifies
merge compatibility before proceeding to the strategy review.
"""

import re
import sys
from datetime import datetime
from pathlib import Path

from ..json_utils import extract_json
from ..state import save_state
from ..human_checkpoint import data_source_selection, strategy_review
from .stage1_5_data_loading import get_bundled_files


# ── Data-grounded validation of the strategy ─────────────────────────────────

# Common English / methods stopwords that look like variable names but aren't.
# Extend as new false positives appear.
_STRATEGY_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "into", "this", "that", "these",
    "those", "data", "panel", "wave", "waves", "year", "years", "time",
    "level", "model", "method", "design", "test", "tests", "score", "scores",
    "study", "group", "groups", "control", "controls", "treat", "treated",
    "treatment", "effect", "effects", "analysis", "rct", "did", "twfe",
    "ols", "iv", "rdd", "fe", "ate", "att", "itt", "tot", "individual",
    "school", "student", "students", "schools", "outcome", "outcomes",
    "baseline", "post", "pre", "policy", "table", "figure", "row", "rows",
    "col", "cols", "column", "columns", "missing", "value", "values",
    "between", "within", "across", "over", "under", "above", "below",
    "all", "any", "some", "none", "one", "two", "three", "four", "five",
    "main", "key", "merge", "join", "left", "right", "inner", "outer",
    "cohort", "cohorts", "robust", "standard", "errors", "cluster",
    "clustered", "fixed", "random", "effect", "linear", "logistic",
    "regression", "estimate", "estimator", "estimation", "specification",
    "set", "subset", "bandwidth", "window", "lag", "lead", "delta",
    "see", "use", "used", "via", "per", "not", "nor", "but", "yes", "are",
    "has", "had", "have", "was", "were", "will", "would", "should", "may",
    "can", "could", "etc", "eg", "ie", "vs", "of", "to", "in", "on", "by",
    "as", "or", "if", "is", "be", "do", "no", "up", "an", "at", "it",
    "csv", "dta", "tab", "xlsx", "parquet", "tsv",
    "callaway", "santanna", "abraham", "bacon", "goodman", "stagger",
    "staggered", "event", "study", "dynamic", "trends", "parallel",
    "identification", "variation", "exogenous", "endogenous", "instrument",
    "first", "second", "stage", "stages", "phase", "phases",
    "id", "ids",
    # journal-style markers
    "qje", "aer", "jpe", "restud", "ecma", "restat",
    # Common prose words that look variable-ish but rarely are column names.
    # Bare "assignment", "assigned" → noun forms used in prose ("wave
    # assignment"); the actual columns are usually wgrp, treat_arm, etc.
    "assignment", "assigned",
    "teacher", "teachers", "performance", "pay", "payment", "incentive",
    "incentives", "attendance", "achievement", "adoption", "absent",
    "absenteeism", "enrollment", "test", "scores",
    "decomposition", "negative", "weighting", "weights", "weight", "bias",
    "biased", "unbiased", "true", "false", "specific", "general",
    "name", "names", "namelist",
    "sant", "anna", "sun",  # author surnames bleeding through tokenizer
    "daily", "weekly", "monthly", "annual",
})

# Tokens that LOOK like variable names: lowercase letter/digit/underscore,
# 2–25 chars, must start with a letter, must contain at least one letter.
_VARNAME_RE = re.compile(r"\b([a-z][a-z0-9_]{1,24})\b")

# Stricter pattern: only tokens that look like REAL variable names (not prose).
# A real column name typically has at least ONE of:
#   - An underscore (e.g. tiene_billetera, factor_07, p558e1_9)
#   - A digit (e.g. p208a, ocu500, factor07)
# Plain English/Spanish words ("does", "receiving", "cash", "billetera")
# without underscores or digits are almost never column names — they're prose.
_LOOKS_LIKE_COLUMN_RE = re.compile(r"[_0-9]")

# Critical-variable keywords. If a strategy text mentions a token that
# matches one of these patterns AND the token is missing from the data,
# we treat it as a hard blocker. The rest are soft warnings.
_CRITICAL_PATTERNS = (
    r"^wgrp",        # M&S wave/treatment cohort
    r"^treat",
    r"^assign",
    r"^random",
    r"_treat$",
    r"_assigned$",
    r"^arm$",
)
_CRITICAL_RE = re.compile("|".join(_CRITICAL_PATTERNS))


def _read_columns(path: str) -> list[str]:
    """Cheaply read the column names of a tabular file."""
    import warnings
    import pandas as pd

    p = Path(path)
    if not p.exists():
        return []
    ext = p.suffix.lower()
    try:
        if ext == ".dta":
            # chunksize=1 reads the file header + 1 row, which is enough to
            # populate the column index without materializing the whole panel.
            # convert_categoricals=False sidesteps the categorical-conversion
            # warning that fires when value labels are partially defined.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                reader = pd.read_stata(
                    path, chunksize=1, convert_categoricals=False,
                )
                try:
                    chunk = next(iter(reader))
                    return list(chunk.columns)
                finally:
                    try:
                        reader.close()
                    except Exception:
                        pass
        elif ext in (".csv", ".tsv"):
            sep = "\t" if ext == ".tsv" else ","
            return list(
                pd.read_csv(path, sep=sep, nrows=0, encoding="utf-8",
                            low_memory=False).columns
            )
        elif ext == ".tab":
            return list(
                pd.read_csv(path, sep="\t", nrows=0, encoding="utf-8",
                            low_memory=False).columns
            )
        elif ext in (".xls", ".xlsx"):
            return list(pd.read_excel(path, nrows=0).columns)
        elif ext == ".parquet":
            return list(pd.read_parquet(path).columns)
    except Exception:
        # Encoding fallback for csv/tab
        try:
            if ext in (".csv", ".tsv", ".tab"):
                sep = "\t" if ext in (".tsv", ".tab") else ","
                return list(
                    pd.read_csv(path, sep=sep, nrows=0, encoding="latin-1",
                                low_memory=False).columns
                )
        except Exception:
            return []
    return []


def _build_variable_inventory(file_paths: list[str]) -> dict[str, list[str]]:
    """Map every column name (lower-cased) to the list of files containing it."""
    inventory: dict[str, list[str]] = {}
    for fp in file_paths:
        cols = _read_columns(fp)
        fname = Path(fp).name
        for col in cols:
            if col is None:
                continue
            key = str(col).strip().lower()
            if not key:
                continue
            inventory.setdefault(key, []).append(fname)
    return inventory


def _extract_candidate_variables(strategy: dict) -> list[str]:
    """Pull tokens that look like variable references out of the strategy text.

    Looks at the data, design, method, and pre_analysis_plan fields. Returns
    a deduplicated list of lowercase tokens that survive the stopword filter.
    """
    fields = []
    for key in ("data_sources", "data", "design", "method", "pre_analysis_plan",
                "user_notes", "title"):
        val = strategy.get(key)
        if isinstance(val, str):
            fields.append(val)
        elif isinstance(val, list):
            fields.extend(str(v) for v in val)

    text = " ".join(fields).lower()
    # Pull tokens out of slash-separated lists too: "obs/prs/par" → obs, prs, par
    text = re.sub(r"[\\/]", " ", text)

    seen: dict[str, None] = {}
    for match in _VARNAME_RE.finditer(text):
        tok = match.group(1)
        if tok in _STRATEGY_STOPWORDS:
            continue
        if tok.isdigit():
            continue
        # FIX: only accept tokens that look like real column names.
        # Real columns typically have an underscore or a digit (e.g.,
        # `tiene_billetera`, `p558e1`, `factor07`). Plain prose words
        # ("does", "receiving", "cash", "transfers") in design/method
        # fields almost never refer to actual columns and produce many
        # false positives in the data-validation report.
        if not _LOOKS_LIKE_COLUMN_RE.search(tok):
            continue
        seen[tok] = None
    return list(seen.keys())


def _validate_strategy_against_data(
    strategy: dict, main_data_path: str
) -> dict:
    """Verify that variables mentioned in the strategy exist in the data files.

    Loads the column inventory of the main file plus any siblings extracted
    from the same archive (via the extraction manifest written by Stage 1.5).
    Tokens that look like variable references but cannot be found anywhere
    are flagged. Tokens matching critical-variable patterns (treatment,
    assignment, wgrp, ...) are flagged as blockers; the rest as soft misses.

    Returns a dict::

        {
            "ran": bool,
            "files_scanned": [str, ...],
            "n_columns": int,
            "candidate_tokens": [str, ...],
            "found": [{"token": str, "files": [str, ...]}, ...],
            "missing": [str, ...],          # all tokens not found
            "critical_missing": [str, ...], # subset matching critical patterns
        }
    """
    if not main_data_path or not Path(main_data_path).exists():
        return {
            "ran": False,
            "reason": "No main dataset path available — cannot validate strategy.",
            "files_scanned": [],
            "n_columns": 0,
            "candidate_tokens": [],
            "found": [],
            "missing": [],
            "critical_missing": [],
        }

    file_paths = get_bundled_files(main_data_path)
    inventory = _build_variable_inventory(file_paths)
    candidates = _extract_candidate_variables(strategy)

    found: list[dict] = []
    missing: list[str] = []
    for tok in candidates:
        hits = inventory.get(tok)
        if hits:
            found.append({"token": tok, "files": sorted(set(hits))})
        else:
            missing.append(tok)

    critical_missing = [t for t in missing if _CRITICAL_RE.search(t)]

    return {
        "ran": True,
        "files_scanned": [Path(p).name for p in file_paths],
        "n_columns": len(inventory),
        "candidate_tokens": candidates,
        "found": found,
        "missing": missing,
        "critical_missing": critical_missing,
    }


def _identify_external_sources(data_sources: list[str], main_data_path: str) -> list[str]:
    """Separate external data sources from the main dataset.

    Aggressively filters out anything that looks like the user's main dataset
    (ENAHO panel references, the filename itself, generic "user dataset" mentions).
    """
    if not main_data_path:
        return data_sources

    main_name = Path(main_data_path).name.lower()
    # Extract key identifiers from main filename (e.g. "enaho01a-2020-2024-500-panel")
    main_stem = Path(main_data_path).stem.lower()

    # Extract column names from main dataset for self-reference detection
    main_cols_set: set[str] = set()
    try:
        import pandas as pd
        ext = Path(main_data_path).suffix.lower()
        if ext == ".parquet":
            main_cols_set = set(c.lower() for c in pd.read_parquet(main_data_path, columns=None).columns)
        else:
            main_cols_set = set(c.lower() for c in pd.read_csv(main_data_path, nrows=0, encoding="latin-1").columns)
    except Exception:
        pass

    external = []
    for src in data_sources:
        src_lower = src.lower()

        # Skip if it IS the main dataset (by filename match)
        if main_name in src_lower or main_stem in src_lower:
            continue
        # Skip generic references to the user's data
        if "user dataset" in src_lower or "available dataset" in src_lower:
            continue
        # Skip references that say "existing dataset" or "current dataset"
        if "existing dataset" in src_lower or "current dataset" in src_lower:
            continue
        # Skip sources described as "no external" or "self-contained"
        if "no external" in src_lower or "self-contained" in src_lower:
            continue
        # Skip if source is just listing main dataset columns (e.g. "num_pushers, language, iso2_code")
        if main_cols_set:
            # Extract parenthesised column lists like "(num_pushers, language, iso2_code, quarter)"
            import re
            paren_match = re.search(r'\(([^)]+)\)', src_lower)
            if paren_match:
                mentioned_cols = {c.strip() for c in paren_match.group(1).split(",")}
                if mentioned_cols and mentioned_cols.issubset(main_cols_set):
                    continue
        # Skip if it's a reference to the same ENAHO panel the user already has
        if "enaho" in src_lower and "(primary)" in src_lower:
            continue
        if "enaho" in src_lower and "current dataset" in src_lower:
            continue
        # Check if it mentions the same module number from the filename
        import re
        mod_match = re.search(r'(\d{3})', main_stem)
        if mod_match:
            main_module = mod_match.group(1)
            if f"module {main_module}" in src_lower or f"modulo {main_module}" in src_lower:
                years_in_main = re.findall(r'20\d{2}', main_stem)
                if years_in_main and all(y in src_lower for y in years_in_main[:2]):
                    continue

        external.append(src)
    return external


def _justify_external_sources(
    external_sources: list[str], strategy: dict, topic: str
) -> list[dict]:
    """Generate justifications for why each external source is needed.

    Uses Claude to explain each source's role in the identification strategy
    and what happens without it.

    Returns list of dicts: {"source", "role", "impact_without", "critical"}.
    """
    from ..config import get_profile
    from ..claude_runner import run_claude

    sources_list = "\n".join(f"  {i+1}. {src}" for i, src in enumerate(external_sources))
    prompt = f"""You are a research methodology advisor.

A study proposes this identification strategy:
  Method: {strategy.get('method', 'N/A')}
  Research question: {strategy.get('design', 'N/A')}
  Topic: {topic}

The strategy references these EXTERNAL data sources (beyond the main survey dataset):
{sources_list}

For EACH external source, explain:
1. Its specific role in the identification strategy (e.g., "serves as the instrumental variable", "provides the running variable for RDD", "used as control variable")
2. What happens if this source is NOT available — can the study still proceed with an adapted strategy, or is it a dealbreaker?
3. Is it CRITICAL (study cannot proceed without it) or OPTIONAL (strengthens the study but alternatives exist)?

Output a JSON array:
```json
[
  {{
    "source": "name of external source",
    "role": "specific role in the identification strategy",
    "impact_without": "what happens without this data — be specific about methodological consequences",
    "critical": true
  }}
]
```
"""
    p = get_profile("stage3_5_justify")
    resp = run_claude(
        prompt, model=p["model"], effort=p["effort"],
        label="justify external sources",
    )
    result = extract_json(resp)

    if isinstance(result, list):
        return result

    # Fallback: generate basic justifications without Claude
    return [
        {
            "source": src,
            "role": "Referenced in the proposed strategy",
            "impact_without": "Strategy may need adaptation",
            "critical": False,
        }
        for src in external_sources
    ]


def _assess_merge_feasibility(
    external_sources: list[str],
    external_justifications: list[dict],
    main_data_path: str,
    strategy: dict,
    topic: str,
) -> list[dict]:
    """Use Claude to assess merge feasibility for each external source.

    For each source, determines:
    - Data type (cross-sectional, panel, time-series)
    - Year(s) needed
    - Merge key and whether it exists in the main dataset
    - Merge level (individual, household, district, sector, occupation)
    - Likely URL or download location
    - Whether the merge is feasible

    Returns list of dicts with full specification for each viable source.
    """
    from ..config import get_profile
    from ..claude_runner import run_claude

    # Get main dataset columns for merge key detection
    main_cols_str = ""
    try:
        import pandas as pd
        ext = Path(main_data_path).suffix.lower()
        if ext == ".parquet":
            main_cols = pd.read_parquet(main_data_path, columns=None).columns.tolist()
        else:
            main_cols = pd.read_csv(main_data_path, nrows=0, encoding="latin-1").columns.tolist()
        # Show a selection of key columns for merge detection
        id_cols = [c for c in main_cols if any(x in c.lower() for x in
                   ["ubigeo", "dominio", "conglome", "vivienda", "hogar", "codperso",
                    "ciiu", "p507", "p505", "ocu500", "numper"])]
        main_cols_str = f"ID/merge columns in main dataset: {', '.join(id_cols[:20])}"
    except Exception:
        main_cols_str = "Could not read main dataset columns."

    sources_text = ""
    for i, src in enumerate(external_sources):
        just = external_justifications[i] if i < len(external_justifications) else {}
        sources_text += (
            f"\n  {i+1}. {src}"
            f"\n     Role: {just.get('role', 'N/A')}"
            f"\n     Critical: {just.get('critical', False)}"
        )

    prompt = f"""You are a data engineering advisor for econometric research.

A study on "{topic}" uses this main dataset: {Path(main_data_path).name}
{main_cols_str}

The identification strategy ({strategy.get('method', 'N/A')}) requires these external datasets:
{sources_text}

For EACH external source, assess merge feasibility:

1. What TYPE of data is it? (cross-sectional, panel, time-series)
2. What YEAR(s) are needed? Be specific (e.g., "2020 or earlier for pre-treatment")
3. What is the MERGE KEY? (e.g., CIIU occupation code, ubigeo district code, etc.)
4. Does that merge key EXIST in the main dataset columns listed above?
5. At what LEVEL would the merge happen? (individual, household, district, sector, occupation)
6. Is the merge FEASIBLE? (Yes/No with reason)
7. What is the most likely DOWNLOAD URL or source?
8. What EXACT FILE or module should the user download?

Output a JSON array:
```json
[
  {{
    "source": "name",
    "data_type": "cross-sectional|panel|time-series",
    "years_needed": "2020 or earlier",
    "merge_key": "CIIU 4-digit occupation code",
    "merge_key_in_main": true,
    "merge_key_column": "p507_20",
    "merge_level": "occupation",
    "merge_feasible": true,
    "feasibility_reason": "p507 contains CIIU codes that can be matched",
    "download_url": "https://...",
    "exact_file": "onet_teleworkable_blscodes.csv",
    "download_instructions": "Go to URL, click Download, extract CSV"
  }}
]
```

If a source CANNOT be merged (no common key exists in the main dataset), set
merge_feasible to false and explain why.
"""
    p = get_profile("stage3_5_merge")
    resp = run_claude(
        prompt, model=p["model"], effort=p["effort"],
        label="assess merge feasibility",
    )
    result = extract_json(resp)

    if isinstance(result, list):
        return result

    # Fallback
    return [
        {
            "source": src,
            "data_type": "unknown",
            "years_needed": "unknown",
            "merge_key": "unknown",
            "merge_key_in_main": False,
            "merge_feasible": False,
            "feasibility_reason": "Could not assess automatically",
            "download_url": "",
            "exact_file": "",
        }
        for src in external_sources
    ]


def _validate_external_file(
    src_path: Path,
    assessment: dict,
    main_data_path: str,
) -> dict:
    """Validate an external file: check merge key exists and has overlap with main data.

    Returns dict with: valid (bool), merge_key_found, overlap_pct, n_common, details.
    """
    import pandas as pd

    result = {"valid": False, "details": ""}
    ext_suffix = src_path.suffix.lower()

    try:
        # Load external file (just a sample for validation)
        if ext_suffix == ".parquet":
            ext_df = pd.read_parquet(src_path)
        elif ext_suffix == ".csv":
            ext_df = pd.read_csv(src_path, encoding="latin-1", low_memory=False)
        elif ext_suffix in (".xls", ".xlsx"):
            ext_df = pd.read_excel(src_path)
        elif ext_suffix == ".dta":
            ext_df = pd.read_stata(src_path)
        else:
            result["details"] = f"Unsupported format: {ext_suffix}"
            return result

        result["n_rows"] = len(ext_df)
        result["n_cols"] = len(ext_df.columns)
        print(f"    Loaded: {result['n_rows']:,} rows x {result['n_cols']} cols")

        # Check if merge key exists in the external file
        merge_key = assessment.get("merge_key", "").lower()
        merge_key_col = assessment.get("merge_key_column", "").lower()

        # Try to find the merge key column in the external data
        ext_key_col = None
        for c in ext_df.columns:
            cl = c.lower()
            if merge_key and (merge_key in cl or cl in merge_key):
                ext_key_col = c
                break
            if merge_key_col and cl == merge_key_col:
                ext_key_col = c
                break

        if not ext_key_col:
            # Try common key patterns
            for c in ext_df.columns:
                cl = c.lower()
                if any(kw in cl for kw in ["occ", "soc", "ciiu", "isic", "onet",
                                            "ubigeo", "distrito", "codperso"]):
                    ext_key_col = c
                    break

        if ext_key_col:
            print(f"    Merge key found: '{ext_key_col}' in external file")
            result["merge_key_found"] = True

            # Test overlap with main dataset
            if main_data_path and Path(main_data_path).exists():
                try:
                    main_suffix = Path(main_data_path).suffix.lower()
                    if main_suffix == ".parquet":
                        # Read only potential merge columns
                        main_df = pd.read_parquet(main_data_path)
                    else:
                        main_df = pd.read_csv(main_data_path, nrows=50000,
                                              encoding="latin-1", low_memory=False)

                    # Find corresponding column in main data
                    main_key_col = None
                    if merge_key_col:
                        matches = [c for c in main_df.columns if c.lower() == merge_key_col]
                        if matches:
                            main_key_col = matches[0]
                    if not main_key_col:
                        for c in main_df.columns:
                            if c.lower() == ext_key_col.lower():
                                main_key_col = c
                                break

                    if main_key_col:
                        main_vals = set(str(v).strip() for v in main_df[main_key_col].dropna().unique())
                        ext_vals = set(str(v).strip() for v in ext_df[ext_key_col].dropna().unique())
                        common = main_vals & ext_vals
                        overlap_pct = len(common) / max(len(ext_vals), 1) * 100

                        result["n_common_values"] = len(common)
                        result["overlap_pct"] = overlap_pct
                        print(f"    Overlap: {len(common)} common values "
                              f"({overlap_pct:.1f}% of external keys match main data)")

                        if overlap_pct < 5:
                            result["details"] = (
                                f"Very low overlap ({overlap_pct:.1f}%) between "
                                f"'{ext_key_col}' in external and '{main_key_col}' in main. "
                                f"Merge may produce mostly missing values."
                            )
                            result["valid"] = False
                        else:
                            result["valid"] = True
                            result["details"] = f"Good overlap ({overlap_pct:.1f}%)"
                    else:
                        print(f"    [warn] Could not find matching column in main data")
                        result["valid"] = True  # Assume ok if can't verify
                        result["details"] = "Could not verify overlap (key column not found in main)"
                    del main_df
                except Exception as e:
                    print(f"    [warn] Could not test overlap: {e}")
                    result["valid"] = True  # Assume ok if can't verify
                    result["details"] = f"Could not verify overlap: {e}"
            else:
                result["valid"] = True
                result["details"] = "No main dataset path for overlap test"
        else:
            print(f"    [!] Merge key not found in external file")
            print(f"        External columns: {', '.join(ext_df.columns[:15].tolist())}")
            result["merge_key_found"] = False
            result["valid"] = False
            result["details"] = f"Merge key '{merge_key}' not found in file columns"

        del ext_df
    except Exception as e:
        result["details"] = f"Could not read file: {e}"

    return result


def _request_external_data_manually(
    assessments: list[dict],
    main_data_name: str,
    main_data_path: str,
    project_dir: Path,
) -> list[dict]:
    """Present external data requirements to the user and collect file paths.

    Only shows sources where merge is feasible. Validates each file before
    accepting. Shows a summary and asks user to confirm before proceeding.
    Returns list of provided files.
    """
    import shutil

    # Filter out sources that are actually the main dataset in disguise
    main_name_lower = Path(main_data_path).name.lower() if main_data_path else ""
    def _is_main_dataset(a: dict) -> bool:
        src = a.get("source", "").lower()
        merge_key = a.get("merge_key", "").lower()
        instructions = a.get("download_instructions", "").lower()
        url = a.get("download_url", "").lower()
        # Matches: "existing dataset", "no external merge", "no download needed",
        # references to the main filename, or empty/N/A download URLs
        if any(kw in src for kw in ("existing dataset", "current dataset", "main dataset")):
            return True
        if any(kw in merge_key for kw in ("no external", "no merge", "self-contained", "computed internally")):
            return True
        if "no download" in instructions or "already in hand" in instructions:
            return True
        if main_name_lower and main_name_lower in src:
            return True
        if not url or url in ("n/a", "none", ""):
            return True
        return False

    assessments = [a for a in assessments if not _is_main_dataset(a)]
    feasible = [a for a in assessments if a.get("merge_feasible", False)]
    not_feasible = [a for a in assessments if not a.get("merge_feasible", False)]

    print(f"\n  {'=' * 60}")
    print(f"  EXTERNAL DATA SPECIFICATIONS")
    print(f"  {'=' * 60}")

    # Show infeasible sources (skipped)
    if not_feasible:
        print(f"\n  SKIPPED (merge not feasible with {main_data_name}):")
        for a in not_feasible:
            print(f"    [x] {a.get('source', '?')}")
            print(f"        Reason: {a.get('feasibility_reason', 'unknown')}")

    if not feasible:
        print(f"\n  No external sources can be merged with {main_data_name}.")
        print(f"  Continuing with main dataset only.")
        return []

    # Show feasible sources with full specifications
    print(f"\n  MERGEABLE SOURCES ({len(feasible)} available):\n")
    for i, a in enumerate(feasible, 1):
        critical = a.get("critical", False)
        tag = " [CRITICAL]" if critical else ""
        print(f"  [{i}] {a.get('source', '?')}{tag}")
        print(f"      Type: {a.get('data_type', '?')}")
        print(f"      Year(s) needed: {a.get('years_needed', '?')}")
        print(f"      Merge key: {a.get('merge_key', '?')}")
        key_col = a.get('merge_key_column', '')
        if key_col:
            print(f"      Key column in main data: {key_col}")
        print(f"      Merge level: {a.get('merge_level', '?')}")
        url = a.get('download_url', '')
        if url:
            print(f"      Download URL: {url}")
        exact = a.get('exact_file', '')
        if exact:
            print(f"      File needed: {exact}")
        instructions = a.get('download_instructions', '')
        if instructions:
            print(f"      Instructions: {instructions}")
        print()

    print(f"  {'=' * 60}")
    print(f"  Provide file paths below, or 'skip' to skip a source.")
    print(f"  {'=' * 60}")
    print("\a", end="", flush=True)

    data_dir = project_dir / "data" / "external"
    data_dir.mkdir(parents=True, exist_ok=True)
    added = []
    skipped = []

    for i, a in enumerate(feasible, 1):
        source_name = a.get('source', '?')[:50]
        while True:
            fpath = input(f"\n  File path for [{i}] {source_name}: ").strip()

            if fpath.lower() in ("skip", ""):
                print(f"  [skip] Skipping {source_name}")
                skipped.append(a)
                break

            src_path = Path(fpath)
            if not src_path.exists():
                print(f"  [!] File not found: {src_path}")
                continue

            # Validate the file
            print(f"  [check] Validating {src_path.name}...")
            validation = _validate_external_file(src_path, a, main_data_path)

            if not validation.get("valid", False):
                print(f"  [!] Validation issue: {validation.get('details', 'unknown')}")
                confirm = input("      Add anyway? (y/n): ").strip().lower()
                if confirm != "y":
                    print(f"  [skip] {src_path.name} not added.")
                    continue

            # Copy to project
            dst = data_dir / src_path.name
            shutil.copy2(src_path, dst)
            added.append({
                "source": a.get("source", ""),
                "local_path": str(dst),
                "merge_key": a.get("merge_key", ""),
                "merge_key_column": a.get("merge_key_column", ""),
                "merge_level": a.get("merge_level", ""),
                "data_type": a.get("data_type", ""),
                "validation": validation,
            })
            print(f"  [ok] Added: {src_path.name}")
            break

    # ── Data collection summary ───────────────────────────────────────────
    print(f"\n  {'=' * 60}")
    print(f"  DATA COLLECTION SUMMARY")
    print(f"  {'=' * 60}")
    print(f"  Provided:  {len(added)} of {len(feasible)} sources")
    if added:
        for f in added:
            print(f"    [ok] {f['source'][:50]}")
    print(f"  Skipped:   {len(skipped)} of {len(feasible)} sources")
    if skipped:
        for s in skipped:
            print(f"    [--] {s.get('source', '?')[:50]}")

    # No feasible sources not yet covered
    not_covered = [a for a in not_feasible]
    if not_covered:
        print(f"  Not mergeable: {len(not_covered)} sources")

    if len(added) < len(feasible):
        # Some sources missing — ask user if they want to continue
        missing_count = len(feasible) - len(added)
        print(f"\n  [?] {missing_count} mergeable source(s) were not provided.")
        print(f"      The strategy will be adapted to work without them.")
        print(f"\n      Options:")
        print(f"      y  -  Continue with what you have (main dataset{' + ' + str(len(added)) + ' external' if added else ''})")
        print(f"      n  -  Go back and provide more files")
        print("\a", end="", flush=True)

        while True:
            choice = input("\n      Continue? (y/n): ").strip().lower()
            if choice == "y":
                print(f"\n  [ok] Continuing with available data.")
                if skipped:
                    skipped_names = ", ".join(s.get("source", "?")[:30] for s in skipped)
                    print(f"       Strategy will adapt for missing: {skipped_names}")
                break
            elif choice == "n":
                # Let user provide more files — recurse through skipped
                print(f"\n  Provide paths for skipped sources:")
                for s in skipped[:]:
                    s_name = s.get("source", "?")[:50]
                    fpath = input(f"\n  File path for {s_name} (or 'skip'): ").strip()
                    if fpath.lower() in ("skip", ""):
                        continue
                    src_path = Path(fpath)
                    if not src_path.exists():
                        print(f"  [!] File not found.")
                        continue
                    print(f"  [check] Validating {src_path.name}...")
                    validation = _validate_external_file(src_path, s, main_data_path)
                    if not validation.get("valid", False):
                        print(f"  [!] {validation.get('details', '')}")
                        confirm = input("      Add anyway? (y/n): ").strip().lower()
                        if confirm != "y":
                            continue
                    dst = data_dir / src_path.name
                    shutil.copy2(src_path, dst)
                    added.append({
                        "source": s.get("source", ""),
                        "local_path": str(dst),
                        "merge_key": s.get("merge_key", ""),
                        "merge_key_column": s.get("merge_key_column", ""),
                        "merge_level": s.get("merge_level", ""),
                        "data_type": s.get("data_type", ""),
                        "validation": validation,
                    })
                    skipped.remove(s)
                    print(f"  [ok] Added: {src_path.name}")
                break
            else:
                print("      Please enter y or n.")

    elif len(added) == len(feasible):
        print(f"\n  [ok] All mergeable sources provided.")

    print(f"  {'=' * 60}")
    return added


def _search_and_download_external(
    external_sources: list[str], project_dir: Path, topic: str
) -> list[dict]:
    """Use Claude to search for external datasets and attempt to download them.

    Returns a list of dicts with keys: source, local_path, downloaded, error.
    """
    from ..config import get_profile
    from ..claude_runner import run_claude

    results = []
    data_dir = project_dir / "data" / "external"
    data_dir.mkdir(parents=True, exist_ok=True)

    for src in external_sources:
        print(f"\n  [ext] Searching for: {src}...")

        search_prompt = f"""You are a data acquisition assistant.

I need to find and download this dataset:
  "{src}"

Context: Research on "{topic}" using Peruvian data.

Search for the EXACT download URL for this dataset. Look in:
- Official government portals (datos.gob.pe, INEI, OSIPTEL, SUNAT, MTPE)
- International organizations (World Bank, IMF, IDB)
- Academic data repositories (Harvard Dataverse, ICPSR, Zenodo)

If you find a downloadable file, provide the DIRECT download URL.
If the data requires registration, API access, or is not freely available,
say so explicitly.

Output a JSON block:
```json
{{
  "source_name": "{src}",
  "found": true,
  "download_url": "https://...",
  "format": ".csv",
  "description": "...",
  "access_notes": "freely available / requires registration / not available"
}}
```

If not found or not freely downloadable:
```json
{{
  "source_name": "{src}",
  "found": false,
  "download_url": "",
  "access_notes": "reason why not available"
}}
```
"""
        p = get_profile("stage1")
        resp = run_claude(
            search_prompt, model=p["model"], effort=p["effort"],
            allowed_tools=["WebSearch", "WebFetch"],
            label=f"search external: {src[:40]}",
        )
        search_result = extract_json(resp) or {}

        if not search_result.get("found") or not search_result.get("download_url"):
            print(f"  [ext] NOT FOUND: {search_result.get('access_notes', 'unknown reason')}")
            results.append({
                "source": src,
                "local_path": None,
                "downloaded": False,
                "error": search_result.get("access_notes", "Dataset not found or not freely available"),
            })
            continue

        # Try to download
        download_url = search_result["download_url"]
        fmt = search_result.get("format", ".csv")
        try:
            import requests
            print(f"  [ext] Downloading from {download_url[:80]}...")
            resp_http = requests.get(download_url, timeout=120, allow_redirects=True)
            if resp_http.status_code == 200 and len(resp_http.content) > 500:
                safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in src[:40])
                local_path = data_dir / f"{safe_name}{fmt}"
                local_path.write_bytes(resp_http.content)
                size_kb = len(resp_http.content) / 1024
                print(f"  [ext] Saved: {local_path.name} ({size_kb:.0f} KB)")
                results.append({
                    "source": src,
                    "local_path": str(local_path),
                    "downloaded": True,
                    "error": None,
                })
            else:
                print(f"  [ext] Download failed: HTTP {resp_http.status_code}")
                results.append({
                    "source": src,
                    "local_path": None,
                    "downloaded": False,
                    "error": f"HTTP {resp_http.status_code}",
                })
        except Exception as e:
            print(f"  [ext] Download error: {e}")
            results.append({
                "source": src,
                "local_path": None,
                "downloaded": False,
                "error": str(e),
            })

    return results


def _verify_merge_compatibility(
    main_data_path: str, external_results: list[dict]
) -> dict:
    """Check if external datasets can be merged with the main dataset.

    Verifies that they share a common identification unit (merge key).
    Returns dict with merge_ok, details, and merged_columns.
    """
    import pandas as pd
    from .stage1_discovery import _load_dataframe

    downloaded = [r for r in external_results if r["downloaded"] and r["local_path"]]
    if not downloaded:
        return {
            "merge_ok": False,
            "details": "No external datasets were downloaded successfully.",
            "merged_paths": [],
        }

    # Load main dataset columns
    try:
        main_df = _load_dataframe(main_data_path)
    except Exception as e:
        return {"merge_ok": False, "details": f"Could not load main dataset: {e}", "merged_paths": []}

    main_cols = set(c.lower() for c in main_df.columns)

    # Common merge keys for Peruvian survey data
    KNOWN_KEYS = {
        # Individual/household level
        "codperso", "conglome", "vivienda", "hogar",
        # Geographic level
        "ubigeo", "dominio", "estrato",
        # Time
        "año", "anio", "year", "mes", "month", "periodo",
    }

    main_keys = main_cols & KNOWN_KEYS
    merge_results = []
    all_ok = True

    for ext in downloaded:
        ext_path = ext["local_path"]
        try:
            ext_df = _load_dataframe(ext_path)
            ext_cols = set(c.lower() for c in ext_df.columns)
            ext_keys = ext_cols & KNOWN_KEYS
            common_keys = main_keys & ext_keys

            if common_keys:
                # Verify actual overlap in values for the best key
                best_key = None
                best_overlap = 0
                for key in common_keys:
                    # Find original column name (case-sensitive)
                    main_col = [c for c in main_df.columns if c.lower() == key][0]
                    ext_col = [c for c in ext_df.columns if c.lower() == key][0]
                    main_vals = set(main_df[main_col].dropna().unique())
                    ext_vals = set(ext_df[ext_col].dropna().unique())
                    overlap = len(main_vals & ext_vals)
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_key = key

                if best_overlap > 0:
                    merge_results.append({
                        "source": ext["source"],
                        "path": ext_path,
                        "merge_key": best_key,
                        "common_values": best_overlap,
                        "ok": True,
                    })
                    print(f"  [merge] {ext['source'][:40]}... -> OK "
                          f"(key: {best_key}, {best_overlap} common values)")
                else:
                    merge_results.append({
                        "source": ext["source"],
                        "path": ext_path,
                        "merge_key": None,
                        "common_values": 0,
                        "ok": False,
                        "error": f"Common key columns ({', '.join(common_keys)}) "
                                 f"but NO overlapping values",
                    })
                    all_ok = False
                    print(f"  [merge] {ext['source'][:40]}... -> FAIL "
                          f"(keys found but no value overlap)")
            else:
                merge_results.append({
                    "source": ext["source"],
                    "path": ext_path,
                    "merge_key": None,
                    "common_values": 0,
                    "ok": False,
                    "error": f"No common ID columns. Main has: {', '.join(sorted(main_keys))}. "
                             f"External has: {', '.join(sorted(ext_keys)) or 'none'}",
                })
                all_ok = False
                print(f"  [merge] {ext['source'][:40]}... -> FAIL (no common keys)")

        except Exception as e:
            merge_results.append({
                "source": ext["source"],
                "path": ext_path,
                "ok": False,
                "error": f"Could not load: {e}",
            })
            all_ok = False
            print(f"  [merge] {ext['source'][:40]}... -> FAIL ({e})")

    return {
        "merge_ok": all_ok,
        "details": merge_results,
        "merged_paths": [r["path"] for r in merge_results if r.get("ok")],
    }


def run(project_dir: Path, state: dict) -> dict:
    """Execute Stage 3.5: data source selection + human strategy review."""
    stage1 = state["stages"].get("stage1", {})
    stage3 = state["stages"].get("stage3", {})
    result = stage3.get("result", {})

    if not result:
        validation_file = project_dir / "stage3_validation.md"
        if validation_file.exists():
            content = validation_file.read_text(encoding="utf-8")
            result = extract_json(content) or {}

    if not result:
        print("  [error] No validation result from Stage 3. Run Stage 3 first.")
        sys.exit(1)

    # Build a strategy summary from what Stage 3 produced
    strategy = {
        "title": result.get("title", "Untitled"),
        "method": result.get("method", "N/A"),
        "design": result.get("refined_question", result.get("research_question", "N/A")),
        "data_sources": result.get("data_sources", []),
        "pre_analysis_plan": result.get("pre_analysis_plan", ""),
    }

    # Save state before prompting (Ctrl-C safe)
    save_state(project_dir, state)

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 1: DATA SOURCE SELECTION
    # ══════════════════════════════════════════════════════════════════════
    # Path B sets stage1["data_path"]; Path A downloads into stage1_5.
    main_data_path = stage1.get("data_path", "")
    if not main_data_path:
        stage1_5 = state["stages"].get("stage1_5", {})
        downloaded = stage1_5.get("downloaded_datasets", [])
        if downloaded:
            main_data_path = downloaded[0].get("local_path", "")
    main_data_name = Path(main_data_path).name if main_data_path else "N/A (Path A)"
    topic = stage1.get("topic", "")

    # Identify which data sources are external
    external_sources = _identify_external_sources(
        strategy.get("data_sources", []), main_data_path
    )

    # Generate justifications for external sources using Claude
    external_justifications = None
    if external_sources:
        external_justifications = _justify_external_sources(
            external_sources, strategy, topic
        )

    data_selection = data_source_selection(
        main_data_name, external_sources, external_justifications
    )

    if data_selection["use_external"]:
        # ── Assess merge feasibility BEFORE asking user to download ──
        print(f"\n  [merge] Assessing merge feasibility for {len(external_sources)} source(s)...")
        assessments = _assess_merge_feasibility(
            external_sources, external_justifications or [],
            main_data_path, strategy, topic,
        )

        # ── Present specifications and collect files from user ──
        provided_files = _request_external_data_manually(
            assessments, main_data_name, main_data_path, project_dir,
        )

        if provided_files:
            data_selection["use_external"] = True
            merge_keys_desc = ", ".join(
                f"{f['source'][:30]} via {f['merge_key']}" for f in provided_files
            )
            strategy["data_sources"] = [main_data_name] + [
                Path(f["local_path"]).name for f in provided_files
            ]
            strategy["user_notes"] = (
                f"User provided {len(provided_files)} external dataset(s). "
                f"Merge keys: {merge_keys_desc}."
            )
            state["stages"]["stage3_5_data"] = {
                "use_external": True,
                "manual_files": [f["local_path"] for f in provided_files],
                "merge_info": provided_files,
            }
        else:
            print(f"\n  [ok] No external files provided. Continuing with {main_data_name} only.")
            data_selection["use_external"] = False
            strategy["data_sources"] = [main_data_name]
            strategy["user_notes"] = (
                f"Use ONLY the main dataset ({main_data_name}). "
                f"External datasets were not provided. "
                f"Adapt the methodology to work without external data."
            )
    else:
        # Option 1: main dataset only
        strategy["data_sources"] = [main_data_name]
        strategy["user_notes"] = (
            f"Use ONLY the main dataset ({main_data_name}). "
            f"Do NOT reference or require any external datasets."
        )

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 2: STRATEGY REVIEW
    # ══════════════════════════════════════════════════════════════════════
    # Cross-check the strategy against the actual data files (main + any
    # siblings extracted from the same replication archive). If variables
    # mentioned in the strategy don't exist anywhere in the file set, the
    # diagnosis will hard-cap the score and surface the missing variables
    # so the user doesn't approve a strategy that can't run.
    data_validation = _validate_strategy_against_data(strategy, main_data_path)
    review = strategy_review(
        strategy,
        main_data_name=main_data_name,
        data_validation=data_validation,
    )

    state["stages"]["stage3_5"] = {
        "status": "completed",
        "action": review["action"],
        "data_selection": data_selection,
        "completed_at": datetime.now().isoformat(),
    }

    if review["action"] == "APPROVE":
        state["stages"]["stage3_5"]["approved_strategy"] = strategy
    elif review["action"] == "REFORMULATE":
        state["stages"]["stage3_5"]["approved_strategy"] = {
            **strategy,
            "reformulated": True,
            "user_notes": strategy.get("user_notes", "") + "\n" + review["notes"],
        }
    # REJECT → no approved_strategy stored

    state["current_stage"] = 3.5
    save_state(project_dir, state)

    if review["action"] == "REJECT":
        print("  [loop] Returning to Stage 2.5 for a different idea.")

    return state
