#!/usr/bin/env python3
"""Replay and summarize frozen boundary captures; never invokes an editor/model."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import docx_boundaries as n
from research import docx_benchmark as b
from research import capture_docx_boundaries_agent as agent


def review():
    result = {'protocol_sha256': b.digest(n.PROTOCOL), 'captures': {}, 'groups': [],
              'agent_scripts': {}, 'agent_errors': {}, 'repetitions': {}}
    saved = {}
    for directory in sorted((n.BASE / 'captures').iterdir()) + [n.BASE / 'agent-local-1']:
        evaluate = agent.evaluate if directory.name == 'agent-local-1' else n.evaluate
        # XML facts use tuples; receipts store JSON arrays. Compare their JSON
        # representation, retaining the frozen evaluator and every original byte.
        data = json.loads(b.json_bytes(evaluate(directory)))
        if data != json.loads((directory / 'evaluation.json').read_text()):
            raise ValueError('Saved evaluation does not replay')
        saved[directory.name] = data
        result['captures'][directory.name] = {'capture_sha256': data['capture_sha256'],
                                               'evaluation_sha256': b.digest(directory / 'evaluation.json')}
        for task in n.TASKS:
            cases = [c for c in data['cases'] if c['task'] == task]
            result['groups'].append({'capture': directory.name, 'adapter': data['adapter'], 'task': task,
                'attempts': len(cases), 'status': dict(Counter(c['status'] for c in cases)),
                'outputs_evaluated': sum(c['protected_content_preserved'] is not None for c in cases),
                'task_completed': sum(c['requested_change_completed'] is True for c in cases),
                'preservation_and_integrity_pass': sum(c['protected_content_preserved'] is True for c in cases),
                'overall_success': sum(c['overall_success'] for c in cases),
                'actionable_findings': dict(Counter(f['code'] for c in cases for f in c.get('actionable_findings', []))),
                'independent_violation_types': dict(Counter(k for c in cases for k,v in c.get('violations',{}).items() if v))})
    for adapter in ('adeu', 'python-docx'):
        left, right = saved[f'{adapter}-1'], saved[f'{adapter}-2']
        keys = ('status', 'requested_change_completed', 'protected_content_preserved', 'normalized_package_sha256',
                'violations', 'checker_findings', 'overall_success')
        mismatch = [x['id'] for x,y in zip(left['cases'],right['cases']) if x['id']!=y['id'] or any(x.get(k)!=y.get(k) for k in keys)]
        prior = json.loads((n.BASE / f'repeat-{adapter}.json').read_text())
        if mismatch != prior['assessment_mismatches']:
            raise ValueError('Repeat comparison drift')
        result['repetitions'][adapter] = prior
    directory = n.BASE / 'agent-local-1'
    receipt = json.loads((directory / 'capture.json').read_text())
    result['agent_input_unchanged'] = all(c['input_unchanged'] for c in receipt['cases'])
    for task in n.TASKS:
        cases = [c for c in receipt['cases'] if c['task']==task]
        result['agent_scripts'][task] = dict(Counter(b.digest(directory/c['id']/'edit.py') for c in cases))
        errors = {}
        for c in cases:
            if c['status'] != 'ok':
                lines = (directory/c['id']/'stderr.txt').read_text().strip().splitlines()
                errors[c['id']] = lines[-1] if lines else c.get('error','No stderr')
        result['agent_errors'][task] = errors
    # Explicit review mapping: duplicate IDs are a protocol-integrity violation;
    # their Word impact and whether REV001 is too strict remain unresolved.
    result['adeu_split_mapping'] = {'observed': 'Two new adjacent deletion fragments share one ID',
        'independent_evidence': 'Raw XML IDs counted by unchanged revision facts, not checker findings',
        'checker': 'REV001 reports that exact repeated ID', 'pre_existing_content_loss_observed': False,
        'word_repair_or_loss_confirmed': False, 'classification': 'Protocol failure; practical impact unresolved'}
    result['agent_save_script_review'] = 'All retained save scripts inspected: Document(input_path) and doc.save(output_path), not a byte copy.'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    result = review()
    if args.write:
        b.save_json(n.BASE/'review.json',result)
    elif result != json.loads((n.BASE/'review.json').read_text()):
        raise ValueError('Review drift')
    print(json.dumps({'attempts':sum(g['attempts'] for g in result['groups']),
                      'overall_success':sum(g['overall_success'] for g in result['groups']),
                      'agent_scripts_per_task':{k:len(v) for k,v in result['agent_scripts'].items()}}))


if __name__ == '__main__':
    main()
