"""Publish the Action's JSON report without overwriting a checked document."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from ooxml_integrity.paths import same_file


def publish(report: Path, destination: Path, against: str) -> None:
    # The checker records every input it selected, including matches from globs.
    with report.open("rb") as stream:
        inputs = [Path(entry["path"]) for entry in json.load(stream)["files"]]
    if against:
        inputs.append(Path(against))
    for source in inputs:
        if same_file(source, destination):
            raise ValueError(f"{destination} points to input document {source}. "
                             "Choose a separate report file.")
    shutil.copyfile(report, destination)


if __name__ == "__main__":
    try:
        publish(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.exit(f"ooxml-integrity: json-report: {exc}")
