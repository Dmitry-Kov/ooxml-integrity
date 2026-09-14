"""Safe XML parsing shared by the OOXML readers.

OOXML parts do not need DTDs or external entities.  Accepting either would add
an input surface that has no legitimate use in an Office package and, on older
``lxml`` releases, can allow a document to read local files while it is being
checked.  Keep the policy explicit rather than inheriting version-dependent
parser defaults.
"""
from __future__ import annotations

from collections import Counter

from lxml import etree


class UnsafeXML(ValueError):
    """XML uses a feature that OOXML does not require and we deliberately reject."""


def fromstring(data: bytes) -> etree._Element:
    """Parse one OOXML part without DTD/entity expansion or network access."""
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
        recover=False,
    )
    root = etree.fromstring(data, parser=parser)
    if root.getroottree().docinfo.doctype:
        raise UnsafeXML("DOCTYPE declarations are not allowed in OOXML parts")
    return root


def text_contexts(root, tag: str):
    """Yield matching nodes, libxml-style paths and effective xml:space.

    getpath() recounts preceding siblings for every node; many warnings in a
    long main story otherwise take quadratic time. Count sibling names once
    per parent. libxml paths distinguish lexical prefixes (even aliases), and
    use positional wildcards for elements with a default namespace.
    """
    xml_space = '{http://www.w3.org/XML/1998/namespace}space'

    def name(node):
        if node.prefix:
            return node.prefix + ':' + etree.QName(node).localname
        return '*' if node.tag.startswith('{') else node.tag

    def walk(node, path, inherited):
        space = node.get(xml_space, inherited)
        if node.tag == tag:
            yield node, path, space
        children = [(child, name(child)) for child in node if isinstance(child.tag, str)]
        totals = Counter(key for _, key in children)
        positions = Counter()
        for ordinal, (child, key) in enumerate(children, 1):
            positions[key] += 1
            count = len(children) if key == '*' else totals[key]
            index = ordinal if key == '*' else positions[key]
            segment = key + (f'[{index}]' if count > 1 else '')
            yield from walk(child, path + '/' + segment, space)

    yield from walk(root, '/' + name(root), None)
