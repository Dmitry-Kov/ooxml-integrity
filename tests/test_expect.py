"""Declared expectations: a requested change is reported as expected, and an
expectation that matches nothing fails the run.

Without them a correct accept/reject or a requested header rewrite fails the
same way as damage does (the benchmark's reference control drew 8 errors on 30
correct edits), and a pipeline learns to switch the rule off.
"""
from __future__ import annotations

import json

import pytest

from conftest import ROOT, run_cli
from ooxml_integrity import ERROR, Expectation, Finding, compare, expect
from ooxml_integrity.policy import ConfigError, Policy, make_baseline

BENCH = ROOT / 'evidence/review-history-benchmark'
S2 = BENCH / 'sources/word-review.docx'
RESOLVED = BENCH / 'captures/reference-1/K6-S2-resolve.docx'
INS = 'FID001:tag=ins,before=2,after=1'
DEL = 'FID001:tag=del,before=2,after=1'


def finding(code='FID001', **extra):
    return Finding(code, ERROR, 'x', part='word/document.xml', extra=extra)


def test_matching_findings_are_expected_and_the_rest_kept():
    found = [finding(tag='ins', before=2, after=1), finding(tag='del', before=2, after=1),
             finding('CMT005')]
    kept, matched = expect(found, [Expectation('fid001', {'tag': 'ins', 'before': '2'},
                                               reason='accepted on purpose')])
    assert [f.code for f in kept] == ['FID001', 'CMT005']
    assert [(f.extra['tag'], why) for f, why in matched] == [
        ('ins', 'FID001 tag=ins before=2: accepted on purpose')]


def test_an_expectation_nothing_matches_is_an_error():
    kept, matched = expect([finding(tag='ins', before=2, after=1)],
                           [Expectation('FID001', {'tag': 'ins', 'after': 0}, reason='r')])
    assert matched == []
    assert [(f.code, f.severity) for f in kept] == [('FID001', ERROR), ('EXP001', ERROR)]
    assert kept[1].extra == {'expected': 'FID001', 'match': {'tag': 'ins', 'after': 0},
                             'reason': 'r'}


def test_attributes_and_missing_keys():
    f = finding(tag='ins')
    assert Expectation('FID001', {'part': 'word/document.xml'}).matches(f)
    assert not Expectation('FID001', {'part': 'word/header1.xml'}).matches(f)
    assert not Expectation('FID001', {'body': 'x'}).matches(f)  # absent key never matches


def test_path_scoping():
    scoped = Expectation('FID001', reason='r', path='out/accepted/*.docx')
    assert expect([], [scoped], 'out/other.docx') == ([], [])
    kept, _ = expect([], [scoped], 'out/accepted/a.docx')
    assert [f.code for f in kept] == ['EXP001']


@pytest.mark.parametrize('spec, code, match', [
    ('FID007', 'FID007', {}),
    ('fid001:tag=ins, before=2,after=1', 'FID001', {'tag': 'ins', 'before': '2', 'after': '1'}),
])
def test_command_line_spec(spec, code, match):
    parsed = Expectation.parse(spec)
    assert (parsed.code, dict(parsed.match)) == (code, match)


@pytest.mark.parametrize('spec', [':tag=ins', 'FID001:tag', 'FID001:=ins'])
def test_malformed_command_line_spec(spec):
    with pytest.raises(ValueError):
        Expectation.parse(spec)


def test_config():
    policy = Policy._from_dict({'expect': [{
        'code': 'FID007', 'path': 'out/*.docx', 'reason': 'the header is rewritten',
        'match': {'story_kind': 'header', 'variant': 'default'}}]})
    (e,) = policy.expectations
    assert (e.code, e.path, dict(e.match)) == (
        'FID007', 'out/*.docx', {'story_kind': 'header', 'variant': 'default'})


@pytest.mark.parametrize('entry, message', [
    ({'code': 'FID007'}, "no 'reason'"),
    ({'code': 'FID007', 'reason': 'r', 'severity': 'off'}, 'unknown key'),
    ({'code': 'FID007', 'reason': 'r', 'match': {'body': ['a']}}, 'single values'),
    ({'reason': 'r'}, "'code'"),
])
def test_config_rejects(entry, message):
    with pytest.raises(ConfigError, match=message):
        Policy._from_dict({'expect': [entry]})


