#!/usr/bin/env python3
"""Explicitly capture adeu 3.0.4 outputs; never used by routine corpus tests."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from adeu.models import AcceptChange, ModifyText, RejectChange
from adeu.redline.engine import RedlineEngine

from revision_evidence import BASE, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if importlib.metadata.version("adeu") != "3.0.4":
        raise ValueError("Capture requires published adeu 3.0.4")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    labels_blob = (BASE / "labels.json").read_bytes()
    cases = [case for case in json.loads(labels_blob) if case["cohort"] == "external_editor" or case.get("producer") == "adeu"]
    for case in cases:
        if (args.output_dir / f"{case['id']}.docx").exists():
            raise ValueError("Use an empty output directory; previous captures are immutable")
    records = []
    for case in cases:
        source = BASE / "sources" / f"{case['source']}.docx"
        engine = RedlineEngine(BytesIO(source.read_bytes()), author="Evidence Editor")
        action = case["action"]
        change = {"edit": lambda: ModifyText(target_text="EDITBEFORE", new_text="EDITAFTER"),
                  "accept": lambda: AcceptChange(target_id="Chg:101"),
                  "reject": lambda: RejectChange(target_id="Chg:102")}
        stats = None if action == "save" else engine.process_batch([change[action]()])
        applied = None if stats is None else stats.get("edits_applied", 0) + stats.get("actions_applied", 0)
        if stats is not None and (stats.get("failed") or applied != 1):
            raise ValueError(f"Failed action {case['id']}: {stats}")
        output = engine.save_to_stream().getvalue()
        (args.output_dir / f"{case['id']}.docx").write_bytes(output)
        records.append(dict(id=case["id"], action=action, source_sha256=digest(source.read_bytes()),
                            raw_output_sha256=digest(output), applied=applied))
    receipt = dict(producer="adeu", version="3.0.4", captured_at=datetime.now(timezone.utc).isoformat(),
                   platform=platform.system(), python=platform.python_version(), labels_sha256=digest(labels_blob),
                   dependencies={name: importlib.metadata.version(name) for name in ("adeu", "lxml", "python-docx", "pydantic", "diff-match-patch")},
                   author="Evidence Editor", sanitizer="none; fixture-only metadata inspected before publication", cases=records)
    (args.output_dir / "capture.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
