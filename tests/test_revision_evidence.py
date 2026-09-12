"""Freeze evidence labels, independently check intent, and retain known misses."""
from __future__ import annotations

import json
import pytest
from lxml import etree as E

from research import revision_evidence as evidence


@pytest.fixture(scope="module")
def manifest():
    return json.loads((evidence.BASE / "manifest.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return evidence.evaluate()


def test_labels_precede_capture_and_are_not_reconstructed_from_findings(manifest):
    declared = json.loads((evidence.BASE / "labels.json").read_text(encoding="utf-8"))
    assert declared == json.loads(json.dumps(evidence.labels()))
    assert len(declared) == 25
    declared.extend(json.loads((evidence.BASE / "labels-online.json").read_text(encoding="utf-8")))
    assert len(declared) == 27
    assert {c["id"] for c in declared} == {c["id"] for c in manifest["pairs"]}
    records = {c["id"]: c for c in manifest["pairs"]}
    for case in declared:
        assert {key: records[case["id"]][key] for key in case} == case
    capture = json.loads((evidence.BASE / "capture-adeu.json").read_text(encoding="utf-8"))
    assert capture["labels_sha256"] == manifest["labels_sha256"]
    assert capture["version"] == "3.0.4"
    assert len(capture["cases"]) == 12
    for case in capture["cases"]:
        saved = records[case["id"]]
        assert case["source_sha256"] == saved["source_sha256"]
        assert case["raw_output_sha256"] == saved["output_sha256"]


@pytest.mark.parametrize("profile", evidence.PROFILES)
def test_sources_rebuild_and_have_existing_revisions(profile, tmp_path):
    rebuilt = tmp_path / "source.docx"
    evidence.write(evidence.source_parts(profile), rebuilt)
    original = evidence.BASE / "sources" / f"{profile}.docx"
    assert rebuilt.read_bytes() == original.read_bytes()
    facts = evidence.facts(evidence.read(original))
    assert len(facts["revisions"]) >= 3
    assert len({r["signature"][2] for r in facts["revisions"]}) >= 2
    assert not facts["invalid"]
    assert not facts["duplicates"]


def test_seeded_outputs_rebuild_without_running_editors(tmp_path):
    evidence.rebuild(tmp_path)
    outputs = list(tmp_path.glob("*.docx"))
    assert len(outputs) == 13
    for path in outputs:
        assert path.read_bytes() == (evidence.BASE / "outputs" / path.name).read_bytes()


def test_every_pair_hash_and_exact_finding_multiset(metrics):
    assert all(case["matches_expected_checker"] for case in metrics["cases"])
    assert metrics == json.loads((evidence.BASE / "metrics.json").read_text(encoding="utf-8"))


def test_external_preservation_and_seeded_detection_have_separate_denominators(metrics):
    editor = metrics["groups"]["external_editor"]
    assert {key: editor[key] for key in ("pairs", "tp", "fp", "fn", "tn")} == dict(pairs=10, tp=0, fp=0, fn=0, tn=10)
    seeded = metrics["groups"]["seeded_defect"]
    assert {key: seeded[key] for key in ("pairs", "tp", "fp", "fn", "tn")} == dict(pairs=9, tp=7, fp=0, fn=2, tn=0)
    assert set(metrics["rules_with_seeded_positive_cases"]) == {"REV001", "REV002", "REV003", "FID001", "FID008"}
    assert "CMT001" in metrics["rules_without_positive_cases"]
    online = metrics["groups"]["word_online"]
    assert {key: online[key] for key in ("pairs", "tp", "fp", "fn", "tn")} == dict(pairs=2, tp=0, fp=0, fn=0, tn=2)


def test_online_raw_and_published_parts_differ_only_in_scrubbed_core_metadata(manifest):
    receipt = json.loads((evidence.BASE / "capture-online.json").read_text(encoding="utf-8"))
    assert receipt["labels_sha256"] == manifest["label_files_sha256"]["labels-online.json"]
    assert receipt["service_build"] is None
    assert len(receipt["cases"]) == 2
    records = {case["id"]: case for case in manifest["pairs"]}
    for capture in receipt["cases"]:
        case = records[capture["id"]]
        assert case["provenance"] == "observed_word_online_edit"
        assert case["source_sha256"] == capture["source_sha256"]
        assert case["output_sha256"] == capture["published_sha256"]
        assert capture["saved"] and capture["downloaded"] and capture["replace_count"] == 1
        parts = evidence.read(evidence.BASE / case["output_path"])
        assert {p: evidence.digest(b) for p, b in parts.items()} == capture["published_part_sha256"]
        assert [p for p in parts if capture["raw_part_sha256"][p] != capture["published_part_sha256"][p]] == ["docProps/core.xml"]


@pytest.mark.parametrize("repair_reference", [True, False])
def test_oracle_accepts_consistent_note_renumbering_but_rejects_dangling_reference(repair_reference):
    source = evidence.read(evidence.BASE / "sources/basic.docx")
    altered = dict(source)
    note = E.fromstring(altered["word/footnotes.xml"])
    note.find("w:footnote[@w:id='1']", evidence.NS).set(evidence.W + "id", "9000")
    altered["word/footnotes.xml"] = evidence.xml(note)
    if repair_reference:
        root = E.fromstring(altered[evidence.MAIN])
        root.find(".//w:footnoteReference", evidence.NS).set(evidence.W + "id", "9000")
        altered[evidence.MAIN] = evidence.xml(root)
    result = evidence.oracle(source, altered, evidence.labels()[0])
    assert result["intent_correct"] is repair_reference


def test_accept_reject_is_characterization_not_preservation_precision(metrics):
    group = metrics["groups"]["characterization"]
    assert group == dict(pairs=6, label_mismatches=0, excluded_from_preservation_metrics=True, correct_actions=5, incorrect_actions=1)
    cases = {case["id"]: case for case in metrics["cases"]}
    correct = cases["synthetic-partial-accept"]
    incorrect = cases["synthetic-accept-with-unrelated-loss"]
    assert correct["intent_correct"] is True
    assert incorrect["intent_correct"] is False
    # The same warning multiset does not establish whether the edit was valid.
    assert correct["actionable_findings"] == incorrect["actionable_findings"]


@pytest.mark.parametrize("ident", ["replace-unrelated-insertion", "unwrap-note-insertion"])
def test_known_misses_remain_defects_when_current_checker_is_silent(ident, manifest, metrics):
    record = next(case for case in manifest["pairs"] if case["id"] == ident)
    assert record["known_miss"] is True
    assert record["intent_correct"] is False
    assert record["oracle"]["violations"]["unrelated_revision_losses"]
    observed = next(case for case in metrics["cases"] if case["id"] == ident)
    assert observed["actionable_findings"] == []


def test_oracle_preserves_payload_and_author_even_when_tag_counts_match():
    source = evidence.read(evidence.BASE / "sources/basic.docx")
    altered = dict(source)
    root = E.fromstring(altered[evidence.MAIN])
    insertion = root.find(".//w:ins", evidence.NS)
    insertion.set(evidence.W + "author", "Wrong reviewer")
    altered[evidence.MAIN] = evidence.xml(root)
    case = next(c for c in evidence.labels() if c["id"] == "basic-save")
    result = evidence.oracle(source, altered, case)
    assert result["intent_correct"] is False
    assert result["violations"]["unrelated_revision_losses"] == [(evidence.MAIN, "101")]
    assert not result["violations"]["unexpected_text_changes"]


def test_oracle_checks_comment_anchor_even_when_text_and_revisions_survive():
    source = evidence.read(evidence.BASE / "sources/basic.docx")
    altered = dict(source)
    root = E.fromstring(altered[evidence.MAIN])
    anchor = root.find(".//w:commentRangeEnd", evidence.NS)
    anchor.getparent().remove(anchor)
    altered[evidence.MAIN] = evidence.xml(root)
    case = next(c for c in evidence.labels() if c["id"] == "basic-save")
    result = evidence.oracle(source, altered, case)
    assert result["intent_correct"] is False
    assert result["violations"]["changed_review_structures"] == [evidence.MAIN]
    assert result["lost_revisions"] == []


def test_no_op_oracle_rejects_an_extra_hidden_review_record():
    source = evidence.read(evidence.BASE / "sources/basic.docx")
    altered = dict(source)
    root = E.fromstring(altered[evidence.MAIN])
    paragraph = root.find("w:body/w:p", evidence.NS)
    paragraph.append(E.fromstring(f'<w:del xmlns:w="{evidence.W[1:-1]}" w:id="999" w:author="Reviewer B"><w:r><w:delText>invented review</w:delText></w:r></w:del>'))
    altered[evidence.MAIN] = evidence.xml(root)
    result = evidence.oracle(source, altered, evidence.labels()[0])
    assert not result["intent_correct"]
    assert result["violations"]["unexpected_new_revisions"]
    assert not result["violations"]["unexpected_text_changes"]


def test_published_authors_and_external_links_are_fixture_only(manifest):
    allowed = {"Reviewer A", "Reviewer B", "Reviewer C", "Evidence Editor"}
    paths = {evidence.BASE / c[key] for c in manifest["pairs"] for key in ("source_path", "output_path")}
    for path in paths:
        for part, blob in evidence.read(path).items():
            if not part.endswith((".xml", ".rels")):
                continue
            for node in E.fromstring(blob).iter():
                if node.get(evidence.W + "author"):
                    assert node.get(evidence.W + "author") in allowed
                if node.get("TargetMode") == "External":
                    assert node.get("Target") == "https://example.org/spec"
