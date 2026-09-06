"""Main presentation order, including names that are not slideN.xml."""
from __future__ import annotations

import hashlib
import itertools
import json
from copy import deepcopy
from dataclasses import replace
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from lxml import etree

from conftest import run_cli
from ooxml_integrity import ERROR, check_pptx
from ooxml_integrity.coverage import CoverageStatus, pptx_coverage
from ooxml_integrity.policy import fingerprint
from ooxml_integrity.pptx_layout import P, R, read_deck
from ooxml_integrity.sarif import build as sarif

PRES = "ppt/presentation.xml"
RELS = "ppt/_rels/presentation.xml.rels"
FIRST = "ppt/slides/intro.xml"


@pytest.fixture
def fixture(root):
    return root / "corpus/pptx-slide-order.pptx"


@pytest.fixture
def parts(fixture):
    with ZipFile(fixture) as z:
        return {name: z.read(name) for name in z.namelist()}


def save(parts, tmp_path):
    path = tmp_path / "changed.pptx"
    with ZipFile(path, "w", ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return path


def order(parts):
    pres = etree.fromstring(parts[PRES])
    return pres, pres.find(f"{{{P}}}sldIdLst")


def first_rel(parts):
    _, ids = order(parts)
    rid = ids[0].get(f"{{{R}}}id")
    rels = etree.fromstring(parts[RELS])
    return rels, next(r for r in rels if r.get("Id") == rid)


def shape_order(path):
    return [(s.slide, s.name) for s in read_deck(path).shapes if s.name != "Label"]


def test_office_order_and_clean_controls_are_pinned(root, fixture):
    evidence = json.loads((root / "docs/calibration/slide-order/evidence.json").read_text())
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == evidence["fixture_sha256"]
    assert shape_order(fixture) == [(1, "FIT_first"), (2, "FIT_second"), (3, "OVER_third")]
    found = check_pptx(fixture)
    assert [(f.code, f.severity, f.where) for f in found] == [
        ("PPT003", ERROR, "slide3/OVER_third")]
    assert len(evidence["cases"]) == 3
    for case in evidence["cases"]:
        assert hashlib.sha256((root / case["render"]).read_bytes()).hexdigest() == case["render_sha256"]
        assert [(f.code, f.severity.name) for f in found if f.where.startswith(f"slide{case['slide']}/")] == [
            tuple(item) for item in case["expected_findings"]]
    item = next(i for i in pptx_coverage(fixture, found).items if i.id == "pptx.slide-order")
    assert item.status == CoverageStatus.CHECKED and item.count == 3


@pytest.mark.parametrize("permutation", list(itertools.permutations(range(3))))
def test_every_permutation_moves_findings_with_the_slide(parts, tmp_path, permutation):
    pres, ids = order(parts)
    original = list(ids)
    ids[:] = [original[i] for i in permutation]
    parts[PRES] = etree.tostring(pres)
    path = save(parts, tmp_path)
    names = ["FIT_first", "FIT_second", "OVER_third"]
    assert shape_order(path) == [(n, names[i]) for n, i in enumerate(permutation, 1)]
    found = check_pptx(path)
    assert [(f.code, f.where) for f in found] == [
        ("PPT003", f"slide{permutation.index(2) + 1}/OVER_third")]


def test_zip_relationship_and_numeric_id_order_do_not_reorder_slides(parts, tmp_path):
    pres, ids = order(parts)
    rels = etree.fromstring(parts[RELS])
    for entry, number, rid in zip(ids, [900, 300, 700], ["z", "a", "m"]):
        old = entry.get(f"{{{R}}}id")
        next(r for r in rels if r.get("Id") == old).set("Id", rid)
        entry.set("id", str(number))
        entry.set(f"{{{R}}}id", rid)
    rels[:] = list(reversed(rels))
    parts[PRES] = etree.tostring(pres)
    parts[RELS] = etree.tostring(rels)
    path = save(dict(reversed(list(parts.items()))), tmp_path)
    assert shape_order(path) == [(1, "FIT_first"), (2, "FIT_second"), (3, "OVER_third")]


def test_reordering_preserves_inherited_geometry_and_formatting(root, tmp_path):
    reference = root / "corpus/deck.pptx"
    original = read_deck(reference)
    with ZipFile(reference) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    pres, ids = order(parts)
    count = len(ids)
    ids[:] = list(reversed(ids))
    parts[PRES] = etree.tostring(pres)
    changed = read_deck(save(parts, tmp_path))
    expected = sorted((replace(s, slide=count + 1 - s.slide) for s in original.shapes),
                      key=lambda s: s.slide)
    assert changed.shapes == expected


def test_nonnumeric_defect_part_is_measured(parts, tmp_path):
    for name, content in list(parts.items()):
        if name.endswith((".xml", ".rels")):
            parts[name] = content.replace(b"slide10.xml", b"overflow.xml")
    parts["ppt/slides/overflow.xml"] = parts.pop("ppt/slides/slide10.xml")
    found = check_pptx(save(parts, tmp_path))
    assert [(f.code, f.where) for f in found] == [("PPT003", "slide3/OVER_third")]


@pytest.mark.parametrize("target", [
    "slides/intro.xml", "./slides/intro.xml", "slides/../slides/intro.xml",
    "/ppt/slides/intro.xml", "slides/%69ntro.xml",
])
def test_relative_absolute_and_encoded_targets(parts, tmp_path, target):
    rels, rel = first_rel(parts)
    rel.set("Target", target)
    parts[RELS] = etree.tostring(rels)
    assert shape_order(save(parts, tmp_path))[0] == (1, "FIT_first")


@pytest.mark.parametrize("stored", ["first slide.xml", "first%20slide.xml", "任意.xml"])
def test_part_names_need_no_numeric_suffix(parts, tmp_path, stored):
    rels, rel = first_rel(parts)
    rel.set("Target", "slides/" + stored.replace(" ", "%20"))
    parts[RELS] = etree.tostring(rels)
    parts["ppt/slides/" + stored] = parts.pop(FIRST)
    assert shape_order(save(parts, tmp_path))[0] == (1, "FIT_first")


def test_hidden_slide_keeps_its_editor_position(parts, tmp_path):
    slide = etree.fromstring(parts[FIRST])
    slide.set("show", "0")
    parts[FIRST] = etree.tostring(slide)
    path = save(parts, tmp_path)
    assert shape_order(path) == [(1, "FIT_first"), (2, "FIT_second"), (3, "OVER_third")]
    assert check_pptx(path)[0].where == "slide3/OVER_third"


def test_unlisted_defect_and_orphan_parts_do_not_create_findings(parts, tmp_path):
    pres, ids = order(parts)
    ids.remove(ids[2])
    parts[PRES] = etree.tostring(pres)
    parts["ppt/slides/slide999.xml"] = b"not XML and not listed"
    path = save(parts, tmp_path)
    assert shape_order(path) == [(1, "FIT_first"), (2, "FIT_second")]
    assert check_pptx(path) == []
    assert read_deck(path).features["slides"] == 2


@pytest.mark.parametrize("absent", [False, True])
def test_empty_main_list_does_not_fall_back_to_part_names(parts, tmp_path, absent):
    pres, ids = order(parts)
    if absent:
        pres.remove(ids)
    else:
        ids[:] = []
    parts[PRES] = etree.tostring(pres)
    path = save(parts, tmp_path)
    assert read_deck(path).shapes == []
    item = next(i for i in pptx_coverage(path, []).items if i.id == "pptx.slide-order")
    assert item.status == CoverageStatus.NOT_PRESENT and item.count == 0


def test_comments_and_processing_instructions_are_not_slide_entries(parts, tmp_path):
    pres, ids = order(parts)
    ids.insert(0, etree.Comment("slide order is explicit"))
    ids.insert(2, etree.ProcessingInstruction("test", "data"))
    parts[PRES] = etree.tostring(pres)
    assert shape_order(save(parts, tmp_path))[0] == (1, "FIT_first")


def test_custom_show_and_first_slide_number_do_not_replace_main_order(parts, tmp_path):
    pres, ids = order(parts)
    pres.set("firstSlideNum", "12")
    shows = etree.SubElement(pres, f"{{{P}}}custShowLst")
    show = etree.SubElement(shows, f"{{{P}}}custShow", name="Reverse", id="0")
    sequence = etree.SubElement(show, f"{{{P}}}sldLst")
    for entry in reversed(ids):
        etree.SubElement(sequence, f"{{{P}}}sld", {f"{{{R}}}id": entry.get(f"{{{R}}}id")})
    parts[PRES] = etree.tostring(pres)
    assert shape_order(save(parts, tmp_path)) == [(1, "FIT_first"), (2, "FIT_second"), (3, "OVER_third")]


@pytest.mark.parametrize("damage", [
    "missing-presentation", "malformed-presentation", "wrong-presentation-root",
    "multiple-lists", "unknown-entry", "missing-id", "bad-id", "duplicate-id",
    "missing-rid", "dangling-rid", "duplicate-reference", "missing-rels",
    "malformed-rels", "wrong-rels-root", "ambiguous-rid", "wrong-type",
    "external", "bad-mode", "missing-target", "empty-target", "url-target",
    "fragment-target", "query-target", "escape-target", "backslash-target",
    "missing-slide", "malformed-slide", "wrong-slide-root",
])
def test_broken_order_fails_closed_instead_of_skipping_and_renumbering(parts, tmp_path, damage):
    pres, ids = order(parts)
    rels, rel = first_rel(parts)
    if damage == "multiple-lists":
        pres.append(deepcopy(ids))
    elif damage == "unknown-entry":
        ids[0].tag = f"{{{P}}}unknown"
    elif damage == "missing-id":
        ids[0].attrib.pop("id")
    elif damage == "bad-id":
        ids[0].set("id", "not-a-number")
    elif damage == "duplicate-id":
        ids[1].set("id", "0" + ids[0].get("id"))
    elif damage == "missing-rid":
        ids[0].attrib.pop(f"{{{R}}}id")
    elif damage == "dangling-rid":
        ids[0].set(f"{{{R}}}id", "not-found")
    elif damage == "duplicate-reference":
        ids[1].set(f"{{{R}}}id", ids[0].get(f"{{{R}}}id"))
    elif damage == "ambiguous-rid":
        rels.append(deepcopy(rel))
    elif damage == "wrong-type":
        rel.set("Type", R + "/slideLayout")
    elif damage in ("external", "bad-mode"):
        rel.set("TargetMode", "External" if damage == "external" else "Bogus")
    elif damage == "missing-target":
        rel.attrib.pop("Target")
    elif damage.endswith("-target"):
        rel.set("Target", {
            "empty-target": "", "url-target": "https://example.invalid/slide.xml",
            "fragment-target": "slides/intro.xml#x", "query-target": "slides/intro.xml?q=1",
            "escape-target": "../../ppt/slides/intro.xml", "backslash-target": "slides\\intro.xml",
        }[damage])
    parts[PRES] = etree.tostring(pres)
    parts[RELS] = etree.tostring(rels)
    for kind, part in (("presentation", PRES), ("rels", RELS), ("slide", FIRST)):
        if damage == "missing-" + kind:
            parts.pop(part)
        elif damage == "malformed-" + kind:
            parts[part] = b"<broken"
        elif damage == "wrong-" + kind + "-root":
            parts[part] = b"<wrong/>"
    path = save(parts, tmp_path)
    found = check_pptx(path)
    assert len(found) == 1 and found[0].code == "PKG002" and found[0].severity == ERROR
    assert "slide" in found[0].message
    report = pptx_coverage(path, found)
    assert all(i.status == CoverageStatus.SKIPPED for i in report.items)


def test_same_slide_identity_reaches_json_sarif_and_baselines(fixture):
    found = check_pptx(fixture)
    assert "slide3/OVER_third" in fingerprint("deck.pptx", found[0])
    result = sarif({"deck.pptx": found})["runs"][0]["results"][0]
    assert result["properties"]["where"] == "slide3/OVER_third"
    cli = run_cli("check", str(fixture), "--json", "--coverage")
    assert cli.returncode == 1
    report = json.loads(cli.stdout)["files"][0]
    assert report["findings"][0]["where"] == "slide3/OVER_third"
    assert next(i for i in report["coverage"]["items"] if i["id"] == "pptx.slide-order")["status"] == "checked"


@pytest.mark.parametrize("part", [FIRST, "ppt/slides/slide1.xml", "ppt/slides/slide10.xml"])
def test_unreadable_slide_anywhere_aborts_before_any_layout_findings(parts, tmp_path, part):
    parts[part] = b"<broken"
    found = check_pptx(save(parts, tmp_path))
    assert [(f.code, f.part) for f in found] == [("PKG002", part)]
