// Run one review-history task with docx-cli 0.26.0, inside its container only:
//   bun /in/runner.mjs /in/spec.json /in/source.docx /out/output.docx
// Uses docx-cli's public commands; ids (cN, fnN, tcN) come from its own list
// commands, as an agent would read them. Prints one JSON line.
import { copyFileSync, readFileSync } from "node:fs";

const [specPath, sourcePath, outputPath] = process.argv.slice(2);
const spec = JSON.parse(readFileSync(specPath, "utf8"));
const { task, editor } = spec;
const steps = [];

function docx(...args) {
  // The image's working directory belongs to its own user; run from /tmp.
  const run = Bun.spawnSync([process.execPath, "/opt/docx/package/dist/index.js", ...args], {
    cwd: "/tmp",
    env: { ...process.env, DOCX_AUTHOR: editor.author, DOCX_CLI_NOW: editor.date },
  });
  const result = { args, code: run.exitCode, stdout: run.stdout.toString(), stderr: run.stderr.toString() };
  steps.push({ args, code: result.code, stderr: result.stderr.slice(0, 500) });
  if (result.code !== 0) throw Object.assign(new Error(result.stderr || result.stdout), { refused: true });
  return result.stdout;
}

function finish(status, note) {
  console.log(JSON.stringify({ status, note, steps }));
}

try {
  const call = task.call;
  if (task.kind === "save") {
    finish("unsupported", "docx-cli has no open-and-save command; every write is an edit");
    process.exit(0);
  }
  copyFileSync(sourcePath, outputPath);
  const tracked = task.mode === "tracked";
  const author = ["--author", editor.author];
  if (task.kind === "replace") {
    const fullNew = call.paragraph_current.replace(call.old, call.new);
    if (call.story === "document") {
      if (tracked) docx("replace", outputPath, call.old, call.new, "--track", ...author);
      else if (spec.tracking_on) {
        docx("track-changes", "off", outputPath);
        docx("replace", outputPath, call.old, call.new);
        docx("track-changes", "on", outputPath);
      } else docx("replace", outputPath, call.old, call.new);
    } else if (call.story.startsWith("header")) {
      docx("headers", "set", outputPath, "--text", fullNew, ...(tracked ? ["--track", ...author] : []));
    } else if (call.story === "footnotes") {
      const notes = JSON.parse(docx("footnotes", "list", outputPath));
      const note = notes.find((n) => n.text.trim() === call.paragraph_current.trim());
      if (!note) throw Object.assign(new Error("footnote not found in footnotes list"), { refused: true });
      docx("footnotes", "edit", outputPath, "--at", note.id, "--text", fullNew.trim(),
           ...(tracked ? ["--track", ...author] : []));
    } else {
      finish("unsupported", `no docx-cli command edits ${call.story}`);
      process.exit(0);
    }
  } else if (task.kind === "comment") {
    const comments = JSON.parse(docx("comments", "list", outputPath));
    const parent = comments.find((c) => c.text.trim() === call.reply_to);
    if (!parent) throw Object.assign(new Error("comment not found in comments list"), { refused: true });
    docx("comments", "reply", outputPath, "--at", parent.id, "--text", call.reply);
    docx("comments", "add", outputPath, "--anchor", call.anchor.text, "--text", call.comment, ...author);
  } else if (task.kind === "resolve") {
    const changes = JSON.parse(docx("track-changes", "list", outputPath, "--json"));
    const handle = ([kind, who, text]) => {
      const hit = changes.filter((c) => c.kind === kind && c.author === who && c.text.trim() === text.trim());
      if (hit.length !== 1) throw Object.assign(new Error(`${kind} by ${who} '${text}': ${hit.length} matches`), { refused: true });
      return hit[0].id;
    };
    const args = [];
    for (const item of call.accept) args.push("--accept", handle(item));
    for (const item of call.reject) args.push("--reject", handle(item));
    docx("track-changes", "apply", outputPath, ...args);
  }
  finish("ok", "");
} catch (error) {
  finish(error.refused ? "rejected" : "error", String(error.message).slice(0, 2000));
}
