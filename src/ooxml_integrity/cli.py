"""Command line interface.

Exit codes are the contract with CI:

    0   nothing at or above the --fail-on threshold
    1   findings at or above the threshold
    2   usage error, or a file that could not be read at all

`fix` keeps 0 and 2 and adds 3, so that 0 always means a verified copy was
written (docs/fix.md):

    0   repaired and re-checked; OUT written
    1   nothing written: no finding fix repairs, or every one refused
    2   usage error, or a package fix does not rewrite (unreadable, Strict,
        malformed); nothing written
    3   a repair could not be proved by the re-check; nothing written
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import Counter
from pathlib import Path

from . import __version__
from .coverage import CoverageReport, coverage_for
from .doctor import build_report as build_doctor_report
from .expect import Expectation
from .finding import Finding, Severity
from .introduced import REASON as INHERITED, source_findings
from .package import LoadedPackage
from .paths import check_report_destination, same_file
from .policy import (
    BASELINE_EXCLUSION_REASONS, ConfigError, DEFAULT_BASELINE, Policy,
    make_baseline, read_baseline,
)
from .runner import (
    EXIT_FINDINGS,
    EXIT_OK,
    EXIT_USAGE,
    GAP_STATUSES as GAP_STATUSES,
    apply_policy,
    fails,
    format_coverage,
    format_head,
    format_human,
    has_gaps,
    json_file,
    json_payload,
    run_checks,
    try_open,
)
from .sarif import build as build_sarif

# Backwards-compatible internal alias for tests importing cli._run_one.
_run_one = run_checks
_head = format_head
_has_gaps = has_gaps


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


def _print_human(path: Path, findings: list[Finding], threshold: Severity,
                 quiet: bool, out,
                 coverage: CoverageReport | None = None) -> None:
    out.write(format_human(path, findings, threshold, quiet=quiet, coverage=coverage))


def _print_coverage(report: CoverageReport, *, details: bool, out) -> None:
    out.write(format_coverage(report, details=details))


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
    c.add_argument("--introduced", action="store_true",
                   help="with --against: fail only on what the edit introduced; "
                        "a finding SOURCE already has is suppressed, not "
                        "failing (see --show-suppressed)")
    c.add_argument("--fail-on", default="error", metavar="SEVERITY",
                   help="minimum severity that makes the run fail: "
                        "error (default), warn, info")
    c.add_argument("--json", action="store_true",
                   help="machine-readable output on stdout")
    c.add_argument("--json-out", metavar="PATH", default=None,
                   help="write the machine-readable JSON report to PATH "
                        "without replacing stdout output")
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
                   help="record the current findings as accepted and exit 0. "
                        "Put this option last to use the default baseline file")
    c.add_argument("--expect", metavar="CODE[:KEY=VALUE,...]", action="append", default=[],
                   help="a finding the edit was asked to cause, e.g. "
                        "FID001:tag=ins,before=2,after=0; it is reported as "
                        "expected, and an expectation nothing matches fails the "
                        "run (EXP001). Repeatable; text values go in the config")
    c.add_argument("--sarif", metavar="PATH", default=None,
                   help="write a SARIF 2.1.0 report for code-scanning upload")
    c.add_argument("--show-suppressed", action="store_true",
                   help="also print what config, the baseline or --introduced "
                        "hid, and why")
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
                    "on the originals and the results and compare, and check "
                    "that every data binding still selects its data. An output "
                    "that is, or links to, an input is refused.",
    )
    a.add_argument("files", nargs="+", type=Path, metavar="DOCX",
                   help="one document, or the source followed by the edited copy")
    a.add_argument("-o", "--output-dir", type=Path, required=True, metavar="DIR",
                   help="writes document.docx, or source.docx and edited.docx")
    a.add_argument("--force", action="store_true",
                   help="overwrite those files if they already exist (never an input)")
    a.add_argument("--json", action="store_true",
                   help="machine-readable report on stdout")

    f = sub.add_parser(
        "fix",
        help="write a repaired copy of a .docx: anchor orphaned replies "
             "(CMT005), renumber repeated revision ids (REV001), correct a "
             "related part's content type (PKG010)",
        description="Write a repaired copy of a .docx, never in place. Three "
                    "repairs, each only when its result is unique: "
                    "anchor-replies gives an orphaned reply its parent "
                    "comment's range, as Word writes a thread; "
                    "renumber-revisions gives every repeated revision id after "
                    "the first a fresh id; content-type gives a related part's "
                    "Override the content type its relationship type requires. "
                    "Lost content is never restored or invented. The copy is "
                    "checked again before it is written. See docs/fix.md.",
        epilog="exit codes: 0 repaired and re-checked, OUT written; 1 nothing "
               "to repair or every repair refused; 2 usage error or a package "
               "fix does not rewrite; 3 the re-check failed. Nothing is "
               "written unless the exit code is 0",
    )
    f.add_argument("file", type=Path, metavar="IN", help="the .docx to repair")
    f.add_argument("-o", "--output", type=Path, required=True, metavar="OUT",
                   help="where to write the repaired copy; must not be IN")
    f.add_argument("--against", metavar="SOURCE", type=Path, default=None,
                   help="also prove the copy loses nothing relative to SOURCE "
                        "that IN did not")
    f.add_argument("--force", action="store_true",
                   help="replace OUT if it already exists (never IN)")
    f.add_argument("--json", action="store_true",
                   help="machine-readable report on stdout")
    return p


def _run_fix(args) -> int:
    from .fix import FixUsageError, fix

    try:
        report = fix(args.file, args.output, against=args.against,
                     force=args.force)
    except FixUsageError as e:
        print(f"ooxml-integrity: {e}", file=sys.stderr)
        return EXIT_USAGE
    if args.json:
        json.dump(report.as_dict(), sys.stdout, indent=2, ensure_ascii=True)
        sys.stdout.write("\n")
    else:
        print(report.render())
    return report.exit_code


def _run_anonymize(args) -> int:
    from .anonymize import Refused, anonymize, check_outputs, output_names
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
    try:
        # before --force is considered: an input is never overwritten
        check_outputs(files, args.output_dir, names)
    except Refused as e:
        print(f"ooxml-integrity: {e}", file=sys.stderr)
        return EXIT_USAGE
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
    return EXIT_OK if report.passed else EXIT_FINDINGS


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


def _write_json(doc, path: str, option: str, inputs: list[Path]) -> bool:
    """Write a report file; a path that cannot be written is a usage error.

    Exit 1 means findings, so a crash there would read as a failing document.
    """
    try:
        check_report_destination(Path(path), inputs)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    except ValueError as e:
        print(f"ooxml-integrity: {option}: {e}", file=sys.stderr)
        return False
    except OSError as e:
        print(f"ooxml-integrity: {option}: cannot write {path}: {e.strerror or e}",
              file=sys.stderr)
        return False
    return True


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
    if args.command == "fix":
        return _run_fix(args)

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

    if args.introduced and args.against is None:
        print("ooxml-integrity: --introduced needs --against SOURCE: without "
              "the source, no finding can be told apart as already there",
              file=sys.stderr)
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

    protected = list(paths)
    if args.against is not None:
        protected.append(args.against)
    if policy.source:
        protected.append(Path(policy.source))
    if args.baseline:
        baseline = Path(args.baseline)
        refresh = Path(args.write_baseline) if args.write_baseline else None
        # Refreshing the named baseline is intentional. A different output
        # name might be a symbolic or hard link back to that input.
        if (refresh is None or refresh.name != baseline.name
                or not same_file(refresh.parent, baseline.parent)):
            protected.append(baseline)
    source_pkg = (
        try_open(args.against, policy.archive)
        if args.against is not None else None
    )
    coverage_requested = (args.coverage or args.coverage_details) and not args.write_baseline
    cov_source = source_pkg if source_pkg is not None else args.against
    raw: dict[Path, list[Finding]] = {}
    coverage: dict[Path, CoverageReport] = {}
    for path in paths:
        pkg = try_open(path, policy.archive)
        target: Path | LoadedPackage = pkg if pkg is not None else path
        findings = _run_one(target, cov_source, policy.archive)
        raw[path] = findings
        if coverage_requested:
            coverage[path] = coverage_for(
                target,
                findings,
                source=cov_source,
                limits=policy.archive,
            )

    # --write-baseline records what the checks actually saw, before any policy:
    # a baseline built from already-filtered findings would silently bake the
    # config in, and changing the config later would then look like regressions.
    if args.write_baseline:
        doc = make_baseline({str(p): f for p, f in raw.items()})
        if not _write_json(doc, args.write_baseline, "--write-baseline", protected):
            return EXIT_USAGE
        total = sum(doc["findings"].values())
        print(f"wrote {args.write_baseline}: {total} finding(s) from "
              f"{len(raw)} file(s) recorded as accepted")
        omitted = Counter(f.code for findings in raw.values() for f in findings
                          if f.code in BASELINE_EXCLUSION_REASONS)
        for code, count in sorted(omitted.items()):
            print(f"ooxml-integrity: warning: {count} {code} finding(s) not "
                  f"recorded: {BASELINE_EXCLUSION_REASONS[code]}", file=sys.stderr)
        return EXIT_OK

    allowance: dict[str, int] | None = None
    if args.baseline:
        try:
            allowance = read_baseline(args.baseline)
        except ConfigError as e:
            print(f"ooxml-integrity: {e}", file=sys.stderr)
            return EXIT_USAGE

    # One source for every file, so its own findings are computed once.
    inherited_from = (
        source_findings(
            source_pkg if source_pkg is not None else args.against,
            limits=policy.archive,
        )
        if args.introduced else None
    )

    results: dict[Path, list[Finding]] = {}
    hidden: dict[Path, list[tuple[Finding, str]]] = {}
    matched: dict[Path, list[tuple[Finding, str]]] = {}
    for path, findings in raw.items():
        results[path], hidden[path], matched[path] = apply_policy(
            path, findings, policy, expectations, allowance, inherited_from,
        )

    # Validate all requested file outputs before writing any of them.
    report_targets: list[tuple[str, Path]] = []
    for option, dest_str in (("--sarif", args.sarif), ("--json-out", args.json_out)):
        if not dest_str:
            continue
        dest = Path(dest_str)
        try:
            check_report_destination(dest, protected)
        except ValueError as e:
            print(f"ooxml-integrity: {option}: {e}", file=sys.stderr)
            return EXIT_USAGE
        if dest.is_dir():
            print(f"ooxml-integrity: {option}: {dest} is a directory", file=sys.stderr)
            return EXIT_USAGE
        if any(same_file(dest, other) for _, other in report_targets):
            print("ooxml-integrity: --json-out and --sarif must use separate paths",
                  file=sys.stderr)
            return EXIT_USAGE
        report_targets.append((option, dest))

    if args.sarif:
        doc = build_sarif({str(p): f for p, f in results.items()},
                          {str(p): d + matched.get(p, []) for p, d in hidden.items()})
        if not _write_json(doc, args.sarif, "--sarif", protected):
            return EXIT_USAGE

    payload: dict | None = None
    if args.json or args.json_out:
        files = [
            json_file(
                p, f, hidden.get(p, []), matched.get(p, []),
                expectations=bool(expectations),
                coverage=coverage[p] if coverage_requested else None,
            )
            for p, f in results.items()
        ]
        payload = json_payload(files, threshold, policy, args.baseline,
                               introduced=args.introduced)

    if args.json_out and payload is not None:
        if not _write_json(payload, args.json_out, "--json-out", protected):
            return EXIT_USAGE

    if args.json and payload is not None:
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
        inherited_n = sum(why == INHERITED for v in hidden.values() for _, why in v)
        if n and not args.show_suppressed:
            said = []
            if n - inherited_n:
                said.append(
                    f"{n - inherited_n} finding(s) suppressed by "
                    + " and ".join(
                        x for x in (
                            f"config ({policy.source})" if policy.source else "",
                            f"baseline ({args.baseline})" if args.baseline else "",
                        ) if x)
                    + ".")
            if inherited_n:
                said.append(f"{inherited_n} finding(s) already in the source "
                            f"{args.against}, set aside by --introduced.")
            print("\n" + "\n".join(said)
                  + " Re-run with --show-suppressed to see them.")

    failed = any(
        fails(findings, threshold) for findings in results.values()
    )
    return EXIT_FINDINGS if failed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
