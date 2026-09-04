"""Header/footer fidelity follows section relationships, never part names."""
from __future__ import annotations

import json
import posixpath

import pytest
from lxml import etree

from conftest import CAREFUL_RUNS, read_part, repack, run_cli

from ooxml_integrity import Severity, compare


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
W = "{" + W_NS + "}"
R = "{" + R_NS + "}"
REL = "{" + REL_NS + "}"
DOC = "word/document.xml"
DOC_RELS = "word/_rels/document.xml.rels"


def _story(kind: str, text: str = "", *, tracked: bool = False,
           split_runs: bool = False) -> bytes:
    root_name = "hdr" if kind == "header" else "ftr"
    root = etree.Element(W + root_name, nsmap={"w": W_NS})
    paragraph = etree.SubElement(root, W + "p")
    parent = paragraph
    if tracked:
        parent = etree.SubElement(paragraph, W + "ins", {
            W + "id": "77",
            W + "author": "Reviewer",
        })
    pieces = text.split("|") if split_runs else [text]
    for piece in pieces:
        run = etree.SubElement(parent, W + "r")
        node = etree.SubElement(run, W + "t")
        node.text = piece
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def _make(
    base,
    destination,
    sections: list[list[tuple[str, str, str]]],
    stories: dict[str, tuple[str, str, bytes]],
):
    """Build section refs and matching relationships on the reference package."""
    document = etree.fromstring(read_part(base, DOC).encode())
    body = document.find(W + "body")
    assert body is not None
    for old in list(document.iter(W + "sectPr")):
        old.getparent().remove(old)

    for index, references in enumerate(sections):
        if index == len(sections) - 1:
            section = etree.SubElement(body, W + "sectPr")
        else:
            paragraph = etree.SubElement(body, W + "p")
            properties = etree.SubElement(paragraph, W + "pPr")
            section = etree.SubElement(properties, W + "sectPr")
        for kind, variant, rid in references:
            etree.SubElement(section, W + kind + "Reference", {
                W + "type": variant,
                R + "id": rid,
            })

    relationships = etree.fromstring(read_part(base, DOC_RELS).encode())
    for rel in list(relationships.iter(REL + "Relationship")):
        if (rel.get("Type") or "").endswith(("/header", "/footer")):
            rel.getparent().remove(rel)

    edits = {
        DOC: etree.tostring(document, xml_declaration=True, encoding="UTF-8"),
    }
    for rid, (kind, target, content) in stories.items():
        etree.SubElement(relationships, REL + "Relationship", {
            "Id": rid,
            "Type": R_NS + "/" + kind,
            "Target": target,
        })
        part = posixpath.normpath(posixpath.join("word", target))
        edits[part] = content
    edits[DOC_RELS] = etree.tostring(
        relationships, xml_declaration=True, encoding="UTF-8",
    )
    return repack(base, destination, edits)


def _story_findings(source, edited, code: str = "FID007"):
    return [finding for finding in compare(source, edited) if finding.code == code]


@pytest.mark.parametrize(("kind", "part", "old", "new"), (
    ("header", "word/header1.xml", "Reference Agreement - Draft 7",
     "Reference Agreement"),
    ("footer", "word/footer1.xml", "Confidential", "Public"),
))
def test_changed_header_or_footer_text_is_an_error(
        base_docx, tmp_path, kind, part, old, new):
    story = read_part(base_docx, part)
    changed = story.replace(old, new)
    edited = repack(
        base_docx, tmp_path / f"changed-{kind}.docx",
        {part: changed.encode()},
    )

    findings = _story_findings(base_docx, edited)

    assert len(findings) == 1
    assert findings[0].severity is Severity.ERROR
    assert findings[0].extra["story_kind"] == kind
    assert findings[0].extra["variant"] == "default"
    assert old in findings[0].message


