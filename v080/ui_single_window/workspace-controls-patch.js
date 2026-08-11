(() => {
  'use strict';

  let activeProjectId = null;
  const nativeFetch = window.fetch.bind(window);

  function stage() {
    return document.querySelector('#pipeline button.is-active')?.dataset?.stage || 'environment';
  }

  function rememberProjectFromUrl(value) {
    const url = typeof value === 'string' ? value : (value?.url || '');
    const match = String(url).match(/\/api\/projects\/([^/?]+)(?:[/?]|$)/);
    if (match) activeProjectId = decodeURIComponent(match[1]);
  }

  window.fetch = async function patchedWorkspaceFetch(input, init) {
    rememberProjectFromUrl(input);
    const response = await nativeFetch(input, init);
    return response;
  };

  async function api(url, options = {}) {
    rememberProjectFromUrl(url);
    const response = await window.fetch(url, options);
    const text = await response.text();
    if (!response.ok) {
      let message = text || `HTTP ${response.status}`;
      try {
        const data = JSON.parse(text);
        message = data.detail || data.message || message;
      } catch (_) {}
      throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
    }
    if (!text) return null;
    try { return JSON.parse(text); } catch (_) { return text; }
  }

  function formData(values) {
    const data = new FormData();
    Object.entries(values).forEach(([key, value]) => data.append(key, value));
    return data;
  }

  function currentPromptText() {
    return (document.getElementById('prompt-output')?.textContent || '').trim();
  }

  function setPromptStatus(text) {
    const node = document.getElementById('prompt-edit-status');
    if (node) node.textContent = text;
  }

  async function savePromptEdit() {
    if (!activeProjectId) throw new Error('Не удалось определить активный проект.');
    const prompt = currentPromptText();
    if (!prompt || prompt === 'Prompt ещё не собран.') throw new Error('Сначала соберите prompt.');
    const result = await api(`/api/projects/${encodeURIComponent(activeProjectId)}/prompt/${stage()}/edit`, {
      method: 'POST',
      body: formData({prompt}),
    });
    document.getElementById('prompt-output').textContent = result.prompt || prompt;
    setPromptStatus('Сохранено · именно этот Nano Banana prompt уйдёт в генерацию');
  }

  async function rebuildPrompt() {
    if (!activeProjectId) throw new Error('Не удалось определить активный проект.');
    await api(`/api/projects/${encodeURIComponent(activeProjectId)}/prompt/${stage()}/edit`, {method: 'DELETE'});
    setPromptStatus('Ручная правка сброшена');
    document.getElementById('compile-prompt')?.click();
  }

  async function deleteProject() {
    if (!activeProjectId) throw new Error('Не удалось определить активный проект.');
    const name = document.getElementById('project-title')?.textContent?.trim() || activeProjectId;
    if (!window.confirm(`Удалить проект «${name}» полностью?\n\nБудут удалены исходники, генерации, prompts, диагностика и история проекта.`)) return;
    await api(`/api/projects/${encodeURIComponent(activeProjectId)}`, {method: 'DELETE'});
    activeProjectId = null;
    window.location.reload();
  }

  function installPromptEditor() {
    const output = document.getElementById('prompt-output');
    const panel = document.querySelector('.inspector-panel[data-panel="prompt"]');
    const actions = panel?.querySelector('.inspector-actions');
    if (!output || !actions || document.getElementById('save-prompt-edit')) return;

    output.contentEditable = 'true';
    output.spellcheck = false;
    output.setAttribute('role', 'textbox');
    output.setAttribute('aria-multiline', 'true');
    output.style.minHeight = '360px';
    output.style.maxHeight = '58vh';
    output.style.overflow = 'auto';
    output.style.whiteSpace = 'pre-wrap';
    output.style.outline = 'none';
    output.style.cursor = 'text';
    output.title = 'Редактируется финальный prompt, который отправляется Nano Banana';

    const save = document.createElement('button');
    save.id = 'save-prompt-edit';
    save.className = 'button button-dark';
    save.type = 'button';
    save.textContent = 'Сохранить правку';
    save.onclick = () => savePromptEdit().catch(error => window.alert(error.message));

    const rebuild = document.createElement('button');
    rebuild.id = 'rebuild-prompt';
    rebuild.className = 'button button-secondary';
    rebuild.type = 'button';
    rebuild.textContent = 'Собрать заново';
    rebuild.onclick = () => rebuildPrompt().catch(error => window.alert(error.message));

    const status = document.createElement('span');
    status.id = 'prompt-edit-status';
    status.textContent = 'Редактируется финальный Nano Banana prompt';

    actions.appendChild(save);
    actions.appendChild(rebuild);
    actions.appendChild(status);

    output.addEventListener('input', () => setPromptStatus('Есть несохранённые изменения'));
  }

  function installDeleteButton() {
    const target = document.querySelector('.workspace-state');
    if (!target || document.getElementById('delete-project')) return;
    const button = document.createElement('button');
    button.id = 'delete-project';
    button.type = 'button';
    button.className = 'button button-secondary';
    button.textContent = 'Удалить проект';
    button.style.marginLeft = '12px';
    button.onclick = () => deleteProject().catch(error => window.alert(error.message));
    target.appendChild(button);
  }

  installPromptEditor();
  installDeleteButton();
})();
