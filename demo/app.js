const $ = (id) => document.getElementById(id);
const MAX_BYTES = 25 * 1024 * 1024;
const selected = { file: null, source: null };
let ready = false;
let busy = false;
let sequence = 0;
let active = null;
const examples = {
  document: { file: "base.docx" },
  deck: { file: "deck.pptx" },
  fidelity: { file: "agreement.docx", source: "base.docx" },
};

function controls() {
  $("check").disabled = !ready || busy || !selected.file;
  $("doctor").disabled = !ready || busy;
  for (const button of document.querySelectorAll("[data-example]")) button.disabled = !ready || busy;
  for (const role of ["file", "source"]) {
    $(`${role}-input`).disabled = busy;
    $(`clear-${role}`).disabled = busy;
  }
  $("coverage").disabled = busy;
  document.querySelector(".results").setAttribute("aria-busy", String(busy));
}

function tab(name, focus = false) {
  for (const format of ["human", "json"]) {
    const current = name === format;
    $(`${format}-tab`).setAttribute("aria-selected", String(current));
    $(`${format}-tab`).tabIndex = current ? 0 : -1;
    $(`${format}-output`).hidden = !current;
  }
  if (focus) $(`${name}-tab`).focus();
}
for (const format of ["human", "json"]) {
  $(`${format}-tab`).addEventListener("click", () => tab(format));
  $(`${format}-tab`).addEventListener("keydown", event => {
    if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      tab(event.key === "Home" ? "human" : event.key === "End" ? "json" : format === "human" ? "json" : "human", true);
    }
  });
}

function showError(error) {
  const message = error instanceof Error ? error.message : String(error);
  $("human-output").textContent = `Error\n\n${message}`;
  $("json-output").textContent = JSON.stringify({ error: message }, null, 2);
  $("result-status").textContent = "Could not complete";
  $("result-status").className = "error";
  tab("human");
}

function validate(file, role) {
  if (!file) throw new Error("Choose a file first.");
  if (!(role === "source" ? /\.docx$/i : /\.(docx|pptx)$/i).test(file.name)) {
    throw new Error(role === "source" ? "The original must be a .docx file." : "Unsupported file: choose a .docx or .pptx file.");
  }
  if (file.size > MAX_BYTES) throw new Error("Demo limit: 25 MiB per file. Use the CLI for larger files.");
}

function select(role, file) {
  selected[role] = file;
  $(`${role}-name`).textContent = file ? file.name : role === "file" ? "Drop a file or browse" : "Add the original for comparison";
  $(`clear-${role}`).hidden = !file;
  if (!file) $(`${role}-input`).value = "";
  controls();
}
for (const role of ["file", "source"]) {
  const input = $(`${role}-input`);
  input.addEventListener("change", () => {
    if (!input.files.length) return;
    try { validate(input.files[0], role); select(role, input.files[0]); }
    catch (error) { select(role, null); showError(error); }
  });
  $(`clear-${role}`).addEventListener("click", () => select(role, null));
  const zone = $(`${role}-zone`);
  zone.addEventListener("dragover", event => { event.preventDefault(); if (!busy) zone.classList.add("dragover"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", event => {
    event.preventDefault(); zone.classList.remove("dragover");
    if (busy) return;
    try {
      if (event.dataTransfer.files.length !== 1) throw new Error("Drop one file per zone.");
      const file = event.dataTransfer.files[0];
      validate(file, role); select(role, file);
    } catch (error) { select(role, null); showError(error); }
  });
}
// Prevent an accidental drop outside a zone from navigating away with the file.
window.addEventListener("dragover", event => event.preventDefault());
window.addEventListener("drop", event => event.preventDefault());

function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({ name: file.name, bytes: reader.result });
    reader.onerror = () => reject(reader.error || new Error(`Could not read ${file.name}`));
    reader.onabort = () => reject(new Error("File reading was cancelled."));
    reader.readAsArrayBuffer(file);
  });
}

let worker;
function request(payload, transfer = []) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    // Terminate a stuck or hostile document check, rather than freezing the UI.
    const timer = setTimeout(() => {
      worker.terminate(); ready = false;
      active = null;
      reject(new Error("Check exceeded 60 seconds. Reload the page to restart Python; use the CLI for this file."));
      $("runtime-status").textContent = "Python stopped — reload to restart";
    }, 60000);
    active = { id, resolve, reject, timer };
    worker.postMessage({ id, ...payload }, transfer);
  });
}

