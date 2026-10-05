"""Anonymizing a document or a pair so a defect can be shared.

The replacement must keep everything the checker reads (structure, ids,
lengths, which words are equal) and nothing a reader could use to recover the
text. Each test below names one of those properties.
"""
from __future__ import annotations

import io
import json
from datetime import datetime
import random
import struct
import zipfile

import pytest

from conftest import ROOT, read_part, run_cli
from ooxml_integrity import check
from ooxml_integrity.anonymize import Mapper, anonymize, leak_scan, placeholder
from ooxml_integrity.xmlutil import fromstring

BENCH = ROOT / "evidence/review-history-benchmark"
TASKS = {t["id"]: t for t in json.loads((BENCH / "tasks.json").read_text())["tasks"]}

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = (f'xmlns:w="{W_NS}" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" '
      'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"')
MAIN = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def package(path, body, *, parts=None, rels="", defaults="", overrides=""):
    """A minimal DOCX: `body` inside w:body, plus extra parts and relationships."""
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        f'<Default Extension="xml" ContentType="application/xml"/>{defaults}'
        f'<Override PartName="/word/document.xml" ContentType="{MAIN}"/>{overrides}</Types>')
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 f'<Relationship Id="rId1" Type="{REL}/officeDocument" Target="word/document.xml"/>'
                 '</Relationships>')
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document {NS}><w:body>{body}</w:body></w:document>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("word/document.xml", document)
        if rels:
            z.writestr("word/_rels/document.xml.rels",
                       '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                       '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       f'{rels}</Relationships>')
        for name, data in (parts or {}).items():
            z.writestr(name, data)
    return path


def text_of(path, part="word/document.xml"):
    root = fromstring(zipfile.ZipFile(path).read(part))
    return ["".join(t.text or "" for t in p.iter(f"{{{W_NS}}}t", f"{{{W_NS}}}delText"))
            for p in root.iter(f"{{{W_NS}}}p")]


def run(tmp_path, *paths, seed=7):
    return anonymize(list(paths), tmp_path / "out", rng=random.Random(seed))


# --- words ---------------------------------------------------------------------

def test_a_word_keeps_its_length_and_character_classes_and_nothing_else():
    mapper = Mapper(random.Random(1))
    text = "Net 30 days, ACME-Corp. owes €1,250 (see §4.2)"
    out = mapper.text(text)
    assert out != text and len(out) == len(text)
    for a, b in zip(text, out):
        if a.isdigit():
            assert b.isdigit()
        elif a.isupper():
            assert b.isupper()
        elif a.isalpha():
            assert b.islower()
        else:
            assert a == b  # spaces, punctuation and symbols stay
    assert mapper.text("ACME") == mapper.text("ACME") != mapper.text("Acme")
    assert len({mapper.text(w) for w in ("in", "on", "an", "at", "it", "is")}) == 6


def test_literal_numeric_character_references_survive():
    # TXT002 looks for them; replacing their digits would name another character
    mapper = Mapper(random.Random(1))
    assert mapper.text("bullet &#8226; and &#x2013; dash").count("&#8226;") == 1
    assert "&#x2013;" in mapper.text("&#x2013;")


def test_a_word_split_across_runs_and_a_comment_anchor_is_one_word(tmp_path):
    split = ('<w:p><w:r><w:t>con</w:t></w:r><w:commentRangeStart w:id="0"/>'
             '<w:r><w:rPr><w:b/></w:rPr><w:t>tract</w:t></w:r></w:p>')
    whole = '<w:p><w:r><w:t>contract</w:t></w:r></w:p>'
    tab = '<w:p><w:r><w:t>con</w:t><w:tab/><w:t>tract</w:t></w:r></w:p>'
    report = run(tmp_path, package(tmp_path / "a.docx", split + whole + tab))
    first, second, third = text_of(report.outputs[0])
    assert first == second  # the anchor and the run break do not split the word
    assert third != second  # a tab is a visible boundary


# --- pairs: the checker's findings come back ---------------------------------------

def pair(adapter, task):
    return ROOT / TASKS[task]["source_path"], BENCH / f"captures/{adapter}/{task}.docx"


