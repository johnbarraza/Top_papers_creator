"""Stage 1.5 — Data Loading (Path A only).

Downloads datasets identified in Stage 1 and profiles them.
For datasets that cannot be downloaded automatically, shows the user
the URL, title, and time span so they can download manually.

Only runs when Path A was used (no --data flag).
Skipped entirely for Path B (user already provided data).
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import functools
print = functools.partial(print, flush=True)  # type: ignore[assignment]

from ..state import save_state


# ── Filename sanitization ────────────────────────────────────────────────────
#
# Filenames in download responses come from third-party APIs (Dataverse,
# Zenodo, ICPSR, etc.) and CANNOT be trusted: they may contain path
# components ("../"), absolute Windows paths, drive letters, or characters
# that are illegal in NTFS (`: ? * " < > |`).  Without sanitization, an
# entry like "../../../Users/jesus/Desktop/important.csv" would write
# outside the project's data_dir, and a name like "data:2024.csv" would
# crash mid-download on Windows.
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _safe_filename(name: str, *, default: str = "download.bin") -> str:
    """Return a filesystem-safe basename derived from `name`.

    Strips path components, replaces illegal-on-Windows characters with
    underscores, refuses Windows reserved device names, and falls back
    to `default` if the result would be empty or too long.
    """
    if not name:
        return default
    # Drop any directory components (handles both `/` and `\`).
    base = Path(str(name).replace("\\", "/")).name
    # Replace illegal Windows characters.
    cleaned = "".join("_" if c in '<>:"|?*\0' else c for c in base)
    # Strip leading/trailing dots and spaces (also illegal on Windows).
    cleaned = cleaned.strip(" .")
    # Refuse traversal-only or empty results.
    if not cleaned or cleaned in {".", ".."}:
        return default
    # Refuse Windows reserved device names (case-insensitive, with or
    # without extension).
    stem = cleaned.split(".")[0].upper()
    if stem in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    # Cap total length to avoid MAX_PATH issues on Windows.
    if len(cleaned) > 200:
        ext = Path(cleaned).suffix[:32]
        cleaned = cleaned[: 200 - len(ext)] + ext
    return cleaned


# ── Download helpers ──────────────────────────────────────────────────────────

def _try_download_dataverse(url: str, data_dir: Path) -> Optional[str]:
    """Download dataset from Harvard Dataverse DOI URL.

    Dataverse DOIs resolve to a landing page. We use the API to get file URLs.
    """
    import requests

    # Extract DOI or persistent ID from URL
    # Formats: https://doi.org/10.7910/DVN/XXXX or https://dataverse.harvard.edu/dataset.xhtml?persistentId=...
    persistent_id = ""
    if "doi.org/10.7910" in url:
        persistent_id = "doi:" + url.split("doi.org/")[-1]
    elif "persistentId=" in url:
        persistent_id = url.split("persistentId=")[-1].split("&")[0]
    elif "DVN/" in url:
        # Try to extract DVN identifier
        dvn_part = url.split("DVN/")[-1].split("/")[0].split("?")[0]
        persistent_id = f"doi:10.7910/DVN/{dvn_part}"

    if not persistent_id:
        return None

    print(f"    [dataverse] Querying API for {persistent_id}...")
    try:
        # Get dataset files via API
        api_url = f"https://dataverse.harvard.edu/api/datasets/:persistentId/?persistentId={persistent_id}"
        r = requests.get(api_url, timeout=30)
        if r.status_code != 200:
            print(f"    [dataverse] API returned {r.status_code}")
            return None

        data = r.json().get("data", {})
        files = data.get("latestVersion", {}).get("files", [])

        if not files:
            print(f"    [dataverse] No files found in dataset")
            return None

        # Find downloadable data files (prefer .csv, .dta, .tab)
        # Also accept compressed archives (.zip, .rar) as fallback
        PRIORITY_EXTS = {".csv": 4, ".tab": 3, ".dta": 3, ".xlsx": 2, ".parquet": 2, ".zip": 1, ".rar": 1}
        scored_files = []
        for f in files:
            df = f.get("dataFile", {})
            name = df.get("filename", "")
            file_id = df.get("id", "")
            size = df.get("filesize", 0)
            ext = Path(name).suffix.lower()
            score = PRIORITY_EXTS.get(ext, 0)
            max_size = 100 * 1024 * 1024  # 100 MB limit
            if score > 0 and size > 500 and size < max_size:
                scored_files.append((score, size, file_id, name))

        if not scored_files:
            # Log what files were found for debugging
            all_names = [f.get("dataFile", {}).get("filename", "?") for f in files]
            print(f"    [dataverse] No supported data files found. Files: {all_names[:5]}")
            return None

        # Download the best file
        scored_files.sort(key=lambda x: (-x[0], -x[1]))
        _, size, file_id, filename = scored_files[0]
        size_mb = size / (1024 * 1024)
        print(f"    [dataverse] Downloading {filename} ({size_mb:.1f} MB)...")

        dl_url = f"https://dataverse.harvard.edu/api/access/datafile/{file_id}"
        resp = requests.get(dl_url, timeout=120, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 500:
            safe_filename = _safe_filename(filename, default=f"dataverse_{file_id}.bin")
            local_path = data_dir / safe_filename
            local_path.write_bytes(resp.content)
            print(f"    [dataverse] Saved: {safe_filename}")

            # If compressed, try to extract data files from it
            if local_path.suffix.lower() in (".zip", ".rar"):
                extracted = _try_extract(local_path, data_dir)
                if extracted:
                    primary, _all_files = extracted
                    return primary
                # Could not extract — don't return the archive as a "dataset"
                print(f"    [dataverse] Archive downloaded but extraction failed — needs manual extraction")
                return None
            return str(local_path)

        print(f"    [dataverse] Download failed (status {resp.status_code})")
        return None

    except Exception as e:
        print(f"    [dataverse] Error: {e}")
        return None


def _try_download_zenodo(url: str, data_dir: Path) -> Optional[str]:
    """Download dataset from Zenodo record URL."""
    import requests

    # Extract record ID from URL
    # Formats: https://zenodo.org/records/12345 or https://doi.org/10.5281/zenodo.12345
    record_id = ""
    if "zenodo.org/records/" in url:
        record_id = url.split("/records/")[-1].split("/")[0].split("?")[0]
    elif "zenodo.org/record/" in url:
        record_id = url.split("/record/")[-1].split("/")[0].split("?")[0]
    elif "10.5281/zenodo." in url:
        record_id = url.split("zenodo.")[-1].split("/")[0]

    if not record_id:
        return None

    print(f"    [zenodo] Querying API for record {record_id}...")
    try:
        r = requests.get(f"https://zenodo.org/api/records/{record_id}", timeout=30)
        if r.status_code != 200:
            return None

        files = r.json().get("files", [])
        PRIORITY_EXTS = {".csv": 3, ".dta": 2, ".tab": 2, ".xlsx": 1, ".parquet": 1}
        scored_files = []
        for f in files:
            name = f.get("key", "")
            size = f.get("size", 0)
            dl_link = f.get("links", {}).get("self", "")
            ext = Path(name).suffix.lower()
            score = PRIORITY_EXTS.get(ext, 0)
            if score > 0 and size > 500 and dl_link:
                scored_files.append((score, size, dl_link, name))

        if not scored_files:
            print(f"    [zenodo] No data files found")
            return None

        scored_files.sort(key=lambda x: (-x[0], -x[1]))
        _, size, dl_link, filename = scored_files[0]
        size_mb = size / (1024 * 1024)
        print(f"    [zenodo] Downloading {filename} ({size_mb:.1f} MB)...")

        resp = requests.get(dl_link, timeout=120, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 500:
            safe_filename = _safe_filename(filename, default="zenodo_download.bin")
            local_path = data_dir / safe_filename
            local_path.write_bytes(resp.content)
            print(f"    [zenodo] Saved: {safe_filename}")
            return str(local_path)

        return None

    except Exception as e:
        print(f"    [zenodo] Error: {e}")
        return None


EXTRACTION_MANIFEST_NAME = ".extraction_manifest.json"


def _write_extraction_manifest(
    data_dir: Path, archive_name: str, primary: str, all_files: list[str]
) -> None:
    """Persist the relationship between a primary extracted file and its siblings.

    Replication packages typically ship as a single archive containing many
    related .dta/.csv files (treatment, outcomes, baseline, covariates).
    Downstream stages need to know which files belong together so they can
    validate the strategy against the full inventory, not just one file.
    """
    manifest_path = data_dir / EXTRACTION_MANIFEST_NAME
    manifest: dict = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    primary_name = Path(primary).name
    manifest[primary_name] = {
        "archive": archive_name,
        "primary": primary_name,
        "all_files": [Path(p).name for p in all_files],
    }
    # Also index every sibling so any of them can look up the bundle
    for f in all_files:
        fname = Path(f).name
        if fname != primary_name and fname not in manifest:
            manifest[fname] = {
                "archive": archive_name,
                "primary": primary_name,
                "all_files": [Path(p).name for p in all_files],
            }

    # Atomic write: a Ctrl-C between read and write previously left the
    # manifest as a partial JSON, after which `get_bundled_files` silently
    # returned only the file passed in (losing every sibling in the bundle).
    # tempfile + os.replace closes that window — readers either observe the
    # previous good content or the new full content.
    try:
        from ..state import atomic_write_text

        atomic_write_text(
            manifest_path,
            json.dumps(manifest, indent=2, ensure_ascii=False),
        )
    except Exception as e:
        print(f"    [extract] Could not write manifest: {e}")


def get_bundled_files(file_path: str) -> list[str]:
    """Return the list of files that were extracted alongside ``file_path``.

    Always returns a list containing at least ``file_path`` itself. If the
    file came from a multi-file archive, the siblings are appended.
    """
    p = Path(file_path)
    if not p.exists():
        return [file_path]
    manifest_path = p.parent / EXTRACTION_MANIFEST_NAME
    if not manifest_path.exists():
        return [file_path]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return [file_path]
    entry = manifest.get(p.name)
    if not entry:
        return [file_path]
    return [str(p.parent / name) for name in entry.get("all_files", [p.name])]


def _try_extract(archive_path: Path, data_dir: Path) -> Optional[tuple[str, list[str]]]:
    """Extract data files from a compressed archive (.zip, .rar).

    Returns ``(primary_path, all_extracted_paths)`` on success.

    Unlike the previous "largest file only" behavior, this function extracts
    EVERY data file in the archive. Replication packages routinely ship the
    treatment assignment, outcomes, and baseline as separate .dta files —
    discarding all but the largest one breaks any merge-based identification
    strategy. The largest file is still returned as the primary (for
    backward-compatible single-path consumers), but all siblings are
    extracted to disk and recorded in an extraction manifest so downstream
    stages can find them.
    """
    import zipfile

    ext = archive_path.suffix.lower()
    DATA_EXTS = {".csv", ".dta", ".tab", ".xlsx", ".parquet", ".tsv"}
    DOC_KEYWORDS = ("readme", "codebook", "documentation", "data_description")

    def _is_doc(name: str) -> bool:
        lname = name.lower()
        return any(kw in lname for kw in DOC_KEYWORDS) and Path(lname).suffix in (
            ".pdf", ".md", ".txt", ".html", ".rtf",
        )

    if ext == ".zip":
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                members = [
                    n for n in zf.namelist()
                    if not n.startswith("__MACOSX") and not n.endswith("/")
                ]
                data_files = [n for n in members if Path(n).suffix.lower() in DATA_EXTS]
                doc_files = [n for n in members if _is_doc(n)]

                if not data_files:
                    print(f"    [extract] No data files found in zip")
                    return None

                extracted_paths: list[str] = []
                for name in data_files:
                    try:
                        zf.extract(name, data_dir)
                        extracted_paths.append(str(data_dir / name))
                    except Exception as ex:
                        print(f"    [extract] Failed to extract {name}: {ex}")

                # Lightweight docs / codebooks help later stages interpret
                # variable names — extract them too, but don't fail if they
                # blow up.
                for name in doc_files:
                    try:
                        zf.extract(name, data_dir)
                    except Exception:
                        pass

                if not extracted_paths:
                    return None

                primary = max(
                    extracted_paths,
                    key=lambda p: Path(p).stat().st_size if Path(p).exists() else 0,
                )

                if len(extracted_paths) == 1:
                    print(f"    [extract] Extracted: {Path(primary).name}")
                else:
                    sibling_names = sorted(
                        Path(p).name for p in extracted_paths if p != primary
                    )
                    print(
                        f"    [extract] Extracted {len(extracted_paths)} data files "
                        f"(primary: {Path(primary).name}; "
                        f"siblings: {', '.join(sibling_names)})"
                    )
                    _write_extraction_manifest(
                        data_dir, archive_path.name, primary, extracted_paths,
                    )
                return primary, extracted_paths
        except Exception as e:
            print(f"    [extract] Zip extraction failed: {e}")

    elif ext == ".rar":
        try:
            import rarfile
            with rarfile.RarFile(str(archive_path), "r") as rf:
                data_files = [
                    n for n in rf.namelist()
                    if Path(n).suffix.lower() in DATA_EXTS
                ]
                if not data_files:
                    return None
                extracted_paths = []
                for name in data_files:
                    try:
                        rf.extract(name, str(data_dir))
                        extracted_paths.append(str(data_dir / name))
                    except Exception:
                        pass
                if not extracted_paths:
                    return None
                primary = max(
                    extracted_paths,
                    key=lambda p: Path(p).stat().st_size if Path(p).exists() else 0,
                )
                if len(extracted_paths) > 1:
                    sibling_names = sorted(
                        Path(p).name for p in extracted_paths if p != primary
                    )
                    print(
                        f"    [extract] Extracted {len(extracted_paths)} data files "
                        f"(primary: {Path(primary).name}; "
                        f"siblings: {', '.join(sibling_names)})"
                    )
                    _write_extraction_manifest(
                        data_dir, archive_path.name, primary, extracted_paths,
                    )
                else:
                    print(f"    [extract] Extracted: {Path(primary).name}")
                return primary, extracted_paths
        except ImportError:
            print(f"    [extract] .rar file — install 'rarfile' package to extract")
        except Exception as e:
            print(f"    [extract] Rar extraction failed: {e}")

    return None


def _try_download_direct(url: str, data_dir: Path) -> Optional[str]:
    """Try a direct HTTP download (for generic URLs)."""
    import requests

    SUPPORTED_EXTS = {".csv", ".dta", ".xlsx", ".xls", ".parquet", ".tab", ".tsv"}

    try:
        # Check if URL points directly to a data file
        from urllib.parse import urlparse
        parsed = urlparse(url)
        ext = Path(parsed.path).suffix.lower()

        if ext not in SUPPORTED_EXTS:
            return None

        print(f"    [direct] Downloading from {url[:80]}...")
        resp = requests.get(url, timeout=120, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 500:
            filename = Path(parsed.path).name or f"dataset{ext}"
            safe_filename = _safe_filename(filename, default=f"dataset{ext}")
            local_path = data_dir / safe_filename
            local_path.write_bytes(resp.content)
            size_mb = len(resp.content) / (1024 * 1024)
            print(f"    [direct] Saved: {safe_filename} ({size_mb:.1f} MB)")
            return str(local_path)

        return None

    except Exception as e:
        print(f"    [direct] Error: {e}")
        return None


# ── Profiling (reuse from stage1) ─────────────────────────────────────────────

def _profile_dataset(data_path: str) -> dict:
    """Profile a downloaded dataset. Delegates to stage1's profiler."""
    from .stage1_discovery import _profile_dataset as _profile
    return _profile(data_path)