def test_relationship_and_part_renumbering_is_clean(base_docx, tmp_path):
    edited = _make(
        base_docx,
        tmp_path / "renumbered-stories.docx",
        [[
            ("header", "default", "rIdHeader99"),
            ("footer", "default", "rIdFooter42"),
        ]],
        {
            "rIdHeader99": (
                "header", "header99.xml",
                read_part(base_docx, "word/header1.xml").encode(),
            ),
            "rIdFooter42": (
                "footer", "footer42.xml",
                read_part(base_docx, "word/footer1.xml").encode(),
            ),
        },
    )

    assert compare(base_docx, edited) == []


def test_first_even_and_default_header_footer_slots_are_distinct(
        base_docx, tmp_path):
    variants = ("default", "first", "even")
    source_stories = {}
    output_stories = {}
    source_refs = []
    output_refs = []
    for kind in ("header", "footer"):
        for variant in variants:
            source_id = f"rSrc-{kind}-{variant}"
            output_id = f"rOut-{kind}-{variant}"
            source_refs.append((kind, variant, source_id))
            output_refs.append((kind, variant, output_id))
            text = f"{kind} {variant}"
            source_stories[source_id] = (
                kind, f"{kind}-{variant}-source.xml", _story(kind, text),
            )
            output_stories[output_id] = (
                kind, f"{kind}-{variant}-output.xml",
                _story(kind, "changed first header" if (
                    kind == "header" and variant == "first") else text),
            )
    source = _make(
        base_docx, tmp_path / "all-story-types-source.docx",
        [source_refs], source_stories,
    )
    edited = _make(
        base_docx, tmp_path / "all-story-types-edited.docx",
        [output_refs], output_stories,
    )

    findings = _story_findings(source, edited)

    assert len(findings) == 1
    assert findings[0].extra["story_kind"] == "header"
    assert findings[0].extra["variant"] == "first"
    assert findings[0].extra["body"] == "header first"


def test_shared_and_split_parts_match_across_multiple_sections(
        base_docx, tmp_path):
    source = _make(
        base_docx,
        tmp_path / "shared-source.docx",
        [[
            ("header", "default", "rSharedH"),
            ("footer", "default", "rSharedF"),
        ], []],
        {
            "rSharedH": ("header", "shared-header.xml", _story("header", "H")),
            "rSharedF": ("footer", "shared-footer.xml", _story("footer", "F")),
        },
    )
    edited = _make(
        base_docx,
        tmp_path / "split-edited.docx",
        [[
            ("header", "default", "rH1"),
            ("footer", "default", "rF1"),
        ], [("header", "default", "rH2")]],
        {
            "rH1": ("header", "header-a.xml", _story("header", "H")),
            "rH2": ("header", "header-b.xml", _story("header", "H")),
            "rF1": ("footer", "footer-a.xml", _story("footer", "F")),
        },
    )

    assert compare(source, edited) == []


def test_losing_one_of_two_shared_story_uses_is_not_hidden(
        base_docx, tmp_path):
    source = _make(
        base_docx, tmp_path / "twice.docx",
        [[("header", "default", "rH")], []],
        {"rH": ("header", "shared.xml", _story("header", "Repeated"))},
    )
    edited = _make(
        base_docx, tmp_path / "once.docx",
        [[("header", "default", "rH")]],
        {"rH": ("header", "shared.xml", _story("header", "Repeated"))},
    )

    findings = _story_findings(source, edited)

    assert len(findings) == 1
    assert findings[0].extra["lost"] == 1
    assert findings[0].extra["in_source"] == 2


def test_renamed_empty_story_is_clean(base_docx, tmp_path):
    source = _make(
        base_docx, tmp_path / "empty-source.docx",
        [[("header", "default", "rEmpty1")]],
        {"rEmpty1": ("header", "empty1.xml", _story("header"))},
    )
    edited = _make(
        base_docx, tmp_path / "empty-edited.docx",
        [[("header", "default", "rEmpty2")]],
        {"rEmpty2": ("header", "empty2.xml", _story("header"))},
    )

    assert compare(source, edited) == []


