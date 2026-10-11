"""`fix`: three unique repairs, refusals with reasons, and the guarantees.

The inputs are the benchmark captures and agent runs that actually have the
three findings; variants change one thing in one of them. Word for Mac 16.113.4
opened the copies these repairs write (docs/fix.md); here the suite proves the
rest: what changes, what does not, and what is refused.
"""
from __future__ import annotations

import difflib
import json
import os
import zipfile
import zlib
from pathlib import Path

import pytest
from conftest import ROOT, read_part, repack, run_cli

from ooxml_integrity import check, compare
from ooxml_integrity.fix import (
    EXIT_NOTHING, EXIT_REFUSED, EXIT_REPAIRED, EXIT_UNVERIFIED, FixUsageError, fix,
)
from ooxml_integrity.repack import read_entries

CAPTURES = ROOT / "evidence" / "review-history-benchmark" / "captures"
SOURCES = ROOT / "evidence" / "review-history-benchmark" / "sources"
CODEX_S1 = CAPTURES / "codex-1" / "K5-S1-comment.docx"
CODEX_S1_ALL = [CAPTURES / f"codex-{n}" / "K5-S1-comment.docx" for n in range(1, 6)]
WORD_CHECK = ROOT / "evidence" / "review-history-benchmark" / "word-check-content-type"
D6 = WORD_CHECK / "variants" / "d6-codex-2-K5-S1-ct-fixed.docx"
D7 = WORD_CHECK / "variants" / "d7-codex-2-K5-S1-anchored-ct-fixed.docx"
CODEX_S2 = CAPTURES / "codex-3" / "K5-S2-comment.docx"
OPENCODE_S1 = CAPTURES / "opencode-qwen-1" / "K5-S1-comment.docx"
OPENCODE_S2 = CAPTURES / "opencode-qwen-1" / "K5-S2-comment.docx"
DOCX_MCP = CAPTURES / "docx-mcp-3" / "K5-S2-comment.docx"
DOCXENGINE = CAPTURES / "docxengine-1" / "K5-S2-comment.docx"
ADEU_S1 = CAPTURES / "adeu-1" / "K4-S1-tracked.docx"
ADEU_S2 = CAPTURES / "adeu-1" / "K4-S2-tracked.docx"
SEEDED_REV001 = ROOT / "evidence" / "docx-revisions" / "outputs" / "duplicate-id.docx"
TOP_LEVEL_ORPHAN = ROOT / "runs" / "t4_fast_fee" / "agreement.docx"
ORPHANED_PARENT = CAPTURES / "python-docx-setter-1" / "K1-S2-plain.docx"
S2_SOURCE = SOURCES / "word-review.docx"
BASE = ROOT / "corpus" / "base.docx"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _codes(path):
    return sorted(f.code for f in check(path))


def _members(path):
    with zipfile.ZipFile(path) as z:
        return {i.filename: z.read(i) for i in z.infolist()}


def _changed(a, b):
    x, y = _members(a), _members(b)
    assert list(x) == list(y)
    return sorted(n for n in x if x[n] != y[n])


# ------------------------------------------------------------- anchor-replies
# The five Codex S1 captures also have PKG010; they are under content-type.
@pytest.mark.parametrize("capture", [CODEX_S2, OPENCODE_S1, OPENCODE_S2,
                                     DOCX_MCP, DOCXENGINE],
                         ids=["codex-S2", "opencode-S1", "opencode-S2",
                              "docx-mcp", "docxengine"])
def test_anchor_replies_on_real_captures(capture, tmp_path):
    out = tmp_path / "fixed.docx"
    report = fix(capture, out)
    assert report.status == "repaired" and report.exit_code == EXIT_REPAIRED
    assert [r.repair for r in report.repaired] == ["anchor-replies"]
    assert "CMT005" in _codes(capture) and "CMT005" not in _codes(out)
    # Nothing new in the copy; Codex's S1 STY001 stays, listed as not repaired.
    assert sorted(set(_codes(out))) == sorted(set(_codes(capture)) - {"CMT005"})
    assert _changed(capture, out) == ["word/document.xml"]
    delta = compare(capture, out)
    assert all(f.code == "FID002" and f.severity.value == "info" for f in delta)
    assert "comment anchors" in " ".join(f.message for f in delta)
    assert report.verification.passed


