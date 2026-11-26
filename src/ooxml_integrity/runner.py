"""Unified single-pass verification runner and public `verify()` API.

All user-facing adapters (CLI, MCP server, browser demo bridge, and direct
Python callers) share this orchestration layer so check execution, policy
application, coverage reporting, verdict wording and JSON serialization never
drift apart.
"""
from __future__ import annotations

import json
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .archive import DEFAULT_ARCHIVE_LIMITS, ArchiveLimits, PackageIssue, PackageSource
from .coverage import CoverageReport, CoverageStatus, coverage_for
from .expect import Expectation, expect as apply_expectations
from .fidelity import compare
from .finding import Finding, Severity, summarize, worst
from .inspector import check
from .introduced import REASON as INHERITED, source_findings, split as split_inherited
from .package import LoadedPackage
from .paths import DECK_SUFFIXES
from .policy import Policy, apply_baseline
from .pptx_checks import check_pptx
from .sarif import build as build_sarif

SCHEMA_VERSION = 1
VERIFICATION_REPORT_SCHEMA = "ooxml-integrity.verification-report.v1"

EXIT_OK, EXIT_FINDINGS, EXIT_USAGE = 0, 1, 2

SUPPORTED_PROFILES = frozenset({"default"})

#: Coverage statuses that mean part of the file was not fully assessed. A file
#: with any of them and no findings is "no findings in checked surfaces", never
#: "clean".
GAP_STATUSES = (
    CoverageStatus.ESTIMATED,
    CoverageStatus.SKIPPED,
    CoverageStatus.UNSUPPORTED,
)


def _source_label(source: PackageSource | LoadedPackage) -> str:
    if isinstance(source, LoadedPackage):
        return source.label
    if isinstance(source, (str, Path)):
        return str(source)
    if isinstance(source, (bytes, bytearray, memoryview)):
        return "<bytes>"
    name = getattr(source, "name", None)
    return str(name) if isinstance(name, (str, Path)) and str(name) else "<stream>"


def try_open(
    source: PackageSource | LoadedPackage,
    limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS,
    *,
    label: str | None = None,
) -> LoadedPackage | None:
    """Open a readable package once; unreadable inputs fall back to normal checks."""
    try:
        return LoadedPackage.open(source, limits=limits, label=label)
    except (FileNotFoundError, PackageIssue, zipfile.BadZipFile, OSError):
        return None


def run_checks(
    target: PackageSource | LoadedPackage,
    source: PackageSource | LoadedPackage | None = None,
    limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS,
) -> list[Finding]:
    """Run structural (or PPTX layout) checks plus optional fidelity comparison."""
    file_path: Path | None
    if isinstance(target, LoadedPackage):
        file_path = target.path
    elif isinstance(target, (str, Path)):
        file_path = Path(target)
    else:
        file_path = None

    is_deck = (
        file_path.suffix.lower() in DECK_SUFFIXES
        if file_path is not None
        else isinstance(target, LoadedPackage) and target.is_deck
    )
    if is_deck:
        suffix = file_path.suffix.lower() if file_path is not None else ".pptx"
        if source is not None:
            return check_pptx(target, limits=limits) + [
                Finding(
                    "FID000", Severity.ERROR,
                    "comparison was NOT performed: --against source comparison "
                    f"is not implemented for {suffix} files; "
                    "only layout checks were run",
                )
            ]
        return check_pptx(target, limits=limits)

    findings = check(target, limits=limits)
    unreadable = any(
        f.code in ("PKG000", "PKG001", "PKG002", "PKG007", "PKG008")
        for f in findings
    )
    if source is not None and not unreadable:
        source_label = _source_label(source)
        try:
            findings = findings + compare(source, target, limits=limits)
        except Exception as e:
            findings = findings + [
                Finding(
                    "FID000", Severity.ERROR,
                    f"comparison was NOT performed against {source_label}: {e}",
                )
            ]
    return findings


def apply_policy(
    path: Path | str,
    findings: list[Finding],
    policy: Policy,
    expectations: Sequence[Expectation] = (),
    allowance: dict[str, int] | None = None,
    inherited_from: list[Finding] | None = None,
) -> tuple[list[Finding], list[tuple[Finding, str]], list[tuple[Finding, str]]]:
    """Config, then `--introduced`, then expectations, then baseline.

    Returns ``(kept, hidden_with_reason, expected_with_reason)``.
    """
    path_str = str(path)
    kept, dropped = policy.apply(path_str, findings)
    if inherited_from is not None:
        kept, inherited = split_inherited(kept, inherited_from)
        dropped = dropped + inherited
    matched: list[tuple[Finding, str]] = []
    if expectations:
        kept, matched = apply_expectations(kept, list(expectations), path_str)
    if allowance is not None:
        kept, base_dropped = apply_baseline(path_str, kept, allowance)
        dropped = dropped + base_dropped
    return kept, dropped, matched


