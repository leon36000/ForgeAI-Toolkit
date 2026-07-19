(function () {
  'use strict';

  const state = {
    lang: document.documentElement.lang || 'fr',
    theme: document.documentElement.dataset.theme || 'dark',
    detect: null,
    stacks: [],
    spheres: [],
    recommendedId: null,
    selectedId: null
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
      select_stack: 'Sélectionnez un profil pour voir le détail.'
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
      select_stack: 'Select a profile to view details.'
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
    renderHardware();
    renderStacks();
    if (state.selectedId) {
      const stack = state.stacks.find((s) => s.id === state.selectedId);
      const full = state.stackDetail;
      if (stack && full) {
        renderDetail(stack, full);
      }
    }
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

  function initControls() {
    document.querySelectorAll('#theme-toggle button[data-theme]').forEach((btn) => {
      btn.addEventListener('click', () => setTheme(btn.dataset.theme));
    });
    document.querySelectorAll('#lang-toggle button[data-lang]').forEach((btn) => {
      btn.addEventListener('click', () => setLang(btn.dataset.lang));
    });
    setTheme(state.theme);
    setLang(state.lang);
  }

  async function boot() {
    initControls();
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
