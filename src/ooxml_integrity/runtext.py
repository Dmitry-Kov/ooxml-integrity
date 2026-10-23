"""Run content a reader sees as text, read the same way by every text rule.

A Word run holds its text in ``w:t`` (``w:delText`` once deleted) and in empty
elements that each stand for one character (ECMA-376 Part 1, 17.3.3). The
rules that compare text read both through `shown`: FID014's paragraphs,
FID013's replacements, and the header, footer, comment and note bodies of
FID004 to FID007 and FID010. A character one of them sees, all of them see.

- ``w:tab`` and ``w:ptab`` (an absolute position tab) read as a tab, ``w:br``
  (a line, column or page break) and ``w:cr`` as a line break: whitespace,
  which separates words and which the rules normalise to one space. A
  ``w:tab`` inside ``w:tabs`` is a tab stop of the paragraph, not a character.
- ``w:noBreakHyphen`` reads as "-": the standard makes it the equivalent of
  U+002D, shown with the same glyph, only not a place to break the line.
- ``w:softHyphen`` reads as nothing: it has no width unless the line breaks at
  it, which depends on the layout, not on the text.
- ``w:sym`` reads as the character its ``w:char`` gives in hexadecimal. In a
  symbol font that is a private-use code (``F0FC``, a check mark in
  Wingdings), so a symbol is not read as ordinary text and replacing it is a
  change; a change of its ``w:font`` alone is not. Without a valid code it
  reads as nothing.

Field instructions (``w:instrText``) are not shown and are not read; the
result a field shows is in ordinary runs. Which of ``w:t`` and ``w:delText``
counts, whether content inside a tracked insertion or deletion does, and what
stands between two paragraphs is each reader's view, not this module's: the
story, comment and note texts read a paragraph boundary as a space, FID014
compares paragraphs one by one.
"""
from __future__ import annotations

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TEXT = W + "t"
DELETED_TEXT = W + "delText"
SYMBOL = W + "sym"
#: Empty run elements that stand for one character, and what they read as.
CHARACTERS = {
    W + "tab": "\t",
    W + "ptab": "\t",
    W + "br": "\n",
    W + "cr": "\n",
    W + "noBreakHyphen": "-",
    W + "softHyphen": "",
}
#: Every element `shown` reads, for ``iter(*TAGS)``.
TAGS = (TEXT, DELETED_TEXT, SYMBOL, *CHARACTERS)


def _symbol(node) -> str:
    value = node.get(W + "char") or ""
    try:
        code = int(value, 16)
    except ValueError:
        return ""
    if not 0 < code <= 0x10FFFF or 0xD800 <= code <= 0xDFFF:
        return ""
    return chr(code)


def shown(node) -> str | None:
    """The text one element of a run reads as; None for anything else.

    ``w:t`` and ``w:delText`` read their own text, the character elements
    what the table above gives, which may be "" (a soft hyphen).
    """
    tag = node.tag
    if tag in (TEXT, DELETED_TEXT):
        return node.text or ""
    if tag == SYMBOL:
        return _symbol(node)
    character = CHARACTERS.get(tag)
    if character is None:
        return None
    if tag == W + "tab":
        parent = node.getparent()
        if parent is not None and parent.tag == W + "tabs":
            return None
    return character


def is_character(node) -> bool:
    """An element that stands for a character, not one that holds text."""
    return node.tag == SYMBOL or node.tag in CHARACTERS
