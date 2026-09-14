"""Text loss with equal revision counts, independent of wrapper IDs."""
from copy import deepcopy
import json
from pathlib import Path

from lxml import etree as E
import pytest

from conftest import repack, run_cli
from ooxml_integrity import compare
from ooxml_integrity.coverage import docx_coverage

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'evidence/docx-revisions'
DOC = 'word/document.xml'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def make(base, path, texts, tag='ins'):
    root = E.Element(W+'document', nsmap={'w': W[1:-1]})
    body = E.SubElement(root, W+'body')
    for ident, text in enumerate(texts, 1):
        p = E.SubElement(body, W+'p')
        rev = E.SubElement(p, W+tag, {W+'id':str(ident), W+'author':'Reviewer'})
        run = E.SubElement(rev, W+'r')
        E.SubElement(run, W+('t' if tag == 'ins' else 'delText')).text = text
    return repack(base, path, {DOC:E.tostring(root)}), root


def text_findings(source, edited):
    return [f for f in compare(source, edited) if f.code == 'FID009']


def test_recorded_count_neutral_loss_is_now_detected():
    source = BASE/'sources/basic.docx'
    output = BASE/'outputs/replace-unrelated-insertion.docx'
    found = text_findings(source, output)
    assert len(found) == 1
    assert found[0].severity.value == 'error'
    assert found[0].part == DOC
    assert found[0].extra == {'tag':'ins', 'body':'optional', 'lost':1, 'in_source':1}


@pytest.mark.parametrize('tag', ['ins', 'del'])
@pytest.mark.parametrize('replacement', ['invented', 'optionaL', 'optiona', 'op tional', ''])
def test_equal_count_payload_change(base_docx, tmp_path, tag, replacement):
    source, _ = make(base_docx, tmp_path/'source.docx', ['optional'], tag)
    output, _ = make(base_docx, tmp_path/'output.docx', [replacement], tag)
    found = text_findings(source, output)
    if not replacement:
        # An empty revision is outside the declared plain-text profile.
        assert not found
    else:
        assert len(found) == 1 and found[0].extra['tag'] == tag


@pytest.mark.parametrize('tag', ['ins', 'del'])
def test_duplicate_wording_requires_enough_occurrences(base_docx, tmp_path, tag):
    source, _ = make(base_docx, tmp_path/'source.docx', ['review', 'review'], tag)
    output, _ = make(base_docx, tmp_path/'output.docx', ['review', 'changed'], tag)
    found = text_findings(source, output)
    assert len(found) == 1
    assert found[0].extra['lost'] == 1 and found[0].extra['in_source'] == 2


@pytest.mark.parametrize('tag', ['ins', 'del'])
def test_ids_run_splits_and_untracked_edits_are_not_text_loss(base_docx, tmp_path, tag):
    source, root = make(base_docx, tmp_path/'source.docx', ['optional', 'review'], tag)
    for ordinal, rev in enumerate(root.iter(W+tag), 100):
        rev.set(W+'id', str(ordinal))
        rev.set(W+'author', 'Another spelling')  # Metadata is not this rule's scope.
        text_tag = W+('t' if tag == 'ins' else 'delText')
        text = rev.find('.//'+text_tag).text
        rev.find('.//'+text_tag).text = text[:2]
        copy = deepcopy(rev[0]); copy.find(text_tag).text = text[2:]
        rev.append(copy)
        p = rev.getparent()
        E.SubElement(E.SubElement(p, W+'r'), W+'t').text = 'An unrelated requested edit.'
    output = repack(source, tmp_path/'output.docx', {DOC:E.tostring(root)})
    assert text_findings(source, output) == []


@pytest.mark.parametrize('tag', ['ins', 'del'])
def test_coalescence_with_a_new_revision_and_equal_counts_is_not_loss(base_docx, tmp_path, tag):
    source, root = make(base_docx, tmp_path/'source.docx', ['red', ' blue'], tag)
    a, b = list(root.iter(W+tag))
    for run in list(b):
        a.append(run)
    b[0:] = []
    E.SubElement(E.SubElement(b, W+'r'), W+('t' if tag == 'ins' else 'delText')).text = 'new'
    output = repack(source, tmp_path/'output.docx', {DOC:E.tostring(root)})
    assert text_findings(source, output) == []


@pytest.mark.parametrize('name', ['source-control', 'adeu-shared-id', 'unique-id-control'])
def test_saved_word_coalescence_remains_clean(name):
    base = ROOT/'evidence/docx-word-id-followup'
    assert not [f for f in compare(base/'inputs'/f'{name}.docx',
                                  base/'outputs'/f'{name}-word.docx')
                if f.severity.value in ('error', 'warn')]


