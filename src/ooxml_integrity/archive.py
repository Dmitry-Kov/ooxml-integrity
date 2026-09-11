"""Bounded reading for untrusted OOXML ZIP packages.

The ZIP central directory is metadata supplied by the input file.  Inspect all
of it before decompressing a member, then keep the total possible allocation
within explicit budgets.  DOCX, PPTX and source-fidelity checks share this
module so one entry point cannot accidentally bypass the limits.
"""
from __future__ import annotations

import os
import re
import struct
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import BinaryIO, Iterable
from urllib.parse import unquote


MIB = 1024 * 1024
_EOCD = struct.Struct("<4s4H2LH")
_ZIP64_LOCATOR = struct.Struct("<4sLQL")
_ZIP64_EOCD = struct.Struct("<4sQ2H2L4Q")
_CENTRAL_HEADER = struct.Struct("<4s6H3L5H2L")
_ASCII_LOWER = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz",
)


@dataclass(frozen=True)
class ArchiveLimits:
    """Resource budgets applied before any ZIP member is decompressed."""

    max_entries: int = 4096
    max_archive_bytes: int = 256 * MIB
    max_total_expanded_bytes: int = 512 * MIB
    max_entry_expanded_bytes: int = 128 * MIB
    max_compression_ratio: float = 1000.0
    # Append new fields to preserve the existing positional constructor.
    max_directory_bytes: int = 16 * MIB

    def __post_init__(self) -> None:
        integer_fields = (
            "max_entries",
            "max_archive_bytes",
            "max_total_expanded_bytes",
            "max_entry_expanded_bytes",
            "max_directory_bytes",
        )
        for name in integer_fields:
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        ratio = self.max_compression_ratio
        if (type(ratio) not in (int, float) or not isfinite(ratio) or ratio < 1):
            raise ValueError("max_compression_ratio must be a finite number >= 1")


DEFAULT_ARCHIVE_LIMITS = ArchiveLimits()


class PackageIssue(Exception):
    """A package problem that maps directly to a stable finding code."""

    def __init__(self, code: str, message: str, *, part: str = ""):
        super().__init__(message)
        self.code = code
        self.part = part


def _size(value: int) -> str:
    if value < MIB:
        return f"{value} bytes"
    return f"{value / MIB:.1f} MiB ({value} bytes)"


def _invalid_directory(reason: str) -> PackageIssue:
    return PackageIssue("PKG002", f"invalid or unsupported ZIP directory: {reason}")


def _directory_bounds(raw: BinaryIO, file_size: int) -> tuple[int, int, int]:
    """Read fixed-size trailers, validating the same directory ZipFile will use.

    The supported single-disk layout has absolute offsets and no gaps between
    the central directory and its trailers. Do not use ZipFile's concatenation
    offset repair: that could select metadata other than what we validated.
    """
    tail_size = min(file_size, _EOCD.size + 65535)
    raw.seek(file_size - tail_size)
    tail = raw.read(tail_size)
    # Match ZipFile's last-signature choice. Searching backwards for a different
    # valid trailer can disagree with its interpretation of a crafted comment.
    pos = tail.rfind(b"PK\x05\x06")
    if pos < 0 or pos + _EOCD.size > len(tail):
        raise _invalid_directory("missing or truncated end record")
    end = _EOCD.unpack_from(tail, pos)
    if pos + _EOCD.size + end[7] != len(tail):
        raise _invalid_directory("comment length or trailing bytes do not match")
    if end[1] != 0 or end[2] != 0:
        raise _invalid_directory("multi-disk archives are not supported")
    disk_count, count, size, offset = end[3:7]
    directory_end = file_size - tail_size + pos

    locator = b""
    if directory_end >= _ZIP64_LOCATOR.size:
        raw.seek(directory_end - _ZIP64_LOCATOR.size)
        locator = raw.read(_ZIP64_LOCATOR.size)
    if locator[:4] == b"PK\x06\x07":
        _, disk, record_offset, disks = _ZIP64_LOCATOR.unpack(locator)
        if disk != 0 or disks != 1:
            raise _invalid_directory("multi-disk ZIP64 archives are not supported")
        # Python 3.9's ZIP64 reader expects exactly this fixed-size record.
        expected_offset = directory_end - _ZIP64_LOCATOR.size - _ZIP64_EOCD.size
        if record_offset != expected_offset or expected_offset < 0:
            raise _invalid_directory("ZIP64 locator offset or record size does not match")
        raw.seek(record_offset)
        record = raw.read(_ZIP64_EOCD.size)
        if len(record) != _ZIP64_EOCD.size or record[:4] != b"PK\x06\x06":
            raise _invalid_directory("missing or truncated ZIP64 end record")
        extended = _ZIP64_EOCD.unpack(record)
        if extended[1] != 44:
            raise _invalid_directory("ZIP64 extensible end records are not supported")
        if extended[4] != 0 or extended[5] != 0:
            raise _invalid_directory("multi-disk ZIP64 archives are not supported")
        for legacy, actual, sentinel in zip(
                end[3:7], extended[6:10], (0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF)):
            if legacy not in (sentinel, actual):
                raise _invalid_directory("ZIP and ZIP64 end records disagree")
        disk_count, count, size, offset = extended[6:10]
        directory_end = record_offset
    if disk_count != count:
        raise _invalid_directory("per-disk and total entry counts disagree")
    if offset + size != directory_end:
        raise _invalid_directory("directory size and offset do not match its end")
    if size == 0 and (count != 0 or offset != 0):
        raise _invalid_directory("empty directory has entries or a nonzero offset")
    return offset, size, count


