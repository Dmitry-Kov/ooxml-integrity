"""The follow-up gate permits exact wording changes, never structural drift."""
from copy import deepcopy
from pathlib import Path

import pytest

from research import review_revision_text as gate

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence/docx-paragraph-revision-ids"


def test_current_saved_outputs_match_declared_diagnostics():
    result = gate.review(saved_outputs=True, evidence_dir=EVIDENCE)
    assert result["saved_outputs"]["output_pairs"] == 168
    assert len(result["saved_outputs"]["changed_pairs"]) == 40
    assert result["saved_outputs"]["not_evaluated_no_output"] == 45


@pytest.mark.parametrize("field,value", [
    ("code", "REV099"), ("severity", "error"), ("message", "Unapproved wording"),
    ("part", "word/another.xml"), ("extra", {"before": 100, "after": 101}),
])
def test_saved_output_gate_rejects_undeclared_drift(monkeypatch, field, value):
    result = deepcopy(gate.review_fid001_fix.review())
    case = next(c for c in result["cases"] if any(f["code"] == "FID002" for f in c["after"]))
    finding = next(f for f in case["after"] if f["code"] == "FID002")
    finding[field] = value
    monkeypatch.setattr(gate.review_fid001_fix, "review", lambda: result)
    with pytest.raises(ValueError, match="Saved output drift"):
        gate.review(saved_outputs=True, evidence_dir=EVIDENCE)


def test_historical_contract_does_not_silently_allow_new_wording():
    old = EVIDENCE.parent / "docx-note-revisions"
    with pytest.raises(ValueError, match="Saved output drift"):
        gate.review(saved_outputs=True, evidence_dir=old)
