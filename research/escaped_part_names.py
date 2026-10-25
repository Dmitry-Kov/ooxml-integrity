#!/usr/bin/env python3
"""Variants of a Word-saved document with one Override named with a percent-escape.

OPC part names are URIs: a character outside the unreserved set is written as
a percent-escape, and an unreserved one (a letter, a digit, `-`, `.`, `_`,
`~`) must not be. Word for Mac refused a package whose Override spells
`/word/%6Eothere.xml` and opened the same Override spelled `/word/nothere.xml`
(evidence/docx-case-overrides). Each variant adds one Override, for a part the
package lacks, after the comments Override of
`evidence/review-history-benchmark/sources/word-review.docx`, so only its name
differs; every other entry keeps its name, order, timestamp, compression method
and content.

    python research/escaped_part_names.py build evidence/docx-escaped-part-names/variants
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
COMMENTS = ('<Override PartName="/word/comments.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>')

#: name -> (PartName of the added Override, what it shows)
VARIANTS = {
    "plain": ("/word/nothere.xml", "no escape (control)"),
    "letter-upper": ("/word/%6Eothere.xml", "an unreserved letter escaped, upper-case hex"),
    "letter-lower": ("/word/%6eothere.xml", "an unreserved letter escaped, lower-case hex"),
    "digit": ("/word/nothere%31.xml", "an unreserved digit escaped"),
    "tilde": ("/word/no%7Ethere.xml", "the unreserved ~ escaped"),
    "space": ("/word/no%20there.xml", "a space, which must be escaped"),
    "percent": ("/word/no%25there.xml", "a %, which must be escaped"),
    "hash": ("/word/no%23there.xml", "a #, which must be escaped"),
    "non-ascii": ("/word/n%C3%A9there.xml", "a non-ASCII letter, escaped as UTF-8"),
    "slash": ("/word/no%2Fthere.xml", "a slash escaped, which OPC forbids"),
    "backslash": ("/word/no%5Cthere.xml", "a backslash escaped, which OPC forbids"),
    "malformed": ("/word/no%ZZthere.xml", "a % not followed by two hex digits"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(SOURCE) as z:
        entries = [(info, z.read(info.filename)) for info in z.infolist()]
    manifest = {"source": str(SOURCE.relative_to(ROOT)), "source_sha256": sha256(SOURCE),
                "variants": {}}
    for name, (part_name, shows) in VARIANTS.items():
        dst = out / f"{name}.docx"
        added = f'<Override PartName="{part_name}" ContentType="application/xml"/>'
        with zipfile.ZipFile(dst, "w") as z:
            for info, data in entries:
                if info.filename == TYPES:
                    text = data.decode("utf-8")
                    if text.count(COMMENTS) != 1:
                        raise SystemExit(f"{TYPES}: expected one comments Override")
                    data = text.replace(COMMENTS, COMMENTS + added).encode("utf-8")
                z.writestr(info, data)
        manifest["variants"][name] = {"file": dst.name, "part_name": part_name,
                                      "shows": shows, "sha256": sha256(dst)}
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
