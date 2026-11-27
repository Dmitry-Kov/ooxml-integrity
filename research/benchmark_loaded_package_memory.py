"""Measure Python heap peak (`tracemalloc`) on synthetic DOCX files with large media.

Run from the repository root:

    python research/benchmark_loaded_package_memory.py
    python research/benchmark_loaded_package_memory.py --compare main 0b75b15 2bedf23 --out evidence/loaded-package-memory/results.json

Scope:
- Measures Python heap allocations tracked by `tracemalloc` only.
- Native C allocations inside `libxml2` XML trees are not included in
  `tracemalloc` figures.
- Uses synthetic copies of `corpus/base.docx` with an additional uncompressed
  (`ZIP_STORED`) binary member `word/media/large.bin`.
"""
from __future__ import annotations

import argparse
import gc
import io
import json
import platform
import subprocess
import sys
import tempfile
import tracemalloc
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CORPUS_BASE = ROOT / "corpus" / "base.docx"


def _make_docx_with_media(base: Path, dst: Path, media_bytes: int, tag: str) -> Path:
    pattern = bytes(range(256))
    chunk = pattern * (1024 * 1024 // len(pattern))
    blob = chunk * (media_bytes // len(chunk))
    with zipfile.ZipFile(base) as zin:
        items = [(name, zin.read(name)) for name in zin.namelist()]
    with zipfile.ZipFile(dst, "w") as zout:
        for name, data in items:
            if name == "[Content_Types].xml":
                data = data.replace(
                    b"</Types>",
                    b'<Default Extension="bin" ContentType="application/octet-stream"/></Types>',
                )
            elif name == "word/document.xml" and tag != "source":
                data = data.replace(b"Services", f"Services-{tag}".encode("utf-8"), 1)
            zout.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
        zout.writestr("word/media/large.bin", blob, compress_type=zipfile.ZIP_STORED)
    return dst


def _measure(fn) -> dict[str, Any]:
    gc.collect()
    tracemalloc.start()
    try:
        fn()
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {
        "peak_bytes": peak,
        "peak_mib": round(peak / (1024 * 1024), 2),
        "current_bytes": current,
        "current_mib": round(current / (1024 * 1024), 2),
    }


def measure_current_tree(src_dir: Path, corpus_base: Path) -> dict[str, Any]:
    sys.path.insert(0, str(src_dir))
    from lxml import etree

    import ooxml_integrity
    from ooxml_integrity import cli, compare

    with tempfile.TemporaryDirectory(prefix="ooxml-mem-bench-") as td:
        tmp = Path(td)
        src20 = _make_docx_with_media(corpus_base, tmp / "src20.docx", 20 * 1024 * 1024, "source")
        ed20 = _make_docx_with_media(corpus_base, tmp / "ed20.docx", 20 * 1024 * 1024, "ed20")

        compare_20 = _measure(lambda: compare(src20, ed20))

        def cli_one() -> None:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main([
                    "check", str(ed20), "--against", str(src20),
                    "--coverage", "--introduced", "--no-config",
                ])
            if rc not in (0, 1):
                raise RuntimeError(f"unexpected exit code {rc}")

        cli_single_20 = _measure(cli_one)

        src10 = _make_docx_with_media(corpus_base, tmp / "src10.docx", 10 * 1024 * 1024, "source")
        batch = [
            _make_docx_with_media(corpus_base, tmp / f"f{i}.docx", 10 * 1024 * 1024, f"f{i}")
            for i in range(5)
        ]

        def cli_batch() -> None:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main([
                    "check", *[str(p) for p in batch], "--against", str(src10),
                    "--coverage", "--introduced", "--no-config",
                ])
            if rc not in (0, 1):
                raise RuntimeError(f"unexpected exit code {rc}")

        cli_batch_5x10 = _measure(cli_batch)

    return {
        "package_version": ooxml_integrity.__version__,
        "runtime": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "lxml": ".".join(str(x) for x in etree.LXML_VERSION),
            "libxml2": ".".join(str(x) for x in etree.LIBXML_VERSION),
        },
        "scenarios": {
            "compare_20mib_pair": compare_20,
            "cli_check_1x20mib_against_20mib_coverage_introduced": cli_single_20,
            "cli_check_5x10mib_against_10mib_coverage_introduced": cli_batch_5x10,
        },
    }


def _git_rev(ref: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "--short", ref],
        text=True,
    ).strip()


def _git_subject(ref: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "log", "-1", "--format=%s", ref],
        text=True,
    ).strip()


def _measure_ref_subprocess(ref: str) -> dict[str, Any]:
    rev = _git_rev(ref)
    subject = _git_subject(ref)
    with tempfile.TemporaryDirectory(prefix=f"ooxml-ref-{rev}-") as td:
        checkout = Path(td)
        archive = subprocess.Popen(
            ["git", "-C", str(ROOT), "archive", ref, "src"],
            stdout=subprocess.PIPE,
        )
        assert archive.stdout is not None
        subprocess.check_call(["tar", "-x", "-C", str(checkout)], stdin=archive.stdout)
        archive.stdout.close()
        if archive.wait() != 0:
            raise RuntimeError(f"git archive failed for {ref}")

        output = subprocess.check_output(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--single-src",
                str(checkout / "src"),
            ],
            text=True,
        )
        data = json.loads(output)
        return {
            "ref": ref,
            "commit": rev,
            "subject": subject,
            **data,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--single-src",
        type=Path,
        default=None,
        help="measure one unpacked src/ directory in-process and print JSON",
    )
    parser.add_argument(
        "--compare",
        nargs="+",
        metavar="REF",
        default=None,
        help="measure each Git ref in a fresh subprocess and output a combined report",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="optional JSON output file path",
    )
    args = parser.parse_args(argv)

    if args.single_src is not None:
        result = measure_current_tree(args.single_src, CORPUS_BASE)
        print(json.dumps(result, indent=2))
        return 0

    if args.compare:
        runs = [_measure_ref_subprocess(ref) for ref in args.compare]
        report: dict[str, Any] = {
            "metric": "python_heap_peak_tracemalloc",
            "scope_note": (
                "Measures Python heap allocations tracked by tracemalloc only; "
                "native C libxml2 tree allocations are excluded. Inputs are "
                "synthetic copies of corpus/base.docx with uncompressed "
                "(ZIP_STORED) word/media/large.bin members."
            ),
            "fixture_base": "corpus/base.docx",
            "runtime": runs[-1]["runtime"],
            "runs": runs,
        }
    else:
        report = measure_current_tree(ROOT / "src", CORPUS_BASE)

    rendered = json.dumps(report, indent=2) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
