"""New text must not silently inherit an old pending insertion's attribution."""
from __future__ import annotations

import json
import copy

import pytest

from conftest import ROOT, read_part, repack, run_cli
from ooxml_integrity import Severity, compare
from ooxml_integrity.revision_growth import assess, inventory
from ooxml_integrity.xmlutil import fromstring

MAIN = 'word/document.xml'
NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
UTC = 'http://schemas.microsoft.com/office/word/2023/wordml/word16du'
DATE = '2026-09-29T10:00:00Z'


def run(text, deleted=False):
    tag = 'delText' if deleted else 't'
    return f'<w:r><w:{tag} xml:space="preserve">{text}</w:{tag}></w:r>'


def revision(text, *, kind='ins', author='Counsel', date=DATE, ident=1, content=False):
    body = text if content else run(text, kind == 'del')
    return (f'<w:{kind} w:id="{ident}" w:author="{author}" w:date="{date}">'
            f'{body}</w:{kind}>')


def document(body):
    return (f'<w:document xmlns:w="{NS}" xmlns:w16du="{UTC}"><w:body>'
            f'{body}<w:sectPr/></w:body></w:document>').encode()


def pair(base, tmp_path, before, after):
    return (repack(base, tmp_path / 'source.docx', {MAIN: document(before)}),
            repack(base, tmp_path / 'edited.docx', {MAIN: document(after)}))


def paragraph(content):
    return f'<w:p>{content}</w:p>'


def attribution(source, edited):
    return [f for f in compare(source, edited) if f.code == 'FID011']


def test_untracked_growth_inside_old_insertion_warns(base_docx, tmp_path):
    source, edited = pair(base_docx, tmp_path,
                          paragraph(revision('indemnity insurance')),
                          paragraph(revision('indemnity insurance liability')))
    found = attribution(source, edited)
    assert len(found) == 1
    assert found[0].severity is Severity.WARN
    assert found[0].extra['additional_text'] == ' liability'
    assert found[0].extra['author'] == 'Counsel'
    assert 'edit intent' in found[0].message


def test_new_text_beside_nested_tracked_deletion_still_has_old_author(base_docx, tmp_path):
    old = revision('indemnity insurance')
    new = revision(revision('indemnity insurance', kind='del', author='Editor', ident=2)
                   + run('liability insurance'), content=True)
    source, edited = pair(base_docx, tmp_path, paragraph(old), paragraph(new))
    found = attribution(source, edited)
    assert len(found) == 1
    assert found[0].extra['additional_text'] == 'liability insurance'


@pytest.mark.parametrize('new', [
    revision('abc', ident=99),  # IDs are not revision context.
    revision(run('a') + run('bc'), content=True),
    revision('a') + revision('bc', ident=3),  # Legitimate wrapper fragmentation.
    revision('abc') + revision('new', author='Editor', ident=2),
    revision(run('a') + revision('new', author='Editor', ident=2) + run('bc'), content=True),
    revision(run('a') + revision('b', kind='del', author='Editor', ident=2)
             + revision('x', author='Editor', ident=3) + run('c'), content=True),
])
def test_correct_new_revisions_and_fragmentation_do_not_warn(base_docx, tmp_path, new):
    source, edited = pair(base_docx, tmp_path, paragraph(revision('abc')), paragraph(new))
    assert attribution(source, edited) == []


def test_coalesced_source_wrappers_do_not_warn(base_docx, tmp_path):
    source, edited = pair(base_docx, tmp_path,
                          paragraph(revision('ab') + revision('cd', ident=2)),
                          paragraph(revision('abcd')))
    assert attribution(source, edited) == []


def test_contexts_are_not_combined_to_hide_growth(base_docx, tmp_path):
    source, edited = pair(base_docx, tmp_path,
        paragraph(revision('abc') + revision('xyz', author='Reviewer', ident=2)),
        paragraph(revision('abc') + revision('xyzabc', author='Reviewer', ident=2)))
    found = attribution(source, edited)
    assert len(found) == 1 and found[0].extra['author'] == 'Reviewer'


@pytest.mark.parametrize('after', [revision('acb'), revision('abd'), revision('abc', author='New')])
def test_changed_or_missing_source_text_is_explicitly_skipped(after):
    source = inventory(fromstring(document(paragraph(revision('abc')))))
    edited = inventory(fromstring(document(paragraph(after))))
    result = assess(source, edited)
    assert result.findings == [] and result.compared == 0 and result.skipped


def test_effective_utc_prevents_offset_date_only_changes_from_warning(base_docx, tmp_path):
    before = revision('abc').replace(f'w:date="{DATE}"',
        f'w:date="2026-09-29T15:00:00Z" w16du:dateUtc="{DATE}"')
    source, edited = pair(base_docx, tmp_path, paragraph(before), paragraph(revision('abc')))
    assert attribution(source, edited) == []


def test_new_revision_with_same_metadata_is_explicitly_ambiguous(base_docx, tmp_path):
    source, edited = pair(base_docx, tmp_path, paragraph(revision('abc')),
                          paragraph(revision('abc') + revision('new', ident=2)))
    found = attribution(source, edited)
    assert len(found) == 1 and found[0].severity is Severity.WARN
    assert 'metadata does not establish edit intent' in found[0].message


