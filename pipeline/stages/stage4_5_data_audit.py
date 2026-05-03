"""Stage 4.5 — Data Audit.

Automatic sanity checks on the clean data and script outputs BEFORE
the paper is written. Catches variable construction errors, implausible
distributions, and cell size issues that referees would flag later.

Runs between Stage 4 (code) and Stage 5 (writing).
"""

from datetime import datetime
from pathlib import Path

import pandas as pd

from ..config import get_profile
from ..json_utils import smart_truncate
from ..state import save_state


# ── Known national benchmarks (Peru, approximate) ────────────────────────────
# These are soft targets — flags are warnings, not hard failures.
INSURANCE_BENCHMARKS = {
    "SIS":       {"min_pct": 15, "max_pct": 60, "label": "Seguro Integral de Salud"},
    "EsSalud":   {"min_pct": 15, "max_pct": 45, "label": "EsSalud (formal sector)"},
    "Uninsured": {"min_pct": 3,  "max_pct": 30, "label": "Sin seguro"},
    "Private":   {"min_pct": 0,  "max_pct": 10, "label": "Seguro privado / EPS"},
}

MIN_CELL_SIZE = 30  # Minimum observations per cell for reliable regression


def _read_file_or(path: Path, default: str = "") -> str:
    return path.read_text(encoding="utf-8") if path.exists() else default


def _check_insurance_distribution(df: pd.DataFrame) -> list[dict]:
    """Check if insurance variable distribution matches known national rates."""
    flags = []
    if "insurance_cat" not in df.columns:
        flags.append({
            "severity": "WARNING",
            "category": "variable_construction",
            "detail": "No 'insurance_cat' column found in clean data.",
        })
        return flags

    total = len(df)
    dist = df["insurance_cat"].value_counts()

    for cat, bench in INSURANCE_BENCHMARKS.items():
        n = dist.get(cat, 0)
        pct = 100 * n / total if total > 0 else 0

        if pct < bench["min_pct"]:
            flags.append({
                "severity": "CRITICAL" if pct < bench["min_pct"] / 3 else "WARNING",
                "category": "insurance_distribution",
                "detail": (
                    f"{cat} ({bench['label']}): {n:,} HH ({pct:.1f}%) — "
                    f"expected {bench['min_pct']}-{bench['max_pct']}% nationally. "
                    f"Possible variable miscoding or wrong ENAHO variable used."
                ),
            })
        elif pct > bench["max_pct"]:
            flags.append({
                "severity": "WARNING",
                "category": "insurance_distribution",
                "detail": (
                    f"{cat} ({bench['label']}): {n:,} HH ({pct:.1f}%) — "
                    f"expected {bench['min_pct']}-{bench['max_pct']}% nationally. "
                    f"Check if variable captures a broader category than intended."
                ),
            })

    return flags


def _check_cell_sizes(df: pd.DataFrame, group_cols: list[str]) -> list[dict]:
    """Check for thin cells in key interaction groups."""
    flags = []
    for cols in group_cols:
        available = [c for c in cols if c in df.columns]
        if len(available) != len(cols):
            continue

        cells = df.groupby(available).size().reset_index(name="n")
        thin = cells[cells["n"] < MIN_CELL_SIZE]

        if len(thin) > 0:
            thin_desc = "; ".join(
                f"{dict(row.drop('n'))}: N={row['n']}"
                for _, row in thin.head(10).iterrows()
            )
            flags.append({
                "severity": "WARNING",
                "category": "cell_sizes",
                "detail": (
                    f"{len(thin)} cells with N < {MIN_CELL_SIZE} in "
                    f"{' x '.join(available)}: {thin_desc}"
                ),
            })

    return flags


