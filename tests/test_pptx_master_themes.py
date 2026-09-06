"""Owning-master theme selection, native Office controls, and fail-closed reads."""
from __future__ import annotations

import hashlib
import json
import posixpath
from copy import deepcopy
from dataclasses import replace
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from lxml import etree

from ooxml_integrity import ERROR, WARN, check_pptx
from ooxml_integrity.coverage import CoverageStatus, pptx_coverage
from ooxml_integrity.doctor import UNAVAILABLE_CHECKS
from ooxml_integrity.pptx_layout import A, P, R, REL, Deck, layout_shape, read_deck

PRES = "ppt/presentation.xml"
SLIDE = "ppt/slides/slide2.xml"
LAYOUT = "ppt/slideLayouts/layout-b.xml"
MASTER = "ppt/slideMasters/master-b.xml"
THEME = "ppt/master-themes/b.xml"
A_FONTS = {"major": "Courier New", "minor": "Arial"}
B_FONTS = {"major": "Times New Roman", "minor": "Courier New"}
EXPECTED_FONTS = ["Arial", "Courier New", "Courier New", "Times New Roman",
                  "Courier New", "Arial", "Arial", "Courier New"]
DEPENDENCIES = [(SLIDE, "/slideLayout", LAYOUT),
                (LAYOUT, "/slideMaster", MASTER), (MASTER, "/theme", THEME)]


@pytest.fixture
def fixture(root):
    return root / "corpus/pptx-master-themes.pptx"


@pytest.fixture
def parts(fixture):
    with ZipFile(fixture) as z:
        return {n: z.read(n) for n in z.namelist()}


