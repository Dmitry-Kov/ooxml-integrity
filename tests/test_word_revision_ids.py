"""Focused diagnostics; mutations here are not Word/editor observations."""
import json

from lxml import etree as E
import pytest

from research import inspect_word_revision_ids as w
from research import revision_evidence as r


def parts(name='adeu-shared-id'):
    return r.read(w.BASE / 'inputs' / (name + '.docx'))


def test_unique_control_changes_only_second_deletion_id():
    shared, unique = parts(), parts('unique-id-control')
    assert shared.keys() == unique.keys()
    assert all(shared[p] == unique[p] for p in shared if p != r.MAIN)
    root = E.fromstring(shared[r.MAIN])
    matches = root.findall('.//w:del[@w:id="104"]', r.NS)
    assert len(matches) == 2
    matches[1].set(r.W + 'id', '106')
    assert E.tostring(root, method='c14n') == E.tostring(E.fromstring(unique[r.MAIN]), method='c14n')


def test_coalescing_formatted_deletions_preserves_ledger_but_changes_nodes():
    before = parts()
    root = E.fromstring(before[r.MAIN])
    left, right = root.findall('.//w:del[@w:id="104"]', r.NS)
    for child in list(right):
        left.append(child)
    right.getparent().remove(right)
    after = {**before, r.MAIN: r.xml(root)}
    assert w.review_characters(before) == w.review_characters(after)
    assert len(w.revision_nodes(after)) == len(w.revision_nodes(before)) - 1


@pytest.mark.parametrize('defect', ['text', 'format', 'author', 'date', 'paragraph'])
def test_review_ledger_detects_protected_change(defect):
    before = parts()
    root = E.fromstring(before[r.MAIN])
    deletion = root.find('.//w:del[@w:id="104"]', r.NS)
    if defect == 'text':
        deletion.find('.//w:delText', r.NS).text = 'EDT'
    elif defect == 'format':
        prop = deletion.find('.//w:b', r.NS)
        prop.getparent().remove(prop)
    elif defect in ('author', 'date'):
        deletion.set(r.W + defect, 'Different' if defect == 'author' else '2025-01-01T00:00:00Z')
        if defect == 'date':
            deletion.set(w.UTC_ATTR, '2025-01-01T00:00:00Z')
    else:
        root.find('w:body/w:p', r.NS).append(deletion)
    assert w.review_characters(before) != w.review_characters({**before, r.MAIN: r.xml(root)})


def test_dateutc_retains_exact_time_but_raw_date_change_is_visible():
    before = parts()
    root = E.fromstring(before[r.MAIN])
    for node in root.iter(r.W + 'del'):
        node.set(w.UTC_ATTR, node.get(r.W + 'date'))
        node.set(r.W + 'date', '2026-09-13T11:24:00Z')
    after = {**before, r.MAIN: r.xml(root)}
    assert w.review_characters(before) == w.review_characters(after)
    assert w.revision_nodes(before) != w.revision_nodes(after)


@pytest.mark.parametrize('kind', ['commentRangeStart', 'footnoteReference'])
def test_anchor_or_note_relocation_changes_diagnostic(kind):
    before = parts()
    root = E.fromstring(before[r.MAIN])
    node = root.find('.//w:' + kind, r.NS)
    root.find('w:body/w:p', r.NS).append(node)
    assert w.anchors(before) != w.anchors({**before, r.MAIN: r.xml(root)})


@pytest.mark.frozen_checker
def test_saved_word_evidence_and_hashes_replay():
    actual = json.loads(w.b.json_bytes(w.evaluate()))
    assert actual == json.loads((w.BASE / 'evaluation.json').read_text())
    for case in actual['cases']:
        assert case['review_characters_authors_utc_positions_direct_bold_italic_preserved']
        assert case['current_text_preserved']
        assert case['target_current_text_and_direct_bold_italic_preserved']
        assert case['anchors_and_note_references_at_same_text_positions']
        assert case['removed_parts'] == ['word/media/chart.png']
        actionable = [(f['code'], f['severity']) for f in case['checker_after'] if f['severity'] != 'info']
        assert actionable == ([] if case['id'] == 'source-control' else [('FID001', 'error')])
