const state = { data: null, filter: 'ALL' };

const fmt = new Intl.NumberFormat('zh-TW', { maximumFractionDigits: 2 });

function daysBetween(a, b) {
  return Math.floor((b - a) / 86400000);
}

function gradeClass(grade) {
  return grade === 'A' ? 'grade-a' : 'grade-b';
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

function renderTable(stocks) {
  const body = document.querySelector('#rankingBody');
  const rows = filteredStocks(stocks);
  body.innerHTML = rows.map(stock => `
    <tr>
      <td>#${stock.rank}</td>
      <td class="company"><strong>${stock.name}</strong><span>${stock.ticker}</span></td>
      <td class="score">${stock.score}</td>
      <td><span class="grade ${gradeClass(stock.grade)}">${stock.grade}</span></td>
      <td>${stock.pe_ttm == null ? '待驗證' : fmt.format(stock.pe_ttm) + 'x'}</td>
      <td class="${trendClass(stock.earnings_trend)}">${stock.earnings_trend}</td>
      <td>${stock.valuation}</td>
      <td class="${actionClass(stock.action)}"><strong>${stock.action}</strong></td>
    </tr>`).join('');
}

function renderCards(stocks) {
  const cards = document.querySelector('#stockCards');
  cards.innerHTML = filteredStocks(stocks).map(stock => `
    <article class="stock-card">
      <div class="card-top">
        <div>
          <h3>${stock.name}</h3>
          <div class="ticker">${stock.ticker} · ${stock.action}</div>
        </div>
        <div>
          <div class="big-score">${stock.score}</div>
          <span class="grade ${gradeClass(stock.grade)}">${stock.grade}</span>
        </div>
      </div>
      <dl>
        <dt>Alpha thesis</dt>
        <dd>${stock.thesis}</dd>
        <dt>Invalidation risk</dt>
        <dd>${stock.risk}</dd>
        <dt>Next verification</dt>
        <dd>${stock.next_check}</dd>
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
    .map(([key, value]) => `<div class="method-row"><span>${labels[key]}</span><strong>${value}</strong></div>`)
    .join('');
}

function renderWatchlist(items) {
  document.querySelector('#watchlist').innerHTML = items
    .map(item => `<div class="watch-row"><span>${item.ticker} ${item.name}</span><small>${item.reason}</small></div>`)
    .join('');
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
  document.querySelector('#triggerStatus').textContent = hit ? '已觸發：本週必須重跑完整 Alpha' : `距觸發約 ${fmt.format((trigger - ref) / ref * 100)}%`;
  const pill = document.querySelector('#tsmcPill');
  pill.textContent = hit ? '已觸發' : '未觸發';
  pill.classList.toggle('hit', hit);

  const asOf = new Date(`${data.meta.as_of}T00:00:00+08:00`);
  const now = new Date();
  const age = daysBetween(asOf, now);
  const freshness = document.querySelector('#freshness');
  freshness.textContent = age > 10 ? `⚠ 資料已 ${age} 天未更新` : `資料更新 ${data.meta.as_of}`;
  freshness.classList.toggle('stale', age > 10);

  document.querySelector('#dataMeta').innerHTML = [
    `研究快照 ${data.meta.as_of}`,
    `市場資料 ${data.meta.market_data_as_of}`,
    `更新頻率 ${data.meta.cadence}`,
    `下次檢查 ${data.meta.next_review}`
  ].map(text => `<span class="tag">${text}</span>`).join('');
}

function render() {
  if (!state.data) return;
  renderHeader(state.data);
  renderTable(state.data.stocks);
  renderCards(state.data.stocks);
  renderMethodology(state.data.methodology.weights);
  renderWatchlist(state.data.watchlist);
}

async function init() {
  try {
    const response = await fetch(`data/alpha.json?v=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    render();
  } catch (error) {
    document.querySelector('#rankingBody').innerHTML = `<tr><td colspan="8"><div class="error">資料載入失敗：${error.message}</div></td></tr>`;
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

init();
