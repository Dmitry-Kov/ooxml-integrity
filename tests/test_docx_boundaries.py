"""Synthetic oracle diagnostics, excluded from real editor results."""
from copy import deepcopy

import pytest
from lxml import etree as E
from research import docx_benchmark as b
from research import docx_boundaries as n
from research import revision_evidence as r


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'source.docx'
    r.write(n.derived_parts('table'), path)
    return path


def write(tmp_path, parts):
    path = tmp_path / 'output.docx'
    r.write(parts, path)
    return path


@pytest.mark.parametrize('profile', r.PROFILES)
@pytest.mark.parametrize('task', n.TASKS)
def test_exact_expected_views(profile, task, tmp_path):
    source = tmp_path / 'source.docx'
    parts = n.derived_parts(profile)
    r.write(parts, source)
    result = n.assess(source, write(tmp_path, parts if task == 'save' else n.expected_parts(parts, task)), task, n.ADAPTERS[1])
    assert result['requested_change_completed']
    assert result['protected_content_preserved'], result['violations']


@pytest.mark.parametrize('task', ['split', 'comment', 'table'])
def test_missing_edit_is_task_failure_without_collateral_loss(source, task):
    result = n.assess(source, source, task, n.ADAPTERS[1])
    assert not result['requested_change_completed']
    assert result['protected_content_preserved']


def tracked(parts, task):
    root = E.fromstring(parts[r.MAIN])
    p = n.target(root, task)
    expected = n.target(E.fromstring(n.expected_parts(parts, task)[r.MAIN]), task)
    ident = 900
    for node, changed in zip(list(p), expected):
        if E.tostring(node) == E.tostring(changed):
            continue
        index = p.index(node)
        p.remove(node)
        for offset, (kind, run) in enumerate((('del', node), ('ins', deepcopy(changed)))):
            wrapper = E.Element(r.W + kind)
            for key, value in {'id': str(ident), 'author': b.AUTHOR, 'date': r.DATE}.items():
                wrapper.set(r.W + key, value)
            ident += 1
            if kind == 'del':
                for t in run.iter(r.W + 't'):
                    t.tag = r.W + 'delText'
            wrapper.append(run)
            p.insert(index + offset, wrapper)
    return {**parts, r.MAIN: r.xml(root)}


@pytest.mark.parametrize('task', ['split', 'comment', 'table'])
def test_fragmented_tracked_views(source, task, tmp_path):
    result = n.assess(source, write(tmp_path, tracked(r.read(source), task)), task, n.ADAPTERS[0])
    assert result['requested_change_completed']
    assert result['protected_content_preserved'], result['violations']


@pytest.mark.parametrize('defect', ['format', 'anchor', 'footnote', 'old_revision', 'cell', 'deleted_format', 'duplicate_id'])
def test_detects_real_protected_changes_even_when_wording_done(source, defect, tmp_path):
    task = 'comment' if defect in ('anchor', 'footnote') else 'split'
    parts = tracked(r.read(source), task) if defect in ('deleted_format', 'duplicate_id') else n.expected_parts(r.read(source), task)
    root = E.fromstring(parts[r.MAIN])
    if defect == 'format':
        props = n.target(root, task).find('w:r/w:rPr', r.NS)
        props.remove(props[0])
    elif defect == 'anchor':
        p = n.target(root, task)
        anchor = p.find('w:commentRangeStart', r.NS)
        p.remove(anchor)
        p.insert(1, anchor)
    elif defect == 'footnote':
        ref = root.find('.//w:footnoteReference', r.NS)
        ref.getparent().remove(ref)
    elif defect == 'old_revision':
        root.find('.//w:ins[@w:id="103"]/w:r/w:t', r.NS).text = 'invented'
    elif defect == 'cell':
        cell = root.find('.//w:tc', r.NS)
        row = cell.getparent()
        row.remove(cell)
        row.append(cell)
    elif defect == 'deleted_format':
        props = n.target(root, task).find('w:del/w:r/w:rPr', r.NS)
        props.remove(props[0])
    else:
        revisions = n.target(root, task).findall('w:ins', r.NS)
        revisions[1].set(r.W + 'id', revisions[0].get(r.W + 'id'))
    parts[r.MAIN] = r.xml(root)
    result = n.assess(source, write(tmp_path, parts), task, n.ADAPTERS[1])
    assert result['requested_change_completed']
    assert not result['protected_content_preserved']


