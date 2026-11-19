"""Publish the Action's reports after checking their destinations."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from ooxml_integrity.paths import check_report_destination, same_file


def publish(report: Path, sarif: Path) -> None:
    with report.open("rb") as stream:
        data = json.load(stream)
    inputs = [Path(entry["path"]) for entry in data["files"]]
    against = os.environ["OOXML_AGAINST"]
    if against:
        inputs.append(Path(against))
    # In discovery mode the checker records the config it actually selected.
    config = os.environ["OOXML_CONFIG"]
    if config == "none":
        config = ""
    elif not config:
        config = data["config"] or ""
    inputs.extend(Path(name) for name in (os.environ["OOXML_BASELINE"], config) if name)

    copies: list[tuple[Path, Path]] = []
    for option, source, name in (("--sarif", sarif, os.environ["OOXML_SARIF"]),
                                 ("json-report", report, os.environ["OOXML_JSON_REPORT"])):
        if not name:
            continue
        destination = Path(name)
        try:
            check_report_destination(destination, inputs)
        except ValueError as exc:
            raise ValueError(f"{option}: {exc}") from exc
        if destination.is_dir():
            raise ValueError(f"{option}: {destination} is a directory")
        if any(same_file(destination, other) for _, other in copies):
            raise ValueError("json-report and --sarif must use separate paths")
        copies.append((source, destination))
    for source, destination in copies:
        shutil.copyfile(source, destination)


if __name__ == "__main__":
    try:
        publish(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.exit(f"ooxml-integrity: {exc}")
