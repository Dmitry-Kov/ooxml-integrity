"""Suspicious numeric spellings after XML decoding, never raw XML entities."""
from __future__ import annotations

import re
import unicodedata

from .comments import story_parts

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
_ENTITY = re.compile(r'&#(?:[0-9]+|[xX][0-9a-fA-F]+);')


def spellings(text: str) -> list[str]:
    """Only valid punctuation/symbol references: ordinary prose is the target.

    XML parser output containing these spellings is literal text, often caused
    by double escaping. Deliberate code examples remain indistinguishable;
    this heuristic is a warning, never proof of corruption or a repair rule.
    """
    out = []
    seen = set()
    for match in _ENTITY.finditer(text):
        token = match.group()
        number = token[2:-1]
        hexadecimal = number[:1].lower() == 'x'
        digits = (number[1:] if hexadecimal else number).lstrip('0') or '0'
        # Arbitrarily padded valid values remain cheap, and malformed long
        # significant values never reach Python's bounded integer conversion.
        if len(digits) > (6 if hexadecimal else 7):
            continue
        value = int(digits, 16 if hexadecimal else 10)
        if 0 <= value <= 0x10ffff and unicodedata.category(chr(value))[:1] in ('P', 'S'):
            if token not in seen:
                out.append(token)
                seen.add(token)
    return out


def surfaces(parts, trees, main):
    """Parsed Word story text nodes and conventional numbering level values.

    A spelling split across separate text nodes is outside this inventory.
    Field instructions, deleted instruction text, Strict OOXML and arbitrary
    custom XML are outside the heuristic.
    """
    for part in dict.fromkeys(story_parts(parts, main)):
        root = trees.get(part)
        if root is not None:
            for node in root.iter(W + 't', W + 'delText'):
                yield part, node, node.text or ''
    root = trees.get('word/numbering.xml')
    if root is not None:
        for node in root.iter(W + 'lvlText'):
            yield 'word/numbering.xml', node, node.get(W + 'val', '')
