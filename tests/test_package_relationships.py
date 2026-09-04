"""Package-wide DOCX relationship validation.

Relationship ids are local to the XML part that carries them.  The main
document fixture alone cannot prove that a hyperlink or image in a header is
checked against the header's own relationship part, so those cases live here.
"""
from __future__ import annotations

import zipfile

from conftest import read_part, repack

from ooxml_integrity import Severity, check


ROOT_RELS = "_rels/.rels"
HEADER = "word/header1.xml"
HEADER_RELS = "word/_rels/header1.xml.rels"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _drop_part(src, dst, part):
    """Copy an OPC package except for one named part."""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(
            dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            if info.filename != part:
                zout.writestr(info, zin.read(info.filename))
    return dst


def _header_with_image_ref(header: str, rid: str) -> str:
    header = header.replace(
        f'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"',
        f'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        f'xmlns:r="{R}" xmlns:a="{A}"',
        1,
    )
    return header.replace(
        "</w:p>",
        f'<w:r><w:drawing><a:blip r:embed="{rid}"/></w:drawing></w:r></w:p>',
        1,
    )


def _relationships(*rows: str) -> bytes:
    body = "".join(rows)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{REL}">{body}</Relationships>'
    ).encode()


def test_missing_package_relationships_is_not_clean(tmp_docx, tmp_path):
    out = _drop_part(tmp_docx, tmp_path / "no-root-rels.docx", ROOT_RELS)
    findings = check(out)
    root = [f for f in findings if f.code == "REL001" and f.part == ROOT_RELS]
    assert root
    assert root[0].severity is Severity.ERROR
    assert "officeDocument" in root[0].message


def test_root_internal_target_must_exist(tmp_docx, tmp_path):
    rels = read_part(tmp_docx, ROOT_RELS)
    broken = rels.replace(
        'Target="word/document.xml"', 'Target="word/missing.xml"', 1)
    out = repack(tmp_docx, tmp_path / "bad-entry-point.docx",
                 {ROOT_RELS: broken.encode()})

    missing = [f for f in check(out)
               if f.code == "REL002" and f.part == ROOT_RELS]
    assert len(missing) == 1
    assert "word/missing.xml" in missing[0].message


def test_office_document_entry_point_cannot_be_external(tmp_docx, tmp_path):
    rels = read_part(tmp_docx, ROOT_RELS)
    broken = rels.replace(
        'Target="word/document.xml"',
        'Target="word/document.xml" TargetMode="External"',
        1,
    )
    out = repack(tmp_docx, tmp_path / "external-entry-point.docx",
                 {ROOT_RELS: broken.encode()})

    invalid = [f for f in check(out)
               if f.code == "REL001" and f.part == ROOT_RELS]
    assert len(invalid) == 1
    assert "internal target" in invalid[0].message


def test_relationship_id_is_checked_in_the_header_that_uses_it(
        tmp_docx, tmp_path):
    header = _header_with_image_ref(read_part(tmp_docx, HEADER), "rIdHeaderImage")
    out = repack(tmp_docx, tmp_path / "header-no-rels.docx",
                 {HEADER: header.encode()})

    dangling = [f for f in check(out)
                if f.code == "REL001" and f.part == HEADER]
    assert len(dangling) == 1
    assert "rIdHeaderImage" in dangling[0].message
    assert HEADER_RELS in dangling[0].message


def test_internal_target_in_a_header_relationship_must_exist(
        tmp_docx, tmp_path):
    rid = "rIdHeaderImage"
    header = _header_with_image_ref(read_part(tmp_docx, HEADER), rid)
    rels = _relationships(
        f'<Relationship Id="{rid}" Type="{R}/image" '
        'Target="media/header-logo.png"/>'
    )
    out = repack(tmp_docx, tmp_path / "header-missing-image.docx", {
        HEADER: header.encode(),
        HEADER_RELS: rels,
    })

    missing = [f for f in check(out)
               if f.code == "REL002" and f.part == HEADER_RELS]
    assert len(missing) == 1
    assert "media/header-logo.png" in missing[0].message
    assert not [f for f in check(out)
                if f.code == "REL003" and f.part == HEADER_RELS]


def test_internal_relationship_requires_a_target(tmp_docx, tmp_path):
    rid = "rIdHeaderImage"
    header = _header_with_image_ref(read_part(tmp_docx, HEADER), rid)
    rels = _relationships(
        f'<Relationship Id="{rid}" Type="{R}/image"/>'
    )
    out = repack(tmp_docx, tmp_path / "header-empty-target.docx", {
        HEADER: header.encode(),
        HEADER_RELS: rels,
    })

    missing = [f for f in check(out)
               if f.code == "REL002" and f.part == HEADER_RELS]
    assert len(missing) == 1
    assert "no internal target" in missing[0].message


def test_external_header_relationship_is_not_treated_as_a_package_part(
        tmp_docx, tmp_path):
    rid = "rIdHeaderLink"
    header = read_part(tmp_docx, HEADER).replace(
        f'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"',
        f'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        f'xmlns:r="{R}"',
        1,
    ).replace(
        "</w:p>",
        f'<w:hyperlink r:id="{rid}"><w:r><w:t>Site</w:t></w:r>'
        '</w:hyperlink></w:p>',
        1,
    )
    rels = _relationships(
        f'<Relationship Id="{rid}" Type="{R}/hyperlink" '
        'Target="https://example.org/header" TargetMode="External"/>'
    )
    out = repack(tmp_docx, tmp_path / "header-external-link.docx", {
        HEADER: header.encode(),
        HEADER_RELS: rels,
    })

    assert not [f for f in check(out) if f.code.startswith("REL")]


def test_unused_relationship_is_still_reported_only_for_its_source_part(
        tmp_docx, tmp_path):
    rels = _relationships(
        f'<Relationship Id="rIdUnused" Type="{R}/image" '
        'Target="media/chart.png"/>'
    )
    out = repack(tmp_docx, tmp_path / "header-unused-rel.docx",
                 {HEADER_RELS: rels})

    unused = [f for f in check(out) if f.code == "REL003"]
    assert len(unused) == 1
    assert unused[0].part == HEADER_RELS
    assert unused[0].severity is Severity.INFO


def test_root_level_xml_part_uses_its_own_companion_relationships(
        tmp_docx, tmp_path):
    source = "custom.xml"
    source_rels = "_rels/custom.xml.rels"
    xml = f'<item xmlns:r="{R}" r:id="rIdCustom"/>'.encode()
    rels = _relationships(
        f'<Relationship Id="rIdCustom" Type="{R}/image" '
        'Target="missing.bin"/>'
    )
    out = repack(tmp_docx, tmp_path / "root-part.docx", {
        source: xml,
        source_rels: rels,
    })

    missing = [f for f in check(out)
               if f.code == "REL002" and f.part == source_rels]
    assert len(missing) == 1


def test_a_directory_is_reported_instead_of_raising(tmp_path):
    findings = check(tmp_path)
    assert len(findings) == 1
    assert findings[0].code == "PKG002"
    assert "could not read OPC package" in findings[0].message


def test_permission_error_is_reported_instead_of_raising(
        monkeypatch, base_docx):
    import ooxml_integrity.inspector as inspector

    def denied(*args, **kwargs):
        raise PermissionError("permission denied by test")

    monkeypatch.setattr(inspector.zipfile, "ZipFile", denied)
    findings = inspector.check(base_docx)
    assert len(findings) == 1
    assert findings[0].code == "PKG002"
    assert "permission denied by test" in findings[0].message
