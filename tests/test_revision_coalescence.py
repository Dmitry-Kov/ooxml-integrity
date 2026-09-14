"""FID001 coalescence witness: real Word captures plus separate fault injection."""
from copy import deepcopy
from pathlib import Path
import json

from lxml import etree as E
import pytest

from conftest import repack, run_cli
from ooxml_integrity import Severity, compare

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'evidence/docx-word-id-followup'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
UTC = '{http://schemas.microsoft.com/office/word/2023/wordml/word16du}dateUtc'
NS = {'w': W[1:-1]}
DOC = 'word/document.xml'


def losses(source, edited, tag='del'):
    return [f for f in compare(source, edited) if f.code == 'FID001' and f.extra.get('tag') == tag]


@pytest.mark.parametrize('name', ['source-control', 'adeu-shared-id', 'unique-id-control'])
def test_actual_word_saves_do_not_lose_revision_text(name):
    assert not losses(BASE/'inputs'/f'{name}.docx', BASE/'outputs'/f'{name}-word.docx')


def test_word_control_cli_has_no_error_without_policy_suppression():
    result = run_cli('check', str(BASE/'outputs/unique-id-control-word.docx'),
                     '--against', str(BASE/'inputs/unique-id-control.docx'), '--no-config', '--json')
    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)['files'][0]
    assert data['findings'] == [] and data['suppressed'] == []


def pair(base_docx, tmp_path, tag='del', author='Reviewer'):
    root = E.Element(W+'document', nsmap=NS)
    body = E.SubElement(root, W+'body')
    p = E.SubElement(body, W+'p')
    plain = E.SubElement(p, W+'r')
    E.SubElement(plain, W+'t').text = 'Context: '
    for ident, text, style in [('101', 'red', 'b'), ('102', ' blue', 'i')]:
        node = E.SubElement(p, W+tag, {W+'id': ident, W+'author': author,
                                    W+'date': '2026-09-13T11:24:16Z'})
        run = E.SubElement(node, W+'r')
        props = E.SubElement(run, W+'rPr')
        E.SubElement(props, W+style)
        E.SubElement(run, W+('delText' if tag == 'del' else 't')).text = text
    E.SubElement(E.SubElement(body, W+'p'), W+'r')
    source = repack(base_docx, tmp_path/'source.docx', {DOC: E.tostring(root)})
    joined = deepcopy(root)
    left, right = list(joined.iter(W+tag))
    for run in list(right):
        left.append(run)
    right.getparent().remove(right)
    left.set(W+'id', '0')
    return source, joined


@pytest.mark.parametrize('tag', ['ins', 'del'])
def test_joining_and_resplitting_runs_is_not_a_loss(base_docx, tmp_path, tag):
    source, root = pair(base_docx, tmp_path, tag)
    node = root.find('.//w:'+tag, NS)
    run = node[0]
    copied = deepcopy(run)
    run[-1].text, copied[-1].text = 'r', 'ed'
    node.insert(1, copied)
    for prop in node.iter(W+'b'):
        prop.set(W+'val', 'true')
    output = repack(source, tmp_path/'joined.docx', {DOC: E.tostring(root)})
    assert not losses(source, output, tag)


@pytest.mark.parametrize('tag', ['ins', 'del'])
@pytest.mark.parametrize('defect', [
    'drop-character', 'replace-same-length', 'drop-first-fragment', 'drop-last-fragment',
    'duplicate-instead-of-retain', 'reverse-text', 'author', 'date', 'format',
    'unwrap', 'all-lost', 'move-paragraph', 'move-within-paragraph',
])
def test_real_change_with_lower_count_still_reports_loss(base_docx, tmp_path, tag, defect):
    source, root = pair(base_docx, tmp_path, tag)
    node = root.find('.//w:'+tag, NS)
    text_tag = W+('delText' if tag == 'del' else 't')
    if defect == 'drop-character':
        node.find('.//'+text_tag).text = 'rd'
    elif defect == 'replace-same-length':
        node.find('.//'+text_tag).text = 'RED'
    elif defect in ('drop-first-fragment', 'drop-last-fragment'):
        node.remove(node[0 if defect == 'drop-first-fragment' else -1])
    elif defect == 'duplicate-instead-of-retain':
        node.remove(node[1])
        node.append(deepcopy(node[0]))
    elif defect == 'reverse-text':
        node.append(node[0])
    elif defect in ('author', 'date'):
        node.set(W+defect, 'Other' if defect == 'author' else '2026-01-01T00:00:00Z')
    elif defect == 'format':
        props = node[0].find(W+'rPr')
        props.remove(props[0])
    elif defect == 'unwrap':
        p = node.getparent()
        for run in list(node):
            for t in run.iter(text_tag):
                t.tag = W+'t'
            p.insert(p.index(node), run)
        p.remove(node)
    elif defect == 'all-lost':
        node.getparent().remove(node)
    elif defect == 'move-paragraph':
        root.findall('w:body/w:p', NS)[1].append(node)
    else:
        node.getparent().insert(0, node)
    output = repack(source, tmp_path/'changed.docx', {DOC: E.tostring(root)})
    found = losses(source, output, tag)
    assert len(found) == 1 and found[0].severity is Severity.ERROR
    assert found[0].extra == {'tag': tag, 'before': 2, 'after': 0 if defect in ('unwrap', 'all-lost') else 1}


