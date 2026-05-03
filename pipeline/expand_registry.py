"""Expand curated registry by searching journal APIs and validating downloads.

Searches all journal collections for datasets, downloads, validates against
Q1-Q4 quality criteria, and outputs validated entries to add to registry.

Usage: python -m pipeline.expand_registry
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.dataset_registry import (
    CURATED_DATASETS, JOURNAL_COLLECTIONS,
    search_journal_collection,
)
from pipeline.validate_registry import _download_dataverse, _load_dataframe


# Already-curated DOIs (don't re-add)
EXISTING_DOIS = {ds.get("dataverse_doi", "") for ds in CURATED_DATASETS if ds.get("dataverse_doi")}


def validate_and_profile(doi: str, title: str, journal: str, temp_dir: str) -> dict | None:
    """Download, validate, and profile a single dataset. Returns entry dict or None."""
    if not doi or doi in EXISTING_DOIS:
        return None

    # Download
    local_path = _download_dataverse(doi, temp_dir)
    if not local_path:
        return None

    # Handle zip
    if local_path.endswith(".zip"):
        try:
            import zipfile
            with zipfile.ZipFile(local_path, 'r') as zf:
                data_files = [f for f in zf.namelist()
                              if any(f.lower().endswith(ext)
                                     for ext in (".csv", ".dta", ".tab", ".tsv", ".xlsx"))
                              and not f.startswith("__MACOSX")]
                if not data_files:
                    return None
                zf.extract(data_files[0], temp_dir)
                local_path = os.path.join(temp_dir, data_files[0])
        except Exception:
            return None

    # Load and validate
    try:
        df = _load_dataframe(local_path)
        n_rows, n_cols = df.shape

        # Must have >= 100 rows and >= 5 cols
        if n_rows < 100 or n_cols < 5:
            return None

        # Q1: <20% of columns with >20% missing
        missing_pcts = df.isnull().mean()
        high_missing_cols = (missing_pcts > 0.20).sum()
        high_missing_pct = 100 * high_missing_cols / max(n_cols, 1)
        if high_missing_pct > 20:
            return None

        # Q3: Not mostly coded column names
        code_cols = sum(
            1 for col in df.columns
            if len(col) <= 6 and any(c.isdigit() for c in col)
            and col.lower() not in ("year", "age", "id", "n", "sex")
        )
        if 100 * code_cols / max(n_cols, 1) > 60:
            return None

        # Q4: Column/row ratio not too high with high missing
        if n_cols / max(n_rows, 1) > 0.40 and high_missing_pct > 20:
            return None

        # Detect design from column names
        cols_lower = " ".join(c.lower() for c in df.columns)
        if any(k in cols_lower for k in ["treat", "treatment", "arm", "randomiz"]):
            design = "rct"
            tier = 1
            ceiling = 93
        elif any(k in cols_lower for k in ["running", "threshold", "cutoff", "margin"]):
            design = "rdd"
            tier = 2
            ceiling = 88
        elif any(k in cols_lower for k in ["instrument", "iv_", "first_stage"]):
            design = "iv"
            tier = 2
            ceiling = 85
        elif any(k in cols_lower for k in ["year", "period", "time", "wave"]):
            design = "did"
            tier = 2
            ceiling = 87
        else:
            design = "iv"  # default conservative
            tier = 3
            ceiling = 80

        # Detect area from title
        title_lower = title.lower()
        area_map = {
            "labor": ["labor", "wage", "employ", "worker", "job", "union"],
            "health": ["health", "mortal", "hospital", "medic", "disease"],
            "education": ["education", "school", "student", "teacher", "learn"],
            "trade": ["trade", "tariff", "import", "export", "dumping"],
            "environment": ["environment", "climate", "emission", "pollut", "water", "forest"],
            "development": ["develop", "poverty", "microfinance", "aid", "africa", "india"],
            "political economy": ["politic", "vote", "elect", "democra", "conflict"],
            "public finance": ["tax", "fiscal", "public", "government", "subsid"],
            "behavioral": ["experiment", "behavio", "bias", "nudge", "preferenc"],
        }
        area = "mixed"
        for a, keywords in area_map.items():
            if any(kw in title_lower for kw in keywords):
                area = a
                break

        del df
        return {
            "title": title[:100],
            "dataverse_doi": doi,
            "journal": journal,
            "design": design,
            "area": area,
            "design_tier": tier,
            "score_ceiling": ceiling,
            "_rows": n_rows,
            "_cols": n_cols,
            "_missing_pct": round(high_missing_pct, 1),
        }

    except Exception:
        return None


def main():
    print("=" * 70)
    print("Expanding curated registry via journal API search + validation")
    print(f"Currently have: {len(CURATED_DATASETS)} curated datasets")
    print(f"Target: 50+")
    print("=" * 70)

    # Search ALL journal collections with multiple queries
    all_candidates = []
    search_queries = [
        "",  # newest
        "randomized experiment",
        "regression discontinuity",
        "difference in differences",
        "instrumental variable",
        "panel data",
        "natural experiment",
        "policy reform",
    ]

    for journal_key, journal_info in JOURNAL_COLLECTIONS.items():
        if journal_info["platform"] not in ("dataverse", "zenodo"):
            continue

        print(f"\n  Searching {journal_info['name']}...")
        for query in search_queries:
            results = search_journal_collection(journal_key, query=query, max_results=5)
            for r in results:
                doi = r.get("doi", "")
                if doi and doi not in EXISTING_DOIS:
                    # Deduplicate
                    if not any(c.get("doi") == doi for c in all_candidates):
                        all_candidates.append({
                            "doi": doi,
                            "title": r.get("name", r.get("description", ""))[:100],
                            "journal": journal_key,
                        })

    print(f"\n  Total unique candidates: {len(all_candidates)}")

    # Validate in parallel
    temp_base = tempfile.mkdtemp(prefix="expand_registry_")
    validated = []
    failed = 0

    print(f"\n  Downloading and validating (4 parallel)...\n")

    def _validate_one(i_c):
        i, c = i_c
        ds_dir = os.path.join(temp_base, f"ds_{i}")
        os.makedirs(ds_dir, exist_ok=True)
        return validate_and_profile(c["doi"], c["title"], c["journal"], ds_dir)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_validate_one, (i, c)): (i, c)
                   for i, c in enumerate(all_candidates)}

        for future in as_completed(futures):
            i, c = futures[future]
            result = future.result()
            total_done = len(validated) + failed + 1

            if result:
                validated.append(result)
                print(f"  [{total_done:3d}/{len(all_candidates)}] PASS: "
                      f"{result['title'][:50]} ({result['_rows']:,}x{result['_cols']})")
            else:
                failed += 1
                if total_done % 10 == 0:
                    print(f"  [{total_done:3d}/{len(all_candidates)}] ... "
                          f"({len(validated)} passed, {failed} failed so far)")

            # Stop if we have enough
            if len(validated) >= 40:
                print(f"\n  Reached {len(validated)} validated datasets. Stopping.")
                break

    print(f"\n{'=' * 70}")
    print(f"RESULTS: {len(validated)} new validated datasets")
    print(f"{'=' * 70}")

    # Print as Python code to add to registry
    print(f"\n# Add to CURATED_DATASETS in dataset_registry.py:")
    for ds in validated:
        rows = ds.pop("_rows", 0)
        cols = ds.pop("_cols", 0)
        miss = ds.pop("_missing_pct", 0)
        print(f"    {{  # {rows:,}x{cols}, {miss}% missing")
        for k, v in ds.items():
            if isinstance(v, str):
                print(f'        "{k}": "{v}",')
            else:
                print(f'        "{k}": {v},')
        print(f"    }},")

    # Save as JSON for programmatic use
    output_path = Path(__file__).parent / "expanded_registry.json"
    output_path.write_text(
        json.dumps(validated, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nSaved: {output_path}")

    # Cleanup
    try:
        shutil.rmtree(temp_base)
    except Exception:
        pass

    total = len(CURATED_DATASETS) + len(validated)
    print(f"\nTotal after expansion: {total} (current {len(CURATED_DATASETS)} + {len(validated)} new)")


if __name__ == "__main__":
    main()
