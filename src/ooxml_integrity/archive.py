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
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote


MIB = 1024 * 1024
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

    def __post_init__(self) -> None:
        integer_fields = (
            "max_entries",
            "max_archive_bytes",
            "max_total_expanded_bytes",
            "max_entry_expanded_bytes",
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


def _zip64_entry_count(raw, eocd_offset: int) -> int | None:
    """Return the ZIP64 count without asking ZipFile to load the directory."""
    locator_size = 20
    if eocd_offset < locator_size:
        return None
    raw.seek(eocd_offset - locator_size)
    locator = raw.read(locator_size)
    if len(locator) != locator_size or locator[:4] != b"PK\x06\x07":
        return None
    _, _, record_offset, _ = struct.unpack("<4sLQL", locator)
    raw.seek(record_offset)
    record = raw.read(56)
    if len(record) < 56 or record[:4] != b"PK\x06\x06":
        return None
    fields = struct.unpack("<4sQ2H2L4Q", record[:56])
    return int(fields[7])


def _declared_entry_count(raw, file_size: int) -> int | None:
    """Read the EOCD count using at most the ZIP comment tail (about 64 KiB)."""
    eocd_size = 22
    if file_size < eocd_size:
        return None
    tail_size = min(file_size, eocd_size + 65535)
    raw.seek(file_size - tail_size)
    tail = raw.read(tail_size)
    search_end = len(tail)
    while True:
        pos = tail.rfind(b"PK\x05\x06", 0, search_end)
        if pos < 0:
            return None
        if pos + eocd_size <= len(tail):
            fields = struct.unpack_from("<4s4H2LH", tail, pos)
            comment_size = fields[-1]
            if pos + eocd_size + comment_size == len(tail):
                count = int(fields[4])
                if count != 0xFFFF:
                    return count
                absolute = file_size - tail_size + pos
                return _zip64_entry_count(raw, absolute) or count
        search_end = pos


def _preflight_file(path: Path, limits: ArchiveLimits) -> None:
    """Bound archive bytes and entry metadata before ZipFile expands the index."""
    with open(path, "rb") as raw:
        file_size = os.fstat(raw.fileno()).st_size
        if file_size > limits.max_archive_bytes:
            raise PackageIssue(
                "PKG007",
                "archive size exceeds max-archive-bytes: "
                f"{_size(file_size)} > {_size(limits.max_archive_bytes)}",
            )
        count = _declared_entry_count(raw, file_size)
        if count is not None and count > limits.max_entries:
            raise PackageIssue(
                "PKG007",
                "archive entry count exceeds max-entries before the central "
                f"directory is loaded: {count} > {limits.max_entries}",
            )


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
    _preflight_file(package, limits)
    with zipfile.ZipFile(package) as archive:
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
    _preflight_file(package, limits)
    with zipfile.ZipFile(package) as archive:
        return [info.filename for info in validate_infos(archive.infolist(), limits)]
