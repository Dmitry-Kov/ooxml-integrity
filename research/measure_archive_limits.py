"""Measure bounded package loading on a real file or a synthetic large member."""
from __future__ import annotations

import argparse
import gc
import json
import tempfile
import time
import tracemalloc
import zipfile
from pathlib import Path

from ooxml_integrity.archive import MIB, read_package


def _synthetic(path: Path, size_mib: int) -> None:
    chunk = b"\0" * MIB
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        with archive.open("media/payload.bin", "w") as member:
            for _ in range(size_mib):
                member.write(chunk)


def _measure(path: Path) -> dict[str, int | float | str]:
    gc.collect()
    tracemalloc.start()
    started = time.perf_counter()
    parts = read_package(path)
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "path": str(path),
        "archive_bytes": path.stat().st_size,
        "expanded_bytes": sum(len(value) for value in parts.values()),
        "entries": len(parts),
        "elapsed_seconds": round(elapsed, 6),
        "python_allocation_peak_bytes": peak,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--synthetic-mib", type=int, default=64)
    args = parser.parse_args()

    if args.path is not None:
        print(json.dumps(_measure(args.path), indent=2))
        return

    with tempfile.TemporaryDirectory(prefix="ooxml-integrity-measure-") as tmp:
        path = Path(tmp) / "representative-large.zip"
        _synthetic(path, args.synthetic_mib)
        print(json.dumps(_measure(path), indent=2))


if __name__ == "__main__":
    main()
