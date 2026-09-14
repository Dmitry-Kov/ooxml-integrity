"""Independent regression expectations from the external adeu pilot."""
import io
import json
import os
import subprocess
import sys

from lxml import etree
import pytest

from ooxml_integrity import check, compare
from ooxml_integrity.coverage import docx_coverage
from research.adeu_pilot_probe import (
    COMMENTS, DOC, REL, RELS, SPACE, W, read_parts, renamed_comments,
    text_document, whitespace_findings, write_parts,
)


@pytest.mark.parametrize('encoding', ['cp1252:strict', 'ascii:strict'])
@pytest.mark.parametrize('json_mode', [False, True])
@pytest.mark.parametrize('threshold, expected_exit', [('error', 0), ('warn', 1)])
def test_redirected_unicode_output_completes(base_docx, tmp_path, encoding,
                                            json_mode, threshold, expected_exit):
    parts = read_parts(base_docx)
    document = etree.fromstring(parts[DOC])
    p = etree.SubElement(document.find(W+'body'), W+'p')
    text = ' \u2012 Пример \U0001f4dd '
    etree.SubElement(etree.SubElement(p, W+'r'), W+'t').text = text
    parts[DOC] = etree.tostring(document)
    path = write_parts(tmp_path/'пример.docx', parts)
    command = [sys.executable, '-m', 'ooxml_integrity', 'check', str(path),
               '--no-config', '--fail-on', threshold, '--coverage']
    if json_mode:
        command.append('--json')
    result = subprocess.run(command, capture_output=True, env=dict(
        os.environ, PYTHONIOENCODING=encoding, PYTHONUTF8='0'))
    assert result.returncode == expected_exit, result.stderr
    assert result.stderr == b''
    output = result.stdout.decode(encoding.split(':')[0])
    if json_mode:
        report = json.loads(output)
        assert report['files'][0]['path'] == str(path)
        assert any(text in f['message'] for f in report['files'][0]['findings'])
    else:
        assert 'TXT001' in output
        assert '\\u2012' in output
        assert '\\u041f' in output


def test_doctor_json_preserves_unicode_under_ascii(monkeypatch):
    from ooxml_integrity import cli
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding='ascii', errors='strict')
    monkeypatch.setattr(cli.sys, 'stdout', stream)
    report = {'capabilities': [], 'message': '\u2012 Пример'}
    monkeypatch.setattr(cli, 'build_doctor_report', lambda: report)
    assert cli.main(['doctor', '--json']) == 0
    stream.flush()
    assert json.loads(raw.getvalue()) == report


@pytest.mark.parametrize('name,target', [
    ('word/comments1.xml', 'comments1.xml'),
    ('word/comments1.xml', '/word/comments1.xml'),
    ('notes/review.xml', '../notes/review.xml'),
    ('word/review note.xml', 'review%20note.xml'),
    ('word/comments1.xml', 'COMMENTS1.XML'),
])
def test_comment_part_name_is_not_identity(base_docx, tmp_path, name, target):
    path = renamed_comments(base_docx, tmp_path/'named.docx', name, target=target)
    findings = check(path)
    assert findings == []
    assert compare(base_docx, path) == []
    assert compare(path, base_docx) == []
    assert compare(path, path) == []
    items = {item.id: item for item in docx_coverage(path, findings, source=base_docx).items}
    assert items['docx.comments'].status.value == 'checked'
    assert items['docx.comments'].count == 4  # Two anchors and two definitions.
    assert items['docx.fidelity.note-bodies'].status.value == 'checked'


@pytest.mark.parametrize('decoy', [False, True])
def test_changed_body_in_named_part_is_detected(base_docx, tmp_path, decoy):
    source = renamed_comments(base_docx, tmp_path/'source.docx', decoy=decoy)
    parts = read_parts(source)
    parts['word/comments1.xml'] = parts['word/comments1.xml'].replace(
        b'Confirm this figure', b'Different body')
    edited = write_parts(tmp_path/'changed.docx', parts)
    assert not [f for f in check(edited) if f.code.startswith('CMT')]
    findings = [f for f in compare(source, edited) if f.code == 'FID004']
    assert len(findings) == 1
    assert 'Confirm this figure' in findings[0].extra['body']
    assert findings[0].part == 'word/comments1.xml'


def test_missing_definition_in_named_part_is_detected(base_docx, tmp_path):
    path = renamed_comments(base_docx, tmp_path/'source.docx', decoy=True)
    parts = read_parts(path)
    cm = etree.fromstring(parts['word/comments1.xml'])
    cm.remove(cm.find(W+'comment'))
    parts['word/comments1.xml'] = etree.tostring(cm)
    edited = write_parts(tmp_path/'missing.docx', parts)
    findings = [f for f in check(edited) if f.code == 'CMT004']
    assert len(findings) == 1
    assert 'comments1.xml' in findings[0].message
    assert any(f.code == 'FID004' for f in compare(path, edited))


