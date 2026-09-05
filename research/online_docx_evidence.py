"""Prepare synthetic inputs and audit actual Word for the web downloads.

This module does not emulate Word Online or use checker output as ground truth.
The browser upload, edit, save and download must be observed separately.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import sys
from datetime import date
from pathlib import Path

import docx

try:
    from . import build_docx_evidence as corpus
    from . import windows_docx_evidence as privacy
except ImportError:
    import build_docx_evidence as corpus
    import windows_docx_evidence as privacy


COUNTS = {
    "contract": 2, "report": 1, "letter": 1, "table": 2,
    "multi-section": 2, "review-heavy": 2,
}
BEFORE = "WEBINPUT"
AFTER = "WEBSAVED"
OPERATION = "Observed Word for the web upload, replace marker, autosave, download DOCX"
LABEL_POLICY = "Expected findings are declared before scoring from isolated mutations or observed Office operations with independent XML audits. Exact actionable multisets are regression-gated."


def prepare(staging: Path) -> dict[str, object]:
    """Create upload inputs only; no producer or success claim is recorded."""
    if staging.exists():
        raise ValueError("Use a fresh staging directory; existing files are never overwritten.")
    (staging / "inputs").mkdir(parents=True)
    (staging / "raw").mkdir()
    documents = []
    for category, count in COUNTS.items():
        for ordinal in range(1, count + 1):
            source_id = f"online-{category}-{ordinal:02d}"
            path = staging / "inputs" / f"{source_id}.docx"
            corpus._build_seed(corpus.SourceSpec(source_id, category, ordinal, "word-online"), path)
            parts, order = corpus._read_package(path)
            main = corpus._xml(parts, "word/document.xml")
            marker = corpus._find_text(main, "EVIDENCE-MARKER-")
            marker.text += " " + BEFORE
            corpus._store_xml(parts, "word/document.xml", main)
            corpus._write_package(parts, order, path)
            privacy.sanitise(path)
            documents.append({
                "id": source_id, "category": category,
                "input": f"inputs/{path.name}", "input_sha256": corpus._sha256(path),
                "output": f"raw/{path.name}",
            })
    request = {
        "schema_version": 1,
        "operation": "synthetic-inputs-for-observed-word-online-edit",
        "edit": {"find": BEFORE, "replace": AFTER, "count": 1},
        "seed_generator": "research/build_docx_evidence.py _build_seed plus web edit marker",
        "seed_python_docx_version": docx.__version__,
        "python_version": sys.version.split()[0], "documents": documents,
    }
    privacy.write_json(staging / "batch.json", request)
    return request


def audit_edit(before: Path, after: Path) -> dict[str, object]:
    """Require the declared edit and preservation of the known semantic facts."""
    original = privacy.semantic_facts(before)
    saved = privacy.semantic_facts(after)
    if original["main_text"].count(BEFORE) != 1 or AFTER in original["main_text"]:
        raise ValueError("Input must have exactly one unedited web marker.")
    expected = copy.deepcopy(original)
    expected["main_text"] = expected["main_text"].replace(BEFORE, AFTER, 1)
    if saved != expected:
        different = sorted(key for key in expected if saved[key] != expected[key])
        raise ValueError(f"Unexplained semantic changes or missing web edit: {different}")
    # Also check exact whitespace and ordered comment endpoints, not just the
    # normalised facts used by the historical Windows capture oracle.
    old_parts, _ = corpus._read_package(before)
    new_parts, _ = corpus._read_package(after)
    def exact_main(parts):
        root = corpus._xml(parts, "word/document.xml")
        return "".join(node.text or "" for node in root.iter(corpus.W + "t"))
    if exact_main(new_parts) != exact_main(old_parts).replace(BEFORE, AFTER, 1):
        raise ValueError("Exact body text changed beyond the declared web edit.")
    def anchors(parts):
        root = corpus._xml(parts, "word/document.xml")
        tags = {corpus.W + kind for kind in ("commentRangeStart", "commentRangeEnd", "commentReference")}
        offset, result = 0, []
        for node in root.iter():
            if node.tag == corpus.W + "t":
                offset += len(node.text or "")
            elif node.tag in tags:
                result.append((node.tag, node.get(corpus.W + "id"), offset))
        # The declared markers have equal length, so an unchanged anchor must
        # keep its exact body-text offset even if Word splits or merges runs.
        return result
    if anchors(old_parts) != anchors(new_parts):
        raise ValueError("Comment anchor order, identifiers or text offsets changed; review before labelling.")
    def comment_text_by_id(parts):
        root = corpus._xml(parts, "word/comments.xml")
        return sorted((node.get(corpus.W + "id"),
                       "".join(t.text or "" for t in node.iter(corpus.W + "t")))
                      for node in root)
    if comment_text_by_id(old_parts) != comment_text_by_id(new_parts):
        raise ValueError("Comment text or its anchor ID mapping changed; review before labelling.")
    return {
        "expected_edit": {"find": BEFORE, "replace": AFTER, "count": 1},
        "preserved_fields": sorted(key for key in expected if key != "main_text"),
        "exact_body_text_except_declared_edit": True,
        "ordered_comment_anchors_preserved": True,
        "facts_sha256": hashlib.sha256(json.dumps(saved, sort_keys=True).encode()).hexdigest(),
    }


def import_batch(staging: Path, manifest_path: Path = corpus.MANIFEST) -> dict[str, object]:
    """Append real downloads, requiring an operator's UI receipt and XML audit.

    Hashes bind the receipt to files; they cannot independently prove which
    application wrote them. The observed UI workflow is the producer evidence.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if any(s["producer"]["id"] == "word-online" for s in manifest["sources"]):
        raise ValueError("Word Online evidence already exists; refuse to replace it.")
    request = json.loads((staging / "batch.json").read_text(encoding="utf-8"))
    run = json.loads((staging / "web-run.json").read_text(encoding="utf-8"))
    if run.get("completed") is not True or run.get("operation") != OPERATION:
        raise ValueError("Incomplete or unsupported observed web run.")
    if set(run) != {"completed", "operation", "observed_on", "service", "documents"} or run["service"] != "word.cloud.microsoft":
        raise ValueError("Unexpected web receipt fields or service; exclude private URLs and accounts.")
    if date.fromisoformat(run["observed_on"]).isoformat() != run["observed_on"]:
        raise ValueError("Use an ISO capture date.")
    expected_ids = {f"online-{category}-{ordinal:02d}": category
                    for category, count in COUNTS.items() for ordinal in range(1, count + 1)}
    requested = {item["id"]: item for item in request["documents"]}
    entries = {item["id"]: item for item in run["documents"]}
    if (len(request["documents"]) != 10 or len(run["documents"]) != 10 or
            {key: item["category"] for key, item in requested.items()} != expected_ids or
            set(entries) != set(expected_ids) or
            request.get("edit") != {"find": BEFORE, "replace": AFTER, "count": 1}):
        raise ValueError("Expected exactly ten web documents and the declared single edit.")
    prepared = []
    for source_id, item in requested.items():
        entry = entries[source_id]
        if (set(entry) != {"id", "input_sha256", "raw_output_sha256", "replace_count", "saved", "downloaded"} or
                type(entry["replace_count"]) is not int or entry["replace_count"] != 1 or
                entry["saved"] is not True or entry["downloaded"] is not True):
            raise ValueError("Missing observed replacement, save or download confirmation.")
        seed = privacy.batch_path(staging, item["input"])
        raw = privacy.batch_path(staging, item["output"])
        if (corpus._sha256(seed) != item["input_sha256"] or
                item["input_sha256"] != entry["input_sha256"] or
                corpus._sha256(raw) != entry["raw_output_sha256"]):
            raise ValueError("Web receipt hash mismatch.")
        privacy.audit_privacy(seed)
        audit = audit_edit(seed, raw)
        published = staging / "sanitised" / f"{source_id}.docx"
        published.parent.mkdir(exist_ok=True)
        shutil.copyfile(raw, published)
        receipt = privacy.sanitise(published)
        if audit_edit(seed, published) != audit:
            raise ValueError("Sanitisation changed semantic facts.")
        prepared.append((item, entry, seed, published, receipt, audit))

    root = manifest_path.parent
    provenance_path = root / "provenance/word-online.json"
    paths = [root / directory / f"{item['id']}.docx" for item, *_ in prepared
             for directory in ("sources", "roundtrips")]
    paths += [root / "outputs" / f"{item['id']}--{mutation}.docx" for item, *_ in prepared
              for mutation in ("clean-copy", "safe-text-edit", *corpus.CATEGORY_MUTATIONS[item["category"]])]
    if any(path.exists() for path in paths + [provenance_path]):
        raise ValueError("Import would overwrite corpus files.")
    sources, pairs, supporting, receipts = [], [], [], []
    version = f"service build not exposed in observed UI ({run['observed_on']})"
    for item, entry, seed, published, receipt, audit in prepared:
        source_relative = f"sources/{item['id']}.docx"
        input_relative = f"roundtrips/{item['id']}.docx"
        for path, relative in ((seed, input_relative), (published, source_relative)):
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, root / relative)
        supporting.append({"path": input_relative, "sha256": corpus._sha256(seed),
                           "role": "synthetic input before observed Word Online edit"})
        sources.append({
            "id": item["id"], "path": source_relative, "sha256": corpus._sha256(published),
            "category": item["category"], "producer": {"id": "word-online", "version": version,
                "operation": "upload, replace WEBINPUT with WEBSAVED once, autosave, download DOCX"},
            "synthetic": True, "personal_data": False, "postprocessing": receipt["description"],
            "provenance": "provenance/word-online.json",
            "expected_behavior": "Observed web editor accepted the input, confirmed one replacement and autosave. Download has the declared edit and preserved audited XML facts; no independent human or pixel-equivalence claim.",
        })
        pairs.append({
            "id": f"{item['id']}--word-online-edit", "source": input_relative,
            "source_sha256": corpus._sha256(seed), "output": source_relative,
            "output_sha256": corpus._sha256(published), "mutation": "word-online-edit", "class": "clean",
            "description": "Actual Word Online marker edit and download with metadata sanitisation",
            "label_method": "Declared single text replacement plus direct XML audit, independent of checker output",
            "label_basis": "Exactly one WEBINPUT becomes WEBSAVED; all other exact body text, table-cell text, comments and ordered anchors, section count and effective header/footer text are preserved.",
            "expected_findings": [],
        })
        receipts.append({**entry, "input": input_relative, "output": source_relative,
                         "published_output_sha256": corpus._sha256(published),
                         "sanitisation": receipt, "semantic_audit": audit})
    privacy.write_json(provenance_path, {
        "schema_version": 1, "producer": "word-online", "operation": OPERATION,
        "observed_on": run["observed_on"], "service": run["service"], "version": version,
        "seed_generator": "research/online_docx_evidence.py prepare (synthetic python-docx inputs)",
        "review": "Browser UI actions observed by the coding agent, followed by direct XML audit; no independent human or dual review claimed. This is an operator receipt, not Microsoft-signed attestation.",
        "raw_artifacts": "Raw downloads remain in ignored local staging. No account names, private document URLs or machine paths are published. Raw and published package-part hashes document metadata-only sanitisation.",
        "documents": receipts,
    })
    supporting.append({"path": "provenance/word-online.json", "sha256": corpus._sha256(provenance_path),
                       "role": "sanitised observed UI receipt, semantic audit and part hashes"})
    manifest["sources"].extend(sources)
    manifest["pairs"].extend(corpus._build_outputs(sources, evidence_root=root) + pairs)
    manifest.setdefault("supporting_artifacts", []).extend(supporting)
    manifest["producer_versions"]["word-online"] = version
    manifest["source_count"], manifest["pair_count"] = len(manifest["sources"]), len(manifest["pairs"])
    manifest["known_evidence_gaps"] = [
        "Legacy labels have one maintainer review; Windows and web labels have coding-agent XML review, not independent human or dual review." if "dual review" in gap else gap
        for gap in manifest["known_evidence_gaps"] if gap != "No Word Online source has been collected."
    ]
    manifest["online_added_on"] = run["observed_on"]
    manifest["label_policy"] = LABEL_POLICY
    privacy.write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--staging", type=Path, required=True)
    import_parser = commands.add_parser("import")
    import_parser.add_argument("--staging", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        request = prepare(args.staging)
        print(f"Prepared {len(request['documents'])} synthetic upload inputs; no Word Online evidence captured yet.")
    else:
        manifest = import_batch(args.staging)
        print(f"Imported observed web evidence: {manifest['source_count']} sources, {manifest['pair_count']} pairs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
