(function () {
  "use strict";

  const i18n = {
    fr: {
      loading: "Chargement de la détection matérielle…",
      title: "Matériel détecté",
      cpu: "Processeur",
      cores: "Cœurs",
      arch: "Architecture",
      ram: "Mémoire vive",
      os: "Système",
      gpus: "GPU(s)",
      none: "aucun",
      error: "Impossible de détecter le matériel.",
      langLabel: "FR",
    },
    en: {
      loading: "Loading hardware detection…",
      title: "Detected hardware",
      cpu: "CPU",
      cores: "Cores",
      arch: "Architecture",
      ram: "RAM",
      os: "Operating system",
      gpus: "GPU(s)",
      none: "none",
      error: "Unable to detect hardware.",
      langLabel: "EN",
    },
  };

  let currentLang = "fr";

  function t(key) {
    return i18n[currentLang][key] ?? key;
  }

  function setTexts() {
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.dataset.i18n;
      if (key && i18n[currentLang][key]) {
        el.textContent = i18n[currentLang][key];
      }
    });
    const toggle = document.getElementById("lang-toggle");
    if (toggle) toggle.textContent = t("langLabel");
  }

  function formatBytes(gb) {
    return `${gb.toFixed(1)} Go`;
  }

  function render(hw) {
    const container = document.getElementById("hardware");
    const gpuCount = Array.isArray(hw.gpus) ? hw.gpus.length : 0;
    const gpuText = gpuCount > 0 ? `${gpuCount}` : t("none");

    container.innerHTML = `
      <h2>${t("title")}</h2>
      <div class="grid">
        <div class="item"><span class="label">${t("cpu")}</span><span class="value">${escapeHtml(hw.cpu_model)}</span></div>
        <div class="item"><span class="label">${t("cores")}</span><span class="value">${hw.cpu_cores}</span></div>
        <div class="item"><span class="label">${t("arch")}</span><span class="value">${escapeHtml(hw.cpu_arch)}</span></div>
        <div class="item"><span class="label">${t("ram")}</span><span class="value">${formatBytes(hw.ram_gb)}</span></div>
        <div class="item"><span class="label">${t("os")}</span><span class="value">${escapeHtml(hw.os_name)}</span></div>
        <div class="item"><span class="label">${t("gpus")}</span><span class="value">${gpuText}</span></div>
      </div>
    `;
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function loadHardware() {
    const container = document.getElementById("hardware");
    try {
      const response = await fetch("/api/detect");
      if (!response.ok) throw new Error(response.statusText);
      const data = await response.json();
      render(data);
    } catch (err) {
      container.innerHTML = `<p class="error">${t("error")} (${escapeHtml(err.message)})</p>`;
    }
  }

  function initTheme() {
    const toggle = document.getElementById("theme-toggle");
    const root = document.documentElement;
    const updateIcon = () => {
      toggle.textContent = root.dataset.theme === "dark" ? "☀️" : "🌙";
    };
    toggle.addEventListener("click", () => {
      root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
      updateIcon();
    });
    updateIcon();
  }

  function initLang() {
    const toggle = document.getElementById("lang-toggle");
    toggle.addEventListener("click", () => {
      currentLang = currentLang === "fr" ? "en" : "fr";
      setTexts();
      loadHardware();
    });
    setTexts();
  }

  document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    initLang();
    loadHardware();
  });
})();