def test_reply_is_written_in_words_thread_order(tmp_path):
    """Start after the thread's last start; end and reference run after the
    thread's last reference run, with the parent's run properties."""
    out = tmp_path / "fixed.docx"
    fix(CODEX_S2, out)
    doc = read_part(out, "word/document.xml")
    start = doc.index('<w:commentRangeStart w:id="2"/>')
    assert doc[start:].startswith(
        '<w:commentRangeStart w:id="2"/><w:commentRangeStart w:id="3"/>'
        '<w:commentRangeStart w:id="15"/>')
    tail = ('<w:commentRangeEnd w:id="3"/><w:r w:rsidR="00FF4098"><w:rPr>'
            '<w:rStyle w:val="CommentReference"/><w:sz w:val="22"/><w:szCs w:val="20"/>'
            '</w:rPr><w:commentReference w:id="3"/></w:r>'
            '<w:commentRangeEnd w:id="15"/><w:r><w:rPr>'
            '<w:rStyle w:val="CommentReference"/><w:sz w:val="22"/><w:szCs w:val="20"/>'
            '</w:rPr><w:commentReference w:id="15"/></w:r>')
    assert tail in doc


def test_only_the_repair_bytes_change(tmp_path):
    """The edited part keeps its declaration and every other byte."""
    for capture in (CODEX_S2, OPENCODE_S1, ADEU_S1):
        out = tmp_path / f"{capture.parent.name}-{capture.stem}.docx"
        fix(capture, out)
        old = read_part(capture, "word/document.xml")
        new = read_part(out, "word/document.xml")
        assert new.split("\n", 1)[0] == old.split("\n", 1)[0]  # XML declaration
        ops = [op for op in difflib.SequenceMatcher(None, old, new, autojunk=False)
               .get_opcodes() if op[0] != "equal"]
        if capture is ADEU_S1:  # one id, 101 -> 106
            assert [(op[0], old[op[1]:op[2]], new[op[3]:op[4]]) for op in ops] == [
                ("replace", "1", "6")]
            assert new[ops[0][3] - 8:ops[0][4] + 1] == 'w:id="106"'
        else:  # insertions only
            assert ops and all(op[0] == "insert" for op in ops)


def test_unchanged_members_are_copied_as_stored(tmp_path):
    out = tmp_path / "fixed.docx"
    fix(DOCX_MCP, out)
    before, after = read_entries(DOCX_MCP), read_entries(out)
    assert [e.name for e in before] == [e.name for e in after]
    with open(DOCX_MCP, "rb") as a, open(out, "rb") as b:
        for old, new in zip(before, after):
            assert (old.method, old.central[12:16]) == (new.method, new.central[12:16])
            if old.name == "word/document.xml":
                continue
            a.seek(old.offset)
            b.seek(new.offset)
            assert a.read(old.length) == b.read(new.length), old.name
    with zipfile.ZipFile(DOCX_MCP) as za, zipfile.ZipFile(out) as zb:
        for x, y in zip(za.infolist(), zb.infolist()):
            assert (x.filename, x.date_time, x.compress_type, x.external_attr) == (
                y.filename, y.date_time, y.compress_type, y.external_attr)


def test_nonstandard_comments_extended_root_is_named(tmp_path):
    report = fix(OPENCODE_S1, tmp_path / "fixed.docx")
    (detail,) = [r.detail for r in report.repaired]
    assert "whose root is commentList, not w15:commentsEx" in detail
    assert "LibreOffice shows it as a separate comment" in detail


