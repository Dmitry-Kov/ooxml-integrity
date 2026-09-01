"""Config, suppressions, baseline and SARIF.

This is the layer that decides what a project *hears*, so the tests are mostly
about the failure modes of suppression rather than about happy paths: a
suppression that hides more than it was asked to, or a baseline that goes stale
and masks something new, is worse than no suppression at all.
"""
from __future__ import annotations

import json

import pytest
from conftest import read_part, repack, run_cli

from ooxml_integrity import ERROR, INFO, WARN, Finding, Severity
from ooxml_integrity.policy import (
    ConfigError, Ignore, Policy, apply_baseline, fingerprint, make_baseline,
    read_baseline,
)
from ooxml_integrity.sarif import build as build_sarif

DOC = "word/document.xml"


def F(code="PPT006", sev=WARN, where="slide3/A"):
    return Finding(code, sev, f"{code} happened", where=where)


# ------------------------------------------------------------------- config
def write_cfg(tmp_path, body, name=".ooxml-integrity.toml"):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_defaults_when_there_is_no_config(tmp_path):
    pol = Policy.load(start=tmp_path)
    assert pol.fail_on is Severity.ERROR
    assert pol.severity == {} and pol.ignores == []


def test_a_named_config_that_does_not_exist_is_an_error(tmp_path):
    """Falling back to defaults here would let a project think a rule is off."""
    with pytest.raises(ConfigError, match="not found"):
        Policy.load(tmp_path / "nope.toml")


def test_unknown_keys_are_refused(tmp_path):
    cfg = write_cfg(tmp_path, 'fail-on = "warn"\nfailon = "error"\n')
    with pytest.raises(ConfigError, match="unknown key"):
        Policy.load(cfg)


def test_severity_can_be_lowered_raised_or_turned_off(tmp_path):
    cfg = write_cfg(tmp_path, """
        [severity]
        PPT006 = "info"
        FID002 = "error"
        TXT001 = "off"
    """)
    pol = Policy.load(cfg)
    kept, dropped = pol.apply("deck.pptx", [
        F("PPT006", WARN), F("FID002", INFO), F("TXT001", INFO), F("CMT005", ERROR),
    ])
    got = {f.code: f.severity for f in kept}
    assert got == {"PPT006": Severity.INFO, "FID002": Severity.ERROR,
                   "CMT005": Severity.ERROR}
    assert [f.code for f, _ in dropped] == ["TXT001"]
    assert "off" in dropped[0][1]


def test_an_ignore_without_a_reason_is_refused(tmp_path):
    cfg = write_cfg(tmp_path, """
        [[ignore]]
        code = "PPT006"
        path = "decks/**"
    """)
    with pytest.raises(ConfigError, match="no 'reason'"):
        Policy.load(cfg)


def test_ignores_are_scoped_to_their_path(tmp_path):
    cfg = write_cfg(tmp_path, """
        [[ignore]]
        code = "PPT006"
        path = "decks/marketing/**"
        reason = "shapes overlap by design in these"
    """)
    pol = Policy.load(cfg)

    kept, dropped = pol.apply("decks/marketing/q3.pptx", [F("PPT006")])
    assert kept == [] and "by design" in dropped[0][1]

    kept, dropped = pol.apply("decks/legal/q3.pptx", [F("PPT006")])
    assert len(kept) == 1 and dropped == [], (
        "an ignore scoped to one directory must not cover another"
    )


@pytest.mark.parametrize("pattern,path,covered", [
    ("**", "a/b/c.pptx", True),
    ("decks/*.pptx", "decks/a.pptx", True),
    # the case fnmatch alone gets wrong: * must not cross a separator
    ("decks/*.pptx", "decks/sub/a.pptx", False),
    ("decks/**/*.pptx", "decks/sub/a.pptx", True),
    ("decks/", "decks/sub/a.pptx", True),
    ("out/*.docx", "decks/a.docx", False),
])
def test_path_matching_uses_shell_semantics(pattern, path, covered):
    assert Ignore("X", pattern, "r").covers("X", path) is covered


def test_pyproject_section_is_read(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n\n[tool.ooxml-integrity]\nfail-on = "warn"\n',
        encoding="utf-8")
    assert Policy.load(start=tmp_path).fail_on is Severity.WARN


