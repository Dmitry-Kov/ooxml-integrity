"""Archive budgets are enforced before untrusted members are decompressed."""
from __future__ import annotations

import hashlib
import json
import random
import struct
import warnings
import zipfile
from dataclasses import replace

import pytest

from conftest import run_cli

from ooxml_integrity import ArchiveLimits, check, check_pptx, compare
from ooxml_integrity.archive import (
    DEFAULT_ARCHIVE_LIMITS,
    PackageIssue,
    read_package,
    validate_infos,
)
from ooxml_integrity.cli import EXIT_FINDINGS
from ooxml_integrity.policy import ConfigError, Policy


def _info(name: str, expanded: int, compressed: int | None = None
          ) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.file_size = expanded
    info.compress_size = expanded if compressed is None else compressed
    return info


def _with_extra(src, dst, name: str, data: bytes = b"extra"):
    with zipfile.ZipFile(src) as incoming, zipfile.ZipFile(
            dst, "w", zipfile.ZIP_DEFLATED) as outgoing:
        for info in incoming.infolist():
            outgoing.writestr(info, incoming.read(info))
        outgoing.writestr(name, data)
    return dst


def test_entry_count_boundary_is_inclusive():
    infos = [_info("a.xml", 1), _info("b.xml", 1)]
    exact = replace(DEFAULT_ARCHIVE_LIMITS, max_entries=2)
    validate_infos(infos, exact)

    with pytest.raises(PackageIssue, match=r"entry count.*2 > 1") as caught:
        validate_infos(infos, replace(exact, max_entries=1))
    assert caught.value.code == "PKG007"


def test_total_expanded_boundary_is_inclusive():
    infos = [_info("a.xml", 7), _info("b.xml", 5)]
    exact = replace(
        DEFAULT_ARCHIVE_LIMITS,
        max_total_expanded_bytes=12,
        max_entry_expanded_bytes=12,
    )
    validate_infos(infos, exact)

    with pytest.raises(PackageIssue, match="max-total-expanded-bytes"):
        validate_infos(
            infos, replace(exact, max_total_expanded_bytes=11),
        )


def test_per_entry_expanded_boundary_is_inclusive():
    info = _info("large.xml", 12)
    exact = replace(
        DEFAULT_ARCHIVE_LIMITS,
        max_entry_expanded_bytes=12,
        max_total_expanded_bytes=12,
    )
    validate_infos([info], exact)

    with pytest.raises(PackageIssue, match="max-entry-expanded-bytes"):
        validate_infos([info], replace(exact, max_entry_expanded_bytes=11))


def test_archive_byte_boundary_is_checked_before_zipfile_opens(
        tmp_path, monkeypatch):
    path = tmp_path / "small.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("part.xml", b"payload")
    exact_size = path.stat().st_size
    exact = replace(DEFAULT_ARCHIVE_LIMITS, max_archive_bytes=exact_size)
    assert read_package(path, exact)["part.xml"] == b"payload"

    opened = False
    original = zipfile.ZipFile

    def unexpected_open(*args, **kwargs):
        nonlocal opened
        opened = True
        return original(*args, **kwargs)

    monkeypatch.setattr("ooxml_integrity.archive.zipfile.ZipFile", unexpected_open)
    limits = replace(DEFAULT_ARCHIVE_LIMITS, max_archive_bytes=exact_size - 1)
    with pytest.raises(PackageIssue, match="max-archive-bytes"):
        read_package(path, limits)
    assert not opened


def test_compression_ratio_boundary_is_inclusive(tmp_path):
    path = tmp_path / "ratio.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("large.xml", b"x" * 1024 * 1024)
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("large.xml")
    ratio = info.file_size / info.compress_size
    exact = replace(DEFAULT_ARCHIVE_LIMITS, max_compression_ratio=ratio)
    assert read_package(path, exact)["large.xml"]

    with pytest.raises(PackageIssue, match="max-compression-ratio"):
        read_package(
            path, replace(exact, max_compression_ratio=ratio - 0.01),
        )