def test_against_source_gains_nothing(tmp_path):
    out = tmp_path / "fixed.docx"
    report = fix(DOCX_MCP, out, against=S2_SOURCE)
    assert report.status == "repaired"
    assert report.verification.against_added == []
    before = {(f.code, f.message) for f in compare(S2_SOURCE, DOCX_MCP)}
    after = {(f.code, f.message) for f in compare(S2_SOURCE, out)}
    assert {c for c, _ in after - before} <= {"FID002"}


def _thread_variant(tmp_path, name, *, document=None, extended=None, styles=None):
    """docx-mcp's S2 output with one part changed."""
    edits = {}
    if document:
        edits["word/document.xml"] = document(read_part(DOCX_MCP, "word/document.xml")).encode()
    if extended:
        edits["word/commentsExtended.xml"] = extended(
            read_part(DOCX_MCP, "word/commentsExtended.xml")).encode()
    if styles:
        edits["word/styles.xml"] = styles(read_part(DOCX_MCP, "word/styles.xml")).encode()
    return repack(DOCX_MCP, tmp_path / f"{name}.docx", edits)


def _drop_markers(cid):
    def edit(doc):
        import re
        doc = re.sub(rf'<w:commentRange(Start|End) w:id="{cid}"/>', "", doc)
        return re.sub(rf'<w:r(?: [^>]*)?>(?:<w:rPr>(?:(?!</w:rPr>).)*</w:rPr>)?'
                      rf'<w:commentReference w:id="{cid}"/></w:r>', "", doc)
    return edit


def test_two_orphaned_replies_are_anchored_in_comment_order(tmp_path):
    variant = _thread_variant(tmp_path, "two-replies", document=_drop_markers("3"))
    assert [f.message.split()[1] for f in check(variant) if f.code == "CMT005"] == [
        "id=15", "id=3"]
    out = tmp_path / "fixed.docx"
    report = fix(variant, out)
    assert report.status == "repaired" and len(report.repaired) == 2
    doc = read_part(out, "word/document.xml")
    assert ('<w:commentRangeStart w:id="2"/><w:commentRangeStart w:id="3"/>'
            '<w:commentRangeStart w:id="15"/>') in doc
    assert doc.index('<w:commentReference w:id="3"/>') < doc.index(
        '<w:commentReference w:id="15"/>')
    assert "CMT005" not in _codes(out)


def test_reply_to_a_reply_is_refused(tmp_path):
    # Reply 15 (paraId 1C4295B9) names reply 3 (529A32D3) as its parent, not 2.
    old = 'w15:paraId="1C4295B9" w15:paraIdParent="4DCE4551"'
    assert old in read_part(DOCX_MCP, "word/commentsExtended.xml")
    variant = _thread_variant(
        tmp_path, "reply-to-reply",
        extended=lambda x: x.replace(old, 'w15:paraId="1C4295B9" '
                                          'w15:paraIdParent="529A32D3"'))
    report = fix(variant, tmp_path / "fixed.docx")
    assert report.status == "nothing-to-repair" and report.exit_code == EXIT_NOTHING
    (refused,) = [n for n in report.not_repaired if n.repair]
    assert "which is itself a reply" in refused.reason
    assert not (tmp_path / "fixed.docx").exists()


def test_undefined_reference_style_is_refused(tmp_path):
    import re
    variant = _thread_variant(
        tmp_path, "no-style",
        styles=lambda x: re.sub(r'<w:style [^>]*w:styleId="CommentReference".*?</w:style>',
                                "", x, flags=re.S))
    report = fix(variant, tmp_path / "fixed.docx")
    assert report.status == "nothing-to-repair"
    (refused,) = [n for n in report.not_repaired if n.repair]
    assert "undefined style CommentReference" in refused.reason


# --------------------------------------------------------- renumber-revisions
@pytest.mark.parametrize("capture", [ADEU_S1, ADEU_S2, SEEDED_REV001],
                         ids=["adeu-S1", "adeu-S2", "seeded"])