def test_pyproject_without_our_section_is_not_treated_as_config(tmp_path):
    """Almost every Python repo has a pyproject; most say nothing about us."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n', encoding="utf-8")
    pol = Policy.load(start=tmp_path)
    assert pol.source == "" and pol.fail_on is Severity.ERROR


def test_a_standalone_config_wins_over_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ooxml-integrity]\nfail-on = "info"\n', encoding="utf-8")
    write_cfg(tmp_path, 'fail-on = "warn"\n')
    assert Policy.load(start=tmp_path).fail_on is Severity.WARN


# ----------------------------------------------------------------- baseline
def test_baseline_hides_the_recorded_finding_and_nothing_else():
    recorded = [F("CMT005", ERROR, "comment id=1")]
    base = make_baseline({"a.docx": recorded})
    allowance = {k: v for k, v in base["findings"].items()}

    kept, dropped = apply_baseline(
        "a.docx", [F("CMT005", ERROR, "comment id=1"),
                   F("CMT005", ERROR, "comment id=2")], allowance)
    assert [f.where for f in kept] == ["comment id=2"], (
        "a different location is a different finding and must survive"
    )
    assert len(dropped) == 1


def test_baseline_counts_rather_than_sets():
    """Two of the same finding where one was recorded: the second is new."""
    base = make_baseline({"a.pptx": [F()]})
    allowance = dict(base["findings"])
    kept, dropped = apply_baseline("a.pptx", [F(), F()], allowance)
    assert len(kept) == 1 and len(dropped) == 1


def test_fingerprint_ignores_the_message():
    """Messages carry measurements; a baseline keyed on those goes stale."""
    a = Finding("PPT001", ERROR, "text needs 118pt in a 48pt box", "slide1/A")
    b = Finding("PPT001", ERROR, "text needs 121pt in a 48pt box", "slide1/A")
    assert fingerprint("d.pptx", a) == fingerprint("d.pptx", b)


def test_a_missing_baseline_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="--write-baseline"):
        read_baseline(tmp_path / "none.json")


def test_a_file_that_is_not_a_baseline_is_refused(tmp_path):
    p = tmp_path / "b.json"
    p.write_text('{"hello": 1}', encoding="utf-8")
    with pytest.raises(ConfigError, match="not a ooxml-integrity baseline"):
        read_baseline(p)


# -------------------------------------------------------------------- SARIF
def test_sarif_is_shaped_as_the_schema_expects():
    doc = build_sarif({"a.docx": [F("CMT005", ERROR, "comment id=1")]})
    assert doc["version"] == "2.1.0"
    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "ooxml-integrity"
    assert [r["id"] for r in run["tool"]["driver"]["rules"]] == ["CMT005"]
    res = run["results"][0]
    assert res["ruleId"] == "CMT005"
    assert res["level"] == "error"
    loc = res["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert loc == "a.docx"


def test_sarif_severity_maps_to_sarif_levels():
    doc = build_sarif({"a": [F("A", ERROR), F("B", WARN), F("C", INFO)]})
    got = {r["ruleId"]: r["level"] for r in doc["runs"][0]["results"]}
    assert got == {"A": "error", "B": "warning", "C": "note"}


def test_sarif_keeps_suppressed_findings_and_says_why():
    """A report that omits what was hidden cannot be audited."""
    doc = build_sarif({"a": []}, {"a": [(F("PPT006"), "ignore: by design")]})
    res = doc["runs"][0]["results"][0]
    assert res["suppressions"][0]["justification"] == "ignore: by design"


# ---------------------------------------------------------------- end to end
def test_cli_config_lowers_a_rule_and_the_run_passes(tmp_path, base_docx, tmp_docx):
    """The scenario the whole module exists for, exercised through the CLI."""
    doc = read_part(tmp_docx, DOC)
    broken = doc.replace('<w:r><w:commentReference w:id="1"/></w:r>', "")
    target = tmp_path / "edited.docx"
    repack(tmp_docx, target, {DOC: broken.encode()})

    r = run_cli("check", str(target), "--against", str(base_docx),
                "--no-config", "--json")
    assert r.returncode == 1, "a detached comment reference should fail by default"
    codes = sorted({f["code"] for f in json.loads(r.stdout)["files"][0]["findings"]
                    if f["severity"] == "error"})
    assert codes, "nothing to suppress, so this proves nothing"

    # The codes come from the run rather than from my memory of which check
    # fires: an earlier version of this test guessed CMT005 and was wrong.
    cfg = tmp_path / ".ooxml-integrity.toml"
    cfg.write_text("[severity]\n"
                   + "".join(f'{c} = "off"\n' for c in codes),
                   encoding="utf-8")
    r = run_cli("check", str(target), "--against", str(base_docx),
                "--config", str(cfg))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "suppressed by config" in r.stdout

    r = run_cli("check", str(target), "--against", str(base_docx),
                "--config", str(cfg), "--show-suppressed")
    for c in codes:
        assert f"[hidden] {c}" in r.stdout


def test_cli_write_then_use_baseline(tmp_path, base_docx, runs_dir):
    fast = runs_dir / "t4_fast_fee" / "agreement.docx"
    if not fast.exists():
        pytest.skip("agent run output missing")
    base = tmp_path / "b.json"

    r = run_cli("check", str(fast), "--against", str(base_docx),
                "--write-baseline", str(base))
    assert r.returncode == 0 and base.exists()
    assert "recorded as accepted" in r.stdout

    r = run_cli("check", str(fast), "--against", str(base_docx),
                "--baseline", str(base))
    assert r.returncode == 0, r.stdout
    assert "suppressed by baseline" in r.stdout


def test_baseline_is_recorded_before_policy_is_applied(tmp_path, base_docx,
                                                      runs_dir):
    """Otherwise the config gets baked into the baseline invisibly.

    A baseline written from post-policy findings would omit whatever the config
    hid. Change or remove that config later and those findings reappear as
    regressions, blamed on a commit that did not cause them.
    """
    fast = runs_dir / "t4_fast_fee" / "agreement.docx"
    if not fast.exists():
        pytest.skip("agent run output missing")
    cfg = tmp_path / ".ooxml-integrity.toml"
    cfg.write_text('[severity]\nCMT005 = "off"\n', encoding="utf-8")
    base = tmp_path / "b.json"

    run_cli("check", str(fast), "--against", str(base_docx),
            "--config", str(cfg), "--write-baseline", str(base))
    recorded = json.loads(base.read_text())["findings"]
    assert any("CMT005" in k for k in recorded), (
        "the baseline must record what the checks saw, not what config allowed"
    )


def test_cli_writes_sarif(tmp_path, base_docx, runs_dir):
    fast = runs_dir / "t4_fast_fee" / "agreement.docx"
    if not fast.exists():
        pytest.skip("agent run output missing")
    out = tmp_path / "r.sarif"
    r = run_cli("check", str(fast), "--against", str(base_docx),
                "--sarif", str(out))
    assert r.returncode == 1
    doc = json.loads(out.read_text())
    assert doc["version"] == "2.1.0"
    assert any(x["ruleId"] == "CMT005" for x in doc["runs"][0]["results"])


def test_the_previous_config_filename_is_still_read(tmp_path):
    """A rename on our side is not a reason for someone's config to stop working."""
    (tmp_path / ".docx-integrity.toml").write_text(
        'fail-on = "warn"\n', encoding="utf-8")
    pol = Policy.load(start=tmp_path)
    assert pol.fail_on is Severity.WARN
    assert pol.source.endswith(".docx-integrity.toml")


def test_the_new_config_filename_wins_over_the_old_one(tmp_path):
    (tmp_path / ".docx-integrity.toml").write_text(
        'fail-on = "info"\n', encoding="utf-8")
    (tmp_path / ".ooxml-integrity.toml").write_text(
        'fail-on = "warn"\n', encoding="utf-8")
    assert Policy.load(start=tmp_path).fail_on is Severity.WARN


def test_the_previous_pyproject_table_is_still_read(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n\n[tool.docx-integrity]\nfail-on = "warn"\n',
        encoding="utf-8")
    assert Policy.load(start=tmp_path).fail_on is Severity.WARN
