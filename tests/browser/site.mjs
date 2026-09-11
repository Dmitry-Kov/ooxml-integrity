import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';

export const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
export const site = resolve(process.env.OOXML_DEMO_DIR || resolve(root, 'demo'));
const worker = readFileSync(resolve(site, 'worker.js'), 'utf8');
export const checkerVersion = worker.match(/^const CHECKER_VERSION = "([^"]+)";$/m)?.[1];
export const pyodideVersion = worker.match(/^const PYODIDE_VERSION = "([^"]+)";$/m)?.[1];
if (!checkerVersion || !pyodideVersion) throw new Error('Missing explicit checker/runtime version');
const previewPath = resolve(site, '_preview.json');
export const preview = existsSync(previewPath) ? JSON.parse(readFileSync(previewPath, 'utf8')) : null;
if (site === resolve(root, 'demo') && (preview || existsSync(resolve(site, '_wheels')))) {
  throw new Error('Test-only preview assets must never be included in the public demo');
}
if (preview && (preview.kind !== 'local-wheel-preview' || preview.version !== checkerVersion)) {
  throw new Error('Preview manifest does not match its worker');
}
export const mode = preview ? 'wheel' : 'release';
if (!preview && !worker.includes('const CHECKER_SPEC = `ooxml-integrity==${CHECKER_VERSION}`;')) {
  throw new Error('Public demo must install the exact released version');
}
export const results = resolve(root, 'tmp/browser-results', mode);
export const metadata = {
  commit: execFileSync('git', ['rev-parse', 'HEAD'], {cwd: root, encoding: 'utf8'}).trim(),
  changedTrackedFiles: execFileSync('git', ['diff', 'HEAD', '--name-only'], {cwd: root, encoding: 'utf8'}).trim().split('\n').filter(Boolean),
  mode, checkerVersion, pyodideVersion, preview,
  pageSha256: Object.fromEntries(['index.html', 'style.css', 'app.js', 'worker.js', 'bridge.py', 'fonts/SHA256SUMS'].map(file => [
    file, createHash('sha256').update(readFileSync(resolve(site, file))).digest('hex'),
  ])),
};
