#!/usr/bin/env python3
"""Version-specific revision-text regression gate; never runs an editor/model.

Historical labels and captures are read-only. An evidence directory declares
baseline corrections and candidate additions to the original finding multisets.
The default directory retains the earlier FID009-only comparison contract.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import platform
import sys

import lxml.etree
import ooxml_integrity

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import docx_benchmark as b
from research import revision_evidence as r
from research import review_fid001_fix

BASE = ROOT/'evidence/docx-revision-text'


def multiset(findings):
    return Counter({(f['code'], f['severity']): f['count'] for f in findings})


def review(*, baseline=False, saved_outputs=False, evidence_dir=BASE):
    evidence_dir = Path(evidence_dir)
    declaration = json.loads((evidence_dir/'expectations.json').read_text())
    manifest = r.BASE/'manifest.json'
    if b.digest(manifest) != declaration['historical_manifest_sha256']:
        raise ValueError('Historical revision manifest drift')
    originals = {c['id']: c for c in json.loads(manifest.read_text())['pairs']}
    additions = declaration['candidate_additions']
    baseline_additions = declaration.get('baseline_additions', {})
    if not (set(additions) | set(baseline_additions)) <= set(originals):
        raise ValueError('Unknown candidate case')
    # This verifies all source/output hashes, original labels and XML oracle.
    current = r.evaluate()
    cases, corrected, remaining = [], [], []
    for case in current['cases']:
        ident = case['id']
        old = originals[ident]
        expected = multiset(old['expected_findings'])
        expected.update(multiset(baseline_additions.get(ident, [])))
        if not baseline:
            expected.update(multiset(additions.get(ident, [])))
        actual = multiset(case['actionable_findings'])
        if actual != expected:
            raise ValueError(f'Finding drift for {ident}: {actual} != {expected}')
        if old.get('known_miss'):
            (corrected if actual else remaining).append(ident)
        cases.append({
            'id': ident, 'cohort': old['cohort'], 'provenance': old['provenance'],
            'intent_correct': case['intent_correct'],
            'source': str((r.BASE/old['source_path']).relative_to(ROOT)),
            'output': str((r.BASE/old['output_path']).relative_to(ROOT)),
            'source_sha256': old['source_sha256'],
            'output_sha256': old['output_sha256'],
            'historical_findings': old['expected_findings'],
            'current_findings': case['actionable_findings'],
        })
    groups = {name: {k:v for k,v in group.items() if k != 'label_mismatches'}
              for name, group in current['groups'].items()}
    imported = Path(ooxml_integrity.__file__).resolve().parent
    result = {
        'scope': 'Re-evaluation of stored pairs; no new editor/model execution',
        'expectation': 'baseline' if baseline else 'candidate',
        'baseline_commit': declaration['baseline_commit'],
        'checker_version': ooxml_integrity.__version__,
        'checker_source_sha256': b.tree_hash(imported),
        'checker_files_sha256': {p.name:b.digest(p) for p in sorted(imported.glob('*.py'))},
        'python': platform.python_version(), 'platform': platform.platform(),
        'lxml': lxml.etree.LXML_VERSION,
        'review_script_sha256': b.digest(__file__),
        'protocol_sha256': b.digest(evidence_dir/'PROTOCOL.md'),
        'expectations_sha256': b.digest(evidence_dir/'expectations.json'),
        'historical_manifest_sha256': b.digest(manifest),
        'oracle_script_sha256': b.digest(r.__file__),
        'pairs': len(cases), 'groups': groups,
        'corrected_known_misses': corrected, 'remaining_known_misses': remaining,
        'cases': cases,
    }
    if saved_outputs:
        saved = review_fid001_fix.review()
        prior_path = review_fid001_fix.BASE/'candidate.json'
        prior = json.loads(prior_path.read_text())
        old = {c['id']: c for c in prior['cases']}
        if {c['id'] for c in saved['cases']} != set(old):
            raise ValueError('Saved output inventory drift')
        for case in saved['cases']:
            for key in ('source_sha256', 'output_sha256', 'after'):
                if case[key] != old[case['id']][key]:
                    raise ValueError(f'Saved output drift: {case["id"]}: {key}')
        if saved['not_evaluated'] != prior['not_evaluated']:
            raise ValueError('Unavailable output inventory drift')
        # The referenced receipt contains every pair's paths, hashes and findings.
        # Its old checker source hash is not the checker imported by this run.
        result['saved_outputs'] = {
            'reference': str(prior_path.relative_to(ROOT)),
            'reference_sha256': b.digest(prior_path),
            'review_script_sha256': b.digest(review_fid001_fix.__file__),
            'historical_receipts_sha256': saved['historical_receipts_sha256'],
            'output_pairs': saved['output_pairs'], 'changed_pairs': [],
            'not_evaluated_no_output': len(saved['not_evaluated']),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--saved-outputs', action='store_true')
    parser.add_argument('--evidence-dir', type=Path, default=BASE,
                        help='Version-specific protocol and expected finding additions')
    parser.add_argument('--output', type=Path, help='Write a new receipt; refuses overwrite')
    args = parser.parse_args()
    result = review(baseline=args.baseline, saved_outputs=args.saved_outputs,
                    evidence_dir=args.evidence_dir)
    if args.output:
        b.save_json(args.output, result)
    print(json.dumps({k:result[k] for k in (
        'expectation', 'pairs', 'groups', 'corrected_known_misses', 'remaining_known_misses'
    )}, indent=2))
    if 'saved_outputs' in result:
        print(json.dumps({k:result['saved_outputs'][k] for k in (
            'output_pairs', 'changed_pairs', 'not_evaluated_no_output'
        )}))


if __name__ == '__main__':
    main()