def _early_warning(profile: dict) -> list[str]:
    """Check dataset quality. Delegates to stage1's warning checker."""
    from .stage1_discovery import _early_warning as _warn
    return _warn(profile)


def _causal_design_warning(profile: dict) -> None:
    """Print causal design assessment. Delegates to stage1."""
    from .stage1_discovery import _causal_design_warning as _causal
    return _causal(profile)


# ── Feasibility assessment ─────────────────────────────────────────────────────

def _assess_feasibility(downloaded: list, not_downloaded: list) -> dict:
    """Assess what causal methods the downloaded data can realistically support.

    Goes beyond structure checks to evaluate:
    - Within-unit variation (can FE/DiD detect anything?)
    - Ordinal vs continuous outcomes (power implications)
    - Self-containment (does the dataset need external merges?)
    - Number of treatment events / transitions
    - Clustering capacity

    Returns a dict with: max_tier, tier_label, score_ceiling,
    allowed_methods, forbidden_methods, warnings.
    """
    import pandas as pd

    warnings = []
    max_tier = 4  # start pessimistic
    score_ceiling = 100

    profiles = [item["profile"] for item in downloaded if item.get("profile")]

    if not profiles:
        return {
            "max_tier": 4,
            "tier_label": "DESCRIPTIVE ONLY (no data profiled)",
            "score_ceiling": 40,
            "allowed_methods": ["OLS", "descriptive statistics"],
            "forbidden_methods": ["DiD", "event study", "TWFE", "FE", "IV", "RDD", "synthetic control"],
            "warnings": ["No data was downloaded or profiled."],
        }

    # Find the best profile
    best = max(profiles, key=lambda p: (
        {"panel": 4, "wide-panel": 4, "pooled-cross-sections": 2,
         "repeated-cross-sections": 2, "cross-sectional": 1}.get(p.get("structure", ""), 0),
        p.get("rows", 0),
    ))

    structure = best.get("structure", "cross-sectional")
    rows = best.get("rows", 0)
    cols = best.get("cols", 0)
    panel_details = best.get("panel_details", {})
    id_cols = best.get("id_cols", [])
    n_periods = panel_details.get("n_time_periods", 0)
    time_values = panel_details.get("time_values", [])
    # columns list available in best.get("columns", []) if needed

    # Try to load actual data for deeper checks
    best_item = None
    for item in downloaded:
        if item.get("profile") == best:
            best_item = item
            break
    df = None
    if best_item and best_item.get("local_path"):
        try:
            local_path = best_item["local_path"]
            ext = Path(local_path).suffix.lower()
            if ext == ".csv":
                df = pd.read_csv(local_path, low_memory=False)
            elif ext in (".xls", ".xlsx"):
                df = pd.read_excel(local_path)
            elif ext == ".dta":
                df = pd.read_stata(local_path)
            elif ext in (".tab", ".tsv"):
                df = pd.read_csv(local_path, sep="\t", low_memory=False)
            elif ext == ".parquet":
                df = pd.read_parquet(local_path)
        except Exception:
            df = None

    # ══════════════════════════════════════════════════════════════════
    # CHECK 1: Data structure
    # ══════════════════════════════════════════════════════════════════
    if structure in ("panel", "wide-panel"):
        max_tier = min(max_tier, 1)
    elif structure in ("pooled-cross-sections", "repeated-cross-sections"):
        max_tier = min(max_tier, 2)
        warnings.append(f"Structure is {structure} — individual FE not feasible.")
    else:
        max_tier = min(max_tier, 3)
        score_ceiling = min(score_ceiling, 75)
        warnings.append("Cross-sectional data — DiD, event study, FE not feasible.")

    # ══════════════════════════════════════════════════════════════════
    # CHECK 2: Sample size
    # ══════════════════════════════════════════════════════════════════
    if rows < 500:
        score_ceiling = min(score_ceiling, 70)
        warnings.append(f"Small sample ({rows:,} rows). Power insufficient for subgroups.")
    elif rows < 1000:
        score_ceiling = min(score_ceiling, 80)
        warnings.append(f"Moderate sample ({rows:,} rows). Limited subgroup power.")

    # ══════════════════════════════════════════════════════════════════
    # CHECK 3: Number of variables (self-containment)
    # ══════════════════════════════════════════════════════════════════
    if cols < 10:
        score_ceiling = min(score_ceiling, 75)
        warnings.append(f"Few variables ({cols} cols). Likely needs external merge "
                        "for treatment or controls — adds complexity and merge attrition.")
    if cols < 5:
        score_ceiling = min(score_ceiling, 60)
        warnings.append(f"Very few variables ({cols} cols). Cannot support a self-contained "
                        "research design. Needs extensive external data.")

    # ══════════════════════════════════════════════════════════════════
    # CHECK 4: Time coverage
    # ══════════════════════════════════════════════════════════════════
    if n_periods > 0:
        if n_periods < 4:
            score_ceiling = min(score_ceiling, 70)
            warnings.append(f"Only {n_periods} time periods — insufficient for event study.")
        elif n_periods < 8:
            score_ceiling = min(score_ceiling, 85)
            warnings.append(f"{n_periods} time periods — limited event study dynamics.")

        if time_values:
            try:
                numeric_times = sorted([int(t) for t in time_values if str(t).isdigit()])
                if numeric_times:
                    earliest = numeric_times[0]
                    if earliest >= 2020:
                        score_ceiling = min(score_ceiling, 65)
                        warnings.append(f"Data starts at {earliest} — no pre-COVID baseline.")
                    elif earliest >= 2018:
                        score_ceiling = min(score_ceiling, 80)
                        warnings.append(f"Data starts at {earliest} — limited pre-treatment.")
            except (ValueError, TypeError):
                pass

    # ══════════════════════════════════════════════════════════════════
    # CHECK 5: Missingness
    # ══════════════════════════════════════════════════════════════════
    high_miss_vars = []
    for profile in profiles:
        miss_pct = profile.get("missing_pct", {})
        for var, pct in miss_pct.items():
            if pct > 40:
                high_miss_vars.append(f"{var} ({pct:.0f}%)")
    if high_miss_vars:
        score_ceiling = min(score_ceiling, 85)
        warnings.append(f"High missingness: {', '.join(high_miss_vars[:5])}")

    # ══════════════════════════════════════════════════════════════════
    # CHECK 6: ORDINAL / LOW-VARIATION OUTCOMES (NEW)
    # ══════════════════════════════════════════════════════════════════
    n_ordinal = 0
    n_continuous = 0
    ordinal_vars = []

    if df is not None:
        numeric_cols = df.select_dtypes(include="number").columns
        for col in numeric_cols:
            nunique = df[col].nunique()
            if 2 <= nunique <= 7:
                n_ordinal += 1
                ordinal_vars.append(f"{col} ({nunique} values)")
            elif nunique > 7:
                n_continuous += 1

        if n_ordinal > 0 and n_continuous == 0:
            score_ceiling = min(score_ceiling, 70)
            warnings.append(
                f"ALL numeric variables are ordinal ({n_ordinal} vars with <=7 unique values). "
                f"Variables: {', '.join(ordinal_vars[:5])}. "
                "Within-unit variation will be very low — TWFE/FE estimates will have poor "
                "power. Consider continuous outcome data instead."
            )
        elif n_ordinal > n_continuous:
            score_ceiling = min(score_ceiling, 80)
            warnings.append(
                f"Majority ordinal variables ({n_ordinal} ordinal vs {n_continuous} continuous). "
                "Power for FE/DiD may be limited."
            )

    # ══════════════════════════════════════════════════════════════════
    # CHECK 7: WITHIN-UNIT VARIATION (NEW)
    # ══════════════════════════════════════════════════════════════════
    if df is not None and structure in ("panel", "wide-panel") and id_cols:
        id_col = id_cols[0]
        if id_col in df.columns:
            numeric_cols = df.select_dtypes(include="number").columns.tolist()
            # Exclude ID and time columns
            outcome_candidates = [c for c in numeric_cols
                                   if c not in id_cols and c.lower() not in ("year", "anio")]

            low_within_vars = []
            for col in outcome_candidates[:15]:
                try:
                    within_std = df.groupby(id_col)[col].transform("std").mean()
                    total_std = df[col].std()
                    if total_std > 0:
                        within_ratio = within_std / total_std
                        if within_ratio < 0.15:
                            low_within_vars.append(f"{col} (within/total={within_ratio:.2f})")
                except Exception:
                    pass

            if low_within_vars and len(low_within_vars) >= len(outcome_candidates[:15]) * 0.5:
                score_ceiling = min(score_ceiling, 70)
                warnings.append(
                    f"LOW WITHIN-UNIT VARIATION in {len(low_within_vars)}/{len(outcome_candidates[:15])} "
                    f"variables: {', '.join(low_within_vars[:5])}. "
                    "Most variation is between countries, not within countries over time. "
                    "FE/DiD will absorb most variation, leaving little signal. "
                    "Power for detecting treatment effects will be very low."
                )
            elif low_within_vars:
                warnings.append(
                    f"Some variables have low within-unit variation: "
                    f"{', '.join(low_within_vars[:3])}. "
                    "Consider using these as controls, not outcomes."
                )

    # ══════════════════════════════════════════════════════════════════
    # CHECK 8: TREATMENT TRANSITIONS / EVENTS (NEW)
    # ══════════════════════════════════════════════════════════════════
    if df is not None and structure in ("panel", "wide-panel") and id_cols:
        id_col = id_cols[0]
        if id_col in df.columns:
            # Count how many units have ANY change in their variables over time
            numeric_cols = df.select_dtypes(include="number").columns.tolist()
            outcome_candidates = [c for c in numeric_cols
                                   if c not in id_cols and c.lower() not in ("year", "anio")]

            n_units = df[id_col].nunique()
            changing_units = 0
            total_transitions = 0

            for col in outcome_candidates[:10]:
                try:
                    changes = df.groupby(id_col)[col].apply(
                        lambda x: (x.diff().abs() > 0).sum()
                    )
                    units_with_change = (changes > 0).sum()
                    total_trans = changes.sum()
                    if units_with_change > changing_units:
                        changing_units = units_with_change
                        total_transitions = total_trans
                except Exception:
                    pass

            if changing_units > 0:
                pct_changing = changing_units / n_units * 100
                if pct_changing < 20:
                    score_ceiling = min(score_ceiling, 65)
                    warnings.append(
                        f"Only {pct_changing:.0f}% of units ({changing_units}/{n_units}) show "
                        f"any change over time ({total_transitions} total transitions). "
                        "Very few 'treatment events' — FE/DiD will have almost no identifying "
                        "variation. Consider a different dataset with more within-unit changes."
                    )
                elif pct_changing < 40:
                    score_ceiling = min(score_ceiling, 80)
                    warnings.append(
                        f"{pct_changing:.0f}% of units change over time. Moderate identifying "
                        "variation — adequate for main effects but limited for heterogeneity."
                    )

    # ══════════════════════════════════════════════════════════════════
    # CHECK 9: CLUSTERING CAPACITY (NEW)
    # ══════════════════════════════════════════════════════════════════
    if df is not None and id_cols:
        id_col = id_cols[0]
        if id_col in df.columns:
            n_clusters = df[id_col].nunique()
            if n_clusters < 30:
                score_ceiling = min(score_ceiling, 70)
                warnings.append(
                    f"Only {n_clusters} clusters — below 30 threshold. "
                    "Cluster-robust SEs unreliable. Wild bootstrap required but may lack power."
                )
            elif n_clusters < 50:
                score_ceiling = min(score_ceiling, 85)
                warnings.append(
                    f"{n_clusters} clusters — borderline. Wild cluster bootstrap recommended."
                )

    # ══════════════════════════════════════════════════════════════════
    # CHECK 10: SELF-CONTAINMENT SCORE (NEW)
    # ══════════════════════════════════════════════════════════════════
    # A dataset that has both plausible treatment AND outcome variables
    # is self-contained. One that only has outcomes (or only treatments)
    # will need external data, which adds risk.
    has_binary = False
    has_continuous_outcome = False
    if df is not None:
        numeric_cols = df.select_dtypes(include="number").columns
        for col in numeric_cols:
            nunique = df[col].nunique()
            if nunique == 2:
                has_binary = True  # potential treatment indicator
            elif nunique > 20:
                has_continuous_outcome = True

    self_contained = has_binary and has_continuous_outcome
    if not self_contained and cols < 15:
        score_ceiling = min(score_ceiling, 75)
        warnings.append(
            "Dataset may not be self-contained: "
            + ("no binary treatment variable found. " if not has_binary else "")
            + ("no continuous outcome variable found. " if not has_continuous_outcome else "")
            + "Ideas should avoid designs requiring extensive external data merges."
        )

    # ══════════════════════════════════════════════════════════════════
    # DETERMINE ALLOWED/FORBIDDEN METHODS
    # ══════════════════════════════════════════════════════════════════
    tier_methods = {
        1: {
            "allowed": ["DiD", "staggered DiD", "event study", "IV/2SLS", "RDD",
                        "synthetic control", "TWFE", "individual FE"],
            "label": "CAUSAL (all methods available)",
        },
        2: {
            "allowed": ["group-level DiD", "repeated cross-section DiD", "IV/2SLS",
                        "RDD", "synthetic control", "cohort analysis",
                        "Oaxaca-Blinder", "quantile regression"],
            "forbidden": ["individual FE", "individual event study",
                          "Arellano-Bond", "Markov transitions"],
            "label": "GROUP-LEVEL CAUSAL (no individual tracking)",
        },
        3: {
            "allowed": ["IV/2SLS", "RDD", "matching (PSM/CEM)", "Oaxaca-Blinder",
                        "Heckman selection", "quantile regression"],
            "forbidden": ["DiD", "event study", "TWFE", "individual FE",
                          "synthetic control", "Arellano-Bond"],
            "label": "CROSS-SECTIONAL CAUSAL (IV, RDD only)",
        },
        4: {
            "allowed": ["OLS", "probit/logit", "descriptive statistics",
                        "correlational analysis"],
            "forbidden": ["DiD", "event study", "TWFE", "FE", "IV", "RDD",
                          "synthetic control", "Arellano-Bond"],
            "label": "DESCRIPTIVE ONLY",
        },
    }

    tier_info = tier_methods.get(max_tier, tier_methods[4])

    return {
        "max_tier": max_tier,
        "tier_label": tier_info["label"],
        "score_ceiling": score_ceiling,
        "allowed_methods": tier_info["allowed"],
        "forbidden_methods": tier_info.get("forbidden", []),
        "warnings": warnings,
        "best_structure": structure,
        "best_rows": rows,
        "best_cols": cols,
        "n_periods": n_periods,
        "n_ordinal_vars": n_ordinal,
        "n_continuous_vars": n_continuous,
        "self_contained": self_contained,
    }


