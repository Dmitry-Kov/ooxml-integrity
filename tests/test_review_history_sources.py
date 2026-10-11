"""S2 source for the review-history benchmark: the generated base and its audit.

The reviewed package below is simulated, not a Word capture. It writes each S2
structure the way Word does, so the audit is shown to accept all of them and to
reject each one removed, before any Word output exists.
"""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile

import pytest

from conftest import ROOT, needs_zlib_bytes

from ooxml_integrity import check

sys.path.insert(0, str(ROOT))
from research import review_history_sources as s2  # noqa: E402

BASE = s2.SOURCES / s2.BASE_NAME
DATE = 'w:date="2026-09-29T10:00:00Z"'
W14 = 'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"'
W15 = 'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"'
MS = "http://schemas.microsoft.com/office/2011/relationships/"


def _rev(kind: str, rid: int, author: str, body: str) -> str:
    return f'<w:{kind} w:id="{rid}" w:author="{author}" {DATE}>{body}</w:{kind}>'


def _run(text: str, tag: str = "t") -> str:
    return f'<w:r><w:{tag} xml:space="preserve">{text}</w:{tag}></w:r>'


def _range(cid: int, runs: str) -> str:
    return (f'<w:commentRangeStart w:id="{cid}"/>{runs}<w:commentRangeEnd w:id="{cid}"/>'
            f'<w:r><w:commentReference w:id="{cid}"/></w:r>')


def _comment(cid: int, author: str, para: str, text: str) -> str:
    initials = "RA" if author.endswith("A") else "RB"
    return (f'<w:comment w:id="{cid}" w:author="{author}" {DATE} w:initials="{initials}">'
            f'<w:p w14:paraId="{para}"><w:r><w:t>{text}</w:t></w:r></w:p></w:comment>')


A, B = s2.REVIEWERS
MOVED = "Comply with the Client's information security policy."
FIRST = "Attend a monthly steering meeting with the Client."

#: part -> [(old, new)], each old string occurring exactly once in the base.
REVIEW = {
    "word/document.xml": [
        ("until the Completion Date.</w:t></w:r>",
         "until the </w:t></w:r>"
         + _range(0, '<w:commentRangeStart w:id="2"/>' + _run("Completion Date"))
         .replace('<w:r><w:commentReference w:id="0"/></w:r>',
                  '<w:r><w:commentReference w:id="0"/></w:r><w:commentRangeEnd w:id="2"/>'
                  '<w:r><w:commentReference w:id="2"/></w:r>')
         + _run(".")),
        ("<w:p><w:r><w:t>EUR 12,000</w:t></w:r></w:p>",
         "<w:p>" + _range(1, _run("EUR 12,000")) + "</w:p>"),
        ("Fees are payable within thirty days of receipt of a valid invoice.</w:t></w:r>",
         "Fees are payable within </w:t></w:r>"
         + _rev("del", 10, A, _run("thirty ", "delText"))
         + _rev("ins", 11, A, _run("forty-five "))
         + _run("days of receipt of a valid invoice.")
         + _rev("ins", 12, A, _run(" The Client may withhold ")
                + _rev("del", 13, B, _run("any ", "delText"))
                + _run("disputed amount."))),
        (s2._item(FIRST),
         s2._item(MOVED).replace(_run(MOVED).replace(' xml:space="preserve"', ""),
                                 _rev("moveTo", 14, A, _run(MOVED)))
         + s2._item(FIRST)),
        (f"<w:r><w:t>{MOVED}</w:t></w:r>", _rev("moveFrom", 15, A, _run(MOVED))),
        ("liability for fraud or gross negligence.</w:t></w:r>",
         "liability for fraud or </w:t></w:r>"
         f'<w:r><w:rPr><w:b/><w:rPrChange w:id="16" w:author="{B}" {DATE}><w:rPr/>'
         "</w:rPrChange></w:rPr><w:t>gross negligence</w:t></w:r>" + _run(".")),
        ('<w:p><w:r><w:t xml:space="preserve">Either party',
         f'<w:p><w:pPr><w:jc w:val="both"/><w:pPrChange w:id="17" w:author="{B}" {DATE}>'
         '<w:pPr/></w:pPrChange></w:pPr><w:r><w:t xml:space="preserve">Either party'),
    ],
    "word/header1.xml": [
        ("<w:r><w:t>Consulting Services Agreement - Draft 3</w:t></w:r>",
         _run("Consulting Services Agreement - Draft ")
         + _rev("del", 18, A, _run("3", "delText")) + _rev("ins", 19, A, _run("4"))),
    ],
    "word/endnotes.xml": [
        ("public register on 1 September 2026.</w:t></w:r>",
         "public register on </w:t></w:r>"
         + _rev("del", 20, B, _run("1", "delText")) + _rev("ins", 21, B, _run("15"))
         + _run(" September 2026.")),
    ],
    "word/_rels/document.xml.rels": [
        ("</Relationships>",
         f'<Relationship Id="rId9" Type="{s2.RT}comments" Target="comments.xml"/>'
         f'<Relationship Id="rId10" Type="{MS}commentsExtended" Target="commentsExtended.xml"/>'
         f'<Relationship Id="rId11" Type="{MS}people" Target="people.xml"/>'
         "</Relationships>"),
    ],
    "docProps/core.xml": [
        ("</dc:creator>", f"</dc:creator><cp:lastModifiedBy>{B}</cp:lastModifiedBy>"),
    ],
}

