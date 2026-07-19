(function () {
  "use strict";

  const I18N = {
    fr: {
      stacks_title: "Choisissez votre stack",
      stacks_subtitle: "Profils de déploiement ForgeAI",
      hardware_title: "Matériel détecté",
      hardware_subtitle: "Ressources locales disponibles",
      recommended: "Recommandé",
      select_stack: "Cliquez pour voir le détail",
      detail_title: "Détail du profil",
      defaults: "Défauts par sphère",
      wiring: "Câblage (wiring)",
      no_wiring: "Aucun wiring",
      close: "Fermer",
      n_deploy: "briques déployées",
      loading: "Chargement…",
      error_load: "Erreur de chargement",
      lang_fr: "FR",
      lang_en: "EN",
      theme_light: "Clair",
      theme_dark: "Sombre",
      cpu: "Processeur",
      memory: "Mémoire",
      gpus: "GPUs",
      no_gpu: "Aucun GPU détecté",
      disk: "Disque",
      unknown: "Inconnu"
    },
    en: {
      stacks_title: "Choose your stack",
      stacks_subtitle: "ForgeAI deployment profiles",
      hardware_title: "Detected hardware",
      hardware_subtitle: "Available local resources",
      recommended: "Recommended",
      select_stack: "Click to view details",
      detail_title: "Profile details",
      defaults: "Defaults by sphere",
      wiring: "Wiring",
      no_wiring: "No wiring",
      close: "Close",
      n_deploy: "deployed bricks",
      loading: "Loading…",
      error_load: "Loading error",
      lang_fr: "FR",
      lang_en: "EN",
      theme_light: "Light",
      theme_dark: "Dark",
      cpu: "CPU",
      memory: "Memory",
      gpus: "GPUs",
      no_gpu: "No GPU detected",
      disk: "Disk",
      unknown: "Unknown"
    }
  };

  const state = {
    lang: safeStorage("lang") || "fr",
    theme: safeStorage("theme") || "dark",
    detect: null,
    stacks: [],
    spheres: [],
    selectedProfile: null
  };

  function $(sel) { return document.querySelector(sel); }
  function $$(sel) { return document.querySelectorAll(sel); }

  function safeStorage(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }

  function safeStorageSet(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* ignore */ }
  }

  function t(key) { return I18N[state.lang][key] || key; }

  function escapeHtml(text) {
    if (text == null) return "";
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function updateI18n() {
    $$("[data-i18n]").forEach((el) => {
      const key = el.dataset.i18n;
      if (I18N[state.lang][key]) el.textContent = I18N[state.lang][key];
    });
  }

  function setTheme(theme) {
    state.theme = theme;
    document.documentElement.setAttribute("data-theme", theme);
    safeStorageSet("theme", theme);
    const btn = $("#theme-toggle");
    if (btn) btn.textContent = theme === "dark" ? t("theme_light") : t("theme_dark");
  }

  function toggleTheme() {
    setTheme(state.theme === "dark" ? "light" : "dark");
  }

  function setLang(lang) {
    state.lang = lang;
    document.documentElement.setAttribute("lang", lang);
    safeStorageSet("lang", lang);
    updateI18n();
    renderStacks();
    if (state.selectedProfile) renderDetail(state.selectedProfile);
    setTheme(state.theme);
  }

  function toggleLang() {
    setLang(state.lang === "fr" ? "en" : "fr");
  }

  function getRecommendedId() {
    const gpus = state.detect && Array.isArray(state.detect.gpus) ? state.detect.gpus : [];
    return gpus.length >= 1 ? "agentique" : "assistant-entreprise";
  }

  function renderHardware(detect) {
    if (!detect) return;
    const cpuEl = $('[data-detect="cpu"]');
    if (cpuEl) cpuEl.textContent = detect.cpu_model || t("unknown");
    const memEl = $('[data-detect="memory"]');
    if (memEl) {
      const mem = detect.memory_gb || detect.memory;
      memEl.textContent = mem ? `${mem} GB` : t("unknown");
    }
    const gpuEl = $('[data-detect="gpus"]');
    if (gpuEl) {
      const gpus = detect.gpus || [];
      gpuEl.textContent = gpus.length ? gpus.join(", ") : t("no_gpu");
    }
    const diskEl = $('[data-detect="disk"]');
    if (diskEl) diskEl.textContent = detect.disk || t("unknown");
  }

  function getStacksGrid() {
    const container = $("#stacks");
    if (!container) return null;
    let grid = container.querySelector(".stacks-grid");
    if (!grid) {
      grid = document.createElement("div");
      grid.className = "stacks-grid";
      container.appendChild(grid);
    }
    return grid;
  }

  function renderStacks() {
    const grid = getStacksGrid();
    if (!grid) return;
    grid.innerHTML = "";
    const recommended = getRecommendedId();

    state.stacks.forEach((stack) => {
      const card = document.createElement("div");
      card.className = "stack-card" + (stack.id === recommended ? " recommended" : "");
      card.dataset.stackId = stack.id;
      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");
      card.setAttribute("aria-label", stack.name || stack.id);

      const desc = state.lang === "en" ? stack.description_en : stack.description_fr;
      const defaults = stack.defaults || {};
      const chips = Object.entries(defaults).slice(0, 3)
        .map(([sid, bid]) => `<span class="default-chip">${escapeHtml(sid)}: ${escapeHtml(bid)}</span>`)
        .join("");

      card.innerHTML = `
        <h3>${escapeHtml(stack.name)}</h3>
        <p class="stack-desc">${escapeHtml(desc)}</p>
        <div class="stack-meta">
          <span class="n-deploy-badge">${stack.n_deploy} ${escapeHtml(t("n_deploy"))}</span>
          ${stack.id === recommended ? `<span class="recommended-badge">${escapeHtml(t("recommended"))}</span>` : ""}
        </div>
        <div class="default-chips">${chips}</div>
      `;

      card.addEventListener("click", () => selectStack(stack.id));
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          selectStack(stack.id);
        }
      });
      grid.appendChild(card);
    });
  }

  function renderDetail(profile) {
    state.selectedProfile = profile;
    const panel = $("#stack-detail");
    if (!panel) return;
    panel.hidden = false;

    const nameEl = $("#detail-name");
    if (nameEl) nameEl.textContent = profile.name || "";
    const descEl = $("#detail-description");
    if (descEl) descEl.textContent = (state.lang === "en" ? profile.description_en : profile.description_fr) || "";

    const defaultsEl = $("#detail-defaults");
    if (defaultsEl) {
      defaultsEl.innerHTML = "";
      const defs = profile.default_by_sphere || {};
      Object.entries(defs).forEach(([sid, bid]) => {
        const sphere = state.spheres.find((s) => s.id === sid);
        const sname = sphere ? (state.lang === "en" ? sphere.name_en : sphere.name_fr) : sid;
        const li = document.createElement("li");
        li.innerHTML = `<strong>${escapeHtml(sid)} — ${escapeHtml(sname)}</strong> : <code>${escapeHtml(bid)}</code>`;
        defaultsEl.appendChild(li);
      });
    }

    const wiringEl = $("#detail-wiring");
    if (wiringEl) {
      wiringEl.innerHTML = "";
      const wires = profile.wiring || [];
      if (wires.length === 0) {
        const li = document.createElement("li");
        li.textContent = t("no_wiring");
        wiringEl.appendChild(li);
      } else {
        wires.forEach((w) => {
          const li = document.createElement("li");
          li.textContent = w;
          wiringEl.appendChild(li);
        });
      }
    }

    updateI18n();
  }

  async function selectStack(id) {
    $$(".stack-card").forEach((c) => c.classList.remove("selected"));
    const card = $(`.stack-card[data-stack-id="${id}"]`);
    if (card) card.classList.add("selected");

    const panel = $("#stack-detail");
    if (panel) panel.hidden = false;

    try {
      const res = await fetch(`/api/stacks/${encodeURIComponent(id)}`);
      if (!res.ok) throw new Error("status " + res.status);
      const profile = await res.json();
      renderDetail(profile);
    } catch (e) {
      if (panel) panel.innerHTML = `<p class="error">${escapeHtml(t("error_load"))}</p>`;
    }
  }

  function closeDetail() {
    const panel = $("#stack-detail");
    if (panel) panel.hidden = true;
    $$(".stack-card").forEach((c) => c.classList.remove("selected"));
    state.selectedProfile = null;
  }

  function showLoadingError() {
    const app = $("#app");
    const msg = escapeHtml(t("error_load"));
    if (app) app.insertAdjacentHTML("afterbegin", `<p class="error-banner">${msg}</p>`);
  }

  async function boot() {
    setTheme(state.theme);
    setLang(state.lang);

    try {
      const [dRes, sRes, spRes] = await Promise.all([
        fetch("/api/detect"),
        fetch("/api/stacks"),
        fetch("/api/spheres")
      ]);
      if (!dRes.ok || !sRes.ok || !spRes.ok) throw new Error("init fetch failed");
      state.detect = await dRes.json();
      state.stacks = await sRes.json();
      state.spheres = await spRes.json();
      renderHardware(state.detect);
      renderStacks();
    } catch (e) {
      showLoadingError();
    }

    $("#lang-toggle")?.addEventListener("click", toggleLang);
    $("#theme-toggle")?.addEventListener("click", toggleTheme);
    $("#stack-detail-close")?.addEventListener("click", closeDetail);

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeDetail();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
