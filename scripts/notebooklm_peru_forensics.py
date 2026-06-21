"""Audit Peru paper candidates with NotebookLM.

This script turns Stage 1 seed papers or a hand-written URL/DOI list into a
NotebookLM notebook, asks a fixed forensic question, and saves the answer.
It is intentionally separate from the main pipeline so it can be tested without
changing stage behavior.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DOI_RE = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s)>\]]+")

PAPERDL_LIKE_SOURCES = {
    "acl",
    "aclanthology",
    "arxiv",
    "biorxiv",
    "medrxiv",
    "openreview",
    "paperdl",
    "pmc",
    "pmcoa",
    "pmlr",
}


@dataclass
class Candidate:
    title: str
    source: str
    url: str
    doi: str = ""
    authors: str = ""
    year: str = ""
    venue: str = ""
    abstract: str = ""

    @property
    def source_url(self) -> str:
        if self.doi:
            return f"https://doi.org/{self.doi.removeprefix('doi:')}"
        return self.url


def _project_dir(value: str) -> Path:
    p = Path(value)
    if p.exists():
        return p
    return Path(__file__).resolve().parents[1] / "projects" / value


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_doi(*values: Any) -> str:
    for value in values:
        if not value:
            continue
        text = str(value).strip()
        if text.lower().startswith("doi:"):
            text = text[4:].strip()
        match = DOI_RE.search(text)
        if match:
            return match.group(1).rstrip(".,;")
    return ""


def _seed_to_candidate(seed: dict[str, Any]) -> Candidate | None:
    ext = seed.get("externalIds") or {}
    dataset = seed.get("dataset_candidate") or {}
    open_pdf = seed.get("openAccessPdf") or {}
    if not isinstance(open_pdf, dict):
        open_pdf = {}

    doi = _extract_doi(
        seed.get("doi"),
        ext.get("DOI"),
        ext.get("doi"),
        dataset.get("doi"),
        dataset.get("dataverse_doi"),
        seed.get("url"),
        seed.get("replication_package_url"),
    )
    url = (
        open_pdf.get("url")
        or seed.get("url")
        or seed.get("replication_package_url")
        or dataset.get("url")
        or ""
    )
    if not doi and not url:
        return None

    return Candidate(
        title=str(seed.get("title") or dataset.get("name") or doi or url),
        authors=str(seed.get("authors") or ""),
        year=str(seed.get("year") or ""),
        venue=str(seed.get("venue") or dataset.get("provider") or ""),
        source=str(seed.get("source") or dataset.get("source_api") or ""),
        doi=doi,
        url=url,
        abstract=str(seed.get("abstract") or dataset.get("description") or ""),
    )


def _load_candidates_from_state(path: Path) -> list[Candidate]:
    state = _load_json(path)
    seeds = state.get("stages", {}).get("stage1", {}).get("seed_papers", [])
    candidates: list[Candidate] = []
    for seed in seeds:
        if isinstance(seed, dict):
            cand = _seed_to_candidate(seed)
            if cand:
                candidates.append(cand)
    return candidates


def _load_candidates_from_forensics_md(path: Path) -> list[Candidate]:
    text = path.read_text(encoding="utf-8")
    candidates: list[Candidate] = []
    in_source_block = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## Source URLs for NotebookLM"):
            in_source_block = True
            continue
        if in_source_block and line.startswith("## "):
            break
        if not in_source_block:
            continue
        if not line.startswith("- "):
            continue
        url_match = URL_RE.search(line)
        if not url_match:
            continue
        url = url_match.group(0).rstrip(".,")
        candidates.append(Candidate(title=url, source="forensics_md", url=url))
    return candidates


def _manual_candidates(dois: list[str], urls: list[str]) -> list[Candidate]:
    candidates: list[Candidate] = []
    for doi in dois:
        clean = _extract_doi(doi) or doi.removeprefix("doi:").strip()
        candidates.append(Candidate(title=f"DOI {clean}", source="manual_doi", doi=clean, url=""))
    for url in urls:
        doi = _extract_doi(url)
        candidates.append(Candidate(title=url, source="manual_url", doi=doi, url=url))
    return candidates


def _dedupe(candidates: list[Candidate]) -> list[Candidate]:
    seen: set[str] = set()
    out: list[Candidate] = []
    for cand in candidates:
        key = (cand.doi or cand.source_url or cand.title).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(cand)
    return out


def _filter_candidates(
    candidates: list[Candidate],
    doi_only: bool,
    source_filter: set[str] | None,
    paperdl_only: bool,
    peru_only: bool,
    max_sources: int,
) -> list[Candidate]:
    if peru_only:
        candidates = [c for c in candidates if _is_peru_related(c)]
    if doi_only:
        candidates = [c for c in candidates if c.doi]
    if paperdl_only:
        candidates = [c for c in candidates if c.source.lower() in PAPERDL_LIKE_SOURCES]
    if source_filter:
        candidates = [c for c in candidates if c.source.lower() in source_filter]
    return candidates[:max_sources]


def _is_peru_related(candidate: Candidate) -> bool:
    source = candidate.source.lower()
    if source in {"alicia", "bcrp_research", "dspace_peru", "forensics_md", "up_dspace"}:
        return True
    haystack = " ".join(
        [
            candidate.title,
            candidate.authors,
            candidate.venue,
            candidate.abstract,
            candidate.url,
            candidate.doi,
        ]
    ).lower()
    return any(
        token in haystack
        for token in (
            "peru",
            "perú",
            "juntos",
            "young lives",
            "enaho",
            "sinadef",
            "sisfoh",
            "midis",
            "bcrp",
            "inei",
        )
    )


def _run_notebooklm(args: list[str], timeout: int = 180) -> tuple[int, str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    proc = subprocess.run(
        ["notebooklm", *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=env,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _parse_json_output(output: str) -> Any:
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\})", output, flags=re.DOTALL)
        if match:
            return json.loads(match.group(1))
    return None


def _create_notebook(title: str) -> str:
    code, stdout, stderr = _run_notebooklm(["create", title, "--json"], timeout=120)
    if code != 0:
        raise RuntimeError(f"notebooklm create failed: {stderr or stdout}")
    data = _parse_json_output(stdout)
    nb_id = ""
    if isinstance(data, dict):
        nb_id = str(data.get("id") or "")
        if not nb_id and isinstance(data.get("notebook"), dict):
            nb_id = str(data["notebook"].get("id") or "")
    if not nb_id:
        raise RuntimeError(f"Could not parse notebook id from: {stdout}")
    return nb_id


def _add_source(notebook_id: str, content: str, title: str | None = None, source_type: str | None = None) -> str:
    cmd = ["source", "add", content, "--notebook", notebook_id, "--json"]
    if title:
        cmd.extend(["--title", title])
    if source_type:
        cmd.extend(["--type", source_type])
    code, stdout, stderr = _run_notebooklm(cmd, timeout=180)
    if code != 0:
        raise RuntimeError(stderr or stdout)
    data = _parse_json_output(stdout)
    if isinstance(data, dict):
        return str(data.get("source_id") or data.get("id") or "")
    return ""


def _wait_sources(notebook_id: str, source_ids: list[str], timeout: int) -> None:
    for source_id in source_ids:
        if not source_id:
            continue
        code, stdout, stderr = _run_notebooklm(
            ["source", "wait", source_id, "--notebook", notebook_id, "--timeout", str(timeout), "--json"],
            timeout=timeout + 30,
        )
        if code != 0:
            print(f"[warn] source wait failed for {source_id}: {stderr or stdout}", file=sys.stderr)


def _ask(notebook_id: str, question: str) -> dict[str, Any]:
    code, stdout, stderr = _run_notebooklm(["ask", question, "--notebook", notebook_id, "--json"], timeout=240)
    if code != 0:
        raise RuntimeError(f"notebooklm ask failed: {stderr or stdout}")
    data = _parse_json_output(stdout)
    if isinstance(data, dict):
        return data
    return {"answer": stdout}


def _manifest(candidates: list[Candidate]) -> str:
    rows = [
        "# Peru paper candidate manifest",
        "",
        "| # | Title | Source | DOI | URL | Venue | Year |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, cand in enumerate(candidates, 1):
        rows.append(
            "| {i} | {title} | {source} | {doi} | {url} | {venue} | {year} |".format(
                i=i,
                title=_cell(cand.title),
                source=_cell(cand.source),
                doi=_cell(cand.doi),
                url=_cell(cand.source_url),
                venue=_cell(cand.venue),
                year=_cell(cand.year),
            )
        )
    rows.append("")
    rows.append("Use this manifest to map NotebookLM source evidence back to pipeline candidates.")
    return "\n".join(rows)


def _cell(value: str) -> str:
    return (value or "").replace("|", "/").replace("\n", " ")[:300]


def _question() -> str:
    return (
        "For each Peru-related paper/source in this notebook, produce a forensic table with: "
        "paper title, DOI or URL, country relevance, empirical method or identification design, "
        "exact datasets used, whether each dataset is public/open, public but registration/DUA, "
        "private/restricted, paid/commercial, or unclear, evidence quoted/paraphrased from the source, "
        "key treatment/outcome/id/time variables if stated, and a feasibility verdict for writing a "
        "causal paper using only public data. Then rank the top three feasible Peru paper ideas. "
        "Be conservative: if the paper requires DNI linkage, administrative rosters, confidential "
        "firm/patient data, or unavailable replication files, classify it as restricted or unclear."
    )


def _write_outputs(
    output_dir: Path,
    notebook_id: str,
    candidates: list[Candidate],
    answer_data: dict[str, Any] | None,
    dry_run: bool,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    manifest_path = output_dir / f"notebooklm_peru_forensics_manifest_{stamp}.md"
    report_path = output_dir / f"notebooklm_peru_forensics_report_{stamp}.md"

    manifest_path.write_text(_manifest(candidates), encoding="utf-8")

    lines = [
        "# NotebookLM Peru Paper Forensics",
        "",
        f"- Created: {datetime.now().isoformat(timespec='seconds')}",
        f"- Notebook ID: {notebook_id or '(dry run)'}",
        f"- Candidates: {len(candidates)}",
        f"- Dry run: {dry_run}",
        "",
        "## Candidate Manifest",
        "",
        f"See `{manifest_path.name}`.",
        "",
        "## NotebookLM Answer",
        "",
    ]
    if answer_data:
        answer = answer_data.get("answer") if isinstance(answer_data, dict) else str(answer_data)
        lines.append(str(answer or "").strip())
        lines.append("")
        if isinstance(answer_data, dict) and answer_data.get("references"):
            refs = answer_data.get("references", [])
            lines.extend(["## References", ""])
            lines.append(f"Full references are saved in the JSON output. Showing first {min(50, len(refs))} of {len(refs)}.")
            lines.append("")
            for ref in refs[:50]:
                lines.append(f"- {json.dumps(ref, ensure_ascii=False)}")
    else:
        lines.append("(No NotebookLM question was run.)")
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    if answer_data:
        (output_dir / f"notebooklm_peru_forensics_answer_{stamp}.json").write_text(
            json.dumps(answer_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Peru paper data access with NotebookLM.")
    parser.add_argument("--project", help="Project name or path containing pipeline_state.json.")
    parser.add_argument("--state", type=Path, help="Explicit pipeline_state.json path.")
    parser.add_argument("--forensics-md", type=Path, help="Markdown file with 'Source URLs for NotebookLM'.")
    parser.add_argument("--doi", action="append", default=[], help="Manual DOI. Repeatable.")
    parser.add_argument("--url", action="append", default=[], help="Manual URL. Repeatable.")
    parser.add_argument("--title", default="Peru causal data audit", help="NotebookLM notebook title.")
    parser.add_argument("--notebook-id", help="Reuse an existing NotebookLM notebook instead of creating one.")
    parser.add_argument("--max-sources", type=int, default=12, help="Maximum URL/DOI sources to add.")
    parser.add_argument("--doi-only", action="store_true", help="Only keep candidates with DOI.")
    parser.add_argument("--paperdl-only", action="store_true", help="Only keep paperdl-like sources.")
    parser.add_argument("--allow-non-peru", action="store_true", help="Do not filter Stage 1 candidates to Peru-related papers.")
    parser.add_argument("--source-filter", help="Comma-separated source names to keep.")
    parser.add_argument("--output-dir", type=Path, help="Directory for report outputs.")
    parser.add_argument("--dry-run", action="store_true", help="Build manifest only; do not call NotebookLM.")
    parser.add_argument("--source-timeout", type=int, default=120, help="Seconds to wait per source.")
    args = parser.parse_args()

    candidates: list[Candidate] = []
    project_dir: Path | None = None
    if args.project:
        project_dir = _project_dir(args.project)
        args.state = args.state or project_dir / "pipeline_state.json"
    if args.state:
        candidates.extend(_load_candidates_from_state(args.state))
    if args.forensics_md:
        candidates.extend(_load_candidates_from_forensics_md(args.forensics_md))
    candidates.extend(_manual_candidates(args.doi, args.url))

    source_filter = {s.strip().lower() for s in args.source_filter.split(",")} if args.source_filter else None
    candidates = _dedupe(candidates)
    candidates = _filter_candidates(
        candidates,
        doi_only=args.doi_only,
        source_filter=source_filter,
        paperdl_only=args.paperdl_only,
        peru_only=not args.allow_non_peru,
        max_sources=args.max_sources,
    )
    if not candidates:
        raise SystemExit("No candidates found after filters.")

    output_dir = args.output_dir or (project_dir / "notebooklm" if project_dir else Path("notebooklm_peru_forensics"))

    notebook_id = ""
    answer_data: dict[str, Any] | None = None
    if not args.dry_run:
        notebook_id = args.notebook_id or _create_notebook(args.title)
        print(f"[notebooklm] using {notebook_id}")
        source_ids = []
        source_ids.append(_add_source(notebook_id, _manifest(candidates), title="Paper candidate manifest", source_type="text"))
        for cand in candidates:
            print(f"[notebooklm] adding {cand.source_url}")
            try:
                source_ids.append(_add_source(notebook_id, cand.source_url, title=cand.title[:120]))
            except Exception as exc:
                print(f"[warn] add failed for {cand.source_url}: {exc}", file=sys.stderr)
        _wait_sources(notebook_id, source_ids, timeout=args.source_timeout)
        # Give NotebookLM a short moment after the last source flips to ready.
        time.sleep(3)
        answer_data = _ask(notebook_id, _question())

    report_path = _write_outputs(output_dir, notebook_id, candidates, answer_data, dry_run=args.dry_run)
    print(f"[saved] {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
