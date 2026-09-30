#!/usr/bin/env python3
"""Reference adapter for the review-history benchmark: a careful XML editor.

It performs every declared task directly on the package XML, the way Word
records it, and is the positive control for the evaluator: each of its outputs
must complete its task and preserve everything else. It is not a benchmarked
tool. It does not import the checker.

    python research/review_history_reference.py TASK_ID OUTPUT
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import zipfile
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import review_history_oracle as oracle  # noqa: E402

W = oracle.W
W14, W15 = oracle.W14, oracle.W15
W16CID, W16CEX = oracle.W16CID, oracle.W16CEX
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
MS = "http://schemas.microsoft.com/office/2011/relationships/"
CT_NS = "{http://schemas.openxmlformats.org/package/2006/content-types}"
TASKS = ROOT / "evidence" / "review-history-benchmark" / "tasks.json"


class Editor:
    def __init__(self, source: Path, editor: dict):
        self.pkg = oracle.Package(source)
        self.editor = editor
        self.roots = {name: (part, root) for name, part, root in oracle.stories(self.pkg)}
        self.touched: set[str] = set()
        self.next_id = 1 + max((int(e.get(W + "id")) for _, root in self.roots.values()
                                for e in root.iter() if (e.get(W + "id") or "").isdigit()),
                               default=0)

    # --- helpers ------------------------------------------------------------

    def new_id(self) -> str:
        self.next_id += 1
        return str(self.next_id)

    def attrs(self) -> dict:
        return {W + "id": self.new_id(), W + "author": self.editor["author"],
                W + "date": self.editor["date"]}

    def story(self, name):
        part, root = self.roots[name]
        self.touched.add(part)
        return root

    def paragraph(self, story, current):
        found = [p for p in self.story(story).iter(W + "p")
                 if oracle.paragraph_text(p, "current") == current]
        assert len(found) == 1, (story, current, len(found))
        return found[0]

    def span(self, paragraph, text):
        """Split runs so that `text` in the current view is whole runs; return them."""
        nodes = [n for n in oracle._own(paragraph) if n.tag == W + "t"
                 and not oracle._in(n, oracle.REMOVED | {W + "pPrChange", W + "rPrChange"})]
        joined = "".join(n.text or "" for n in nodes)
        assert joined.count(text) == 1, (joined, text)
        start = joined.index(text)
        end = start + len(text)
        runs, offset = [], 0
        for node in nodes:
            length = len(node.text or "")
            lo, hi = max(start - offset, 0), min(end - offset, length)
            offset += length
            if lo >= hi:
                continue
            if hi < length:
                _split(node, hi)
            if lo > 0:
                node = _split(node, lo)
            runs.append(node.getparent())
        parents = {r.getparent() for r in runs}
        assert len(parents) == 1, "span crosses containers"
        return runs

    # --- tasks ----------------------------------------------------------------

    def replace(self, call, tracked: bool):
        paragraph = self.paragraph(call["story"], call["paragraph_current"])
        runs = self.span(paragraph, call["old"])
        parent = runs[0].getparent()
        new_run = copy.deepcopy(runs[0])
        for child in [c for c in new_run if c.tag != W + "rPr"]:
            new_run.remove(child)
        t = etree.SubElement(new_run, W + "t")
        t.text = call["new"]
        t.set(XML_SPACE, "preserve")
        if not tracked:
            runs[0].addprevious(new_run)
            for run in runs:
                parent.remove(run)
            return
        deletion = etree.Element(W + "del", self.attrs())
        runs[0].addprevious(deletion)
        for run in runs:
            deletion.append(run)
            for node in run.iter(W + "t"):
                node.tag = W + "delText"
                node.set(XML_SPACE, "preserve")
        insertion = etree.Element(W + "ins", self.attrs())
        insertion.append(new_run)
        if parent.tag == W + "ins":
            # An insertion cannot hold another: split the other author's one.
            rest = etree.Element(W + "ins", dict(parent.attrib, **{W + "id": self.new_id()}))
            for sibling in list(deletion.itersiblings()):
                rest.append(sibling)
            parent.addnext(insertion)
            if len(rest):
                insertion.addnext(rest)
        else:
            deletion.addnext(insertion)

    def resolve(self, call):
        for action in ("accept", "reject"):
            for kind, author, text in call[action]:
                hits = [(name, e) for name in self.roots for e in self.roots[name][1].iter(W + kind)
                        if e.get(W + "author") == author and oracle.payload(e) == text]
                assert len(hits) == 1, (kind, author, text)
                name, node = hits[0]
                self.story(name)
                if (kind == "ins") == (action == "accept"):
                    for deleted in node.iter(W + "delText"):
                        if not any(a.tag == W + "del" and a is not node for a in deleted.iterancestors()):
                            deleted.tag = W + "t"
                    _unwrap(node)
                else:
                    node.getparent().remove(node)

    def comment(self, call):
        comments_part = self.pkg.first("comments")
        comments = self.pkg.xml(comments_part)
        self.touched.add(comments_part)
        extended_part = self.pkg.first("commentsExtended") or self._add_part(
            "word/commentsExtended.xml", MS + "commentsExtended",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtended+xml",
            f'<w15:commentsEx xmlns:w15="{W15[1:-1]}"/>')
        extended = self.pkg.xml(extended_part)
        self.touched.add(extended_part)
        parent = next(c for c in comments.iter(W + "comment")
                      if oracle.text(c, "current").strip() == call["reply_to"])
        parent_para = _para_id(parent, self._hex)
        if not any(e.get(W15 + "paraId") == parent_para for e in extended):
            etree.SubElement(extended, W15 + "commentEx",
                             {W15 + "paraId": parent_para, W15 + "done": "0"})
        reply_id, reply_para = self._comment(comments, extended, call["reply"], parent_para)
        new_id, _ = self._comment(comments, extended, call["comment"], None)
        story = self.story("document")
        pid = parent.get(W + "id")
        start = next(n for n in story.iter(W + "commentRangeStart") if n.get(W + "id") == pid)
        end = next(n for n in story.iter(W + "commentRangeEnd") if n.get(W + "id") == pid)
        reference = next(n for n in story.iter(W + "commentReference") if n.get(W + "id") == pid)
        start.addnext(etree.Element(W + "commentRangeStart", {W + "id": reply_id}))
        end.addnext(etree.Element(W + "commentRangeEnd", {W + "id": reply_id}))
        reference.getparent().addnext(_reference_run(reply_id))
        anchor = call["anchor"]
        runs = self.span(self.paragraph(anchor["story"], anchor["paragraph_current"]), anchor["text"])
        runs[0].addprevious(etree.Element(W + "commentRangeStart", {W + "id": new_id}))
        runs[-1].addnext(etree.Element(W + "commentRangeEnd", {W + "id": new_id}))
        runs[-1].getnext().addnext(_reference_run(new_id))
        people_part = self.pkg.first("people")
        if people_part:
            people = self.pkg.xml(people_part)
            self.touched.add(people_part)
            if not any(p.get(W15 + "author") == self.editor["author"] for p in people):
                person = etree.SubElement(people, W15 + "person", {W15 + "author": self.editor["author"]})
                etree.SubElement(person, W15 + "presenceInfo",
                                 {W15 + "providerId": "None", W15 + "userId": self.editor["author"]})

    def _comment(self, comments, extended, text, parent_para):
        cid = self.new_id()
        para = self._hex()
        node = etree.SubElement(comments, W + "comment", {
            W + "id": cid, W + "author": self.editor["author"], W + "date": self.editor["date"],
            W + "initials": self.editor["initials"]})
        paragraph = etree.SubElement(node, W + "p", {W14 + "paraId": para, W14 + "textId": "77777777"})
        run = etree.SubElement(paragraph, W + "r")
        etree.SubElement(run, W + "annotationRef")
        run = etree.SubElement(paragraph, W + "r")
        t = etree.SubElement(run, W + "t")
        t.text = text
        attrs = {W15 + "paraId": para, W15 + "done": "0"}
        if parent_para:
            attrs = {W15 + "paraId": para, W15 + "paraIdParent": parent_para, W15 + "done": "0"}
        etree.SubElement(extended, W15 + "commentEx", attrs)
        for kind, tag, attrs in (
                ("commentsIds", W16CID + "commentId", lambda d: {W16CID + "paraId": para,
                                                                 W16CID + "durableId": d}),
                ("commentsExtensible", W16CEX + "commentExtensible",
                 lambda d: {W16CEX + "durableId": d, W16CEX + "dateUtc": self.editor["date"]})):
            part = self.pkg.first(kind)
            if part:
                self.touched.add(part)
                etree.SubElement(self.pkg.xml(part), tag, attrs(_durable(para)))
        return cid, para

    def _hex(self) -> str:
        self.next_id += 1
        return hashlib.sha256(f"para-{self.next_id}".encode()).hexdigest()[:8].upper()

    def _add_part(self, name, rel_type, content_type, xml) -> str:
        self.pkg.parts[name] = xml.encode()
        rels_name = "word/_rels/document.xml.rels"
        rels = self.pkg.xml(rels_name)
        ids = {r.get("Id") for r in rels}
        rid = next(f"rId{n}" for n in range(1, 10000) if f"rId{n}" not in ids)
        etree.SubElement(rels, oracle.REL + "Relationship",
                         {"Id": rid, "Type": rel_type, "Target": name.split("/", 1)[1]})
        self.touched.add(rels_name)
        types = self.pkg.xml("[Content_Types].xml")
        etree.SubElement(types, CT_NS + "Override", {"PartName": "/" + name, "ContentType": content_type})
        self.touched.add("[Content_Types].xml")
        return name

    def save(self, output: Path):
        parts = dict(self.pkg.parts)
        for name in self.touched:
            parts[name] = etree.tostring(self.pkg.xml(name), xml_declaration=True,
                                         encoding="UTF-8", standalone=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in parts.items():
                z.writestr(name, data)


def _split(t_node, offset):
    """Split the run holding `t_node` so its text from `offset` starts a new run."""
    run = t_node.getparent()
    right = copy.deepcopy(run)
    index = list(run).index(t_node)
    for child in list(right)[:index]:
        if child.tag != W + "rPr":
            right.remove(child)
    right_t = [c for c in right if c.tag == W + "t"][0]
    for child in list(run)[index + 1:]:
        run.remove(child)
    right_t.text = (t_node.text or "")[offset:]
    t_node.text = (t_node.text or "")[:offset]
    for node in (t_node, right_t):
        node.set(XML_SPACE, "preserve")
    run.addnext(right)
    return right_t


def _unwrap(node):
    parent, index = node.getparent(), node.getparent().index(node)
    for child in reversed(list(node)):
        parent.insert(index, child)
    parent.remove(node)


def _reference_run(cid):
    # No CommentReference character style: the source may not define it.
    run = etree.Element(W + "r")
    etree.SubElement(run, W + "commentReference", {W + "id": cid})
    return run


def _para_id(comment, make):
    paragraph = comment.findall(W + "p")[-1]
    if paragraph.get(W14 + "paraId") is None:
        paragraph.set(W14 + "paraId", make())
    return paragraph.get(W14 + "paraId")


def _durable(para):
    return hashlib.sha256(f"durable-{para}".encode()).hexdigest()[:8].upper()


def perform(task: dict, editor: dict, output: Path) -> Path:
    source = ROOT / task["source_path"]
    if task["kind"] == "save":
        output.write_bytes(source.read_bytes())
        return output
    edit = Editor(source, editor)
    if task["kind"] == "replace":
        edit.replace(task["call"], task["mode"] == "tracked")
    elif task["kind"] == "comment":
        edit.comment(task["call"])
    elif task["kind"] == "resolve":
        edit.resolve(task["call"])
    edit.save(output)
    return output


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("task")
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    declared = json.loads(TASKS.read_text(encoding="utf-8"))
    task = next(t for t in declared["tasks"] if t["id"] == args.task)
    print(perform(task, declared["editor"], args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
