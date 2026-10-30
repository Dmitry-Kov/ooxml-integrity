#!/usr/bin/env python3
"""Variants of a Word-saved document with a custom XML part whose namespace name is not a URI.

SharePoint document libraries write custom XML parts that declare
`xmlns:ns3="$ListId:Shared Documents;"`. Namespaces in XML asks for a URI;
libxml2 2.14 reports such a name as a namespace warning at error level, so
lxml refused the part and the checker called it malformed (XML001). Each
variant adds `customXml/item1.xml`, related from the main document, to
`evidence/review-history-benchmark/sources/word-review.docx`; every other
entry keeps its name, order, timestamp, compression method and content.

    python research/namespace_names.py build evidence/xml-namespace-names/variants
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evidence" / "review-history-benchmark" / "sources" / "word-review.docx"
RELS = "word/_rels/document.xml.rels"
ITEM = "customXml/item1.xml"
RELATIONSHIP = ('<Relationship Id="rId90" Type="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships/customXml" Target="../customXml/item1.xml"/>')

#: name -> (the namespace name ns3 is declared with, what it shows)
VARIANTS = {
    "not-a-uri": ("$ListId:Shared Documents;", "the name SharePoint writes, not a URI"),
    "uri": ("urn:example:shared-documents", "a URI (control)"),
}


def item(name: str) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?><p:properties xmlns:p="http://schemas.'
            'microsoft.com/office/2006/metadata/properties" xmlns:xsi="http://www.w3.org/2001/'
            f'XMLSchema-instance"><documentManagement><ns3:Owner xmlns:ns3="{name}">Benchmark '
            'Editor</ns3:Owner></documentManagement></p:properties>')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(SOURCE) as z:
        entries = [(info, z.read(info.filename)) for info in z.infolist()]
    manifest = {"source": str(SOURCE.relative_to(ROOT)), "source_sha256": sha256(SOURCE),
                "variants": {}}
    for name, (namespace, shows) in VARIANTS.items():
        dst = out / f"{name}.docx"
        with zipfile.ZipFile(dst, "w") as z:
            for info, data in entries:
                if info.filename == RELS:
                    text = data.decode("utf-8")
                    if text.count("</Relationships>") != 1:
                        raise SystemExit(f"{RELS}: expected one </Relationships>")
                    data = text.replace("</Relationships>",
                                        RELATIONSHIP + "</Relationships>").encode("utf-8")
                z.writestr(info, data)
            added = zipfile.ZipInfo(ITEM, date_time=entries[-1][0].date_time)
            added.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(added, item(namespace).encode("utf-8"))
        manifest["variants"][name] = {"file": dst.name, "namespace": namespace, "shows": shows,
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
