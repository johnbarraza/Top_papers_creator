"""Quantitative-macro (general equilibrium) track for Papers-HQ.

- equilibrium_checks.py  model-agnostic GE / numerical tests + TestReport
- ha_core.py             HJB-KFE toolkit (Huggett, Aiyagari, one-asset HANK)
- model_catalog.py       model classes, test contracts, template defaults

equilibrium_checks.py and ha_core.py are copied verbatim into each macro
project's scripts/python/ so the replication package is self-contained.
"""

import re
import shutil
from pathlib import Path

MACRO_DIR = Path(__file__).resolve().parent
SUPPORT_FILES = ("equilibrium_checks.py", "ha_core.py")
# Upper-case only: f-strings in the templates contain literal {{table}} etc.
PLACEHOLDER = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


def install_support_files(scripts_dir: Path) -> list[Path]:
    """Copy the solver library into a project's scripts directory."""
    scripts_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name in SUPPORT_FILES:
        target = scripts_dir / name
        shutil.copyfile(MACRO_DIR / name, target)      # byte-exact copy
        written.append(target)
    return written


def render_template(content: str, values: dict[str, str]) -> str:
    """Fill {{NAME}} placeholders with Python literals (strings as source)."""
    def sub(m):
        key = m.group(1)
        if key not in values:
            raise KeyError(f"No value for placeholder {{{{{key}}}}}")
        return values[key]
    return PLACEHOLDER.sub(sub, content)


def unfilled_placeholders(content: str) -> list[str]:
    return list(dict.fromkeys(PLACEHOLDER.findall(content)))
