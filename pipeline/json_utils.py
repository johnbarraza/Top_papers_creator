"""JSON extraction and validation helpers."""

import json
import re
from typing import Optional


def extract_json(text: str, *, key: Optional[str] = None) -> dict | list | None:
    """Extract a JSON block from Claude's response text.

    Tries, in order:
      1. Fenced ```json ... ``` blocks (greedy — picks the largest).
      2. The outermost ``{ ... }`` or ``[ ... ]`` literal.

    Parameters
    ----------
    text : str
        The raw response text.
    key : str, optional
        If given, return ``data[key]`` instead of the whole object.
    """
    # 1. Fenced JSON blocks
    for match in re.finditer(r'```json\s*\n(.*?)\n\s*```', text, re.DOTALL):
        try:
            data = json.loads(match.group(1))
            return data.get(key) if key else data
        except json.JSONDecodeError:
            continue

    # 2. Outermost braces / brackets
    for opener, closer in [("{", "}"), ("[", "]")]:
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(text[start : i + 1])
                        return data.get(key) if key else data
                    except json.JSONDecodeError:
                        break

    return None


def validate_keys(data: dict, required: list[str]) -> list[str]:
    """Return a list of missing keys (empty list means all present)."""
    if not isinstance(data, dict):
        return required
    return [k for k in required if k not in data]


def smart_truncate(text: str, max_chars: int, *, keep_end: int = 0) -> str:
    """Truncate text at a paragraph or sentence boundary instead of mid-word.

    Parameters
    ----------
    text : str
        The text to truncate.
    max_chars : int
        Maximum characters to keep (approximate — may be slightly less).
    keep_end : int
        If > 0, also keep the last *keep_end* characters, separated by a
        ``[... truncated ...]`` marker.  Useful for keeping closing sections.
    """
    if len(text) <= max_chars + keep_end:
        return text

    if keep_end > 0:
        head_budget = max_chars
        tail = text[-keep_end:]
        head_text = text[:head_budget]
    else:
        head_text = text[:max_chars]
        tail = ""

    # Cut at the last paragraph break (double newline)
    cut = head_text.rfind("\n\n")
    if cut < max_chars * 0.5:
        # Fall back to last single newline
        cut = head_text.rfind("\n")
    if cut < max_chars * 0.3:
        # Fall back to last sentence end
        for sep in [". ", ".\n", ")\n"]:
            pos = head_text.rfind(sep)
            if pos > cut:
                cut = pos + len(sep) - 1
    if cut < max_chars * 0.3:
        cut = max_chars  # give up, hard cut

    result = head_text[: cut + 1].rstrip()

    if tail:
        return result + "\n\n[... truncated ...]\n\n" + tail.lstrip()
    if len(text) > len(result):
        return result + "\n[... truncated ...]"
    return result
