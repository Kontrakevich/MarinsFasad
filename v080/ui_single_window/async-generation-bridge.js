(() => {
  'use strict';

  const nativeFetch = window.fetch.bind(window);
  const GENERATION_PATTERN = /\/api\/projects\/([^/]+)\/environment\/generate(?:\?.*)?$/;
  const POLL_INTERVAL_MS = 2000;
  const RETRY_INTERVAL_MS = 3000;
  const MAX_WAIT_MS = 25 * 60 * 1000;
  const TRANSIENT_HTTP_STATUSES = new Set([408, 425, 429, 502, 503, 504]);
  const activePolls = new Map();

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
    else if (status === 'processing') title.textContent = 'Генерация окружения выполняется в фоне…';
    else if (status === 'completed') title.textContent = 'Генерация окружения завершена';
    else if (status === 'error') title.textContent = 'Генерация завершилась с ошибкой';
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

    if (projectResult.networkError) return {kind: 'transient'};
    if (TRANSIENT_HTTP_STATUSES.has(projectResult.status)) return {kind: 'transient'};
    if (projectResult.status === 404) return {kind: 'missing-project'};
    if (!projectResult.ok) return {kind: 'transient'};

    const project = await readJson(projectResult);
    if (!project) return {kind: 'transient'};
    return {kind: 'project', status: normalizeProjectGeneration(project)};
  }

  async function projectSnapshotResponse(projectId, maxAttempts = 5) {
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      const recovery = await recoverStatusFromProject(projectId);
      if (recovery.kind === 'project') return jsonResponse(recovery.status.project, 200);
      if (recovery.kind === 'missing-project') return jsonResponse({detail: 'Проект генерации больше не найден.'}, 404);
      await sleep(350 + attempt * 250);
    }
    return null;
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

      if (result.networkError || TRANSIENT_HTTP_STATUSES.has(result.status)) {
        transientFailures += 1;
        showProgress('processing', transientFailures);
        window.dispatchEvent(new CustomEvent('marins-generation-status', {
          detail: {status: 'processing', transient_failures: transientFailures, project_id: projectId}
        }));
        continue;
      }

      let status = null;
      if (result.status === 404) {
        // Never duplicate the generation request. Recover from persisted project state.
        const recovery = await recoverStatusFromProject(projectId);
        if (recovery.kind === 'missing-project') {
          return {status: 'error', error: 'Проект генерации больше не найден.', project_id: projectId};
        }
        if (recovery.kind !== 'project') {
          transientFailures += 1;
          showProgress('processing', transientFailures);
          continue;
        }
        status = recovery.status;
      } else if (!result.ok) {
        const payload = await readJson(result);
        return {
          status: 'error',
          error: payload?.detail || `Ошибка проверки статуса генерации: HTTP ${result.status}`,
          project_id: projectId,
        };
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

      if (status.status === 'completed' || status.status === 'error') return status;
    }

    return {
      status: 'processing',
      background_timeout: true,
      project_id: projectId,
      error: null,
    };
  }

  async function recoverOrStart(input, init, projectId) {
    const statusUrl = `/api/projects/${projectId}/environment/generation-status`;
    let transientFailures = 0;

    for (let attempt = 0; attempt < 4; attempt += 1) {
      const startResult = await safeFetch(input, init);
      if (!startResult.networkError && !TRANSIENT_HTTP_STATUSES.has(startResult.status)) return startResult;

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
          return jsonResponse({job_id: status.job_id, status: status.status, status_url: statusUrl}, 202);
        }
        if (status?.status === 'completed') return jsonResponse(status.project, 200);
        if (status?.status === 'error') return jsonResponse({detail: status.error || 'Генерация окружения завершилась с ошибкой.'}, 502);
      } else if (!statusResult.networkError && statusResult.status === 404) {
        const recovery = await recoverStatusFromProject(projectId);
        const status = recovery.kind === 'project' ? recovery.status : null;
        if (status?.status === 'queued' || status?.status === 'processing') {
          return jsonResponse({job_id: status.job_id, status: status.status, status_url: statusUrl}, 202);
        }
        if (status?.status === 'completed') return jsonResponse(status.project, 200);
        if (status?.status === 'error') return jsonResponse({detail: status.error || 'Генерация окружения завершилась с ошибкой.'}, 502);
      }
      await sleep(RETRY_INTERVAL_MS);
    }

    return jsonResponse(
      {detail: 'Не удалось связаться с Codespaces. Запрос не будет продублирован. Повторно откройте проект и проверьте статус генерации.'},
      503
    );
  }

  function startDetachedPolling(statusUrl, projectId) {
    if (activePolls.has(projectId)) return activePolls.get(projectId);
    const promise = pollStatus(statusUrl, projectId, Date.now() + MAX_WAIT_MS)
      .then(status => {
        if (status?.background_timeout) {
          window.dispatchEvent(new CustomEvent('marins-generation-status', {
            detail: {
              status: 'processing',
              project_id: projectId,
              message: 'Генерация продолжает выполняться в фоне.'
            }
          }));
        } else if (status?.status === 'error') {
          window.dispatchEvent(new CustomEvent('marins-generation-status', {detail: status}));
        }
        return status;
      })
      .finally(() => activePolls.delete(projectId));
    activePolls.set(projectId, promise);
    return promise;
  }

  window.fetch = async function marinsFetch(input, init = {}) {
    const details = requestDetails(input, init);
    if (!details.matched) return nativeFetch(input, init);

    const startResponse = await recoverOrStart(input, init, details.projectId);
    if (startResponse.status === 200) return startResponse;
    if (startResponse.status !== 202) return startResponse;

    const started = await readJson(startResponse);
    const statusUrl = started?.status_url || `/api/projects/${details.projectId}/environment/generation-status`;
    showProgress(started?.status || 'queued');
    window.dispatchEvent(new CustomEvent('marins-generation-status', {
      detail: {job_id: started?.job_id || null, status: started?.status || 'queued', project_id: details.projectId}
    }));

    // Generation is a background job. Do not keep the UI's busy() promise open
    // until Nano Banana finishes. Poll in the background and return persisted
    // project state immediately so the button is released.
    startDetachedPolling(statusUrl, details.projectId);

    const snapshot = await projectSnapshotResponse(details.projectId);
    if (snapshot) return snapshot;

    // Only if Codespaces cannot return the project snapshot, fall back to the old
    // blocking behaviour rather than returning a non-project payload to app-v080.js.
    const finalStatus = await pollStatus(statusUrl, details.projectId, Date.now() + MAX_WAIT_MS);
    if (finalStatus?.status === 'completed' && finalStatus.project) return jsonResponse(finalStatus.project, 200);
    if (finalStatus?.status === 'error') return jsonResponse({detail: finalStatus.error || 'Генерация окружения завершилась с ошибкой.'}, 502);
    return jsonResponse({detail: 'Генерация продолжает выполняться в фоне. Используйте команду process для просмотра состояния.'}, 408);
  };
})();
