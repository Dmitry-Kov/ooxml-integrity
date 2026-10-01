"""Parsed literal entity spellings are suspicious, raw valid entities are not."""
from __future__ import annotations

import pytest
import re

from conftest import read_part, repack
from ooxml_integrity import Severity, check
from ooxml_integrity.literal_entities import spellings


def findings(path):
    return [f for f in check(path) if f.code == 'TXT002']


@pytest.mark.parametrize('token', ['&amp;#8226;', '&amp;#x2013;', '&amp;#X2013;'])
def test_literal_numeric_punctuation_in_word_text_warns(base_docx, tmp_path, token):
    document = read_part(base_docx, 'word/document.xml')
    document = document.replace('</w:body>', f'<w:p><w:r><w:t>{token}</w:t></w:r></w:p></w:body>')
    output = repack(base_docx, tmp_path / 'entity.docx', {'word/document.xml': document.encode()})
    found = findings(output)
    assert len(found) == 1 and found[0].severity is Severity.WARN
    assert 'possible double escaping' in found[0].message
    assert found[0].part == 'word/document.xml'


def test_literal_numbering_level_marker_warns(base_docx, tmp_path):
    numbering = read_part(base_docx, 'word/numbering.xml')
    numbering = re.sub(r'(<w:lvlText\s+w:val=")[^"]*', r'\1&amp;#8226;', numbering, count=1)
    assert '&amp;#8226;' in numbering
    output = repack(base_docx, tmp_path / 'numbering.docx', {'word/numbering.xml': numbering.encode()})
    assert any(f.part == 'word/numbering.xml' for f in findings(output))


def test_real_entities_and_normal_punctuation_are_clean(base_docx, tmp_path):
    document = read_part(base_docx, 'word/document.xml')
    document = document.replace('</w:body>', '<w:p><w:r><w:t>• – &#8226; &#x2013;</w:t></w:r></w:p></w:body>')
    output = repack(base_docx, tmp_path / 'real.docx', {'word/document.xml': document.encode()})
    assert findings(output) == []


def test_literal_code_example_is_qualified_not_called_corruption():
    assert spellings('HTML syntax: &#8226;') == ['&#8226;']
    # Intent cannot be inferred. Rule messages acknowledge this case and the
    # normal rule configuration can suppress TXT002 for intentional examples.


@pytest.mark.parametrize('token', ['&#00000008226;', '&#x00002013;'])
def test_valid_zero_padded_entities_remain_in_scope(token):
    assert spellings(token) == [token]


def test_extreme_padding_and_significant_lengths_never_require_large_integers():
    padded = '&#' + '0' * 5000 + '8226;'
    assert spellings(padded) == [padded]
    assert spellings('&#' + '9' * 5000 + ';') == []


@pytest.mark.parametrize('text', ['&#65;', '&#32;', '&#0;', '&#xD800;', '&#x110000;',
                                 '&#99999999999999999999999999999;', '&#xZZ;', '&amp;'])
def test_invalid_non_symbol_or_non_numeric_spellings_are_out_of_scope(text):
    assert spellings(text) == []


def test_split_node_spelling_is_an_explicit_gap(base_docx, tmp_path):
    document = read_part(base_docx, 'word/document.xml')
    document = document.replace('</w:body>', '<w:p><w:r><w:t>&amp;#82</w:t></w:r>'
                                '<w:r><w:t>26;</w:t></w:r></w:p></w:body>')
    output = repack(base_docx, tmp_path / 'split.docx', {'word/document.xml': document.encode()})
    assert findings(output) == []
