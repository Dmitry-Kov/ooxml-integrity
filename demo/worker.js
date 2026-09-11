// Module workers are required by Pyodide 314; no application build is needed.
const PYODIDE_VERSION = "314.0.6";
const CHECKER_VERSION = "0.4.1";
const CHECKER_SPEC = `ooxml-integrity==${CHECKER_VERSION}`;
const CDN = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const MAX_BYTES = 25 * 1024 * 1024;
const families = ["Carlito", "Caladea", "LiberationSans", "LiberationSerif", "LiberationMono"];
const styles = ["Regular", "Bold", "Italic", "BoldItalic"];
const progress = (message) => postMessage({ type: "progress", message });

async function getAsset(path, binary = false) {
  const response = await fetch(new URL(path, import.meta.url));
  if (!response.ok) throw new Error(`Could not load ${path}: HTTP ${response.status}`);
  return binary ? new Uint8Array(await response.arrayBuffer()) : response.text();
}

async function initialize() {
  const started = performance.now();
  progress(`Loading Pyodide ${PYODIDE_VERSION} (Python + WebAssembly)…`);
  // Same-origin font downloads overlap the larger Python runtime download.
  const assets = Promise.all([
    getAsset("bridge.py"),
    Promise.all(families.flatMap(family => styles.map(async style => {
      const name = `${family}-${style}.ttf`;
      return [name, await getAsset(`fonts/${name}`, true)];
    }))),
  ]);
  // Attach a rejection handler immediately, even while the CDN is loading.
  assets.catch(() => {});
  const { loadPyodide } = await import(`${CDN}pyodide.mjs`);
  const py = await loadPyodide({ indexURL: CDN });
  progress("Python ready. Loading built-in lxml, fonttools and micropip…");
  await py.loadPackage(["lxml", "fonttools", "micropip"]);
  progress(`Installing ooxml-integrity ${CHECKER_VERSION}…`);
  py.globals.set("_demo_package_spec", CHECKER_SPEC);
  try {
    await py.runPythonAsync('import micropip\nawait micropip.install(_demo_package_spec)');
  } finally { py.globals.delete("_demo_package_spec"); }
  const installed = py.runPython('from importlib.metadata import version\nversion("ooxml-integrity")');
  if (installed !== CHECKER_VERSION) throw new Error(`Expected ooxml-integrity ${CHECKER_VERSION}, installed ${installed}.`);
  progress("Installing 20 OFL font faces into /usr/share/fonts/…");
  const [bridge, fonts] = await assets;
  py.FS.mkdirTree("/usr/share/fonts");
  for (const [name, bytes] of fonts) py.FS.writeFile(`/usr/share/fonts/${name}`, bytes);
  py.FS.mkdirTree("/work/input");
  py.FS.mkdirTree("/work/source");
  py.FS.chdir("/work");
  // Import only after seeding fonts, before any font-directory cache is built.
  await py.runPythonAsync(bridge);
  // Warm the font index and surface a broken runtime before enabling Check.
  const doctor = JSON.parse(py.runPython('dispatch(\'{"action":"doctor"}\')'));
  if (doctor.exit_code !== 0) throw new Error(doctor.human);
  const version = py.runPython("__version__");
  if (version !== installed) throw new Error(`Package version ${installed} does not match module version ${version}.`);
  postMessage({ type: "ready", version, pyodide: PYODIDE_VERSION,
    seconds: (performance.now() - started) / 1000 });
  return py;
}

function filePath(file, directory, source = false) {
  if (!file || !(file.bytes instanceof ArrayBuffer)) throw new Error("No readable file selected.");
  if (file.bytes.byteLength > MAX_BYTES) throw new Error("Demo limit: 25 MiB per file. Use the CLI for larger files.");
  const name = String(file.name).split(/[\\/]/).pop().replace(/[\x00-\x1f\x7f]/g, "_");
  if (!(source ? /\.docx$/i : /\.(docx|pptx)$/i).test(name)) throw new Error("Unsupported file extension.");
  return `${directory}/${name}`;
}

const ready = initialize();
ready.catch(error => postMessage({ type: "fatal",
  error: `Could not start Python. Check your network connection and reload the page.\n\n${error.message || String(error)}` }));
let busy = false;
self.onmessage = async ({ data }) => {
  const { id, action, file, source, coverage } = data;
  if (busy) { postMessage({ type: "error", id, error: "A check is already running." }); return; }
  busy = true;
  const paths = [];
  let py;
  try {
    py = await ready;
    const request = { action, coverage: Boolean(coverage) };
    if (action === "check") {
      request.path = filePath(file, "input");
      if (source && !/\.docx$/i.test(file.name)) throw new Error("Fidelity comparison requires two .docx files.");
      if (source) request.source = filePath(source, "source", true);
      py.FS.writeFile(request.path, new Uint8Array(file.bytes));
      paths.push(request.path);
      if (source) {
        py.FS.writeFile(request.source, new Uint8Array(source.bytes));
        paths.push(request.source);
      }
    }
    // Names and document contents are data, never interpolated into Python code.
    py.globals.set("_demo_request", JSON.stringify(request));
    const result = JSON.parse(py.runPython("dispatch(_demo_request)"));
    postMessage({ type: "result", id, result });
  } catch (error) {
    postMessage({ type: "error", id, error: error.stack || String(error) });
  } finally {
    if (py) {
      for (const path of paths) py.FS.unlink(path);
      py.globals.delete("_demo_request");
    }
    busy = false;
  }
};
