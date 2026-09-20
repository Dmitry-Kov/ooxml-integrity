"""
Fidelity check against the source document.

The inspector answers "is this file self-consistent?". That is not enough: a
document stripped of every style, footnote and revision is perfectly
self-consistent. A second question is needed - "what was lost relative to the
original?".
"""
from __future__ import annotations

import collections
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .archive import (
    DEFAULT_ARCHIVE_LIMITS,
    ArchiveLimits,
    package_names,
    read_package,
)
from .finding import ERROR, INFO, WARN, Finding
from .comments import comment_part, comment_tree
from .revision_text import RevisionText, inventory as revision_inventory, assess as assess_revision_text
from .xmlutil import fromstring as parse_xml

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

#: (tag, human label, severity when some are lost)
#:
#: The severity rule: losing something that makes content or an audit trail
#: INVISIBLE is an error, because nothing downstream will report it. Losing
#: something that only changes how the document looks is a warning. Losing all
#: of any construct is always an error.
TRACKED: tuple[tuple[str, str, object], ...] = (
    ("commentReference", "comment anchors", ERROR),
    ("footnoteReference", "footnote references", ERROR),
    ("ins", "tracked insertions", ERROR),
    ("del", "tracked deletions", ERROR),
    ("sdt", "content controls", ERROR),
    ("drawing", "images and charts", ERROR),
    ("tbl", "tables", ERROR),
    ("hyperlink", "hyperlinks", WARN),
    ("pStyle", "paragraph style references", WARN),
    ("rStyle", "character style references", WARN),
    ("numPr", "numbered list items", WARN),
    ("tblHeader", "table header rows", WARN),
)

#: below this fraction of the source's text length, report FID003
TEXT_LOSS_THRESHOLD = 0.95

#: Parts whose bodies are compared by content rather than by count, and the
#: element that holds one item.
#:
#: Counting is not enough, and this is the hole that counting leaves: remove
#: one comment and add another, and every count matches. The document is then
#: perfectly self-consistent - nothing is orphaned, because both the anchor and
#: the comments.xml entry went together - so the inspector is silent too, and
#: the tool reports a clean file while the reviewer's note is gone. That is the
#: exact defect this project exists to catch, missed by its own fidelity check
#: until someone pointed at the arithmetic.
#:
#: Matching is on the item's normalised body text, not its id. Ids are a
#: producer's private business and get renumbered legitimately; the reviewer's
#: sentence is the thing that either survived or did not.
BODY_PARTS: tuple[tuple[str, str, str, str], ...] = (
    ("word/comments.xml", "comment", "FID004", "comment"),
    ("word/footnotes.xml", "footnote", "FID005", "footnote"),
    ("word/endnotes.xml", "endnote", "FID006", "endnote"),
)

#: Footnote and endnote parts always carry these two housekeeping items, which
#: hold no author's words and are not interesting to compare.
_BOILERPLATE = {"separator", "continuationSeparator", "continuationNotice"}

_STORY_REFERENCES = {
    W + "headerReference": "header",
    W + "footerReference": "footer",
}
_STORY_VARIANTS = {"default", "first", "even"}
_ASCII_LOWER = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz",
)

_REVISION_TAGS = {W + "ins", W + "del"}
_DATE_UTC = "{http://schemas.microsoft.com/office/word/2023/wordml/word16du}dateUtc"
_REVISION_ATTRIBUTES = {W + "id", W + "author", W + "date", _DATE_UTC}


def _run_properties(node):
    """Expanded XML names avoid prefix differences; only b/i booleans fold."""
    if node.tag == W + "rPrChange":
        raise ValueError("revision of run properties")
    attrs = dict(node.attrib)
    if node.tag in (W + "b", W + "i"):
        value = attrs.get(W + "val", "1")
        if value in ("1", "true", "on"):
            attrs[W + "val"] = "1"
        elif value in ("0", "false", "off"):
            attrs[W + "val"] = "0"
    return (node.tag, tuple(sorted(attrs.items())), node.text or "",
            tuple(_run_properties(child) for child in node))


