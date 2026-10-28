#!/usr/bin/env python3
"""Recheck tools of the frozen review-history benchmark at their new releases.

Post-hoc evidence (evidence/review-history-recheck), kept apart from the frozen
evaluation: nothing under evidence/review-history-benchmark changes. Each new
version runs every declared task through the benchmark's own adapter and
runner, unchanged, in an image built the way the frozen one was
(evidence/review-history-recheck/tools.json); only the image name differs.

    python research/review_history_recheck.py capture TOOL REPEAT [--version V]
    python research/review_history_recheck.py control TOOL [--version V]
    python research/review_history_recheck.py evaluate --checker PYTHON
    python research/review_history_recheck.py table
    python research/review_history_recheck.py nested-deletion [--version V]

`--version` names a release in tools.json; without it, the latest.
`capture`, `control` and `nested-deletion` run Docker. `control` runs the image
of the version before V through this same path and compares its outputs with
that version's captures (the frozen ones, or an earlier recheck's), so a
difference in the recheck comes from the release, not from the harness.
`evaluate` scores the recheck captures and the frozen captures of the version
the benchmark ran with the benchmark's oracle and evaluator and the checker in
PYTHON.
"""
from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import review_history_adapters as adapters  # noqa: E402
from research import review_history_benchmark as bench  # noqa: E402
from research import review_history_oracle as oracle  # noqa: E402

W = oracle.W
RECHECK = ROOT / "evidence" / "review-history-recheck"
TOOLS = RECHECK / "tools.json"
CAPTURES = RECHECK / "captures"
CONTROL = RECHECK / "control.json"
RESULTS = RECHECK / "results.json"


def tools() -> dict:
    return json.loads(TOOLS.read_text(encoding="utf-8"))["tools"]


def release(tool: str, version: str | None = None) -> dict:
    """`tool`'s recheck release `version`, by default the latest."""
    found = tools()[tool]["releases"]
    return found[-1] if version is None else next(r for r in found if r["version"] == version)


def versions(tool: str) -> list[tuple[dict, str, list[Path]]]:
    """(spec, origin, capture folders) of the frozen version, then of each release."""
    spec = tools()[tool]
    out = [(spec["frozen"], "frozen", [bench.CAPTURES / n for n in spec["frozen"]["captures"]])]
    for r in spec["releases"]:
        out.append((r, "recheck", sorted(f.parent for f in CAPTURES.glob(
            f"{tool}-{r['version']}-*/capture.json"))))
    return out


def _declared() -> dict:
    return json.loads(bench.TASKS.read_text(encoding="utf-8"))


def _image_id(image: str) -> str:
    return subprocess.run(["docker", "image", "inspect", image, "--format", "{{.Id}}"],
                          capture_output=True, text=True, check=True).stdout.strip()


def performer(tool: str, image: str):
    """The frozen benchmark's adapter for `tool`, pointed at `image`."""
    if tool == "adeu":
        def perform(task, editor, output):
            saved = adapters.ADEU_IMAGE
            adapters.ADEU_IMAGE = image
            try:
                return adapters.adeu(task, editor, output)
            finally:
                adapters.ADEU_IMAGE = saved
        return perform
    saved = adapters.CONTAINER_TOOLS[tool]
    adapters.CONTAINER_TOOLS[tool] = (image, *saved[1:])
    try:
        return adapters.container_tool(tool)
    finally:
        adapters.CONTAINER_TOOLS[tool] = saved


def _run_tasks(folder: Path, perform, record: dict) -> dict:
    """Every declared task once, from its source, with receipts as in the
    frozen captures (bench.capture)."""
    declared = _declared()
    bench._write_new(folder / "started.json", {"started_at": bench._now(), **record,
                                               "environment": bench._tool_versions()})
    attempts = []
    for task in declared["tasks"]:
        output = folder / f"{task['id']}.docx"
        began = time.monotonic()
        try:
            status, note = perform(task, declared["editor"], output)
        except Exception as error:  # the tool's own failure is a result
            status, note = "error", f"{type(error).__name__}: {error}"
        receipt = {"task": task["id"], "status": status, "note": note,
                   "seconds": round(time.monotonic() - began, 3), "finished_at": bench._now()}
        if status == "ok":
            receipt.update(output=output.name, output_sha256=bench._sha(output))
        elif output.exists():
            output.unlink()
        bench._write_new(folder / "receipts" / f"{task['id']}.json", receipt)
        attempts.append(receipt)
    summary = {**record, "finished_at": bench._now(), "attempts": attempts}
    bench._write_new(folder / "capture.json", summary)
    return summary


