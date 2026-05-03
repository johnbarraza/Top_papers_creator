# Papers-HQ: Orchestration Pipeline

## Quick Start

```bash
# Path A: Discover repositories and papers automatically
python papers-HQ/run_pipeline.py --topic "Economics"

# Path B: Use your own dataset (URL or local file)
python papers-HQ/run_pipeline.py --topic "Economics" --data "https://example.com/panel_data.csv"
python papers-HQ/run_pipeline.py --topic "Economics" --data "./my_dataset.dta"

# Run with a custom project name
python papers-HQ/run_pipeline.py --topic "Education policy" --project education_2026

# Run only specific stages
python papers-HQ/run_pipeline.py --topic "Public Health" --to-stage 3

# Resume from a specific stage (reuses previous outputs)
python papers-HQ/run_pipeline.py --from-stage 4 --project education_2026

# Check project status
python papers-HQ/run_pipeline.py --status education_2026
```

### Project Structure (auto-generated)
```
papers-HQ/projects/my_project/
  pipeline_state.json       # Pipeline state and handoff data
  stage1_discovery.md       # GitHub repos + 3 seed papers (Path A) or dataset analysis + 3 papers (Path B)
  user_data/                # User-provided dataset (Path B only)
  stage2_ideation.md        # 8-10 ideas, top 3 ranked
  selected_idea.md          # User-selected idea from top 3
  stage3_validation.md      # 8-step evaluation results
  approved_strategy.md      # User-approved identification strategy
  evaluation/
    idea.txt                # Formatted idea template
  paper/
    PROMPT.md               # Research prompt for Clo-Author
    main.tex                # Final LaTeX paper
    sections/               # Section-level .tex files
    tables/                 # Publication-ready tables (.tex)
    figures/                # Publication-ready figures (.pdf, .png)
    replication/            # AEA-compliant replication package
  scripts/
    python/                 # Analysis scripts (Python only)
  quality_reports/
    strategy_memo.md        # Formalized identification strategy
    robustness_plan.md      # Robustness checks plan
    reviews/                # Referee reports + editorial decisions
```

## Overview

This pipeline connects Papers-HQ (Stages 1–3) with Clo-Author (Stages 4–7) to produce high-quality academic papers end-to-end. Two human-in-the-loop checkpoints ensure the user controls the most critical decisions: which idea to pursue (Stage 2.5) and which identification strategy to execute (Stage 3.5).

All analysis code uses **Python exclusively**.

```
Papers-HQ                                        Checkpoints       Clo-Author
──────────────────────────────────────────────  ──────────────  ──────────────────────────────

Path A: --topic only
  search-repos ──┐
   (Stage 1A)    ├→ research-junshi → USER → idea-eval → USER → strategist+coder → writer → peer-review → submission
Path B: --data   │    (Stage 2)      (2.5)  (Stage 3)   (3.5)    (Stage 4)       (Stage 5)   (Stage 6)    (Stage 7)
  analyze-data ──┘
   (Stage 1B)
```

---

## Stage 1: Discovery

**Goal:** Obtain a dataset foundation and 3 related academic papers to seed the ideation stage. The user chooses one of two paths:

### Path A: Repository Search — `search-repositories/` (default)

Triggered when the user provides only `--topic`.

**Input:** A thematic area of interest (e.g., Education, Economics, Political Science).

**Process:**
1. Search GitHub for replication packages of peer-reviewed papers (minimum 50 stars or 20 forks).
2. Group results by broad thematic area and rank by total star score.
3. User selects a thematic area.
4. Web search returns 3 published academic papers related to the selected area.

**Output:**
- List of GitHub repositories with: repo URL, paper title, journal, DOI, dataset format.
- 3 related academic papers with: title, authors, journal, year, DOI, 2-sentence summary.

### Path B: User-Provided Data — `analyze-data/`

Triggered when the user provides `--data <URL|filepath>`.

**Input:**
- A thematic area of interest (`--topic`).
- A dataset provided by the user (URL or local file: `.csv`, `.dta`, `.parquet`, `.xlsx`, etc.).