@pytest.mark.parametrize('unsupported', ['field', 'nested', 'empty', 'property-change', 'anchor'])
def test_unsupported_content_retains_count_guard(base_docx, tmp_path, unsupported):
    source, joined = pair(base_docx, tmp_path)
    # Apply the same unsupported content to source and joined versions.
    from zipfile import ZipFile
    with ZipFile(source) as z:
        before = E.fromstring(z.read(DOC))
    for root in (before, joined):
        first = root.find('.//w:del', NS)
        if unsupported == 'field':
            E.SubElement(first[0], W+'fldChar', {W+'fldCharType': 'begin'})
        elif unsupported == 'nested':
            p = first.getparent()
            wrapper = E.Element(W+'ins', {W+'id':'200', W+'author':'Other'})
            p.insert(p.index(first), wrapper)
            wrapper.append(first)
        elif unsupported == 'empty':
            first[0].find(W+'delText').text = ''
        elif unsupported == 'property-change':
            E.SubElement(first[0].find(W+'rPr'), W+'rPrChange', {W+'id':'200'})
        else:
            p = first.getparent()
            p.insert(0, E.Element(W+'commentRangeStart', {W+'id':'1'}))
    source2 = repack(source, tmp_path/'unsupported-source.docx', {DOC:E.tostring(before)})
    output = repack(source, tmp_path/'unsupported-output.docx', {DOC:E.tostring(joined)})
    assert losses(source2, output)


def test_retained_utc_allows_word_minute_rounding_but_changed_utc_does_not(base_docx, tmp_path):
    source, root = pair(base_docx, tmp_path)
    node = root.find('.//w:del', NS)
    node.set(UTC, node.get(W+'date'))
    node.set(W+'date', '2026-09-13T11:24:00Z')
    output = repack(source, tmp_path/'rounded.docx', {DOC:E.tostring(root)})
    assert not losses(source, output)
    node.set(UTC, '2026-09-13T11:24:17Z')
    output = repack(source, tmp_path/'changed-time.docx', {DOC:E.tostring(root)})
    assert losses(source, output)


def test_equal_wording_from_different_authors_cannot_be_joined(base_docx, tmp_path):
    source, root = pair(base_docx, tmp_path)
    from zipfile import ZipFile
    with ZipFile(source) as z:
        before = E.fromstring(z.read(DOC))
    list(before.iter(W+'del'))[1].set(W+'author', 'Other')
    source2 = repack(source, tmp_path/'authors.docx', {DOC:E.tostring(before)})
    output = repack(source, tmp_path/'joined.docx', {DOC:E.tostring(root)})
    assert losses(source2, output)


def test_other_change_in_revision_paragraph_keeps_conservative_count_warning(base_docx, tmp_path):
    source, root = pair(base_docx, tmp_path)
    root.find('w:body/w:p/w:r/w:t', NS).text = 'Changed context: '
    output = repack(source, tmp_path/'changed-context.docx', {DOC:E.tostring(root)})
    assert losses(source, output)


def test_current_checker_is_rejected_by_frozen_word_replayer():
    from research import inspect_word_revision_ids as archived
    with pytest.raises(ValueError, match='Checker drift'):
        archived.evaluate()


def test_corrupt_archived_checker_is_never_executed(tmp_path, monkeypatch):
    from research import replay_frozen_docx as replay
    base = tmp_path/'archive'
    base.mkdir()
    (base/'baseline.json').write_bytes((replay.BASE/'baseline.json').read_bytes())
    (base/'baseline-checker.zip').write_bytes((replay.BASE/'baseline-checker.zip').read_bytes() + b'tamper')
    monkeypatch.setattr(replay, 'BASE', base)
    with pytest.raises(ValueError, match='archive drift'):
        replay.prepare(tmp_path/'workspace')
    assert not (tmp_path/'workspace').exists()
