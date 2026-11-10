"""--introduced: an edit is not blamed for findings its source already had.

Every document here is the reference document with one defect put in by hand,
so each test can say exactly which finding the source had and which the edit
added.
"""
from __future__ import annotations

import json
import re

import pytest
from lxml import etree

from conftest import ROOT, read_part, repack, run_cli

from ooxml_integrity import ERROR, WARN, Finding, check, compare, introduced
from ooxml_integrity.cli import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE
from ooxml_integrity.introduced import REASON, split
from ooxml_integrity.mcp_server import Server, ToolError


DOC = "word/document.xml"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CLAUSE = "The Supplier shall deliver the services with reasonable skill and care."


# ------------------------------------------------------------ documents
def _tree(path):
    return etree.fromstring(read_part(path, DOC).encode("utf-8"))


def _save(source, target, tree):
    data = etree.tostring(tree, xml_declaration=True, encoding="UTF-8",
                          standalone=True)
    return repack(source, target, {DOC: data})


def _orphan(tree, comment_id):
    """Remove every anchor of one comment; its body stays in comments.xml."""
    tags = (W + "commentRangeStart", W + "commentRangeEnd", W + "commentReference")
    found = [el for el in tree.iter(*tags) if el.get(W + "id") == comment_id]
    assert found, f"the reference document has no anchor for comment {comment_id}"
    for el in found:
        el.getparent().remove(el)
    return tree


def _paragraphs(tree):
    return tree.find(W + "body").findall(W + "p")


def _style(tree, index, value):
    _paragraphs(tree)[index].find(W + "pPr").find(W + "pStyle").set(W + "val", value)
    return tree


def _prepend(tree, text):
    paragraph = etree.Element(W + "p")
    etree.SubElement(etree.SubElement(paragraph, W + "r"), W + "t").text = text
    tree.find(W + "body").insert(0, paragraph)
    return tree


def _retext(tree, old, new):
    for t in tree.iter(W + "t"):
        if t.text == old:
            t.text = new
            return tree
    raise AssertionError(f"the reference document has no run reading {old!r}")


def _codes(findings):
    return sorted(f.code for f in findings)


@pytest.fixture
def source(base_docx, tmp_path):
    """The reference document with comment 2 already orphaned."""
    path = _save(base_docx, tmp_path / "source.docx", _orphan(_tree(base_docx), "2"))
    assert [f.code for f in check(path) if f.code == "CMT005"] == ["CMT005"]
    return path


@pytest.fixture
def unrelated_edit(source, tmp_path):
    """One clause reworded; the orphaned comment is the source's, not the edit's."""
    tree = _retext(_tree(source), CLAUSE, CLAUSE.replace("reasonable", "due"))
    return _save(source, tmp_path / "edited.docx", tree)


@pytest.fixture
def styled_source(base_docx, tmp_path):
    """The reference document whose third paragraph names a missing style."""
    path = _save(base_docx, tmp_path / "styled-source.docx",
                 _style(_tree(base_docx), 2, "NoSuchStyle"))
    assert _codes(f for f in check(path) if f.code == "STY001") == ["STY001"]
    return path


def _json(*args):
    result = run_cli("check", *map(str, args), "--json", "--no-config")
    return json.loads(result.stdout), result.returncode


# ------------------------------------------------------------------- CLI
def test_an_inherited_defect_does_not_fail_an_unrelated_edit(source, unrelated_edit):
    plain, code = _json(unrelated_edit, "--against", source)
    assert code == EXIT_FINDINGS
    assert "CMT005" in [f["code"] for f in plain["files"][0]["findings"]]
    assert "introduced" not in plain

    payload, code = _json(unrelated_edit, "--against", source, "--introduced")
    entry = payload["files"][0]
    assert code == EXIT_OK, entry
    assert payload["introduced"] is True
    assert "CMT005" not in [f["code"] for f in entry["findings"]]
    assert [(f["code"], f["suppressed_because"]) for f in entry["suppressed"]] == [
        ("CMT005", REASON)]
    assert entry["summary"]["error"] == 0


def test_a_new_defect_beside_an_inherited_one_still_fails(source, tmp_path):
    edited = _save(source, tmp_path / "edited.docx", _orphan(_tree(source), "1"))

    payload, code = _json(edited, "--against", source, "--introduced")
    entry = payload["files"][0]
    assert code == EXIT_FINDINGS
    kept = [f for f in entry["findings"] if f["code"] == "CMT005"]
    assert [f["message"].split(" is orphaned")[0] for f in kept] == ["comment id=1"]
    # the anchor the edit removed is lost content, which is never set aside
    assert "FID001" in [f["code"] for f in entry["findings"]]
    aside = [f for f in entry["suppressed"] if f["code"] == "CMT005"]
    assert [f["message"].split(" is orphaned")[0] for f in aside] == ["comment id=2"]


def test_a_finding_moved_by_an_inserted_paragraph_is_still_inherited(
        styled_source, tmp_path):
    edited = _save(styled_source, tmp_path / "edited.docx",
                   _prepend(_tree(styled_source), "Draft for discussion."))
    before = [f.where for f in check(styled_source) if f.code == "STY001"]
    after = [f.where for f in check(edited) if f.code == "STY001"]
    assert before != after, "the inserted paragraph must move the finding"

    payload, code = _json(edited, "--against", styled_source, "--introduced")
    entry = payload["files"][0]
    assert code == EXIT_OK, entry
    assert [f["code"] for f in entry["suppressed"]] == ["STY001"]