def test_renumber_revisions(capture, tmp_path):
    out = tmp_path / "fixed.docx"
    report = fix(capture, out)
    assert report.status == "repaired"
    assert "REV001" in _codes(capture) and "REV001" not in _codes(out)
    assert compare(capture, out) == []
    assert _changed(capture, out) == ["word/document.xml"]
    (repaired,) = report.repaired
    ids = set()
    for name, data in _members(capture).items():
        if name.endswith(".xml"):
            ids |= {int(v) for v in __import__("re").findall(rb'w:id="(-?\d+)"', data)}
    for change in repaired.changes:
        new = int(change.new.split('"')[1])
        assert new > max(ids)
        assert change.old != change.new and change.element in ("w:ins", "w:del")


def test_renumbering_keeps_text_authors_and_dates(tmp_path):
    out = tmp_path / "fixed.docx"
    fix(ADEU_S1, out)

    def revisions(path):
        from lxml import etree
        root = etree.fromstring(read_part(path, "word/document.xml").encode())
        return [(e.tag, e.get(W + "author"), e.get(W + "date"),
                 "".join(e.itertext())) for e in root.iter(W + "ins", W + "del")]
    assert revisions(ADEU_S1) == revisions(out)


# ---------------------------------------------------------------- content-type
TYPES = "[Content_Types].xml"
WRONG = 'ContentType="application/vnd.ms-word.commentsExtended+xml"'
RIGHT = ('ContentType="application/vnd.openxmlformats-officedocument.'
         'wordprocessingml.commentsExtended+xml"')
EXTENDED = '<Override PartName="/word/commentsExtended.xml" '


def _markers(path):
    import re
    return re.findall(r'<w:comment(?:RangeStart|RangeEnd|Reference) w:id="\d+"/>',
                      read_part(path, "word/document.xml"))


def _stored(path):
    """Each member's local header, compressed bytes and descriptor, as stored."""
    out = {}
    with open(path, "rb") as fh:
        for e in read_entries(path):
            fh.seek(e.offset)
            out[e.name] = fh.read(e.length)
    return out


def _types_variant(src, dst, edit):
    return repack(src, dst, {TYPES: edit(read_part(src, TYPES)).encode()})


@pytest.mark.parametrize("capture", CODEX_S1_ALL, ids=lambda p: p.parent.name)
def test_content_type_and_anchor_replies_compose_on_codex_s1(capture, tmp_path):
    """Word for Mac refused all five; d7, which it opened, has these two repairs."""
    out = tmp_path / "fixed.docx"
    report = fix(capture, out, against=BASE)
    assert report.status == "repaired" and report.exit_code == EXIT_REPAIRED
    assert [r.repair for r in report.repaired] == ["anchor-replies", "content-type"]
    before = _codes(capture)
    assert {"CMT005", "PKG010"} <= set(before)
    before.remove("CMT005")
    before.remove("PKG010")
    assert _codes(out) == before  # Codex's STY001 in codex-1 and -4 stays
    v = report.verification
    assert v.passed and v.check_added == [] and v.against_added == []
    assert sorted(f.code for f in v.check_removed) == ["CMT005", "PKG010"]
    assert v.changed_parts == _changed(capture, out) == [TYPES, "word/document.xml"]
    # The content type and the comment markers are d7's.
    assert read_part(out, TYPES) == read_part(D7, TYPES)
    assert _markers(out) == _markers(D7)
    (change,) = report.repaired[1].changes
    assert (change.part, change.element, change.where, change.line, change.old,
            change.new) == (TYPES, "Override", "/Types/Override[11]", 16, WRONG, RIGHT)
    assert "Word for Mac 16.113.4 refused" in report.repaired[1].detail


def test_only_the_content_type_value_changes(tmp_path):
    """The rest of [Content_Types].xml, and every member no repair edits, keep
    their bytes."""
    for capture in CODEX_S1_ALL:
        out = tmp_path / f"{capture.parent.name}.docx"
        fix(capture, out)
        with zipfile.ZipFile(capture) as za, zipfile.ZipFile(out) as zb:
            old, new = za.read(TYPES), zb.read(TYPES)
            for x, y in zip(za.infolist(), zb.infolist()):
                assert (x.filename, x.date_time, x.compress_type, x.external_attr) == (
                    y.filename, y.date_time, y.compress_type, y.external_attr)
        assert old.count(WRONG.encode()) == 1
        assert new == old.replace(WRONG.encode(), RIGHT.encode())
        a, b = _stored(capture), _stored(out)
        assert list(a) == list(b)
        assert [n for n in a if a[n] != b[n]] == [TYPES, "word/document.xml"]