def _revision_text_signature(document, tag: str):
    """A conservative witness for plain inline revision coalescence.

    Only paragraphs made of direct text runs and nonempty ins/del wrappers
    qualify. Their complete ordered text, revision kind/author/effective date,
    direct run properties and paragraph ordinal must agree. IDs and wrapper/run
    fragmentation may differ. Unsupported content returns None, retaining the
    existing count warning; this is not general revision identity matching.
    """
    revisions = list(document.iter(W + tag))
    if not revisions:
        return ()
    if any(node.getparent() is None or node.getparent().tag != W + "p"
           for node in revisions):
        return None
    paragraphs = {node.getparent() for node in revisions}
    result = []
    try:
        for ordinal, paragraph in enumerate(document.iter(W + "p")):
            if paragraph not in paragraphs:
                continue
            tokens = []

            def text_run(run, context):
                if run.tag != W + "r":
                    raise ValueError("non-run revision content")
                properties = run.find(W + "rPr")
                props = _run_properties(properties) if properties is not None else ()
                expected = W + ("delText" if context[0] == W + "del" else "t")
                texts = []
                for child in run:
                    if child is properties:
                        continue
                    if child.tag != expected or len(child):
                        raise ValueError("non-text run content")
                    if set(child.attrib) - {"{http://www.w3.org/XML/1998/namespace}space"}:
                        raise ValueError("unknown text attributes")
                    texts.append(child.text or "")
                text = "".join(texts)
                if not text:
                    raise ValueError("empty run")
                identity = (context, props)
                if tokens and tokens[-1][0] == identity:
                    tokens[-1][1].append(text)
                else:
                    tokens.append((identity, [text]))

            for child in paragraph:
                if child.tag == W + "pPr":
                    continue
                if child.tag == W + "r":
                    text_run(child, (None, None, None))
                elif child.tag in _REVISION_TAGS:
                    if (not len(child) or not child.get(W + "author")
                            or child.get(W + "id") is None
                            or set(child.attrib) - _REVISION_ATTRIBUTES):
                        raise ValueError("unsupported revision metadata/content")
                    context = (child.tag, child.get(W + "author"),
                               child.get(_DATE_UTC, child.get(W + "date")))
                    for run in child:
                        text_run(run, context)
                else:
                    raise ValueError("non-text paragraph content")
            result.append((ordinal, tuple((key, "".join(chunks)) for key, chunks in tokens)))
    except ValueError:
        return None
    return tuple(result)


def _norm(text: str) -> str:
    """Whitespace-insensitive body text: a reflowed comment is not a lost one."""
    return re.sub(r"\s+", " ", text or "").strip()


def _bodies(parts: dict[str, bytes], part: str, tag: str
            ) -> tuple[collections.Counter, dict[str, str]]:
    """Normalised body text of every item in `part`, as a multiset.

    A multiset rather than a set, so losing one of two identically worded
    comments is still a loss.
    """
    blob = parts.get(part)
    if blob is None:
        return collections.Counter(), {}
    root = parse_xml(blob)
    out: collections.Counter = collections.Counter()
    authors: dict[str, str] = {}
    for item in root.iter(W + tag):
        if item.get(W + "type") in _BOILERPLATE:
            continue
        body = _norm("".join(t.text or "" for t in item.iter(W + "t")))
        if body:
            out[body] += 1
            authors.setdefault(body, item.get(W + "author") or "")
    return out, authors


@dataclass
class NoteRevisions:
    notes: collections.Counter
    revised: collections.Counter
    empty_records: int