def test_declared_entry_limit_fails_before_any_member_read(tmp_path, monkeypatch):
    path = tmp_path / "two.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("a.xml", b"a")
        archive.writestr("b.xml", b"b")

    def forbidden(*args, **kwargs):
        raise AssertionError("a member was read before metadata limits passed")

    monkeypatch.setattr(zipfile.ZipFile, "read", forbidden)
    with pytest.raises(PackageIssue, match="before the central directory"):
        read_package(path, replace(DEFAULT_ARCHIVE_LIMITS, max_entries=1))


def test_unsupported_compression_is_invalid_input_not_a_traceback(tmp_path):
    path = tmp_path / "unsupported.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("part.xml", b"payload")
    data = bytearray(path.read_bytes())
    local = data.index(b"PK\x03\x04")
    central = data.index(b"PK\x01\x02")
    struct.pack_into("<H", data, local + 8, 99)
    struct.pack_into("<H", data, central + 10, 99)
    path.write_bytes(data)

    findings = check(path)
    assert [f.code for f in findings] == ["PKG002"]
    assert "compression method" in findings[0].message


def test_duplicate_literal_part_names_are_rejected(base_docx, tmp_path):
    out = tmp_path / "duplicate.docx"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        _with_extra(base_docx, out, "word/document.xml", b"<replacement/>")

    findings = check(out)
    assert [f.code for f in findings] == ["PKG008"]
    assert "duplicate normalized" in findings[0].message


def test_duplicate_percent_normalized_part_names_are_rejected(
        base_docx, tmp_path):
    out = _with_extra(
        base_docx, tmp_path / "normalized-duplicate.docx",
        "word/%64ocument.xml", b"<replacement/>",
    )

    findings = check(out)
    assert [f.code for f in findings] == ["PKG008"]
    assert "word/document.xml" in findings[0].message


def test_duplicate_ascii_case_insensitive_part_names_are_rejected(
        base_docx, tmp_path):
    out = _with_extra(
        base_docx, tmp_path / "case-duplicate.docx",
        "WORD/DOCUMENT.XML", b"<replacement/>",
    )

    findings = check(out)
    assert [f.code for f in findings] == ["PKG008"]
    assert "duplicate normalized" in findings[0].message


def test_unicode_case_is_not_folded_beyond_opc_ascii_equivalence():
    infos = [_info("word/Ä.xml", 1), _info("word/ä.xml", 1)]
    assert validate_infos(infos) == infos


@pytest.mark.parametrize("name", [
    "../outside.xml",
    "word/../../outside.xml",
    "/absolute.xml",
    "C:/absolute.xml",
    "word\\..\\outside.xml",
    "word/%2e%2e/outside.xml",
    "word//outside.xml",
    "word/%FF.xml",
])
def test_traversal_like_part_names_are_rejected(base_docx, tmp_path, name):
    out = _with_extra(base_docx, tmp_path / "unsafe.docx", name)

    findings = check(out)
    assert [f.code for f in findings] == ["PKG008"]
    assert findings[0].part == name


def test_default_limits_leave_normal_corpus_unchanged(base_docx, root):
    before = hashlib.sha256(base_docx.read_bytes()).digest()
    assert check(base_docx) == []
    assert not [
        f for f in check_pptx(root / "corpus" / "deck.pptx")
        if f.code in ("PKG007", "PKG008")
    ]
    assert hashlib.sha256(base_docx.read_bytes()).digest() == before


def test_docx_cli_uses_archive_limits_from_config(base_docx, tmp_path):
    config = tmp_path / "limits.toml"
    with zipfile.ZipFile(base_docx) as archive:
        count = len(archive.infolist())
    config.write_text(
        f"[archive]\nmax-entries = {count - 1}\n",
        encoding="utf-8",
    )

    result = run_cli("check", str(base_docx), "--config", str(config), "--json")
    assert result.returncode == EXIT_FINDINGS
    finding = json.loads(result.stdout)["files"][0]["findings"][0]
    assert finding["code"] == "PKG007"
    assert "max-entries" in finding["message"]


