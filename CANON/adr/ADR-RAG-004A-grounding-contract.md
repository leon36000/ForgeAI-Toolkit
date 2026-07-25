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
- `src/forgeai/guardrails/io_guard.py:59-60` : `if not context_used: raise GuardrailBlocked("sortie non ancrée (aucun contexte récupéré)")`.

Conséquence mécanique : le paramètre `context_used` vaut toujours `True` à ce point d'appel, donc la branche `io_guard.py:59-60` est **inatteignable** — c'est du code mort. La vérification d'ancrage runtime n'est **jamais déclenchée**.

**Preuve comportementale.**

- Toute réponse non vide retournée par le LLM après un retrieval non vide est exposée avec `context_used: True` (chemin nominal de `hardened.py`), qu'elle exploite ou non le contexte, qu'elle le contredise, qu'elle invente ses faits.
- Le seul chemin retournant `context_used: False` est le court-circuit « aucun hit » ; il ne constitue pas une vérification d'ancrage, seulement un constat de retrieval vide.
- La branche « sortie vide » de `scan_output` reste vivante ; seule la branche d'ancrage est morte. Le défaut est donc silencieux : les tests qui ne ciblent que « sortie vide » passent et masquent FAI-U-004.

**Oracle minimal de reproduction** (à transformer en test de non-régression par RAG-004B) : pour une question dont le retrieval retourne des chunks et dont la réponse LLM est sémantiquement décorrélée du contexte, le système actuel retourne `context_used: True`. Après correction, ce scénario **ne peut plus** produire `context_used: True`.

## 3. Contrat & états

Le booléen `context_used` cesse d'être une **donnée déclarée** (fournie par l'appelant) et devient une **donnée dérivée** d'un verdict calculé. Le contrat repose sur trois états d'ancrage, chacun **calculable** et **décidable par un test**.

### 3.1 Définitions calculables

Soient :

