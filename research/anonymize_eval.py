#!/usr/bin/env python3
"""Measure anonymize(): are the findings reproduced, is any text left?

Every labelled pair in this repository is anonymized as a pair: the DOCX
producer corpus, the existing-revision tranche, the saved editor outputs, the
eight agent runs and the review-history benchmark's outputs. Every DOCX of the
public corpora (see research/realworld_scan.py) is anonymized on its own. Each
item gets its own seed, so a rerun gives the same replacements.

For each item the checker runs on the originals and on the results, as the
CLI does; *reproduced* means the same findings by code, severity, part and
location. The leak scan is anonymize()'s own. With --libreoffice, a sample of
results is also converted to PDF headless, as a check that they still open.

    python research/anonymize_eval.py [--corpora ~/ooxml-corpora] \
        [--libreoffice /Applications/LibreOffice.app/Contents/MacOS/soffice]
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research"))

from ooxml_integrity import __version__  # noqa: E402
from ooxml_integrity.anonymize import anonymize  # noqa: E402
from ooxml_integrity.archive import PackageIssue  # noqa: E402

EVIDENCE = ROOT / "evidence"
OUTPUT = EVIDENCE / "anonymize" / "results.json"


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def pairs():
    """(group, id, source, edited) for every labelled pair in the repository."""
    beta = json.loads((EVIDENCE / "docx-beta/manifest.json").read_text())
    for p in beta["pairs"]:
        yield ("producer corpus", p["id"], EVIDENCE / "docx-beta" / p["source"],
               EVIDENCE / "docx-beta" / p["output"])
    revisions = json.loads((EVIDENCE / "docx-revisions/manifest.json").read_text())
    for p in revisions["pairs"]:
        yield ("existing revisions", p["id"], EVIDENCE / "docx-revisions" / p["source_path"],
               EVIDENCE / "docx-revisions" / p["output_path"])
    saved = json.loads((EVIDENCE / "docx-fid001-coalescence/candidate.json").read_text())
    for c in saved["cases"]:
        yield "saved editor outputs", c["id"], ROOT / c["source"], ROOT / c["output"]
    for run in sorted((ROOT / "runs").glob("*/agreement.docx")):
        yield "agent runs", run.parent.name, ROOT / "corpus/base.docx", run
    bench = EVIDENCE / "review-history-benchmark"
    tasks = {t["id"]: t for t in json.loads((bench / "tasks.json").read_text())["tasks"]}
    for r in json.loads((bench / "evaluation.json").read_text())["results"]:
        if r["status"] == "ok":
            capture = f"{r['adapter']}-{r['repeat']}"
            yield ("review-history benchmark", f"{capture}/{r['task']}",
                   ROOT / tasks[r["task"]]["source_path"],
                   bench / "captures" / capture / f"{r['task']}.docx")


def measure(group: str, ident: str, paths: list[Path], keep: Path | None) -> dict:
    row = {"group": group, "id": ident}
    with tempfile.TemporaryDirectory() as scratch:
        try:
            report = anonymize(paths, Path(scratch), rng=random.Random(f"{group}/{ident}"))
        except (ValueError, PackageIssue) as e:
            return {**row, "unreadable": str(e).replace(str(Path.home()), "~")[:200]}
        row.update({
            "reproduced": report.reproduced,
            "findings": {stage: sum(c.values()) for stage, c in report.original.items()},
            "leaks": sum(leak["words"] for leak in report.leaks),
            "collisions": report.collisions,
        })
        if not report.reproduced:
            row["differences"] = report.differences()
        lexical = sorted({p for f in report.files for p in f.lexical})
        if lexical:
            row["raw_text_parts"] = lexical
        if keep is not None:
            for output in report.outputs:
                target = keep / f"{len(list(keep.iterdir())):04d}-{output.name}"
                target.write_bytes(output.read_bytes())
    return row


def render(soffice: str, files: list[Path]) -> dict:
    """Convert `files` to PDF with LibreOffice; count the ones that produced one."""
    with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as profile:
        subprocess.run([soffice, f"-env:UserInstallation=file://{profile}", "--headless",
                        "--convert-to", "pdf", "--outdir", out, *map(str, files)],
                       capture_output=True, timeout=3600, check=False)
        made = {p.stem for p in Path(out).glob("*.pdf")}
    return {"converted": sum(f.stem in made for f in files), "files": len(files)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpora", type=Path, default=Path.home() / "ooxml-corpora")
    parser.add_argument("--libreoffice", default=None, help="soffice binary for the render sample")
    parser.add_argument("--sample", type=int, default=200,
                        help="results to render: every n-th pair output and public file")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)

    keep_dir = tempfile.TemporaryDirectory() if args.libreoffice else None
    keep = Path(keep_dir.name) if keep_dir else None
    rows = [measure(group, ident, [source, edited], keep)
            for group, ident, source, edited in pairs()]
    public = []
    if args.corpora.is_dir():
        from realworld_scan import documents
        for path in documents(args.corpora, (".docx",)):
            ident = str(path.relative_to(args.corpora.resolve()))
            public.append(measure("public corpora", ident, [path], keep))
    rows += public

    summary = collections.defaultdict(collections.Counter)
    for row in rows:
        s = summary[row["group"]]
        s["items"] += 1
        if "unreadable" in row:
            s["unreadable"] += 1
            continue
        s["anonymized"] += 1
        s["reproduced"] += row["reproduced"]
        s["with findings"] += any(row["findings"].values())
        s["with leak reports"] += bool(row["leaks"])
        s["with raw-text parts"] += bool(row.get("raw_text_parts"))
        s["with shared replacements"] += bool(row["collisions"])
    result = {
        "scope": "anonymize() on every labelled pair in this repository and every DOCX "
                 "of the public corpora; the checker and the anonymizer from this checkout",
        "checker": f"ooxml-integrity {__version__}",
        "summary": {g: dict(c) for g, c in summary.items()},
        "results": rows,
    }
    if keep is not None:
        outputs = sorted(keep.iterdir())
        step = max(1, len(outputs) // args.sample)
        result["libreoffice"] = render(args.libreoffice, outputs[::step])
        keep_dir.cleanup()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    for group, counts in result["summary"].items():
        print(group, dict(counts))
    if "libreoffice" in result:
        print("libreoffice", result["libreoffice"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
