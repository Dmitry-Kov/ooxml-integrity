"""The post-release recheck of docx-cli and adeu is what its outputs show.

The captures were made in Docker (research/review_history_recheck.py); these
tests only read them. Status, completion, preservation and the probes are
re-derived with the oracle and the evaluator; the checker axis stays a
receipt, as in the frozen benchmark's own test, because a later checker
release changes it without changing the outputs.
"""
from __future__ import annotations

import json

import pytest

from conftest import ROOT
from research import review_history_benchmark as bench
from research import review_history_recheck as recheck

pytestmark = pytest.mark.skipif(not recheck.RESULTS.exists(),
                                reason="the recheck evidence is not in this tree")

RECORD = json.loads(recheck.RESULTS.read_text(encoding="utf-8")) if recheck.RESULTS.exists() else {
    "results": []}
TASK = {t["id"]: t for t in json.loads(bench.TASKS.read_text(encoding="utf-8"))["tasks"]}
RECEIPT_ONLY = ("checker", "detection", "frozen_detection", "tool", "version", "origin", "capture")


def _folder(result):
    parent = bench.CAPTURES if result["origin"] == "frozen" else recheck.CAPTURES
    return parent / result["capture"]


def _attempt(result):
    data = json.loads((_folder(result) / "capture.json").read_text(encoding="utf-8"))
    return next(a for a in data["attempts"] if a["task"] == result["task"])


def test_the_frozen_benchmark_is_untouched():
    assert bench.verify() == []


@pytest.mark.parametrize("folder", sorted(recheck.CAPTURES.glob("*/capture.json")),
                         ids=lambda p: p.parent.name)
def test_recheck_captures_match_their_receipts(folder):
    data = json.loads(folder.read_text(encoding="utf-8"))
    spec = recheck.release(data["tool"], data["version"])
    assert data["image_id"] == spec["image_id"]
    assert data["protocol_sha256"] == bench._sha(bench.PROTOCOL)
    assert [a["task"] for a in data["attempts"]] == list(TASK)
    for attempt in data["attempts"]:
        receipt = json.loads((folder.parent / "receipts" / f"{attempt['task']}.json").read_text(
            encoding="utf-8"))
        assert receipt == attempt
        if attempt["status"] == "ok":
            assert bench._sha(folder.parent / attempt["output"]) == attempt["output_sha256"]


@pytest.mark.parametrize("recorded", RECORD["results"],
                         ids=lambda r: f"{r['capture']}-{r['task']}")
def test_recheck_results_reevaluate_identically(recorded):
    again = recheck.evaluate_one(TASK[recorded["task"]], _attempt(recorded), _folder(recorded), None)
    keep = lambda r: {k: v for k, v in r.items() if k not in RECEIPT_ONLY}  # noqa: E731
    assert keep(again) == keep(recorded)


def test_two_captures_per_version_cover_every_task():
    for tool in recheck.tools():
        for spec, _, _ in recheck.versions(tool):
            version = spec["version"]
            found = [r for r in RECORD["results"] if (r["tool"], r["version"]) == (tool, version)]
            assert len(found) == 2 * len(TASK) and len({r["capture"] for r in found}) == 2


def test_summary_and_readme_table_are_derived_from_the_results():
    assert recheck.summarise(RECORD["results"]) == RECORD["summary"]
    readme = (recheck.RECHECK / "README.md").read_text(encoding="utf-8")
    for block in recheck.table(RECORD).strip().split("\n\n"):
        assert block in readme


def _probes(capture, task):
    return next(r["probes"] for r in RECORD["results"]
                if (r["capture"], r["task"]) == (capture, task))


def test_the_recorded_damage_classes():
    # docx-cli 0.26.0 wrote the S1 bullet as the text `&#8226;`; 0.27.0 and 0.28.0 do not.
    s1 = [t for t in TASK if "-S1-" in t and not t.startswith("K0")]
    assert all(_probes("docx-cli-5", t)["literal_bullets"] == ["&#8226;"] for t in s1)
    for capture in ("docx-cli-0.27.0-1", "docx-cli-0.28.0-1"):
        assert all(_probes(capture, t)["literal_bullets"] == [] for t in s1)
    # adeu keeps one w:id on both halves of the other author's split insertion.
    for capture in ("adeu-1", "adeu-3.0.7-1"):
        assert _probes(capture, "K4-S1-tracked")["repeated_revision_ids"] == {
            "word/document.xml": ["101"]}
        assert _probes(capture, "K4-S2-tracked")["repeated_revision_ids"] == {
            "word/document.xml": ["12"]}


