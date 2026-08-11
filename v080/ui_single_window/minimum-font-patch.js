(() => {
  'use strict';

  const MIN_FONT_PT = 10;
  const MIN_FONT_PX = MIN_FONT_PT * 96 / 72;
  const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'SVG', 'PATH', 'DEFS', 'CLIPPATH', 'MASK']);

  function enforceElement(node) {
    if (!(node instanceof HTMLElement)) return;
    if (SKIP_TAGS.has(node.tagName)) return;
    const size = Number.parseFloat(window.getComputedStyle(node).fontSize || '0');
    if (Number.isFinite(size) && size + 0.01 < MIN_FONT_PX) {
      node.style.setProperty('font-size', `${MIN_FONT_PT}pt`, 'important');
      node.dataset.marinsMinFont = `${MIN_FONT_PT}pt`;
    }
  }

  function enforceTree(root = document) {
    if (root instanceof HTMLElement) enforceElement(root);
    const scope = root.querySelectorAll ? root.querySelectorAll('*') : [];
    scope.forEach(enforceElement);
  }

  function start() {
    enforceTree(document);

    const observer = new MutationObserver(mutations => {
      for (const mutation of mutations) {
        mutation.addedNodes.forEach(node => {
          if (node instanceof HTMLElement) enforceTree(node);
        });
        if (mutation.type === 'attributes' && mutation.target instanceof HTMLElement) {
          enforceElement(mutation.target);
        }
      }
    });

    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['class', 'style']
    });

    window.addEventListener('marins-generation-status', () => requestAnimationFrame(() => enforceTree(document)));
    window.addEventListener('resize', () => requestAnimationFrame(() => enforceTree(document)));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, {once: true});
  } else {
    start();
  }
})();
