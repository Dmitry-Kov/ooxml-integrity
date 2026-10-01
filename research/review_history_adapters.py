#!/usr/bin/env python3
"""Adapters for the review-history benchmark: how each tool performs a task.

Each adapter takes a declared task and writes an output, returning a status
and a note. It does what the tool's public API allows and nothing more; an
operation the API lacks is `unsupported`, not approximated with raw XML.

python-docx 1.2 (MIT) has no tracked changes, no comment replies and no
footnote or endnote API, so tracked replacements, K6 and K7n are unsupported.
K5 adds the new comment with `Document.add_comment`, which anchors whole runs,
and records that the reply is unsupported; completion then fails honestly.

- `python-docx-setter`: the tutorial and MCP-wrapper path, `Paragraph.text =`
  on every paragraph containing the old text and `_Cell.text =` on table cells.
- `python-docx-runs`: the careful path, `Run.text =` on the runs that contain
  the old text, leaving the rest of the paragraph alone.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _stories(document, story):
    """python-docx block containers for a story name, or None if unsupported."""
    if story == "document":
        return [document]
    kind = story.split("/")[0]
    if kind in ("header", "footer"):
        return [getattr(section, kind) for section in document.sections]
    return None


def _paragraphs(container):
    yield from container.paragraphs
    for table in container.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs


def _setter(document, call):
    changed = 0
    for container in _stories(document, call["story"]):
        for paragraph in container.paragraphs:
            if call["old"] in paragraph.text:
                paragraph.text = paragraph.text.replace(call["old"], call["new"])
                changed += 1
        for table in container.tables:
            for row in table.rows:
                for cell in row.cells:
                    if call["old"] in cell.text:
                        cell.text = cell.text.replace(call["old"], call["new"])
                        changed += 1
    return changed


def _runs(document, call):
    changed = 0
    for container in _stories(document, call["story"]):
        for paragraph in _paragraphs(container):
            for run in paragraph.runs:
                if call["old"] in run.text:
                    run.text = run.text.replace(call["old"], call["new"])
                    changed += 1
    return changed


def _comment(document, call, editor):
    anchor = call["anchor"]
    found = [(p, r) for p in _paragraphs(document) if p.text == anchor["paragraph_current"]
             for r in p.runs if anchor["text"] in r.text]
    if not found:
        return "anchor run not found; reply unsupported"
    document.add_comment(found[0][1], text=call["comment"], author=editor["author"],
                         initials=editor["initials"])
    return "new comment anchored on the whole run holding the phrase; reply unsupported"


def python_docx(path: str):
    def perform(task: dict, editor: dict, output: Path) -> tuple[str, str]:
        import docx

        kind, mode = task["kind"], task["mode"]
        if kind == "replace" and mode == "tracked":
            return "unsupported", "python-docx has no tracked-change API"
        if kind == "resolve":
            return "unsupported", "python-docx has no tracked-change API"
        document = docx.Document(str(ROOT / task["source_path"]))
        note = ""
        if kind == "replace":
            if _stories(document, task["call"]["story"]) is None:
                return "unsupported", "python-docx has no footnote or endnote API"
            changed = (_setter if path == "setter" else _runs)(document, task["call"])
            note = f"{changed} element(s) contained the old text"
        elif kind == "comment":
            note = _comment(document, task["call"], editor)
        document.save(str(output))
        return "ok", note
    return perform


ADAPTERS = {
    "python-docx-setter": python_docx("setter"),
    "python-docx-runs": python_docx("runs"),
}


# --- adeu, in its own container ---------------------------------------------------

ADEU_IMAGE = "ooxml-bench-adeu:3.0.6"
SANDBOX = ["docker", "run", "--rm", "--network", "none", "--user", "65534:65534",
           "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "-e", "HOME=/tmp"]


def _revision_id(source: Path, kind: str, author: str, text: str) -> str:
    """The w:id adeu addresses as Chg:N, found by kind, author and text."""
    import sys
    sys.path.insert(0, str(ROOT))
    from research import review_history_oracle as oracle
    pkg = oracle.Package(source)
    hits = [e.get(oracle.W + "id") for _, _, root in oracle.stories(pkg)
            for e in root.iter(oracle.W + kind)
            if e.get(oracle.W + "author") == author and oracle.payload(e) == text]
    assert len(hits) == 1, (kind, author, text, hits)
    return hits[0]


def _comment_id(source: Path, text: str) -> str:
    import sys
    sys.path.insert(0, str(ROOT))
    from research import review_history_oracle as oracle
    pkg = oracle.Package(source)
    root = pkg.xml(pkg.first("comments"))
    hits = [c.get(oracle.W + "id") for c in root.iter(oracle.W + "comment")
            if oracle.text(c, "current").strip() == text]
    assert len(hits) == 1, (text, hits)
    return hits[0]


def adeu_operations(task: dict) -> list[dict] | None:
    """adeu's operations for a declared task; None when adeu has no such operation."""
    kind, mode, call = task["kind"], task["mode"], task.get("call")
    source = ROOT / task["source_path"]
    if kind == "save":
        return []
    if kind == "replace":
        if mode == "plain":
            return None  # adeu's contract: every write is a tracked change
        return [{"type": "modify", "target_text": call["old"], "new_text": call["new"],
                 "match_mode": "strict", "regex": False}]
    if kind == "comment":
        phrase = call["anchor"]["text"]
        return [{"type": "reply", "target_id": f"Com:{_comment_id(source, call['reply_to'])}",
                 "text": call["reply"]},
                {"type": "modify", "target_text": phrase, "new_text": phrase,
                 "match_mode": "strict", "regex": False, "comment": call["comment"]}]
    return [{"type": action, "target_id": f"Chg:{_revision_id(source, k, a, t)}"}
            for action in ("accept", "reject") for k, a, t in call[action]]


def adeu(task: dict, editor: dict, output: Path) -> tuple[str, str]:
    import json
    import shutil
    import subprocess
    import tempfile

    operations = adeu_operations(task)
    if operations is None:
        return "unsupported", "adeu writes only tracked changes"
    work = Path(tempfile.mkdtemp(prefix="adeu-", dir=ROOT / "tmp"))
    try:
        (work / "in").mkdir()
        (work / "out").mkdir()
        (work / "out").chmod(0o777)
        shutil.copyfile(ROOT / task["source_path"], work / "in" / "source.docx")
        (work / "in" / "operations.json").write_text(json.dumps(
            {"author": editor["author"], "operations": operations}), encoding="utf-8")
        shutil.copyfile(ROOT / "research" / "review_history_adeu.py", work / "in" / "runner.py")
        result = subprocess.run(SANDBOX + [
            "-v", f"{work / 'in'}:/in:ro", "-v", f"{work / 'out'}:/out", ADEU_IMAGE,
            "/src/.venv/bin/python", "/in/runner.py", "/in/operations.json",
            "/in/source.docx", "/out/output.docx"], capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return "error", (result.stderr or result.stdout).strip()[-2000:]
        report = json.loads(result.stdout.strip().splitlines()[-1])
        if report["status"] == "ok":
            shutil.copyfile(work / "out" / "output.docx", output)
        return report["status"], json.dumps({"operations": operations, "adeu": report["note"]})
    finally:
        shutil.rmtree(work, ignore_errors=True)


ADAPTERS["adeu"] = adeu
