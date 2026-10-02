#!/usr/bin/env python3
"""Re-read the review-history benchmark with declared expectations.

The frozen evaluation scores the published 0.4.6 checker. This is a separate,
later analysis of the same captures: the checker from this checkout, run once
as is and once with expectations derived only from each task's declaration and
its source, the way a caller who asked for the edit would declare them. The
oracle's verdicts (completed, preserved) are read from evaluation.json and are
not recomputed.

Expectations per task:
- K6 accept/reject: FID001 with the insertion and deletion counts the named
  revisions remove from the main document (required).
- K7h plain: FID007 for the edited header or footer story (required).
- K7n plain: FID005 for the edited footnote's source text (required).
- K4 plain: FID009 for the edited insertion's text, allowed but not required,
  because FID009 does not read insertions that hold nested deletions.
Every other task declares none.

    python research/review_history_expectations.py [--output PATH]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from ooxml_integrity import Expectation, check, compare, expect, __version__  # noqa: E402
from research import review_history_benchmark as bench  # noqa: E402
from research import review_history_oracle as oracle  # noqa: E402

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
OUTPUT = bench.EVIDENCE / "expectations" / "results.json"


def _document(source: Path):
    with zipfile.ZipFile(source) as z:
        return etree.fromstring(z.read("word/document.xml"))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def expectations_for(task: dict) -> list[Expectation]:
    kind, mode, call = task["kind"], task["mode"], task.get("call") or {}
    source = ROOT / task["source_path"]
    why = f"{task['id']} requests it"
    if kind == "resolve":
        doc = _document(source)
        removed = collections.Counter()
        for tag, author, text in call["accept"] + call["reject"]:
            removed[tag] += sum(1 for e in doc.iter(W + tag)
                                if e.get(W + "author") == author and oracle.payload(e) == text)
        out = []
        for tag in ("ins", "del"):
            if removed[tag]:
                before = sum(1 for _ in doc.iter(W + tag))
                out.append(Expectation("FID001", {"tag": tag, "before": before,
                                                  "after": before - removed[tag]}, reason=why))
        return out
    if kind != "replace" or mode != "plain":
        return []
    story = call["story"]
    if story.startswith(("header/", "footer/")):
        story_kind, variant = story.split("/")[:2]
        return [Expectation("FID007", {"story_kind": story_kind, "variant": variant}, reason=why)]
    if story in ("footnotes", "endnotes"):
        code = "FID005" if story == "footnotes" else "FID006"
        return [Expectation(code, {"body": _norm(call["paragraph_current"])}, reason=why)]
    if task["task"] == "K4":
        bodies = {"".join(t.text or "" for t in e.iter(W + "t"))
                  for e in _document(source).iter(W + "ins")
                  if call["old"] in "".join(t.text or "" for t in e.iter(W + "t"))}
        return [Expectation("FID009", {"tag": "ins", "body": body}, reason=why, required=False)
                for body in sorted(bodies)]
    return []


def actionable(source: Path, output: Path, expectations: list[Expectation]) -> dict:
    known = {(f.code, f.message) for f in check(source)}
    findings = check(output) + compare(source, output)
    kept, matched = expect(findings, expectations)
    new = [f for f in kept if f.severity.value in ("error", "warn")
           and (f.code, f.message) not in known]
    return {"codes": sorted({f.code for f in new}), "expected": sorted({f.code for f, _ in matched})}


def outcome(record: dict, codes: list[str]) -> str:
    if not record["preservation"]["preserved"]:
        return "detected" if codes else "missed"
    if not record.get("completed"):
        return "incomplete, flagged" if codes else "incomplete, clean"
    return "false alarm" if codes else "clean"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    declared = json.loads(bench.TASKS.read_text(encoding="utf-8"))
    tasks = {t["id"]: t for t in declared["tasks"]}
    plan = {tid: [dict(code=e.code, match=dict(e.match), required=e.required)
                  for e in expectations_for(t)] for tid, t in tasks.items()}
    evaluation = json.loads(bench.EVALUATION.read_text(encoding="utf-8"))
    rows = []
    table = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for record in evaluation["results"]:
        if record["status"] != "ok":
            continue
        task = tasks[record["task"]]
        source = ROOT / task["source_path"]
        output = bench.CAPTURES / f"{record['adapter']}-{record['repeat']}" / f"{record['task']}.docx"
        if bench.unparseable(output):
            before = after = {"codes": ["XML001"], "expected": []}
        else:
            before = actionable(source, output, [])
            after = actionable(source, output, expectations_for(task))
        row = {"adapter": record["adapter"], "repeat": record["repeat"], "task": record["task"],
               "completed": bool(record.get("completed")),
               "preserved": record["preservation"]["preserved"],
               "without": {**before, "outcome": outcome(record, before["codes"])},
               "with": {**after, "outcome": outcome(record, after["codes"])}}
        rows.append(row)
        for mode in ("without", "with"):
            table[record["adapter"]][mode][row[mode]["outcome"]] += 1
    result = {
        "scope": "Post-hoc analysis of the frozen captures; not part of the frozen evaluation.",
        "checker": f"ooxml-integrity {__version__} from this checkout",
        "oracle": "verdicts read from evaluation.json",
        "expectations": plan,
        "summary": {a: {m: dict(c) for m, c in modes.items()} for a, modes in sorted(table.items())},
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for adapter, modes in result["summary"].items():
        print(adapter, "| without:", modes["without"], "| with:", modes["with"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
