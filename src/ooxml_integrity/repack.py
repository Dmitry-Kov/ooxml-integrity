"""Write a copy of a ZIP package with some members replaced.

Every other member is copied as it is: its local header, compressed bytes
and data descriptor, in the input's order, so a reader that compares the two
packages entry by entry finds the same bytes. Only the central directory's
local-header offsets change. A replaced member keeps its name, compression
method, timestamps, attributes and extra fields; it is compressed again and
gets new sizes and CRC.

Only the layouts the corpora contain are supported: single-disk archives with
stored or deflated members and no ZIP64 fields. Anything else raises
`RepackError` rather than being rewritten approximately.
"""
from __future__ import annotations

import os
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .archive import _CENTRAL_HEADER, _EOCD, _directory_bounds

_LOCAL_HEADER = struct.Struct("<4s5H3L2H")
_STORED, _DEFLATED = 0, 8
_DATA_DESCRIPTOR = 0x08
_ZIP64_EXTRA = 0x0001
#: Info-ZIP Unicode Path: readers that honour it see another member name.
_UNICODE_PATH_EXTRA = 0x7075
#: Byte offsets inside a central directory record.
_CENTRAL_FLAGS, _CENTRAL_CRC, _CENTRAL_OFFSET = 8, 16, 42


class RepackError(ValueError):
    """The package uses a ZIP layout this writer does not copy exactly."""


@dataclass(frozen=True)
class Entry:
    """One member as the input stores it."""

    name: str
    central: bytes      # the central directory record, verbatim
    offset: int         # local header offset in the input
    length: int         # local header + compressed data + data descriptor
    header: bytes       # the local header with its name and extra field
    flags: int
    method: int
    crc: int
    compressed: int
    size: int


def _extra_ids(extra: bytes) -> set[int]:
    ids, pos = set(), 0
    while pos + 4 <= len(extra):
        ident, length = struct.unpack_from("<HH", extra, pos)
        ids.add(ident)
        pos += 4 + length
    return ids


def _entries(raw: BinaryIO, file_size: int) -> tuple[list[Entry], bytes]:
    """The members in central directory order, and the archive comment."""
    offset, size, count = _directory_bounds(raw, file_size)
    raw.seek(offset)
    directory = raw.read(size)
    entries: list[Entry] = []
    pos = 0
    while pos < len(directory):
        fields = _CENTRAL_HEADER.unpack_from(directory, pos)
        record_end = pos + _CENTRAL_HEADER.size + sum(fields[10:13])
        record = directory[pos:record_end]
        name_bytes = record[_CENTRAL_HEADER.size:_CENTRAL_HEADER.size + fields[10]]
        extra = record[_CENTRAL_HEADER.size + fields[10]:
                       _CENTRAL_HEADER.size + fields[10] + fields[11]]
        flags, method, crc, compressed, size_, local = (
            fields[3], fields[4], fields[7], fields[8], fields[9], fields[16])
        name = name_bytes.decode("utf-8" if flags & 0x800 else "cp437")
        if 0xFFFFFFFF in (compressed, size_, local) or _ZIP64_EXTRA in _extra_ids(extra):
            raise RepackError(f"{name}: ZIP64 members are not supported")
        if _UNICODE_PATH_EXTRA in _extra_ids(extra):
            raise RepackError(f"{name}: a Unicode Path extra field gives the member "
                              "a second name")
        if flags & 0x01:
            raise RepackError(f"{name}: encrypted members are not supported")
        raw.seek(local)
        head = raw.read(_LOCAL_HEADER.size)
        if len(head) != _LOCAL_HEADER.size or head[:4] != b"PK\x03\x04":
            raise RepackError(f"{name}: missing local header")
        lf = _LOCAL_HEADER.unpack(head)
        variable = raw.read(lf[9] + lf[10])
        if variable[:lf[9]] != name_bytes:
            raise RepackError(f"{name}: local and central names differ")
        if {_ZIP64_EXTRA, _UNICODE_PATH_EXTRA} & _extra_ids(variable[lf[9]:]):
            raise RepackError(f"{name}: ZIP64 or Unicode Path fields are not supported")
        header = head + variable
        length = len(header) + compressed
        if flags & _DATA_DESCRIPTOR:
            raw.seek(local + length)
            tail = raw.read(16)
            signed = tail[:4] == b"PK\x07\x08"
            body = tail[4:16] if signed else tail[:12]
            if len(body) != 12 or struct.unpack("<3L", body) != (crc, compressed, size_):
                raise RepackError(f"{name}: data descriptor does not match the directory")
            length += 16 if signed else 12
        elif (lf[6], lf[7], lf[8]) != (crc, compressed, size_):
            raise RepackError(f"{name}: local header and directory disagree")
        entries.append(Entry(name, record, local, length, header, flags,
                             method, crc, compressed, size_))
        pos = record_end
    if len(entries) != count:
        raise RepackError("entry count does not match the directory")
    tail_size = min(file_size, _EOCD.size + 65535)
    raw.seek(file_size - tail_size)
    tail = raw.read(tail_size)
    end = tail.rfind(b"PK\x05\x06")
    comment_length = _EOCD.unpack_from(tail, end)[7]
    comment = tail[end + _EOCD.size:end + _EOCD.size + comment_length]
    return entries, comment


