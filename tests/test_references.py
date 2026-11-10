"""Bookmarks and fields against a source: FID015, FID016, and the two
constructs counted with them, section breaks and endnote references.

Each document is the reference document with a cross-reference put in by
hand: a bookmark around the fee, a REF field pointing at it, a PAGE field in
the footer.
"""
from __future__ import annotations

import pytest
from lxml import etree

from conftest import read_part, repack

from ooxml_integrity import ERROR, INFO, WARN, compare
from ooxml_integrity.introduced import split
from ooxml_integrity.policy import fingerprint
from ooxml_integrity.references import References, assess, instructions, read_fields

DOC = "word/document.xml"
FOOTER = "word/footer1.xml"
NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % NS
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _xml(fragment: str):
    return etree.fromstring(f'<w:root xmlns:w="{NS}">{fragment}</w:root>')


def _complex(instruction: str, result: str = "x", *, deleted: bool = False) -> str:
    tag = "delInstrText" if deleted else "instrText"
    return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r><w:{tag} xml:space="preserve">{instruction}</w:{tag}></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            f'<w:r><w:t>{result}</w:t></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>')


def _simple(instruction: str, result: str = "x") -> str:
    return f'<w:fldSimple w:instr="{instruction}"><w:r><w:t>{result}</w:t></w:r></w:fldSimple>'


def _bookmark(name: str, inner: str = "<w:r><w:t>4.2</w:t></w:r>", ident: str = "90") -> str:
    return (f'<w:bookmarkStart w:id="{ident}" w:name="{name}"/>{inner}'
            f'<w:bookmarkEnd w:id="{ident}"/>')


def _paragraph(inner: str) -> str:
    return f'<w:p xmlns:w="{NS}">{inner}</w:p>'


def _with_body(source, target, *paragraphs: str, footer: str | None = None):
    """The reference document with paragraphs added before its section break."""
    tree = etree.fromstring(read_part(source, DOC).encode("utf-8"))
    body = tree.find(W + "body")
    last = body.find(W + "sectPr")
    for paragraph in paragraphs:
        last.addprevious(etree.fromstring(paragraph))
    edits = {DOC: etree.tostring(tree, xml_declaration=True, encoding="UTF-8",
                                 standalone=True)}
    if footer is not None:
        edits[FOOTER] = (f'<w:ftr xmlns:w="{NS}"><w:p>{footer}</w:p></w:ftr>'
                         ).encode("utf-8")
    return repack(source, target, edits)


def _found(source, edited, *codes):
    return [f for f in compare(source, edited) if f.code in codes]


@pytest.fixture
def source(base_docx, tmp_path):
    """A clause number in a bookmark, a REF field to it, PAGE in the footer."""
    return _with_body(
        base_docx, tmp_path / "source.docx",
        _paragraph(_bookmark("_Ref100") + "<w:r><w:t> Fees</w:t></w:r>"),
        _paragraph("<w:r><w:t>See clause </w:t></w:r>" + _complex(r" REF _Ref100 \r \h ", "4.2")),
        footer="<w:r><w:t>Page </w:t></w:r>" + _complex(" PAGE ", "1"),
    )


# ------------------------------------------------------------ what is read
def test_simple_and_complex_forms_are_the_same_field():
    simple = instructions(_xml(_simple(r"REF _Ref1 \h")))
    complex_ = instructions(_xml(_complex(r"  REF   _Ref1 \h ")))
    assert simple == complex_ == [("REF", r"REF _Ref1 \h")]


def test_an_instruction_split_over_runs_is_one_instruction():
    root = _xml('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
                '<w:r><w:instrText> PAGE</w:instrText></w:r>'
                '<w:r><w:instrText>REF _Toc1 \\h </w:instrText></w:r>'
                '<w:r><w:fldChar w:fldCharType="end"/></w:r>')
    assert instructions(root) == [("PAGEREF", r"PAGEREF _Toc1 \h")]


