"""Exercise the installed distribution, not an editable checkout.

Run with a fresh wheel/sdist installation's Python from this source checkout:
    python research/release_smoke.py --version 0.4.1
No Office, network, or font files are needed for these DOCX/CLI contracts.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from importlib import metadata
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    import ooxml_integrity

    root = Path(__file__).resolve().parents[1]
    installed = Path(ooxml_integrity.__file__).resolve()
    assert not installed.is_relative_to(root / "src"), "must test an installed distribution"
    assert ooxml_integrity.__version__ == metadata.version("ooxml-integrity") == args.version
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

    with tempfile.TemporaryDirectory(prefix="ooxml-release-") as folder:
        work = Path(folder)
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
    print(f"Installed {args.version}: both entry points, clean/findings/usage exits, JSON, coverage, "
          "baseline v2, v1 rejection, new-file regression, SARIF, config and archive policy passed")


if __name__ == "__main__":
    main()
