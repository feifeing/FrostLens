/* FrostLens — no framework, no external services. All plotted values come from the report. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const COLORS = { ink: '#193a42', teal: '#177f75', pale: '#eaf4ef', amber: '#bf9550', muted: '#96a591', line: '#e8eee2' };
  const state = { report: null, reports: new Map(), cases: [], currentCase: 'narrow', busy: false, readOnly: location.protocol === 'file:', row: 0 };
  const BOUNDS = [
    { id: 'te', key: 'te_c', label: '蒸发温度', defaults: [-48, -28], limits: [-52, -20] },
    { id: 'tc', key: 'tc_c', label: '冷凝温度', defaults: [24, 44], limits: [15, 50] },
    { id: 'tm', key: 'tm_c', label: 'CO₂ 凝结温度', defaults: [-15, 2], limits: [-18, 5] },
    { id: 'load', key: 'load_kw', label: '制冷量', defaults: [4, 14], limits: [0.5, 16] }
  ];
  let toastTimer;
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const fmt = (value, digits = 2) => finite(value) ? value.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits }) : '—';
  const compact = value => finite(value) ? value.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—';
  const exp = value => finite(value) ? (value === 0 ? '0' : value.toExponential(2)) : '—';
  const set = (id, text) => { $(id).textContent = text; };
  function node(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    Object.entries(attrs).forEach(([key, value]) => {
      if (key === 'class') el.className = value;
      else if (key === 'text') el.textContent = value;
      else if (key === 'disabled') el.disabled = value;
      else el.setAttribute(key, value);
    });
    children.forEach(child => { if (child != null) el.append(child); });
    return el;
  }
  function svg(tag, attrs = {}, text) {
    const el = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, String(value)));
    if (text != null) el.textContent = text;
    return el;
  }
  function chartRoot(width, height, label) {
    const el = svg('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': label });
    el.append(svg('title', {}, label));
    return el;
  }
  function line(chart, x1, y1, x2, y2, color = COLORS.line, extra = {}) {
    chart.append(svg('line', { x1, y1, x2, y2, stroke: color, 'stroke-width': 1, ...extra }));
  }
  function text(chart, x, y, value, options = {}) {
    chart.append(svg('text', { x, y, fill: COLORS.muted, 'font-size': 10, ...options }, value));
  }
  function error(message) {
    set('error-message', message);
    $('error-banner').hidden = false;
  }
  function toast(message) {
    clearTimeout(toastTimer);
    set('toast', message);
    $('toast').hidden = false;
    toastTimer = setTimeout(() => { $('toast').hidden = true; }, 5000);
  }
  function syncControls() {
    document.querySelectorAll('[data-server-control]').forEach(el => { el.disabled = state.busy || state.readOnly; });
    // A snapshot can be explored without a server, including its other saved cases.
    $('case-select').disabled = state.busy || (state.readOnly && !state.reports.size);
    const pending = hasPendingSettings();
    document.querySelectorAll('.experiment-action').forEach(el => {
      const synthetic = state.report?.provenance?.kind === 'synthetic';
      el.disabled = state.busy || state.readOnly || !synthetic || pending;
      el.querySelector('span:first-child').textContent = state.readOnly ? '启动本地服务后试验' : !synthetic ? '采集新数据后导入' : pending ? '先分析新的设置' : '添加虚拟测量';
    });
    $('row-input').disabled = !state.report?.rows?.length;
    $('export-json').disabled = !state.report;
    $('export-csv').disabled = !state.report;
    $('sample-button').disabled = state.readOnly && !state.report;
    $('import-submit').disabled = state.busy || state.readOnly;
    $('csv-file').disabled = state.busy || state.readOnly;
    $('csv-text').disabled = state.busy || state.readOnly;
    $('settings-note').hidden = !pending || state.readOnly || !state.report;
    $('offline-banner').hidden = !state.readOnly;
    $('results').setAttribute('aria-busy', String(state.busy));
    $('busy-indicator').hidden = !state.busy;
  }
  function setBusy(busy, title = '正在读懂这组数据') {
    state.busy = busy;
    set('busy-title', title);
    syncControls();
  }
  async function request(path, body) {
    const response = await fetch(path, body ? {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    } : {});
    let result;
    try { result = await response.json(); }
    catch (_) { throw new Error('本地服务没有返回可读取的分析结果，请确认 FrostLens 服务正在运行。'); }
    if (!response.ok) throw new Error(result.error || `分析请求失败（${response.status}）。`);
    return result;
  }
  function settings() {
    const value = { sensor_mode: $('sensor-select').value, budget: Number($('budget-input').value) };
    BOUNDS.forEach(({ id, label }) => {
      if (['min', 'max'].some(end => $(`${id}-${end}`).validity.badInput)) throw new Error(`请输入有效的${label}数值。`);
    });
    const changed = BOUNDS.some(({ id }) => $(`${id}-min`).value.trim() || $(`${id}-max`).value.trim());
    if (changed) {
      value.bounds = {};
      BOUNDS.forEach(({ id, key, label, defaults, limits }) => {
        const a = $(`${id}-min`), b = $(`${id}-max`);
        const lower = a.value.trim() ? Number(a.value) : defaults[0];
        const upper = b.value.trim() ? Number(b.value) : defaults[1];
        if (!finite(lower) || !finite(upper) || lower > upper) throw new Error(`${label}的最小值不能大于最大值；两者相等表示固定该变量。`);
        if (lower < limits[0] || upper > limits[1]) throw new Error(`${label}需在模型支持范围 ${limits[0]} 至 ${limits[1]} 内。`);
        value.bounds[key] = [lower, upper];
      });
    }
    return value;
  }
  const reportKey = report => report?.provenance?.kind === 'synthetic' ? report.provenance.case_id : '__user__';
  function hasPendingSettings() {
    if (!state.report) return false;
    if ($('case-select').value !== reportKey(state.report)) return true;
    try {
      const options = settings();
      if (options.sensor_mode !== state.report.sensor_mode || options.budget !== state.report.budget) return true;
      return BOUNDS.some(({ key, defaults }) => {
        const requested = options.bounds?.[key] || defaults;
        const used = state.report.design_meta?.bounds?.[key] || defaults;
        return requested.some((value, index) => value !== used[index]);
      });
    } catch (_) { return true; }
  }
  function syncBounds(report) {
    BOUNDS.forEach(({ id, key, defaults }) => {
      const used = report.design_meta?.bounds?.[key] || defaults;
      ['min', 'max'].forEach((end, index) => {
        $(`${id}-${end}`).value = used[index] === defaults[index] ? '' : String(used[index]);
      });
    });
  }
  async function analyze(reset = false) {
    if (state.busy || state.readOnly) return;
    $('error-banner').hidden = true;
    try {
      const options = settings();
      const selected = $('case-select').value;
      const saved = state.reports.get(selected);
      let payload;
      // Preserve all appended measurements when changing channel, budget, or bounds.
      if (!reset && saved) {
        payload = { rows: saved.rows, ...options };
        // Case identity allows the server to retain verified synthetic provenance.
        if (saved.provenance?.kind === 'synthetic') payload.case_id = selected;
      } else {
        if (selected === '__user__') throw new Error('请先选择一个内置示例，或重新导入数据。');
        payload = { case_id: selected, ...options };
      }
      setBusy(true);
      const report = await request('/api/analyze', payload);
      if (selected !== reportKey(state.report)) state.row = 0;
      render(report);
    } catch (err) { error(err.message || '分析失败，请重试。'); }
    finally { setBusy(false); }
  }
  function render(report) {
    if (!report || !Array.isArray(report.rows) || !report.summary) throw new Error('分析结果不完整，无法显示。');
    state.report = report;
    state.reports.set(reportKey(report), report);
    state.row = Math.min(state.row, report.rows.length - 1);
    state.currentCase = report.provenance?.case_id || null;
    $('sensor-select').value = report.sensor_mode;
    $('budget-input').value = report.budget;
    set('budget-value', report.budget);
    syncBounds(report);
    const synthetic = report.provenance?.kind === 'synthetic';
    if (!synthetic) {
      if (!$('case-select').querySelector('option[value="__user__"]')) $('case-select').append(node('option', { value: '__user__', text: '我的导入数据' }));
      $('case-select').value = '__user__';
    } else if (state.currentCase) $('case-select').value = state.currentCase;
    updateCaseText();
    set('provenance-badge', synthetic ? '合成示例' : '导入数据');
    $('provenance-badge').classList.toggle('user-data', !synthetic);
    const caseInfo = state.cases.find(item => item.id === state.currentCase);
    set('dataset-name', synthetic ? (caseInfo?.name || '双级制冷合成示例') : '我的导入数据集');
    const created = report.provenance?.created_at;
    if (created && !Number.isNaN(new Date(created).getTime())) {
      set('report-date', new Date(created).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }));
    } else set('report-date', '');
    set('stat-n', report.summary.n);
    $('stat-rmse').replaceChildren(document.createTextNode(fmt(report.summary.rmse_kw, 3)), node('span', { class: 'unit', text: 'kW' }));
    $('stat-rank').replaceChildren(document.createTextNode(String(report.summary.rank)), node('span', { class: 'unit', text: `/ ${report.parameters.length}` }));
    $('stat-rank').title = `有效方向数：${report.summary.rank}；按归一化奇异值 ≥ 1 判断。${finite(report.summary.numerical_rank) ? `数值矩阵秩：${report.summary.numerical_rank}。` : ''}`;
    const statuses = { weak: '还有看不清的方向', informative: '数据提供了更多约束', mismatch: '模型 / 噪声需复核' };
    set('stat-status', statuses[report.summary.status] || '请结合假设解读');
    $('stat-status').className = report.summary.status;
    set('stat-message', report.summary.message);
    $('row-input').max = String(Math.max(0, report.rows.length - 1));
    $('row-input').value = String(state.row);
    renderCycle();
    renderFit(report);
    renderTable(report.rows);
    renderParameters(report);
    renderSensitivity(report);
    renderExperiments(report);
    renderWarnings(report);
    $('assumptions').replaceChildren(...(report.model?.assumptions || []).map(item => node('li', { text: item })));
    set('model-version', `${report.model?.name || '稳态制冷模型'} · ${report.model?.version || ''}`);
    const provenance = report.provenance || {};
    $('provenance-detail').replaceChildren(
      node('div', { text: `数据来源：${synthetic ? '内置合成示例' : '用户导入；来源由用户确认'}` }),
      node('div', { text: `生成时间：${provenance.created_at || '未记录'}` }),
      node('div', { text: `数据 SHA-256：${provenance.data_sha256 || '未记录'}` }),
      node('div', { text: `软件版本：${provenance.software_version || '未记录'}` })
    );
    syncControls();
  }
  function renderCycle() {
    const row = state.report?.rows[state.row];
    if (!row) return;
    set('row-number', String(state.row + 1).padStart(2, '0'));
    set('cycle-power', `输入 ${fmt(row.power_kw)} kW`);
    const root = chartRoot(540, 230, `第 ${state.row + 1} 次测量：蒸发温度 ${fmt(row.te_c)} 摄氏度，冷凝温度 ${fmt(row.tc_c)} 摄氏度，CO₂ 凝结温度 ${fmt(row.tm_c)} 摄氏度，制冷量 ${fmt(row.load_kw)} 千瓦。`);
    const defs = svg('defs');
    [['low-arrow', COLORS.teal], ['high-arrow', COLORS.ink]].forEach(([id, color]) => {
      const marker = svg('marker', { id, markerWidth: 5, markerHeight: 5, refX: 4, refY: 2.5, orient: 'auto' });
      marker.append(svg('path', { d: 'M0 0 L5 2.5 L0 5Z', fill: color }));
      defs.append(marker);
    });
    root.append(defs);
    const low = COLORS.teal, high = COLORS.ink;
    root.append(svg('path', { d: 'M62 150 V78 H255 V156 H62', fill: 'none', stroke: low, 'stroke-width': 2 }));
    root.append(svg('path', { d: 'M285 150 V78 H478 V156 H285', fill: 'none', stroke: high, 'stroke-width': 2 }));
    line(root, 204, 78, 223, 78, low, { 'stroke-width': 2, 'marker-end': 'url(#low-arrow)' });
    line(root, 106, 156, 88, 156, low, { 'stroke-width': 2, 'marker-end': 'url(#low-arrow)' });
    line(root, 431, 78, 448, 78, high, { 'stroke-width': 2, 'marker-end': 'url(#high-arrow)' });
    line(root, 324, 156, 306, 156, high, { 'stroke-width': 2, 'marker-end': 'url(#high-arrow)' });
    [62, 478].forEach((x, i) => {
      root.append(svg('rect', { x: x - 15, y: 95, width: 30, height: 45, rx: 7, fill: i ? '#eff3ef' : '#e8f4ed', stroke: i ? '#c9d4c7' : '#c5ddd0' }));
      root.append(svg('path', { d: `M${x - 7} 105 l14 7 -14 7 14 7`, fill: 'none', stroke: i ? high : low, 'stroke-width': 1.5 }));
    });
    [159, 380].forEach((x, i) => {
      root.append(svg('circle', { cx: x, cy: 78, r: 19, fill: '#fff', stroke: i ? high : low, 'stroke-width': 1.5 }));
      root.append(svg('path', { d: `M${x - 7} 69 l16 9 -16 9Z`, fill: i ? '#dae4da' : '#d6ece1', stroke: i ? high : low, 'stroke-width': 1 }));
      text(root, x, 114, i ? '高温级压缩机' : '低温级压缩机', { 'text-anchor': 'middle', 'font-size': 9, fill: i ? high : low });
      root.append(svg('path', { d: `M${x - 8} 151 l16 10 v-10 l-16 10Z`, fill: '#fff', stroke: i ? high : low, 'stroke-width': 1.4 }));
    });
    root.append(svg('rect', { x: 240, y: 90, width: 60, height: 58, rx: 9, fill: '#fbf8ee', stroke: '#dacfac' }));
    line(root, 270, 99, 270, 140, '#d6c795');
    root.append(svg('path', { d: 'M251 102 l11 6 -11 6 11 6 -11 6 11 6 M279 102 l11 6 -11 6 11 6 -11 6 11 6', fill: 'none', stroke: '#b2a06f', 'stroke-width': 1.3 }));
    text(root, 62, 35, `${fmt(row.te_c, 1)}°C`, { 'text-anchor': 'middle', 'font-size': 16, fill: low, 'font-weight': 500 });
    text(root, 62, 51, '蒸发温度', { 'text-anchor': 'middle', 'font-size': 8 });
    text(root, 270, 35, `${fmt(row.tm_c, 1)}°C`, { 'text-anchor': 'middle', 'font-size': 16, fill: '#a08754', 'font-weight': 500 });
    text(root, 270, 51, 'CO₂ 凝结温度', { 'text-anchor': 'middle', 'font-size': 8 });
    text(root, 478, 35, `${fmt(row.tc_c, 1)}°C`, { 'text-anchor': 'middle', 'font-size': 16, fill: high, 'font-weight': 500 });
    text(root, 478, 51, '冷凝温度', { 'text-anchor': 'middle', 'font-size': 8 });
    text(root, 62, 182, `制冷 ${fmt(row.load_kw, 1)} kW`, { 'text-anchor': 'middle', 'font-size': 9, fill: low });
    text(root, 270, 176, '级间换热器', { 'text-anchor': 'middle', 'font-size': 9, fill: '#a08754' });
    text(root, 478, 182, '向环境放热', { 'text-anchor': 'middle', 'font-size': 9, fill: high });
    text(root, 158, 200, 'CO₂ 低温循环', { 'text-anchor': 'middle', 'font-size': 9, fill: low });
    text(root, 380, 200, 'NH₃ 高温循环', { 'text-anchor': 'middle', 'font-size': 9, fill: high });
    text(root, 270, 224, '能量路径示意 · 不代表设备管路布置', { 'text-anchor': 'middle', 'font-size': 7.5, fill: '#a6b09e' });
    $('cycle-diagram').replaceChildren(root);
  }
  function renderFit(report) {
    const predictions = report.predictions || [];
    const root = chartRoot(520, 260, `测量与模型功率对比，${predictions.length} 个测量点，解释 A 的均方根误差为 ${fmt(report.summary.rmse_kw, 3)} 千瓦。`);
    if (!predictions.length) { $('fit-chart').replaceChildren(root); return; }
    const hasAlternative = predictions.some(p => finite(p.alternative_kw));
    $('alternative-legend').hidden = !hasAlternative;
    const vals = predictions.flatMap(p => [p.observed_kw, p.fitted_kw, p.alternative_kw]).filter(finite);
    const min = Math.min(...vals), max = Math.max(...vals);
    const range = Math.max(max - min, Math.abs(max) * 0.03, 0.03);
    const low = Math.max(0, min - range * 0.20), high = max + range * 0.2;
    const plot = { left: 49, right: 497, top: 23, bottom: 224 };
    const x = i => predictions.length > 1 ? plot.left + i / (predictions.length - 1) * (plot.right - plot.left) : (plot.left + plot.right) / 2;
    const y = value => plot.bottom - (value - low) / (high - low) * (plot.bottom - plot.top);
    for (let i = 0; i <= 4; i++) {
      const yy = plot.top + (plot.bottom - plot.top) * i / 4;
      line(root, plot.left, yy, plot.right, yy, COLORS.line, { 'stroke-dasharray': i === 4 ? '' : '2 4' });
      text(root, plot.left - 10, yy + 3, fmt(high - (high - low) * i / 4, high - low < 1 ? 2 : 1), { 'text-anchor': 'end', 'font-size': 9 });
    }
    const ticks = [...new Set([0, Math.floor((predictions.length - 1) * .25), Math.floor((predictions.length - 1) * .5), Math.floor((predictions.length - 1) * .75), predictions.length - 1])];
    ticks.forEach(i => text(root, x(i), 246, String(i + 1).padStart(2, '0'), { 'text-anchor': 'middle', 'font-size': 9 }));
    const areaPath = `M${x(0)} ${plot.bottom} ${predictions.map((p, i) => `L${x(i)} ${y(p.fitted_kw)}`).join(' ')} L${x(predictions.length - 1)} ${plot.bottom}Z`;
    root.append(svg('path', { d: areaPath, fill: '#eff7f0', opacity: .75 }));
    if (hasAlternative) root.append(svg('polyline', { points: predictions.map((p, i) => finite(p.alternative_kw) ? `${x(i)},${y(p.alternative_kw)}` : '').filter(Boolean).join(' '), fill: 'none', stroke: COLORS.amber, 'stroke-width': 1.7, 'stroke-dasharray': '5 4', 'stroke-linejoin': 'round' }));
    root.append(svg('polyline', { points: predictions.map((p, i) => `${x(i)},${y(p.fitted_kw)}`).join(' '), fill: 'none', stroke: COLORS.teal, 'stroke-width': 2, 'stroke-linejoin': 'round' }));
    predictions.forEach((p, i) => {
      const dot = svg('circle', { cx: x(i), cy: y(p.observed_kw), r: predictions.length > 80 ? 2 : 3.3, fill: COLORS.ink, stroke: '#fff', 'stroke-width': 1.3 });
      dot.append(svg('title', {}, `测量 ${i + 1}：${fmt(p.observed_kw, 3)} kW；A：${fmt(p.fitted_kw, 3)} kW${finite(p.alternative_kw) ? `；B：${fmt(p.alternative_kw, 3)} kW` : ''}`));
      root.append(dot);
    });
    $('fit-chart').replaceChildren(root);
  }
  function renderTable(rows) {
    const keys = ['te_c', 'tc_c', 'tm_c', 'load_kw', 'power_kw', 'sigma_kw', 'low_power_kw', 'sigma_low_kw'];
    const frag = document.createDocumentFragment();
    rows.forEach((row, index) => frag.append(node('tr', {}, node('td', { text: String(index + 1).padStart(2, '0') }), ...keys.map(key => node('td', { text: finite(row[key]) ? fmt(row[key], key.includes('sigma') ? 3 : 2) : '—' })))));
    $('data-table').replaceChildren(frag);
    set('table-summary', `${rows.length} 次测量 · 温度 °C · 功率 kW`);
  }
  function renderParameters(report) {
    const alternative = report.alternative;
    $('parameter-b-legend').hidden = !alternative;
    set('alternative-description', alternative ? `A 误差 ${fmt(report.summary.rmse_kw, 3)} kW · B 误差 ${fmt(alternative.rmse_kw, 3)} kW` : '本轮搜索未找到满足条件的另一种解释');
    const frag = document.createDocumentFragment();
    report.parameters.forEach(p => {
      const other = alternative?.parameters?.[p.key];
      const ratio = value => Math.max(0, Math.min(100, (value - p.lower) / (p.upper - p.lower) * 100));
      const a = ratio(p.value), b = finite(other) ? ratio(other) : null;
      const values = node('span', { class: 'parameter-values' }, node('span', { class: 'value-a', text: fmt(p.value, 3), title: '解释 A' }));
      if (b != null) values.append(node('span', { class: 'value-b', text: fmt(other, 3), title: '解释 B' }));
      const track = node('div', { class: 'parameter-track', role: 'img', 'aria-label': `${p.name}：解释 A ${fmt(p.value, 3)}${finite(other) ? `，解释 B ${fmt(other, 3)}` : ''}；允许区间 ${p.lower} 至 ${p.upper} ${p.unit || ''}。` });
      if (b != null) track.append(node('span', { class: 'parameter-span', style: `left:${Math.min(a, b)}%;width:${Math.abs(a - b)}%` }));
      track.append(node('span', { class: 'parameter-marker', style: `left:${a}%` }));
      if (b != null) track.append(node('span', { class: 'parameter-marker b', style: `left:${b}%` }));
      frag.append(node('div', { class: 'parameter-row' },
        node('div', { class: 'parameter-heading' }, node('span', { text: p.name }), node('span', { class: 'parameter-unit', text: p.unit || '' }), values),
        track, node('div', { class: 'parameter-limits' }, node('span', { text: compact(p.lower) }), node('span', { text: compact(p.upper) }))
      ));
    });
    $('parameters').replaceChildren(frag);
    set('alternative-note', alternative ? '两组解说明当前数据可能存在歧义。参数条表示搜索范围，不是置信区间。' : '未找到替代解不等于参数唯一。参数条表示搜索范围，不是置信区间。');
  }
  function renderSensitivity(report) {
    const detail = report.identifiability || {};
    const relative = detail.relative_singular_values || [];
    const actual = detail.singular_values || [];
    const root = chartRoot(400, 192, `噪声归一化灵敏度，相对奇异值为 ${relative.map(exp).join('、')}。使用对数坐标，越靠左的方向越弱。`);
    const left = 49, right = 342, top = 28, bottom = 154;
    const minPositive = Math.min(...relative.filter(v => v > 0), 1);
    const exponentMin = Math.max(-16, Math.min(-3, Math.floor(Math.log10(minPositive)) - 1));
    const sx = value => left + (Math.max(exponentMin, Math.log10(Math.max(value, Math.pow(10, exponentMin)))) - exponentMin) / -exponentMin * (right - left);
    const tickCount = Math.min(4, -exponentMin);
    for (let i = 0; i <= tickCount; i++) {
      const exponent = Math.round(exponentMin + (-exponentMin * i / tickCount));
      const xx = sx(Math.pow(10, exponent));
      line(root, xx, top - 8, xx, bottom + 9, '#e9eee3', { 'stroke-dasharray': '2 4' });
      text(root, xx, 181, exponent === 0 ? '1' : `10${superscript(exponent)}`, { 'text-anchor': 'middle', 'font-size': 9 });
    }
    relative.forEach((value, i) => {
      const yy = top + (relative.length > 1 ? i / (relative.length - 1) * (bottom - top) : 50);
      const weak = finite(actual[i]) && actual[i] < 1;
      const color = weak ? COLORS.amber : COLORS.teal;
      text(root, 4, yy + 3, `方向 ${i + 1}`, { 'font-size': 9 });
      line(root, left, yy, sx(value), yy, weak ? '#efe3ce' : '#dceade', { 'stroke-width': 5, 'stroke-linecap': 'round' });
      const dot = svg('circle', { cx: sx(value), cy: yy, r: 4.5, fill: color, stroke: '#fff', 'stroke-width': 1.5 });
      dot.append(svg('title', {}, `方向 ${i + 1}：相对值 ${exp(value)}；归一化奇异值 ${exp(actual[i])}${weak ? '，小于 1，当前测量约束较弱' : ''}`));
      root.append(dot);
      text(root, 395, yy + 3, exp(value), { 'text-anchor': 'end', 'font-size': 8, fill: color });
    });
    $('sensitivity-chart').replaceChildren(root);
    set('identifiability-text', `${detail.explanation || '越小的奇异值对应越难区分的参数方向。'} 图中使用对数坐标；金色表示归一化奇异值小于 1。有效方向数使用阈值 1，不是数值矩阵秩。`);
  }
  function superscript(n) {
    const chars = { '-': '⁻', '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹' };
    return String(n).split('').map(c => chars[c]).join('');
  }
  function renderExperiments(report) {
    const designs = report.design || [];
    set('design-count', `${designs.length} 个推荐工况`);
    set('design-note', report.design_meta?.note || '在候选工况中顺序补充局部参数信息；排序不等于两种解释的全局最佳区分顺序。');
    const bounds = report.design_meta?.bounds;
    const descriptions = [['te_c', '蒸发', '°C'], ['tc_c', '冷凝', '°C'], ['tm_c', 'CO₂ 凝结', '°C'], ['load_kw', '制冷量', 'kW']];
    const domains = bounds ? descriptions.filter(([key]) => Array.isArray(bounds[key])).map(([key, label, unit]) => `${label} ${compact(bounds[key][0])}–${compact(bounds[key][1])} ${unit}`) : [];
    set('design-bounds', domains.length ? `推荐范围：${domains.join(' · ')}。${finite(report.design_meta?.candidate_count) ? `评估 ${report.design_meta.candidate_count} 个可行候选工况。` : ''}` : '');
    const synthetic = report.provenance?.kind === 'synthetic';
    const frag = document.createDocumentFragment();
    designs.forEach((design, index) => {
      const conditions = node('div', { class: 'conditions' });
      descriptions.forEach(([key, label, unit]) => conditions.append(node('div', {}, node('div', { class: 'condition-label', text: label }), node('div', { class: 'condition-value' }, document.createTextNode(compact(design.point[key])), node('span', { text: unit })))));
      const rank = node('span', { class: 'experiment-rank' }, document.createTextNode(String(design.rank).padStart(2, '0')));
      if (index === 0) rank.append(node('span', { class: 'rank-label', text: '先试这一点' }));
      const button = node('button', { class: 'experiment-action', type: 'button', disabled: !synthetic || state.readOnly || state.busy,
        title: synthetic ? '在合成案例中生成一条虚拟测量，并重新分析' : '导入数据不支持生成虚拟测量，请补充新的数据后重新导入。' },
        node('span', { text: state.readOnly ? '启动本地服务后试验' : synthetic ? '添加虚拟测量' : '采集新数据后导入' }), node('span', { text: synthetic ? '＋' : '↗', 'aria-hidden': 'true' }));
      button.addEventListener('click', () => addExperiment(design.point));
      const predicted = `A 预测 ${fmt(design.predicted_kw)} kW${finite(design.alternative_kw) ? ` · B ${fmt(design.alternative_kw)} kW` : ''}`;
      frag.append(node('article', { class: 'card experiment-card' },
        node('div', { class: 'experiment-card-heading' }, rank, node('span', { class: 'experiment-gain', title: '新增测量带来的正则化信息矩阵对数行列式增量，不是百分比。' }, document.createTextNode('信息增益 '), node('strong', { text: `+${fmt(design.gain, 2)}` }))),
        conditions,
        node('div', { class: 'experiment-separation' }, node('span', { text: '预测分歧 / 测量噪声' }), node('strong', { text: finite(design.separation_sigma) ? `${fmt(design.separation_sigma, 1)} σ` : '暂无替代解' })),
        node('div', { class: 'predicted-value', text: predicted }), button
      ));
    });
    if (!designs.length) frag.append(node('div', { class: 'card empty-experiments', text: '当前范围内没有可推荐的实验。可检查设备允许工况设置与模型提示。' }));
    $('experiment-cards').replaceChildren(frag);
    set('experiment-disclaimer', synthetic ? '虚拟测量来自已知的合成系统，不是两种拟合解释的预测值。添加后可重新比较结果；真实设备实验请先核对运行边界。' : '导入数据保留原始测量，不会生成虚拟结果。可导出 JSON 报告中的推荐工况，在完成实验后将新测量加入 CSV 重新导入。');
  }
  function renderWarnings(report) {
    const warnings = report.warnings || [];
    $('warnings').hidden = !warnings.length;
    $('warnings').replaceChildren(node('strong', { text: '解释结果时，请一起考虑' }), node('ul', {}, ...warnings.map(warning => node('li', { text: warning }))));
  }
  async function addExperiment(point) {
    if (state.busy || state.readOnly || state.report?.provenance?.kind !== 'synthetic' || !state.currentCase || hasPendingSettings()) return;
    $('error-banner').hidden = true;
    try {
      const options = settings();
      setBusy(true, '正在用新的证据，重新检验解释');
      const previous = state.report.summary;
      const report = await request('/api/experiment', { case_id: state.currentCase, rows: state.report.rows, point, ...options });
      state.row = report.rows.length - 1;
      render(report);
      toast(`已加入第 ${report.rows.length} 条合成测量。测量可约束的方向：${previous.rank} → ${report.summary.rank}。`);
    } catch (err) { error(err.message || '虚拟实验失败，请重试。'); }
    finally { setBusy(false); }
  }
  function updateCaseText() {
    const selected = $('case-select').value;
    const item = state.cases.find(item => item.id === selected);
    set('case-description', selected === '__user__' ? '当前使用导入数据。可调整测量通道和推荐范围后重新分析。' : item?.description || '内置示例全部使用合成数据。');
    $('analyze-button').querySelector('span:last-child').textContent = state.readOnly ? '离线报告 · 仅供查看' : selected === '__user__' ? '重新分析我的数据' : (state.report && selected === state.currentCase ? '重新分析这组数据' : '分析这个示例');
    $('reset-button').textContent = selected === '__user__' ? '返回原始合成示例' : '重置为原始示例';
  }
  function csvString(rows) {
    const keys = ['te_c', 'tc_c', 'tm_c', 'load_kw', 'power_kw', 'sigma_kw'];
    if (rows.some(row => finite(row.low_power_kw))) keys.push('low_power_kw');
    if (rows.some(row => finite(row.sigma_low_kw))) keys.push('sigma_low_kw');
    // Only validated numeric fields are exported; no spreadsheet formula cells.
    return keys.join(',') + '\r\n' + rows.map(row => keys.map(key => finite(row[key]) ? String(row[key]) : '').join(',')).join('\r\n') + '\r\n';
  }
  function download(content, type, filename) {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const link = node('a', { href: url, download: filename });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  $('analysis-form').addEventListener('submit', event => { event.preventDefault(); analyze(); });
  $('reset-button').addEventListener('click', () => {
    if ($('case-select').value === '__user__') $('case-select').value = 'narrow';
    state.row = 0;
    analyze(true);
  });
  $('case-select').addEventListener('change', () => {
    if (state.readOnly) {
      const report = state.reports.get($('case-select').value);
      if (report) { state.row = 0; render(report); }
    }
    updateCaseText();
    syncControls();
  });
  $('analysis-form').addEventListener('input', () => {
    set('budget-value', $('budget-input').value);
    syncControls();
  });
  $('row-input').addEventListener('input', () => { state.row = Number($('row-input').value); renderCycle(); });
  $('dismiss-error').addEventListener('click', () => { $('error-banner').hidden = true; });
  $('export-json').addEventListener('click', () => {
    if (!state.report) return;
    download(JSON.stringify(state.report, null, 2) + '\n', 'application/json;charset=utf-8', 'frostlens-report.json');
    toast('已导出完整分析报告，包含模型假设、推荐工况与数据指纹。');
  });
  $('export-csv').addEventListener('click', () => {
    if (!state.report) return;
    download(csvString(state.report.rows), 'text/csv;charset=utf-8', 'frostlens-measurements.csv');
    toast('已导出当前数据集。CSV 导入后将标记为导入数据。');
  });
  $('sample-button').addEventListener('click', () => {
    if (state.readOnly) {
      const sample = state.reports.get('narrow') || state.report;
      if (sample) download(csvString(sample.rows), 'text/csv;charset=utf-8', 'frostlens-synthetic-sample.csv');
    } else {
      const a = node('a', { href: '/api/sample.csv', download: 'frostlens-example.csv' });
      document.body.append(a); a.click(); a.remove();
    }
  });
  const openDialog = id => {
    const dialog = $(id);
    dialog.showModal();
    dialog.scrollTop = 0;
    dialog.querySelector('.close-button').focus();
  };
  const openAbout = () => openDialog('about-dialog');
  $('about-button').addEventListener('click', openAbout);
  $('sensitivity-help').addEventListener('click', openAbout);
  $('close-about').addEventListener('click', () => $('about-dialog').close());
  $('open-import').addEventListener('click', () => { $('import-error').hidden = true; openDialog('import-dialog'); });
  $('close-import').addEventListener('click', () => $('import-dialog').close());
  [$('about-dialog'), $('import-dialog')].forEach(dialog => dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
  }));
  $('csv-file').addEventListener('change', async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    $('csv-text').value = '';
    set('file-label', file.name);
    if (file.size > 900000) {
      set('import-error', 'CSV 文件过大。请选择小于 900 KB、最多 250 行的测量文件。'); $('import-error').hidden = false; return;
    }
    try {
      $('csv-text').value = (await file.text()).replace(/^\uFEFF/, '');
      set('file-label', file.name);
      $('import-error').hidden = true;
    } catch (_) { set('import-error', '无法读取这个文件，请重新选择 UTF-8 编码的 CSV。'); $('import-error').hidden = false; }
  });
  $('import-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (state.busy || state.readOnly) return;
    $('import-error').hidden = true;
    $('error-banner').hidden = true;
    try {
      const csv = $('csv-text').value.trim();
      if (!csv) throw new Error('请先选择文件或粘贴 CSV 内容。');
      if (new Blob([csv]).size > 900000) throw new Error('CSV 内容过大。请使用小于 900 KB、最多 250 行的数据。');
      const options = settings();
      setBusy(true, '正在检查并分析你的测量');
      $('import-submit').textContent = '正在分析…';
      const report = await request('/api/import', { csv, ...options });
      state.currentCase = null; state.row = 0;
      render(report);
      $('import-dialog').close();
      toast(`已导入 ${report.rows.length} 条测量。结果仅在本机处理。`);
    } catch (err) {
      const message = err.message || '导入失败，请检查 CSV 格式。';
      set('import-error', message); $('import-error').hidden = false;
      if (!$('import-dialog').open) error(message);
    }
    finally { setBusy(false); $('import-submit').textContent = '导入并分析 ↗'; }
  });
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      const visible = entries.filter(entry => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (!visible.length) return;
      document.querySelectorAll('.step-link').forEach(link => link.classList.toggle('active', link.getAttribute('href') === `#${visible[0].target.id}`));
    }, { rootMargin: '-5% 0px -60% 0px', threshold: 0 });
    ['data', 'explanations', 'experiments'].forEach(id => observer.observe($(id)));
  }
  function loadCases(cases) {
    state.cases = cases;
    $('case-select').replaceChildren(...cases.map(item => node('option', { value: item.id, text: item.name })));
    updateCaseText();
  }
  async function initialize() {
    loadCases([
      { id: 'narrow', name: '同样吻合，两种解释', description: '相近工况的测量：拟合可以很好，参数仍可能难以区分。' },
      { id: 'wide', name: '让工况提供更多线索', description: '覆盖不同温度和负荷，比较工况范围与分项传感器的作用。' },
      { id: 'drift', name: '模型也可能解释不了', description: '显式模型外合成案例，检验恒参数模型的边界。' }
    ]);
    if (state.readOnly) {
      const snapshot = window.FROSTLENS_DEMO;
      const demo = snapshot?.report || (snapshot?.summary ? snapshot : null);
      if (Array.isArray(snapshot?.cases) && snapshot.cases.length) loadCases(snapshot.cases);
      if (snapshot?.reports) Object.entries(snapshot.reports).forEach(([key, report]) => {
        if (report?.summary && Array.isArray(report.rows)) state.reports.set(key, report);
      });
      if (demo) state.reports.set(reportKey(demo), demo);
      // Never offer a case whose precomputed report is absent from this snapshot.
      loadCases(state.cases.filter(item => state.reports.has(item.id)));
      if (demo) {
        try { render(demo); }
        catch (err) { error(err.message); }
      } else if (state.reports.size) render(state.reports.values().next().value);
      else error('没有找到离线示例结果。请启动 FrostLens 本地服务后打开工作台。');
      syncControls();
      return;
    }
    try {
      setBusy(true);
      const catalog = await request('/api/cases');
      loadCases(catalog.cases);
      const report = await request('/api/analyze', { case_id: 'narrow', sensor_mode: 'power', budget: 3 });
      render(report);
    } catch (err) {
      error(err.message || '无法连接本地服务。请确认 FrostLens 服务正在运行。');
    } finally { setBusy(false); }
  }
  initialize();
})();
