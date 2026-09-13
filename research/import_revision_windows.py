#!/usr/bin/env python3
"""Import the reviewed E1 Windows save batch, without running Word or the checker."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from lxml import etree as E

try:
    from . import revision_evidence as evidence
except ImportError:
    import revision_evidence as evidence

BASE = evidence.BASE
ENVIRONMENT_FIELDS = (
    "word_version", "word_build", "word_file_version", "word_architecture",
    "windows_caption", "windows_version", "windows_build", "windows_architecture",
    "powershell_version",
)
CP = "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}"


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sanitise(parts):
    """Only redact lastModifiedBy; reject other unreviewed identities/parts."""
    parts = dict(parts)
    core = E.fromstring(parts["docProps/core.xml"])
    modifier = core.find(CP + "lastModifiedBy")
    if modifier is None:
        raise ValueError("Missing lastModifiedBy")
    modifier.text = "Evidence Editor"
    parts["docProps/core.xml"] = evidence.xml(core)
    for part, blob in parts.items():
        if not part.endswith((".xml", ".rels")):
            raise ValueError(f"Unreviewed binary part: {part}")
        if re.search(r"(?:(?<![A-Za-z])[A-Za-z]:[\\/]|file:/|\\\\[^\\]|/Users/|/home/|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})", blob.decode("utf-8")):
            raise ValueError(f"Unreviewed local path or email: {part}")
        for node in E.fromstring(blob).iter():
            name = E.QName(node).localname
            if node.get(evidence.W + "author") not in (None, "Reviewer A", "Reviewer B", "Reviewer C"):
                raise ValueError(f"Unreviewed revision/comment author: {part}")
            if name in ("creator", "lastModifiedBy") and node.text not in ("Revision fixture builder", "Evidence Editor"):
                raise ValueError(f"Unreviewed core identity: {part}")
            if name in ("Company", "Manager", "HyperlinkBase") and node.text:
                raise ValueError(f"Unreviewed extended identity: {part}")
            if name in ("docVars", "attachedTemplate", "person") or node.get("userId") or node.get("providerId"):
                raise ValueError(f"Unreviewed user metadata: {part}")
            if node.get("TargetMode") == "External" and node.get("Target") != "https://example.org/spec":
                raise ValueError(f"Unreviewed external relationship: {part}")
    return parts


def validate_capture(staging, base=BASE):
    """Check the entire batch before any published file is written."""
    for received, committed in (("batch.json", "batch-windows.json"), ("expectations.json", "expectations-windows.json")):
        if (staging / received).read_bytes() != (base / committed).read_bytes():
            raise ValueError("Predeclared batch or expectations changed")
    batch = load(base / "batch-windows.json")
    if evidence.digest((staging / "save_docx_word_windows.ps1").read_bytes()) != batch["capture_script_sha256"]:
        raise ValueError("Capture script hash mismatch")
    if evidence.digest((base / "expectations-windows.json").read_bytes()) != batch["expectations_sha256"]:
        raise ValueError("Expectation hash mismatch")
    run = load(staging / "word-run.json")
    if run["schema_version"] != 1 or run["completed"] is not True or run["operation"] != "Word.Application COM Documents.Open then Document.SaveAs2":
        raise ValueError("Incomplete or unexpected capture operation")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", run.get("captured_at_utc", "")):
        raise ValueError("Missing capture timestamp")
    if any(not isinstance(run["environment"].get(key), str) or not run["environment"][key] for key in ENVIRONMENT_FIELDS):
        raise ValueError("Incomplete producer environment")
    entries = {entry["id"]: entry for entry in run["documents"]}
    expected_ids = {item["id"] for item in batch["documents"]}
    if len(entries) != len(run["documents"]) or set(entries) != expected_ids:
        raise ValueError("Capture case inventory mismatch")
    labels = {case["id"]: case for case in load(base / "labels-windows.json")}
    expectations = {case["id"]: case for case in load(base / "expectations-windows.json")["cases"]}
    if set(labels) != expected_ids or set(expectations) != expected_ids:
        raise ValueError("Label inventory mismatch")
    prepared = []
    for item in batch["documents"]:
        entry, case, expectation = entries[item["id"]], labels[item["id"]], expectations[item["id"]]
        if any(entry[key] != item[key] for key in ("input", "output", "input_sha256")):
            raise ValueError("Capture paths/input hash mismatch")
        if entry["saved"] is not True or entry["open_and_repair"] is not False or entry["save_format"] != 12:
            raise ValueError("Expected completed no-repair DOCX save")
        for key in ("source", "action", "cohort", "allowed_revision_losses", "allowed_text_changes"):
            if case[key] != expectation[key]:
                raise ValueError("Label no longer matches predeclared intent")
        if case["expected_findings"] != expectation["expected_findings_if_preserved"]:
            raise ValueError("Expected findings changed after capture")
        source = base / "sources" / f"{case['source']}.docx"
        if (staging / item["input"]).read_bytes() != source.read_bytes() or evidence.digest(source.read_bytes()) != item["input_sha256"] or item["input_sha256"] != expectation["source_sha256"]:
            raise ValueError("Source hash mismatch")
        raw = staging / item["output"]
        if evidence.digest(raw.read_bytes()) != entry["raw_output_sha256"]:
            raise ValueError("Raw output hash mismatch")
        original = evidence.read(raw)
        parts = sanitise(original)
        audit = evidence.oracle(evidence.read(source), parts, case)
        if not audit["intent_correct"] or case["intent_correct"] is not True:
            raise ValueError(f"Review preservation failure independently: {case['id']}: {audit}")
        strict_case = {key: value for key, value in case.items() if key != "comparison_profile"}
        widths = lambda package: E.fromstring(package[evidence.MAIN]).xpath(".//w:tblGrid/w:gridCol/@w:w", namespaces=evidence.NS)
        record = {key: entry[key] for key in ("id", "input_sha256", "raw_output_sha256", "saved", "open_and_repair", "save_format", "input_object_counts")}
        record.update(source_sha256=item["input_sha256"],
                      raw_part_sha256={p: evidence.digest(b) for p, b in sorted(original.items())},
                      published_part_sha256={p: evidence.digest(b) for p, b in sorted(parts.items())},
                      changed_parts=[p for p in parts if original[p] != parts[p]],
                      original_comparison=evidence.oracle(evidence.read(source), parts, strict_case),
                      comparison_profile=case["comparison_profile"],
                      table_grid_widths_twips={"source": widths(evidence.read(source)), "output": widths(parts)})
        prepared.append((case, parts, record))
    return run, prepared


def import_capture(staging, base=BASE):
    run, prepared = validate_capture(staging, base)
    receipt_path = base / "capture-windows.json"
    outputs = [base / "outputs" / f"{case['id']}.docx" for case, _, _ in prepared]
    if any(path.exists() for path in [receipt_path, *outputs]):
        raise ValueError("Previous published capture exists; use a new tranche")
    records = []
    for output, (_, parts, record) in zip(outputs, prepared):
        evidence.write(parts, output)
        record["published_sha256"] = evidence.digest(output.read_bytes())
        records.append(record)
    receipt = dict(schema_version=1, producer="Microsoft Word for Windows",
                   captured_at_utc=run["captured_at_utc"],
                   environment={key: run["environment"][key] for key in ENVIRONMENT_FIELDS},
                   operation=run["operation"],
                   batch_sha256=evidence.digest((base / "batch-windows.json").read_bytes()),
                   expectations_sha256=evidence.digest((base / "expectations-windows.json").read_bytes()),
                   labels_sha256=evidence.digest((base / "labels-windows.json").read_bytes()),
                   raw_run_sha256=evidence.digest((staging / "word-run.json").read_bytes()),
                   sanitizer="Only core.xml lastModifiedBy replaced with Evidence Editor; ZIP repacked. All other part bytes retained.",
                   review="Owner-supplied COM capture; independent XML comparison and local LibreOffice page review by the coding agent. No independent human or Windows screenshot review claimed.",
                   cases=records)
    receipt_path.write_bytes((json.dumps(receipt, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", required=True, type=Path)
    args = parser.parse_args()
    receipt = import_capture(args.staging)
    print(f"Imported {len(receipt['cases'])} observed Windows saves; checker has not run.")


if __name__ == "__main__":
    main()
