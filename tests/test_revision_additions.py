"""FID012: the tracked changes an edit added, per story, kind and author.

A correct tracked edit in the wrong story looked the same to compare() as one
in the requested story: in the review-history benchmark, docxengine edited the
document title instead of the requested header, with tracked changes, and no
finding said where the new revisions were. FID012 says so, and an expectation
can require it.
"""
from __future__ import annotations

import pytest

from conftest import ROOT, read_part, repack
from ooxml_integrity import INFO, Expectation, compare, expect
from ooxml_integrity.policy import fingerprint

BENCH = ROOT / 'evidence/review-history-benchmark'
S2 = BENCH / 'sources/word-review.docx'
HEADER = Expectation('FID012', {'story': 'header/default', 'author': 'Benchmark Editor'},
                     reason='the header is edited with tracked changes')


def added(source, edited):
    return [(f.extra['story'], f.extra['tag'], f.extra['author'], f.extra['count'])
            for f in compare(source, edited) if f.code == 'FID012']


def test_a_tracked_header_edit_is_reported_in_the_header():
    edited = BENCH / 'captures/reference-1/K7h-S2-tracked.docx'
    assert added(S2, edited) == [('header/default', 'ins', 'Benchmark Editor', 1),
                                 ('header/default', 'del', 'Benchmark Editor', 1)]
    assert all(f.severity is INFO for f in compare(S2, edited) if f.code == 'FID012')


def test_the_same_edit_made_in_the_title_fails_a_header_expectation():
    wrong = BENCH / 'captures/docxengine-1/K7h-S2-tracked.docx'
    assert {story for story, *_ in added(S2, wrong)} == {'document'}
    kept, matched = expect(compare(S2, wrong), [HEADER])
    assert matched == [] and 'EXP001' in {f.code for f in kept}
    kept, matched = expect(compare(S2, BENCH / 'captures/reference-1/K7h-S2-tracked.docx'), [HEADER])
    assert len(matched) == 2 and 'EXP001' not in {f.code for f in kept}


def test_notes_are_a_story_of_their_own():
    edited = BENCH / 'captures/reference-1/K7n-S2-tracked.docx'
    assert {story for story, *_ in added(S2, edited)} == {'footnotes'}


def test_unchanged_and_resaved_files_add_nothing():
    assert added(S2, S2) == []
    assert added(S2, BENCH / 'captures/reference-1/K0-S2-save.docx') == []


DATE = 'w:date="2026-09-29T14:25:00Z"'


@pytest.mark.parametrize('replacement, expected', [
    # Splitting an existing revision into two keeps its author and date.
    ('split', []),
    # The same author with a new date is a new revision.
    ('redated', [('document', 'ins', 'Reviewer A', 1)]),
])
def test_identity_is_kind_author_and_date(tmp_path, replacement, expected):
    document = read_part(S2, 'word/document.xml')
    run = '<w:r w:rsidR="001B7773" w:rsidRPr="001B7773"><w:t>forty-five</w:t></w:r>'
    start = document.index(run)
    open_tag = document.rindex('<w:ins ', 0, start)
    wrapper = document[open_tag:document.index('</w:ins>', start) + len('</w:ins>')]
    assert DATE in wrapper and wrapper.count(run) == 1
    if replacement == 'split':
        head = wrapper.replace(run, run.replace('forty-five', 'forty-'))
        tail = wrapper.replace(run, run.replace('forty-five', 'five')).replace('w:id="', 'w:id="9')
        new = head + tail
    else:
        new = wrapper.replace(DATE, 'w:date="2026-10-04T00:00:00Z"').replace(
            'w16du:dateUtc="2026-09-29T09:25:00Z"', 'w16du:dateUtc="2026-10-04T00:00:00Z"')
    edited = repack(S2, tmp_path / f'{replacement}.docx',
                    {'word/document.xml': document.replace(wrapper, new).encode()})
    assert added(S2, edited) == expected


def test_baseline_identity_ignores_the_count_and_hides_the_author():
    from ooxml_integrity import Finding
    one = Finding('FID012', INFO, 'x', extra={'story': 'document', 'tag': 'ins',
                                              'author': 'Benchmark Editor', 'count': 1})
    two = Finding('FID012', INFO, 'y', extra={'story': 'document', 'tag': 'ins',
                                              'author': 'Benchmark Editor', 'count': 2})
    other = Finding('FID012', INFO, 'x', extra={'story': 'header/default', 'tag': 'ins',
                                                'author': 'Benchmark Editor', 'count': 1})
    assert fingerprint('a.docx', one) == fingerprint('a.docx', two) != fingerprint('a.docx', other)
    assert 'Benchmark Editor' not in fingerprint('a.docx', one)
