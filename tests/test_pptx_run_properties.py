"""Each run property inherits independently through the supported style chain."""
from __future__ import annotations

import json
from copy import deepcopy
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from conftest import run_cli
from lxml import etree

from ooxml_integrity.pptx_layout import A, P, read_deck


PRES = "ppt/presentation.xml"
SLIDE = "ppt/slides/slide2.xml"
LAYOUT = "ppt/slideLayouts/layout-b.xml"
MASTER = "ppt/slideMasters/master-b.xml"
INHERITED = ("paragraph", "list", "layout", "master-placeholder",
             "master-style", "presentation")


def a(tag):
    return f"{{{A}}}{tag}"


def p(tag):
    return f"{{{P}}}{tag}"


def properties(element, values):
    for key, value in values.items():
        if key == "family":
            etree.SubElement(element, a("latin"), typeface=value)
        else:
            element.set(key, str(value))


def level_properties(style, values, level):
    style[:] = []
    paragraph = etree.SubElement(style, a(f"lvl{level + 1}pPr"))
    properties(etree.SubElement(paragraph, a("defRPr")), values)


def make_deck(root, tmp_path, sources, *, level=0, placeholder=True):
    # Retain a real package's relationship/theme graph, but replace its selected
    # slide's text and defaults with controlled XML. No Office rendering claim.
    with ZipFile(root / "corpus/pptx-master-themes.pptx") as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    trees = {name: etree.fromstring(parts[name]) for name in (PRES, SLIDE, LAYOUT, MASTER)}
    pres, slide, layout, master = (trees[name] for name in (PRES, SLIDE, LAYOUT, MASTER))
    ids = pres.find(p("sldIdLst"))
    ids[:] = [ids[1]]

    slide_shapes = slide.find(f'{p("cSld")}/{p("spTree")}')
    body = slide_shapes.findall(p("sp"))[1]
    for shape in list(slide_shapes.findall(p("sp"))):
        if shape is not body:
            slide_shapes.remove(shape)
    nv = body.find(f'{p("nvSpPr")}/{p("nvPr")}')
    nv[:] = []
    if placeholder:
        etree.SubElement(nv, p("ph"), idx="42", type="body")
    tx = body.find(p("txBody"))
    for paragraph in list(tx.findall(a("p"))):
        tx.remove(paragraph)
    paragraph = etree.SubElement(tx, a("p"))
    ppr = etree.SubElement(paragraph, a("pPr"), lvl=str(level))
    properties(etree.SubElement(ppr, a("defRPr")), sources.get("paragraph", {}))
    run = etree.SubElement(paragraph, a("r"))
    properties(etree.SubElement(run, a("rPr")), sources.get("run", {}))
    etree.SubElement(run, a("t")).text = "ABCD"
    level_properties(tx.find(a("lstStyle")), sources.get("list", {}), level)

    for owner, source in ((layout, "layout"), (master, "master-placeholder")):
        shapes = owner.find(f'{p("cSld")}/{p("spTree")}')
        for shape in list(shapes.findall(p("sp"))):
            shapes.remove(shape)
        inherited = deepcopy(body)
        shapes.append(inherited)
        level_properties(inherited.find(f'{p("txBody")}/{a("lstStyle")}'),
                         sources.get(source, {}), level)
    level_properties(master.find(f'{p("txStyles")}/{p("bodyStyle")}'),
                     sources.get("master-style", {}), level)
    level_properties(pres.find(p("defaultTextStyle")), sources.get("presentation", {}), level)
    parts.update({name: etree.tostring(tree) for name, tree in trees.items()})
    path = tmp_path / "run-properties.pptx"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return path


def resolved(path):
    deck = read_deck(path)
    assert len(deck.shapes) == 1
    run = deck.shapes[0].paragraphs[0].runs[0]
    return run.size_pt, run.font, run.bold, run.italic


