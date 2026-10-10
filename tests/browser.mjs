// Optional integration checks: npm install --no-save playwright && npx playwright install chromium
// Run against a running local server: node tests/browser.mjs
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
const { chromium } = await import(process.env.FROSTLENS_PLAYWRIGHT || 'playwright');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const url = process.env.FROSTLENS_URL || 'http://127.0.0.1:8765';
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1050 } });
const page = await context.newPage();
const errors = [], requests = [], checks = [];
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => requests.push(request.url()));
const check = (name, condition) => { assert.ok(condition, name); checks.push(name); };
async function ready() {
  await page.waitForFunction(() => document.getElementById('results').getAttribute('aria-busy') === 'false');
}
async function analyze() {
  const pending = page.waitForResponse(r => r.url().endsWith('/api/analyze') && r.request().method() === 'POST');
  await page.locator('#analyze-button').click();
  const response = await pending;
  assert.equal(response.status(), 200, await response.text());
  const result = await response.json();
  await ready();
  return result;
}
async function downloadReport() {
  const pending = page.waitForEvent('download');
  await page.locator('#export-json').click();
  const download = await pending;
  return JSON.parse(await fs.readFile(await download.path(), 'utf8'));
}
try {
  // CI may start the local server immediately before this process.
  for (let attempt = 0; attempt < 20; attempt++) {
    try {
      const response = await fetch(url + '/api/cases');
      if (response.ok) break;
    } catch (_) { /* Server is still starting. */ }
    if (attempt === 19) throw new Error('Local FrostLens server did not become ready: ' + url);
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  await page.goto(url);
  await page.waitForFunction(() => document.getElementById('stat-n').textContent === '12');
  await ready();
  check('initial synthetic case renders', (await page.locator('#provenance-badge').innerText()) === '合成示例');
  check('cycle and fit charts render', await page.locator('#cycle-diagram svg, #fit-chart svg').count() === 2);
  const before = await downloadReport();
  check('report export carries provenance and scientific versions', before.provenance.data_sha256.length === 64 && !!before.model.coolprop_version);

  for (let n = 13; n <= 15; n++) {
    const pending = page.waitForResponse(r => r.url().endsWith('/api/experiment'));
    await page.locator('.experiment-action').first().click();
    const response = await pending;
    assert.equal(response.status(), 200, await response.text());
    await page.waitForFunction(expected => document.getElementById('stat-n').textContent === String(expected), n);
    await ready();
  }
  let result = await downloadReport();
  check('three virtual experiments close the loop', result.summary.n === 15 && result.summary.rank === 4);
  check('new evidence improves the weakest local direction', result.identifiability.singular_values.at(-1) > before.identifiability.singular_values.at(-1));
  await page.locator('#sensor-select').selectOption('split');
  check('changed settings disable stale recommendations', await page.locator('.experiment-action').first().isDisabled());
  result = await analyze();
  check('reanalyzing retains added synthetic rows', result.summary.n === 15 && result.sensor_mode === 'split' && result.provenance.kind === 'synthetic');

  await page.locator('#case-select').selectOption('wide');
  result = await analyze();
  check('wide case is locally informative', result.summary.n === 16 && result.summary.rank === 4);
  await page.locator('#case-select').selectOption('drift');
  result = await analyze();
  check('out-of-model case surfaces a mismatch', result.summary.status === 'mismatch');

  await page.locator('.bounds-panel summary').click();
  for (const [key, value] of [['te', '-40'], ['tc', '35'], ['tm', '-8'], ['load', '8']]) {
    await page.locator(`#${key}-min`).fill(value);
    await page.locator(`#${key}-max`).fill(value);
  }
  result = await analyze();
  check('fixed variable bounds are supported', result.design.length === 1 && result.design[0].point.load_kw === 8);
  for (const key of ['te', 'tc', 'tm', 'load']) {
    await page.locator(`#${key}-min`).fill('');
    await page.locator(`#${key}-max`).fill('');
  }
  await page.locator('#sensor-select').selectOption('power');
  const csv = await fs.readFile(path.join(root, 'examples/narrow.csv'), 'utf8');
  await page.locator('#open-import').click();
  await page.locator('#csv-text').fill(csv);
  const importing = page.waitForResponse(r => r.url().endsWith('/api/import'));
  await page.locator('#import-submit').click();
  assert.equal((await importing).status(), 200);
  await page.waitForFunction(() => !document.getElementById('import-dialog').open);
  await ready();
  result = await downloadReport();
  check('imported synthetic CSV remains user-supplied data', result.provenance.kind === 'user' && result.provenance.case_id === null);
  check('imported data cannot generate virtual observations', await page.locator('.experiment-action').first().isDisabled());
  await page.locator('#open-import').click();
  await page.locator('#csv-text').fill('wrong_header\n1');
  const invalid = page.waitForResponse(r => r.url().endsWith('/api/import'));
  await page.locator('#import-submit').click();
  assert.equal((await invalid).status(), 400);
  await page.locator('#import-error').waitFor({state:'visible'});
  check('bad imports show an actionable error', (await page.locator('#import-error').innerText()).includes('缺少列'));
  await page.keyboard.press('Escape');
  check('import dialog closes with Escape', !(await page.locator('#import-dialog').evaluate(el => el.open)));
  await page.locator('#about-button').click();
  check('method dialog opens', await page.locator('#about-dialog').evaluate(el => el.open));
  await page.keyboard.press('Escape');
  await page.setViewportSize({width:390,height:844});
  check('mobile layout has no horizontal page overflow', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));

  await page.goto(pathToFileURL(path.join(root, 'frostlens/web/index.html')).href);
  await page.waitForFunction(() => document.getElementById('stat-n').textContent === '12');
  check('offline view disables server mutations', await page.locator('#open-import').isDisabled() && await page.locator('#analyze-button').isDisabled());
  await page.locator('#case-select').selectOption('wide');
  await page.waitForFunction(() => document.getElementById('stat-n').textContent === '16');
  check('offline cases can be switched', (await downloadReport()).provenance.case_id === 'wide');
  await page.locator('#case-select').selectOption('drift');
  check('offline mismatch remains labeled', (await downloadReport()).summary.status === 'mismatch');
  check('no browser script errors', errors.length === 0);
  check('no external network requests', requests.every(item => item.startsWith(url) || item.startsWith('file:') || item.startsWith('blob:')));
  console.log(JSON.stringify({passed: checks.length, checks, errors}, null, 2));
} finally {
  await browser.close();
}
