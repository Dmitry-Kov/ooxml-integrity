"""Resolve the main story and its comments part through typed relationships."""
from __future__ import annotations

import posixpath
from urllib.parse import unquote, urlsplit

from lxml import etree

from .xmlutil import fromstring as parse_xml

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
REL = '{http://schemas.openxmlformats.org/package/2006/relationships}'
COMMENTS_TYPE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments'
ASCII_LOWER = str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')
MAIN_DOCUMENT = 'word/document.xml'
DOCUMENT = W + 'document'
# The rules only know Transitional names; a Strict document is reported, not checked.
STRICT_DOCUMENT = '{http://purl.oclc.org/ooxml/wordprocessingml/main}document'
STRICT = 'Strict Open XML (ISO/IEC 29500 Strict) is not supported'


def relationships_part(part: str) -> str:
    """The relationship part that belongs to `part`."""
    directory, _, leaf = part.rpartition('/')
    return f'{directory}/_rels/{leaf}.rels' if directory else f'_rels/{leaf}.rels'


def _existing(candidates, names: set[str]) -> str | None:
    """The member a target denotes, exactly or ASCII-case-insensitively."""
    equivalents = {name.translate(ASCII_LOWER): name for name in names}
    for candidate in candidates:
        if candidate in names:
            return candidate
        matched = equivalents.get(candidate.translate(ASCII_LOWER))
        if matched is not None:
            return matched
    return None


def _resolve(target: str, base: str) -> str | None:
    """A relationship target as a part name, or None when it leaves the package."""
    path = urlsplit(target).path
    if not path:
        return None
    resolved = posixpath.normpath(
        path.lstrip('/') if path.startswith('/') else posixpath.join(base, path))
    if resolved in ('.', '..') or resolved.startswith('../'):
        return None
    return resolved


def _relationships(parts: dict[str, bytes], name: str) -> list:
    """Relationship elements of one relationship part; unreadable ones have none."""
    blob = parts.get(name)
    if blob is None:
        return []
    try:
        root = parse_xml(blob)
    except (ValueError, etree.XMLSyntaxError):
        return []
    return root.findall(REL + 'Relationship')


def office_documents(parts: dict[str, bytes], *,
                     names: set[str] | None = None) -> list[str]:
    """Distinct parts named by internal package officeDocument relationships.

    A package is entered through this relationship, not through a part name:
    Word Online wrote docx4j's HelloWordOnline sample as /word/document22.xml.
    A missing target keeps its resolved name. Unreadable root relationships
    name nothing; the inspector reports them as XML001.
    """
    names = set(parts) if names is None else names
    found: dict[str, str] = {}
    for rel in _relationships(parts, '_rels/.rels'):
        if (not (rel.get('Type') or '').endswith('/officeDocument')
                or rel.get('TargetMode') == 'External'):
            continue
        resolved = _resolve(rel.get('Target') or '', '')
        if resolved is None:
            continue
        part = _existing((resolved, unquote(resolved)), names) or resolved
        found.setdefault(part.translate(ASCII_LOWER), part)
    return list(found.values())


def story_parts(parts: dict[str, bytes], main: str, *,
                names: set[str] | None = None) -> list[str]:
    """The main part, then the header, footer and note parts it relates.

    Comment ranges and references may be written in any of these stories, so
    a comment anchored only in a header is not orphaned. Only existing parts
    are returned, each once, in relationship order.
    """
    names = set(parts) if names is None else names
    stories = [main]
    for rel in _relationships(parts, relationships_part(main)):
        kind = (rel.get('Type') or '').rsplit('/', 1)[-1]
        if (kind not in ('header', 'footer', 'footnotes', 'endnotes')
                or rel.get('TargetMode') == 'External'):
            continue
        resolved = _resolve(rel.get('Target') or '', posixpath.dirname(main))
        part = (_existing((resolved, unquote(resolved)), names)
                if resolved is not None else None)
        if part is not None and part not in stories:
            stories.append(part)
    return stories


def main_part(parts: dict[str, bytes], *, names: set[str] | None = None) -> str:
    """The single officeDocument target, else the conventional word/document.xml.

    The fallback applies only when no single part is named (REL001 then reports
    the package), so a broken entry point still gets the other checks.
    """
    found = office_documents(parts, names=names)
    return found[0] if len(found) == 1 else MAIN_DOCUMENT


def main_document(parts: dict[str, bytes], part: str):
    root = parse_xml(parts[part])
    if root.tag == STRICT_DOCUMENT:
        raise ValueError(f'{part}: {STRICT}')
    if root.tag != DOCUMENT:
        raise ValueError(f'{part} is the main document part but has root {root.tag!r}')
    return root


def comment_part(parts: dict[str, bytes], *, names: set[str] | None = None,
                 main: str | None = None) -> str | None:
    """Return an internal target, None when absent, or fail on ambiguity/damage.

    Never substitute an unlinked conventional filename for the related part.
    `names` permits fidelity to resolve metadata before loading the target.
    Archive validation already rejects equivalent duplicate member names.
    """
    main = main_part(parts, names=names) if main is None else main
    blob = parts.get(relationships_part(main))
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
        else posixpath.join(posixpath.dirname(main), parsed.path))
    candidates = (resolved, unquote(resolved, errors='strict'))
    if any(p in ('', '.', '..') or p.startswith('../') for p in candidates):
        raise ValueError(f'unsafe comments relationship target: {target!r}')
    names = set(parts) if names is None else names
    matched = _existing(candidates, names)
    if matched is not None:
        return matched
    raise ValueError(f'comments relationship target is missing: {target!r}')


def comment_tree(parts: dict[str, bytes], part: str):
    root = parse_xml(parts[part])
    if root.tag != W + 'comments':
        raise ValueError(f'{part} is related as comments but has root {root.tag!r}')
    return root
