"""Each run property inherits independently through the supported style chain."""
from __future__ import annotations

from copy import deepcopy
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
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
