"""The single result type shared by the inspector and the fidelity check."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Ordered so comparisons work: ERROR > WARN > INFO."""

    ERROR = "error"
    WARN = "warn"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"error": 3, "warn": 2, "info": 1}[self.value]

    def __ge__(self, other: "Severity") -> bool:  # type: ignore[override]
        return self.rank >= other.rank

    def __gt__(self, other: "Severity") -> bool:  # type: ignore[override]
        return self.rank > other.rank

    def __le__(self, other: "Severity") -> bool:  # type: ignore[override]
        return self.rank <= other.rank

    def __lt__(self, other: "Severity") -> bool:  # type: ignore[override]
        return self.rank < other.rank

    @classmethod
    def parse(cls, s: str) -> "Severity":
        try:
            return cls(s.strip().lower())
        except ValueError:
            raise ValueError(
                f"unknown severity {s!r}; expected one of: "
                + ", ".join(m.value for m in cls)
            ) from None


# Convenience aliases, so check code reads cleanly.
ERROR = Severity.ERROR
WARN = Severity.WARN
INFO = Severity.INFO


@dataclass(frozen=True)
class Finding:
    """One problem found in one document.

    code     stable identifier, e.g. CMT005 - safe to grep, safe to suppress
    severity ERROR / WARN / INFO
    message  human-readable, says what breaks rather than what rule fired
    where    XPath to the offending node, or a part name, when known
    part     the package part the finding belongs to, when known
    """

    code: str
    severity: Severity
    message: str
    where: str = ""
    part: str = ""
    extra: dict[str, Any] = field(default_factory=dict, compare=False)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        if not d["extra"]:
            d.pop("extra")
        return {k: v for k, v in d.items() if v != ""}

    def __str__(self) -> str:
        head = f"[{self.severity.value.upper():5}] {self.code}  {self.message}"
        return f"{head}\n          -> {self.where}" if self.where else head


def summarize(findings: list[Finding]) -> dict[str, int]:
    """Counts by severity, always with all three keys present."""
    out = {m.value: 0 for m in Severity}
    for f in findings:
        out[f.severity.value] += 1
    return out


def worst(findings: list[Finding]) -> Severity | None:
    """Highest severity present, or None for an empty list."""
    return max((f.severity for f in findings), key=lambda s: s.rank, default=None)
