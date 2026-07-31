# WEB-034B — Mode TLS explicite ou refus des identifiants sur HTTP réseau

- **Issue** : #252 · **Tier** : T2 (sécurité — confidentialité des identifiants en transit)
- **Dépend de** : WEB-034A (en-têtes de sécurité) — mergé.
- **Reprise lane CODEX** · **Périmètre** : `src/forgeai/web/server.py`,
  `tests/test_web034b_secure_transport.py` (nouveau), `stories/WEB-034B.md`.

## 1. Problème (code réel)
Le serveur (`ThreadingHTTPServer`) sert en **HTTP clair** et n'a aucun support TLS. Sur un bind
non-loopback (`--host 0.0.0.0`), le jeton `Authorization: Bearer` — exigé par WEB-001/016/017 dès
qu'on quitte le loopback — et le mot de passe de `POST /api/nodes` transitent **en clair**,
capturables par un attaquant passif du réseau.

## 2. Décision (deux volets complémentaires)
1. **REFUS (protection immédiate)** — une requête porteuse d'identifiants (`Authorization`) sur un
   transport **non sûr** est rejetée **426 Upgrade Required**, message générique orientant vers TLS ou
   un tunnel (ne divulgue pas quel secret a été vu).
2. **TLS opt-in (issue de secours)** — si `FORGEAI_TLS_CERT` **et** `FORGEAI_TLS_KEY` sont définis,
   `build_server` enveloppe la socket (`ssl.SSLContext(PROTOCOL_TLS_SERVER)`), `serve()` affiche
   `https://`, et le transport devenant sûr, le refus (1) ne s'applique plus. **Aucun certificat n'est
   généré** : l'opérateur reste maître de son matériel cryptographique.

### 2b. Prédicat « transport sûr » — adresse SOURCE, pas le bind
`_is_secure_transport()` = client en **loopback** (`_is_loopback_host(self.client_address[0])`) **OU**
connexion **TLS** (`isinstance(self.connection, ssl.SSLSocket)`). Se baser sur l'adresse SOURCE (et non
sur le bind) autorise l'UI locale même quand le serveur écoute sur `0.0.0.0` — indispensable au confort
d'usage — tout en refusant les vrais clients réseau en clair.

### 2c. Le mot de passe du corps est couvert transitivement (mesuré, non supposé)
L'ADR proposait d'inspecter aussi un champ `password` du corps. **Écarté comme redondant** : sur un bind
non-loopback, `authorize_mutation` (WEB-001) **exige déjà** un Bearer — donc tout `POST /api/nodes`
réseau porte un `Authorization` et tombe sur la garde d'en-tête. Sans Bearer, il est refusé 401 avant
tout traitement. Inspecter le corps exigerait de le lire avant la garde (surface d'attaque en plus)
pour zéro gain. Un test couvre explicitement ce chemin (password réseau → refusé).

### 2d. Portée du refus
Branché en TÊTE de `_guard_mutation` → couvre les **mutations** (POST) ET les **GET sensibles**
(WEB-017), sans toucher `/api/health`, les assets ni l'i18n : le trafic **sans identifiant** reste servi
sur un bind réseau (on ne bloque que ce qui fuit un secret).

## 3. TDAD (RED d'abord) — `tests/test_web034b_secure_transport.py`
Client de test = 127.0.0.1 ⇒ pour simuler un client RÉSEAU on patche `_is_loopback_host` → False
(même technique que WEB-016). Certificat auto-signé généré par `openssl` en `tmp_path`.
- identifiants sur réseau clair → **426** + message TLS ;
- **sans** identifiant sur réseau clair (`/api/health`) → **200** (pas de blocage du trafic sain) ;
- loopback en clair + identifiants → **jamais 426** (UI locale préservée) ;
- password de `POST /api/nodes` sur réseau clair → refusé (couverture transitive, cf. §2c) ;
- **TLS réel** (cert auto-signé, `FORGEAI_TLS_*`) + identifiants + `_is_loopback_host`→False → **pas de
  426** : c'est bien le TLS (et non le loopback) qui rend le transport sûr ;
- `build_server` sans variables d'env → `forgeai_tls is False`.
- **Mutation** : retirer l'appel `_require_secure_transport` → le test 426 tombe.

## 4. Critères d'acceptation
- **CA1** identifiants + transport réseau non chiffré → 426, message sans fuite.
- **CA2** trafic sans identifiant, loopback, et TLS → non bloqués.
- **CA3** TLS opt-in fonctionnel (socket enveloppée, `https://`, `forgeai_tls`), sans génération de cert.
- **CA4** non-régression : WEB-016/017/034A intacts ; suite complète verte, couverture ≥ 85 %.
