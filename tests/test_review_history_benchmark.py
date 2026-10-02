"""The review-history evaluator, checked before any benchmarked tool runs.

Positive control: the reference adapter's output completes every declared
task and preserves everything else. Negative controls: known bad outputs fail
on the declared axis, with the violation categories derived from the damage.
"""
from __future__ import annotations

import json
import sys
import zipfile

import pytest
from lxml import etree

from conftest import ROOT

sys.path.insert(0, str(ROOT))
from research import review_history_benchmark as bench  # noqa: E402
from research import review_history_oracle as oracle  # noqa: E402
from research import review_history_reference as reference  # noqa: E402

W = oracle.W
DECLARED = json.loads(bench.TASKS.read_text(encoding="utf-8"))
EDITOR = DECLARED["editor"]
TASK = {t["id"]: t for t in DECLARED["tasks"]}


def _reference(tmp_path, task_id):
    return reference.perform(TASK[task_id], EDITOR, tmp_path / f"{task_id}.docx")


def _edit(path, part, edit):
    with zipfile.ZipFile(path) as z:
        parts = {i.filename: z.read(i) for i in z.infolist()}
    root = etree.fromstring(parts[part])
    edit(root)
    parts[part] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    with zipfile.ZipFile(path, "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return path


def _summary(task_id, output):
    result = bench.evaluate(TASK[task_id], output, "ok", EDITOR)
    return result["completed"], sorted(result["preservation"]["violations"])


@pytest.mark.parametrize("task_id", sorted(TASK))
def test_the_reference_adapter_completes_and_preserves_every_task(tmp_path, task_id):
    result = bench.evaluate(TASK[task_id], _reference(tmp_path, task_id), "ok", EDITOR)
    assert result["completed"] is True
    assert result["preservation"]["violations"] == {}


def _setter(tmp_path, task_id, old, new):
    docx = pytest.importorskip("docx")
    task = TASK[task_id]
    document = docx.Document(str(ROOT / task["source_path"]))
    start = task["call"]["paragraph_current"][:20]
    [paragraph] = [p for p in document.paragraphs if p.text.startswith(start)]
    paragraph.text = paragraph.text.replace(old, new)
    output = tmp_path / f"{task_id}-setter.docx"
    document.save(str(output))
    return output


def test_a_paragraph_text_setter_on_a_commented_sentence_loses_anchor_and_footnote(tmp_path):
    output = _setter(tmp_path, "K1-S1-plain", "Effective Date", "Commencement Date")
    assert _summary("K1-S1-plain", output) == (True, ["comment_anchor", "note_reference"])


def test_a_paragraph_text_setter_inside_other_revisions_destroys_them(tmp_path):
    # python-docx does not see text inside w:ins/w:del, so the edit cannot even
    # find its target; rewriting the paragraph still wipes every revision in it.
    output = _setter(tmp_path, "K4-S2-plain", "disputed amount", "disputed sum")
    assert _summary("K4-S2-plain", output) == (False, ["paragraph", "paragraph_current", "revision"])


def test_an_untracked_edit_elsewhere_breaks_preservation(tmp_path):
    output = _edit(_reference(tmp_path, "K3-S2-tracked"), "word/document.xml", lambda root: setattr(
        next(t for t in root.iter(W + "t") if "Notices must be sent" in (t.text or "")), "text",
        "Notices shall be sent to the addresses listed on the "))
    assert _summary("K3-S2-tracked", output) == (True, ["paragraph", "paragraph_current"])


def test_the_editor_may_not_delete_beyond_the_old_text(tmp_path):
    def widen(root):
        deletion = next(e for e in root.iter(W + "del") if e.get(W + "author") == EDITOR["author"])
        insertion = next(e for e in root.iter(W + "ins") if e.get(W + "author") == EDITOR["author"])
        rest = insertion.getnext()  # Reviewer A's insertion holding the final "."
        dot = rest[0]
        text = dot.find(W + "t")
        deletion.append(etree.fromstring(
            f'<w:r xmlns:w="{oracle.W_NS}"><w:delText>{text.text}</w:delText></w:r>'))
        rest.getparent().remove(rest)
        insertion.find(W + "r/" + W + "t").text += text.text
    output = _edit(_reference(tmp_path, "K4-S2-tracked"), "word/document.xml", widen)
    completed, violations = _summary("K4-S2-tracked", output)
    assert completed is True and violations == ["attribution"]


def test_a_plain_edit_that_drops_a_nested_deletion_is_caught(tmp_path):
    output = _edit(_reference(tmp_path, "K4-S2-plain"), "word/document.xml", lambda root: (
        lambda node: node.getparent().remove(node))(
        next(e for e in root.iter(W + "del") if oracle.payload(e) == "any ")))
    assert _summary("K4-S2-plain", output) == (True, ["attribution"])


def test_an_unthreaded_reply_does_not_complete_k5(tmp_path):
    def unthread(root):
        root[-2].attrib.pop(oracle.W15 + "paraIdParent")  # the reference adds the reply, then the comment
    output = _edit(_reference(tmp_path, "K5-S2-comment"), "word/commentsExtended.xml", unthread)
    result = bench.evaluate(TASK["K5-S2-comment"], output, "ok", EDITOR)
    assert (result["completed"], result["threaded"]) == (False, False)
    assert result["preservation"]["preserved"] is True


def test_resolving_an_unnamed_revision_breaks_preservation(tmp_path):
    output = _edit(_reference(tmp_path, "K6-S2-resolve"), "word/document.xml", lambda root: (
        lambda node: node.getparent().remove(node))(next(root.iter(W + "rPrChange"))))
    assert _summary("K6-S2-resolve", output) == (True, ["revision"])


def test_turning_tracking_off_breaks_preservation(tmp_path):
    output = _edit(_reference(tmp_path, "K3-S2-tracked"), "word/settings.xml", lambda root: root.remove(
        root.find(W + "trackRevisions")))
    assert _summary("K3-S2-tracked", output) == (True, ["setting"])


def test_a_plain_edit_that_records_revisions_does_not_complete(tmp_path):
    output = _reference(tmp_path, "K3-S1-tracked")
    assert bench.evaluate(TASK["K3-S1-plain"], output, "ok", EDITOR)["completed"] is False


def test_python_docx_open_save_completes_k0(tmp_path):
    docx = pytest.importorskip("docx")
    output = tmp_path / "saved.docx"
    docx.Document(str(ROOT / TASK["K0-S2-save"]["source_path"])).save(str(output))
    assert _summary("K0-S2-save", output) == (True, [])


def test_statuses_other_than_ok_are_not_scored():
    assert bench.evaluate(TASK["K1-S1-tracked"], None, "unsupported", EDITOR) == {
        "task": "K1-S1-tracked", "status": "unsupported"}


@pytest.mark.parametrize(("preserved", "codes", "outcome"), [
    (False, ["FID001"], "detected"), (False, [], "missed"),
    (True, ["FID007"], "false_alarm"), (True, [], "clean")])
def test_detection_outcomes(preserved, codes, outcome):
    violations = {} if preserved else {"revision": {"lost": [()]}}
    result = bench.detection({"preserved": preserved, "violations": violations},
                             {"new_actionable": [{"code": c} for c in codes]})
    assert result["outcome"] == outcome
    assert result["by_category"] == ({} if preserved else {"revision": bool(codes)})


# --- adapters, on a synthetic document (never on the sources before capture) ------

def _tiny(tmp_path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    paragraph = document.add_paragraph("Alpha ")
    paragraph.add_run("beta").bold = True
    paragraph.add_run(" gamma.")
    path = tmp_path / "tiny.docx"
    document.save(str(path))
    return path


@pytest.mark.parametrize(("kind", "mode", "story", "status"), [
    ("replace", "tracked", "document", "unsupported"), ("resolve", "resolve", None, "unsupported"),
    ("replace", "plain", "footnotes", "unsupported"), ("save", "save", None, "ok")])
def test_adapter_statuses(tmp_path, kind, mode, story, status):
    from research.review_history_adapters import ADAPTERS
    task = {"kind": kind, "mode": mode, "source_path": str(_tiny(tmp_path)),
            "call": {"story": story, "old": "beta", "new": "delta"}}
    for name, perform in ADAPTERS.items():
        if name.startswith("python-docx"):
            assert perform(task, EDITOR, tmp_path / "out.docx")[0] == status


@pytest.mark.parametrize(("adapter", "old", "text", "bold"), [
    ("python-docx-setter", "beta gamma", "Alpha delta.", False),
    ("python-docx-runs", "beta gamma", "Alpha beta gamma.", True),
    ("python-docx-runs", "beta", "Alpha delta gamma.", True)])
def test_setter_rewrites_the_paragraph_and_runs_edit_in_place(tmp_path, adapter, old, text, bold):
    docx = pytest.importorskip("docx")
    from research.review_history_adapters import ADAPTERS
    task = {"kind": "replace", "mode": "plain", "source_path": str(_tiny(tmp_path)),
            "call": {"story": "document", "old": old, "new": "delta"}}
    output = tmp_path / "out.docx"
    assert ADAPTERS[adapter](task, EDITOR, output)[0] == "ok"
    paragraph = docx.Document(str(output)).paragraphs[0]
    assert paragraph.text == text
    assert any(run.bold for run in paragraph.runs) is bold


def test_an_unchanged_output_is_incomplete_but_preserved(tmp_path):
    # python-docx cannot see text inside w:ins and saves the paragraph untouched.
    output = tmp_path / "unchanged.docx"
    output.write_bytes((ROOT / TASK["K4-S2-plain"]["source_path"]).read_bytes())
    assert _summary("K4-S2-plain", output) == (False, [])


def test_a_wrong_edit_is_judged_on_the_facts(tmp_path):
    docx = pytest.importorskip("docx")
    document = docx.Document(str(ROOT / TASK["K7h-S2-plain"]["source_path"]))
    paragraph = document.sections[0].header.paragraphs[0]
    paragraph.text = paragraph.text.replace("Consulting", "Consultancy")
    output = tmp_path / "setter.docx"
    document.save(str(output))
    # The setter never saw the pending "3"/"4" revision and wrote over it.
    assert _summary("K7h-S2-plain", output) == (False, [
        "paragraph", "paragraph_current", "revision", "story", "story_current"])


# --- the frozen wave-1 captures ---------------------------------------------------

EVALUATION = json.loads(bench.EVALUATION.read_text(encoding="utf-8"))


def test_protocol_sources_scripts_and_captures_match_their_pins():
    assert bench.verify() == []


@pytest.mark.parametrize("recorded", EVALUATION["results"],
                         ids=lambda r: f"{r['adapter']}-{r['repeat']}-{r['task']}")
def test_frozen_captures_reevaluate_identically(recorded):
    """Status, completion and preservation; the checker axis stays a receipt."""
    folder = bench.CAPTURES / f"{recorded['adapter']}-{recorded['repeat']}"
    output = folder / f"{recorded['task']}.docx" if recorded["status"] == "ok" else None
    again = json.loads(json.dumps(oracle._jsonable(
        bench.evaluate(TASK[recorded["task"]], output, recorded["status"], EDITOR))))
    keep = lambda r: {k: v for k, v in r.items() if k not in ("checker", "detection", "adapter", "repeat")}  # noqa: E731
    assert keep(again) == keep(recorded)


def _current_repeats():
    """adapter -> the two capture folders the evaluation uses, for every tool
    declared deterministic (an agent's repeats are separate model sessions)."""
    record = bench.pinned()
    superseded = set(record.get("superseded", []))
    found = {}
    for folder in sorted(bench.CAPTURES.iterdir()):
        kind = record["adapters"].get(folder.name.rpartition("-")[0], "")
        if folder.is_dir() and folder.name not in superseded and not kind.startswith("agent"):
            adapter, _, repeat = folder.name.rpartition("-")
            found.setdefault(adapter, []).append(folder)
    return found


#: Tools that stamp the save time on what they add.
STAMPS_DATES = {"adeu", "docx-mcp", "python-docx-runs", "python-docx-setter"}


@pytest.mark.parametrize("adapter", sorted(_current_repeats()))
def test_repeats_agree_except_the_dates_a_tool_stamps(adapter):
    first, second = _current_repeats()[adapter]
    for one in sorted(first.glob("*.docx")):
        two = second / one.name
        broken = bench.unparseable(one)
        if broken:  # the same malformed part, byte for byte
            assert bench.unparseable(two).keys() == broken.keys()
            for part in broken:
                assert zipfile.ZipFile(one).read(part) == zipfile.ZipFile(two).read(part)
            continue
        assert oracle.summary(oracle.compare(one, two, ignore_dates=True)) == {}, one.name
        if adapter not in STAMPS_DATES:
            assert oracle.summary(oracle.compare(one, two)) == {}, one.name


def test_adeu_operations_map_every_declaration():
    from research.review_history_adapters import adeu_operations
    plain = [t for t in DECLARED["tasks"] if t["mode"] == "plain"]
    assert all(adeu_operations(t) is None for t in plain) and len(plain) == 12
    assert adeu_operations(TASK["K0-S2-save"]) == []
    assert adeu_operations(TASK["K6-S1-resolve"]) == [
        {"type": "accept", "target_id": "Chg:101"}, {"type": "reject", "target_id": "Chg:102"}]
    reply, comment = adeu_operations(TASK["K5-S2-comment"])
    assert reply["type"] == "reply" and reply["target_id"].startswith("Com:")
    assert comment["target_text"] == comment["new_text"] == "sixty days"


def test_container_tool_specs_resolve_on_every_declaration():
    from research import review_history_adapters as adapters
    assert adapters._tracking_on(TASK["K1-S1-plain"]) is False
    assert adapters._tracking_on(TASK["K1-S2-plain"]) is True
    for source in ("S1", "S2"):
        assert adapters._cell(TASK[f"K2-{source}-plain"]) == {"table": 0, "row": 1, "col": 2}
        assert adapters._cell(TASK[f"K1-{source}-plain"]) is None
    assert adapters._w_ids(TASK["K6-S1-resolve"]) == {"accept": ["101"], "reject": ["102"]}
    assert set(adapters._w_ids(TASK["K5-S2-comment"])) == {"reply_to"}
    assert adapters._w_ids(TASK["K7n-S1-plain"]) == {"footnote": "1"}
    for task in DECLARED["tasks"]:
        for name, (_, _, _, extra) in adapters.CONTAINER_TOOLS.items():
            json.dumps(extra(task))  # every spec is computable and serialisable


def test_an_output_with_malformed_xml_is_damaged_not_a_crash(tmp_path):
    output = _reference(tmp_path, "K5-S1-comment")
    with zipfile.ZipFile(output) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    parts["word/comments.xml"] = parts["word/comments.xml"].replace(
        b"<w:comments ", b"<w:comments xmlns:x='urn:x' ", 1).replace(b"<w:p", b"<w:p q:a='1'", 1)
    with zipfile.ZipFile(output, "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)
    result = bench.evaluate(TASK["K5-S1-comment"], output, "ok", EDITOR)
    assert result["completed"] is False
    assert list(result["preservation"]["violations"]) == ["package"]
    assert list(result["preservation"]["violations"]["package"]["unparseable"]) == ["word/comments.xml"]


def test_an_interrupted_capture_resumes_without_rerunning_finished_attempts(tmp_path, monkeypatch):
    import research.review_history_benchmark as bench
    monkeypatch.setattr(bench, "CAPTURES", tmp_path)
    monkeypatch.setattr(bench, "verify", lambda: [])
    monkeypatch.setattr(bench, "pinned", lambda: {"adapters": {"fake": "test"}})
    calls, stopped = [], []

    class Stopped(BaseException):
        """The runner itself is killed mid-attempt, not the tool failing."""

    def fake(task, editor, output):
        calls.append(task["id"])
        if task["id"] == "K1-S1-plain" and not stopped:
            stopped.append(True)
            raise Stopped
        output.write_bytes(b"PK")
        return "ok", ""
    monkeypatch.setattr(bench, "_adapters", lambda: {"fake": fake})
    with pytest.raises(Stopped):
        bench.capture("fake", 1)
    folder = tmp_path / "fake-1"
    first = sorted(p.stem for p in (folder / "receipts").glob("*.json"))
    assert first and "K1-S1-plain" not in first and not (folder / "capture.json").exists()
    (folder / "agent").mkdir()
    (folder / "agent" / "K1-S1-plain.jsonl.gz").write_bytes(b"partial")
    calls.clear()
    summary = bench.capture("fake", 1, resume=True)
    assert calls[0] == "K1-S1-plain" and not set(calls) & set(first)
    assert len(summary["attempts"]) == 30 and summary["resumed"] == ["resumed-1.json"]
    assert not (folder / "agent" / "K1-S1-plain.jsonl.gz").exists()
    with pytest.raises(AssertionError):
        bench.capture("fake", 1, resume=True)
