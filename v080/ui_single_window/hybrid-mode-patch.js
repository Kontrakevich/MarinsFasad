(() => {
  'use strict';

  const MODE_PREFIX = '__MARINS_GENERATION_MODE__:';
  const QUALITY_PREFIX = '__MARINS_GENERATION_QUALITY__:';
  const MODES = {
    hybrid: 'HYBRID · EDIT / RELIGHT + OUTPAINT',
    relight: 'RELIGHT · NEW LIGHTING',
    edit: 'IMAGE EDIT',
    outpaint: 'OUTPAINT'
  };
  const QUALITIES = {
    draft: 'Черновик',
    standard: 'Стандарт',
    high: 'Высокое',
    max: 'Максимум'
  };
  const previousFetch = window.fetch.bind(window);
  let activeProjectId = '';
  let modeSelect = null;
  let qualitySelect = null;
  let savingSettings = null;

  const projectPattern = /\/api\/projects\/([^/?]+)(?:\?.*)?$/;
  const promptPattern = /\/api\/projects\/([^/]+)\/prompt\/environment(?:\?.*)?$/;
  const generationPattern = /\/api\/projects\/([^/]+)\/environment\/generate(?:\?.*)?$/;

  function normalizeMode(value) {
    const mode = String(value || '').trim().toLowerCase();
    return Object.prototype.hasOwnProperty.call(MODES, mode) ? mode : 'hybrid';
  }

  function normalizeQuality(value) {
    const quality = String(value || '').trim().toLowerCase();
    return Object.prototype.hasOwnProperty.call(QUALITIES, quality) ? quality : 'high';
  }

  function serviceCommentKind(item) {
    const text = String(item?.text || '').trim().toLowerCase();
    if (text.startsWith(MODE_PREFIX.toLowerCase())) return 'mode';
    if (text.startsWith(QUALITY_PREFIX.toLowerCase())) return 'quality';
    return '';
  }

  function projectMode(project) {
    let mode = 'hybrid';
    for (const item of project?.comments || []) {
      const text = String(item?.text || '').trim();
      if (!text.toLowerCase().startsWith(MODE_PREFIX.toLowerCase())) continue;
      mode = normalizeMode(text.slice(MODE_PREFIX.length));
    }
    return mode;
  }

  function projectQuality(project) {
    let quality = 'high';
    for (const item of project?.comments || []) {
      const text = String(item?.text || '').trim();
      if (!text.toLowerCase().startsWith(QUALITY_PREFIX.toLowerCase())) continue;
      quality = normalizeQuality(text.slice(QUALITY_PREFIX.length));
    }
    return quality;
  }

  function scheduleVisibleCommentCount(project) {
    const visibleCount = (project?.comments || []).filter(
      item => item?.stage === 'environment' && !serviceCommentKind(item)
    ).length;
    requestAnimationFrame(() => {
      const environmentActive = !document.getElementById('environment-actions')?.classList.contains('hidden');
      const node = document.getElementById('comment-status');
      if (!environmentActive || !node) return;
      node.textContent = visibleCount
        ? `${visibleCount} комментариев включено в prompt`
        : 'Комментариев нет';
    });
  }

  function installControl() {
    const actions = document.getElementById('environment-actions');
    if (!actions || document.getElementById('environment-mode')) return;

    const group = document.createElement('div');
    group.className = 'generation-settings-group';
    group.innerHTML = `
      <label class="generation-setting-control">
        <span>SKILL</span>
        <select id="environment-mode" aria-label="Skill генерации окружения">
          <option value="hybrid">${MODES.hybrid}</option>
          <option value="relight">${MODES.relight}</option>
          <option value="edit">${MODES.edit}</option>
          <option value="outpaint">${MODES.outpaint}</option>
        </select>
      </label>
      <label class="generation-setting-control">
        <span>КАЧЕСТВО</span>
        <select id="environment-quality" aria-label="Качество генерации">
          <option value="draft">${QUALITIES.draft}</option>
          <option value="standard">${QUALITIES.standard}</option>
          <option value="high">${QUALITIES.high}</option>
          <option value="max">${QUALITIES.max}</option>
        </select>
      </label>
    `;
    actions.insertBefore(group, actions.firstChild);
    modeSelect = group.querySelector('#environment-mode');
    qualitySelect = group.querySelector('#environment-quality');
    modeSelect.value = 'hybrid';
    qualitySelect.value = 'high';

    const save = () => {
      if (activeProjectId) ensureGenerationSettings(activeProjectId).catch(() => {});
    };
    modeSelect.addEventListener('change', save);
    qualitySelect.addEventListener('change', save);

    const style = document.createElement('style');
    style.textContent = `
      .generation-settings-group{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
      .generation-setting-control{display:flex;align-items:center;gap:7px;height:32px;border:1px solid var(--ink);padding:0 7px;background:var(--paper)}
      .generation-setting-control>span{font-size:7px;letter-spacing:.12em;color:var(--ink-2)}
      .generation-setting-control select{height:28px;max-width:245px;border:0;background:transparent;font-size:7px;letter-spacing:.08em;font-weight:600;outline:none;cursor:pointer}
      .generation-setting-control select:focus{box-shadow:inset 0 -2px 0 var(--accent)}
    `;
    document.head.appendChild(style);

    const version = document.querySelector('.version-mark');
    if (version) version.textContent = 'V0.8.1 QUALITY';
  }

  async function responseJson(response) {
    try {
      return await response.clone().json();
    } catch (_) {
      return null;
    }
  }

  async function readProject(projectId) {
    const response = await previousFetch(`/api/projects/${projectId}`, {
      method: 'GET',
      cache: 'no-store',
      headers: {'Accept': 'application/json', 'Cache-Control': 'no-cache'}
    });
    if (!response.ok) return null;
    return responseJson(response);
  }

  async function saveServiceComment(projectId, text) {
    const body = new FormData();
    body.append('comment', text);
    const response = await previousFetch(`/api/projects/${projectId}/comments/environment`, {
      method: 'POST',
      body
    });
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || `Не удалось сохранить настройки генерации: HTTP ${response.status}`);
    }
    return responseJson(response);
  }

  async function ensureGenerationSettings(projectId) {
    installControl();
    const requestedMode = normalizeMode(modeSelect?.value || 'hybrid');
    const requestedQuality = normalizeQuality(qualitySelect?.value || 'high');
    if (savingSettings) await savingSettings;

    savingSettings = (async () => {
      let project = await readProject(projectId);
      if (project) {
        activeProjectId = projectId;
        scheduleVisibleCommentCount(project);
      }

      if (!project || projectMode(project) !== requestedMode) {
        project = await saveServiceComment(projectId, `${MODE_PREFIX}${requestedMode}`) || project;
      }
      if (!project || projectQuality(project) !== requestedQuality) {
        project = await saveServiceComment(projectId, `${QUALITY_PREFIX}${requestedQuality}`) || project;
      }
      if (project) scheduleVisibleCommentCount(project);
    })();

    try {
      await savingSettings;
    } finally {
      savingSettings = null;
    }
  }

  window.fetch = async function generationSettingsFetch(input, init = {}) {
    installControl();
    const url = typeof input === 'string' ? input : input?.url || '';
    const method = String(init?.method || input?.method || 'GET').toUpperCase();

    const promptMatch = url.match(promptPattern);
    const generationMatch = url.match(generationPattern);
    const settingsProjectId = promptMatch?.[1] || generationMatch?.[1] || '';
    if (settingsProjectId) {
      activeProjectId = settingsProjectId;
      await ensureGenerationSettings(settingsProjectId);
    }

    const response = await previousFetch(input, init);

    if (method === 'GET') {
      const projectMatch = url.match(projectPattern);
      if (projectMatch && !url.includes('/history') && !url.includes('/diagnostics')) {
        const project = await responseJson(response);
        if (project?.id) {
          activeProjectId = project.id;
          if (modeSelect) modeSelect.value = projectMode(project);
          if (qualitySelect) qualitySelect.value = projectQuality(project);
          scheduleVisibleCommentCount(project);
        }
      }
    }
    return response;
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installControl, {once: true});
  } else {
    installControl();
  }
})();