@pytest.mark.parametrize("left_pt,right_pt,expected_right_pt,exit_code", [
    (16, 32, 32, 1), (32, 16, 16, 0), (16, None, 32, 1), (16, 16, 16, 0),
], ids=["missed-overflow", "false-overflow", "inherit-from-master", "both-fit"])
def test_two_content_uses_each_columns_own_font_size(tmp_path, left_pt, right_pt,
                                                     expected_right_pt, exit_code):
    from pptx import Presentation
    from pptx.util import Pt

    prs = Presentation()
    layout = prs.slide_layouts.get_by_name("Two Content")
    left, right = (layout.placeholders.get(idx=i) for i in (1, 2))
    left_style = left.element.xpath("p:txBody/a:lstStyle")[0]
    right_style = right.element.xpath("p:txBody/a:lstStyle")[0]
    level_properties(left_style, {"sz": left_pt * 100}, 0)
    level_properties(right_style, {"sz": right_pt * 100} if right_pt is not None else {}, 0)
    # The master date placeholder shares idx 2 with the right column.
    # Only the master's body style should supply the missing column size.
    date = layout.slide_master.element.xpath('.//p:sp[p:nvSpPr/p:nvPr/p:ph[@type="dt" and @idx="2"]]')[0]
    level_properties(date.find(f'{p("txBody")}/{a("lstStyle")}'), {"sz": 1200}, 0)
    master = layout.slide_master.element.xpath("p:txStyles/p:bodyStyle")[0]
    level_properties(master, {"sz": 3200}, 0)
    right.height = Pt(35)

    slide = prs.slides.add_slide(layout)
    if right_pt is None:
        # Explicit obj and the template's implicit object type both use the master's body style.
        slide.placeholders[2].element.xpath("p:nvSpPr/p:nvPr/p:ph")[0].set("type", "obj")
    for column in (slide.placeholders[1], slide.placeholders[2]):
        column.text = "Review"
        column.text_frame.paragraphs[0].runs[0].font.name = "Arial"
    path = tmp_path / "two-content.pptx"
    prs.save(path)

    result = run_cli("check", str(path), "--no-config", "--json")
    assert result.returncode == exit_code, result.stdout + result.stderr
    findings = json.loads(result.stdout)["files"][0]["findings"]
    expected = [("PPT001", "error", f"slide1/{slide.placeholders[2].name}")] if exit_code else []
    assert [(f["code"], f["severity"], f["where"]) for f in findings if f["severity"] != "info"] == expected
    sizes = {shape.name: shape.paragraphs[0].runs[0].size_pt
             for shape in read_deck(path).shapes if shape.has_text}
    assert sizes == {slide.placeholders[1].name: left_pt, slide.placeholders[2].name: expected_right_pt}


@pytest.mark.parametrize("source", INHERITED)
@pytest.mark.parametrize("level", [0, 2])
def test_explicit_size_and_family_do_not_stop_bold_italic_inheritance(
        root, tmp_path, source, level):
    path = make_deck(root, tmp_path, {
        "run": {"sz": "1800", "family": "Arial"},
        source: {"sz": "4000", "family": "Courier New", "b": "1", "i": "true"},
    }, level=level)
    assert resolved(path) == (18, "Arial", True, True)


@pytest.mark.parametrize("source", ("run", *INHERITED[:-1]))
@pytest.mark.parametrize("attribute,expected", [("b", (False, True)), ("i", (True, False))])
def test_explicit_false_wins_while_the_other_property_keeps_inheriting(
        root, tmp_path, source, attribute, expected):
    sources = {
        "run": {"sz": "1800", "family": "Arial"},
        "presentation": {"b": "1", "i": "1"},
    }
    sources.setdefault(source, {})[attribute] = "0" if attribute == "b" else "false"
    assert resolved(make_deck(root, tmp_path, sources)) == (18, "Arial", *expected)


def test_all_four_properties_can_come_from_different_levels(root, tmp_path):
    path = make_deck(root, tmp_path, {
        "run": {"sz": "1800"},
        "paragraph": {"family": "Arial"},
        "list": {"b": "1"},
        "layout": {"i": "1"},
        "presentation": {"sz": "4000", "family": "Courier New", "b": "0", "i": "0"},
    })
    assert resolved(path) == (18, "Arial", True, True)


def test_early_bold_and_italic_do_not_stop_size_or_theme_family_inheritance(root, tmp_path):
    path = make_deck(root, tmp_path, {
        "run": {"b": "0", "i": "1"},
        "paragraph": {"sz": "2400"},
        "list": {"family": "+mj-lt"},
        "presentation": {"b": "1", "i": "0"},
    })
    assert resolved(path) == (24, "Times New Roman", False, True)


@pytest.mark.parametrize("explicit", [False, True])
def test_unset_style_flags_default_to_false_only_after_the_chain(root, tmp_path, explicit):
    sources = {"run": {"sz": "1800", "family": "Arial"}} if explicit else {}
    assert resolved(make_deck(root, tmp_path, sources)) == (
        18, "Arial" if explicit else "Courier New", False, False,
    )


def test_explicit_regular_face_overrides_lower_bold_italic(root, tmp_path):
    path = make_deck(root, tmp_path, {
        "run": {"sz": "1800", "family": "Arial", "b": "0", "i": "0"},
        "list": {"b": "1", "i": "1"},
    })
    assert resolved(path) == (18, "Arial", False, False)


def test_nonplaceholder_inherits_presentation_flags_without_layout_defaults(root, tmp_path):
    path = make_deck(root, tmp_path, {
        "run": {"sz": "1800", "family": "Arial"},
        "layout": {"b": "0", "i": "0"},
        "master-style": {"b": "0", "i": "0"},
        "presentation": {"b": "1", "i": "1"},
    }, placeholder=False)
    assert resolved(path) == (18, "Arial", True, True)
