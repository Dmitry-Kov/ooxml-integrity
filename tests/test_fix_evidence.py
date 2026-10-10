"""The committed record of `fix` on the repository's DOCX is what fix does now.

Output hashes depend on the zlib that compresses the edited part, and the
runtime versions on the machine, so those are left out of the comparison.
"""
from __future__ import annotations

import json
import zlib

import pytest
from conftest import ROOT

from research import fix_evidence

RESULTS = ROOT / "evidence" / "fix-repairs" / "results.json"


def _stable(record: dict) -> dict:
    out = {k: v for k, v in record.items()
           if k not in ("python", "lxml", "zlib")}
    out["files"] = [{k: v for k, v in f.items() if k != "output_sha256"}
                    for f in record["files"]]
    return out


@pytest.mark.skipif(not (ROOT / "demo/examples").is_dir(),
                    reason="the record covers demo/, which the sdist does not ship")
def test_fix_evidence_is_reproduced():
    committed = json.loads(RESULTS.read_text(encoding="utf-8"))
    current = fix_evidence.evaluate()
    assert _stable(current) == _stable(committed)
    if current["zlib"] == committed["zlib"]:
        assert ([f["output_sha256"] for f in current["files"]]
                == [f["output_sha256"] for f in committed["files"]])


def test_every_repair_was_proved_and_every_refusal_has_a_reason():
    committed = json.loads(RESULTS.read_text(encoding="utf-8"))
    for f in committed["files"]:
        assert f["deterministic"], f["paths"]
        if f["status"] == "repaired":
            assert f["verification"]["passed"], f["paths"]
            assert f["verification"]["zip"]["changed"] == ["word/document.xml"]
            # Checked against the source wherever the repository records one.
            expected = [] if f["source"] else None
            assert f["verification"]["against_added"] == expected, f["paths"]
        else:
            assert f["status"] == "nothing-to-repair" and f["refused"]
            assert all(r["reason"] for r in f["refused"])
        if "oracle" in f:
            assert f["oracle"]["before"] == f["oracle"]["after"]
    assert zlib.ZLIB_RUNTIME_VERSION  # recorded, so a changed hash can be traced
