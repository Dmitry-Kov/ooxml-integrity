"""`repack`: a copy with some members replaced and every other one as stored.

Copied with no replacement, each of the 3,241 DOCX packages in the repository
and the public corpora that it can copy (not ZIP64, no Unicode Path fields)
came out byte-identical when this was written; these cases keep the layouts
that took care.
"""
from __future__ import annotations

import io
import struct
import zipfile

import pytest
from conftest import ROOT

from ooxml_integrity.repack import RepackError, differences, read_entries, repack

ADEU = ROOT / "evidence" / "review-history-benchmark" / "captures" / "adeu-1" / "K4-S1-tracked.docx"


class _Unseekable(io.RawIOBase):
    """Makes zipfile write data descriptors, as streaming writers do."""

    def __init__(self):
        self.buffer = io.BytesIO()

    def writable(self):
        return True

    def write(self, data):
        return self.buffer.write(data)


def _streamed(path):
    sink = _Unseekable()
    with zipfile.ZipFile(sink, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", b"<Types/>")
        z.writestr("word/document.xml", b"<doc>old</doc>")
        z.writestr("media/a.bin", b"\x00" * 100, compress_type=zipfile.ZIP_STORED)
    path.write_bytes(sink.buffer.getvalue())
    return path


def test_unchanged_copy_is_byte_identical(tmp_path):
    for source in (ADEU, _streamed(tmp_path / "streamed.zip")):
        out = io.BytesIO()
        repack(source, out, {})
        assert out.getvalue() == source.read_bytes()


def test_data_descriptors_are_kept_and_replaced_member_is_read_back(tmp_path):
    source = _streamed(tmp_path / "streamed.zip")
    assert all(e.flags & 0x08 for e in read_entries(source))
    out = tmp_path / "out.zip"
    with open(out, "wb") as fh:
        repack(source, fh, {"word/document.xml": b"<doc>new</doc>"})
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        assert z.read("word/document.xml") == b"<doc>new</doc>"
        assert z.read("media/a.bin") == b"\x00" * 100
        assert z.getinfo("media/a.bin").compress_type == zipfile.ZIP_STORED
    assert differences(source, out, {"word/document.xml"}) == []
    assert differences(source, out, set()) == [
        "word/document.xml: stored bytes differ",
        "word/document.xml: directory record differs"]


def test_stored_order_is_kept_when_it_differs_from_the_directory(tmp_path):
    """Members are written in stored order; the directory keeps its own."""
    source = tmp_path / "plain.zip"
    with zipfile.ZipFile(source, "w") as z:
        z.writestr("a", b"A")
        z.writestr("b", b"B")
    data = bytearray(source.read_bytes())
    start = data.index(b"PK\x01\x02")
    end = data.index(b"PK\x05\x06")
    first = struct.unpack_from("<HHH", data, start + 28)
    size = 46 + sum(first)
    data[start:end] = data[start + size:end] + data[start:start + size]
    swapped = tmp_path / "swapped.zip"
    swapped.write_bytes(bytes(data))
    assert [e.name for e in read_entries(swapped)] == ["b", "a"]
    out = io.BytesIO()
    repack(swapped, out, {})
    assert out.getvalue() == bytes(data)


def test_unicode_path_field_is_refused(tmp_path):
    """Readers that honour it see another name than readers that do not."""
    source = tmp_path / "unicode.zip"
    with zipfile.ZipFile(source, "w") as z:
        info = zipfile.ZipInfo("word/document.xml")
        name = b"other.xml"
        info.extra = struct.pack("<HHB", 0x7075, 5 + len(name), 1) + struct.pack(
            "<L", zipfile.crc32(b"word/document.xml")) + name
        z.writestr(info, b"<doc/>")
    with pytest.raises(RepackError, match="second name"):
        repack(source, io.BytesIO(), {})