def test_requested_accept_and_reject_pass_only_when_declared():
    assert run_cli('check', str(RESOLVED), '--against', str(S2), '--no-config').returncode == 1
    result = run_cli('check', str(RESOLVED), '--against', str(S2), '--no-config',
                     '--expect', INS, '--expect', DEL, '--json')
    assert result.returncode == 0, result.stdout
    report = json.loads(result.stdout)['files'][0]
    assert [f['code'] for f in report['findings'] if f['severity'] == 'error'] == []
    assert [x['expected_because'] for x in report['expected']] == [
        'FID001 tag=ins before=2 after=1: declared with --expect',
        'FID001 tag=del before=2 after=1: declared with --expect']


def test_a_wrong_count_fails_with_both_the_finding_and_exp001():
    result = run_cli('check', str(RESOLVED), '--against', str(S2), '--no-config', '--json',
                     '--expect', 'FID001:tag=ins,before=2,after=0', '--expect', DEL)
    assert result.returncode == 1
    codes = [f['code'] for f in json.loads(result.stdout)['files'][0]['findings']]
    assert codes.count('FID001') == 1 and 'EXP001' in codes


def test_no_expectations_leave_the_report_unchanged():
    result = run_cli('check', str(RESOLVED), '--against', str(S2), '--no-config', '--json')
    assert 'expected' not in json.loads(result.stdout)['files'][0]


def test_sarif_marks_expected_findings_suppressed(tmp_path):
    sarif = tmp_path / 'out.sarif'
    assert run_cli('check', str(RESOLVED), '--against', str(S2), '--no-config',
                   '--expect', INS, '--expect', DEL, '--sarif', str(sarif)).returncode == 0
    results = json.loads(sarif.read_text())['runs'][0]['results']
    fid001 = [r for r in results if r['ruleId'] == 'FID001']
    assert len(fid001) == 2 and all(r['suppressions'][0]['justification'].startswith('FID001 tag=')
                                    for r in fid001)


def test_a_baseline_never_absorbs_an_unmet_expectation(tmp_path):
    baseline = tmp_path / 'baseline.json'
    assert run_cli('check', str(RESOLVED), '--against', str(S2), '--no-config',
                   '--write-baseline', str(baseline)).returncode == 0
    assert run_cli('check', str(RESOLVED), '--against', str(S2), '--no-config',
                   '--baseline', str(baseline)).returncode == 0
    result = run_cli('check', str(RESOLVED), '--against', str(S2), '--no-config',
                     '--baseline', str(baseline), '--expect', 'FID003')
    assert result.returncode == 1 and 'EXP001' in result.stdout
    doc = make_baseline({'f.docx': [Finding('EXP001', ERROR, 'x')]})
    assert doc['findings'] == {}


def test_usage_error_for_a_malformed_expectation():
    result = run_cli('check', str(RESOLVED), '--no-config', '--expect', 'FID001:tag')
    assert result.returncode == 2 and '--expect' in result.stderr


def test_the_api_works_on_compare_output():
    kept, matched = expect(compare(S2, RESOLVED), [Expectation.parse(INS), Expectation.parse(DEL)])
    assert [f for f in kept if f.severity is ERROR] == [] and len(matched) == 2


def test_an_optional_expectation_allows_without_requiring():
    allowed = Expectation('FID009', {'tag': 'ins'}, reason='r', required=False)
    assert expect([], [allowed]) == ([], [])
    kept, matched = expect([finding('FID009', tag='ins')], [allowed])
    assert kept == [] and len(matched) == 1
    policy = Policy._from_dict({'expect': [{'code': 'FID009', 'reason': 'r', 'required': False}]})
    assert policy.expectations[0].required is False
    with pytest.raises(ConfigError, match='true or false'):
        Policy._from_dict({'expect': [{'code': 'FID009', 'reason': 'r', 'required': 'no'}]})


def test_the_benchmark_expectation_analysis_reproduces(tmp_path):
    from research import review_history_expectations as analysis
    out = tmp_path / 'results.json'
    analysis.main(['--output', str(out)])
    committed = json.loads((BENCH / 'expectations/results.json').read_text())
    again = json.loads(out.read_text())
    assert again['expectations'] == committed['expectations']
    assert again['tracked_expectations'] == committed['tracked_expectations']
    assert again['summary'] == committed['summary']
    for mode in ('with', 'with_tracked'):
        moves = {(r['without']['outcome'], r[mode]['outcome']) for r in again['results']}
        assert ('detected', 'missed') not in moves and ('clean', 'false alarm') not in moves
