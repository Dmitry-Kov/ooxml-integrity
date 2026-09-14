#!/usr/bin/env python3
"""Capture two pinned local DOCX adapters; evaluate separately, without network.

The bounded XML comparison implements evidence/docx-benchmark/PROTOCOL.md.
It is deliberately not a public semantic-diff or intentional-changes API.
"""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import io
import json
import platform
import subprocess
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from zipfile import BadZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import revision_evidence as revision
from lxml import etree as E

BASE = ROOT / "evidence/docx-benchmark"
PROTOCOL = BASE / "protocol.json"
W, NS, MAIN = revision.W, revision.NS, revision.MAIN
OLD, NEW, AUTHOR = "EDITBEFORE", "EDITAFTER", "Evidence Editor"
ADAPTERS = ("adeu-sdk-v1", "python-docx-run-v1")
SPACE = "{http://www.w3.org/XML/1998/namespace}space"
CORE_MUTABLE = {
    "{http://purl.org/dc/terms/}modified",
    "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}lastModifiedBy",
    "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}revision",
}


def digest(path):
    return revision.digest(Path(path).read_bytes())


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def save_json(path, value):
    # Exclusive creation: captures and evaluations are immutable receipts.
    with Path(path).open("xb") as stream:
        stream.write(json_bytes(value))


def utc():
    return datetime.now(timezone.utc).isoformat()


def tree_hash(directory):
    return revision.digest(json_bytes({str(p.relative_to(directory)): digest(p)
                                      for p in sorted(Path(directory).rglob("*.py"))}))


