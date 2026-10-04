"""Exercise the installed distribution, not an editable checkout.

Run with a fresh wheel/sdist installation's Python from this source checkout:
    python research/release_smoke.py --version 0.4.8
No Office, network, or font files are needed for these DOCX/CLI contracts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from importlib import metadata
from pathlib import Path
from zipfile import ZipFile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    import ooxml_integrity

    root = Path(__file__).resolve().parents[1]
    installed = Path(ooxml_integrity.__file__).resolve()
    assert not installed.is_relative_to(root / "src"), "must test an installed distribution"
    assert ooxml_integrity.__version__ == metadata.version("ooxml-integrity") == args.version

    def source_hashes(directory):
        return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in directory.rglob("*.py")}

    assert source_hashes(installed.parent) == source_hashes(root / "src/ooxml_integrity"), (
        "installed Python sources differ from this release checkout"
    )
    source = root / "corpus/base.docx"
    edited = root / "runs/t4_fast_fee/agreement.docx"

    def cli(*values, code=0):
        result = subprocess.run([sys.executable, "-m", "ooxml_integrity", *map(str, values)],
                                capture_output=True, text=True, cwd=root)
        assert result.returncode == code, (values, result.returncode, result.stdout, result.stderr)
        return result

    assert args.version in cli("--version").stdout
    console = Path(sysconfig.get_path("scripts")) / ("ooxml-integrity.exe" if os.name == "nt" else "ooxml-integrity")
    result = subprocess.run([str(console), "--version"], capture_output=True, text=True)
    assert result.returncode == 0 and args.version in result.stdout
    cli("check", source, "--no-config", "--fail-on", "info")
    cli("check", source, "--no-config", "--fail-on", "not-a-severity", code=2)
    report = json.loads(cli("check", edited, "--against", source, "--no-config",
                            "--json", "--coverage", code=1).stdout)
    assert report["version"] == args.version
    assert {"CMT005", "FID001"} <= {f["code"] for f in report["files"][0]["findings"]}
    assert report["files"][0]["coverage"]["schema_version"] == 1

    # Previously missed seeded defects must also fail from the built package.
    # Read static fixtures only: research imports can add checkout/src to sys.path.
    revisions = root / "evidence/docx-revisions"
    for output, original, rule, coverage_id in (
        ("replace-unrelated-insertion", "basic", "FID009", "docx.fidelity.revision-text"),
        ("unwrap-note-insertion", "notes", "FID010", "docx.fidelity.note-revisions"),
    ):
        result = json.loads(cli("check", revisions / f"outputs/{output}.docx", "--against",
                                revisions / f"sources/{original}.docx", "--no-config",
                                "--json", "--coverage", code=1).stdout)["files"][0]
        assert rule in {f["code"] for f in result["findings"]}
        coverage = {item["id"]: item for item in result["coverage"]["items"]}
        assert coverage[coverage_id]["status"] == "checked"
        assert coverage[coverage_id]["count"] > 0

    with tempfile.TemporaryDirectory(prefix="ooxml-release-") as folder:
        work = Path(folder)
        # Synthetic public inputs: exercise the 0.4.3 correction in the actual
        # installation, including a third occurrence that must remain an error.
        for kind, text_tag in (("ins", "t"), ("del", "delText")):
            attrs = 'w:id="9" w:author="Reviewer" w:date="2026-09-20T12:00:00Z"'
            content = (f'<w:{kind} {attrs}><w:r><w:{text_tag}>Tracked paragraph.'
                       f'</w:{text_tag}></w:r></w:{kind}>')
            paragraph = (f'<w:p><w:pPr><w:rPr><w:{kind} {attrs}/></w:rPr></w:pPr>'
                         f'{content}</w:p>')
            for duplicate in (False, True):
                sample = work / f"paragraph-{kind}-{duplicate}.docx"
                with ZipFile(sample, "w") as z:
                    z.writestr("[Content_Types].xml", '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
                      <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
                      <Default Extension="xml" ContentType="application/xml"/>
                      <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
                    </Types>''')
                    z.writestr("_rels/.rels", '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
                    </Relationships>''')
                    extra = f"<w:p>{content}</w:p>" if duplicate else ""
                    z.writestr("word/document.xml",
                               '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                               f'<w:body>{paragraph}{extra}</w:body></w:document>')
                found = json.loads(cli("check", sample, "--no-config", "--json",
                                       code=int(duplicate)).stdout)["files"][0]["findings"]
                assert [f["code"] for f in found] == (["REV001"] if duplicate else [])

        # 0.4.4 corrections, on variants of the reference document.
        with ZipFile(source) as z:
            base = {name: z.read(name) for name in z.namelist()}

        def variant(name, parts):
            path = work / name
            with ZipFile(path, "w") as z:
                for part, data in parts.items():
                    z.writestr(part, data)
            return path

        def found(path, code=0):
            report = json.loads(cli("check", path, "--no-config", "--json", code=code).stdout)
            return [(f["code"], f["severity"]) for f in report["files"][0]["findings"]]

        # The main part is the officeDocument target, whatever its name.
        moved = dict(base)
        moved["word/document22.xml"] = moved.pop("word/document.xml")
        moved["word/_rels/document22.xml.rels"] = moved.pop("word/_rels/document.xml.rels")
        for part, old in (("_rels/.rels", b"word/document.xml"),
                          ("[Content_Types].xml", b"/word/document.xml")):
            assert moved[part].count(old) == 1
            moved[part] = moved[part].replace(old, old.replace(b"document", b"document22"))
        assert found(variant("moved.docx", moved)) == []
        # A malformed part that nothing relates is a warning.
        assert found(variant("dump.docx", {**base, "word/dump.xml": b"not XML"})) == [
            ("XML001", "warn")]
        # Strict Open XML is reported as not checked.
        strict = {}
        for part, data in base.items():
            if part.endswith((".xml", ".rels")):
                data = data.replace(b"http://schemas.openxmlformats.org/wordprocessingml/2006/main",
                                    b"http://purl.oclc.org/ooxml/wordprocessingml/main")
                data = data.replace(b"http://schemas.openxmlformats.org/officeDocument/2006/relationships",
                                    b"http://purl.oclc.org/ooxml/officeDocument/relationships")
            strict[part] = data
        assert found(variant("strict.docx", strict), code=1) == [("PKG009", "error")]
        # A comment anchored only in a header is not orphaned; losing that anchor is.
        stories = root / "evidence/docx-comment-stories"
        assert found(stories / "sources/header-anchor.docx") == []
        assert found(stories / "outputs/header-anchor-lost-anchor.docx", code=1) == [
            ("CMT005", "error")]

        # 0.4.5 corrections. An undefined w:next is INFO; an undefined w:basedOn stays WARN.
        clause = b'<w:name w:val="Clause Body"/><w:basedOn w:val="Normal"/>'
        assert base["word/styles.xml"].count(clause) == 1
        for element, severity in ((b'<w:next w:val="NoSuchStyle"/>', "info"),
                                  (b'<w:basedOn w:val="NoSuchStyle"/>', "warn")):
            styled = clause.replace(b'<w:basedOn w:val="Normal"/>', element)
            styles = base["word/styles.xml"].replace(clause, styled)
            assert found(variant(f"style-{severity}.docx", {**base, "word/styles.xml": styles})) == [
                ("STY002", severity)]
        # A part nested past the parser's depth limit says so instead of "not well-formed".
        deep = b"<a>" * 300 + b"</a>" * 300
        report = json.loads(cli("check", variant("deep.docx", {**base, "word/deep.xml": deep}),
                                "--no-config", "--json").stdout)
        [finding] = report["files"][0]["findings"]
        assert finding["code"] == "XML001" and "safe parser's limit" in finding["message"]
        # Text kept as a new tracked deletion is not a text-volume loss; untracked loss is.
        def minimal(name, body):
            return variant(name, {
                "[Content_Types].xml": '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
                  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
                  <Default Extension="xml" ContentType="application/xml"/>
                  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
                </Types>''',
                "_rels/.rels": '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
                </Relationships>''',
                "word/document.xml": (
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    f"<w:body><w:p>{body}</w:p></w:body></w:document>").encode(),
            })
        rev = 'w:author="Editor" w:date="2026-09-27T00:00:00Z"'
        short = minimal("short.docx", '<w:r><w:t xml:space="preserve">This is an initial document.</w:t></w:r>')
        tracked = minimal("tracked.docx", (
            '<w:r><w:t xml:space="preserve">This is an </w:t></w:r>'
            f'<w:del w:id="1" {rev}><w:r><w:delText>initial document</w:delText></w:r></w:del>'
            f'<w:ins w:id="2" {rev}><w:r><w:t>final contract</w:t></w:r></w:ins>'
            '<w:r><w:t>.</w:t></w:r>'))
        untracked = minimal("untracked.docx", '<w:r><w:t xml:space="preserve">This is an final contract.</w:t></w:r>')

        def compared(edited_path, code=0):
            report = json.loads(cli("check", edited_path, "--against", short, "--no-config",
                                    "--json", code=code).stdout)
            return [(f["code"], f["message"]) for f in report["files"][0]["findings"]]

        assert compared(short) == []
        # A tracked edit loses nothing; FID012 lists the tracked changes it added.
        assert [c for c in compared(tracked) if c[0] != "FID012"] == []
        assert {c[0] for c in compared(tracked)} == {"FID012"}
        assert compared(untracked, code=1) == [
            ("FID003", "text volume fell from 28 to 26 characters (7% of content lost)")]

        # 0.4.6: a tracked edit to note or header text is not a loss; untracked is.
        s2 = root / "evidence/review-history-benchmark/sources"
        report = json.loads(cli("check", s2 / "word-review.docx", "--against",
                                s2 / "review-base.docx", "--no-config", "--json").stdout)
        assert {f["code"] for f in report["files"][0]["findings"]} == {"FID002", "FID012"}
        header_run = b"<w:r><w:t>Reference Agreement - Draft 7</w:t></w:r>"
        assert base["word/header1.xml"].count(header_run) == 1
        for name, run, code, expected in (
            ("header-tracked.docx",
             b'<w:r><w:t xml:space="preserve">Reference Agreement - Draft </w:t></w:r>'
             + f'<w:del w:id="901" {rev}><w:r><w:delText>7</w:delText></w:r></w:del>'
               f'<w:ins w:id="902" {rev}><w:r><w:t>8</w:t></w:r></w:ins>'.encode(), 0,
             [("FID012", "info", "header/default: 1 new tracked insertion by Editor"),
              ("FID012", "info", "header/default: 1 new tracked deletion by Editor")]),
            ("header-untracked.docx", b"<w:r><w:t>Reference Agreement - Draft 8</w:t></w:r>",
             1, [("FID007", "error", None)]),
        ):
            header = base["word/header1.xml"].replace(header_run, run)
            path = variant(name, {**base, "word/header1.xml": header})
            report = json.loads(cli("check", path, "--against", source, "--no-config",
                                    "--json", code=code).stdout)
            assert [(f["code"], f["severity"], f["message"] if f["code"] == "FID012" else None)
                    for f in report["files"][0]["findings"]] == expected

        # 0.4.7: a tracked header edit next to a pending revision is not a loss.
        bench = root / "evidence/review-history-benchmark"
        report = json.loads(cli("check", bench / "captures/reference-1/K7h-S2-tracked.docx",
                                "--against", s2 / "word-review.docx", "--no-config",
                                "--json").stdout)
        assert "FID007" not in {f["code"] for f in report["files"][0]["findings"]}
        # 0.4.7 TXT002: a list label holding an escaped reference warns.
        assert base["word/numbering.xml"].count(b'w:val="&#8226;"') == 1
        escaped = base["word/numbering.xml"].replace(b'w:val="&#8226;"', b'w:val="&amp;#8226;"')
        assert found(variant("escaped-bullet.docx", {**base, "word/numbering.xml": escaped})) == [
            ("TXT002", "warn")]
        # 0.4.7 FID011: words added inside another author's pending insertion warn.
        pending = b"<w:t>The Supplier shall maintain professional indemnity insurance.</w:t>"
        assert base["word/document.xml"].count(pending) == 1
        grown = base["word/document.xml"].replace(
            pending, b"<w:t>The Supplier shall maintain professional indemnity insurance and cyber cover.</w:t>")
        report = json.loads(cli("check", variant("grown-insertion.docx",
                                                 {**base, "word/document.xml": grown}),
                                "--against", source, "--no-config", "--json", "--coverage",
                                code=1).stdout)["files"][0]
        assert [(f["code"], f["severity"]) for f in report["findings"]] == [
            ("FID009", "error"), ("FID011", "warn")]
        coverage = {item["id"]: item for item in report["coverage"]["items"]}
        assert coverage["docx.fidelity.insertion-attribution"]["status"] == "checked"
        # 0.4.7 INT001: a check that raises is an error that names the check.
        from ooxml_integrity.inspector import Inspector, check as inspect

        def check_styles(self):
            raise RuntimeError("synthetic")
        saved = Inspector.CHECKS
        Inspector.CHECKS = tuple(check_styles if c.__name__ == "check_styles" else c
                                 for c in saved)
        try:
            crashed = [f for f in inspect(source) if f.code == "INT001"]
        finally:
            Inspector.CHECKS = saved
        assert len(crashed) == 1 and crashed[0].severity.value == "error"
        assert crashed[0].extra["check"] == "check_styles"

        # 0.4.8: a requested accept/reject passes only when declared; a wrong
        # declaration fails with EXP001.
        resolved = bench / "captures/reference-1/K6-S2-resolve.docx"
        review = s2 / "word-review.docx"
        ins, dele = "FID001:tag=ins,before=2,after=1", "FID001:tag=del,before=2,after=1"
        cli("check", resolved, "--against", review, "--no-config", code=1)
        report = json.loads(cli("check", resolved, "--against", review, "--no-config", "--json",
                                "--expect", ins, "--expect", dele).stdout)["files"][0]
        assert len(report["expected"]) == 2 and not [
            f for f in report["findings"] if f["severity"] == "error"]
        report = json.loads(cli("check", resolved, "--against", review, "--no-config", "--json",
                                "--expect", "FID001:tag=ins,before=2,after=0", "--expect", dele,
                                code=1).stdout)["files"][0]
        assert "EXP001" in {f["code"] for f in report["findings"]}
        declared = work / "expect.toml"
        declared.write_text('[[expect]]\ncode = "FID001"\nreason = "accepted on purpose"\n'
                            'match = { tag = "ins", before = 2, after = 1 }\n'
                            '[[expect]]\ncode = "FID001"\nreason = "rejected on purpose"\n'
                            'match = { tag = "del", before = 2, after = 1 }\n', encoding="utf-8")
        cli("check", resolved, "--against", review, "--config", declared)
        from ooxml_integrity import Expectation, compare as fidelity, expect
        kept, matched = expect(fidelity(review, resolved),
                               [Expectation.parse(ins), Expectation.parse(dele)])
        assert len(matched) == 2 and not [f for f in kept if f.severity.value == "error"]
        baseline = work / "baseline.json"
        cli("check", edited, "--against", source, "--no-config", "--write-baseline", baseline)
        data = json.loads(baseline.read_text())
        assert data["version"] == 2 and data["findings"]
        cli("check", edited, "--against", source, "--no-config", "--baseline", baseline)
        legacy = work / "v1.json"
        legacy.write_text(json.dumps({"version": 1, "findings": {}}), encoding="utf-8")
        rejection = cli("check", edited, "--against", source, "--no-config", "--baseline", legacy, code=2)
        assert "version 1" in rejection.stderr and "--write-baseline" in rejection.stderr
        other = work / "another.docx"
        shutil.copyfile(edited, other)
        cli("check", other, "--against", source, "--no-config", "--baseline", baseline, code=1)
        sarif = work / "report.sarif"
        cli("check", edited, "--against", source, "--no-config", "--sarif", sarif, code=1)
        data = json.loads(sarif.read_text())
        assert data["version"] == "2.1.0"
        assert data["runs"][0]["tool"]["driver"]["version"] == args.version
        assert {"CMT005", "FID001"} <= {r["ruleId"] for r in data["runs"][0]["results"]}

        # Exercise installed TOML parsing and policy, including the new archive key.
        config = work / "policy.toml"
        config.write_text('[severity]\nCMT005 = "off"\nFID001 = "off"\n', encoding="utf-8")
        configured = json.loads(cli("check", edited, "--against", source,
                                    "--config", config, "--json").stdout)
        assert not {"CMT005", "FID001"} & {f["code"] for f in configured["files"][0]["findings"]}
        # An explicit CLI threshold still overrides project configuration.
        config.write_text('fail-on = "info"\n[severity]\nCMT005 = "off"\nFID001 = "off"\n',
                          encoding="utf-8")
        cli("check", edited, "--against", source, "--config", config, code=1)
        cli("check", edited, "--against", source, "--config", config, "--fail-on", "error")
        config.write_text('[archive]\nmax-directory-bytes = 1\n', encoding="utf-8")
        limited = json.loads(cli("check", source, "--config", config, "--json", code=1).stdout)
        assert [f["code"] for f in limited["files"][0]["findings"]] == ["PKG007"]
        config.write_text('unknown-option = true\n', encoding="utf-8")
        cli("check", source, "--config", config, code=2)
    print(f"Installed {args.version}: source-byte parity, REV001 mark/content and third-occurrence controls, "
          "renamed main part, unreferenced malformed part, Strict and comment-story controls, "
          "STY002 next/basedOn, XML001 depth limit, FID003 tracked-deletion controls, "
          "FID006/FID007 tracked note and header edits, "
          "0.4.7 FID007 next to a pending revision, TXT002, FID011 and INT001, "
          "0.4.8 expectations from the CLI, config and API with EXP001, "
          "FID012 tracked additions per story, "
          "FID009/FID010 and their coverage, "
          "both entry points, clean/findings/usage exits, JSON, coverage, "
          "baseline v2, v1 rejection, new-file regression, SARIF, config and archive policy passed")


if __name__ == "__main__":
    main()
