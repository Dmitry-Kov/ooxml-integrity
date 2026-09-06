"""Browser adapter, not a fork of the package. Kept importable for CLI parity tests."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path

from ooxml_integrity import (
    __version__, check, check_pptx, compare, coverage_for,
    ArchiveLimits, Finding, Severity, summarize, worst,
)
from ooxml_integrity.cli import _print_coverage, _print_human, main


def run_check(path, source=None, include_coverage=True):
    path = Path(path)
    source = Path(source) if source else None
    if path.suffix.lower() not in (".docx", ".pptx"):
        raise ValueError("Unsupported file: choose a .docx or .pptx file.")
    if source and (source.suffix.lower() != ".docx" or path.suffix.lower() != ".docx"):
        raise ValueError("Fidelity comparison requires two .docx files. Remove the source for PPTX checks.")

    # Default CLI archive limits, no configuration or baseline suppressions.
    limits = ArchiveLimits()
    findings = check_pptx(path, limits=limits) if path.suffix.lower() == ".pptx" else check(path, limits=limits)
    unreadable = any(f.code in {"PKG000", "PKG001", "PKG002", "PKG007", "PKG008"} for f in findings)
    if source and not unreadable:
        try:
            findings += compare(source, path, limits=limits)
        except Exception as exc:
            # Same explicit comparison-failure finding as the CLI.
            findings.append(Finding("FID000", Severity.ERROR,
                                    f"comparison was NOT performed against {source}: {exc}"))
    coverage = coverage_for(path, findings, source=source, limits=limits) if include_coverage else None
    out = StringIO()
    # Hide virtual-FS directories in the report, not in the paths used to check.
    display_path = Path(path.name)
    _print_human(display_path, findings, Severity.ERROR, False, out, coverage)
    if coverage is not None:
        _print_coverage(coverage, details=False, out=out)

    # cli.main serializes this inline; there is no separate JSON formatter.
    item = {
        "path": str(display_path), "summary": summarize(findings),
        "worst": worst(findings).value if findings else None,
        "findings": [finding.as_dict() for finding in findings], "suppressed": [],
    }
    if coverage is not None:
        item["coverage"] = coverage.as_dict()
    payload = {"version": __version__, "fail_on": "error", "config": None,
               "baseline": None, "files": [item]}
    return {"human": out.getvalue(), "json": payload,
            "exit_code": int(any(f.severity >= Severity.ERROR for f in findings))}


def run_doctor():
    human, machine = StringIO(), StringIO()
    with redirect_stdout(human):
        code = main(["doctor"])
    with redirect_stdout(machine):
        main(["doctor", "--json"])
    return {"human": human.getvalue(), "json": json.loads(machine.getvalue()), "exit_code": code}


def dispatch(request_json):
    request = json.loads(request_json)
    if request["action"] == "doctor":
        result = run_doctor()
    elif request["action"] == "check":
        result = run_check(request["path"], request.get("source"), request["coverage"])
    else:
        raise ValueError("Unknown action")
    return json.dumps(result, ensure_ascii=False)
