#!/usr/bin/env python3
"""PKG010 across every WordprocessingML package here and in the public corpora.

For every file, this runs the checker and keeps its PKG010 and INT001
findings. Separately, it reads the package without the checker: every
relationship from the main document whose type PKG010 knows, and the content
type `[Content_Types].xml` declares for its target. The two must name the same
parts, and the inventory shows what producers actually declare for each
relationship type.

The repository's files are the ones git tracks or would track (`tmp/` and
`.venv/` are ignored). Public files are the DOCX, DOCM, DOTX and DOTM under
the clones of `research/realworld_scan.py fetch`.

    python research/content_type_scan.py --public ~/ooxml-corpora \
        --output evidence/docx-content-types/results.json

To show that nothing else changed, run another checker's source over the same
files with `--checker-src DIR --findings OTHER.json`, then pass
`--compare-with OTHER.json`: every finding except PKG010 must be identical.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import platform
import posixpath
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = (".docx", ".docm", ".dotx", ".dotm")
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
WP = "application/vnd.openxmlformats-officedocument.wordprocessingml."
MAIN = WP + "document.main+xml"
STRICT = "{http://purl.oclc.org/ooxml/wordprocessingml/main}document"


def _checker(src: Path):
    sys.path.insert(0, str(src))
    import lxml
    import ooxml_integrity
    from ooxml_integrity import check
    try:
        from ooxml_integrity.content_types import RELATED as table
    except ImportError:  # a checker without PKG010: findings only
        table = {}
    digest = hashlib.sha256()
    for path in sorted((src / "ooxml_integrity").glob("*.py")):
        digest.update(path.name.encode() + b"\0" + path.read_bytes())
    meta = {"version": ooxml_integrity.__version__, "source_sha256": digest.hexdigest(),
            "python": platform.python_version(), "lxml": lxml.__version__}
    return check, table, meta


def repository_files() -> list[tuple[str, str, Path]]:
    names = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT, check=True, capture_output=True).stdout.decode().split("\0")
    out = []
    for name in sorted(n for n in names if n.lower().endswith(SUFFIXES)):
        parts = name.split("/")
        group = "/".join(parts[:2]) if parts[0] == "evidence" else parts[0]
        out.append((group, name, ROOT / name))
    return out


def public_files(root: Path) -> list[tuple[str, str, Path]]:
    out = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() in SUFFIXES and path.is_file() and ".git" not in path.parts:
            rel = path.relative_to(root).as_posix()
            out.append((f"public/{rel.split('/')[0]}", f"public/{rel}", path))
    return out


def _parse(blob: bytes):
    from lxml import etree
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    return etree.fromstring(blob, parser)


def _resolve(source: str, target: str) -> str | None:
    path = urlsplit(target).path
    if not path:
        return None
    joined = path.lstrip("/") if path.startswith("/") else posixpath.join(
        posixpath.dirname(source), path)
    resolved = posixpath.normpath(joined)
    return None if resolved.startswith("..") else unquote(resolved)


def inventory(path: Path, table: dict) -> dict:
    """Main-document relationships of PKG010's types and their declared types."""
    with zipfile.ZipFile(path) as z:
        names = {n.lower(): n for n in z.namelist()}
        types = _parse(z.read("[Content_Types].xml"))
        defaults = {d.get("Extension", "").lower(): d.get("ContentType", "")
                    for d in types.findall(CT + "Default")}
        overrides = {unquote(o.get("PartName", "").lstrip("/")).lower(): o.get("ContentType", "")
                     for o in types.findall(CT + "Override")}

        def declared(part: str) -> str | None:
            if part.lower() in overrides:
                return overrides[part.lower()]
            return defaults.get(part.rsplit(".", 1)[-1].lower()) if "." in part else None

        office = [r for r in _parse(z.read("_rels/.rels")).findall(REL + "Relationship")
                  if r.get("Type", "").endswith("/officeDocument")]
        main = _resolve("", office[0].get("Target", "")) if len(office) == 1 else None
        main = names.get((main or "").lower())
        if main is None:
            return {"main": "no single main part", "pairs": []}
        if _parse(z.read(main)).tag == STRICT:
            return {"main": "strict", "pairs": []}
        main_type = declared(main) or "none"
        if main_type.lower() != MAIN:
            return {"main": main_type, "pairs": []}
        rels_name = posixpath.join(posixpath.dirname(main), "_rels",
                                   posixpath.basename(main) + ".rels")
        pairs = []
        if rels_name.lower() in names:
            for rel in _parse(z.read(names[rels_name.lower()])).findall(REL + "Relationship"):
                kind = rel.get("Type", "")
                if kind not in table or rel.get("TargetMode") == "External":
                    continue
                part = names.get((_resolve(main, rel.get("Target", "")) or "").lower())
                if part is None:
                    continue
                pairs.append({"type": kind, "part": part, "declared": declared(part),
                              "expected": table[kind]})
        return {"main": main_type, "pairs": pairs}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--public", type=Path, help="root of the public corpora clones")
    parser.add_argument("--checker-src", type=Path, default=ROOT / "src")
    parser.add_argument("--output", type=Path, help="summary JSON")
    parser.add_argument("--findings", type=Path, help="every finding per file, for --compare-with")
    parser.add_argument("--compare-with", type=Path, help="another run's --findings file")
    args = parser.parse_args(argv)
    check, table, meta = _checker(args.checker_src.resolve())

    files = repository_files() + (public_files(args.public.expanduser()) if args.public else [])
    groups: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    pairs: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    mains: collections.Counter = collections.Counter()
    seen: set[str] = set()
    pkg010, int001, mismatches, everything = [], [], [], {}
    for group, name, path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        counts = groups[group]
        counts["files"] += 1
        findings = check(path)
        everything[name] = sorted([f.code, f.severity.value, f.part, f.where, f.message]
                                  for f in findings)
        reported = sorted(f.part for f in findings if f.code == "PKG010")
        for f in findings:
            if f.code == "PKG010":
                counts["PKG010"] += 1
                pkg010.append({"file": name, "sha256": digest, "part": f.part, **f.extra})
            elif f.code == "INT001":
                int001.append({"file": name, "message": f.message})
        try:
            found = inventory(path, table)
        except Exception as error:  # unreadable packages are other rules' business
            counts["unreadable"] += 1
            found = {"main": f"unreadable: {type(error).__name__}", "pairs": []}
        wrong = sorted(p["part"] for p in found["pairs"]
                       if (p["declared"] or "").split(";")[0].strip().lower()
                       != p["expected"].lower() and p["declared"] is not None)
        if wrong != reported:
            mismatches.append({"file": name, "checker": reported, "inventory": wrong})
        if digest in seen:
            continue
        seen.add(digest)
        counts["distinct"] += 1
        mains[found["main"]] += 1
        for p in found["pairs"]:
            pairs[p["type"]][p["declared"] or "(none)"] += 1
            counts["pairs"] += 1

    result = {
        "checker": meta,
        "public_root": "~/ooxml-corpora (research/realworld_scan.py fetch)" if args.public else None,
        "files": len(files),
        "distinct_files": len(seen),
        "groups": {g: dict(sorted(c.items())) for g, c in sorted(groups.items())},
        "main_part_content_types": dict(mains.most_common()),
        "pairs_by_relationship_type": {
            kind: {"expected": table[kind], "declared": dict(c.most_common())}
            for kind, c in sorted(pairs.items())},
        "PKG010": pkg010,
        "INT001": int001,
        "checker_and_inventory_disagree": mismatches,
    }
    if args.compare_with:
        other = json.loads(args.compare_with.read_text(encoding="utf-8"))
        drop = (lambda rows: [r for r in rows if r[0] != "PKG010"])
        differences = sorted(n for n in set(other["findings"]) | set(everything)
                             if drop(other["findings"].get(n, [])) != drop(everything.get(n, [])))
        result["compared_with"] = {"checker": other["checker"],
                                   "findings_other_than_PKG010_differ_in": differences}
    if args.findings:
        args.findings.write_text(json.dumps({"checker": meta, "findings": everything}))
    text = json.dumps(result, indent=1, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("files", "distinct_files", "groups")}, indent=1))
    print(f"PKG010 {len(pkg010)}: " + ", ".join(p["file"] for p in pkg010))
    print(f"INT001 {len(int001)}; checker vs inventory disagreements {len(mismatches)}")
    if "compared_with" in result:
        print("other findings differ in", len(result["compared_with"]["findings_other_than_PKG010_differ_in"]))
    return 1 if mismatches or int001 else 0


if __name__ == "__main__":
    raise SystemExit(main())