@pytest.mark.parametrize('defect', ['nested', 'field', 'empty', 'paragraph-mark'])
def test_unsupported_revision_content_declares_a_skip(base_docx, tmp_path, defect):
    source, root = make(base_docx, tmp_path/'source.docx', ['optional'])
    rev = next(root.iter(W+'ins'))
    if defect == 'nested':
        p = rev.getparent()
        outer = E.Element(W+'del', {W+'id':'20', W+'author':'Reviewer'})
        p.replace(rev, outer); outer.append(rev)
    elif defect == 'field':
        E.SubElement(rev[0], W+'fldChar', {W+'fldCharType':'begin'})
    elif defect == 'empty':
        rev.clear()
    else:
        p = rev.getparent(); p.remove(rev)
        props = E.SubElement(E.SubElement(p, W+'pPr'), W+'rPr')
        props.append(rev)
    output = repack(source, tmp_path/'unsupported.docx', {DOC:E.tostring(root)})
    findings = compare(source, output)
    assert not [f for f in findings if f.code == 'FID009']
    coverage = {i.id:i for i in docx_coverage(output, findings, source=source).items}
    assert coverage['docx.fidelity.revision-text'].status.value == 'skipped'
    assert 'unsupported' in coverage['docx.fidelity.revision-text'].reason


def test_note_revision_loss_is_still_outside_this_fix():
    assert not text_findings(BASE/'sources/notes.docx', BASE/'outputs/unwrap-note-insertion.docx')


def test_cli_json_sarif_and_baseline_keep_new_losses_visible(tmp_path):
    source = BASE/'sources/basic.docx'
    output = BASE/'outputs/replace-unrelated-insertion.docx'
    sarif = tmp_path/'report.sarif'
    result = run_cli('check', str(output), '--against', str(source), '--no-config',
                     '--coverage', '--json', '--sarif', str(sarif))
    assert result.returncode == 1
    report = json.loads(result.stdout)['files'][0]
    assert any(f['code'] == 'FID009' for f in report['findings'])
    assert any(f['ruleId'] == 'FID009' and f['level'] == 'error'
               for f in json.loads(sarif.read_text())['runs'][0]['results'])
    coverage = {i['id']:i for i in report['coverage']['items']}
    assert coverage['docx.fidelity.revision-text']['status'] == 'checked'
    baseline = tmp_path/'accepted.json'
    recorded = run_cli('check', str(output), '--against', str(source), '--no-config',
                       '--write-baseline', str(baseline))
    assert recorded.returncode == 0
    accepted = run_cli('check', str(output), '--against', str(source), '--no-config',
                       '--baseline', str(baseline), '--json')
    assert accepted.returncode == 0
    assert any(f['code'] == 'FID009' for f in json.loads(accepted.stdout)['files'][0]['suppressed'])


def test_baseline_distinguishes_payload_kind_and_increased_loss():
    from ooxml_integrity.finding import Finding, ERROR
    from ooxml_integrity.policy import fingerprint
    def identity(body='optional', tag='ins', lost=1):
        return fingerprint('file.docx', Finding('FID009', ERROR, 'diagnostic',
                           part=DOC, extra={'body':body,'tag':tag,'lost':lost}))
    assert len({identity(),identity('different'),identity(tag='del'),identity(lost=2)}) == 4
    assert 'optional' not in identity()


def test_search_work_is_bounded_and_incomplete_coverage_is_explicit(base_docx, tmp_path, monkeypatch):
    from ooxml_integrity import coverage as coverage_module
    from ooxml_integrity.revision_text import inventory, assess
    source, old = make(base_docx, tmp_path/'source.docx', ['optional', 'retained'])
    output, new = make(base_docx, tmp_path/'output.docx', ['invented', 'retained'])
    result = assess(inventory(old), inventory(new), scan_limit=0)
    assert not result.findings and result.compared == 1
    assert result.skipped == ['ins: literal-text search budget exhausted']
    monkeypatch.setattr(coverage_module, 'assess_revision_text',
                        lambda a,b: assess(a,b,scan_limit=0))
    item = next(i for i in docx_coverage(output, [], source=source).items
                if i.id == 'docx.fidelity.revision-text')
    assert item.status.value == 'estimated' and item.count == 1
    assert 'budget exhausted' in item.reason


def test_count_change_defers_to_existing_count_checks(base_docx, tmp_path):
    source, _ = make(base_docx, tmp_path/'source.docx', ['optional'])
    output, _ = make(base_docx, tmp_path/'output.docx', ['optional', 'new'])
    assert not text_findings(source, output)
    item = next(i for i in docx_coverage(output, compare(source,output), source=source).items
                if i.id == 'docx.fidelity.revision-text')
    assert item.status.value == 'skipped' and 'count changed' in item.reason


def test_no_source_revisions_is_not_present(base_docx, tmp_path):
    source, _ = make(base_docx, tmp_path/'source.docx', [])
    item = next(i for i in docx_coverage(source, [], source=source).items
                if i.id == 'docx.fidelity.revision-text')
    assert item.status.value == 'not-present' and item.count == 0


def test_incidental_wording_is_a_documented_identity_blind_spot(base_docx, tmp_path):
    source, _ = make(base_docx, tmp_path/'source.docx', ['optional', 'optional optional'])
    output, _ = make(base_docx, tmp_path/'output.docx', ['invented', 'optional optional'])
    # A conservative literal-text witness can mask the loss of one record.
    # Retain this limitation explicitly, rather than claim identity matching.
    assert text_findings(source, output) == []
