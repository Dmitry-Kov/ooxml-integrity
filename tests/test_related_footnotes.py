"""Footnotes seen by a reader are the ones the main document relates."""
from copy import deepcopy
import json

from lxml import etree
import pytest

from conftest import read_part, repack, run_cli
from ooxml_integrity.comments import REL, W
from ooxml_integrity.xmlutil import fromstring


DOC = "word/document.xml"
NOTES = "word/footnotes.xml"
RELS = "word/_rels/document.xml.rels"
TYPES = "[Content_Types].xml"
RENAMED = "notes/annotations.xml"
TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"


def _root(path, part):
    return fromstring(read_part(path, part).encode())


def _relationship(path):
    rels = _root(path, RELS)
    return rels, rels.find(f"{REL}Relationship[@Type='{TYPE}']")


def _without_references(path):
    doc = _root(path, DOC)
    for ref in doc.iter(W + "footnoteReference"):
        ref.getparent().remove(ref)
    return etree.tostring(doc)


def _check(path, exit_code, *args):
    result = run_cli("check", str(path), "--no-config", "--coverage", "--json", *args)
    assert result.returncode == exit_code, result.stdout + result.stderr
    [entry] = json.loads(result.stdout)["files"]
    surface = next(item for item in entry["coverage"]["items"] if item["id"] == "docx.footnotes")
    return entry["findings"], surface


def test_conventional_related_footnotes_remain_clean(base_docx):
    findings, surface = _check(base_docx, 0)
    assert findings == []
    assert (surface["status"], surface["count"]) == ("checked", 6)


@pytest.mark.parametrize("keep_references, foreign_type", [
    (True, False), (True, True), (False, False),
], ids=["dangling", "unrelated-type-with-same-suffix", "no-footnotes"])
def test_unlinked_definitions_do_not_count(base_docx, tmp_path, keep_references, foreign_type):
    rels, relationship = _relationship(base_docx)
    if foreign_type:
        relationship.set("Type", "https://example.org/private/footnotes")
    else:
        rels.remove(relationship)
    edits = {RELS: etree.tostring(rels)}
    if not keep_references:
        edits[DOC] = _without_references(base_docx)
    # Both note bodies and both separators remain in the conventional ZIP entry.
    edited = repack(base_docx, tmp_path / "unlinked.docx", edits)
    findings, surface = _check(edited, 1 if keep_references else 0)
    if keep_references:
        assert [(f["code"], f["severity"]) for f in findings] == [("FTN001", "error")] * 2
        for note_id in (1, 2):
            assert any(f"id={note_id}" in f["message"].split() for f in findings)
        assert (surface["status"], surface["count"]) == ("checked", 2)
    else:
        assert findings == []
        assert (surface["status"], surface["count"]) == ("not-present", 0)


def test_renamed_related_part_wins_over_a_decoy_and_locates_orphan(base_docx, tmp_path):
    rels, relationship = _relationship(base_docx)
    relationship.set("Target", "../" + RENAMED)
    types = _root(base_docx, TYPES)
    override = deepcopy(types.find(f"*[@PartName='/{NOTES}']"))
    override.set("PartName", "/" + RENAMED)
    types.append(override)
    notes = _root(base_docx, NOTES)
    decoy = etree.Element(W + "footnotes")
    path = repack(base_docx, tmp_path / "renamed.docx", {
        RELS: etree.tostring(rels), TYPES: etree.tostring(types),
        NOTES: etree.tostring(decoy), RENAMED: etree.tostring(notes),
    })
    findings, surface = _check(path, 0)
    assert findings == []
    assert (surface["status"], surface["count"]) == ("checked", 6)

    orphan = deepcopy(notes.find(f"{W}footnote[@{W}id='1']"))
    orphan.set(W + "id", "17")
    notes.append(orphan)
    edited = repack(path, tmp_path / "orphan.docx", {RENAMED: etree.tostring(notes)})
    [finding], surface = _check(edited, 1)
    assert (finding["code"], finding["severity"], finding["part"]) == ("FTN002", "error", RENAMED)
    assert "id=17" in finding["message"].split()
    assert (surface["status"], surface["count"]) == ("checked", 7)


@pytest.mark.parametrize("problem, detail, location", [
    ("duplicate", "multiple", RELS),
    ("external", "internal", RELS),
    ("missing-target", "missing.xml", RELS),
    ("invalid-target", "#unexpected", RELS),
    ("wrong-root", "endnotes", NOTES),
    ("wrong-root-without-references", "endnotes", NOTES),
    ("malformed-xml", NOTES, NOTES),
])
def test_unusable_footnote_relationship_or_root_skips_the_surface(base_docx, tmp_path,
                                                                 problem, detail, location):
    rels, relationship = _relationship(base_docx)
    edits = {}
    if problem == "duplicate":
        other = deepcopy(relationship)
        other.set("Id", "rIdAnotherNotePart")
        rels.append(other)
    elif problem == "external":
        relationship.set("TargetMode", "External")
        relationship.set("Target", "https://example.org/notes.xml")
    elif problem == "missing-target":
        relationship.set("Target", "missing.xml")
    elif problem == "invalid-target":
        relationship.set("Target", "footnotes.xml#unexpected")
    elif problem.startswith("wrong-root"):
        notes = _root(base_docx, NOTES)
        notes.tag = W + "endnotes"  # The two matching footnote children still exist.
        edits[NOTES] = etree.tostring(notes)
        if problem == "wrong-root-without-references":
            edits[DOC] = _without_references(base_docx)
    else:
        edits[NOTES] = b"<footnotes"
    edits[RELS] = etree.tostring(rels)
    edited = repack(base_docx, tmp_path / "damaged.docx", edits)
    findings, surface = _check(edited, 1)
    [failure] = [f for f in findings if f["code"].startswith("FTN")]
    assert (failure["code"], failure["severity"], failure["part"]) == ("FTN003", "error", location)
    assert detail in failure["message"]
    assert surface["status"] == "skipped" and detail in surface["reason"]


def test_introduced_keeps_unreadable_footnotes_shared_with_the_source(base_docx, tmp_path):
    rels, relationship = _relationship(base_docx)
    relationship.set("TargetMode", "External")
    source = repack(base_docx, tmp_path / "source.docx", {RELS: etree.tostring(rels)})
    edited = repack(source, tmp_path / "edited.docx", {})
    [finding], surface = _check(edited, 1, "--against", str(source), "--introduced")
    assert (finding["code"], finding["severity"]) == ("FTN003", "error")
    assert surface["status"] == "skipped"