@pytest.mark.parametrize("adapter, task", [
    ("reference-1", "K7h-S1-tracked"),    # tracked replacement of a whole header word
    ("claude-code-1", "K7n-S2-tracked"),  # tracked note edit next to a pending revision
    ("docx-cli-5", "K4-S2-tracked"),      # text grown inside another author's insertion
    ("docxengine-1", "K5-S1-comment"),    # a comments part no XML parser accepts
    ("python-docx-setter-1", "K2-S1-plain"),  # lost comment anchor
])
def test_a_pair_reproduces_every_finding(tmp_path, adapter, task):
    report = run(tmp_path, *pair(adapter, task))
    assert report.reproduced, report.differences()
    assert report.leaks == []


def test_a_tracked_edit_inside_a_word_reads_as_the_source_once_rejected(tmp_path):
    # the deletion and the insertion sit inside one word; read together they
    # would make a word the source never had, and FID005/FID007 would fire
    source = package(tmp_path / "s.docx", '<w:p><w:r><w:t>Services</w:t></w:r></w:p>')
    edited = package(tmp_path / "e.docx",
                     '<w:p><w:r><w:t>Servic</w:t></w:r>'
                     '<w:del w:id="1" w:author="Ed" w:date="2026-10-01T00:00:00Z">'
                     '<w:r><w:delText>es</w:delText></w:r></w:del>'
                     '<w:ins w:id="2" w:author="Ed" w:date="2026-10-01T00:00:00Z">'
                     '<w:r><w:t>ing</w:t></w:r></w:ins></w:p>')
    report = run(tmp_path, source, edited)
    (anonymous_source,) = text_of(report.outputs[0])
    root = fromstring(zipfile.ZipFile(report.outputs[1]).read("word/document.xml"))
    kept = "".join(t.text for t in root.iter(f"{{{W_NS}}}t", f"{{{W_NS}}}delText")
                   if t.getparent().getparent().tag != f"{{{W_NS}}}ins")
    assert kept == anonymous_source


def test_a_malformed_part_stays_malformed_the_same_way(tmp_path):
    source, edited = pair("docxengine-1", "K5-S1-comment")
    report = run(tmp_path, source, edited)
    assert report.files[1].lexical == ["word/comments.xml"]
    original = zipfile.ZipFile(edited).read("word/comments.xml")
    result = zipfile.ZipFile(report.outputs[1]).read("word/comments.xml")
    with pytest.raises(Exception) as before:
        fromstring(original)
    with pytest.raises(Exception) as after:
        fromstring(result)
    assert str(before.value).split(",")[0] == str(after.value).split(",")[0]
    assert {f.code for f in check(report.outputs[1])} == {f.code for f in check(edited)}


# --- people, time and properties ---------------------------------------------------

def test_authors_initials_dates_and_properties(tmp_path):
    body = ('<w:p><w:ins w:id="1" w:author="Jane Roe" w:date="2026-09-29T14:25:00Z">'
            '<w:r><w:t>new</w:t></w:r></w:ins>'
            '<w:del w:id="2" w:author="John Doe" w:date="2026-09-30T08:00:00Z">'
            '<w:r><w:delText>old</w:delText></w:r></w:del></w:p>')
    comments = (f'<w:comments {NS}><w:comment w:id="0" w:author="John Doe" w:initials="JD" '
                'w:date="2026-09-30T09:00:00Z"><w:p><w:r><w:t>Check</w:t></w:r></w:p>'
                '</w:comment></w:comments>')
    people = (f'<w15:people {NS}><w15:person w15:author="Jane Roe"><w15:presenceInfo '
              'w15:providerId="AD" w15:userId="S::jane.roe@acme.example::1234"/></w15:person>'
              '</w15:people>')
    core = ('<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>Acme Supply Deal</dc:title>'
            '<dc:creator>Jane Roe</dc:creator>'
            '<dcterms:created xsi:type="dcterms:W3CDTF">2026-09-01T10:00:00Z</dcterms:created>'
            '</cp:coreProperties>')
    doc = package(tmp_path / "a.docx", body, parts={
        "word/comments.xml": comments, "word/people.xml": people, "docProps/core.xml": core})
    out = run(tmp_path, doc).outputs[0]
    document, comments_out = read_part(out, "word/document.xml"), read_part(out, "word/comments.xml")
    people_out, core_out = read_part(out, "word/people.xml"), read_part(out, "docProps/core.xml")
    joined = document + comments_out + people_out + core_out
    for secret in ("Jane", "Roe", "John", "Doe", "JD", "acme", "Acme", "Supply", "2026-09"):
        assert secret not in joined
    assert 'w:author="Author 1"' in document and 'w:author="Author 2"' in document
    assert 'w:author="Author 2" w:initials="A2"' in comments_out
    assert 'w15:author="Author 1"' in people_out and 'w15:providerId="AD"' in people_out
    revisions = fromstring(zipfile.ZipFile(out).read("word/document.xml"))
    dates = [datetime.fromisoformat(e.get(f"{{{W_NS}}}date").rstrip("Z"))
             for e in revisions.iter() if e.get(f"{{{W_NS}}}date")]
    # one offset for every date: order and gaps survive, the dates do not
    assert (dates[1] - dates[0]).total_seconds() == 17 * 3600 + 35 * 60
    assert dates[0] < datetime(2025, 9, 30)
    created = fromstring(zipfile.ZipFile(out).read("docProps/core.xml"))
    datetime.fromisoformat(created.findtext("{http://purl.org/dc/terms/}created").rstrip("Z"))


