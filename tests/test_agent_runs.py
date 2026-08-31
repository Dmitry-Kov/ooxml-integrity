"""
The committed agent-run outputs are a regression fixture.

Six careful runs must stay clean and two fast runs must report exactly the
orphaned comment. If a future check breaks either half, this fails - which is
the point: the careful runs are the precision guard, the fast runs are the
recall guard, and both came from real agents rather than from fixtures I wrote.
"""
from __future__ import annotations

import pytest
from conftest import CAREFUL_RUNS, FAST_RUNS

from docx_integrity import Severity, check, compare


def all_findings(base, path):
    return check(path) + compare(base, path)


@pytest.mark.parametrize("run", CAREFUL_RUNS)
def test_careful_runs_report_nothing_actionable(runs_dir, base_docx, run):
    path = runs_dir / run / "agreement.docx"
    if not path.exists():
        pytest.skip(f"{run} output missing")
    actionable = [f for f in all_findings(base_docx, path)
                  if f.severity >= Severity.WARN]
    assert actionable == [], (
        f"{run} is a correct edit by a real agent; reporting anything here is a "
        f"false positive: {actionable}"
    )


@pytest.mark.parametrize("run", FAST_RUNS)
def test_fast_runs_report_the_orphaned_comment(runs_dir, base_docx, run):
    path = runs_dir / run / "agreement.docx"
    if not path.exists():
        pytest.skip(f"{run} output missing")
    findings = all_findings(base_docx, path)
    codes = {f.code for f in findings}
    assert "CMT005" in codes, "the orphaned reviewer comment must be caught"
    assert "FID001" in codes, "the lost comment anchor must be caught"
    assert any(f.severity is Severity.ERROR for f in findings), (
        "an invisible reviewer note must fail CI at the default threshold"
    )


@pytest.mark.parametrize("run", FAST_RUNS)
def test_fast_runs_are_otherwise_intact(runs_dir, base_docx, run):
    """Only the comment broke. Reporting more would be over-flagging."""
    path = runs_dir / run / "agreement.docx"
    if not path.exists():
        pytest.skip(f"{run} output missing")
    codes = {f.code for f in all_findings(base_docx, path)
             if f.severity >= Severity.WARN}
    assert codes == {"CMT005", "FID001"}, f"unexpected extra findings: {codes}"


def test_the_pair_that_is_the_whole_point(runs_dir, base_docx):
    """Same task, same document. One passes, one fails, nothing else differs."""
    careful = runs_dir / "t2_pres" / "agreement.docx"
    fast = runs_dir / "t4_fast_table" / "agreement.docx"
    if not (careful.exists() and fast.exists()):
        pytest.skip("agent run outputs missing")

    careful_bad = [f for f in all_findings(base_docx, careful)
                   if f.severity >= Severity.WARN]
    fast_bad = [f for f in all_findings(base_docx, fast)
                if f.severity >= Severity.WARN]

    assert careful_bad == []
    assert fast_bad, "the fast run's defect is the finding this project exists for"