def _entry_budget(count: int, limits: ArchiveLimits) -> None:
    if count > limits.max_entries:
        raise PackageIssue(
            "PKG007",
            "archive entry count exceeds max-entries before the central "
            f"directory is loaded: {count} > {limits.max_entries}",
        )


def _preflight_file(raw: BinaryIO, limits: ArchiveLimits) -> int:
    """Count actual records using fixed-size reads before allocating ZipInfos."""
    file_size = os.fstat(raw.fileno()).st_size
    if file_size > limits.max_archive_bytes:
        raise PackageIssue(
            "PKG007",
            "archive size exceeds max-archive-bytes: "
            f"{_size(file_size)} > {_size(limits.max_archive_bytes)}",
        )
    offset, size, declared_count = _directory_bounds(raw, file_size)
    _entry_budget(declared_count, limits)
    if size > limits.max_directory_bytes:
        raise PackageIssue(
            "PKG007", "central directory size exceeds max-directory-bytes: "
            f"{_size(size)} > {_size(limits.max_directory_bytes)}",
        )
    raw.seek(offset)
    remaining = size
    count = 0
    while remaining:
        if remaining < _CENTRAL_HEADER.size:
            raise _invalid_directory("truncated central file header")
        header = raw.read(_CENTRAL_HEADER.size)
        if len(header) != _CENTRAL_HEADER.size or header[:4] != b"PK\x01\x02":
            raise _invalid_directory("missing or truncated central file header")
        fields = _CENTRAL_HEADER.unpack(header)
        count += 1
        _entry_budget(count, limits)
        variable_size = sum(fields[10:13])  # filename, extra fields, comment
        record_size = _CENTRAL_HEADER.size + variable_size
        if record_size > remaining:
            raise _invalid_directory("variable metadata extends past the directory")
        if fields[13] != 0:
            raise _invalid_directory("multi-disk member references are not supported")
        if fields[16] != 0xFFFFFFFF and fields[16] >= offset:
            raise _invalid_directory("local header offset points into the directory")
        # Do not allocate names, comments or extra fields during preflight.
        raw.seek(variable_size, os.SEEK_CUR)
        remaining -= record_size
    if count != declared_count:
        raise _invalid_directory(
            f"entry count does not match the directory: {declared_count} != {count}",
        )
    return offset


@contextmanager
def _open_archive(path: Path, limits: ArchiveLimits):
    # Keep the same file handle through preflight and loading, so a replacement
    # of the path cannot substitute an unchecked package between the two.
    with open(path, "rb") as raw:
        directory_offset = _preflight_file(raw, limits)
        raw.seek(0)
        try:
            archive = zipfile.ZipFile(raw)
        except (NotImplementedError, UnicodeError) as error:
            raise _invalid_directory(str(error)) from error
        with archive:
            # ZipFile has now decoded ZIP64 local offsets from member extras.
            # Validate those too, before any read can seek outside member data.
            for info in archive.infolist():
                if not 0 <= info.header_offset < directory_offset:
                    raise _invalid_directory("local header offset is outside member data")
            yield archive