def test_nested_fields_are_each_read():
    # PAGEREF inside the result of TOC; MERGEFIELD inside the instruction of IF
    toc = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
           '<w:r><w:instrText>TOC \\o "1-3"</w:instrText></w:r>'
           '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
           + _complex(r"PAGEREF _Toc1 \h", "3")
           + '<w:r><w:fldChar w:fldCharType="end"/></w:r>')
    assert sorted(kind for kind, _ in instructions(_xml(toc))) == ["PAGEREF", "TOC"]
    nested = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
              '<w:r><w:instrText>IF </w:instrText></w:r>'
              + _complex("MERGEFIELD Total", "5")
              + '<w:r><w:instrText> &gt; 0 "yes"</w:instrText></w:r>'
              '<w:r><w:fldChar w:fldCharType="end"/></w:r>')
    assert sorted(kind for kind, _ in instructions(_xml(nested))) == ["IF", "MERGEFIELD"]


def test_a_field_inside_another_fields_result_is_derived():
    # each entry of a table of contents: text and a PAGEREF, written by TOC
    toc = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
           '<w:r><w:instrText>TOC \\o "1-3"</w:instrText></w:r>'
           '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
           + _complex(r"PAGEREF _Toc1 \h", "3") + _simple(r"PAGEREF _Toc2 \h", "4")
           + '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
           + _complex(r"PAGEREF _Toc1 \h", "3"))
    assert [(kind, derived) for kind, _, derived in read_fields(_xml(toc))] == [
        ("TOC", False), ("PAGEREF", True), ("PAGEREF", True), ("PAGEREF", False)]
    nested = f'<w:fldSimple w:instr="SEQ Table">{_complex("PAGE")}</w:fldSimple>'
    assert [(kind, derived) for kind, _, derived in read_fields(_xml(nested))] == [
        ("SEQ", False), ("PAGE", True)]


def test_a_field_inside_an_instruction_is_not_derived():
    nested = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
              '<w:r><w:instrText>IF </w:instrText></w:r>'
              + _complex("MERGEFIELD Total", "5")
              + '<w:r><w:instrText> &gt; 0 "yes"</w:instrText></w:r>'
              '<w:r><w:fldChar w:fldCharType="end"/></w:r>')
    assert [(kind, derived) for kind, _, derived in read_fields(_xml(nested))] == [
        ("IF", False), ("MERGEFIELD", False)]


def test_a_field_with_no_end_is_still_read():
    root = _xml('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
                '<w:r><w:instrText>PAGE</w:instrText></w:r>')
    assert instructions(root) == [("PAGE", "PAGE")]


def test_a_table_of_contents_written_back_without_its_entries_fields_is_not_a_loss():
    # what LibreOffice writes: the TOC field, its entries as plain text
    entries = _complex(r"PAGEREF _Toc1 \h", "3") * 3
    def toc(result):
        return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
                '<w:r><w:instrText>TOC \\o "1-3"</w:instrText></w:r>'
                '<w:r><w:fldChar w:fldCharType="separate"/></w:r>' + result
                + '<w:r><w:fldChar w:fldCharType="end"/></w:r>')
    before = _references(_bookmark("_Toc1") + toc(entries))
    after = _references(_bookmark("_Toc1") + toc("<w:r><w:t>Fees 3</w:t></w:r>"))
    assert assess(before, after) == []
    # the entries still count as pointing at the heading's bookmark
    [f] = assess(before, _references(toc(entries)))
    assert (f.code, f.severity, f.extra["referenced"]) == ("FID015", ERROR, "fields")


def test_a_formula_field_has_the_kind_equals():
    assert instructions(_xml(_simple("=SUM(ABOVE)"))) == [("=", "=SUM(ABOVE)")]


def test_a_field_in_a_tracked_deletion_is_still_there():
    assert instructions(_xml(_complex("PAGE", deleted=True))) == [("PAGE", "PAGE")]


def test_a_text_box_is_read_once():
    # Word writes a text box in mc:Choice and again in mc:Fallback
    mc = "http://schemas.openxmlformats.org/markup-compatibility/2006"
    inner = _bookmark("Box1") + _complex("PAGE")
    both = _references(f'<mc:AlternateContent xmlns:mc="{mc}"><mc:Choice Requires="wps">'
                       f"{inner}</mc:Choice><mc:Fallback>{inner}</mc:Fallback>"
                       "</mc:AlternateContent>")
    first_only = _references(f'<mc:AlternateContent xmlns:mc="{mc}">'
                             f'<mc:Choice Requires="wps">{inner}</mc:Choice>'
                             "</mc:AlternateContent>")
    assert both.fields == first_only.fields and sum(both.fields["document"].values()) == 1
    assert assess(both, first_only) == [] and assess(first_only, both) == []
    assert [f.code for f in assess(both, _references(""))] == ["FID015", "FID016"]


