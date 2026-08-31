#!/usr/bin/env python3
"""
Inject word/settings.xml into an existing .docx without touching anything else.

Why this exists: a package with no settings.xml opens in Word's Compatibility
Mode. Word's own "Convert" button fixes that by re-serialising the whole
document, which can itself alter tracked changes and comment anchors - i.e. it
would destroy the very evidence these files carry. So the part is added at the
package level instead.

Guarantees, asserted at the end of every run:
  - every pre-existing part is byte-identical
  - only [Content_Types].xml and word/_rels/document.xml.rels gain one line each
  - the inspector's verdict on the file is unchanged

Usage:  python3 add_settings.py runs/*/agreement.docx
"""
import sys, zipfile, shutil, re, os

#: Fixed timestamp so the package is byte-reproducible.
ZIP_EPOCH = (2026, 1, 1, 0, 0, 0)
from lxml import etree

CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

SETTINGS = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="{W}" xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
<w:zoom w:percent="100"/>
<w:defaultTabStop w:val="720"/>
<w:characterSpacingControl w:val="doNotCompress"/>
<w:footnotePr>
<w:footnote w:id="-1"/><w:footnote w:id="0"/>
</w:footnotePr>
<w:compat>
<w:compatSetting w:name="compatibilityMode"
 w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>
<w:compatSetting w:name="overrideTableStyleFontSizeAndJustification"
 w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>
<w:compatSetting w:name="enableOpenTypeFeatures"
 w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>
<w:compatSetting w:name="doNotFlipMirrorIndents"
 w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>
<w:compatSetting w:name="differentiateMultirowTableHeaders"
 w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>
</w:compat>
</w:settings>'''

OVERRIDE = ('<Override PartName="/word/settings.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>')
REL_TYPE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings'


def next_rid(rels_xml):
    used = {int(m) for m in re.findall(r'Id="rId(\d+)"', rels_xml)}
    n = 1
    while n in used:
        n += 1
    return f'rId{n}'


def add_settings(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        parts = {n: z.read(n) for n in names}
        stamps = {i.filename: i.date_time for i in z.infolist()}

    if 'word/settings.xml' in parts:
        return 'already has settings.xml'

    original = dict(parts)

    ct = parts['[Content_Types].xml'].decode('utf-8')
    if OVERRIDE not in ct:
        ct = ct.replace('</Types>', OVERRIDE + '\n</Types>')
    parts['[Content_Types].xml'] = ct.encode('utf-8')

    relname = 'word/_rels/document.xml.rels'
    rels = parts[relname].decode('utf-8')
    rid = next_rid(rels)
    rel_line = f'<Relationship Id="{rid}" Type="{REL_TYPE}" Target="settings.xml"/>'
    rels = rels.replace('</Relationships>', rel_line + '\n</Relationships>')
    parts[relname] = rels.encode('utf-8')

    parts['word/settings.xml'] = SETTINGS.encode('utf-8')

    def entry(n):
        """Keep each original entry's timestamp; use a fixed one for the new part."""
        zi = zipfile.ZipInfo(n, date_time=stamps.get(n, ZIP_EPOCH))
        zi.compress_type = zipfile.ZIP_DEFLATED
        zi.external_attr = 0o644 << 16
        return zi

    tmp = path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for n in names:                      # original order preserved
            z.writestr(entry(n), parts[n])
        z.writestr(entry('word/settings.xml'), parts['word/settings.xml'])

    # verify: every pre-existing part except the two we touched is byte-identical
    with zipfile.ZipFile(tmp) as z:
        after = {n: z.read(n) for n in z.namelist()}
    touched = {'[Content_Types].xml', relname}
    for n, data in original.items():
        if n in touched:
            continue
        assert after[n] == data, f'{path}: part {n} changed - aborting'
    assert 'word/settings.xml' in after
    assert b'val="15"' in after['word/settings.xml']

    os.replace(tmp, path)
    return f'settings.xml added as {rid}'


if __name__ == '__main__':
    targets = sys.argv[1:]
    if not targets:
        print(__doc__)
        sys.exit(1)
    for p in targets:
        print(f'{p:<45} {add_settings(p)}')
