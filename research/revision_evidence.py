#!/usr/bin/env python3
"""Existing-revision fixtures. Build/label without importing the checker.

Captured external editor outputs are immutable inputs to evaluation. Rebuilding
seeded defects needs only lxml; rerunning adeu is an explicit capture operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from lxml import etree as E

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "evidence" / "docx-revisions"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NS = {"w": W[1:-1]}
MAIN = "word/document.xml"
PROFILES = ("basic", "nested", "table", "notes", "stories")
DATE = "2026-09-12T00:00:00Z"
LABEL_FILES = ("labels.json", "labels-online.json")


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def declared_cases():
    return [case for name in LABEL_FILES for case in json.loads((BASE / name).read_text(encoding="utf-8"))]


def read(path):
    with ZipFile(path) as z:
        return {name: z.read(name) for name in z.namelist()}


def write(parts, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w") as z:
        for name, blob in sorted(parts.items()):
            info = ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_STORED
            info.create_system = 0
            info.external_attr = 0o600 << 16
            z.writestr(info, blob)


def xml(root):
    return E.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)


def run(text, deleted=False):
    tag = "delText" if deleted else "t"
    return f'<w:r><w:{tag} xml:space="preserve">{text}</w:{tag}></w:r>'


def rev(kind, ident, text, author="Reviewer A"):
    return (f'<w:{kind} w:id="{ident}" w:author="{author}" w:date="{DATE}">'
            f'{run(text, kind == "del")}</w:{kind}>')


def source_parts(profile):
    # Reuse the MIT reference package's styles, relationships and diagram.
    # No original file is edited. All replacement prose and authors are invented.
    parts = read(ROOT / "corpus/base.docx")
    namespace = f'xmlns:w="{W[1:-1]}"'
    p = lambda text: f"<w:p>{run(text)}</w:p>"
    body = ('<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr>'
            + run("Existing revision preservation") + "</w:p>")
    body += p(f"Fixture profile {profile}")
    body += ('<w:p>' + run("The cycle marker is EDITBEFORE. The service is ")
             + rev("ins", "101", "renewable") + run(" and ")
             + rev("ins", "103", "optional", "Reviewer B") + run(".") + "</w:p>")
    body += "<w:p>" + run("The review is") + rev("del", "102", " retired", "Reviewer B") + run(" complete.") + "</w:p>"
    body += p("Keep the agreed delivery, ownership and review terms available to the next reviewer. "
              "The schedule remains subject to written approval. Each participant can examine the "
              "pending wording before deciding whether to retain or resolve a change. "
              "A nearby editorial update must preserve the existing review record and its authors.")
    body += ('<w:p><w:commentRangeStart w:id="1"/>' + run("Review the delivery terms.")
             + '<w:commentRangeEnd w:id="1"/><w:r><w:commentReference w:id="1"/></w:r>'
             + '<w:r><w:footnoteReference w:id="1"/></w:r></w:p>')
    if profile == "nested":
        body += ('<w:p>' + run("Pending nested wording: ")
                 + f'<w:ins w:id="201" w:author="Reviewer A" w:date="{DATE}">'
                 + run("current ") + rev("del", "202", "former ", "Reviewer B")
                 + run("term") + "</w:ins></w:p>")
    cell = (rev("del", "301", "old ") + rev("ins", "302", "new ", "Reviewer B")
            if profile == "table" else run("Scheduled "))
    body += ('<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/></w:tblPr>'
             '<w:tblGrid><w:gridCol w:w="4600"/><w:gridCol w:w="4600"/></w:tblGrid>'
             '<w:tr><w:trPr><w:tblHeader/></w:trPr><w:tc>' + p("Milestone") + "</w:tc><w:tc>"
             + p("Status") + "</w:tc></w:tr><w:tr><w:tc>" + p("Delivery")
             + "</w:tc><w:tc><w:p>" + cell + run("review") + "</w:p></w:tc></w:tr></w:tbl>")
    original = E.fromstring(parts[MAIN])
    section = xml(original.find("w:body/w:sectPr", NS)).decode().split("?>", 1)[1]
    parts[MAIN] = xml(E.fromstring(f'<w:document {namespace} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>{body}{section}</w:body></w:document>'))
    note = run("The review record includes ") + (rev("ins", "401", "retained ") if profile == "notes" else run("retained ")) + run("supporting information.")
    parts["word/footnotes.xml"] = xml(E.fromstring(f'<w:footnotes {namespace}><w:footnote w:id="-1" w:type="separator"><w:p><w:r><w:separator/></w:r></w:p></w:footnote><w:footnote w:id="0" w:type="continuationSeparator"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote><w:footnote w:id="1"><w:p>{note}</w:p></w:footnote></w:footnotes>'))
    parts["word/comments.xml"] = xml(E.fromstring(f'<w:comments {namespace}><w:comment w:id="1" w:author="Reviewer C" w:initials="RC" w:date="{DATE}">{p("Preserve this independent delivery comment.")}</w:comment></w:comments>'))
    for kind, tag in (("header", "hdr"), ("footer", "ftr")):
        extra = ""
        if profile == "stories":
            extra = rev("ins", "501", "pending ") if kind == "header" else rev("del", "502", "former ", "Reviewer B")
        parts[f"word/{kind}1.xml"] = xml(E.fromstring(f'<w:{tag} {namespace}><w:p>{extra}{run("Review record " + kind)}</w:p></w:{tag}>'))
    styles = E.fromstring(parts["word/styles.xml"])
    styles.append(E.fromstring(f'<w:style {namespace} w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:color w:val="000000"/><w:sz w:val="32"/></w:rPr></w:style>'))
    parts["word/styles.xml"] = xml(styles)
    parts["docProps/core.xml"] = b'<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>Revision fixture builder</dc:creator><cp:lastModifiedBy>Revision fixture builder</cp:lastModifiedBy></cp:coreProperties>'
    parts["docProps/app.xml"] = b'<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>revision-fixture-builder 1</Application></Properties>'
    return parts


def labels():
    result = []

    def case(ident, profile, action, cohort, findings=(), losses=(), changes=(), correct=True, **extra):
        result.append(dict(id=ident, source=profile, action=action, cohort=cohort,
                           intent_correct=correct, allowed_revision_losses=list(losses),
                           allowed_text_changes=list(changes),
                           expected_findings=[dict(code=code, severity="ERROR", count=n) for code, n in findings],
                           **extra))

    for profile in PROFILES:
        case(f"{profile}-save", profile, "save", "external_editor")
        case(f"{profile}-edit", profile, "edit", "external_editor",
             changes=[(MAIN, "EDITBEFORE", "EDITAFTER")])
    defects = [
        ("duplicate-id", "basic", [("REV001", 1)]),
        ("deletion-uses-t", "basic", [("REV002", 1)]),
        ("insertion-uses-delText", "basic", [("REV003", 1)]),
        ("drop-insertion", "basic", [("FID001", 1)]),
        ("drop-deletion", "basic", [("FID001", 1)]),
        ("replace-unrelated-insertion", "basic", []),
        ("unwrap-note-insertion", "notes", []),
        ("unwrap-header-insertion", "stories", [("FID008", 1)]),
        ("drop-footer-deletion", "stories", [("FID008", 1)]),
    ]
    for action, profile, findings in defects:
        case(action, profile, action, "seeded_defect", findings, correct=False,
             known_miss=not bool(findings))
    for prefix in ("synthetic", "adeu"):
        case(f"{prefix}-partial-accept", "basic", "accept", "characterization",
             [("FID001", 1)], [(MAIN, "101")], producer=prefix)
        case(f"{prefix}-partial-reject", "basic", "reject", "characterization",
             [("FID001", 1)], [(MAIN, "102")], [(MAIN, "The review is complete.", "The review is retired complete.")], producer=prefix)
    case("synthetic-accept-table-replacement", "table", "accept-table", "characterization",
         [("FID001", 2)], [(MAIN, "301"), (MAIN, "302")], producer="synthetic")
    case("synthetic-accept-with-unrelated-loss", "basic", "accept-with-loss", "characterization",
         [("FID001", 1)], [(MAIN, "101")], correct=False, producer="synthetic")
    return result


def unwrap(el):
    parent = el.getparent()
    index = parent.index(el)
    for child in list(el):
        parent.insert(index, child)
        index += 1
    parent.remove(el)


def mutate(parts, action):
    parts = dict(parts)
    part = ({"unwrap-note-insertion": "word/footnotes.xml", "unwrap-header-insertion": "word/header1.xml", "drop-footer-deletion": "word/footer1.xml"}.get(action, MAIN))
    root = E.fromstring(parts[part])
    by_id = lambda ident: root.xpath(".//w:ins[@w:id=$id] | .//w:del[@w:id=$id]", namespaces=NS, id=ident)[0]
    if action == "duplicate-id":
        by_id("102").set(W + "id", "101")
    elif action in ("deletion-uses-t", "insertion-uses-delText"):
        el = by_id("102" if action == "deletion-uses-t" else "101")
        el[0][0].tag = W + ("t" if action == "deletion-uses-t" else "delText")
    elif action in ("drop-insertion", "drop-deletion", "drop-footer-deletion"):
        el = by_id({"drop-insertion": "101", "drop-deletion": "102", "drop-footer-deletion": "502"}[action])
        el.getparent().remove(el)
    elif action == "replace-unrelated-insertion":
        by_id("103")[0][0].text = "invented"
    elif action in ("unwrap-note-insertion", "unwrap-header-insertion", "accept", "accept-with-loss"):
        unwrap(by_id({"unwrap-note-insertion": "401", "unwrap-header-insertion": "501"}.get(action, "101")))
        if action == "accept-with-loss":
            el = by_id("103")
            el.getparent().remove(el)
    elif action == "reject":
        el = by_id("102")
        for t in el.iter(W + "delText"):
            t.tag = W + "t"
        unwrap(el)
    elif action == "accept-table":
        el = by_id("301")
        el.getparent().remove(el)
        unwrap(by_id("302"))
    else:
        raise ValueError(action)
    parts[part] = xml(root)
    return parts


def facts(parts):
    """Independent XML oracle: payloads, authors, nesting and accepted text.

    This deliberately does not import inspector/fidelity or compare tag counts.
    IDs locate declared review actions; matching payloads tolerates renumbering.
    """
    revisions, text, invalid, duplicates, protected = [], {}, [], [], {}
    # Office may renumber a note while keeping its reference and body paired.
    # Resolve references to their definitions; ignoring IDs without resolving
    # them would incorrectly bless a dangling or retargeted anchor.
    definitions = {}
    for kind, part in (("footnote", "word/footnotes.xml"), ("comment", "word/comments.xml")):
        definitions[kind] = {}
        if part in parts:
            for node in E.fromstring(parts[part]).iter(W + kind):
                definitions[kind][node.get(W + "id")] = (node.get(W + "type"), "".join(t.text or "" for t in node.iter(W + "t")))

    def attributes(node):
        attrs = dict(node.attrib)
        name = E.QName(node).localname
        kind = "footnote" if name in ("footnote", "footnoteReference") else "comment" if name.startswith("comment") else None
        if kind is not None and W + "id" in attrs:
            ident = attrs[W + "id"]
            attrs[W + "id"] = definitions[kind].get(ident, ("missing definition", ident))
        return sorted(attrs.items())
    for part, blob in sorted(parts.items()):
        if not part.startswith("word/") or not part.endswith(".xml"):
            continue
        root = E.fromstring(blob)
        local_ids = []
        for node in root.iter():
            if node.tag in (W + "ins", W + "del"):
                parents = tuple(E.QName(a).localname for a in node.iterancestors() if a.tag in (W + "ins", W + "del"))
                payload = "".join(t.text or "" for t in node.iter() if t.tag in (W + "t", W + "delText"))
                revisions.append(dict(part=part, id=node.get(W + "id"),
                                      signature=(part, E.QName(node).localname, node.get(W + "author"), node.get(W + "date"), parents, payload)))
                local_ids.append(node.get(W + "id"))
            if node.tag in (W + "t", W + "delText"):
                ancestor = next((a for a in node.iterancestors() if a.tag in (W + "ins", W + "del")), None)
                if ancestor is not None and ((ancestor.tag == W + "del") != (node.tag == W + "delText")):
                    invalid.append((part, ancestor.get(W + "id")))
        duplicates.extend((part, ident) for ident, n in Counter(local_ids).items() if ident is not None and n > 1)
        protected_tags = {W + name for name in ("commentRangeStart", "commentRangeEnd", "commentReference", "footnoteReference", "comment", "footnote", "tblGrid", "gridCol", "headerReference", "footerReference")}
        protected[part] = [(E.QName(node).localname, attributes(node)) for node in root.iter() if node.tag in protected_tags]
        paragraphs = []
        for p in root.iter(W + "p"):
            paragraphs.append("".join(t.text or "" for t in p.iter(W + "t")
                                      if not any(a.tag == W + "del" for a in t.iterancestors())))
        if paragraphs:
            text[part] = "\n".join(paragraphs)
    return dict(revisions=revisions, text=text, invalid=invalid, duplicates=duplicates, protected=protected)


def oracle(source, output, case):
    before, after = facts(source), facts(output)
    available = Counter(r["signature"] for r in after["revisions"])
    lost = []
    for r in before["revisions"]:
        if available[r["signature"]]:
            available[r["signature"]] -= 1
        else:
            lost.append((r["part"], r["id"]))
    expected_text = dict(before["text"])
    for part, old, new in case["allowed_text_changes"]:
        if expected_text[part].count(old) != 1:
            raise ValueError(f"ambiguous oracle text target: {case['id']}")
        expected_text[part] = expected_text[part].replace(old, new, 1)
    allowed = set(map(tuple, case["allowed_revision_losses"]))
    lost_set = set(lost)
    allowed_new = Counter()
    if case["cohort"] == "external_editor" and case["action"] == "edit":
        for part, old, new in case["allowed_text_changes"]:
            allowed_new[(part, "del", "Evidence Editor", (), old)] += 1
            allowed_new[(part, "ins", "Evidence Editor", (), new)] += 1
    unexpected_new = []
    for signature, count in available.items():
        part, kind, author, date, parents, payload = signature
        identity = (part, kind, author, parents, payload)
        accepted = min(count, allowed_new[identity])
        allowed_new[identity] -= accepted
        if count > accepted:
            unexpected_new.append((part, kind, author, payload, count - accepted))
    changes = [part for part in sorted(set(expected_text) | set(after["text"])) if expected_text.get(part) != after["text"].get(part)]
    violations = dict(unrelated_revision_losses=sorted(lost_set - allowed),
                      unresolved_requested_revisions=sorted(allowed - lost_set),
                      unexpected_new_revisions=unexpected_new,
                      missing_requested_tracked_edits=[(key, n) for key, n in allowed_new.items() if n],
                      unexpected_text_changes=changes,
                      changed_review_structures=[part for part in sorted(set(before["protected"]) | set(after["protected"])) if before["protected"].get(part) != after["protected"].get(part)],
                      invalid_revision_text=after["invalid"], duplicate_revision_ids=after["duplicates"])
    return dict(intent_correct=not any(violations.values()), lost_revisions=lost,
                violations=violations)


def prepare():
    BASE.mkdir(parents=True, exist_ok=True)
    declared = BASE / "labels.json"
    payload = json.dumps(labels(), indent=2) + "\n"
    if declared.exists() and declared.read_text() != payload:
        raise ValueError("Refusing to replace predeclared labels")
    declared.write_text(payload)
    for profile in PROFILES:
        write(source_parts(profile), BASE / "sources" / f"{profile}.docx")
    rebuild()


def rebuild(destination=BASE / "outputs"):
    for case in labels():
        if case["cohort"] == "external_editor" or case.get("producer") == "adeu":
            continue
        parts = read(BASE / "sources" / f"{case['source']}.docx")
        write(mutate(parts, case["action"]), destination / f"{case['id']}.docx")


def manifest():
    records = []
    declared = declared_cases()
    for case in declared:
        output = BASE / "outputs" / f"{case['id']}.docx"
        source = BASE / "sources" / f"{case['source']}.docx"
        external = case["cohort"] == "external_editor" or case.get("producer") == "adeu"
        online = case["cohort"] == "word_online"
        record = dict(case, source_path=str(source.relative_to(BASE)), output_path=str(output.relative_to(BASE)),
                      source_sha256=digest(source.read_bytes()), output_sha256=digest(output.read_bytes()),
                      producer_name="Microsoft Word for the web" if online else "adeu" if external else "revision-fixture-builder",
                      producer_version="2026-09-12 session; service build not exposed" if online else "3.0.4" if external else "1",
                      provenance="observed_word_online_edit" if online else "controlled_external_tool_run" if external else "synthetic_xml_mutation",
                      oracle=oracle(read(source), read(output), case))
        if record["oracle"]["intent_correct"] != case["intent_correct"]:
            raise ValueError(f"Editor contract mismatch: {case['id']}: {record['oracle']}")
        records.append(record)
    result = dict(schema_version=1, license="MIT", labels_sha256=digest((BASE / "labels.json").read_bytes()),
                  label_files_sha256={name: digest((BASE / name).read_bytes()) for name in LABEL_FILES},
                  source_producer="revision-fixture-builder 1; synthetic XML, not Office capture",
                  source_reference_sha256=digest((ROOT / "corpus/base.docx").read_bytes()),
                  pairs=records)
    (BASE / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def evaluate():
    # Import only at the explicitly requested checker stage, after labels.
    from ooxml_integrity.cli import _run_one
    from ooxml_integrity.archive import DEFAULT_ARCHIVE_LIMITS
    from ooxml_integrity import __version__

    data = json.loads((BASE / "manifest.json").read_text())
    if {name: digest((BASE / name).read_bytes()) for name in LABEL_FILES} != data["label_files_sha256"]:
        raise ValueError("labels drifted")
    declared = {case["id"]: case for case in declared_cases()}
    if len(data["pairs"]) != len(declared) or {c["id"] for c in data["pairs"]} != set(declared):
        raise ValueError("manifest case inventory drifted")
    for case in data["pairs"]:
        if {key: case.get(key) for key in declared[case["id"]]} != declared[case["id"]]:
            raise ValueError(f"manifest label drift: {case['id']}")
    groups = {}
    positive_rules = Counter()
    results = []
    for case in data["pairs"]:
        source, output = BASE / case["source_path"], BASE / case["output_path"]
        for path, key in ((source, "source_sha256"), (output, "output_sha256")):
            if digest(path.read_bytes()) != case[key]:
                raise ValueError(f"Hash mismatch: {path}")
        observed = oracle(read(source), read(output), case)
        if json.loads(json.dumps(observed)) != case["oracle"]:
            raise ValueError(f"Oracle drift: {case['id']}")
        findings = _run_one(output, source, DEFAULT_ARCHIVE_LIMITS)
        actual = Counter((f.code, f.severity.name) for f in findings if f.severity.name in ("ERROR", "WARN"))
        expected = Counter({(f["code"], f["severity"]): f["count"] for f in case["expected_findings"]})
        match = actual == expected
        initial = dict(pairs=0, label_mismatches=0)
        if case["cohort"] == "characterization":
            initial.update(excluded_from_preservation_metrics=True, correct_actions=0, incorrect_actions=0)
        else:
            initial.update(tp=0, fp=0, fn=0, tn=0)
        group = groups.setdefault(case["cohort"], initial)
        group["pairs"] += 1
        group["label_mismatches"] += not match
        if case["cohort"] != "characterization":
            group[("fp" if actual else "tn") if case["intent_correct"] else ("tp" if actual else "fn")] += 1
            if not case["intent_correct"]:
                positive_rules.update(code for code, severity in expected)
        else:
            group["correct_actions" if observed["intent_correct"] else "incorrect_actions"] += 1
        results.append(dict(id=case["id"], matches_expected_checker=match,
                            intent_correct=observed["intent_correct"],
                            actionable_findings=[dict(code=c, severity=s, count=n) for (c, s), n in sorted(actual.items())]))
    inventory = set()
    for path in (ROOT / "src/ooxml_integrity").glob("*.py"):
        inventory.update(re.findall(r'''["']([A-Z]{3}\d{3})["']''', path.read_text(encoding="utf-8")))
    return dict(checker_version=__version__, metric_unit="document pair; actionable ERROR/WARN", groups=groups,
                rules_with_seeded_positive_cases=dict(sorted(positive_rules.items())),
                rules_without_positive_cases=sorted(code for code in inventory - set(positive_rules) if not code.startswith("PPT")),
                cases=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "rebuild", "manifest", "evaluate"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "rebuild":
        rebuild()
    elif args.command == "manifest":
        manifest()
    else:
        result = evaluate()
        if args.write:
            (BASE / "metrics.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result["groups"], indent=2))
        return int(any(g["label_mismatches"] for g in result["groups"].values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