def _deflates_like(path, names):
    """Whether this zlib compresses the named members to the bytes `path` stores."""
    entries = {e.name: e for e in read_entries(path)}
    with zipfile.ZipFile(path) as z, open(path, "rb") as fh:
        for name in names:
            e = entries[name]
            fh.seek(e.offset + len(e.header))
            packer = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15)
            if packer.compress(z.read(name)) + packer.flush() != fh.read(e.compressed):
                return False
    return True


@pytest.mark.parametrize("given", [CAPTURES / "codex-2" / "K5-S1-comment.docx", D6],
                         ids=["capture", "d6"])
def test_fix_writes_the_copy_word_opened(given, tmp_path):
    """Word opened d7 and showed the reply in its parent's thread. fix writes it
    from codex-2's capture, which Word refused, and from d6, which has only the
    content type corrected. The edited members' bytes depend on zlib."""
    out = tmp_path / "fixed.docx"
    assert fix(given, out).status == "repaired"
    assert _members(out) == _members(D7)
    edited = [TYPES, "word/document.xml"]
    a, b = _stored(out), _stored(D7)
    assert list(a) == list(b)
    assert [n for n in a if a[n] != b[n] and n not in edited] == []
    if _deflates_like(D7, edited):
        assert out.read_bytes() == D7.read_bytes()


def test_the_other_codex_outputs_differ_from_d7_only_where_codex_did(tmp_path):
    def edits(a, b):
        return [(op, a[i:j], b[k:m]) for op, i, j, k, m in difflib.SequenceMatcher(
            None, a, b, autojunk=False).get_opcodes() if op != "equal"]
    codex2, d7 = _members(CAPTURES / "codex-2" / "K5-S1-comment.docx"), _members(D7)
    for capture in CODEX_S1_ALL:
        out = tmp_path / f"{capture.parent.name}.docx"
        fix(capture, out)
        given, written = _members(capture), _members(out)
        for name in d7:
            assert edits(d7[name], written[name]) == edits(codex2[name], given[name]), (
                capture.parent.name, name)


def test_a_part_typed_by_a_default_is_refused(tmp_path):
    """Without its Override, commentsExtended.xml is application/xml through the
    Default for "xml", which also types every other .xml part."""
    import re
    variant = _types_variant(D7, tmp_path / "default.docx",
                             lambda t: re.sub(EXTENDED + r"[^>]*/>", "", t))
    assert [f.extra["declared"] for f in check(variant) if f.code == "PKG010"] == [
        "application/xml"]
    out = tmp_path / "fixed.docx"
    report = fix(variant, out)
    assert report.status == "nothing-to-repair" and report.exit_code == EXIT_NOTHING
    assert report.reason == "every CMT005/REV001/PKG010 finding was refused"
    (refused,) = [n for n in report.not_repaired if n.repair]
    assert refused.repair == "content-type" and refused.finding.code == "PKG010"
    assert 'the Default for the extension "xml"' in refused.reason
    assert "would retype every other part" in refused.reason
    assert not out.exists()


def test_a_refused_content_type_does_not_stop_another_repair(tmp_path):
    capture = CAPTURES / "codex-2" / "K5-S1-comment.docx"
    variant = _types_variant(capture, tmp_path / "default.docx",
                             lambda t: t.replace(EXTENDED + WRONG + "/>", ""))
    out = tmp_path / "fixed.docx"
    report = fix(variant, out)
    assert report.status == "repaired"
    assert [r.repair for r in report.repaired] == ["anchor-replies"]
    assert [n.repair for n in report.not_repaired if n.repair] == ["content-type"]
    assert _codes(out) == ["PKG010"] and _changed(variant, out) == ["word/document.xml"]


