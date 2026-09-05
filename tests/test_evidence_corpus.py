"""The committed beta evidence is a labelled corpus, not a screenshot metric."""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path

import pytest

from research.build_docx_evidence import evaluate


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evidence" / "docx-beta" / "manifest.json"


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    # evaluate() also checks every committed source/output hash and compares the
    # exact actionable finding multiset for all labelled pairs.
    return evaluate(MANIFEST)


def test_beta_evidence_has_the_declared_automated_denominator(manifest):
    assert manifest["source_count"] == 40
    assert manifest["pair_count"] == 170
    assert len(manifest["sources"]) == manifest["source_count"]
    assert len(manifest["pairs"]) == manifest["pair_count"]
    assert collections.Counter(
        source["category"] for source in manifest["sources"]
    ) == {"contract": 7, "report": 6, "letter": 6, "table": 7,
          "multi-section": 7, "review-heavy": 7}
    assert collections.Counter(
        source["producer"]["id"] for source in manifest["sources"]
    ) == {"python-docx": 10, "libreoffice": 10, "word-mac": 10,
          "word-windows": 10}
    assert len({s["sha256"] for s in manifest["sources"]}) == 40
    assert len({p["id"] for p in manifest["pairs"]}) == 170
    assert all(source["synthetic"] for source in manifest["sources"])
    assert not any(source["personal_data"] for source in manifest["sources"])


def test_every_label_and_hash_is_a_regression_gate(metrics):
    assert metrics["sources"] == 40
    assert metrics["pairs"] == 170
    assert metrics["clean_pairs"] == 90
    assert metrics["seeded_defect_pairs"] == 80
    assert metrics["pair_failures"] == []
    assert metrics["error_level"]["precision"] >= 0.95
    assert metrics["error_level"]["recall"] == 1.0
    assert metrics["error_level"] == {"tp": 88, "fp": 0, "fn": 0,
                                      "precision": 1.0, "recall": 1.0}


def test_rule_metrics_are_explicit_about_measured_scope(metrics):
    measured = {
        rule["code"] for rule in metrics["rules"]
        if rule["status"] == "measured"
    }
    assert measured >= {
        "CMT001", "CMT002", "CMT004", "CMT005",
        "FID000", "FID001", "FID003", "FID004", "FID007",
        "REL002", "STY001", "TBL001", "TBL002", "TXT001",
    }
    assert all(
        rule["status"] in {"measured", "not-measured"}
        for rule in metrics["rules"]
    )


def test_missing_external_producers_are_not_presented_as_evidence(manifest):
    gaps = " ".join(manifest["known_evidence_gaps"]).lower()
    assert "no word for windows source" not in gaps
    assert "word online" in gaps
    assert "independently supplied" in gaps
    assert "dual review" in gaps


def test_original_tranche_records_including_all_hashes_and_labels_are_immutable(manifest):
    legacy = {
        "sources": [s for s in manifest["sources"] if s["producer"]["id"] != "word-windows"],
        "pairs": [p for p in manifest["pairs"] if not p["id"].startswith("windows-")],
    }
    assert len(legacy["sources"]) == 30
    assert len(legacy["pairs"]) == 120
    # Canonical JSON of those exact records at 594cb6b, independent of Git
    # availability in a source distribution. evaluate() gates their bytes too.
    assert hashlib.sha256(json.dumps(legacy, sort_keys=True).encode()).hexdigest() == (
        "2e7dfbff4f58fa07d613ad4d6adc6785092ed7e971176bf0ce40006803664b35"
    )


def test_group_denominators_and_legacy_error_results_are_preserved(metrics):
    groups = metrics["groups"]
    for producer, tp in (("python-docx", 23), ("libreoffice", 21), ("word-mac", 21)):
        assert groups[f"producer:{producer}"] == {
            "pairs": 40, "clean_pairs": 20, "tp": tp, "fp": 0, "fn": 0,
            "precision": 1.0, "recall": 1.0,
        }
    assert groups["producer:word-windows"]["tp"] == 23
    assert groups["producer:word-windows"]["pairs"] == 50
    assert groups["kind:word-roundtrip"] == {
        "pairs": 10, "clean_pairs": 10, "tp": 0, "fp": 0, "fn": 0,
        "precision": None, "recall": None,
    }


def test_published_metrics_match_the_immutable_evaluation(metrics):
    assert metrics == json.loads((MANIFEST.parent / "metrics.json").read_text(encoding="utf-8"))
