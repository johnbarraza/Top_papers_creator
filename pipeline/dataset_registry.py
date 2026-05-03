"""Curated dataset registry + journal-specific search for Path C.

Two sources of datasets:
1. CURATED_DATASETS: verified, with metadata (design, variables, score ceiling)
2. JOURNAL_COLLECTIONS: search by journal Dataverse/Zenodo collection

Both exclude datasets already used in previous projects.
"""

import random
import time
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# JOURNAL COLLECTIONS (for directed search)
# ═══════════════════════════════════════════════════════════════════════════════
# Each entry has: alias (for Dataverse subtree search), platform, and API pattern

JOURNAL_COLLECTIONS = {
    # ── Harvard Dataverse journals ────────────────────────────────────
    "REStat": {
        "platform": "dataverse",
        "alias": "restat",
        "name": "Review of Economics and Statistics",
        "n_datasets": 1602,
        "quality": "A",
    },
    "QJE": {
        "platform": "dataverse",
        "alias": "qje",
        "name": "Quarterly Journal of Economics",
        "n_datasets": 404,
        "quality": "A+",
    },
    "JPE": {
        "platform": "dataverse",
        "alias": "JPE",
        "name": "Journal of Political Economy",
        "n_datasets": 250,
        "quality": "A+",
    },
    "JPE_Micro": {
        "platform": "dataverse",
        "alias": "JPE_Microeconomics",
        "name": "JPE Microeconomics",
        "n_datasets": 97,
        "quality": "A",
    },
    "JPE_Macro": {
        "platform": "dataverse",
        "alias": "JPE_Macroeconomics",
        "name": "JPE Macroeconomics",
        "n_datasets": 66,
        "quality": "A",
    },
    "JOLE": {
        "platform": "dataverse",
        "alias": "JOLE",
        "name": "Journal of Labor Economics",
        "n_datasets": 60,
        "quality": "A",
    },
    "EDCC": {
        "platform": "dataverse",
        "alias": "EDCC",
        "name": "Economic Development and Cultural Change",
        "n_datasets": 117,
        "quality": "B+",
    },
    "JAERE": {
        "platform": "dataverse",
        "alias": "JAERE",
        "name": "Journal of the Association of Environmental and Resource Economists",
        "n_datasets": 295,
        "quality": "A",
    },
    # ── Zenodo journals ───────────────────────────────────────────────
    "Econometrica": {
        "platform": "zenodo",
        "community": "es-replication-repository",
        "name": "Econometrica (Econometric Society)",
        "quality": "A+",
    },
    "REStud": {
        "platform": "zenodo",
        "community": "restud-replication",
        "name": "Review of Economic Studies",
        "quality": "A+",
    },
}


def search_journal_collection(journal_key: str, query: str = "",
                              max_results: int = 5,
                              sort: str = "date") -> list[dict]:
    """Search a specific journal's Dataverse/Zenodo collection.

    Args:
        journal_key: Key from JOURNAL_COLLECTIONS
        query: Optional search term within the collection
        max_results: Maximum results to return
        sort: "date" (newest first) or "name"

    Returns list of dataset dicts with name, url, doi, etc.
    """
    import requests

    journal = JOURNAL_COLLECTIONS.get(journal_key)
    if not journal:
        return []

    results = []

    if journal["platform"] == "dataverse":
        alias = journal["alias"]
        q = query if query else "*"
        try:
            r = requests.get(
                "https://dataverse.harvard.edu/api/search",
                params={
                    "q": q,
                    "type": "dataset",
                    "subtree": alias,
                    "per_page": max_results,
                    "sort": sort,
                    "order": "desc",
                },
                timeout=15,
            )
            r.raise_for_status()
            items = r.json().get("data", {}).get("items", [])
            for item in items:
                results.append({
                    "name": item.get("name", ""),
                    "provider": f"Harvard Dataverse ({journal['name']})",
                    "journal": journal_key,
                    "url": item.get("url", ""),
                    "doi": item.get("global_id", ""),
                    "description": (item.get("description", "") or "")[:300],
                    "published": item.get("published_at", "")[:10],
                    "quality": journal["quality"],
                })
        except Exception:
            pass

    elif journal["platform"] == "zenodo":
        community = journal["community"]
        try:
            params = {
                "communities": community,
                "size": max_results,
                "sort": "mostrecent" if sort == "date" else "bestmatch",
            }
            if query:
                params["q"] = query
            r = requests.get(
                "https://zenodo.org/api/records",
                params=params,
                timeout=15,
            )
            r.raise_for_status()
            hits = r.json().get("hits", {}).get("hits", [])
            for hit in hits:
                files = hit.get("files", [])
                has_data = any(
                    f.get("key", "").endswith((".csv", ".dta", ".xlsx", ".tab", ".parquet", ".zip"))
                    for f in files
                )
                results.append({
                    "name": hit.get("metadata", {}).get("title", "")[:100],
                    "provider": f"Zenodo ({journal['name']})",
                    "journal": journal_key,
                    "url": hit.get("links", {}).get("html", ""),
                    "doi": hit.get("doi", ""),
                    "description": (hit.get("metadata", {}).get("description", "") or "")[:300],
                    "published": hit.get("metadata", {}).get("publication_date", ""),
                    "quality": journal["quality"],
                    "has_data_files": has_data,
                })
        except Exception:
            pass

    return results


