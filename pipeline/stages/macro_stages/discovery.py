"""Macro track — Stage 1 (seed papers + calibration data plan) and 1.5
(download the calibration series the plan names: FRED, BCRP).

In a model-based paper data disciplines the model (calibration targets,
untargeted moments); it does not identify a causal effect. So Stage 1 looks
for the papers that define the model frontier and for the moments a referee
will expect the model to match.
"""

import json
from datetime import datetime
from pathlib import Path

from ...claude_runner import run_claude
from ...config import get_profile
from ...json_utils import extract_json
from ...macro.model_catalog import MODEL_CLASSES
from ...state import save_state

MACRO_QUERY_SUFFIX = "general equilibrium heterogeneous agents macroeconomics"


def _seed_candidates(topic: str, state: dict) -> list[dict]:
    """Journal-targeted papers first (top-5, macro field journals, NBER/central
    bank working papers), then broad Semantic Scholar/OpenAlex results."""
    from ...macro.literature import scopes_from_state, search_journals
    from ..stage1_discovery import (
        _dedupe_seed_papers,
        _search_openalex_seed_papers,
        _search_semantic_scholar_seed_papers,
    )
    scopes, extra = scopes_from_state(state)
    journal_papers = search_journals(topic, scopes=scopes, extra_journals=extra, max_results=15)
    broad = []
    for q in (f"{topic} {MACRO_QUERY_SUFFIX}", topic):
        broad += _search_semantic_scholar_seed_papers(q, max_results=10)
        broad += _search_openalex_seed_papers(q, max_results=10)
    broad.sort(key=lambda p: p.get("citationCount") or 0, reverse=True)
    return _dedupe_seed_papers(journal_papers + broad)[:25]


def run_stage1(project_dir: Path, topic: str, state: dict, data_path: str | None = None) -> dict:
    print(f"  [macro] Discovery for '{topic}'")
    candidates = _seed_candidates(topic, state)
    cand_text = "\n".join(
        f"{i + 1}. {p.get('authors', '?')} ({p.get('year', '?')}). \"{p.get('title', '')}\". "
        f"{p.get('venue', '')}{' [' + p['venue_tier'] + ']' if p.get('venue_tier') else ''}. "
        f"Citations: {p.get('citationCount', 0)}.\n"
        f"   {(p.get('abstract') or '')[:300]}"
        for i, p in enumerate(candidates)
    ) or "(search returned nothing — rely on canonical references you are certain exist)"

    user_data_block = ""
    profile = None
    if data_path:
        from ..stage1_discovery import _profile_dataset
        profile = _profile_dataset(data_path)
        cols = ", ".join(profile.get("columns", [])[:40])
        user_data_block = (
            f"\nUSER DATA (to compute calibration targets or untargeted moments):\n"
            f"- file: {data_path}\n- rows: {profile.get('rows')}, cols: {profile.get('cols')}\n"
            f"- variables: {cols}\n"
        )

    classes = "\n".join(f"- {k}: {v['name']} (template solver: {'yes' if v['template'] else 'no'})"
                        for k, v in MODEL_CLASSES.items())

    prompt = f"""You are a quantitative macroeconomist (in the style of Benjamin Moll,
Greg Kaplan, Gianluca Violante, Adrien Auclert) preparing a MODEL-BASED paper on:

TOPIC: {topic}

This is NOT an applied-micro paper. Data will discipline a general-equilibrium
model (calibration targets + untargeted moments); it will not identify a
causal effect.

CANDIDATE PAPERS (real papers; [top5]/[macro_field]/[working_papers] = found in
those journals or series via OpenAlex, the rest from broad search):
{cand_text}
{user_data_block}
MODEL CLASSES THE PIPELINE KNOWS:
{classes}

Tasks:
1. Pick the 3 seed papers (from the list above ONLY) that best define the model
   frontier for this topic; say what each contributes (mechanism, method, result).
2. Rank 2-3 model classes from the list that fit the topic and say why.
3. Write a calibration data plan: the moments a referee will expect the model to
   match. For each give a typical value with its source (SCF, PSID, CEX, NIPA,
   FRED, BCRP, ENAHO, ...). When a public time series exists, give its exact
   FRED id (e.g. GDPC1, FEDFUNDS, PCECC96) or BCRP code (e.g. PN01288PM). Mark
   each moment as "targeted" (pins a parameter) or "untargeted" (validation).

Output a JSON block:
```json
{{
  "seed_papers": [{{"title": "...", "authors": "...", "year": 2018, "venue": "...",
                    "contribution": "..."}}],
  "candidate_model_classes": [{{"model_class": "hank", "why": "..."}}],
  "calibration_plan": [{{"moment": "average quarterly MPC", "typical_value": 0.2,
                         "source": "Kaplan and Violante (2014)", "role": "targeted",
                         "fred_series": "", "bcrp_series": ""}}],
  "notes": "..."
}}
```
"""
    p = get_profile("macro_discovery")
    out = project_dir / "stage1_discovery.md"
    response = run_claude(prompt, model=p["model"], effort=p["effort"], output_file=out,
                          allowed_tools=[], label="macro-discovery")
    data = extract_json(response) or {}

    seeds = data.get("seed_papers") or [
        {k: c.get(k) for k in ("title", "authors", "year", "venue")} for c in candidates[:3]
    ]
    state["stages"]["stage1"] = {
        "status": "completed",
        "path": "macro",
        "topic": topic,
        "seed_papers": seeds,
        "candidate_model_classes": data.get("candidate_model_classes", []),
        "calibration_plan": data.get("calibration_plan", []),
        "output_file": str(out),
        "completed_at": datetime.now().isoformat(),
    }
    if data_path:
        state["stages"]["stage1"]["data_path"] = data_path
        state["stages"]["stage1"]["calibration_data_profile"] = profile
    state["current_stage"] = 1
    save_state(project_dir, state)
    print(f"  [ok] {len(seeds)} seed papers, "
          f"{len(state['stages']['stage1']['calibration_plan'])} calibration moments planned")
    return state


