#!/usr/bin/env python3
"""Variants of a Word-saved document with a declaration repeated (PKG011, REL004).

A script that adds a comments part, or a relationship, without reading what
the package already declares writes a second `Override` for the same part
name, a second `Default` for the same extension, or a relationship `Id` that
is already taken. Each variant changes one entry of
`evidence/review-history-benchmark/sources/word-review.docx`: every other
entry keeps its name, order, timestamp, compression method and content.

    python research/opc_duplicates.py build evidence/docx-opc-duplicates/variants
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evidence" / "review-history-benchmark" / "sources" / "word-review.docx"
TYPES = "[Content_Types].xml"
RELS = "word/_rels/document.xml.rels"
WML = "application/vnd.openxmlformats-officedocument.wordprocessingml."
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"

XML_DEFAULT = '<Default Extension="xml" ContentType="application/xml"/>'
COMMENTS = f'<Override PartName="/word/comments.xml" ContentType="{WML}comments+xml"/>'
COMMENTS_REL = f'<Relationship Id="rId7" Type="{DOC_REL}comments" Target="comments.xml"/>'
STYLES_REL = f'<Relationship Id="rId2" Type="{DOC_REL}styles" Target="styles.xml"/>'

#: name -> (entry, old text, new text, what changed)
VARIANTS = {
    "default-repeated": (TYPES, XML_DEFAULT, XML_DEFAULT * 2,
                         'the xml Default written twice, same content type'),
    "default-conflicting": (TYPES, XML_DEFAULT,
                            XML_DEFAULT + '<Default Extension="xml" ContentType="text/xml"/>',
                            'a second xml Default with another content type'),
    "default-case": (TYPES, XML_DEFAULT,
                     XML_DEFAULT + '<Default Extension="XML" ContentType="application/xml"/>',
                     'a second Default for XML, the same extension in capitals'),
    "override-repeated": (TYPES, COMMENTS, COMMENTS * 2,
                          'the comments Override written twice, same content type'),
    "override-conflicting": (TYPES, COMMENTS,
                             COMMENTS + '<Override PartName="/word/comments.xml" '
                                        'ContentType="application/xml"/>',
                             'a second comments Override with another content type'),
    "override-case": (TYPES, COMMENTS,
                      COMMENTS + COMMENTS.replace("/word/comments.xml", "/WORD/COMMENTS.XML"),
                      'a second comments Override naming the part in capitals'),
    "relationship-repeated": (RELS, COMMENTS_REL, COMMENTS_REL * 2,
                              'the comments relationship written twice, same Id'),
    "relationship-conflicting": (RELS, STYLES_REL, STYLES_REL + (
        f'<Relationship Id="rId2" Type="{DOC_REL}hyperlink" '
        'Target="https://example.org/added" TargetMode="External"/>'),
        'a hyperlink relationship added with the styles relationship\'s Id'),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(SOURCE) as z:
        entries = [(info, z.read(info.filename)) for info in z.infolist()]
    manifest = {"source": str(SOURCE.relative_to(ROOT)), "source_sha256": sha256(SOURCE),
                "variants": {}}
    for name, (entry, old, new, change) in VARIANTS.items():
        dst = out / f"{name}.docx"
        with zipfile.ZipFile(dst, "w") as z:
            for info, data in entries:
                if info.filename == entry:
                    text = data.decode("utf-8")
                    if text.count(old) != 1:
                        raise SystemExit(f"{entry}: expected one {old!r}")
                    data = text.replace(old, new).encode("utf-8")
                z.writestr(info, data)
        manifest["variants"][name] = {"file": dst.name, "entry": entry, "change": change,
                                      "sha256": sha256(dst)}
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="write the variants and print their manifest")
    b.add_argument("out", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(build(args.out), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