def fails(findings: Sequence[Finding], threshold: Severity) -> bool:
    return any(f.severity >= threshold for f in findings)


def has_gaps(coverage: CoverageReport | None) -> bool:
    return coverage is not None and any(
        item.status in GAP_STATUSES for item in coverage.items
    )


def format_head(path: Path | str, findings: Sequence[Finding]) -> str:
    counts = summarize(findings)
    return (
        f"{path}: "
        f"{counts['error']} error(s), {counts['warn']} warning(s), "
        f"{counts['info']} info"
    )


def _codes(findings: Sequence[Finding]) -> str:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.code] = counts.get(f.code, 0) + 1
    return ", ".join(
        code if n == 1 else f"{code} ({n})" for code, n in counts.items()
    )


def _shown(path: str) -> str:
    """A config path as short as it can be said: relative when below cwd."""
    try:
        relative = os.path.relpath(path)
    except ValueError:  # another drive on Windows
        return path
    return path if relative.startswith("..") else relative


def format_verdict(
    path: Path | str,
    findings: Sequence[Finding],
    threshold: Severity,
    coverage: CoverageReport | None,
    expected: Sequence[tuple[Finding, str]] = (),
    hidden: Sequence[tuple[Finding, str]] = (),
    config: str = "",
    note: str = "",
) -> str:
    """One line: the CLI's summary head, then what it means at `threshold`."""
    line = format_head(path, findings)
    failing = [f for f in findings if f.severity >= threshold]
    gaps = has_gaps(coverage)
    if failing:
        line += f" - fails at fail-on {threshold.value}: {_codes(failing)}"
    elif findings:
        line += (
            f" - nothing at or above fail-on {threshold.value}; "
            f"below it: {_codes(findings)}"
        )
    else:
        line += " - no findings in checked surfaces" if gaps else " - clean"
    if expected:
        line += (
            f"; {len(expected)} finding(s) accepted as expected: "
            f"{_codes([f for f, _ in expected])}"
        )
    inherited = [f for f, why in hidden if why == INHERITED]
    by_config = [f for f, why in hidden if why != INHERITED]
    if by_config:
        line += (
            f"; {len(by_config)} finding(s) suppressed by config"
            + (f" {_shown(config)}" if config else "")
            + f": {_codes(by_config)}"
        )
    if inherited:
        line += (
            f"; {len(inherited)} finding(s) already in the original, "
            f"not failing: {_codes(inherited)}"
        )
    if note:
        line += f"; {note}"
    if gaps and coverage is not None:
        counts = coverage.summary()
        line += "; not fully checked: " + ", ".join(
            f"{counts[s.value]} {s.value}" for s in GAP_STATUSES
            if counts[s.value]
        ) + " (see coverage)"
    return line


def format_human(
    path: Path | str,
    findings: Sequence[Finding],
    threshold: Severity,
    *,
    quiet: bool = False,
    coverage: CoverageReport | None = None,
) -> str:
    """Format one file's human-readable findings block with trailing newline."""
    shown = [f for f in findings if f.severity >= threshold] if quiet else list(findings)
    head = format_head(path, findings)
    if not shown and not findings:
        suffix = "no findings in checked surfaces" if has_gaps(coverage) else "clean"
        return f"{head}  - {suffix}\n"
    lines = [head]
    for f in shown:
        lines.append("  " + str(f).replace("\n", "\n  "))
    return "\n".join(lines) + "\n"


def format_coverage(report: CoverageReport, *, details: bool = False) -> str:
    """Format one file's coverage summary block with trailing newline."""
    counts = report.summary()
    summary = ", ".join(
        f"{counts[status.value]} {status.value}"
        for status in CoverageStatus if counts[status.value]
    )
    lines = [f"  coverage: {summary}"]
    visible = (
        report.items if details else tuple(
            item for item in report.items if item.status in GAP_STATUSES
        )
    )
    for item in visible:
        lines.append(f"    [{item.status.value}] {item.id}: {item.reason}")
    return "\n".join(lines) + "\n"