def _check_outcome_distribution(df: pd.DataFrame) -> list[dict]:
    """Check outcome variable for anomalies."""
    flags = []

    if "oop_share" not in df.columns:
        return flags

    oop = df["oop_share"]
    zero_rate = (oop == 0).mean()
    mean_val = oop.mean()
    max_val = oop.max()

    if zero_rate > 0.60:
        flags.append({
            "severity": "CRITICAL",
            "category": "outcome_distribution",
            "detail": (
                f"Zero-OOP rate = {100*zero_rate:.1f}%. With >60% zeros, "
                f"quantile regression is degenerate at tau < {zero_rate:.2f}. "
                f"Two-part model or censored QR is required as primary specification."
            ),
        })
    elif zero_rate > 0.35:
        flags.append({
            "severity": "WARNING",
            "category": "outcome_distribution",
            "detail": (
                f"Zero-OOP rate = {100*zero_rate:.1f}%. Standard QR is uninformative "
                f"at low quantiles. Report two-part model as complementary analysis."
            ),
        })

    if max_val > 1.0:
        flags.append({
            "severity": "CRITICAL",
            "category": "outcome_distribution",
            "detail": f"OOP share max = {max_val:.4f} > 1.0. Cap not applied correctly.",
        })

    return flags


def _check_sample_size(df: pd.DataFrame) -> list[dict]:
    """Check overall and subgroup sample sizes."""
    flags = []
    n = len(df)

    if n < 500:
        flags.append({
            "severity": "CRITICAL",
            "category": "sample_size",
            "detail": f"Total sample N = {n:,}. Very small for regression analysis.",
        })
    elif n < 2000:
        flags.append({
            "severity": "WARNING",
            "category": "sample_size",
            "detail": f"Total sample N = {n:,}. Consider power limitations.",
        })

    return flags


def _check_weight_distribution(df: pd.DataFrame) -> list[dict]:
    """Check survey weights for extreme values."""
    flags = []
    weight_col = None
    for col in ["FACTOR07", "factor07", "weight", "FACTOR"]:
        if col in df.columns:
            weight_col = col
            break

    if weight_col is None:
        flags.append({
            "severity": "WARNING",
            "category": "survey_weights",
            "detail": "No survey weight column found. Results may not be population-representative.",
        })
        return flags

    w = df[weight_col].dropna()
    if len(w) == 0:
        return flags

    median_w = w.median()
    max_w = w.max()
    ratio = max_w / median_w if median_w > 0 else 0

    if ratio > 50:
        flags.append({
            "severity": "WARNING",
            "category": "survey_weights",
            "detail": (
                f"Extreme weight ratio: max/median = {ratio:.0f}x. "
                f"Max weight = {max_w:,.0f}, median = {median_w:,.0f}. "
                f"Consider winsorizing weights at 99th percentile for robustness."
            ),
        })

    return flags


def _generate_audit_report(flags: list[dict], df: pd.DataFrame) -> str:
    """Generate a markdown audit report."""
    lines = [
        "# Data Audit Report",
        f"\nGenerated: {datetime.now().isoformat()}",
        f"Sample size: {len(df):,} observations",
    ]

    # Summary
    critical = [f for f in flags if f["severity"] == "CRITICAL"]
    warnings = [f for f in flags if f["severity"] == "WARNING"]

    if critical:
        lines.append(f"\n## CRITICAL ISSUES ({len(critical)})")
        lines.append("These must be resolved before proceeding to paper writing.")
        for f in critical:
            lines.append(f"- **[{f['category']}]** {f['detail']}")

    if warnings:
        lines.append(f"\n## WARNINGS ({len(warnings)})")
        lines.append("These should be acknowledged in the paper or addressed if possible.")
        for f in warnings:
            lines.append(f"- **[{f['category']}]** {f['detail']}")

    if not critical and not warnings:
        lines.append("\n## STATUS: ALL CHECKS PASSED")
        lines.append("No anomalies detected in the clean data.")

    # Data summary for referee context
    lines.append("\n## Data Summary (for referee review packet)")

    if "insurance_cat" in df.columns:
        lines.append("\n### Insurance Distribution")
        dist = df["insurance_cat"].value_counts()
        for cat, n in dist.items():
            pct = 100 * n / len(df)
            lines.append(f"- {cat}: {n:,} ({pct:.1f}%)")

    if "quintile" in df.columns and "insurance_cat" in df.columns:
        lines.append("\n### Cell Sizes (quintile x insurance)")
        ct = pd.crosstab(df["quintile"], df["insurance_cat"])
        lines.append(f"```\n{ct.to_string()}\n```")

    if "oop_share" in df.columns:
        oop = df["oop_share"]
        lines.append(f"\n### OOP Share Distribution")
        lines.append(f"- Mean: {oop.mean():.4f}")
        lines.append(f"- Median: {oop.median():.4f}")
        lines.append(f"- Std: {oop.std():.4f}")
        lines.append(f"- Zero rate: {100*(oop==0).mean():.1f}%")
        lines.append(f"- P75: {oop.quantile(0.75):.4f}")
        lines.append(f"- P90: {oop.quantile(0.90):.4f}")
        lines.append(f"- P99: {oop.quantile(0.99):.4f}")

    return "\n".join(lines)