NEW_PARTS = {
    "word/comments.xml": s2.DECL + f"<w:comments {s2.WNS} {W14}>"
    + _comment(0, A, "1A000001", "Completion Date is not defined.")
    + _comment(1, A, "1A000002", "Check this against the approved budget.")
    + _comment(2, B, "1B000003", "Agreed. Add it to Schedule 1.") + "</w:comments>",
    "word/commentsExtended.xml": s2.DECL + f"<w15:commentsEx {W15}>"
    '<w15:commentEx w15:paraId="1A000001" w15:done="0"/>'
    '<w15:commentEx w15:paraId="1A000002" w15:done="1"/>'
    '<w15:commentEx w15:paraId="1B000003" w15:paraIdParent="1A000001" w15:done="0"/>'
    "</w15:commentsEx>",
    "word/people.xml": s2.DECL + f"<w15:people {W15}>" + "".join(
        f'<w15:person w15:author="{name}"><w15:presenceInfo w15:providerId="None" '
        f'w15:userId="{name}"/></w15:person>' for name in s2.REVIEWERS) + "</w15:people>",
}


def _reviewed(tmp_path, mutation=None):
    parts = dict(s2.PARTS)
    for name, edits in REVIEW.items():
        for old, new in edits:
            assert parts[name].count(old) == 1, (name, old)
            parts[name] = parts[name].replace(old, new)
    parts.update(NEW_PARTS)
    if mutation:
        name, old, new = mutation
        assert parts[name].count(old) == 1, (name, old)
        parts[name] = parts[name].replace(old, new)
    path = tmp_path / "reviewed.docx"
    with zipfile.ZipFile(path, "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return path


def _failed(path):
    return sorted(k for k, ok in s2.audit(path)["requirements"].items() if not ok)


@needs_zlib_bytes
def test_base_rebuilds_byte_identically(tmp_path):
    assert s2.build(tmp_path).read_bytes() == BASE.read_bytes()


def test_base_is_clean_and_has_no_review_record():
    assert list(check(BASE)) == []
    report = s2.audit(BASE)
    assert report["revisions"] == [] and report["comments"] == [] and report["people"] == []


def test_simulated_review_meets_every_requirement(tmp_path):
    assert set(s2.REQUIREMENTS) == set(s2.audit(_reviewed(tmp_path))["requirements"])
    assert _failed(_reviewed(tmp_path)) == []


MUTATIONS = {
    "authors": ("word/people.xml", 'w15:author="Reviewer B"', 'w15:author="R. Someone"'),
    "comment-thread": ("word/commentsExtended.xml", ' w15:paraIdParent="1A000001"', ""),
    "comment-resolved": ("word/commentsExtended.xml",
                         'w15:paraId="1A000002" w15:done="1"', 'w15:paraId="1A000002" w15:done="0"'),
    "replacement": ("word/document.xml", _rev("del", 10, A, _run("thirty ", "delText")), ""),
    "nested-deletion": ("word/document.xml",
                        _run(" The Client may withhold ")
                        + _rev("del", 13, B, _run("any ", "delText")),
                        _run(" The Client may withhold any ")),
    "move": ("word/document.xml", _rev("moveFrom", 15, A, _run(MOVED)),
             _rev("del", 15, A, _run(MOVED, "delText"))),
    "run-format-change": ("word/document.xml", "<w:rPr><w:b/><w:rPrChange", "<w:rPr><w:rPrChange"),
    "paragraph-format-change": ("word/document.xml", f'w:id="17" w:author="{B}"',
                                f'w:id="17" w:author="{A}"'),
    "header-revision": ("word/header1.xml", _rev("ins", 19, A, _run("4")), ""),
    "endnote-revision": ("word/endnotes.xml", f'w:id="21" w:author="{B}"', f'w:id="21" w:author="{A}"'),
}


@pytest.mark.parametrize("requirement", sorted(MUTATIONS))
def test_each_requirement_fails_without_its_structure(tmp_path, requirement):
    assert _failed(_reviewed(tmp_path, MUTATIONS[requirement])) == [requirement]


@pytest.mark.parametrize("mutation", [
    ("word/people.xml", 'w15:providerId="None" w15:userId="Reviewer A"',
     'w15:providerId="AD" w15:userId="S::reviewer@example.org::0000"'),
    ("docProps/core.xml", f"<cp:lastModifiedBy>{B}", "<cp:lastModifiedBy>R. Someone"),
    ("word/comments.xml", "Add it to Schedule 1.", "Mail reviewer@example.org."),
])
def test_personal_metadata_fails_privacy(tmp_path, mutation):
    assert _failed(_reviewed(tmp_path, mutation)) == ["privacy"]


def test_declaration_pins_the_committed_base_and_checklist():
    declared = json.loads(s2.DECLARATION.read_text())
    for key in ("base", "checklist"):
        path = ROOT / declared[key]["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == declared[key]["sha256"], key
    assert declared["requirements"] == s2.REQUIREMENTS


# --- the Word for Mac capture ------------------------------------------------

CAPTURE = json.loads((s2.SOURCES / "s2-capture.json").read_text())
REVIEW_A = s2.SOURCES / "review-a.docx"
WORD_REVIEW = s2.SOURCES / "word-review.docx"
STORIES = ("word/document.xml", "word/header1.xml", "word/footer1.xml",
           "word/footnotes.xml", "word/endnotes.xml")


def _view(path, part, view):
    """Nonempty paragraph texts with every revision rejected or accepted."""
    root = s2.etree.fromstring(zipfile.ZipFile(path).read(part), s2.PARSER)
    hidden = ({s2.W + "ins", s2.W + "moveTo"} if view == "reject"
              else {s2.W + "del", s2.W + "moveFrom"})
    texts = []
    for p in root.iter(s2.W + "p"):
        text = "".join(t.text or "" for t in p.iter(s2.W + "t", s2.W + "delText")
                       if not hidden & {a.tag for a in t.iterancestors()})
        if text.strip():
            texts.append(text)
    return texts


def test_capture_pins_the_saved_packages():
    assert CAPTURE["input"]["sha256"] == hashlib.sha256(BASE.read_bytes()).hexdigest()
    for output in CAPTURE["outputs"]:
        path = ROOT / output["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == output["sha256"], path
    for record in CAPTURE["operator_records"]:
        path = ROOT / record["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"], path


def test_word_review_meets_every_declared_requirement():
    assert _failed(WORD_REVIEW) == []
    assert _failed(REVIEW_A) == CAPTURE["audit"]["failed"]["review-a.docx"] == [
        "authors", "comment-resolved", "comment-thread", "endnote-revision",
        "nested-deletion", "paragraph-format-change", "run-format-change"]


@pytest.mark.parametrize("output", [REVIEW_A, WORD_REVIEW], ids=lambda p: p.name)
@pytest.mark.parametrize("part", STORIES)
def test_rejecting_every_revision_restores_the_base(output, part):
    assert _view(output, part, "reject") == _view(BASE, part, "accept")


def test_accepting_every_revision_gives_only_the_checklist_edits():
    base = _view(BASE, "word/document.xml", "accept")
    moved = base.index(MOVED)
    expected = base[:moved] + base[moved + 1:]
    expected.insert(expected.index(FIRST), MOVED)
    fees = expected.index("Fees are payable within thirty days of receipt of a valid invoice.")
    expected[fees] = ("Fees are payable within forty-five days of receipt of a valid invoice. "
                      "The Client may withhold disputed amount.")
    assert _view(WORD_REVIEW, "word/document.xml", "accept") == expected
    assert _view(WORD_REVIEW, "word/header1.xml", "accept") == [
        "Consulting Services Agreement - Draft 4"]
    assert _view(WORD_REVIEW, "word/endnotes.xml", "accept") == [
        " Company details are taken from the public register on 15 September 2026."]