def _record(tool: str, version: str, image: str, image_id: str, repeat) -> dict:
    assert not bench.verify(), "the frozen benchmark drifted"
    assert _image_id(image) == image_id, f"{image} is not the recorded image"
    runner = ("research/review_history_adeu.py" if tool == "adeu"
              else "research/review_history_runners/" + adapters.CONTAINER_TOOLS[tool][2])
    return {"tool": tool, "version": version, "repeat": repeat, "image": image,
            "image_id": image_id, "protocol_sha256": bench._sha(bench.PROTOCOL),
            "tasks_sha256": bench._sha(bench.TASKS),
            "scripts": {s: bench._sha(ROOT / s) for s in (
                "research/review_history_adapters.py", runner)}}


def capture(tool: str, repeat: int, version: str | None = None) -> dict:
    spec = release(tool, version)
    folder = CAPTURES / f"{tool}-{spec['version']}-{repeat}"
    record = _record(tool, spec["version"], spec["image"], spec["image_id"], repeat)
    return _run_tasks(folder, performer(tool, spec["image"]), record)


def control(tool: str, version: str | None = None, work: Path | None = None) -> dict:
    """The image of the version before `version` through this path, against its captures."""
    import shutil
    order = versions(tool)
    new = release(tool, version)["version"]
    previous, _, folders = order[[s["version"] for s, _, _ in order].index(new) - 1]
    work = work or ROOT / "tmp" / "recheck" / "control" / f"{tool}-{previous['version']}"
    if work.exists():
        shutil.rmtree(work)
    record = _record(tool, previous["version"], previous["image"], previous["image_id"], "control")
    summary = _run_tasks(work, performer(tool, previous["image"]), record)
    recorded = [json.loads((f / "capture.json").read_text(encoding="utf-8")) for f in folders]
    rows = []
    for attempt in summary["attempts"]:
        before = [next(a for a in r["attempts"] if a["task"] == attempt["task"]) for r in recorded]
        row = {"task": attempt["task"], "status": attempt["status"],
               "recorded_status": sorted({a["status"] for a in before})}
        if attempt["status"] == "ok":
            output = work / attempt["output"]
            row["byte_identical_to"] = [f.name for f, a in zip(folders, before)
                                        if a.get("output_sha256") == attempt["output_sha256"]]
            row["facts_equal_ignoring_dates"] = [
                f.name for f, a in zip(folders, before) if a.get("output")
                and oracle.summary(oracle.compare(f / a["output"], output,
                                                  ignore_dates=True)) == {}]
        rows.append(row)
    same = [r for r in rows if r["recorded_status"] == [r["status"]] and (
        r["status"] != "ok" or len(r["facts_equal_ignoring_dates"]) == len(folders))]
    result = {"tool": tool, "version": previous["version"], "image_id": previous["image_id"],
              "ran_at": summary["finished_at"], "attempts": len(rows),
              "same_status_and_facts": len(same),
              "byte_identical": sum(bool(r.get("byte_identical_to")) for r in rows),
              "ok": sum(r["status"] == "ok" for r in rows), "rows": rows}
    record = json.loads(CONTROL.read_text(encoding="utf-8")) if CONTROL.exists() else {}
    record.setdefault(tool, {})[previous["version"]] = result
    CONTROL.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


#: docx-cli issue #13's `nested-deletion.docx`: Reviewer A's pending insertion
#: holding Reviewer B's pending deletion of `any ` before the target.
NESTED_DELETION = (
    '<w:p><w:r><w:t xml:space="preserve">Fees are due. </w:t></w:r>'
    '<w:ins w:id="1" w:author="Reviewer A" w:date="2026-09-01T00:00:00Z">'
    '<w:r><w:t xml:space="preserve">The Client may withhold </w:t></w:r>'
    '<w:del w:id="2" w:author="Reviewer B" w:date="2026-09-02T00:00:00Z">'
    '<w:r><w:delText xml:space="preserve">any </w:delText></w:r></w:del>'
    '<w:r><w:t>disputed amount.</w:t></w:r></w:ins></w:p>')


def nested_record(version: str) -> Path:
    return RECHECK / f"nested-deletion-{version}.json"


