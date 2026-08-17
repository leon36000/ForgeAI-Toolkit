# ERR-041A — Redaction centrale (erreurs, logs, états persistés)

Reprise de la lane CODEX (Codex retiré 2026-07-30, gouvernance seq 310). Issue #237.
Fondation SÉCURITÉ (TDAD) : débloque ERR-041B/C, CLI-013/036, OPS-031*. Dépendance ORCH-001 (faite).
Aucun design laissé par CODEX — décision architecte (Kimi-K3) rendue et vérifiée ci-dessous.

## Découpage
- **Lot 1 (cette story, d'abord)** : module `src/forgeai/core/redaction.py` (stdlib-only, sans import forgeai) + `tests/test_redaction.py` (TDAD, rouge d'abord).
- **Lot 2** : adoption aux **3 chemins de fuite RÉELS et courants** (RouteError, deploy-state writer, portability.py:69 -> délégation), chacun prouvé par un test real-path. Les 2 autres sites du design (gateway/rag except, openbao_init) sont **déjà durcis par conception** — écart mesuré et prouvé en §7, reporté à ERR-041B avec le module comme primitive prête. Cf. §4 (design) vs §7 (implémentation).

# DÉCISION D'ARCHITECTURE — ERR-041A : redaction centrale (erreurs, logs, états persistés)

- Statut : PROPOSÉ — prêt pour implémentation sous TDAD
- Référence : issue #237 ; débloque ERR-041B/C, CLI-013/036, OPS-031*
- Portée : `src/forgeai/core/redaction.py` (nouveau) ; adoption : module `routes` (RouteError), `gateway.py`, `openbao_init`, writer deploy-state, `core/portability.py:69` ; `tests/test_redaction.py` (nouveau)
- Invariant : aucune signature existante cassée ; `portability.secret_keys` conserve son nom et capte au moins tout ce qu'il captait avant.

## 1. EMPLACEMENT — `src/forgeai/core/redaction.py`

Décision : module feuille dans `core/`, imports stdlib uniquement (`re`, `collections.abc`, `typing`). AUCUN import `forgeai.*` — propriété vérifiée par test (§5.12), pas par discipline.

Confrontation, une ligne chacune :