def json_file(
    path: Path | str,
    findings: Sequence[Finding],
    hidden: Sequence[tuple[Finding, str]] = (),
    matched: Sequence[tuple[Finding, str]] = (),
    *,
    expectations: bool = False,
    coverage: CoverageReport | None = None,
) -> dict[str, Any]:
    """One file's entry in the `--json` / MCP / browser report."""
    item: dict[str, Any] = {
        "path": str(path),
        "summary": summarize(findings),
        "worst": (w.value if (w := worst(findings)) else None),
        "findings": [x.as_dict() for x in findings],
        "suppressed": [
            {**x.as_dict(), "suppressed_because": why} for x, why in hidden
        ],
    }
    if expectations:
        item["expected"] = [
            {**x.as_dict(), "expected_because": why} for x, why in matched
        ]
    if coverage is not None:
        item["coverage"] = coverage.as_dict()
    return item


def json_payload(
    files: list[dict[str, Any]],
    threshold: Severity,
    policy: Policy | None = None,
    baseline: str | None = None,
    *,
    config: str | None = None,
    introduced: bool = False,
) -> dict[str, Any]:
    """Top-level `--json` / `--json-out` / MCP / browser report envelope.

    Preserves the existing multi-file `files[]` CLI contract (`version`,
    `fail_on`, `config`, `baseline`, `files`, optional `introduced`) without
    colliding with `VerificationReport.to_dict()`'s single-document schema.
    """
    resolved_config = (
        config if config is not None
        else (policy.source or None if policy is not None else None)
    )
    payload: dict[str, Any] = {
        "version": __version__,
        "fail_on": threshold.value,
        "config": resolved_config,
        "baseline": baseline,
    }
    if introduced:
        # Optional: present only when the source's own findings were set aside.
        payload["introduced"] = True
    payload["files"] = files
    return payload


@dataclass(frozen=True)
class SuppressedFinding:
    finding: Finding
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {**self.finding.as_dict(), "suppressed_because": self.reason}


@dataclass(frozen=True)
class ExpectedFinding:
    finding: Finding
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {**self.finding.as_dict(), "expected_because": self.reason}


