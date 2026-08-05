const browserGlobals = {
  window: "readonly",
  document: "readonly",
  fetch: "readonly",
  console: "readonly",
  setTimeout: "readonly",
  clearTimeout: "readonly",
  localStorage: "readonly",
  location: "readonly",
  navigator: "readonly",
  URL: "readonly",
  EventSource: "readonly",
  alert: "readonly",
  CSS: "readonly",
  FormData: "readonly",
  Blob: "readonly",
  getComputedStyle: "readonly",
  // Les assets utilisent un export UMD : `if (typeof module !== 'undefined' && module.exports)`
  // — c'est DÉLIBÉRÉ, c'est ce qui permet à tests/js/*.cjs de les charger sous Node pour la
  // preuve d'assertions réelles (stories D4 et UI-039). Sans ce global, eslint sort 4 no-undef
  // sur du code parfaitement correct.
  module: "readonly",
  // Globals exposés d'un asset à l'autre via `root.X` : engine_filter.js et adoption.js sont
  // chargés en <script> AVANT app.js, qui les consomme. 3 no-undef sinon, également faux.
  ForgeAIAdoption: "readonly",
  ForgeAIEngineFilter: "readonly",
};

const nodeCommonJsGlobals = {
  require: "readonly",
  module: "readonly",
  __dirname: "readonly",
  process: "readonly",
  console: "readonly",
};

const securityRules = {
  "no-eval": "error",
  "no-implied-eval": "error",
  "no-new-func": "error",
  "no-undef": "error",
};

export default [
  {
    files: [
      "src/forgeai/web/assets/app.js",
      "src/forgeai/web/assets/adoption.js",
      "src/forgeai/web/assets/engine_filter.js",
    ],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "script",
      globals: browserGlobals,
    },
    rules: {
      ...securityRules,
      "no-unused-vars": "warn",
    },
  },
  {
    files: ["tests/js/*.cjs"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "commonjs",
      globals: nodeCommonJsGlobals,
    },
    rules: {
      ...securityRules,
      "no-unused-vars": "warn",
    },
  },
];