**Process:**
1. Load and inspect the dataset: variables, types, N observations, temporal/geographic coverage, structure (cross-section, panel, time-series).
2. **Early warning check:** If the dataset appears inadequate for research (e.g., very few observations, very few variables, no variation), display a warning to the user: *"⚠ This dataset has N=47 observations and 3 variables — are you sure you want to proceed?"*. The user can confirm or provide a different dataset.
3. Profile the data: key summary statistics, missingness patterns, potential outcome/treatment variables.
4. Web search for 3 published academic papers related to: (a) the thematic area specified in `--topic`, (b) the context of the data (e.g., labor economics in LATAM if the dataset is Mexican employment panel), and (c) methodologies applicable to this data structure (e.g., DiD for panel data, RDD for threshold data).

**Output:**
- Dataset profile: variables, types, N obs, coverage, structure, summary statistics.
- 3 related academic papers with: title, authors, journal, year, DOI, 2-sentence summary.

### Handoff to Stage 2

Both paths produce the same handoff format:
- 3 academic papers (title, authors, DOI, summary) serve as seed papers for research-junshi.
- Dataset context (either from discovered repositories or from user-provided data analysis) informs the ideation.

---

## Stage 2: Ideation — `research-junshi/`

**Goal:** Generate and rank novel research ideas based on the seed papers from Stage 1.

**Input:**
- Seed papers from Stage 1 (titles, DOIs, summaries).
- Configuration: research area, target venues, notification preferences.

**Process (Daily Digest Workflow):**
1. Read the seed papers from Stage 1.
2. Search arXiv and academic venues for related recent work.
3. Cross-reference findings with seed paper themes.
4. Generate candidate research ideas.
5. Rank ideas by novelty (×0.4), feasibility (×0.3), and impact (×0.3).
6. Compile a structured digest of top-ranked ideas.
7. Output the digest with ranked ideas.

**Output:**
- Ranked list of research ideas, each containing:
  - Research question
  - Proposed methodology
  - Composite score (N×0.4 + F×0.3 + I×0.3)
  - Connection to existing literature

**Handoff to Stage 2.5:** The top 3 ranked ideas (with scores and justifications) are presented to the user for selection.

---

## Stage 2.5: Idea Selection — Human-in-the-Loop

**Goal:** Let the user choose which research idea to pursue, based on the ranked output from Stage 2.

**Input:** Top 3 ranked ideas from Stage 2, each with:
- Research question
- Proposed methodology
- Composite score (N×0.4 + F×0.3 + I×0.3)
- Justification for ranking position
- Required data sources

**Process:**
1. Present the top 3 ideas to the user with full detail.
2. User decides:
   - **SELECT** → choose one idea, proceed to Stage 3
   - **COMBINE** → merge elements from 2+ ideas into a hybrid, proceed to Stage 3
   - **REJECT ALL** → return to Stage 2 with feedback to generate new ideas

**Output:** `selected_idea.md` — the user-selected (or user-combined) research idea, formatted as `idea_template.txt` for Stage 3.

**Why this matters:** Which question to investigate is as important as how to identify it. The automatic ranking (N×0.4 + F×0.3 + I×0.3) cannot capture the researcher's domain knowledge, data familiarity, or strategic agenda. A researcher may prefer idea #3 because they have unique access to the data, or idea #2 because it aligns with their publication strategy.

**Handoff to Stage 3:** The selected idea formatted into the `idea_template.txt` structure required by the evaluation pipeline.

---

## Stage 3: Validation — `idea-evaluation-pipeline/`

**Goal:** Rigorously evaluate research ideas through an 8-step iterative pipeline until they achieve a quality score >= 7/10.

**Input:** An idea file following `idea_template.txt` format:
```
Title: [Research title]
Research Question: [Clear empirical/theoretical question]
Identification Strategy: [Causal method: DiD, RDD, IV, etc.]
Data Sources: [Specific datasets with access details]
3 Closest Papers:
  1. Author (Year). "Title." Journal. DOI.
  2. ...
  3. ...
```