def _nested_deletion_docx(path: Path) -> None:
    import zipfile
    w = 'xmlns:w="' + oracle.W_NS + '"'
    r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" '
                   'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   f'<Relationship Id="rId1" Type="{r}/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", f"<w:document {w}><w:body>{NESTED_DELETION}</w:body></w:document>")


def nested_deletion(tool: str = "docx-cli", version: str | None = None) -> dict:
    """Issue #13's nested-deletion case with and without --track, in a release's image."""
    import shutil
    import tempfile
    import zipfile
    from lxml import etree
    spec = release(tool, version)
    assert _image_id(spec["image"]) == spec["image_id"]
    work = Path(tempfile.mkdtemp(prefix="nested-", dir=ROOT / "tmp"))
    try:
        (work / "in").mkdir()
        (work / "out").mkdir()
        (work / "out").chmod(0o777)
        _nested_deletion_docx(work / "in" / "nested-deletion.docx")
        runs = {}
        for mode, extra in (("plain", []), ("tracked", ["--track", "--author", "Editor"])):
            command = ["replace", f"/out/{mode}.docx", "disputed amount", "disputed sum", *extra]
            result = subprocess.run(adapters.SANDBOX + [
                "-v", f"{work / 'in'}:/in:ro", "-v", f"{work / 'out'}:/out", "-w", "/tmp",
                "-e", "DOCX_CLI_NOW=2026-10-01T00:00:00Z", spec["image"], "sh", "-c",
                f"cp /in/nested-deletion.docx /out/{mode}.docx && "
                "bun /opt/docx/package/dist/index.js \"$@\"", "sh", *command],
                capture_output=True, text=True, timeout=120)
            xml = zipfile.ZipFile(work / "out" / f"{mode}.docx").read("word/document.xml").decode()
            body = xml.split("<w:body>", 1)[1].split("</w:body>", 1)[0]
            paragraph = etree.fromstring(f'<w:body xmlns:w="{oracle.W_NS}">{body}</w:body>')
            runs[mode] = {"command": ["docx", *command], "exit": result.returncode,
                          "stdout": result.stdout.strip(), "stderr": result.stderr.strip(),
                          "paragraph": body, "current": oracle.text(paragraph, "current"),
                          "original": oracle.text(paragraph, "original")}
    finally:
        shutil.rmtree(work, ignore_errors=True)
    record = {"tool": tool, "version": spec["version"], "image_id": spec["image_id"],
              "ran_at": bench._now(), "source_paragraph": NESTED_DELETION,
              "expected_current": "Fees are due. The Client may withhold disputed sum.",
              "runs": runs}
    nested_record(spec["version"]).write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n",
                                              encoding="utf-8")
    return record


# --- what each damage class looks like in an output ----------------------------------

def literal_bullets(output: Path) -> list[str]:
    """List level labels that read as an escaped character reference (`&#8226;`)."""
    pkg = oracle.Package(output)
    part = pkg.first("numbering")
    root = pkg.xml(part) if part else None
    if root is None:
        return []
    return sorted({e.get(W + "val") for e in root.iter(W + "lvlText")
                   if "&#" in (e.get(W + "val") or "")})


def _revision_ids(path: Path) -> dict[str, list[str]]:
    """Per part: w:id values carried by more than one tracked text change."""
    pkg = oracle.Package(path)
    out = {}
    for _, part, root in oracle.stories(pkg):
        counts = collections.Counter(e.get(W + "id") for e in root.iter(
            *(W + t for t in oracle.TEXT_REVISIONS)))
        repeated = sorted(i for i, n in counts.items() if n > 1)
        if repeated:
            out[part] = repeated
    return out


def repeated_revision_ids(source: Path, output: Path) -> dict[str, list[str]]:
    """Revision ids repeated in the output that the source did not repeat."""
    before = _revision_ids(source)
    return {part: new for part, ids in _revision_ids(output).items()
            if (new := [i for i in ids if i not in before.get(part, [])])}


def tool_messages(note: str) -> list[str]:
    """What the tool printed on stderr in steps that succeeded (docx-cli's warnings)."""
    try:
        steps = json.loads(note).get("steps") or []
    except (ValueError, AttributeError):
        return []
    return [s["stderr"].strip() for s in steps if s.get("code") == 0 and s.get("stderr", "").strip()]


def probes(task: dict, attempt: dict, output: Path | None) -> dict:
    found = {"tool_messages": tool_messages(attempt.get("note") or "")}
    if output is not None and not bench.unparseable(output):
        found["literal_bullets"] = literal_bullets(output)
        found["repeated_revision_ids"] = repeated_revision_ids(ROOT / task["source_path"], output)
    return found


