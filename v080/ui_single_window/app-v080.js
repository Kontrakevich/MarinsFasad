(() => {
  'use strict';

  const $ = id => document.getElementById(id);
  const STAGES = ['source', 'geometry', 'environment', 'final', 'branding'];
  const STAGE_LABELS = {
    source: 'Исходник',
    geometry: 'Геометрия',
    environment: 'Окружение',
    final: 'Final',
    branding: 'Вывеска'
  };
  const VIEW_CONFIG = {
    source: ['original'],
    geometry: ['grid', 'result', 'split'],
    environment: ['original', 'result', 'generation', 'split'],
    final: ['original', 'result', 'split'],
    branding: ['original', 'result', 'split']
  };

  let current = null;
  let projectsCache = [];
  let currentStage = 'source';
  let currentView = 'original';
  let selectedAssetKey = null;
  let fitMode = true;
  let zoomFactor = 1;

  const geo = {
    image: null,
    corners: [],
    drag: -1,
    history: [],
    future: [],
    projectId: null,
    sourcePath: null
  };

  async function api(url, options = {}) {
    const response = await fetch(url, options);
    const text = await response.text();
    if (!response.ok) {
      let message = text || `HTTP ${response.status}`;
      try {
        const data = JSON.parse(text);
        message = data.detail || data.message || message;
        if (typeof message !== 'string') message = JSON.stringify(message, null, 2);
      } catch (_) {}
      throw new Error(message);
    }
    if (!text) return null;
    try { return JSON.parse(text); } catch (_) { return text; }
  }

  function formData(values) {
    const data = new FormData();
    Object.entries(values).forEach(([key, value]) => {
      if (value !== undefined && value !== null) data.append(key, value);
    });
    return data;
  }

  function assetUrl(key) {
    return current?.assets?.[key]
      ? `/api/projects/${current.id}/assets/${key}?t=${Date.now()}`
      : '';
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[ch]));
  }

  function showError(error, title = 'Операция не выполнена') {
    $('error-title').textContent = title;
    $('error-text').textContent = error?.message || String(error || 'Неизвестная ошибка');
    $('error-modal').classList.remove('hidden');
  }

  async function busy(button, work) {
    if (!button) return work();
    const label = button.textContent;
    button.disabled = true;
    button.textContent = 'Выполняется…';
    try {
      return await work();
    } catch (error) {
      showError(error);
      throw error;
    } finally {
      button.disabled = false;
      button.textContent = label;
    }
  }

  async function loadHealth() {
    try {
      const data = await api('/api/health');
      const node = $('health');
      const ok = data.runtime === 'standalone-v080';
      node.classList.toggle('ok', ok);
      node.classList.toggle('bad', !ok);
      node.innerHTML = `<i></i>${ok ? 'SYSTEM ONLINE' : 'RUNTIME MISMATCH'}`;
    } catch (_) {
      $('health').classList.add('bad');
      $('health').innerHTML = '<i></i>SYSTEM OFFLINE';
    }
  }

  async function loadProjects(selectFirst = false) {
    projectsCache = await api('/api/projects');
    $('project-count').textContent = `${projectsCache.length} ${projectsCache.length === 1 ? 'проект' : 'проектов'}`;
    const list = $('project-list');
    list.innerHTML = '';
    if (!projectsCache.length) {
      list.innerHTML = '<div class="status-line">Проектов пока нет.</div>';
      return;
    }
    projectsCache.forEach(project => {
      const button = document.createElement('button');
      const status = project.pipeline?.[project.active_stage] || project.pipeline?.source || 'ready';
      const canvas = project.master_canvas
        ? `${project.master_canvas.width} × ${project.master_canvas.height}`
        : 'Master не загружен';
      button.className = `project-card${current?.id === project.id ? ' active' : ''}`;
      button.innerHTML = `<strong>${escapeHtml(project.name)}</strong><span>${escapeHtml(canvas)}</span><small>${escapeHtml(project.updated_at ? new Date(project.updated_at).toLocaleString('ru-RU') : '')}</small><span class="project-status">${escapeHtml(STAGE_LABELS[project.active_stage] || project.active_stage || 'Source')} · ${escapeHtml(status)}</span>`;
      button.onclick = () => selectProject(project.id).catch(showError);
      list.appendChild(button);
    });
    if (selectFirst && !current && projectsCache[0]) await selectProject(projectsCache[0].id);
  }

  function defaultViewForStage(stage) {
    if (stage === 'source') return 'original';
    if (stage === 'geometry') return current?.assets?.source_master ? 'grid' : 'original';
    if (stage === 'environment') {
      if (current?.assets?.environment_candidate) return 'generation';
      if (current?.assets?.geometry_candidate) return 'result';
      return 'original';
    }
    if (stage === 'final' || stage === 'branding') {
      return current?.assets?.environment_candidate ? 'result' : 'original';
    }
    return 'original';
  }

  function viewAssetKey(view = currentView, stage = currentStage) {
    if (selectedAssetKey && view !== 'grid' && view !== 'split') return selectedAssetKey;
    if (view === 'original') return current?.assets?.source_master ? 'source_master' : null;
    if (view === 'result') {
      if (stage === 'geometry') return current?.assets?.geometry_candidate ? 'geometry_candidate' : null;
      if (stage === 'environment') return current?.assets?.geometry_candidate ? 'geometry_candidate' : null;
      if (stage === 'final') return current?.assets?.environment_candidate ? 'environment_candidate' : null;
      if (stage === 'branding') {
        return current?.assets?.branding_candidate
          ? 'branding_candidate'
          : (current?.assets?.environment_candidate ? 'environment_candidate' : null);
      }
    }
    if (view === 'generation') {
      return current?.assets?.environment_candidate ? 'environment_candidate' : null;
    }
    return null;
  }

  function splitPair(stage = currentStage) {
    if (stage === 'geometry') {
      return {
        beforeKey: current?.assets?.source_master ? 'source_master' : null,
        afterKey: current?.assets?.geometry_candidate ? 'geometry_candidate' : null,
        beforeLabel: 'ОРИГИНАЛ',
        afterLabel: 'РЕЗУЛЬТАТ'
      };
    }
    if (stage === 'environment') {
      return {
        beforeKey: current?.assets?.geometry_candidate ? 'geometry_candidate' : null,
        afterKey: current?.assets?.environment_candidate ? 'environment_candidate' : null,
        beforeLabel: 'РЕЗУЛЬТАТ',
        afterLabel: 'ГЕНЕРАЦИЯ'
      };
    }
    if (stage === 'final') {
      return {
        beforeKey: current?.assets?.source_master ? 'source_master' : null,
        afterKey: current?.assets?.environment_candidate ? 'environment_candidate' : null,
        beforeLabel: 'ОРИГИНАЛ',
        afterLabel: 'FINAL'
      };
    }
    if (stage === 'branding') {
      return {
        beforeKey: current?.assets?.environment_candidate ? 'environment_candidate' : null,
        afterKey: current?.assets?.branding_candidate ? 'branding_candidate' : null,
        beforeLabel: 'FINAL',
        afterLabel: 'ВЫВЕСКА'
      };
    }
    return null;
  }

  function isViewAvailable(view, stage = currentStage) {
    if (view === 'grid') return stage === 'geometry' && !!current?.assets?.source_master;
    if (view === 'split') {
      const pair = splitPair(stage);
      return !!pair?.beforeKey && !!pair?.afterKey;
    }
    return !!viewAssetKey(view, stage);
  }

  function normalizeCurrentView() {
    const allowed = VIEW_CONFIG[currentStage] || ['original'];
    if (!allowed.includes(currentView) || !isViewAvailable(currentView)) {
      currentView = defaultViewForStage(currentStage);
    }
    if (!isViewAvailable(currentView) && current?.assets?.source_master) currentView = 'original';
  }

  function renderWorkspaceTabs() {
    normalizeCurrentView();
    const allowed = VIEW_CONFIG[currentStage] || ['original'];
    document.querySelectorAll('.mode-tabs button').forEach(button => {
      const view = button.dataset.view;
      const visible = allowed.includes(view);
      button.classList.toggle('hidden', !visible);
      button.disabled = visible && !isViewAvailable(view);
      button.classList.toggle('active', visible && view === currentView);
    });
  }

  async function createProject() {
    const name = window.prompt('Название проекта');
    if (!name?.trim()) return;
    current = await api('/api/projects', {method: 'POST', body: formData({name: name.trim()})});
    currentStage = 'source';
    currentView = 'original';
    selectedAssetKey = null;
    await loadProjects();
    renderAll();
  }

  async function selectProject(id) {
    current = await api(`/api/projects/${id}`);
    currentStage = current.active_stage || (current.assets?.source_master ? 'geometry' : 'source');
    currentView = defaultViewForStage(currentStage);
    selectedAssetKey = null;
    resetGeometryRuntime();
    renderAll();
    await Promise.all([loadProjects(), loadHistory()]);
  }

  function resetGeometryRuntime() {
    geo.image = null;
    geo.corners = [];
    geo.drag = -1;
    geo.history = [];
    geo.future = [];
    geo.projectId = null;
    geo.sourcePath = null;
  }

  function renderAll() {
    const hasProject = !!current;
    $('empty-state').classList.toggle('hidden', hasProject);
    $('project-workspace').classList.toggle('hidden', !hasProject);
    if (!hasProject) return;

    $('header-project').textContent = current.name;
    $('project-title').textContent = current.name;
    $('header-master').textContent = current.master_canvas
      ? `${current.master_canvas.width} × ${current.master_canvas.height}`
      : '—';
    $('source-status').textContent = current.master_canvas
      ? `Оригинал ${current.master_canvas.width} × ${current.master_canvas.height}. Production policy: original resolution.`
      : 'Файл не загружен.';
    $('active-stage-label').textContent = STAGE_LABELS[currentStage];
    $('inspector-stage').textContent = STAGE_LABELS[currentStage];
    renderPipeline();
    renderStageActions();
    renderWorkspaceTabs();
    renderView();
    renderCandidates();
    updateCommentStatus();
  }

  function renderPipeline() {
    document.querySelectorAll('#pipeline button').forEach(button => {
      const stage = button.dataset.stage;
      const status = current?.pipeline?.[stage] || 'locked';
      button.className = `${status}${stage === currentStage ? ' is-active' : ''}`;
      button.querySelector('b').textContent = status;
      button.disabled = false;
    });
  }

  function stageResultKey() {
    if (selectedAssetKey) return selectedAssetKey;
    if (currentView === 'split') {
      return splitPair()?.afterKey || splitPair()?.beforeKey || null;
    }
    return viewAssetKey(currentView, currentStage)
      || viewAssetKey(defaultViewForStage(currentStage), currentStage)
      || (current?.assets?.source_master ? 'source_master' : null);
  }

  function renderStageActions() {
    STAGES.forEach(stage => $(`${stage}-actions`).classList.toggle('hidden', stage !== currentStage));
    const titles = {
      source: ['SOURCE / IMMUTABLE MASTER', 'Загрузите исходное изображение'],
      geometry: ['PERSPECTIVE GRID', 'Совместите сетку с главной плоскостью фасада'],
      environment: ['AI ENVIRONMENT', 'Сгенерируйте окружение по всему canvas'],
      final: ['FINAL REVIEW', 'Проверьте итоговый мастер'],
      branding: ['BRANDING', 'Разместите вывеску на утверждённом изображении']
    };
    $('action-stage-kicker').textContent = titles[currentStage][0];
    $('action-stage-title').textContent = titles[currentStage][1];
    $('geometry-apply').disabled = !current.assets?.source_master;
    $('geometry-approve').disabled = !current.assets?.geometry_candidate;
    $('environment-generate').disabled = current.pipeline?.geometry !== 'approved';
    $('environment-approve').disabled = !current.assets?.environment_candidate;
  }

  function setCurrentStage(stage) {
    currentStage = stage;
    selectedAssetKey = null;
    currentView = defaultViewForStage(stage);
    renderAll();
    loadHistory().catch(showError);
  }

  function setView(view) {
    if (!isViewAvailable(view)) return;
    selectedAssetKey = null;
    currentView = view;
    renderWorkspaceTabs();
    renderView();
  }

  function hideViewerPanels() {
    ['source-panel', 'single-view', 'grid-view', 'split-view'].forEach(id => $(id).classList.add('hidden'));
  }

  function renderView() {
    if (!current) return;
    normalizeCurrentView();
    renderWorkspaceTabs();
    hideViewerPanels();

    if (!current.assets?.source_master) {
      $('source-panel').classList.remove('hidden');
      return;
    }

    if (currentView === 'grid' && currentStage === 'geometry') {
      $('grid-view').classList.remove('hidden');
      loadGeometryImage();
      return;
    }

    if (currentView === 'split') {
      const pair = splitPair();
      if (pair?.beforeKey && pair?.afterKey) {
        $('split-view').classList.remove('hidden');
        $('split-before-label').textContent = pair.beforeLabel;
        $('split-after-label').textContent = pair.afterLabel;
        $('split-before').src = assetUrl(pair.beforeKey);
        $('split-after').src = assetUrl(pair.afterKey);
        return;
      }
      currentView = defaultViewForStage(currentStage);
      renderWorkspaceTabs();
    }

    const key = viewAssetKey(currentView, currentStage) || 'source_master';
    $('single-view').classList.remove('hidden');
    $('single-image').src = assetUrl(key);
    applyZoom();
  }

  function applyZoom() {
    const single = $('single-view');
    const grid = $('grid-view');
    single.classList.toggle('actual', !fitMode);
    grid.classList.toggle('actual', !fitMode);
    const image = $('single-image');
    const canvas = $('geometry-canvas');
    if (fitMode) {
      image.style.width = '';
      canvas.style.width = '';
      $('zoom-value').textContent = 'FIT';
    } else {
      const percent = Math.max(10, Math.round(zoomFactor * 100));
      if (image.naturalWidth) image.style.width = `${Math.round(image.naturalWidth * zoomFactor)}px`;
      if (canvas.width) canvas.style.width = `${Math.round(canvas.width * zoomFactor)}px`;
      $('zoom-value').textContent = `${percent}%`;
    }
  }

  async function uploadSource() {
    if (!current) return showError(new Error('Сначала создайте проект.'));
    const file = $('source-file').files?.[0];
    if (!file) return showError(new Error('Выберите изображение.'));
    current = await api(`/api/projects/${current.id}/source`, {
      method: 'POST',
      body: formData({file})
    });
    currentStage = 'geometry';
    currentView = 'grid';
    selectedAssetKey = null;
    resetGeometryRuntime();
    renderAll();
    await loadProjects();
  }

  function defaultCorners(image) {
    const x = image.naturalWidth * 0.12;
    const y = image.naturalHeight * 0.12;
    return [
      {x, y},
      {x: image.naturalWidth - x, y},
      {x: image.naturalWidth - x, y: image.naturalHeight - y},
      {x, y: image.naturalHeight - y}
    ];
  }

  function loadGeometryImage() {
    const sourcePath = current.assets?.source_master;
    if (!sourcePath) return;
    if (geo.projectId === current.id && geo.sourcePath === sourcePath && geo.image) {
      resizeGeometry();
      return;
    }
    const image = new Image();
    image.onload = () => {
      geo.image = image;
      geo.projectId = current.id;
      geo.sourcePath = sourcePath;
      const saved = current.geometry?.quad;
      geo.corners = Array.isArray(saved) && saved.length === 4
        ? saved.map(point => ({x: +point.x, y: +point.y}))
        : defaultCorners(image);
      geo.history = [];
      geo.future = [];
      resizeGeometry();
    };
    image.onerror = () => showError(new Error('Не удалось загрузить master image для Perspective Grid.'));
    image.src = assetUrl('source_master');
  }

  function resizeGeometry() {
    const canvas = $('geometry-canvas');
    if (!geo.image) return;
    if (canvas.width !== geo.image.naturalWidth || canvas.height !== geo.image.naturalHeight) {
      canvas.width = geo.image.naturalWidth;
      canvas.height = geo.image.naturalHeight;
    }
    drawGeometry();
    applyZoom();
  }

  function bilinear(u, v) {
    const [tl, tr, br, bl] = geo.corners;
    const top = {x: tl.x + (tr.x - tl.x) * u, y: tl.y + (tr.y - tl.y) * u};
    const bottom = {x: bl.x + (br.x - bl.x) * u, y: bl.y + (br.y - bl.y) * u};
    return {x: top.x + (bottom.x - top.x) * v, y: top.y + (bottom.y - top.y) * v};
  }

  function drawGeometry() {
    const canvas = $('geometry-canvas');
    if (!geo.image || geo.corners.length !== 4) return;
    const context = canvas.getContext('2d');
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(geo.image, 0, 0, canvas.width, canvas.height);
    context.strokeStyle = '#19d3c5';
    context.lineWidth = Math.max(2, canvas.width / 1100);
    context.setLineDash([Math.max(10, canvas.width / 180), Math.max(7, canvas.width / 260)]);
    for (let i = 0; i <= 8; i += 1) {
      const u = i / 8;
      let point = bilinear(u, 0);
      context.beginPath();
      context.moveTo(point.x, point.y);
      for (let step = 1; step <= 30; step += 1) {
        point = bilinear(u, step / 30);
        context.lineTo(point.x, point.y);
      }
      context.stroke();
    }
    for (let i = 0; i <= 6; i += 1) {
      const v = i / 6;
      let point = bilinear(0, v);
      context.beginPath();
      context.moveTo(point.x, point.y);
      for (let step = 1; step <= 30; step += 1) {
        point = bilinear(step / 30, v);
        context.lineTo(point.x, point.y);
      }
      context.stroke();
    }
    context.strokeStyle = '#fff';
    context.lineWidth = Math.max(3, canvas.width / 700);
    context.setLineDash([16, 10]);
    context.beginPath();
    context.moveTo(geo.corners[0].x, geo.corners[0].y);
    geo.corners.slice(1).forEach(point => context.lineTo(point.x, point.y));
    context.closePath();
    context.stroke();
    context.setLineDash([]);
    geo.corners.forEach((point, index) => {
      context.beginPath();
      context.arc(point.x, point.y, Math.max(12, canvas.width / 140), 0, Math.PI * 2);
      context.fillStyle = '#008a90';
      context.fill();
      context.strokeStyle = '#fff';
      context.stroke();
      context.fillStyle = '#fff';
      context.font = `${Math.max(18, canvas.width / 70)}px Arial`;
      context.textAlign = 'center';
      context.textBaseline = 'middle';
      context.fillText(String(index + 1), point.x, point.y);
    });
  }

  function geometryPosition(event) {
    const canvas = $('geometry-canvas');
    const rect = canvas.getBoundingClientRect();
    return {
      x: (event.clientX - rect.left) * canvas.width / rect.width,
      y: (event.clientY - rect.top) * canvas.height / rect.height
    };
  }

  function geometryHit(point) {
    const canvas = $('geometry-canvas');
    const rect = canvas.getBoundingClientRect();
    const radius = 30 * canvas.width / rect.width;
    let index = -1;
    let best = Infinity;
    geo.corners.forEach((corner, i) => {
      const distance = Math.hypot(point.x - corner.x, point.y - corner.y);
      if (distance < radius && distance < best) {
        index = i;
        best = distance;
      }
    });
    return index;
  }

  function resetGeometry() {
    if (!geo.image) return;
    geo.history.push(geo.corners.map(point => ({...point})));
    geo.corners = defaultCorners(geo.image);
    geo.future = [];
    drawGeometry();
  }

  function undoGeometry() {
    if (!geo.history.length) return;
    geo.future.push(geo.corners.map(point => ({...point})));
    geo.corners = geo.history.pop();
    drawGeometry();
  }

  function redoGeometry() {
    if (!geo.future.length) return;
    geo.history.push(geo.corners.map(point => ({...point})));
    geo.corners = geo.future.pop();
    drawGeometry();
  }

  async function applyGeometry() {
    if (!current || geo.corners.length !== 4) return;
    current = await api(`/api/projects/${current.id}/geometry/apply-grid`, {
      method: 'POST',
      body: formData({quad_json: JSON.stringify(geo.corners)})
    });
    selectedAssetKey = null;
    currentView = 'result';
    renderAll();
    await Promise.all([loadHistory(), loadProjects()]);
  }

  async function approveGeometry() {
    current = await api(`/api/projects/${current.id}/geometry/approve`, {method: 'POST'});
    currentStage = 'environment';
    currentView = current.assets?.environment_candidate ? 'generation' : 'result';
    selectedAssetKey = null;
    renderAll();
    await Promise.all([loadHistory(), loadProjects()]);
  }

  async function addComment() {
    if (!current) return;
    const comment = $('comment-input').value.trim();
    if (!comment) throw new Error('Введите комментарий.');
    current = await api(`/api/projects/${current.id}/comments/${currentStage}`, {
      method: 'POST',
      body: formData({comment})
    });
    $('comment-input').value = '';
    renderAll();
    await Promise.all([loadHistory(), loadProjects()]);
  }

  async function compilePrompt() {
    if (!current) return;
    const result = await api(`/api/projects/${current.id}/prompt/${currentStage}`);
    $('prompt-output').textContent = result.prompt || JSON.stringify(result, null, 2);
    openInspectorTab('prompt');
    await loadHistory();
  }

  async function generateEnvironment() {
    const pending = $('comment-input').value.trim();
    if (pending) await addComment();
    current = await api(`/api/projects/${current.id}/environment/generate`, {method: 'POST'});
    currentView = 'generation';
    selectedAssetKey = null;
    renderAll();
    await Promise.all([loadHistory(), loadProjects()]);
  }

  async function approveEnvironment() {
    current = await api(`/api/projects/${current.id}/environment/approve`, {method: 'POST'});
    currentStage = 'final';
    currentView = 'result';
    selectedAssetKey = null;
    renderAll();
    await Promise.all([loadHistory(), loadProjects()]);
  }

  async function runQuality() {
    if (!current) return;
    const key = stageResultKey();
    if (!key) throw new Error('Нет изображения для проверки.');
    const report = await api(`/api/projects/${current.id}/quality/${key}`);
    renderQuality(report);
    openInspectorTab('quality');
    await loadHistory();
  }

  function renderQuality(report) {
    const output = $('quality-output');
    const entries = Object.entries(report || {});
    output.innerHTML = entries.map(([key, value]) => {
      const pass = value === true || value === 'passed' || (key === 'passed' && value);
      const fail = value === false || value === 'failed' || (key === 'passed' && !value);
      const className = pass ? 'pass' : fail ? 'fail' : '';
      const text = typeof value === 'object' ? JSON.stringify(value) : value;
      return `<div class="quality-row"><span>${escapeHtml(key)}</span><strong class="${className}">${escapeHtml(text)}</strong></div>`;
    }).join('') || 'Нет данных.';
  }

  async function loadHistory() {
    if (!current) return;
    const events = await api(`/api/projects/${current.id}/history`);
    const ordered = Array.isArray(events) ? events : [];
    $('history-output').innerHTML = ordered.slice().reverse().map(renderHistoryCard).join('') || '<div class="status-line">История пуста.</div>';
    $('timeline-list').innerHTML = ordered.slice(-12).reverse().map(event => `<article class="timeline-item"><time>${escapeHtml(formatTime(event.timestamp))}</time><strong>${escapeHtml(event.type || event.event_type || 'Event')}</strong><p>${escapeHtml(event.actor || 'system')}</p></article>`).join('') || '<div class="status-line">Событий пока нет.</div>';
    $('events-output').textContent = JSON.stringify(ordered, null, 2);
  }

  function renderHistoryCard(event) {
    return `<article class="history-card"><time>${escapeHtml(event.timestamp || '')}</time><strong>${escapeHtml(event.type || event.event_type || 'Event')}</strong><pre>${escapeHtml(JSON.stringify(event.payload || {}, null, 2))}</pre></article>`;
  }

  function formatTime(value) {
    try {
      return new Date(value).toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'});
    } catch (_) {
      return value || '';
    }
  }

  async function loadDiagnostics() {
    if (!current) return;
    const diagnostics = await api(`/api/projects/${current.id}/diagnostics`);
    $('diagnostics-output').textContent = JSON.stringify(diagnostics, null, 2);
    openInspectorTab('diagnostics');
  }

  function updateCommentStatus() {
    const comments = (current?.comments || []).filter(item => item.stage === currentStage);
    $('comment-status').textContent = comments.length
      ? `${comments.length} комментариев включено в prompt`
      : 'Комментариев нет';
  }

  function renderCandidates() {
    const definitions = [
      ['source_preview', 'Original'],
      ['geometry_preview', 'Geometry'],
      ['environment_preview', 'Environment'],
      ['branding_preview', 'Branding']
    ];
    const target = $('candidate-list');
    target.innerHTML = '';
    definitions.filter(([key]) => current.assets?.[key]).forEach(([key, label]) => {
      const productionKey = key.replace('_preview', '_candidate').replace('source_candidate', 'source_master');
      const button = document.createElement('button');
      button.className = `candidate-card${selectedAssetKey === productionKey ? ' active' : ''}`;
      button.innerHTML = `<img src="${assetUrl(key)}" alt="${escapeHtml(label)}"><span>${escapeHtml(label)}</span>`;
      button.onclick = () => {
        selectedAssetKey = null;
        if (productionKey === 'source_master') currentView = 'original';
        else if (productionKey === 'geometry_candidate') currentView = 'result';
        else if (productionKey === 'environment_candidate') currentView = currentStage === 'environment' ? 'generation' : 'result';
        else {
          selectedAssetKey = productionKey;
          currentView = 'result';
        }
        renderAll();
      };
      target.appendChild(button);
    });
    if (!target.children.length) target.innerHTML = '<div class="status-line">Кандидатов пока нет.</div>';
  }

  function openInspectorTab(name) {
    document.querySelectorAll('.inspector-tabs button').forEach(button => {
      button.classList.toggle('active', button.dataset.tab === name);
    });
    document.querySelectorAll('.inspector-panel').forEach(panel => {
      panel.classList.toggle('active', panel.dataset.panel === name);
    });
  }

  function openBottomTab(name) {
    document.querySelectorAll('.bottom-tabs button').forEach(button => {
      button.classList.toggle('active', button.dataset.bottom === name);
    });
    document.querySelectorAll('.bottom-content').forEach(panel => {
      panel.classList.toggle('active', panel.dataset.bottomPanel === name);
    });
  }

  const canvas = $('geometry-canvas');
  canvas.onpointerdown = event => {
    const index = geometryHit(geometryPosition(event));
    if (index < 0) return;
    geo.history.push(geo.corners.map(point => ({...point})));
    geo.future = [];
    geo.drag = index;
    canvas.setPointerCapture(event.pointerId);
  };
  canvas.onpointermove = event => {
    if (geo.drag < 0) return;
    const point = geometryPosition(event);
    geo.corners[geo.drag] = {
      x: Math.max(0, Math.min(canvas.width, point.x)),
      y: Math.max(0, Math.min(canvas.height, point.y))
    };
    drawGeometry();
  };
  canvas.onpointerup = event => {
    geo.drag = -1;
    try { canvas.releasePointerCapture(event.pointerId); } catch (_) {}
  };
  canvas.ondblclick = resetGeometry;

  document.querySelectorAll('#pipeline button').forEach(button => {
    button.onclick = () => setCurrentStage(button.dataset.stage);
  });
  document.querySelectorAll('.mode-tabs button').forEach(button => {
    button.onclick = () => setView(button.dataset.view);
  });
  document.querySelectorAll('.inspector-tabs button').forEach(button => {
    button.onclick = () => openInspectorTab(button.dataset.tab);
  });
  document.querySelectorAll('.bottom-tabs button').forEach(button => {
    button.onclick = () => openBottomTab(button.dataset.bottom);
  });

  $('new-project').onclick = createProject;
  $('new-project-bottom').onclick = createProject;
  $('empty-new-project').onclick = createProject;
  $('upload-source').onclick = () => busy($('upload-source'), uploadSource);
  $('source-replace').onclick = () => {
    setCurrentStage('source');
    $('source-file').click();
  };
  $('source-file').onchange = () => {
    if ($('source-file').files?.[0]) busy($('upload-source'), uploadSource);
  };
  $('geometry-reset').onclick = resetGeometry;
  $('geometry-undo').onclick = undoGeometry;
  $('geometry-redo').onclick = redoGeometry;
  $('geometry-apply').onclick = () => busy($('geometry-apply'), applyGeometry);
  $('geometry-approve').onclick = () => busy($('geometry-approve'), approveGeometry);
  $('adapt-comment').onclick = () => busy($('adapt-comment'), addComment);
  $('compile-prompt').onclick = () => busy($('compile-prompt'), compilePrompt);
  $('environment-prompt').onclick = () => busy($('environment-prompt'), compilePrompt);
  $('environment-generate').onclick = () => busy($('environment-generate'), generateEnvironment);
  $('environment-approve').onclick = () => busy($('environment-approve'), approveEnvironment);
  $('run-quality').onclick = () => busy($('run-quality'), runQuality);
  $('refresh-diagnostics').onclick = () => busy($('refresh-diagnostics'), loadDiagnostics);
  $('fit-view').onclick = () => {
    fitMode = true;
    zoomFactor = 1;
    applyZoom();
  };
  $('actual-view').onclick = () => {
    fitMode = false;
    zoomFactor = 1;
    applyZoom();
  };
  $('zoom-in').onclick = () => {
    fitMode = false;
    zoomFactor = Math.min(8, zoomFactor + 0.25);
    applyZoom();
  };
  $('zoom-out').onclick = () => {
    fitMode = false;
    zoomFactor = Math.max(0.1, zoomFactor - 0.25);
    applyZoom();
  };
  $('fullscreen-view').onclick = () => $('viewer').requestFullscreen?.();
  $('error-close').onclick = () => $('error-modal').classList.add('hidden');
  $('error-modal').onclick = event => {
    if (event.target === $('error-modal')) $('error-modal').classList.add('hidden');
  };
  window.addEventListener('resize', () => {
    if (currentView === 'grid') resizeGeometry();
  });

  Promise.all([loadHealth(), loadProjects(true)]).catch(showError);
})();
