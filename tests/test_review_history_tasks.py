"""Task declarations for the review-history benchmark match their generator."""
from __future__ import annotations

import json
import sys

from conftest import ROOT

sys.path.insert(0, str(ROOT))
from research import review_history_tasks as tasks  # noqa: E402

DECLARED = json.loads(tasks.TASKS.read_text(encoding="utf-8"))


def test_tasks_json_is_what_the_generator_computes():
    assert DECLARED == {"status": DECLARED["status"], "editor": tasks.EDITOR,
                        "tasks": json.loads(json.dumps(tasks.declarations()))}


def test_every_declared_edit_changes_its_target_as_its_mode_says():
    replace = [t for t in DECLARED["tasks"] if t["kind"] == "replace"]
    assert len(DECLARED["tasks"]) == 30 and len(replace) == 24
    for task in replace:
        call = task["call"]
        assert call["expected"]["current"] != call["paragraph_current"], task["id"]
        keeps_original = task["mode"] == "tracked" or task["task"] == "K4"
        assert (call["expected"]["original"] == call["paragraph_original"]) == keeps_original, task["id"]
