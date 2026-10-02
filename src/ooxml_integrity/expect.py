"""Expected findings: changes a caller asked for, declared before the run.

A baseline says "we know about this finding, not today". An expectation says
"this change was requested": accepting a named revision lowers the revision
count (`FID001`), an untracked edit to a header changes that story (`FID007`).
Without a way to say so, a correct edit and a damaging one look the same to
`compare()`, and a pipeline that edits headers on purpose learns to ignore
`FID007` altogether.

An expectation names a rule code and, optionally, values the finding must
carry: `part`, `where`, or any key of its `extra` (`tag`, `before` and `after`
for `FID001`; `story_kind`, `variant` and `body` for `FID007`; `body` for the
note and comment rules). Values compare as text. A matching finding is
reported as expected, with the reason, and does not fail the run. An
expectation that matches nothing in a file it applies to is an `EXP001` error:
the requested change did not happen, or not the way it was declared. That is
the difference from a baseline, which only ever hides. An expectation with
`required=False` only allows its finding: use it where the checker may or may
not see the requested change, for example `FID009` for a direct edit inside a
pending insertion that holds another author's nested deletion.

Like the rest of the policy layer this never alters what `check()` and
`compare()` report; it sorts their findings afterwards.

    >>> from ooxml_integrity import Expectation, compare, expect
    >>> accepted = Expectation("FID001", {"tag": "ins", "before": 2, "after": 0},
    ...                        reason="the pipeline accepts both insertions")
    >>> kept, expected = expect(compare("in.docx", "out.docx"), [accepted])
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .finding import ERROR, Finding

#: Keys that read a Finding attribute rather than a key of its `extra`.
ATTRIBUTES = ("part", "where")


@dataclass(frozen=True)
class Expectation:
    code: str
    match: Mapping[str, Any] = field(default_factory=dict)
    reason: str = ""
    path: str = "**"
    required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", str(self.code).strip().upper())
        object.__setattr__(self, "match", {str(k): v for k, v in dict(self.match).items()})

    def matches(self, finding: Finding) -> bool:
        if finding.code != self.code:
            return False
        for key, value in self.match.items():
            actual = getattr(finding, key) if key in ATTRIBUTES else finding.extra.get(key)
            if actual is None or str(actual) != str(value):
                return False
        return True

    def describe(self) -> str:
        values = " ".join(f"{k}={v!r}" if isinstance(v, str) and (" " in v or not v)
                          else f"{k}={v}" for k, v in self.match.items())
        return f"{self.code} {values}".strip()

    @classmethod
    def parse(cls, spec: str, reason: str = "declared with --expect") -> "Expectation":
        """`CODE` or `CODE:key=value,key=value`. Values cannot contain commas;
        declare text values such as a story body in the config file instead."""
        code, _, rest = spec.partition(":")
        if not code.strip():
            raise ValueError(f"expectation {spec!r} has no rule code")
        match = {}
        for item in filter(None, (x.strip() for x in rest.split(","))):
            key, sep, value = item.partition("=")
            if not sep or not key.strip():
                raise ValueError(f"expectation {spec!r}: {item!r} is not key=value")
            match[key.strip()] = value.strip()
        return cls(code, match, reason=reason)


def unmet(expectation: Expectation) -> Finding:
    """EXP001: a declared change that the edited file does not show."""
    because = f" ({expectation.reason})" if expectation.reason else ""
    return Finding(
        "EXP001", ERROR,
        f"expected finding did not occur: {expectation.describe()}{because} - the "
        "requested change was not made, or not the way it was declared",
        extra={"expected": expectation.code, "match": dict(expectation.match),
               "reason": expectation.reason},
    )


def expect(findings: Iterable[Finding], expectations: Iterable[Expectation],
           file: str = "") -> tuple[list[Finding], list[tuple[Finding, str]]]:
    """Returns (kept, [(expected finding, why)]). `kept` gains one EXP001 for
    every expectation that applies to `file` and matched nothing."""
    from .policy import _match

    findings = list(findings)
    applying = [e for e in expectations if not file or _match(file, e.path)]
    kept: list[Finding] = []
    matched: list[tuple[Finding, str]] = []
    used = set()
    for f in findings:
        hits = [i for i, e in enumerate(applying) if e.matches(f)]
        if hits:
            used.update(hits)
            first = applying[hits[0]]
            matched.append((f, f"{first.describe()}: {first.reason}" if first.reason
                               else first.describe()))
        else:
            kept.append(f)
    kept.extend(unmet(e) for i, e in enumerate(applying) if i not in used and e.required)
    return kept, matched
