#!/usr/bin/env python3
"""Measure anonymize(): are the findings reproduced, is any text left?

Every labelled pair in this repository is anonymized as a pair: the DOCX
producer corpus, the existing-revision tranche, the saved editor outputs, the
eight agent runs and the review-history benchmark's outputs. Every DOCX of the
public corpora (see research/realworld_scan.py) is anonymized on its own. Each
item gets its own seed, so a rerun gives the same replacements.

For each item the checker runs on the originals and on the results, as the
CLI does; *reproduced* means the same findings by code, severity, part and
location. The data binding check and the leak scan are anonymize()'s own. An
item anonymize refuses (a data binding path it cannot map) is recorded as
refused. With --libreoffice, a sample of results is also converted to PDF
headless, one file at a time, as a check that they still open.

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
from ooxml_integrity.anonymize import Refused, anonymize  # noqa: E402
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


def measure(group: str, ident: str, paths: list[Path], keep: Path | None,
            kept: dict | None = None) -> dict:
    row = {"group": group, "id": ident}
    with tempfile.TemporaryDirectory() as scratch:
        try:
            report = anonymize(paths, Path(scratch), rng=random.Random(f"{group}/{ident}"))
        except Refused as e:
            return {**row, "refused": str(e).replace(str(Path.home()), "~")[:300]}
        except (ValueError, PackageIssue) as e:
            return {**row, "unreadable": str(e).replace(str(Path.home()), "~")[:200]}
        row.update({
            "reproduced": report.reproduced,
            "findings": {stage: sum(c.values()) for stage, c in report.original.items()},
            "leaks": sum(leak["words"] for leak in report.leaks),
            "collisions": report.collisions,
            "bindings": report.bindings,
        })
        if not report.reproduced:
            row["differences"] = report.differences()
        if report.changed_bindings:
            row["changed_bindings"] = report.changed_bindings
        lexical = sorted({p for f in report.files for p in f.lexical})
        if lexical:
            row["raw_text_parts"] = lexical
        if keep is not None:
            for output, original in zip(report.outputs, paths):
                target = keep / f"{len(list(keep.iterdir())):04d}-{output.name}"
                target.write_bytes(output.read_bytes())
                kept[target.name] = (f"{group}/{ident}", original)
    return row


def render(soffice: str, files: list[Path], kept: dict, timeout: int = 120) -> dict:
    """Convert `files` to PDF with LibreOffice, one at a time; count the ones
    that produced one. A conversion still running after `timeout` seconds is
    stopped. A copy that gives no PDF is listed with its item, and its
    original is tried the same way, to tell a copy LibreOffice cannot open
    from a document it cannot."""
    with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as profiles:
        profile = [0]  # a stopped LibreOffice can leave its profile locked: then a new one

        def convert(path: Path) -> bool | None:
            try:
                subprocess.run([soffice, f"-env:UserInstallation=file://{profiles}/{profile[0]}",
                                "--headless", "--convert-to", "pdf", "--outdir", out, str(path)],
                               capture_output=True, timeout=timeout, check=False)
            except subprocess.TimeoutExpired:
                profile[0] += 1
                return None
            made = Path(out, path.stem + ".pdf").exists()
            Path(out, path.stem + ".pdf").unlink(missing_ok=True)
            return made

        outcome = {True: "converted", False: "no PDF", None: "stopped"}
        converted, failed = 0, []
        for path in files:
            made = convert(path)
            converted += bool(made)
            if not made:
                item, original = kept[path.name]
                failed.append({"item": item, "copy": outcome[made],
                               "original": outcome[convert(original)]})
    return {"converted": converted, "files": len(files), "timeout_seconds": timeout,
            "not converted": failed}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpora", type=Path, default=Path.home() / "ooxml-corpora")
    parser.add_argument("--libreoffice", default=None, help="soffice binary for the render sample")
    parser.add_argument("--sample", type=int, default=200,
                        help="results to render: every n-th pair output and public file")
    parser.add_argument("--render-timeout", type=int, default=120,
                        help="seconds LibreOffice may take for one file")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)

    keep_dir = tempfile.TemporaryDirectory() if args.libreoffice else None
    keep = Path(keep_dir.name) if keep_dir else None
    kept: dict = {}
    rows = [measure(group, ident, [source, edited], keep, kept)
            for group, ident, source, edited in pairs()]
    public = []
    if args.corpora.is_dir():
        from realworld_scan import documents
        for path in documents(args.corpora, (".docx",)):
            ident = str(path.relative_to(args.corpora.resolve()))
            public.append(measure("public corpora", ident, [path], keep, kept))
    rows += public

    summary = collections.defaultdict(collections.Counter)
    for row in rows:
        s = summary[row["group"]]
        s["items"] += 1
        if "unreadable" in row or "refused" in row:
            s["unreadable" if "unreadable" in row else "refused"] += 1
            continue
        s["anonymized"] += 1
        s["reproduced"] += row["reproduced"]
        s["with findings"] += any(row["findings"].values())
        s["with data bindings"] += bool(row["bindings"])
        s["with a binding changed"] += bool(row.get("changed_bindings"))
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
        result["libreoffice"] = render(args.libreoffice, outputs[::step], kept,
                                       args.render_timeout)
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
