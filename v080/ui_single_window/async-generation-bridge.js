(() => {
  'use strict';

  const nativeFetch = window.fetch.bind(window);
  const GENERATION_PATTERN = /\/api\/projects\/[^/]+\/environment\/generate(?:\?.*)?$/;
  const POLL_INTERVAL_MS = 2000;
  const MAX_WAIT_MS = 20 * 60 * 1000;

  const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

  function generationRequest(input, init) {
    const url = typeof input === 'string' ? input : input?.url || '';
    const method = String(init?.method || input?.method || 'GET').toUpperCase();
    return method === 'POST' && GENERATION_PATTERN.test(url);
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

  function showProgress(status) {
    const title = document.getElementById('action-stage-title');
    if (!title) return;
    if (status === 'queued') title.textContent = 'Генерация поставлена в очередь';
    else if (status === 'processing') title.textContent = 'Генерация окружения выполняется…';
  }

  window.fetch = async function marinsFetch(input, init = {}) {
    if (!generationRequest(input, init)) return nativeFetch(input, init);

    const startResponse = await nativeFetch(input, init);
    if (startResponse.status !== 202) return startResponse;

    let started;
    try {
      started = await startResponse.clone().json();
    } catch (_) {
      return startResponse;
    }

    if (!started?.status_url) return startResponse;
    showProgress(started.status || 'queued');

    const deadline = Date.now() + MAX_WAIT_MS;
    while (Date.now() < deadline) {
      await sleep(POLL_INTERVAL_MS);
      const statusResponse = await nativeFetch(started.status_url, {
        method: 'GET',
        cache: 'no-store',
        headers: {'Accept': 'application/json'}
      });
      if (!statusResponse.ok) return statusResponse;

      const status = await statusResponse.json();
      showProgress(status.status);
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
        detail: 'Генерация продолжает выполняться в фоне. Обновите проект через несколько минут.'
      },
      408
    );
  };
})();
