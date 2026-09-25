"""Labelled DOCX pairs for comments anchored outside the main story.

A comment's range and reference may be written in a header, footer, footnote
or endnote, not only in the main document part. Each source moves comment 1 of
corpus/base.docx, with its range start, range end and reference run, into the
default header or into footnote 1. Every source has a byte-identical control
and an output that loses the moved anchors while the comment body remains.

    python research/comment_story_evidence.py build
    python research/comment_story_evidence.py evaluate [--output receipt.json]

Labels are the exact actionable (rule, severity, count) multiset of check() on
the output plus compare() against its source, scored as in evidence/docx-beta.
`build` refuses to replace a committed manifest; receipts refuse overwrite.
"""
from __future__ import annotations

import argparse
import collections
import json
import platform
import sys
from pathlib import Path

import lxml.etree
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ooxml_integrity  # noqa: E402
from research import build_docx_evidence as beta  # noqa: E402
from research import docx_benchmark as b  # noqa: E402

EVIDENCE = ROOT / "evidence" / "docx-comment-stories"
MANIFEST = EVIDENCE / "manifest.json"
BASE = ROOT / "corpus" / "base.docx"
W = beta.W
COMMENT = "1"

#: (source id, story part, how the anchors are placed, rationale per output)
SOURCES = (
    ("header-anchor", "word/header1.xml",
     "comment 1 anchored around the text of the default header"),
    ("footnote-anchor", "word/footnotes.xml",
     "comment 1 anchored around the text of footnote 1"),
)
LABELS = {
    "header-anchor-control": ([], (
        "Range start, range end and reference of comment 1 are all in the "
        "default header, which the main part relates and references.")),
    "header-anchor-lost-anchor": ([("CMT005", "error", 1), ("FID008", "error", 1)], (
        "The header keeps its text but loses the range and reference; the "
        "comment stays in comments.xml with no anchor in any story (CMT005), "
        "and the default header's comment anchors fall from 1 to 0 (FID008).")),
    "footnote-anchor-control": ([], (
        "Range start, range end and reference of comment 1 are all in "
        "footnote 1, which the main part references.")),
    "footnote-anchor-lost-anchor": ([("CMT005", "error", 1)], (
        "Footnote 1 keeps its text but loses the range and reference; the "
        "comment has no anchor in any story (CMT005). The source comparison "
        "does not count comment anchors in notes, so it adds nothing.")),
}


def _anchors(root: etree._Element) -> list[etree._Element]:
    """Comment 1's range start, range end and reference run, in document order."""
    start = root.find(f".//{W}commentRangeStart[@{W}id='{COMMENT}']")
    end = root.find(f".//{W}commentRangeEnd[@{W}id='{COMMENT}']")
    reference = root.find(f".//{W}commentReference[@{W}id='{COMMENT}']")
    if start is None or end is None or reference is None:
        raise RuntimeError("corpus/base.docx no longer anchors comment 1 in the body")
    return [start, end, reference.getparent()]


def _story_paragraph(root: etree._Element, story: str) -> tuple[etree._Element, int]:
    """The paragraph that receives the anchors, and where its text begins."""
    if story == "word/footnotes.xml":
        note = root.find(f"{W}footnote[@{W}id='1']")
        paragraph = note.find(f"{W}p") if note is not None else None
    else:
        paragraph = root.find(f"{W}p")
    if paragraph is None:
        raise RuntimeError(f"{story} has no paragraph for the anchors")
    first = 0
    for index, child in enumerate(paragraph):
        if child.tag == W + "pPr" or child.find(f"{W}footnoteRef") is not None:
            first = index + 1
    return paragraph, first


def _moved(parts: dict[str, bytes], story: str) -> dict[str, bytes]:
    moved = dict(parts)
    document = beta._xml(moved, "word/document.xml")
    start, end, reference = _anchors(document)
    for node in (start, end, reference):
        node.getparent().remove(node)
        node.tail = None
    beta._store_xml(moved, "word/document.xml", document)
    root = beta._xml(moved, story)
    paragraph, first = _story_paragraph(root, story)
    paragraph.insert(first, start)
    paragraph.append(end)
    paragraph.append(reference)
    beta._store_xml(moved, story, root)
    return moved


def _lost_anchor(parts: dict[str, bytes], story: str) -> dict[str, bytes]:
    damaged = dict(parts)
    root = beta._xml(damaged, story)
    for node in _anchors(root):
        node.getparent().remove(node)
    beta._store_xml(damaged, story, root)
    return damaged


