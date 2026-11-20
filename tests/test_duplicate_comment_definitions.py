"""One comment id must identify a single definition in the related part."""
from copy import deepcopy
import json

from lxml import etree

from conftest import read_part, repack, run_cli
from ooxml_integrity import check
from ooxml_integrity.comments import W
from ooxml_integrity.xmlutil import fromstring
from research.adeu_pilot_probe import COMMENTS, renamed_comments


def _with_extra_definition(source, cid):
    comments = fromstring(read_part(source, COMMENTS).encode())
    original = comments.find(f"{W}comment[@{W}id='{cid}']")
    assert original is not None
    comments.append(deepcopy(original))
    return etree.tostring(comments)


def test_duplicate_definitions_fail_the_default_gate_once_per_id(base_docx, tmp_path):
    part = "notes/review.xml"
    named = renamed_comments(base_docx, tmp_path / "source.docx", part)
    assert check(named) == []
    comments = fromstring(read_part(named, part).encode())
    first, second = comments.findall(W + "comment")
    # One comment id is used for different text; even an exact copy of a
    # second comment still makes its definition ambiguous.
    changed = deepcopy(first)
    changed.find(".//" + W + "t").text = "Restore the prior amount."
    comments.extend([changed, deepcopy(first), deepcopy(second)])
    output = repack(named, tmp_path / "edited.docx", {part: etree.tostring(comments)})
    result = run_cli("check", str(output), "--against", str(named), "--no-config", "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    findings = json.loads(result.stdout)["files"][0]["findings"]
    assert [(f["code"], f["severity"], f["part"]) for f in findings] == [
        ("CMT008", "error", part), ("CMT008", "error", part)]
    assert sorted((f["extra"]["id"], f["extra"]["definitions"]) for f in findings) == [
        ("1", 3), ("2", 2)]


def test_equivalent_decimal_ids_count_as_one_ambiguous_comment(base_docx, tmp_path):
    comments = fromstring(read_part(base_docx, COMMENTS).encode())
    first = comments.find(f"{W}comment[@{W}id='1']")
    for spelling in ("01", "+01"):
        copy = deepcopy(first)
        copy.set(W + "id", spelling)
        comments.append(copy)
    output = repack(base_docx, tmp_path / "spellings.docx", {COMMENTS: etree.tostring(comments)})
    [finding] = [f for f in check(output) if f.code == "CMT008"]
    assert finding.severity.value == "error" and finding.part == COMMENTS
    assert (finding.extra["id"], finding.extra["definitions"]) == ("1", 3)


def test_nested_and_unlinked_comment_copies_are_clean(base_docx, tmp_path):
    part = "word/comments1.xml"
    named = renamed_comments(base_docx, tmp_path / "source.docx", part, decoy=True)
    comments = fromstring(read_part(named, part).encode())
    mc = "http://schemas.openxmlformats.org/markup-compatibility/2006"
    ac = etree.SubElement(comments, f"{{{mc}}}AlternateContent", nsmap={"mc": mc})
    etree.SubElement(ac, f"{{{mc}}}Choice", Requires="w")
    etree.SubElement(ac, f"{{{mc}}}Fallback").append(deepcopy(comments.find(W + "comment")))
    output = repack(named, tmp_path / "edited.docx", {
        part: etree.tostring(comments),
        COMMENTS: _with_extra_definition(named, "2"),
    })
    assert check(output) == []


def test_baseline_for_one_duplicate_id_does_not_hide_another(base_docx, tmp_path):
    output = tmp_path / "edited.docx"
    baseline = tmp_path / "baseline.json"
    args = ["check", str(output), "--no-config", "--json"]
    repack(base_docx, output, {COMMENTS: _with_extra_definition(base_docx, "1")})
    assert run_cli(*args, "--write-baseline", str(baseline)).returncode == 0
    accepted = run_cli(*args, "--baseline", str(baseline))
    assert accepted.returncode == 0
    assert [f["code"] for f in json.loads(accepted.stdout)["files"][0]["suppressed"]] == ["CMT008"]

    repack(base_docx, output, {COMMENTS: _with_extra_definition(base_docx, "2")})
    changed = run_cli(*args, "--baseline", str(baseline))
    assert changed.returncode == 1, changed.stdout + changed.stderr
    [finding] = json.loads(changed.stdout)["files"][0]["findings"]
    assert finding["code"] == "CMT008" and finding["extra"]["id"] == "2"
