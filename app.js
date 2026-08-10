const state = {
  data: null,
  filter: 'ALL',
  historyIndex: null,
  history: [],
  previous: null,
  allocations: []
};

const fmt = new Intl.NumberFormat('zh-TW', { maximumFractionDigits: 2 });
const moneyFmt = new Intl.NumberFormat('zh-TW', {
  style: 'currency',
  currency: 'TWD',
  maximumFractionDigits: 0
});

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function localDate(value) {
  return new Date(`${value}T00:00:00+08:00`);
}

function daysBetween(a, b) {
  return Math.floor((b - a) / 86400000);
}

function gradeClass(grade) {
  if (grade === 'A') return 'grade-a';
  if (grade === 'B') return 'grade-b';
  return 'grade-c';
}

function actionClass(action) {
  return action.includes('BUY') ? 'action-buy' : 'action-watch';
}

function trendClass(trend) {
  return trend === 'UP' ? 'up' : trend === 'MIXED' ? 'mixed' : '';
}

function filteredStocks(stocks) {
  if (state.filter === 'A') return stocks.filter(s => s.grade === 'A');
  if (state.filter === 'WATCH') return stocks.filter(s => s.action === 'WATCH');
  return stocks;
}

function previousStock(ticker) {
  return state.previous?.stocks?.find(stock => stock.ticker === ticker) ?? null;
}

function rankDelta(stock) {
  const previous = previousStock(stock.ticker);
  if (!previous) return null;
  return previous.rank - stock.rank;
}

function rankDeltaMarkup(stock) {
  const delta = rankDelta(stock);
  if (delta == null) return '<span class="rank-flat">NEW</span>';
  if (delta > 0) return `<span class="rank-up">↑${delta}</span>`;
  if (delta < 0) return `<span class="rank-down">↓${Math.abs(delta)}</span>`;
  return '<span class="rank-flat">—</span>';
}

function renderTable(stocks) {
  const body = document.querySelector('#rankingBody');
  const rows = filteredStocks(stocks);
  body.innerHTML = rows.map(stock => `
    <tr>
      <td>#${stock.rank}</td>
      <td>${rankDeltaMarkup(stock)}</td>
      <td class="company"><strong>${escapeHtml(stock.name)}</strong><span>${escapeHtml(stock.ticker)}</span></td>
      <td class="score">${stock.score}</td>
      <td><span class="grade ${gradeClass(stock.grade)}">${escapeHtml(stock.grade)}</span></td>
      <td>${stock.reference_price == null ? '待驗證' : fmt.format(stock.reference_price)}</td>
      <td>${stock.pe_ttm == null ? '待驗證' : fmt.format(stock.pe_ttm) + 'x'}</td>
      <td class="${trendClass(stock.earnings_trend)}">${escapeHtml(stock.earnings_trend)}</td>
      <td>${escapeHtml(stock.valuation)}</td>
      <td class="${actionClass(stock.action)}"><strong>${escapeHtml(stock.action)}</strong></td>
    </tr>`).join('');

  const baseline = document.querySelector('#rankBaseline');
  baseline.textContent = state.previous
    ? `週變動基準：${state.previous.meta.as_of} snapshot`
    : '目前只有第一份 snapshot；下一次週報後開始顯示 ↑↓ 排名變化。';
}

function renderCards(stocks) {
  const cards = document.querySelector('#stockCards');
  cards.innerHTML = filteredStocks(stocks).map(stock => `
    <article class="stock-card">
      <div class="card-top">
        <div>
          <h3>${escapeHtml(stock.name)}</h3>
          <div class="ticker">${escapeHtml(stock.ticker)} · ${escapeHtml(stock.action)}</div>
        </div>
        <div>
          <div class="big-score">${stock.score}</div>
          <span class="grade ${gradeClass(stock.grade)}">${escapeHtml(stock.grade)}</span>
        </div>
      </div>
      <dl>
        <dt>Alpha thesis</dt>
        <dd>${escapeHtml(stock.thesis)}</dd>
        <dt>Invalidation risk</dt>
        <dd>${escapeHtml(stock.risk)}</dd>
        <dt>Next verification</dt>
        <dd>${escapeHtml(stock.next_check)}</dd>
      </dl>
    </article>`).join('');
}