def test_external_targets_are_replaced_and_relationship_ids_kept(tmp_path):
    rels = (f'<Relationship Id="rId5" Type="{REL}/hyperlink" '
            'Target="https://deals.acme.example/contract?id=7" TargetMode="External"/>'
            f'<Relationship Id="rId6" Type="{REL}/image" Target="media/logo.png"/>')
    body = '<w:p><w:hyperlink r:id="rId5"><w:r><w:t>portal</w:t></w:r></w:hyperlink></w:p>'
    custom = ('<x:data xmlns:x="urn:acme:deal" '
              'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
              'x:client="Acme Holdings" r:id="rId5">secret</x:data>')
    doc = package(tmp_path / "a.docx", body, rels=rels, parts={
        "word/media/logo.png": b"\x89PNG not really", "customXml/item1.xml": custom},
        defaults='<Default Extension="png" ContentType="image/png"/>')
    out = run(tmp_path, doc).outputs[0]
    relationships = read_part(out, "word/_rels/document.xml.rels")
    assert 'Target="https://' in relationships and "acme" not in relationships
    assert 'Target="media/logo.png"' in relationships and 'Id="rId5"' in relationships
    item = read_part(out, "customXml/item1.xml")
    assert 'r:id="rId5"' in item and "Acme" not in item and "secret" not in item


def test_pictures_become_placeholders_embeddings_empty_fonts_kept(tmp_path):
    pillow = pytest.importorskip("PIL.Image")
    font = b"\x00\x01\x00\x00 obfuscated font bytes"
    doc = package(tmp_path / "a.docx", "<w:p/>", parts={
        "word/media/image1.png": b"x", "word/media/image2.jpeg": b"x",
        "word/media/image3.emf": b"x", "word/media/image4.wmf": b"x",
        "word/media/image5.svg": b"<svg/>", "docProps/thumbnail.jpeg": b"x",
        "word/embeddings/oleObject1.bin": b"confidential workbook",
        "word/fonts/font1.odttf": font,
    })
    report = run(tmp_path, doc)
    out = zipfile.ZipFile(report.outputs[0])
    for name in ("word/media/image1.png", "word/media/image2.jpeg", "docProps/thumbnail.jpeg"):
        pillow.open(io.BytesIO(out.read(name))).load()
    assert out.read("word/media/image3.emf")[40:44] == b" EMF"
    assert struct.unpack("<I", out.read("word/media/image4.wmf")[:4])[0] == 0x9AC6CDD7
    assert out.read("word/media/image5.svg").startswith(b"<svg")
    assert out.read("word/embeddings/oleObject1.bin") == b""
    assert out.read("word/fonts/font1.odttf") == font
    assert placeholder("x.unknown") is None


