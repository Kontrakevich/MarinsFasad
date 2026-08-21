(() => {
  'use strict';

  const previousFetch = window.fetch.bind(window);
  let activeProjectId = '';
  let latestProject = null;
  let sequence = 0;

  const aliases = new Map([
    ['?', 'help'], ['помощь', 'help'], ['help', 'help'],
    ['статус', 'status'], ['status', 'status'],
    ['процесс', 'process'], ['process', 'process'], ['progress', 'process'],
    ['промпт', 'prompt'], ['prompt', 'prompt'],
    ['диагностика', 'diagnostics'], ['diagnostics', 'diagnostics'], ['diag', 'diagnostics'],
    ['качество', 'quality'], ['quality', 'quality'], ['qc', 'quality'],
    ['генерировать', 'generate'], ['generate', 'generate'], ['run', 'generate'],
    ['утвердить', 'approve'], ['approve', 'approve'],
    ['проекты', 'projects'], ['projects', 'projects'],
    ['очистить', 'clear'], ['clear', 'clear'], ['cls', 'clear'],
    ['удалить', 'delete'], ['delete', 'delete'],
  ]);

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }

  function now() {
    return new Date().toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit', second: '2-digit'});
  }

  function projectIdFromUrl(value) {
    const url = typeof value === 'string' ? value : (value?.url || '');
    const match = String(url).match(/\/api\/projects\/([^/?]+)(?:[/?]|$)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function currentStage() {
    return latestProject?.active_stage
      || document.querySelector('#pipeline button.is-active')?.dataset?.stage
      || 'environment';
  }

  function commandRoot() {
    return document.getElementById('system1-command-console');
  }

  function outputNode() {
    return document.getElementById('command-console-output');
  }

  function append(kind, title, body = '', raw = false) {
    const output = outputNode();
    if (!output) return;
    sequence += 1;
    const item = document.createElement('article');
    item.className = `command-console-entry ${kind || 'info'}`;
    item.dataset.seq = String(sequence);
    item.innerHTML = `
      <header><span>${esc(now())}</span><strong>${esc(title)}</strong></header>
      <div class="command-console-body">${raw ? body : esc(body).replace(/\n/g, '<br>')}</div>
    `;
    output.appendChild(item);
    output.scrollTop = output.scrollHeight;
  }

  function setProcess(status, text = '') {
    const state = document.getElementById('command-process-state');
    const detail = document.getElementById('command-process-detail');
    if (state) {
      state.textContent = String(status || 'IDLE').toUpperCase();
      state.dataset.status = String(status || 'idle').toLowerCase();
    }
    if (detail) detail.textContent = text || 'Нет активной операции';
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

  function acceptProject(project) {
    if (!project?.id) return;
    activeProjectId = project.id;
    latestProject = project;
    updateHeader();
    renderSuggestions();
  }

  function updateHeader() {
    const project = document.getElementById('command-project');
    const stage = document.getElementById('command-stage');
    if (project) project.textContent = latestProject?.name || 'Проект не выбран';
    if (stage) stage.textContent = String(currentStage()).toUpperCase();

    const generation = latestProject?.generation || {};
    const status = generation.status || latestProject?.pipeline?.environment || 'idle';
    if (['queued', 'processing'].includes(status)) {
      const job = generation.job_id ? `JOB ${String(generation.job_id).slice(0, 8)}` : 'BACKGROUND JOB';
      setProcess(status, `${job} · генерация продолжается в фоне`);
    } else if (status === 'error') {
      setProcess('error', generation.error || 'Генерация завершилась с ошибкой');
    } else {
      setProcess(status === 'review' ? 'completed' : status, generation.completed_at ? 'Последняя генерация завершена' : 'Нет активной генерации');
    }
  }

  function suggestedCommands() {
    if (!latestProject) return ['projects', 'help'];
    const stage = currentStage();
    const generation = latestProject.generation || {};
    const status = generation.status || latestProject.pipeline?.environment || 'idle';
    if (['queued', 'processing'].includes(status)) {
      return ['process', 'diagnostics', 'prompt', 'status'];
    }
    if (status === 'error') {
      return ['diagnostics', 'process', 'prompt', 'generate'];
    }
    if (stage === 'geometry') {
      return ['status', 'diagnostics', 'approve', 'help'];
    }
    if (stage === 'environment') {
      const actions = ['prompt', 'generate', 'quality', 'diagnostics'];
      if (latestProject.assets?.environment_candidate) actions.push('approve');
      return actions;
    }
    return ['status', 'quality', 'diagnostics', 'projects'];
  }

  function renderSuggestions() {
    const node = document.getElementById('command-suggestions');
    if (!node) return;
    node.innerHTML = '';
    suggestedCommands().forEach(command => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = command;
      button.dataset.command = command;
      button.addEventListener('click', () => execute(command));
      node.appendChild(button);
    });
  }

  function helpText() {
    return [
      'status / статус           — состояние проекта и pipeline',
      'process / процесс         — активный job, retry и Run Trace',
      'prompt / промпт           — показать финальный Nano Banana prompt',
      'prompt edit               — открыть prompt в редакторе консоли',
      'prompt rebuild            — сбросить ручную правку и собрать заново',
      'comment <текст>           — добавить требование в активный этап',
      'generate / генерировать   — запустить background generation',
      'quality / qc              — проверить текущий результат',
      'diagnostics / diag        — transport/provider/System №1',
      'approve / утвердить       — утвердить текущий этап',
      'projects / проекты        — список проектов',
      'delete confirm            — удалить активный проект',
      'clear                     — очистить вывод консоли',
    ].join('\n');
  }

  async function refreshProject() {
    if (!activeProjectId) throw new Error('Проект не выбран.');
    const project = await api(`/api/projects/${encodeURIComponent(activeProjectId)}`, {cache: 'no-store'});
    acceptProject(project);
    return project;
  }

  async function commandStatus() {
    const project = await refreshProject();
    const generation = project.generation || {};
    const route = project.intent_router || project.system1_intelligence?.intent_router || null;
    const lines = [
      `PROJECT: ${project.name} (${project.id})`,
      `STAGE: ${String(project.active_stage || '—').toUpperCase()}`,
      `PIPELINE: ${Object.entries(project.pipeline || {}).map(([k,v]) => `${k}=${v}`).join(' · ')}`,
      `GENERATION: ${generation.status || 'idle'}`,
      `MODEL: ${generation.model || 'google/gemini-2.5-flash-image'}`,
    ];
    if (route) lines.push(`ROUTER: ${String(route.requested_mode || '—').toUpperCase()} → ${String(route.effective_mode || '—').toUpperCase()}`);
    append('info', 'STATUS', lines.join('\n'));
  }

  async function commandProcess() {
    if (!activeProjectId) throw new Error('Проект не выбран.');
    let status;
    try {
      status = await api(`/api/projects/${encodeURIComponent(activeProjectId)}/environment/generation-status`, {cache: 'no-store'});
      if (status.project) acceptProject(status.project);
    } catch (_) {
      const project = await refreshProject();
      status = {status: project.generation?.status || project.pipeline?.environment || 'idle', project};
    }
    const project = status.project || latestProject || {};
    const generation = project.generation || {};
    const intelligence = project.system1_intelligence || {};
    const trace = (intelligence.recent_trace || []).slice(-12);
    const transport = generation.transport || project.generation_input || {};
    const lines = [
      `STATUS: ${String(status.status || generation.status || 'idle').toUpperCase()}`,
      `JOB: ${generation.job_id || status.job_id || '—'}`,
      `STARTED: ${generation.started_at || generation.queued_at || '—'}`,
      `PROVIDER CALLS: ${generation.provider_call_count ?? transport.provider_call_count ?? '—'}`,
      `RETRIES: ${transport.provider_retry_count ?? generation.provider_retry_count ?? 0}`,
      `PROMPT SOURCE: ${generation.prompt_source || transport.prompt_source || '—'}`,
      `OUTPAINT: ${generation.outpaint ? JSON.stringify(generation.outpaint) : '—'}`,
      '',
      'RUN TRACE:',
      ...(trace.length ? trace.map(item => `${item.status || '—'} · ${item.event_type || 'event'} · ${item.component || '—'}`) : ['Нет событий.']),
    ];
    append('process', 'PROCESS', lines.join('\n'));
  }

  async function commandPrompt(edit = false) {
    if (!activeProjectId) throw new Error('Проект не выбран.');
    const stage = currentStage() === 'environment' ? 'environment' : currentStage();
    if (!['geometry', 'environment', 'branding'].includes(stage)) throw new Error('Для этого этапа prompt не используется.');
    const payload = await api(`/api/projects/${encodeURIComponent(activeProjectId)}/prompt/${stage}`, {cache: 'no-store'});
    if (!edit) {
      append('prompt', `PROMPT · ${payload.prompt_source || 'compiled'}`, payload.prompt || 'Prompt пуст.');
      return;
    }
    renderPromptEditor(payload, stage);
  }

  function renderPromptEditor(payload, stage) {
    const output = outputNode();
    if (!output) return;
    sequence += 1;
    const item = document.createElement('article');
    item.className = 'command-console-entry prompt-editor';
    item.innerHTML = `
      <header><span>${esc(now())}</span><strong>PROMPT EDITOR · ${esc(payload.prompt_source || 'compiled')}</strong></header>
      <textarea class="command-prompt-editor" spellcheck="false"></textarea>
      <div class="command-inline-actions">
        <button type="button" data-save>СОХРАНИТЬ</button>
        <button type="button" data-rebuild>СОБРАТЬ ЗАНОВО</button>
      </div>
    `;
    const textarea = item.querySelector('textarea');
    textarea.value = payload.prompt || '';
    item.querySelector('[data-save]').addEventListener('click', async () => {
      try {
        const data = new FormData();
        data.append('prompt', textarea.value.trim());
        const saved = await api(`/api/projects/${encodeURIComponent(activeProjectId)}/prompt/${stage}/edit`, {method: 'POST', body: data});
        textarea.value = saved.prompt || textarea.value;
        append('ok', 'PROMPT SAVED', 'Сохранённый текст будет отправлен Nano Banana без повторного переписывания.');
      } catch (error) { append('error', 'PROMPT ERROR', error.message); }
    });
    item.querySelector('[data-rebuild]').addEventListener('click', async () => {
      try {
        await api(`/api/projects/${encodeURIComponent(activeProjectId)}/prompt/${stage}/edit`, {method: 'DELETE'});
        const rebuilt = await api(`/api/projects/${encodeURIComponent(activeProjectId)}/prompt/${stage}`, {cache: 'no-store'});
        textarea.value = rebuilt.prompt || '';
        append('ok', 'PROMPT REBUILT', 'Ручная версия сброшена. Prompt собран из актуальных требований.');
      } catch (error) { append('error', 'PROMPT ERROR', error.message); }
    });
    output.appendChild(item);
    output.scrollTop = output.scrollHeight;
    textarea.focus();
  }

  async function commandDiagnostics() {
    if (!activeProjectId) throw new Error('Проект не выбран.');
    const data = await api(`/api/projects/${encodeURIComponent(activeProjectId)}/diagnostics`, {cache: 'no-store'});
    const generation = data.generation || {};
    const transport = data.generation_input || {};
    const intelligence = latestProject?.system1_intelligence || {};
    const lines = [
      `GENERATION: ${generation.status || 'idle'}`,
      `ERROR: ${generation.error || '—'}`,
      `REQUEST BYTES: ${transport.request_body_bytes || generation.request_body_bytes || '—'}`,
      `TRANSPORT: ${transport.transport_width || '—'}×${transport.transport_height || '—'}`,
      `PROMPT SOURCE: ${generation.prompt_source || transport.prompt_source || '—'}`,
      `PROMPT OVERRIDE: ${generation.prompt_override_active || transport.prompt_override_active ? 'YES' : 'NO'}`,
      `PROVIDER RETRIES: ${transport.provider_retry_count || 0}`,
      `L1: ${intelligence.layer1_technical?.failure_type || intelligence.layer1_technical?.status || '—'}`,
      `L2: ${intelligence.layer2_alignment?.failure_type || intelligence.layer2_alignment?.status || '—'}`,
    ];
    append(generation.error ? 'error' : 'info', 'DIAGNOSTICS', lines.join('\n'));
  }

  async function commandQuality() {
    const project = await refreshProject();
    const assets = project.assets || {};
    const key = assets.environment_candidate ? 'environment_candidate'
      : assets.geometry_candidate ? 'geometry_candidate'
      : assets.source_master ? 'source_master' : '';
    if (!key) throw new Error('Нет изображения для QC.');
    const report = await api(`/api/projects/${encodeURIComponent(activeProjectId)}/quality/${key}`, {cache: 'no-store'});
    append(report.passed === false ? 'error' : 'ok', `QUALITY · ${key}`, JSON.stringify(report, null, 2));
  }

  async function commandGenerate() {
    if (!activeProjectId) throw new Error('Проект не выбран.');
    const button = document.getElementById('environment-generate');
    if (!button || button.disabled) throw new Error('Генерация сейчас недоступна. Проверьте утверждение геометрии.');
    append('process', 'GENERATION', 'Запрос отправлен. Job будет выполняться в фоне; используйте process для подробностей.');
    button.click();
  }

  async function commandApprove() {
    const stage = currentStage();
    const id = stage === 'geometry' ? 'geometry-approve' : stage === 'environment' ? 'environment-approve' : '';
    if (!id) throw new Error('На текущем этапе нет команды утверждения.');
    const button = document.getElementById(id);
    if (!button || button.disabled) throw new Error('Нечего утверждать на текущем этапе.');
    button.click();
    append('ok', 'APPROVE', `Команда утверждения отправлена для этапа ${stage}.`);
  }

  async function commandProjects() {
    const projects = await api('/api/projects', {cache: 'no-store'});
    append('info', 'PROJECTS', (projects || []).map(item => `${item.id === activeProjectId ? '●' : '○'} ${item.name} · ${item.active_stage} · ${item.pipeline?.[item.active_stage] || '—'}`).join('\n') || 'Проектов нет.');
  }

  async function commandDelete(args) {
    if (!activeProjectId) throw new Error('Проект не выбран.');
    if (String(args || '').trim().toLowerCase() !== 'confirm') {
      append('error', 'DELETE REQUIRES CONFIRMATION', 'Для полного удаления проекта выполните: delete confirm');
      return;
    }
    const deleted = await api(`/api/projects/${encodeURIComponent(activeProjectId)}`, {method: 'DELETE'});
    append('ok', 'PROJECT DELETED', `${deleted.name || activeProjectId} удалён.`);
    activeProjectId = '';
    latestProject = null;
    setTimeout(() => window.location.reload(), 450);
  }

  async function commandComment(text) {
    const clean = String(text || '').trim();
    if (!clean) throw new Error('Использование: comment <текст требования>');
    if (!activeProjectId) throw new Error('Проект не выбран.');
    const stage = currentStage();
    if (!['geometry', 'environment', 'branding'].includes(stage)) throw new Error('На текущем этапе комментарии не поддерживаются.');
    const data = new FormData();
    data.append('comment', clean);
    const project = await api(`/api/projects/${encodeURIComponent(activeProjectId)}/comments/${stage}`, {method: 'POST', body: data});
    acceptProject(project);
    append('ok', 'COMMENT ADDED', clean);
  }

  async function execute(rawCommand) {
    const input = document.getElementById('command-input');
    const source = String(rawCommand ?? input?.value ?? '').trim();
    if (!source) return;
    if (input) input.value = '';
    append('command', 'COMMAND', `> ${source}`);

    const [headRaw, ...rest] = source.split(/\s+/);
    const head = aliases.get(headRaw.toLowerCase()) || headRaw.toLowerCase();
    const args = rest.join(' ');
    try {
      if (head === 'help') append('info', 'HELP', helpText());
      else if (head === 'status') await commandStatus();
      else if (head === 'process') await commandProcess();
      else if (head === 'prompt') {
        if (args.toLowerCase() === 'edit' || args.toLowerCase() === 'редактировать') await commandPrompt(true);
        else if (args.toLowerCase() === 'rebuild' || args.toLowerCase() === 'собрать') {
          if (!activeProjectId) throw new Error('Проект не выбран.');
          const stage = currentStage();
          await api(`/api/projects/${encodeURIComponent(activeProjectId)}/prompt/${stage}/edit`, {method: 'DELETE'});
          await commandPrompt(false);
        } else await commandPrompt(false);
      }
      else if (head === 'diagnostics') await commandDiagnostics();
      else if (head === 'quality') await commandQuality();
      else if (head === 'generate') await commandGenerate();
      else if (head === 'approve') await commandApprove();
      else if (head === 'projects') await commandProjects();
      else if (head === 'delete') await commandDelete(args);
      else if (head === 'comment' || head === 'комментарий') await commandComment(args);
      else if (head === 'clear') { if (outputNode()) outputNode().innerHTML = ''; }
      else append('error', 'UNKNOWN COMMAND', `Неизвестная команда: ${source}\nВведите help для списка команд.`);
    } catch (error) {
      append('error', 'ERROR', error?.message || String(error));
    }
    renderSuggestions();
  }

  function installConsole() {
    const pane = document.querySelector('.inspector-pane');
    if (!pane || commandRoot()) return;

    pane.querySelectorAll(':scope > .pane-heading, :scope > .inspector-tabs, :scope > .inspector-panel').forEach(node => {
      node.classList.add('command-console-legacy');
    });

    const shell = document.createElement('section');
    shell.id = 'system1-command-console';
    shell.className = 'system1-command-console';
    shell.innerHTML = `
      <header class="command-console-header">
        <div><span>SYSTEM №1</span><strong>COMMAND CONSOLE</strong></div>
        <div class="command-console-context"><b id="command-project">Проект не выбран</b><small id="command-stage">—</small></div>
      </header>
      <div class="command-process-strip">
        <span id="command-process-state" data-status="idle">IDLE</span>
        <p id="command-process-detail">Нет активной операции</p>
      </div>
      <div id="command-console-output" class="command-console-output"></div>
      <div class="command-next">
        <span>NEXT</span>
        <div id="command-suggestions" class="command-suggestions"></div>
      </div>
      <form id="command-form" class="command-form">
        <span>&gt;</span>
        <input id="command-input" autocomplete="off" spellcheck="false" placeholder="Введите команду: process, prompt, diagnostics, help">
        <button type="submit">RUN</button>
      </form>
    `;
    pane.prepend(shell);

    const style = document.createElement('style');
    style.textContent = `
      :root{--inspector:420px}
      .command-console-legacy{display:none!important}
      .inspector-pane{background:#102b43;color:#f3f2ee;overflow:hidden}
      .system1-command-console{height:100%;min-height:0;display:grid;grid-template-rows:auto auto minmax(0,1fr) auto auto;background:#102b43;color:#f3f2ee;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
      .command-console-header{display:flex;justify-content:space-between;gap:12px;padding:12px;border-bottom:1px solid #7590a4;background:#132f49}
      .command-console-header span,.command-console-header small{font-size:7px;letter-spacing:.15em;color:#9eb1bf}
      .command-console-header strong{display:block;margin-top:2px;font-size:12px;letter-spacing:.08em}
      .command-console-context{text-align:right;min-width:0}.command-console-context b{display:block;max-width:190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font:600 9px/1.4 var(--sans);color:#fff}
      .command-process-strip{display:grid;grid-template-columns:84px 1fr;align-items:center;border-bottom:1px solid #506b80;min-height:36px}.command-process-strip span{height:100%;display:grid;place-items:center;font-size:8px;font-weight:700;letter-spacing:.12em;border-right:1px solid #506b80}.command-process-strip span[data-status="processing"],.command-process-strip span[data-status="queued"]{background:#0f766e}.command-process-strip span[data-status="completed"],.command-process-strip span[data-status="approved"]{background:#25704d}.command-process-strip span[data-status="error"]{background:#9d3e34}.command-process-strip p{margin:0;padding:0 10px;font-size:8px;color:#c6d1d9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .command-console-output{min-height:0;overflow:auto;padding:8px;background:#0b2235}
      .command-console-entry{margin:0 0 8px;border-left:2px solid #58778d;padding:6px 8px;background:rgba(255,255,255,.025)}.command-console-entry header{display:flex;gap:8px;margin-bottom:5px;font-size:7px;letter-spacing:.08em;color:#91a7b7}.command-console-entry header strong{color:#dce5ea}.command-console-entry.command{border-color:#8ea6b7}.command-console-entry.ok{border-color:#58a67b}.command-console-entry.error{border-color:#d66b61}.command-console-entry.process{border-color:#42b8ae}.command-console-entry.prompt{border-color:#bda66e}.command-console-body{font-size:8px;line-height:1.52;color:#e3e9ed;word-break:break-word}
      .command-prompt-editor{width:100%;min-height:280px;resize:vertical;background:#071a29;color:#fff;border:1px solid #607b8f;padding:9px;font:8px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;outline:none}.command-prompt-editor:focus{border-color:#42b8ae}.command-inline-actions{display:flex;gap:6px;margin-top:6px}.command-inline-actions button,.command-suggestions button,.command-form button{border:1px solid #7892a5;background:transparent;color:#e8eef2;padding:5px 7px;font:7px/1.2 ui-monospace,SFMono-Regular,Consolas,monospace;letter-spacing:.06em;text-transform:uppercase}.command-inline-actions button:hover,.command-suggestions button:hover,.command-form button:hover{background:#e8eef2;color:#102b43}
      .command-next{border-top:1px solid #506b80;padding:7px 8px;background:#102b43}.command-next>span{display:block;margin-bottom:5px;font-size:6px;letter-spacing:.16em;color:#91a7b7}.command-suggestions{display:flex;flex-wrap:wrap;gap:5px}
      .command-form{display:grid;grid-template-columns:20px minmax(0,1fr) 42px;align-items:center;border-top:1px solid #7590a4;background:#071a29}.command-form>span{display:grid;place-items:center;color:#42b8ae;font-size:13px}.command-form input{height:38px;border:0;background:transparent;color:#fff;outline:none;font:9px/1 ui-monospace,SFMono-Regular,Consolas,monospace}.command-form input::placeholder{color:#70899b}.command-form button{height:100%;border-top:0;border-bottom:0;border-right:0}
    `;
    document.head.appendChild(style);

    document.getElementById('command-form')?.addEventListener('submit', event => {
      event.preventDefault();
      execute();
    });

    append('info', 'SYSTEM №1 READY', 'Командная консоль активна. Введите help или выберите следующую команду ниже.');
    renderSuggestions();
  }

  window.fetch = async function commandConsoleFetch(input, init = {}) {
    installConsole();
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

  window.addEventListener('marins-generation-status', event => {
    installConsole();
    const status = event.detail || {};
    if (status.project) acceptProject(status.project);
    const value = status.status || 'processing';
    const job = status.job_id ? `JOB ${String(status.job_id).slice(0, 8)}` : 'BACKGROUND JOB';
    if (value === 'queued' || value === 'processing') {
      setProcess(value, `${job} · работа продолжается, интерфейс свободен`);
    } else if (value === 'completed') {
      setProcess('completed', `${job} · результат готов`);
      append('ok', 'GENERATION COMPLETED', 'Результат сохранён. Проект обновляется.');
      setTimeout(() => document.querySelector('.project-card.active')?.click(), 120);
    } else if (value === 'error') {
      setProcess('error', status.error || 'Ошибка генерации');
      append('error', 'GENERATION ERROR', status.error || 'Генерация завершилась с ошибкой.');
      setTimeout(() => document.querySelector('.project-card.active')?.click(), 120);
    }
    renderSuggestions();
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', installConsole, {once: true});
  else installConsole();
})();
