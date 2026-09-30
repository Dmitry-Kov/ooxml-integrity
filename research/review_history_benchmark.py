#!/usr/bin/env python3
"""Evaluate review-history benchmark outputs on four separate axes.

For one declared task, a source and an output: the adapter's status, whether
the task was completed (the output's XML), whether everything else was
preserved (the oracle's report minus what the task declares), and what
`ooxml-integrity` reported. See evidence/review-history-benchmark/PROTOCOL.md.

    python research/review_history_benchmark.py evaluate TASK_ID OUTPUT [--checker PYTHON]

The checker runs as a separate process from the given Python environment, so
the evaluation can pin a published release; nothing here imports it.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import review_history_oracle as oracle  # noqa: E402

W = oracle.W
TASKS = ROOT / "evidence" / "review-history-benchmark" / "tasks.json"
WRAPPERS = {W + t for t in oracle.TEXT_REVISIONS}

#: Failure category -> checker rules that concern it (PROTOCOL.md, axis 4).
RULES = {
    "revision": ("FID001", "FID009", "FID010", "REV"),
    "attribution": ("FID001", "FID009", "FID010", "REV"),
    "move_range": ("FID001", "REV"),
    "comment": ("CMT", "FID004"), "comment_anchor": ("CMT", "FID004", "FID001"),
    "comment_thread": ("CMT",), "comment_done": ("CMT",), "comment_date": ("CMT",),
    "comment_durable_id": ("CMT",), "person": ("CMT",),
    "note": ("FID005", "FID006", "FTN"), "note_current": ("FID005", "FID006", "FTN"),
    "note_reference": ("FID001", "FTN"),
    "story": ("FID007", "FID008"), "story_current": ("FID007", "FID008"),
    "content_control": ("FID001",), "table": ("FID001",), "hyperlink": ("FID001",),
    "image": ("FID001",), "list_item": ("FID001",),
    "paragraph": ("FID003",), "paragraph_current": ("FID003",),
    "setting": (), "part": ("PKG",),
}


# --- target paragraph -----------------------------------------------------------

def _paragraphs(path: Path, story: str):
    pkg = oracle.Package(path)
    root = next((r for name, _, r in oracle.stories(pkg) if name == story), None)
    return [] if root is None else list(root.iter(W + "p"))


def _find(path: Path, story: str, current: str, original: str | None = None):
    found = [p for p in _paragraphs(path, story)
             if oracle.paragraph_text(p, "current") == current
             and (original is None or oracle.paragraph_text(p, "original") == original)]
    return found[0] if len(found) == 1 else None


def _state(node, editor: str) -> tuple:
    """Revision wrappers holding a text node, outermost first, and its run's
    formatting revision; each as (kind, author, date)."""
    state = [(a.tag[len(W):], a.get(W + "author"), a.get(W + "date"))
             for a in reversed(list(node.iterancestors())) if a.tag in WRAPPERS]
    run = next(node.iterancestors(W + "r"), None)
    change = None if run is None else run.find(W + "rPr/" + W + "rPrChange")
    if change is not None:
        state.append(("rPrChange", change.get(W + "author"), change.get(W + "date")))
    return tuple(state)


def _characters(paragraph, editor: str) -> list[tuple[str, tuple]]:
    out = []
    for node in oracle._own(paragraph):
        if node.tag in (W + "t", W + "delText") and not oracle._in(
                node, {W + "pPrChange", W + "rPrChange"}):
            state = _state(node, editor)
            out.extend((char, state) for char in node.text or "")
    return out


def _marks(paragraph) -> list:
    """Paragraph-level revisions: its mark's wrappers and property changes."""
    props = paragraph.find(W + "pPr")
    if props is None:
        return []
    found = [(e.tag[len(W):], e.get(W + "author"), e.get(W + "date"))
             for e in props.iter(*(W + t for t in oracle.TEXT_REVISIONS + ("pPrChange", "rPrChange")))
             if not oracle._in(e, {W + "pPrChange"}) or e.tag == W + "pPrChange"]
    return sorted(found)


