"""Run one review-history operation list with adeu's public engine.

Executed inside the adeu container, never on the host:

    /src/.venv/bin/python /bench/review_history_adeu.py OPERATIONS.json SOURCE.docx OUTPUT.docx

OPERATIONS.json holds the author and the adeu operations the host adapter
derived from a declared task. Prints one JSON line: status, adeu's own
statistics or message. Uses only adeu's documented models and engine.
"""
import io
import json
import sys
from importlib import metadata
from pathlib import Path

from adeu.models import AcceptChange, ModifyText, RejectChange, ReplyComment
from adeu.redline.engine import BatchValidationError, RedlineEngine

MODELS = {"modify": ModifyText, "accept": AcceptChange, "reject": RejectChange,
          "reply": ReplyComment}


def main(spec_path, source_path, output_path):
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    engine = RedlineEngine(io.BytesIO(Path(source_path).read_bytes()), author=spec["author"])
    stats = None
    if spec["operations"]:
        changes = [MODELS[op["type"]](**op) for op in spec["operations"]]
        try:
            stats = engine.process_batch(changes, partial=False)
        except BatchValidationError as error:
            return {"status": "rejected", "note": str(error)}
        if stats.get("failed"):
            return {"status": "rejected", "note": json.dumps(stats.get("failed"), default=str)}
    Path(output_path).write_bytes(engine.save_to_stream().getvalue())
    return {"status": "ok", "note": json.dumps({k: stats.get(k) for k in (
        "actions_applied", "edits_applied")} if stats else {}, default=str),
            "adeu": metadata.version("adeu")}


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:4])))
