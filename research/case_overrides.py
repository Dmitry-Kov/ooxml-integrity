#!/usr/bin/env python3
"""Variants of a Word-saved document whose Override names a part in other letters.

OPC compares part names ASCII-case-insensitively, so an `Override` for
`/WORD/COMMENTS.XML` covers `word/comments.xml`. Through 0.8.3
`PKG005` and `PKG010` compared the name exactly, which a package with an `xml`
`Default` hides: the part is covered by the default. Without that default,
`PKG005` reported such a part as having no content type, and `PKG010` did not
read it. The first four variants remove the `xml` `Default` of
`evidence/review-history-benchmark/sources/word-review.docx`, whose other XML
parts all have an `Override`, and change one `Override`; the last three keep the
default and add one `Override`, to see what Word makes of an escaped name.
Every other entry keeps its name, order, timestamp, compression method and
content.

    python research/case_overrides.py build evidence/docx-case-overrides/variants
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
WML = "application/vnd.openxmlformats-officedocument.wordprocessingml."
XML_DEFAULT = '<Default Extension="xml" ContentType="application/xml"/>'
COMMENTS = f'<Override PartName="/word/comments.xml" ContentType="{WML}comments+xml"/>'
EXTENDED = (f'<Override PartName="/word/commentsExtended.xml" '
            f'ContentType="{WML}commentsExtended+xml"/>')


def extra(part_name: str) -> str:
    return f'{COMMENTS}<Override PartName="{part_name}" ContentType="application/xml"/>'


#: name -> (remove the xml Default, Override replaced, its replacement, what changed)
VARIANTS = {
    "no-xml-default": (True, None, None,
                       "the xml Default removed; every XML part keeps its Override"),
    "override-capitals": (True, COMMENTS,
                          COMMENTS.replace("/word/comments.xml", "/WORD/COMMENTS.XML"),
                          "no xml Default, and the comments Override names /WORD/COMMENTS.XML"),
    "override-escaped": (True, COMMENTS,
                         COMMENTS.replace("/word/comments.xml", "/word/%63omments.xml"),
                         "no xml Default, and the comments Override names /word/%63omments.xml"),
    "override-capitals-wrong-type": (
        True, EXTENDED,
        '<Override PartName="/WORD/COMMENTSEXTENDED.XML" '
        'ContentType="application/vnd.ms-word.commentsExtended+xml"/>',
        "no xml Default, and the commentsExtended Override names "
        "/WORD/COMMENTSEXTENDED.XML with the type Codex wrote"),
    "override-escaped-repeat": (False, COMMENTS, COMMENTS + COMMENTS.replace(
        "/word/comments.xml", "/word/%63omments.xml"),
        "a second comments Override naming /word/%63omments.xml"),
    "override-absent-part": (False, COMMENTS, extra("/word/nothere.xml"),
                             "an Override for /word/nothere.xml, a part the package lacks"),
    "override-absent-escaped": (False, COMMENTS, extra("/word/%6Eothere.xml"),
                                "an Override for /word/%6Eothere.xml, the same name escaped"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(SOURCE) as z:
        entries = [(info, z.read(info.filename)) for info in z.infolist()]
    manifest = {"source": str(SOURCE.relative_to(ROOT)), "source_sha256": sha256(SOURCE),
                "variants": {}}
    for name, (no_default, old, new, change) in VARIANTS.items():
        dst = out / f"{name}.docx"
        with zipfile.ZipFile(dst, "w") as z:
            for info, data in entries:
                if info.filename == TYPES:
                    text = data.decode("utf-8")
                    for before, after in ((XML_DEFAULT if no_default else None, ""), (old, new)):
                        if before is None:
                            continue
                        if text.count(before) != 1:
                            raise SystemExit(f"{TYPES}: expected one {before!r}")
                        text = text.replace(before, after)
                    data = text.encode("utf-8")
                z.writestr(info, data)
        manifest["variants"][name] = {"file": dst.name, "change": change, "sha256": sha256(dst)}
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
