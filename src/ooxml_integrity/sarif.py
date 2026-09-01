"""SARIF 2.1.0 output, so findings land in a pull request instead of a log.

A CI job that fails with a message in its log makes someone open the log. A
SARIF report uploaded with `github/codeql-action/upload-sarif` puts the finding
on the changed line, in the review, where the person who caused it is already
looking. That is the whole reason this file exists; nothing here is clever.

Two decisions worth stating:

**Suppressed findings are still emitted, marked suppressed.** SARIF has a
`suppressions` field for exactly this. A report that silently omits what a
baseline or an ignore hid is a report you cannot audit, and the point of
requiring a reason for every ignore is lost if the reason never appears
anywhere.

**`level` follows the severity after policy, not before.** If a project lowered
a rule to a note, the review should show a note. The original severity is kept
in the result's properties so nothing is lost.
"""
from __future__ import annotations

import os
from typing import Any, Iterable

from . import __version__
from .finding import Finding, Severity

SARIF_VERSION = "2.1.0"
SCHEMA = ("https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/"
          "Schemata/sarif-schema-2.1.0.json")

#: SARIF has error / warning / note / none.
LEVELS = {Severity.ERROR: "error", Severity.WARN: "warning",
          Severity.INFO: "note"}


def _uri(path: str) -> str:
    p = str(path).replace(os.sep, "/")
    return p[2:] if p.startswith("./") else p


def _result(file: str, f: Finding, suppressed_why: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {
        "ruleId": f.code,
        "level": LEVELS[f.severity],
        "message": {"text": f.message},
        "locations": [{
            "physicalLocation": {
                "artifactLocation": {"uri": _uri(file)},
                # No line numbers: the artifact is a zip of XML, and a line in
                # word/document.xml is not something a reviewer can act on.
                # The location within the package goes in the message and in
                # properties instead.
            }
        }],
        "properties": {"severity": f.severity.value},
    }
    if f.where:
        out["properties"]["where"] = f.where
    if f.part:
        out["properties"]["part"] = f.part
    if suppressed_why:
        out["suppressions"] = [{
            "kind": "external",
            "justification": suppressed_why,
        }]
    return out


def build(results: dict[str, list[Finding]],
          suppressed: dict[str, list[tuple[Finding, str]]] | None = None,
          ) -> dict[str, Any]:
    """A SARIF log for one run over several files."""
    suppressed = suppressed or {}
    rules: dict[str, dict[str, Any]] = {}
    out_results: list[dict[str, Any]] = []

    def note_rule(f: Finding) -> None:
        rules.setdefault(f.code, {
            "id": f.code,
            "shortDescription": {"text": f.code},
            "defaultConfiguration": {"level": LEVELS[f.severity]},
        })

    for file, findings in results.items():
        for f in findings:
            note_rule(f)
            out_results.append(_result(file, f))
    for file, pairs in suppressed.items():
        for f, why in pairs:
            note_rule(f)
            out_results.append(_result(file, f, suppressed_why=why))

    return {
        "$schema": SCHEMA,
        "version": SARIF_VERSION,
        "runs": [{
            "tool": {"driver": {
                "name": "ooxml-integrity",
                "version": __version__,
                "informationUri": "https://github.com/Dmitry-Kov/ooxml-integrity",
                "rules": [rules[k] for k in sorted(rules)],
            }},
            "results": out_results,
        }],
    }