def _normal_part_name(name: str, *, directory: bool) -> str:
    """Return a comparison spelling or reject path-like package member names."""
    try:
        decoded = unquote(name, errors="strict")
    except UnicodeDecodeError as e:
        raise PackageIssue(
            "PKG008", f"package part name has invalid percent encoding: {name!r}",
            part=name,
        ) from e
    if not decoded or "\x00" in decoded:
        raise PackageIssue(
            "PKG008", f"unsafe empty or NUL-containing package part name: {name!r}",
            part=name,
        )
    if "\\" in decoded:
        raise PackageIssue(
            "PKG008",
            f"unsafe package part name uses a backslash separator: {name!r}",
            part=name,
        )
    if decoded.startswith("/") or re.match(r"^[A-Za-z]:/", decoded):
        raise PackageIssue(
            "PKG008", f"unsafe absolute package part name: {name!r}", part=name,
        )

    candidate = decoded[:-1] if directory and decoded.endswith("/") else decoded
    segments = candidate.split("/")
    if not candidate or any(segment in ("", ".", "..") for segment in segments):
        raise PackageIssue(
            "PKG008",
            f"unsafe traversal-like or non-canonical package part name: {name!r}",
            part=name,
        )
    # OPC part-URI equivalence is ASCII-case-insensitive. Do not use lower(),
    # which would introduce additional Unicode equivalences the standard does
    # not define.
    return "/".join(segments).translate(_ASCII_LOWER)


def validate_infos(
    infos: Iterable[zipfile.ZipInfo],
    limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS,
) -> list[zipfile.ZipInfo]:
    """Validate all central-directory metadata without reading member bodies."""
    entries = list(infos)
    if len(entries) > limits.max_entries:
        raise PackageIssue(
            "PKG007",
            f"archive entry count exceeds max-entries: "
            f"{len(entries)} > {limits.max_entries}",
        )

    total = 0
    names: dict[str, str] = {}
    for info in entries:
        name = info.filename
        normal = _normal_part_name(name, directory=info.is_dir())
        if normal in names:
            raise PackageIssue(
                "PKG008",
                "duplicate normalized package part name: "
                f"{names[normal]!r} and {name!r} both resolve to /{normal}",
                part=name,
            )
        names[normal] = name

        expanded = info.file_size
        if expanded > limits.max_entry_expanded_bytes:
            raise PackageIssue(
                "PKG007",
                f"expanded part exceeds max-entry-expanded-bytes: "
                f"{_size(expanded)} > {_size(limits.max_entry_expanded_bytes)}",
                part=name,
            )
        total += expanded
        if total > limits.max_total_expanded_bytes:
            raise PackageIssue(
                "PKG007",
                "total expanded package size exceeds max-total-expanded-bytes: "
                f"{_size(total)} > {_size(limits.max_total_expanded_bytes)}",
                part=name,
            )

        if expanded:
            ratio = (expanded / info.compress_size
                     if info.compress_size else float("inf"))
            if ratio > limits.max_compression_ratio:
                shown = ("infinite" if ratio == float("inf")
                         else f"{ratio:.6g}:1")
                raise PackageIssue(
                    "PKG007",
                    "part compression ratio exceeds max-compression-ratio: "
                    f"{shown} > {limits.max_compression_ratio:g}:1",
                    part=name,
                )
    return entries


def read_package(path: str | Path,
                 limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS, *,
                 members: Iterable[str] | None = None) -> dict[str, bytes]:
    """Read a ZIP package only after every configured budget has passed."""
    package = Path(path)
    with _open_archive(package, limits) as archive:
        infos = validate_infos(archive.infolist(), limits)
        wanted = set(members) if members is not None else None
        parts: dict[str, bytes] = {}
        for info in infos:
            if wanted is not None and info.filename not in wanted:
                continue
            try:
                parts[info.filename] = archive.read(info)
            except zipfile.BadZipFile as e:
                raise PackageIssue(
                    "PKG001", f"corrupt entry in archive: {info.filename}: {e}",
                    part=info.filename,
                ) from e
            except (NotImplementedError, RuntimeError) as e:
                raise PackageIssue(
                    "PKG002", f"could not read package part {info.filename}: {e}",
                    part=info.filename,
                ) from e
    return parts


def package_names(path: str | Path,
                  limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS) -> list[str]:
    """Validate a package and return its names without decompressing members."""
    package = Path(path)
    with _open_archive(package, limits) as archive:
        return [info.filename for info in validate_infos(archive.infolist(), limits)]
