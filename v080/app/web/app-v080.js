(() => {
  'use strict';
  let current = null;
  const $ = id => document.getElementById(id);
  const api = async (url, options = {}) => {
    const response = await fetch(url, options);
    if (!response.ok) throw new Error(await response.text());
    const type = response.headers.get('content-type') || '';
    return type.includes('application/json') ? response.json() : response.text();
  };
  const show = (el, value = true) => el && el.classList.toggle('hidden', !value);
  const notify = (title, description = '') => {
    if ($('action-title')) $('action-title').textContent = title;
    if ($('action-description')) $('action-description').textContent = description;
  };
  const assetUrl = key => current?.assets?.[key] ? `/api/projects/${current.id}/assets/${key}?v=${Date.now()}` : '';

  async function health() {
    try {
      const data = await api('/api/health');
      const node = $('health');
      if (node) {
        node.classList.toggle('ok', data.runtime === 'standalone-v080');
        node.classList.toggle('bad', data.runtime !== 'standalone-v080');
        node.lastChild.textContent = data.runtime === 'standalone-v080' ? 'Система работает' : 'Runtime mismatch';
      }
    } catch (_) {
      $('health')?.classList.add('bad');
    }
  }

  function renderStageStrip() {
    const strip = $('stage-strip');
    if (!strip || !current) return;
    const labels = {source:'ИСХОДНИК', geometry:'ГЕОМЕТРИЯ', environment:'ОКРУЖЕНИЕ', final:'FINAL', branding:'ВЫВЕСКА'};
    strip.innerHTML = Object.entries(labels).map(([key,label]) => {
      const status = current.pipeline?.[key] || 'locked';
      return `<div class="stage-cell ${status}"><small>${label}</small><strong>${status}</strong></div>`;
    }).join('');
  }

  function setImage(id, key) {
    const img = $(id);
    if (!img) return;
    const url = assetUrl(key);
    if (url) { img.src = url; img.hidden = false; }
    else img.removeAttribute('src');
  }

  function renderProject() {
    if (!current) return;
    $('project-title').textContent = current.name;
    show($('onboarding'), false);
    show($('workspace'), true);
    renderStageStrip();
    const master = current.master_canvas;
    $('source-status').textContent = master ? `Оригинал: ${master.width} × ${master.height}. Production policy: original resolution.` : 'Файл не загружен.';
    const sourceKey = current.assets?.source_master ? 'source_master' : 'source_preview';
    setImage('geometry-before', sourceKey);
    setImage('geometry-after', current.assets?.geometry_output ? 'geometry_output' : sourceKey);
    setImage('environment-before', current.assets?.geometry_output ? 'geometry_output' : sourceKey);
    setImage('environment-after', current.assets?.environment_output ? 'environment_output' : sourceKey);
    setImage('branding-before', current.assets?.environment_output ? 'environment_output' : sourceKey);
    setImage('branding-after', current.assets?.branding_output ? 'branding_output' : 'environment_output');
    show($('geometry-empty'), !current.assets?.source_master);
    show($('geometry-editor'), !!current.assets?.source_master);
  }

  async function selectProject(id) {
    current = await api(`/api/projects/${id}`);
    renderProject();
    await loadProjects();
  }

  async function loadProjects() {
    const projects = await api('/api/projects');
    const list = $('project-list');
    if (!list) return;
    list.innerHTML = '';
    projects.forEach(project => {
      const button = document.createElement('button');
      button.className = `project-chip${current?.id === project.id ? ' active' : ''}`;
      button.textContent = project.name;
      button.onclick = () => selectProject(project.id).catch(error => alert(error.message));
      list.appendChild(button);
    });
  }

  async function createProject() {
    const name = prompt('Название проекта');
    if (!name) return;
    const data = new FormData(); data.append('name', name);
    current = await api('/api/projects', {method:'POST', body:data});
    await loadProjects(); renderProject();
  }

  async function uploadSource() {
    if (!current) return alert('Сначала создайте проект.');
    const file = $('source-file')?.files?.[0];
    if (!file) return alert('Выберите изображение.');
    notify('Загрузка оригинала', `${file.name} · ${(file.size/1048576).toFixed(1)} MB`);
    const data = new FormData(); data.append('file', file);
    current = await api(`/api/projects/${current.id}/source`, {method:'POST', body:data});
    renderProject(); notify('Исходник загружен', 'Оригинальное разрешение сохранено.');
  }

  async function addRevision(stage) {
    if (!current) return;
    const field = $(`${stage}-comment`);
    const comment = field?.value?.trim();
    if (!comment) return alert('Введите комментарий.');
    const data = new FormData(); data.append('comment', comment);
    current = await api(`/api/projects/${current.id}/comments/${stage}`, {method:'POST', body:data});
    if (field) field.value = '';
    renderProject(); notify('Комментарий принят', 'Он включён в compiled prompt этапа.');
  }

  async function compile(stage) {
    if (!current) return;
    const result = await api(`/api/projects/${current.id}/prompt/${stage}`);
    const target = $(`${stage}-prompt`);
    if (target) target.value = result.prompt || '';
    return result;
  }

  async function setStage(stage, status) {
    if (!current) return;
    const data = new FormData(); data.append('status', status);
    current = await api(`/api/projects/${current.id}/stages/${stage}`, {method:'POST', body:data});
    renderProject();
  }

  async function loadHistory() {
    if (!current) return;
    const events = await api(`/api/projects/${current.id}/history`);
    const target = $('history-list');
    if (!target) return;
    target.innerHTML = events.map(event => `<article class="history-entry"><time>${event.timestamp || ''}</time><strong>${event.type || event.event_type || 'Event'}</strong><pre>${JSON.stringify(event.payload || {}, null, 2)}</pre></article>`).join('') || '<div class="empty-note">История пуста.</div>';
  }

  $('new-project') && ($('new-project').onclick = () => createProject().catch(error => alert(error.message)));
  $('upload-source') && ($('upload-source').onclick = () => uploadSource().catch(error => alert(error.message)));
  $('environment-refresh-prompt') && ($('environment-refresh-prompt').onclick = () => compile('environment').catch(error => alert(error.message)));
  $('branding-setup') && ($('branding-setup').onclick = () => compile('branding').catch(error => alert(error.message)));
  $('refresh-history') && ($('refresh-history').onclick = () => loadHistory().catch(error => alert(error.message)));
  document.querySelectorAll('.revise-stage').forEach(button => button.onclick = () => addRevision(button.dataset.stage).catch(error => alert(error.message)));
  document.querySelectorAll('.approve-stage').forEach(button => button.onclick = () => setStage(button.dataset.stage, 'approved').catch(error => alert(error.message)));

  // Deterministic geometry canvas placeholder: exact v0.7 UI remains; v0.8 geometry engine attaches here.
  $('geometry-reset') && ($('geometry-reset').onclick = () => notify('Perspective Grid', 'Сетка сброшена.'));
  $('geometry-undo') && ($('geometry-undo').onclick = () => notify('Undo', 'История геометрии готова к подключению.'));
  $('geometry-redo') && ($('geometry-redo').onclick = () => notify('Redo', 'История геометрии готова к подключению.'));
  $('geometry-apply') && ($('geometry-apply').onclick = () => notify('Geometry', 'Модуль трансформации v0.8 подключается к сохранённой оболочке v0.7.'));
  $('environment-generate') && ($('environment-generate').onclick = async () => { await compile('environment'); notify('Environment', 'Prompt собран. Генерация запускается через AI Engine v0.8.'); });
  $('branding-generate') && ($('branding-generate').onclick = async () => { await compile('branding'); notify('Branding', 'Prompt собран. Генерация запускается через AI Engine v0.8.'); });

  Promise.all([health(), loadProjects()]).catch(error => console.error(error));
})();