def test_charts_keep_cell_references_styles_and_an_openable_workbook(tmp_path):
    # Word refused a chart whose data range changed shape, a chart style whose
    # enumerations were replaced, and repaired one with an empty workbook
    chart = ('<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart">'
             "<c:f>'Acme Revenue'!$A$2:$C$17</c:f><c:v>Acme</c:v></c:chartSpace>")
    colors = ('<cs:colorStyle xmlns:cs="http://schemas.microsoft.com/office/drawing/2012/chartStyle" '
              'meth="cycle" id="10"/>')
    doc = package(tmp_path / "a.docx", "<w:p/>", parts={
        "word/charts/chart1.xml": chart, "word/charts/colors1.xml": colors,
        "word/embeddings/Microsoft_Excel_Worksheet.xlsx": b"PK confidential"})
    out = run(tmp_path, doc).outputs[0]
    formula = fromstring(read_part(out, "word/charts/chart1.xml").encode()).findtext(
        "{http://schemas.openxmlformats.org/drawingml/2006/chart}f")
    assert formula.endswith("'!$A$2:$C$17") and "Acme" not in formula
    assert 'meth="cycle" id="10"' in read_part(out, "word/charts/colors1.xml")
    workbook = zipfile.ZipFile(io.BytesIO(
        zipfile.ZipFile(out).read("word/embeddings/Microsoft_Excel_Worksheet.xlsx")))
    assert b"<sheetData/>" in workbook.read("xl/worksheets/sheet1.xml")


def test_strict_documents_are_refused_like_the_checker_does(tmp_path):
    strict = package(tmp_path / "a.docx", "<w:p/>")
    data = zipfile.ZipFile(strict).read("word/document.xml").replace(
        W_NS.encode(), b"http://purl.oclc.org/ooxml/wordprocessingml/main")
    other = tmp_path / "strict.docx"
    with zipfile.ZipFile(strict) as src, zipfile.ZipFile(other, "w") as dst:
        for name in src.namelist():
            dst.writestr(name, data if name == "word/document.xml" else src.read(name))
    with pytest.raises(ValueError, match="Strict"):
        run(tmp_path, other)


def test_custom_styles_are_renamed_everywhere_and_built_in_ones_kept(tmp_path):
    styles = (f'<w:styles {NS}>'
              '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>'
              '<w:style w:type="paragraph" w:customStyle="1" w:styleId="AcmeClause">'
              '<w:name w:val="Acme Clause"/><w:basedOn w:val="Heading1"/></w:style></w:styles>')
    body = ('<w:p><w:pPr><w:pStyle w:val="AcmeClause"/></w:pPr><w:r><w:t>One</w:t></w:r></w:p>'
            '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr></w:p>'
            # undefined, so STY001 must still be reported after the rename
            '<w:p><w:pPr><w:pStyle w:val="AcmeMissing"/></w:pPr></w:p>')
    doc = package(tmp_path / "a.docx", body, parts={"word/styles.xml": styles},
                  rels=f'<Relationship Id="rId1" Type="{REL}/styles" Target="styles.xml"/>')
    report = run(tmp_path, doc)
    assert report.reproduced
    styles_out = read_part(report.outputs[0], "word/styles.xml")
    document = read_part(report.outputs[0], "word/document.xml")
    assert "Acme" not in styles_out and "AcmeClause" not in document
    assert 'w:styleId="Heading1"' in styles_out and 'w:val="heading 1"' in styles_out
    renamed = fromstring(styles_out.encode()).findall(f".//{{{W_NS}}}style")[1].get(f"{{{W_NS}}}styleId")
    assert f'w:val="{renamed}"' in document


def test_shape_names_and_their_references_change_together(tmp_path):
    body = ('<w:p><w:r><w:object><v:shape id="Acme Logo" type="#_x0000_t75"/>'
            '<o:OLEObject ShapeID="Acme Logo" r:id="rId9"/></w:object>'
            '<w:pict><v:shape id="_x0000_i1025"/></w:pict></w:r></w:p>')
    out = run(tmp_path, package(tmp_path / "a.docx", body)).outputs[0]
    root = fromstring(zipfile.ZipFile(out).read("word/document.xml"))
    shapes = [e.get("id") for e in root.iter("{urn:schemas-microsoft-com:vml}shape")]
    ole = root.find(".//{urn:schemas-microsoft-com:office:office}OLEObject")
    assert shapes[0] != "Acme Logo" and ole.get("ShapeID") == shapes[0]
    assert shapes[1] == "_x0000_i1025"  # Word's generated ids hold no content
    assert ole.get(f"{{{REL}}}id") == "rId9"


