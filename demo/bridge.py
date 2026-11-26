"""Browser adapter, not a fork of the package. Kept importable for CLI parity tests."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path

from ooxml_integrity import verify
from ooxml_integrity.cli import main


def run_check(path, source=None, include_coverage=True):
    path = Path(path)
    source = Path(source) if source else None
    if path.suffix.lower() not in (".docx", ".pptx"):
        raise ValueError("Unsupported file: choose a .docx or .pptx file.")
    if source and (source.suffix.lower() != ".docx" or path.suffix.lower() != ".docx"):
        raise ValueError("Fidelity comparison requires two .docx files. Remove the source for PPTX checks.")

    # Default CLI archive limits, no configuration or baseline suppressions.
    # Hide virtual-FS directories in the report, not in the paths used to check.
    report = verify(
        path,
        against=source,
        coverage=include_coverage,
        label=path.name,
    )
    return {
        "human": report.to_text(),
        "json": report.to_cli_report(),
        "exit_code": report.exit_code,
    }


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
