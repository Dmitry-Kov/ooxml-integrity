"""Run `ooxml-integrity fix` on every DOCX in the repository that it targets.

Every .docx under corpus/, runs/, demo/ and evidence/ is checked once per
distinct content. A file with CMT005, REV001 or PKG010 is given to fix(),
against its source when the repository records one: the review-history tasks,
the two earlier benchmarks' protocols, the agent runs, and the docx-beta,
docx-revisions and comment-story manifests. The record keeps, per file, what
was repaired or refused and why, the re-check, which ZIP members changed, the
output hash, whether a second run wrote the same bytes, and for benchmark
captures the oracle's verdict before and after.

    python research/fix_evidence.py evaluate [--output evidence/fix-repairs/results.json]

Offline; the repaired copies go to a temporary directory and are not kept.
Output hashes depend on the zlib that compresses the edited part, so the
record names it.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import platform
import sys
import tempfile
import zlib
from pathlib import Path

import lxml.etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
import ooxml_integrity  # noqa: E402
from ooxml_integrity import check  # noqa: E402
from ooxml_integrity.fix import REPAIRS, fix  # noqa: E402
from research import review_history_benchmark as bench  # noqa: E402

EVIDENCE = ROOT / "evidence" / "fix-repairs"
RESULTS = EVIDENCE / "results.json"
SCANNED = ("corpus", "runs", "demo", "evidence")
TARGETS = set(REPAIRS.values())


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def sources() -> dict[str, str]:
    """Output path -> source path, for every pair the repository records."""
    out: dict[str, str] = {}
    tasks = {t["id"]: t for t in json.loads(bench.TASKS.read_text())["tasks"]}
    for capture in sorted(bench.CAPTURES.glob("*/*.docx")):
        if capture.stem in tasks:
            out[_rel(capture)] = tasks[capture.stem]["source_path"]
    for name in ("docx-benchmark", "docx-benchmark-boundaries"):
        evidence = ROOT / "evidence" / name
        declared = json.loads((evidence / "protocol.json").read_text())["sources"]
        for capture in sorted((evidence / "captures").glob("*/*.docx")):
            source = declared.get(capture.stem.split("-")[0])
            if source:
                out[_rel(capture)] = source["path"]
    for run in sorted((ROOT / "runs").glob("*/agreement.docx")):
        out[_rel(run)] = "corpus/base.docx"
    beta = ROOT / "evidence" / "docx-beta"
    for p in json.loads((beta / "manifest.json").read_text())["pairs"]:
        out[_rel(beta / p["output"])] = _rel(beta / p["source"])
    revisions = ROOT / "evidence" / "docx-revisions"
    for p in json.loads((revisions / "manifest.json").read_text())["pairs"]:
        out[_rel(revisions / p["output_path"])] = _rel(revisions / p["source_path"])
    stories = ROOT / "evidence" / "docx-comment-stories"
    manifest = json.loads((stories / "manifest.json").read_text())
    paths = {s["id"]: s["path"] for s in manifest["sources"]}
    for p in manifest["pairs"]:
        out[_rel(stories / p["output_path"])] = _rel(stories / paths[p["source"]])
    return out


def _benchmark_task(path: str):
    """(task, editor, counted) for a review-history capture, else None.

    `counted` says whether evaluation.json scores the attempt; captures an
    amendment superseded stay in the repository but are not scored.
    """
    prefix = _rel(bench.CAPTURES) + "/"
    if not path.startswith(prefix):
        return None
    declared = json.loads(bench.TASKS.read_text())
    tasks = {t["id"]: t for t in declared["tasks"]}
    task = tasks.get(Path(path).stem)
    if task is None:
        return None
    attempt = Path(path).parent.name
    counted = any(f"{r['adapter']}-{r['repeat']}" == attempt and r["task"] == task["id"]
                  and r["status"] == "ok"
                  for r in json.loads(bench.EVALUATION.read_text())["results"])
    return task, declared["editor"], counted


def _verdict(task, editor, path: Path) -> dict:
    ev = bench.evaluate(task, path, "ok", editor)
    return {"completed": bool(ev.get("completed")),
            "preserved": bool(ev["preservation"]["preserved"])}


def evaluate() -> dict:
    files: dict[str, list[str]] = collections.defaultdict(list)
    for top in SCANNED:
        for path in sorted((ROOT / top).rglob("*.docx")):
            files[_sha(path)].append(_rel(path))
    pairs = sources()
    records = []
    scanned = 0
    with tempfile.TemporaryDirectory() as work:
        for digest, paths in sorted(files.items(), key=lambda x: x[1][0]):
            path = ROOT / paths[0]
            scanned += 1
            found = collections.Counter(f.code for f in check(path) if f.code in TARGETS)
            if not found:
                continue
            source = next((pairs[p] for p in paths if p in pairs), None)
            out_a, out_b = Path(work, f"{digest}-a.docx"), Path(work, f"{digest}-b.docx")
            against = ROOT / source if source else None
            report = fix(path, out_a, against=against)
            again = fix(path, out_b, against=against)
            d = report.as_dict()
            v = d["verification"]
            record = {
                "paths": paths,
                "sha256": digest,
                "source": source,
                "findings": dict(sorted(found.items())),
                "status": report.status,
                "exit": report.exit_code,
                "reason": report.reason,
                "repaired": [
                    {"repair": r["repair"], "finding": r["finding"]["message"],
                     "detail": r["detail"],
                     "changes": [{k: c[k] for k in ("part", "element", "where", "old", "new")}
                                 for c in r["changes"]]}
                    for r in d["repaired"]],
                "refused": [
                    {"repair": n["repair"], "finding": n["message"], "reason": n["reason"]}
                    for n in d["not_repaired"] if n.get("repair")],
                "other_findings": sorted(
                    f"{n['code']} {n['severity']}" for n in d["not_repaired"]
                    if not n.get("repair") and n["origin"] == "check"),
                "verification": None if v is None else {
                    "passed": v["passed"],
                    "failures": v["failures"],
                    "removed": sorted(f["code"] for f in v["check"]["removed"]),
                    "added": sorted(f["code"] for f in v["check"]["added"]),
                    "compare_input_output": [f"{f['code']} {f['severity']} {f['message']}"
                                             for f in v["compare_input_output"]],
                    "against_added": (None if v["against_added"] is None else
                                      [f"{f['code']} {f['severity']} {f['message']}"
                                       for f in v["against_added"]]),
                    "zip": v["zip"],
                },
                "output_sha256": report.output_sha256,
                "deterministic": (report.output_sha256 == again.output_sha256
                                  and report.status == again.status),
            }
            benchmark = _benchmark_task(paths[0])
            if benchmark and report.status == "repaired":
                task, editor, counted = benchmark
                record["oracle"] = {"scored_attempt": counted,
                                    "before": _verdict(task, editor, path),
                                    "after": _verdict(task, editor, out_a)}
            records.append(record)
    summary = collections.Counter()
    for r in records:
        summary[f"files {r['status']}"] += 1
        for x in r["repaired"]:
            summary[f"repaired {x['repair']}"] += 1
        for x in r["refused"]:
            summary[f"refused {x['repair']}"] += 1
    return {
        "checker": ooxml_integrity.__version__,
        "python": platform.python_version(),
        "lxml": ".".join(map(str, lxml.etree.LXML_VERSION)),
        "zlib": zlib.ZLIB_RUNTIME_VERSION,
        "scanned": {"roots": list(SCANNED), "distinct_docx": scanned,
                    "paths": sum(len(p) for p in files.values())},
        "summary": dict(sorted(summary.items())),
        "files": records,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    e = sub.add_parser("evaluate")
    e.add_argument("--output", type=Path, default=None,
                   help=f"write the record here (e.g. {_rel(RESULTS)})")
    args = parser.parse_args(argv)
    result = evaluate()
    text = json.dumps(result, indent=1, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    for k, n in result["summary"].items():
        print(f"{k}: {n}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