def note_revision_inventory(parts: dict[str, bytes]) -> NoteRevisions:
    """Note/kind presence grouped by text, never by note or revision IDs.

    Include deleted words in the key so unwrapping a deletion can be compared
    with the same words in ordinary runs. This is not rendered text or identity.
    One note contributes at most once per kind, regardless of fragment count.
    """
    result = NoteRevisions(collections.Counter(), collections.Counter(), 0)
    for part, kind in (('word/footnotes.xml','footnote'), ('word/endnotes.xml','endnote')):
        if part not in parts:
            continue
        root = parse_xml(parts[part])
        if root.tag != W + kind + 's':
            raise ValueError(f'{part} has unexpected note-part root {root.tag!r}')
        for note in root.findall(W + kind):
            if note.get(W + 'type') in _BOILERPLATE:
                continue
            chunks, kinds = [], set()
            for node in note.iter():
                if node.tag in (W + 't', W + 'delText'):
                    chunks.append(node.text or '')
                elif node.tag in _REVISION_TAGS:
                    kinds.add(node.tag[len(W):])
            body = _norm(''.join(chunks))
            if not body:
                result.empty_records += len(kinds)
                continue
            result.notes[(part, body)] += 1
            for tag in sorted(kinds):
                result.revised[(part, body, tag)] += 1
    return result


@dataclass
class NoteRevisionComparison:
    findings: list[Finding]
    source_count: int
    compared: int
    skipped: list[str]


def assess_note_revisions(source: NoteRevisions, edited: NoteRevisions) -> NoteRevisionComparison:
    """Detect missing ins/del presence only in equally populated text groups.

    A surviving same-kind revision can mask partial removal within a note, and
    identical note text can mask reassignment across notes. Coalescence inside
    a note preserves presence and therefore cannot alone trigger this rule.
    """
    result = NoteRevisionComparison([], sum(source.revised.values()) + source.empty_records, 0, [])
    if source.empty_records:
        result.skipped.append(f'{source.empty_records} source note/kind record(s) have empty text')
    unmatched = collections.Counter()
    for (part, body, tag), count in source.revised.items():
        if source.notes[(part, body)] != edited.notes[(part, body)]:
            unmatched[part] += count
            continue
        result.compared += count
        lost = count - edited.revised[(part, body, tag)]
        if lost <= 0:
            continue
        label = 'insertion' if tag == 'ins' else 'deletion'
        snippet = body if len(body) <= 80 else body[:77] + '...'
        result.findings.append(Finding(
            'FID010', ERROR,
            f'tracked {label} presence lost in {lost} of {count} source note(s) '
            f'with matching normalized text and note multiplicity: {snippet!r}',
            part=part, extra={'tag':tag, 'body':body, 'lost':lost, 'in_source':count},
        ))
    result.skipped.extend(f'{part}: {count} source note/kind record(s) have changed '
                          'text or note multiplicity' for part, count in unmatched.items())
    return result


@dataclass
class _StoryFacts:
    texts: collections.Counter
    constructs: collections.Counter
    parts: dict[tuple[str, str, str], str]


def _relationship_part(target: str, names: set[str],
                       names_by_equivalent: dict[str, str]) -> str:
    """Resolve a document relationship target to an existing package part."""
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path:
        raise ValueError(f"invalid header/footer relationship target: {target!r}")
    if parsed.path.startswith("/"):
        resolved = parsed.path.lstrip("/")
    else:
        resolved = posixpath.join("word", parsed.path)
    resolved = posixpath.normpath(resolved).lstrip("/")
    if resolved in ("", ".", "..") or resolved.startswith("../"):
        raise ValueError(f"unsafe header/footer relationship target: {target!r}")
    decoded = unquote(resolved, errors="strict")
    for candidate in (resolved, decoded):
        if candidate in names:
            return candidate
    for candidate in (resolved, decoded):
        equivalent = names_by_equivalent.get(candidate.translate(_ASCII_LOWER))
        if equivalent is not None:
            return equivalent
    raise ValueError(f"header/footer relationship target is missing: {target!r}")


