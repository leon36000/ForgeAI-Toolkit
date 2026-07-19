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
    bricks: null,
    overrides: {},
    search: ''
  };

  const i18n = {
    fr: {
      title: 'ForgeAI Toolkit',
      hardware_title: 'Matériel détecté',
      loading: 'Chargement…',
      stacks_title: 'Profils de déploiement',
      stacks_subtitle: 'Choisissez le stack synergique à déployer.',
      theme_light: 'Clair',
      theme_dark: 'Sombre',
      hardware_cpu: 'Processeur',
      hardware_gpu: 'GPU',
      hardware_ram: 'Mémoire',
      hardware_no_gpu: 'Aucun GPU détecté',
      recommended: 'Recommandé',
      n_deploy_label: 'briques',
      defaults_title: 'Défauts par sphère',
      wiring_title: 'Câblage synergique',
      close: 'Fermer',
      error_load: 'Impossible de charger les données.',
      aria_lang: 'Langue',
      aria_theme: 'Thème',
      aria_spheres: 'Sous-étapes par sphère',
      aria_filter: 'Filtrer',
      bricks_title: 'Briques additionnelles',
      bricks_subtitle: 'Catalogue complet, classé par sphère. Les briques du stack sont pré-cochées ; le châssis commun est verrouillé.',
      search_placeholder: 'Filtrer les briques…',
      installed_badge: 'Installé avec le stack',
      locked_badge: 'Châssis — verrouillé',
      default_badge: 'Défaut de sphère',
      counts_tpl: '{installed} installées avec le stack · {checked} cochées · {total} disponibles',
      no_results: 'Aucune brique ne correspond au filtre.',
      stars_label: 'étoiles',
      models_title: 'Modèles & clés API',
      models_subtitle: 'Routes modèle cloud — test de connexion réel obligatoire ; la clé est scellée au coffre, seule l\'empreinte est conservée.',
      f_name: 'Nom de la route',
      f_provenance: 'Provenance',
      f_model_id: 'Identifiant du modèle',
      f_base_url: 'Base URL (OpenAI-compatible)',
      f_api_key: 'Clé API', // proof:allow (libellé i18n, pas un secret)
      f_passphrase: 'Passphrase du coffre',
      prov_direct: 'Direct fournisseur',
      prov_autre: 'Autre (URL)',
      key_note: 'La clé transite en mémoire vers le serveur local (127.0.0.1) puis est scellée au coffre chiffré — jamais écrite en clair, jamais réaffichée.',
      add_route: 'Ajouter la route (test réel)',
      testing_route: 'Test de connexion en cours…',
      route_added: 'Route ajoutée — test réel réussi.',
      no_models: 'Aucune route configurée pour l\'instant.',
      fingerprint_label: 'empreinte',
      nodes_title: 'Nœuds — cluster multi-machines',
      nodes_subtitle: 'Ajoutez un nœud avec son IP, utilisateur et mot de passe — utilisé une seule fois au bootstrap, puis bascule sur clé ed25519. Jamais écrit sur disque.',
      f_node_ip: 'Adresse IP',
      f_node_user: 'Utilisateur',
      f_node_password: 'Mot de passe (éphémère)', // proof:allow (libellé i18n)
      node_key_note: '🔑 Le mot de passe sert une seule fois : installation de la clé publique, bascule immédiate sur ed25519, puis seule l\'empreinte est journalisée au registre.',
      add_node: 'Ajouter le nœud',
      adding_node: 'Bootstrap du nœud en cours…',
      node_added: 'Nœud ajouté — bascule clé ed25519 réussie.',
      no_nodes: 'Aucun nœud dans le cluster pour l\'instant.',
      deploy_title: 'Résumé & Déploiement',
      deploy_subtitle: 'Vérifiez le résumé, puis tapez FORCER pour lancer le déploiement réel — chaque étape est prouvée en direct.',
      f_backend: 'Backend',
      f_confirm: 'Confirmation (tapez FORCER)',
      launch_deploy: 'Déployer le stack',
      deploy_running: 'Déploiement en cours — journal live ci-dessous.',
      deploy_done_ok: 'Déploiement terminé — code 0 (prouvé).',
      deploy_done_fail: 'Déploiement en échec — code {code}. Journal ci-dessus.',
      deploy_need_forcer: 'Tapez exactement FORCER pour confirmer.',
      s_stack: 'Stack',
      s_bricks: 'briques déployées',
      s_backends: 'Backends prêts',
      s_chassis: 'châssis commun',
      s_none: 'aucun',
      f_node_target: 'Nœud cible',
      node_local: 'Local (cette machine)',
      node_auto: 'Auto — scheduler du cluster',
      tagline: 'Installateur d\'infrastructure IA souveraine',
      step_hardware: 'Matériel',
      step_stack: 'Stack',
      step_models: 'Modèles IA',
      step_bricks: 'Briques',
      step_nodes: 'Nœuds',
      step_deploy: 'Déploiement',
      hardware_lede: 'Votre machine est analysée automatiquement — le reste de l\'installation s\'adapte à ce qu\'elle peut faire tourner.',
      models_step_title: 'Modèles IA',
      models_step_lede: 'Tous les modèles open-weight — petits, moyens, gros — déployables sur n\'importe quel nœud du réseau. Aucun n\'est masqué : choisissez librement, chaque nœud cible affiche s\'il peut le servir.',
      tier_all: 'Tous',
      tier_small: 'Petits',
      tier_medium: 'Moyens',
      tier_large: 'Gros',
      model_search_placeholder: 'Filtrer les modèles…',
      aria_tier: 'Taille',
      aria_filter_models: 'Filtrer',
      aria_steps: 'Étapes d\'installation',
      nav_prev: '← Précédent',
      nav_next: 'Suivant →',
      need_stack_first: 'Choisissez d\'abord un stack à l\'étape 2.'
    },
    en: {
      title: 'ForgeAI Toolkit',
      hardware_title: 'Detected hardware',
      loading: 'Loading…',
      stacks_title: 'Deployment profiles',
      stacks_subtitle: 'Choose the synergistic stack to deploy.',
      theme_light: 'Light',
      theme_dark: 'Dark',
      hardware_cpu: 'CPU',
      hardware_gpu: 'GPU',
      hardware_ram: 'Memory',
      hardware_no_gpu: 'No GPU detected',
      recommended: 'Recommended',
      n_deploy_label: 'bricks',
      defaults_title: 'Defaults by sphere',
      wiring_title: 'Synergistic wiring',
      close: 'Close',
      error_load: 'Unable to load data.',
      aria_lang: 'Language',
      aria_theme: 'Theme',
      aria_spheres: 'Sub-steps by sphere',
      aria_filter: 'Filter',
      bricks_title: 'Additional bricks',
      bricks_subtitle: 'Full catalogue, sorted by sphere. Stack bricks are pre-checked; the shared chassis is locked.',
      search_placeholder: 'Filter bricks…',
      installed_badge: 'Installed with the stack',
      locked_badge: 'Chassis — locked',
      default_badge: 'Sphere default',
      counts_tpl: '{installed} installed with the stack · {checked} checked · {total} available',
      no_results: 'No brick matches the filter.',
      stars_label: 'stars',
      models_title: 'Models & API keys',
      models_subtitle: 'Cloud model routes — real connection test required; the key is sealed in the vault, only its fingerprint is kept.',
      f_name: 'Route name',
      f_provenance: 'Provenance',
      f_model_id: 'Model identifier',
      f_base_url: 'Base URL (OpenAI-compatible)',
      f_api_key: 'API key', // proof:allow (libellé i18n, pas un secret)
      f_passphrase: 'Vault passphrase',
      prov_direct: 'Direct provider',
      prov_autre: 'Other (URL)',
      key_note: 'The key transits in memory to the local server (127.0.0.1) then is sealed in the encrypted vault — never written in clear, never shown again.',
      add_route: 'Add route (real test)',
      testing_route: 'Connection test running…',
      route_added: 'Route added — real test passed.',
      no_models: 'No route configured yet.',
      fingerprint_label: 'fingerprint',
      nodes_title: 'Nodes — multi-machine cluster',
      nodes_subtitle: 'Add a node with its IP, user and password — used once at bootstrap, then switches to an ed25519 key. Never written to disk.',
      f_node_ip: 'IP address',
      f_node_user: 'User',
      f_node_password: 'Password (ephemeral)', // proof:allow (libellé i18n)
      node_key_note: '🔑 The password is used once: public key install, immediate switch to ed25519, then only the fingerprint is logged to the ledger.',
      add_node: 'Add node',
      adding_node: 'Node bootstrap running…',
      node_added: 'Node added — ed25519 key switch succeeded.',
      no_nodes: 'No node in the cluster yet.',
      deploy_title: 'Summary & Deployment',
      deploy_subtitle: 'Check the summary, then type FORCER to start the real deployment — every step is proven live.',
      f_backend: 'Backend',
      f_confirm: 'Confirmation (type FORCER)',
      launch_deploy: 'Deploy the stack',
      deploy_running: 'Deployment running — live log below.',
      deploy_done_ok: 'Deployment finished — exit code 0 (proven).',
      deploy_done_fail: 'Deployment failed — exit code {code}. Log above.',
      deploy_need_forcer: 'Type exactly FORCER to confirm.',
      s_stack: 'Stack',
      s_bricks: 'deployed bricks',
      s_backends: 'Ready backends',
      s_chassis: 'shared chassis',
      s_none: 'none',
      f_node_target: 'Target node',
      node_local: 'Local (this machine)',
      node_auto: 'Auto — cluster scheduler',
      tagline: 'Sovereign AI infrastructure installer',
      step_hardware: 'Hardware',
      step_stack: 'Stack',
      step_models: 'AI Models',
      step_bricks: 'Bricks',
      step_nodes: 'Nodes',
      step_deploy: 'Deployment',
      hardware_lede: 'Your machine is analyzed automatically — the rest of the install adapts to what it can run.',
      models_step_title: 'AI Models',
      models_step_lede: 'All open-weight models — small, medium, large — deployable to any node on the network. None is hidden: choose freely, each target node shows whether it can serve it.',
      tier_all: 'All',
      tier_small: 'Small',
      tier_medium: 'Medium',
      tier_large: 'Large',
      model_search_placeholder: 'Filter models…',
      aria_tier: 'Size',
      aria_filter_models: 'Filter',
      aria_steps: 'Install steps',
      nav_prev: '← Previous',
      nav_next: 'Next →',
      need_stack_first: 'Choose a stack first at step 2.'
    }
  };

  function t(key) {
    return i18n[state.lang][key] || key;
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

  function setLang(lang) {
    state.lang = lang;
    document.documentElement.lang = lang;
    document.querySelectorAll('#lang-toggle button[data-lang]').forEach((btn) => {
      btn.setAttribute('aria-pressed', String(btn.dataset.lang === lang));
    });
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.dataset.i18n;
      if (i18n[lang][key]) {
        el.textContent = i18n[lang][key];
      }
    });
    document.querySelectorAll('[data-i18n-aria]').forEach((el) => {
      const key = el.dataset.i18nAria;
      if (i18n[lang][key]) {
        el.setAttribute('aria-label', i18n[lang][key]);
      }
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
      const key = el.dataset.i18nPlaceholder;
      if (i18n[lang][key]) {
        el.placeholder = i18n[lang][key];
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
        <li><strong>${escapeHtml(t('hardware_gpu'))}:</strong> ${gpus.length}</li>
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
      goToStep(state.step); // rafraîchit rail + verrous (stack désormais choisi)
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
      return;
    }
    renderBricks();
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

  function showDeploySection() {
    document.getElementById('deploy').classList.remove('hidden');
    loadSummary();
  }

  function hideDeploySection() {
    document.getElementById('deploy').classList.add('hidden');
    state.summary = null;
  }

  function streamDeployLog() {
    const log = document.getElementById('deploy-log');
    const status = document.getElementById('deploy-form-status');
    log.classList.remove('hidden');
    log.textContent = '';
    const es = new EventSource('/api/deploy/events');
    es.onmessage = (ev) => {
      log.textContent += ev.data + '\n';
      log.scrollTop = log.scrollHeight;
    };
    es.addEventListener('end', (ev) => {
      es.close();
      let code = null;
      try { code = JSON.parse(ev.data).exit_code; } catch (e) { /* fin sans code */ }
      if (code === 0) {
        status.textContent = t('deploy_done_ok');
        status.classList.remove('error');
      } else {
        status.textContent = t('deploy_done_fail').replace('{code}', String(code));
        status.classList.add('error');
      }
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
      try {
        const res = await fetch('/api/deploy', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            stack: state.selectedId,
            backend: form.elements.backend.value,
            node: form.elements.node ? form.elements.node.value : 'local',
            models: Object.keys(state.modelsChosen),
            confirm: confirm
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


  /* ---------- Étape Modèles IA (P0.3) — 113 modèles vérifiés HF, zéro masquage ---------- */

  async function loadLocalModels() {
    if (state.localModels) { renderLocalModels(); return; }
    const box = document.getElementById('local-models-list');
    box.innerHTML = `<p>${escapeHtml(t('loading'))}</p>`;
    try {
      state.localModels = await fetchJson('/api/models/local');
    } catch (e) {
      box.innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
      return;
    }
    renderLocalModels();
  }

  function renderLocalModels() {
    const box = document.getElementById('local-models-list');
    if (!state.localModels) return;
    const q = state.modelSearch.trim().toLowerCase();
    const visibles = state.localModels.modeles.filter((m) => {
      if (state.modelTier !== 'tous' && m.tier !== state.modelTier) return false;
      if (!q) return true;
      return (m.hf_id + ' ' + m.name + ' ' + m.famille + ' ' + (m.notes_fr || '')).toLowerCase().includes(q);
    });
    const counts = document.getElementById('models-counts');
    if (counts) counts.textContent = `${visibles.length}/${state.localModels.total}`;
    box.innerHTML = visibles.map((m) => {
      const chosen = !!state.modelsChosen[m.hf_id];
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
            </span>
            <span class="brick-desc">${escapeHtml(m.notes_fr || '')}</span>
            <span class="brick-stars">${escapeHtml(m.famille)} · ${escapeHtml(m.license)} · ${escapeHtml(m.hf_id)}</span>
          </span>
        </label>`;
    }).join('');
    box.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener('change', () => {
        if (cb.checked) state.modelsChosen[cb.dataset.modelId] = true;
        else delete state.modelsChosen[cb.dataset.modelId];
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

  /* ---------- Nœuds (B-02d) ---------- */

  async function loadNodes() {
    const list = document.getElementById('nodes-list');
    if (!list) return;
    try {
      state.nodes = await fetchJson('/api/nodes/status');
    } catch (e) {
      list.innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
      return;
    }
    renderNodes();
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
      // hygiène : mot de passe vidé du DOM AVANT l'appel — strictement éphémère
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
      // hygiène : vider les champs secrets AVANT l'appel — jamais conservés dans le DOM
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


  /* ---------- Installateur par étapes (P0.3) ---------- */

  const TOTAL_STEPS = 6;
  const NEEDS_STACK = new Set([3, 4, 6]);

  function stepAllowed(n) {
    if (NEEDS_STACK.has(n) && !state.selectedId) return false;
    return n >= 1 && n <= TOTAL_STEPS;
  }

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
    document.querySelectorAll('.step-item').forEach((b) => {
      const sn = Number(b.dataset.step);
      b.classList.toggle('active', sn === n);
      b.classList.toggle('done', sn < n);
      b.classList.toggle('locked', !stepAllowed(sn));
      b.setAttribute('aria-pressed', String(sn === n));
    });
    const hint = document.getElementById('step-hint');
    if (hint) { hint.textContent = ''; hint.classList.remove('error'); }
    const prev = document.getElementById('btn-prev');
    const next = document.getElementById('btn-next');
    if (prev) prev.disabled = n === 1;
    if (next) next.disabled = n === TOTAL_STEPS;
    window.scrollTo({ top: 0, behavior: 'instant' });
    if (n === 3) loadLocalModels();
    if (n === 4 && state.selectedId && !state.bricks) loadBricks();
    if (n === 6 && state.selectedId && !state.summary) { loadSummary(); populateNodeChoices(); }
    if (n === 5) loadNodes();
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
    initNodeForm();
    initDeployForm();
    setTheme(state.theme);
    setLang(state.lang);
  }

  async function boot() {
    initControls();
    initStepper();
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
      document.getElementById('stacks-grid').innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
    }
    renderHardware();
    renderStacks();
  }

  boot();
})();
