#!/usr/bin/env python3
"""Controls and seeded damage for FID015, FID016 and the two new FID001 tags.

The repository's own DOCX evidence holds no bookmark and no field, so this
record uses the public corpora (`research/realworld_scan.py fetch DIR`). For
every DOCX there whose main document compare() reads:

    copy      the file against itself                     must report nothing
    pydocx    python-docx loads and saves it              must report nothing
    rebuilt   python-docx assigns `paragraph.text` in every body paragraph
              that holds a field or a bookmark            should report

With `--soffice PATH`, a fixed sample of the files that hold a bookmark other
than `_GoBack` or a field is also converted by LibreOffice, headless, to DOCX
and compared with its source. LibreOffice rewrites every part, so those
findings show what a producer's save does to instructions and names.

    python research/reference_evidence.py ~/ooxml-corpora \\
        --soffice /Applications/LibreOffice.app/Contents/MacOS/soffice \\
        --output evidence/docx-references/results.json

The corpora are other projects' files; run this with `python -I`.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import platform
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import docx
from lxml import etree

from ooxml_integrity import __version__, compare
from ooxml_integrity.references import References

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NEW_CODES = {"FID015", "FID016"}
NEW_TAGS = {"sectPr", "endnoteReference"}
SAMPLE = 120


def main_story(path: str) -> References | None:
    """Bookmarks and fields of `word/document.xml`, or None if unreadable."""
    try:
        with zipfile.ZipFile(path) as package:
            root = etree.fromstring(package.read("word/document.xml"))
    except Exception:
        return None
    found = References()
    found.read("document", root)
    return found


def has_content(found: References) -> bool:
    return bool(set(found.bookmarks) - {"_goback"} or found.fields["document"])


def new_findings(source, edited):
    """The findings this change adds, or None when compare() refuses the pair."""
    try:
        found = compare(source, edited)
    except Exception:
        return None
    return [f for f in found if f.code in NEW_CODES
            or (f.code == "FID001" and f.extra.get("tag") in NEW_TAGS)]


def label(finding) -> str:
    what = finding.extra.get("kind") or finding.extra.get("tag") or (
        "referenced" if finding.extra.get("referenced") else "unreferenced")
    return f"{finding.code} {finding.severity.value} {what}"


def rebuild(source: str, target: Path) -> int:
    """Assign `paragraph.text` where a body paragraph holds a field or bookmark."""
    document = docx.Document(source)
    touched = 0
    for paragraph in document.paragraphs:
        if next(paragraph._p.iter(W + "bookmarkStart", W + "fldChar", W + "fldSimple"),
                None) is not None:
            paragraph.text = paragraph.text
            touched += 1
    document.save(target)
    return touched


def why_silent(source: str, rebuilt: Path) -> str:
    before, after = main_story(source), main_story(str(rebuilt))
    gone = [name for key, name in before.bookmarks.items() if key not in after.bookmarks]
    if sum((before.fields["document"] - after.fields["document"]).values()):
        return "a field was lost"
    if any(not name.startswith("_") for name in gone):
        return "a visible bookmark was lost"
    return "only hidden bookmarks nothing points at were lost" if gone else "nothing was lost"


def run(corpora: str, soffice: str | None, work: Path) -> dict:
    files = sorted(glob.glob(f"{corpora}/**/*.docx", recursive=True))
    stats: collections.Counter = collections.Counter()
    seeded: collections.Counter = collections.Counter()
    silent: collections.Counter = collections.Counter()
    unexpected: list[dict] = []
    holding: list[str] = []

    for index, path in enumerate(files):
        story = main_story(path)
        if story is None or (found := new_findings(path, path)) is None:
            stats["not compared"] += 1
            continue
        relative = str(Path(path).relative_to(corpora))
        held = has_content(story)
        if held:
            holding.append(path)
        stats["copy"] += 1
        if found:
            stats["copy with a finding"] += 1
            unexpected.append({"control": "copy", "file": relative,
                               "findings": [str(f) for f in found]})

        saved = work / f"{index}.docx"
        try:
            docx.Document(path).save(saved)
        except Exception:
            stats["python-docx cannot open"] += 1
            continue
        found = new_findings(path, saved)
        if found is None:
            stats["python-docx output not compared"] += 1
            continue
        stats["pydocx"] += 1
        stats["pydocx holding a bookmark or field"] += held
        if found:
            stats["pydocx with a finding"] += 1
            unexpected.append({"control": "pydocx", "file": relative,
                               "findings": [str(f) for f in found]})
        if not held:
            continue

        try:
            touched = rebuild(path, saved)
        except Exception:
            stats["rebuild failed"] += 1
            continue
        if not touched:
            stats["no body paragraph holds one"] += 1
            continue
        found = new_findings(path, saved)
        if found is None:
            stats["rebuilt output not compared"] += 1
            continue
        stats["rebuilt"] += 1
        if found:
            stats["rebuilt and reported"] += 1
            seeded.update(label(f) for f in found)
        else:
            silent[why_silent(path, saved)] += 1

    result = {
        "checker": __version__,
        "python": platform.python_version(),
        "python_docx": docx.__version__ if hasattr(docx, "__version__") else "",
        "docx_files": len(files),
        "holding_a_bookmark_or_field": len(holding),
        "counts": dict(sorted(stats.items())),
        "rebuilt_findings": dict(sorted(seeded.items())),
        "rebuilt_silent": dict(sorted(silent.items())),
        "control_findings": unexpected,
    }

    if soffice:
        sample = holding[::max(1, len(holding) // SAMPLE)][:SAMPLE]
        counts: collections.Counter = collections.Counter()
        kinds: collections.Counter = collections.Counter()
        rows = []
        profile = work / "profile"
        for index, path in enumerate(sample):
            out = work / f"lo-{index}"
            out.mkdir()
            try:
                subprocess.run(
                    [soffice, f"-env:UserInstallation=file://{profile}", "--headless",
                     "--convert-to", "docx:MS Word 2007 XML", "--outdir", str(out), path],
                    capture_output=True, timeout=180, check=True)
                made = next(out.glob("*.docx"))
            except Exception:
                counts["not converted"] += 1
                continue
            found = new_findings(path, made)
            if found is None:
                counts["not compared"] += 1
                continue
            counts["compared"] += 1
            if found:
                counts["with a finding"] += 1
                counts["with an error"] += any(f.severity.value == "error" for f in found)
                kinds.update(label(f) for f in found)
                rows.append({"file": str(Path(path).relative_to(corpora)),
                             "findings": [str(f).replace("\n", " ") for f in found]})
        version = subprocess.run([soffice, "--version"], capture_output=True, text=True)
        result["libreoffice"] = {
            "version": version.stdout.strip(),
            "sample": len(sample),
            "counts": dict(sorted(counts.items())),
            "findings": dict(sorted(kinds.items())),
            "files": rows,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("corpora", help="directory of research/realworld_scan.py fetch")
    parser.add_argument("--soffice", help="LibreOffice binary for the save sample")
    parser.add_argument("--output", type=Path, help="write the result here as JSON")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as work:
        result = run(args.corpora, args.soffice, Path(work))
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 1 if result["control_findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