def save(parts, tmp_path):
    path = tmp_path / "changed.pptx"
    with ZipFile(path, "w", ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return path


def relname(part):
    folder, _, base = part.rpartition("/")
    return f"{folder}/_rels/{base}.rels"


def relation(parts, owner, suffix):
    tree = etree.fromstring(parts[relname(owner)])
    return tree, next(r for r in tree if r.get("Type") == R + suffix)


def only_slides(parts, *indices):
    pres = etree.fromstring(parts[PRES])
    ids = pres.find(f"{{{P}}}sldIdLst")
    old = list(ids)
    ids[:] = [old[i - 1] for i in indices]
    parts[PRES] = etree.tostring(pres)


def bodies(deck):
    return [s for s in deck.shapes if s.name != "Label"]


def fonts(deck):
    return [s.paragraphs[0].runs[0].font for s in bodies(deck)]


def test_native_office_fixture_fonts_findings_and_hashes(root, fixture):
    evidence = json.loads((root / "docs/calibration/master-themes/evidence.json").read_text())
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == evidence["fixture_sha256"]
    deck = read_deck(fixture)
    assert fonts(deck) == EXPECTED_FONTS
    found = check_pptx(fixture)
    assert [(f.code, f.severity, f.where) for f in found] == [
        ("PPT003", ERROR, "slide2/OVER_B_minor"),
        ("PPT003", ERROR, "slide5/OVER_A_major"),
        ("PPT003", ERROR, "slide8/OVER_B_inherited")]
    assert len(evidence["cases"]) == 8
    for shape, case in zip(bodies(deck), evidence["cases"]):
        assert shape.slide == case["slide"] and shape.name == case["shape"]
        result = layout_shape(shape)
        assert result.measured and result.confident and result.lines == 1
        assert (result.horizontal_overflow_pt > 0) == case["observed_horizontal_overflow"]
        assert hashlib.sha256((root / case["render"]).read_bytes()).hexdigest() == case["render_sha256"]
        assert [(f.code, f.severity.name) for f in found if f.where.startswith(f"slide{shape.slide}/")] == [
            tuple(item) for item in case["expected_findings"]]
    report = {i.id: i for i in pptx_coverage(fixture, found).items}
    assert report["pptx.font-metrics"].status == CoverageStatus.CHECKED
    assert report["pptx.text-overflow"].status == CoverageStatus.CHECKED


def test_diagnostic_maps_are_per_slide_and_independent(fixture):
    deck = read_deck(fixture)
    assert deck.theme_fonts == {}  # No fictitious global font for a mixed deck.
    assert deck.slide_theme_fonts == {
        1: A_FONTS, 2: B_FONTS, 3: B_FONTS, 4: B_FONTS,
        5: A_FONTS, 7: A_FONTS, 8: B_FONTS}
    deck.slide_theme_fonts[2]["minor"] = "Changed"
    assert deck.slide_theme_fonts[3] == B_FONTS
    assert Deck(fixture, 1, 1, [], {}, {}).slide_theme_fonts == {}


def test_unrelated_themes_and_zip_order_cannot_change_run_fonts(parts, tmp_path):
    for name in list(parts):
        if name.startswith("ppt/theme/"):
            parts[name] = b"<broken unrelated theme"
    parts["ppt/theme/theme0.xml"] = b"<also-broken/>"
    path = save(dict(reversed(list(parts.items()))), tmp_path)
    assert fonts(read_deck(path)) == EXPECTED_FONTS


@pytest.mark.parametrize("indices", [(8, 1, 4, 7, 2), (5, 2, 1), (2, 3, 8)])
def test_theme_cache_tracks_owners_not_previous_slide_or_ordinal(parts, tmp_path, indices):
    only_slides(parts, *indices)
    deck = read_deck(save(parts, tmp_path))
    assert fonts(deck) == [EXPECTED_FONTS[i - 1] for i in indices]
    if indices == (2, 3, 8):
        assert deck.theme_fonts == B_FONTS


def test_changing_one_master_theme_does_not_change_other_slides(parts, tmp_path):
    parts[THEME] = parts[THEME].replace(b'"Courier New"', b'"Arial"')
    expected = list(EXPECTED_FONTS)
    for i in (1, 2, 7):
        expected[i] = "Arial"
    assert fonts(read_deck(save(parts, tmp_path))) == expected


@pytest.mark.parametrize("owner,suffix,target", DEPENDENCIES)
@pytest.mark.parametrize("spelling", ["relative", "absolute", "normalized", "encoded"])
def test_dependency_target_spellings(parts, tmp_path, owner, suffix, target, spelling):
    tree, rel = relation(parts, owner, suffix)
    relative = posixpath.relpath(target, posixpath.dirname(owner))
    values = {"relative": relative, "absolute": "/" + target,
              "normalized": "./unused/../" + relative,
              "encoded": "/" + target.replace(".xml", "%2Exml")}
    rel.set("Target", values[spelling])
    parts[relname(owner)] = etree.tostring(tree)
    assert fonts(read_deck(save(parts, tmp_path))) == EXPECTED_FONTS


def test_theme_part_can_live_outside_conventional_theme_folder(parts, tmp_path):
    tree, rel = relation(parts, MASTER, "/theme")
    rel.set("Target", "/custom/styles/body%20theme.xml")
    parts[relname(MASTER)] = etree.tostring(tree)
    parts["custom/styles/body theme.xml"] = parts.pop(THEME)
    assert fonts(read_deck(save(parts, tmp_path))) == EXPECTED_FONTS


@pytest.mark.parametrize("owner,suffix,target", DEPENDENCIES)
@pytest.mark.parametrize("damage", [
    "missing-link", "wrong-type", "duplicate-link", "duplicate-id", "missing-id",
    "external", "bad-mode", "no-target", "empty-target", "url", "network-path",
    "query", "fragment", "above-root", "backslash", "control",
    "missing-rels", "malformed-rels", "wrong-rels-root",
    "missing-part", "malformed-part", "wrong-part-root",
])
def test_unresolvable_dependency_fails_closed(parts, tmp_path, owner, suffix, target, damage):
    tree, rel = relation(parts, owner, suffix)
    if damage == "missing-link":
        tree.remove(rel)
    elif damage == "wrong-type":
        rel.set("Type", "https://example.invalid" + suffix)
    elif damage in ("duplicate-link", "duplicate-id"):
        duplicate = deepcopy(rel)
        duplicate.set("Id" if damage == "duplicate-link" else "Type",
                      "another" if damage == "duplicate-link" else R + "/image")
        tree.append(duplicate)
    elif damage == "missing-id":
        rel.attrib.pop("Id")
    elif damage in ("external", "bad-mode"):
        rel.set("TargetMode", "External" if damage == "external" else "Bogus")
    elif damage == "no-target":
        rel.attrib.pop("Target")
    else:
        invalid = {"empty-target": "", "url": "https://example.invalid/" + target,
                   "network-path": "//example.invalid/" + target,
                   "query": "/" + target + "?q=1", "fragment": "/" + target + "#id",
                   "above-root": "../../../" + target,
                   "backslash": "/" + target.replace("/", "\\"),
                   "control": "/" + target + "\n"}
        if damage in invalid:
            rel.set("Target", invalid[damage])
    parts[relname(owner)] = etree.tostring(tree)
    for kind, name in (("rels", relname(owner)), ("part", target)):
        if damage == "missing-" + kind:
            parts.pop(name)
        elif damage == "malformed-" + kind:
            parts[name] = b"<broken"
        elif damage == "wrong-" + kind + "-root":
            parts[name] = b"<wrong/>"
    path = save(parts, tmp_path)
    found = check_pptx(path)
    assert len(found) == 1 and found[0].code == "PKG002" and found[0].severity == ERROR
    assert all(i.status == CoverageStatus.SKIPPED for i in pptx_coverage(path, found).items)


@pytest.mark.parametrize("damage", ["missing-scheme", "missing-minor", "empty", "token"])
def test_missing_required_latin_font_does_not_borrow_global_theme(parts, tmp_path, damage):
    theme = etree.fromstring(parts[THEME])
    scheme = theme.find(f"{{{A}}}themeElements/{{{A}}}fontScheme")
    minor = scheme.find(f"{{{A}}}minorFont")
    if damage == "missing-scheme":
        scheme.getparent().remove(scheme)
    elif damage == "missing-minor":
        scheme.remove(minor)
    else:
        minor.find(f"{{{A}}}latin").set("typeface", " " if damage == "empty" else "+mn-lt")
    parts[THEME] = etree.tostring(theme)
    found = check_pptx(save(parts, tmp_path))
    assert len(found) == 1 and found[0].code == "PKG002"
    assert "minor Latin theme font" in found[0].message


def test_missing_unused_major_font_does_not_block_minor_text(parts, tmp_path):
    only_slides(parts, 2)
    theme = etree.fromstring(parts[THEME])
    major = theme.find(f"{{{A}}}themeElements/{{{A}}}fontScheme/{{{A}}}majorFont")
    major.getparent().remove(major)
    parts[THEME] = etree.tostring(theme)
    assert fonts(read_deck(save(parts, tmp_path))) == ["Courier New"]


@pytest.mark.parametrize("owner,suffix,target", DEPENDENCIES)
def test_literal_fonts_do_not_require_a_theme_dependency(parts, tmp_path, owner, suffix, target):
    only_slides(parts, 6)  # Literal Calibri label and literal Arial body on master B.
    parts.pop(target)
    deck = read_deck(save(parts, tmp_path))
    assert fonts(deck) == ["Arial"] and deck.slide_theme_fonts == {}


@pytest.mark.parametrize("source", ["run", "paragraph", "list", "layout", "master-placeholder",
                                   "master-style", "presentation"])
@pytest.mark.parametrize("token,expected", [("+mn-lt", "Courier New"), ("+mj-lt", "Times New Roman")])
def test_inherited_tokens_use_the_owner_theme(parts, tmp_path, source, token, expected):
    only_slides(parts, 2)
    slide = etree.fromstring(parts[SLIDE])
    body = slide.findall(f"{{{P}}}cSld/{{{P}}}spTree/{{{P}}}sp")[1]
    tx = body.find(f"{{{P}}}txBody")
    for latin in list(tx.iter(f"{{{A}}}latin")):
        latin.getparent().remove(latin)
    ap = tx.find(f"{{{A}}}p")
    pres = etree.fromstring(parts[PRES])
    default = pres.find(f"{{{P}}}defaultTextStyle/{{{A}}}lvl1pPr/{{{A}}}defRPr")
    default.find(f"{{{A}}}latin").set("typeface", "ShouldNotWin")

    def level(style):
        for old in list(style):
            style.remove(old)
        return etree.SubElement(etree.SubElement(style, f"{{{A}}}lvl1pPr"), f"{{{A}}}defRPr")

    changed = {}
    if source == "run":
        dest = ap.find(f"{{{A}}}r/{{{A}}}rPr")
    elif source == "paragraph":
        ppr = ap.find(f"{{{A}}}pPr")
        dest = ppr.find(f"{{{A}}}defRPr")
        if dest is None:
            dest = etree.SubElement(ppr, f"{{{A}}}defRPr")
    elif source == "list":
        dest = level(tx.find(f"{{{A}}}lstStyle"))
    elif source == "presentation":
        default.remove(default.find(f"{{{A}}}latin"))
        dest = default
    else:
        etree.SubElement(body.find(f"{{{P}}}nvSpPr/{{{P}}}nvPr"), f"{{{P}}}ph", idx="42", type="body")
        owner = LAYOUT if source == "layout" else MASTER
        owner_tree = etree.fromstring(parts[owner])
        if source == "master-style":
            styles = owner_tree.find(f"{{{P}}}txStyles")
            dest = level(styles.find(f"{{{P}}}bodyStyle"))
        else:
            placeholder = deepcopy(body)
            owner_tree.find(f"{{{P}}}cSld/{{{P}}}spTree").append(placeholder)
            dest = level(placeholder.find(f"{{{P}}}txBody/{{{A}}}lstStyle"))
        changed[owner] = owner_tree
    etree.SubElement(dest, f"{{{A}}}latin", typeface=token)
    for name, tree in {PRES: pres, SLIDE: slide, **changed}.items():
        parts[name] = etree.tostring(tree)
    assert fonts(read_deck(save(parts, tmp_path))) == [expected]


def test_hard_break_uses_owner_theme_and_preserves_existing_size_default(parts, tmp_path):
    only_slides(parts, 2)
    tree = etree.fromstring(parts[SLIDE])
    body = tree.findall(f"{{{P}}}cSld/{{{P}}}spTree/{{{P}}}sp")[1]
    ap = body.find(f"{{{P}}}txBody/{{{A}}}p")
    br = etree.SubElement(ap, f"{{{A}}}br")
    etree.SubElement(etree.SubElement(br, f"{{{A}}}rPr"), f"{{{A}}}latin", typeface="+mj-lt")
    parts[SLIDE] = etree.tostring(tree)
    run = bodies(read_deck(save(parts, tmp_path)))[0].paragraphs[0].runs[-1]
    assert run.text == "\n" and run.font == "Times New Roman" and run.size_pt == 18


@pytest.mark.parametrize("owner", [SLIDE, LAYOUT])
@pytest.mark.parametrize("kind", ["fontScheme", "clrScheme", "missing-part"])
def test_font_scheme_overrides_are_explicitly_outside_this_model(parts, tmp_path, owner, kind):
    tree = etree.fromstring(parts[relname(owner)])
    etree.SubElement(tree, f"{{{REL}}}Relationship", Id="themeOverride",
                     Type=R + "/themeOverride", Target="/ppt/overrides/override.xml")
    parts[relname(owner)] = etree.tostring(tree)
    override = etree.Element(f"{{{A}}}themeOverride", nsmap={"a": A})
    if kind != "missing-part":
        etree.SubElement(override, f"{{{A}}}{kind}", name="Override")
        parts["ppt/overrides/override.xml"] = etree.tostring(override)
    path = save(parts, tmp_path)
    if kind == "clrScheme":
        assert fonts(read_deck(path)) == EXPECTED_FONTS
    else:
        found = check_pptx(path)
        assert len(found) == 1 and found[0].code == "PKG002"
        assert "themeOverride" in found[0].message


def test_resolved_theme_does_not_upgrade_substituted_font_confidence(fixture, monkeypatch):
    import ooxml_integrity.pptx_layout as layout

    original = layout._metrics_for

    def substitute(run):
        metric = original(run)
        return replace(metric, face=replace(metric.face, match="fallback")) if metric else None

    monkeypatch.setattr(layout, "_metrics_for", substitute)
    found = [f for f in check_pptx(fixture) if f.code == "PPT003"]
    assert len(found) == 3 and all(f.severity == WARN for f in found)
    report = {i.id: i for i in pptx_coverage(fixture, found).items}
    assert report["pptx.text-overflow"].status == CoverageStatus.ESTIMATED


def test_doctor_does_not_claim_slide_order_is_unavailable():
    assert "pptx.slide-order" not in {item["id"] for item in UNAVAILABLE_CHECKS}
