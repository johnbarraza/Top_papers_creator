"""Paper-type routing: empirical (identification-first) vs macro (GE models)."""

from .config import DEFAULT_PAPER_TYPE, MACRO_STAGE_NAMES, PAPER_TYPES, STAGE_NAMES


def get_paper_type(state: dict) -> str:
    pt = state.get("config", {}).get("paper_type") or DEFAULT_PAPER_TYPE
    return pt if pt in PAPER_TYPES else "empirical"


def is_macro(state: dict) -> bool:
    return get_paper_type(state) == "macro"


def stage_name(stage_num: float, state: dict) -> str:
    if is_macro(state) and stage_num in MACRO_STAGE_NAMES:
        return MACRO_STAGE_NAMES[stage_num]
    return STAGE_NAMES.get(stage_num, "Unknown")