def test_removing_a_referenced_story_is_a_loss(base_docx, tmp_path):
    edited = _make(
        base_docx,
        tmp_path / "no-header-reference.docx",
        [[("footer", "default", "rFooter")]],
        {
            "rFooter": (
                "footer", "footer-renamed.xml",
                read_part(base_docx, "word/footer1.xml").encode(),
            ),
        },
    )

    findings = _story_findings(base_docx, edited)

    assert len(findings) == 1
    assert findings[0].extra["story_kind"] == "header"
    assert findings[0].extra["body"] == "Reference Agreement - Draft 7"


def test_unresolvable_story_reference_fails_requested_comparison_closed(
        base_docx, tmp_path):
    document = read_part(base_docx, DOC).replace(
        'w:headerReference w:type="default" r:id="rId5"',
        'w:headerReference w:type="default" r:id="rIdMissing"',
    )
    edited = repack(
        base_docx, tmp_path / "unresolved-header.docx",
        {DOC: document.encode()},
    )

    result = run_cli(
        "check", str(edited), "--against", str(base_docx), "--json",
    )

    assert result.returncode == 1
    findings = json.loads(result.stdout)["files"][0]["findings"]
    assert any(finding["code"] == "REL001" for finding in findings)
    failures = [finding for finding in findings if finding["code"] == "FID000"]
    assert len(failures) == 1
    assert "comparison was NOT performed" in failures[0]["message"]


def test_adding_a_section_and_story_does_not_create_a_false_loss(
        base_docx, tmp_path):
    edited = _make(
        base_docx,
        tmp_path / "added-story.docx",
        [[
            ("header", "default", "rHeader"),
            ("footer", "default", "rFooter"),
            ("header", "first", "rNewFirst"),
        ], []],
        {
            "rHeader": (
                "header", "header-preserved.xml",
                read_part(base_docx, "word/header1.xml").encode(),
            ),
            "rFooter": (
                "footer", "footer-preserved.xml",
                read_part(base_docx, "word/footer1.xml").encode(),
            ),
            "rNewFirst": (
                "header", "new-first.xml", _story("header", "New first page"),
            ),
        },
    )

    assert compare(base_docx, edited) == []


def test_story_text_is_whitespace_normalised(base_docx, tmp_path):
    source = _make(
        base_docx, tmp_path / "whitespace-source.docx",
        [[("header", "default", "rSource")]],
        {"rSource": (
            "header", "source.xml", _story("header", "Alpha   Beta"),
        )},
    )
    edited = _make(
        base_docx, tmp_path / "whitespace-edited.docx",
        [[("header", "default", "rEdited")]],
        {"rEdited": (
            "header", "edited.xml",
            _story("header", "Alpha |\nBeta", split_runs=True),
        )},
    )

    assert compare(source, edited) == []


def test_lost_tracked_construct_is_caught_when_story_text_survives(
        base_docx, tmp_path):
    source = _make(
        base_docx, tmp_path / "tracked-source.docx",
        [[("header", "default", "rSource")]],
        {"rSource": (
            "header", "tracked.xml",
            _story("header", "Same visible text", tracked=True),
        )},
    )
    edited = _make(
        base_docx, tmp_path / "tracked-edited.docx",
        [[("header", "default", "rEdited")]],
        {"rEdited": (
            "header", "plain.xml", _story("header", "Same visible text"),
        )},
    )

    text_losses = _story_findings(source, edited)
    construct_losses = _story_findings(source, edited, "FID008")

    assert text_losses == []
    assert len(construct_losses) == 1
    assert construct_losses[0].severity is Severity.ERROR
    assert construct_losses[0].extra["tag"] == "ins"
    assert construct_losses[0].extra["story_kind"] == "header"


def test_six_careful_agent_outputs_keep_their_header_footer_stories(
        runs_dir, base_docx):
    compared = 0
    for name in CAREFUL_RUNS:
        output = runs_dir / name / "agreement.docx"
        if not output.exists():
            continue
        compared += 1
        findings = [
            finding for finding in compare(base_docx, output)
            if finding.code in ("FID007", "FID008")
        ]
        assert not findings, f"{name}: {[finding.message for finding in findings]}"
    if not compared:
        pytest.skip("careful agent outputs are unavailable")
