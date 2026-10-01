"""Run one review-history task with docx-mcp 0.7.4 (its DocxDocument class),
inside its container only:
    python /in/runner.py /in/spec.json /in/source.docx /out/output.docx
Paragraphs are addressed by the paraId its own search_text returns; comment,
footnote and revision ids are the w:id values its methods take. Prints one JSON line."""
import json
import shutil
import sys
import tempfile
from pathlib import Path

from docx_mcp.document import DocxDocument


def _para(doc, text):
    hits = [h for h in doc.search_text(text) if h["source"] == "document"]
    if len(hits) != 1:
        raise ValueError(f"search_text found {len(hits)} body paragraphs for {text!r}")
    return hits[0]["paraId"]


def main(spec_path, source, output):
    spec = json.load(open(spec_path, encoding="utf-8"))
    task, editor, ids = spec["task"], spec["editor"], spec.get("ids", {})
    kind, mode, call = task["kind"], task["mode"], task.get("call")
    author = editor["author"]
    if kind == "replace" and call["story"] == "footnotes" and mode == "tracked":
        return "unsupported", "update_footnote has no tracked mode", None
    work = Path(tempfile.mkdtemp()) / "source.docx"
    shutil.copyfile(source, work)
    doc = DocxDocument(str(work))
    doc.open()
    result = None
    if kind == "replace":
        tracked = mode == "tracked"
        if call["story"] == "document":
            result = doc.replace_text(_para(doc, call["old"]), find=call["old"], replace=call["new"],
                                      author=author, tracked=tracked)
        elif call["story"].startswith("header"):
            result = doc.edit_header_footer("header", call["old"], call["new"], author=author,
                                            tracked=tracked)
        else:
            # The new text exactly as declared, including the leading space.
            result = doc.update_footnote(int(ids["footnote"]),
                                         call["paragraph_current"].replace(call["old"], call["new"]))
    elif kind == "comment":
        result = [doc.reply_to_comment(int(ids["reply_to"]), call["reply"], author=author),
                  doc.add_comment(_para(doc, call["anchor"]["text"]), call["comment"], author=author)]
    elif kind == "resolve":
        result = [doc.accept_change(int(i)) for i in ids["accept"]] + [
            doc.reject_change(int(i)) for i in ids["reject"]]
    saved = doc.save(output, backup=False)
    doc.close()
    return "ok", json.dumps({"result": result, "repairs": saved.get("repairs"),
                             "warnings": saved.get("warnings")}, default=str)[:3000], None


if __name__ == "__main__":
    try:
        status, note, _ = main(*sys.argv[1:4])
    except (ValueError, KeyError, LookupError) as error:
        status, note = "rejected", f"{type(error).__name__}: {error}"
    except Exception as error:  # the tool's own failure is a result
        status, note = "error", f"{type(error).__name__}: {error}"
    print(json.dumps({"status": status, "note": note}))