def test_pptx_library_api_accepts_custom_limits(root):
    deck = root / "corpus" / "deck.pptx"
    findings = check_pptx(
        deck, limits=replace(DEFAULT_ARCHIVE_LIMITS, max_entries=1),
    )
    assert [f.code for f in findings] == ["PKG007"]


def test_source_comparison_is_bounded_and_fails_closed(
        base_docx, tmp_path):
    source = _with_extra(
        base_docx, tmp_path / "large-source.docx", "extra.bin",
    )
    with zipfile.ZipFile(base_docx) as archive:
        target_count = len(archive.infolist())
    limits = replace(DEFAULT_ARCHIVE_LIMITS, max_entries=target_count)

    with pytest.raises(PackageIssue, match="max-entries"):
        compare(source, base_docx, limits=limits)

    config = tmp_path / "limits.toml"
    config.write_text(
        f"[archive]\nmax-entries = {target_count}\n",
        encoding="utf-8",
    )
    result = run_cli(
        "check", str(base_docx), "--against", str(source),
        "--config", str(config), "--json",
    )
    assert result.returncode == EXIT_FINDINGS
    findings = json.loads(result.stdout)["files"][0]["findings"]
    assert [f["code"] for f in findings] == ["FID000"]
    assert "max-entries" in findings[0]["message"]


@pytest.mark.parametrize("bad", [0, -1, 1.5, "100", True])
def test_integer_archive_limits_must_be_positive_integers(bad):
    with pytest.raises(ConfigError, match="positive integer"):
        Policy._from_dict({"archive": {"max-entries": bad}})


def test_unknown_archive_config_key_is_rejected():
    with pytest.raises(ConfigError, match="unknown archive key"):
        Policy._from_dict({"archive": {"max-expanded-byte": 123}})


@pytest.mark.parametrize("bad", [[], "large", 42, True])
def test_archive_config_must_be_a_table(bad):
    with pytest.raises(ConfigError, match="TOML table"):
        Policy._from_dict({"archive": bad})


@pytest.mark.parametrize("bad", [0.5, float("inf"), float("-inf"), float("nan")])
def test_compression_ratio_must_be_finite_and_at_least_one(bad):
    with pytest.raises(ConfigError, match="finite number"):
        Policy._from_dict({"archive": {"max-compression-ratio": bad}})


def test_every_archive_config_value_is_loaded():
    policy = Policy._from_dict({
        "archive": {
            "max-entries": 10,
            "max-archive-bytes": 20,
            "max-total-expanded-bytes": 30,
            "max-entry-expanded-bytes": 15,
            "max-compression-ratio": 4.5,
        },
    })
    assert policy.archive == ArchiveLimits(10, 20, 30, 15, 4.5)


def test_randomized_size_metadata_obeys_the_two_expanded_budgets():
    """Property-style coverage around many total/per-entry boundary mixes."""
    rng = random.Random(20260904)
    for case in range(250):
        sizes = [rng.randrange(0, 5000) for _ in range(rng.randrange(1, 12))]
        per_entry = rng.randrange(1, 5000)
        total = rng.randrange(1, 20000)
        infos = [_info(f"part-{case}-{i}.xml", size)
                 for i, size in enumerate(sizes)]
        limits = ArchiveLimits(
            max_entries=20,
            max_archive_bytes=1024 * 1024,
            max_total_expanded_bytes=total,
            max_entry_expanded_bytes=per_entry,
            max_compression_ratio=10,
        )
        should_fail = max(sizes) > per_entry or sum(sizes) > total
        if should_fail:
            with pytest.raises(PackageIssue) as caught:
                validate_infos(infos, limits)
            assert caught.value.code == "PKG007"
        else:
            assert validate_infos(infos, limits) == infos
