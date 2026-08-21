(() => {
  'use strict';

  const previousFetch = window.fetch.bind(window);
  let activeProjectId = '';
  let latestIntelligence = null;
  let latestIntentRoute = null;

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }

  function installPanel() {
    const tabs = document.querySelector('.inspector-tabs');
    if (!tabs || document.querySelector('[data-tab="intelligence"]')) return;

    const button = document.createElement('button');
    button.dataset.tab = 'intelligence';
    button.textContent = 'SYSTEM №1';
    tabs.appendChild(button);

    const diagnostics = document.querySelector('.inspector-panel[data-panel="diagnostics"]');
    if (!diagnostics?.parentNode) return;
    const panel = document.createElement('section');
    panel.className = 'inspector-panel';
    panel.dataset.panel = 'intelligence';
    panel.innerHTML = `
      <div class="inspector-actions">
        <button id="refresh-system1" class="button button-primary">Обновить</button>
        <span>L1 TECH → L2 ALIGNMENT</span>
      </div>
      <div id="system1-output" class="system1-output">System №1 ещё не получил данные запуска.</div>
    `;
    diagnostics.parentNode.insertBefore(panel, diagnostics.nextSibling);

    button.addEventListener('click', () => {
      document.querySelectorAll('.inspector-tabs button').forEach(node => node.classList.toggle('active', node === button));
      document.querySelectorAll('.inspector-panel').forEach(node => node.classList.toggle('active', node === panel));
      render(latestIntelligence);
    });

    panel.querySelector('#refresh-system1')?.addEventListener('click', async () => {
      if (!activeProjectId) return;
      try {
        const response = await previousFetch(`/api/projects/${activeProjectId}`, {cache: 'no-store'});
        if (!response.ok) return;
        const project = await response.json();
        acceptProject(project);
      } catch (_) {}
    });

    const style = document.createElement('style');
    style.textContent = `
      .system1-output{display:grid;gap:8px;padding-top:8px;font-size:9px;line-height:1.45}
      .system1-card{border:1px solid var(--ink);padding:8px;background:var(--paper)}
      .system1-card header{display:flex;justify-content:space-between;gap:8px;margin-bottom:6px;font-size:7px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-2)}
      .system1-card strong{display:block;margin:3px 0;font-size:9px}
      .system1-card p{margin:3px 0;white-space:normal}
      .system1-state{font-weight:700}
      .system1-trace{max-height:150px;overflow:auto;border-top:1px solid var(--ink);margin-top:6px;padding-top:5px;font-family:monospace;font-size:7px}
    `;
    document.head.appendChild(style);
  }

  function diagnosisCard(title, data, fallback) {
    if (!data) return `<div class="system1-card"><header><span>${esc(title)}</span><span>—</span></header><p>${esc(fallback)}</p></div>`;
    const state = data.status || '—';
    const cause = data.failure_type || data.root_cause || 'нет технической причины';
    const why = data.why || data.desired_change || '';
    const route = data.repair_route?.route || data.repair?.target || '';
    return `<div class="system1-card"><header><span>${esc(title)}</span><span class="system1-state">${esc(state)}</span></header><strong>${esc(cause)}</strong><p>${esc(why)}</p>${route ? `<p>ROUTE: ${esc(route)}</p>` : ''}</div>`;
  }

  function intentRouterCard(route) {
    if (!route) {
      return '<div class="system1-card"><header><span>INTENT → SKILL</span><span>—</span></header><p>Маршрутизация появится после компиляции prompt.</p></div>';
    }
    const requested = String(route.requested_mode || '—').toUpperCase();
    const effective = String(route.effective_mode || '—').toUpperCase();
    const status = route.auto_routed ? 'AUTO ROUTED' : 'UNCHANGED';
    const signals = (route.signals || []).join(', ') || 'no conflict';
    return `<div class="system1-card"><header><span>INTENT → SKILL</span><span class="system1-state">${esc(status)}</span></header><strong>${esc(requested)} → ${esc(effective)}</strong><p>${esc(signals)}</p><p>${esc(route.reason || '')}</p></div>`;
  }

  function render(data) {
    installPanel();
    const output = document.getElementById('system1-output');
    if (!output) return;
    if (!data && !latestIntentRoute) {
      output.textContent = 'System №1 ещё не получил данные запуска.';
      return;
    }
    const run = data?.latest_run;
    const feedback = data?.latest_feedback;
    const trace = (data?.recent_trace || []).slice(-8);
    const layer2State = feedback?.analysis?.status === 'GATED_BY_LAYER1'
      ? 'Layer 2 заблокирован: Layer 1 уже нашёл техническую причину.'
      : 'Layer 2 запускается только после чистого Layer 1.';
    output.innerHTML = `
      <div class="system1-card"><header><span>PIPELINE</span><span>v${esc(data?.version || '1.0.0')}</span></header><strong>L1 TECHNICAL → L2 HUMAN ALIGNMENT</strong><p>${esc(layer2State)}</p><p>RUN: ${esc(run?.run_id || '—')} · ${esc(run?.status || 'idle')}</p></div>
      ${intentRouterCard(latestIntentRoute)}
      ${diagnosisCard('LAYER 1 · TECHNICAL', data?.layer1_technical, 'Техническая диагностика появится после генерации.')}
      ${diagnosisCard('LAYER 2 · ALIGNMENT', data?.layer2_alignment, 'Не запускался или пока заблокирован Layer 1.')}
      <div class="system1-card"><header><span>LEARNING</span><span>SAFE</span></header><p>Regression cases: ${esc(data?.counts?.regressions || 0)}</p><p>Preference candidates: ${esc(data?.counts?.preferences || 0)}</p><p>Постоянные правила автоматически не продвигаются.</p></div>
      <div class="system1-card"><header><span>RUN TRACE</span><span>${esc(data?.counts?.events || 0)} events</span></header><div class="system1-trace">${trace.length ? trace.map(item => `${esc(item.status)} · ${esc(item.event_type)} · ${esc(item.component)}`).join('<br>') : 'Нет событий.'}</div></div>
    `;
  }

  function acceptProject(project) {
    if (!project) return;
    if (project.id) activeProjectId = project.id;
    if (project.system1_intelligence) {
      latestIntelligence = project.system1_intelligence;
      render(latestIntelligence);
    }
  }

  window.fetch = async function system1Fetch(input, init = {}) {
    installPanel();
    const response = await previousFetch(input, init);
    const url = typeof input === 'string' ? input : input?.url || '';
    const projectMatch = url.match(/\/api\/projects\/([^/?]+)/);
    if (projectMatch?.[1]) activeProjectId = projectMatch[1];
    if (!url.includes('/assets/')) {
      try {
        const payload = await response.clone().json();
        if (payload?.intent_router) {
          latestIntentRoute = payload.intent_router;
          render(latestIntelligence);
        }
        if (payload?.system1_intelligence) acceptProject(payload);
        if (payload?.project?.system1_intelligence) acceptProject(payload.project);
      } catch (_) {}
    }
    return response;
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installPanel, {once: true});
  } else {
    installPanel();
  }
})();