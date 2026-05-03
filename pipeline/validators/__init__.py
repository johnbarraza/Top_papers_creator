"""Validation framework for pipeline quality gates.

Validators run programmatic checks BEFORE the LLM critic.
HARD checks are objective facts (files exist, scripts ran, citations match).
SOFT checks are informational (word count, code patterns).

A single HARD failure vetoes the gate regardless of critic score.
"""

from dataclasses import dataclass, field
from enum import Enum


class CheckLevel(Enum):
    HARD = "HARD"
    SOFT = "SOFT"


@dataclass
class Check:
    name: str
    level: CheckLevel
    passed: bool
    detail: str = ""


@dataclass
class ValidationResult:
    checks: list = field(default_factory=list)

    def add(self, name: str, level: CheckLevel, passed: bool, detail: str = ""):
        self.checks.append(Check(name, level, passed, detail))

    @property
    def hard_pass(self) -> bool:
        hard_checks = [c for c in self.checks if c.level == CheckLevel.HARD]
        return all(c.passed for c in hard_checks)

    @property
    def hard_failures(self) -> list:
        return [c for c in self.checks if c.level == CheckLevel.HARD and not c.passed]

    @property
    def soft_failures(self) -> list:
        return [c for c in self.checks if c.level == CheckLevel.SOFT and not c.passed]

    @property
    def summary_counts(self) -> dict:
        hard = [c for c in self.checks if c.level == CheckLevel.HARD]
        soft = [c for c in self.checks if c.level == CheckLevel.SOFT]
        return {
            "hard_passed": sum(1 for c in hard if c.passed),
            "hard_failed": sum(1 for c in hard if not c.passed),
            "hard_total": len(hard),
            "soft_passed": sum(1 for c in soft if c.passed),
            "soft_failed": sum(1 for c in soft if not c.passed),
            "soft_total": len(soft),
        }

    def format_for_critic(self) -> str:
        lines = ["=== AUTOMATED VALIDATION RESULTS ==="]
        counts = self.summary_counts
        lines.append(
            f"HARD checks: {counts['hard_passed']}/{counts['hard_total']} passed  "
            f"| SOFT checks: {counts['soft_passed']}/{counts['soft_total']} passed"
        )
        if not self.hard_pass:
            lines.append(
                "\n** HARD FAILURES (must be fixed before approval): **"
            )
        for c in self.checks:
            status = "PASS" if c.passed else "FAIL"
            lines.append(f"  [{c.level.value}] [{status}] {c.name}: {c.detail}")
        return "\n".join(lines)

    def format_for_log(self) -> str:
        counts = self.summary_counts
        status = "PASS" if self.hard_pass else "HARD FAIL"
        return (
            f"Validation {status}: "
            f"hard {counts['hard_passed']}/{counts['hard_total']}, "
            f"soft {counts['soft_passed']}/{counts['soft_total']}"
        )
