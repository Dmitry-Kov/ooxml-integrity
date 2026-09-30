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
