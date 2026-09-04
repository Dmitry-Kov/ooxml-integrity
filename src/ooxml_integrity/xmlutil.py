"""Safe XML parsing shared by the OOXML readers.

OOXML parts do not need DTDs or external entities.  Accepting either would add
an input surface that has no legitimate use in an Office package and, on older
``lxml`` releases, can allow a document to read local files while it is being
checked.  Keep the policy explicit rather than inheriting version-dependent
parser defaults.
"""
from __future__ import annotations

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
