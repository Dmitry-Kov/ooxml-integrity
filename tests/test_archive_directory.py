"""Untrusted ZIP indexes must be bounded before ZipFile creates any ZipInfo."""
from __future__ import annotations

import io
import json
import struct
import zipfile
from dataclasses import replace

import pytest

from conftest import run_cli

from ooxml_integrity import archive as archive_module
from ooxml_integrity import check, check_pptx, compare
from ooxml_integrity.archive import (
    DEFAULT_ARCHIVE_LIMITS, PackageIssue, package_names, read_package,
)
from ooxml_integrity.policy import ConfigError, Policy


def _archive(path, count=2, *, comment=b"", extra=b"", name_size=0,
             member_comment=b""):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.comment = comment
        for index in range(count):
            info = zipfile.ZipInfo(f"part-{index:05d}" + "x" * name_size + ".xml")
            info.extra = extra
            info.comment = member_comment
            archive.writestr(info, b"")
    return path


def _end(data):
    return data.rindex(b"PK\x05\x06")


def _fake_count(path, count=1):
    data = bytearray(path.read_bytes())
    struct.pack_into("<HH", data, _end(data) + 8, count, count)
    path.write_bytes(data)
    return path


def _zip64(path, *, sentinels=True):
    """Add a small ZIP64 trailer; no multi-gigabyte fixture is needed."""
    data = bytearray(path.read_bytes())
    end = _end(data)
    count, size, offset = struct.unpack_from("<HLL", data, end + 10)
    record = struct.pack("<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45,
                         0, 0, count, count, size, offset)
    locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, end, 1)
    if sentinels:
        struct.pack_into("<HHLL", data, end + 8,
                         0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF)
    path.write_bytes(data[:end] + record + locator + data[end:])
    return path