**Process (8-Step Pipeline with Loop):**
1. **Literature Check** — Verify novelty against existing work.
2. **Idea Refinement** — Sharpen the research question and scope.
3. **Methodology Review** — Assess identification strategy validity.
4. **Data Feasibility** — Confirm data availability and suitability.
5. **Pre-Analysis Plan** — Lock specifications before analysis.
6. **Draft Evaluation** — Assess completeness of the research design.
7. **Peer Simulation** — Simulated review of the research design (not the full paper).
8. **Final Score** — Assign score 1-10.

**Loop Logic:** If score < 7, return to Step 2 with feedback. Repeat until score >= 7. **Maximum 5 iterations.** If after 5 loops the score remains < 7, the pipeline stalls with a warning: "Idea stalled after 5 refinement loops (best score: X/10). Returning to Stage 2.5 to select a different idea."

**Model Configuration:**
- Steps 1-5: Claude Sonnet (speed/cost efficient)
- Steps 6-8: Claude Opus (deeper reasoning for evaluation)

**Output:**
- Approved idea with score >= 7
- Refined research question, methodology, and pre-analysis plan
- Evaluation reports from each step

**Handoff to Stage 3.5:** The approved idea + evaluation reports are presented to the user for strategy review.

---

## Stage 3.5: Strategy Review — Human-in-the-Loop

**Goal:** Ensure the user validates the identification strategy before committing resources to execution.

**Input:** PROMPT.md + evaluation reports from Stage 3.

**Process:**
1. Present identification strategy to the user:
   - Research question
   - Proposed causal method (DiD, RDD, IV, etc.)
   - Data sources and variables
   - Key assumptions and threats to validity
   - Pre-analysis plan summary
2. User decides:
   - **APPROVE** → proceed to Stage 4
   - **REFORMULATE** → adjust strategy based on user feedback, re-present
   - **REJECT** → return to Stage 2.5 to select a different idea. If all 3 exhausted, return to Stage 2

**Output:** `approved_strategy.md` — the user-approved identification strategy that becomes the binding contract for all subsequent stages.

**Why this matters:** The identification strategy is the single most important decision in an empirical paper. Automating everything else is valuable; automating this decision without human validation is risky.

---

## Stage 4: Strategy & Analysis — Clo-Author (strategist + coder + data-engineer)

**Goal:** Formalize the approved strategy into executable pseudo-code, then implement the full analysis in Python.

**Input:** `approved_strategy.md` from Stage 3.5.

### 4a. Strategy Formalization (strategist + strategist-critic)

The strategist translates the user-approved strategy into implementation-ready artifacts:
1. Formalize estimand, estimator, assumptions
2. Design robustness plan (alternative specs, placebos, falsification)
3. Write pseudo-code for the coder

**Gate:** strategist-critic score >= 80.
**Note:** The strategist does NOT redesign the strategy — only formalizes what the user approved.

**Output:**
- `strategy_memo.md`
- `pseudo_code.md`
- `robustness_plan.md`

### 4b. Data Engineering (data-engineer + coder-critic)

1. Load raw data, inspect structure (if Path B was used, reuse the dataset profile from Stage 1B — skip re-inspection)
2. Clean: missing values, outliers, merges
3. Construct variables per strategy memo
4. Summary statistics table
5. Descriptive figures (publication-ready)

**Path B optimization:** When the user provided their own dataset in Stage 1B, the data profile (variables, types, N obs, structure, summary stats, missingness patterns) is already available. The data-engineer reuses this profile and starts directly from step 2 (cleaning), avoiding redundant re-loading and re-inspection.

**Output:** `data/cleaned/` + codebook + summary stats table

### 4c. Main Analysis (coder + coder-critic)

1. Implement main specification from pseudo-code (Python: `pyfixest`, `linearmodels`, `statsmodels`)
2. Run all robustness checks from robustness plan
3. Generate publication-ready tables (`.tex`) and figures (`.pdf`)
4. Produce `results_summary.md` (mandatory handoff to writer)

