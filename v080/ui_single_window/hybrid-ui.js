(() => {
  'use strict';

  const MODE_PREFIX = '__MARINS_GENERATION_MODE__:';
  const STORAGE_KEY = 'marins-facade-generation-mode';
  const VALID_MODES = new Set(['hybrid', 'edit', 'outpaint']);
  const GENERATE_PATTERN = /\/api\/projects\/([^/]+)\/environment\/generate(?:\?.*)?$/;
  const PROMPT_PATTERN = /\/api\/projects\/([^/]+)\/prompt\/environment(?:\?.*)?$/;
  const previousFetch = window.fetch.bind(window);
  const persisted = new Map();

  function normalized(value) {
    const mode = String(value || '').trim().toLowerCase();
    return VALID_MODES.has(mode) ? mode : 'hybrid';
  }

  function selectedMode() {
    return normalized(document.getElementById('environment-generation-mode')?.value || localStorage.getItem(STORAGE_KEY));
  }

  function updateModeHint() {
    const mode = selectedMode();
    const hint = document.getElementById('environment-generation-mode-hint');
    if (!hint) return;
    hint.textContent = mode === 'edit'
      ? 'Только semantic image edit: объекты, провода, погода, атмосфера.'
      : mode === 'outpaint'
        ? 'Только дорисовка отсутствующих участков после геометрии.'
        : 'Сначала semantic image edit, затем отдельный outpaint отсутствующих участков.';
  }

  function installSelector() {
    const actions = document.getElementById('environment-actions');
    const generate = document.getElementById('environment-generate');
    if (!actions || !generate || document.getElementById('environment-generation-mode')) return;

    const control = document.createElement('label');
    control.className = 'generation-mode-control';
    control.innerHTML = `
      <span>РЕЖИМ</span>
      <select id="environment-generation-mode" aria-label="Режим генерации окружения">
        <option value="hybrid">HYBRID · EDIT + OUTPAINT</option>
        <option value="edit">EDIT · IMAGE EDIT</option>
        <option value="outpaint">OUTPAINT · ТОЛЬКО КРАЯ</option>
      </select>
      <small id="environment-generation-mode-hint"></small>
    `;
    actions.insertBefore(control, generate);
    const select = document.getElementById('environment-generation-mode');
    select.value = normalized(localStorage.getItem(STORAGE_KEY));
    select.addEventListener('change', () => {
      localStorage.setItem(STORAGE_KEY, selectedMode());
      updateModeHint();
    });
    updateModeHint();
  }

  async function persistMode(projectId) {
    const mode = selectedMode();
    if (persisted.get(projectId) === mode) return;
    const body = new FormData();
    body.append('comment', `${MODE_PREFIX}${mode}`);
    const response = await previousFetch(`/api/projects/${projectId}/comments/environment`, {
      method: 'POST',
      body
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `Не удалось сохранить режим генерации: HTTP ${response.status}`);
    }
    persisted.set(projectId, mode);
  }

  window.fetch = async function marinsHybridModeFetch(input, init = {}) {
    const url = typeof input === 'string' ? input : input?.url || '';
    const method = String(init?.method || input?.method || 'GET').toUpperCase();
    const generationMatch = method === 'POST' ? url.match(GENERATE_PATTERN) : null;
    const promptMatch = method === 'GET' ? url.match(PROMPT_PATTERN) : null;
    const projectId = generationMatch?.[1] || promptMatch?.[1];
    if (projectId) await persistMode(projectId);
    return previousFetch(input, init);
  };

  const style = document.createElement('style');
  style.textContent = `
    .generation-mode-control{display:grid;grid-template-columns:auto minmax(170px,230px);grid-template-rows:auto auto;align-items:center;gap:2px 7px;margin-right:3px}
    .generation-mode-control>span{font-size:7px;letter-spacing:.12em;color:var(--ink-2)}
    .generation-mode-control select{height:32px;border:1px solid var(--ink);border-radius:0;background:var(--paper);padding:0 7px;font-size:7px;letter-spacing:.06em;text-transform:uppercase;outline:none}
    .generation-mode-control small{grid-column:1/-1;max-width:280px;font-size:6px;line-height:1.15;color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  `;
  document.head.appendChild(style);

  installSelector();
  window.addEventListener('load', installSelector, {once: true});
})();