@dataclass(frozen=True)
class VerificationReport:
    """Single-document result returned by `verify()`.

    `verify()`, `VerificationReport` and its `to_dict()` JSON format are
    provisional and may change before 1.0. `to_dict()` carries
    `"schema": "ooxml-integrity.verification-report.v1"` and
    `"schema_version": 1` so consumers can distinguish it unambiguously
    from the multi-file `check --json` envelope (`to_cli_report()`).
    """

    schema: str
    schema_version: int
    checker_version: str
    passed: bool
    exit_code: int
    verdict: str
    fail_on: Severity
    profile: str
    path: str
    sha256: str | None
    source_path: str | None
    source_sha256: str | None
    findings: tuple[Finding, ...]
    suppressed: tuple[SuppressedFinding, ...]
    expected: tuple[ExpectedFinding, ...]
    coverage: CoverageReport | None
    config: str | None = None
    baseline: str | None = None
    introduced: bool = False
    expectations_configured: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Single-document structured report (`ooxml-integrity.verification-report.v1`)."""
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "checker_version": self.checker_version,
            "passed": self.passed,
            "exit_code": self.exit_code,
            "verdict": self.verdict,
            "fail_on": self.fail_on.value,
            "profile": self.profile,
            "path": self.path,
            "sha256": self.sha256,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "config": self.config,
            "baseline": self.baseline,
            "introduced": self.introduced,
            "summary": summarize(self.findings),
            "worst": (w.value if (w := worst(self.findings)) else None),
            "findings": [f.as_dict() for f in self.findings],
            "suppressed": [s.as_dict() for s in self.suppressed],
            "expected": [e.as_dict() for e in self.expected],
            "coverage": self.coverage.as_dict() if self.coverage is not None else None,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=True)

    def to_text(
        self,
        *,
        quiet: bool = False,
        show_suppressed: bool = False,
        coverage_details: bool = False,
    ) -> str:
        parts = [
            format_human(
                self.path, self.findings, self.fail_on,
                quiet=quiet, coverage=self.coverage,
            )
        ]
        if self.coverage is not None:
            parts.append(format_coverage(self.coverage, details=coverage_details))
        for exp in self.expected:
            parts.append(f"  [expected] {exp.reason}\n")
        if show_suppressed:
            for sup in self.suppressed:
                parts.append(f"  [hidden] {sup.finding.code}  {sup.reason}\n")
        return "".join(parts)

    def to_sarif(self) -> dict[str, Any]:
        suppressed = [
            *((s.finding, s.reason) for s in self.suppressed),
            *((e.finding, e.reason) for e in self.expected),
        ]
        return build_sarif(
            {self.path: list(self.findings)},
            {self.path: suppressed},
        )

    def to_cli_file(self) -> dict[str, Any]:
        """Entry matching the multi-file CLI / MCP / browser JSON schema."""
        return json_file(
            self.path,
            self.findings,
            [(s.finding, s.reason) for s in self.suppressed],
            [(e.finding, e.reason) for e in self.expected],
            expectations=self.expectations_configured,
            coverage=self.coverage,
        )

    def to_cli_report(self) -> dict[str, Any]:
        """Envelope matching `ooxml-integrity check --json`."""
        return json_payload(
            [self.to_cli_file()],
            self.fail_on,
            config=self.config,
            baseline=self.baseline,
            introduced=self.introduced,
        )


def verify(
    target: PackageSource | LoadedPackage,
    *,
    against: PackageSource | LoadedPackage | None = None,
    fail_on: Severity | str | None = None,
    profile: str = "default",
    policy: Policy | None = None,
    expect: Sequence[Expectation | str] = (),
    baseline: dict[str, int] | None = None,
    baseline_path: str | None = None,
    introduced: bool = False,
    coverage: bool = True,
    limits: ArchiveLimits | None = None,
    label: str | None = None,
    source_label: str | None = None,
    note: str = "",
) -> VerificationReport:
    """Verify one OOXML package in a single pass and return a `VerificationReport`.

    Accepts filesystem paths, raw `bytes`/`bytearray`/`memoryview`, seekable
    binary streams, or pre-opened `LoadedPackage` instances for both `target`
    and `against`.
    """
    if profile not in SUPPORTED_PROFILES:
        valid = ", ".join(sorted(SUPPORTED_PROFILES))
        raise ValueError(f"unknown profile {profile!r}; expected one of: {valid}")
    if introduced and against is None:
        raise ValueError("introduced=True requires against")

    active_policy = policy if policy is not None else Policy()
    active_limits = limits if limits is not None else active_policy.archive

    if fail_on is None:
        threshold = active_policy.fail_on
    elif isinstance(fail_on, Severity):
        threshold = fail_on
    else:
        threshold = Severity.parse(fail_on)

    parsed_expect = [
        e if isinstance(e, Expectation) else Expectation.parse(e)
        for e in expect
    ]
    all_expectations = active_policy.expectations + parsed_expect

    display_path = label if label is not None else _source_label(target)
    display_source = (
        source_label if source_label is not None
        else (_source_label(against) if against is not None else None)
    )

    target_pkg = try_open(target, active_limits, label=display_path)
    source_pkg = (
        try_open(against, active_limits, label=display_source)
        if against is not None else None
    )
    target_input: PackageSource | LoadedPackage = (
        target_pkg if target_pkg is not None else target
    )
    source_input: PackageSource | LoadedPackage | None = (
        source_pkg if source_pkg is not None else against
    )

    raw_findings = run_checks(target_input, source_input, active_limits)
    cov_report = (
        coverage_for(
            target_input, raw_findings, source=source_input, limits=active_limits,
        )
        if coverage else None
    )
    inherited_from = (
        source_findings(source_input, limits=active_limits)
        if introduced and source_input is not None else None
    )

    policy_path = (
        str(target_pkg.path) if target_pkg is not None and target_pkg.path is not None
        else (str(target) if isinstance(target, (str, Path)) else display_path)
    )
    kept, hidden, matched = apply_policy(
        policy_path, raw_findings, active_policy,
        all_expectations, baseline, inherited_from,
    )

    failed = fails(kept, threshold)
    verdict_line = format_verdict(
        display_path, kept, threshold, cov_report,
        matched, hidden, active_policy.source, note,
    )
    return VerificationReport(
        schema=VERIFICATION_REPORT_SCHEMA,
        schema_version=SCHEMA_VERSION,
        checker_version=__version__,
        passed=not failed,
        exit_code=EXIT_FINDINGS if failed else EXIT_OK,
        verdict=verdict_line,
        fail_on=threshold,
        profile=profile,
        path=display_path,
        sha256=target_pkg.sha256 if target_pkg is not None else None,
        source_path=display_source,
        source_sha256=source_pkg.sha256 if source_pkg is not None else None,
        findings=tuple(kept),
        suppressed=tuple(SuppressedFinding(f, why) for f, why in hidden),
        expected=tuple(ExpectedFinding(f, why) for f, why in matched),
        coverage=cov_report,
        config=active_policy.source or None,
        baseline=baseline_path,
        introduced=bool(introduced and against is not None),
        expectations_configured=bool(all_expectations),
    )
