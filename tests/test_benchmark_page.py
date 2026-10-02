"""The public results page is generated from the committed benchmark evidence."""
from __future__ import annotations

from research import build_benchmark_page as page


def test_the_results_page_matches_the_evidence():
    assert page.main(['--check']) == 0, 'run research/build_benchmark_page.py'


def test_every_tool_in_the_evaluation_is_on_the_page():
    shown = {adapter for _, members in page.GROUPS for adapter, _, _ in members}
    assert shown == set(page.tally())
