"""Validate all curated datasets in the registry.

Downloads each dataset, runs quality checks (Q1-Q4), and reports which
ones pass or fail. Outputs a clean list of validated datasets.

Usage: python -m pipeline.validate_registry
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.dataset_registry import CURATED_DATASETS


def _download_dataverse(doi: str, dest_dir: str) -> str | None:
    """Download first data file from a Dataverse DOI."""
    import requests

    try:
        # Resolve DOI to Dataverse API
        if not doi.startswith("http"):
            doi_url = f"https://doi.org/{doi}"
        else:
            doi_url = doi

        # Get dataset files via API
        persistent_id = f"doi:{doi}" if not doi.startswith("doi:") else doi
        api_url = f"https://dataverse.harvard.edu/api/datasets/:persistentId/?persistentId={persistent_id}"

        r = requests.get(api_url, timeout=30)
        r.raise_for_status()
        data = r.json().get("data", {})
        files = data.get("latestVersion", {}).get("files", [])

        # Find first tabular/CSV/Stata file
        data_extensions = (".csv", ".tab", ".dta", ".tsv", ".xlsx", ".parquet")
        target = None
        for f in files:
            fname = f.get("dataFile", {}).get("filename", "")
            if any(fname.lower().endswith(ext) for ext in data_extensions):
                target = f
                break

        # Fallback: try zip files
        if not target:
            for f in files:
                fname = f.get("dataFile", {}).get("filename", "")
                if fname.lower().endswith(".zip"):
                    target = f
                    break

        if not target:
            return None

        file_id = target.get("dataFile", {}).get("id")
        fname = target.get("dataFile", {}).get("filename", "data.csv")

        # Download
        dl_url = f"https://dataverse.harvard.edu/api/access/datafile/{file_id}"
        r = requests.get(dl_url, timeout=60, stream=True)
        r.raise_for_status()

        dest = os.path.join(dest_dir, fname)
        with open(dest, "wb") as fp:
            for chunk in r.iter_content(8192):
                fp.write(chunk)

        return dest

    except Exception as e:
        return None


def _load_dataframe(path: str):
    """Load a data file into pandas DataFrame."""
    import pandas as pd

    ext = Path(path).suffix.lower()
    if ext == ".dta":
        return pd.read_stata(path)
    elif ext == ".tab" or ext == ".tsv":
        return pd.read_csv(path, sep="\t", encoding="latin-1", low_memory=False)
    elif ext == ".parquet":
        return pd.read_parquet(path)
    elif ext == ".xlsx":
        return pd.read_excel(path)
    else:
        return pd.read_csv(path, encoding="latin-1", low_memory=False)


def validate_dataset(ds: dict, temp_dir: str) -> dict:
    """Download and validate a single dataset. Returns result dict."""
    title = ds.get("title", "?")[:60]
    doi = ds.get("dataverse_doi", "")

    result = {
        "title": ds.get("title", ""),
        "doi": doi,
        "status": "unknown",
        "reason": "",
        "rows": 0,
        "cols": 0,
        "high_missing_pct": 0,
        "has_treat_var": False,
        "col_row_ratio": 0,
        "coded_cols_pct": 0,
    }

    if not doi:
        result["status"] = "skip"
        result["reason"] = "no DOI"
        return result

    # Download
    try:
        local_path = _download_dataverse(doi, temp_dir)
        if not local_path:
            result["status"] = "fail_download"
            result["reason"] = "could not download data file"
            return result
    except Exception as e:
        result["status"] = "fail_download"
        result["reason"] = str(e)[:100]
        return result

    # Handle zip files
    if local_path.endswith(".zip"):
        try:
            import zipfile
            with zipfile.ZipFile(local_path, 'r') as zf:
                data_files = [f for f in zf.namelist()
                              if any(f.lower().endswith(ext)
                                     for ext in (".csv", ".dta", ".tab", ".tsv", ".xlsx"))]
                if not data_files:
                    result["status"] = "fail_download"
                    result["reason"] = "zip contains no data files"
                    return result
                # Extract first data file
                zf.extract(data_files[0], temp_dir)
                local_path = os.path.join(temp_dir, data_files[0])
        except Exception as e:
            result["status"] = "fail_download"
            result["reason"] = f"zip extraction failed: {str(e)[:80]}"
            return result

    # Load and validate
    try:
        df = _load_dataframe(local_path)
        n_rows, n_cols = df.shape
        result["rows"] = n_rows
        result["cols"] = n_cols

        # Q1: Missing data (>20% of columns have >20% missing)
        missing_pcts = df.isnull().mean()
        high_missing_cols = (missing_pcts > 0.20).sum()
        high_missing_pct = 100 * high_missing_cols / max(n_cols, 1)
        result["high_missing_pct"] = round(high_missing_pct, 1)

        if high_missing_pct > 20:
            result["status"] = "fail_quality"
            result["reason"] = f"Q1: {high_missing_pct:.0f}% cols >20% missing"
            return result

        # Q2: Treatment variable identifiable
        treat_keywords = ["treat", "treatment", "arm", "group", "condition",
                          "assigned", "randomiz", "intervent", "program"]
        has_treat = any(
            any(kw in col.lower() for kw in treat_keywords)
            for col in df.columns
        )
        result["has_treat_var"] = has_treat

        # Q3: Coded column names without codebook
        code_pattern_cols = sum(
            1 for col in df.columns
            if len(col) <= 6 and any(c.isdigit() for c in col)
            and col.lower() not in ("year", "age", "id", "n", "sex")
        )
        coded_pct = 100 * code_pattern_cols / max(n_cols, 1)
        result["coded_cols_pct"] = round(coded_pct, 1)

        if coded_pct > 60:
            result["status"] = "fail_quality"
            result["reason"] = f"Q3: {coded_pct:.0f}% coded column names, no codebook"
            return result

        # Q4: High column/row ratio + high missing
        col_row_ratio = n_cols / max(n_rows, 1)
        result["col_row_ratio"] = round(col_row_ratio, 3)

        if col_row_ratio > 0.40 and high_missing_pct > 20:
            result["status"] = "fail_quality"
            result["reason"] = (f"Q4: col/row ratio={col_row_ratio:.0%} "
                                f"AND {high_missing_pct:.0f}% cols >20% missing")
            return result

        # Q5: Minimum viable size
        if n_rows < 100:
            result["status"] = "fail_quality"
            result["reason"] = f"Too small: {n_rows} rows"
            return result

        result["status"] = "pass"
        del df

    except Exception as e:
        result["status"] = "fail_load"
        result["reason"] = str(e)[:100]

    return result


def main():
    print("=" * 70)
    print("Validating all curated datasets in registry")
    print(f"Total datasets: {len(CURATED_DATASETS)}")
    print("=" * 70)

    # Create temp directory for downloads
    temp_base = tempfile.mkdtemp(prefix="registry_validate_")

    results = []
    passed = []
    failed = []

    # Run validations with thread pool (parallel downloads)
    MAX_WORKERS = 4

    def _validate_one(i_ds):
        i, ds = i_ds
        # Each dataset gets its own temp dir
        ds_dir = os.path.join(temp_base, f"ds_{i}")
        os.makedirs(ds_dir, exist_ok=True)
        return i, validate_dataset(ds, ds_dir)

    print(f"\nDownloading and validating ({MAX_WORKERS} parallel)...\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_validate_one, (i, ds)): i
                   for i, ds in enumerate(CURATED_DATASETS)}

        for future in as_completed(futures):
            i, result = future.result()
            results.append((i, result))
            title = result["title"][:50]
            status = result["status"]

            if status == "pass":
                icon = "PASS"
                passed.append(i)
            else:
                icon = "FAIL"
                failed.append(i)

            reason = f" — {result['reason']}" if result.get("reason") else ""
            dims = (f" ({result['rows']:,}x{result['cols']})"
                    if result['rows'] > 0 else "")

            print(f"  [{len(results):2d}/{len(CURATED_DATASETS)}] "
                  f"[{icon}] {title}{dims}{reason}")

    # Summary
    print(f"\n{'=' * 70}")
    print(f"RESULTS: {len(passed)} passed, {len(failed)} failed")
    print(f"{'=' * 70}")

    if failed:
        print(f"\nFailed datasets:")
        for i in sorted(failed):
            r = [r for _, r in results if _ == i][0]
            print(f"  {i:2d}. {r['title'][:60]}")
            print(f"      Reason: {r['reason']}")

    # Save results
    output_path = Path(__file__).parent / "registry_validation_results.json"
    output_data = {
        "total": len(CURATED_DATASETS),
        "passed": len(passed),
        "failed": len(failed),
        "passed_indices": sorted(passed),
        "failed_indices": sorted(failed),
        "details": {str(i): r for i, r in results},
    }
    output_path.write_text(json.dumps(output_data, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    print(f"\nResults saved: {output_path}")

    # Clean up
    try:
        shutil.rmtree(temp_base)
    except Exception:
        pass

    print(f"\nTo remove failed datasets from registry, run:")
    print(f"  python -m pipeline.validate_registry --clean")

    if "--clean" in sys.argv:
        print(f"\nCleaning registry...")
        registry_path = Path(__file__).parent / "dataset_registry.py"
        content = registry_path.read_text(encoding="utf-8")

        # We can't easily remove entries programmatically from Python source
        # Instead, print the indices to manually remove
        print(f"Remove these indices from CURATED_DATASETS in dataset_registry.py:")
        for i in sorted(failed):
            r = [r for _, r in results if _ == i][0]
            print(f"  [{i}] {r['title'][:60]} — {r['reason']}")


if __name__ == "__main__":
    main()
