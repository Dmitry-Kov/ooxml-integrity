"""Note revision presence, independently of wrapper counts and identifiers."""
from copy import deepcopy
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from lxml import etree as E
import pytest

from conftest import repack, run_cli
from ooxml_integrity import compare
from ooxml_integrity.coverage import docx_coverage

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
BASE = Path(__file__).resolve().parents[1]/'evidence/docx-revisions'
SURFACE = 'docx.fidelity.note-revisions'


def package(base, path, notes, kind='footnote'):
    root = E.Element(W+kind+'s', nsmap={'w':W[1:-1]})
    for ident, segments in enumerate(notes, 1):
        note = E.SubElement(root, W+kind, {W+'id':str(ident)})
        p = E.SubElement(note, W+'p')
        E.SubElement(E.SubElement(p, W+'r'), W+kind+'Ref')
        for ordinal, (tag, text) in enumerate(segments):
            parent = (E.SubElement(p, W+tag, {W+'id':str(ident*100+ordinal),
                                             W+'author':'Reviewer'}) if tag else p)
            E.SubElement(E.SubElement(parent, W+'r'),
                         W+('delText' if tag == 'del' else 't')).text = text
    return repack(base, path, {'word/'+kind+'s.xml':E.tostring(root)}), root


def unwrap(node):
    parent = node.getparent()
    position = parent.index(node)
    for child in list(node):
        parent.insert(position, child)
        position += 1
        for text in child.iter(W+'delText'):
            text.tag = W+'t'
    parent.remove(node)


def findings(source, output):
    return [f for f in compare(source, output) if f.code == 'FID010']


def coverage(source, output):
    return next(i for i in docx_coverage(output, compare(source, output), source=source).items
                if i.id == SURFACE)


def test_recorded_note_wrapper_loss_is_detected():
    source, output = BASE/'sources/notes.docx', BASE/'outputs/unwrap-note-insertion.docx'
    found = findings(source, output)
    assert len(found) == 1 and found[0].severity.value == 'error'
    assert found[0].part == 'word/footnotes.xml'
    assert found[0].extra['tag'] == 'ins' and found[0].extra['lost'] == 1
    assert coverage(source, output).status.value == 'checked'


@pytest.mark.parametrize('kind', ['footnote', 'endnote'])
@pytest.mark.parametrize('tag', ['ins', 'del'])
def test_unwrap_preserves_words_but_loses_review_presence(base_docx, tmp_path, kind, tag):
    source, root = package(base_docx, tmp_path/'source.docx', [[(None,'Keep '),(tag,'word')]], kind)
    unwrap(next(root.iter(W+tag)))
    output = repack(source, tmp_path/'output.docx', {'word/'+kind+'s.xml':E.tostring(root)})
    found = findings(source, output)
    assert len(found) == 1 and found[0].extra['body'] == 'Keep word'
    assert found[0].extra['tag'] == tag and found[0].extra['lost'] == 1


@pytest.mark.parametrize('kind', ['footnote', 'endnote'])
@pytest.mark.parametrize('tag', ['ins', 'del'])
def test_note_coalescence_is_not_a_presence_loss(base_docx, tmp_path, kind, tag):
    source, root = package(base_docx, tmp_path/'source.docx', [[(tag,'one '),(tag,'two')]], kind)
    a,b = list(root.iter(W+tag))
    for run in list(b):
        a.append(run)
    b.getparent().remove(b)
    output = repack(source, tmp_path/'output.docx', {'word/'+kind+'s.xml':E.tostring(root)})
    assert findings(source, output) == []
    assert coverage(source, output).count == 1  # Note/kind, not wrapper count.


