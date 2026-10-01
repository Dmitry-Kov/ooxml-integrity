"""Run one review-history task with docxengine 1.0.0 through its JSON-lines CLI
(python -m docxengine.cli), inside its container only:
    python /in/runner.py /in/spec.json /in/source.docx /out/output.docx
Comment and revision ids come from its own list operations. Prints one JSON line."""
import json
import os
import shutil
import subprocess
import sys
import tempfile


def main(spec_path, source, output):
    spec = json.load(open(spec_path, encoding="utf-8"))
    task, editor = spec["task"], spec["editor"]
    kind, mode, call = task["kind"], task["mode"], task.get("call")
    work = os.path.join(tempfile.mkdtemp(), "source.docx")
    shutil.copyfile(source, work)
    cli = subprocess.Popen([sys.executable, "-m", "docxengine.cli"], stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE, text=True,
                           env={**os.environ, "DOCXENGINE_AUTHOR": editor["author"],
                                "DOCXENGINE_FIXED_DATE": editor["date"]})
    steps = []

    def tool(name, **args):
        cli.stdin.write(json.dumps({"tool": name, "args": args}) + "\n")
        cli.stdin.flush()
        reply = json.loads(cli.stdout.readline())
        steps.append({"tool": name, "error": reply.get("error"), "message": reply.get("message")})
        if "error" in reply:
            raise RuntimeError(f"{name}: {reply['error']}: {reply.get('message')}")
        return reply

    try:
        doc = tool("docx_open", path=work)["doc_id"]
        if kind == "replace":
            tool("docx_replace", doc_id=doc, old=call["old"], new=call["new"],
                 track_changes=mode == "tracked", author=editor["author"])
        elif kind == "comment":
            threads = tool("docx_comment", doc_id=doc, op="list")["comments"]
            parent = [c for c in threads if (c.get("text") or "").strip() == call["reply_to"]]
            if len(parent) != 1:
                raise RuntimeError(f"comment list: {len(parent)} matches for the parent")
            tool("docx_comment", doc_id=doc, op="reply", comment_id=parent[0]["id"],
                 text=call["reply"], author=editor["author"])
            found = tool("docx_search", doc_id=doc, query=call["anchor"]["text"])
            anchors = [m["anchor"] for m in found.get("matches", [])]
            if len(anchors) != 1:
                raise RuntimeError(f"search: {len(anchors)} matches for the anchor phrase")
            tool("docx_comment", doc_id=doc, op="add", anchor=anchors[0], text=call["comment"],
                 author=editor["author"])
        elif kind == "resolve":
            listed = tool("docx_revision", doc_id=doc, op="list")["revisions"]
            for op in ("accept", "reject"):
                for want, who, text in call[op]:
                    hit = [r for r in listed if r["type"] == want and r["author"] == who
                           and (r.get("text") or "").strip() == text.strip()]
                    if len(hit) != 1:
                        raise RuntimeError(f"revision list: {len(hit)} matches for {want} {text!r}")
                    tool("docx_revision", doc_id=doc, op=op, id=hit[0]["id"])
        tool("docx_save", doc_id=doc, path=output)
        return "ok", json.dumps(steps)
    except RuntimeError as error:
        return "rejected", f"{error}; steps: {json.dumps(steps)}"[:3000]
    finally:
        cli.stdin.close()
        cli.wait(timeout=60)


if __name__ == "__main__":
    try:
        status, note = main(*sys.argv[1:4])
    except Exception as error:  # the tool's own failure is a result
        status, note = "error", f"{type(error).__name__}: {error}"
    print(json.dumps({"status": status, "note": note}))
