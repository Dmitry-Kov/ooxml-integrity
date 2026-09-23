"""Spec-valid constructs from real producers must not raise structural errors.

Each case was first seen in public test documents (LibreOffice's
sw/qa/extras/ooxmlexport corpus, Word 2007 files, docx4j's samples) and is
rebuilt here from corpus/base.docx. Every case keeps a negative control, so the
rule still fires on a genuine defect.
"""
from __future__ import annotations

import re
import zipfile

import pytest
from lxml import etree

from conftest import read_part, repack

from ooxml_integrity import check, compare, coverage_for


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % W_NS
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
DOC = "word/document.xml"
FOOTNOTES = "word/footnotes.xml"
NUMBERING = "word/numbering.xml"
CT = "[Content_Types].xml"


def _codes(path):
    return [f.code for f in check(path)]


# ------------------------------------------------------------ separator notes

def _libreoffice_footnote_ids(source, target, *, drop_reference=None):
    """Renumber notes the way LibreOffice and Word 2007 do: separators 0/1."""
    notes = etree.fromstring(read_part(source, FOOTNOTES).encode())
    document = read_part(source, DOC)
    mapping = {}
    for note in notes.findall(W + "footnote"):
        old = note.get(W + "id")
        kind = note.get(W + "type")
        new = {"separator": "0", "continuationSeparator": "1"}.get(
            kind, str(int(old) + 1))
        mapping[old] = new
        note.set(W + "id", new)
    document = re.sub(
        r'(<w:footnoteReference w:id=")(-?\d+)(")',
        lambda m: m.group(1) + mapping[m.group(2)] + m.group(3), document)
    if drop_reference is not None:
        document = document.replace(
            '<w:footnoteReference w:id="%s"/>' % drop_reference, "", 1)
    return repack(source, target, {
        FOOTNOTES: etree.tostring(notes, xml_declaration=True,
                                  encoding="UTF-8", standalone=True),
        DOC: document.encode(),
    })


def test_separator_notes_are_identified_by_type_not_id(base_docx, tmp_path):
    edited = _libreoffice_footnote_ids(base_docx, tmp_path / "lo-notes.docx")
    assert 'w:type="continuationSeparator" w:id="1"' in read_part(edited, FOOTNOTES)
    codes = _codes(edited)
    assert "FTN001" not in codes and "FTN002" not in codes


def test_orphaned_normal_note_is_still_reported_with_0_1_separators(
        base_docx, tmp_path):
    edited = _libreoffice_footnote_ids(
        base_docx, tmp_path / "lo-orphan.docx", drop_reference="2")
    findings = [f for f in check(edited) if f.code == "FTN002"]
    assert [f.message.split(" ")[1] for f in findings] == ["id=2"]


# ------------------------------------------------------------ numId="0"

def _with_num_id(source, target, value, *, drop_numbering=False):
    document = read_part(source, DOC)
    document, n = re.subn(r'<w:numId w:val="2"/>',
                          '<w:numId w:val="%s"/>' % value, document, count=1)
    assert n == 1, "the reference document changed"
    edits = {DOC: document.encode()}
    if not drop_numbering:
        return repack(source, target, edits)
    tmp = repack(source, target.with_suffix(".tmp.docx"), edits)
    with zipfile.ZipFile(tmp) as z:
        parts = {name: z.read(name) for name in z.namelist() if name != NUMBERING}
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return target


def test_num_id_zero_removes_numbering_and_is_not_a_dangling_reference(
        base_docx, tmp_path):
    codes = _codes(_with_num_id(base_docx, tmp_path / "num0.docx", "0"))
    assert not [c for c in codes if c.startswith("NUM")]


def test_num_id_zero_without_numbering_part_is_not_reported(base_docx, tmp_path):
    edited = _with_num_id(base_docx, tmp_path / "num0-nopart.docx", "0",
                          drop_numbering=True)
    num001 = [f.message for f in check(edited) if f.code == "NUM001"]
    # the other numbered paragraphs (numId=1/2) still lose their definitions
    assert num001 and not [m for m in num001 if "numId=0 " in m]


