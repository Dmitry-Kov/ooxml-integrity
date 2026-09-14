"""Resolve the main story's comments part through its typed relationship."""
from __future__ import annotations

import posixpath
from urllib.parse import unquote, urlsplit

from .xmlutil import fromstring as parse_xml

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
REL = '{http://schemas.openxmlformats.org/package/2006/relationships}'
COMMENTS_TYPE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments'
ASCII_LOWER = str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')


def comment_part(parts: dict[str, bytes], *, names: set[str] | None = None) -> str | None:
    """Return an internal target, None when absent, or fail on ambiguity/damage.

    Never substitute an unlinked conventional filename for the related part.
    `names` permits fidelity to resolve metadata before loading the target.
    Archive validation already rejects equivalent duplicate member names.
    """
    blob = parts.get('word/_rels/document.xml.rels')
    if blob is None:
        return None
    root = parse_xml(blob)
    if root.tag != REL + 'Relationships':
        raise ValueError('document relationships have an invalid root')
    relationships = [r for r in root if r.tag == REL + 'Relationship'
                     and r.get('Type') == COMMENTS_TYPE]
    if not relationships:
        return None
    if len(relationships) != 1:
        raise ValueError('multiple main-document comments relationships')
    rel = relationships[0]
    rid = rel.get('Id')
    if not rid or sum(r.get('Id') == rid for r in root) != 1:
        raise ValueError('comments relationship has a missing or duplicate Id')
    if rel.get('TargetMode', 'Internal') != 'Internal':
        raise ValueError('comments relationship must be internal')
    target = rel.get('Target', '')
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path or parsed.query or parsed.fragment:
        raise ValueError(f'invalid comments relationship target: {target!r}')
    resolved = posixpath.normpath(
        parsed.path.lstrip('/') if parsed.path.startswith('/')
        else posixpath.join('word', parsed.path))
    candidates = (resolved, unquote(resolved, errors='strict'))
    if any(p in ('', '.', '..') or p.startswith('../') for p in candidates):
        raise ValueError(f'unsafe comments relationship target: {target!r}')
    names = set(parts) if names is None else names
    equivalents = {name.translate(ASCII_LOWER): name for name in names}
    for candidate in candidates:
        if candidate in names:
            return candidate
        matched = equivalents.get(candidate.translate(ASCII_LOWER))
        if matched is not None:
            return matched
    raise ValueError(f'comments relationship target is missing: {target!r}')


def comment_tree(parts: dict[str, bytes], part: str):
    root = parse_xml(parts[part])
    if root.tag != W + 'comments':
        raise ValueError(f'{part} is related as comments but has root {root.tag!r}')
    return root
