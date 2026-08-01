# OPS-031C — Bundle de diagnostic reproductible et rédigé

- **Issue** : #262 · **Tier** : T2 (sécurité — un bundle de support quitte la machine)
- **Dépend de** : OPS-031B — mergé.
- **Périmètre** : `src/forgeai/diagnostic.py` (nouveau), `src/forgeai/cli.py`,
  `tests/test_ops031c_diagnostic.py` (nouveau), `stories/OPS-031C.md`.

## 1. État MESURÉ de l'existant
`portability.py` possède déjà un « bundle », mais il répond à une **autre question** : exporter le
**setup du stack-modèles** (routes, gateway, wirings, stratégie, budgets) pour **migrer vers une autre
machine**. Il ne contient ni état d'exécution, ni logs, ni matériel — ce n'est pas un bundle de
diagnostic. Il fournit en revanche deux patrons à **réutiliser plutôt qu'à réinventer** :
`_canonical` (sérialisation déterministe) et `bundle_sha256` (empreinte couvrant tout le bundle).

Les briques de contenu existent déjà : `collect_status` (OPS-031A) et `lire_logs_deploiement`
(OPS-031B, déjà borné et rédigé).

## 2. Décision
Un module `forgeai/diagnostic.py` produisant un bundle **reproductible** et **rédigé**.

1. **Reproductible = déterministe et vérifiable.** Sérialisation **canonique**
   (`sort_keys`, séparateurs compacts) et **empreinte SHA256** couvrant l'intégralité du contenu.
   L'horodatage est **injecté** (paramètre), jamais lu de l'horloge à l'intérieur : sans cela, deux
   appels sur le même état produiraient des octets différents et « reproductible » ne voudrait rien
   dire — c'est aussi ce qui rend la propriété **testable**.
2. **Rédigé — à la construction, pas à l'écriture.** Tout le bundle traverse `redact_mapping` /
   `redact_text` **avant** d'exister en mémoire. Même raisonnement qu'OPS-031B : rédiger « au moment
   d'écrire le fichier » laisserait fuir toute autre sortie (affichage, envoi). Les clés sensibles
   sont neutralisées par `is_sensitive_key` (ERR-041A) **quel que soit** leur contenu.
3. **Contenu** : version, horodatage injecté, état d'exécution (`collect_status`), logs de
   déploiement **bornés** (`lire_logs_deploiement`), et l'empreinte du tout. Dépendances **injectées**
   → testable sans sonde réelle, comme `collect_status`.
4. **`forgeai diagnostic [--out FICHIER] [--tail N]`** : écrit le bundle (ou l'imprime). Un bundle de
   support est destiné à **quitter la machine** — c'est précisément pourquoi la rédaction et
   l'absence de donnée confidentielle sont la propriété centrale de cette story, pas un ornement.

## 3. TDAD (RED d'abord) — `tests/test_ops031c_diagnostic.py`
- **G1 reproductibilité** : deux constructions avec le **même horodatage injecté** et le même état
  produisent des octets **identiques** et la **même empreinte**.
- **G2 l'empreinte couvre le contenu** : altérer une valeur du bundle change l'empreinte recalculée
  (détection d'altération).
- **G3 rédaction** : une fausse valeur confidentielle présente dans l'état ou les logs
  **n'apparaît pas** dans le bundle.
- **G4 clés sensibles** : une clé au nom réputé sensible est neutralisée **quelle que soit** sa
  valeur (on ne dépend pas de la seule détection par motif dans la valeur).
- **G5** l'horodatage est **injecté** : aucun appel d'horloge interne (deux constructions à des
  moments différents, même horodatage passé → mêmes octets).
- **G6 CLI** : `forgeai diagnostic --out F` écrit un JSON valide, borné, rédigé ; sortie propre.
- **Mutation** : retirer `sort_keys` → G1 tombe ; retirer la rédaction → G3/G4 tombent.

## 4. Critères d'acceptation
- **CA1** bundle reproductible : sérialisation canonique + empreinte SHA256 couvrant le contenu.
- **CA2** aucune donnée confidentielle : rédaction à la CONSTRUCTION, clés sensibles
  neutralisées par leur nom.
- **CA3** contenu borné (logs) et dépendances injectées (testable sans sonde).
- **CA4** `forgeai diagnostic` ; suite complète verte, couverture ≥ 85 %.
