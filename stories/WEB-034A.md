# WEB-034A — En-têtes de sécurité + suppression de la bannière Python

- **Issue** : #251 · **Tier** : T2 (sécurité — durcissement des réponses HTTP)
- **Dépend de** : WEB-016 (rate limiting) — mergé.
- **Reprise lane CODEX** · **Périmètre** : `src/forgeai/web/server.py`,
  `tests/test_web034a_security_headers.py` (nouveau), `stories/WEB-034A.md`.

## 1. Problème (code réel)
Le serveur web n'émet AUCUN en-tête de sécurité (pas de CSP, pas d'anti-sniffing, pas d'anti-clickjacking)
et expose la **bannière Python** via le header `Server` (`ForgeAI/0.1 Python/3.x`, défaut de
`BaseHTTPRequestHandler.version_string`), donnant à un attaquant la version de l'interpréteur.

## 2. Décision (design)
Deux surcharges sur `ForgeAIHandler`, appliquées à TOUTE réponse via le chokepoint unique `end_headers`
(toutes les réponses — `_send`, `_send_json`, SSE, `_rate_gate` — y passent) :
- **`end_headers`** injecte `_SECURITY_HEADERS` puis `super().end_headers()` :
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
  et une **CSP** calibrée sur l'UI réelle.
- **`version_string`** retourne `server_version` seul → header `Server: ForgeAI/0.1` (sans `Python/x`).

### 2b. CSP calibrée sur l'UI (vérifiée, non cassante)
`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;
connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`.
Analyse de `assets/` : scripts et styles UNIQUEMENT externes même-origine (`<script src=app.js>`,
`<link href=app.css>`) ; **aucun** handler inline (`onclick=`) — 27 `addEventListener`, 0 `on*=` ;
**aucun** `style=` inline ; `fetch` vers `/api/*` seulement. Donc **`script-src 'self'` strict ne casse
pas l'UI** (pas d'`unsafe-inline`/`unsafe-eval` côté script). `style-src` tolère `'unsafe-inline'`
(risque XSS négligeable, marge pour un style dynamique éventuel). `frame-ancestors 'none'` double
`X-Frame-Options: DENY` (anti-clickjacking).

## 3. TDAD (RED d'abord) — `tests/test_web034a_security_headers.py`
Serveur live loopback. Groupes :
- en-têtes de sécurité présents sur `/` (HTML) ET sur `/api/health` (JSON) — l'override est global.
- `Server` sans `Python`, commence par `ForgeAI`.
- CSP : `script-src 'self'` présent, SANS `unsafe-inline`/`unsafe-eval` (script strict).
- non-régression : `GET /` → 200 corps non vide.
- Mutation : retirer un header (ou l'override `end_headers`) → un test tombe ; retirer `version_string`
  → le test bannière tombe. (Prouvé.)

## 4. Critères d'acceptation
- **CA1** toutes les réponses portent nosniff + X-Frame-Options DENY + Referrer-Policy + CSP.
- **CA2** header `Server` sans bannière Python.
- **CA3** CSP `script-src 'self'` strict, compatible UI (UI toujours servie).
- **CA4** non-régression : WEB-016/017/015 intacts ; suite complète verte, couverture ≥ 85 %.
