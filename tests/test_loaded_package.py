"""Tests for PR #2: single-pass LoadedPackage and in-memory PackageSource support."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from lxml import etree

from ooxml_integrity import (
    ERROR,
    ArchiveLimits,
    LoadedPackage,
    PackageIssue,
    check,
    check_pptx,
    compare,
    coverage_for,
    introduced,
)
from ooxml_integrity import archive as archive_mod
from ooxml_integrity import cli
from ooxml_integrity.mcp_server import Server
from ooxml_integrity.xmlutil import split_fallback
from tests.conftest import read_part, repack


class _NamedBytesIO(io.BytesIO):
    def __init__(self, initial_bytes: bytes, name: str) -> None:
        super().__init__(initial_bytes)
        self.name = name


class _NonSeekableStream:
    """Minimal binary stream that declares itself non-seekable."""

    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)

    def seekable(self) -> bool:
        return False

    def read(self, size: int = -1) -> bytes:
        return self._buf.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        raise io.UnsupportedOperation("seek")


def _tuples(findings):
    return [(f.code, f.severity, f.where, f.message) for f in findings]


def _make_edited_docx(base_docx: Path, dst: Path) -> Path:
    """Break a comment anchor and drop a body word so check/compare/introduced all fire."""
    xml = read_part(base_docx, "word/document.xml")
    assert "commentRangeEnd" in xml
    # Remove the first commentRangeEnd (triggers CMT001 + fidelity/comment checks)
    # and alter a literal phrase so fidelity diff also runs.
    tree = etree.fromstring(xml.encode("utf-8"))
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    end = tree.find(f".//{w}commentRangeEnd")
    assert end is not None
    parent = end.getparent()
    assert parent is not None
    parent.remove(end)
    first_t = tree.find(f".//{w}t")
    assert first_t is not None and first_t.text
    first_t.text = first_t.text + " [edited]"
    return repack(base_docx, dst, {"word/document.xml": etree.tostring(tree, xml_declaration=True, encoding="UTF-8")})


def test_open_path_bytes_bytearray_memoryview_and_stream_parity(base_docx: Path) -> None:
    raw = base_docx.read_bytes()
    expected_sha = hashlib.sha256(raw).hexdigest()

    stream = io.BytesIO(raw)
    stream.seek(7)  # non-zero offset must be restored after open()
    named_stream = _NamedBytesIO(raw, "uploaded-contract.docx")

    pkgs = [
        LoadedPackage.open(base_docx),
        LoadedPackage.open(str(base_docx)),
        LoadedPackage.open(raw),
        LoadedPackage.open(bytearray(raw)),
        LoadedPackage.open(memoryview(raw)),
        LoadedPackage.open(stream),
        LoadedPackage.open(named_stream),
    ]

    assert stream.tell() == 7
    assert pkgs[0].path == base_docx
    assert pkgs[1].path == base_docx
    assert pkgs[2].path is None and pkgs[2].label == "<bytes>"
    assert pkgs[5].path is None and pkgs[5].label == "<stream>"
    assert pkgs[6].path is None and pkgs[6].label == "uploaded-contract.docx"

    for pkg in pkgs:
        assert pkg.sha256 == expected_sha
        assert pkg.main == pkgs[0].main
        assert pkg.stories == pkgs[0].stories
        assert pkg.parts == pkgs[0].parts
        assert pkg.is_deck is False
        assert pkg.xml_errors == {}
        assert LoadedPackage.open(pkg) is pkg


def test_non_seekable_stream_fails_closed(base_docx: Path) -> None:
    raw = base_docx.read_bytes()

    with pytest.raises(PackageIssue) as exc_info:
        LoadedPackage.open(_NonSeekableStream(raw))  # type: ignore[arg-type]
    assert exc_info.value.code == "PKG002"

    check_findings = check(_NonSeekableStream(raw))  # type: ignore[arg-type]
    assert [f.code for f in check_findings] == ["PKG002"]
    assert check_findings[0].severity == ERROR

    with pytest.raises(PackageIssue) as cmp_exc:
        compare(base_docx, _NonSeekableStream(raw))  # type: ignore[arg-type]
    assert cmp_exc.value.code == "PKG002"


def test_archive_limits_enforced_on_in_memory_sources(base_docx: Path) -> None:
    raw = base_docx.read_bytes()
    tight = ArchiveLimits(max_archive_bytes=128)

    for source in (raw, bytearray(raw), memoryview(raw), io.BytesIO(raw)):
        with pytest.raises(PackageIssue) as exc_info:
            LoadedPackage.open(source, limits=tight)
        assert exc_info.value.code == "PKG007"

        findings = check(source, limits=tight)
        assert [f.code for f in findings] == ["PKG007"]


def test_in_memory_parity_for_check_compare_coverage_and_introduced(
    base_docx: Path, tmp_path: Path,
) -> None:
    edited_path = _make_edited_docx(base_docx, tmp_path / "edited.docx")
    base_bytes = base_docx.read_bytes()
    edited_bytes = edited_path.read_bytes()

    base_pkg = LoadedPackage.open(base_bytes)
    edited_pkg = LoadedPackage.open(edited_bytes)

    expected_check = _tuples(check(edited_path))
    assert expected_check  # sanity check: we did break something
    assert _tuples(check(edited_bytes)) == expected_check
    assert _tuples(check(bytearray(edited_bytes))) == expected_check
    assert _tuples(check(memoryview(edited_bytes))) == expected_check
    assert _tuples(check(io.BytesIO(edited_bytes))) == expected_check
    assert _tuples(check(edited_pkg)) == expected_check

    expected_cmp = _tuples(compare(base_docx, edited_path))
    assert _tuples(compare(base_bytes, edited_bytes)) == expected_cmp
    assert _tuples(compare(io.BytesIO(base_bytes), io.BytesIO(edited_bytes))) == expected_cmp
    assert _tuples(compare(base_pkg, edited_pkg)) == expected_cmp

    all_findings = check(edited_path) + compare(base_docx, edited_path)
    expected_cov = coverage_for(edited_path, all_findings, source=base_docx).as_dict()
    assert coverage_for(edited_bytes, all_findings, source=base_bytes).as_dict() == expected_cov
    assert coverage_for(edited_pkg, all_findings, source=base_pkg).as_dict() == expected_cov

    expected_new, expected_inh = introduced(all_findings, base_docx)
    new_bytes, inh_bytes = introduced(all_findings, base_bytes)
    new_pkg, inh_pkg = introduced(all_findings, base_pkg)
    assert _tuples(new_bytes) == _tuples(expected_new)
    assert [(_tuples([f])[0], why) for f, why in inh_bytes] == [
        (_tuples([f])[0], why) for f, why in expected_inh
    ]
    assert _tuples(new_pkg) == _tuples(expected_new)
    assert [(_tuples([f])[0], why) for f, why in inh_pkg] == [
        (_tuples([f])[0], why) for f, why in expected_inh
    ]


def test_split_fallback_and_split_tree_do_not_mutate_cached_tree(
    base_docx: Path, tmp_path: Path,
) -> None:
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    mc = "http://schemas.openxmlformats.org/markup-compatibility/2006"
    xml = read_part(base_docx, "word/document.xml")
    tree = etree.fromstring(xml.encode("utf-8"))
    body = tree.find(f"{{{w}}}body")
    assert body is not None

    alt_p = etree.fromstring(
        f'<w:p xmlns:w="{w}" xmlns:mc="{mc}">'
        '<mc:AlternateContent>'
        '<mc:Choice Requires="wps"><w:r><w:t>ChoiceBoxText</w:t></w:r></mc:Choice>'
        '<mc:Fallback><w:r><w:t>FallbackBoxText</w:t></w:r></mc:Fallback>'
        '</mc:AlternateContent>'
        '</w:p>',
    )
    body.insert(0, alt_p)
    ac_docx = repack(
        base_docx,
        tmp_path / "altcontent.docx",
        {"word/document.xml": etree.tostring(tree, xml_declaration=True, encoding="UTF-8")},
    )

    pkg = LoadedPackage.open(ac_docx)
    cached = pkg.tree(pkg.main)
    assert cached is not None
    before_xml = etree.tostring(cached)
    assert b"FallbackBoxText" in before_xml

    # Direct split_fallback must also leave its input untouched.
    direct_primary, direct_fallback = split_fallback(cached)
    assert direct_primary is not cached
    assert direct_fallback is not None
    assert b"ChoiceBoxText" in etree.tostring(direct_primary)
    assert b"FallbackBoxText" not in etree.tostring(direct_primary)
    assert b"FallbackBoxText" in etree.tostring(direct_fallback)
    assert etree.tostring(cached) == before_xml

    # Running split_tree + check + compare + coverage on the same LoadedPackage
    # must never mutate the cached XML tree and must reuse the split cache.
    primary1, fallback1 = pkg.split_tree(pkg.main)
    primary2, fallback2 = pkg.split_tree(pkg.main)
    assert primary1 is primary2
    assert fallback1 is fallback2

    findings = check(pkg) + compare(base_docx, pkg)
    cov = coverage_for(pkg, findings, source=base_docx)
    assert cov.as_dict()["summary"]["checked"] > 0

    after_xml = etree.tostring(cached)
    assert after_xml == before_xml


def test_single_pass_zip_read_cli_and_mcp(
    base_docx: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    edited = _make_edited_docx(base_docx, tmp_path / "edited.docx")

    opens: list[object] = []
    real_open = archive_mod._open_archive_with_stream

    def counting_open(source, limits):
        opens.append(source)
        return real_open(source, limits)

    monkeypatch.setattr(archive_mod, "_open_archive_with_stream", counting_open)

    # CLI check + --against + --coverage + --introduced: 1 read for edited, 1 read for source.
    opens.clear()
    rc = cli.main([
        "check", str(edited), "--against", str(base_docx),
        "--coverage", "--introduced", "--json", "--no-config",
    ])
    capsys.readouterr()
    assert rc in (cli.EXIT_OK, cli.EXIT_FINDINGS)
    assert len(opens) == 2

    # MCP Server compare with introduced=True (always includes coverage): 1 read each.
    opens.clear()
    server = Server(no_config=True)
    result = server.run(
        str(edited), str(base_docx), introduced_arg=True, edited_name="edited",
    )
    assert result["exit_code"] in (cli.EXIT_OK, cli.EXIT_FINDINGS)
    assert len(opens) == 2


def test_single_pass_and_in_memory_check_pptx(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    deck_path = root / "corpus" / "deck.pptx"
    if not deck_path.exists():
        pytest.skip("corpus/deck.pptx missing")

    deck_bytes = deck_path.read_bytes()
    pkg = LoadedPackage.open(deck_bytes)
    assert pkg.is_deck is True
    assert pkg.path is None

    expected = _tuples(check_pptx(deck_path))
    assert _tuples(check_pptx(deck_bytes)) == expected
    assert _tuples(check_pptx(io.BytesIO(deck_bytes))) == expected
    assert _tuples(check_pptx(pkg)) == expected

    opens: list[object] = []
    real_open = archive_mod._open_archive_with_stream

    def counting_open(source, limits):
        opens.append(source)
        return real_open(source, limits)

    monkeypatch.setattr(archive_mod, "_open_archive_with_stream", counting_open)

    # Direct check_pptx(path) must read the ZIP once (shared by PresentationInspector and read_deck).
    opens.clear()
    check_pptx(deck_path)
    assert len(opens) == 1

    # CLI check on .pptx with --coverage must also read the ZIP once.
    opens.clear()
    rc = cli.main(["check", str(deck_path), "--coverage", "--json", "--no-config"])
    capsys.readouterr()
    assert rc in (cli.EXIT_OK, cli.EXIT_FINDINGS)
    assert len(opens) == 1