# --- evaluation ---------------------------------------------------------------------

def _captures():
    """(tool, version, origin, folder) for the frozen version's captures and each
    release's recheck captures."""
    for tool in tools():
        for spec, origin, folders in versions(tool):
            for folder in folders:
                yield tool, spec["version"], origin, folder


def evaluate_one(task: dict, attempt: dict, folder: Path, python: str | None) -> dict:
    output = folder / attempt["output"] if attempt.get("output") else None
    result = bench.evaluate(task, output, attempt["status"], _declared()["editor"], python)
    result["probes"] = probes(task, attempt, output)
    return json.loads(json.dumps(oracle._jsonable(result), ensure_ascii=False))


def _checker_version(python: str) -> dict:
    version = subprocess.run([python, "-I", "-m", "ooxml_integrity", "--version"],
                             capture_output=True, text=True, check=True).stdout.strip()
    where = subprocess.run([python, "-I", "-c", "import ooxml_integrity; print(ooxml_integrity.__file__)"],
                           capture_output=True, text=True, check=True).stdout.strip()
    found = {"version": version}
    if Path(where).resolve().is_relative_to(ROOT / "src"):
        git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True,  # noqa: E731
                                        text=True, check=True).stdout.strip()
        found["source"] = "src/ of this repository"
        found["commit"] = git("rev-parse", "HEAD")
        found["src_modified"] = bool(git("status", "--porcelain", "--", "src"))
    return found


def evaluate(python: str) -> dict:
    assert not bench.verify(), "the frozen benchmark drifted"
    tasks = {t["id"]: t for t in _declared()["tasks"]}
    frozen = {(r["adapter"], r["repeat"], r["task"]): r for r in json.loads(
        bench.EVALUATION.read_text(encoding="utf-8"))["results"]}
    results = []
    for tool, version, origin, folder in _captures():
        data = json.loads((folder / "capture.json").read_text(encoding="utf-8"))
        for attempt in data["attempts"]:
            result = evaluate_one(tasks[attempt["task"]], attempt, folder, python)
            result.update(tool=tool, version=version, origin=origin, capture=folder.name)
            if origin == "frozen":
                # The frozen evaluation's checker axis (0.4.6), as recorded there.
                recorded = frozen[(data["adapter"], data["repeat"], attempt["task"])]
                result["frozen_detection"] = recorded.get("detection")
            results.append(result)
    record = {"evaluated_at": bench._now(), "checker": _checker_version(python),
              "oracle_sha256": bench._sha(ROOT / "research/review_history_oracle.py"),
              "evaluator_sha256": bench._sha(ROOT / "research/review_history_benchmark.py"),
              "summary": summarise(results), "results": results}
    RESULTS.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return record


def _damaged(result: dict) -> bool:
    return result["status"] == "ok" and not result["preservation"]["preserved"]


def summarise(results: list[dict]) -> dict:
    """tool -> version -> counts, as the benchmark README counts them."""
    table = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for r in results:
        row = table[r["tool"]][r["version"]]
        row[r["status"]] += 1
        if r["status"] != "ok":
            continue
        row["completed"] += bool(r["completed"])
        row["preserved"] += r["preservation"]["preserved"]
        if _damaged(r):
            row["damaged"] += 1
            row["damaged_with_new_error_or_warn"] += r["detection"]["outcome"] == "detected"
            row["damaged_with_finding_on_category"] += any(r["detection"]["by_category"].values())
        else:
            row["correct_with_new_error_or_warn"] += r["detection"]["outcome"] == "false_alarm"
    return {tool: {version: dict(sorted(row.items())) for version, row in versions.items()}
            for tool, versions in table.items()}


# --- the comparison table --------------------------------------------------------------

def _cell(results: list[dict]) -> dict:
    """One version's attempts at one task, folded over its repeats."""
    def fold(values):
        values = [json.dumps(v, sort_keys=True) for v in values]
        return json.loads(values[0]) if len(set(values)) == 1 else [json.loads(v) for v in values]
    ok = [r for r in results if r["status"] == "ok"]
    out = {"status": fold([r["status"] for r in results])}
    if ok:
        out["completed"] = fold([bool(r["completed"]) for r in ok])
        out["damage"] = fold([sorted(r["preservation"]["violations"]) for r in ok])
        out["codes"] = fold([r["detection"]["codes"] for r in ok])
    return out


