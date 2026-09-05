"""Actual web downloads and labels are tested offline, without a Microsoft account."""
from __future__ import annotations

import copy
import json
import shutil

import pytest

from research import build_docx_evidence as corpus
from research import online_docx_evidence as online
from research import windows_docx_evidence as privacy

ROOT = corpus.EVIDENCE
MANIFEST = json.loads(corpus.MANIFEST.read_text(encoding="utf-8"))
ONLINE = [s for s in MANIFEST["sources"] if s["producer"]["id"] == "word-online"]


@pytest.fixture(scope="module")
def receipt():
    return json.loads((ROOT / "provenance/word-online.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("source", ONLINE, ids=lambda s: s["id"])
def test_web_edit_and_metadata_only_sanitisation_have_auditable_receipts(source, receipt):
    entry = next(e for e in receipt["documents"] if e["id"] == source["id"])
    before, after = ROOT / entry["input"], ROOT / entry["output"]
    assert online.audit_edit(before, after) == entry["semantic_audit"]
    assert entry["input_sha256"] == corpus._sha256(before)
    assert entry["published_output_sha256"] == source["sha256"] == corpus._sha256(after)
    assert entry["replace_count"] == 1 and entry["saved"] and entry["downloaded"]
    cleanup = entry["sanitisation"]
    published = privacy.part_hashes(corpus._read_package(after)[0])
    assert published == cleanup["published_part_sha256"]
    assert cleanup["removed_parts"] == []
    assert set(cleanup["changed_parts"]) == {"docProps/core.xml", "docProps/app.xml", "word/comments.xml"}
    assert set(cleanup["raw_part_sha256"]) == set(published)
    assert {p for p in published if published[p] != cleanup["raw_part_sha256"][p]} == set(cleanup["changed_parts"])
    assert published["word/document.xml"] != privacy.part_hashes(corpus._read_package(before)[0])["word/document.xml"]


def test_complete_web_tranche_is_private_and_honest_about_provenance(receipt):
    assert len(ONLINE) == len(receipt["documents"]) == 10
    assert receipt["operation"] == online.OPERATION
    assert receipt["service"] == "word.cloud.microsoft"
    assert "not exposed" in receipt["version"]
    assert "not Microsoft-signed" in receipt["review"]
    assert "no independent human" in receipt["review"]
    paths = {path for pair in MANIFEST["pairs"] if pair["id"].startswith("online-")
             for path in (pair["source"], pair["output"])}
    assert len(paths) == 60
    for path in paths:
        privacy.audit_privacy(ROOT / path)
    receipt_bytes = (ROOT / "provenance/word-online.json").read_bytes()
    assert b"\r" not in receipt_bytes
    for private in (b"docId=", b"driveId=", b"/Users/", b"Dmitrii", b"Kovalev"):
        assert private not in receipt_bytes


@pytest.mark.parametrize("defect", ["no-edit", "extra-text", "extra-whitespace", "anchor-id", "anchor-position", "comment-id", "cell", "header"])
def test_clean_label_oracle_rejects_missing_edit_and_unexplained_changes(tmp_path, defect):
    source = ONLINE[0]
    before = ROOT / "roundtrips" / f"{source['id']}.docx"
    after = tmp_path / "changed.docx"
    shutil.copyfile(before if defect == "no-edit" else ROOT / source["path"], after)
    if defect != "no-edit":
        parts, order = corpus._read_package(after)
        part = "word/document.xml"
        if defect == "header":
            part = next(p for p in parts if p.startswith("word/header") and p.endswith(".xml"))
        elif defect == "comment-id":
            part = "word/comments.xml"
        root = corpus._xml(parts, part)
        if defect == "comment-id":
            next(root.iter(corpus.W + "comment")).set(corpus.W + "id", "999")
        elif defect == "extra-whitespace":
            text = next(root.iter(corpus.W + "t"))
            text.text = text.text.replace(" ", "  ", 1)
        elif defect == "anchor-id":
            next(root.iter(corpus.W + "commentRangeStart")).set(corpus.W + "id", "999")
        elif defect == "anchor-position":
            anchor = next(root.iter(corpus.W + "commentRangeStart"))
            paragraph = anchor.getparent()
            paragraph.remove(anchor)
            paragraph.insert(1, anchor)
        elif defect == "cell":
            next(next(root.iter(corpus.W + "tc")).iter(corpus.W + "t")).text = "changed cell"
        else:
            next(root.iter(corpus.W + "t")).text += " unexplained"
        corpus._store_xml(parts, part, root)
        corpus._write_package(parts, order, after)
    with pytest.raises(ValueError, match="semantic|anchor|text changed"):
        online.audit_edit(before, after)


def test_import_cannot_overwrite_web_evidence(tmp_path):
    manifest = tmp_path / "manifest.json"
    privacy.write_json(manifest, MANIFEST)
    before = manifest.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        online.import_batch(tmp_path / "absent", manifest)
    assert manifest.read_bytes() == before


def test_import_rejects_unobserved_run_without_touching_corpus(tmp_path):
    manifest = copy.deepcopy(MANIFEST)
    manifest["sources"] = [s for s in manifest["sources"] if s not in ONLINE]
    path = tmp_path / "evidence/manifest.json"
    privacy.write_json(path, manifest)
    staging = tmp_path / "staging"
    privacy.write_json(staging / "batch.json", {})
    privacy.write_json(staging / "web-run.json", {"completed": False})
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Incomplete"):
        online.import_batch(staging, path)
    assert path.read_bytes() == before
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("fault", ["missing-document", "duplicate-document", "not-saved", "wrong-count", "hash", "private-url", "escape"])
def test_import_receipt_validation_fails_before_corpus_writes(tmp_path, receipt, fault):
    manifest = copy.deepcopy(MANIFEST)
    manifest["sources"] = [s for s in manifest["sources"] if s not in ONLINE]
    path = tmp_path / "evidence/manifest.json"
    privacy.write_json(path, manifest)
    staging = tmp_path / "staging"
    request = {"edit": {"find": online.BEFORE, "replace": online.AFTER, "count": 1}, "documents": []}
    run = {"completed": True, "operation": online.OPERATION, "service": "word.cloud.microsoft",
           "observed_on": receipt["observed_on"], "documents": []}
    for source in ONLINE:
        entry = next(e for e in receipt["documents"] if e["id"] == source["id"])
        item = {"id": source["id"], "category": source["category"], "input": entry["input"],
                "output": entry["output"], "input_sha256": entry["input_sha256"]}
        for relative in (item["input"], item["output"]):
            (staging / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, staging / relative)
        request["documents"].append(item)
        # Test data reuses public sanitised bytes; it does not claim a new capture.
        run["documents"].append({"id": item["id"], "input_sha256": item["input_sha256"],
                                 "raw_output_sha256": corpus._sha256(staging / item["output"]),
                                 "replace_count": 1, "saved": True, "downloaded": True})
    if fault == "missing-document":
        run["documents"].pop()
    elif fault == "duplicate-document":
        run["documents"][-1] = run["documents"][0]
    elif fault == "not-saved":
        run["documents"][0]["saved"] = False
    elif fault == "wrong-count":
        run["documents"][0]["replace_count"] = True
    elif fault == "hash":
        run["documents"][0]["raw_output_sha256"] = "0" * 64
    elif fault == "private-url":
        run["document_url"] = "https://example.invalid/?docId=private"
    else:
        request["documents"][0]["output"] = "../outside.docx"
    privacy.write_json(staging / "batch.json", request)
    privacy.write_json(staging / "web-run.json", run)
    before = path.read_bytes()
    with pytest.raises(ValueError):
        online.import_batch(staging, path)
    assert path.read_bytes() == before
    assert list(path.parent.iterdir()) == [path]
