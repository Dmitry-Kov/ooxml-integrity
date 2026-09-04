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
from .fidelity import compare
from .finding import Finding, Severity, summarize, worst
from .inspector import check
from .policy import (
    ConfigError, DEFAULT_BASELINE, Policy, apply_baseline, make_baseline,
    read_baseline,
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


def _run_one(path: Path, source: Path | None) -> list[Finding]:
    if path.suffix.lower() in (".pptx", ".potx", ".ppsx"):
        if source is not None:
            return check_pptx(path) + [
                Finding(
                    "FID000", Severity.ERROR,
                    "comparison was NOT performed: --against source comparison "
                    f"is not implemented for {path.suffix.lower()} files; "
                    "only layout checks were run",
                )
            ]
        return check_pptx(path)
    findings = check(path)
    unreadable = any(f.code in ("PKG000", "PKG002") for f in findings)
    if source is not None and not unreadable:
        try:
            findings = findings + compare(source, path)
        except Exception as e:
            findings = findings + [
                Finding(
                    "FID000", Severity.ERROR,
                    f"comparison was NOT performed against {source}: {e}",
                )
            ]
    return findings


def _print_human(path: Path, findings: list[Finding], threshold: Severity,
                 quiet: bool, out) -> None:
    shown = [f for f in findings if f.severity >= threshold] if quiet else findings
    counts = summarize(findings)
    head = (f"{path}: "
            f"{counts['error']} error(s), {counts['warn']} warning(s), "
            f"{counts['info']} info")
    if not shown and not findings:
        print(f"{head}  - clean", file=out)
        return
    print(head, file=out)
    for f in shown:
        print("  " + str(f).replace("\n", "\n  "), file=out)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ooxml-integrity",
        description="Structural integrity checks for .docx files. "
                    "Answers 'will Word open this, and did the edit lose "
                    "anything', which schema validation and rendering do not.",
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
    c.add_argument("--sarif", metavar="PATH", default=None,
                   help="write a SARIF 2.1.0 report for code-scanning upload")
    c.add_argument("--show-suppressed", action="store_true",
                   help="also print what config or the baseline hid, and why")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

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
        raw[path] = _run_one(path, args.against)

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
        return EXIT_OK

    allowance: dict[str, int] | None = None
    if args.baseline:
        try:
            allowance = read_baseline(args.baseline)
        except ConfigError as e:
            print(f"ooxml-integrity: {e}", file=sys.stderr)
            return EXIT_USAGE

    results: dict[Path, list[Finding]] = {}
    hidden: dict[Path, list[tuple[Finding, str]]] = {}
    for path, findings in raw.items():
        kept, dropped = policy.apply(str(path), findings)
        if allowance is not None:
            kept, base_dropped = apply_baseline(str(path), kept, allowance)
            dropped = dropped + base_dropped
        results[path] = kept
        hidden[path] = dropped

    if args.sarif:
        doc = build_sarif({str(p): f for p, f in results.items()},
                          {str(p): d for p, d in hidden.items()})
        with open(args.sarif, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.write("\n")

    if args.json:
        payload = {
            "version": __version__,
            "fail_on": threshold.value,
            "config": policy.source or None,
            "baseline": args.baseline,
            "files": [
                {
                    "path": str(p),
                    "summary": summarize(f),
                    "worst": (w.value if (w := worst(f)) else None),
                    "findings": [x.as_dict() for x in f],
                    "suppressed": [
                        {**x.as_dict(), "suppressed_because": why}
                        for x, why in hidden.get(p, [])
                    ],
                }
                for p, f in results.items()
            ],
        }
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        for i, (p, f) in enumerate(results.items()):
            if i:
                print()
            _print_human(p, f, threshold, args.quiet, sys.stdout)
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
        f.severity >= threshold for findings in results.values() for f in findings
    )
    return EXIT_FINDINGS if failed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