@pytest.mark.parametrize('defect', ['external', 'duplicate', 'missing', 'unsafe',
                                   'wrong-root', 'malformed', 'no-relationship'])
def test_unresolvable_comments_are_not_clean(base_docx, tmp_path, defect):
    parts = read_parts(base_docx)
    rels = etree.fromstring(parts[RELS])
    comment_rel = next(r for r in rels if r.get('Type', '').endswith('/comments'))
    if defect == 'external':
        comment_rel.set('TargetMode', 'External')
    elif defect == 'duplicate':
        duplicate = etree.SubElement(rels, REL+'Relationship', dict(comment_rel.attrib))
        duplicate.set('Id', 'rIdExtraComments')
    elif defect == 'missing':
        comment_rel.set('Target', 'missing.xml')
    elif defect == 'unsafe':
        comment_rel.set('Target', '../../comments.xml')
    elif defect == 'wrong-root':
        parts[COMMENTS] = b'<other/>'
    elif defect == 'malformed':
        parts[COMMENTS] = b'<broken'
    elif defect == 'no-relationship':
        rels.remove(comment_rel)
    parts[RELS] = etree.tostring(rels)
    path = write_parts(tmp_path/'bad.docx', parts)
    findings = check(path)
    assert any(f.code in ('CMT004', 'CMT006') for f in findings)
    assert not any(f.code == 'INT001' for f in findings)
    with pytest.raises((ValueError, etree.XMLSyntaxError)):
        compare(base_docx, path)
    items = {item.id: item for item in docx_coverage(path, findings).items}
    if defect != 'no-relationship':
        assert items['docx.comments'].status.value == 'skipped'


@pytest.mark.parametrize('text,inherited,local,warn', [
    (' ordinary ', None, None, True),
    ('ordinary', None, None, False),
    ('\u00a0ordinary\u00a0', None, None, False),
    ('\u2002ordinary\u2003', None, None, False),
    ('\u202fordinary\u202f', None, None, False),
    ('\tordinary\n', None, None, True),
    (' ordinary ', 'preserve', None, False),
    (' ordinary ', 'preserve', 'default', True),
    (' ordinary ', 'default', 'preserve', False),
])
def test_xml_whitespace_and_inheritance(base_docx, tmp_path, text, inherited, local, warn):
    path = text_document(base_docx, tmp_path/'space.docx', text,
                         inherited=inherited, local=local)
    findings = whitespace_findings(path)
    assert len(findings) == int(warn)
    if findings:
        assert findings[0].code == 'TXT001'
        assert findings[0].severity.value == 'warn'


def test_whitespace_locations_match_lxml(base_docx, tmp_path):
    # Multiple same-name siblings, aliases, default namespaces and comments:
    # fast path generation must retain exact existing baseline locations.
    parts = read_parts(base_docx)
    ns = W[1:-1]
    parts[DOC] = (f'<w:document xmlns:w="{ns}" xmlns:x="{ns}"><w:body>'
                  '<w:p><w:r><w:t> a </w:t><x:t> b </x:t></w:r></w:p>'
                  '<!-- sibling --><w:p><w:r><w:t> c </w:t></w:r></w:p>'
                  f'<p xmlns="{ns}"><r><t> d </t></r></p>'
                  '</w:body></w:document>').encode()
    path = write_parts(tmp_path/'paths.docx', parts)
    tree = etree.fromstring(parts[DOC])
    expected = [tree.getroottree().getpath(t) for t in tree.iter(W+'t')]
    assert [f.where for f in whitespace_findings(path)] == expected


def test_current_checker_retains_revision_corpus_results():
    # Current expectations now live beside the note follow-up; the original
    # 30-pair receipt is still tested against its archived checker.
    from research.review_revision_text import review, ROOT
    metrics = review(evidence_dir=ROOT/'evidence/docx-note-revisions')
    assert metrics['corrected_known_misses'] == ['replace-unrelated-insertion', 'unwrap-note-insertion']
    assert metrics['remaining_known_misses'] == []


@pytest.mark.parametrize('xml', [
    '<a xmlns="z"><b/><c/><!--x--><b/></a>',
    '<a><x:t xmlns:x="z"/><x:t xmlns:x="y"/><x:t xmlns:x="z"/></a>',
    '<a xmlns="z"><b xmlns=""/><b/><c/><b xmlns=""/></a>',
])
def test_fast_paths_keep_libxml_namespace_spelling(xml):
    from ooxml_integrity.xmlutil import text_contexts
    root = etree.fromstring(xml)
    for tag in {node.tag for node in root.iter() if isinstance(node.tag, str)}:
        expected = [root.getroottree().getpath(node) for node in root.iter(tag)]
        assert [path for _, path, _ in text_contexts(root, tag)] == expected