def _references(fragment: str, story: str = "document") -> References:
    out = References()
    out.read(story, _xml(fragment))
    return out


# ------------------------------------------------------------- matching
def test_switches_are_not_compared():
    # what LibreOffice writes back for these instructions
    before = _references(_complex(r'TOC \o "1-3" \h \z \u') + _complex(r"PAGE \* Arabic")
                         + _complex(r"REF _Ref1 \r \h"))
    after = _references(_complex(r'TOC \z \o "1-3" \u \h') + _complex(r"PAGE \* ARABIC")
                        + _complex(r"REF _Ref1 \r \r \h"))
    assert assess(before, after) == []


def test_a_field_pointed_at_another_bookmark_is_reported():
    before = _references(_complex(r"REF _Ref1 \h") + _complex(r"REF _Ref2 \h"))
    after = _references(_complex(r"REF _Ref1 \h") + _complex(r"REF _Ref9 \h"))
    [f] = assess(before, after)
    assert (f.code, f.severity) == ("FID016", ERROR)
    assert f.extra["targets"] == ["_Ref2"] and f.extra["after"] == 2


def test_bookmark_names_ignore_case_and_ids():
    before = _references(_bookmark("Clause4", ident="1"))
    after = _references(_bookmark("CLAUSE4", ident="77"))
    assert assess(before, after) == []


@pytest.mark.parametrize("name", ["_GoBack", "_Hlk158039523", "_Toc376250471"])
def test_a_hidden_bookmark_nothing_points_at_is_not_reported(name):
    assert assess(_references(_bookmark(name)), _references("")) == []


def test_a_visible_bookmark_nothing_points_at_is_a_warning():
    [f] = assess(_references(_bookmark("Schedule1")), _references(""))
    assert (f.code, f.severity, f.extra["referenced"]) == ("FID015", WARN, "nothing")
    assert f.extra["names"] == ["Schedule1"]


@pytest.mark.parametrize("pointer", [
    _complex(r"REF _Toc1 \h"),
    _complex(r"PAGEREF _toc1 \h"),
    _complex(r'NOTEREF "_Toc1"'),
])
def test_a_bookmark_a_field_still_points_at_is_an_error(pointer):
    before = _references(_bookmark("_Toc1") + pointer)
    after = _references(pointer)
    [f] = [f for f in assess(before, after) if f.code == "FID015"]
    assert (f.severity, f.extra["referenced"], f.extra["references"]) == (ERROR, "fields", 1)
    assert "Error! Bookmark not defined." in f.message


@pytest.mark.parametrize("pointer", [
    _complex(r'HYPERLINK \l "_Toc1"'),
    '<w:hyperlink w:anchor="_Toc1"><w:r><w:t>4.2</w:t></w:r></w:hyperlink>',
])
def test_a_bookmark_only_a_link_points_at_is_a_warning(pointer):
    before = _references(_bookmark("_Toc1") + pointer)
    after = _references(pointer)
    [f] = [f for f in assess(before, after) if f.code == "FID015"]
    assert (f.severity, f.extra["referenced"], f.extra["references"]) == (WARN, "links", 1)
    assert "no longer leads anywhere" in f.message


def test_a_reference_that_dangled_in_the_source_is_not_blamed_on_the_edit():
    dangling = _complex(r"REF _Ref404 \h")
    assert assess(_references(dangling), _references(dangling)) == []


def test_a_hyperlink_field_that_became_an_element_is_not_lost():
    before = _references(_complex('HYPERLINK "https://example.com"', "site"))
    after = _references('<w:hyperlink><w:r><w:t>site</w:t></w:r></w:hyperlink>')
    assert assess(before, after) == []
    assert [f.code for f in assess(before, _references(""))] == ["FID016"]


def test_fields_are_compared_story_by_story():
    before = _references(_complex("PAGE"), "footer/default")
    after = _references(_complex("PAGE"), "document")
    [f] = assess(before, after)
    assert (f.code, f.severity, f.where) == ("FID016", ERROR, "footer/default")


