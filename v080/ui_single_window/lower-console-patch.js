(() => {
  'use strict';

  const previousFetch = window.fetch.bind(window);
  let activeProjectId = '';
  let latestProject = null;

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }

  function now() {
    return new Date().toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  }

  function projectIdFromUrl(value) {
    const url = typeof value === 'string' ? value : (value?.url || '');
    const match = String(url).match(/\/api\/projects\/([^/?]+)(?:[/?]|$)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  async function api(url, options = {}) {
    const response = await previousFetch(url, options);
    const text = await response.text();
    if (!response.ok) {
      let message = text || `HTTP ${response.status}`;
      try {
        const payload = JSON.parse(text);
        message = payload.detail || payload.message || message;
      } catch (_) {}
      throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
    }
    if (!text) return null;
    try { return JSON.parse(text); } catch (_) { return text; }
  }

  function output() {
    return document.getElementById('command-console-output');
  }

  function append(kind, title, body = '', raw = false) {
    const target = output();
    if (!target) return;
    const item = document.createElement('article');
    item.className = `command-console-entry ${kind || 'info'}`;
    item.innerHTML = `
      <header><span>${esc(now())}</span><strong>${esc(title)}</strong></header>
      <div class="command-console-body">${raw ? body : esc(body).replace(/\n/g, '<br>')}</div>
    `;
    target.appendChild(item);
    target.scrollTop = target.scrollHeight;
  }

  function acceptProject(project) {
    if (!project?.id) return;
    activeProjectId = project.id;
    latestProject = project;
  }

  async function ensureProject() {
    if (!activeProjectId) throw new Error('Проект не выбран.');
    latestProject = await api(`/api/projects/${encodeURIComponent(activeProjectId)}`, {cache:'no-store'});
    return latestProject;
  }

  function eventLine(item, index) {
    const stamp = item.created_at || item.timestamp || item.at || item.time || '—';
    const type = item.event_type || item.type || item.event || item.name || `event-${index + 1}`;
    const payload = item.payload || item.data || item.details || item;
    let summary = '';
    try { summary = JSON.stringify(payload); } catch (_) { summary = String(payload || ''); }
    if (summary.length > 320) summary = `${summary.slice(0, 317)}…`;
    return `${stamp} · ${type}${summary ? `\n  ${summary}` : ''}`;
  }

  async function commandHistory() {
    if (!activeProjectId) throw new Error('Проект не выбран.');
    const history = await api(`/api/projects/${encodeURIComponent(activeProjectId)}/history?limit=60`, {cache:'no-store'});
    const rows = Array.isArray(history) ? history : [];
    const recent = rows.slice(-30).reverse();
    append('info', `HISTORY · ${recent.length}`, recent.length ? recent.map(eventLine).join('\n\n') : 'История проекта пуста.');
  }

  async function commandEvents() {
    if (!activeProjectId) throw new Error('Проект не выбран.');
    const history = await api(`/api/projects/${encodeURIComponent(activeProjectId)}/history?limit=100`, {cache:'no-store'});
    const rows = Array.isArray(history) ? history : [];
    append('info', `EVENTS · ${rows.length}`, JSON.stringify(rows.slice(-50), null, 2));
  }

  async function commandCandidates() {
    const project = await ensureProject();
    const assets = project.assets || {};
    const keys = Object.keys(assets).filter(key => /candidate|preview|master/i.test(key));
    if (!keys.length) {
      append('info', 'CANDIDATES', 'Кандидаты изображений отсутствуют.');
      return;
    }
    const html = keys.map(key => {
      const value = assets[key];
      const href = `/api/projects/${encodeURIComponent(activeProjectId)}/assets/${encodeURIComponent(key)}`;
      return `<div class="command-candidate-row"><b>${esc(key)}</b><span>${esc(value)}</span><a href="${href}" target="_blank" rel="noopener">ОТКРЫТЬ</a></div>`;
    }).join('');
    append('info', `CANDIDATES · ${keys.length}`, `<div class="command-candidate-list">${html}</div>`, true);
  }

  function normalize(raw) {
    const first = String(raw || '').trim().split(/\s+/)[0]?.toLowerCase() || '';
    if (['history','история','timeline'].includes(first)) return 'history';
    if (['candidates','candidate','кандидаты','кандидат'].includes(first)) return 'candidates';
    if (['events','event','события','событие'].includes(first)) return 'events';
    return '';
  }

  async function executeExtended(raw) {
    const command = normalize(raw);
    if (!command) return false;
    append('command', 'COMMAND', `> ${String(raw).trim()}`);
    try {
      if (command === 'history') await commandHistory();
      else if (command === 'candidates') await commandCandidates();
      else if (command === 'events') await commandEvents();
    } catch (error) {
      append('error', 'ERROR', error?.message || String(error));
    }
    return true;
  }

  function installSuggestionButtons() {
    const host = document.getElementById('command-suggestions');
    if (!host) return;
    for (const command of ['history', 'candidates', 'events']) {
      if (host.querySelector(`[data-lower-console-command="${command}"]`)) continue;
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.lowerConsoleCommand = command;
      button.textContent = command;
      button.addEventListener('click', () => executeExtended(command));
      host.appendChild(button);
    }
  }

  function install() {
    const style = document.createElement('style');
    style.textContent = `
      .bottom-pane{display:none!important}
      .workspace-layout{grid-template-rows:minmax(0,1fr)!important}
      .projects-pane{grid-row:1!important}
      .command-candidate-list{display:grid;gap:7px}
      .command-candidate-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:3px 8px;padding:7px;border:1px solid #506b80}
      .command-candidate-row b{grid-column:1/2;color:#fff}
      .command-candidate-row span{grid-column:1/2;color:#9eb1bf;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .command-candidate-row a{grid-column:2/3;grid-row:1/3;align-self:center;color:#dce5ea;text-decoration:none;border:1px solid #7892a5;padding:5px 7px}
      .command-candidate-row a:hover{background:#e8eef2;color:#102b43}
    `;
    document.head.appendChild(style);

    const form = document.getElementById('command-form');
    if (form) {
      form.addEventListener('submit', event => {
        const input = document.getElementById('command-input');
        const raw = String(input?.value || '').trim();
        if (!normalize(raw)) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        if (input) input.value = '';
        executeExtended(raw);
      }, true);
    }

    installSuggestionButtons();
    const observer = new MutationObserver(() => installSuggestionButtons());
    const suggestions = document.getElementById('command-suggestions');
    if (suggestions) observer.observe(suggestions, {childList:true});
  }

  window.fetch = async function lowerConsoleFetch(input, init = {}) {
    const id = projectIdFromUrl(input);
    if (id) activeProjectId = id;
    const response = await previousFetch(input, init);
    const url = typeof input === 'string' ? input : (input?.url || '');
    if (!url.includes('/assets/')) {
      try {
        const payload = await response.clone().json();
        if (payload?.id && payload?.pipeline) acceptProject(payload);
        if (payload?.project?.id && payload?.project?.pipeline) acceptProject(payload.project);
      } catch (_) {}
    }
    return response;
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, {once:true});
  else install();
})();
