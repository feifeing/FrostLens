// Run after generating a StateLens report. No running server is necessary.
// STATELENS_REPORT=/absolute/path/report.html node tests/statelens-browser.mjs
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const { chromium } = await import(process.env.FROSTLENS_PLAYWRIGHT || 'playwright');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const reportPath = path.resolve(process.env.STATELENS_REPORT || path.join(root, 'local-reports/statelens/report.html'));
const html = await fs.readFile(reportPath, 'utf8');
const browser = await chromium.launch({ headless: true, args: ['--disable-gpu'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, acceptDownloads: true });
const page = await context.newPage();
const errors = [], external = [], checks = [];
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => { if (/^https?:/i.test(request.url())) external.push(request.url()); });
const check = (name, condition) => { assert.ok(condition, name); checks.push(name); };
const ready = () => page.waitForFunction(() => document.documentElement.dataset.ready === 'true');
async function exported(button, asJSON = true) {
  const pending = page.waitForEvent('download');
  await page.locator(button).click();
  const download = await pending;
  const contents = await fs.readFile(await download.path(), 'utf8');
  return asJSON ? JSON.parse(contents) : contents;
}
async function fixture(report) {
  const json = JSON.stringify(report).replaceAll('&', '\\u0026').replaceAll('<', '\\u003c').replaceAll('>', '\\u003e').replaceAll('\u2028', '\\u2028').replaceAll('\u2029', '\\u2029');
  const modified = html.replace(/(<script id="report-data" type="application\/json">)[\s\S]*?(<\/script>)/, (_, opening, closing) => opening + json + closing);
  await page.goto('about:blank');
  await page.setContent(modified);
  await ready();
}

const hostile = '</script><img src=x onerror="window.__injected=true">';
const metrics = [
  { id: 'energy', label: '能耗', unit: 'kWh', direction: 'lower', margin: 1 },
  { id: 'bias', label: '负值指标', unit: 'Pa', direction: 'higher', margin: 0.1 },
  { id: 'observe', label: '观察量', unit: 'mm', direction: 'observe', margin: 0 },
];
const sample = {
  schema_version: 'statelens-report/1', title: '可验证的状态比较',
  provenance: { engine_version: '0.2.0', sha256: 'a'.repeat(64), seed: 42, draws: 1000, method: 'percentile bootstrap', synthetic: true, sources: [{id:'raw',file:'independent-runs.csv',locator:'rows 2–21',sha256:'b'.repeat(64),method:'CSV',verified:false}], limitations: ['合成测试；不构成设备验证。'] },
  studies: [{ id: 'engineering', label: '工程实验', domain: '热物理', baseline: 'reference', question: '更省能耗的代价是什么？', design: 'independent', context_keys:['calibration'], metrics,
    states: [{id:'reference',label:'参照状态',context:{}},{id:'candidate',label:'候选状态',context:{}},{id:'blocked',label:'混杂状态',context:{}}],
    comparisons: [
      {baseline_id:'reference',state_id:'candidate',gate:'comparable',reasons:[],changes:[{key:'设定温度',baseline:10,state:12,allowed:true}],metrics:[
        {...metrics[0],baseline_mean:10,state_mean:7,n_baseline:10,n_state:10,delta:-3,percent_delta:-30,benefit:3,interval:[2,4],decision:'better',warnings:[],sensitivity:{positive_margin_max:2}},
        {...metrics[1],baseline_mean:-10,state_mean:-8,n_baseline:10,n_state:10,delta:2,percent_delta:20,benefit:2,interval:[-1,5],decision:'uncertain',warnings:['保留负测量值。']},
        {...metrics[2],baseline_mean:3,state_mean:4,n_baseline:1,n_state:1,delta:1,percent_delta:33.33,benefit:null,interval:null,decision:'descriptive',warnings:[]},
        {id:'small',label:'少量重复',unit:'s',direction:'lower',margin:1,baseline_mean:10,state_mean:7,n_baseline:3,n_state:3,delta:-3,benefit:3,interval:[2,4],decision:'insufficient',warnings:['样本不足，仅作探索。']},
        {id:'no-controls',label:'条件未确认',unit:'s',direction:'lower',margin:1,baseline_mean:10,state_mean:7,n_baseline:10,n_state:10,delta:-3,benefit:3,interval:[2,4],decision:'descriptive',warnings:['未声明必要控制条件。']},
      ]},
      {baseline_id:'reference',state_id:'blocked',gate:'blocked',reasons:['传感器校准不同。'],changes:[{key:'校准版本',baseline:'A',state:'B',allowed:false}],metrics:[{...metrics[0],baseline_mean:10,state_mean:2,n_baseline:10,n_state:10,delta:-8,percent_delta:-80,benefit:8,interval:[7,9],decision:'blocked',warnings:[]}]},
    ],pareto:{state_ids:['candidate'],eligible_ids:['reference','candidate'],note:'仅本研究内的均值权衡。'},next_steps:['统一校准，再增加独立重复。']},
    {id:'biology',label:'生物学实验',domain:'生物学',baseline:'b0',design:'descriptive',metrics:[],states:[{id:'b0',label:'空白组',context:{}}],comparisons:[],pareto:{state_ids:[],eligible_ids:[],note:'缺少数据。'},next_steps:[]},
  ],
};