def test_a_lost_cross_reference_is_an_error_while_others_remain():
    refs = _complex(r"REF _Ref1 \h") + _complex(r"REF _Ref2 \h")
    [f] = assess(_references(refs), _references(_complex(r"REF _Ref1 \h")))
    assert (f.code, f.severity, f.extra["after"]) == ("FID016", ERROR, 1)


def test_losing_every_field_of_a_kind_is_an_error_and_some_a_warning():
    three = _complex("SEQ Figure") * 3
    [some] = assess(_references(three), _references(_complex("SEQ Figure")))
    assert (some.severity, some.extra["lost"], some.extra["after"]) == (WARN, 2, 1)
    [every] = assess(_references(three), _references(""))
    assert (every.severity, every.extra["lost"], every.extra["after"]) == (ERROR, 3, 0)


# -------------------------------------------------------- whole documents
def test_an_unchanged_copy_reports_nothing(source, tmp_path):
    copy = repack(source, tmp_path / "copy.docx", {})
    assert _found(source, copy, "FID001", "FID015", "FID016") == []


def test_a_rebuilt_paragraph_loses_its_field(source, tmp_path):
    # what `paragraph.text = ...` leaves: the last result as plain text
    tree = etree.fromstring(read_part(source, DOC).encode("utf-8"))
    paragraph = next(p for p in tree.iter(W + "p")
                     if "REF _Ref100" in "".join(p.itertext()))
    for child in list(paragraph):
        paragraph.remove(child)
    etree.SubElement(etree.SubElement(paragraph, W + "r"), W + "t").text = "See clause 4.2"
    edited = repack(source, tmp_path / "edited.docx", {DOC: etree.tostring(tree)})

    [f] = _found(source, edited, "FID015", "FID016")
    assert (f.code, f.severity, f.where) == ("FID016", ERROR, "document")
    assert (f.extra["kind"], f.extra["targets"]) == ("REF", ["_Ref100"])


def test_a_rebuilt_heading_leaves_the_reference_dangling(source, tmp_path):
    tree = etree.fromstring(read_part(source, DOC).encode("utf-8"))
    for tag in ("bookmarkStart", "bookmarkEnd"):
        for node in list(tree.iter(W + tag)):
            node.getparent().remove(node)
    edited = repack(source, tmp_path / "edited.docx", {DOC: etree.tostring(tree)})

    [f] = _found(source, edited, "FID015", "FID016")
    assert (f.code, f.severity) == ("FID015", ERROR)
    assert f.extra["names"] == ["_Ref100"] and f.extra["references"] == 1
    assert "Error! Reference source not found." in f.message


def test_a_footer_that_lost_its_page_field_is_reported(source, tmp_path):
    footer = f'<w:ftr xmlns:w="{NS}"><w:p><w:r><w:t>Page 1</w:t></w:r></w:p></w:ftr>'
    edited = repack(source, tmp_path / "edited.docx", {FOOTER: footer.encode()})

    [f] = _found(source, edited, "FID016")
    assert (f.severity, f.where, f.extra["kind"]) == (ERROR, "footer/default", "PAGE")


# ------------------------------------------- section breaks, endnote references
def _body_with(base_docx, target, inner: str):
    return _with_body(base_docx, target, _paragraph(inner))


def test_a_lost_section_break_is_a_warning_and_an_added_one_info(base_docx, tmp_path):
    two = _body_with(base_docx, tmp_path / "two.docx",
                     "<w:pPr><w:sectPr/></w:pPr><w:r><w:t>Part one</w:t></w:r>")
    [lost] = [f for f in compare(two, base_docx)
              if f.code == "FID001" and f.extra["tag"] == "sectPr"]
    assert (lost.severity, lost.extra["before"], lost.extra["after"]) == (WARN, 2, 1)
    [added] = [f for f in compare(base_docx, two)
               if f.code == "FID002" and f.extra["tag"] == "sectPr"]
    assert added.severity == INFO


