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
from .pptx_checks import check_pptx

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
                Finding("FID000", Severity.INFO,
                        "--against is not implemented for .pptx yet; only layout "
                        "checks were run")
            ]
        return check_pptx(path)
    findings = check(path)
    unreadable = any(f.code in ("PKG000", "PKG002") for f in findings)
    if source is not None and not unreadable:
        try:
            findings = findings + compare(source, path)
        except Exception as e:
            findings = findings + [
                Finding("FID000", Severity.WARN,
                        f"could not compare against {source}: {e}")
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
        prog="docx-integrity",
        description="Structural integrity checks for .docx files. "
                    "Answers 'will Word open this, and did the edit lose "
                    "anything', which schema validation and rendering do not.",
        epilog="exit codes: 0 clean, 1 findings at or above --fail-on, 2 usage error",
    )
    p.add_argument("--version", action="version",
                   version=f"docx-integrity {__version__}")
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
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        threshold = Severity.parse(args.fail_on)
    except ValueError as e:
        print(f"docx-integrity: {e}", file=sys.stderr)
        return EXIT_USAGE

    if args.against is not None and not args.against.exists():
        print(f"docx-integrity: --against file not found: {args.against}",
              file=sys.stderr)
        return EXIT_USAGE

    paths, unmatched = _expand(args.files)
    if unmatched and not paths:
        print("docx-integrity: no files matched: " + ", ".join(unmatched),
              file=sys.stderr)
        return EXIT_USAGE
    for pat in unmatched:
        print(f"docx-integrity: warning: no files matched {pat}", file=sys.stderr)
    if not paths:
        print("docx-integrity: nothing to check", file=sys.stderr)
        return EXIT_USAGE

    results: dict[Path, list[Finding]] = {}
    for path in paths:
        results[path] = _run_one(path, args.against)

    if args.json:
        payload = {
            "version": __version__,
            "fail_on": threshold.value,
            "files": [
                {
                    "path": str(p),
                    "summary": summarize(f),
                    "worst": (w.value if (w := worst(f)) else None),
                    "findings": [x.as_dict() for x in f],
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

    failed = any(
        f.severity >= threshold for findings in results.values() for f in findings
    )
    return EXIT_FINDINGS if failed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
