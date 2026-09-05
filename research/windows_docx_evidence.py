"""Append-only Windows Word evidence import; expected labels never use the checker."""
from __future__ import annotations

import collections
import hashlib
import json
import posixpath
import re
import shutil
import sys
from pathlib import Path

import docx
from lxml import etree

try:
    from . import build_docx_evidence as corpus
except ImportError:  # python research/build_docx_evidence.py
    import build_docx_evidence as corpus


WINDOWS_COUNTS = {
    "contract": 2, "report": 1, "letter": 1, "table": 2,
    "multi-section": 2, "review-heavy": 2,
}
ENVIRONMENT_FIELDS = {
    "word_version", "word_build", "word_file_version", "word_architecture",
    "windows_caption", "windows_version", "windows_build", "windows_architecture",
    "powershell_version",
}
FIXED_DATE = "2026-01-01T00:00:00Z"
IDENTITY = "ooxml-integrity evidence builder"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
DC = "{http://purl.org/dc/elements/1.1/}"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # The receipt itself is hashed. Windows newline translation must not make
    # its hash change when Git checks it out with the repository's LF policy.
    path.write_bytes((json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def part_hashes(parts: dict[str, bytes]) -> dict[str, str]:
    return {name: hashlib.sha256(blob).hexdigest() for name, blob in sorted(parts.items())}


def sanitise(path: Path) -> dict[str, object]:
    """Allowlisted identity cleanup, with a part-by-part transformation receipt.

    Printer settings can contain workstation/printer paths and are not document
    content. Remove that optional part and its exact references as one unit.
    No checker results influence this operation.
    """
    parts, order = corpus._read_package(path)
    before = part_hashes(parts)
    removed = {name for name in parts if name.startswith(("word/printerSettings/", "docProps/thumbnail."))}
    if "docProps/custom.xml" in parts:
        removed.add("docProps/custom.xml")
    for name in removed:
        del parts[name]
    for name, blob in list(parts.items()):
        if not (name.endswith(".xml") or name.endswith(".rels")):
            continue
        root = etree.fromstring(blob)
        changed = False
        if name == "docProps/core.xml":
            for node in root:
                if node.tag in {DC + "creator", corpus.CP + "lastModifiedBy"}:
                    node.text = IDENTITY
                    changed = True
                elif node.tag in {corpus.DCTERMS + "created", corpus.DCTERMS + "modified", corpus.CP + "lastPrinted"}:
                    node.text = FIXED_DATE
                    changed = True
        if name == "docProps/app.xml":
            for node in root:
                if etree.QName(node).localname in {"Company", "Manager", "HyperlinkBase"}:
                    node.text = None
                    changed = True
                elif etree.QName(node).localname == "Template":
                    node.text = "Normal.dotm"
                    changed = True
        for node in list(root.iter()):
            local = etree.QName(node).localname
            if local in {"docVars", "attachedTemplate", "printerSettings"}:
                node.getparent().remove(node)
                changed = True
                continue
            if local == "Relationship" and (node.get("Type", "").endswith(("/printerSettings", "/custom-properties", "/attachedTemplate", "/thumbnail"))):
                node.getparent().remove(node)
                changed = True
                continue
            if local == "Override" and node.get("PartName", "").lstrip("/") in removed:
                node.getparent().remove(node)
                changed = True
                continue
            for attribute, value in list(node.attrib.items()):
                attribute_name = etree.QName(attribute).localname
                if attribute_name == "author" and not re.fullmatch(r"Evidence Reviewer(?: [23])?", value):
                    node.set(attribute, "Evidence Reviewer")
                    changed = True
                elif attribute_name == "initials" and value not in {"ER", "E2", "E3"}:
                    node.set(attribute, "ER")
                    changed = True
                elif attribute_name in {"userId", "providerId"}:
                    node.set(attribute, "synthetic-evidence")
                    changed = True
                elif attribute_name in {"date", "dateUtc"}:
                    node.set(attribute, FIXED_DATE)
                    changed = True
        if changed:
            corpus._store_xml(parts, name, root)
    corpus._write_package(parts, order, path)
    audit_privacy(path)
    after = part_hashes(parts)
    return {
        "policy": "windows-word-metadata-v1",
        "description": "Synthetic identities and fixed metadata dates; no user/host/absolute paths in receipt. Optional printer settings, thumbnails, custom properties, docVars and attached template links removed. ZIP timestamps/attributes normalised.",
        "removed_parts": sorted(removed),
        "changed_parts": [name for name in after if before.get(name) != after[name]],
        "raw_part_sha256": before,
        "published_part_sha256": after,
    }


def audit_privacy(path: Path) -> None:
    """Fail closed on identity fields and local paths; all inputs are synthetic."""
    parts, _ = corpus._read_package(path)
    for name, blob in parts.items():
        if not (name.endswith(".xml") or name.endswith(".rels")):
            # Our synthetic seeds have no media or embedded objects. Do not
            # silently publish an unreviewed binary (e.g. printer DEVMODE).
            raise ValueError(f"unreviewed binary part: {name}")
        text = blob.decode("utf-8")
        if re.search(r"(?:(?<![A-Za-z])[A-Za-z]:[\\/]|file:/|\\\\[^\\]|/Users/|/home/|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})", text):
            raise ValueError(f"possible local path or email in {name}")
        root = etree.fromstring(blob)
        for node in root.iter():
            local = etree.QName(node).localname
            if local in {"creator", "lastModifiedBy"} and node.text not in {None, "", IDENTITY}:
                raise ValueError(f"unexpected core identity in {name}")
            if local in {"Company", "Manager", "HyperlinkBase"} and node.text:
                raise ValueError(f"unexpected extended identity in {name}")
            for key, value in node.attrib.items():
                local_key = etree.QName(key).localname
                if local_key == "author" and not re.fullmatch(r"Evidence Reviewer(?: [23])?", value):
                    raise ValueError(f"unexpected author in {name}")
                if local_key == "initials" and value not in {"ER", "E2", "E3"}:
                    raise ValueError(f"unexpected initials in {name}")
                if local_key in {"userId", "providerId"} and value != "synthetic-evidence":
                    raise ValueError(f"unexpected account identifier in {name}")


def semantic_facts(path: Path) -> dict[str, object]:
    """Direct XML oracle for the known synthetic inputs, independent of check/compare.

    Compare body text, cell text, comments, anchors, section slots and effective
    header/footer text. This is a structural/content audit, never a visual one.
    """
    parts, _ = corpus._read_package(path)
    main = corpus._xml(parts, "word/document.xml")
    def text(node):
        return re.sub(r"\s+", " ", "".join(t.text or "" for t in node.iter(corpus.W + "t"))).strip()
    comments = corpus._xml(parts, "word/comments.xml")
    rels = corpus._xml(parts, "word/_rels/document.xml.rels")
    targets = {r.get("Id"): posixpath.normpath(posixpath.join("word", r.get("Target", ""))).lstrip("/") for r in rels}
    inherited = {}
    stories = []
    sections = list(main.iter(corpus.W + "sectPr"))
    for section in sections:
        for node in section:
            if node.tag in {corpus.W + "headerReference", corpus.W + "footerReference"}:
                key = (etree.QName(node).localname, node.get(corpus.W + "type", "default"))
                inherited[key] = text(corpus._xml(parts, targets[node.get(R + "id")]))
        # Empty producer-added story slots carry no words.
        stories.append(sorted((kind, variant, value) for (kind, variant), value in inherited.items() if value))
    return {
        "main_text": text(main),
        "table_cells": [[text(cell) for cell in table.iter(corpus.W + "tc")] for table in main.iter(corpus.W + "tbl")],
        "comment_bodies": sorted(text(comment) for comment in comments),
        "comment_anchors": len(list(main.iter(corpus.W + "commentReference"))),
        "sections": len(sections),
        "stories": stories,
    }


def prepare(staging: Path) -> dict[str, object]:
    if staging.exists():
        raise ValueError("Use a fresh staging directory; existing files are never overwritten.")
    staging.mkdir(parents=True)
    documents = []
    for category, count in WINDOWS_COUNTS.items():
        for ordinal in range(1, count + 1):
            source_id = f"windows-{category}-{ordinal:02d}"
            seed = staging / "inputs" / f"{source_id}.docx"
            seed.parent.mkdir(exist_ok=True)
            corpus._build_seed(corpus.SourceSpec(source_id, category, ordinal, "word-windows"), seed)
            sanitise(seed)
            documents.append({
                "id": source_id, "category": category,
                "input": f"inputs/{seed.name}", "input_sha256": corpus._sha256(seed),
                "output": f"raw/{seed.name}",
            })
    request = {
        "schema_version": 1, "operation": "synthetic-clean-inputs-only",
        "seed_generator": "research/build_docx_evidence.py _build_seed",
        "seed_python_docx_version": docx.__version__, "python_version": sys.version.split()[0],
        "documents": documents,
    }
    write_json(staging / "batch.json", request)
    return request


def batch_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Path escapes the batch directory.")
    return path


def import_batch(staging: Path, manifest_path: Path = corpus.MANIFEST) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if any(source["producer"]["id"] == "word-windows" for source in manifest["sources"]):
        raise ValueError("Windows evidence already exists; refuse to replace it.")
    request = json.loads((staging / "batch.json").read_text(encoding="utf-8"))
    run = json.loads((staging / "word-run.json").read_text(encoding="utf-8-sig"))
    if not run["completed"] or run["operation"] != "Word.Application COM Documents.Open then Document.SaveAs2":
        raise ValueError("Word run is incomplete or has an unsupported operation.")
    requested = {item["id"]: item for item in request["documents"]}
    expected_ids = {f"windows-{category}-{ordinal:02d}": category
                    for category, count in WINDOWS_COUNTS.items()
                    for ordinal in range(1, count + 1)}
    if (len(request["documents"]) != 10 or len(run["documents"]) != 10 or
            {key: item["category"] for key, item in requested.items()} != expected_ids or
            {item["id"] for item in run["documents"]} != set(requested) or
            collections.Counter(item["category"] for item in requested.values()) != WINDOWS_COUNTS):
        raise ValueError("Expected exactly ten Windows documents covering the declared categories.")
    if set(run["environment"]) != ENVIRONMENT_FIELDS:
        raise ValueError("Unexpected environment fields; do not publish machine/account identifiers.")
    for field in ("word_version", "word_build", "word_file_version", "windows_version", "windows_build", "powershell_version"):
        if not re.fullmatch(r"\d+(?:\.\d+)*", run["environment"][field]):
            raise ValueError("Environment versions must be numeric, without paths or identifiers.")
    # Validate everything before touching the committed corpus.
    prepared = []
    for entry in run["documents"]:
        item = requested[entry["id"]]
        if (entry["input"] != item["input"] or entry["output"] != item["output"] or
                entry["input_sha256"] != item["input_sha256"] or
                entry["open_and_repair"] is not False or entry["save_format"] != 12 or entry["saved"] is not True):
            raise ValueError("Word receipt does not match the clean input request.")
        seed = batch_path(staging, item["input"])
        raw = batch_path(staging, item["output"])
        if corpus._sha256(seed) != item["input_sha256"] or corpus._sha256(raw) != entry["raw_output_sha256"]:
            raise ValueError("Word receipt hash mismatch.")
        published = staging / "sanitised" / raw.name
        published.parent.mkdir(exist_ok=True)
        shutil.copyfile(raw, published)
        receipt = sanitise(published)
        facts = semantic_facts(seed)
        if semantic_facts(raw) != facts or semantic_facts(published) != facts:
            raise ValueError(f"Unexplained semantic change during Word save/sanitisation: {item['id']}")
        if entry["input_object_counts"] != {
            "comments": len(facts["comment_bodies"]),
            "tables": len(facts["table_cells"]), "sections": facts["sections"],
        }:
            raise ValueError("Word object counts disagree with the input XML.")
        if part_hashes(corpus._read_package(seed)[0]) == receipt["raw_part_sha256"]:
            raise ValueError("No package changes from Word; investigate the producer evidence.")
        prepared.append((item, entry, seed, published, receipt, facts))

    root = manifest_path.parent
    sources = []
    roundtrips = []
    supporting = []
    receipts = []
    paths = [root / directory / f"{item['id']}.docx" for item, *_ in prepared for directory in ("sources", "roundtrips")]
    paths += [root / "outputs" / f"{item['id']}--{mutation}.docx" for item, *_ in prepared for mutation in ("clean-copy", "safe-text-edit", *corpus.CATEGORY_MUTATIONS[item["category"]])]
    provenance_path = root / "provenance" / "word-windows.json"
    if any(path.exists() for path in paths + [provenance_path]):
        raise ValueError("Import would overwrite corpus files.")
    for item, entry, seed, published, receipt, facts in prepared:
        source_relative = f"sources/{published.name}"
        input_relative = f"roundtrips/{seed.name}"
        for path, relative in ((seed, input_relative), (published, source_relative)):
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, root / relative)
        supporting.append({"path": input_relative, "sha256": corpus._sha256(seed), "role": "synthetic input before Windows Word save"})
        sources.append({
            "id": item["id"], "path": source_relative, "sha256": corpus._sha256(published),
            "category": item["category"],
            "producer": {"id": "word-windows", "version": run["environment"]["word_file_version"], "operation": "open-and-save as DOCX"},
            "synthetic": True, "personal_data": False,
            "postprocessing": receipt["description"],
            "provenance": "provenance/word-windows.json",
            "expected_behavior": "COM open without requested repair and SaveAs2 succeeded; semantic XML facts preserved. No visual or independent human review is claimed.",
        })
        roundtrips.append({
            "id": f"{item['id']}--word-roundtrip", "source": input_relative,
            "source_sha256": corpus._sha256(seed), "output": source_relative,
            "output_sha256": corpus._sha256(published), "mutation": "word-roundtrip",
            "class": "clean", "description": "Actual Windows Word open/save with metadata sanitisation",
            "label_method": "No-edit producer roundtrip plus direct XML semantic audit, independent of checker output",
            "label_basis": "Main-story text, all table cell text, comment bodies and anchor count, section count and effective header/footer text are identical before and after Word. No supported content was intentionally removed.",
            "expected_findings": [],
        })
        receipts.append({
            **{key: entry[key] for key in ("id", "input_sha256", "raw_output_sha256",
                "open_and_repair", "save_format", "saved", "input_object_counts")},
            "input": input_relative, "output": source_relative,
            "published_output_sha256": corpus._sha256(published),
            "sanitisation": receipt,
            "semantic_audit": {"equal_before_raw_and_published": True, "facts_sha256": hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest(), "fields": sorted(facts)},
        })
    provenance = {
        "schema_version": 1, "producer": "word-windows", "operation": run["operation"],
        "captured_at_utc": run["captured_at_utc"], "environment": run["environment"],
        "seed_generator": request["seed_generator"],
        "seed_python_docx_version": request["seed_python_docx_version"], "python_version": request["python_version"],
        "review": "Automated COM receipt and direct XML audit by the coding agent; no independent human or dual review claimed.",
        "raw_artifacts": "Raw Word saves are kept only in ignored local staging because Office metadata may contain personal information. Their hashes and every part hash are recorded; published saves differ only by the documented sanitisation.",
        "documents": receipts,
    }
    write_json(provenance_path, provenance)
    supporting.append({"path": "provenance/word-windows.json", "sha256": corpus._sha256(provenance_path), "role": "sanitised COM provenance and part-hash receipt"})
    pairs = corpus._build_outputs(sources, evidence_root=root)
    manifest["sources"].extend(sources)
    manifest["pairs"].extend(pairs + roundtrips)
    manifest.setdefault("supporting_artifacts", []).extend(supporting)
    manifest["producer_versions"]["word-windows"] = run["environment"]["word_file_version"]
    manifest["source_count"] = len(manifest["sources"])
    manifest["pair_count"] = len(manifest["pairs"])
    manifest["known_evidence_gaps"] = [gap for gap in manifest["known_evidence_gaps"] if gap != "No Word for Windows source has been collected."]
    manifest["known_evidence_gaps"] = [
        "Legacy labels have one maintainer review; Windows labels have automated semantic XML review by the coding agent, not independent human or dual review." if "dual review" in gap else gap
        for gap in manifest["known_evidence_gaps"]
    ]
    manifest["windows_added_on"] = run["captured_at_utc"][:10]
    write_json(manifest_path, manifest)
    return manifest