def _versions(tool: str) -> list[str]:
    return [spec["version"] for spec, _, _ in versions(tool)]


def comparison(record: dict) -> list[dict]:
    rows = []
    by = collections.defaultdict(list)
    for r in record["results"]:
        by[(r["tool"], r["task"], r["version"])].append(r)
    for tool in tools():
        names = _versions(tool)
        for task in _declared()["tasks"]:
            if not by[(tool, task["id"], names[-1])]:
                continue
            rows.append({"tool": tool, "task": task["id"],
                         **{v: _cell(by[(tool, task["id"], v)]) for v in names}})
    return rows


CLEAN = {"status": "ok", "completed": True, "damage": [], "codes": []}


def _show(cell: dict) -> str:
    """`completed`/`incomplete`; the damaged categories or `preserved`; the
    checker's new ERROR/WARN codes or `-`. Repeats that differ are shown a / b."""
    if cell["status"] != "ok":
        return cell["status"] if isinstance(cell["status"], str) else " / ".join(cell["status"])
    def fold(value, show):
        return " / ".join(map(show, value)) if value and isinstance(value[0], list) else show(value)
    done = cell["completed"]
    done = " / ".join(("completed" if d else "incomplete") for d in (
        done if isinstance(done, list) else [done]))
    damage = fold(cell["damage"], lambda v: "damaged: " + ", ".join(v) if v else "preserved")
    codes = fold(cell["codes"], lambda v: ", ".join(f"`{c}`" for c in v) or "-")
    return f"{done}; {damage}; {codes}"


def table(record: dict | None = None) -> str:
    """The counts per version, then every task where some version is not
    completed, preserved and free of new ERROR/WARN findings (and ran), marked
    with the versions whose cell differs from the one before."""
    record = record or json.loads(RESULTS.read_text(encoding="utf-8"))
    lines = ["| Tool | Captures | Ran | Unsupported | Rejected | Completed | Preserved "
             "| Damaged | damaged with a new ERROR/WARN | Correct with a new ERROR/WARN |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for tool in tools():
        for spec, origin, _ in versions(tool):
            version = spec["version"]
            row = collections.Counter(record["summary"][tool][version])
            lines.append(f"| {tool} {version} | {origin} | {row['ok']} | {row['unsupported']} "
                         f"| {row['rejected']} | {row['completed']} | {row['preserved']} "
                         f"| {row['damaged']} | {row['damaged_with_new_error_or_warn']} "
                         f"| {row['correct_with_new_error_or_warn']} |")
    lines.append("")
    for tool in tools():
        names = _versions(tool)
        lines += [f"| {tool} task | " + " | ".join(names) + " |", "| --- |" + " --- |" * len(names)]
        for row in comparison(record):
            if row["tool"] != tool or all(row[v] == CLEAN or row[v]["status"] != "ok"
                                          for v in names):
                continue
            changed = [new for old, new in zip(names, names[1:]) if row[old] != row[new]]
            marker = f" (changed in {', '.join(changed)})" if changed else ""
            lines.append(f"| {row['task']}{marker} | "
                         + " | ".join(_show(row[v]) for v in names) + " |")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    version = {"help": "a release in tools.json (default: the latest)"}
    run = sub.add_parser("capture")
    run.add_argument("tool", choices=sorted(tools()))
    run.add_argument("repeat", type=int)
    run.add_argument("--version", **version)
    check = sub.add_parser("control")
    check.add_argument("tool", choices=sorted(tools()))
    check.add_argument("--version", **version)
    every = sub.add_parser("evaluate")
    every.add_argument("--checker", required=True, help="Python with ooxml-integrity")
    sub.add_parser("table")
    nested = sub.add_parser("nested-deletion", help="docx-cli issue #13's nested-deletion case, both modes")
    nested.add_argument("--version", **version)
    args = parser.parse_args(argv)
    if args.command == "capture":
        summary = capture(args.tool, args.repeat, args.version)
        print(args.tool, args.repeat, dict(collections.Counter(a["status"] for a in summary["attempts"])))
    elif args.command == "control":
        result = control(args.tool, args.version)
        print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=1))
    elif args.command == "evaluate":
        print(json.dumps(evaluate(args.checker)["summary"], indent=1))
    elif args.command == "nested-deletion":
        runs = nested_deletion(version=args.version)["runs"]
        print(json.dumps({m: r["current"] for m, r in runs.items()}, indent=1))
    else:
        print(table())
    return 0


if __name__ == "__main__":
    sys.exit(main())