def _effective_story_references(
        parts: dict[str, bytes], document, *, names: set[str] | None = None,
        ) -> list[tuple[str, str, str]]:
    """Return effective (kind, variant, part) once for every section slot.

    An omitted reference inherits the corresponding first/even/default story
    from the preceding section. Counting effective slots rather than unique
    parts makes a shared part and several identical split parts equivalent.
    """
    sections = [
        section for section in document.iter(W + "sectPr")
        if not any(
            ancestor.tag == W + "sectPrChange"
            for ancestor in section.iterancestors()
        )
    ]
    direct = [
        child for section in sections for child in section
        if child.tag in _STORY_REFERENCES
    ]
    if not direct:
        return []

    rel_blob = parts.get("word/_rels/document.xml.rels")
    if rel_blob is None:
        raise ValueError(
            "document has header/footer references but no document relationships"
        )
    rel_root = parse_xml(rel_blob)
    relationships = {
        rel.get("Id"): rel
        for rel in rel_root.iter(REL + "Relationship")
    }
    names = names if names is not None else set(parts)
    names_by_equivalent = {
        name.translate(_ASCII_LOWER): name for name in names
    }
    current: dict[tuple[str, str], str] = {}
    effective: list[tuple[str, str, str]] = []
    for section in sections:
        for ref in section:
            kind = _STORY_REFERENCES.get(ref.tag)
            if kind is None:
                continue
            variant = ref.get(W + "type") or "default"
            if variant not in _STORY_VARIANTS:
                raise ValueError(
                    f"unsupported {kind} reference type: {variant!r}"
                )
            rid = ref.get(R + "id")
            if not rid:
                raise ValueError(f"{variant} {kind} reference has no r:id")
            rel = relationships.get(rid)
            if rel is None:
                raise ValueError(
                    f"{variant} {kind} reference {rid!r} has no relationship"
                )
            rel_type = rel.get("Type") or ""
            if not rel_type.endswith("/" + kind):
                raise ValueError(
                    f"{variant} {kind} reference {rid!r} resolves as {rel_type!r}"
                )
            if (rel.get("TargetMode") or "").lower() == "external":
                raise ValueError(
                    f"{variant} {kind} reference {rid!r} is external"
                )
            target = rel.get("Target") or ""
            current[(kind, variant)] = _relationship_part(
                target, names, names_by_equivalent,
            )
        effective.extend(
            (kind, variant, part)
            for (kind, variant), part in sorted(current.items())
        )
    return effective


def _story_text(root) -> str:
    """Normalised story text, preserving run joins and paragraph boundaries."""
    paragraphs: list[str] = []
    for paragraph in root.iter(W + "p"):
        tokens: list[str] = []
        for node in paragraph.iter():
            if node.tag == W + "t":
                tokens.append(node.text or "")
            elif node.tag in (W + "tab", W + "br", W + "cr"):
                tokens.append(" ")
        paragraphs.append("".join(tokens))
    return _norm("\n".join(paragraphs))


def _story_facts(parts: dict[str, bytes], document, *,
                 references: list[tuple[str, str, str]] | None = None,
                 ) -> _StoryFacts:
    texts: collections.Counter = collections.Counter()
    constructs: collections.Counter = collections.Counter()
    locations: dict[tuple[str, str, str], str] = {}
    trees: dict[str, object] = {}
    references = (
        references if references is not None
        else _effective_story_references(parts, document)
    )
    for kind, variant, part in references:
        if part not in trees:
            root = parse_xml(parts[part])
            if root.tag != W + ("hdr" if kind == "header" else "ftr"):
                raise ValueError(
                    f"{part} is related as a {kind} but has root {root.tag!r}"
                )
            trees[part] = root
        root = trees[part]
        body = _story_text(root)
        identity = (kind, variant, body)
        texts[identity] += 1
        locations.setdefault(identity, part)
        for tag, _, _ in TRACKED:
            constructs[(kind, variant, tag)] += len(list(root.iter(W + tag)))
    return _StoryFacts(texts, constructs, locations)


