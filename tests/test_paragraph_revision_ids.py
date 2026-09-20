"""Synthetic mark/content pairs, not native Word captures or private pilot data."""
from copy import deepcopy
from zipfile import ZipFile

from lxml import etree as E
import pytest

from ooxml_integrity import Severity, check

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DU = "{http://schemas.microsoft.com/office/word/2023/wordml/word16du}dateUtc"


def q(name):
    return f"{{{W}}}{name}"


def pair(kind, unique=False):
    text_tag = "t" if kind == "ins" else "delText"
    attrs = 'w:author="Reviewer" w:date="2026-09-20T12:00:10Z"'
    content_id = "10" if unique else "9"
    root = E.fromstring(f'''<w:document xmlns:w="{W}"><w:body>
      <w:p><w:r><w:t>Before.</w:t></w:r></w:p>
      <w:p><w:pPr><w:rPr><w:{kind} w:id="9" {attrs}/></w:rPr></w:pPr>
        <w:{kind} w:id="{content_id}" {attrs}>
          <w:r><w:rPr><w:b/></w:rPr><w:{text_tag}>Tracked paragraph.</w:{text_tag}></w:r>
        </w:{kind}></w:p>
      <w:p><w:ins w:id="20" w:author="Neighbor" w:date="2026-09-20T12:01:00Z">
        <w:r><w:t>Independent.</w:t></w:r></w:ins></w:p>
    </w:body></w:document>''')
    p = root.find(q("body"))[1]
    return root, p[0][0][0], p[1]


def findings(tmp_path, root):
    output = tmp_path / "synthetic.docx"
    with ZipFile(output, "w") as z:
        z.writestr("[Content_Types].xml", '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
          <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
          <Default Extension="xml" ContentType="application/xml"/>
          <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
        </Types>''')
        z.writestr("_rels/.rels", '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
        </Relationships>''')
        z.writestr("word/document.xml", E.tostring(root))
    return check(output)


@pytest.mark.parametrize("kind", ["ins", "del"])
@pytest.mark.parametrize("unique", [False, True])
@pytest.mark.parametrize("date_utc", [False, True])
def test_whole_paragraph_pair_is_clean(tmp_path, kind, unique, date_utc):
    root, mark, content = pair(kind, unique)
    if date_utc:
        for e in (mark, content):
            e.set(DU, e.get(q("date")))
    assert findings(tmp_path, root) == []


@pytest.mark.parametrize("kind", ["ins", "del"])
@pytest.mark.parametrize("case", [
    "author-mismatch", "date-mismatch", "author-missing", "date-missing",
    "both-authors-missing", "both-dates-missing", "utc-mismatch", "utc-one-sided",
    "third-occurrence", "different-paragraph", "unrelated-content", "two-marks",
    "different-kind", "moves", "nested", "field", "empty", "plain-neighbor",
    "property-history", "table-paragraph", "inline-mark", "third-move",
])
def test_unverified_shared_ids_remain_errors(tmp_path, kind, case):
    root, mark, content = pair(kind)
    p = content.getparent()
    body = p.getparent()
    if case in ("author-mismatch", "date-mismatch"):
        content.set(q(case.split("-")[0]), "different")
    elif case in ("author-missing", "date-missing"):
        del content.attrib[q(case.split("-")[0])]
    elif case.startswith("both-"):
        attr = q("author" if "authors" in case else "date")
        for e in (mark, content):
            del e.attrib[attr]
    elif case in ("utc-mismatch", "utc-one-sided"):
        content.set(DU, "2026-09-20T12:00:10Z")
        if case == "utc-mismatch":
            mark.set(DU, "2026-09-20T12:00:11Z")
    elif case == "third-occurrence":
        body[0].append(deepcopy(content))
    elif case == "third-move":
        extra = deepcopy(content)
        extra.tag = q("moveFrom")
        body[0].append(extra)
    elif case == "different-paragraph":
        body[0].append(content)
    elif case == "unrelated-content":
        mark.getparent().remove(mark)
        body[0].append(deepcopy(content))
    elif case == "two-marks":
        p.remove(content)
        body[0].insert(0, deepcopy(p[0]))
    elif case == "different-kind":
        mark.tag = q("del" if kind == "ins" else "ins")
    elif case == "moves":
        mark.tag = content.tag = q("moveTo")
    elif case == "nested":
        nested = E.Element(q("del" if kind == "ins" else "ins"), {q("id"): "30"})
        nested.extend(list(content))
        content.append(nested)
    elif case == "field":
        E.SubElement(content[0], q("fldChar"), {q("fldCharType"): "begin"})
    elif case == "empty":
        content.remove(content[0])
    elif case == "plain-neighbor":
        p.append(E.fromstring(f'<w:r xmlns:w="{W}"><w:t>Untracked.</w:t></w:r>'))
    elif case == "property-history":
        E.SubElement(content[0][0], q("rPrChange"), {q("id"): "31"})
    elif case == "table-paragraph":
        table = E.SubElement(body, q("tbl"))
        E.SubElement(E.SubElement(table, q("tr")), q("tc")).append(p)
    elif case == "inline-mark":
        content[0][0].append(mark)
    collisions = [f for f in findings(tmp_path, root) if f.code == "REV001"]
    assert len(collisions) == 1
    assert collisions[0].severity is Severity.ERROR
    assert "revision id 9 used" in collisions[0].message


@pytest.mark.parametrize("ident", ["", "invalid", "-1"])
def test_pair_with_unverified_id_lexical_form_stays_reported(tmp_path, ident):
    root, mark, content = pair("ins")
    for e in (mark, content):
        e.set(q("id"), ident)
    assert "REV001" in {f.code for f in findings(tmp_path, root)}


@pytest.mark.parametrize("kind,wrong,code", [("ins", "delText", "REV003"), ("del", "t", "REV002")])
def test_pair_does_not_hide_bad_text_markup(tmp_path, kind, wrong, code):
    root, _, content = pair(kind)
    content[0][-1].tag = q(wrong)
    codes = {f.code for f in findings(tmp_path, root)}
    assert {"REV001", code} <= codes