def attribution(source: Path, output: Path, call: dict, mode: str, editor: str) -> list[str]:
    """Problems with who owns each character of the edited paragraph.

    All text of the paragraph, deleted or not, is compared character by
    character with its revision wrappers. In tracked mode, removing the
    editor's insertions and the editor's wrappers from the output must give the
    source exactly, and the editor may delete only inside the declared old
    text. In plain mode, the output must be the source with exactly the old
    text replaced by the new, which takes the old text's wrappers.
    """
    before = _find(source, call["story"], call["paragraph_current"])
    after = _find(output, call["story"], call["expected"]["current"], call["expected"]["original"])
    if after is None:
        return ["target paragraph not found with the expected texts"]
    a, b = _characters(before, editor), _characters(after, editor)
    visible = [i for i, (_, state) in enumerate(a)
               if not any(s[0] in ("del", "moveFrom") for s in state)]
    current = "".join(a[i][0] for i in visible)
    at = current.find(call["old"])
    start, stop = visible[at], visible[at + len(call["old"]) - 1] + 1
    strip = lambda state: tuple(s for s in state if s[1] != editor)  # noqa: E731
    mine = lambda state, kind: any(s[1] == editor and s[0] == kind for s in state)  # noqa: E731
    problems = []
    if mode == "tracked":
        kept = [(c, state) for c, state in b if not mine(state, "ins")]
        if [(c, strip(state)) for c, state in kept] != a:
            problems.append("without the editor's insertions the paragraph is not the source: "
                            f"{''.join(c for c, _ in kept)!r}")
        else:
            outside = [i for i, (_, state) in enumerate(kept)
                       if mine(state, "del") and not start <= i < stop]
            if outside:
                problems.append(f"the editor deleted source text outside the old text at {outside}")
    else:
        state = a[start][1]
        expected = a[:start] + [(c, state) for c in call["new"]] + a[stop:]
        if b != expected:
            problems.append(f"expected {''.join(c for c, _ in expected)!r} with the source's owners, "
                            f"got {''.join(c for c, _ in b)!r}")
    if [m for m in _marks(after) if m[1] != editor] != _marks(before):
        problems.append(f"paragraph revisions changed {_marks(before)} -> {_marks(after)}")
    return problems


# --- preservation -----------------------------------------------------------------

def _pop(bucket: list, predicate) -> bool:
    for index, item in enumerate(bucket):
        if predicate(item):
            del bucket[index]
            return True
    return False