def test_mail_merge_source_is_replaced_and_its_relationship_kept(tmp_path):
    settings = (f'<w:settings {NS}><w:mailMerge><w:mainDocumentType w:val="formLetters"/>'
                '<w:connectString w:val="Provider=ACE;Data Source=C:\\Clients\\Acme.xlsx"/>'
                '<w:query w:val="SELECT * FROM `Clients$`"/><w:dataSource r:id="rId1"/>'
                '</w:mailMerge></w:settings>')
    out = run(tmp_path, package(tmp_path / "a.docx", "<w:p/>",
                                parts={"word/settings.xml": settings})).outputs[0]
    text = read_part(out, "word/settings.xml")
    assert "Acme" not in text and "Clients" not in text
    assert 'r:id="rId1"' in text and 'w:val="formLetters"' in text


# --- the report -----------------------------------------------------------------

def test_the_leak_scan_finds_copied_text_and_does_not_repeat_it(tmp_path):
    copied = package(tmp_path / "a.docx",
                     '<w:p><w:r><w:t>kept</w:t></w:r></w:p>'
                     '<w:p><w:pPr><w:jc w:val="left"/></w:pPr>'
                     '<w:r><w:t w:mystery="Acme Holdings">x</w:t></w:r></w:p>')
    leaks, structural = leak_scan([copied], {"Acme", "Holdings", "left", "kept"},
                                  {("Acme", "Holdings")})
    assert leaks == [{"file": 1, "part": "word/document.xml", "where": "t", "words": 1},
                     {"file": 1, "part": "word/document.xml", "where": "t/@mystery", "words": 1}]
    assert "Acme" not in json.dumps(leaks)


def test_the_report_holds_no_text_from_the_documents(tmp_path):
    source, edited = ROOT / "corpus/base.docx", ROOT / "runs/t4_fast_fee/agreement.docx"
    report = run(tmp_path, source, edited)
    assert report.reproduced and report.leaks == [] and report.people == 2
    shown = report.render(tmp_path / "out") + json.dumps(report.as_dict())
    for secret in ("Master Services", "Reviewer", "Counsel", "Reference Agreement",
                   "corpus-builder", "agreement.docx", "base.docx"):
        assert secret not in shown
    assert [p.name for p in report.outputs] == ["source.docx", "edited.docx"]


def test_only_word_documents_are_accepted(tmp_path):
    with pytest.raises(ValueError, match="not a WordprocessingML"):
        run(tmp_path, ROOT / "corpus/deck.pptx")


# --- command line --------------------------------------------------------------------

def test_cli_writes_a_pair_and_refuses_to_overwrite_it(tmp_path):
    out = tmp_path / "share"
    first = run_cli("anonymize", str(ROOT / "corpus/base.docx"),
                    str(ROOT / "runs/t4_fast_fee/agreement.docx"), "-o", str(out))
    assert first.returncode == 0, first.stderr
    assert "findings reproduced" in first.stdout
    assert sorted(p.name for p in out.iterdir()) == ["edited.docx", "source.docx"]
    again = run_cli("anonymize", str(ROOT / "corpus/base.docx"),
                    str(ROOT / "runs/t4_fast_fee/agreement.docx"), "-o", str(out))
    assert again.returncode == 2 and "--force" in again.stderr
    forced = run_cli("anonymize", str(ROOT / "corpus/base.docx"), "-o", str(out),
                     "--force", "--json")
    assert forced.returncode == 0
    assert json.loads(forced.stdout)["outputs"] == ["document.docx"]


def test_cli_usage_errors(tmp_path):
    three = run_cli("anonymize", *[str(ROOT / "corpus/base.docx")] * 3, "-o", str(tmp_path))
    deck = run_cli("anonymize", str(ROOT / "corpus/deck.pptx"), "-o", str(tmp_path))
    missing = run_cli("anonymize", str(tmp_path / "nope.docx"), "-o", str(tmp_path))
    assert three.returncode == deck.returncode == missing.returncode == 2
    assert "not a WordprocessingML" in deck.stderr