def test_two_overrides_for_the_part_are_refused(tmp_path):
    capture = CAPTURES / "codex-2" / "K5-S1-comment.docx"
    override = EXTENDED + WRONG + "/>"
    variant = _types_variant(capture, tmp_path / "twice.docx",
                             lambda t: t.replace(override, override * 2))
    report = fix(variant, tmp_path / "fixed.docx")
    (refused,) = [n for n in report.not_repaired if n.repair]
    assert refused.finding.code == "PKG010"
    assert "2 Overrides in [Content_Types].xml name word/commentsExtended.xml" in (
        refused.reason)


def test_a_content_types_part_fix_cannot_compress_is_refused(tmp_path):
    capture = CAPTURES / "codex-2" / "K5-S1-comment.docx"
    variant = tmp_path / "bzip2.docx"
    with zipfile.ZipFile(capture) as zin, zipfile.ZipFile(variant, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info),
                          zipfile.ZIP_BZIP2 if info.filename == TYPES
                          else zipfile.ZIP_DEFLATED)
    report = fix(variant, tmp_path / "fixed.docx")
    (refused,) = [n for n in report.not_repaired if n.repair]
    assert refused.reason == ("[Content_Types].xml uses compression method 12, "
                              "which fix does not write")


def test_another_relationship_type_is_repaired_and_word_is_not_claimed(tmp_path):
    """Any of the fifteen relationship types PKG010 reads; the attribute keeps
    its quotes. Word was observed only with commentsExtended."""
    styles = '<Override PartName="/word/styles.xml" ContentType="'
    expected = "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"
    assert styles + expected + '"/>' in read_part(BASE, TYPES)
    variant = _types_variant(BASE, tmp_path / "styles.docx", lambda t: t.replace(
        styles + expected + '"/>',
        "<Override PartName='/word/styles.xml' ContentType = 'application/xml'/>"))
    assert _codes(variant) == ["PKG010"]
    out = tmp_path / "fixed.docx"
    report = fix(variant, out, against=BASE)
    assert report.status == "repaired"
    (repaired,) = report.repaired
    (change,) = repaired.changes
    assert (change.old, change.new) == ("ContentType = 'application/xml'",
                                        f"ContentType = '{expected}'")
    assert "Word was not observed with this declaration" in repaired.detail
    assert _codes(out) == [] and compare(variant, out) == []
    assert _changed(variant, out) == [TYPES]
    assert read_part(out, TYPES) == read_part(variant, TYPES).replace(
        "'application/xml'", f"'{expected}'")


# ------------------------------------------------------------------ refusals
def test_top_level_orphan_is_refused_with_its_reason(tmp_path):
    out = tmp_path / "fixed.docx"
    report = fix(TOP_LEVEL_ORPHAN, out)
    assert report.status == "nothing-to-repair" and report.exit_code == EXIT_NOTHING
    (refused,) = [n for n in report.not_repaired if n.repair]
    assert refused.finding.code == "CMT005"
    assert "not a reply" in refused.reason and "does not guess" in refused.reason
    assert not out.exists()


def test_reply_whose_parent_lost_its_anchor_is_refused(tmp_path):
    report = fix(ORPHANED_PARENT, tmp_path / "fixed.docx")
    reasons = {n.finding.message.split()[1]: n.reason
               for n in report.not_repaired if n.repair}
    assert "not a reply" in reasons["id=2"]
    assert "replies to comment 2, which is not anchored" in reasons["id=3"]


def test_every_finding_not_repaired_is_listed_with_why(tmp_path):
    report = fix(CODEX_S1, tmp_path / "fixed.docx", against=BASE)
    listed = [(n.finding.code, n.origin) for n in report.not_repaired]
    remaining = [f.code for f in check(CODEX_S1) if f.code not in ("CMT005", "PKG010")]
    assert sorted(c for c, o in listed if o == "check") == sorted(remaining)
    assert ("STY001", "check") in listed
    assert sorted(c for c, o in listed if o == "against") == sorted(
        f.code for f in compare(BASE, CODEX_S1))
    assert all(n.reason for n in report.not_repaired)


