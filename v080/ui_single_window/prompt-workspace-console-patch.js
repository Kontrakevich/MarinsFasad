(() => {
  'use strict';

  const nativeFetch = window.fetch.bind(window);
  let activeProjectId = '';
  let activeProject = null;
  let loadSerial = 0;
  let bypassGenerateIntercept = false;

  function projectIdFromUrl(value) {
    const url = typeof value === 'string' ? value : (value?.url || '');
    const match = String(url).match(/\/api\/projects\/([^/?]+)(?:[/?]|$)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function currentStage() {
    return activeProject?.active_stage
      || document.querySelector('#pipeline button.is-active')?.dataset?.stage
      || 'environment';
  }

  async function api(url, options = {}) {
    const response = await nativeFetch(url, options);
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

  function nodes() {
    return {
      root: document.getElementById('command-prompt-workspace'),
      textarea: document.getElementById('command-pre-generation-prompt'),
      status: document.getElementById('command-prompt-workspace-status'),
      source: document.getElementById('command-prompt-workspace-source'),
      save: document.getElementById('command-prompt-save'),
      rebuild: document.getElementById('command-prompt-rebuild'),
      refresh: document.getElementById('command-prompt-refresh'),
    };
  }

  function setStatus(text, state = 'idle') {
    const {status} = nodes();
    if (!status) return;
    status.textContent = text;
    status.dataset.state = state;
  }

  function markDirty() {
    const {textarea} = nodes();
    if (!textarea || textarea.disabled) return;
    textarea.dataset.dirty = 'true';
    setStatus('НЕСОХРАНЁННЫЕ ИЗМЕНЕНИЯ · будут сохранены перед генерацией', 'dirty');
  }

  function isDirty() {
    return nodes().textarea?.dataset?.dirty === 'true';
  }

  async function loadPrompt({force = false} = {}) {
    installWorkspace();
    const {textarea, source} = nodes();
    if (!textarea) return null;
    if (!activeProjectId || currentStage() !== 'environment') {
      textarea.value = '';
      textarea.disabled = true;
      textarea.placeholder = 'Редактор станет доступен на этапе ОКРУЖЕНИЕ.';
      if (source) source.textContent = '—';
      setStatus('PROMPT НЕДОСТУПЕН НА ТЕКУЩЕМ ЭТАПЕ', 'idle');
      return null;
    }
    if (!force && isDirty()) return null;

    const serial = ++loadSerial;
    textarea.disabled = true;
    setStatus('ЗАГРУЗКА ФИНАЛЬНОГО PROMPT…', 'loading');
    try {
      const payload = await api(`/api/projects/${encodeURIComponent(activeProjectId)}/prompt/environment`, {cache: 'no-store'});
      if (serial !== loadSerial) return null;
      textarea.value = payload?.prompt || '';
      textarea.disabled = false;
      textarea.dataset.dirty = 'false';
      textarea.dataset.loadedProject = activeProjectId;
      textarea.placeholder = 'Отредактируйте финальный текст, который будет отправлен Nano Banana.';
      if (source) source.textContent = String(payload?.prompt_source || 'compiled').toUpperCase();
      setStatus(
        payload?.prompt_override_active
          ? 'РУЧНАЯ ВЕРСИЯ АКТИВНА · именно этот текст уйдёт в генерацию'
          : 'ГОТОВ К РЕДАКТИРОВАНИЮ · сохраните или сразу нажмите «Сгенерировать»',
        payload?.prompt_override_active ? 'saved' : 'ready',
      );
      return payload;
    } catch (error) {
      if (serial !== loadSerial) return null;
      textarea.disabled = false;
      setStatus(`ОШИБКА PROMPT: ${error.message}`, 'error');
      return null;
    }
  }

  async function savePrompt() {
    const {textarea, source} = nodes();
    if (!activeProjectId) throw new Error('Проект не выбран.');
    if (currentStage() !== 'environment') throw new Error('Prompt редактируется на этапе ОКРУЖЕНИЕ.');
    if (!textarea) throw new Error('Редактор prompt не инициализирован.');
    const prompt = textarea.value.trim();
    if (!prompt) throw new Error('Prompt не может быть пустым.');

    setStatus('СОХРАНЕНИЕ…', 'loading');
    const form = new FormData();
    form.append('prompt', prompt);
    const saved = await api(`/api/projects/${encodeURIComponent(activeProjectId)}/prompt/environment/edit`, {
      method: 'POST',
      body: form,
    });
    textarea.value = saved?.prompt || prompt;
    textarea.dataset.dirty = 'false';
    if (source) source.textContent = 'MANUAL OVERRIDE';
    setStatus('СОХРАНЕНО · этот текст будет отправлен Nano Banana', 'saved');
    return saved;
  }

  async function rebuildPrompt() {
    if (!activeProjectId) throw new Error('Проект не выбран.');
    setStatus('ПЕРЕСБОРКА…', 'loading');
    await api(`/api/projects/${encodeURIComponent(activeProjectId)}/prompt/environment/edit`, {method: 'DELETE'});
    const {textarea} = nodes();
    if (textarea) textarea.dataset.dirty = 'false';
    return loadPrompt({force: true});
  }

  async function saveIfDirtyBeforeGeneration() {
    if (currentStage() !== 'environment') return;
    const {textarea} = nodes();
    if (!textarea || textarea.disabled) {
      await loadPrompt({force: true});
      return;
    }
    if (isDirty()) await savePrompt();
  }

  function installGenerateGuard() {
    const button = document.getElementById('environment-generate');
    if (!button || button.dataset.promptGuardInstalled === 'true') return;
    button.dataset.promptGuardInstalled = 'true';
    button.addEventListener('click', async event => {
      if (bypassGenerateIntercept) {
        bypassGenerateIntercept = false;
        return;
      }
      if (currentStage() !== 'environment') return;
      event.preventDefault();
      event.stopImmediatePropagation();
      try {
        await saveIfDirtyBeforeGeneration();
        bypassGenerateIntercept = true;
        button.click();
      } catch (error) {
        setStatus(`ГЕНЕРАЦИЯ ОСТАНОВЛЕНА: ${error.message}`, 'error');
      }
    }, true);
  }

  function installWorkspace() {
    const consoleRoot = document.getElementById('system1-command-console');
    const output = document.getElementById('command-console-output');
    if (!consoleRoot || !output || document.getElementById('command-prompt-workspace')) return;

    const workspace = document.createElement('section');
    workspace.id = 'command-prompt-workspace';
    workspace.className = 'command-prompt-workspace';
    workspace.innerHTML = `
      <header class="command-prompt-workspace-header">
        <div><span>BEFORE GENERATION</span><strong>FINAL NANO BANANA PROMPT</strong></div>
        <b id="command-prompt-workspace-source">—</b>
      </header>
      <textarea id="command-pre-generation-prompt" spellcheck="false" disabled placeholder="Загрузка prompt…"></textarea>
      <div class="command-prompt-workspace-footer">
        <span id="command-prompt-workspace-status" data-state="idle">PROMPT ЕЩЁ НЕ ЗАГРУЖЕН</span>
        <div>
          <button id="command-prompt-refresh" type="button">ОБНОВИТЬ</button>
          <button id="command-prompt-rebuild" type="button">СОБРАТЬ ЗАНОВО</button>
          <button id="command-prompt-save" type="button">СОХРАНИТЬ</button>
        </div>
      </div>
    `;
    consoleRoot.insertBefore(workspace, output);

    const style = document.createElement('style');
    style.textContent = `
      .system1-command-console{grid-template-rows:auto auto minmax(190px,28vh) minmax(0,1fr) auto auto!important}
      .command-prompt-workspace{min-height:0;display:grid;grid-template-rows:auto minmax(100px,1fr) auto;border-bottom:1px solid #7590a4;background:#0d263a;color:#eef3f6}
      .command-prompt-workspace-header{display:flex;justify-content:space-between;gap:10px;padding:8px 10px;border-bottom:1px solid #506b80;background:#102f48}
      .command-prompt-workspace-header span{display:block;color:#90a8b8;letter-spacing:.12em;text-transform:uppercase}
      .command-prompt-workspace-header strong{display:block;margin-top:2px;color:#fff;letter-spacing:.04em}
      .command-prompt-workspace-header b{align-self:center;max-width:42%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#66c8bf;font-weight:600;text-align:right}
      #command-pre-generation-prompt{width:100%;min-height:0;resize:none;border:0;background:#071a29;color:#fff;padding:10px;outline:none;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;line-height:1.45}
      #command-pre-generation-prompt:focus{box-shadow:inset 0 0 0 1px #42b8ae}
      #command-pre-generation-prompt:disabled{opacity:.55;cursor:not-allowed}
      .command-prompt-workspace-footer{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;padding:7px 9px;border-top:1px solid #506b80}
      .command-prompt-workspace-footer>span{min-width:0;white-space:normal;overflow-wrap:anywhere;color:#a9bbc7}
      .command-prompt-workspace-footer>span[data-state="dirty"]{color:#f1c66d}
      .command-prompt-workspace-footer>span[data-state="saved"]{color:#78d09c}
      .command-prompt-workspace-footer>span[data-state="error"]{color:#e98980}
      .command-prompt-workspace-footer>div{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}
      .command-prompt-workspace-footer button{min-height:32px;border:1px solid #7892a5;background:transparent;color:#eef3f6;padding:5px 7px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;text-transform:uppercase}
      .command-prompt-workspace-footer button:hover{background:#eef3f6;color:#102b43}
      #command-prompt-save{border-color:#42b8ae!important;background:#0f5f5b!important}
      @media (max-height:760px){.system1-command-console{grid-template-rows:auto auto minmax(150px,23vh) minmax(0,1fr) auto auto!important}}
    `;
    document.head.appendChild(style);

    const {textarea, save, rebuild, refresh} = nodes();
    textarea?.addEventListener('input', markDirty);
    save?.addEventListener('click', () => savePrompt().catch(error => setStatus(`ОШИБКА: ${error.message}`, 'error')));
    rebuild?.addEventListener('click', () => rebuildPrompt().catch(error => setStatus(`ОШИБКА: ${error.message}`, 'error')));
    refresh?.addEventListener('click', () => loadPrompt({force: true}));
    installGenerateGuard();
  }

  function acceptProject(project) {
    if (!project?.id) return;
    const changed = project.id !== activeProjectId;
    activeProjectId = project.id;
    activeProject = project;
    installWorkspace();
    installGenerateGuard();
    const {textarea} = nodes();
    const wrongProject = textarea?.dataset?.loadedProject !== activeProjectId;
    if (changed || wrongProject || (!isDirty() && currentStage() === 'environment')) {
      loadPrompt({force: changed || wrongProject});
    }
  }

  window.fetch = async function promptWorkspaceConsoleFetch(input, init = {}) {
    installWorkspace();
    installGenerateGuard();
    const id = projectIdFromUrl(input);
    if (id) activeProjectId = id;
    const response = await nativeFetch(input, init);
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
    if (event.detail?.project) acceptProject(event.detail.project);
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      installWorkspace();
      installGenerateGuard();
    }, {once: true});
  } else {
    installWorkspace();
    installGenerateGuard();
  }
})();
