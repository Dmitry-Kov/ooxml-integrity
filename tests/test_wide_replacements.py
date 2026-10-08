"""FID013: a tracked replacement wider than the change.

docx-cli edited a footnote by deleting its whole text and inserting it again
with one phrase changed. Nothing was lost, so no rule reported it, but a
reviewer sees the unchanged words struck through and added again under the
editor's name. A replacement is reported when the unchanged words it carries
are at least four and outnumber the words it changes.
"""
from __future__ import annotations

import json
import zipfile

import pytest

from conftest import ROOT
from ooxml_integrity import WARN, Expectation, compare, expect
from ooxml_integrity.policy import fingerprint
from ooxml_integrity.replacements import unchanged_words

BENCH = ROOT / "evidence/review-history-benchmark"
TASKS = {t["id"]: t for t in json.loads((BENCH / "tasks.json").read_text())["tasks"]}
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MAIN = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"


def wide(source, edited):
    return [f for f in compare(source, edited) if f.code == "FID013"]


def pair(capture, task):
    return ROOT / TASKS[task]["source_path"], BENCH / "captures" / capture / f"{task}.docx"


def docx(path, body):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   f'<Override PartName="/word/document.xml" ContentType="{MAIN}"/></Types>')
        z.writestr("_rels/.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                   'relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml",
                   f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>')
    return path


OLD = "The Supplier shall deliver the goods within thirty days of the order."


def replaced(old, new, author="Ed", date="2026-10-01T00:00:00Z", between=""):
    return (f'<w:p><w:del w:id="1" w:author="{author}" w:date="{date}"><w:r><w:delText>{old}'
            f'</w:delText></w:r></w:del>{between}<w:ins w:id="2" w:author="Ed" w:date="{date}">'
            f'<w:r><w:t>{new}</w:t></w:r></w:ins></w:p>')


def test_a_note_deleted_and_inserted_again_to_change_one_phrase_is_reported():
    (finding,) = wide(*pair("docx-cli-5", "K7n-S2-tracked"))
    assert finding.severity is WARN and finding.where == "footnotes"
    assert finding.extra["author"] == "Benchmark Editor"
    assert (finding.extra["unchanged_words"], finding.extra["changed_words"]) == (6, 3)
    assert "Business days exclude public holidays in" in finding.extra["deleted"]


@pytest.mark.parametrize("capture, task", [
    ("reference-1", "K3-S2-tracked"),   # "ten business days" -> "fifteen business days"
    ("reference-1", "K4-S1-tracked"),   # "professional indemnity insurance" -> "... liability ..."
    ("reference-1", "K7n-S1-tracked"),  # "section 17.3.1" -> "section 17.3.2"
    ("codex-1", "K7h-S2-tracked"),
    ("claude-code-1", "K7n-S2-tracked"),
])
def test_a_replaced_phrase_keeping_a_word_or_two_of_itself_is_not(capture, task):
    assert wide(*pair(capture, task)) == []


def test_a_rewritten_sentence_that_keeps_its_first_words_is_not():
    # four unchanged words, but nine of the replaced words change
    assert wide(ROOT / "corpus/base.docx", ROOT / "runs/t5_rewrite_bare/agreement.docx") == []


def test_unchanged_words_are_the_shared_start_and_end_only():
    assert unchanged_words(OLD, OLD.replace("thirty", "sixty")) == 11
    assert unchanged_words("the cat sat on the mat", "a dog lay on a rug") == 0
    assert unchanged_words("Net 30 days", "Net 30 days") == 3


@pytest.mark.parametrize("edit, reported", [
    (replaced(OLD, OLD.replace("thirty", "sixty")), True),
    # the same replacement already pending in the source is not the edit's
    ("known", False),
    # deletion and insertion by different authors are two edits, not one
    (replaced(OLD, OLD.replace("thirty", "sixty"), author="Someone else"), False),
    # text between them makes them two replacements
    (replaced(OLD, OLD.replace("thirty", "sixty"), between="<w:r><w:t> and </w:t></w:r>"), False),
    # a sentence rewritten from end to end
    (replaced(OLD, "The Client must pay each invoice when it is received."), False),
])
def test_only_a_replacement_the_edit_added_and_mostly_unchanged_is_reported(tmp_path, edit, reported):
    wide_edit = replaced(OLD, OLD.replace("thirty", "sixty"))
    source_body = wide_edit if edit == "known" else f"<w:p><w:r><w:t>{OLD}</w:t></w:r></w:p>"
    source = docx(tmp_path / "source.docx", source_body)
    edited = docx(tmp_path / "edited.docx", wide_edit if edit == "known" else edit)
    findings = wide(source, edited)
    assert bool(findings) is reported
    if reported:
        assert findings[0].extra["story"] == "document"
        assert (findings[0].extra["unchanged_words"], findings[0].extra["changed_words"]) == (11, 1)


def test_its_baseline_identity_holds_no_text_and_an_expectation_can_declare_it():
    source, edited = pair("docx-cli-6", "K7n-S2-tracked")
    (finding,) = wide(source, edited)
    key = fingerprint("out.docx", finding)
    assert "wide-replacement-sha256=" in key and "Business" not in key
    assert key == fingerprint("out.docx", wide(source, edited)[0])
    kept, matched = expect(compare(source, edited),
                           [Expectation("FID013", {"story": "footnotes"},
                                        reason="the pipeline rewrites whole notes")])
    assert len(matched) == 1 and "FID013" not in {f.code for f in kept}