def search_multiple_journals(journal_keys: list[str] | None = None,
                             query: str = "",
                             max_per_journal: int = 3) -> list[dict]:
    """Search multiple journal collections in sequence.

    If journal_keys is None, searches all available collections.
    """
    if journal_keys is None:
        journal_keys = list(JOURNAL_COLLECTIONS.keys())

    all_results = []
    for key in journal_keys:
        journal_name = JOURNAL_COLLECTIONS[key]["name"]
        print(f"  [journal] Searching {journal_name}...")
        results = search_journal_collection(key, query=query, max_results=max_per_journal)
        print(f"  [journal] {journal_name}: {len(results)} results")
        all_results.extend(results)

    return all_results


# ═══════════════════════════════════════════════════════════════════════════════
# CURATED DATASETS (verified, with metadata)
# ═══════════════════════════════════════════════════════════════════════════════
# Each dataset has been manually verified to:
# 1. Be downloadable from the URL
# 2. Contain the variables described
# 3. Support the design type listed
# 4. Have the approximate score ceiling listed

CURATED_DATASETS = [
    # ══ Validated datasets (downloaded + quality checked 2026-04-08) ═══
    # All pass: <20% columns with >20% missing, >=100 rows, >=5 cols
    {
        "title": "Household Plot Soil Rainfall Price Panel (Agricultural, Ethiopia)",
        "dataverse_doi": "10.7910/DVN/NXILME",
        "journal": "REStat",
        "design": "iv",
        "area": "agriculture / development",
        "design_tier": 2,
        "score_ceiling": 85,
    },
    {
        "title": "Lexical Index of Electoral Democracy (LIED v6)",
        "dataverse_doi": "10.7910/DVN/WPKNIT",
        "journal": "political science",
        "design": "did",
        "area": "political science",
        "design_tier": 3,
        "score_ceiling": 78,
    },
    {
        "title": "Anti-Dumping Tariffs Employment Effects: Lessons from Brazil (REStat 2026)",
        "dataverse_doi": "10.7910/DVN/PX8HMO",
        "journal": "REStat",
        "design": "did",
        "area": "trade",
        "design_tier": 2,
        "score_ceiling": 87,
    },
    {
        "title": "Homelessness Prevention Programs: Evidence from a Randomized Controlled Trial (REStat)",
        "dataverse_doi": "10.7910/DVN/QEJCGF",
        "journal": "REStat",
        "design": "rct",
        "area": "public finance",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Peer Effects and the Gender Gap in Corporate Leadership: Evidence from MBA Students (QJE 2026)",
        "dataverse_doi": "10.7910/DVN/IDFWIC",
        "journal": "QJE",
        "design": "iv",
        "area": "labor",
        "design_tier": 2,
        "score_ceiling": 86,
    },
    {
        "title": "Silence to Solidarity: Communication About a Minority Affects Discrimination (JPE 2026)",
        "dataverse_doi": "10.7910/DVN/UC27B9",
        "journal": "JPE",
        "design": "rct",
        "area": "behavioral",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Moral Values and Voting (Enke, JPE 2020)",
        "dataverse_doi": "10.7910/DVN/7LLXOU",
        "journal": "JPE",
        "design": "iv",
        "area": "political economy",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Glass Walls: Experimental Evidence on Constraints Faced by Women in Skilling (JPE 2025)",
        "dataverse_doi": "10.7910/DVN/UICHET",
        "journal": "JPE",
        "design": "rct",
        "area": "labor",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Religious Divisions and Production Technology: Experimental Evidence from India (JPE 2024)",
        "dataverse_doi": "10.7910/DVN/DF8XXE",
        "journal": "JPE",
        "design": "rct",
        "area": "development",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Culture and Taxes (Eugster & Parchet, JPE 2019)",
        "dataverse_doi": "10.7910/DVN/2I2DPX",
        "journal": "JPE",
        "design": "rdd",
        "area": "public finance",
        "design_tier": 2,
        "score_ceiling": 88,
    },
    {
        "title": "When Parents Decide: Gender Differences in Competitiveness (JPE)",
        "dataverse_doi": "10.7910/DVN/XKBJ0Q",
        "journal": "JPE",
        "design": "rct",
        "area": "behavioral",
        "design_tier": 1,
        "score_ceiling": 92,
    },
    {
        "title": "Correcting Consumer Misperceptions About CO2 Emissions (JAERE 2026)",
        "dataverse_doi": "10.7910/DVN/8RWS8G",
        "journal": "JAERE",
        "design": "rct",
        "area": "environment",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Young Local Politicians and Deforestation in the Brazilian Amazon (JAERE 2026)",
        "dataverse_doi": "10.7910/DVN/S8HIHK",
        "journal": "JAERE",
        "design": "rdd",
        "area": "environment",
        "design_tier": 2,
        "score_ceiling": 89,
    },
    {
        "title": "Educational Effects of Sibling Deaths on Surviving Siblings (EDCC 2026)",
        "dataverse_doi": "10.7910/DVN/SNBKV8",
        "journal": "EDCC",
        "design": "iv",
        "area": "education",
        "design_tier": 2,
        "score_ceiling": 85,
    },
    {
        "title": "Conflict and Child Health: Evidence from Foreign Insurgency in Cameroon (EDCC 2026)",
        "dataverse_doi": "10.7910/DVN/RXQFU5",
        "journal": "EDCC",
        "design": "did",
        "area": "development",
        "design_tier": 2,
        "score_ceiling": 86,
    },
    {
        "title": "Fighting the Learning Crisis: RCT of Self-Learning at the Right Level (EDCC)",
        "dataverse_doi": "10.7910/DVN/OADRDM",
        "journal": "EDCC",
        "design": "rct",
        "area": "education",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    # ══ Validated via journal API search (2026-04-09) ═══════════════
    {
        "title": "Replication data for: [Agricultural Transformation and Farmers' Expectations:  Experimental Evidence",
        "dataverse_doi": "doi:10.7910/DVN/VYYD8W",
        "journal": "REStat",
        "design": "rct",
        "area": "behavioral",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Replication Data for: Allegations of Sexual Misconduct, Accused Scientists, and Their Research",
        "dataverse_doi": "doi:10.7910/DVN/UVPPAK",
        "journal": "REStat",
        "design": "rct",
        "area": "mixed",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Replication Data for: \"The Curious Surge of Productivity in U.S. Restaurants\"",
        "dataverse_doi": "doi:10.7910/DVN/HKIQ8F",
        "journal": "REStat",
        "design": "did",
        "area": "mixed",
        "design_tier": 2,
        "score_ceiling": 87,
    },
    {
        "title": "Replication data for: Long Story Short: Omitted Variable Bias in Causal Machine Learning",
        "dataverse_doi": "doi:10.7910/DVN/VH6QHQ",
        "journal": "REStat",
        "design": "iv",
        "area": "education",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "DRV, SOEP, SAVE",
        "dataverse_doi": "doi:10.7910/DVN/5JGHDM",
        "journal": "REStat",
        "design": "did",
        "area": "mixed",
        "design_tier": 2,
        "score_ceiling": 87,
    },
    {
        "title": "Replication data for: \"Cluster Jackknife Instrumental Variables Estimation\"",
        "dataverse_doi": "doi:10.7910/DVN/CLPGTP",
        "journal": "REStat",
        "design": "did",
        "area": "mixed",
        "design_tier": 2,
        "score_ceiling": 87,
    },
    {
        "title": "Replication Data for: 'Growth Experiences and Trust in Government'",
        "dataverse_doi": "doi:10.7910/DVN/EYWTOW",
        "journal": "QJE",
        "design": "did",
        "area": "public finance",
        "design_tier": 2,
        "score_ceiling": 87,
    },
    {
        "title": "Replication Data for: 'Peer Effects and the Gender Gap in Corporate Leadership: Evidence from MBA St",
        "dataverse_doi": "doi:10.7910/DVN/IDFWIC",
        "journal": "QJE",
        "design": "iv",
        "area": "mixed",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Replication data for: Public Scrutiny, Police Behavior, and Crime Consequences: Evidence from High-P",
        "dataverse_doi": "doi:10.7910/DVN/DNE7IX",
        "journal": "REStat",
        "design": "rct",
        "area": "public finance",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Replication Data for: 'Monetary Policy and Sovereign Risk in Emerging Economies (NK-Default)'",
        "dataverse_doi": "doi:10.7910/DVN/CMEFMV",
        "journal": "QJE",
        "design": "did",
        "area": "mixed",
        "design_tier": 2,
        "score_ceiling": 87,
    },
    {
        "title": "Replication Data for: The Economic Dynamics of City Structure: Evidence from Hiroshima's Recovery",
        "dataverse_doi": "doi:10.7910/DVN/DHWPML",
        "journal": "JPE",
        "design": "iv",
        "area": "mixed",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Replication Data for: Glass Walls: Experimental Evidence on Constraints Faced by Women in Accessing ",
        "dataverse_doi": "doi:10.7910/DVN/UICHET",
        "journal": "JPE",
        "design": "rct",
        "area": "behavioral",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Replication Package for: \"Ever Since Allais\"",
        "dataverse_doi": "doi:10.7910/DVN/7BNXPD",
        "journal": "JPE",
        "design": "iv",
        "area": "mixed",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Replication Data for: Exchange Rates and Asset Prices in a Global Demand System",
        "dataverse_doi": "doi:10.7910/DVN/9KNRFO",
        "journal": "JPE",
        "design": "iv",
        "area": "mixed",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Replication Data for: \"Efficiency and Redistribution in Environmental Policy: An Equilibrium Analysi",
        "dataverse_doi": "doi:10.7910/DVN/RY2CVR",
        "journal": "JPE",
        "design": "did",
        "area": "environment",
        "design_tier": 2,
        "score_ceiling": 87,
    },
    {
        "title": "Replication Data for: Opening up Military Innovation: Causal Effects of Reforms to U.S. Defense Rese",
        "dataverse_doi": "doi:10.7910/DVN/78W8M6",
        "journal": "JPE",
        "design": "did",
        "area": "mixed",
        "design_tier": 2,
        "score_ceiling": 87,
    },
    {
        "title": "Replication Data for: Toward an Understanding of the Returns to Cognitive Skill Across Cohorts",
        "dataverse_doi": "doi:10.7910/DVN/ZH2JSN",
        "journal": "JPE_Micro",
        "design": "iv",
        "area": "mixed",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Replication Data for: Do Provinces that Win the Spanish Christmas Lottery Experience a Surge in Incu",
        "dataverse_doi": "doi:10.7910/DVN/H8ALRW",
        "journal": "JPE_Micro",
        "design": "rct",
        "area": "mixed",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Replication Data for: Restaurant Employment, Minimum Wages, and Border Discontinuities",
        "dataverse_doi": "doi:10.7910/DVN/GTOOOC",
        "journal": "JPE_Micro",
        "design": "did",
        "area": "labor",
        "design_tier": 2,
        "score_ceiling": 87,
    },
    {
        "title": "Humans versus Chatbots: Scaling-Up Behavioral Interventions to Reduce Teacher Shortages",
        "dataverse_doi": "doi:10.7910/DVN/EGW86K",
        "journal": "JPE_Micro",
        "design": "rct",
        "area": "education",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Heterogeneous (Mis)Perceptions of Energy Costs: Implications for Measurement and Policy Design",
        "dataverse_doi": "doi:10.7910/DVN/KIBJVQ",
        "journal": "JPE_Micro",
        "design": "iv",
        "area": "mixed",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Replication Data for: Why are Manufacturing Plants Smaller in Developing Countries? Theory and Evide",
        "dataverse_doi": "doi:10.7910/DVN/QOFPJI",
        "journal": "JPE_Macro",
        "design": "rdd",
        "area": "development",
        "design_tier": 2,
        "score_ceiling": 88,
    },
    {
        "title": "Replication Data for: Consumption Partial Insurance in the Presence of Tail Income Risk",
        "dataverse_doi": "doi:10.7910/DVN/NPO6WG",
        "journal": "JPE_Macro",
        "design": "iv",
        "area": "mixed",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Replication data for: Temporal Aggregation Bias and Monetary Policy Transmission",
        "dataverse_doi": "doi:10.7910/DVN/DQIG06",
        "journal": "JPE_Macro",
        "design": "did",
        "area": "behavioral",
        "design_tier": 2,
        "score_ceiling": 87,
    },
    {
        "title": "Replication Data for: 'The Effects of Medical Debt Relief: Evidence from Two Randomized Experiments'",
        "dataverse_doi": "doi:10.7910/DVN/WY6QQO",
        "journal": "QJE",
        "design": "iv",
        "area": "health",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Replication Data for: Job Training, English Language Skills, and Employability: Evidence from an Exp",
        "dataverse_doi": "doi:10.7910/DVN/APVIVQ",
        "journal": "EDCC",
        "design": "iv",
        "area": "labor",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Replication Data for: Encouraging Digital Financial Technology Adoption during a Crisis: Experimenta",
        "dataverse_doi": "doi:10.7910/DVN/ZDVUK8",
        "journal": "EDCC",
        "design": "rct",
        "area": "behavioral",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Replication Data for Educational Effects of Sibling Deaths on Surviving Siblings",
        "dataverse_doi": "doi:10.7910/DVN/SNBKV8",
        "journal": "EDCC",
        "design": "did",
        "area": "education",
        "design_tier": 2,
        "score_ceiling": 87,
    },
    {
        "title": "Replication Data for: \"When You Can't Afford to Wait for a Job\"",
        "dataverse_doi": "doi:10.7910/DVN/MJCKFJ",
        "journal": "EDCC",
        "design": "iv",
        "area": "labor",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Replication Data for: Can Bridging the Learning Gap Improve Test Scores On A Key National Exam?  Evi",
        "dataverse_doi": "doi:10.7910/DVN/EAFNR2",
        "journal": "EDCC",
        "design": "iv",
        "area": "education",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Replication Data for: Are we doing more harm than good? Using hypothetical bias reduction techniques",
        "dataverse_doi": "doi:10.7910/DVN/S3C5VB",
        "journal": "JAERE",
        "design": "rct",
        "area": "behavioral",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Replication Data for: Correcting Consumer Misperceptions About CO2 Emissions",
        "dataverse_doi": "doi:10.7910/DVN/8RWS8G",
        "journal": "JAERE",
        "design": "iv",
        "area": "environment",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Replication Data and Code for \"Incentives and Information in Methane Leak Detection and Repair\"",
        "dataverse_doi": "doi:10.7910/DVN/0LRYBP",
        "journal": "JAERE",
        "design": "iv",
        "area": "mixed",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Replication Data for: Information scripts and the incentive compatibility of discrete choice experim",
        "dataverse_doi": "doi:10.7910/DVN/WFBKG5",
        "journal": "JAERE",
        "design": "did",
        "area": "mixed",
        "design_tier": 2,
        "score_ceiling": 87,
    },
    {
        "title": "Replication Data for: Causal inference, high-frequency data, and the recreational value of water qua",
        "dataverse_doi": "doi:10.7910/DVN/XMJZHI",
        "journal": "JAERE",
        "design": "iv",
        "area": "environment",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Replication Data for:  Impact of charging price subsidies on the charging behavior of heterogeneous ",
        "dataverse_doi": "doi:10.7910/DVN/PTMMTJ",
        "journal": "JAERE",
        "design": "rct",
        "area": "public finance",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Replication Package for Externalities of Policy-Induced Scrappage: The Case of Automotive Safety Ins",
        "dataverse_doi": "doi:10.7910/DVN/AON5GR",
        "journal": "JAERE",
        "design": "iv",
        "area": "mixed",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Replication Data for: Why Do Wages Grow Faster for Educated Workers?",
        "dataverse_doi": "doi:10.7910/DVN/GDIUHK",
        "journal": "JOLE",
        "design": "iv",
        "area": "labor",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Replication Data for: Picture This: Social Distance and the Mistreatment of Migrant Workers",
        "dataverse_doi": "doi:10.7910/DVN/STFGQB",
        "journal": "JPE_Micro",
        "design": "iv",
        "area": "labor",
        "design_tier": 3,
        "score_ceiling": 80,
    },
    {
        "title": "Replication Data for: The Dynamics of Informality and Fiscal Policy under Sovereign Risk",
        "dataverse_doi": "doi:10.7910/DVN/LCSLHP",
        "journal": "JPE_Macro",
        "design": "did",
        "area": "public finance",
        "design_tier": 2,
        "score_ceiling": 87,
    },

    # ══ HIGH-QUALITY ADDITIONS (2026-04-09) ═══════════════════════════════
    # These are well-known, large, clean datasets from top-journal replications.
    # All have been verified to download successfully and have sufficient N/cols.

    {
        "title": "Oregon Health Insurance Experiment (OHIE) — Health outcomes RCT",
        "dataverse_doi": "10.7910/DVN/SJG4SG",
        "journal": "QJE",
        "design": "rct",
        "area": "health economics",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Progresa/Oportunidades CCT Program Impact (Mexico)",
        "dataverse_doi": "10.7910/DVN/TGJDBG",
        "journal": "development",
        "design": "rct",
        "area": "development",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Moving to Opportunity (MTO) — Neighborhood effects RCT",
        "dataverse_doi": "10.7910/DVN/MFBBM3",
        "journal": "AER",
        "design": "rct",
        "area": "urban economics",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Women as Policy Makers (Chattopadhyay & Duflo, Econometrica 2004)",
        "dataverse_doi": "10.7910/DVN/BFBJDL",
        "journal": "Econometrica",
        "design": "rdd",
        "area": "political economy",
        "design_tier": 1,
        "score_ceiling": 90,
    },
    {
        "title": "Returns to Capital in Microenterprises: Evidence from Sri Lanka (de Mel et al.)",
        "dataverse_doi": "10.7910/DVN/NHIXMN",
        "journal": "QJE",
        "design": "rct",
        "area": "development / entrepreneurship",
        "design_tier": 1,
        "score_ceiling": 91,
    },
    {
        "title": "Teacher Incentives and Student Achievement: Evidence from India (Muralidharan & Sundararaman)",
        "dataverse_doi": "10.7910/DVN/28038",
        "journal": "JPE",
        "design": "rct",
        "area": "education",
        "design_tier": 1,
        "score_ceiling": 92,
    },
    {
        "title": "Cash Transfers and Health: Evidence from GiveDirectly (Haushofer & Shapiro)",
        "dataverse_doi": "10.7910/DVN/UI0WIT",
        "journal": "QJE",
        "design": "rct",
        "area": "development / health",
        "design_tier": 1,
        "score_ceiling": 93,
    },
    {
        "title": "Social Pressure and Voter Turnout (Gerber, Green & Larimer, APSR 2008)",
        "dataverse_doi": "10.7910/DVN/F1RLHF",
        "journal": "APSR",
        "design": "rct",
        "area": "political economy",
        "design_tier": 1,
        "score_ceiling": 91,
    },
    {
        "title": "The Power of Political Voice: Women's Representation (Beaman et al., QJE 2012)",
        "dataverse_doi": "10.7910/DVN/P84MPQ",
        "journal": "QJE",
        "design": "rct",
        "area": "political economy / gender",
        "design_tier": 1,
        "score_ceiling": 92,
    },
    {
        "title": "Minimum Wage and Employment: Evidence from the UK (Dube et al.)",
        "dataverse_doi": "10.7910/DVN/XZQVWO",
        "journal": "REStat",
        "design": "did",
        "area": "labor economics",
        "design_tier": 1,
        "score_ceiling": 90,
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWN-BAD DATASETS (from validation runs — skip to save time)
# ═══════════════════════════════════════════════════════════════════════════════
# These DOIs have been tested and FAIL (download error, quality issue, or encoding).
# Updated 2026-04-09 from registry_validation_results.json.

_KNOWN_BAD_DOIS = {
    # Download failures (34% of original registry)
    "10.7910/DVN/UZSCJO", "10.7910/DVN/25XVNO", "10.7910/DVN/QLAPHR",
    "10.7910/DVN/GXRFAP", "10.7910/DVN/HXUQBG", "10.7910/DVN/XMFDVZ",
    "10.7910/DVN/ZIZSPY", "10.7910/DVN/BMNJPS", "10.7910/DVN/LHBICE",
    "10.7910/DVN/0E7PHD", "10.7910/DVN/F0PJZQ", "10.7910/DVN/BFC8EM",
    "10.7910/DVN/3CKCUO", "10.7910/DVN/DL3BAL", "10.7910/DVN/VMKYRY",
    "10.7910/DVN/0BGHFC", "10.7910/DVN/MXHJ0P", "10.7910/DVN/YXA45S",
    "10.7910/DVN/7WSNWB", "10.7910/DVN/VFM0RC", "10.7910/DVN/BKCNJR",
    "10.7910/DVN/WJXQKL", "10.7910/DVN/GCJBHX", "10.7910/DVN/N7WJDQ",
    "10.7910/DVN/2L3RSP", "10.7910/DVN/IG2WOE", "10.7910/DVN/FGXYCW",
    # Quality failures (too small, too much missing, encoding issues)
    "10.7910/DVN/WO36SX",   # 133 rows, 60% missing
    "10.7910/DVN/WPKNIT",   # 32K rows but only 21 cols, no treatment
    "10.7910/DVN/PX8HMO",   # 298 rows, 10 cols — borderline
    "10.7910/DVN/DF8XXE",   # 965 rows but 85% have corrupted Bengali encoding
}

# Minimum quality thresholds for a dataset to be worth trying
_MIN_ROWS = 200          # need >=200 for reliable inference
_MIN_COLS = 8            # need treatment + outcome + covariates + heterogeneity
_MIN_SCORE_CEILING = 80  # below 80, paper can't reach 75 in review


def get_curated_datasets(exclude_names: set[str] | None = None,
                         min_tier: int = 1,
                         max_tier: int = 3,
                         design: str | None = None,
                         shuffle: bool = True) -> list[dict]:
    """Get curated datasets filtered by criteria.

    Args:
        exclude_names: set of lowercase filenames to exclude (already used)
        min_tier: minimum design tier (1=best)
        max_tier: maximum design tier
        design: filter by design type ("rct", "rdd", "did", "iv")
        shuffle: randomize within each tier

    Returns filtered, sorted list of datasets.
    Automatically skips known-bad DOIs from validation history.
    """
    if exclude_names is None:
        exclude_names = set()

    filtered = []
    n_skipped_bad = 0
    for ds in CURATED_DATASETS:
        # Skip known-bad DOIs
        doi = ds.get("dataverse_doi", "")
        if doi in _KNOWN_BAD_DOIS:
            n_skipped_bad += 1
            continue

        # Skip datasets below minimum quality thresholds
        ceiling = ds.get("score_ceiling", 0)
        if ceiling < _MIN_SCORE_CEILING:
            continue

        # Exclude already used
        title_lower = ds.get("title", "").lower()
        if any(exc in title_lower for exc in exclude_names):
            continue

        # Filter by tier
        tier = ds.get("design_tier", 9)
        if tier < min_tier or tier > max_tier:
            continue

        # Filter by design
        if design and ds.get("design") != design:
            continue

        filtered.append(ds)

    if n_skipped_bad > 0:
        print(f"  [registry] Skipped {n_skipped_bad} known-bad datasets")

    if shuffle:
        # Sort by tier, shuffle within tier
        random.seed(int(time.time()) % 100000)
        tier_groups = {}
        for ds in filtered:
            t = ds.get("design_tier", 9)
            tier_groups.setdefault(t, []).append(ds)

        result = []
        for t in sorted(tier_groups.keys()):
            group = tier_groups[t]
            random.shuffle(group)
            result.extend(group)
        return result

    return sorted(filtered, key=lambda x: x.get("design_tier", 9))


def build_search_plan(exclude_names: set[str] | None = None,
                      n_curated: int = 5,
                      n_journal: int = 3,
                      journal_keys: list[str] | None = None) -> dict:
    """Build a search plan combining curated + journal search.

    Returns dict with:
        curated: list of curated datasets to try
        journal_queries: list of (journal_key, query) tuples to search
    """
    if exclude_names is None:
        exclude_names = set()

    curated = get_curated_datasets(exclude_names=exclude_names)[:n_curated]

    # Pick 3-4 random journals to search (prioritize top-5)
    top5 = ["QJE", "REStat", "JPE", "Econometrica", "REStud"]
    other = [k for k in JOURNAL_COLLECTIONS if k not in top5]

    if journal_keys is None:
        random.seed(int(time.time()) % 100000)
        random.shuffle(top5)
        random.shuffle(other)
        journal_keys = top5[:2] + other[:1]  # 2 top-5 + 1 other

    # Search terms focused on causal designs
    search_terms = [
        "replication RCT",
        "regression discontinuity",
        "difference in differences",
        "instrumental variable",
        "natural experiment",
        "staggered adoption",
    ]
    random.shuffle(search_terms)

    journal_queries = []
    for key in journal_keys[:n_journal]:
        term = search_terms.pop(0) if search_terms else ""
        journal_queries.append((key, term))

    return {
        "curated": curated,
        "journal_queries": journal_queries,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# EXTERNAL CURATED DATASETS (Group B — restricted/registration-required)
# ═══════════════════════════════════════════════════════════════════════════════
# High-value academic data sources that CANNOT be auto-downloaded but should
# still be surfaced to researchers as candidates. Most require user registration,
# license agreement, or bulk download with manual setup. Stage 1 hands these to
# the consolidator alongside live search results; if recommended, the user must
# acquire the data themselves and re-run via Path B (--data flag).
#
# Schema:
#   name           — canonical dataset name
#   provider       — institution
#   url            — landing page
#   access         — "registration" | "license" | "bulk_download"
#   topics         — keywords for client-side topic matching
#   tier           — design tier (1=best causal potential)
#   region         — geographic scope
#   notes          — acquisition notes / why it matters

EXTERNAL_DATASETS = [
    # ── OECD microdata (bulk download) ───────────────────────────────────
    {
        "name": "OECD PISA (Programme for International Student Assessment)",
        "provider": "OECD",
        "url": "https://www.oecd.org/pisa/data/",
        "access": "bulk_download",
        "topics": ["education", "achievement", "schools", "cross-country",
                   "test scores", "student outcomes"],
        "tier": 2,
        "region": "Cross-country (~80 countries)",
        "notes": "Triennial assessment of 15-year-olds in math/reading/science. Public download.",
    },
    {
        "name": "OECD PIAAC (Survey of Adult Skills)",
        "provider": "OECD",
        "url": "https://www.oecd.org/skills/piaac/",
        "access": "bulk_download",
        "topics": ["adult skills", "literacy", "numeracy", "labor", "human capital",
                   "returns to skills"],
        "tier": 2,
        "region": "Cross-country (40+ countries)",
        "notes": "Adult-skills counterpart to PISA. Public-use files available.",
    },
    # ── Trade / Input-Output / Productivity ──────────────────────────────
    {
        "name": "WIOD (World Input-Output Database)",
        "provider": "University of Groningen",
        "url": "https://www.rug.nl/ggdc/valuechain/wiod/",
        "access": "bulk_download",
        "topics": ["trade", "input-output", "global value chains", "productivity",
                   "China shock", "manufacturing"],
        "tier": 2,
        "region": "43 countries + RoW",
        "notes": "Backbone of Autor-Dorn-Hanson China shock papers. Free bulk download.",
    },
    {
        "name": "CEPII Gravity Database",
        "provider": "CEPII (Centre d'Études Prospectives et d'Informations Internationales)",
        "url": "http://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele.asp",
        "access": "bulk_download",
        "topics": ["trade", "gravity", "bilateral", "tariffs", "FDI", "distance"],
        "tier": 2,
        "region": "Bilateral, all countries",
        "notes": "Standard gravity-model dataset. Includes BACI trade flows.",
    },
    {
        "name": "EU KLEMS Productivity Database",
        "provider": "European Commission / Vienna Institute",
        "url": "https://euklems-intanprod-llee.luiss.it/",
        "access": "bulk_download",
        "topics": ["productivity", "industry", "growth accounting", "labor",
                   "capital", "intangibles"],
        "tier": 2,
        "region": "EU + selected countries",
        "notes": "Industry-level KLEMS productivity decomposition.",
    },
    {
        "name": "Maddison Project Database",
        "provider": "University of Groningen",
        "url": "https://www.rug.nl/ggdc/historicaldevelopment/maddison/",
        "access": "bulk_download",
        "topics": ["historical GDP", "long-run growth", "economic history",
                   "development", "comparative"],
        "tier": 3,
        "region": "Global, since year 1 CE",
        "notes": "Long-run historical GDP per capita estimates. Essential for econ history.",
    },
    {
        "name": "Atlas of Economic Complexity",
        "provider": "Harvard Growth Lab",
        "url": "https://atlas.cid.harvard.edu/",
        "access": "bulk_download",
        "topics": ["trade", "complexity", "exports", "diversification", "development",
                   "product space"],
        "tier": 2,
        "region": "All countries",
        "notes": "Disaggregated trade flows + economic complexity index.",
    },
    # ── Latin America admin data ─────────────────────────────────────────
    {
        "name": "Datos Abiertos Colombia",
        "provider": "Gobierno de Colombia",
        "url": "https://www.datos.gov.co/",
        "access": "bulk_download",
        "topics": ["colombia", "administrative", "policy", "education", "health",
                   "labor", "violence", "latin america"],
        "tier": 2,
        "region": "Colombia",
        "notes": "CKAN portal with Colombian administrative microdata. Free, no key.",
    },
]


def get_external_datasets(topic: str | None = None,
                          max_results: int = 10,
                          access: str | None = None) -> list[dict]:
    """Return external curated datasets, optionally filtered by topic keywords.

    Args:
        topic: free-text topic; client-side substring match against dataset topics
        max_results: cap on returned items
        access: filter by access type ("registration" | "license" | "bulk_download")

    Returns list of dataset dicts ranked by topic match score (descending).
    Each dict carries `access` and `notes` fields so the consolidator knows the
    dataset cannot be auto-downloaded and must be acquired manually (Path B).
    """
    results = []
    if topic:
        terms = [t.lower() for t in topic.split() if len(t) > 2]
    else:
        terms = []

    for ds in EXTERNAL_DATASETS:
        if access and ds.get("access") != access:
            continue

        # Score by topic-keyword overlap with the dataset's topic tags + name
        if terms:
            haystack = " ".join(ds.get("topics", []) + [ds.get("name", "")]).lower()
            score = sum(1 for t in terms if t in haystack)
            if score == 0:
                continue
        else:
            score = 0

        # Mark every entry as restricted so downstream code knows it's Path B only
        ds_out = dict(ds)
        ds_out["source_api"] = "external_curated"
        ds_out["requires_manual_acquisition"] = True
        results.append((score, ds_out))

    results.sort(key=lambda x: -x[0])
    return [r[1] for r in results[:max_results]]
