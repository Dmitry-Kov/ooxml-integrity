import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { checkerVersion, pyodideVersion, site, metadata, mode } from './site.mjs';

const fixture = name => resolve(site, 'examples', name);
const file = (name, original = 'base.docx') => ({
  name, mimeType: 'application/octet-stream', buffer: readFileSync(fixture(original)),
});
const ready = page => expect(page.locator('#runtime-status')).toContainText('Python runs locally', {timeout: 120_000});
async function open(page) {
  await page.goto('/');
  await ready(page);
  await expect(page.locator('#version')).toHaveText(`ooxml-integrity ${checkerVersion} · Pyodide ${pyodideVersion}`);
}
async function json(page) {
  await page.getByRole('tab', {name:'JSON', exact:true}).click();
  return JSON.parse(await page.locator('#json-output').innerText());
}
async function run(page, button, exit) {
  await page.getByRole('button', {name:button, exact:true}).click();
  await expect(page.locator('.results')).toHaveAttribute('aria-busy', 'false');
  await expect(page.locator('#result-status')).toContainText(`Exit ${exit} ·`);
  return json(page);
}
function codes(report) { return report.files[0].findings.map(f => f.code); }

test.afterEach(async ({page, browser}, info) => {
  await info.attach('environment', {contentType:'application/json', body:JSON.stringify({
    ...metadata, browser:browser.version(), viewport:page.viewportSize(),
    footer: await page.locator('#version').textContent().catch(() => null),
  }, null, 2)});
});

