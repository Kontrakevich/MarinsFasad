(() => {
  'use strict';

  const MODE_PREFIX = '__MARINS_GENERATION_MODE__:';
  const MODES = {
    hybrid: 'HYBRID · EDIT + OUTPAINT',
    edit: 'IMAGE EDIT',
    outpaint: 'OUTPAINT'
  };
  const previousFetch = window.fetch.bind(window);
  let activeProjectId = '';
  let modeSelect = null;
  let savingMode = null;

  const projectPattern = /\/api\/projects\/([^/?]+)(?:\?.*)?$/;
  const promptPattern = /\/api\/projects\/([^/]+)\/prompt\/environment(?:\?.*)?$/;
  const generationPattern = /\/api\/projects\/([^/]+)\/environment\/generate(?:\?.*)?$/;

  function normalizeMode(value) {
    const mode = String(value || '').trim().toLowerCase();
    return Object.prototype.hasOwnProperty.call(MODES, mode) ? mode : 'hybrid';
  }

  function isModeComment(item) {
    return String(item?.text || '').trim().toLowerCase().startsWith(MODE_PREFIX.toLowerCase());
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

  function scheduleVisibleCommentCount(project) {
    const visibleCount = (project?.comments || []).filter(
      item => item?.stage === 'environment' && !isModeComment(item)
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

    const label = document.createElement('label');
    label.className = 'generation-mode-control';
    label.innerHTML = `
      <span>РЕЖИМ</span>
      <select id="environment-mode" aria-label="Режим генерации окружения">
        <option value="hybrid">${MODES.hybrid}</option>
        <option value="edit">${MODES.edit}</option>
        <option value="outpaint">${MODES.outpaint}</option>
      </select>
    `;
    actions.insertBefore(label, actions.firstChild);
    modeSelect = label.querySelector('select');
    modeSelect.value = 'hybrid';
    modeSelect.addEventListener('change', () => {
      if (activeProjectId) ensureMode(activeProjectId).catch(() => {});
    });

    const style = document.createElement('style');
    style.textContent = `
      .generation-mode-control{display:flex;align-items:center;gap:7px;height:32px;border:1px solid var(--ink);padding:0 7px;background:var(--paper)}
      .generation-mode-control>span{font-size:7px;letter-spacing:.12em;color:var(--ink-2)}
      .generation-mode-control select{height:28px;max-width:205px;border:0;background:transparent;font-size:7px;letter-spacing:.08em;font-weight:600;outline:none;cursor:pointer}
      .generation-mode-control select:focus{box-shadow:inset 0 -2px 0 var(--accent)}
    `;
    document.head.appendChild(style);

    const version = document.querySelector('.version-mark');
    if (version) version.textContent = 'V0.8.0 HYBRID';
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

  async function ensureMode(projectId) {
    installControl();
    const requested = normalizeMode(modeSelect?.value || 'hybrid');
    if (savingMode) await savingMode;

    savingMode = (async () => {
      const project = await readProject(projectId);
      if (project) {
        activeProjectId = projectId;
        scheduleVisibleCommentCount(project);
        const stored = projectMode(project);
        if (stored === requested) return;
      }
      const body = new FormData();
      body.append('comment', `${MODE_PREFIX}${requested}`);
      const response = await previousFetch(`/api/projects/${projectId}/comments/environment`, {
        method: 'POST',
        body
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Не удалось сохранить режим генерации: HTTP ${response.status}`);
      }
      const updated = await responseJson(response);
      if (updated) scheduleVisibleCommentCount(updated);
    })();

    try {
      await savingMode;
    } finally {
      savingMode = null;
    }
  }

  window.fetch = async function hybridModeFetch(input, init = {}) {
    installControl();
    const url = typeof input === 'string' ? input : input?.url || '';
    const method = String(init?.method || input?.method || 'GET').toUpperCase();

    const promptMatch = url.match(promptPattern);
    const generationMatch = url.match(generationPattern);
    const modeProjectId = promptMatch?.[1] || generationMatch?.[1] || '';
    if (modeProjectId) {
      activeProjectId = modeProjectId;
      await ensureMode(modeProjectId);
    }

    const response = await previousFetch(input, init);

    if (method === 'GET') {
      const projectMatch = url.match(projectPattern);
      if (projectMatch && !url.includes('/history') && !url.includes('/diagnostics')) {
        const project = await responseJson(response);
        if (project?.id) {
          activeProjectId = project.id;
          if (modeSelect) modeSelect.value = projectMode(project);
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