function renderMethodology(weights) {
  const labels = {
    earnings_acceleration: 'Earnings acceleration',
    revenue_quality: 'Revenue quality',
    valuation: 'Valuation',
    structural_catalyst: 'Structural catalyst',
    balance_sheet_cash_flow: 'Balance sheet / cash flow',
    circle_of_competence: 'Circle of competence'
  };
  document.querySelector('#methodology').innerHTML = Object.entries(weights)
    .map(([key, value]) => `<div class="method-row"><span>${escapeHtml(labels[key] ?? key)}</span><strong>${value}</strong></div>`)
    .join('');
}

function renderWatchlist(items) {
  document.querySelector('#watchlist').innerHTML = items
    .map(item => `<div class="watch-row"><span>${escapeHtml(item.ticker)} ${escapeHtml(item.name)}</span><small>${escapeHtml(item.reason)}</small></div>`)
    .join('');
}

function dataAgeDays() {
  if (!state.data) return Infinity;
  return daysBetween(localDate(state.data.meta.as_of), new Date());
}

function renderHeader(data) {
  const top = [...data.stocks].sort((a, b) => b.score - a.score)[0];
  document.querySelector('#topAlpha').textContent = `${top.ticker} ${top.name}`;
  document.querySelector('#topAlphaScore').textContent = `Alpha Score ${top.score} · ${top.action}`;
  document.querySelector('#triggerPrice').textContent = fmt.format(data.tsmc.rotation_trigger);
  document.querySelector('#nextReview').textContent = `下一次 ${data.meta.next_review}`;

  const ref = data.tsmc.reference_price;
  const trigger = data.tsmc.rotation_trigger;
  const hit = ref >= trigger;
  const progress = Math.min(100, Math.max(0, ref / trigger * 100));
  document.querySelector('#tsmcProgress').style.width = `${progress}%`;
  document.querySelector('#tsmcReference').textContent = `參考價 ${fmt.format(ref)} / ${fmt.format(trigger)}（${data.tsmc.reference_price_date}）`;
  document.querySelector('#triggerStatus').textContent = hit
    ? '已觸發：本週必須重跑完整 Alpha'
    : `距觸發約 ${fmt.format((trigger - ref) / ref * 100)}%`;
  const pill = document.querySelector('#tsmcPill');
  pill.textContent = hit ? '已觸發' : '未觸發';
  pill.classList.toggle('hit', hit);

  const age = dataAgeDays();
  const freshness = document.querySelector('#freshness');
  freshness.textContent = age > 10 ? `⚠ 資料已 ${age} 天未更新` : `資料更新 ${data.meta.as_of}`;
  freshness.classList.toggle('stale', age > 10);

  document.querySelector('#dataMeta').innerHTML = [
    `Schema v${data.meta.schema_version ?? 1}`,
    `研究快照 ${data.meta.as_of}`,
    `市場資料 ${data.meta.market_data_as_of}`,
    `更新頻率 ${data.meta.cadence}`,
    `下次檢查 ${data.meta.next_review}`,
    `歷史快照 ${state.history.length} 份`
  ].map(text => `<span class="tag">${escapeHtml(text)}</span>`).join('');
}

function currentAndHistoricalSeries(ticker) {
  const byDate = new Map();
  for (const snapshot of state.history) {
    const stock = snapshot.stocks?.find(item => item.ticker === ticker);
    if (stock) byDate.set(snapshot.meta.as_of, { date: snapshot.meta.as_of, score: stock.score, rank: stock.rank });
  }
  const current = state.data.stocks.find(item => item.ticker === ticker);
  if (current) byDate.set(state.data.meta.as_of, { date: state.data.meta.as_of, score: current.score, rank: current.rank });
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date)).slice(-26);
}

