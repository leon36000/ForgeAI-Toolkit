(function () {
  'use strict';

  const state = {
    lang: document.documentElement.lang || 'fr',
    theme: document.documentElement.dataset.theme || 'dark',
    detect: null,
    stacks: [],
    spheres: [],
    recommendedId: null,
    selectedId: null,
    sphereId: 'S1',
    step: 1,
    localModels: null,
    modelTier: 'tous',
    modelSearch: '',
    modelsChosen: {},
    embeddingsChosen: {},
    engines: null,
    embeddingSearch: '',
    bricks: null,
    overrides: {},
    inventaire: null,     // /api/discover ; null = indisponible, jamais bloquant
    adoptChoisis: {},     // { id: true } — services que l'utilisateur adopte
    search: '',
    i18nTables: {},
    embeddingsLoaded: false,
    detectError: false,
    deployStatus: null // null=jamais lancé | 'running' | 'ok' | 'failed' (UI-039, preuve backend)
  };

  async function loadI18n(lang) {
    if (state.i18nTables[lang]) return;
    try {
      state.i18nTables[lang] = await fetchJson(`/api/i18n/${encodeURIComponent(lang)}`);
    } catch (e) {
      state.i18nTables[lang] = {};
    }
  }

  function t(key) {
    return (state.i18nTables[state.lang] || {})[key] || key;
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function setTheme(theme) {
    state.theme = theme;
    document.documentElement.dataset.theme = theme;
    document.querySelectorAll('#theme-toggle button[data-theme]').forEach((btn) => {
      btn.setAttribute('aria-pressed', String(btn.dataset.theme === theme));
    });
  }

  async function setLang(lang) {
    await loadI18n(lang);
    state.lang = lang;
    document.documentElement.lang = lang;
    document.querySelectorAll('#lang-toggle button[data-lang]').forEach((btn) => {
      btn.setAttribute('aria-pressed', String(btn.dataset.lang === lang));
    });
    const table = state.i18nTables[lang] || {};
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.dataset.i18n;
      if (table[key]) {
        el.textContent = table[key];
      }
    });
    document.querySelectorAll('[data-i18n-aria]').forEach((el) => {
      const key = el.dataset.i18nAria;
      if (table[key]) {
        el.setAttribute('aria-label', table[key]);
      }
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
      const key = el.dataset.i18nPlaceholder;
      if (table[key]) {
        el.placeholder = table[key];
      }
    });
    renderHardware();
    renderStacks();
    if (state.selectedId) {
      const stack = state.stacks.find((s) => s.id === state.selectedId);
      const full = state.stackDetail;
      if (stack && full) {
        renderDetail(stack, full);
      }
    }
    if (state.bricks) {
      renderSphereSteps();
      renderBricks();
    }
    if (state.models !== undefined) renderModels();
    if (state.nodes !== undefined) renderNodes();
    if (state.summary) renderSummary();
    if (state.localModels) renderLocalModels();
    if (state.embeddingsLoaded) renderEmbeddings();
    applyStepStatuses(); // UI-039 : libellés textuels de statut traduits (fonction hoistée)
  }

  async function fetchJson(path) {
    const res = await fetch(path);
    if (!res.ok) {
      throw new Error(`${path} -> ${res.status}`);
    }
    return res.json();
  }

  function renderHardware() {
    const container = document.getElementById('hardware-content');
    if (!state.detect) {
      container.innerHTML = `<p data-i18n="loading">${escapeHtml(t('loading'))}</p>`;
      return;
    }
    const d = state.detect;
    const gpus = Array.isArray(d.gpus) ? d.gpus : [];
    const gpuHtml = gpus.length
      ? gpus.map((g) => {
          const label = (g && typeof g === 'object')
            ? `${g.name || g.vendor || '?'}${g.vram_mb ? ` — ${Math.round(g.vram_mb / 1024)} GB VRAM` : ''}`
            : String(g);
          return `<li>${escapeHtml(label)}</li>`;
        }).join('')
      : `<li>${escapeHtml(t('hardware_no_gpu'))}</li>`;
    container.innerHTML = `
      <ul class="detail-list">
        <li><strong>${escapeHtml(t('hardware_cpu'))}:</strong> ${escapeHtml(d.cpu_model || '—')}</li>
        <li><strong>${escapeHtml(t('hardware_gpu'))}:</strong> ${escapeHtml(gpus.length)}</li>
        <li><strong>${escapeHtml(t('hardware_ram'))}:</strong> ${escapeHtml(d.ram_gb !== undefined ? d.ram_gb + ' GB' : '—')}</li>
      </ul>
      <ul class="detail-list">${gpuHtml}</ul>
    `;
  }

  function sphereName(sphereId) {
    const sp = state.spheres.find((s) => s.id === sphereId);
    if (!sp) return sphereId;
    return state.lang === 'en' ? sp.name_en : sp.name_fr;
  }

  function renderStacks() {
    const grid = document.getElementById('stacks-grid');
    if (!state.stacks.length) {
      grid.innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
      return;
    }
    grid.innerHTML = state.stacks.map((stack) => {
      const isRecommended = stack.id === state.recommendedId;
      const shortKeys = ['S5', 'S4', 'S7'].filter((k) => stack.defaults && stack.defaults[k]);
      const defaultsHtml = shortKeys.map((k) => {
        const name = sphereName(k);
        const val = stack.defaults[k];
        return `<span class="def-pill" title="${escapeHtml(name)}">${escapeHtml(k)}: ${escapeHtml(val)}</span>`;
      }).join('');
      return `
        <article class="stack-card${isRecommended ? ' recommended' : ''}${state.selectedId === stack.id ? ' selected' : ''}"
                 data-stack-id="${escapeHtml(stack.id)}" tabindex="0" role="button" aria-pressed="${state.selectedId === stack.id}">
          <div class="stack-meta">
            <span class="n-deploy-badge">${stack.n_deploy} ${escapeHtml(t('n_deploy_label'))}</span>
            ${isRecommended ? `<span class="recommended-badge">${escapeHtml(t('recommended'))}</span>` : ''}
          </div>
          <h3>${escapeHtml(stack.name)}</h3>
          <p class="stack-desc">${escapeHtml(state.lang === 'en' ? stack.description_en : stack.description_fr)}</p>
          <div class="stack-defaults">${defaultsHtml}</div>
        </article>
      `;
    }).join('');

    grid.querySelectorAll('.stack-card').forEach((card) => {
      card.addEventListener('click', () => selectStack(card.dataset.stackId));
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          selectStack(card.dataset.stackId);
        }
      });
    });
  }

  async function selectStack(stackId) {
    state.selectedId = stackId;
    document.querySelectorAll('.stack-card').forEach((c) => {
      const active = c.dataset.stackId === stackId;
      c.classList.toggle('selected', active);
      c.setAttribute('aria-pressed', String(active));
    });
    const summary = state.stacks.find((s) => s.id === stackId);
    try {
      const full = await fetchJson(`/api/stacks/${encodeURIComponent(stackId)}`);
      state.stackDetail = full;
      renderDetail(summary, full);
      state.bricks = null;
      state.summary = null;
      goToStep(state.step);
    } catch (e) {
      const detail = document.getElementById('stack-detail');
      detail.classList.remove('hidden');
      detail.innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
    }
  }

  function closeDetail() {
    state.selectedId = null;
    state.stackDetail = null;
    document.querySelectorAll('.stack-card').forEach((c) => {
      c.classList.remove('selected');
      c.setAttribute('aria-pressed', 'false');
    });
    const detail = document.getElementById('stack-detail');
    detail.classList.add('hidden');
    detail.innerHTML = '';
    goToStep(2);
  }

  function renderDetail(summary, full) {
    const detail = document.getElementById('stack-detail');
    const isRecommended = summary.id === state.recommendedId;
    const defaults = full.default_by_sphere || {};
    const defaultKeys = Object.keys(defaults).sort();
    const defaultsHtml = defaultKeys.map((sid) => {
      const name = sphereName(sid);
      const val = defaults[sid];
      return `<div class="stack-defaults">
        <span class="def-pill">${escapeHtml(name)} (${escapeHtml(sid)})</span>
        <span class="def-pill">${escapeHtml(val)}</span>
      </div>`;
    }).join('');

    const wiring = Array.isArray(full.wiring) ? full.wiring : [];
    const wiringHtml = wiring.length
      ? wiring.map((w) => `<li>${escapeHtml(w)}</li>`).join('')
      : `<li>—</li>`;

    detail.classList.remove('hidden');
    detail.innerHTML = `
      <div class="detail-header">
        <div class="stack-meta">
          ${isRecommended ? `<span class="recommended-badge">${escapeHtml(t('recommended'))}</span>` : ''}
          <span class="n-deploy-badge">${summary.n_deploy} ${escapeHtml(t('n_deploy_label'))}</span>
        </div>
        <h3>${escapeHtml(summary.name)}</h3>
        <p class="stack-desc">${escapeHtml(state.lang === 'en' ? summary.description_en : summary.description_fr)}</p>
        <button class="btn" id="stack-detail-close">${escapeHtml(t('close'))}</button>
      </div>
      <h4>${escapeHtml(t('defaults_title'))}</h4>
      ${defaultsHtml}
      <h4>${escapeHtml(t('wiring_title'))}</h4>
      <ul class="detail-list">${wiringHtml}</ul>
    `;

    document.getElementById('stack-detail-close').addEventListener('click', closeDetail);
  }

  /* ---------- Briques additionnelles (IMPL-4) ---------- */

  function overrideKey() {
    return state.selectedId || '_none_';
  }

  // Briques réellement AU PLAN = celles cochées. Source UNIQUE partagée par le POST et
  // l'écran d'inventaire : proposer d'adopter une brique non déployée serait un choix
  // impossible à honorer.
  function briquesDuPlan() {
    return Object.entries(state.overrides[overrideKey()] || {})
      .filter(function(e){ return e[1]; }).map(function(e){ return e[0]; });
  }

  async function chargerInventaire() {
    try {
      const res = await fetch('/api/discover?node=local');
      if (!res.ok) throw new Error('/api/discover -> ' + res.status);
      state.inventaire = await res.json();
    } catch (e) {
      // L'inventaire est une COMMODITÉ : son indisponibilité ne doit jamais empêcher de
      // déployer. On retombe simplement sur « aucun service détecté ». L'erreur est
      // journalisée : un inventaire absent doit rester diagnosticable, pas silencieux.
      console.warn('inventaire indisponible, déploiement sans adoption :', e);
      state.inventaire = null;
    }
    renderInventaire();
  }

  function renderInventaire() {
    const container = document.getElementById('inventaire-content');
    if (!container) return;
    const services = ForgeAIAdoption.servicesAdoptables(state.inventaire, briquesDuPlan());
    container.innerHTML = '';
    if (!services.length) {
      // Jamais de liste vide muette : l'utilisateur doit savoir que la recherche a eu lieu.
      const p = document.createElement('p');
      p.className = 'muted';
      p.textContent = t('inventaire_vide');
      container.appendChild(p);
      return;
    }
    services.forEach(function(svc){
      const label = document.createElement('label');
      label.className = 'inventaire-item';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.id = 'adopt-' + svc.id;
      cb.checked = !!state.adoptChoisis[svc.id];
      cb.addEventListener('change', function(){
        if (cb.checked) state.adoptChoisis[svc.id] = true;
        else delete state.adoptChoisis[svc.id];
      });
      label.appendChild(cb);
      label.appendChild(document.createTextNode(' ' + svc.id + ' \u2014 ' + svc.endpoint));
      container.appendChild(label);
    });
  }

  // Fragment `adopt` du corps POST /api/deploy. Rendu VIDE quand rien n'est coché : le corps
  // est alors strictement identique à celui d'avant D4 (équivalence stricte, CA-4).
  // Extrait en fonction nommée plutôt qu'en expression inline : le quality gate refusait
  // l'IIFE dans le littéral (maintenabilité), et un nom rend l'intention lisible.
  function champAdopt() {
    const choix = ForgeAIAdoption.servicesAdoptables(state.inventaire, briquesDuPlan())
      .map(function (sv) {
        return { id: sv.id, endpoint: sv.endpoint, adopte: !!state.adoptChoisis[sv.id] };
      });
    const dict = ForgeAIAdoption.construireAdopt(choix);
    return Object.keys(dict).length ? { adopt: dict } : {};
  }

  function isChecked(brick) {
    if (brick.locked) return true;
    const ov = state.overrides[overrideKey()];
    if (ov && Object.prototype.hasOwnProperty.call(ov, brick.id)) return ov[brick.id];
    return brick.installed;
  }

  function renderSphereSteps() {
    const nav = document.getElementById('sphere-steps');
    nav.innerHTML = state.spheres.map((sp) => `
      <button class="sphere-step${sp.id === state.sphereId ? ' active' : ''}" data-sphere="${escapeHtml(sp.id)}"
              aria-pressed="${sp.id === state.sphereId}">
        <span class="sphere-num">${sp.num}</span>
        <span class="sphere-label">${escapeHtml(state.lang === 'en' ? sp.name_en : sp.name_fr)}</span>
        <span class="sphere-count">${sp.count}</span>
      </button>
    `).join('');
    nav.querySelectorAll('.sphere-step').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.sphereId = btn.dataset.sphere;
        loadBricks();
      });
    });
  }

  async function loadBricks() {
    renderSphereSteps();
    const list = document.getElementById('bricks-list');
    list.innerHTML = `<p>${escapeHtml(t('loading'))}</p>`;
    try {
      const stackQ = state.selectedId ? `&stack=${encodeURIComponent(state.selectedId)}` : '';
      state.bricks = await fetchJson(`/api/bricks?sphere=${encodeURIComponent(state.sphereId)}${stackQ}`);
    } catch (e) {
      state.bricks = null;
      list.innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
      applyStepStatuses();
      return;
    }
    renderBricks();
    renderInventaire();  // re-filtre sur la nouvelle sélection (pas de refetch)
    applyStepStatuses(); // UI-039 : preuve étape 5 (chargement backend réel) mise à jour
  }

  function renderCounts(shown) {
    const el = document.getElementById('bricks-counts');
    if (!state.bricks) { el.textContent = ''; return; }
    const bricks = state.bricks.bricks;
    const installed = bricks.filter((b) => b.installed).length;
    const checked = bricks.filter((b) => isChecked(b)).length;
    el.textContent = t('counts_tpl')
      .replace('{installed}', installed)
      .replace('{checked}', checked)
      .replace('{total}', state.bricks.total) + (shown < bricks.length ? ` (${shown}/${bricks.length})` : '');
  }

  function renderBricks() {
    const list = document.getElementById('bricks-list');
    if (!state.bricks) { list.innerHTML = ''; renderCounts(0); return; }
    const q = state.search.trim().toLowerCase();
    const visible = state.bricks.bricks.filter((b) => {
      if (!q) return true;
      const desc = state.lang === 'en' ? b.description_en : b.description_fr;
      return (b.id + ' ' + b.name + ' ' + (desc || '')).toLowerCase().includes(q);
    });
    renderCounts(visible.length);
    if (!visible.length) {
      list.innerHTML = `<p>${escapeHtml(t('no_results'))}</p>`;
      return;
    }
    list.innerHTML = visible.map((b) => {
      const desc = state.lang === 'en' ? b.description_en : b.description_fr;
      const checked = isChecked(b);
      const badges = [
        b.installed ? `<span class="badge-installed">${escapeHtml(t('installed_badge'))}</span>` : '',
        b.locked ? `<span class="badge-locked">${escapeHtml(t('locked_badge'))}</span>` : '',
        b.default ? `<span class="badge-default">${escapeHtml(t('default_badge'))}</span>` : ''
      ].join('');
      return `
        <label class="brick-row${b.installed ? ' installed' : ''}${b.locked ? ' locked' : ''}">
          <input type="checkbox" data-brick-id="${escapeHtml(b.id)}"
                 ${checked ? 'checked' : ''} ${b.locked ? 'disabled' : ''}
                 aria-label="${escapeHtml(b.name)}">
          <span class="brick-main">
            <span class="brick-head">
              <span class="brick-name">${escapeHtml(b.name)}</span>
              <span class="brick-stars" title="${escapeHtml(t('stars_label'))}">★ ${b.stars}</span>
              ${badges}
            </span>
            <span class="brick-desc">${escapeHtml(desc || '')}</span>
          </span>
        </label>
      `;
    }).join('');
    list.querySelectorAll('input[type="checkbox"]:not([disabled])').forEach((cb) => {
      cb.addEventListener('change', () => {
        const key = overrideKey();
        if (!state.overrides[key]) state.overrides[key] = {};
        state.overrides[key][cb.dataset.brickId] = cb.checked;
        renderCounts(visible.length);
      });
    });
  }

  function showBricksSection() {
    document.getElementById('bricks').classList.remove('hidden');
    loadBricks();
  }

  function hideBricksSection() {
    document.getElementById('bricks').classList.add('hidden');
    state.bricks = null;
  }

  /* ---------- Modèles & clés API (B-02c) ---------- */

  async function loadModels() {
    const list = document.getElementById('models-list');
    try {
      state.models = await fetchJson('/api/models');
    } catch (e) {
      list.innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
      return;
    }
    renderModels();
  }

  function renderModels() {
    const list = document.getElementById('models-list');
    const models = state.models || [];
    if (!models.length) {
      list.innerHTML = `<p class="form-note">${escapeHtml(t('no_models'))}</p>`;
      return;
    }
    list.innerHTML = models.map((m) => `
      <div class="model-row">
        <span class="brick-name">${escapeHtml(m.name)}</span>
        <span class="def-pill">${escapeHtml(m.provenance)}</span>
        <span class="def-pill">${escapeHtml(m.model_id)}</span>
        ${m.key_fingerprint ? `<span class="brick-stars" title="${escapeHtml(t('fingerprint_label'))}">${escapeHtml(String(m.key_fingerprint).slice(0, 16))}…</span>` : ''}
      </div>
    `).join('');
  }

  /* ---------- Résumé & Déploiement (B-02e) ---------- */

  async function loadSummary() {
    if (!state.selectedId) return;
    const box = document.getElementById('deploy-summary');
    try {
      state.summary = await fetchJson(`/api/summary?stack=${encodeURIComponent(state.selectedId)}`);
    } catch (e) {
      box.innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
      return;
    }
    renderSummary();
    populateNodeChoices();
    populateRagChoices();
    chargerInventaire();   // l'inventaire dépend des briques cochées : on le charge en arrivant ici
  }

  function renderSummary() {
    const box = document.getElementById('deploy-summary');
    const s = state.summary;
    if (!s) { box.innerHTML = ''; return; }
    const backends = (s.backends && s.backends.length) ? s.backends.join(', ') : t('s_none');
    box.innerHTML = `
      <div class="model-row">
        <span class="brick-name">${escapeHtml(t('s_stack'))}: ${escapeHtml(s.stack.name)}</span>
        <span class="def-pill">${s.stack.n_deploy} ${escapeHtml(t('s_bricks'))}</span>
        <span class="def-pill">${s.chassis} ${escapeHtml(t('s_chassis'))}</span>
      </div>
      <div class="model-row">
        <span class="brick-name">${escapeHtml(t('hardware_cpu'))}: ${escapeHtml(s.hardware.cpu_model || '—')}</span>
        <span class="def-pill">GPU: ${s.hardware.gpus}</span>
        <span class="def-pill">RAM: ${escapeHtml(String(s.hardware.ram_gb))} GB</span>
      </div>
      <div class="model-row">
        <span class="brick-name">${escapeHtml(t('s_backends'))}: ${escapeHtml(backends)}</span>
      </div>
    `;
  }

  function populateNodeChoices() {
    const sel = document.getElementById('deploy-node-select');
    if (!sel || !state.summary) return;
    const keep = new Set(['local', 'auto']);
    [...sel.options].forEach((o) => { if (!keep.has(o.value)) o.remove(); });
    (state.summary.nodes || []).forEach((n) => {
      const name = typeof n === 'string' ? n : (n.name || n.hostname);
      if (!name) return;
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
    });
  }

  function populateRagChoices() {
    const sel = document.getElementById('deploy-rag-select');
    if (!sel) return;
    const keep = new Set(['local', 'auto']);
    [...sel.options].forEach((o) => { if (!keep.has(o.value)) o.remove(); });
    let nodes = [];
    if (state.summary && Array.isArray(state.summary.nodes)) {
      nodes = state.summary.nodes;
    } else if (state.nodes && Array.isArray(state.nodes.nodes)) {
      nodes = state.nodes.nodes;
    }
    nodes.forEach((n) => {
      const name = typeof n === 'string' ? n : (n.name || n.hostname);
      if (!name) return;
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
    });
  }

  function showDeploySection() {
    document.getElementById('deploy').classList.remove('hidden');
    loadSummary();
  }

  function hideDeploySection() {
    document.getElementById('deploy').classList.add('hidden');
    state.summary = null;
  }

  // OPS-031E : un SEUL flux partagé entre l'étape 7 et le panneau d'exploitation. Ouvrir un second
  // EventSource dupliquerait la charge serveur et désynchroniserait les deux vues.
  let deployLogEventSource = null;
  let deployLogBuffer = '';

  function renderDeployLog() {
    document.querySelectorAll('#deploy-log, #ops-log').forEach((el) => {
      el.classList.remove('hidden');
      el.textContent = deployLogBuffer;
      el.scrollTop = el.scrollHeight;
    });
  }

  function streamDeployLog(logElement, statusElement) {
    const log = logElement || document.getElementById('deploy-log');
    const status = statusElement || document.getElementById('deploy-form-status');
    if (deployLogEventSource) {  // flux déjà ouvert : on rattache la vue, sans réabonnement
      renderDeployLog();
      return;
    }
    log.classList.remove('hidden');
    log.textContent = '';
    deployLogBuffer = '';
    const es = new EventSource('/api/deploy/events');
    deployLogEventSource = es;
    es.onmessage = (ev) => {
      deployLogBuffer += ev.data + '\n';
      renderDeployLog();
    };
    es.addEventListener('end', (ev) => {
      es.close();
      deployLogEventSource = null;
      let code = null;
      try { code = JSON.parse(ev.data).exit_code; } catch (e) { /* fin sans code */ }
      state.deployStatus = code === 0 ? 'ok' : 'failed'; // UI-039 : preuve backend réelle, jamais positionnelle
      if (code === 0) {
        status.textContent = t('deploy_done_ok');
        status.classList.remove('error');
      } else {
        status.textContent = t('deploy_done_fail').replace('{code}', String(code));
        status.classList.add('error');
      }
      applyStepStatuses();
    });
    es.onerror = () => { es.close(); };
  }

  function initDeployForm() {
    const form = document.getElementById('deploy-form');
    if (!form) return;
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const status = document.getElementById('deploy-form-status');
      const confirm = form.elements.confirm.value.trim();
      if (confirm !== 'FORCER') {
        status.textContent = t('deploy_need_forcer');
        status.classList.add('error');
        return;
      }
      status.classList.remove('error');
      status.textContent = t('deploy_running');
      state.deployStatus = 'running'; // UI-039 : jamais 'done' tant que l'exit_code n'est pas connu
      applyStepStatuses();
      try {
        const res = await fetch('/api/deploy', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            stack: state.selectedId,
            backend: form.elements.backend.value,
            node: form.elements.node ? form.elements.node.value : 'local',
            models: Object.entries(state.modelsChosen).map(([hf_id, v]) => ({hf_id, node: v.node, engine: v.engine})),
            embeddings: Object.entries(state.embeddingsChosen).map(([hf_id, v]) => ({hf_id, node: v.node, engine: v.engine})),
            bricks: briquesDuPlan(),
            rag_node: form.elements.rag_node.value,
            confirm: confirm,
            ...champAdopt()
          })
        });
        const body = await res.json();
        if (!res.ok) throw new Error(body.error || res.status);
        form.elements.confirm.value = '';
        streamDeployLog();
      } catch (e) {
        status.textContent = String(e.message || e);
        status.classList.add('error');
      }
    });
  }


  /* ---------- Modèles IA, Embeddings & moteurs (P0.3 / N2b) ---------- */

  async function loadEngines() {
    if (state.engines) return;
    try {
      const reponse = await fetchJson('/api/engines');
      state.engines = reponse.moteurs || [];
    } catch (e) {
      state.engines = [];
    }
  }

  async function ensureNodes() {
    if (state.summary && Array.isArray(state.summary.nodes)) return;
    if (state.nodes) return;
    try {
      state.nodes = await fetchJson('/api/nodes/status');
    } catch (e) {
      state.nodes = { nodes: [] };
    }
  }

  function nodeOptions(selected) {
    const opts = [
      `<option value="local"${selected === 'local' ? ' selected' : ''}>local</option>`,
      `<option value="auto"${selected === 'auto' ? ' selected' : ''}>auto</option>`
    ];
    let nodes = [];
    if (state.summary && Array.isArray(state.summary.nodes)) {
      nodes = state.summary.nodes;
    } else if (state.nodes && Array.isArray(state.nodes.nodes)) {
      nodes = state.nodes.nodes;
    }
    nodes.forEach((n) => {
      const name = typeof n === 'string' ? n : (n.name || n.hostname);
      if (!name) return;
      opts.push(`<option value="${escapeHtml(name)}"${selected === name ? ' selected' : ''}>${escapeHtml(name)}</option>`);
    });
    return opts.join('');
  }

  // Vendor GPU du nœud sélectionné (via /api/nodes/status enrichi, S6b). null si
  // local/auto/mixte/inconnu => aucun filtrage (fallback : tous les moteurs).
  function vendorForNode(nodeName) {
    const F = window.ForgeAIEngineFilter;
    if (!F) return null;
    const nodes = (state.nodes && state.nodes.nodes) || (state.summary && state.summary.nodes) || [];
    return F.nodeVendorForFilter(nodes, nodeName);
  }

  function engineOptions(selected, vendor) {
    if (!state.engines || !state.engines.length) {
      return `<option value="">${escapeHtml(t('loading'))}</option>`;
    }
    // S6b : ne proposer que les moteurs compatibles avec le vendor du nœud (module pur testé).
    // La sélection courante reste toujours visible (jamais de saut de valeur silencieux).
    const F = window.ForgeAIEngineFilter;
    const engines = F ? F.engineChoices(state.engines, vendor, selected) : state.engines;
    return engines.map((eng) => {
      const id = eng.id || eng.engine_id || String(eng);
      const label = eng.name || id;
      return `<option value="${escapeHtml(id)}"${selected === id ? ' selected' : ''}>${escapeHtml(label)}</option>`;
    }).join('');
  }

  async function loadLocalModels() {
    if (state.localModels) { await ensureNodes(); renderLocalModels(); return; }
    const box = document.getElementById('local-models-list');
    box.innerHTML = `<p>${escapeHtml(t('loading'))}</p>`;
    try {
      state.localModels = await fetchJson('/api/models/local');
    } catch (e) {
      box.innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
      return;
    }
    await loadEngines();
    await ensureNodes();
    renderLocalModels();
  }

  function renderLocalModels() {
    const box = document.getElementById('local-models-list');
    if (!state.localModels) return;
    const q = state.modelSearch.trim().toLowerCase();
    const visibles = state.localModels.modeles.filter((m) => {
      if (m.famille === 'embeddings-rerank') return false;
      if (state.modelTier !== 'tous' && m.tier !== state.modelTier) return false;
      if (!q) return true;
      return (m.hf_id + ' ' + m.name + ' ' + m.famille + ' ' + (m.notes_fr || '')).toLowerCase().includes(q);
    });
    const counts = document.getElementById('models-counts');
    // dénominateur = hors embeddings (symétrie avec l'étape dédiée)
    const totalLlm = state.localModels.modeles.filter((m) => m.famille !== 'embeddings-rerank').length;
    if (counts) counts.textContent = `${visibles.length}/${totalLlm}`;
    box.innerHTML = visibles.map((m) => {
      const chosenObj = state.modelsChosen[m.hf_id];
      const chosen = !!chosenObj;
      const nodeVal = chosenObj ? (chosenObj.node || 'local') : 'local';
      const engineVal = chosenObj ? (chosenObj.engine || 'vllm') : 'vllm';
      return `
        <label class="brick-row${chosen ? ' installed' : ''}">
          <input type="checkbox" data-model-id="${escapeHtml(m.hf_id)}" ${chosen ? 'checked' : ''}
                 aria-label="${escapeHtml(m.name)}">
          <span class="brick-main">
            <span class="brick-head">
              <span class="brick-name">${escapeHtml(m.name)}</span>
              <span class="def-pill">${escapeHtml(m.tier)}</span>
              <span class="def-pill">${escapeHtml(String(m.params_b))}B</span>
              ${m.vram_q4_gb ? `<span class="brick-stars">Q4 ~${escapeHtml(String(m.vram_q4_gb))} GB</span>` : ''}
              ${m.gguf ? '<span class="badge-default">GGUF</span>' : ''}
              ${chosen ? `<span class="badge-default">${escapeHtml(t('chosen_badge'))}</span>` : ''}
            </span>
            <span class="brick-desc">${escapeHtml(m.notes_fr || '')}</span>
            <span class="brick-stars">${escapeHtml(m.famille)} · ${escapeHtml(m.license)} · ${escapeHtml(m.hf_id)}</span>
            <span class="place-row">
              <span class="place-label">${escapeHtml(t('f_target_node'))}</span>
              <select class="place-select" data-model-node="${escapeHtml(m.hf_id)}" aria-label="${escapeHtml(t('f_target_node'))}">
                ${nodeOptions(nodeVal)}
              </select>
              <span class="place-label">${escapeHtml(t('f_engine'))}</span>
              <select class="place-select" data-model-engine="${escapeHtml(m.hf_id)}" aria-label="${escapeHtml(t('f_engine'))}">
                ${engineOptions(engineVal, vendorForNode(nodeVal))}
              </select>
            </span>
          </span>
        </label>`;
    }).join('');
    box.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener('change', () => {
        const id = cb.dataset.modelId;
        if (cb.checked) {
          const nodeSel = box.querySelector(`select[data-model-node="${CSS.escape(id)}"]`);
          const engineSel = box.querySelector(`select[data-model-engine="${CSS.escape(id)}"]`);
          state.modelsChosen[id] = {
            node: nodeSel ? nodeSel.value : 'local',
            engine: engineSel ? engineSel.value : 'vllm'
          };
        } else {
          delete state.modelsChosen[id];
        }
        renderLocalModels();
        applyStepStatuses(); // UI-039 : preuve étape 3 mise à jour immédiatement
      });
    });
    box.querySelectorAll('select[data-model-node]').forEach((sel) => {
      sel.addEventListener('change', () => {
        const id = sel.dataset.modelNode;
        if (!state.modelsChosen[id]) return;
        state.modelsChosen[id].node = sel.value;
        renderLocalModels();  // S6b : re-filtre le dropdown moteur selon le vendor du nœud choisi
      });
    });
    box.querySelectorAll('select[data-model-engine]').forEach((sel) => {
      sel.addEventListener('change', () => {
        const id = sel.dataset.modelEngine;
        if (!state.modelsChosen[id]) return;
        state.modelsChosen[id].engine = sel.value;
      });
    });
  }

  async function loadEmbeddings() {
    const box = document.getElementById('embeddings-list');
    if (!state.localModels) {
      box.innerHTML = `<p>${escapeHtml(t('loading'))}</p>`;
      await loadLocalModels();
      if (!state.localModels) return;
    }
    await loadEngines();
    await ensureNodes();
    state.embeddingsLoaded = true;
    renderEmbeddings();
  }

  function renderEmbeddings() {
    const box = document.getElementById('embeddings-list');
    if (!state.localModels) { box.innerHTML = ''; return; }
    const q = state.embeddingSearch.trim().toLowerCase();
    const visibles = state.localModels.modeles.filter((m) => {
      if (m.famille !== 'embeddings-rerank') return false;
      if (!q) return true;
      return (m.hf_id + ' ' + m.name + ' ' + m.famille + ' ' + (m.notes_fr || '')).toLowerCase().includes(q);
    });
    const counts = document.getElementById('embeddings-counts');
    // dénominateur = les embeddings SEULEMENT (objection revue N2 — jamais le total global)
    const totalEmb = state.localModels.modeles.filter((m) => m.famille === 'embeddings-rerank').length;
    if (counts) counts.textContent = `${visibles.length}/${totalEmb}`;
    box.innerHTML = visibles.map((m) => {
      const chosenObj = state.embeddingsChosen[m.hf_id];
      const chosen = !!chosenObj;
      const nodeVal = chosenObj ? (chosenObj.node || 'local') : 'local';
      const engineVal = chosenObj ? (chosenObj.engine || 'llama-cpp') : 'llama-cpp';
      return `
        <label class="brick-row${chosen ? ' installed' : ''}">
          <input type="checkbox" data-embedding-id="${escapeHtml(m.hf_id)}" ${chosen ? 'checked' : ''}
                 aria-label="${escapeHtml(m.name)}">
          <span class="brick-main">
            <span class="brick-head">
              <span class="brick-name">${escapeHtml(m.name)}</span>
              <span class="def-pill">${escapeHtml(m.tier)}</span>
              <span class="def-pill">${escapeHtml(String(m.params_b))}B</span>
              ${m.vram_q4_gb ? `<span class="brick-stars">Q4 ~${escapeHtml(String(m.vram_q4_gb))} GB</span>` : ''}
              ${m.gguf ? '<span class="badge-default">GGUF</span>' : ''}
              ${chosen ? `<span class="badge-default">${escapeHtml(t('chosen_badge'))}</span>` : ''}
            </span>
            <span class="brick-desc">${escapeHtml(m.notes_fr || '')}</span>
            <span class="brick-stars">${escapeHtml(m.famille)} · ${escapeHtml(m.license)} · ${escapeHtml(m.hf_id)}</span>
            <span class="place-row">
              <span class="place-label">${escapeHtml(t('f_target_node'))}</span>
              <select class="place-select" data-embedding-node="${escapeHtml(m.hf_id)}" aria-label="${escapeHtml(t('f_target_node'))}">
                ${nodeOptions(nodeVal)}
              </select>
              <span class="place-label">${escapeHtml(t('f_engine'))}</span>
              <select class="place-select" data-embedding-engine="${escapeHtml(m.hf_id)}" aria-label="${escapeHtml(t('f_engine'))}">
                ${engineOptions(engineVal, vendorForNode(nodeVal))}
              </select>
            </span>
          </span>
        </label>`;
    }).join('');
    box.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener('change', () => {
        const id = cb.dataset.embeddingId;
        if (cb.checked) {
          const nodeSel = box.querySelector(`select[data-embedding-node="${CSS.escape(id)}"]`);
          const engineSel = box.querySelector(`select[data-embedding-engine="${CSS.escape(id)}"]`);
          state.embeddingsChosen[id] = {
            node: nodeSel ? nodeSel.value : 'local',
            engine: engineSel ? engineSel.value : 'llama-cpp'
          };
        } else {
          delete state.embeddingsChosen[id];
        }
        renderEmbeddings();
        applyStepStatuses(); // UI-039 : preuve étape 4 mise à jour immédiatement
      });
    });
    box.querySelectorAll('select[data-embedding-node]').forEach((sel) => {
      sel.addEventListener('change', () => {
        const id = sel.dataset.embeddingNode;
        if (!state.embeddingsChosen[id]) return;
        state.embeddingsChosen[id].node = sel.value;
        renderEmbeddings();  // S6b : re-filtre le dropdown moteur selon le vendor du nœud choisi
      });
    });
    box.querySelectorAll('select[data-embedding-engine]').forEach((sel) => {
      sel.addEventListener('change', () => {
        const id = sel.dataset.embeddingEngine;
        if (!state.embeddingsChosen[id]) return;
        state.embeddingsChosen[id].engine = sel.value;
      });
    });
  }

  function initModelStep() {
    document.querySelectorAll('#tier-filter button[data-tier]').forEach((b) => {
      b.addEventListener('click', () => {
        state.modelTier = b.dataset.tier;
        document.querySelectorAll('#tier-filter button[data-tier]').forEach((x) =>
          x.setAttribute('aria-pressed', String(x === b)));
        renderLocalModels();
      });
    });
    const search = document.getElementById('model-search');
    if (search) search.addEventListener('input', () => { state.modelSearch = search.value; renderLocalModels(); });
  }

  function initEmbeddingStep() {
    const search = document.getElementById('embedding-search');
    if (search) search.addEventListener('input', () => { state.embeddingSearch = search.value; renderEmbeddings(); });
  }

  /* ---------- Nœuds (B-02d) ---------- */

  async function loadNodes() {
    const list = document.getElementById('nodes-list');
    if (!list) return;
    try {
      state.nodes = await fetchJson('/api/nodes/status');
    } catch (e) {
      list.innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
      applyStepStatuses();
      return;
    }
    renderNodes();
    applyStepStatuses(); // UI-039 : preuve étape 6 (chargement backend réel) mise à jour
  }

  function renderNodes() {
    const list = document.getElementById('nodes-list');
    if (!list) return;
    const nodes = (state.nodes && state.nodes.nodes) || [];
    if (!nodes.length) {
      list.innerHTML = `<p class="form-note">${escapeHtml(t('no_nodes'))}</p>`;
      return;
    }
    list.innerHTML = nodes.map((n) => `
      <div class="model-row">
        <span class="brick-name">${escapeHtml(n.name || n.hostname || n.ip || '?')}</span>
        ${n.ip ? `<span class="def-pill">${escapeHtml(n.ip)}</span>` : ''}
        ${n.status ? `<span class="def-pill">${escapeHtml(n.status)}</span>` : ''}
        ${n.roles ? `<span class="def-pill">${escapeHtml(String(n.roles))}</span>` : ''}
      </div>
    `).join('');
  }

  function initNodeForm() {
    const form = document.getElementById('node-form');
    if (!form) return;
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const status = document.getElementById('node-form-status');
      const payload = {
        ip: form.elements.ip.value.trim(),
        user: form.elements.user.value.trim(),
        password: form.elements.password.value // proof:allow (champ payload, valeur jamais litterale)
      };
      form.elements.password.value = '';
      status.textContent = t('adding_node');
      status.classList.remove('error');
      try {
        const res = await fetch('/api/nodes', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const body = await res.json();
        if (!res.ok) throw new Error(body.error || res.status);
        status.textContent = `${t('node_added')} (${body.node.key_fingerprint})`;
        form.elements.ip.value = '';
        form.elements.user.value = '';
        loadNodes();
      } catch (e) {
        status.textContent = String(e.message || e);
        status.classList.add('error');
      }
    });
  }

  function initModelForm() {
    const form = document.getElementById('model-form');
    if (!form) return;
    const provenance = form.elements.provenance;
    const baseUrlField = document.getElementById('base-url-field');
    const syncBaseUrl = () => {
      const need = provenance.value === 'direct' || provenance.value === 'autre';
      baseUrlField.classList.toggle('hidden', !need);
      form.elements.base_url.required = need;
    };
    provenance.addEventListener('change', syncBaseUrl);
    syncBaseUrl();

    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const status = document.getElementById('model-form-status');
      const payload = {
        name: form.elements.name.value.trim(),
        provenance: provenance.value,
        model_id: form.elements.model_id.value.trim(),
        api_key: form.elements.api_key.value, // proof:allow (champ payload, valeur jamais litterale)
        passphrase: form.elements.passphrase.value
      };
      const baseUrl = form.elements.base_url.value.trim();
      if (baseUrl) payload.base_url = baseUrl;
      form.elements.api_key.value = '';
      form.elements.passphrase.value = '';
      status.textContent = t('testing_route');
      status.classList.remove('error');
      try {
        const res = await fetch('/api/models', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const body = await res.json();
        if (!res.ok) throw new Error(body.error || res.status);
        status.textContent = t('route_added');
        form.elements.name.value = '';
        form.elements.model_id.value = '';
        form.elements.base_url.value = '';
        loadModels();
      } catch (e) {
        status.textContent = String(e.message || e);
        status.classList.add('error');
      }
    });
  }


  /* ---------- Installateur par étapes (P0.3 / N2b / UI-039) ---------- */

  const TOTAL_STEPS = 7;
  const NEEDS_STACK = new Set([3, 4, 5, 7]);

  // FAI-U-039 : marqueur textuel par statut d'étape — jamais uniquement une couleur.
  // Vocabulaire indépendant de la langue (symbole + jeton technique), pour ne pas
  // dupliquer une traduction hors périmètre (locales fr.json/en.json interdites ici)
  // ni recréer un dictionnaire fr/en embarqué (invariant test_ui_n2b::test_pas_de_dico_embarque).
  const STEP_STATUS_SYMBOL = {
    locked: '\u{1F512}',
    pending: '\u25CB',
    active: '\u25CF',
    done: '\u2713',
    failed: '\u2717'
  };

  function stepStatusLabel(status) {
    const symbol = STEP_STATUS_SYMBOL[status] || '';
    return (symbol + ' ' + status).trim();
  }

  function stepAllowed(n) {
    if (NEEDS_STACK.has(n) && !state.selectedId) return false;
    return n >= 1 && n <= TOTAL_STEPS;
  }

  // Rassemble la PREUVE backend réelle disponible côté client pour chaque étape.
  // Aucune position/index n'entre dans ce calcul (cause racine de FAI-U-039).
  function collectEvidence() {
    return {
      hardwareOk: Boolean(state.detect) && Object.keys(state.detect).length > 0 && !state.detectError,
      hardwareFailed: Boolean(state.detectError),
      stackChosen: Boolean(state.selectedId),
      modelsChosenCount: Object.keys(state.modelsChosen || {}).length,
      embeddingsChosenCount: Object.keys(state.embeddingsChosen || {}).length,
      bricksLoaded: Boolean(state.bricks),
      nodesLoaded: Boolean(
        (state.nodes && Array.isArray(state.nodes.nodes)) ||
        (state.summary && Array.isArray(state.summary.nodes))
      ),
      deployStatus: state.deployStatus || null
    };
  }

  // Fonctions PURES (aucune I/O, aucun DOM) : testables hors navigateur (Node), à l'image de
  // engine_filter.js/S6b. Le contrat de preuve par étape, dérivé de `collectEvidence()` :
  //   1 Matériel    -> détection backend reçue sans erreur
  //   2 Stack       -> une stack a été choisie
  //   3 Modèles IA  -> au moins un modèle choisi
  //   4 Embeddings  -> au moins un embedding choisi
  //   5 Briques     -> liste de briques chargée depuis le backend
  //   6 Nœuds       -> statut des nœuds chargé depuis le backend
  //   7 Déploiement -> exit_code backend == 0 (jamais "visité" seul)
  function computeStepEvidence(n, ev) {
    if (!ev) return false;
    switch (n) {
      case 1: return Boolean(ev.hardwareOk);
      case 2: return Boolean(ev.stackChosen);
      case 3: return ev.modelsChosenCount > 0;
      case 4: return ev.embeddingsChosenCount > 0;
      case 5: return Boolean(ev.bricksLoaded);
      case 6: return Boolean(ev.nodesLoaded);
      case 7: return ev.deployStatus === 'ok';
      default: return false;
    }
  }

  // Une étape échouée (preuve backend négative) n'est JAMAIS confondue avec "non exécutée" :
  // statut dédié 'failed', distinct de 'pending' et de 'done'.
  function computeStepFailure(n, ev) {
    if (!ev) return false;
    if (n === 1) return Boolean(ev.hardwareFailed);
    if (n === 7) return ev.deployStatus === 'failed';
    return false;
  }

  // Dérive le statut final d'une étape à partir de la SEULE preuve backend (jamais de la
  // position). Déterministe et idempotent : rejouable à l'identique après un rafraîchissement
  // dès lors que la même preuve est retransmise par le backend (cf. syncDeployStatus()).
  function computeStepStatus(n, currentStep, ev, allowed) {
    if (computeStepFailure(n, ev)) return 'failed';
    if (!allowed) return 'locked';
    if (computeStepEvidence(n, ev)) return 'done';
    if (n === currentStep) return 'active';
    return 'pending';
  }

  // (Re)applique les statuts d'étape sur le rail SANS changer de panneau — appelable après
  // tout événement qui change la preuve (chargement, sélection, fin de déploiement, changement
  // de langue) pour que le rail reflète toujours l'état réel, jamais un flag "visité" figé.
  function applyStepStatuses() {
    const ev = collectEvidence();
    document.querySelectorAll('.step-item').forEach((b) => {
      const sn = Number(b.dataset.step);
      const status = computeStepStatus(sn, state.step, ev, stepAllowed(sn));
      b.classList.toggle('active', status === 'active');
      b.classList.toggle('done', status === 'done');
      b.classList.toggle('failed', status === 'failed');
      b.classList.toggle('locked', status === 'locked');
      b.setAttribute('aria-pressed', String(sn === state.step));
      b.dataset.stepStatus = status;
      let label = b.querySelector('.step-status-text');
      if (!label) {
        label = document.createElement('span');
        label.className = 'step-status-text';
        b.appendChild(label);
      }
      label.textContent = stepStatusLabel(status);
    });
  }

  // Interroge le backend pour l'état RÉEL du dernier déploiement (SSE /api/deploy/events,
  // rejoue l'historique + clôture avec l'exit_code connu même si aucun process n'est vivant,
  // cf. server.py). Appelé au boot pour que le rail reflète le vrai statut dès l'affichage,
  // y compris après un rafraîchissement/redémarrage de page pendant/après un déploiement.
  function syncDeployStatus() {
    if (typeof EventSource === 'undefined') return;
    try {
      const es = new EventSource('/api/deploy/events');
      es.addEventListener('end', (ev) => {
        es.close();
        let code = null;
        try { code = JSON.parse(ev.data).exit_code; } catch (e) { /* fin sans code connu */ }
        state.deployStatus = code === null ? null : (code === 0 ? 'ok' : 'failed');
        applyStepStatuses();
      });
      es.onerror = () => { es.close(); };
    } catch (e) { /* EventSource indisponible (environnement restreint) */ }
  }

  async function refreshOperationsStatus() {
    const status = document.getElementById('ops-status');
    if (!status) return;
    status.textContent = '';
    try {
      const response = await fetch('/api/status');
      if (response.status === 401) {
        // WEB-017 : hors loopback la santé profonde exige un jeton. On l'annonce explicitement
        // plutôt que d'échouer en silence — et sans jamais rendre le corps d'erreur brut (WEB-015).
        status.textContent = t('ops_auth_requise');
        return;
      }
      if (!response.ok) {
        status.textContent = t('ops_indisponible');
        return;
      }
      const payload = await response.json();
      status.textContent = JSON.stringify(payload, null, 2);
    } catch (error) {
      status.textContent = t('ops_indisponible');
    }
  }

  function initOperationsPanel() {
    const toggle = document.getElementById('ops-toggle');
    const panel = document.getElementById('operations');
    if (!toggle || !panel) return;
    toggle.addEventListener('click', () => {
      const opening = panel.hidden;
      panel.hidden = !opening;
      toggle.setAttribute('aria-expanded', String(opening));
      if (opening) refreshOperationsStatus();
    });
    const refresh = document.getElementById('ops-refresh');
    if (refresh) refresh.addEventListener('click', refreshOperationsStatus);
    const loadLogs = document.getElementById('ops-load-logs');
    if (loadLogs) {
      loadLogs.addEventListener('click', () => {
        // On ne passe QUE l'élément de journal. Passer `#ops-status` comme élément de statut
        // laisserait le handler `end` y écrire le résultat du déploiement
        // (`status.textContent = t('deploy_done_ok')`) et ÉCRASER l'agrégat /api/status que
        // l'opérateur vient de charger. `#ops-status` reste dédié à la santé.
        streamDeployLog(document.getElementById('ops-log'));
      });
    }
  }

  document.addEventListener('DOMContentLoaded', initOperationsPanel);

  function goToStep(n) {
    if (!stepAllowed(n)) {
      const hint = document.getElementById('step-hint');
      if (hint) { hint.textContent = t('need_stack_first'); hint.classList.add('error'); }
      return;
    }
    state.step = n;
    document.querySelectorAll('[data-step-panel]').forEach((p) => {
      p.classList.toggle('hidden', Number(p.dataset.stepPanel) !== n);
    });
    applyStepStatuses();
    const hint = document.getElementById('step-hint');
    if (hint) { hint.textContent = ''; hint.classList.remove('error'); }
    const prev = document.getElementById('btn-prev');
    const next = document.getElementById('btn-next');
    if (prev) prev.disabled = n === 1;
    if (next) next.disabled = n === TOTAL_STEPS;
    window.scrollTo({ top: 0, behavior: 'instant' });
    if (n === 3) { loadEngines(); loadLocalModels(); }
    if (n === 4) loadEmbeddings();
    if (n === 5 && state.selectedId && !state.bricks) loadBricks();
    if (n === 6) loadNodes();
    if (n === 7 && state.selectedId && !state.summary) { loadSummary(); populateNodeChoices(); populateRagChoices(); }
  }

  function initStepper() {
    document.querySelectorAll('.step-item').forEach((b) => {
      b.addEventListener('click', () => goToStep(Number(b.dataset.step)));
    });
    const prev = document.getElementById('btn-prev');
    const next = document.getElementById('btn-next');
    if (prev) prev.addEventListener('click', () => goToStep(state.step - 1));
    if (next) next.addEventListener('click', () => goToStep(state.step + 1));
    goToStep(1);
    syncDeployStatus();
  }

  function initControls() {
    document.querySelectorAll('#theme-toggle button[data-theme]').forEach((btn) => {
      btn.addEventListener('click', () => setTheme(btn.dataset.theme));
    });
    document.querySelectorAll('#lang-toggle button[data-lang]').forEach((btn) => {
      btn.addEventListener('click', () => setLang(btn.dataset.lang));
    });
    const search = document.getElementById('brick-search');
    if (search) {
      search.addEventListener('input', () => {
        state.search = search.value;
        renderBricks();
      });
    }
    initModelForm();
    initModelStep();
    initEmbeddingStep();
    initNodeForm();
    initDeployForm();
    setTheme(state.theme);
    setLang(state.lang);
  }

  async function boot() {
    initControls();
    initStepper();
    await loadI18n(state.lang);
    loadI18n(state.lang === 'fr' ? 'en' : 'fr');
    loadModels();
    loadNodes();
    try {
      const [detect, stacks, spheres] = await Promise.all([
        fetchJson('/api/detect'),
        fetchJson('/api/stacks'),
        fetchJson('/api/spheres')
      ]);
      state.detect = detect;
      state.stacks = stacks;
      state.spheres = spheres;
      const gpuCount = Array.isArray(detect.gpus) ? detect.gpus.length : 0;
      state.recommendedId = gpuCount >= 1 ? 'agentique' : 'assistant-entreprise';
    } catch (e) {
      state.detect = state.detect || {};
      state.detectError = true; // UI-039 : échec réel, jamais confondu avec "done"
      document.getElementById('stacks-grid').innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
    }
    renderHardware();
    renderStacks();
    applyStepStatuses(); // UI-039 : (re)dérive l'état des étapes depuis la preuve backend réelle
  }

  boot();
})();