def build(directory: Path = EVIDENCE) -> dict[str, object]:
    """Write sources, outputs and the manifest; the bytes are deterministic."""
    parts, order = beta._read_package(BASE)
    (directory / "sources").mkdir(parents=True, exist_ok=True)
    (directory / "outputs").mkdir(parents=True, exist_ok=True)
    sources, pairs = [], []
    for source_id, story, description in SOURCES:
        source = directory / "sources" / f"{source_id}.docx"
        moved = _moved(parts, story)
        beta._write_package(moved, order, source)
        sources.append({
            "id": source_id, "path": f"sources/{source.name}",
            "sha256": b.digest(source), "story": story,
            "description": description,
        })
        control = directory / "outputs" / f"{source_id}-control.docx"
        control.write_bytes(source.read_bytes())
        lost = directory / "outputs" / f"{source_id}-lost-anchor.docx"
        beta._write_package(_lost_anchor(moved, story), order, lost)
        for output, mutation in ((control, "byte-identical control"),
                                 (lost, f"comment 1 anchors removed from {story}")):
            pair_id = output.stem
            expected, rationale = LABELS[pair_id]
            pairs.append({
                "id": pair_id, "source": source_id,
                "output_path": f"outputs/{output.name}",
                "output_sha256": b.digest(output), "mutation": mutation,
                "expected_findings": [
                    {"code": code, "severity": severity, "count": count}
                    for code, severity, count in expected
                ],
                "label_rationale": rationale,
            })
    return {
        "schema_version": 1,
        "construction": {
            "base": "corpus/base.docx", "base_sha256": b.digest(BASE),
            "script": "research/comment_story_evidence.py",
        },
        "scoring": "exact actionable (rule, severity, count) multiset of check() "
                   "on the output plus compare() against its source",
        "sources": sources,
        "pairs": pairs,
    }


def evaluate(manifest_path: Path = MANIFEST) -> dict[str, object]:
    """Score the committed pairs with the imported checker."""
    manifest = json.loads(manifest_path.read_text())
    directory = manifest_path.parent
    if b.digest(BASE) != manifest["construction"]["base_sha256"]:
        raise ValueError("corpus/base.docx drift")
    sources = {}
    for source in manifest["sources"]:
        path = directory / source["path"]
        if b.digest(path) != source["sha256"]:
            raise ValueError(f"Source drift: {source['path']}")
        sources[source["id"]] = path
    totals = collections.Counter()
    cases = []
    for pair in manifest["pairs"]:
        output = directory / pair["output_path"]
        if b.digest(output) != pair["output_sha256"]:
            raise ValueError(f"Output drift: {pair['output_path']}")
        expected = beta._expected_counter(pair)
        findings = beta._actual_findings(sources[pair["source"]], output)
        actual = collections.Counter((f.code, f.severity.value) for f in findings)
        tp = sum((expected & actual).values())
        totals.update(pairs=1, tp=tp, fp=sum((actual - expected).values()),
                      fn=sum((expected - actual).values()),
                      label_mismatches=int(actual != expected))
        cases.append({
            "id": pair["id"], "expected": pair["expected_findings"],
            "actual": [{"code": f.code, "severity": f.severity.value,
                        "message": f.message, "part": f.part} for f in findings],
            "matches_label": actual == expected,
        })
    imported = Path(ooxml_integrity.__file__).resolve().parent
    return {
        "scope": "Synthetic comment-story pairs; no editor or Office run",
        "checker_version": ooxml_integrity.__version__,
        "checker_source_sha256": b.tree_hash(imported),
        "checker_files_sha256": {p.name: b.digest(p) for p in sorted(imported.glob("*.py"))},
        "python": platform.python_version(), "platform": platform.platform(),
        "lxml": lxml.etree.LXML_VERSION,
        "script_sha256": b.digest(__file__),
        "manifest_sha256": b.digest(manifest_path),
        "totals": dict(sorted(totals.items())),
        "cases": cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build", help="write sources, outputs and labels")
    evaluate_parser = commands.add_parser("evaluate", help="score committed labels")
    evaluate_parser.add_argument("--output", type=Path,
                                 help="save a JSON receipt (refuses overwrite)")
    args = parser.parse_args(argv)
    if args.command == "build":
        if MANIFEST.exists():
            raise SystemExit(f"{MANIFEST.relative_to(ROOT)} exists; labels are not rebuilt")
        manifest = build()
        MANIFEST.write_bytes(b.json_bytes(manifest))
        print(f"wrote {len(manifest['pairs'])} pairs")
        return 0
    result = evaluate()
    if args.output:
        b.save_json(args.output, result)
    totals = result["totals"]
    print(f"pairs={totals['pairs']} tp={totals['tp']} fp={totals['fp']} "
          f"fn={totals['fn']} label mismatches={totals['label_mismatches']}")
    return 1 if totals["label_mismatches"] else 0


if __name__ == "__main__":
    sys.exit(main())
