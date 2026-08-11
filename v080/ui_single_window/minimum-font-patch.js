(() => {
  'use strict';

  const MIN_FONT_PT = 10;
  const MIN_FONT_PX = MIN_FONT_PT * 96 / 72;
  const LAYOUT_GRID_CONTRACT = 'system1-grid-console-v1';
  const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'SVG', 'PATH', 'DEFS', 'CLIPPATH', 'MASK']);

  function installLayoutGrid() {
    if (document.getElementById('marins-layout-grid-contract')) return;
    const style = document.createElement('style');
    style.id = 'marins-layout-grid-contract';
    style.dataset.contract = LAYOUT_GRID_CONTRACT;
    style.textContent = `
      :root{
        --projects:clamp(220px,13.5vw,250px);
        --inspector:clamp(360px,23vw,420px);
        --marins-min-font:10pt;
        --marins-line:1.35;
      }
      html,body{min-width:0;overflow:hidden}
      body,button,input,textarea,select,pre{font-size:var(--marins-min-font);line-height:var(--marins-line)}
      *,*::before,*::after{box-sizing:border-box}
      div,section,aside,header,footer,nav,main,article,form,label,figure,button,input,textarea,select,pre{min-width:0}

      .app-shell{height:100vh;grid-template-rows:64px 62px minmax(0,1fr);overflow:hidden}
      .app-header{grid-template-columns:var(--projects) minmax(0,1fr) var(--inspector);min-height:64px}
      .brand{padding:0 16px}.brand-logo{width:min(170px,100%);max-height:34px}
      .header-context{padding:0 16px;gap:10px;overflow:hidden}.header-context strong{font-size:11pt;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .system-meta{padding:8px 12px;gap:12px;align-content:center;justify-content:end;flex-wrap:wrap;overflow:hidden}
      .system-meta .meta-item,.system-meta .system-state,.system-meta .version-mark{max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

      .pipeline{grid-template-columns:var(--projects) repeat(5,minmax(0,1fr)) var(--inspector);min-height:62px}
      .pipeline-label,.pipeline-meta{padding:8px 12px;overflow:hidden}
      .pipeline button{padding:8px 10px;grid-template-columns:30px minmax(0,1fr);grid-template-rows:auto auto;align-content:center;min-height:62px;overflow:hidden}
      .pipeline button small{grid-row:1/3;align-self:start;padding-top:1px}
      .pipeline button span,.pipeline button b,.pipeline-label span,.pipeline-label small,.pipeline-meta span,.pipeline-meta small{max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

      .workspace-layout{grid-template-columns:var(--projects) minmax(0,1fr) var(--inspector);grid-template-rows:minmax(0,1fr)!important;min-height:0;overflow:hidden}
      .projects-pane{grid-row:1!important;min-height:0;overflow:hidden}.work-pane,.inspector-pane{min-height:0;overflow:hidden}.bottom-pane{display:none!important}

      .pane-heading{min-height:58px;padding:10px 12px}.pane-heading h2{font-size:15pt;line-height:1.15}
      .project-list{min-height:0;overflow:auto}.project-card{padding:12px}.project-card strong{font-size:10.5pt;line-height:1.35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .project-card span,.project-card small{font-size:10pt;line-height:1.4;white-space:normal;overflow-wrap:anywhere}
      .projects-footer{padding:10px 12px}.storage-note{gap:8px;align-items:center}.storage-note>*{min-width:0;overflow:hidden;text-overflow:ellipsis}

      .project-workspace{height:100%;min-height:0;grid-template-rows:60px 44px minmax(0,1fr) auto}
      .workspace-titlebar{min-height:60px;padding:8px 12px;gap:12px}.workspace-title{overflow:hidden}.workspace-title h1{font-size:16pt;line-height:1.1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .workspace-state{max-width:46%;display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap;text-align:right}.workspace-state>*{white-space:nowrap}

      .viewer-toolbar{min-height:44px;display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:stretch;overflow:hidden}
      .mode-tabs{display:flex;min-width:0;overflow:hidden}.mode-tabs button{flex:0 1 auto;min-width:72px;padding:0 10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .zoom-tools{display:flex;flex-wrap:nowrap;min-width:max-content}.zoom-tools button,.zoom-tools span{min-width:38px;padding:0 8px;white-space:nowrap}

      .viewer{min-height:0;overflow:hidden;padding:0}.single-view,.grid-view,.split-view{min-height:0;overflow:auto}.single-view{padding:12px}.single-view img{max-width:100%;max-height:100%;object-fit:contain}
      .canvas-scroll{padding:12px;min-height:0}.grid-legend{min-height:36px;padding:6px 10px;gap:12px;flex-wrap:wrap}.grid-legend span{white-space:normal}
      .split-view{grid-template-columns:repeat(2,minmax(0,1fr))}.split-view figure{padding:10px}.split-view figcaption{min-height:24px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

      .stage-actions{min-height:66px;display:grid;grid-template-columns:minmax(220px,1fr) auto;gap:12px;align-items:center;padding:8px 10px;overflow:visible}
      .action-context{min-width:0;margin:0}.action-context p,.action-context strong{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.action-context strong{font-size:10pt;line-height:1.35}
      .action-group{min-width:0;display:flex;justify-content:flex-end;align-items:center;gap:6px;flex-wrap:wrap}.action-group .button,.action-group button,.action-group select{min-height:36px;max-width:100%;padding:6px 10px;font-size:10pt;white-space:nowrap}
      #environment-actions select{min-width:150px;max-width:230px}

      .inspector-pane{display:grid;grid-template-rows:minmax(0,1fr);background:#102b43}
      .system1-command-console{height:100%;min-height:0;display:grid;grid-template-rows:auto auto minmax(0,1fr) auto auto;overflow:hidden}
      .command-console-header{display:grid;grid-template-columns:minmax(0,1fr) minmax(120px,42%);gap:10px;padding:10px 12px;align-items:start}
      .command-console-header>div{min-width:0}.command-console-header strong{font-size:11pt!important;line-height:1.25}.command-console-header span,.command-console-header small,.command-console-context b{font-size:10pt!important;line-height:1.3}
      .command-console-context{text-align:right;overflow:hidden}.command-console-context b{display:block;max-width:100%!important;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.command-console-context small{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .command-process-strip{grid-template-columns:110px minmax(0,1fr);min-height:48px}.command-process-strip span,.command-process-strip p{font-size:10pt!important;line-height:1.3}.command-process-strip p{padding:6px 10px;white-space:normal;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
      .command-console-output{min-height:0;overflow:auto;padding:9px}.command-console-entry{padding:8px 9px;margin-bottom:8px}.command-console-entry header{font-size:10pt!important;line-height:1.3;flex-wrap:wrap}.command-console-body{font-size:10pt!important;line-height:1.45;overflow-wrap:anywhere}
      .command-prompt-editor{min-height:260px;font-size:10pt!important;line-height:1.45}.command-inline-actions{flex-wrap:wrap}.command-inline-actions button{font-size:10pt!important;min-height:34px}
      .command-next{padding:8px 9px}.command-next>span{font-size:10pt!important}.command-suggestions{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.command-suggestions button{font-size:10pt!important;min-height:34px;padding:6px 8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .command-form{grid-template-columns:28px minmax(0,1fr) 62px;min-height:46px}.command-form>span{font-size:13pt!important}.command-form input,.command-form button{font-size:10pt!important;min-height:46px}.command-form input{padding:0 6px}
      .command-candidate-row{grid-template-columns:minmax(0,1fr) auto!important}.command-candidate-row b,.command-candidate-row span,.command-candidate-row a{font-size:10pt!important}.command-candidate-row span{white-space:normal!important;overflow-wrap:anywhere}

      .button,button,select,input,textarea{max-width:100%}.code-output,.events-output,pre{white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word}

      @media (max-width:1500px){
        :root{--projects:210px;--inspector:360px}
        .app-shell{grid-template-rows:66px 66px minmax(0,1fr)}.pipeline,.pipeline button{min-height:66px}
        .stage-actions{grid-template-columns:1fr;gap:6px;padding:8px 10px}.action-group{justify-content:flex-start}.action-context{width:100%}
      }
      @media (max-width:1180px){
        :root{--projects:190px;--inspector:330px}
        .system-meta .meta-item{display:none}.pipeline-meta{display:none}.pipeline{grid-template-columns:var(--projects) repeat(5,minmax(0,1fr))}
        .app-header{grid-template-columns:var(--projects) minmax(0,1fr) var(--inspector)}.command-suggestions{grid-template-columns:1fr}.workspace-state{display:none}
      }
    `;
    document.head.appendChild(style);
  }

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
    installLayoutGrid();
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

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once:true});
  else start();
})();
