"""Run one review-history task with Office-Word-MCP-Server 1.1.11 (its tool
functions, as an MCP client would call them), inside its container only:
    python /in/runner.py /in/spec.json /in/source.docx /out/output.docx
Prints one JSON line."""
import asyncio
import json
import shutil
import sys

from word_document_server.tools import content_tools, format_tools


def main(spec_path, source, output):
    spec = json.load(open(spec_path, encoding="utf-8"))
    task = spec["task"]
    kind, mode, call = task["kind"], task["mode"], task.get("call")
    if kind == "save":
        return "unsupported", "no open-and-save tool; copy_document copies the file"
    if kind == "comment":
        return "unsupported", "comment tools only read comments"
    if kind == "resolve" or mode == "tracked":
        return "unsupported", "no tracked-change tools"
    shutil.copyfile(source, output)
    if spec.get("cell"):
        cell = spec["cell"]
        message = asyncio.run(format_tools.format_table_cell_text(
            output, cell["table"], cell["row"], cell["col"],
            text_content=call["paragraph_current"].replace(call["old"], call["new"])))
    else:
        message = asyncio.run(content_tools.search_and_replace(output, call["old"], call["new"]))
    status = "rejected" if message.startswith(("Failed", "Cannot", "Document")) else "ok"
    return status, message


if __name__ == "__main__":
    try:
        status, note = main(*sys.argv[1:4])
    except Exception as error:  # the tool's own failure is a result
        status, note = "error", f"{type(error).__name__}: {error}"
    print(json.dumps({"status": status, "note": note}))