**Gate:** coder-critic score >= 80 (12-category checklist).
**Escalation:** 3 strikes → strategist-critic re-evaluates tractability.

**Output:**
- `scripts/python/` (numbered: 00_clean, 01_main, 02_robustness, etc.)
- `paper/tables/*.tex`
- `paper/figures/*.pdf`
- `results_summary.md`

---

## Stage 5: Writing — Clo-Author (writer + writer-critic)

**Goal:** Draft a complete LaTeX manuscript from the analysis results.

**Input:** `results_summary.md` + tables + figures + `strategy_memo.md`

**Process:**
1. Draft Introduction (contribution, preview of results)
2. Draft Literature Review (positioning vs. frontier)
3. Draft Data section (sources, sample, summary stats)
4. Draft Empirical Strategy (identification, assumptions)
5. Draft Results (main + robustness, effect sizes with units)
6. Draft Conclusion (implications, limitations)
7. Abstract (150 words max)
8. Humanizer pass (strip AI writing patterns, anti-hedging)

**Format:** LaTeX, 12pt, double-spaced, biblatex+biber.

**Gate:** writer-critic score >= 80.
**Escalation:** 3 strikes → orchestrator triggers structural rewrite.

**Output:**
- `paper/main.tex`
- `paper/sections/*.tex`
- `Bibliography_base.bib`

---

## Stage 6: Peer Review — Clo-Author (editor + domain-referee + methods-referee)

**Goal:** Simulate a realistic journal peer review process.

**Input:** `paper/main.tex` (compiled PDF).

### 6a. Desk Review (editor)
1. Novelty verification (web search)
2. Journal fit assessment
3. Decision: send to referees or desk reject
   - If desk reject: return to Stage 5 with feedback

### 6b. Referee Reports (blind, independent, parallel)
- **Domain-referee:** Contribution, literature, external validity
- **Methods-referee:** Identification, inference, robustness
- Each scores 5 dimensions (weighted):
  - 30% Contribution + 25% Literature + 20% Substance + 15% External validity + 10% Journal fit
- Each comment includes "what would change my mind"

### 6c. Editorial Decision (editor)
1. Synthesize referee reports
2. Classify concerns: FATAL / ADDRESSABLE / TASTE
3. Decision: Accept / Minor Revisions / Major Revisions / Reject
   - If Major Revisions: route back via `/revise` protocol (max 3 R&R rounds)

**Output:**
- `quality_reports/reviews/` (referee reports + editorial decision)
- `response_letter.md` (if R&R)

---

## Stage 7: Submission — Clo-Author (orchestrator + verifier)

**Goal:** Prepare the final submission-ready package.

**Input:** Accepted paper + all artifacts.

**Process:**
1. Journal targeting (match paper to 30 journal profiles)
2. Replication package audit (AEA Data Editor compliance):
   - All Python scripts run without error
   - Data documented with codebook
   - README with execution instructions
   - Computational requirements stated
3. Final quality gate:
   - Overall score >= 95
   - Every component >= 80
4. Compile final PDF

**Output:**
- `paper/replication/` (AEA-compliant package)
- `paper/main.pdf` (submission-ready)
- `journal_targeting.md`

---

## Quality Scoring (Adjusted Weights)

Since Stages 1-3 of Papers-HQ already cover literature discovery and data sourcing, the quality weights for Clo-Author's execution phases are adjusted:

| Component | Weight | Source |
|-----------|--------|--------|
| Identification validity | 30% | strategist-critic |
| Code quality | 20% | coder-critic |
| Paper quality | 25% | avg. domain + methods referee |
| Manuscript polish | 15% | writer-critic |
| Replication readiness | 10% | verifier pass/fail |

**Thresholds:**
| Gate | Score | Requirement |
|------|-------|-------------|
| Commit | >= 80 | Weighted aggregate |
| PR | >= 90 | Weighted aggregate |
| Submission | >= 95 | Aggregate + all components >= 80 |

---

## File Handoff Map

