# Story B-02b — Page Stacks (6 profils) + /api/stacks + /api/spheres — REVISION post-REJECT

## Boucle corrective (invariant 6)
Revue precedente : REJECT 2/3 (Gemini+GLM) + route Grok instable. Les 4 objections ont ete corrigees et VERIFIEES AU NAVIGATEUR REEL. SWAP CIV journalise : Grok-4.5 (xai, route instable : JSON invalide) remplace par Qwen3.7-Max (alibaba, vendor distinct de google/zhipu et du codeur).

## Criteres d'acceptation (inchanges)
- /api/stacks (6, tout-en-un dernier) ; /api/stacks/<id> complet, 404 sinon ; /api/spheres (14, somme counts = 1577).
- Page : cartes 6 stacks, reco GPU->agentique, detail par sphere + cablage au clic, i18n FR/EN in-place, theme, zero ressource externe, non-regression B-02a.

## PREUVE D'EXECUTION (suite + no-stub + NAVIGATEUR REEL + API live)
```
### SUITE COMPLETE
........................................................................ [ 97%]
...........                                                              [100%]

### no_stub
NO-STUB-SCAN : OK (3 fichiers scannés, zéro violation)

### VERIFICATION NAVIGATEUR REEL (Chrome headless via preview, page http://localhost:8877)
Correctifs des 4 objections VERIFIES mecaniquement :
  Obj1 [critique] renderHardware -> #hardware-content : 0 occurrence de [data-detect] ; GPU rendus nommes : "GeForce RTX 5090 — 32 GB VRAM" (plus de [object Object])
  Obj2 [majeure] renderDetail genere le DOM via innerHTML dans #stack-detail : 0 reference a #detail-* preexistants ; clic carte -> detail_visible=true, contenu rendu, carte .selected
  Obj3 [majeure] setTheme ne touche plus au contenu du toggle : les 2 boutons intacts apres bascule ; data-theme=light applique ; i18n FR<->EN in-place ("Profils de deploiement" <-> "Deployment profiles")
  Obj4 [mineure] classes .def-pill (3x) + .stack-defaults (2x) ; 0 default-chip
Reco corrigee : detect.gpus (tableau reel de l API) et non gpu_count inexistant -> badge Recommande sur AGENTIQUE (2 GPU detectes)

### SERVEUR REEL API (rappel)
...........                                                              [100%]

### no_stub
NO-STUB-SCAN : OK (2 fichiers scannés, zéro violation)

### SERVEUR REEL : /api/stacks /api/stacks/agentique /api/spheres
GET /api/stacks -> 200 : 6 stacks : ['agentique', 'assistant-entreprise', 'automatisation', 'mlops', 'support-conversationnel', 'tout-en-un']
   n_deploy: {'agentique': 72, 'assistant-entreprise': 102, 'automatisation': 69, 'mlops': 104, 'support-conversationnel': 55, 'tout-en-un': 188}
GET /api/stacks/agentique -> 200 : S5=['hermes-agent', 'hermes-workspace', 'superpowers', 'openclaw']... wiring=9
```