def preservation(task: dict, source: Path, output: Path, editor: dict) -> dict:
    report = oracle.compare(source, output)
    lost = {c: list(v) for c, v in report["lost"].items()}
    added = {c: list(v) for c, v in report["added"].items()}
    changed = {c: list(v) for c, v in report["changed"].items()}
    name = editor["author"]
    extra: dict[str, list] = {}
    kind = task["kind"]

    def allow_change(category, before, after):
        return _pop(changed.get(category, []), lambda pair: pair == [before, after]) or (
            _pop(lost.get(category, []), lambda f: f == before)
            and _pop(added.get(category, []), lambda f: f == after))

    def drop(bucket, category, predicate):
        items = bucket.get(category, [])
        bucket[category] = [i for i in items if not predicate(i)]

    if kind == "replace":
        call = task["call"]
        story, o0, c0 = call["story"], call["paragraph_original"], call["paragraph_current"]
        o1, c1 = call["expected"]["original"], call["expected"]["current"]
        contexts = {o0, o1}
        if o0 != o1:
            allow_change("paragraph", (story, o0), (story, o1))
        allow_change("paragraph_current", (story, o0, c0), (story, o1, c1))
        # Revisions in the target paragraph are judged character by character.
        in_target = lambda f: f[0] == story and f[6] in contexts  # noqa: E731
        drop(lost, "revision", in_target)
        drop(added, "revision", lambda f: in_target(f) and (task["mode"] == "tracked" or f[2] != name))
        drop(changed, "revision", lambda pair: in_target(pair[0]) and in_target(pair[1]))
        extra["attribution"] = attribution(source, output, call, task["mode"], name)
        # Other facts that record the paragraph's rejected text as their context.
        for category, at in (("note_reference", 3), ("list_item", 1)):
            for fact in [f for f in lost.get(category, []) if f[at] == o0]:
                moved = fact[:at] + (o1,) + fact[at + 1:]
                if o0 != o1 and _pop(added.get(category, []), lambda f: f == moved):
                    lost[category].remove(fact)
            for pair in list(changed.get(category, [])):
                if pair[0][at] == o0 and pair[1] == pair[0][:at] + (o1,) + pair[0][at + 1:]:
                    changed[category].remove(pair)
        # Tables and content controls record the rejected text of their paragraphs.
        relined = lambda value: "\n".join(o1 if line == o0 else line  # noqa: E731
                                          for line in value.split("\n"))
        for pair in list(changed.get("table", [])):
            (s0, grid0, head0, rows0), (s1, grid1, head1, rows1) = pair
            if (s0, grid0, head0) == (s1, grid1, head1) and s0 == story and rows1 == tuple(
                    tuple(relined(cell) for cell in row) for row in rows0):
                changed["table"].remove(pair)
        for pair in list(changed.get("content_control", [])):
            if pair[0][:4] == pair[1][:4] and pair[0][0] == story and pair[1][4] == relined(pair[0][4]):
                changed["content_control"].remove(pair)
        for pair in list(changed.get("comment_anchor", [])):
            (key, s0, orig0, cur0, *flags0), (key1, s1, orig1, cur1, *flags1) = pair
            if s0 == s1 == story and flags0 == flags1 and key == key1 and orig0 and orig0 in o0 \
                    and (task["mode"] == "plain" or orig0 == orig1):
                changed["comment_anchor"].remove(pair)
                extra.setdefault("anchor_follows_edit", []).append(call["new"] in (cur1 or ""))
        if story.startswith(("header", "footer")):
            kind_, variant, section = story.split("/")
            if o0 != o1:
                allow_change("story", (kind_, variant, section, o0), (kind_, variant, section, o1))
            allow_change("story_current", (kind_, variant, section, o0, c0),
                         (kind_, variant, section, o1, c1))
        if story in ("footnotes", "endnotes"):
            n0, n1, m0, m1 = o0.strip(), o1.strip(), c0.strip(), c1.strip()
            if n0 != n1:
                allow_change("note", (story, n0), (story, n1))
                for fact in [f for f in lost.get("note_reference", []) if f[:2] == (story, n0)]:
                    if _pop(added.get("note_reference", []), lambda f: f == (story, n1) + fact[2:]):
                        lost["note_reference"].remove(fact)
            allow_change("note_current", (story, n0, m0), (story, n1, m1))
    elif kind == "comment":
        call = task["call"]
        texts = {call["reply"], call["comment"]}
        mine = lambda key: key[0] == name and key[2] in texts  # noqa: E731
        drop(added, "comment", mine)
        for category in ("comment_anchor", "comment_date", "comment_done", "comment_durable_id",
                         "comment_thread"):
            drop(added, category, lambda f: mine(f[0]))
        facts = oracle.facts(source)
        if not facts["comment_done"]:
            # The source had no commentsExtended: the tool may create it.
            drop(added, "comment_done", lambda f: f[1] is False)
        if not facts["comment_durable_id"]:
            drop(added, "comment_durable_id", lambda f: True)
            drop(changed, "comment_date", lambda pair: pair[0][:2] == pair[1][:2] and pair[0][2] is None)
    elif kind == "resolve":
        call = task["call"]
        for kind_, author, text in call["accept"] + call["reject"]:
            _pop(lost.get("revision", []), lambda f: (f[1], f[2], f[5]) == (kind_, author, text))
        for paragraph in call["paragraphs"]:
            s, before, after = paragraph["story"], paragraph["before"], paragraph["expected"]
            if before["original"] != after["original"]:
                allow_change("paragraph", (s, before["original"]), (s, after["original"]))
            allow_change("paragraph_current", (s, before["original"], before["current"]),
                         (s, after["original"], after["current"]))
            for pair in list(changed.get("revision", [])):
                f0, f1 = pair
                if f0[0] == s and f0[6] == before["original"] and f1[6] == after["original"] \
                        and f0[:6] == f1[:6]:
                    changed["revision"].remove(pair)
            for fact in [f for f in lost.get("list_item", []) if f[:2] == (s, before["original"])]:
                if _pop(added.get("list_item", []),
                        lambda f: f == (s, after["original"]) + fact[2:]):
                    lost["list_item"].remove(fact)
    # Anyone may be listed in people.xml; the editor or an existing author.
    authors = {f[0][0] for f in oracle.facts(source)["comment"]} | {name} | {
        f[2] for f in oracle.facts(source)["revision"]}
    drop(added, "person", lambda f: f[0] in authors)

    violations = {}
    for label, bucket in (("lost", lost), ("added", added), ("changed", changed)):
        for category, items in bucket.items():
            if category == "part" and label != "lost":
                continue
            if items:
                violations.setdefault(category, {})[label] = items
    if extra.get("attribution"):
        violations["attribution"] = {"problems": extra["attribution"]}
    package = {label: report[label].get("part", []) for label in ("added", "changed")}
    return {"preserved": not violations, "violations": violations,
            "package_changes": {k: v for k, v in package.items() if v},
            "anchor_follows_edit": extra.get("anchor_follows_edit")}