def run(project_dir: Path, state: dict) -> dict:
    """Execute Stage 4.5: data audit on clean data."""

    # Skip if already completed
    if state["stages"].get("stage4_5", {}).get("status") == "completed":
        print("  [4.5] Already completed — skipping.")
        return state

    clean_csv = project_dir / "data" / "clean" / "clean_data.csv"
    audit_dir = project_dir / "quality_reports"
    audit_dir.mkdir(exist_ok=True)

    if not clean_csv.exists():
        print("  [4.5] No clean_data.csv found — skipping audit.")
        state["stages"]["stage4_5"] = {
            "status": "completed",
            "flags": [],
            "completed_at": datetime.now().isoformat(),
        }
        save_state(project_dir, state)
        return state

    print("  [4.5] Running data audit on clean data...")

    try:
        df = pd.read_csv(clean_csv, encoding="latin-1", low_memory=False)
    except Exception as e:
        print(f"  [4.5] Error reading clean data: {e}")
        state["stages"]["stage4_5"] = {
            "status": "completed",
            "flags": [{"severity": "CRITICAL", "category": "file_read",
                       "detail": str(e)}],
            "completed_at": datetime.now().isoformat(),
        }
        save_state(project_dir, state)
        return state

    print(f"  [4.5] Clean data: {len(df):,} rows, {len(df.columns)} columns")

    # Run all checks
    flags = []
    flags.extend(_check_insurance_distribution(df))
    flags.extend(_check_cell_sizes(df, [
        ["quintile", "insurance_cat"],
        ["quintile", "ins_sis"],
    ]))
    flags.extend(_check_outcome_distribution(df))
    flags.extend(_check_sample_size(df))
    flags.extend(_check_weight_distribution(df))

    # Generate and save report
    report = _generate_audit_report(flags, df)
    report_path = audit_dir / "data_audit.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"  [saved] {report_path}")

    # Print summary
    critical = [f for f in flags if f["severity"] == "CRITICAL"]
    warnings = [f for f in flags if f["severity"] == "WARNING"]
    print(f"  [4.5] Audit: {len(critical)} critical, {len(warnings)} warnings")

    for f in critical:
        print(f"  [CRITICAL] {f['detail'][:120]}")
    for f in warnings[:5]:
        print(f"  [WARNING] {f['detail'][:120]}")

    # If critical issues, warn user but don't block
    if critical:
        print(f"\n  {'=' * 60}")
        print(f"  DATA AUDIT: {len(critical)} CRITICAL ISSUE(S) DETECTED")
        print(f"  {'=' * 60}")
        print(f"  Review: {report_path}")
        print(f"  These issues will likely be flagged by referees in Stage 6.")
        print(f"  Consider fixing scripts and re-running Stage 4 before proceeding.")
        print(f"  {'=' * 60}")

    state["stages"]["stage4_5"] = {
        "status": "completed",
        "audit_report": str(report_path),
        "n_critical": len(critical),
        "n_warnings": len(warnings),
        "flags": flags,
        "completed_at": datetime.now().isoformat(),
    }
    save_state(project_dir, state)
    return state