# ── Main runner ───────────────────────────────────────────────────────────────

def run(project_dir: Path, state: dict) -> dict:
    """Execute Stage 1.5: Download and profile datasets (Path A only)."""
    stage1 = state["stages"].get("stage1", {})
    path = stage1.get("path", "A")

    # Skip for Path B — data already profiled in Stage 1
    if path == "B" or stage1.get("data_profile"):
        print("  [skip] Path B — data already profiled in Stage 1")
        state["stages"]["stage1_5"] = {
            "status": "skipped",
            "reason": "Path B or data already profiled",
        }
        save_state(project_dir, state)
        return state

    data_sources = stage1.get("recommended_data_sources", [])
    if not data_sources:
        print("  [skip] No recommended data sources from Stage 1")
        state["stages"]["stage1_5"] = {
            "status": "skipped",
            "reason": "No data sources found",
        }
        save_state(project_dir, state)
        return state

    try:
        import requests
    except ImportError:
        print("  [error] 'requests' package required. Run: pip install requests")
        sys.exit(1)

    data_dir = project_dir / "data" / "external"
    data_dir.mkdir(parents=True, exist_ok=True)

    downloaded = []   # [(dataset_info, local_path, profile)]
    not_downloaded = []  # [dataset_info]

    print(f"\n  Attempting to download {len(data_sources)} datasets...\n")

    for i, ds in enumerate(data_sources, 1):
        name = ds.get("name", "Unknown")[:70]
        url = ds.get("url", "")
        provider = ds.get("provider", "").lower()
        print(f"  [{i}/{len(data_sources)}] {name}")
        print(f"       URL: {url}")

        local_path = None

        # Try provider-specific downloaders
        if "dataverse" in provider or "doi.org/10.7910" in url or "dataverse" in url:
            local_path = _try_download_dataverse(url, data_dir)
        elif "zenodo" in provider or "zenodo.org" in url or "10.5281/zenodo" in url:
            local_path = _try_download_zenodo(url, data_dir)

        # Fallback: try direct download
        if not local_path:
            local_path = _try_download_direct(url, data_dir)

        if local_path:
            print(f"       [ok] Downloaded successfully")
            try:
                profile = _profile_dataset(local_path)
                warnings = _early_warning(profile)
                print(f"       [ok] Profiled: {profile['rows']:,} rows x {profile['cols']} cols\n")
                downloaded.append({
                    "dataset": ds,
                    "local_path": local_path,
                    "profile": profile,
                    "warnings": warnings,
                })
            except Exception as e:
                print(f"       [warn] Downloaded but could not profile: {e}\n")
                downloaded.append({
                    "dataset": ds,
                    "local_path": local_path,
                    "profile": None,
                    "warnings": [],
                })
        else:
            # Could not download/extract — ask user for manual paths
            print(f"       [!] Could not download automatically")
            print(f"       Options:")
            print(f"         1 - Provide path to a single data file")
            print(f"         2 - Provide paths to multiple data files (comma-separated)")
            print(f"         3 - Skip this dataset")
            print("\a", end="", flush=True)

            while True:
                choice = input(f"\n       >> ").strip()

                if choice == "3" or choice.lower() == "skip":
                    print(f"       [skip] Skipping this dataset\n")
                    not_downloaded.append(ds)
                    break

                elif choice == "1":
                    user_path = input(f"       File path: ").strip().strip('"')
                    if user_path and Path(user_path).exists():
                        try:
                            profile = _profile_dataset(user_path)
                            warnings = _early_warning(profile)
                            print(f"       [ok] Profiled: {profile['rows']:,} rows x {profile['cols']} cols\n")
                            downloaded.append({
                                "dataset": ds,
                                "local_path": user_path,
                                "profile": profile,
                                "warnings": warnings,
                            })
                            break
                        except Exception as e:
                            print(f"       [error] Could not profile: {e}")
                    else:
                        print(f"       [!] File not found: {user_path}")

                elif choice == "2":
                    paths_input = input(f"       File paths (comma-separated): ").strip()
                    paths = [p.strip().strip('"') for p in paths_input.split(",") if p.strip()]
                    profiled_any = False
                    for user_path in paths:
                        if Path(user_path).exists():
                            try:
                                profile = _profile_dataset(user_path)
                                warnings = _early_warning(profile)
                                fname = Path(user_path).name
                                print(f"       [ok] {fname}: {profile['rows']:,} rows x {profile['cols']} cols")
                                downloaded.append({
                                    "dataset": ds,
                                    "local_path": user_path,
                                    "profile": profile,
                                    "warnings": warnings,
                                })
                                profiled_any = True
                            except Exception as e:
                                print(f"       [error] {Path(user_path).name}: {e}")
                        else:
                            print(f"       [!] Not found: {user_path}")
                    if profiled_any:
                        print()
                        break
                    else:
                        print(f"       No files profiled. Try again or enter 3 to skip.")

                else:
                    print(f"       Enter 1, 2, or 3.")

    # ── Show results ──────────────────────────────────────────────────────
    print(f"\n  {'=' * 60}")
    print(f"  STAGE 1.5 — DATA LOADING RESULTS")
    print(f"  {'=' * 60}")

    if downloaded:
        print(f"\n  DOWNLOADED ({len(downloaded)}):")
        for i, item in enumerate(downloaded, 1):
            ds = item["dataset"]
            profile = item["profile"]
            print(f"\n    [{i}] {ds.get('name', '?')[:70]}")
            print(f"        File: {Path(item['local_path']).name}")
            if profile:
                print(f"        Rows: {profile['rows']:,}")
                print(f"        Columns: {profile['cols']}")
                print(f"        Structure: {profile['structure']}")
                if profile.get("id_cols"):
                    print(f"        ID cols: {', '.join(profile['id_cols'][:5])}")
                if profile.get("time_cols"):
                    print(f"        Time cols: {', '.join(profile['time_cols'][:5])}")
                # Show key variable names
                key_vars = profile.get("columns", [])[:20]
                if key_vars:
                    print(f"        Variables: {', '.join(key_vars[:10])}")
                    if len(key_vars) > 10:
                        print(f"                   ... ({profile['cols']} total)")
                if item["warnings"]:
                    for w in item["warnings"]:
                        print(f"        [!] {w}")

    if not_downloaded:
        print(f"\n  NOT DOWNLOADED ({len(not_downloaded)}) — download manually:")
        for i, ds in enumerate(not_downloaded, 1):
            print(f"\n    [{i}] {ds.get('name', '?')[:70]}")
            print(f"        URL:       {ds.get('url', 'N/A')}")
            print(f"        Provider:  {ds.get('provider', 'N/A')}")
            print(f"        Structure: {ds.get('data_structure', 'N/A')}")
            print(f"        Time span: {ds.get('time_span', 'N/A')}")
            print(f"        Access:    {ds.get('access', 'N/A')}")
            files = ds.get("files_needed", [])
            if files:
                print(f"        Files:     {', '.join(files[:5])}")

    # ── If nothing downloaded, final chance to provide paths ────────────
    if not downloaded:
        print(f"\n  No datasets were downloaded or provided.")
        print(f"  Enter a file path to profile, or 'skip' to continue without data.\n")
        print("\a", end="", flush=True)
        while True:
            choice = input("  >> ").strip().strip('"')
            if choice.lower() == "skip":
                print("  [ok] Continuing without local data.")
                break
            elif choice and Path(choice).exists():
                try:
                    profile = _profile_dataset(choice)
                    warnings = _early_warning(profile)
                    downloaded.append({
                        "dataset": data_sources[0] if data_sources else {"name": Path(choice).name},
                        "local_path": choice,
                        "profile": profile,
                        "warnings": warnings,
                    })
                    print(f"  [ok] Profiled: {profile['rows']:,} rows x {profile['cols']} cols")
                    break
                except Exception as e:
                    print(f"  [error] Could not profile: {e}")
            else:
                print(f"  File not found: {choice}")

    # ── Show causal design warning for best downloaded dataset ────────────
    if downloaded:
        best = None
        for item in downloaded:
            if item["profile"]:
                best = item
                break
        if best:
            print()
            _causal_design_warning(best["profile"])

    # ── FEASIBILITY ASSESSMENT ─────────────────────────────────────────────
    # Determine what methods the data can actually support, and set a
    # realistic score ceiling so Stage 2 doesn't propose impossible designs.
    feasibility = _assess_feasibility(downloaded, not_downloaded)
    print(f"\n  {'=' * 60}")
    print(f"  FEASIBILITY ASSESSMENT")
    print(f"  {'=' * 60}")
    print(f"  Max method tier: {feasibility['max_tier']} ({feasibility['tier_label']})")
    print(f"  Score ceiling:   {feasibility['score_ceiling']}/100")
    print(f"  Allowed methods: {', '.join(feasibility['allowed_methods'])}")
    if feasibility["forbidden_methods"]:
        print(f"  Forbidden:       {', '.join(feasibility['forbidden_methods'])}")
    if feasibility["warnings"]:
        print(f"\n  Data limitations:")
        for w in feasibility["warnings"]:
            print(f"    - {w}")
    print(f"  {'=' * 60}")

    print(f"\n  {'=' * 60}")

    # ── Save to state ─────────────────────────────────────────────────────
    state["stages"]["stage1_5"] = {
        "status": "completed",
        "completed_at": datetime.now().isoformat(),
        "n_downloaded": len(downloaded),
        "n_not_downloaded": len(not_downloaded),
        "feasibility": feasibility,
    }

    # Save profiles of downloaded datasets
    if downloaded:
        profiles = []
        for item in downloaded:
            entry = {
                "name": item["dataset"].get("name", ""),
                "local_path": item["local_path"],
                "warnings": item["warnings"],
            }
            if item["profile"]:
                entry["profile"] = {
                    "rows": item["profile"]["rows"],
                    "cols": item["profile"]["cols"],
                    "columns": item["profile"]["columns"],
                    "structure": item["profile"]["structure"],
                    "panel_flag": item["profile"]["panel_flag"],
                    "panel_details": item["profile"].get("panel_details", {}),
                    "id_cols": item["profile"].get("id_cols", []),
                    "time_cols": item["profile"].get("time_cols", []),
                    "wide_panel": item["profile"].get("wide_panel"),
                    "data_summary": item["profile"].get("data_summary", ""),
                }
            profiles.append(entry)

        state["stages"]["stage1_5"]["downloaded_datasets"] = profiles

        # Also set the primary data_profile (best downloaded) for downstream stages
        for item in downloaded:
            if item["profile"]:
                state["stages"]["stage1"]["data_path"] = item["local_path"]
                state["stages"]["stage1"]["data_profile"] = {
                    "rows": item["profile"]["rows"],
                    "cols": item["profile"]["cols"],
                    "columns": item["profile"]["columns"],
                    "structure": item["profile"]["structure"],
                    "panel_flag": item["profile"]["panel_flag"],
                    "panel_details": item["profile"].get("panel_details", {}),
                    "id_cols": item["profile"].get("id_cols", []),
                    "time_cols": item["profile"].get("time_cols", []),
                    "wide_panel": item["profile"].get("wide_panel"),
                }
                break

    if not_downloaded:
        state["stages"]["stage1_5"]["not_downloaded"] = [
            {
                "name": ds.get("name", ""),
                "url": ds.get("url", ""),
                "provider": ds.get("provider", ""),
                "data_structure": ds.get("data_structure", ""),
                "time_span": ds.get("time_span", ""),
            }
            for ds in not_downloaded
        ]

    save_state(project_dir, state)
    return state