async function perform(action, example = null) {
  if (!ready || busy) throw new Error("Python is not ready or a check is already running.");
  busy = true; controls();
  $("result-status").className = "";
  $("result-status").textContent = example ? "Loading example…" : "Checking locally…";
  $("human-output").textContent = "Running locally in Python…";
  $("json-output").textContent = "{}";
  tab("human");
  const started = performance.now();
  try {
    if (example) {
      if (!Object.hasOwn(examples, example)) throw new Error("Unknown example.");
      const spec = examples[example];
      const load = async name => {
        const response = await fetch(new URL(`examples/${name}`, import.meta.url));
        if (!response.ok) throw new Error(`Could not load example ${name}: HTTP ${response.status}`);
        return new File([await response.blob()], name);
      };
      const [file, source] = await Promise.all([load(spec.file), spec.source ? load(spec.source) : null]);
      select("file", file); select("source", source);
    }
    let payload = { action }, transfer = [];
    if (action === "check") {
      validate(selected.file, "file");
      if (selected.source) {
        validate(selected.source, "source");
        if (!/\.docx$/i.test(selected.file.name)) throw new Error("Fidelity comparison requires two .docx files. Remove the source for PPTX checks.");
      }
      const [file, source] = await Promise.all([readFile(selected.file), selected.source ? readFile(selected.source) : null]);
      payload = { action, file, source, coverage: $("coverage").checked };
      transfer = [file.bytes, ...(source ? [source.bytes] : [])];
    }
    const result = await request(payload, transfer);
    $("human-output").textContent = result.human;
    $("json-output").textContent = JSON.stringify(result.json, null, 2);
    const seconds = ((performance.now() - started) / 1000).toFixed(2);
    $("result-status").textContent = `Exit ${result.exit_code} · ${seconds} s · local`;
    $("result-status").className = result.exit_code ? "error" : "";
    return result;
  } catch (error) {
    showError(error);
    throw error;
  } finally { busy = false; controls(); }
}
// perform has already displayed errors; do not turn them into unhandled promises.
const fromUI = promise => promise.catch(() => {});
$("check").addEventListener("click", () => fromUI(perform("check")));
$("doctor").addEventListener("click", () => fromUI(perform("doctor")));
for (const button of document.querySelectorAll("[data-example]")) {
  button.addEventListener("click", () => fromUI(perform("check", button.dataset.example)));
}

function fatal(message) {
  ready = false; busy = false;
  if (active) { clearTimeout(active.timer); active.reject(new Error(message)); active = null; }
  $("runtime-status").textContent = "Startup failed — reload to retry";
  document.querySelector(".runtime").classList.add("error");
  showError(message); controls();
}
try {
  worker = new Worker(new URL("worker.js", import.meta.url), { type: "module" });
  worker.onerror = event => { event.preventDefault(); fatal(event.message || "Could not start the Python worker. Check your network and reload."); };
  worker.onmessageerror = () => fatal("Could not read the Python worker response.");
  worker.onmessage = ({ data }) => {
    if (data.type === "progress") {
      const line = document.createElement("li"); line.textContent = data.message;
      $("progress").append(line);
    } else if (data.type === "ready") {
      ready = true;
      const message = `Ready in ${data.seconds.toFixed(1)} s · Python runs locally`;
      $("runtime-status").textContent = message;
      const line = document.createElement("li"); line.textContent = message; $("progress").append(line);
      document.querySelector(".runtime").open = false;
      $("version").textContent = `ooxml-integrity ${data.version} · Pyodide ${data.pyodide}`;
      controls();
    } else if (data.type === "fatal") {
      fatal(data.error);
    } else if (active && data.id === active.id) {
      const pending = active; active = null; clearTimeout(pending.timer);
      if (data.type === "error") pending.reject(new Error(data.error));
      else pending.resolve(data.result);
    }
  };
} catch (error) { fatal(error.message); }

// Optional browser-native agent entry point for the same public examples.
// Never expose a tool that reads the user's selected documents or report.
if (document.modelContext?.registerTool) {
  const lifecycle = new AbortController();
  try {
    Promise.resolve(document.modelContext.registerTool({
      name: "run_integrity_example",
      title: "Run a public integrity example",
      description: "Replace the selected files with a public synthetic example and run its check locally. Updates the visible report. Does not inspect previously selected user files. Python must be ready.",
      inputSchema: {
        type: "object", additionalProperties: false,
        properties: { example: { type: "string", enum: ["document", "deck", "fidelity"] } },
        required: ["example"],
      },
      annotations: { readOnlyHint: false, untrustedContentHint: true },
      async execute(input) {
        if (!input || typeof input !== "object" || Object.keys(input).length !== 1 ||
            typeof input.example !== "string" || !Object.hasOwn(examples, input.example)) {
          throw new Error("Choose example: document, deck or fidelity.");
        }
        const result = await perform("check", input.example);
        return { exit_code: result.exit_code, summary: result.json.files[0].summary,
          codes: result.json.files[0].findings.map(finding => finding.code) };
      },
    }, { signal: lifecycle.signal })).catch(error => console.warn("Optional example tool unavailable:", error));
    window.addEventListener("pagehide", () => lifecycle.abort(), { once: true });
  } catch (error) { console.warn("Optional example tool unavailable:", error); }
}