def test_undefined_nonzero_num_id_is_still_an_error(base_docx, tmp_path):
    codes = _codes(_with_num_id(base_docx, tmp_path / "num999.docx", "999"))
    assert "NUM002" in codes


# ------------------------------------------------------------ content types

def _override_only_content_types(source, target, *, uncovered=None):
    """Declare every part by Override, as older LibreOffice exports did."""
    with zipfile.ZipFile(source) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
    tree = etree.fromstring(read_part(source, CT).encode())
    overrides = {o.get("PartName") for o in tree.findall("{%s}Override" % CT_NS)}
    for default in tree.findall("{%s}Default" % CT_NS):
        if default.get("Extension") == "xml":
            tree.remove(default)
    for name in names:
        if name == CT or not name.endswith(".xml") or "/" + name in overrides:
            continue
        el = etree.SubElement(tree, "{%s}Override" % CT_NS)
        el.set("PartName", "/" + name)
        el.set("ContentType", "application/xml")
    edits = {CT: etree.tostring(tree, xml_declaration=True, encoding="UTF-8",
                                standalone=True)}
    if uncovered:
        edits[uncovered] = b"<x/>"
    return repack(source, target, edits)


def test_content_types_stream_is_not_a_part(base_docx, tmp_path):
    edited = _override_only_content_types(base_docx, tmp_path / "ct.docx")
    assert 'Extension="xml"' not in read_part(edited, CT)
    assert [f for f in check(edited) if f.code == "PKG005"] == []


def test_uncovered_part_is_still_reported(base_docx, tmp_path):
    edited = _override_only_content_types(
        base_docx, tmp_path / "ct-uncovered.docx", uncovered="word/extra.xml")
    flagged = [f.part for f in check(edited) if f.code == "PKG005"]
    assert flagged == ["word/extra.xml"]


# ------------------------------------------------------------ table rows

DELIVERY_ROW = re.compile(r"<w:tr>\s*(<w:tc>(?:(?!</w:tc>).)*Delivery.*?</w:tc>)"
                          r"(.*?)</w:tr>", re.S)


def _edit_delivery_row(source, target, edit):
    document = read_part(source, DOC)
    match = DELIVERY_ROW.search(document)
    assert match, "the reference document changed"
    first, rest = match.group(1), match.group(2)
    row = edit(first, rest)
    return repack(source, target, {
        DOC: (document[:match.start()] + row + document[match.end():]).encode()})


def _tbl002(path):
    return [f.message for f in check(path) if f.code == "TBL002"]


def test_grid_before_accounts_for_skipped_columns(base_docx, tmp_path):
    edited = _edit_delivery_row(
        base_docx, tmp_path / "grid-before.docx",
        lambda first, rest: '<w:tr><w:trPr><w:gridBefore w:val="1"/></w:trPr>'
                            + rest + "</w:tr>")
    assert _tbl002(edited) == []


def test_grid_after_accounts_for_skipped_columns(base_docx, tmp_path):
    def drop_last(first, rest):
        cells = re.findall(r"<w:tc>.*?</w:tc>", rest, re.S)
        return ('<w:tr><w:trPr><w:gridAfter w:val="1"/></w:trPr>' + first
                + cells[0] + "</w:tr>")
    edited = _edit_delivery_row(base_docx, tmp_path / "grid-after.docx", drop_last)
    assert _tbl002(edited) == []


def test_cells_inside_content_controls_are_counted(base_docx, tmp_path):
    edited = _edit_delivery_row(
        base_docx, tmp_path / "cell-sdt.docx",
        lambda first, rest: "<w:tr><w:sdt><w:sdtPr/><w:sdtContent>" + first
                            + "</w:sdtContent></w:sdt>" + rest + "</w:tr>")
    codes = _codes(edited)
    assert "TBL002" not in codes and "SDT001" not in codes