def read_entries(path: str | Path) -> list[Entry]:
    """The members of a package as stored, for checking a copy against it."""
    with open(path, "rb") as raw:
        return _entries(raw, os.fstat(raw.fileno()).st_size)[0]


def _compress(data: bytes, method: int, name: str) -> bytes:
    if method == _STORED:
        return data
    if method == _DEFLATED:
        packer = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15)
        return packer.compress(data) + packer.flush()
    raise RepackError(f"{name}: compression method {method} is not supported "
                      "for a changed member")


def repack(source: str | Path, out: BinaryIO, replaced: dict[str, bytes]) -> None:
    """Write `source` to `out`, with the members named in `replaced` replaced."""
    with open(source, "rb") as raw:
        entries, comment = _entries(raw, os.fstat(raw.fileno()).st_size)
        missing = set(replaced) - {e.name for e in entries}
        if missing:
            raise RepackError(f"no such member: {sorted(missing)[0]}")
        # Members are written in the order they are stored, which can differ
        # from the directory's order; the directory keeps its own order.
        written = 0
        records: dict[int, bytearray] = {}
        for index, entry in sorted(enumerate(entries), key=lambda x: x[1].offset):
            central = bytearray(entry.central)
            if entry.name in replaced:
                data = replaced[entry.name]
                packed = _compress(data, entry.method, entry.name)
                crc = zlib.crc32(data) & 0xFFFFFFFF
                # Sizes are known now, so they go in the header, not a descriptor.
                flags = entry.flags & ~_DATA_DESCRIPTOR
                head = bytearray(entry.header)
                struct.pack_into("<H", head, 6, flags)
                struct.pack_into("<3L", head, 14, crc, len(packed), len(data))
                chunk = bytes(head) + packed
                struct.pack_into("<H", central, _CENTRAL_FLAGS, flags)
                struct.pack_into("<3L", central, _CENTRAL_CRC, crc, len(packed), len(data))
            else:
                raw.seek(entry.offset)
                chunk = raw.read(entry.length)
            struct.pack_into("<L", central, _CENTRAL_OFFSET, written)
            records[index] = central
            out.write(chunk)
            written += len(chunk)
        directory = b"".join(bytes(records[i]) for i in range(len(entries)))
        out.write(directory)
        out.write(_EOCD.pack(b"PK\x05\x06", 0, 0, len(entries), len(entries),
                             len(directory), written, len(comment)) + comment)


def differences(source: str | Path, copy: str | Path,
                replaced: set[str]) -> list[str]:
    """How `copy` departs from `source` beyond replacing the named members.

    Unchanged members must have the same stored bytes and the same directory
    record apart from the offset; replaced ones the same name, method,
    timestamps and attributes. Members must be in the same order.
    """
    before, after = read_entries(source), read_entries(copy)
    problems: list[str] = []
    if [e.name for e in before] != [e.name for e in after]:
        return ["the members or their order differ"]
    with open(source, "rb") as a, open(copy, "rb") as b:
        for old, new in zip(before, after):
            if old.name in replaced:
                # name, version, method, time, date; then attributes onwards
                same = (old.central[4:8] == new.central[4:8]
                        and old.central[10:16] == new.central[10:16]
                        and old.central[28:42] == new.central[28:42]
                        and old.central[46:] == new.central[46:]
                        and old.header[4:6] == new.header[4:6]
                        and old.header[8:14] == new.header[8:14]
                        and old.header[26:] == new.header[26:])
                if not same:
                    problems.append(f"{old.name}: header fields other than size and CRC changed")
                continue
            a.seek(old.offset)
            b.seek(new.offset)
            if a.read(old.length) != b.read(new.length):
                problems.append(f"{old.name}: stored bytes differ")
            if old.central[:42] != new.central[:42] or old.central[46:] != new.central[46:]:
                problems.append(f"{old.name}: directory record differs")
    return problems