# --- completion -----------------------------------------------------------------

def completion(task: dict, source: Path, output: Path, editor: dict) -> dict:
    kind, call, name = task["kind"], task.get("call"), editor["author"]
    if kind == "save":
        return {"completed": True}
    if kind == "replace":
        paragraph = _find(output, call["story"], call["expected"]["current"], call["expected"]["original"])
        if paragraph is None:
            return {"completed": False, "reason": "no paragraph with the expected texts"}
        mine = [e for e in paragraph.iter(*(W + t for t in oracle.TEXT_REVISIONS))
                if e.get(W + "author") == name]
        elsewhere = [f for f in oracle.facts(output)["revision"]
                     if f[2] == name and not (f[0] == call["story"]
                                              and f[6] == call["expected"]["original"])]
        if task["mode"] == "tracked" and (not mine or elsewhere):
            return {"completed": False, "reason": "tracked edit missing or outside the target"}
        if task["mode"] == "plain" and (mine or elsewhere):
            return {"completed": False, "reason": "plain edit recorded revisions"}
        return {"completed": True}
    facts = oracle.facts(output)
    if kind == "comment":
        reply = [k for k in facts["comment"] if k[0] == name and k[2] == call["reply"]]
        threaded = [t for t in facts["comment_thread"]
                    if t[0][0] == name and t[0][2] == call["reply"] and t[1] and t[1][2] == call["reply_to"]]
        anchored = [a for a in facts["comment_anchor"] if a[0][0] == name
                    and a[0][2] == call["comment"] and a[1] == call["anchor"]["story"]
                    and a[3] == call["anchor"]["text"] and all(a[4:7])]
        done = bool(reply and threaded and anchored)
        return {"completed": done, "reply": bool(reply), "threaded": bool(threaded),
                "anchored": bool(anchored)}
    named = call["accept"] + call["reject"]
    remaining = [n for n in named if any((f[1], f[2], f[5]) == tuple(n) for f in facts["revision"])]
    texts = [p for p in call["paragraphs"] if _find(output, p["story"], p["expected"]["current"],
                                                    p["expected"]["original"]) is None]
    return {"completed": not remaining and not texts, "unresolved": remaining,
            "paragraphs_not_found": len(texts)}


# --- checker ----------------------------------------------------------------------

def checker(source: Path, output: Path, python: str) -> dict:
    def run(*args):
        result = subprocess.run([python, "-m", "ooxml_integrity", *map(str, args),
                                 "--no-config", "--json"], capture_output=True, text=True)
        assert result.returncode in (0, 1), result.stderr
        report = json.loads(result.stdout)
        return report["version"], report["files"][0]["findings"]
    version, baseline = run("check", source)
    _, found = run("check", output, "--against", source)
    known = {(f["code"], f["message"]) for f in baseline}
    actionable = [f for f in found if f["severity"] in ("error", "warn")
                  and (f["code"], f["message"]) not in known]
    return {"version": version, "findings": found, "new_actionable": actionable}


def detection(preserved: dict, checked: dict) -> dict:
    codes = [f["code"] for f in checked["new_actionable"]]
    failed = not preserved["preserved"]
    outcome = ("detected" if codes else "missed") if failed else (
        "false_alarm" if codes else "clean")
    by_category = {category: any(code.startswith(RULES.get(category, ())) for code in codes)
                   for category in preserved["violations"]} if failed else {}
    return {"outcome": outcome, "codes": sorted(set(codes)), "by_category": by_category}


def evaluate(task: dict, output: Path | None, status: str, editor: dict,
             python: str | None = None) -> dict:
    result = {"task": task["id"], "status": status}
    if status != "ok" or output is None:
        return result
    source = ROOT / task["source_path"]
    result.update(completion(task, source, output, editor))
    result["preservation"] = preservation(task, source, output, editor)
    if python:
        checked = checker(source, output, python)
        result["checker"] = checked
        result["detection"] = detection(result["preservation"], checked)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("evaluate")
    one.add_argument("task")
    one.add_argument("output", type=Path)
    one.add_argument("--checker", default=sys.executable)
    args = parser.parse_args(argv)
    declared = json.loads(TASKS.read_text(encoding="utf-8"))
    task = next(t for t in declared["tasks"] if t["id"] == args.task)
    result = evaluate(task, args.output, "ok", declared["editor"], args.checker)
    print(json.dumps(oracle._jsonable(result), indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
