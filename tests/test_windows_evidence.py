"""Windows Word bytes are committed; these checks require no Office installation."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from lxml import etree

from research import build_docx_evidence as corpus
from research import windows_docx_evidence as windows

ROOT = corpus.EVIDENCE
MANIFEST = json.loads(corpus.MANIFEST.read_text(encoding="utf-8"))
WINDOWS = [s for s in MANIFEST["sources"] if s["producer"]["id"] == "word-windows"]
RECEIPT = json.loads((ROOT / "provenance/word-windows.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("source", WINDOWS, ids=lambda s: s["id"])
def test_actual_word_roundtrip_has_matching_provenance_and_semantic_xml(source):
    receipt = next(r for r in RECEIPT["documents"] if r["id"] == source["id"])
    before, after = ROOT / receipt["input"], ROOT / source["path"]
    assert corpus._sha256(before) == receipt["input_sha256"]
    assert corpus._sha256(after) == receipt["published_output_sha256"] == source["sha256"]
    assert receipt["saved"] is True and receipt["open_and_repair"] is False
    assert receipt["save_format"] == 12
    facts = windows.semantic_facts(before)
    assert facts == windows.semantic_facts(after)
    assert facts["comment_anchors"] >= 1
    assert facts["table_cells"] and all(facts["stories"])
    assert receipt["input_object_counts"] == {
        "comments": len(facts["comment_bodies"]), "tables": len(facts["table_cells"]),
        "sections": facts["sections"],
    }
    assert hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest() == receipt["semantic_audit"]["facts_sha256"]
    sanitisation = receipt["sanitisation"]
    published = windows.part_hashes(corpus._read_package(after)[0])
    assert published == sanitisation["published_part_sha256"]
    # These actual saves needed only metadata cleanup. Main XML, relationships,
    # all stories, tables, styles and extensions are the exact Word-written bytes.
    assert sanitisation["removed_parts"] == []
    assert set(sanitisation["changed_parts"]) == {"docProps/core.xml", "docProps/app.xml", "word/comments.xml"}
    raw = sanitisation["raw_part_sha256"]
    assert {part for part in raw if raw[part] != published[part]} == set(sanitisation["changed_parts"])
    assert raw["word/document.xml"] != windows.part_hashes(corpus._read_package(before)[0])["word/document.xml"]


def test_every_new_docx_passes_the_privacy_audit():
    paths = {s["path"] for s in WINDOWS}
    for pair in MANIFEST["pairs"]:
        if pair["id"].startswith("windows-"):
            paths.update((pair["source"], pair["output"]))
    assert len(paths) == 60
    for relative in sorted(paths):
        windows.audit_privacy(ROOT / relative)


def test_windows_environment_is_precise_without_machine_or_account_identifiers():
    env = RECEIPT["environment"]
    assert env["word_file_version"] == "16.0.14334.20848"
    assert env["word_architecture"] == "x64"
    assert env["windows_version"] == "10.0.26200"
    assert set(env) == {"word_version", "word_build", "word_file_version", "word_architecture",
                        "windows_caption", "windows_version", "windows_build", "windows_architecture",
                        "powershell_version"}
    assert "no independent human" in RECEIPT["review"]
    assert b"\r" not in (ROOT / "provenance/word-windows.json").read_bytes()


def test_hashed_receipt_writer_uses_lf_on_every_platform(tmp_path):
    path = tmp_path / "receipt.json"
    windows.write_json(path, {"value": "synthetic"})
    assert path.read_bytes() == b'{\n  "value": "synthetic"\n}\n'


def test_sanitisation_removes_identities_and_preserves_words(tmp_path):
    path = tmp_path / "private.docx"
    shutil.copyfile(ROOT / WINDOWS[0]["path"], path)
    before_facts = windows.semantic_facts(path)
    parts, order = corpus._read_package(path)
    core = corpus._xml(parts, "docProps/core.xml")
    core.find(windows.DC + "creator").text = "Private Test User"
    corpus._store_xml(parts, "docProps/core.xml", core)
    comments = corpus._xml(parts, "word/comments.xml")
    comment = next(comments.iter(corpus.W + "comment"))
    comment.set(corpus.W + "author", "Private Test User")
    comment.set(corpus.W + "initials", "PTU")
    corpus._store_xml(parts, "word/comments.xml", comments)
    app = corpus._xml(parts, "docProps/app.xml")
    for local, value in (("Company", "Private Employer"), ("Template", "C:/Users/private/Normal.dotm")):
        element = app.find("{*}" + local)
        if element is None:
            element = etree.SubElement(app, "{" + etree.QName(app).namespace + "}" + local)
        element.text = value
    corpus._store_xml(parts, "docProps/app.xml", app)
    corpus._write_package(parts, order, path)
    with pytest.raises(ValueError, match="identity|author|path"):
        windows.audit_privacy(path)
    windows.sanitise(path)
    windows.audit_privacy(path)
    assert windows.semantic_facts(path) == before_facts
    first_hash = corpus._sha256(path)
    windows.sanitise(path)
    assert corpus._sha256(path) == first_hash


def test_privacy_audit_rejects_unreviewed_binary_and_local_path(tmp_path):
    path = tmp_path / "unsafe.docx"
    parts, order = corpus._read_package(ROOT / WINDOWS[0]["path"])
    parts["word/unknown.bin"] = b"unreviewed payload"
    corpus._write_package(parts, order, path)
    with pytest.raises(ValueError, match="unreviewed binary"):
        windows.sanitise(path)
    del parts["word/unknown.bin"]
    root = corpus._xml(parts, "word/document.xml")
    next(root.iter(corpus.W + "t")).text = "C:/Users/private/secret"
    corpus._store_xml(parts, "word/document.xml", root)
    corpus._write_package(parts, order, path)
    with pytest.raises(ValueError, match="path or email"):
        windows.sanitise(path)


def test_import_refuses_to_replace_existing_windows_tranche(tmp_path):
    manifest = tmp_path / "manifest.json"
    windows.write_json(manifest, MANIFEST)
    before = manifest.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        windows.import_batch(tmp_path / "missing-staging", manifest)
    assert manifest.read_bytes() == before


def test_import_rejects_incomplete_word_run_without_modifying_corpus(tmp_path):
    manifest = copy.deepcopy(MANIFEST)
    manifest["sources"] = [s for s in manifest["sources"] if s not in WINDOWS]
    manifest_path = tmp_path / "evidence" / "manifest.json"
    windows.write_json(manifest_path, manifest)
    staging = tmp_path / "staging"
    windows.write_json(staging / "batch.json", {})
    windows.write_json(staging / "word-run.json", {"completed": False})
    before = manifest_path.read_bytes()
    with pytest.raises(ValueError, match="incomplete"):
        windows.import_batch(staging, manifest_path)
    assert manifest_path.read_bytes() == before
    assert list(manifest_path.parent.iterdir()) == [manifest_path]


def test_batch_paths_cannot_escape_staging(tmp_path):
    with pytest.raises(ValueError, match="escapes"):
        windows.batch_path(tmp_path, "../outside.docx")


def test_rebuild_preserves_real_word_pairs_and_every_committed_docx(tmp_path):
    copied = tmp_path / "evidence"
    shutil.copytree(ROOT, copied)
    originals = {path.relative_to(copied): corpus._sha256(path) for path in copied.rglob("*.docx")}
    rebuilt = corpus.rebuild_outputs(copied / "manifest.json")
    assert rebuilt == MANIFEST
    assert {relative: corpus._sha256(copied / relative) for relative in originals} == originals


def test_evaluator_checks_the_before_word_artifact_hash(tmp_path):
    copied = tmp_path / "evidence"
    shutil.copytree(ROOT, copied)
    path = copied / RECEIPT["documents"][0]["input"]
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(RuntimeError, match="hash mismatch"):
        corpus.evaluate(copied / "manifest.json")