@pytest.mark.parametrize('kind', ['footnote', 'endnote'])
def test_note_order_ids_run_splits_and_whitespace_can_change(base_docx, tmp_path, kind):
    source, root = package(base_docx, tmp_path/'source.docx', [[('ins','one two')],[('del','other')]], kind)
    root[:] = list(reversed(root[:]))
    for i,note in enumerate(root, 70):
        note.set(W+'id',str(i))
        rev = next(n for n in note.iter() if n.tag in (W+'ins', W+'del'))
        rev.set(W+'id',str(i+100))
        text = rev[0][0]
        original = text.text
        text.text = original[:2]
        run = deepcopy(rev[0]); run[0].text = original[2:].replace(' ','  ')
        rev.append(run)
    output = repack(source, tmp_path/'output.docx', {'word/'+kind+'s.xml':E.tostring(root)})
    assert findings(source, output) == []
    assert coverage(source, output).count == 2


@pytest.mark.parametrize('kind', ['footnote', 'endnote'])
def test_duplicate_note_wording_counts_revision_bearing_notes(base_docx, tmp_path, kind):
    source, root = package(base_docx, tmp_path/'source.docx', [[('ins','same')],[('ins','same')]], kind)
    unwrap(next(root.iter(W+'ins')))
    output = repack(source, tmp_path/'output.docx', {'word/'+kind+'s.xml':E.tostring(root)})
    found = findings(source, output)
    assert len(found) == 1 and found[0].extra['lost'] == 1 and found[0].extra['in_source'] == 2


@pytest.mark.parametrize('kind', ['footnote', 'endnote'])
def test_partial_removal_inside_one_note_is_a_declared_gap(base_docx, tmp_path, kind):
    source, root = package(base_docx, tmp_path/'source.docx', [[('ins','one '),('ins','two')]], kind)
    unwrap(next(root.iter(W+'ins')))
    output = repack(source, tmp_path/'output.docx', {'word/'+kind+'s.xml':E.tostring(root)})
    assert findings(source, output) == []


def test_same_worded_notes_can_mask_revision_reassignment(base_docx, tmp_path):
    source, _ = package(base_docx, tmp_path/'source.docx', [[('ins','same')],[(None,'same')]])
    output, _ = package(base_docx, tmp_path/'output.docx', [[(None,'same')],[('ins','same')]])
    assert findings(source, output) == []  # Body groups do not establish note identity.


@pytest.mark.parametrize('change', ['text', 'multiplicity', 'part', 'empty'])
def test_unmatched_or_empty_note_groups_are_skipped(base_docx, tmp_path, change):
    text = '' if change == 'empty' else 'one'
    source, root = package(base_docx, tmp_path/'source.docx', [[('ins',text)]])
    if change == 'text':
        next(root.iter(W+'t')).text = 'different'
    elif change == 'multiplicity':
        root.append(deepcopy(root[0]))
        root[-1].set(W+'id','99')
    output = tmp_path/'output.docx'
    if change == 'part':
        with ZipFile(source) as src, ZipFile(output,'w',ZIP_DEFLATED) as dst:
            for name in src.namelist():
                if name != 'word/footnotes.xml':
                    dst.writestr(name,src.read(name))
    else:
        repack(source, output, {'word/footnotes.xml':E.tostring(root)})
    assert findings(source, output) == []
    item = coverage(source, output)
    assert item.status.value == 'skipped' and item.count == 0
    if change == 'text':
        assert any(f.code == 'FID005' for f in compare(source, output))


def test_mixed_note_groups_have_partial_coverage(base_docx, tmp_path):
    source, _ = package(base_docx, tmp_path/'source.docx', [[('ins','one')],[('ins','two')]])
    output, _ = package(base_docx, tmp_path/'output.docx', [[(None,'one')],[('ins','changed')]])
    assert len(findings(source, output)) == 1
    item = coverage(source, output)
    assert item.status.value == 'estimated' and item.count == 1


@pytest.mark.parametrize('kind', ['footnote','endnote'])
def test_housekeeping_notes_are_excluded(base_docx, tmp_path, kind):
    source, root = package(base_docx, tmp_path/'source.docx', [[('ins','ignore')]]*3, kind)
    for note,type_ in zip(root, ['separator','continuationSeparator','continuationNotice']):
        note.set(W+'type', type_)
    source = repack(source, tmp_path/'housekeeping.docx', {'word/'+kind+'s.xml':E.tostring(root)})
    for rev in list(root.iter(W+'ins')):
        unwrap(rev)
    output = repack(source, tmp_path/'output.docx', {'word/'+kind+'s.xml':E.tostring(root)})
    assert findings(source, output) == []
    assert coverage(source, output).status.value == 'not-present'


