#!/usr/bin/env python3
"""Task declarations for the review-history benchmark (DRAFT, not yet frozen).

One declaration per source and task gives a structured call for deterministic
tools and a prompt for agents. `write` validates every target against its
source and computes the expected text of each affected paragraph in both
oracle views, then writes tasks.json; nothing is typed in by hand.

    python research/review_history_tasks.py write

A target paragraph is named by its story and its current (accept-all) text,
which must be unique in that story; the text to edit must occur once in it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import review_history_oracle as oracle  # noqa: E402

EVIDENCE = ROOT / "evidence" / "review-history-benchmark"
TASKS = EVIDENCE / "tasks.json"
SOURCES = {
    "S1": "corpus/base.docx",
    "S2": "evidence/review-history-benchmark/sources/word-review.docx",
}
EDITOR = {"author": "Benchmark Editor", "initials": "BE", "date": "2026-10-01T00:00:00Z"}
REPLACE_MODES = ("tracked", "plain")

#: (task, source) -> declaration. `where` is (story, paragraph current text).
DECLARED = {
    ("K0", "S1"): {"kind": "save"},
    ("K0", "S2"): {"kind": "save"},
    ("K1", "S1"): {"kind": "replace", "where": ("document",
        "This agreement governs the provision of services described in Schedule A. "
        "The Effective Date is the date of last signature."),
        "old": "Effective Date", "new": "Commencement Date",
        "place": "the opening paragraph, inside the range of the comment "
                 "'Defined term must match the definitions schedule.'"},
    ("K1", "S2"): {"kind": "replace", "where": ("document",
        "The Consultant shall provide the Services from the Effective Date until the Completion Date."),
        "old": "Completion Date", "new": "Expiry Date",
        "place": "clause 1 (Term), inside the range of the comment thread "
                 "'Completion Date is not defined.'"},
    ("K2", "S1"): {"kind": "replace", "where": ("document", "EUR 12,000"),
        "old": "EUR 12,000", "new": "EUR 12,500",
        "place": "the Fee cell of the Discovery row, which carries the comment "
                 "'Confirm this figure against the source table before circulation.'"},
    ("K2", "S2"): {"kind": "replace", "where": ("document", "EUR 12,000"),
        "old": "EUR 12,000", "new": "EUR 12,500",
        "place": "the Fee cell of the Discovery row, which carries the resolved comment "
                 "'Check this against the approved budget.'"},
    ("K3", "S1"): {"kind": "replace", "where": ("document", "Historic spend is shown below."),
        "old": "Historic spend", "new": "Annual spend",
        "place": "the sentence before the chart, which ends with footnote 2"},
    ("K3", "S2"): {"kind": "replace", "where": ("document",
        "The Consultant shall deliver a monthly progress report within ten business days "
        "after the end of each month."),
        "old": "ten business days", "new": "fifteen business days",
        "place": "clause 3 (Reporting), which ends with a footnote"},
    ("K4", "S1"): {"kind": "replace", "where": ("document",
        "The Supplier shall maintain professional indemnity insurance."),
        "old": "professional indemnity insurance", "new": "professional liability insurance",
        "place": "the list item that A. Counsel inserted as a pending tracked change",
        "inside_insertion": True},
    ("K4", "S2"): {"kind": "replace", "where": ("document",
        "Fees are payable within forty-five days of receipt of a valid invoice. "
        "The Client may withhold disputed amount."),
        "old": "disputed amount", "new": "disputed sum",
        "place": "clause 4 (Fees), inside the sentence Reviewer A inserted, next to "
                 "Reviewer B's pending deletion of 'any'",
        "inside_insertion": True},
    ("K5", "S1"): {"kind": "comment",
        "reply_to": "Defined term must match the definitions schedule.",
        "reply": "Checked against the definitions schedule.",
        "anchor": ("document", "Invoices are payable within 30 days.", "30 days"),
        "comment": "Confirm the payment term with finance."},
    ("K5", "S2"): {"kind": "comment",
        "reply_to": "Completion Date is not defined.",
        "reply": "Schedule 1 now defines it.",
        "anchor": ("document", "Either party may terminate this agreement on sixty days' "
                   "written notice.", "sixty days"),
        "comment": "Check the notice period with the client."},
    ("K6", "S1"): {"kind": "resolve",
        "accept": [("ins", "A. Counsel", "The Supplier shall maintain professional indemnity insurance.")],
        "reject": [("del", "A. Counsel", "EUR 40,000 ")]},
    ("K6", "S2"): {"kind": "resolve",
        "accept": [("ins", "Reviewer A", "forty-five")],
        "reject": [("del", "Reviewer B", "any ")]},
    ("K7h", "S1"): {"kind": "replace", "where": ("header/default/1", "Reference Agreement - Draft 7"),
        "old": "Draft 7", "new": "Draft 8", "place": "the page header"},
    ("K7h", "S2"): {"kind": "replace", "where": ("header/default/1",
        "Consulting Services Agreement - Draft 4"),
        "old": "Consulting Services", "new": "Consultancy Services",
        "place": "the page header, which carries Reviewer A's pending change of the draft number"},
    ("K7n", "S1"): {"kind": "replace", "where": ("footnotes",
        " ECMA-376 Part 1, 5th edition, section 17.3.1."),
        "old": "section 17.3.1", "new": "section 17.3.2", "place": "the text of footnote 1"},
    ("K7n", "S2"): {"kind": "replace", "where": ("footnotes",
        " Business days exclude public holidays in England and Wales."),
        "old": "England and Wales", "new": "Scotland", "place": "the text of the footnote"},
}


def _paragraphs(path, story):
    pkg = oracle.Package(ROOT / path)
    root = next(r for name, _, r in oracle.stories(pkg) if name == story)
    return [p for p in root.iter(oracle.W + "p")]


def _target(path, story, current, paragraphs=None):
    paragraphs = _paragraphs(path, story) if paragraphs is None else paragraphs
    found = [p for p in paragraphs if oracle.paragraph_text(p, "current") == current]
    assert len(found) == 1, (path, story, current, len(found))
    return found[0]


def _unique_context(path, story, paragraph, paragraphs):
    """No other paragraph with revisions shares the target's rejected text, so
    facts that carry it as context belong to the target alone."""
    original = oracle.paragraph_text(paragraph, "original")
    revised = oracle.TEXT_REVISIONS + oracle.PROPERTY_REVISIONS
    twins = [p for p in paragraphs if p is not paragraph
             and oracle.paragraph_text(p, "original") == original
             and next(p.iter(*(oracle.W + t for t in revised)), None) is not None]
    assert not twins, (path, story, original)


def _replace(task, source, spec, mode):
    story, current = spec["where"]
    paragraphs = _paragraphs(SOURCES[source], story)
    paragraph = _target(SOURCES[source], story, current, paragraphs)
    _unique_context(SOURCES[source], story, paragraph, paragraphs)
    original = oracle.paragraph_text(paragraph, "original")
    assert current.count(spec["old"]) == 1, (task, source, spec["old"])
    inside = spec.get("inside_insertion", False)
    # A direct edit inside another author's pending insertion stays inside it,
    # so the rejected view keeps the source text in both modes.
    if mode == "plain" and not inside:
        assert original.count(spec["old"]) == 1, (task, source, "old text not in plain region")
        expected_original = original.replace(spec["old"], spec["new"])
    else:
        expected_original = original
    return {"story": story, "paragraph_current": current, "paragraph_original": original,
            "old": spec["old"], "new": spec["new"],
            "expected": {"current": current.replace(spec["old"], spec["new"]),
                         "original": expected_original},
            "new_revisions_by_editor": mode == "tracked"}


def _prompt(task, source, spec, mode):
    kind = spec["kind"]
    if kind == "save":
        return "Open the document and save it without making any change."
    if kind == "replace":
        how = (f"Record the change as a tracked change by the author '{EDITOR['author']}'."
               if mode == "tracked" else "Make the change directly, without tracked changes.")
        return (f"In {spec['place']}, replace '{spec['old']}' with '{spec['new']}'. {how} "
                "Do not change anything else.")
    if kind == "comment":
        story, sentence, phrase = spec["anchor"]
        end = lambda quoted: f"'{quoted}'" + ("" if quoted.endswith(".") else ".")  # noqa: E731
        return (f"As '{EDITOR['author']}', reply to the comment '{spec['reply_to']}' with "
                f"{end(spec['reply'])} Then add a new comment on '{phrase}' in the sentence "
                f"'{sentence}' with the text {end(spec['comment'])} Do not change anything else.")
    accept = "; ".join(f"{a}'s {'insertion' if k == 'ins' else 'deletion'} of '{t.strip()}'"
                       for k, a, t in spec["accept"])
    reject = "; ".join(f"{a}'s {'insertion' if k == 'ins' else 'deletion'} of '{t.strip()}'"
                       for k, a, t in spec["reject"])
    return (f"Accept {accept}. Reject {reject}. Leave every other tracked change and every "
            "comment as it is. Do not change anything else.")


def _resolve(source, spec):
    """Accept and reject the named revisions on a copy of the source; record the
    texts of every paragraph that changes."""
    pkg = oracle.Package(ROOT / SOURCES[source])
    roots = {name: root for name, _, root in oracle.stories(pkg)}
    before = {name: [(p, oracle.paragraph_text(p, "original"), oracle.paragraph_text(p, "current"))
                     for p in root.iter(oracle.W + "p")] for name, root in roots.items()}
    for action, items in (("accept", spec["accept"]), ("reject", spec["reject"])):
        for kind, author, text in items:
            hits = [(name, e) for name, root in roots.items() for e in root.iter(oracle.W + kind)
                    if e.get(oracle.W + "author") == author and oracle.payload(e) == text]
            assert len(hits) == 1, (source, kind, author, text, len(hits))
            node = hits[0][1]
            keep = (kind == "ins") == (action == "accept")
            if keep:
                for deleted in node.iter(oracle.W + "delText"):
                    if not any(a.tag == oracle.W + "del" and a is not node
                               for a in deleted.iterancestors()):
                        deleted.tag = oracle.W + "t"
                parent, index = node.getparent(), node.getparent().index(node)
                for child in reversed(list(node)):
                    parent.insert(index, child)
            node.getparent().remove(node)
    changed = []
    for name, paragraphs in before.items():
        for p, original, current in paragraphs:
            after = (oracle.paragraph_text(p, "original"), oracle.paragraph_text(p, "current"))
            if after != (original, current):
                changed.append({"story": name, "before": {"original": original, "current": current},
                                "expected": {"original": after[0], "current": after[1]}})
    return {"accept": [list(x) for x in spec["accept"]], "reject": [list(x) for x in spec["reject"]],
            "paragraphs": changed}


def _comment(source, spec):
    comments = oracle.facts(ROOT / SOURCES[source])["comment"]
    assert sum(1 for c in comments if c[2] == spec["reply_to"]) == 1, spec["reply_to"]
    story, sentence, phrase = spec["anchor"]
    _target(SOURCES[source], story, sentence)
    assert sentence.count(phrase) == 1
    return {"reply_to": spec["reply_to"], "reply": spec["reply"],
            "anchor": {"story": story, "paragraph_current": sentence, "text": phrase},
            "comment": spec["comment"]}


def declarations() -> list[dict]:
    out = []
    for (task, source), spec in sorted(DECLARED.items()):
        modes = REPLACE_MODES if spec["kind"] == "replace" else (spec["kind"],)
        for mode in modes:
            entry = {"id": f"{task}-{source}-{mode}", "task": task, "source": source,
                     "source_path": SOURCES[source], "kind": spec["kind"], "mode": mode,
                     "prompt": _prompt(task, source, spec, mode)}
            if spec["kind"] == "replace":
                entry["call"] = _replace(task, source, spec, mode)
            elif spec["kind"] == "comment":
                entry["call"] = _comment(source, spec)
            elif spec["kind"] == "resolve":
                entry["call"] = _resolve(source, spec)
            out.append(entry)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["write", "show"])
    args = parser.parse_args(argv)
    record = {"status": "draft", "editor": EDITOR, "tasks": declarations()}
    text = json.dumps(record, indent=2, ensure_ascii=False) + "\n"
    if args.command == "write":
        TASKS.write_text(text, encoding="utf-8")
    print(text if args.command == "show" else f"{len(record['tasks'])} declarations -> {TASKS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
