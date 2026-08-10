(() => {
  'use strict';

  const nativeFetch = window.fetch.bind(window);
  const GENERATION_PATTERN = /\/api\/projects\/([^/]+)\/environment\/generate(?:\?.*)?$/;
  const POLL_INTERVAL_MS = 2000;
  const RETRY_INTERVAL_MS = 3000;
  const MAX_WAIT_MS = 25 * 60 * 1000;
  const TRANSIENT_HTTP_STATUSES = new Set([408, 425, 429, 502, 503, 504]);

  const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

  function requestDetails(input, init) {
    const url = typeof input === 'string' ? input : input?.url || '';
    const method = String(init?.method || input?.method || 'GET').toUpperCase();
    const match = url.match(GENERATION_PATTERN);
    return {
      matched: method === 'POST' && !!match,
      url,
      projectId: match?.[1] || ''
    };
  }

  function jsonResponse(payload, status) {
    return new Response(JSON.stringify(payload), {
      status,
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'no-store'
      }
    });
  }

  function showProgress(status, transientFailures = 0) {
    const title = document.getElementById('action-stage-title');
    if (!title) return;
    if (transientFailures > 0) {
      title.textContent = 'Генерация продолжается. Восстанавливается связь с Codespaces…';
      return;
    }
    if (status === 'queued') title.textContent = 'Генерация поставлена в очередь';
    else if (status === 'processing') title.textContent = 'Генерация окружения выполняется…';
    else if (status === 'completed') title.textContent = 'Генерация окружения завершена';
  }

  async function safeFetch(url, init) {
    try {
      return await nativeFetch(url, init);
    } catch (error) {
      return {networkError: error};
    }
  }

  async function readJson(response) {
    try {
      return await response.clone().json();
    } catch (_) {
      return null;
    }
  }

  function normalizeProjectGeneration(project) {
    const generation = project?.generation || {};
    let status = generation.status || project?.pipeline?.environment || 'idle';
    if (status === 'review' || status === 'approved') status = 'completed';
    if (status === 'ready' && project?.assets?.environment_candidate) status = 'completed';
    return {
      job_id: generation.job_id || null,
      status,
      error: generation.error || null,
      project
    };
  }

  async function recoverStatusFromProject(projectId) {
    const projectResult = await safeFetch(`/api/projects/${projectId}`, {
      method: 'GET',
      cache: 'no-store',
      headers: {
        'Accept': 'application/json',
        'Cache-Control': 'no-cache'
      }
    });

    if (projectResult.networkError) {
      return {kind: 'transient'};
    }
    if (TRANSIENT_HTTP_STATUSES.has(projectResult.status)) {
      return {kind: 'transient'};
    }
    if (projectResult.status === 404) {
      return {kind: 'missing-project'};
    }
    if (!projectResult.ok) {
      return {kind: 'transient'};
    }

    const project = await readJson(projectResult);
    if (!project) return {kind: 'transient'};
    return {kind: 'project', status: normalizeProjectGeneration(project)};
  }

  async function pollStatus(statusUrl, projectId, deadline) {
    let transientFailures = 0;

    while (Date.now() < deadline) {
      await sleep(transientFailures > 0 ? RETRY_INTERVAL_MS : POLL_INTERVAL_MS);
      const result = await safeFetch(statusUrl, {
        method: 'GET',
        cache: 'no-store',
        headers: {
          'Accept': 'application/json',
          'Cache-Control': 'no-cache'
        }
      });

      if (result.networkError) {
        transientFailures += 1;
        showProgress('processing', transientFailures);
        continue;
      }

      if (TRANSIENT_HTTP_STATUSES.has(result.status)) {
        transientFailures += 1;
        showProgress('processing', transientFailures);
        continue;
      }

      let status = null;
      if (result.status === 404) {
        // Codespaces / stale frontend-server combinations can temporarily expose
        // the project API while the dedicated status route is unavailable.
        // Never duplicate the generation request: recover from persisted project state.
        const recovery = await recoverStatusFromProject(projectId);
        if (recovery.kind === 'missing-project') {
          return jsonResponse({detail: 'Проект генерации больше не найден.'}, 404);
        }
        if (recovery.kind !== 'project') {
          transientFailures += 1;
          showProgress('processing', transientFailures);
          continue;
        }
        status = recovery.status;
      } else if (!result.ok) {
        const payload = await readJson(result);
        return jsonResponse(
          {detail: payload?.detail || `Ошибка проверки статуса генерации: HTTP ${result.status}`},
          result.status
        );
      } else {
        status = await readJson(result);
      }

      if (!status) {
        transientFailures += 1;
        showProgress('processing', transientFailures);
        continue;
      }

      transientFailures = 0;
      showProgress(status.status, 0);
      window.dispatchEvent(new CustomEvent('marins-generation-status', {detail: status}));

      if (status.status === 'completed') {
        return jsonResponse(status.project, 200);
      }
      if (status.status === 'error') {
        return jsonResponse(
          {detail: status.error || 'Генерация окружения завершилась с ошибкой.'},
          502
        );
      }
    }

    return jsonResponse(
      {
        detail: 'Генерация продолжает выполняться в фоне. Откройте проект повторно через несколько минут — результат сохранится автоматически.'
      },
      408
    );
  }

  async function recoverOrStart(input, init, projectId) {
    const statusUrl = `/api/projects/${projectId}/environment/generation-status`;
    let transientFailures = 0;

    for (let attempt = 0; attempt < 4; attempt += 1) {
      const startResult = await safeFetch(input, init);
      if (!startResult.networkError && !TRANSIENT_HTTP_STATUSES.has(startResult.status)) {
        return startResult;
      }

      transientFailures += 1;
      showProgress('processing', transientFailures);

      const statusResult = await safeFetch(statusUrl, {
        method: 'GET',
        cache: 'no-store',
        headers: {'Accept': 'application/json', 'Cache-Control': 'no-cache'}
      });
      if (!statusResult.networkError && statusResult.ok) {
        const status = await readJson(statusResult);
        if (status?.status === 'queued' || status?.status === 'processing') {
          return jsonResponse(
            {job_id: status.job_id, status: status.status, status_url: statusUrl},
            202
          );
        }
        if (status?.status === 'completed') {
          return jsonResponse(status.project, 200);
        }
        if (status?.status === 'error') {
          return jsonResponse(
            {detail: status.error || 'Генерация окружения завершилась с ошибкой.'},
            502
          );
        }
      } else if (!statusResult.networkError && statusResult.status === 404) {
        const recovery = await recoverStatusFromProject(projectId);
        const status = recovery.kind === 'project' ? recovery.status : null;
        if (status?.status === 'queued' || status?.status === 'processing') {
          return jsonResponse(
            {job_id: status.job_id, status: status.status, status_url: statusUrl},
            202
          );
        }
        if (status?.status === 'completed') {
          return jsonResponse(status.project, 200);
        }
        if (status?.status === 'error') {
          return jsonResponse(
            {detail: status.error || 'Генерация окружения завершилась с ошибкой.'},
            502
          );
        }
      }
      await sleep(RETRY_INTERVAL_MS);
    }

    return jsonResponse(
      {detail: 'Не удалось связаться с Codespaces. Запрос не будет продублирован. Повторно откройте проект и проверьте статус генерации.'},
      503
    );
  }

  window.fetch = async function marinsFetch(input, init = {}) {
    const details = requestDetails(input, init);
    if (!details.matched) return nativeFetch(input, init);

    const startResponse = await recoverOrStart(input, init, details.projectId);
    if (startResponse.status === 200) return startResponse;
    if (startResponse.status !== 202) return startResponse;

    const started = await readJson(startResponse);
    const statusUrl = started?.status_url
      || `/api/projects/${details.projectId}/environment/generation-status`;
    showProgress(started?.status || 'queued');

    return pollStatus(statusUrl, details.projectId, Date.now() + MAX_WAIT_MS);
  };
})();