def story_reference_count(parts: dict[str, bytes]) -> int:
    """Number of effective first/even/default header/footer section slots."""
    document = parse_xml(parts["word/document.xml"])
    return len(_effective_story_references(parts, document))


@dataclass
class _Snapshot:
    counts: dict[str, int]
    bodies: dict[str, collections.Counter]
    authors: dict[tuple[str, str], str]
    text_length: int
    stories: _StoryFacts
    revision_text: dict[str, tuple | None]
    body_locations: dict[str, str]
    inline_revision_text: RevisionText
    note_revisions: NoteRevisions


def _snapshot(path: str | Path, limits: ArchiveLimits) -> _Snapshot:
    """Read one bounded package, retain only the fidelity facts, then release it."""
    # Header/footer part names are relationship targets and cannot be known
    # before document.xml.rels is parsed. Inspect metadata first, then read only
    # the main, note-body, relationship and referenced story parts. Large media
    # inside an otherwise valid package never needs to enter fidelity memory.
    names = set(package_names(path, limits))
    wanted = {
        "word/document.xml",
        "word/_rels/document.xml.rels",
        *(part for part, _, _, _ in BODY_PARTS),
    }
    parts = read_package(path, limits, members=wanted)
    doc = parse_xml(parts["word/document.xml"])
    comments = comment_part(parts, names=names)
    if comments is None and next(doc.iter(W + "commentReference"), None) is not None:
        raise ValueError("document has comment references but no comments relationship")
    story_references = _effective_story_references(parts, doc, names=names)
    story_parts = {part for _, _, part in story_references}
    if comments is not None:
        story_parts.add(comments)
    if story_parts:
        parts.update(read_package(path, limits, members=story_parts))
    if comments is not None:
        comment_tree(parts, comments)
    counts = {tag: len(list(doc.iter(W + tag))) for tag, _, _ in TRACKED}
    text_length = sum(len(t.text or "") for t in doc.iter(W + "t"))
    bodies: dict[str, collections.Counter] = {}
    authors: dict[tuple[str, str], str] = {}
    locations: dict[str, str] = {}
    for part, tag, _, _ in BODY_PARTS:
        actual = comments if tag == "comment" else part
        body_counts, body_authors = (
            _bodies(parts, actual, tag) if actual is not None
            else (collections.Counter(), {})
        )
        bodies[part] = body_counts
        if actual is not None:
            locations[part] = actual
        authors.update(
            ((part, body), author) for body, author in body_authors.items()
        )
    return _Snapshot(
        counts, bodies, authors, text_length,
        _story_facts(parts, doc, references=story_references),
        {tag: _revision_text_signature(doc, tag) for tag in ("ins", "del")},
        locations,
        revision_inventory(doc),
        note_revision_inventory(parts),
    )


def _story_losses(source: _Snapshot, edited: _Snapshot) -> list[Finding]:
    out: list[Finding] = []
    for (kind, variant, body), n in source.stories.texts.items():
        lost = n - edited.stories.texts.get((kind, variant, body), 0)
        if lost <= 0:
            continue
        occurrences = (
            "" if lost == 1 and n == 1 else f" ({lost} of {n} occurrences)"
        )
        if body:
            snippet = body if len(body) <= 80 else body[:77] + "..."
            content = f' Its normalised text was: "{snippet}"'
        else:
            content = (
                " It was an explicitly referenced empty story; preserving it "
                "matters because it can suppress an inherited story."
            )
        out.append(Finding(
            "FID007", ERROR,
            f"a source {variant} {kind} story is missing or changed in the "
            f"edited file{occurrences}.{content}",
            where=f"{kind}/{variant}",
            part=source.stories.parts[(kind, variant, body)],
            extra={
                "story_kind": kind,
                "variant": variant,
                "body": body,
                "lost": lost,
                "in_source": n,
            },
        ))

    labels = {tag: (label, severity) for tag, label, severity in TRACKED}
    for (kind, variant, tag), before in source.stories.constructs.items():
        if not before:
            continue
        after = edited.stories.constructs.get((kind, variant, tag), 0)
        if after >= before:
            continue
        label, severity = labels[tag]
        lost = before - after
        out.append(Finding(
            "FID008", ERROR if after == 0 else severity,
            f"{variant} {kind} {label}: {before} -> {after} "
            f'({"all lost" if after == 0 else f"{lost} lost"})',
            where=f"{kind}/{variant}",
            extra={
                "story_kind": kind,
                "variant": variant,
                "tag": tag,
                "before": before,
                "after": after,
            },
        ))
    return out


