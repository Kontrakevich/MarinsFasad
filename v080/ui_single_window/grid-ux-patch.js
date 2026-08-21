(() => {
  'use strict';

  const ZOOM_STEP = 0.05;
  const MIN_ZOOM = 0.10;
  const MAX_ZOOM = 8.00;
  let overrideZoomFactor = null;

  const $ = id => document.getElementById(id);

  function clampZoom(value) {
    return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(value * 100) / 100));
  }

  function currentZoomFactor() {
    if (overrideZoomFactor !== null) return overrideZoomFactor;
    const label = $('zoom-value')?.textContent || '';
    const match = label.match(/(\d+(?:\.\d+)?)%/);
    return match ? Number(match[1]) / 100 : 1;
  }

  function applyOverrideZoom() {
    if (overrideZoomFactor === null) return;
    const single = $('single-view');
    const grid = $('grid-view');
    const image = $('single-image');
    const canvas = $('geometry-canvas');

    single?.classList.add('actual');
    grid?.classList.add('actual');

    if (image?.naturalWidth) {
      image.style.width = `${Math.round(image.naturalWidth * overrideZoomFactor)}px`;
    }
    if (canvas?.width) {
      canvas.style.width = `${Math.round(canvas.width * overrideZoomFactor)}px`;
    }
    if ($('zoom-value')) {
      $('zoom-value').textContent = `${Math.round(overrideZoomFactor * 100)}%`;
    }
  }

  function changeZoom(delta) {
    overrideZoomFactor = clampZoom(currentZoomFactor() + delta);
    applyOverrideZoom();
  }

  function requestGridFullscreen() {
    const viewer = $('viewer');
    const gridVisible = !$('grid-view')?.classList.contains('hidden');
    if (!viewer || !gridVisible || document.fullscreenElement || !viewer.requestFullscreen) return;
    viewer.requestFullscreen().catch(() => {});
  }

  const zoomIn = $('zoom-in');
  const zoomOut = $('zoom-out');
  const fitView = $('fit-view');
  const actualView = $('actual-view');

  if (zoomIn) zoomIn.onclick = () => changeZoom(ZOOM_STEP);
  if (zoomOut) zoomOut.onclick = () => changeZoom(-ZOOM_STEP);

  if (fitView) {
    const originalFit = fitView.onclick;
    fitView.onclick = event => {
      overrideZoomFactor = null;
      originalFit?.call(fitView, event);
    };
  }

  if (actualView) {
    const originalActual = actualView.onclick;
    actualView.onclick = event => {
      overrideZoomFactor = 1;
      originalActual?.call(actualView, event);
      applyOverrideZoom();
    };
  }

  document.querySelectorAll('.mode-tabs button[data-view="grid"]').forEach(button => {
    const original = button.onclick;
    button.onclick = event => {
      original?.call(button, event);
      requestAnimationFrame(requestGridFullscreen);
    };
  });

  document.querySelectorAll('#pipeline button[data-stage="geometry"]').forEach(button => {
    const original = button.onclick;
    button.onclick = event => {
      original?.call(button, event);
      requestAnimationFrame(requestGridFullscreen);
    };
  });

  const canvas = $('geometry-canvas');
  canvas?.addEventListener('pointerdown', () => {
    requestGridFullscreen();
  }, {capture: true});

  document.addEventListener('fullscreenchange', () => {
    if (overrideZoomFactor !== null) requestAnimationFrame(applyOverrideZoom);
  });

  window.addEventListener('resize', () => {
    if (overrideZoomFactor !== null) requestAnimationFrame(applyOverrideZoom);
  });
})();