def test_the_record_of_a_tracked_section_change_is_not_a_section_break(
        base_docx, tmp_path):
    def with_section(properties: str, name: str):
        tree = etree.fromstring(read_part(base_docx, DOC).encode("utf-8"))
        section = tree.find(W + "body").find(W + "sectPr")
        section.append(etree.fromstring(properties))
        return repack(base_docx, tmp_path / name, {DOC: etree.tostring(tree)})

    pending = with_section(
        f'<w:sectPrChange xmlns:w="{NS}" w:id="900" w:author="A" '
        'w:date="2026-01-01T00:00:00Z"><w:sectPr/></w:sectPrChange>', "pending.docx")
    # accepting the change removes the record and no section break
    assert [f for f in compare(pending, base_docx)
            if f.code == "FID001" and f.extra["tag"] == "sectPr"] == []


def test_a_lost_endnote_reference_is_an_error(base_docx, tmp_path):
    noted = _body_with(base_docx, tmp_path / "noted.docx",
                       '<w:r><w:t>Text</w:t></w:r><w:r><w:endnoteReference w:id="5"/></w:r>')
    [f] = [f for f in compare(noted, base_docx)
           if f.code == "FID001" and f.extra["tag"] == "endnoteReference"]
    assert f.severity == ERROR


# ------------------------------------------------------ policy and --introduced
def test_another_lost_bookmark_or_field_is_another_baseline_entry(source):
    a, b = (assess(_references(_bookmark(name)), _references(""))[0]
            for name in ("Schedule1", "Schedule2"))
    assert fingerprint("x.docx", a) != fingerprint("x.docx", b)
    one, two = (assess(_references(_complex("SEQ Figure") * n), _references(""))[0]
                for n in (1, 2))
    assert fingerprint("x.docx", one) != fingerprint("x.docx", two)
    assert "Schedule1" not in fingerprint("x.docx", a)


def test_lost_references_are_never_set_aside_as_inherited():
    found = assess(_references(_bookmark("Schedule1") + _complex("PAGE")), _references(""))
    assert {f.code for f in found} == {"FID015", "FID016"}
    assert split(found, found) == (found, [])


def test_two_slots_showing_one_footer_hold_the_fields_of_two(base_docx, tmp_path):
    """Two sections with identical footer parts, then both showing one part."""
    footer = (f'<w:ftr xmlns:w="{NS}" xmlns:r="{R}"><w:p>'
              + _complex("PAGE", "1") + "</w:p></w:ftr>").encode()
    rels_name = "word/_rels/document.xml.rels"

    def build(name, second_target):
        tree = etree.fromstring(read_part(base_docx, DOC).encode("utf-8"))
        body = tree.find(W + "body")
        last = body.find(W + "sectPr")
        for ref in list(last.iter(W + "footerReference")):
            last.remove(ref)
        rels = etree.fromstring(read_part(base_docx, rels_name).encode("utf-8"))
        footer_type = ("http://schemas.openxmlformats.org/officeDocument/2006/"
                       "relationships/footer")
        for rid, target in (("rIdFooterA", "footerA.xml"), ("rIdFooterB", second_target)):
            etree.SubElement(rels, f"{{{PKG_REL}}}Relationship",
                             Id=rid, Type=footer_type, Target=target)
        first = etree.fromstring(
            f'<w:p xmlns:w="{NS}" xmlns:r="{R}"><w:pPr><w:sectPr>'
            '<w:footerReference w:type="default" r:id="rIdFooterA"/>'
            "</w:sectPr></w:pPr></w:p>")
        last.addprevious(first)
        last.insert(0, etree.fromstring(
            f'<w:footerReference xmlns:w="{NS}" xmlns:r="{R}" w:type="default" '
            'r:id="rIdFooterB"/>'))
        types = read_part(base_docx, "[Content_Types].xml").replace(
            "</Types>",
            '<Override PartName="/word/footerA.xml" ContentType="application/vnd.'
            'openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
            '<Override PartName="/word/footerB.xml" ContentType="application/vnd.'
            'openxmlformats-officedocument.wordprocessingml.footer+xml"/></Types>')
        edits = {DOC: etree.tostring(tree), rels_name: etree.tostring(rels),
                 "[Content_Types].xml": types.encode(), "word/footerA.xml": footer}
        if second_target == "footerB.xml":
            edits["word/footerB.xml"] = footer
        return repack(base_docx, tmp_path / name, edits)

    two_parts = build("two-parts.docx", "footerB.xml")
    one_part = build("one-part.docx", "footerA.xml")
    assert _found(two_parts, one_part, "FID016") == []
    assert _found(one_part, two_parts, "FID016") == []
