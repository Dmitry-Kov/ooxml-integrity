#!/usr/bin/env python3
"""Import observed Word Online edits after a narrow metadata privacy scrub."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from lxml import etree as E

from revision_evidence import BASE, W, digest, oracle, read, write, xml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True, type=Path)
    args = parser.parse_args()
    labels_blob = (BASE / "labels-online.json").read_bytes()
    observations = json.loads((args.raw_dir / "observations.json").read_text(encoding="utf-8"))
    records = []
    for case in json.loads(labels_blob):
        observation = next(o for o in observations if o["id"] == case["id"])
        if observation["replace_count"] != 1 or observation["saved"] is not True or observation["downloaded"] is not True:
            raise ValueError("An observed completed editor action and download are required")
        raw = args.raw_dir / f"{case['id']}.docx"
        if digest(raw.read_bytes()) != observation["raw_sha256"]:
            raise ValueError("Raw capture hash mismatch")
        parts = read(raw)
        before_hashes = {part: digest(blob) for part, blob in parts.items()}
        core = E.fromstring(parts["docProps/core.xml"])
        modifier = core.find("{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}lastModifiedBy")
        if modifier is None:
            raise ValueError("Unexpected Office metadata structure")
        modifier.text = "Evidence Editor"
        parts["docProps/core.xml"] = xml(core)
        allowed_authors = {"Reviewer A", "Reviewer B", "Reviewer C", "Evidence Editor"}
        for part, blob in parts.items():
            if not part.endswith((".xml", ".rels")):
                continue
            for node in E.fromstring(blob).iter():
                if node.get(W + "author") and node.get(W + "author") not in allowed_authors:
                    raise ValueError(f"Unreviewed author in {part}")
                if node.get("TargetMode") == "External" and node.get("Target") != "https://example.org/spec":
                    raise ValueError(f"Unreviewed external relationship in {part}")
                if E.QName(node).localname in ("creator", "lastModifiedBy") and node.text not in ("Revision fixture builder", "Evidence Editor"):
                    raise ValueError("Unreviewed core metadata")
        source = BASE / "sources" / f"{case['source']}.docx"
        audit = oracle(read(source), parts, case)
        if not audit["intent_correct"]:
            raise ValueError(f"Review editor action against its predeclared intent: {case['id']}: {audit}")
        output = BASE / "outputs" / f"{case['id']}.docx"
        if output.exists():
            raise ValueError("Previous published capture exists; use a new tranche")
        write(parts, output)
        records.append(dict(observation, source_sha256=digest(source.read_bytes()),
                            published_sha256=digest(output.read_bytes()),
                            raw_part_sha256=before_hashes,
                            published_part_sha256={part: digest(blob) for part, blob in parts.items()},
                            changed_parts=["docProps/core.xml"]))
    receipt = dict(producer="Microsoft Word for the web", observed_on="2026-09-12",
                   service_build=None, package_app_version="16.0000", service="word.cloud.microsoft",
                   labels_sha256=digest(labels_blob), sanitizer="Only core.xml lastModifiedBy replaced with Evidence Editor; ZIP repacked",
                   cases=records)
    (BASE / "capture-online.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