def test_missing_cell_without_grid_skip_is_still_reported(base_docx, tmp_path):
    edited = _edit_delivery_row(
        base_docx, tmp_path / "ragged.docx",
        lambda first, rest: "<w:tr>" + rest + "</w:tr>")
    assert _tbl002(edited) == [
        "table 1, row 3: 2 cells vs 3 tblGrid columns - Word will re-lay out the table"]


# ------------------------------------------------------------ list styles

LIST_STYLE_NUMBERING = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="%s">
<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="multilevel"/>
<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%%1."/></w:lvl>
<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%%1.%%2"/></w:lvl>
</w:abstractNum>
<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="multilevel"/>
<w:numStyleLink w:val="%s"/></w:abstractNum>
%s
<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
<w:num w:numId="2"><w:abstractNumId w:val="1"/>%s</w:num>
%s
</w:numbering>"""


def _numbering(tmp_path, name, *, link="BulletList", style_link=True,
               override="", extra_num="", styles=None, source=None):
    defining = ""
    if style_link:
        defining = ('<w:abstractNum w:abstractNumId="2"><w:multiLevelType '
                    'w:val="multilevel"/><w:styleLink w:val="BulletList"/>'
                    '<w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/>'
                    '<w:lvlText w:val="-"/></w:lvl></w:abstractNum>')
    elif extra_num:
        defining = ('<w:abstractNum w:abstractNumId="2"><w:multiLevelType '
                    'w:val="multilevel"/><w:lvl w:ilvl="0"><w:numFmt '
                    'w:val="bullet"/><w:lvlText w:val="-"/></w:lvl>'
                    '</w:abstractNum>')
    xml = LIST_STYLE_NUMBERING % (W_NS.encode(), link.encode(), defining.encode(),
                                  override.encode(), extra_num.encode())
    edits = {NUMBERING: xml}
    if styles is not None:
        edits["word/styles.xml"] = styles
    return repack(source, tmp_path / name, edits)


def _num004(path):
    return [f.message for f in check(path) if f.code.startswith("NUM")]


def test_num_style_link_uses_the_list_style_levels(base_docx, tmp_path):
    edited = _numbering(tmp_path, "style-link.docx", source=base_docx)
    assert _num004(edited) == []


def test_num_style_link_resolves_through_styles_part(base_docx, tmp_path):
    styles = read_part(base_docx, "word/styles.xml").replace(
        "</w:styles>",
        '<w:style w:type="numbering" w:styleId="BulletList"><w:name '
        'w:val="Bullet List"/><w:pPr><w:numPr><w:numId w:val="3"/></w:numPr>'
        "</w:pPr></w:style></w:styles>").encode()
    edited = _numbering(
        tmp_path, "style-numid.docx", style_link=False, styles=styles,
        extra_num='<w:num w:numId="3"><w:abstractNumId w:val="2"/></w:num>',
        source=base_docx)
    assert _num004(edited) == []


def test_level_defined_by_lvl_override_is_defined(base_docx, tmp_path):
    document = read_part(base_docx, DOC).replace(
        '<w:ilvl w:val="0"/><w:numId w:val="2"/>',
        '<w:ilvl w:val="3"/><w:numId w:val="2"/>', 1)
    source = repack(base_docx, tmp_path / "ilvl3.docx", {DOC: document.encode()})
    override = ('<w:lvlOverride w:ilvl="3"><w:lvl w:ilvl="3"><w:numFmt '
                'w:val="bullet"/><w:lvlText w:val="-"/></w:lvl></w:lvlOverride>')
    with_override = _numbering(tmp_path, "override.docx", override=override,
                               source=source)
    without = _numbering(tmp_path, "no-override.docx", source=source)
    assert _num004(with_override) == []
    assert _num004(without) == ["level ilvl=3 undefined in abstractNum 1"]


def test_unresolved_num_style_link_is_still_reported(base_docx, tmp_path):
    edited = _numbering(tmp_path, "dangling-link.docx", link="NoSuchStyle",
                        source=base_docx)
    assert _num004(edited) == ["level ilvl=0 undefined in abstractNum 1"] * 2


# ------------------------------------------------------------ relationship content types

def test_override_only_relationship_parts_are_a_warning(base_docx, tmp_path):
    with zipfile.ZipFile(base_docx) as z:
        rels = [n for n in z.namelist() if n.endswith(".rels")]
    ct = read_part(base_docx, CT)
    default = re.search(r'<Default Extension="rels"[^>]*/>', ct).group(0)
    overrides = "".join(
        '<Override PartName="/%s" ContentType="application/'
        'vnd.openxmlformats-package.relationships+xml"/>' % n for n in rels)
    edited = repack(base_docx, tmp_path / "rels-override.docx", {
        CT: ct.replace(default, overrides).encode()})
    findings = [f for f in check(edited) if f.code == "PKG004"]
    assert [f.severity.value for f in findings] == ["warn"]


def test_relationship_parts_without_content_type_are_an_error(base_docx, tmp_path):
    ct = read_part(base_docx, CT)
    default = re.search(r'<Default Extension="rels"[^>]*/>', ct).group(0)
    edited = repack(base_docx, tmp_path / "rels-uncovered.docx", {
        CT: ct.replace(default, "").encode()})
    findings = [f for f in check(edited) if f.code == "PKG004"]
    assert [f.severity.value for f in findings] == ["error"]
    assert "_rels/.rels" in findings[0].message


# ------------------------------------------------------------ reporting

def test_encrypted_documents_are_named_as_such(tmp_path):
    encrypted = tmp_path / "encrypted.docx"
    encrypted.write_bytes(bytes.fromhex("D0CF11E0A1B11AE1") + b"\0" * 1024)
    findings = check(encrypted)
    assert [f.code for f in findings] == ["PKG002"]
    assert "OLE compound file" in findings[0].message


def test_human_output_names_the_part_when_there_is_no_xpath():
    from ooxml_integrity import Finding, ERROR
    finding = Finding("FTN002", ERROR, "footnote id=3 is defined but never "
                      "referenced", part="word/footnotes.xml")
    assert str(finding).endswith("-> word/footnotes.xml")


# ------------------------------------------------------------ main part name

ROOT_RELS = "_rels/.rels"
OFFICE_DOCUMENT = ("http://schemas.openxmlformats.org/officeDocument/2006/"
                   "relationships/officeDocument")


def _once(text, old, new):
    assert text.count(old) == 1, "the reference document changed"
    return text.replace(old, new)


def _moved_main_part(source, target, name, *, root_target=None,
                     edit=lambda xml: xml, stale=None):
    """Name the main part as only the officeDocument relationship knows it.

    docx4j's Word Online sample uses word/document22.xml (targeted as
    /word/document22.xml), LibreOffice's tdf104713 test word/trial.xml.
    `stale` keeps an unrelated copy under the conventional name.
    """
    with zipfile.ZipFile(source) as z:
        parts = {n: z.read(n).decode() for n in z.namelist()
                 if not n.startswith("word/media/")}
        media = {n: z.read(n) for n in z.namelist() if n.startswith("word/media/")}
    document = parts.pop(DOC)
    rels = parts.pop("word/_rels/document.xml.rels")
    parts[name] = edit(document)
    parts["word/_rels/%s.rels" % name.rsplit("/", 1)[1]] = rels
    if stale is not None:
        parts[DOC] = stale(document)
        parts["word/_rels/document.xml.rels"] = rels
    parts[ROOT_RELS] = _once(parts[ROOT_RELS], 'Target="word/document.xml"',
                             'Target="%s"' % (root_target or name))
    parts[CT] = _once(parts[CT], 'PartName="/word/document.xml"',
                      'PartName="/%s"' % name)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in parts.items():
            z.writestr(n, data.encode())
        for n, data in media.items():
            z.writestr(n, data)
    return target


def _drop_comment_anchor(xml):
    return _once(xml, '<w:commentReference w:id="1"/>', "")


@pytest.mark.parametrize("name, root_target", [
    ("word/trial.xml", None),
    ("word/document22.xml", "/word/document22.xml"),
    ("word/body", None),          # the Override, not ".xml", gives the type
])
def test_main_part_is_found_through_the_office_document_relationship(
        base_docx, tmp_path, name, root_target):
    moved = _moved_main_part(base_docx, tmp_path / "moved.docx", name,
                             root_target=root_target)
    assert check(moved) == []
    # headers, footers and comments resolve through the moved part's relationships
    assert compare(base_docx, moved) == []
    coverage = {i.id: i.status.value for i in coverage_for(moved, []).items}
    assert coverage["docx.comments"] == coverage["docx.tables"] == "checked"


def test_findings_in_a_moved_main_part_are_reported_there(base_docx, tmp_path):
    moved = _moved_main_part(base_docx, tmp_path / "moved-orphan.docx",
                             "word/trial.xml", edit=_drop_comment_anchor)
    assert {f.code: f.part for f in check(moved)} == {
        "CMT003": "word/trial.xml", "CMT005": "word/comments.xml"}
    assert "FID001" in [f.code for f in compare(base_docx, moved)]


def test_an_unrelated_word_document_xml_is_not_the_main_part(base_docx, tmp_path):
    moved = _moved_main_part(base_docx, tmp_path / "stale.docx", "word/trial.xml",
                             stale=_drop_comment_anchor)
    assert check(moved) == []


def test_a_missing_main_part_is_not_replaced_by_the_conventional_name(
        base_docx, tmp_path):
    rels = _once(read_part(base_docx, ROOT_RELS), 'Target="word/document.xml"',
                 'Target="word/missing.xml"')
    out = repack(base_docx, tmp_path / "missing-main.docx",
                 {ROOT_RELS: rels.encode()})
    assert [f.message for f in check(out) if f.code == "PKG006"] == [
        "missing word/missing.xml"]
    tables = next(i for i in coverage_for(out, []).items if i.id == "docx.tables")
    assert tables.status.value == "skipped"
    assert tables.reason.startswith("word/missing.xml ")
    with pytest.raises(ValueError, match="word/missing.xml is missing"):
        compare(base_docx, out)


def test_a_main_part_that_is_not_a_word_document_is_an_error(root):
    findings = [f for f in check(root / "corpus" / "deck.pptx") if f.code == "PKG006"]
    assert [(f.severity.value, f.part) for f in findings] == [
        ("error", "ppt/presentation.xml")]


@pytest.mark.parametrize("second, ambiguous", [
    ("word/trial.xml", True),
    ("/word/document.xml", False),      # the same part, spelled absolutely
])
def test_office_document_relationships_to_two_parts_are_ambiguous(
        base_docx, tmp_path, second, ambiguous):
    rels = _once(read_part(base_docx, ROOT_RELS), "</Relationships>",
                 '<Relationship Id="rId9" Type="%s" Target="%s"/></Relationships>'
                 % (OFFICE_DOCUMENT, second))
    out = repack(base_docx, tmp_path / "two-entry-points.docx", {
        ROOT_RELS: rels.encode(), "word/trial.xml": read_part(base_docx, DOC).encode()})
    root = [f.message for f in check(out) if f.code == "REL001" and f.part == ROOT_RELS]
    assert root == ([
        "_rels/.rels has officeDocument relationships to 2 different parts - the "
        "main document is ambiguous"] if ambiguous else [])