class FredUnavailable(Exception):
    """The public FRED endpoint is not answering; stop trying for this run."""


def _fetch_fred(series_id: str, data_dir: Path) -> dict | None:
    """Official FRED API when FRED_API_KEY is set, else the public CSV endpoint
    (which often hangs for non-browser clients)."""
    import os

    import requests

    key = os.environ.get("FRED_API_KEY")
    try:
        if key:
            r = requests.get("https://api.stlouisfed.org/fred/series/observations",
                             params={"series_id": series_id, "api_key": key,
                                     "file_type": "json"}, timeout=30)
            r.raise_for_status()
            obs = r.json().get("observations", [])
            text = "date,value\n" + "\n".join(f"{o['date']},{o['value']}" for o in obs)
        else:
            r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}",
                             timeout=30, headers={"User-Agent": "Mozilla/5.0 (papers-hq)"})
            r.raise_for_status()
            text = r.text
    except requests.exceptions.Timeout as e:
        if not key:
            raise FredUnavailable(str(e)) from e
        print(f"    [fred] {series_id} failed: {e}")
        return None
    except Exception as e:
        print(f"    [fred] {series_id} failed: {e}")
        return None
    path = data_dir / f"fred_{series_id}.csv"
    path.write_text(text, encoding="utf-8")
    values = []
    for line in text.strip().splitlines()[1:]:
        try:
            values.append(float(line.split(",")[1]))
        except (IndexError, ValueError):
            continue
    if not values:
        return None
    return {"series": series_id, "source": "FRED", "local_path": str(path),
            "n_obs": len(values), "last": values[-1], "mean": sum(values) / len(values)}


def run_stage1_5(project_dir: Path, state: dict) -> dict:
    plan = state["stages"].get("stage1", {}).get("calibration_plan", [])
    data_dir = project_dir / "data" / "external"
    data_dir.mkdir(parents=True, exist_ok=True)
    fetched = []
    bcrp = {}
    fred_ok = True
    for item in plan:
        fid = (item.get("fred_series") or "").strip()
        if fid and fred_ok:
            try:
                res = _fetch_fred(fid, data_dir)
            except FredUnavailable as e:
                fred_ok = False
                res = None
                print(f"    [fred] public endpoint not responding ({e}); skipping the rest. "
                      "Set FRED_API_KEY (free at fred.stlouisfed.org) to use the official API.")
            if res:
                res["moment"] = item.get("moment")
                fetched.append(res)
                print(f"    [fred] {fid}: {res['n_obs']} obs, last = {res['last']:.4g}")
        bid = (item.get("bcrp_series") or "").strip()
        if bid:
            bcrp[item.get("moment", bid)[:40]] = bid
    if bcrp:
        from ..stage1_5_data_loading import _try_download_bcrp
        path = _try_download_bcrp({"series": bcrp, "start": "2000-01"}, data_dir)
        if path:
            fetched.append({"series": ",".join(bcrp.values()), "source": "BCRP",
                            "local_path": path})
    state["stages"]["stage1_5"] = {
        "status": "completed",
        "calibration_series": fetched,
        "completed_at": datetime.now().isoformat(),
    }
    (data_dir / "calibration_series.json").write_text(json.dumps(fetched, indent=2),
                                                      encoding="utf-8")
    save_state(project_dir, state)
    print(f"  [ok] {len(fetched)} calibration series downloaded "
          f"(missing ones are filled from the literature in Stage 4)")
    return state
