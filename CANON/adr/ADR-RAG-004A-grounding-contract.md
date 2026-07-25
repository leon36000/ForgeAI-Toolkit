# ADR-RAG-004A — Contrat d'ancrage (grounding) vérifiable

| Champ | Valeur |
|---|---|
| Statut | **PROPOSED** — en attente d'approbation Nathan (gate d'approbation finale : Nathan ; aucune implémentation ne démarre avant cette approbation) |
| Package | RAG-004A (**DESIGN_FIRST** — design pur, aucune implémentation dans le présent document) |
| Finding | FAI-U-004 |
| Packages dépendants | RAG-005 (runtime du vérificateur), RAG-004B (câblage pipeline) |
| Date | à dater au moment de l'approbation |

---

## 1. Contexte

Le pipeline RAG (`src/forgeai/rag/hardened.py`) applique des guardrails d'E/S (`src/forgeai/guardrails/io_guard.py`) : garde d'entrée anti-injection avant tout accès retrieval/LLM, garde de sortie censée vérifier l'ancrage de la réponse générée au contexte récupéré. La promesse affichée est : « Bloqué → réponse refusée `blocked` sans fabrication ».

Cette promesse est **fausse en l'état** : la vérification d'ancrage de sortie est neutralisée par un booléen codé en dur à l'appel. Le finding FAI-U-004 documente le défaut ; le présent ADR définit le contrat qui le corrige, sans écrire le code (DESIGN_FIRST).

## 2. Reproduction / preuve du défaut

**Preuve statique (fichier:ligne).**

- `src/forgeai/rag/hardened.py:101` : appelle `scan_output(answer, context_used=True)` — le second argument est **codé en dur à `True`**, indépendamment de tout ancrage réel de `answer`.
- `src/forgeai/guardrails/io_guard.py:59-60` : `if not context_used: raise GuardrailBlocked("sortie non ancrée (aucun contexte récupéré)")` — cette branche est **du code mort** : la condition n'est jamais vraie puisque l'appelant passe toujours `True`.
- Conséquence observable : toute réponse non vide sort du pipeline avec `{"context_used": True}` (voir le `return` final de `query()`), qu'elle s'appuie ou non sur le contexte récupéré. Une hallucination pure est présentée à l'appelant comme ancrée.