def frozen_protocol():
    data = json.loads(PROTOCOL.read_text())
    for name, expected in data["frozen_files"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Frozen protocol/oracle drift: {name}")
    for source in data["sources"].values():
        if digest(ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"Source drift: {source['path']}")
    return data


class Unsupported(Exception):
    """The declared adapter cannot address the input task."""


class Rejected(Exception):
    """The editing tool explicitly refused the operation."""


def edit_python_docx(source, output, action):
    from docx import Document

    document = Document(source)
    if action == "edit":
        matches = [run for paragraph in document.paragraphs
                   for run in paragraph.runs if OLD in run.text]
        if len(matches) != 1 or matches[0].text.count(OLD) != 1:
            raise Unsupported("Expected one direct body run containing the entire marker")
        run = matches[0]
        run.text = run.text.replace(OLD, NEW, 1)
    document.save(output)
    return {"replacement_count": 1 if action == "edit" else 0,
            "operation": "Document/Run.text/Document.save"}


def edit_adeu(source, output, action):
    from adeu import ModifyText, RedlineEngine

    engine = RedlineEngine(io.BytesIO(source.read_bytes()), author=AUTHOR)
    stats = None
    parameters = None
    if action == "edit":
        change = ModifyText(target_text=OLD, new_text=NEW, match_mode="strict",
                            regex=False, comment=None)
        parameters = change.model_dump()
        try:
            stats = engine.process_batch([change], partial=False)
        except Exception as exc:
            # Only adeu's explicit batch rejection is a refusal, not arbitrary errors.
            if type(exc).__name__ == "BatchValidationError":
                raise Rejected(str(exc)) from exc
            raise
        if stats.get("failed") or stats.get("edits_applied", 0) != 1:
            raise Rejected(json.dumps(stats, default=str))
    output.write_bytes(engine.save_to_stream().getvalue())
    return {"stats": stats, "change": parameters, "author": AUTHOR,
            "partial": False, "engine_options": "3.0.4 defaults except author"}


def capture(adapter, destination):
    protocol = frozen_protocol()
    pins = {"python-docx": "1.2.0", "lxml": "6.1.3"}
    if adapter == "adeu-sdk-v1":
        pins["adeu"] = "3.0.4"
    for package, version in pins.items():
        if metadata.version(package) != version:
            raise ValueError(f"This capture requires {package}=={version}")
    destination.mkdir(parents=True, exist_ok=False)
    receipt = {"schema": 1, "adapter": adapter, "started_at": utc(),
               "protocol_sha256": digest(PROTOCOL), "harness_sha256": digest(__file__),
               "checker_source_sha256": tree_hash(ROOT / "src/ooxml_integrity"),
               "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "command": [sys.executable, *sys.argv], "cwd": str(ROOT),
               "python": platform.python_version(), "platform": platform.platform(),
               "distributions": dict(sorted((d.metadata["Name"], d.version) for d in metadata.distributions())),
               "implementation_sha256": {}, "cases": []}
    import docx
    receipt["implementation_sha256"]["docx"] = tree_hash(Path(docx.__file__).parent)
    if adapter == "adeu-sdk-v1":
        import adeu
        receipt["implementation_sha256"]["adeu"] = tree_hash(Path(adeu.__file__).parent)
    # Start receipt establishes protocol pin and versions before any editor call.
    save_json(destination / "started.json", receipt)
    for profile, source_record in protocol["sources"].items():
        source = ROOT / source_record["path"]
        for action in protocol["actions"]:
            ident = f"{profile}-{action}"
            output = destination / f"{ident}.docx"
            record = {"id": ident, "source": source_record["path"], "action": action,
                      "source_sha256": digest(source), "started_at": utc()}
            stdout, stderr = io.StringIO(), io.StringIO()
            try:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    operation = edit_adeu if adapter == "adeu-sdk-v1" else edit_python_docx
                    record["tool_result"] = operation(source, output, action)
                    if not output.is_file():
                        raise RuntimeError("Adapter returned without an output file")
                record["status"] = "ok"
            except (Unsupported, Rejected) as exc:
                record.update(status="unsupported" if isinstance(exc, Unsupported) else "rejected",
                              error=str(exc), exception_type=type(exc).__name__)
            except Exception as exc:
                record.update(status="error", error=str(exc), exception_type=type(exc).__name__)
                traceback.print_exc(file=stderr)
            record.update(finished_at=utc(), output=output.name if output.exists() else None,
                          output_sha256=digest(output) if output.exists() else None,
                          stdout=stdout.getvalue(), stderr=stderr.getvalue())
            receipt["cases"].append(record)
            save_json(destination / f"{ident}.json", record)
            print(adapter, ident, record["status"])
    receipt["finished_at"] = utc()
    save_json(destination / "capture.json", receipt)
    return receipt


def visible(parts):
    return revision.facts(parts)["text"]


def node_signature(node):
    if not isinstance(node.tag, str):
        return (str(node.tag), node.text, node.tail)
    attrs = dict(node.attrib)
    if node.tag == "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship":
        if attrs.get("TargetMode") == "Internal":
            del attrs["TargetMode"]
    text = node.text or ""
    if node.tag not in (W + "t", W + "delText") and not text.strip():
        text = ""
    children = [node_signature(child) for child in node]
    if node.tag in ("{http://schemas.openxmlformats.org/package/2006/relationships}Relationships",
                    "{http://schemas.openxmlformats.org/package/2006/content-types}Types"):
        children.sort(key=repr)
    tail = node.tail if (node.tail or "").strip() else ""
    return (node.tag, tuple(sorted(attrs.items())), text, tail, tuple(children))


def target_normalization(root, action):
    """Only the third body paragraph has a permitted edit/run split in v1."""
    if action != "edit":
        return
    paragraphs = root.findall("w:body/w:p", NS)
    if len(paragraphs) < 3:
        return
    paragraph = paragraphs[2]
    for node in list(paragraph):
        payload = "".join(n.text or "" for n in node.iter() if n.tag in (W + "t", W + "delText"))
        if node.get(W + "author") != AUTHOR:
            continue
        # The pinned marker has no run formatting or nontext run content. Do
        # not hide a style/drawing change inside an otherwise exact new pair.
        allowed_attrs = {W + name for name in ("id", "author", "date")}
        if set(node.attrib) - allowed_attrs or len(node) != 1:
            continue
        run = node[0]
        if (run.tag != W + "r" or run.attrib or len(run) != 1
                or run[0].tag not in (W + "t", W + "delText")
                or set(run[0].attrib) - {SPACE}):
            continue
        if node.tag == W + "ins" and payload == NEW:
            paragraph.remove(node)
        elif node.tag == W + "del" and payload == OLD:
            for text in node.iter(W + "delText"):
                text.tag = W + "t"
            revision.unwrap(node)
    for node in paragraph.findall("w:r/w:t", NS):
        node.text = (node.text or "").replace(NEW, OLD)

    def plain_run(run):
        return run.tag == W + "r" and len(run) > 0 and all(
            n.tag in (W + "rPr", W + "t") for n in run) and bool(run.findall(W + "t"))

    previous = None
    for run in list(paragraph):
        if not plain_run(run):
            previous = None
            continue
        texts = run.findall(W + "t")
        content = "".join(t.text or "" for t in texts)
        for text in texts[1:]:
            run.remove(text)
        texts[0].text = content
        texts[0].attrib.pop(SPACE, None)
        props = run.find(W + "rPr")
        key = (tuple(sorted(run.attrib.items())), node_signature(props) if props is not None else None,
               tuple(sorted(texts[0].attrib.items())))
        if previous is not None and previous[1] == key:
            prior_text = previous[0].find(W + "t")
            prior_text.text = (prior_text.text or "") + content
            paragraph.remove(run)
        else:
            previous = (run, key)


def package_facts(parts, action):
    signatures, mutable_metadata = {}, {}
    for name, blob in sorted(parts.items()):
        if name.endswith((".xml", ".rels")):
            root = E.fromstring(blob, parser=E.XMLParser(resolve_entities=False, no_network=True))
            if name == "docProps/core.xml":
                for node in list(root):
                    if node.tag in CORE_MUTABLE:
                        mutable_metadata[node.tag] = node_signature(node)
                        root.remove(node)
            if name == MAIN:
                target_normalization(root, action)
            signatures[name] = revision.digest(json_bytes(node_signature(root)))
        else:
            signatures[name] = revision.digest(blob)
    return signatures, mutable_metadata


def assess(source, output, action, adapter):
    """Independent intent/content assessment, with no checker import."""
    before, after = revision.read(source), revision.read(output)
    before_text, after_text = visible(before), visible(after)
    current = after_text.get(MAIN, "")
    tracked = adapter == "adeu-sdk-v1"
    if adapter == "local-agent-v1":
        tracked = any(r["signature"][2] == AUTHOR for r in revision.facts(after)["revisions"])
    case = {"id": "benchmark", "action": action,
            "cohort": "external_editor" if tracked else "benchmark_untracked",
            "allowed_revision_losses": [],
            "allowed_text_changes": [(MAIN, OLD, NEW)] if action == "edit" else []}
    oracle = revision.oracle(before, after, case)
    task = current.count(NEW) == 1 and current.count(OLD) == 0 if action == "edit" else (
        current.count(OLD) == 1 and current.count(NEW) == 0)
    task = task and not oracle["violations"]["missing_requested_tracked_edits"]
    # Do not count a missing replacement, on its own, as unrelated text loss.
    for text_map in (before_text, after_text):
        if action == "edit" and MAIN in text_map:
            text_map[MAIN] = text_map[MAIN].replace(NEW, OLD)
    text_changes = [p for p in sorted(set(before_text) | set(after_text))
                    if before_text.get(p) != after_text.get(p)]
    old_package, old_meta = package_facts(before, action)
    new_package, new_meta = package_facts(after, action)
    package_changes = [p for p in sorted(set(old_package) | set(new_package))
                       if old_package.get(p) != new_package.get(p)]
    violations = {k: v for k, v in oracle["violations"].items()
                  if k not in ("unexpected_text_changes", "missing_requested_tracked_edits")}
    violations.update(protected_text_changes=text_changes, protected_package_changes=package_changes)
    return {"requested_change_completed": bool(task),
            "protected_content_preserved": not any(violations.values()),
            "violations": violations, "revision_oracle": oracle,
            "normalized_package_sha256": revision.digest(json_bytes(new_package)),
            "changed_raw_parts": [p for p in sorted(set(before) | set(after)) if before.get(p) != after.get(p)],
            "mutable_metadata_changed": old_meta != new_meta,
            "raw_part_sha256": {p: revision.digest(blob) for p, blob in sorted(after.items())}}


def checker_findings(source, output):
    # Force checkout code, avoiding stale editable-install metadata (0.4.0 locally).
    sys.path.insert(0, str(ROOT / "src"))
    from ooxml_integrity import check, compare

    return [f.as_dict() for f in check(output) + compare(source, output)]


def inspect_pair(source, output, action, adapter):
    assessment = assess(source, output, action, adapter)
    findings = checker_findings(source, output)
    actionable = [f for f in findings if f["severity"] in ("error", "warn")]
    preserved = assessment["protected_content_preserved"]
    # Automatic reports expose the evidence; they do not pretend a warning has
    # been mapped to a particular loss without review.
    detection = ("no_independent_defect" if preserved else
                 "findings_require_mapping" if actionable else "checker_silent_on_undeclared_change")
    return {**assessment, "checker_findings": findings, "actionable_findings": actionable,
            "checker_detection": detection}


def evaluate(directory):
    protocol = frozen_protocol()
    receipt = json.loads((directory / "capture.json").read_text())
    for key, actual in (("protocol_sha256", digest(PROTOCOL)), ("harness_sha256", digest(__file__)),
                        ("checker_source_sha256", tree_hash(ROOT / "src/ooxml_integrity"))):
        if receipt[key] != actual:
            raise ValueError(f"Capture {key} drift")
    expected = {f"{profile}-{action}" for profile in protocol["sources"] for action in protocol["actions"]}
    if len(receipt["cases"]) != len(expected) or {c["id"] for c in receipt["cases"]} != expected:
        raise ValueError("Capture inventory drift")
    source_findings = {name: checker_findings(ROOT / s["path"], ROOT / s["path"])
                       for name, s in protocol["sources"].items()}
    results = []
    for record in receipt["cases"]:
        if record != json.loads((directory / f"{record['id']}.json").read_text()):
            raise ValueError("Per-attempt receipt drift")
        profile, action = record["id"].rsplit("-", 1)
        source_decl = protocol["sources"][profile]
        if record["source"] != source_decl["path"] or record["action"] != action:
            raise ValueError("Capture task drift")
        if record["source_sha256"] != source_decl["sha256"]:
            raise ValueError("Capture input hash drift")
        result = {"id": record["id"], "status": record["status"],
                  "requested_change_completed": None, "protected_content_preserved": None,
                  "checker_detection": "not_evaluated", "overall_success": False}
        if record["output"] is not None:
            if record["output"] != f"{record['id']}.docx":
                raise ValueError("Unexpected output path")
            output = directory / record["output"]
            if digest(output) != record["output_sha256"]:
                raise ValueError("Capture output hash drift")
            try:
                result.update(inspect_pair(ROOT / record["source"], output, action, receipt["adapter"]))
                result["overall_success"] = (record["status"] == "ok" and result["requested_change_completed"]
                                             and result["protected_content_preserved"])
            except (E.XMLSyntaxError, BadZipFile, ValueError, KeyError) as exc:
                result.update(evaluation_error=f"{type(exc).__name__}: {exc}",
                              requested_change_completed=False, protected_content_preserved=None)
        results.append(result)
    import ooxml_integrity
    return {"schema": 1, "capture_sha256": digest(directory / "capture.json"),
            "adapter": receipt["adapter"], "checker_version": ooxml_integrity.__version__,
            "checker_source_sha256": receipt["checker_source_sha256"], "config": "none",
            "source_findings": source_findings, "cases": results}


def compare_captures(left, right):
    a, b = evaluate(left), evaluate(right)
    if a["adapter"] != b["adapter"]:
        raise ValueError("Repeat comparison requires the same adapter")
    keys = ("status", "requested_change_completed", "protected_content_preserved", "overall_success",
            "normalized_package_sha256", "checker_findings", "violations", "evaluation_error")
    mismatches, raw_equal = [], []
    for x, y in zip(a["cases"], b["cases"]):
        if x["id"] != y["id"] or any(x.get(k) != y.get(k) for k in keys):
            mismatches.append(x["id"])
        p, q = left / f"{x['id']}.docx", right / f"{y['id']}.docx"
        if p.exists() and q.exists() and digest(p) == digest(q):
            raw_equal.append(x["id"])
    return {"adapter": a["adapter"], "left_capture_sha256": a["capture_sha256"],
            "right_capture_sha256": b["capture_sha256"], "pairs": len(a["cases"]),
            "semantic_mismatches": mismatches, "raw_byte_equal": raw_equal}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("capture")
    p.add_argument("--adapter", choices=ADAPTERS, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    for name in ("evaluate", "verify"):
        p = commands.add_parser(name)
        p.add_argument("directory", type=Path)
    p = commands.add_parser("compare")
    p.add_argument("left", type=Path)
    p.add_argument("right", type=Path)
    p = commands.add_parser("inspect")
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--action", choices=("save", "edit"), required=True)
    p.add_argument("--adapter", choices=ADAPTERS + ("local-agent-v1",), required=True)
    args = parser.parse_args()
    if args.command == "capture":
        capture(args.adapter, args.output_dir)
    elif args.command in ("evaluate", "verify"):
        result = evaluate(args.directory)
        target = args.directory / "evaluation.json"
        if args.command == "evaluate":
            save_json(target, result)
        elif result != json.loads(target.read_text()):
            raise ValueError("Saved evaluation does not reproduce")
        print(json.dumps({"adapter": result["adapter"], "attempts": len(result["cases"]),
                          "successes": sum(c["overall_success"] for c in result["cases"]),
                          "evaluation": str(target)}))
    elif args.command == "compare":
        result = compare_captures(args.left, args.right)
        print(json_bytes(result).decode(), end="")
        if result["semantic_mismatches"]:
            raise SystemExit(1)
    else:
        frozen_protocol()
        print(json_bytes(inspect_pair(args.source, args.output, args.action, args.adapter)).decode(), end="")


if __name__ == "__main__":
    main()
