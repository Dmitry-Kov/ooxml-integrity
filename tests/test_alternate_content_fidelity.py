"""Fidelity of the primary and fallback copies of a Word text box."""
from __future__ import annotations

import json

import pytest
from conftest import read_part, repack, run_cli
from test_repeated_comment_markers import DOC, REFERENCE, _before_section, _boxed_comment, _text_box

from ooxml_integrity import Severity, compare
from ooxml_integrity.policy import apply_baseline, make_baseline


def _loss(source, edited, code, severity):
    findings = compare(source, edited)
    assert [(f.code, f.severity) for f in findings if f.severity != Severity.INFO] == [(code, severity)]
    finding = next(f for f in findings if f.code == code)
    if severity == Severity.WARN:
        assert "fallback" in finding.message.lower()
        assert finding.extra["branch"] == "fallback"

    args = ["check", str(edited), "--against", str(source), "--no-config", "--json"]
    result = run_cli(*args)
    assert result.returncode == (1 if severity == Severity.ERROR else 0), result.stdout + result.stderr
    reported = json.loads(result.stdout)["files"][0]["findings"]
    assert any(f["code"] == code and f["severity"] == severity.value for f in reported)
    if severity == Severity.WARN:
        strict = run_cli(*args, "--fail-on", "warn")
        assert strict.returncode == 1, strict.stdout + strict.stderr
    return finding


def _with_reference(base_docx, dst, choice, fallback):
    return _boxed_comment(base_docx, dst.parent, choice, fallback).replace(dst)


@pytest.mark.parametrize("before_fallback,after_choice,after_fallback,severity", [
    ("", "", REFERENCE, Severity.ERROR),
    (REFERENCE, REFERENCE, "", Severity.WARN),
], ids=["move-to-fallback", "drop-fallback-copy"])
def test_text_box_comment_reference(tmp_docx, tmp_path, before_fallback, after_choice,
                                    after_fallback, severity):
    source = _with_reference(tmp_docx, tmp_path / "source.docx", REFERENCE, before_fallback)
    edited = _with_reference(tmp_docx, tmp_path / "edited.docx", after_choice, after_fallback)
    finding = _loss(source, edited, "FID001", severity)
    assert finding.extra["tag"] == "commentReference"
    assert finding.extra["before"] - finding.extra["after"] == 1


# Long enough to exceed FID003's margin even with the rest of base.docx present.
TERMS = "The fee is payable only after written acceptance. " * 12


def _with_text_box(base_docx, dst, choice, fallback):
    def paragraph(text):
        return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"

    box = _text_box(paragraph(choice), paragraph(fallback or ""))
    if fallback is None:  # the editor dropped the entire backup representation
        start, end = box.index("<mc:Fallback>"), box.index("</mc:Fallback>") + len("</mc:Fallback>")
        box = box[:start] + box[end:]
    return repack(base_docx, dst, {DOC: _before_section(read_part(base_docx, DOC), box)})


@pytest.mark.parametrize("before_fallback,after_choice,after_fallback,severity", [
    ("", "", TERMS, Severity.ERROR),
    (TERMS, TERMS, None, Severity.WARN),
], ids=["move-to-fallback", "drop-fallback-branch"])
def test_text_box_text_volume(base_docx, tmp_path, before_fallback, after_choice, after_fallback, severity):
    source = _with_text_box(base_docx, tmp_path / "source.docx", TERMS, before_fallback)
    edited = _with_text_box(base_docx, tmp_path / "edited.docx", after_choice, after_fallback)
    finding = _loss(source, edited, "FID003", severity)
    assert finding.extra["before"] - finding.extra["after"] == len(TERMS)


@pytest.mark.parametrize("branch", ["Choice", "Fallback"])
def test_only_a_primary_tracked_deletion_accounts_for_primary_text_loss(base_docx, tmp_path, branch):
    source = _with_text_box(base_docx, tmp_path / "source.docx", TERMS, "")
    deletion = ('<w:p><w:del w:id="246" w:author="Editor" w:date="2026-09-27T00:00:00Z">'
                f'<w:r><w:delText>{TERMS}</w:delText></w:r></w:del></w:p>')
    box = _text_box(deletion, "<w:p/>") if branch == "Choice" else _text_box("<w:p/>", deletion)
    edited = repack(base_docx, tmp_path / "tracked.docx",
                    {DOC: _before_section(read_part(base_docx, DOC), box)})
    loss = [f for f in compare(source, edited) if f.code == "FID003"]
    if branch == "Choice":
        assert loss == []
    else:
        [finding] = loss
        assert finding.severity == Severity.ERROR
        assert finding.extra["before"] - finding.extra["after"] == len(TERMS)


@pytest.mark.parametrize("with_box,content,code", [
    (_with_reference, REFERENCE, "FID001"), (_with_text_box, TERMS, "FID003"),
], ids=["comment-reference", "text"])
def test_baselining_a_backup_loss_preserves_the_primary_error(base_docx, tmp_path, with_box, content, code):
    source = with_box(base_docx, tmp_path / "source.docx", content, content)
    edited = with_box(base_docx, tmp_path / "edited.docx", content, "")
    [backup] = [f for f in compare(source, edited) if f.code == code]
    assert backup.severity == Severity.WARN
    allowance = make_baseline({str(edited): [backup]})["findings"]
    assert apply_baseline(str(edited), [backup], allowance.copy())[0] == []

    with_box(base_docx, edited, "", content)
    [primary] = [f for f in compare(source, edited) if f.code == code]
    assert primary.severity == Severity.ERROR
    assert apply_baseline(str(edited), [primary], allowance) == ([primary], [])


def test_rewrapping_the_same_text_in_both_copies_is_clean(tmp_docx, tmp_path):
    source = _boxed_comment(tmp_docx, tmp_path)
    doc = read_part(source, DOC)
    text = "<w:r><w:t>Boxed</w:t></w:r>"
    assert doc.count(text) == 2
    edited = repack(source, tmp_path / "rewrapped.docx",
                    {DOC: doc.replace(text, "<w:r><w:t>Box</w:t></w:r><w:r><w:t>ed</w:t></w:r>").encode()})
    assert compare(source, edited) == []
    result = run_cli("check", str(edited), "--against", str(source), "--no-config", "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["files"][0]["findings"] == []


def test_replacing_tracked_text_only_in_the_backup_warns_even_at_equal_length(base_docx, tmp_path):
    def with_revision(path, word):
        revision = (f'<w:p><w:ins w:id="4001" w:author="Reviewer"><w:r><w:t>{word}</w:t>'
                    '</w:r></w:ins></w:p>')
        box = _text_box("<w:p/>", revision)
        return repack(base_docx, path, {DOC: _before_section(read_part(base_docx, DOC), box)})

    source = with_revision(tmp_path / "source.docx", "confirmed")
    edited = with_revision(tmp_path / "edited.docx", "withdrawn")
    finding = _loss(source, edited, "FID009", Severity.WARN)
    assert finding.extra["body"] == "confirmed"
