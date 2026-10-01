"""Conservative attribution-growth witness for pending main-story insertions.

Like the character accounting used for tracked story edits, revision context
means kind/author/effective date, not an ID or proof of who performed an edit.
Only preserved source characters followed by surplus under an old context are
reported. This is intentionally not a general revision diff.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
from typing import Optional

from .finding import WARN, Finding

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
UTC = '{http://schemas.microsoft.com/office/word/2023/wordml/word16du}dateUtc'
REVISIONS = {W + kind for kind in ('ins', 'del', 'moveFrom', 'moveTo')}
INSERTED = {W + 'ins', W + 'moveTo'}
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'
#: Zero-width markers Word writes inside insertions; they hold no text.
MARKERS = {W + tag for tag in (
    'proofErr', 'bookmarkStart', 'bookmarkEnd', 'commentRangeStart',
    'commentRangeEnd', 'permStart', 'permEnd')}
Context = tuple[str, Optional[str], Optional[str]]


def _context(node) -> Context:
    return node.tag, node.get(W + 'author'), node.get(UTC, node.get(W + 'date'))


def _plain(run, text_tag: str) -> str | None:
    if run.tag != W + 'r':
        return None
    chunks = []
    for child in run:
        if child.tag == W + 'rPr':
            if any(e.tag == W + 'rPrChange' for e in child.iter()):
                return None
            continue
        if child.tag == W + 'lastRenderedPageBreak':
            continue
        if (child.tag != text_tag or len(child)
                or set(child.attrib) - {XML_SPACE}):
            return None
        chunks.append(child.text or '')
    return ''.join(chunks)


@dataclass
class PendingInsertions:
    source_count: int
    known: set[Context]
    texts: dict[Context, str]
    counts: dict[Context, int]
    records: dict[Context, list[tuple[str | None, tuple[Context, ...]]]]
    skipped: list[str]


def inventory(document) -> PendingInsertions:
    """Nonempty direct paragraph insertions containing plain text revisions.

    All source contexts are retained to distinguish old and new wrappers when
    projecting an edited character record. Unsupported same-context wrappers
    make the whole group ineligible, rather than being silently ignored.
    """
    # An empty insertion in a property element (a paragraph mark's w:rPr, a
    # row's w:trPr) marks that mark or row as inserted and holds no text.
    nodes = [node for node in document.iter(W + 'ins')
             if len(node) or node.getparent() is None
             or not node.getparent().tag.endswith('Pr')]
    known = {_context(node) for node in document.iter(*REVISIONS)}
    counts = defaultdict(int)
    unsupported = set()
    records = defaultdict(list)

    def record(node, state, outer):
        if node.tag == W + 'r':
            deleted = any(s[0] in (W + 'del', W + 'moveFrom') for s in state)
            records[outer].append((_plain(node, W + ('delText' if deleted else 't')), state))
        elif node.tag in REVISIONS:
            for child in node:
                record(child, state + (_context(node),), outer)
        elif node.tag in MARKERS:
            return
        else:
            records[outer].append((None, state))

    for node in nodes:
        context = _context(node)
        counts[context] += 1
        parent = node.getparent()
        ancestors = any(a.tag in REVISIONS for a in node.iterancestors())
        start = len(records[context])
        if not ancestors:
            if parent is not None and parent.tag == W + 'p':
                record(node, (), context)
            else:
                records[context].append((None, (context,)))
        chunks = records[context][start:] if not ancestors else ()
        if (parent is None or parent.tag != W + 'p'
                or ancestors
                or not context[1] or not context[2]
                or any(text is None for text, _ in chunks)
                or any(not state[1] or not state[2] or state[0] not in (W + 'ins', W + 'del')
                       for _, states in chunks for state in states)
                or any(state[0] == W + 'ins' for _, states in chunks for state in states[1:])
                or not ''.join(text or '' for text, _ in chunks)):
            unsupported.add(context)
    texts = {context: ''.join(text or '' for text, _ in chunks)
             for context, chunks in records.items() if context not in unsupported}
    return PendingInsertions(
        len(nodes), known, texts, dict(counts), dict(records),
        [f'{sum(counts[c] for c in unsupported)} source insertion(s) have '
         'unsupported content or incomplete metadata'] if unsupported else [],
    )


@dataclass
class GrowthComparison:
    findings: list[Finding]
    source_count: int
    compared: int
    skipped: list[str]


def assess(source: PendingInsertions, edited: PendingInsertions, *,
           part: str = 'word/document.xml') -> GrowthComparison:
    """Reject new contexts, then find preserved text plus surplus old attribution.

    This uses linear subsequence accounting, allowing run/wrapper fragmentation
    and new tracked deletions while retaining source character order. Text loss
    or reordering is outside this witness. Equal-metadata new wrappers cannot
    be distinguished from old ones, and repeated wording can mask a change.
    """
    result = GrowthComparison([], source.source_count, 0, list(source.skipped))
    for context, old in source.texts.items():
        chunks = []
        unsupported = False
        for text, state in edited.records.get(context, ()):
            # Reject new insertions; reject new deletion wrappers, retaining
            # their source payload. This is #40's character-state projection.
            if any(s not in source.known and s[0] in INSERTED for s in state):
                continue
            projected = tuple(s for s in state if s in source.known)
            if text is None or not projected or projected[0] != context:
                unsupported = True
                break
            chunks.append((text, projected))
        new = ''.join(text for text, _ in chunks)
        if unsupported:
            result.skipped.append('edited insertion context has unsupported content')
            continue
        expected = ((char, state) for text, state in source.records[context]
                    for char in text or '')
        wanted = next(expected, None)
        surplus = []
        other_context_surplus = False
        for text, state in chunks:
            for char in text:
                if wanted == (char, state):
                    wanted = next(expected, None)
                elif state == (context,):
                    surplus.append(char)
                else:
                    other_context_surplus = True
        if wanted is not None:
            result.skipped.append('source insertion text/context was removed, altered or reordered')
            continue
        if other_context_surplus:
            result.skipped.append('surplus text under another pre-existing revision context')
            continue
        result.compared += source.counts[context]
        if not surplus:
            continue
        added = ''.join(surplus)
        snippet = new if len(new) <= 120 else new[:117] + '...'
        result.findings.append(Finding(
            'FID011', WARN,
            f'{len(added)} additional character(s) carry a source pending '
            f'insertion context by {context[1]!r} dated {context[2]!r}, without '
            f'a distinct new insertion context; projected text: {snippet!r}; check attribution '
            '(author/date metadata does not establish edit intent)',
            part=part,
            extra={'author': context[1], 'date': context[2],
                   'source_text_sha256': hashlib.sha256(old.encode('utf-8')).hexdigest(),
                   'additional_characters': len(added), 'additional_text': added},
        ))
    return result