def _forbid_index(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("ZipFile loaded the unvalidated directory")
    monkeypatch.setattr("ooxml_integrity.archive.zipfile.ZipFile", forbidden)


@pytest.mark.parametrize("reader", [read_package, package_names])
@pytest.mark.parametrize("zip64", [False, True], ids=["zip", "zip64"])
def test_underreported_count_is_rejected_before_index_loading(
        tmp_path, monkeypatch, reader, zip64):
    path = _fake_count(_archive(tmp_path / "forged.zip", 10_000))
    if zip64:
        _zip64(path)
    _forbid_index(monkeypatch)

    with pytest.raises(PackageIssue, match=r"max-entries.*before the central") as caught:
        reader(path)
    assert caught.value.code == "PKG007"


@pytest.mark.parametrize("zip64", [False, True], ids=["zip", "zip64"])
def test_real_count_boundary_is_inclusive(tmp_path, monkeypatch, zip64):
    exact = _archive(tmp_path / "4096.zip", 4096)
    excessive = _archive(tmp_path / "4097.zip", 4097)
    if zip64:
        _zip64(exact)
        _zip64(excessive)
    assert len(package_names(exact)) == 4096
    assert len(read_package(exact)) == 4096
    _forbid_index(monkeypatch)
    with pytest.raises(PackageIssue, match="max-entries") as caught:
        read_package(excessive)
    assert caught.value.code == "PKG007"


@pytest.mark.parametrize("kind", ["name", "extra", "comment"])
def test_directory_bytes_include_all_variable_metadata(tmp_path, monkeypatch, kind):
    options = {
        "name": {"name_size": 60_000},
        "extra": {"extra": struct.pack("<HH", 0xCAFE, 60_000) + b"x" * 60_000},
        "comment": {"member_comment": b"x" * 60_000},
    }[kind]
    path = _archive(tmp_path / "large-metadata.zip", 1, **options)
    data = path.read_bytes()
    size = struct.unpack_from("<L", data, _end(data) + 12)[0]
    limits = replace(DEFAULT_ARCHIVE_LIMITS, max_directory_bytes=size)
    assert len(read_package(path, limits)) == 1
    _forbid_index(monkeypatch)
    with pytest.raises(PackageIssue, match="max-directory-bytes") as caught:
        package_names(path, replace(limits, max_directory_bytes=size - 1))
    assert caught.value.code == "PKG007"


@pytest.mark.parametrize("comment", [b"", b"ordinary ZIP comment", b"x" * 65535])
@pytest.mark.parametrize("zip64", [False, True], ids=["zip", "zip64"])
@pytest.mark.parametrize("count", [0, 2], ids=["empty", "members"])
def test_supported_comments_and_empty_archives(tmp_path, comment, zip64, count):
    path = _archive(tmp_path / "supported.zip", count, comment=comment)
    if zip64:
        _zip64(path)
    assert len(package_names(path)) == count
    assert len(read_package(path)) == count


def test_zip64_trailer_without_legacy_sentinels_is_supported(tmp_path):
    path = _zip64(_archive(tmp_path / "zip64.zip"), sentinels=False)
    assert len(read_package(path)) == 2


def test_stdlib_generated_zip64_directory_and_member_extras(tmp_path, monkeypatch):
    # Lower writer thresholds instead of allocating large files. This exercises
    # actual ZIP64 size/offset extra fields as well as the archive trailer.
    path = tmp_path / "writer64.zip"
    with monkeypatch.context() as writer:
        writer.setattr(zipfile, "ZIP64_LIMIT", 100)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("a.xml", b"a" * 200)
            archive.writestr("b.xml", b"b" * 200)
    assert b"PK\x06\x06" in path.read_bytes()
    assert read_package(path) == {"a.xml": b"a" * 200, "b.xml": b"b" * 200}


def test_preflight_reads_are_bounded_and_stop_at_the_real_entry_limit(
        tmp_path, monkeypatch):
    path = _fake_count(_archive(tmp_path / "forged.zip", 10_000))
    reads = []

    class ObservedFile:
        def __init__(self, raw):
            self.raw = raw

        def __getattr__(self, name):
            return getattr(self.raw, name)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.raw.close()

        def read(self, size=-1):
            assert 0 <= size <= 65557, "unbounded read before validating the index"
            reads.append(size)
            return self.raw.read(size)

    monkeypatch.setattr(archive_module, "open",
                        lambda *args: ObservedFile(open(*args)), raising=False)
    _forbid_index(monkeypatch)
    with pytest.raises(PackageIssue, match="max-entries"):
        package_names(path)
    assert reads.count(46) == 4097


@pytest.mark.parametrize("force_zip64", [False, True])
def test_data_descriptors_and_member_zip64_are_supported(tmp_path, force_zip64):
    class NonSeekable(io.BytesIO):
        def seek(self, *args):
            raise io.UnsupportedOperation("stream")

    output = NonSeekable()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        with archive.open("part.xml", "w", force_zip64=force_zip64) as part:
            part.write(b"<part>streamed</part>")
    path = tmp_path / "descriptor.zip"
    path.write_bytes(output.getvalue())
    assert read_package(path) == {"part.xml": b"<part>streamed</part>"}


@pytest.mark.parametrize("mutation", [
    "small-count", "large-count", "disk-count", "disk-number", "directory-disk",
    "small-size", "large-size", "huge-size", "offset-before", "offset-after",
    "huge-offset", "empty-index", "truncated-comment", "extra-trailing-bytes",
    "comment-signature", "bad-central-signature", "truncated-central-header",
    "truncated-variable-data", "truncated-end-record",
    "oversized-name", "oversized-extra", "oversized-member-comment",
    "member-disk", "member-offset",
])
def test_inconsistent_zip_metadata_is_rejected_before_index(
        tmp_path, monkeypatch, mutation):
    path = _archive(tmp_path / "invalid.zip")
    data = bytearray(path.read_bytes())
    end = _end(data)
    size, offset = struct.unpack_from("<LL", data, end + 12)
    fields = {
        "small-count": ("<HH", end + 8, (1, 1)),
        "large-count": ("<HH", end + 8, (3, 3)),
        "disk-count": ("<H", end + 8, (1,)),
        "disk-number": ("<H", end + 4, (1,)),
        "directory-disk": ("<H", end + 6, (1,)),
        "small-size": ("<L", end + 12, (size - 1,)),
        "large-size": ("<L", end + 12, (size + 1,)),
        "huge-size": ("<L", end + 12, (0xFFFFFFFE,)),
        "offset-before": ("<L", end + 16, (offset - 1,)),
        "offset-after": ("<L", end + 16, (offset + 1,)),
        "huge-offset": ("<L", end + 16, (0xFFFFFFFE,)),
        "empty-index": ("<HHLL", end + 8, (0, 0, 0, end)),
        "truncated-comment": ("<H", end + 20, (1,)),
        "oversized-name": ("<H", offset + 28, (65535,)),
        "oversized-extra": ("<H", offset + 30, (65535,)),
        "oversized-member-comment": ("<H", offset + 32, (65535,)),
        "member-disk": ("<H", offset + 34, (1,)),
        "member-offset": ("<L", offset + 42, (end,)),
    }
    if mutation in fields:
        fmt, position, values = fields[mutation]
        struct.pack_into(fmt, data, position, *values)
    elif mutation == "extra-trailing-bytes":
        data.extend(b"trailing")
    elif mutation == "comment-signature":
        struct.pack_into("<H", data, end + 20, 4)
        data.extend(b"PK\x05\x06")
    elif mutation == "bad-central-signature":
        data[offset:offset + 4] = b"junk"
    elif mutation == "truncated-central-header":
        trailer = data[end:]
        struct.pack_into("<HHLL", trailer, 8, 1, 1, 20, offset)
        data = data[:offset + 20] + trailer
    elif mutation == "truncated-variable-data":
        # Keep the trailer bounds consistent, with a too-short final record.
        data = data[:end - 1] + data[end:]
        struct.pack_into("<L", data, end - 1 + 12, size - 1)
    elif mutation == "truncated-end-record":
        del data[-10:]
    path.write_bytes(data)
    _forbid_index(monkeypatch)
    with pytest.raises(PackageIssue) as caught:
        read_package(path)
    assert caught.value.code == "PKG002"


@pytest.mark.parametrize("mutation", [
    "locator-offset", "locator-disk", "locator-disks", "record-size",
    "record-signature", "disk-number", "directory-disk", "disk-count",
    "count", "size", "offset", "legacy-count", "legacy-size", "legacy-offset",
    "missing-locator", "extensible-data",
])
def test_inconsistent_zip64_metadata_is_rejected_before_index(
        tmp_path, monkeypatch, mutation):
    path = _zip64(_archive(tmp_path / "invalid64.zip"))
    data = bytearray(path.read_bytes())
    end = _end(data)
    locator = end - 20
    record = locator - 56
    fields = {
        "locator-offset": ("<Q", locator + 8, (record - 1,)),
        "locator-disk": ("<L", locator + 4, (1,)),
        "locator-disks": ("<L", locator + 16, (2,)),
        "record-size": ("<Q", record + 4, (45,)),
        "disk-number": ("<L", record + 16, (1,)),
        "directory-disk": ("<L", record + 20, (1,)),
        "disk-count": ("<Q", record + 24, (1,)),
        "count": ("<QQ", record + 24, (1, 1)),
        "size": ("<Q", record + 40, (2**63,)),
        "offset": ("<Q", record + 48, (2**63,)),
        "legacy-count": ("<HH", end + 8, (1, 1)),
        "legacy-size": ("<L", end + 12, (1,)),
        "legacy-offset": ("<L", end + 16, (1,)),
    }
    if mutation in fields:
        fmt, position, values = fields[mutation]
        struct.pack_into(fmt, data, position, *values)
    elif mutation == "record-signature":
        data[record:record + 4] = b"junk"
    elif mutation == "missing-locator":
        del data[locator:end]
    elif mutation == "extensible-data":
        struct.pack_into("<Q", data, record + 4, 45)
        data[locator:locator] = b"x"
    path.write_bytes(data)
    _forbid_index(monkeypatch)
    with pytest.raises(PackageIssue) as caught:
        read_package(path)
    assert caught.value.code == "PKG002"


def test_all_readers_reject_forged_index_without_decompression(
        base_docx, tmp_path, monkeypatch):
    path = _fake_count(_archive(tmp_path / "forged.docx", 10_000))

    def forbidden(*args, **kwargs):
        raise AssertionError("member decompressed before directory validation")
    monkeypatch.setattr(zipfile.ZipFile, "read", forbidden)
    assert [f.code for f in check(path)] == ["PKG007"]
    assert [f.code for f in check_pptx(path)] == ["PKG007"]
    with pytest.raises(PackageIssue) as caught:
        compare(path, base_docx)
    assert caught.value.code == "PKG007"
    with pytest.raises(PackageIssue) as caught:
        read_package(path, members=["part-00000.xml"])
    assert caught.value.code == "PKG007"


def test_directory_budget_config_and_cli_reports(base_docx, tmp_path):
    config = tmp_path / "limits.toml"
    config.write_text("[archive]\nmax-directory-bytes = 100\n", encoding="utf-8")
    policy = Policy.load(config)
    assert policy.archive.max_directory_bytes == 100
    sarif = tmp_path / "limits.sarif"
    result = run_cli("check", str(base_docx), "--config", str(config),
                     "--coverage", "--json", "--sarif", str(sarif))
    assert result.returncode == 1, result.stdout + result.stderr
    file = json.loads(result.stdout)["files"][0]
    assert [f["code"] for f in file["findings"]] == ["PKG007"]
    assert "max-directory-bytes" in file["findings"][0]["message"]
    assert file["coverage"]["items"][0]["status"] == "skipped"
    report = json.loads(sarif.read_text(encoding="utf-8"))
    assert report["runs"][0]["results"][0]["ruleId"] == "PKG007"


@pytest.mark.parametrize("kind", ["utf8-name", "extract-version", "zip64-offset"])
def test_invalid_index_fields_are_findings_without_member_reads(
        tmp_path, monkeypatch, kind):
    if kind == "zip64-offset":
        # The 64-bit offset is decoded by ZipFile only after the bounded scan.
        extra = struct.pack("<HHQ", 1, 8, 2**64 - 1)
        path = _archive(tmp_path / "invalid.docx", 1, extra=extra)
    else:
        path = _archive(tmp_path / "invalid.docx", 1)
    data = bytearray(path.read_bytes())
    offset = struct.unpack_from("<L", data, _end(data) + 16)[0]
    if kind == "utf8-name":
        struct.pack_into("<H", data, offset + 8, 0x800)
        data[offset + 46] = 255
    elif kind == "extract-version":
        struct.pack_into("<H", data, offset + 6, 255)
    else:
        struct.pack_into("<L", data, offset + 42, 0xFFFFFFFF)
    path.write_bytes(data)

    def forbidden(*args, **kwargs):
        raise AssertionError("member read before index validation")
    monkeypatch.setattr(zipfile.ZipFile, "read", forbidden)
    assert [f.code for f in check(path)] == ["PKG002"]
    assert [f.code for f in check_pptx(path)] == ["PKG002"]
    with pytest.raises((PackageIssue, zipfile.BadZipFile)):
        package_names(path)


@pytest.mark.parametrize("value", [0, -1, 0.5, True, "100"])
def test_directory_budget_rejects_invalid_config(value):
    with pytest.raises(ConfigError, match="positive integer"):
        Policy._from_dict({"archive": {"max-directory-bytes": value}})