test('real package: examples, JSON, coverage, Doctor and narrow layout', async ({page, context}, info) => {
  const requests = [], errors = [];
  context.on('request', request => requests.push({url:request.url(), method:request.method()}));
  page.on('pageerror', error => errors.push(String(error)));
  page.on('console', message => { if (['error','warning'].includes(message.type())) errors.push(message.text()); });
  await open(page);

  let report = await run(page, 'A clean document', 0);
  expect(report.version).toBe(checkerVersion);
  expect(report.files[0].findings).toEqual([]);
  expect(report.files[0].coverage.items.length).toBeGreaterThan(0);
  report = await run(page, 'A detached comment, with its original', 1);
  expect(codes(report)).toEqual(expect.arrayContaining(['CMT005','FID001']));
  expect(report.files[0].summary).toEqual({error:2, warn:0, info:1});
  await page.getByRole('tab', {name:'Report', exact:true}).click();
  await expect(page.locator('#human-output')).toContainText('CMT005');
  await expect(page.locator('#human-output')).toContainText('FID001');

  report = await run(page, 'A deck with text that does not fit', 1);
  expect(report.files[0].summary).toEqual({error:6, warn:4, info:1});
  expect(codes(report)).toEqual(expect.arrayContaining(['PPT001','PPT003','PPT004','PPT005','PPT006','PPT007']));
  const findings = report.files[0].findings;
  expect(report.files[0].coverage.summary.estimated).toBeGreaterThan(0);
  await page.getByRole('checkbox', {name:'Include coverage'}).uncheck();
  report = await run(page, 'Check', 1);
  expect(report.files[0]).not.toHaveProperty('coverage');
  expect(report.files[0].findings).toEqual(findings);
  await page.getByRole('checkbox', {name:'Include coverage'}).check();
  report = await run(page, 'Check', 1);
  expect(report.files[0]).toHaveProperty('coverage');

  const doctor = await run(page, 'Doctor', 0);
  expect(doctor.version).toBe(checkerVersion);
  expect(doctor.status).toBe('ready');
  expect(doctor.runtime.implementation).toBe('CPython');
  expect(doctor.runtime.platform).toContain('wasm');
  expect(doctor.fonts.failures).toEqual([]);
  expect(doctor.fonts.probes.map(p => p.confidence)).toEqual(['metric','metric','metric']);
  expect(doctor.capabilities.every(c => c.status === 'available')).toBe(true);
  await info.attach('doctor', {contentType:'application/json', body:JSON.stringify(doctor, null, 2)});
  const wheels = requests.filter(r => /\/ooxml_integrity-[^/]+\.whl$/.test(new URL(r.url).pathname));
  expect(wheels.length).toBeGreaterThan(0);
  expect(wheels.every(r => mode === 'wheel' ? r.url.includes('/_wheels/') : new URL(r.url).hostname === 'files.pythonhosted.org')).toBe(true);
  expect(requests.every(r => r.method === 'GET')).toBe(true);
  await info.attach('package-downloads', {contentType:'application/json', body:JSON.stringify(wheels, null, 2)});

  for (const width of [1280, 390]) {
    await page.setViewportSize({width, height:900});
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    await page.getByRole('link', {name:'Install', exact:true}).click();
    await expect(page).toHaveURL(/#install$/);
    await page.getByRole('link', {name:'Try it', exact:true}).click();
    await expect(page).toHaveURL(/#try$/);
  }
  const table = page.getByRole('region', {name:'Controlled mutation results'});
  await table.scrollIntoViewIfNeeded();
  const scroll = await table.evaluate(element => {
    element.scrollLeft = element.scrollWidth;
    return {left:element.scrollLeft, viewport:element.clientWidth, content:element.scrollWidth};
  });
  expect(scroll.left).toBeGreaterThan(0);
  expect(scroll.left + scroll.viewport).toBe(scroll.content);
  await info.attach('narrow-table', {body:await page.screenshot(), contentType:'image/png'});
  await run(page, 'A clean document', 0);
  expect(errors).toEqual([]);
});

test('uploads: same names, remove/reselect, corrupt input and recovery', async ({page}) => {
  await open(page);
  await page.locator('#file-input').setInputFiles(file('same.docx', 'agreement.docx'));
  await page.locator('#source-input').setInputFiles(file('same.docx'));
  let report = await run(page, 'Check', 1);
  expect(report.files[0].path).toBe('same.docx');
  expect(codes(report)).toEqual(expect.arrayContaining(['CMT005','FID001']));
  await page.getByRole('button', {name:'Remove source', exact:true}).click();
  report = await run(page, 'Check', 1);
  expect(codes(report)).toEqual(['CMT005']);
  await page.locator('#source-input').setInputFiles(file('same.docx'));
  report = await run(page, 'Check', 1);
  expect(codes(report)).toContain('FID001');
  await page.getByRole('button', {name:'Remove file', exact:true}).click();
  await expect(page.getByRole('button', {name:'Check', exact:true})).toBeDisabled();
  await page.locator('#file-input').setInputFiles(file('same.docx', 'agreement.docx'));
  expect(codes(await run(page, 'Check', 1))).toContain('FID001');
  await page.getByRole('button', {name:'Remove source', exact:true}).click();

  await page.locator('#file-input').setInputFiles({name:'corrupt.docx', mimeType:'application/octet-stream', buffer:Buffer.from('not a ZIP')});
  report = await run(page, 'Check', 1);
  expect(report.files[0].summary.error).toBeGreaterThan(0);
  expect(codes(report).some(code => code.startsWith('PKG'))).toBe(true);
  await page.locator('#file-input').setInputFiles(file('wrong.txt'));
  await expect(page.locator('#human-output')).toContainText('Unsupported file');
  await expect(page.getByRole('button', {name:'Check', exact:true})).toBeDisabled();
  await page.locator('#file-input').setInputFiles(file('same.docx'));
  expect((await run(page, 'Check', 0)).files[0].findings).toEqual([]);
  await page.locator('#file-input').setInputFiles(fixture('deck.pptx'));
  await page.locator('#source-input').setInputFiles(file('same.docx'));
  await page.getByRole('button', {name:'Check', exact:true}).click();
  await expect(page.locator('#human-output')).toContainText('Fidelity comparison requires two .docx files');
  expect((await json(page)).error).toContain('Remove the source');
  await page.getByRole('button', {name:'Remove source', exact:true}).click();
  expect((await run(page, 'Check', 1)).files[0].summary.error).toBe(6);
});

for (const dependency of ['runtime', 'font']) {
  test(`unavailable ${dependency}: visible startup error, disabled checks, reload recovery`, async ({page, context}) => {
    const pattern = dependency === 'runtime' ? '**/pyodide.mjs' : '**/fonts/Carlito-Regular.ttf';
    let intercepted = 0;
    await context.route(pattern, route => { intercepted++; return route.abort('failed'); });
    await page.goto('/');
    await expect(page.locator('#runtime-status')).toHaveText('Startup failed — reload to retry', {timeout:120_000});
    expect(intercepted).toBeGreaterThan(0);
    await expect(page.locator('#human-output')).toContainText('Check your network connection and reload');
    await expect(page.getByRole('button', {name:'Doctor', exact:true})).toBeDisabled();
    await expect(page.getByRole('button', {name:'A clean document', exact:true})).toBeDisabled();
    expect((await json(page)).error).toContain('Could not start Python');
    await context.unroute(pattern);
    await page.reload();
    await ready(page);
    await run(page, 'A clean document', 0);
  });
}

test('delayed runtime download: progress remains visible and then a real check succeeds', async ({page, context}, info) => {
  let intercepted = 0;
  await context.route('**/pyodide.mjs', async route => {
    intercepted++;
    await new Promise(resolve => setTimeout(resolve, 4000));
    await route.continue();
  });
  const start = Date.now();
  await page.goto('/');
  await expect(page.locator('#progress')).toContainText('Loading Pyodide');
  await expect(page.getByRole('button', {name:'A clean document', exact:true})).toBeDisabled();
  await ready(page);
  expect(intercepted).toBe(1);
  expect(Date.now() - start).toBeGreaterThanOrEqual(4000);
  await info.attach('network-scenario', {contentType:'application/json', body:JSON.stringify({
    injectedLatencyMs:4000, elapsedMs:Date.now()-start, scope:'pyodide.mjs request; no bandwidth throttle',
  })});
  await run(page, 'A clean document', 0);
});

test('60-second deadline terminates a busy Python worker; reload restores checks', async ({page, context}, info) => {
  test.setTimeout(240_000);
  // The real interpreter spins in a test-only bridge response. No Worker or
  // checker-result mock, shortened deadline or virtual clock is used.
  const bridge = readFileSync(resolve(site, 'bridge.py'), 'utf8') + `
_real_dispatch = dispatch
def dispatch(request_json):
    if json.loads(request_json).get("path") == "input/stalled.docx":
        while True:
            pass
    return _real_dispatch(request_json)
`;
  let intercepted = 0, closed = false;
  await context.route('**/bridge.py', route => {
    intercepted++;
    return route.fulfill({status:200, contentType:'text/plain', body:bridge});
  });
  await open(page);
  expect(intercepted).toBe(1);
  expect(page.workers()).toHaveLength(1);
  page.workers()[0].on('close', () => { closed = true; });
  await page.locator('#file-input').setInputFiles(file('stalled.docx'));
  const start = Date.now();
  await page.getByRole('button', {name:'Check', exact:true}).click();
  await expect(page.locator('.results')).toHaveAttribute('aria-busy', 'true');
  // Main-thread UI still responds while Python occupies the worker.
  await page.getByRole('tab', {name:'JSON', exact:true}).click();
  await expect(page.locator('#json-output')).toBeVisible();
  await expect(page.locator('#runtime-status')).toHaveText('Python stopped — reload to restart', {timeout:75_000});
  expect(Date.now() - start).toBeGreaterThanOrEqual(59_000);
  await expect.poll(() => closed).toBe(true);
  await expect(page.locator('#human-output')).toContainText('Check exceeded 60 seconds');
  await expect(page.locator('.results')).toHaveAttribute('aria-busy', 'false');
  await expect(page.getByRole('button', {name:'Check', exact:true})).toBeDisabled();
  await expect(page.getByRole('button', {name:'Doctor', exact:true})).toBeDisabled();
  await info.attach('timeout', {contentType:'application/json', body:JSON.stringify({elapsedMs:Date.now()-start, workerClosed:closed})});
  await context.unroute('**/bridge.py');
  await page.reload();
  await ready(page);
  await run(page, 'A clean document', 0);
});
