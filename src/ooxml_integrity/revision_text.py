"""Bounded literal-text checks for equal-count main-part revisions.

This is deliberately a text inventory, not revision identity or edit intent.
IDs, metadata, formatting, locations and wrapper boundaries are not identities.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .finding import ERROR, Finding

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
KINDS = ('ins', 'del')
# An adversarial rewrite must not cause unbounded pattern-by-stream work.
# Exact inventory matches are linear and do not consume this fallback budget.
MAX_SCAN_WORK = 64 * 1024 * 1024


@dataclass
class RevisionText:
    counts: dict[str, int]
    payloads: dict[str, Counter | None]
    streams: dict[str, list[str]]


def inventory(document) -> RevisionText:
    counts, payloads, streams = {}, {}, {}
    for kind in KINDS:
        nodes = list(document.iter(W + kind))
        counts[kind] = len(nodes)
        texts = []
        supported = True
        for node in nodes:
            if node.getparent() is None or node.getparent().tag != W + 'p':
                supported = False
                break
            chunks = []
            for run in node:
                if run.tag != W + 'r':
                    supported = False
                    break
                for child in run:
                    if child.tag == W + 'rPr':
                        continue
                    if child.tag != W + ('t' if kind == 'ins' else 'delText') or len(child):
                        supported = False
                        break
                    chunks.append(child.text or '')
                if not supported:
                    break
            text = ''.join(chunks)
            if not supported or not text:
                supported = False
                break
            texts.append(text)
        payloads[kind] = Counter(texts) if supported else None
        streams[kind] = texts if supported else []
    return RevisionText(counts, payloads, streams)


@dataclass
class TextComparison:
    findings: list[Finding]
    source_count: int
    compared: int
    skipped: list[str]


def assess(source: RevisionText, edited: RevisionText, *,
           scan_limit: int = MAX_SCAN_WORK,
           part: str = 'word/document.xml') -> TextComparison:
    """Report text deficits only where both same-kind inventories are supported.

    Exact payload matches are cheap. For changed boundaries, count nonoverlapping
    literal occurrences in the concatenated same-kind text. This preserves
    split/coalesced runs and wrappers, but incidental wording or cross-boundary
    joins can mask a lost record. No identity/order/format preservation is claimed.
    """
    result = TextComparison([], sum(source.counts.values()), 0, [])
    remaining = scan_limit
    for kind in KINDS:
        before = source.counts[kind]
        if not before:
            continue
        if before != edited.counts[kind]:
            result.skipped.append(f'{kind}: wrapper count changed; FID001/FID002 apply')
            continue
        old, new = source.payloads[kind], edited.payloads[kind]
        if old is None or new is None:
            result.skipped.append(f'{kind}: unsupported revision content')
            continue
        stream = None
        budget_skipped = False
        for body, count in old.items():
            available = new[body]
            if available < count:
                if stream is None:
                    stream = ''.join(edited.streams[kind])
                if len(stream) > remaining:
                    budget_skipped = True
                    continue
                remaining -= len(stream)
                available = stream.count(body)
            result.compared += count
            if available >= count:
                continue
            lost = count - available
            snippet = body if len(body) <= 80 else body[:77] + '...'
            label = 'insertion' if kind == 'ins' else 'deletion'
            result.findings.append(Finding(
                'FID009', ERROR,
                f'source tracked {label} text is missing or altered despite '
                f'unchanged wrapper count ({lost} of {count} literal occurrences '
                f'not found): {snippet!r}',
                part=part,
                extra={'tag':kind, 'body':body, 'lost':lost, 'in_source':count},
            ))
        if budget_skipped:
            result.skipped.append(f'{kind}: literal-text search budget exhausted')
    return result