@pytest.mark.parametrize('proper', [False, True])
def test_real_s2_nested_pending_deletion_keeps_its_context(tmp_path, proper):
    """The exact S2 Fees source span from the declared Word #3 observation.

    Reproduce its source-preserving wrong-span transformation locally, then
    contrast it with a new insertion around the added text. No frozen receipt
    or native-Word artifact is modified.
    """
    source = ROOT / 'evidence/review-history-benchmark/sources/word-review.docx'
    tree = fromstring(read_part(source, MAIN).encode())
    w = '{' + NS + '}'
    pending = next(node for node in tree.iter(w + 'ins')
                   if node.get(w + 'author') == 'Reviewer A'
                   and any(t.text == ' The Client may withhold ' for t in node.iter(w + 't')))
    old_run = pending[0]
    old_run.find(w + 't').text = ' withhold '
    deleted = fromstring(revision(' The Client may', kind='del', author='Benchmark Editor',
                                 date='2026-10-01T00:00:00Z', ident=17).replace(
                                     '<w:del ', f'<w:del xmlns:w="{NS}" ', 1).encode())
    # A small namespace-owning container avoids depending on inherited prefixes.
    wrapper = fromstring(document(paragraph(
        revision('disputed sum', author='Benchmark Editor', date='2026-10-01T00:00:00Z', ident=18)
        if proper else run('disputed sum'))))
    inserted = copy.deepcopy(wrapper.find(w + 'body/' + w + 'p')[0])
    pending.insert(0, deleted)
    pending.insert(1, inserted)
    from lxml import etree
    output = repack(source, tmp_path / ('proper.docx' if proper else 'wrong-span.docx'),
                    {MAIN: etree.tostring(tree)})
    found = attribution(source, output)
    if proper:
        assert found == []
    else:
        assert len(found) == 1
        assert found[0].extra['author'] == 'Reviewer A'
        assert found[0].extra['additional_characters'] == len('disputed sum')


def test_changing_a_source_nested_deletion_context_is_skipped():
    old = revision(run('a') + revision('b', kind='del', author='Other', ident=2)
                   + run('c'), content=True)
    changed = revision(run('a') + revision('b', kind='del', author='Changed', ident=2)
                       + run('cnew'), content=True)
    result = assess(inventory(fromstring(document(paragraph(old)))),
                    inventory(fromstring(document(paragraph(changed)))))
    assert result.findings == [] and result.compared == 0 and result.skipped


def test_growth_inside_a_pre_existing_nested_deletion_is_explicitly_skipped():
    old = revision(run('a') + revision('b', kind='del', author='Other', ident=2)
                   + run('c'), content=True)
    changed = revision(run('a') + revision('bX', kind='del', author='Other', ident=2)
                       + run('c'), content=True)
    result = assess(inventory(fromstring(document(paragraph(old)))),
                    inventory(fromstring(document(paragraph(changed)))))
    assert result.findings == [] and result.compared == 0
    assert result.skipped == ['surplus text under another pre-existing revision context']


def test_unsupported_source_content_and_output_have_honest_coverage(base_docx, tmp_path):
    before = paragraph(revision('abc') + revision('<w:r><w:tab/></w:r>', ident=2,
                                                  author='Other', content=True))
    source, edited = pair(base_docx, tmp_path, before, before)
    result = run_cli('check', str(edited), '--against', str(source), '--coverage', '--json')
    report = json.loads(result.stdout)['files'][0]['coverage']
    item = next(x for x in report['items'] if x['id'] == 'docx.fidelity.insertion-attribution')
    assert item['status'] == 'estimated' and item['count'] == 1
    assert 'unsupported' in item['reason']


def test_source_with_no_insertions_has_absent_coverage(base_docx, tmp_path):
    source, edited = pair(base_docx, tmp_path, paragraph(run('abc')), paragraph(run('abc')))
    result = run_cli('check', str(edited), '--against', str(source), '--coverage', '--json')
    report = json.loads(result.stdout)['files'][0]['coverage']
    item = next(x for x in report['items'] if x['id'] == 'docx.fidelity.insertion-attribution')
    assert item['status'] == 'not-present' and item['count'] == 0


def word_inserted_paragraph(text):
    """Word marks an inserted paragraph's mark with an empty w:ins in its
    w:rPr and writes proofing and page-break markers inside the insertion."""
    mark = f'<w:pPr><w:rPr><w:ins w:id="5" w:author="Counsel" w:date="{DATE}"/></w:rPr></w:pPr>'
    body = ('<w:proofErr w:type="spellStart"/>'
            f'<w:r><w:lastRenderedPageBreak/><w:t xml:space="preserve">{text}</w:t></w:r>'
            '<w:proofErr w:type="spellEnd"/><w:bookmarkStart w:id="0" w:name="x"/>'
            '<w:bookmarkEnd w:id="0"/>')
    return paragraph(mark + revision(body, content=True))


@pytest.mark.parametrize('after, added', [
    ('indemnity insurance', None), ('indemnity insurance liability', ' liability'),
])
def test_word_inserted_paragraph_markers_are_compared(base_docx, tmp_path, after, added):
    source, edited = pair(base_docx, tmp_path, word_inserted_paragraph('indemnity insurance'),
                          word_inserted_paragraph(after))
    found = attribution(source, edited)
    assert [f.extra['additional_text'] for f in found] == ([added] if added else [])
    result = run_cli('check', str(edited), '--against', str(source), '--coverage', '--json')
    report = json.loads(result.stdout)['files'][0]['coverage']
    item = next(x for x in report['items'] if x['id'] == 'docx.fidelity.insertion-attribution')
    assert item['status'] == 'checked' and item['count'] == 1