- **`core/redaction.py`** — retenu : `core/` abrite déjà les utilitaires bas niveau partagés (précédent #286 : `core/_portable_lock.py`, stdlib-only, consommé depuis `models/` sans controverse) et la convention à étendre (`portability.py:69`) ; un module sans aucun import interne ne peut créer de cycle — l'impossibilité est structurelle.
- **`secrets/redaction.py` (nouveau package)** — rejeté : un package top-level pour un seul module crée un espace de nommage sans contenu prévisible ; si un domaine secrets émerge sous ERR-041B/C, migrer un module auto-contenu est un renommage, pas une refonte.

## 2. API — constantes gelées, trois fonctions et un prédicat

Pas de `RedactionRegistry` : un registre est un état global mutable avec ordre d'enregistrement implicite — contraire au contrat « sans état » ; la surface de motifs est finie et connue, et une extension = modification d'une constante + tests, ce que le TDAD couvre déjà. Minimal donc.

    REDACTED: Final[str] = "«REDACTED»"
    # Marqueur stable, greppable, diffable. Remplace INTÉGRALEMENT la valeur :
    # aucun préfixe/suffixe conservé (un fragment de clé suffit à corréler).

    SENSITIVE_KEY_TOKENS: Final[frozenset[str]] = frozenset({
        "key", "apikey", "secret", "token", "password",
        "passphrase", "authorization", "bearer", "credentials",
    })

    MAX_DEPTH: Final[int] = 32  # borne de récursion (cycles, structures pathologiques)

    SECRET_VALUE_PATTERNS: Final[tuple[Pattern[str], ...]]
    # Motifs compilés, appliqués dans un ordre fixe (déterminisme), tous
    # LINÉAIRES : classes de caractères à quantificateur simple ; ni
    # backreference, ni lookaround quantifié, ni alternance recouvrante
    # quantifiée. La sûreté vient de la linéarité, jamais d'une troncature.
    #   M1 schème d'autorisation : « Bearer » + suite non-blanche (casse
    #      insensible) → « Bearer » conservé (non secret), valeur → marqueur.
    #      La classe de valeur exclut espace, guillemets, « & », « ; ».
    #   M2 clé=valeur en texte libre : nom contenant key|token|secret|
    #      password|passphrase (bornes de mot, casse insensible — couvre
    #      api_key, FORGEAI_API_TOKEN, LANGFUSE_NEXTAUTH_SECRET, séparateur = ou :) +
    #      séparateur « = » ou « : » → nom et séparateur conservés, valeur
    #      (guillemets optionnels) intégralement remplacée.
    #   M3 clé préfixée par provenance : « sk- » + ≥8 caractères
    #      [A-Za-z0-9_-] → marqueur (seuil 8 : les vraies clés en ont ≥20,
    #      les mots ordinaires ne matchent pas).
    #   M4 empreinte/hex long : ≥32 caractères hexadécimaux bornés → marqueur.

    def is_sensitive_key(key: object) -> bool
    # True ssi la forme normalisée (minuscules, découpe sur tout caractère
    # non alphanumérique) intersecte SENSITIVE_KEY_TOKENS.
    # « FORGEAI_API_TOKEN » → True ; « monkey », « keyboard », « note » →
    # False (découpe sur séparateurs, jamais de test de sous-chaîne).
    # Entrée non-str → False. Ne lève jamais.

    def redact_text(s: str) -> str
    # Applique M1..M4 séquentiellement. Entrée non-str : coercion gardée
    # (str() sous try ; repli : nom de classe). Ne lève jamais, ne tronque
    # jamais.

    def redact_mapping(d: Mapping) -> dict
    # Nouveau dict — l'entrée n'est JAMAIS mutée, la structure est préservée.
    # Par couple (k, v), récursivement à tous les niveaux :
    #   - is_sensitive_key(k) → REDACTED, quel que soit le type de v ;
    #   - v Mapping → récursion ; v list/tuple → list d'items récursive ;
    #   - v str → redact_text(v) (défense en profondeur : un Bearer peut
    #     se cacher sous une clé innocente) ;
    #   - autre type → inchangé.
    # Au-delà de MAX_DEPTH : sous-arbre remplacé par REDACTED — couvre les
    # structures cycliques sans lever.

    def redact_exception(exc: BaseException) -> str
    # « {type(exc).__name__}: {redact_text(str(exc))} » ; si str(exc) lève →
    # le seul nom de classe. Jamais de lever, y compris sur exception
    # exotique.

Idempotence par construction : le marqueur ne contient aucune forme secrète, et `Bearer «REDACTED»` / `key=«REDACTED»` sont des points fixes de M1/M2.

## 3. CONTRAT de sûreté

(a) **Déterministe et sans état** : fonctions pures, pas d'E/S, pas d'horloge, pas d'aléa, constantes gelées (frozenset/tuple), ordre d'application des motifs fixe.

(b) **Idempotent** : `redact(redact(x)) == redact(x)`, texte comme mapping — prouvé sur chaque fixture (§5.8), garanti par le point fixe du marqueur.

(c) **Ne lève jamais** : coercion gardée, profondeur bornée, motifs linéaires ; None, bytes, objet dont `__str__` lève, dict auto-référencé → une valeur est retournée, pas une trace. Aucune borne de longueur : la troncature est interdite (ambiguë), la sûreté sur grande entrée vient de la linéarité des motifs (prouvée §5.11).

(d) **Frontière** : elle est dans la LISTE (tokens de clés + motifs de valeurs), versionnée avec ses tests — ce qui correspond est intégralement remplacé, ce qui ne correspond pas passe tel quel. Faux négatif toléré et documenté : un jeton opaque sans préfixe sous clé innocente passe ; la règle d'extension est « en cas de doute, ajouter à la liste » — on sur-rédige, on n'affine jamais pour préserver un fragment de valeur. Faux positif accepté : un sha1 git en log est rédigé ; le coût est du diagnostic, jamais de la confidentialité.

## 4. POINTS D'ADOPTION — maintenant vs suivi

MAINTENANT — un site par catégorie de fuite, chacun prouvé par §5.10 :

1. **`routes.RouteError`** — redaction à la CONSTRUCTION du message (le message stocké est déjà rédigé : tout rendu ou log ultérieur est sûr par construction ; couvre `add_cloud(api_key, passphrase)`).
2. **`gateway.py`, handler `except`** — message journalisé/relévé via `redact_exception` (couvre `HardenedRagClient.gateway_key` ; catégorie logs).
3. **`openbao_init`** — `redact_mapping` sur la config avant persistance/log (couvre `FORGEAI_BAO_TOKEN` et la famille d'env).
4. **Writer deploy-state** — `redact_mapping` à l'écriture de l'état (catégorie états persistés).
5. **`core/portability.py:69`** — le set local est remplacé par une délégation à `is_sensitive_key` : source de vérité unique, comportement étendu (sur-rédaction), compatibilité garantie par test (§5.6). Coût : un import.

`probe.py` n'est PAS modifié : `Authorization: Bearer {api_key}` est une émission légitime ; toute fuite de cet en-tête dans un message d'erreur est couverte par M1 aux points 1–2.

SUIVI (ERR-041B/C, hors story) : rendus d'erreur CLI (CLI-013/036), env Langfuse (`FORGEAI_LANGFUSE_*`), `budgets.json` / `meter-events.jsonl`, journaux du registre, OPS-031*.

## 5. STRATÉGIE DE TEST TDAD — rouge d'abord

`tests/test_redaction.py` écrit en entier AVANT le module (rouge = ImportError), implémenté jusqu'au vert sans retouche des tests. Secrets de test : fixtures longues et distinctives (constante `SK` du module de test, hex de 64) n'apparaissant nulle part ailleurs dans les sorties attendues — la preuve d'absence ne peut pas être un faux positif.

1. **Chaque forme de la surface** (paramétré) : `Bearer <clé>` ; `sk-…` seul ; `api_key`, `key`, `token`, `password`, `passphrase` (séparateurs `=`/`:`, casses variées) ; les cinq env nommées (`FORGEAI_API_TOKEN`, `FORGEAI_BAO_TOKEN`, `FORGEAI_GATEWAY_KEY`, `FORGEAI_LANGFUSE_ENCRYPTION_KEY`, `FORGEAI_LANGFUSE_NEXTAUTH_SECRET`) ; hex 32/40/64 → pour chacun : secret absent, marqueur présent.
2. **Bornes de M4** : hex de 7 (git court) NON rédigé ; hex de 32 rédigé.
3. **M1** conserve le schème : la sortie porte `Bearer «REDACTED»`.
4. **M2** conserve nom de clé et séparateur, rédige intégralement la valeur, guillemets compris.
5. **Mapping imbriqué** : `{"routes": [{"api_key": S, "name": "openai"}], "meta": {"passphrase": P}, "tags": ["a", S]}` → valeurs sensibles == REDACTED, S rédigé même en liste, clés non sensibles et structure intactes, entrée non mutée (comparaison à copie profonde).
6. **Prédicat de clé** : `FORGEAI_API_TOKEN`, `LANGFUSE_ENCRYPTION_KEY` → True ; `monkey`, `keyboard`, `note` → False ; compatibilité : `api_key`, `key`, `secret` (les trois historiques) → True.
7. **Non-lever** : `redact_text(None / 123 / b"x" / objet dont __str__ lève)` → str ; `redact_mapping` sur dict auto-référencé → retourne sans lever ; valeur bytes/objet → jamais d'exception.
8. **Idempotence** : pour TOUTES les fixtures ci-dessus, texte et mapping.
9. **Absence sans fuite partielle** : outre `secret not in output`, aucune fenêtre de 8 caractères du secret n'apparaît dans la sortie — prouve qu'aucun fragment ne survit.
10. **CHEMIN RÉEL** : (a) RouteError construit avec `api_key` interpolée → message rendu : secret absent (fenêtres §5.9 incluses), marqueur présent ; (b) handler `except` de gateway alimenté d'une exception contenant `Bearer <gateway_key>` → sortie journalisée/rendue rédigée ; (c) config openbao persistée → `FORGEAI_BAO_TOKEN` absente du dict écrit, structure intacte.
11. **Anti-ReDoS** : `"key=" + "A"*100_000`, `"sk-" + "z"*100_000` traités — les motifs linéaires terminent immédiatement ; un motif catastrophique pendrait la CI, le test EST le détecteur.
12. **Contrat de couche** : analyse AST du module — aucun import `forgeai.*` ; l'absence de cycle est prouvée, pas espérée.

## 6. RISQUES — un par ligne

- Sur-rédaction : M4 rédige aussi les empreintes légitimes (sha de contrats, digests git) dans les logs, au prix d'un diagnostic moins lisible — assumé, le contexte autour du marqueur est préservé.
- ReDoS : un motif futur à quantificateurs imbriqués sur grande entrée pendrait le rendu d'erreur — verrou structurel (motifs linéaires uniquement) + test §5.11.
- Faux négatif : un secret opaque sans préfixe sous clé innocente passe en clair — documenté, l'atténuation réelle est côté émetteur (ne jamais interpoler de secret dans un message), chantier ERR-041B/C.

## 7. IMPLÉMENTATION — écarts prouvés vs design (2026-07-30, reprise CODEX)

Codeurs : module `redaction.py` écrit par l'ORCHESTRATEUR (disclosed) après 4 échecs crew (Kimi-K3 budget reasoning ×3, MiniMax-M3 vide ×1) ; tests `test_redaction.py` par crew MiniMax-M3 (lot 1b) = contre-vérification indépendante ; tests d'adoption `test_redaction_adoption.py` par crew Kimi-K3 (lot 2), troncature max-tokens complétée + 1 assertion corrigée par l'orchestrateur (disclosed, structure crew inchangée).

### Lot 1 — module (FAIT, prouvé)
- 87 tests TDAD verts. **6/6 mutations détectantes** (M1..M4, `is_sensitive_key`, troncature — chaque retrait fait tomber ≥1 test ; autorité = exit-code déterministe).
- Écart design assumé : M4 élargi de « hex » à « ≥32 alphanumériques » (sur-rédaction §3(d)) — exigé par une fixture (`"h"*32`, non-hex) en liste sous clé non sensible ; superset de l'hex, journalisé.
- `redact_text` piloté par une table `_REDACTION_RULES` (motif→substitution) : `SECRET_VALUE_PATTERNS` en est dérivé (plus de constante « décorative » ; retirer une règle = mutation détectable). Ajout d'un test discriminant M1 (valeur courte que M4 ne masque pas) après analyse de mutation.

### Lot 2 — adoption aux 3 chemins de fuite RÉELS (FAIT, prouvé — 8 tests real-path, 4/4 mutations détectantes)
1. **`RouteError.__init__`** (models/routes.py) — rédige le message à la construction (couvre `result.detail` d'une sonde en échec). Aucune régression : les messages existants sans secret sont inchangés (tests `existe déjà`/`introuvable` verts).
4. **`_persist_deploy_state`** (web/server.py) — `redact_text` par LIGNE avant persistance (la sortie deploy peut échotyper un secret). `redact_text` par ligne et non `redact_mapping` : le snapshot n'a aucune clé sensible, seul le CONTENU des lignes fuit. Test écrit+relit (round-trip).
5. **`_validate_route`** (portability.py) — délègue à `is_sensitive_key` (source de vérité unique) AVEC garde `SAFE_ROUTE_FIELDS`. **Cadrage honnête** : la garde « champs inconnus » rejetait DÉJÀ tout champ hors whitelist ; l'apport net = message dédié « secret en clair » + définition unifiée du sensible, PAS une extension de la couverture de rejet. Piège `key_fingerprint` (∈ SAFE, contient « key ») neutralisé par la garde (2 mutations détectantes : délégation + garde).

### Sites 2 & 3 du §4 — DÉJÀ durcis par conception (écart MESURÉ, reporté ERR-041B)
Méthode : « avis d'architecte = hypothèse, mesurer avant d'appliquer ». Vérification par lecture/grep :
- **`rag/hardened.py` (gateway_key)** : `_post_bearer` n'a AUCUN point de log ; docstring l.7/33 « clé Bearer JAMAIS journalisée » ; monkeypatché dans TOUS les tests d'erreur. urllib n'échotype pas l'en-tête `Authorization`. Envelopper changerait le type d'exception (URLError→…) SANS fuite courante à corriger. Module dispo pour ERR-041B si un chemin de log est un jour introduit.
- **`openbao_init`** : erreurs sans token (docstring l.20, commentaire l.70) ; AUCUN print/log ; `key_store.write({...root_token...})` DOIT contenir le vrai token (fonctionnel) — `redact_mapping` casserait l'init du coffre. Déjà durci ; rien à rédiger sans casser.

Preuve d'exécution : suite complète verte (exit 0, 1 skip) ; no-stub OK (7 fichiers) ; matrices de mutation lot 1 (6/6) et lot 2 (4/4) détectantes.
