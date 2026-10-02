"""The wave-2 agent harness: egress allowlist, status, prompt and configuration."""
from __future__ import annotations

import json

import pytest

from conftest import ROOT
from research import review_history_agents as agents
from research import review_history_agents_egress as egress


ALLOWED = set(agents.ALLOWED)


@pytest.mark.parametrize('request_line, host', [
    ('CONNECT api.anthropic.com:443 HTTP/1.1', 'api.anthropic.com'),
    ('CONNECT API.Anthropic.com:443 HTTP/1.1', 'api.anthropic.com'),
    ('CONNECT chatgpt.com:443 HTTP/1.1', 'chatgpt.com'),
    ('CONNECT pypi.org:443 HTTP/1.1', None),
    ('CONNECT files.pythonhosted.org:443 HTTP/1.1', None),
    ('CONNECT api.anthropic.com:80 HTTP/1.1', None),
    ('CONNECT api.anthropic.com.evil.example:443 HTTP/1.1', None),
    ('GET http://api.anthropic.com/ HTTP/1.1', None),
    ('CONNECT api.anthropic.com HTTP/1.1', None),
    ('', None),
])
def test_egress_tunnels_only_to_allowed_hosts_on_443(request_line, host):
    assert egress.permitted(request_line, ALLOWED) == host


def test_no_package_index_or_code_host_is_allowed():
    assert not ALLOWED & {'pypi.org', 'files.pythonhosted.org', 'registry.npmjs.org',
                          'github.com', 'objects.githubusercontent.com'}


@pytest.mark.parametrize('timed_out, package, code, status', [
    (True, True, None, 'timeout'),
    (False, True, 0, 'ok'),
    (False, True, 1, 'ok'),
    (False, False, 0, 'rejected'),
    (False, False, 1, 'error'),
    (False, False, None, 'error'),
])
def test_status(timed_out, package, code, status):
    assert agents._status(timed_out, package, code) == status


def test_every_task_prompt_is_passed_verbatim_inside_the_wrapper():
    tasks = json.loads((ROOT / 'evidence/review-history-benchmark/tasks.json').read_text())
    for task in tasks['tasks']:
        wrapped = agents.PROMPT.format(prompt=task['prompt'])
        assert task['prompt'] in wrapped and 'input.docx' in wrapped and 'output.docx' in wrapped


def test_agents_get_no_web_fetch_and_only_the_relay_for_the_local_model():
    config = agents.OPENCODE_CONFIG
    assert config['permission']['webfetch'] == 'deny'
    assert config['provider']['ollama']['options']['baseURL'] == 'http://ollama.internal:11434/v1'
    assert config['share'] == 'disabled' and config['autoupdate'] is False


def test_containers_are_unprivileged_on_the_internal_network():
    limits = agents.LIMITS
    assert limits[limits.index('--network') + 1] == agents.NETWORK
    assert limits[limits.index('--user') + 1] == '65534:65534'
    assert 'ALL' == limits[limits.index('--cap-drop') + 1]
    assert 'no-new-privileges' in limits


def test_every_declared_agent_has_an_adapter_and_a_pinned_image():
    from research import review_history_adapters
    for name in agents.AGENTS:
        assert name in review_history_adapters.ADAPTERS
        assert agents.IMAGE_IDS[name].startswith('sha256:')


@pytest.mark.parametrize('name, flag, model', [
    ('claude-code', '--model', 'claude-opus-5-5'),
    ('codex', '-m', 'gpt-6.1-sol'),
    ('opencode-qwen', '-m', 'ollama/qwen3.8-64k'),
])
def test_every_agent_pins_its_model(name, flag, model):
    command = agents.AGENTS[name]['command']('PROMPT')
    assert command[command.index(flag) + 1] == model
    assert command.count('PROMPT') == 1


def test_no_agent_gets_a_web_tool():
    claude = agents.AGENTS['claude-code']['command']('PROMPT')
    assert claude[claude.index('--disallowedTools') + 1] == 'WebSearch,WebFetch'
    assert '--search' not in agents.AGENTS['codex']['command']('PROMPT')
    assert agents.OPENCODE_CONFIG['permission']['webfetch'] == 'deny'


def test_kept_agent_records_match_their_receipts():
    import hashlib
    captures = ROOT / 'evidence/review-history-benchmark/captures'
    checked = 0
    for receipt in sorted(captures.glob('*/receipts/*.json')):
        record = json.loads(receipt.read_text())
        if not record['note'].startswith('{"agent"'):
            continue
        note = json.loads(record['note'])
        agent = receipt.parent.parent / 'agent'
        sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()  # noqa: E731
        assert sha(agent / note['transcript']) == note['transcript_sha256'], receipt
        for name, digest in note['files'].items():
            assert sha(agent / f"{record['task']}.files" / name) == digest, (receipt, name)
        checked += 1
    assert checked == 0 or checked >= 30