function renderHistoryChart(ticker) {
  const stock = state.data.stocks.find(item => item.ticker === ticker);
  const series = currentAndHistoricalSeries(ticker);
  const chart = document.querySelector('#historyChart');
  const meta = document.querySelector('#historyMeta');

  if (!stock || series.length === 0) {
    chart.innerHTML = '<div class="empty-state">尚無歷史資料</div>';
    meta.innerHTML = '';
    return;
  }

  const width = 720;
  const height = 285;
  const pad = { left: 48, right: 24, top: 22, bottom: 42 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const scores = series.map(point => point.score);
  let minScore = Math.max(0, Math.floor(Math.min(...scores) / 5) * 5 - 5);
  let maxScore = Math.min(100, Math.ceil(Math.max(...scores) / 5) * 5 + 5);
  if (minScore === maxScore) {
    minScore = Math.max(0, minScore - 5);
    maxScore = Math.min(100, maxScore + 5);
  }

  const x = index => series.length === 1
    ? pad.left + plotW / 2
    : pad.left + (index / (series.length - 1)) * plotW;
  const y = score => pad.top + ((maxScore - score) / (maxScore - minScore)) * plotH;
  const coords = series.map((point, index) => `${x(index)},${y(point.score)}`).join(' ');
  const gridValues = [minScore, Math.round((minScore + maxScore) / 2), maxScore];

  const grid = gridValues.map(value => `
    <line x1="${pad.left}" y1="${y(value)}" x2="${width - pad.right}" y2="${y(value)}" class="chart-grid-line" />
    <text x="${pad.left - 9}" y="${y(value) + 4}" class="chart-axis" text-anchor="end">${value}</text>`).join('');

  const dots = series.map((point, index) => `
    <circle cx="${x(index)}" cy="${y(point.score)}" r="5" class="chart-dot">
      <title>${point.date}: Score ${point.score}, Rank #${point.rank}</title>
    </circle>`).join('');

  const first = series[0];
  const last = series.at(-1);
  chart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(stock.name)} Alpha Score 歷史曲線">
      ${grid}
      <polyline points="${coords}" class="chart-line" />
      ${dots}
      <text x="${pad.left}" y="${height - 12}" class="chart-axis">${first.date}</text>
      <text x="${width - pad.right}" y="${height - 12}" class="chart-axis" text-anchor="end">${last.date}</text>
    </svg>`;

  const delta = last.score - first.score;
  const direction = delta > 0 ? `+${delta}` : `${delta}`;
  meta.innerHTML = [
    `<span class="tag">${escapeHtml(stock.ticker)} ${escapeHtml(stock.name)}</span>`,
    `<span class="tag">最新 ${last.score}</span>`,
    `<span class="tag">期間變化 ${direction}</span>`,
    `<span class="tag">${series.length} 個觀測點</span>`
  ].join('');
}

function renderHistorySelector() {
  const select = document.querySelector('#historyTicker');
  const current = select.value;
  select.innerHTML = state.data.stocks
    .map(stock => `<option value="${escapeHtml(stock.ticker)}">${escapeHtml(stock.ticker)} ${escapeHtml(stock.name)}</option>`)
    .join('');
  if (current && state.data.stocks.some(stock => stock.ticker === current)) select.value = current;
  renderHistoryChart(select.value || state.data.stocks[0]?.ticker);
}

function renderWeeklyChanges() {
  const container = document.querySelector('#weeklyChanges');
  if (!state.previous) {
    container.innerHTML = '<div class="empty-state">2026-08-10 已建立第一份基準。下一次週報後開始產生排名、分數與 Grade 變化。</div>';
    return;
  }

  const changes = [];
  for (const stock of state.data.stocks) {
    const old = previousStock(stock.ticker);
    if (!old) {
      changes.push({ type: 'new', title: `${stock.ticker} ${stock.name}`, detail: `NEW · Score ${stock.score} · #${stock.rank}` });
      continue;
    }
    const scoreDelta = stock.score - old.score;
    const rDelta = old.rank - stock.rank;
    if (scoreDelta !== 0 || rDelta !== 0 || stock.grade !== old.grade || stock.action !== old.action) {
      const parts = [];
      if (rDelta > 0) parts.push(`排名 ↑${rDelta}`);
      if (rDelta < 0) parts.push(`排名 ↓${Math.abs(rDelta)}`);
      if (scoreDelta > 0) parts.push(`Score +${scoreDelta}`);
      if (scoreDelta < 0) parts.push(`Score ${scoreDelta}`);
      if (stock.grade !== old.grade) parts.push(`${old.grade} → ${stock.grade}`);
      if (stock.action !== old.action) parts.push(`${old.action} → ${stock.action}`);
      changes.push({
        type: scoreDelta >= 0 && rDelta >= 0 ? 'up' : 'down',
        title: `${stock.ticker} ${stock.name}`,
        detail: parts.join(' · ') || '狀態更新'
      });
    }
  }

  for (const old of state.previous.stocks ?? []) {
    if (!state.data.stocks.some(stock => stock.ticker === old.ticker)) {
      changes.push({ type: 'down', title: `${old.ticker} ${old.name}`, detail: '本週移出 Alpha universe' });
    }
  }

  if (!changes.length) {
    container.innerHTML = '<div class="empty-state">本週排名、Score 與 Grade 無變化。</div>';
    return;
  }

  container.innerHTML = changes.map(change => `
    <div class="change-row ${change.type}">
      <strong>${escapeHtml(change.title)}</strong>
      <small>${escapeHtml(change.detail)}</small>
    </div>`).join('');
}