def test_nothing_to_repair_writes_nothing(tmp_path):
    out = tmp_path / "fixed.docx"
    report = fix(BASE, out)
    assert report.status == "nothing-to-repair" and not out.exists()
    assert "no CMT005, REV001 or PKG010" in report.reason


def test_strict_package_is_refused(tmp_path):
    from test_strict_ooxml import _strict
    strict = _strict(SEEDED_REV001, tmp_path / "strict.docx")
    report = fix(strict, tmp_path / "fixed.docx")
    assert report.status == "input-refused" and report.exit_code == EXIT_REFUSED
    assert "Strict" in report.reason
    assert not (tmp_path / "fixed.docx").exists()


def test_malformed_part_is_refused(tmp_path):
    broken = repack(ADEU_S1, tmp_path / "broken.docx", {
        "word/settings.xml": b"<w:settings"})
    report = fix(broken, tmp_path / "fixed.docx")
    assert report.status == "input-refused" and "XML001" in report.reason


def test_unreadable_package_is_refused(tmp_path):
    junk = tmp_path / "junk.docx"
    junk.write_bytes(b"not a zip")
    report = fix(junk, tmp_path / "fixed.docx")
    assert report.status == "input-refused" and report.exit_code == EXIT_REFUSED


def test_pptx_is_a_usage_error(tmp_path):
    with pytest.raises(FixUsageError, match=".docx files only"):
        fix(ROOT / "corpus" / "deck.pptx", tmp_path / "fixed.pptx")
    r = run_cli("fix", "corpus/deck.pptx", "-o", str(tmp_path / "x.pptx"))
    assert r.returncode == EXIT_REFUSED and ".docx files only" in r.stderr


# --------------------------------------------------------- copies, not edits
def test_never_in_place(tmp_path):
    copy = tmp_path / "in.docx"
    copy.write_bytes(ADEU_S1.read_bytes())
    for target in (copy, tmp_path / "." / "in.docx"):
        with pytest.raises(FixUsageError, match="not the input"):
            fix(copy, target, force=True)
    link = tmp_path / "link.docx"
    os.link(copy, link)
    with pytest.raises(FixUsageError, match="not the input"):
        fix(copy, link, force=True)
    assert copy.read_bytes() == ADEU_S1.read_bytes()


def test_output_is_never_the_source(tmp_path):
    source = tmp_path / "source.docx"
    source.write_bytes(S2_SOURCE.read_bytes())
    with pytest.raises(FixUsageError, match="--against source"):
        fix(DOCX_MCP, source, against=source, force=True)
    assert source.read_bytes() == S2_SOURCE.read_bytes()


def test_existing_output_needs_force(tmp_path):
    out = tmp_path / "fixed.docx"
    out.write_bytes(b"keep me")
    with pytest.raises(FixUsageError, match="--force"):
        fix(ADEU_S1, out)
    assert out.read_bytes() == b"keep me"
    r = run_cli("fix", str(ADEU_S1), "-o", str(out))
    assert r.returncode == EXIT_REFUSED and out.read_bytes() == b"keep me"
    assert fix(ADEU_S1, out, force=True).status == "repaired"
    assert "REV001" not in _codes(out)


def test_output_directory_must_exist(tmp_path):
    with pytest.raises(FixUsageError, match="directory does not exist"):
        fix(ADEU_S1, tmp_path / "missing" / "fixed.docx")
    with pytest.raises(FixUsageError, match="is a directory"):
        fix(ADEU_S1, tmp_path, force=True)


def test_output_is_deterministic(tmp_path):
    for capture in (CODEX_S2, ADEU_S2):
        a, b = tmp_path / "a.docx", tmp_path / "b.docx"
        fix(capture, a, force=True)
        fix(capture, b, force=True)
        assert a.read_bytes() == b.read_bytes()