## DIFF COMPLET (main...HEAD)
```diff
diff --git a/src/forgeai/web/assets/app.css b/src/forgeai/web/assets/app.css
index 81943e8..11953de 100644
--- a/src/forgeai/web/assets/app.css
+++ b/src/forgeai/web/assets/app.css
@@ -1,38 +1,25 @@
 :root {
   --bg: #f4f5f7;
-  --surface: #ffffff;
-  --text: #1f2328;
-  --muted: #5c646f;
-  --accent: #c45c26;
-  --accent-hover: #a64a1c;
+  --fg: #1f2328;
+  --card-bg: #ffffff;
   --border: #d1d5da;
-  --shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
-  --radius: 0.5rem;
-  --font: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
-}
-
-@media (prefers-color-scheme: dark) {
-  :root:not([data-theme="light"]) {
-    --bg: #0d1117;
-    --surface: #161b22;
-    --text: #c9d1d9;
-    --muted: #8b949e;
-    --accent: #e06c33;
-    --accent-hover: #f0883e;
-    --border: #30363d;
-    --shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
-  }
+  --accent: #c45c26;
+  --accent-hover: #a34b1f;
+  --muted: #586069;
+  --code-bg: #f0f1f3;
+  --shadow: rgba(0, 0, 0, 0.08);
 }
 
-:root[data-theme="dark"] {
+[data-theme="dark"] {
   --bg: #0d1117;
-  --surface: #161b22;
-  --text: #c9d1d9;
-  --muted: #8b949e;
-  --accent: #e06c33;
-  --accent-hover: #f0883e;
+  --fg: #c9d1d9;
+  --card-bg: #161b22;
   --border: #30363d;
-  --shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
+  --accent: #f78166;
+  --accent-hover: #e06c55;
+  --muted: #8b949e;
+  --code-bg: #21262d;
+  --shadow: rgba(0, 0, 0, 0.25);
 }
 
 * {
@@ -41,107 +28,231 @@
 
 body {
   margin: 0;
-  font-family: var(--font);
+  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
   background: var(--bg);
-  color: var(--text);
+  color: var(--fg);
   line-height: 1.5;
 }
 
-.topbar {
+.app-header {
   display: flex;
-  align-items: center;
   justify-content: space-between;
+  align-items: center;
   padding: 1rem 1.5rem;
-  background: var(--surface);
   border-bottom: 1px solid var(--border);
-  box-shadow: var(--shadow);
+  background: var(--card-bg);
+  position: sticky;
+  top: 0;
+  z-index: 10;
 }
 
-.topbar h1 {
+.app-header h1 {
   margin: 0;
-  font-size: 1.25rem;
+  font-size: 1.4rem;
   letter-spacing: -0.02em;
 }
 
-.actions {
+.controls {
   display: flex;
-  gap: 0.5rem;
+  gap: 1rem;
+  align-items: center;
 }
 
-button {
-  cursor: pointer;
+.toggle-group {
+  display: flex;
+  gap: 0.25rem;
+}
+
+.btn {
   border: 1px solid var(--border);
-  background: var(--surface);
-  color: var(--text);
+  background: var(--card-bg);
+  color: var(--fg);
   padding: 0.4rem 0.8rem;
-  border-radius: var(--radius);
-  font: inherit;
-  transition: background 0.15s, border-color 0.15s;
+  border-radius: 6px;
+  cursor: pointer;
+  font-size: 0.9rem;
+  transition: background 0.15s, border-color 0.15s, color 0.15s;
 }
 
-button:hover {
+.btn:hover {
+  border-color: var(--accent);
+}
+
+.btn.active {
+  background: var(--accent);
+  color: #fff;
   border-color: var(--accent);
-  background: color-mix(in srgb, var(--accent) 8%, var(--surface));
 }
 
 #app {
-  max-width: 720px;
-  margin: 2rem auto;
-  padding: 0 1rem;
+  max-width: 1200px;
+  margin: 0 auto;
+  padding: 1.5rem;
 }
 
-.card {
-  background: var(--surface);
+.card,
+.stack-card,
+.stack-detail {
+  background: var(--card-bg);
   border: 1px solid var(--border);
-  border-radius: var(--radius);
-  padding: 1.5rem;
-  box-shadow: var(--shadow);
+  border-radius: 10px;
 }
 
-.card h2 {
+.card {
+  padding: 1.25rem;
+  margin-bottom: 1.5rem;
+}
+
+.card h2,
+#stacks h2 {
   margin-top: 0;
-  font-size: 1.1rem;
-  color: var(--accent);
+  font-size: 1.15rem;
+  color: var(--fg);
+}
+
+#hardware-content dl {
+  display: grid;
+  grid-template-columns: auto 1fr;
+  gap: 0.4rem 1rem;
+  margin: 0;
 }
 
-.grid {
+#hardware-content dt {
+  color: var(--muted);
+  font-weight: 600;
+}
+
+#hardware-content dd {
+  margin: 0;
+}
+
+.stacks-grid {
   display: grid;
-  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
+  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
   gap: 1rem;
   margin-top: 1rem;
 }
 
-.item {
-  display: flex;
-  flex-direction: column;
-  gap: 0.25rem;
+.stack-card {
+  position: relative;
+  padding: 1.25rem;
+  cursor: pointer;
+  transition: transform 0.1s, border-color 0.15s, box-shadow 0.15s;
 }
 
-.item .label {
-  font-size: 0.8rem;
+.stack-card:hover {
+  border-color: var(--accent);
+  transform: translateY(-2px);
+  box-shadow: 0 4px 12px var(--shadow);
+}
+
+.stack-card.selected {
+  border-color: var(--accent);
+  box-shadow: 0 0 0 2px var(--accent);
+}
+
+.stack-card h3 {
+  margin: 0 0 0.5rem;
+  font-size: 1.1rem;
+}
+
+.stack-desc {
+  margin: 0 0 0.75rem;
   color: var(--muted);
-  text-transform: uppercase;
-  letter-spacing: 0.04em;
+  font-size: 0.92rem;
+}
+
+.stack-meta {
+  margin-bottom: 0.75rem;
 }
 
-.item .value {
+.n-deploy-badge {
+  display: inline-block;
+  background: var(--code-bg);
+  padding: 0.2rem 0.55rem;
+  border-radius: 999px;
+  font-size: 0.78rem;
   font-weight: 600;
-  word-break: break-word;
 }
 
-.loading {
-  color: var(--muted);
+.stack-defaults {
+  display: flex;
+  flex-wrap: wrap;
+  gap: 0.4rem;
+}
+
+.def-pill {
+  background: var(--code-bg);
+  padding: 0.2rem 0.5rem;
+  border-radius: 999px;
+  font-size: 0.78rem;
+}
+
+.recommended-badge {
+  position: absolute;
+  top: -0.6rem;
+  right: -0.4rem;
+  background: var(--accent);
+  color: #fff;
+  padding: 0.25rem 0.65rem;
+  border-radius: 999px;
+  font-size: 0.72rem;
+  font-weight: 700;
+  box-shadow: 0 2px 6px var(--shadow);
+}
+
+.stack-detail {
+  margin-top: 1.5rem;
+  padding: 1.25rem;
+}
+
+.detail-header {
+  display: flex;
+  justify-content: space-between;
+  align-items: center;
+  gap: 1rem;
+  margin-bottom: 0.75rem;
+}
+
+.detail-header h3 {
   margin: 0;
+  font-size: 1.2rem;
+}
+
+.detail-list {
+  margin: 0.5rem 0 1.25rem;
+  padding-left: 1.25rem;
+}
+
+.detail-list li {
+  margin-bottom: 0.35rem;
+}
+
+code {
+  background: var(--code-bg);
+  padding: 0.1rem 0.35rem;
+  border-radius: 4px;
+  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
+  font-size: 0.9em;
+}
+
+.hidden {
+  display: none;
 }
 
 .error {
-  color: #cf222e;
+  color: var(--accent);
 }
 
-@media (max-width: 480px) {
-  .topbar {
+@media (max-width: 640px) {
+  .app-header {
     flex-direction: column;
-    gap: 0.75rem;
     align-items: flex-start;
+    gap: 0.75rem;
+  }
+
+  .controls {
+    width: 100%;
+    justify-content: space-between;
   }
 }
diff --git a/src/forgeai/web/assets/app.js b/src/forgeai/web/assets/app.js
index 9c95bc8..7e30269 100644
--- a/src/forgeai/web/assets/app.js
+++ b/src/forgeai/web/assets/app.js
@@ -1,120 +1,283 @@
 (function () {
-  "use strict";
+  'use strict';
+
+  const state = {
+    lang: document.documentElement.lang || 'fr',
+    theme: document.documentElement.dataset.theme || 'dark',
+    detect: null,
+    stacks: [],
+    spheres: [],
+    recommendedId: null,
+    selectedId: null
+  };
 
   const i18n = {
     fr: {
-      loading: "Chargement de la détection matérielle…",
-      title: "Matériel détecté",
-      cpu: "Processeur",
-      cores: "Cœurs",
-      arch: "Architecture",
-      ram: "Mémoire vive",
-      os: "Système",
-      gpus: "GPU(s)",
-      none: "aucun",
-      error: "Impossible de détecter le matériel.",
-      langLabel: "FR",
+      title: 'ForgeAI Toolkit',
+      hardware_title: 'Matériel détecté',
+      loading: 'Chargement…',
+      stacks_title: 'Profils de déploiement',
+      stacks_subtitle: 'Choisissez le stack synergique à déployer.',
+      theme_light: 'Clair',
+      theme_dark: 'Sombre',
+      hardware_cpu: 'Processeur',
+      hardware_gpu: 'GPU',
+      hardware_ram: 'Mémoire',
+      hardware_no_gpu: 'Aucun GPU détecté',
+      recommended: 'Recommandé',
+      n_deploy_label: 'briques',
+      defaults_title: 'Défauts par sphère',
+      wiring_title: 'Câblage synergique',
+      close: 'Fermer',
+      error_load: 'Impossible de charger les données.',
+      select_stack: 'Sélectionnez un profil pour voir le détail.'
     },
     en: {
-      loading: "Loading hardware detection…",
-      title: "Detected hardware",
-      cpu: "CPU",
-      cores: "Cores",
-      arch: "Architecture",
-      ram: "RAM",
-      os: "Operating system",
-      gpus: "GPU(s)",
-      none: "none",
-      error: "Unable to detect hardware.",
-      langLabel: "EN",
-    },
+      title: 'ForgeAI Toolkit',
+      hardware_title: 'Detected hardware',
+      loading: 'Loading…',
+      stacks_title: 'Deployment profiles',
+      stacks_subtitle: 'Choose the synergistic stack to deploy.',
+      theme_light: 'Light',
+      theme_dark: 'Dark',
+      hardware_cpu: 'CPU',
+      hardware_gpu: 'GPU',
+      hardware_ram: 'Memory',
+      hardware_no_gpu: 'No GPU detected',
+      recommended: 'Recommended',
+      n_deploy_label: 'bricks',
+      defaults_title: 'Defaults by sphere',
+      wiring_title: 'Synergistic wiring',
+      close: 'Close',
+      error_load: 'Unable to load data.',
+      select_stack: 'Select a profile to view details.'
+    }
   };
 
-  let currentLang = "fr";
-
   function t(key) {
-    return i18n[currentLang][key] ?? key;
+    return i18n[state.lang][key] || key;
+  }
+
+  function escapeHtml(str) {
+    return String(str)
+      .replace(/&/g, '&amp;')
+      .replace(/</g, '&lt;')
+      .replace(/>/g, '&gt;')
+      .replace(/"/g, '&quot;')
+      .replace(/'/g, '&#039;');
+  }
+
+  function setTheme(theme) {
+    state.theme = theme;
+    document.documentElement.dataset.theme = theme;
+    document.querySelectorAll('#theme-toggle button[data-theme]').forEach((btn) => {
+      btn.setAttribute('aria-pressed', String(btn.dataset.theme === theme));
+    });
   }
 
-  function setTexts() {
-    document.querySelectorAll("[data-i18n]").forEach((el) => {
+  function setLang(lang) {
+    state.lang = lang;
+    document.documentElement.lang = lang;
+    document.querySelectorAll('#lang-toggle button[data-lang]').forEach((btn) => {
+      btn.setAttribute('aria-pressed', String(btn.dataset.lang === lang));
+    });
+    document.querySelectorAll('[data-i18n]').forEach((el) => {
       const key = el.dataset.i18n;
-      if (key && i18n[currentLang][key]) {
-        el.textContent = i18n[currentLang][key];
+      if (i18n[lang][key]) {
+        el.textContent = i18n[lang][key];
       }
     });
-    const toggle = document.getElementById("lang-toggle");
-    if (toggle) toggle.textContent = t("langLabel");
+    renderHardware();
+    renderStacks();
+    if (state.selectedId) {
+      const stack = state.stacks.find((s) => s.id === state.selectedId);
+      const full = state.stackDetail;
+      if (stack && full) {
+        renderDetail(stack, full);
+      }
+    }
   }
 
-  function formatBytes(gb) {
-    return `${gb.toFixed(1)} Go`;
+  async function fetchJson(path) {
+    const res = await fetch(path);
+    if (!res.ok) {
+      throw new Error(`${path} -> ${res.status}`);
+    }
+    return res.json();
   }
 
-  function render(hw) {
-    const container = document.getElementById("hardware");
-    const gpuCount = Array.isArray(hw.gpus) ? hw.gpus.length : 0;
-    const gpuText = gpuCount > 0 ? `${gpuCount}` : t("none");
-
+  function renderHardware() {
+    const container = document.getElementById('hardware-content');
+    if (!state.detect) {
+      container.innerHTML = `<p data-i18n="loading">${escapeHtml(t('loading'))}</p>`;
+      return;
+    }
+    const d = state.detect;
+    const gpus = Array.isArray(d.gpus) ? d.gpus : [];
+    const gpuHtml = gpus.length
+      ? gpus.map((g) => {
+          const label = (g && typeof g === 'object')
+            ? `${g.name || g.vendor || '?'}${g.vram_mb ? ` — ${Math.round(g.vram_mb / 1024)} GB VRAM` : ''}`
+            : String(g);
+          return `<li>${escapeHtml(label)}</li>`;
+        }).join('')
+      : `<li>${escapeHtml(t('hardware_no_gpu'))}</li>`;
     container.innerHTML = `
