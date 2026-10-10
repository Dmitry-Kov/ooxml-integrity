"""Command line interface.

Exit codes are the contract with CI:

    0   nothing at or above the --fail-on threshold
    1   findings at or above the threshold
    2   usage error, or a file that could not be read at all
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

from . import __version__
from .archive import ArchiveLimits
from .coverage import CoverageReport, CoverageStatus, coverage_for
from .doctor import build_report as build_doctor_report
from .expect import Expectation, expect
from .fidelity import compare
from .finding import Finding, Severity, summarize, worst
from .inspector import check
from .policy import (
    ConfigError, DEFAULT_BASELINE, NOT_BASELINED, Policy, apply_baseline,
    make_baseline, read_baseline,
)
from .pptx_checks import check_pptx
from .sarif import build as build_sarif

EXIT_OK, EXIT_FINDINGS, EXIT_USAGE = 0, 1, 2


_GLOB_CHARS = "*?["


def _expand(patterns: list[str]) -> tuple[list[Path], list[str]]:
    """Expand globs ourselves so behaviour matches on every shell and OS.

    A named path that does not exist is kept, so it gets reported as a finding
    about that file rather than silently skipped. A *glob* that matches nothing
    is different: there is no file to report on, and "file not found: *.docx"
    would be a nonsense message. Those come back as `empty` for the caller to
    treat as a usage error.
    """
    found: list[Path] = []
    empty: list[str] = []
    for pat in patterns:
        p = Path(pat)
        if p.exists():
            found.append(p)
            continue
        if any(c in pat for c in _GLOB_CHARS):
            hits = sorted(glob.glob(pat, recursive=True))
            if hits:
                found.extend(Path(h) for h in hits)
            else:
                empty.append(pat)
        else:
            found.append(p)
    return found, empty


def _run_one(path: Path, source: Path | None,
             limits: ArchiveLimits) -> list[Finding]:
    if path.suffix.lower() in (".pptx", ".potx", ".ppsx"):
        if source is not None:
            return check_pptx(path, limits=limits) + [
                Finding(
                    "FID000", Severity.ERROR,
                    "comparison was NOT performed: --against source comparison "
                    f"is not implemented for {path.suffix.lower()} files; "
                    "only layout checks were run",
                )
            ]
        return check_pptx(path, limits=limits)
    findings = check(path, limits=limits)
    unreadable = any(
        f.code in ("PKG000", "PKG001", "PKG002", "PKG007", "PKG008")
        for f in findings
    )
    if source is not None and not unreadable:
        try:
            findings = findings + compare(source, path, limits=limits)
        except Exception as e:
            findings = findings + [
                Finding(
                    "FID000", Severity.ERROR,
                    f"comparison was NOT performed against {source}: {e}",
                )
            ]
    return findings


def _apply_policy(path: Path, findings: list[Finding], policy: Policy,
                  expectations: list[Expectation],
                  allowance: dict[str, int] | None,
                  ) -> tuple[list[Finding], list[tuple[Finding, str]],
                             list[tuple[Finding, str]]]:
    """Config, then expectations, then the baseline. Returns (kept, hidden
    with why, expected with why)."""
    kept, dropped = policy.apply(str(path), findings)
    matched: list[tuple[Finding, str]] = []
    if expectations:
        kept, matched = expect(kept, expectations, str(path))
    if allowance is not None:
        kept, base_dropped = apply_baseline(str(path), kept, allowance)
        dropped = dropped + base_dropped
    return kept, dropped, matched


def _fails(findings: list[Finding], threshold: Severity) -> bool:
    return any(f.severity >= threshold for f in findings)


def _json_file(path: Path | str, findings: list[Finding],
               hidden: list[tuple[Finding, str]],
               matched: list[tuple[Finding, str]], *, expectations: bool,
               coverage: CoverageReport | None) -> dict:
    """One file's entry in the `--json` report."""
    item = {
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


def _json_payload(files: list[dict], threshold: Severity, policy: Policy,
                  baseline: str | None) -> dict:
    return {
        "version": __version__,
        "fail_on": threshold.value,
        "config": policy.source or None,
        "baseline": baseline,
        "files": files,
    }


#: Coverage statuses that mean part of the file was not fully assessed. A file
#: with any of them and no findings is "no findings in checked surfaces", never
#: "clean".
GAP_STATUSES = (
    CoverageStatus.ESTIMATED,
    CoverageStatus.SKIPPED,
    CoverageStatus.UNSUPPORTED,
)


def _head(path: Path | str, findings: list[Finding]) -> str:
    counts = summarize(findings)
    return (f"{path}: "
            f"{counts['error']} error(s), {counts['warn']} warning(s), "
            f"{counts['info']} info")


def _has_gaps(coverage: CoverageReport | None) -> bool:
    return coverage is not None and any(
        item.status in GAP_STATUSES for item in coverage.items
    )


def _print_human(path: Path, findings: list[Finding], threshold: Severity,
                 quiet: bool, out,
                 coverage: CoverageReport | None = None) -> None:
    shown = [f for f in findings if f.severity >= threshold] if quiet else findings
    head = _head(path, findings)
    if not shown and not findings:
        qualified = _has_gaps(coverage)
        suffix = ("no findings in checked surfaces" if qualified else "clean")
        print(f"{head}  - {suffix}", file=out)
        return
    print(head, file=out)
    for f in shown:
        print("  " + str(f).replace("\n", "\n  "), file=out)


def _print_coverage(report: CoverageReport, *, details: bool, out) -> None:
    counts = report.summary()
    summary = ", ".join(
        f"{counts[status.value]} {status.value}"
        for status in CoverageStatus if counts[status.value]
    )
    print(f"  coverage: {summary}", file=out)
    visible = (
        report.items if details else tuple(
            item for item in report.items if item.status in GAP_STATUSES
        )
    )
    for item in visible:
        print(
            f"    [{item.status.value}] {item.id}: {item.reason}",
            file=out,
        )


def _run_doctor(*, json_output: bool) -> int:
    report = build_doctor_report()
    capabilities = report["capabilities"]
    unavailable = any(
        item["status"] == "unavailable" for item in capabilities
    )
    if json_output:
        json.dump(report, sys.stdout, indent=2, ensure_ascii=True)
        sys.stdout.write("\n")
        return EXIT_FINDINGS if unavailable else EXIT_OK

    runtime = report["runtime"]
    print(f"ooxml-integrity {report['version']} doctor: {report['status']}")
    print(
        f"  runtime: {runtime['implementation']} {runtime['python']}; "
        f"lxml {runtime['lxml']}; libxml2 {runtime['libxml2']}; "
        f"fonttools {runtime['fonttools']}"
    )
    print("  capabilities:")
    for item in capabilities:
        print(
            f"    [{item['status']}] {item['id']} "
            f"({item['confidence']}): {item['detail']}"
        )
    print("  unavailable checks in this release:")
    for item in report["unavailable_checks"]:
        print(f"    - {item['id']}: {item['reason']}")
    return EXIT_FINDINGS if unavailable else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ooxml-integrity",
        description="Structural and fidelity checks for .docx files, plus "
                    "layout-risk checks for .pptx files.",
        epilog="exit codes: 0 clean, 1 findings at or above --fail-on, 2 usage error",
    )
    p.add_argument("--version", action="version",
                   version=f"ooxml-integrity {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="inspect one or more .docx files")
    c.add_argument("files", nargs="+",
                   help="paths or globs, e.g. 'out/**/*.docx'. "
                        ".pptx files get the layout checks instead")
    c.add_argument("--against", metavar="SOURCE", type=Path, default=None,
                   help="also report what was lost relative to SOURCE")
    c.add_argument("--fail-on", default="error", metavar="SEVERITY",
                   help="minimum severity that makes the run fail: "
                        "error (default), warn, info")
    c.add_argument("--json", action="store_true",
                   help="machine-readable output on stdout")
    c.add_argument("--quiet", "-q", action="store_true",
                   help="print only findings at or above --fail-on")
    c.add_argument("--config", metavar="PATH", default=None,
                   help="config file; by default .ooxml-integrity.toml or a "
                        "[tool.ooxml-integrity] section in pyproject.toml, "
                        "searched upwards from the working directory")
    c.add_argument("--no-config", action="store_true",
                   help="ignore any config file that would otherwise be found")
    c.add_argument("--baseline", metavar="PATH", nargs="?",
                   const=DEFAULT_BASELINE, default=None,
                   help=f"fail only on findings not in this baseline "
                        f"(default file: {DEFAULT_BASELINE})")
    c.add_argument("--write-baseline", metavar="PATH", nargs="?",
                   const=DEFAULT_BASELINE, default=None,
                   help="record the current findings as accepted and exit 0")
    c.add_argument("--expect", metavar="CODE[:KEY=VALUE,...]", action="append", default=[],
                   help="a finding the edit was asked to cause, e.g. "
                        "FID001:tag=ins,before=2,after=0; it is reported as "
                        "expected, and an expectation nothing matches fails the "
                        "run (EXP001). Repeatable; text values go in the config")
    c.add_argument("--sarif", metavar="PATH", default=None,
                   help="write a SARIF 2.1.0 report for code-scanning upload")
    c.add_argument("--show-suppressed", action="store_true",
                   help="also print what config or the baseline hid, and why")
    c.add_argument("--coverage", action="store_true",
                   help="report what was checked, absent, estimated, skipped or "
                        "unsupported for each file")
    c.add_argument("--coverage-details", action="store_true",
                   help="show every coverage item, including checked and absent "
                        "surfaces (implies --coverage)")

    d = sub.add_parser("doctor", help="report parser, runtime and font capability")
    d.add_argument("--json", action="store_true",
                   help="machine-readable capability report on stdout")

    m = sub.add_parser(
        "mcp",
        help="serve check and compare as tools for AI agents (MCP over stdio)",
        description="A local Model Context Protocol server on stdin and "
                    "stdout, for an agent to check a document it edited. It "
                    "opens no socket and reads only the files a call names. "
                    "See docs/mcp.md.",
    )
    m.add_argument("--config", metavar="PATH", default=None,
                   help="config file; by default found as for check, from the "
                        "server's working directory")
    m.add_argument("--no-config", action="store_true",
                   help="ignore any config file that would otherwise be found")
    m.add_argument("--fail-on", default=None, metavar="SEVERITY",
                   help="minimum severity a verdict fails on; by default the "
                        "config's, else error")

    a = sub.add_parser(
        "anonymize",
        help="replace the text of a .docx, or of a source and its edited copy, "
             "so a defect can be shared; then check the findings are reproduced",
        description="Replace every word, author, date, property, picture and "
                    "embedded object, keep the structure, then run the checks "
                    "on the originals and the results and compare.",
    )
    a.add_argument("files", nargs="+", type=Path, metavar="DOCX",
                   help="one document, or the source followed by the edited copy")
    a.add_argument("-o", "--output-dir", type=Path, required=True, metavar="DIR",
                   help="writes document.docx, or source.docx and edited.docx")
    a.add_argument("--force", action="store_true",
                   help="overwrite those files if they already exist")
    a.add_argument("--json", action="store_true",
                   help="machine-readable report on stdout")
    return p


def _run_anonymize(args) -> int:
    from .anonymize import anonymize, output_names
    from .archive import PackageIssue

    files = args.files
    if len(files) > 2:
        print("ooxml-integrity: anonymize takes one document, or a source and "
              "its edited copy", file=sys.stderr)
        return EXIT_USAGE
    for path in files:
        if not path.is_file():
            print(f"ooxml-integrity: file not found: {path}", file=sys.stderr)
            return EXIT_USAGE
    names = output_names(len(files))
    taken = [n for n in names if (args.output_dir / n).exists()]
    if taken and not args.force:
        print(f"ooxml-integrity: {args.output_dir} already holds "
              f"{', '.join(taken)}; use --force to overwrite", file=sys.stderr)
        return EXIT_USAGE
    try:
        report = anonymize(files, args.output_dir)
    except (ValueError, PackageIssue) as e:
        print(f"ooxml-integrity: cannot anonymize: {e}", file=sys.stderr)
        return EXIT_USAGE
    if args.json:
        json.dump(report.as_dict(), sys.stdout, indent=2, ensure_ascii=True)
        sys.stdout.write("\n")
    else:
        print(report.render(args.output_dir))
    return EXIT_OK if report.reproduced and not report.leaks else EXIT_FINDINGS


def _run_mcp(args) -> int:
    from .mcp_server import serve

    # Settle what the server starts with before the client connects: a typo
    # in --fail-on or a missing config file is a usage error, not a tool
    # error on every call.
    try:
        fail_on = Severity.parse(args.fail_on) if args.fail_on else None
        if not args.no_config:
            Policy.load(args.config)
    except (ValueError, ConfigError) as e:
        print(f"ooxml-integrity: {e}", file=sys.stderr)
        return EXIT_USAGE
    return serve(config=args.config, no_config=args.no_config, fail_on=fail_on)


def main(argv: list[str] | None = None) -> int:
    # Redirected Windows streams can use a legacy encoding. Keep that encoding
    # but escape unencodable diagnostic characters instead of truncating output.
    # JSON below uses JSON escapes so decoding restores the exact original text.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)

    if args.command == "doctor":
        return _run_doctor(json_output=args.json)
    if args.command == "anonymize":
        return _run_anonymize(args)
    if args.command == "mcp":
        return _run_mcp(args)

    try:
        policy = Policy() if args.no_config else Policy.load(args.config)
    except ConfigError as e:
        print(f"ooxml-integrity: {e}", file=sys.stderr)
        return EXIT_USAGE

    # An explicit --fail-on beats the config file; the config sets the default
    # so a project does not have to repeat itself in every CI invocation.
    explicit_fail_on = any(a.startswith("--fail-on") for a in (argv or sys.argv[1:]))
    try:
        threshold = (Severity.parse(args.fail_on) if explicit_fail_on
                     else policy.fail_on)
    except ValueError as e:
        print(f"ooxml-integrity: {e}", file=sys.stderr)
        return EXIT_USAGE

    try:
        expectations = policy.expectations + [Expectation.parse(x) for x in args.expect]
    except ValueError as e:
        print(f"ooxml-integrity: --expect: {e}", file=sys.stderr)
        return EXIT_USAGE

    if args.against is not None and not args.against.exists():
        print(f"ooxml-integrity: --against file not found: {args.against}",
              file=sys.stderr)
        return EXIT_USAGE

    paths, unmatched = _expand(args.files)
    if unmatched and not paths:
        print("ooxml-integrity: no files matched: " + ", ".join(unmatched),
              file=sys.stderr)
        return EXIT_USAGE
    for pat in unmatched:
        print(f"ooxml-integrity: warning: no files matched {pat}", file=sys.stderr)
    if not paths:
        print("ooxml-integrity: nothing to check", file=sys.stderr)
        return EXIT_USAGE

    raw: dict[Path, list[Finding]] = {}
    for path in paths:
        raw[path] = _run_one(path, args.against, policy.archive)

    # --write-baseline records what the checks actually saw, before any policy:
    # a baseline built from already-filtered findings would silently bake the
    # config in, and changing the config later would then look like regressions.
    if args.write_baseline:
        doc = make_baseline({str(p): f for p, f in raw.items()})
        with open(args.write_baseline, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        total = sum(doc["findings"].values())
        print(f"wrote {args.write_baseline}: {total} finding(s) from "
              f"{len(raw)} file(s) recorded as accepted")
        crashed = sum(f.code in NOT_BASELINED for fs in raw.values() for f in fs)
        if crashed:
            print(f"ooxml-integrity: warning: {crashed} INT001 finding(s) not "
                  "recorded: a check that did not complete cannot be "
                  "baselined", file=sys.stderr)
        return EXIT_OK

    coverage_requested = args.coverage or args.coverage_details
    coverage: dict[Path, CoverageReport] = {}
    if coverage_requested:
        for path, findings in raw.items():
            coverage[path] = coverage_for(
                path, findings, source=args.against, limits=policy.archive,
            )

    allowance: dict[str, int] | None = None
    if args.baseline:
        try:
            allowance = read_baseline(args.baseline)
        except ConfigError as e:
            print(f"ooxml-integrity: {e}", file=sys.stderr)
            return EXIT_USAGE

    results: dict[Path, list[Finding]] = {}
    hidden: dict[Path, list[tuple[Finding, str]]] = {}
    matched: dict[Path, list[tuple[Finding, str]]] = {}
    for path, findings in raw.items():
        results[path], hidden[path], matched[path] = _apply_policy(
            path, findings, policy, expectations, allowance,
        )

    if args.sarif:
        doc = build_sarif({str(p): f for p, f in results.items()},
                          {str(p): d + matched.get(p, []) for p, d in hidden.items()})
        with open(args.sarif, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.write("\n")

    if args.json:
        files = [
            _json_file(
                p, f, hidden.get(p, []), matched.get(p, []),
                expectations=bool(expectations),
                coverage=coverage[p] if coverage_requested else None,
            )
            for p, f in results.items()
        ]
        payload = _json_payload(files, threshold, policy, args.baseline)
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=True)
        sys.stdout.write("\n")
    else:
        for i, (p, f) in enumerate(results.items()):
            if i:
                print()
            _print_human(
                p, f, threshold, args.quiet, sys.stdout,
                coverage[p] if coverage_requested else None,
            )
            if coverage_requested:
                _print_coverage(
                    coverage[p], details=args.coverage_details, out=sys.stdout,
                )
            for x, why in matched.get(p, []):
                print(f"  [expected] {why}")
            if args.show_suppressed and hidden.get(p):
                for x, why in hidden[p]:
                    print(f"  [hidden] {x.code}  {why}")
        n = sum(len(v) for v in hidden.values())
        if n and not args.show_suppressed:
            print(f"\n{n} finding(s) suppressed by "
                  + " and ".join(
                      x for x in (
                          f"config ({policy.source})" if policy.source else "",
                          f"baseline ({args.baseline})" if args.baseline else "",
                      ) if x)
                  + ". Re-run with --show-suppressed to see them.")

    failed = any(
        _fails(findings, threshold) for findings in results.values()
    )
    return EXIT_FINDINGS if failed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