def test_nested_revision_presence_is_counted_once_per_kind(base_docx, tmp_path):
    source, root = package(base_docx, tmp_path/'source.docx', [[('del','word')]])
    deletion = next(root.iter(W+'del'))
    outer = E.Element(W+'ins', {W+'id':'99',W+'author':'Reviewer'})
    deletion.getparent().replace(deletion,outer); outer.append(deletion)
    source = repack(source, tmp_path/'nested.docx', {'word/footnotes.xml':E.tostring(root)})
    # Unwrap only the outer insertion; the inner deletion and its words stay.
    parent = outer.getparent(); parent.replace(outer,deletion)
    output = repack(source, tmp_path/'output.docx', {'word/footnotes.xml':E.tostring(root)})
    assert [f.extra['tag'] for f in findings(source, output)] == ['ins']
    assert coverage(source, output).count == 2


@pytest.mark.parametrize('blob', [b'<broken', b'<other/>'])
def test_unreadable_note_part_cannot_pass_requested_comparison(tmp_path, blob):
    source = BASE/'sources/notes.docx'
    output = repack(source,tmp_path/'broken.docx',{'word/footnotes.xml':blob})
    result = run_cli('check',str(output),'--against',str(source),'--no-config','--coverage','--json')
    assert result.returncode == 1
    report = json.loads(result.stdout)['files'][0]
    assert any(f['code'] == 'FID000' for f in report['findings'])
    item = next(i for i in report['coverage']['items'] if i['id'] == SURFACE)
    assert item['status'] == 'skipped'


def test_cli_sarif_and_baseline_round_trip(tmp_path):
    source, output = BASE/'sources/notes.docx', BASE/'outputs/unwrap-note-insertion.docx'
    sarif, baseline = tmp_path/'out.sarif', tmp_path/'baseline.json'
    args = ['check',str(output),'--against',str(source),'--no-config']
    result = run_cli(*args,'--json','--coverage','--sarif',str(sarif))
    assert result.returncode == 1
    assert any(f['ruleId']=='FID010' and f['level']=='error'
               for f in json.loads(sarif.read_text())['runs'][0]['results'])
    assert run_cli(*args,'--write-baseline',str(baseline)).returncode == 0
    accepted = run_cli(*args,'--baseline',str(baseline),'--json')
    assert accepted.returncode == 0
    assert any(f['code']=='FID010' for f in json.loads(accepted.stdout)['files'][0]['suppressed'])


def test_baseline_distinguishes_kind_body_part_and_loss_multiplicity():
    from ooxml_integrity.finding import Finding, ERROR
    from ooxml_integrity.policy import fingerprint
    def identity(body='word',tag='ins',part='word/footnotes.xml',lost=1):
        return fingerprint('file.docx',Finding('FID010',ERROR,'diagnostic',part=part,
                           extra={'body':body,'tag':tag,'lost':lost}))
    assert len({identity(),identity('other'),identity(tag='del'),
                identity(part='word/endnotes.xml'),identity(lost=2)}) == 5
    assert 'body-sha256=' in identity()


def test_unavailable_source_coverage_does_not_claim_absent_note_revisions(tmp_path, monkeypatch):
    from ooxml_integrity import coverage as module
    source = BASE/'sources/notes.docx'
    output = tmp_path/'copy.docx'
    output.write_bytes(source.read_bytes())
    checked = compare(source, output)
    real_read = module.read_package
    def read(path, *args, **kwargs):
        if Path(path) == source:
            # Fidelity reads selected parts; coverage loads the entire source
            # and can separately fail on an unused package member.
            raise ValueError('source package unavailable to coverage')
        return real_read(path, *args, **kwargs)
    monkeypatch.setattr(module, 'read_package', read)
    item = next(i for i in docx_coverage(output, checked, source=source).items if i.id == SURFACE)
    assert item.status.value == 'skipped' and item.count is None
    assert 'source package' in item.reason
