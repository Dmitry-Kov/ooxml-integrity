#!/usr/bin/env python3
"""Variants of a PowerPoint-saved deck with one package defect each.

The package rules (content types, relationships, XML well-formedness) were
measured against Word only. Each variant changes, removes or adds one entry of
`evidence/pptx-package-rules/powerpoint-seed.pptx`: every other entry keeps
its name, order, timestamp, compression method and content.

The seed is PowerPoint's own: PowerPoint for Mac made a new presentation of
two slides, `media` added a picture and a hyperlink to slide 2, and PowerPoint
opened that file and saved it under a new name, rewriting every entry.

    python research/pptx_package.py media IN OUT
    python research/pptx_package.py build evidence/pptx-package-rules/variants
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evidence" / "pptx-package-rules" / "powerpoint-seed.pptx"
TYPES = "[Content_Types].xml"
ROOT_RELS = "_rels/.rels"
SLIDE = "ppt/slides/slide2.xml"
SLIDE_RELS = "ppt/slides/_rels/slide2.xml.rels"
PRESENTATION_RELS = "ppt/_rels/presentation.xml.rels"
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
PML = "application/vnd.openxmlformats-officedocument.presentationml."

XML_DEFAULT = '<Default Extension="xml" ContentType="application/xml"/>'
PNG_DEFAULT = '<Default Extension="png" ContentType="image/png"/>'
RELS_DEFAULT = ('<Default Extension="rels" '
                'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>')
SLIDE_OVERRIDE = f'<Override PartName="/ppt/slides/slide2.xml" ContentType="{PML}slide+xml"/>'
IMAGE_REL = f'<Relationship Id="rId3" Type="{DOC_REL}image" Target="../media/image1.png"/>'
OFFICE_REL = (f'<Relationship Id="rId1" Type="{DOC_REL}officeDocument" '
              'Target="ppt/presentation.xml"/>')
CUSTOM_XML_REL = (f'<Relationship Id="rId90" Type="{DOC_REL}customXml" '
                  'Target="../customXml/item1.xml"/>')
#: The custom XML item SharePoint document libraries write, in short: the
#: namespace name is not a URI.
CUSTOM_XML = ('<?xml version="1.0" encoding="utf-8"?><p:properties xmlns:p="http://schemas.'
              'microsoft.com/office/2006/metadata/properties"><documentManagement><ns3:Owner '
              'xmlns:ns3="$ListId:Shared Documents;">Benchmark Editor</ns3:Owner>'
              '</documentManagement></p:properties>')


def _override(name: str) -> str:
    return f'<Override PartName="{name}" ContentType="application/xml"/>'


def _rels_overrides() -> str:
    """An Override for every relationship part of the seed."""
    with zipfile.ZipFile(SOURCE) as z:
        names = [n for n in z.namelist() if n.endswith(".rels")]
    return "".join(f'<Override PartName="/{n}" ContentType="application/vnd.openxmlformats-'
                   'package.relationships+xml"/>' for n in names)


#: an Override added after slide 2's, for a part the deck lacks: (PartName, what it shows)
NAMES = {
    "name-plain": ("/ppt/nothere.xml", "no escape (control)"),
    "name-space": ("/ppt/no%20there.xml", "a space, which must be escaped"),
    "name-percent": ("/ppt/no%25there.xml", "a %, which must be escaped"),
    "name-hash": ("/ppt/no%23there.xml", "a #, which must be escaped"),
    "name-letter-upper": ("/ppt/%6Eothere.xml", "an unreserved letter escaped, upper-case hex"),
    "name-letter-lower": ("/ppt/%6eothere.xml", "an unreserved letter escaped, lower-case hex"),
    "name-digit": ("/ppt/nothere%31.xml", "an unreserved digit escaped"),
    "name-tilde": ("/ppt/no%7Ethere.xml", "the unreserved ~ escaped"),
    "name-non-ascii": ("/ppt/n%C3%A9there.xml", "a non-ASCII letter, escaped as UTF-8"),
    "name-slash": ("/ppt/no%2Fthere.xml", "a /, which a part name must not escape"),
    "name-backslash": ("/ppt/no%5Cthere.xml", "a \\, which a part name must not escape"),
    "name-malformed": ("/ppt/no%ZZthere.xml", "a % that starts no escape"),
}

#: name -> (operations, what changed). An operation is ("replace", entry, old,
#: new), with `old` occurring once; ("drop", entry); or ("add", entry, text),
#: appended after the last entry.
VARIANTS = {
    "default-repeated": ([("replace", TYPES, XML_DEFAULT, XML_DEFAULT * 2)],
                         "the xml Default written twice, same content type"),
    "default-conflicting": ([("replace", TYPES, XML_DEFAULT, XML_DEFAULT + (
        '<Default Extension="xml" ContentType="text/xml"/>'))],
        "a second xml Default with another content type"),
    "default-case": ([("replace", TYPES, XML_DEFAULT, XML_DEFAULT + (
        '<Default Extension="XML" ContentType="application/xml"/>'))],
        "a second Default for XML, the same extension in capitals"),
    "override-repeated": ([("replace", TYPES, SLIDE_OVERRIDE, SLIDE_OVERRIDE * 2)],
                          "slide 2's Override written twice, same content type"),
    "override-conflicting": ([("replace", TYPES, SLIDE_OVERRIDE, SLIDE_OVERRIDE + (
        '<Override PartName="/ppt/slides/slide2.xml" ContentType="application/xml"/>'))],
        "a second Override for slide 2 with another content type"),
    "override-case": ([("replace", TYPES, SLIDE_OVERRIDE, SLIDE_OVERRIDE + SLIDE_OVERRIDE.replace(
        "/ppt/slides/slide2.xml", "/PPT/SLIDES/SLIDE2.XML"))],
        "a second Override for slide 2 naming the part in capitals"),
    **{name: ([("replace", TYPES, SLIDE_OVERRIDE, SLIDE_OVERRIDE + _override(part))],
              f"an Override for {part}, which the deck lacks: {shows}")
       for name, (part, shows) in NAMES.items()},
    "no-xml-default": ([("replace", TYPES, XML_DEFAULT, "")],
                       "the xml Default removed; every XML part keeps its Override"),
    "override-capitals": ([("replace", TYPES, XML_DEFAULT, ""),
                           ("replace", TYPES, 'PartName="/ppt/slides/slide2.xml"',
                            'PartName="/PPT/SLIDES/SLIDE2.XML"')],
                          "the xml Default removed, and slide 2's Override names "
                          "/PPT/SLIDES/SLIDE2.XML"),
    "types-missing": ([("drop", TYPES)], "[Content_Types].xml removed"),
    "rels-default-missing": ([("replace", TYPES, RELS_DEFAULT, "")],
                             "the rels Default removed; no relationship part has a content type"),
    "rels-by-override": ([("replace", TYPES, RELS_DEFAULT, ""),
                          ("replace", TYPES, "</Types>", "{rels_overrides}</Types>")],
                         "the rels Default replaced by an Override for every relationship part"),
    "png-uncovered": ([("replace", TYPES, PNG_DEFAULT, "")],
                      "the png Default removed, so ppt/media/image1.png has no content type"),
    "slide-uncovered": ([("replace", TYPES, XML_DEFAULT, ""), ("replace", TYPES, SLIDE_OVERRIDE, "")],
                        "the xml Default and slide 2's Override removed"),
    "relationship-repeated": ([("replace", SLIDE_RELS, IMAGE_REL, IMAGE_REL * 2)],
                              "slide 2's image relationship written twice, same Id"),
    "relationship-conflicting": ([("replace", SLIDE_RELS, IMAGE_REL, IMAGE_REL + (
        f'<Relationship Id="rId3" Type="{DOC_REL}hyperlink" '
        'Target="https://example.org/added" TargetMode="External"/>'))],
        "a hyperlink relationship added with the image relationship's Id"),
    "embed-dangling": ([("replace", SLIDE, 'r:embed="rId3"', 'r:embed="rId9"')],
                       "the picture's r:embed names rId9, which slide 2 does not declare"),
    "hyperlink-dangling": ([("replace", SLIDE, '<a:hlinkClick r:id="rId2"/>',
                             '<a:hlinkClick r:id="rId9"/>')],
                           "the hyperlink's r:id names rId9, which slide 2 does not declare"),
    "target-missing": ([("replace", SLIDE_RELS, 'Target="../media/image1.png"',
                         'Target="../media/image2.png"')],
                       "the image relationship targets ../media/image2.png, which the deck lacks"),
    "thumbnail-missing": ([("drop", "docProps/thumbnail.jpeg")],
                          "the thumbnail the package relationships name removed"),
    "office-document-missing": ([("replace", ROOT_RELS, OFFICE_REL, "")],
                                "the package officeDocument relationship removed"),
    "root-rels-missing": ([("drop", ROOT_RELS)], "_rels/.rels removed"),
    "slide-malformed": ([("replace", SLIDE, "</p:sld>", "")],
                        "slide 2's closing </p:sld> removed"),
    "unreferenced-malformed": ([("add", "ppt/unused.xml", "<unused>")],
                               "a malformed ppt/unused.xml added that no relationship reaches"),
    "custom-xml-namespace": ([("add", "customXml/item1.xml", CUSTOM_XML),
                              ("replace", PRESENTATION_RELS, "</Relationships>",
                               CUSTOM_XML_REL + "</Relationships>")],
                             "a custom XML item related from the presentation, declaring "
                             "the namespace name $ListId:Shared Documents;"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _apply(entries: list, operations: list) -> list:
    out = list(entries)
    for op in operations:
        if op[0] == "add":
            info = zipfile.ZipInfo(op[1], date_time=out[-1][0].date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            out.append((info, op[2].encode("utf-8")))
            continue
        index = next(i for i, (info, _) in enumerate(out) if info.filename == op[1])
        if op[0] == "drop":
            del out[index]
            continue
        _, entry, old, new = op
        text = out[index][1].decode("utf-8")
        if text.count(old) != 1:
            raise SystemExit(f"{entry}: expected one {old!r}")
        new = new.replace("{rels_overrides}", _rels_overrides())
        out[index] = (out[index][0], text.replace(old, new).encode("utf-8"))
    return out


def build(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(SOURCE) as z:
        entries = [(info, z.read(info.filename)) for info in z.infolist()]
    manifest = {"source": str(SOURCE.relative_to(ROOT)), "source_sha256": sha256(SOURCE),
                "variants": {}}
    for name, (operations, change) in VARIANTS.items():
        dst = out / f"{name}.pptx"
        with zipfile.ZipFile(dst, "w") as z:
            for info, data in _apply(entries, operations):
                z.writestr(info, data)
        manifest["variants"][name] = {"file": dst.name, "change": change, "sha256": sha256(dst)}
    return manifest


def _png(width: int = 16, height: int = 16) -> bytes:
    raw = b"".join(b"\x00" + bytes((40, 110, 200)) * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data)))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


PICTURE = ('<p:pic><p:nvPicPr><p:cNvPr id="6" name="Picture 5"/><p:cNvPicPr>'
           '<a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill>'
           '<a:blip r:embed="rId2"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr>'
           '<a:xfrm><a:off x="8382000" y="4572000"/><a:ext cx="1524000" cy="1524000"/></a:xfrm>'
           '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')


def media(src: Path, dst: Path) -> None:
    """Add a picture and a hyperlink to slide 2 of PowerPoint's new two-slide deck."""
    with zipfile.ZipFile(src) as z, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as out:
        for info in z.infolist():
            data = z.read(info.filename).decode("utf-8") if info.filename.endswith(
                (".xml", ".rels")) else z.read(info.filename)
            if info.filename == TYPES:
                data = data.replace("<Default Extension=\"rels\"", PNG_DEFAULT
                                    + "<Default Extension=\"rels\"", 1)
            elif info.filename == SLIDE_RELS:
                data = data.replace("</Relationships>", (
                    f'<Relationship Id="rId2" Type="{DOC_REL}image" Target="../media/image1.png"/>'
                    f'<Relationship Id="rId3" Type="{DOC_REL}hyperlink" Target="https://example.org/" '
                    'TargetMode="External"/></Relationships>'), 1)
            elif info.filename == SLIDE:
                old = '<a:rPr lang="en-US"/><a:t>One paragraph of body text.</a:t>'
                if data.count(old) != 1:
                    raise SystemExit(f"{SLIDE}: expected one {old!r}")
                data = data.replace(old, '<a:rPr lang="en-US"><a:hlinkClick r:id="rId3"/></a:rPr>'
                                         '<a:t>One paragraph of body text.</a:t>')
                data = data.replace("</p:sp></p:spTree>", "</p:sp>" + PICTURE + "</p:spTree>", 1)
            out.writestr(info, data.encode("utf-8") if isinstance(data, str) else data)
        out.writestr("ppt/media/image1.png", _png())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    m = sub.add_parser("media", help="add the picture and the hyperlink to PowerPoint's new deck")
    m.add_argument("src", type=Path)
    m.add_argument("dst", type=Path)
    b = sub.add_parser("build", help="write the variants and print their manifest")
    b.add_argument("out", type=Path)
    args = parser.parse_args(argv)
    if args.command == "media":
        media(args.src, args.dst)
    else:
        print(json.dumps(build(args.out), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