- **Bundle de retrieval** `B` : la liste ordonnée des chunks exactement tels qu'injectés dans le prompt (cf. §5). Chaque chunk porte un `chunk_id` déterministe (son rang d'apparition dans le contexte formaté), son `text` intégral, sa `source`.
- **Span assertionnel** : une unité factuelle de la réponse. En V1, la segmentation est **déterministe** : découpage de la réponse en phrases (ponctuation forte), chaque phrase non vide = un span. (Raffinements ultérieurs — exclusion des formules de transition — admis uniquement s'ils restent déterministes et versionnés.)
- **Citation** : un marqueur de la réponse référençant un `chunk_id` (format V1 : marqueur numérique `[n]` correspondant au n-ième passage du contexte, tel que présenté au LLM).
- **Citation résolue** : citation dont le `chunk_id` existe dans `B`. Sinon : **citation non résolue** (preuve de fabrication de provenance).
- **Preuve d'ancrage d'un span** : un triplet `(span, chunk_id, s)` où la citation est résolue et où `s`, le recouvrement lexical normalisé entre le span et le texte du chunk, satisfait `s ≥ τ_s`. Normalisation V1 : casse repliée, unicode normalisé, tokenisation sur séparateurs non alphanumériques ; `s = |tokens(span) ∩ tokens(chunk)| / |tokens(span)|`. La normalisation fait partie du contrat et est **versionnée** (toute modification = nouveau comportement auditable).
- **Couverture** `C` : fraction des spans de la réponse disposant d'au moins une preuve d'ancrage.

États :

| État | Définition calculable |
|---|---|
| `grounded` | Le vérificateur s'est exécuté complètement **ET** `C ≥ τ_c` **ET** nombre de citations non résolues = 0 |
| `ungrounded` | Le vérificateur s'est exécuté complètement **ET** (`C < τ_c` **OU** ≥ 1 citation non résolue) |
| `unknown` | Le vérificateur n'a pas pu décider : exception interne, entrées malformées, bundle absent alors qu'une réponse existe, réponse vide soumise à l'évaluation d'ancrage, format de citation indécidable dans les conditions prévues |

`τ_s` et `τ_c` sont des **paramètres de configuration versionnés**, jamais codés en dur (cf. INV-5). Les valeurs par défaut initiales sont fixées et justifiées par RAG-005 après calibration en mode shadow (§8), avec valeur de repli conservative documentée (fail-closed : un doute tranche vers `ungrounded`/`unknown`, jamais vers `grounded`).

**Distinction clé** : `ungrounded` est une **preuve positive de non-ancrage** (on a cherché et on n'a pas trouvé, ou on a trouvé une citation fabriquée) ; `unknown` est une **absence de verdict** (on n'a pas pu chercher correctement). Aucun des deux ne peut être promu en `grounded`.

### 3.2 Provenance des citations

- Une citation n'existe que relativement au bundle `B` **tel qu'envoyé au LLM** : le `chunk_id` est attribué au moment de la construction du contexte du prompt, par le même composant qui formate `CONTEXTE` (jonction des passages, cf. `hardened.py` — contexte joint par séparateurs). Toute réattribution ultérieure est interdite (INV-2).
- Ce qui compte comme « preuve » : exclusivement le triplet `(span, chunk_id, s ≥ τ_s)` avec citation résolue, calculé par le vérificateur déterministe. Ni le score de similarité du retriever, ni une déclaration du LLM, ni une appréciation humaine a posteriori ne constituent une preuve d'ancrage au sens du contrat.
- Les `sources` exposées à l'appelant doivent être **cohérentes avec les citations résolues** : une source listée sans aucune citation résolue y pointant est un défaut de cohérence traqué par métrique (§6).

### 3.3 Politique de refus

| Verdict | Exposition autorisée |
|---|---|
| `grounded` | Réponse présentée comme ancrée : `context_used: true`, citations et sources exposées |
| `ungrounded` | **Refus par défaut** : sortie `blocked` avec raison explicite, réponse non livrée. Mode dégradé étiqueté possible uniquement en opt-in de configuration explicite : réponse livrée avec `grounding: "ungrounded"` + avertissement, **jamais** `context_used: true` |
| `unknown` | **Fail-closed, identique à `ungrounded`** : refus par défaut ; dégradation étiquetée `"unknown"` en opt-in uniquement ; jamais `context_used: true` |

`context_used: true` est désormais **un calcul** : il vaut `true` si et seulement si le verdict est `grounded`. Toute autre combinaison est un bug bloquant (oracle T5, §4).

### 3.4 Métriques

Compteurs étiquetés `{modèle, mode(shadow|enforce), état}` :

- taux `grounded` / `ungrounded` / `unknown` (et alerte si `unknown` dépasse un seuil d'exploitation fixé par RAG-005) ;
- couverture de citations `C` (distribution, pas seulement moyenne) ;
- nombre de citations non résolues par réponse ;
- taux de refus (`blocked`) et taux de dégradations étiquetées ;
- taux d'incohérence sources↔citations (§3.2).

Ces métriques sont une **exigence du contrat** : RAG-004B ne peut pas être déclaré terminé sans elles, car le passage shadow → enforce (§8) en dépend.

## 4. Machine d'états et oracles de test

### 4.1 Machine d'états

```
REÇU (réponse brute + bundle B)
  → T1 SEGMENTÉ (spans)
  → T2 CITATIONS_RÉSOLUES (citations résolues | non résolues)
  → T3 PREUVES_CALCULÉES (par span : preuves, scores)
  → T4 VERDICT (grounded | ungrounded)
  ↘ (toute défaillance de T1..T4) → UNKNOWN
  → T5 EXPOSÉ (blocked | dégradé_étiqueté | présenté_comme_ancré)
```

### 4.2 Oracles par transition

Chaque transition possède un oracle **décidable en test unitaire**, sans LLM, sans réseau (cohérent avec l'invariant de portabilité du dépôt).

| Transition | Oracle de test | Politique de refus associée |
|---|---|---|
| **T1** réponse → spans | Segmentation déterministe : même entrée ⇒ mêmes spans ; union des spans = réponse (aux séparateurs près) ; aucun span vide. Test : réponse connue à k phrases ⇒ exactement k spans attendus | Échec de segmentation ⇒ `unknown` ⇒ fail-closed |
| **T2** spans → citations résolues/non résolues | Pour chaque citation extraite : résolue ⟺ son `chunk_id` ∈ ids(B). Tests : citation dans la plage ⇒ résolue ; citation hors plage ⇒ non résolue ; B vide ⇒ toute citation non résolue ; réponse sans aucune citation ⇒ 0 citation résolue (le verdict se joue alors en T4 via la couverture) | ≥ 1 citation non résolue ⇒ `ungrounded` (fabrication de provenance) ; impossible d'extraire selon le format prévu ⇒ `unknown` |
| **T3** span + citation résolue → preuve | Le score `s` est déterministe et monotone : ajouter des tokens communs au chunk ne diminue pas `s`. Tests : span quasi-textuellement présent dans le chunk ⇒ `s ≥ τ_s` (preuve) ; span disjoint (aucun token commun significatif) ⇒ pas de preuve ; normalisation : même contenu modulo casse/ponctuation ⇒ même `s` | Span sans preuve ⇒ contribue à baisser `C` ; échec de calcul ⇒ `unknown` |
| **T4** preuves → verdict | Table de décision exhaustive (cf. §3.1) : toutes les combinaisons `{C vs τ_c} × {citations non résolues}` sont testées ; aucune combinaison ne produit `grounded` si (≥ 1 citation non résolue) ou (`C < τ_c`) ; le verdict est total (chaque entrée valide produit exactement un état) | `ungrounded` ⇒ refus par défaut ; toute indétermination ⇒ `unknown` ⇒ fail-closed |
| **T5** verdict → exposition | Invariant testé en non-régression directe de FAI-U-004 : `context_used == true` ⟺ verdict `grounded` ; verdict `ungrounded`/`unknown` ⇒ (`blocked` présent) OU (étiquette explicite `grounding` ≠ `"grounded"` ET `context_used == false`) ; le scénario du §2 (réponse décorrélée du contexte) ne produit plus `context_used: true` | Violation ⇒ test rouge bloquant la livraison de RAG-004B |

## 5. Interface retrieval → guardrail → réponse

Contrat de données entre étapes (niveau design, noms indicatifs ; RAG-005 fixe les types exacts) :

1. **Retrieval → prompt & guardrail** : le composant qui construit le contexte produit un **RetrievalBundle** `{chunks: [{chunk_id, text, source, score_retrieval}]}`. Contrainte d'identité (INV-2) : le bundle fourni au guardrail est **le même objet de données** que celui formaté dans le prompt — pas une reconstruction, pas un sous-ensemble, pas une re-recherche.
2. **Guardrail d'ancrage — entrée** : `(question, réponse_brute, RetrievalBundle, config{τ_s, τ_c, version_normalisation, politique_refus})`.
3. **Guardrail — sortie (GroundingVerdict)** : `{state: grounded|ungrounded|unknown, coverage, spans: [{span, cited_chunk_ids, resolved, s}], unresolved_citations: [...], reason}`.
4. **Réponse exposée** : `{answer, sources, grounding: <état>, context_used: <dérivé == (state==grounded)>, citations, blocked?}`. Le champ `context_used` reste présent pour compatibilité consommateurs mais change de sémantique : de *déclaré* à *calculé*. Ce changement de sémantique est **le point de migration** à documenter par RAG-004B (§8).
5. La garde d'entrée (anti-injection) et le court-circuit « aucun hit » existants sont **inchangés** : le présent contrat ne s'applique qu'au chemin où une réponse LLM existe.

## 6. Invariants et modèle de menace

### 6.1 Invariants

- **INV-1** : `context_used: true` n'est émis que si et seulement si le verdict est `grounded`. Aucun chemin de code ne peut court-circuiter cette dérivation.
- **INV-2** : le guardrail vérifie l'ancrage contre **le contexte exact envoyé au LLM** (même source de vérité, attribution des `chunk_id` au formatage du prompt).
- **INV-3** : le vérificateur V1 est **déterministe et sans dépendance externe** (stdlib pur), cohérent avec l'invariant de portabilité du dépôt ; pas d'appel réseau, pas de modèle auxiliaire dans le chemin de verdict.
- **INV-4** : toute défaillance du vérificateur produit `unknown`, et `unknown` est fail-closed (jamais présenté comme ancré).
- **INV-5** : `τ_s`, `τ_c`, la version de normalisation et la politique de refus sont de la **configuration versionnée et auditable**, jamais des constantes dispersées dans le code.

### 6.2 Menaces couvertes

- Hallucination présentée comme ancrée (réponse plausible mais sans preuve dans B) → `ungrounded` → refus.
- Citation fabriquée (renvoi vers un passage inexistant de B) → citation non résolue → `ungrounded`.
- Réponse confiante sur retrieval non vide mais non exploité → couverture insuffisante → `ungrounded`.
- Régression du type FAI-U-004 (paramètre de verdict fourni par l