**Preuve dynamique (reproductible).** Injecter un LLM factice retournant une phrase sans rapport avec le contexte (ex. contexte sur « retraite », réponse « la capitale de l'Australie est Canberra ») : le pipeline retourne `context_used: True`, aucun `blocked`. Aucun test ne peut échouer sur ce comportement, car il n'existe aucun oracle calculable — c'est précisément le vide que ce contrat comble.

## 3. Contrat & états

### 3.1 Vocabulaire

- **Passage récupéré** : élément de `hits` dans `query()` (`h["payload"]["text"]`, `h["payload"]["source"]`), identifié de façon stable par `passage_id = sha256(texte_normalisé)` tronqué + `source`.
- **Span de réponse** : segment contigu de `answer` (unité : phrase ou proposition ; découpage déterministe documenté).
- **Citation** : couple `(span_réponse, passage_id)` produit par le vérificateur.
- **Support** : une citation est **supportée** si le span est entaillable du passage par un critère calculable (§3.3).

### 3.2 États d'ancrage

| État | Définition calculable |
|---|---|
| `grounded` | Couverture de citations **≥ seuil S** (S = 0,8 par défaut, configuration explicite) : au moins 80 % des spans factuels de la réponse possèdent une citation supportée, ET zéro span contradictoire (§3.4). |
| `ungrounded` | Couverture < S, OU au moins un span est en contradiction avec le passage cité. |
| `unknown` | Le vérificateur ne peut pas décider : contexte vide, vérificateur indisponible/timeout, réponse non segmentable, ou signal interne < confiance minimale. `unknown` est un état **de premier rang**, jamais assimilé à `grounded`. |

### 3.3 Critère de support (preuve d'ancrage)

Une citation `(span, passage_id)` est une **preuve** si et seulement si :

1. **Provenance** : `passage_id` appartient à l'ensemble exact des passages fournis par retrieval pour cette requête (pas de passage inventé — le vérificateur reçoit la liste close).
2. **Entailment lexical calculable** : recouvrement de contenu mesuré par un score déterministe (ensemble : similarité tokenisée avec normalisation, seuil documenté ; le choix précis du scorer est délégué à RAG-005 mais doit être déterministe, reproductible hors-ligne, sans appel réseau). Score ≥ seuil T (défaut T = 0,6).
3. **Non-contradiction** : aucun marqueur de négation/nombre/date du span ne contredit le passage (contrôle par règles déterministes au minimum).

Seule une citation satisfaisant 1+2+3 incrémente la couverture. Une citation décorative (présente mais non supportée) **ne compte pas** et déclenche `ungrounded` si elle abaisse la couverture sous S.

### 3.4 Politique de refus

- `grounded` → réponse exposée avec `grounding: "grounded"`, citations et sources.
- `ungrounded` → **refus** : `{"answer": "", "blocked": "sortie non ancrée (preuve insuffisante)", "grounding": "ungrounded", ...}`. Aucune réponse fabriquée.
- `unknown` → **dégradation étiquetée ou refus**, jamais un ancrage implicite : mode par défaut = refus (`blocked: "ancrage invérifiable"`) ; mode `allow_labelled` (opt-in explicite) = réponse exposée avec `grounding: "unknown"` et bandeau « non vérifié ». **Interdit dans tous les modes** : émettre `context_used: True` / `grounding: "grounded"` sans preuve.

### 3.5 Métriques (émises à chaque appel)

`grounding_state` (grounded/ungrounded/unknown), `citation_coverage` (0..1), `citations_supported` / `citations_total`, `refusals_total{reason}`, latence du vérificateur, taux d'`unknown` par cause (timeout, contexte vide, faible confiance). Cibles de suivi : taux `unknown` < 5 % en régime nominal ; toute dérive du taux `ungrounded` est investiguée (régression retrieval ou LLM).

## 4. Machine d'états + oracles

États du pipeline de sortie : `RECEIVED` (réponse LLM reçue) → `VERIFIED` (vérificateur exécuté) → état terminal ∈ {`GROUNDED`, `UNGROUNDED`, `UNKNOWN`} → action (`EXPOSE` | `BLOCK` | `EXPOSE_LABELLED`).

| Transition | Condition calculable | Oracle de test | Politique de refus |
|---|---|---|---|
| RECEIVED → UNKNOWN | contexte vide OU vérificateur timeout/erreur OU spans non segmentables | Test : fixture contexte `[]` ou vérificateur stubé en échec → l'oracle lit `grounding_state == "unknown"` et la cause | BLOCK par défaut (§3.4) ; jamais EXPOSE comme ancré |
| RECEIVED → GROUNDED | couverture ≥ S ∧ 0 contradiction | Test : réponse fixture dont les spans sont des paraphrases directes des passages → oracle recompte la couverture attendue = 1,0 ≥ S et exige `grounded` + citations présentes, chaque `passage_id` ∈ liste retrieval | — |
| RECEIVED → UNGROUNDED (couverture) | couverture < S | Test : réponse fixture hors-sujet (Canberra/retraite) → oracle calcule couverture < S et exige `ungrounded` + `blocked` non vide + `answer == ""` | BLOCK, `answer` vidé, pas de fabrication |
| RECEIVED → UNGROUNDED (contradiction) | ≥ 1 span contredit son passage cité | Test : passage « âge légal 64 ans », réponse « 62 ans » citant ce passage → oracle exige `ungrounded`, raison `contradiction` | BLOCK |
| RECEIVED → UNGROUNDED (provenance) | citation pointant hors de la liste retrieval | Test : réponse fixture citant un `passage_id` forgé → oracle vérifie l'appartenance à la liste close et exige `ungrounded`, raison `provenance_invalide` | BLOCK |
| UNKNOWN → EXPOSE_LABELLED | mode `allow_labelled` actif | Test : config opt-in + fixture `unknown` → oracle exige `grounding == "unknown"` présent dans la sortie et absent de toute valeur `grounded` | Dégradation étiquetée uniquement |
| tout état → sortie | — | Test de non-régression : aucune sortie ne contient `context_used: True` hérité ni `grounded` sans `citations_supported ≥ 1` | Invariant global |

Règle d'oracle : chaque test **recalcule** l'état attendu à partir des fixtures (couverture, appartenance, contradiction) et compare à l'état émis — il ne se contente pas d'asséner une chaîne.

## 5. Interface retrieval → guardrail → réponse

**Contrat de données (types conceptuels, sans implémentation).**

1. **Retrieval → Guardrail.** `query()` fournit un `GroundingInput` :
   - `answer: str` — réponse LLM brute ;
   - `passages: list[Passage]` où `Passage = {passage_id: str, source: str, text: str}` — la **liste close** des passages réellement injectés dans le prompt (après rerank/troncature à `top_k`, donc exactement ce que le LLM a vu) ;
   - `query_id: str`, `config: {seuil_S, seuil_T, mode_refus}`.
2. **Guardrail → Pipeline.** Le vérificateur retourne un `GroundingVerdict` :
   - `state: "grounded" | "ungrounded" | "unknown"` ;
   - `coverage: float`, `citations: list[{span, passage_id, supported: bool, reason?}]` ;
   - `reason: str` (obligatoire si ≠ grounded) ; `duration_ms: int`.
   - Le vérificateur est **pur** : pas d'E/S réseau, pas d'appel LLM, déterministe (mêmes entrées → même verdict).
3. **Pipeline → Appelant.** La réponse finale expose :
   - succès : `{answer, sources, grounding: "grounded", citations, coverage}` ;
   - refus : `{answer: "", sources: [], grounding: state, blocked: reason}` — même discipline que le chemin `GuardrailBlocked` existant (jamais de fabrication) ;
   - le champ `context_used: bool` est **retiré** (remplacé par `grounding`) ; voir §8 pour la migration.

Le guardrail de sortie ne reçoit **jamais** un booléen pré-cuit de l'appelant : il calcule. L'appelant (`hardened.py`) ne décide pas de l'ancrage ; il assemble `GroundingInput` et applique le verdict.

## 6. Invariants & modèle de menace

**Invariants.**

- I1 — *Pas de preuve, pas d'ancrage* : toute sortie exposée comme ancrée possède ≥ 1 citation supportée et une couverture ≥ S recalculable par un tiers.
- I2 — *Liste close* : aucune citation ne référence un passage hors de l'ensemble retrieval de la requête.
- I3 — *Fail-closed* : toute indétermination (`unknown`) est traitée comme non-ancrée par défaut.
- I4 — *Déterminisme* : le verdict est reproductible hors-ligne ; pas de dépendance réseau dans le vérificateur (cohérent avec l'invariant portabilité du dépôt).
- I5 — *Non-régression entrée* : la garde d'entrée anti-injection (`scan_input`) est inchangée et s'exécute avant tout retrieval/LLM.

**Menaces couvertes.** (a) Hallucination LLM présentée comme ancrée (cas FAI-U-004). (b) Citations fabriquées ou décoratives (§3.3.1/§3.3.3). (c) Injection indirecte *via le contenu récupéré* tentant de forcer un faux verdict : traitée par I4 (le vérificateur n'exécute aucune instruction du contexte ; il mesure des recouvrements).

**Menaces explicitement hors scope.** Entailment sémantique profond (paraphrases lointaines) : le critère lexical est une borne inférieure assumée, documentée ; il peut produire des faux `ungrounded` (refus sûrs) mais borne les faux `grounded`. Un vérificateur NLI pourra être substitué derrière la même interface si la contrainte de portabilité est relâchée (analogue au compromis documenté dans `src/forgeai/models/vault.py`).

## 7. Alternatives considérées

**Retenue : A — Vérificateur déterministe par citations + couverture (§3).** Déterministe, testable par oracles recalculables, stdlib-compatible, fail-closed. Les faux refus sont observables via métriques et réglables par seuils versionnés.

**Rejetées.**

- **B — Statu quo paramétré** (passer le vrai booléen « hits non vides » à `scan_output`) : ne détecte qu'un contexte vide ; une réponse hallucinée sur contexte non vide reste `True`. Rejetée : ne corrige pas FAI-U-004.
- **C — LLM-as-judge** (un second appel LLM note l'ancrage) : non déterministe, coût/latence doublés, dépendance réseau dans un garde-fou (viole I4), le juge peut halluciner ; aucun oracle de test stable. Rejetée.
- **D — Confiance déclarative du LLM** (le prompt demande au LLM de s'auto-citer et on fait confiance) : citations non vérifiées = citations fabriquables ; viole I1. Rejetée (la *production* de citations par le LLM reste permise, mais seule la *vérification* calculée compte).
- **E — Bloquer toute réponse non extractive** (n'accepter que des citations verbatim) : trop restrictif, tue les paraphrases légitimes ; taux de refus inacceptable. Rejetée.
- **F — Post-filtrage par similarité globale réponse↔contexte (sans spans)** : un score moyen masque une phrase hallucinée noyée dans des phrases ancrées ; pas de provenance par span (viole I1/I2). Rejetée.

## 8. Contrat pour les packages dépendants

### 8.1 RAG-005 — runtime du vérificateur

- **Livrable** : `verify_grounding(input: GroundingInput) -> GroundingVerdict` (signature conceptuelle §5), module pur, déterministe, sans réseau ; configuration `seuil_S`, `seuil_T` injectées, versionnées, loguées dans le verdict.
- **Obligations** : implémenter §3.2–§3.4 ; émettre les métriques §3.5 ; garantir I1–I4.
- **Oracles de test par transition** : le tableau du §4 est le cahier de recette de RAG-005 — un test par ligne, chaque oracle **recalculant** l'état attendu depuis les fixtures (couverture recomptée, appartenance à la liste close, contradiction par règle). Ajout minimal : test de déterminisme (double appel → verdicts identiques) et test de performance (verdict < 50 ms sur 10 passages / réponse de 5 phrases, en local).

### 8.2 RAG-004B — câblage pipeline

- **Livrable** : dans `src/forgeai/rag/hardened.py`, remplacer l'appel de la ligne 101 par la construction de `GroundingInput` (passages = `hits` post-rerank effectivement injectés) puis l'application du verdict ; `src/forgeai/guardrails/io_guard.py` expose la nouvelle entrée de vérification et supprime le paramètre `context_used` de `scan_output` (la branche morte 59-60 disparaît au profit du verdict).
- **Contrat de sortie** : formes exactes du §5.3 ; suppression du champ `context_used` au profit de `grounding`.
- **Oracles de test** : (1) test d'intégration « réponse hors-sujet » → `blocked` présent, `answer == ""` ; (2) test « réponse ancrée » → `grounding == "grounded"` avec citations dont les `passage_id` ⊆ sources retournées ; (3) test de non-régression garde d'entrée (injection → `blocked` avant tout appel LLM) ; (4) test structural : recherche statique interdisant toute réintroduction d'un littéral `True` en argument d'ancrage.

### 8.3 Migration depuis `context_used=True`

1. **Phase 0 (pré-merge)** : feature flag `grounding_mode: "legacy" | "enforce"` (défaut `legacy`).
2. **Phase 1** : RAG-005 livre le vérificateur + ses tests ; en mode `legacy`, le verdict est calculé et **logué en shadow** (métriques §3.5) sans bloquer → mesure du taux de refus à blanc.
3. **Phase 2** : RAG-004B câble `enforce` ; bascule du défaut après validation des métriques shadow (taux `ungrounded` cohérent avec l'attendu, `unknown` < 5 %).
4. **Phase 3** : suppression du chemin `legacy` et du champ `context_used` ; annonce du breaking change de schéma de sortie aux consommateurs.

### 8.4 Rollback

- **Déclencheurs** : taux `unknown` > 15 %, latence p95 du verdict > budget, régression constatée sur les tests d'entrée.
- **Action** : repasser `grounding_mode` à `legacy` (configuration seule, sans revert de code) — le pipeline retrouve le comportement antérieur, y compris son défaut connu, ce qui est assumé et tracé ; puis revert des commits RAG-004B si nécessaire. Le schéma `legacy` est conservé jusqu'à la fin de la Phase 3 précisément pour rendre ce rollback possible en une ligne de configuration.

## 9. Conséquences

**Positives.** La promesse « Bloqué → refus sans fabrication » devient vraie et **testée** ; le code mort `io_guard.py:59-60` est remplacé par une vérification réelle ; chaque transition possède un oracle recalculable ; les métriques rendent l'hallucination observable et régressable ; l'interface pure permet de faire évoluer le scorer sans toucher au câblage.

**Négatives.** Faux refus possibles sur paraphrases lointaines (borne lexicale, §6) — coût assumé, mitigé par les seuils et le mode shadow ; latence ajoutée bornée par le budget de test ; breaking change du schéma de sortie (`context_used` → `grounding`) nécessitant la migration §8.3 ; complexité accrue du guardrail (segmentation, règles de contradiction) à maintenir.

**Conclusion.** Le défaut FAI-U-004 n'est pas un bug local mais l'absence de contrat : tant que l'ancrage est un booléen fourni par l'appelant, il sera vrai par construction. Le présent ADR le remplace par un verdict calculé, provenant, mesuré et refusant par défaut. **Gate d'approbation finale : Nathan — aucune implémentation (RAG-005, RAG-004B) ne démarre avant son approbation explicite.**