```
Stage 1 Output (Path A or B)      Stage 2 Input
---------------------             ---------------------
3 academic papers     --------->  Seed papers for digest
(title, DOI, summary)             (research area config)
+ dataset context                 + data structure info

Stage 2 Output                    Stage 2.5 Input
---------------------             ---------------------
Top 3 ranked ideas    --------->  Presented to user with
(question, method,                scores, justifications,
 relevance score)                  and data requirements

Stage 2.5 Output                  Stage 3 Input
---------------------             ---------------------
selected_idea.md      --------->  idea_template.txt
(user-selected or                 (title, question, ID
 user-combined idea)               strategy, data, 3 papers)

Stage 3 Output                    Stage 3.5 Input
---------------------             ---------------------
Approved idea (>=7)   --------->  Strategy + evaluation reports
(PROMPT.md, PAP)                  presented to user for review

Stage 3.5 Output                  Stage 4 Input
---------------------             ---------------------
approved_strategy.md  --------->  strategist formalizes →
(user-validated)                  coder implements in Python

Stage 4 Output                    Stage 5 Input
---------------------             ---------------------
results_summary.md    --------->  writer drafts LaTeX paper
tables/*.tex                      from results + strategy
figures/*.pdf

Stage 5 Output                    Stage 6 Input
---------------------             ---------------------
paper/main.tex        --------->  editor + 2 referees
(compiled PDF)                    simulate peer review

Stage 6 Output                    Stage 7 Input
---------------------             ---------------------
Accepted paper        --------->  verifier audits replication
editorial decision                package + final quality gate
```

---

## Pipeline Summary

| Stage | Name | Source | Automatic? | Language |
|-------|------|--------|------------|----------|
| 1A | Discovery (repo search) | search-repositories/ | Fully auto | — |
| 1B | Discovery (user data) | analyze-data/ | Fully auto | Python |
| 2 | Ideation | research-junshi/ | Fully auto | — |
| 2.5 | **Idea Selection** | **User** | **Human-in-the-loop** | — |
| 3 | Validation | idea-evaluation-pipeline/ | Auto (loop if < 7) | — |
| 3.5 | **Strategy Review** | **User** | **Human-in-the-loop** | — |
| 4 | Strategy & Analysis | Clo-Author | Auto (critic gate >= 80) | Python |
| 5 | Writing | Clo-Author | Auto (critic gate >= 80) | LaTeX |
| 6 | Peer Review | Clo-Author | Auto (R&R max 3 rounds) | — |
| 7 | Submission | Clo-Author | Auto (gate >= 95) | — |

---

## Notes

- **Two human checkpoints:** Stage 2.5 (user selects which idea to pursue) and Stage 3.5 (user approves identification strategy). These are the two most important decisions in an empirical paper.
- **Quality Gate:** Stage 3 validates the idea (score >= 7). Stage 3.5 validates the strategy (user approval). Stage 4+ enforces execution quality (critic scores >= 80).
- **No redundancy:** Stage 3's peer simulation evaluates the research design only, not a full paper. Stage 6's peer review evaluates the complete manuscript.
- **Iteration:** If Stage 3 rejects an idea after multiple loops, return to Stage 2.5 to let the user select a different idea. If Stage 3.5 rejects, user can reformulate or return to Stage 2.5 to pick another idea (or Stage 2 if all 3 exhausted).
- **Data Requirement:** Stage 1 ensures data availability — Path A discovers repositories with real datasets, Path B uses the user's own dataset. Both feed Stage 4's need for actual empirical data.
- **Two entry paths:** Path A (`--topic` only) searches GitHub for replication packages and discovers data. Path B (`--topic` + `--data`) accepts a user-provided dataset (URL or file), analyzes its structure, and finds 3 papers tailored to the data context and applicable methodologies. Both paths converge on the same handoff format to Stage 2.
- **Python only:** All analysis scripts use Python exclusively (pandas, pyfixest, linearmodels, statsmodels, matplotlib, seaborn).
- **Versioning:** Papers are versioned and tracked; R&R rounds produce v2, v3, etc.