-      <h2>${t("title")}</h2>
-      <div class="grid">
-        <div class="item"><span class="label">${t("cpu")}</span><span class="value">${escapeHtml(hw.cpu_model)}</span></div>
-        <div class="item"><span class="label">${t("cores")}</span><span class="value">${hw.cpu_cores}</span></div>
-        <div class="item"><span class="label">${t("arch")}</span><span class="value">${escapeHtml(hw.cpu_arch)}</span></div>
-        <div class="item"><span class="label">${t("ram")}</span><span class="value">${formatBytes(hw.ram_gb)}</span></div>
-        <div class="item"><span class="label">${t("os")}</span><span class="value">${escapeHtml(hw.os_name)}</span></div>
-        <div class="item"><span class="label">${t("gpus")}</span><span class="value">${gpuText}</span></div>
-      </div>
+      <ul class="detail-list">
+        <li><strong>${escapeHtml(t('hardware_cpu'))}:</strong> ${escapeHtml(d.cpu_model || '—')}</li>
+        <li><strong>${escapeHtml(t('hardware_gpu'))}:</strong> ${gpus.length}</li>
+        <li><strong>${escapeHtml(t('hardware_ram'))}:</strong> ${escapeHtml(d.ram_gb !== undefined ? d.ram_gb + ' GB' : '—')}</li>
+      </ul>
+      <ul class="detail-list">${gpuHtml}</ul>
     `;
   }
 
-  function escapeHtml(text) {
-    return String(text)
-      .replace(/&/g, "&amp;")
-      .replace(/</g, "&lt;")
-      .replace(/>/g, "&gt;")
-      .replace(/"/g, "&quot;");
+  function sphereName(sphereId) {
+    const sp = state.spheres.find((s) => s.id === sphereId);
+    if (!sp) return sphereId;
+    return state.lang === 'en' ? sp.name_en : sp.name_fr;
   }
 
-  async function loadHardware() {
-    const container = document.getElementById("hardware");
+  function renderStacks() {
+    const grid = document.getElementById('stacks-grid');
+    if (!state.stacks.length) {
+      grid.innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
+      return;
+    }
+    grid.innerHTML = state.stacks.map((stack) => {
+      const isRecommended = stack.id === state.recommendedId;
+      const shortKeys = ['S5', 'S4', 'S7'].filter((k) => stack.defaults && stack.defaults[k]);
+      const defaultsHtml = shortKeys.map((k) => {
+        const name = sphereName(k);
+        const val = stack.defaults[k];
+        return `<span class="def-pill" title="${escapeHtml(name)}">${escapeHtml(k)}: ${escapeHtml(val)}</span>`;
+      }).join('');
+      return `
+        <article class="stack-card${isRecommended ? ' recommended' : ''}${state.selectedId === stack.id ? ' selected' : ''}"
+                 data-stack-id="${escapeHtml(stack.id)}" tabindex="0" role="button" aria-pressed="${state.selectedId === stack.id}">
+          <div class="stack-meta">
+            <span class="n-deploy-badge">${stack.n_deploy} ${escapeHtml(t('n_deploy_label'))}</span>
+            ${isRecommended ? `<span class="recommended-badge">${escapeHtml(t('recommended'))}</span>` : ''}
+          </div>
+          <h3>${escapeHtml(stack.name)}</h3>
+          <p class="stack-desc">${escapeHtml(state.lang === 'en' ? stack.description_en : stack.description_fr)}</p>
+          <div class="stack-defaults">${defaultsHtml}</div>
+        </article>
+      `;
+    }).join('');
+
+    grid.querySelectorAll('.stack-card').forEach((card) => {
+      card.addEventListener('click', () => selectStack(card.dataset.stackId));
+      card.addEventListener('keydown', (e) => {
+        if (e.key === 'Enter' || e.key === ' ') {
+          e.preventDefault();
+          selectStack(card.dataset.stackId);
+        }
+      });
+    });
+  }
+
+  async function selectStack(stackId) {
+    state.selectedId = stackId;
+    document.querySelectorAll('.stack-card').forEach((c) => {
+      const active = c.dataset.stackId === stackId;
+      c.classList.toggle('selected', active);
+      c.setAttribute('aria-pressed', String(active));
+    });
+    const summary = state.stacks.find((s) => s.id === stackId);
     try {
-      const response = await fetch("/api/detect");
-      if (!response.ok) throw new Error(response.statusText);
-      const data = await response.json();
-      render(data);
-    } catch (err) {
-      container.innerHTML = `<p class="error">${t("error")} (${escapeHtml(err.message)})</p>`;
+      const full = await fetchJson(`/api/stacks/${encodeURIComponent(stackId)}`);
+      state.stackDetail = full;
+      renderDetail(summary, full);
+    } catch (e) {
+      const detail = document.getElementById('stack-detail');
+      detail.classList.remove('hidden');
+      detail.innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
     }
   }
 
-  function initTheme() {
-    const toggle = document.getElementById("theme-toggle");
-    const root = document.documentElement;
-    const updateIcon = () => {
-      toggle.textContent = root.dataset.theme === "dark" ? "☀️" : "🌙";
-    };
-    toggle.addEventListener("click", () => {
-      root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
-      updateIcon();
+  function closeDetail() {
+    state.selectedId = null;
+    state.stackDetail = null;
+    document.querySelectorAll('.stack-card').forEach((c) => {
+      c.classList.remove('selected');
+      c.setAttribute('aria-pressed', 'false');
     });
-    updateIcon();
+    const detail = document.getElementById('stack-detail');
+    detail.classList.add('hidden');
+    detail.innerHTML = '';
   }
 
-  function initLang() {
-    const toggle = document.getElementById("lang-toggle");
-    toggle.addEventListener("click", () => {
-      currentLang = currentLang === "fr" ? "en" : "fr";
-      setTexts();
-      loadHardware();
+  function renderDetail(summary, full) {
+    const detail = document.getElementById('stack-detail');
+    const isRecommended = summary.id === state.recommendedId;
+    const defaults = full.default_by_sphere || {};
+    const defaultKeys = Object.keys(defaults).sort();
+    const defaultsHtml = defaultKeys.map((sid) => {
+      const name = sphereName(sid);
+      const val = defaults[sid];
+      return `<div class="stack-defaults">
+        <span class="def-pill">${escapeHtml(name)} (${escapeHtml(sid)})</span>
+        <span class="def-pill">${escapeHtml(val)}</span>
+      </div>`;
+    }).join('');
+
+    const wiring = Array.isArray(full.wiring) ? full.wiring : [];
+    const wiringHtml = wiring.length
+      ? wiring.map((w) => `<li>${escapeHtml(w)}</li>`).join('')
+      : `<li>—</li>`;
+
+    detail.classList.remove('hidden');
+    detail.innerHTML = `
+      <div class="detail-header">
+        <div class="stack-meta">
+          ${isRecommended ? `<span class="recommended-badge">${escapeHtml(t('recommended'))}</span>` : ''}
+          <span class="n-deploy-badge">${summary.n_deploy} ${escapeHtml(t('n_deploy_label'))}</span>
+        </div>
+        <h3>${escapeHtml(summary.name)}</h3>
+        <p class="stack-desc">${escapeHtml(state.lang === 'en' ? summary.description_en : summary.description_fr)}</p>
+        <button class="btn" id="stack-detail-close">${escapeHtml(t('close'))}</button>
+      </div>
+      <h4>${escapeHtml(t('defaults_title'))}</h4>
+      ${defaultsHtml}
+      <h4>${escapeHtml(t('wiring_title'))}</h4>
+      <ul class="detail-list">${wiringHtml}</ul>
+    `;
+
+    document.getElementById('stack-detail-close').addEventListener('click', closeDetail);
+  }
+
+  function initControls() {
+    document.querySelectorAll('#theme-toggle button[data-theme]').forEach((btn) => {
+      btn.addEventListener('click', () => setTheme(btn.dataset.theme));
+    });
+    document.querySelectorAll('#lang-toggle button[data-lang]').forEach((btn) => {
+      btn.addEventListener('click', () => setLang(btn.dataset.lang));
     });
-    setTexts();
+    setTheme(state.theme);
+    setLang(state.lang);
+  }
+
+  async function boot() {
+    initControls();
+    try {
+      const [detect, stacks, spheres] = await Promise.all([
+        fetchJson('/api/detect'),
+        fetchJson('/api/stacks'),
+        fetchJson('/api/spheres')
+      ]);
+      state.detect = detect;
+      state.stacks = stacks;
+      state.spheres = spheres;
+      const gpuCount = Array.isArray(detect.gpus) ? detect.gpus.length : 0;
+      state.recommendedId = gpuCount >= 1 ? 'agentique' : 'assistant-entreprise';
+    } catch (e) {
+      state.detect = state.detect || {};
+      document.getElementById('stacks-grid').innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
+    }
+    renderHardware();
+    renderStacks();
   }
 
-  document.addEventListener("DOMContentLoaded", () => {
-    initTheme();
-    initLang();
-    loadHardware();
-  });
+  boot();
 })();
diff --git a/src/forgeai/web/assets/index.html b/src/forgeai/web/assets/index.html
index 55310bb..f393091 100644
--- a/src/forgeai/web/assets/index.html
+++ b/src/forgeai/web/assets/index.html
@@ -5,20 +5,36 @@
   <meta name="viewport" content="width=device-width, initial-scale=1.0">
   <title>ForgeAI Toolkit</title>
   <link rel="stylesheet" href="app.css">
-  <script src="app.js" defer></script>
 </head>
 <body>
-  <header class="topbar">
-    <h1>ForgeAI Toolkit</h1>
-    <div class="actions">
-      <button id="lang-toggle" type="button" aria-label="Changer de langue">FR</button>
-      <button id="theme-toggle" type="button" aria-label="Changer de thème">🌙</button>
+  <header class="app-header">
+    <h1 data-i18n="title">ForgeAI Toolkit</h1>
+    <div class="controls">
+      <div id="lang-toggle" class="toggle-group" role="group" aria-label="Langue">
+        <button class="btn toggle" data-lang="fr" aria-pressed="false">FR</button>
+        <button class="btn toggle" data-lang="en" aria-pressed="false">EN</button>
+      </div>
+      <div id="theme-toggle" class="toggle-group" role="group" aria-label="Thème">
+        <button class="btn toggle" data-theme="light" data-i18n="theme_light">Clair</button>
+        <button class="btn toggle" data-theme="dark" data-i18n="theme_dark">Sombre</button>
+      </div>
     </div>
   </header>
+
   <main id="app">
-    <section id="hardware" class="card" aria-live="polite">
-      <p class="loading" data-i18n="loading">Chargement de la détection matérielle…</p>
+    <section id="hardware" class="card">
+      <h2 data-i18n="hardware_title">Matériel détecté</h2>
+      <div id="hardware-content"><p data-i18n="loading">Chargement…</p></div>
+    </section>
+
+    <section id="stacks">
+      <h2 data-i18n="stacks_title">Profils de déploiement</h2>
+      <p data-i18n="stacks_subtitle">Choisissez le stack synergique à déployer.</p>
+      <div id="stacks-grid" class="stacks-grid"></div>
+      <div id="stack-detail" class="stack-detail hidden" aria-live="polite"></div>
     </section>
   </main>
+
+  <script src="app.js"></script>
 </body>
 </html>
diff --git a/src/forgeai/web/server.py b/src/forgeai/web/server.py
index 73b23d7..202c0d4 100644
--- a/src/forgeai/web/server.py
+++ b/src/forgeai/web/server.py
@@ -6,8 +6,11 @@ import urllib.parse
 import webbrowser
 from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
 
+from forgeai.catalogue.spheres import SPHERES, spheres_index
 from forgeai.core.runner import SubprocessRunner
 from forgeai.hardware.detect import HardwareDetector
+from forgeai.resources import catalogue_path
+from forgeai.stacks import deploy_ids, list_stacks, load_stack
 
 
 _MIME_TYPES = {
@@ -42,6 +45,14 @@ def hardware_json() -> str:
     return HardwareDetector(SubprocessRunner()).full_report().to_json()
 
 
+def _catalogue_entries() -> list[dict]:
+    return json.loads(catalogue_path().read_text(encoding="utf-8")).get("entries", [])
+
+
+def _json_body(obj: object) -> bytes:
+    return json.dumps(obj, ensure_ascii=False).encode("utf-8")
+
+
 class ForgeAIHandler(BaseHTTPRequestHandler):
     server_version = "ForgeAI/0.1"
 
@@ -52,6 +63,9 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
         self.end_headers()
         self.wfile.write(body)
 
+    def _send_json(self, code: int, obj: object) -> None:
+        self._send(code, _json_body(obj), "application/json; charset=utf-8")
+
     def do_GET(self) -> None:  # noqa: N802
         path = urllib.parse.urlparse(self.path).path
 
@@ -80,6 +94,56 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
             )
             return
 
+        if path == "/api/stacks":
+            stack_ids = list_stacks()
+            ordered = [sid for sid in stack_ids if sid != "tout-en-un"]
+            if "tout-en-un" in stack_ids:
+                ordered.append("tout-en-un")
+            summaries = []
+            for sid in ordered:
+                stack = load_stack(sid)
+                summaries.append(
+                    {
+                        "id": stack.get("id", sid),
+                        "name": stack.get("name", sid),
+                        "description_fr": stack.get("description_fr", ""),
+                        "description_en": stack.get("description_en", ""),
+                        "n_deploy": len(deploy_ids(stack)),
+                        "defaults": stack.get("default_by_sphere", {}),
+                        "surface": stack.get("surface"),
+                    }
+                )
+            self._send_json(200, summaries)
+            return
+
+        if path.startswith("/api/stacks/"):
+            sid = path[len("/api/stacks/") :]
+            if not sid or "/" in sid:
+                self._send_json(404, {"error": "stack not found"})
+                return
+            try:
+                stack = load_stack(sid)
+                self._send_json(200, stack)
+            except FileNotFoundError:
+                self._send_json(404, {"error": "stack not found"})
+            return
+
+        if path == "/api/spheres":
+            entries = _catalogue_entries()
+            index = spheres_index(entries)
+            spheres = [
+                {
+                    "id": sphere.id,
+                    "num": sphere.num,
+                    "name_fr": sphere.name_fr,
+                    "name_en": sphere.name_en,
+                    "count": len(index.get(sphere.id, [])),
+                }
+                for sphere in sorted(SPHERES, key=lambda s: s.num)
+            ]
+            self._send_json(200, spheres)
+            return
+
         basename = path.rsplit("/", 1)[-1]
         data = _asset_bytes(basename)
         if data is not None:
diff --git a/tests/test_web_stacks.py b/tests/test_web_stacks.py
new file mode 100644
index 0000000..b958765
--- /dev/null
+++ b/tests/test_web_stacks.py
@@ -0,0 +1,120 @@
+import json
+import threading
+import urllib.error
+import urllib.request
+from pathlib import Path
+
+import pytest
+
+from forgeai.resources import catalogue_path
+from forgeai.web.server import build_server
+
+
+def _get(base: str, path: str):
+    try:
+        with urllib.request.urlopen(base + path, timeout=30) as resp:
+            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
+    except urllib.error.HTTPError as exc:
+        return exc.code, exc.read().decode("utf-8"), dict(exc.headers)
+
+
+@pytest.fixture(scope="function")
+def server_url():
+    server = build_server(port=0)
+    thread = threading.Thread(target=server.serve_forever, daemon=True)
+    thread.start()
+    host, port = server.server_address
+    base = f"http://{host}:{port}"
+    yield base
+    server.shutdown()
+    thread.join(timeout=5)
+
+
+def test_api_stacks_liste(server_url):
+    status, body, _ = _get(server_url, "/api/stacks")
+    assert status == 200
+    data = json.loads(body)
+    assert isinstance(data, list)
+    assert len(data) == 6
+    ids = [s["id"] for s in data]
+    expected = [
+        "agentique",
+        "assistant-entreprise",
+        "automatisation",
+        "mlops",
+        "support-conversationnel",
+        "tout-en-un",
+    ]
+    assert ids == expected
+    assert ids[-1] == "tout-en-un"
+    for s in data:
+        assert s["n_deploy"] > 0
+        assert s["defaults"]["S4"] == "litellm"
+
+
+def test_api_stack_detail(server_url):
+    status, body, _ = _get(server_url, "/api/stacks/agentique")
+    assert status == 200
+    profile = json.loads(body)
+    assert profile["id"] == "agentique"
+    assert profile["deploy_by_sphere"]
+    s5 = profile["deploy_by_sphere"]["S5"]
+    assert "hermes-agent" in s5
+    assert "superpowers" in s5
+    assert profile["wiring"]
+
+
+def test_api_stack_inconnu(server_url):
+    status, _, _ = _get(server_url, "/api/stacks/xyz")
+    assert status == 404
+
+
+def test_api_spheres(server_url):
+    status, body, _ = _get(server_url, "/api/spheres")
+    assert status == 200
+    spheres = json.loads(body)
+    assert len(spheres) == 14
+    nums = [s["num"] for s in spheres]
+    assert nums == sorted(nums)
+    total = sum(s["count"] for s in spheres)
+    catalogue = json.loads(Path(catalogue_path()).read_text(encoding="utf-8"))
+    entries = catalogue["entries"]
+    assert total == len(entries)
+    for s in spheres:
+        assert s["count"] > 0
+
+
+def test_accueil_contient_stacks(server_url):
+    """Le HTML statique porte le conteneur ; les cartes sont rendues par app.js
+    (données via /api/stacks) — on vérifie le contrat réel des deux côtés."""
+    status, body, _ = _get(server_url, "/")
+    assert status == 200
+    assert 'id="stacks"' in body
+    assert "stacks-grid" in body
+    status_js, js, _ = _get(server_url, "/app.js")
+    assert status_js == 200
+    assert "stack-card" in js  # le renderer crée les cartes
+    assert "/api/stacks" in js  # alimentées par l'API
+
+
+def test_routes_b02a_intactes(server_url):
+    status, body, _ = _get(server_url, "/api/detect")
+    assert status == 200
+    detect = json.loads(body)
+    assert "cpu_model" in detect
+
+    status, _, _ = _get(server_url, "/api/health")
+    assert status == 200
+
+    status, _, _ = _get(server_url, "/nope")
+    assert status == 404
+
+
+def test_auto_suffisance_assets():
+    import forgeai.web.server as server_mod
+
+    assets_dir = Path(server_mod.__file__).resolve().parent / "assets"
+    for name in ("index.html", "app.css", "app.js"):
+        text = (assets_dir / name).read_text(encoding="utf-8")
+        assert "http://" not in text
+        assert "https://" not in text
```