function allocationStock(ticker) {
  return state.data.stocks.find(stock => stock.ticker === ticker) ?? null;
}

function allocationAmount(weight) {
  const capital = Math.max(0, Number(document.querySelector('#capitalInput').value) || 0);
  return capital * weight / 100;
}

function allocationPositionDetail(item, amount) {
  if (item.ticker === 'CASH') return '保留流動性';
  const stock = allocationStock(item.ticker);
  if (!stock?.reference_price) return '缺最新參考價，無法估股數';
  const shares = Math.floor(amount / stock.reference_price);
  const lots = Math.floor(shares / 1000);
  return `約 ${fmt.format(shares)} 股 · ${fmt.format(lots)} 張整股`;
}

function passesBuyGate(stock) {
  if (!stock) return false;
  return stock.score >= state.data.methodology.buy_gate && stock.action.includes('BUY');
}

function simulationValidation() {
  const model = state.data.rotation_model;
  const sum = state.allocations.reduce((total, item) => total + Number(item.weight || 0), 0);
  const cash = state.allocations.find(item => item.ticker === 'CASH')?.weight ?? 0;
  const allocatedStocks = state.allocations.filter(item => item.ticker !== 'CASH' && Number(item.weight) > 0);
  const errors = [];

  if (Math.abs(sum - 100) > 0.001) errors.push('配置總和必須等於 100%');
  if (cash < model.guardrails.cash_floor_pct) errors.push(`現金不得低於 ${model.guardrails.cash_floor_pct}%`);
  for (const item of allocatedStocks) {
    if (item.weight > model.guardrails.max_single_stock_pct) {
      errors.push(`${item.ticker} 超過單一持股 ${model.guardrails.max_single_stock_pct}% 上限`);
    }
    const stock = allocationStock(item.ticker);
    if (model.guardrails.require_buy_gate && !passesBuyGate(stock)) {
      errors.push(`${item.ticker} 尚未通過 Buy Gate`);
    }
  }
  if (dataAgeDays() > model.guardrails.max_data_age_days) {
    errors.push(`研究資料超過 ${model.guardrails.max_data_age_days} 天未更新`);
  }
  return { valid: errors.length === 0, errors, sum, cash };
}

function renderSimulationSummary() {
  const validation = simulationValidation();
  const capital = Math.max(0, Number(document.querySelector('#capitalInput').value) || 0);
  const cashWeight = state.allocations.find(item => item.ticker === 'CASH')?.weight ?? 0;
  const cashAmount = capital * cashWeight / 100;
  const invested = capital - cashAmount;
  const triggered = state.data.tsmc.reference_price >= state.data.tsmc.rotation_trigger;

  document.querySelector('#allocationTotal').textContent = `${fmt.format(validation.sum)}%`;
  document.querySelector('#allocationTotal').classList.toggle('bad-text', Math.abs(validation.sum - 100) > 0.001);
  document.querySelector('#allocationWarning').textContent = validation.valid ? '配置符合研究 guardrails' : validation.errors[0];
  document.querySelector('#cashFloor').textContent = `≥ ${state.data.rotation_model.guardrails.cash_floor_pct}%`;
  document.querySelector('#investedAmount').textContent = moneyFmt.format(invested);
  document.querySelector('#cashAmount').textContent = moneyFmt.format(cashAmount);

  const gate = document.querySelector('#gateResult');
  if (!validation.valid) {
    gate.textContent = 'BLOCKED';
    gate.className = 'bad-text';
  } else if (!triggered) {
    gate.textContent = 'PREVIEW';
    gate.className = 'warn-text';
  } else {
    gate.textContent = 'READY FOR REVIEW';
    gate.className = 'good-text';
  }

  const status = document.querySelector('#simulationStatus');
  status.textContent = triggered ? 'Triggered review' : 'Preview only';
  status.classList.toggle('hit', triggered && validation.valid);
  status.classList.toggle('blocked', !validation.valid);
}

