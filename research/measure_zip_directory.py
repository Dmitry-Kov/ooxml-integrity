"""Measure ZIP index rejection independently of member decompression and RSS.

Run from the repository with its development environment:
    python research/measure_zip_directory.py

Fixtures are generated before tracing. The unguarded ZipFile control shows
the index allocation the former EOCD-count preflight allowed. It does not read
member bodies. No precise memory/time threshold belongs in the unit tests.
"""
from __future__ import annotations

import gc
import json
import platform
import struct
import tempfile
import time
import tracemalloc
import zipfile
from dataclasses import asdict, replace
from pathlib import Path

from ooxml_integrity.archive import DEFAULT_ARCHIVE_LIMITS, PackageIssue, package_names


def _fixture(path, entries, *, forged=False, metadata=False):
    with zipfile.ZipFile(path, "w") as archive:
        for index in range(entries):
            info = zipfile.ZipInfo(f"part-{index:05d}" + ("x" * 60000 if metadata else ""))
            if metadata:
                info.extra = struct.pack("<HH", 0xCAFE, 60000) + b"x" * 60000
                info.comment = b"x" * 60000
            archive.writestr(info, b"")
    data = bytearray(path.read_bytes())
    end = data.rindex(b"PK\x05\x06")
    if forged:
        struct.pack_into("<HH", data, end + 8, 1, 1)
        path.write_bytes(data)
    return {
        "archive_bytes": len(data),
        "directory_bytes": struct.unpack_from("<L", data, end + 12)[0],
        "actual_entries": entries,
        "declared_entries": 1 if forged else entries,
    }


def _measure(path, limits, *, guarded):
    created = 0
    original = zipfile.ZipInfo

    class CountedInfo(original):
        __slots__ = ()

        def __init__(self, *args, **kwargs):
            nonlocal created
            created += 1
            super().__init__(*args, **kwargs)

    gc.collect()
    zipfile.ZipInfo = CountedInfo
    tracemalloc.start()
    started = time.perf_counter()
    try:
        try:
            if guarded:
                package_names(path, limits)
            else:
                with zipfile.ZipFile(path):
                    pass
            result = "accepted"
        except PackageIssue as error:
            result = error.code
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        zipfile.ZipInfo = original
    return {
        "result": result,
        "zipinfo_created": created,
        "elapsed_seconds": round(elapsed, 6),
        "peak_python_bytes": peak,
    }


def main():
    samples = []
    with tempfile.TemporaryDirectory(prefix="ooxml-directory-") as directory:
        path = Path(directory) / "sample.zip"
        _fixture(path, 1)
        # Warm filename codecs and imports before tracing either reader.
        package_names(path)
        for label, entries, forged, metadata in (
            ("boundary-4096", 4096, False, False),
            ("forged-4097", 4097, True, False),
            ("forged-10000", 10000, True, False),
            ("forged-50000", 50000, True, False),
            ("large-metadata", 1, False, True),
        ):
            limits = DEFAULT_ARCHIVE_LIMITS
            if metadata:
                limits = replace(limits, max_directory_bytes=128 * 1024)
            sample = {"case": label, **_fixture(path, entries, forged=forged, metadata=metadata)}
            sample["limits"] = asdict(limits)
            sample["unguarded_zipfile"] = _measure(path, limits, guarded=False)
            sample["package_names"] = _measure(path, limits, guarded=True)
            samples.append(sample)
    print(json.dumps({
        "python": platform.python_version(),
        "platform": platform.platform(),
        "measurement": "tracemalloc peak, excluding fixture generation; no member reads",
        "samples": samples,
    }, indent=2))


if __name__ == "__main__":
    main()