try {
  await page.goto(pathToFileURL(reportPath).href);
  await ready();
  const inputReport = await page.locator('#report-data').textContent();
  const parsed = JSON.parse(inputReport);
  check('generated real report renders its study list', await page.locator('#study-select option').count() === (parsed.studies || []).length);
  check('real report includes provenance without network dependencies', await page.locator('#provenance-fields').textContent() !== '');
  const initialExport = await exported('#export-json');
  check('JSON preserves the complete original report', JSON.stringify(initialExport.report) === JSON.stringify(parsed));
  check('scenario stays separate from measured results', initialExport.scenario.schema_version === 'statelens-scenario/1' && Array.isArray(initialExport.scenario.thresholds));
  let originalDecisionsAgree = true;
  for (const [studyIndex, study] of parsed.studies.entries()) {
    await page.locator('#study-select').selectOption(String(studyIndex));
    for (const comparison of study.comparisons || []) {
      if (await page.locator('#baseline-select').inputValue() !== comparison.baseline_id) await page.locator('#baseline-select').selectOption(comparison.baseline_id);
      const matching = study.comparisons.filter(c => c.baseline_id === comparison.baseline_id);
      await page.locator('#state-select').selectOption(String(matching.indexOf(comparison)));
      for (const metric of comparison.metrics || []) {
        const actual = await page.locator('.metric-card').filter({has:page.locator('h3', {hasText:metric.label || metric.id})}).getAttribute('data-decision');
        originalDecisionsAgree &&= actual === metric.decision;
      }
    }
  }
  check('all initial UI decisions agree with the scientific engine', originalDecisionsAgree);
  await page.locator('#study-select').selectOption('0');
  const percentageMetric = parsed.studies[0].comparisons[0].metrics.find(m => m.unit === '%');
  if (percentageMetric) {
    const percentageCard = page.locator('.metric-card').filter({has:page.locator('h3', {hasText:percentageMetric.label})});
    check('percent means remain percentages while differences use percentage points', (await percentageCard.locator('.means').innerText()).includes('%') && (await percentageCard.locator('.delta').innerText()).includes('百分点') && (await percentageCard.locator('.unit').innerText()) === '百分点');
  }

  await fixture(sample);
  await page.locator('#provenance').evaluate(el => {el.open = true;});
  check('source files, locators and verification state are visible', (await page.locator('#sources').innerText()).includes('independent-runs.csv') && (await page.locator('#sources').innerText()).includes('rows 2–21') && (await page.locator('#sources').innerText()).includes('尚未核验'));
  check('synthetic examples are explicitly identified', (await page.locator('#report-kind').innerText()).includes('合成示例'));
  check('newcomer guide explains independent repeats and bootstrap limits', (await page.locator('.reading-guide').textContent()).includes('不能直接当作独立重复') && (await page.locator('.reading-guide').textContent()).includes('Bootstrap'));
  const energy = page.locator('[data-metric-id="energy"]');
  check('a lower-is-better negative raw delta is correctly improved', await energy.locator('.status').innerText() === '达到设定的改善幅度' && (await energy.locator('.delta').innerText()).includes('-3'));
  check('negative raw measurements remain visible', (await page.locator('[data-metric-id="bias"] .means').innerText()).includes('-10'));
  check('the conclusion boundary is explained with units', (await energy.locator('.cutoff').innerText()).includes('δ < 2 kWh'));
  await energy.locator('input').fill('2');
  check('touching the interval boundary no longer asserts improvement', await energy.locator('.status').innerText() === '证据仍不确定');
  await energy.locator('input').fill('4');
  check('touching the outer margin boundary stays uncertain', await energy.locator('.status').innerText() === '证据仍不确定');
  await energy.locator('input').fill('4.1');
  check('a wider practical margin contains the interval', await energy.locator('.status').innerText() === '差异在阈值内');
  const scenarioExport = await exported('#export-json');
  check('what-if export retains original threshold and decision', scenarioExport.report.studies[0].comparisons[0].metrics[0].margin === 1 && scenarioExport.report.studies[0].comparisons[0].metrics[0].decision === 'better');
  check('what-if export records the edited threshold separately', scenarioExport.scenario.thresholds.find(m => m.study_id === 'engineering' && m.metric_id === 'energy').margin === 4.1);
  await energy.locator('input').fill('-1');
  check('negative thresholds are rejected without changing the scenario', await energy.locator('input').getAttribute('aria-invalid') === 'true' && (await exported('#export-json')).scenario.thresholds.find(m => m.metric_id === 'energy').margin === 4.1);
  await page.locator('#reset-margins').click();
  check('reset restores both input and decision', await energy.locator('input').inputValue() === '1' && await energy.locator('.status').innerText() === '达到设定的改善幅度');
  await energy.locator('input').fill('1.7976931348623157e308');
  check('very large finite thresholds do not corrupt the interval chart', (await energy.locator('.chart-ci').evaluate(el => Number.isFinite(parseFloat(el.style.left)) && Number.isFinite(parseFloat(el.style.width)))) && !(await energy.locator('.chart-ticks').innerText()).includes('—'));
  await page.locator('#reset-margins').click();
  await page.locator('[data-metric-id="observe"] input').fill('100');
  check('observation-only metrics never turn into a win', await page.locator('[data-metric-id="observe"] .status').innerText() === '仅作描述');
  await page.locator('[data-metric-id="small"] input').fill('0');
  check('an exploratory positive interval cannot override insufficient evidence', await page.locator('[data-metric-id="small"] .status').innerText() === '有效数据不足');
  await page.locator('[data-metric-id="small"] input').fill('100');
  check('a broad margin cannot turn insufficient evidence into equivalence', await page.locator('[data-metric-id="small"] .status').innerText() === '有效数据不足');
  await page.locator('[data-metric-id="no-controls"] input').fill('0');
  check('descriptive results with preferred direction cannot become a win', await page.locator('[data-metric-id="no-controls"] .status').innerText() === '仅作描述');
  await page.locator('#metric-filter').fill('负值');
  check('metric filter narrows the displayed evidence', await page.locator('.metric-card').count() === 1 && await page.locator('[data-metric-id="bias"]').count() === 1);
  await page.locator('#metric-filter').fill('does-not-exist');
  check('empty metric filters explain how to recover', (await page.locator('#metric-list').innerText()).includes('没有匹配的指标'));
  await page.locator('#metric-filter').fill('');
  await page.locator('#state-select').selectOption('1');
  check('a blocked comparison states its concrete reason', (await page.locator('#gate-reasons').innerText()).includes('传感器校准不同') && await page.locator('#gate').getAttribute('class') === 'gate blocked');
  await energy.locator('input').fill('0');
  check('editing thresholds cannot remove comparability blocks', await energy.locator('.status').innerText() === '可比性受限' && (await energy.locator('.cutoff').innerText()).includes('先解决可比性'));
  await page.locator('#study-select').selectOption('1');
  check('study selector changes domain and handles no comparison', await page.locator('#domain').innerText() === '生物学' && (await page.locator('#gate-title').innerText()).includes('尚无状态'));
  await page.locator('#study-select').focus();
  await page.keyboard.press('Home');
  await page.keyboard.press('Enter');
  check('study selection is keyboard accessible', await page.locator('#study-select').inputValue() === '0');

  const noControls = structuredClone(sample);
  noControls.studies[0].context_keys = [];
  await fixture(noControls);
  check('undeclared controls never display a green passed badge', (await page.locator('#gate-title').innerText()).includes('必要实验条件尚未补全') && await page.locator('#gate').getAttribute('class') === 'gate blocked');

  const attack = structuredClone(sample);
  attack.title = hostile;
  attack.studies[0].label = ' \t=HYPERLINK("https://example.invalid","click")';
  attack.studies[0].comparisons[0].metrics[0].label = hostile;
  attack.studies[0].comparisons[0].changes[0].state = hostile;
  attack.provenance.limitations.push(hostile);
  attack.provenance.sources[0].file = hostile;
  attack.provenance.sources[0].locator = hostile;
  await fixture(attack);
  check('hostile names render literally without executing HTML', await page.evaluate(() => !window.__injected && document.querySelectorAll('img').length === 0) && (await page.locator('#report-title').innerText()) === hostile);
  const csv = await exported('#export-csv', false);
  check('CSV neutralizes formula-like labels including leading whitespace', csv.includes('"\' \t=HYPERLINK('));
  check('CSV keeps actual negative numbers numerical', csv.includes('"-3"') && !csv.includes('"\'-3"'));
  check('CSV exports original and scenario conclusions explicitly', csv.includes('"original_decision","scenario_decision"'));
  check('CSV export does not change the selected study', await page.locator('#study-select').inputValue() === '0');

  await page.setViewportSize({width:390,height:844});
  await fixture(sample);
  check('mobile report fits a 390px viewport', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.locator('#provenance').evaluate(el => {el.open = true;});
  check('long source fingerprints remain within the mobile viewport', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.locator('[data-metric-id="energy"] input').fill('2.5');
  check('mobile threshold interaction stays usable', await page.locator('[data-metric-id="energy"] .status').innerText() === '证据仍不确定');
  await fixture({...sample,studies:[]});
  check('empty reports have an honest recovery state', await page.locator('#empty-report').isVisible() && !await page.locator('#study-content').isVisible());
  const emptyExport = await exported('#export-json');
  check('empty report can still be exported with provenance', emptyExport.report.studies.length === 0 && emptyExport.scenario.selection === null);
  check('report performed no network requests', external.length === 0);
  check('all interactive reports ran without script errors', errors.length === 0);

  if (process.env.STATELENS_SCREENSHOT) {
    await page.setViewportSize({width:1440,height:1050});
    await page.goto(pathToFileURL(reportPath).href);
    await ready();
    await page.screenshot({path:path.resolve(process.env.STATELENS_SCREENSHOT),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(path.dirname(path.resolve(process.env.STATELENS_SCREENSHOT)),'mobile.png'),fullPage:true});
  }
  console.log(JSON.stringify({passed:checks.length,checks,errors,external},null,2));
} finally { await context.close(); await browser.close(); }