@pytest.mark.parametrize("version, plain", [
    ("0.27.0", "Fees are due. disputed sumwithhold disputed amount."),
    ("0.28.0", "Fees are due. The Client may withhold disputed sum.")])
def test_an_untracked_replace_next_to_a_nested_deletion_hits_the_target_from_0_28_0(version, plain):
    from lxml import etree
    from research import review_history_oracle as oracle
    record = json.loads(recheck.nested_record(version).read_text(encoding="utf-8"))
    assert record["version"] == version and record["source_paragraph"] == recheck.NESTED_DELETION
    texts = {}
    for mode, run in record["runs"].items():
        assert run["exit"] == 0 and run["stdout"] == "replace 1 occurrence replaced"
        body = etree.fromstring(f'<w:body xmlns:w="{oracle.W_NS}">{run["paragraph"]}</w:body>')
        texts[mode] = oracle.text(body, "current")
        assert texts[mode] == run["current"]
    assert texts["tracked"] == record["expected_current"]
    assert texts["plain"] == plain


def test_the_requested_text_is_expected_on_k4_s2_plain_from_0_28_0():
    # The expectations' fourth reading: 0.27.0's edit of the wrong span fails
    # them (the expected FID014 does not occur), 0.28.0's edit matches.
    from research import review_history_expectations as analysis
    task = TASK["K4-S2-plain"]
    expectations = analysis.expectations_for(task) + analysis.text_expectations(task)
    for version, codes, expected in (("0.27.0", ["EXP001"], []), ("0.28.0", [], ["FID014"])):
        for repeat in (1, 2):
            output = recheck.CAPTURES / f"docx-cli-{version}-{repeat}" / "K4-S2-plain.docx"
            assert analysis.actionable(ROOT / task["source_path"], output, expectations) == {
                "codes": codes, "expected": expected}


def test_tool_messages_are_stderr_of_successful_steps():
    note = json.dumps({"note": "", "steps": [
        {"args": [], "code": 0, "stderr": "warning: resolved\n"},
        {"args": [], "code": 0, "stderr": ""}, {"args": [], "code": 1, "stderr": "refused"}]})
    assert recheck.tool_messages(note) == ["warning: resolved"]
    assert recheck.tool_messages("not json") == []


def test_performer_points_the_frozen_adapters_at_the_image_and_restores_them(monkeypatch):
    from research import review_history_adapters as adapters
    seen = []
    monkeypatch.setattr(adapters, "adeu", lambda *a: seen.append(adapters.ADEU_IMAGE) or ("ok", ""))
    recheck.performer("adeu", "ooxml-bench-adeu:test")({}, {}, None)
    assert seen == ["ooxml-bench-adeu:test"] and adapters.ADEU_IMAGE == "ooxml-bench-adeu:3.0.6"

    frozen = adapters.CONTAINER_TOOLS["docx-cli"]
    images = []
    monkeypatch.setattr(adapters, "container_tool",
                        lambda name: images.append(adapters.CONTAINER_TOOLS[name][0]))
    recheck.performer("docx-cli", "ooxml-bench-docx-cli:test")
    assert images == ["ooxml-bench-docx-cli:test"] and adapters.CONTAINER_TOOLS["docx-cli"] == frozen


def test_the_control_reproduced_the_previous_captures():
    # Each release's control ran the version before it: the frozen one, or the
    # release before.
    control = json.loads(recheck.CONTROL.read_text(encoding="utf-8"))
    for tool in recheck.tools():
        before = [spec for spec, _, _ in recheck.versions(tool)][:-1]
        assert sorted(control[tool]) == sorted(spec["version"] for spec in before)
        for spec in before:
            result = control[tool][spec["version"]]
            assert result["image_id"] == spec["image_id"]
            assert result["same_status_and_facts"] == result["attempts"] == len(TASK)


def test_the_build_record_pins_what_the_dockerfiles_check():
    for spec in (r for t in recheck.tools().values() for r in t["releases"]):
        dockerfile = (ROOT / spec["dockerfile"]).read_text(encoding="utf-8")
        assert spec["base_image"] in dockerfile
        assert spec.get("tarball_sha256", spec.get("uv_lock_sha256")) in dockerfile
