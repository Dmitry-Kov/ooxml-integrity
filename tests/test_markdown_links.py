"""Relative links and heading anchors in the repository's Markdown must resolve.

The docs are what users and agents read; a moved file or a renamed heading
breaks links silently, and nothing else in the suite notices. The scan covers
tracked files in a checkout. An sdist has no git metadata and leaves some
directories out (demo/), so there every Markdown file it carries is read and a
link into a directory it does not carry is not counted as broken.

The parser is deliberately small. Fenced code blocks and HTML comments are
masked everywhere; inline code is masked for link extraction only, because a
heading like "## `doctor`" still anchors as #doctor. Anchors are GitHub-style
slugs of ATX and setext headings. Indented code blocks are not detected: none
in the repository carries a link, and treating every indented line as code
would hide real links in list continuations. External targets are not fetched;
the suite makes no network calls. Raw HTML links and explicit HTML anchors are
not read; the Markdown here uses none.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable, Iterator, NamedTuple
from urllib.parse import unquote

from conftest import ROOT


class Problem(NamedTuple):
    file: Path
    line: int
    target: str
    reason: str


def _tracked_files() -> list[Path]:
    """Tracked Markdown; empty outside a checkout of this repository (an
    sdist, also one unpacked inside another repository, or no git at all)."""
    try:
        tracked = subprocess.run(["git", "ls-files", "-z", "--", "*.md"],
                                 cwd=ROOT, capture_output=True, text=True)
    except OSError:
        return []
    if tracked.returncode != 0:
        return []
    return sorted(p for p in (ROOT / n for n in tracked.stdout.split("\0") if n)
                  if p.is_file())


def _carried_files() -> list[Path]:
    """Every Markdown file of an unpacked sdist."""
    local = {"tmp", "drafts", "node_modules", "__pycache__"}
    return sorted(p for p in ROOT.rglob("*.md") if p.is_file()
                  and not any(part.startswith(".") or part in local
                              for part in p.relative_to(ROOT).parts[:-1]))


_FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")


def _mask_blocks(text: str) -> str:
    """Blank out fenced code and HTML comments, keeping line structure."""
    lines = text.split("\n")
    fence: tuple[str, int] | None = None
    for i, line in enumerate(lines):
        m = _FENCE.match(line)
        if fence is None:
            if m and not (m.group(2)[0] == "`" and "`" in m.group(3)):
                fence = (m.group(2)[0], len(m.group(2)))
                lines[i] = ""
        else:
            if (m and m.group(2)[0] == fence[0]
                    and len(m.group(2)) >= fence[1] and not m.group(3).strip()):
                fence = None
            lines[i] = ""
    masked = "\n".join(lines)
    return re.sub(r"<!--.*?-->",
                  lambda m: re.sub(r"[^\n]", " ", m.group(0)), masked, flags=re.S)


def _mask_inline(text: str) -> str:
    """Blank out inline code spans, keeping offsets."""
    return re.sub(r"(`+)(.+?)\1", lambda m: " " * len(m.group(0)), text)


def _slug(title: str) -> str:
    """The anchor GitHub gives a heading: rendered text, lowercased, spaces to
    hyphens, punctuation other than hyphens and underscores dropped."""
    title = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", title)
    title = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", title)
    title = re.sub(r"<[^>]*>", "", title)
    title = title.replace("`", "")
    title = re.sub(r"(?<!\w)_|_(?!\w)", "", title)
    title = re.sub(r"[^\w\- ]", "", title.strip().lower())
    return title.replace(" ", "-")


_ATX = re.compile(r"^ {0,3}#{1,6}[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_SETEXT = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
_NOT_PARAGRAPH = re.compile(r"^\s*(?:[#>|]|[-*+][ \t]|\d+[.)][ \t])")


def _heading_slugs(masked: str) -> set[str]:
    slugs: set[str] = set()
    lines = masked.split("\n")
    for i, line in enumerate(lines):
        m = _ATX.match(line)
        if m:
            title = m.group(1)
        elif (line.strip() and not _NOT_PARAGRAPH.match(line)
              and i + 1 < len(lines) and _SETEXT.match(lines[i + 1])):
            title = line.strip()
        else:
            continue
        base = _slug(title)
        slug, n = base, 0
        while slug in slugs:
            n += 1
            slug = f"{base}-{n}"
        slugs.add(slug)
    return slugs


def _inline_targets(text: str) -> Iterator[tuple[int, str]]:
    """(line, target) of every inline link and image, nested ones included."""
    for m in re.finditer(r"\]\(", text):
        i = m.end()
        while i < len(text) and text[i] in " \t":
            i += 1
        if i >= len(text) or text[i] == "\n":
            continue
        if text[i] == "<":
            end = text.find(">", i + 1)
            if end == -1 or "\n" in text[i + 1:end]:
                continue
            target, rest = text[i + 1:end], end + 1
        else:
            depth, j = 0, i
            while j < len(text) and text[j] not in " \t\n":
                if text[j] == "(":
                    depth += 1
                elif text[j] == ")":
                    if depth == 0:
                        break
                    depth -= 1
                j += 1
            target, rest = text[i:j], j
        line_end = text.find("\n", rest)
        if line_end == -1:
            line_end = len(text)
        if ")" not in text[rest:line_end]:
            continue
        yield text.count("\n", 0, m.start()) + 1, target


_DEFINITION = re.compile(r"^ {0,3}\[([^\]]+)\]:[ \t]*(?:<([^>]*)>|(\S+))")


def _reference_targets(text: str) -> Iterator[tuple[int, str]]:
    definitions: dict[str, str] = {}
    for n, line in enumerate(text.split("\n"), 1):
        m = _DEFINITION.match(line)
        if m:
            target = m.group(2) if m.group(2) is not None else m.group(3)
            definitions[m.group(1).strip().lower()] = target
            yield n, target
    for m in re.finditer(r"\[([^\]]+)\]\[([^\]]*)\]", text):
        label = (m.group(2) or m.group(1)).strip().lower()
        if label in definitions:
            yield text.count("\n", 0, m.start()) + 1, definitions[label]
    for m in re.finditer(r"(?<!\])\[([^\]]+)\](?![\[(])", text):
        label = m.group(1).strip().lower()
        if label in definitions:
            yield text.count("\n", 0, m.start()) + 1, definitions[label]


_EXTERNAL = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.-]*:|//)")


def _exists_with_case(base: Path, link: str) -> bool:
    """exists() is case-blind on macOS and Windows; GitHub is not. Only the
    names the link spells are compared, so no directory above it is listed."""
    current = base
    for part in Path(link.lstrip("/")).parts:
        if part in (".", ".."):
            current = (current / part).resolve()
        elif not current.is_dir() or part not in {p.name for p in current.iterdir()}:
            return False
        else:
            current = current / part
    return True


def _left_out(destination: Path, tree: Path) -> bool:
    """The link leads into a top-level directory that `tree` does not carry."""
    try:
        parts = destination.relative_to(tree.resolve()).parts
    except ValueError:
        return False
    return bool(parts) and not (tree / parts[0]).exists()


def _broken(source: Path, target: str, anchors: Callable[[Path], set[str]],
            partial_tree: Path | None = None) -> str | None:
    if not target or _EXTERNAL.match(target):
        return None
    path, _, fragment = target.partition("#")
    path, fragment = unquote(path), unquote(fragment)
    if path:
        base = ROOT if path.startswith("/") else source.parent
        destination = (base / path).resolve()
        if not _exists_with_case(base, path):
            if partial_tree is not None and _left_out(destination, partial_tree):
                return None
            return "no such file or directory"
        if destination.is_dir():
            return None
    else:
        destination = source.resolve()
    if fragment and destination.suffix.lower() == ".md":
        if fragment not in anchors(destination):
            return f"no heading with anchor #{fragment}"
    return None


def _scan(files: list[Path], partial_tree: Path | None = None) -> list[Problem]:
    """Broken links of `files`. With `partial_tree`, the root of a tree known
    to be incomplete, a link into a top-level directory it lacks is skipped."""
    cache: dict[Path, set[str]] = {}

    def anchors(path: Path) -> set[str]:
        if path not in cache:
            cache[path] = _heading_slugs(
                _mask_blocks(path.read_text(encoding="utf-8")))
        return cache[path]

    problems: list[Problem] = []
    for source in files:
        masked = _mask_inline(_mask_blocks(source.read_text(encoding="utf-8")))
        targets = list(_inline_targets(masked)) + list(_reference_targets(masked))
        for line, target in targets:
            reason = _broken(source, target, anchors, partial_tree)
            if reason:
                problems.append(Problem(source, line, target, reason))
    return sorted(set(problems))


def test_relative_links_and_anchors_resolve():
    tracked = _tracked_files()
    files = tracked or _carried_files()
    assert ROOT / "README.md" in files, "the scan found no Markdown to check"
    problems = _scan(files, partial_tree=None if tracked else ROOT)
    report = "\n".join(
        f"{p.file.relative_to(ROOT)}:{p.line}: {p.target} - {p.reason}"
        for p in problems)
    assert not problems, f"{len(problems)} broken Markdown link(s):\n{report}"


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_good_links_pass(tmp_path):
    _write(tmp_path, "b.md", "## Section\n\ntext\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "p.png").write_bytes(b"")
    a = _write(tmp_path, "a.md",
               "# Title\n\n"
               "[file](b.md) [anchor](b.md#section) [same](#title)\n"
               "[dir](sub/) [external](https://example.com/x) [mail](mailto:x@y.z)\n"
               "![img](sub/p.png) [angle](<b.md#section>) [title](b.md \"Title\")\n")
    assert _scan([a]) == []


def test_broken_file_and_anchors_are_reported(tmp_path):
    _write(tmp_path, "b.md", "## Real section\n")
    a = _write(tmp_path, "a.md",
               "# Title\n\n[m](missing.md) [a](b.md#wrong) [s](#wrong)\n")
    problems = _scan([a])
    assert [(p.line, p.target) for p in problems] == [
        (3, "#wrong"), (3, "b.md#wrong"), (3, "missing.md")]
    assert all("no such file" in p.reason or "no heading" in p.reason
               for p in problems)


def test_links_in_code_and_comments_are_not_links(tmp_path):
    a = _write(tmp_path, "a.md",
               "# T\n\n```\n[x](missing.md)\n```\n\n"
               "use `[y](missing.md)` here\n\n<!-- [z](missing.md) -->\n")
    assert _scan([a]) == []


def test_github_style_anchors(tmp_path):
    _write(tmp_path, "b.md",
           "## Fix: `run` now\n\n## Fix: `run` now\n\n## Snake_case stays\n\n"
           "Setext title\n------------\n")
    a = _write(tmp_path, "a.md",
               "[1](b.md#fix-run-now) [2](b.md#fix-run-now-1) "
               "[3](b.md#snake_case-stays) [4](b.md#setext-title)\n")
    assert _scan([a]) == []
    bad = _write(tmp_path, "c.md", "[x](b.md#fix-run-now-2)\n")
    assert len(_scan([bad])) == 1


def test_case_mismatch_is_broken(tmp_path):
    _write(tmp_path, "b.md", "# T\n")
    a = _write(tmp_path, "a.md", "[x](B.md)\n")
    assert len(_scan([a])) == 1


def test_reference_links_resolve(tmp_path):
    a = _write(tmp_path, "a.md",
               "[good][ref] [ignored][undefined]\n\n[ref]: missing.md\n")
    problems = _scan([a])
    assert [p.target for p in problems] == ["missing.md", "missing.md"]
    assert [p.line for p in problems] == [1, 3]


def test_a_partial_tree_does_not_count_links_into_what_it_lacks(tmp_path):
    """An sdist leaves demo/ out; a link there is not a defect of the sdist."""
    _write(tmp_path, "docs/b.md", "# T\n")
    a = _write(tmp_path, "docs/a.md",
               "[demo](../demo/README.md) [gone](missing.md) [ok](b.md)\n")
    assert [p.target for p in _scan([a])] == ["../demo/README.md", "missing.md"]
    assert [p.target for p in _scan([a], partial_tree=tmp_path)] == ["missing.md"]


def test_only_the_names_a_link_spells_are_compared(tmp_path):
    _write(tmp_path, "Docs/b.md", "# T\n")
    a = _write(tmp_path, "notes/a.md", "[up](../Docs/b.md) [wrong](../docs/b.md)\n")
    assert [p.target for p in _scan([a])] == ["../docs/b.md"]