def compare(source: str | Path, edited: str | Path, *,
            limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS) -> list[Finding]:
    """What did `edited` lose relative to `source`?

    Package reads are bounded by `limits`. Raises package/XML exceptions;
    callers that may be handed invalid input should use the CLI, which converts
    a failed requested comparison into an error-level `FID000` finding.
    """
    source_snapshot = _snapshot(source, limits)
    edited_snapshot = _snapshot(edited, limits)
    before, after = source_snapshot.counts, edited_snapshot.counts
    out: list[Finding] = []

    for tag, label, sev in TRACKED:
        a, b = before[tag], after[tag]
        if not a:
            continue
        if b < a:
            # Word can join adjacent deletion/insertion wrappers on a save.
            # Suppress the count-only loss only with a positive content witness;
            # two unsupported (None) signatures must never count as equal.
            witness = source_snapshot.revision_text.get(tag)
            if witness is not None and witness == edited_snapshot.revision_text.get(tag):
                continue
            lost = a - b
            out.append(Finding(
                "FID001",
                ERROR if b == 0 else sev,
                f"{label}: {a} -> {b} "
                f'({"all lost" if b == 0 else f"{lost} lost"})',
                extra={"tag": tag, "before": a, "after": b},
            ))
        elif b > a:
            # A higher count is not itself a defect: the agent may legitimately
            # have added an item, or wrapped its edit in w:ins. Neither this
            # count nor revision-ID uniqueness establishes editing correctness.
            out.append(Finding(
                "FID002", INFO,
                f"{label}: {a} -> {b} - added during editing "
                "(count increase alone does not establish a defect)",
                extra={"tag": tag, "before": a, "after": b},
            ))

    for part, tag, code, label in BODY_PARTS:
        src_bodies = source_snapshot.bodies[part]
        out_bodies = edited_snapshot.bodies[part]
        for body, n in src_bodies.items():
            lost = n - out_bodies.get(body, 0)
            if lost <= 0:
                continue
            who = source_snapshot.authors.get((part, body), "")
            snippet = body if len(body) <= 60 else body[:57] + "..."
            times = "" if lost == 1 and n == 1 else f" ({lost} of {n})"
            out.append(Finding(
                code, ERROR,
                f"a {label} present in the source is gone from the edited "
                f"file{times} - its text is not there under any id, so nothing "
                f"downstream will report it"
                + (f". {label.capitalize()} by {who}: " if who
                   else f". {label.capitalize()}: ")
                + f'"{snippet}"',
                part=source_snapshot.body_locations.get(part, part),
                extra={"body": body, "author": who, "lost": lost,
                       "in_source": n},
            ))

    out.extend(_story_losses(source_snapshot, edited_snapshot))
    out.extend(assess_revision_text(
        source_snapshot.inline_revision_text, edited_snapshot.inline_revision_text,
    ).findings)
    out.extend(assess_note_revisions(
        source_snapshot.note_revisions, edited_snapshot.note_revisions,
    ).findings)

    ta, tb = source_snapshot.text_length, edited_snapshot.text_length
    if ta and tb < ta * TEXT_LOSS_THRESHOLD:
        out.append(Finding(
            "FID003", ERROR,
            f"text volume fell from {ta} to {tb} characters "
            f"({round(100 * (1 - tb / ta))}% of content lost)",
            extra={"before": ta, "after": tb},
        ))
    return out
