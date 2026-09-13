"""Recorded Windows saves, privacy boundary and guarded content comparison."""
from __future__ import annotations

import json
import shutil

import pytest
from lxml import etree as E

from research import import_revision_windows as capture
from research import revision_evidence as evidence


def json_file(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def pair(profile="basic"):
    case = next(c for c in evidence.declared_cases() if c["id"] == f"windows-{profile}-save")
    return (evidence.read(evidence.BASE / "sources" / f"{profile}.docx"),
            evidence.read(evidence.BASE / "outputs" / f"windows-{profile}-save.docx"), case)


def test_windows_receipt_binds_predeclared_intent_sources_and_only_core_scrub():
    receipt = json_file(evidence.BASE / "capture-windows.json")
    batch = json_file(evidence.BASE / "batch-windows.json")
    expected = json_file(evidence.BASE / "expectations-windows.json")
    assert receipt["environment"]["word_file_version"] == "16.0.14334.20848"
    assert receipt["environment"]["word_architecture"] == "x64"
    assert receipt["captured_at_utc"] == "2026-09-13T08:19:48Z"
    for key, filename in (("batch_sha256", "batch-windows.json"), ("expectations_sha256", "expectations-windows.json"), ("labels_sha256", "labels-windows.json")):
        assert receipt[key] == evidence.digest((evidence.BASE / filename).read_bytes())
    assert batch["expectations_sha256"] == receipt["expectations_sha256"]
    assert batch["capture_script_sha256"] == evidence.digest((evidence.ROOT / "research/save_docx_word_windows.ps1").read_bytes())
    assert expected["prepared_at_utc"] == "2026-09-12"
    assert len(receipt["cases"]) == 3
    manifest = {c["id"]: c for c in json_file(evidence.BASE / "manifest.json")["pairs"]}
    for record, intent in zip(receipt["cases"], expected["cases"]):
        case = manifest[record["id"]]
        assert record["id"] == intent["id"]
        assert record["source_sha256"] == case["source_sha256"] == intent["source_sha256"]
        assert record["published_sha256"] == case["output_sha256"]
        assert case["provenance"] == "observed_word_windows_save"
        assert case["expected_findings"] == intent["expected_findings_if_preserved"] == []
        assert case["allowed_revision_losses"] == case["allowed_text_changes"] == []
        parts = evidence.read(evidence.BASE / case["output_path"])
        hashes = {p: evidence.digest(b) for p, b in parts.items()}
        assert hashes == record["published_part_sha256"]
        assert set(hashes) == set(record["raw_part_sha256"])
        assert [p for p in hashes if hashes[p] != record["raw_part_sha256"][p]] == ["docProps/core.xml"]
        assert record["changed_parts"] == ["docProps/core.xml"]
        assert evidence.facts(parts)["revisions"] == evidence.facts(capture.sanitise(parts))["revisions"]
        assert record["saved"] and not record["open_and_repair"]


@pytest.mark.parametrize("profile", ["basic", "nested", "table"])
def test_windows_revision_signatures_survive_and_layout_differences_remain_recorded(profile):
    source, output, case = pair(profile)
    assert evidence.oracle(source, output, case)["intent_correct"]
    strict = evidence.oracle(source, output, {k: v for k, v in case.items() if k != "comparison_profile"})
    assert not strict["intent_correct"]
    assert not strict["lost_revisions"]
    assert strict["violations"]["changed_review_structures"]
    record = next(c for c in json_file(evidence.BASE / "capture-windows.json")["cases"] if c["id"] == case["id"])
    assert json.loads(json.dumps(strict)) == record["original_comparison"]
    assert record["table_grid_widths_twips"]["source"] != record["table_grid_widths_twips"]["output"]


@pytest.mark.parametrize("damage", ["dangling_header", "retargeted_header", "missing_header", "grid_column", "cell_boundary", "revision_author", "note_anchor", "interior_empty_paragraph", "endnote_text"])
def test_word_save_comparison_still_rejects_content_and_reference_damage(damage):
    source, output, case = pair()
    part = evidence.MAIN
    root = E.fromstring(output[part])
    if damage in ("dangling_header", "retargeted_header"):
        reference = root.find(".//w:headerReference", evidence.NS)
        target = "missing" if damage == "dangling_header" else root.find(".//w:footerReference", evidence.NS).get(evidence.R + "id")
        reference.set(evidence.R + "id", target)
    elif damage == "missing_header":
        del output["word/header1.xml"]
    elif damage == "grid_column":
        grid = root.find(".//w:tblGrid", evidence.NS)
        grid.remove(grid[-1])
    elif damage == "cell_boundary":
        # Preserve concatenated paragraph text/order but move it into one cell.
        row = root.find(".//w:tr", evidence.NS)
        first, second = row.findall("w:tc", evidence.NS)
        first.append(second.find("w:p", evidence.NS))
        row.remove(second)
    elif damage == "revision_author":
        root.find(".//w:ins", evidence.NS).set(evidence.W + "author", "Reviewer B")
    elif damage == "note_anchor":
        root.find(".//w:footnoteReference", evidence.NS).set(evidence.W + "id", "missing")
    elif damage == "interior_empty_paragraph":
        root.find("w:body", evidence.NS).insert(2, E.Element(evidence.W + "p"))
    elif damage == "endnote_text":
        part = "word/endnotes.xml"
        root = E.fromstring(output[part])
        E.SubElement(root.find(".//w:r", evidence.NS), evidence.W + "t").text = "Unexpected note text"
    output[part] = evidence.xml(root)
    assert not evidence.oracle(source, output, case)["intent_correct"]


def test_fixed_layout_widths_are_not_normalized():
    source, _, case = pair()
    root = E.fromstring(source[evidence.MAIN])
    E.SubElement(root.find(".//w:tblPr", evidence.NS), evidence.W + "tblLayout").set(evidence.W + "type", "fixed")
    source[evidence.MAIN] = evidence.xml(root)
    root.find(".//w:gridCol", evidence.NS).set(evidence.W + "w", "100")
    output = dict(source, **{evidence.MAIN: evidence.xml(root)})
    assert not evidence.oracle(source, output, case)["intent_correct"]


@pytest.fixture
def replay_batch(tmp_path):
    """Use public sanitized bytes as a new test capture; no private raw needed."""
    base, staging = tmp_path / "evidence", tmp_path / "staging"
    shutil.copytree(evidence.BASE, base)
    (staging / "inputs").mkdir(parents=True)
    (staging / "raw").mkdir()
    for old, new in (("batch-windows.json", "batch.json"), ("expectations-windows.json", "expectations.json")):
        shutil.copyfile(base / old, staging / new)
    shutil.copyfile(evidence.ROOT / "research/save_docx_word_windows.ps1", staging / "save_docx_word_windows.ps1")
    receipt = json_file(base / "capture-windows.json")
    run = {key: receipt[key] for key in ("environment", "operation", "captured_at_utc")}
    run.update(schema_version=1, completed=True, documents=[])
    for item, record in zip(json_file(staging / "batch.json")["documents"], receipt["cases"]):
        shutil.copyfile(base / "sources" / item["input"].split("/")[-1], staging / item["input"])
        shutil.copyfile(base / "outputs" / f"{item['id']}.docx", staging / item["output"])
        entry = dict(item, raw_output_sha256=evidence.digest((staging / item["output"]).read_bytes()), saved=True, open_and_repair=False, save_format=12, input_object_counts=record["input_object_counts"])
        run["documents"].append(entry)
    save_json(staging / "word-run.json", run)
    return staging, base


@pytest.mark.parametrize("damage", [None, "incomplete", "repair", "missing_case", "raw_hash", "input_hash", "script", "expectations"])
def test_import_checks_capture_before_writing(replay_batch, damage):
    staging, base = replay_batch
    run = json_file(staging / "word-run.json")
    if damage == "incomplete":
        run["completed"] = False
    elif damage == "repair":
        run["documents"][0]["open_and_repair"] = True
    elif damage == "missing_case":
        run["documents"].pop()
    elif damage == "raw_hash":
        run["documents"][0]["raw_output_sha256"] = "0" * 64
    elif damage in ("input_hash", "script", "expectations"):
        target = {"input_hash": "inputs/basic.docx", "script": "save_docx_word_windows.ps1", "expectations": "expectations.json"}[damage]
        (staging / target).write_bytes(b"changed")
    save_json(staging / "word-run.json", run)
    if damage:
        with pytest.raises(ValueError):
            capture.validate_capture(staging, base)
    else:
        _, prepared = capture.validate_capture(staging, base)
        assert len(prepared) == 3
        with pytest.raises(ValueError, match="Previous published capture"):
            capture.import_capture(staging, base)


@pytest.mark.parametrize("damage", ["author", "binary", "external_link"])
def test_capture_does_not_publish_unreviewed_metadata(damage):
    _, parts, _ = pair()
    if damage == "binary":
        parts["word/printerSettings/printerSettings1.bin"] = b"private printer data"
    else:
        part = evidence.MAIN if damage == "author" else "word/_rels/document.xml.rels"
        root = E.fromstring(parts[part])
        if damage == "author":
            root.find(".//w:ins", evidence.NS).set(evidence.W + "author", "Unreviewed person")
        else:
            root[0].set("TargetMode", "External")
            root[0].set("Target", "https://unreviewed.example/template")
        parts[part] = evidence.xml(root)
    with pytest.raises(ValueError, match="Unreviewed"):
        capture.sanitise(parts)