function renderAllocations() {
  const container = document.querySelector('#allocationList');
  container.innerHTML = state.allocations.map(item => {
    const stock = item.ticker === 'CASH' ? null : allocationStock(item.ticker);
    const label = item.ticker === 'CASH' ? '現金' : `${item.ticker} ${stock?.name ?? item.name ?? ''}`;
    const amount = allocationAmount(Number(item.weight));
    const gate = item.ticker === 'CASH' ? 'LIQUIDITY' : passesBuyGate(stock) ? 'PASS' : 'WATCH';
    const gateClass = gate === 'PASS' || gate === 'LIQUIDITY' ? 'gate-pass' : 'gate-watch';
    return `
      <div class="allocation-row">
        <div class="allocation-name">
          <strong>${escapeHtml(label)}</strong>
          <span class="mini-pill ${gateClass}">${gate}</span>
        </div>
        <label class="weight-input"><input type="number" min="0" max="100" step="1" value="${Number(item.weight)}" data-allocation="${escapeHtml(item.ticker)}" /><span>%</span></label>
        <div class="allocation-amount">
          <strong>${moneyFmt.format(amount)}</strong>
          <small>${escapeHtml(allocationPositionDetail(item, amount))}</small>
        </div>
      </div>`;
  }).join('');

  container.querySelectorAll('[data-allocation]').forEach(input => {
    input.addEventListener('input', event => {
      const item = state.allocations.find(allocation => allocation.ticker === event.target.dataset.allocation);
      if (!item) return;
      item.weight = Math.max(0, Math.min(100, Number(event.target.value) || 0));
      renderAllocations();
      renderSimulationSummary();
    });
  });

  renderSimulationSummary();
}

function initSimulator() {
  const model = state.data.rotation_model;
  state.allocations = model.allocations.map(item => ({ ...item }));
  const input = document.querySelector('#capitalInput');
  input.value = model.capital_default;
  input.addEventListener('input', () => {
    renderAllocations();
  });
  renderAllocations();
}

async function loadHistory() {
  try {
    const response = await fetch(`data/history/index.json?v=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.historyIndex = await response.json();
    const entries = [...(state.historyIndex.snapshots ?? [])]
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(-26);
    const snapshots = await Promise.all(entries.map(async entry => {
      const res = await fetch(`${entry.path}?v=${Date.now()}`, { cache: 'no-store' });
      if (!res.ok) throw new Error(`${entry.path}: HTTP ${res.status}`);
      return res.json();
    }));
    state.history = snapshots.sort((a, b) => a.meta.as_of.localeCompare(b.meta.as_of));
    state.previous = [...state.history]
      .filter(snapshot => snapshot.meta.as_of < state.data.meta.as_of)
      .sort((a, b) => b.meta.as_of.localeCompare(a.meta.as_of))[0] ?? null;
  } catch (error) {
    console.warn('History load failed:', error);
    state.historyIndex = null;
    state.history = [];
    state.previous = null;
  }
}

function render() {
  if (!state.data) return;
  renderHeader(state.data);
  renderTable(state.data.stocks);
  renderCards(state.data.stocks);
  renderMethodology(state.data.methodology.weights);
  renderWatchlist(state.data.watchlist);
  renderHistorySelector();
  renderWeeklyChanges();
}

async function init() {
  try {
    const response = await fetch(`data/alpha.json?v=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    await loadHistory();
    render();
    initSimulator();
  } catch (error) {
    document.querySelector('#rankingBody').innerHTML = `<tr><td colspan="10"><div class="error">資料載入失敗：${escapeHtml(error.message)}</div></td></tr>`;
    document.querySelector('#freshness').textContent = '資料載入失敗';
    document.querySelector('#freshness').classList.add('stale');
  }
}

document.querySelectorAll('.filter').forEach(button => {
  button.addEventListener('click', () => {
    document.querySelectorAll('.filter').forEach(b => b.classList.remove('active'));
    button.classList.add('active');
    state.filter = button.dataset.filter;
    if (state.data) {
      renderTable(state.data.stocks);
      renderCards(state.data.stocks);
    }
  });
});

document.querySelector('#historyTicker').addEventListener('change', event => {
  renderHistoryChart(event.target.value);
});

init();