def test_matching_is_counted_and_reports_the_new_location(styled_source, tmp_path):
    edited = _save(styled_source, tmp_path / "edited.docx",
                   _style(_tree(styled_source), 0, "NoSuchStyle"))

    payload, code = _json(edited, "--against", styled_source, "--introduced")
    entry = payload["files"][0]
    assert code == EXIT_FINDINGS
    kept = [f["where"] for f in entry["findings"] if f["code"] == "STY001"]
    aside = [f["where"] for f in entry["suppressed"] if f["code"] == "STY001"]
    assert kept == ["/w:document/w:body/w:p[1]/w:pPr/w:pStyle"]
    assert aside == ["/w:document/w:body/w:p[3]/w:pPr/w:pStyle"]


def test_an_unreadable_source_absorbs_nothing(source, tmp_path):
    broken = tmp_path / "broken-source.docx"
    broken.write_bytes(b"not an OOXML package")

    payload, code = _json(source, "--against", broken, "--introduced")
    entry = payload["files"][0]
    assert code == EXIT_FINDINGS
    assert {"CMT005", "FID000"} <= {f["code"] for f in entry["findings"]}
    assert entry["suppressed"] == []


def test_a_deck_still_fails_closed_on_the_comparison(root):
    deck = root / "corpus" / "deck.pptx"

    payload, code = _json(deck, "--against", deck, "--introduced")
    entry = payload["files"][0]
    assert code == EXIT_FINDINGS
    assert [f["code"] for f in entry["findings"]] == ["FID000"]
    assert "PPT001" in [f["code"] for f in entry["suppressed"]]


def test_introduced_needs_a_source(unrelated_edit):
    result = run_cli("check", str(unrelated_edit), "--introduced", "--no-config")
    assert result.returncode == EXIT_USAGE
    assert "--introduced needs --against" in result.stderr


def test_the_human_report_says_what_was_set_aside(source, unrelated_edit):
    result = run_cli("check", str(unrelated_edit), "--against", str(source),
                     "--introduced", "--no-config")
    assert result.returncode == EXIT_OK, result.stdout + result.stderr
    assert "1 finding(s) already in the source" in result.stdout
    assert "set aside by --introduced" in result.stdout

    shown = run_cli("check", str(unrelated_edit), "--against", str(source),
                    "--introduced", "--show-suppressed", "--no-config")
    assert f"[hidden] CMT005  {REASON}" in shown.stdout


# -------------------------------------------------------------- matching
def _finding(code, *, message="the same item", where="", part="word/document.xml",
             severity=ERROR):
    return Finding(code, severity, message, where, part)


@pytest.mark.parametrize("code", [
    "FID001", "FID004", "FID000", "INT001", "EXP001",
    "PKG000", "PKG002", "PKG006", "PKG009", "XML001", "CMT006", "PPT000",
])
def test_some_findings_are_never_set_aside(code):
    f = _finding(code)
    assert split([f], [f]) == ([f], [])


def test_one_source_finding_absorbs_one_edited_finding():
    f = _finding("CMT005")
    kept, aside = split([f, f], [f])
    assert kept == [f] and aside == [(f, REASON)]


def test_the_same_location_is_matched_first():
    there = _finding("STY001", where="/w:document/w:body/w:p[3]")
    moved = _finding("STY001", where="/w:document/w:body/w:p[1]")
    kept, aside = split([moved, there], [there])
    assert kept == [moved]
    assert aside == [(there, REASON)]


def test_another_message_or_part_is_another_finding():
    f = _finding("CMT005", message="comment id=1 is orphaned")
    other_item = _finding("CMT005", message="comment id=2 is orphaned")
    other_part = _finding("CMT005", message="comment id=1 is orphaned",
                          part="word/comments.xml")
    assert split([f], [other_item, other_part]) == ([f], [])


def test_severity_does_not_take_part_in_matching():
    # a config can raise or lower a code; the source is checked raw
    raised = _finding("STY002", severity=ERROR)
    raw = _finding("STY002", severity=WARN)
    assert split([raised], [raw]) == ([], [(raised, REASON)])


# --------------------------------------------------------------- Python
def test_the_python_api_separates_inherited_findings(source, unrelated_edit):
    found = check(unrelated_edit) + compare(source, unrelated_edit)
    new, inherited = introduced(found, source)
    assert "CMT005" not in _codes(new)
    assert [(f.code, why) for f, why in inherited] == [("CMT005", REASON)]


# ------------------------------------------------------------------ MCP
def test_the_mcp_compare_tool_takes_introduced(source, unrelated_edit):
    server = Server(no_config=True)
    plain = server.run(str(unrelated_edit), str(source))
    assert plain["exit_code"] == EXIT_FINDINGS

    result = server.run(str(unrelated_edit), str(source), None, True)
    assert result["exit_code"] == EXIT_OK, result["verdict"]
    assert result["report"]["introduced"] is True
    assert ("1 finding(s) already in the original, not failing: CMT005"
            in result["verdict"])


def test_an_mcp_client_can_send_introduced(source, unrelated_edit):
    from test_mcp_server import tool

    result = tool("compare", {"source": str(source), "edited": str(unrelated_edit),
                              "introduced": True})
    assert result["isError"] is False, result
    assert result["structuredContent"]["exit_code"] == EXIT_OK
    assert "already in the original" in result["content"][0]["text"]


def test_the_mcp_introduced_argument_must_be_a_boolean(source, unrelated_edit):
    with pytest.raises(ToolError, match="introduced must be true or false"):
        Server(no_config=True).run(str(unrelated_edit), str(source), None, "yes")


# --------------------------------------------------------------- Action
def test_the_action_passes_introduced_through_the_environment():
    text = (ROOT / "action.yml").read_text(encoding="utf-8")
    assert re.search(r"^  introduced:\n", text, re.M)
    assert "OOXML_INTRODUCED: ${{ inputs.introduced }}" in text
    assert "true) args+=(--introduced) ;;" in text
