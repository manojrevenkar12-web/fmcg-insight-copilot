// Insight Copilot web client. Plain JavaScript, no build step, no inline scripts (strict CSP).
'use strict';

const EXAMPLES = [
  'Which supplier had the worst OTIF last quarter?',
  'Why did OEE drop at the Vistula plant in August 2026?',
  'Purchase price variance by material in Q3 2026',
  'Net revenue by country this year vs last year',
  'How is OEE calculated?',
];

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};

let interactionId = null;

function apiKey() {
  return $('#user').value;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey(), ...(options.headers || {}) },
  });
  if (res.status === 204) return null;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(body?.error?.message || `Request failed (${res.status})`);
  return body;
}

function formatValue(v, unit) {
  if (v === null || v === undefined) return 'n/a';
  switch (unit) {
    case 'percent': return `${(v * 100).toFixed(1)}%`;
    case 'eur': return `€${Math.round(v).toLocaleString('en-GB')}`;
    case 'eur_per_kg': return `€${v.toFixed(2)}/kg`;
    case 'tonnes': return `${v.toLocaleString('en-GB', { maximumFractionDigits: 1 })} t`;
    case 'hours': return `${v.toLocaleString('en-GB', { maximumFractionDigits: 1 })} h`;
    default: return String(v);
  }
}

function renderAnswerText(text) {
  const p = $('#answer');
  p.replaceChildren();
  // Render [N1]-style citations as small marks; everything else as plain text (never innerHTML).
  for (const part of text.split(/(\[N\d+\])/)) {
    if (/^\[N\d+\]$/.test(part)) p.append(el('span', 'cite', part.slice(1, -1)));
    else if (part.startsWith('Note:')) {
      const [note, ...rest] = part.split(/(?<=\.)\s/);
      p.append(el('span', 'note', note + ' '), document.createTextNode(rest.join(' ')));
    } else p.append(document.createTextNode(part));
  }
}

function renderFigures(r) {
  const box = $('#figures');
  box.replaceChildren();
  for (const card of r.metrics) {
    const o = r.overall[card.name];
    if (!o) continue;
    const f = el('div', 'figure');
    f.append(el('b', '', o.formatted), el('span', '', `${card.label}, ${r.period}`));
    box.append(f);
  }
}

function renderChart(r) {
  const chart = $('#chart');
  chart.replaceChildren();
  const q = r.query;
  if (!q || !q.dimensions.length || !r.rows.length) return;
  const dim = q.dimensions[0];
  const metric = r.metrics[0];
  const vals = r.rows.map((row) => row[metric.name] ?? 0);
  const max = Math.max(...vals.map(Math.abs), 1e-9);
  const extreme = q.order === 'asc' ? Math.min(...vals) : Math.max(...vals);
  r.rows.forEach((row) => {
    const v = row[metric.name] ?? 0;
    const bar = el('div', 'bar');
    const track = el('div', 'track');
    const fill = el('div', 'fill' + (v === extreme && !['year', 'quarter', 'month', 'week'].includes(dim) ? ' flag' : ''));
    fill.style.width = `${Math.max(1, (Math.abs(v) / max) * 100)}%`;
    track.append(fill);
    bar.append(el('span', 'label', String(row[dim])), track, el('span', 'value', formatValue(row[metric.name], metric.unit)));
    chart.append(bar);
  });
}

function renderChecks(r) {
  const c = $('#checks');
  c.replaceChildren();
  const v = r.verification;
  if (r.status === 'answered' && r.intent === 'metric') {
    c.append(v.status === 'verified'
      ? el('span', 'ok', `All ${v.numbers_checked} numbers checked against the data`)
      : el('span', 'warn', `${v.ungrounded.length} unsupported number(s) removed before showing this answer`));
  }
  if (r.access.countries !== 'all') c.append(el('span', '', `Showing ${r.access.countries.join(', ')} only`));
  c.append(el('span', '', `Data as of ${r.data_as_of}`));
  if (r.metrics.length) c.append(el('span', '', `Owner: ${[...new Set(r.metrics.map((m) => m.owner))].join(', ')}`));
}

function renderHow(r) {
  const body = $('#how-body');
  body.replaceChildren();
  for (const m of r.metrics) {
    body.append(el('h3', '', m.label));
    body.append(el('p', '', `${m.description} Owner: ${m.owner}. Source: ${m.source_table}.`));
    const lin = el('ul', 'lineage');
    m.lineage.forEach((step) => lin.append(el('li', '', `${step.layer}: ${step.model}`)));
    m.landing_files.forEach((f) => lin.append(el('li', 'file', `landing: ${f}`)));
    body.append(lin);
  }
  if (r.sql.length) {
    body.append(el('h3', '', 'SQL that ran (parameters bound separately)'));
    r.sql.forEach((s) => body.append(el('pre', '', s)));
  }
  if (r.context.length) {
    body.append(el('h3', '', 'Context used'));
    r.context.forEach((c) => body.append(el('p', '', `[${c.id}] ${c.title} — ${c.section}: ${c.text}`)));
  }
  if (r.data_quality.length) {
    body.append(el('h3', '', 'Data quality of the sources used'));
    r.data_quality.forEach((d) => body.append(el('p', '', `${d.source}: ${d.rows_passed} of ${d.rows_received} rows passed; held back: ${d.issues || 'none'}.`)));
  }
}

async function ask(question) {
  $('#status').textContent = 'Working on it…';
  $('#result').hidden = true;
  try {
    const r = await api('/v1/ask', { method: 'POST', body: JSON.stringify({ question }) });
    interactionId = r.interaction_id;
    renderAnswerText(r.answer);
    renderFigures(r);
    renderChart(r);
    renderChecks(r);
    renderHow(r);
    document.querySelectorAll('.feedback button').forEach((b) => b.setAttribute('aria-pressed', 'false'));
    $('#result').hidden = false;
    $('#status').textContent = '';
  } catch (err) {
    $('#status').textContent = err.message;
  }
}

async function loadDataStatus() {
  try {
    const dq = await api('/v1/data-quality');
    $('#asof').textContent = `Data as of ${dq.data_as_of}. Rows failing a quality rule are held back with a reason.`;
    const tbody = $('#dq tbody');
    tbody.replaceChildren();
    dq.sources.forEach((s) => {
      const tr = el('tr');
      tr.append(el('td', '', s.source), el('td', '', s.rows_passed.toLocaleString('en-GB')), el('td', '', String(s.rows_quarantined)));
      tbody.append(tr);
    });
  } catch (err) {
    $('#asof').textContent = err.message;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  EXAMPLES.forEach((q) => {
    const b = el('button', '', q);
    b.type = 'button';
    b.addEventListener('click', () => { $('#q').value = q; ask(q); });
    $('#examples').append(b);
  });
  $('#ask-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const q = $('#q').value.trim();
    if (q.length >= 3) ask(q);
  });
  $('#user').addEventListener('change', () => { $('#result').hidden = true; loadDataStatus(); });
  document.querySelectorAll('.feedback button').forEach((b) => b.addEventListener('click', async () => {
    if (!interactionId) return;
    await api('/v1/feedback', { method: 'POST', body: JSON.stringify({ interaction_id: interactionId, rating: b.dataset.rating }) });
    document.querySelectorAll('.feedback button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  }));
  loadDataStatus();
});