def test_failed_verification_leaves_nothing(tmp_path, monkeypatch):
    from ooxml_integrity import fix as module
    real = module._verify

    def failing(*args, **kwargs):
        v = real(*args, **kwargs)
        v.passed, v.failures = False, ["forced failure"]
        return v
    monkeypatch.setattr(module, "_verify", failing)
    out = tmp_path / "fixed.docx"
    report = fix(ADEU_S1, out)
    assert report.status == "verification-failed" and report.exit_code == EXIT_UNVERIFIED
    assert report.output_sha256 is None
    assert list(tmp_path.iterdir()) == []


def test_internal_error_leaves_nothing(tmp_path, monkeypatch):
    from ooxml_integrity import fix as module

    def broken(*args, **kwargs):
        raise RuntimeError("boom")
    monkeypatch.setattr(module, "repack", broken)
    report = fix(ADEU_S1, tmp_path / "fixed.docx")
    assert report.status == "verification-failed" and "boom" in report.reason
    assert list(tmp_path.iterdir()) == []


def test_input_is_never_modified(tmp_path):
    copy = tmp_path / "in.docx"
    copy.write_bytes(CODEX_S2.read_bytes())
    fix(copy, tmp_path / "out.docx")
    assert copy.read_bytes() == CODEX_S2.read_bytes()


# ------------------------------------------------------------------- the CLI
def test_cli_json_report(tmp_path):
    out = tmp_path / "fixed.docx"
    r = run_cli("fix", str(CODEX_S2), "-o", str(out), "--against", str(S2_SOURCE),
                "--json")
    assert r.returncode == EXIT_REPAIRED, r.stderr
    doc = json.loads(r.stdout)
    import hashlib

    def sha(p):
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    from ooxml_integrity import __version__
    assert doc["version"] == __version__ and doc["status"] == "repaired"
    assert doc["input"] == {"path": str(CODEX_S2), "sha256": sha(CODEX_S2)}
    assert doc["output"] == {"path": str(out), "sha256": sha(out)}
    assert doc["against"]["sha256"] == sha(S2_SOURCE)
    (repaired,) = doc["repaired"]
    assert repaired["repair"] == "anchor-replies"
    assert repaired["finding"]["code"] == "CMT005"
    assert [c["element"] for c in repaired["changes"]] == [
        "w:commentRangeStart", "w:commentRangeEnd", "w:r"]
    for c in repaired["changes"]:
        assert c["part"] == "word/document.xml" and c["old"] is None
        assert c["where"].startswith("/w:document/w:body/")
    assert all({"code", "severity", "message", "origin", "reason"} <= set(n)
               for n in doc["not_repaired"])
    v = doc["verification"]
    assert v["passed"] and v["failures"] == [] and v["against_added"] == []
    assert [f["code"] for f in v["check"]["removed"]] == ["CMT005"]
    assert v["check"]["added"] == []
    assert v["zip"]["changed"] == ["word/document.xml"]


def test_cli_exit_codes(tmp_path):
    assert run_cli("fix", str(BASE), "-o", str(tmp_path / "a.docx")).returncode == EXIT_NOTHING
    assert run_cli("fix", str(TOP_LEVEL_ORPHAN), "-o",
                   str(tmp_path / "b.docx")).returncode == EXIT_NOTHING
    r = run_cli("fix", str(ADEU_S1), "-o", str(tmp_path / "c.docx"))
    assert r.returncode == EXIT_REPAIRED and "renumber-revisions" in r.stdout
    assert run_cli("fix", str(ADEU_S1), "-o", str(ADEU_S1)).returncode == EXIT_REFUSED
    r = run_cli("fix", "missing.docx", "-o", str(tmp_path / "d.docx"))
    assert r.returncode == EXIT_REFUSED and "not found" in r.stderr
    junk = tmp_path / "junk.docx"
    junk.write_bytes(b"junk")
    r = run_cli("fix", str(junk), "-o", str(tmp_path / "e.docx"), "--json")
    assert r.returncode == EXIT_REFUSED
    assert json.loads(r.stdout)["status"] == "input-refused"
    assert not (tmp_path / "e.docx").exists()