def test_format_only_loss_is_not_measured_by_checker(source, tmp_path):
    parts = n.expected_parts(r.read(source), 'split')
    root = E.fromstring(parts[r.MAIN])
    props = n.target(root, 'split').find('w:r/w:rPr', r.NS)
    props.remove(props[0])
    parts[r.MAIN] = r.xml(root)
    result = n.inspect(source, write(tmp_path, parts), 'split', n.ADAPTERS[1])
    assert result['requested_change_completed']
    assert not result['protected_content_preserved']
    assert result['actionable_findings'] == []


def test_current_text_in_wrong_cell_fails_intent(source, tmp_path):
    parts = r.read(source)
    root = E.fromstring(parts[r.MAIN])
    root.find('.//w:tc/w:p/w:r/w:t', r.NS).text = 'TABLEAFTER'
    parts[r.MAIN] = r.xml(root)
    assert not n.assess(source, write(tmp_path, parts), 'table', n.ADAPTERS[1])['requested_change_completed']


def test_explicit_true_formatting_is_equivalent(source, tmp_path):
    parts = n.expected_parts(r.read(source), 'split')
    root = E.fromstring(parts[r.MAIN])
    for tag in ('b', 'i'):
        n.target(root, 'split').find(f'w:r/w:rPr/w:{tag}', r.NS).set(r.W + 'val', '1')
    parts[r.MAIN] = r.xml(root)
    assert n.assess(source, write(tmp_path, parts), 'split', n.ADAPTERS[1])['protected_content_preserved']


@pytest.mark.frozen_checker
def test_protocol_and_source_derivation_reproduce():
    import json
    data = n.protocol()
    assert data['tasks'] == n.TASKS
    for name, item in data['sources'].items():
        assert r.read(b.ROOT / item['path']) == n.derived_parts(name)
    for directory in sorted((n.BASE / 'captures').iterdir()):
        assert json.loads(b.json_bytes(n.evaluate(directory))) == json.loads((directory / 'evaluation.json').read_text())


@pytest.mark.frozen_checker
def test_local_agent_declares_sixty_attempts_and_exact_requests(monkeypatch, tmp_path):
    import json
    import sys
    from pathlib import Path
    from research import capture_docx_boundaries_agent as agent
    model = {'tag': {'digest': agent.DIGEST}, 'runtime': {'version': '0.30.7'}}
    details = {'version': '3.12.14', 'packages': {'python-docx': '1.2.0', 'lxml': '6.1.3', 'typing_extensions': '4.16.0'}}
    monkeypatch.setattr(agent.a, 'model_record', lambda: model)
    monkeypatch.setattr(agent.a, 'python_details', lambda _: details)
    installation = tmp_path / 'runtime.json'
    installation.write_text('{}')
    directory = tmp_path / 'capture'
    agent.prepare(Path(sys.executable), directory, installation)
    declaration = json.loads((directory / 'declaration.json').read_text())
    assert len(declaration['cases']) == len({c['id'] for c in declaration['cases']}) == 60
    assert len(declaration['requests']) == 12
    for task in n.TASKS:
        for seed in (101, 102, 103):
            request = declaration['requests'][f'{task}-{seed}']
            assert request['options'] == {'temperature': 0, 'num_ctx': 8192, 'num_predict': 4096, 'seed': seed}
            assert request['messages'][1]['content'] == json.loads((n.BASE / 'prompts.json').read_text())[task]
    assert not (directory / 'capture.json').exists()


@pytest.mark.frozen_checker
def test_incomplete_deterministic_inventory_is_rejected(tmp_path):
    import json
    import shutil
    directory = n.BASE / 'captures/python-docx-1'
    receipt = json.loads((directory / 'capture.json').read_text())
    receipt['cases'].pop()
    (tmp_path / 'capture.json').write_text(json.dumps(receipt))
    shutil.copyfile(directory / 'capture-harness.py', tmp_path / 'capture-harness.py')
    with pytest.raises(ValueError, match='Inventory drift'):
        n.evaluate(tmp_path)


@pytest.mark.frozen_checker
def test_completed_agent_capture_replays_if_available():
    import json
    from research import capture_docx_boundaries_agent as agent
    directory = n.BASE / 'agent-local-1'
    if not (directory / 'evaluation.json').exists():
        pytest.skip('Boundary model capture/evaluation still in progress')
    assert agent.evaluate(directory) == json.loads((directory / 'evaluation.json').read_text())
