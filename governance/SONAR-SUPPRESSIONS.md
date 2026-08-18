<!-- Généré par scripts/governance/validate_sonar_suppressions.py --render ; ne pas éditer à la main. -->
# Suppressions Sonar et risques acceptés

Ce rapport inventorie les suppressions actives. Les échéances sont révisées tous les 180 jours.

Les suppressions inline ciblées utilisent obligatoirement la syntaxe Sonar `# NOSONAR(Sxxxx)`. La forme `# NOSONAR Sxxxx` est une suppression nue : le texte après `NOSONAR` n'est pas une clé de règle. Source : https://community.sonarsource.com/t/python-issue-suppression-improvements-nosonar-and-new-rules/145017

La réduction de S2612 dans `openbao_flow.py` est désormais au site : une nouvelle occurrence ailleurs dans ce fichier n'est plus masquée.

La portée réelle des suppressions ciblées est vérifiée par le scan SonarCloud de la PR qui introduit une occurrence voisine : toute occurrence non couverte par un `NOSONAR(<règle>)` ciblé apparaît dans ce scan.

## Preuves mesurées

Les mutations temporaires ci-dessous ont été poussées, scannées, puis retirées.

### Critère 5 satisfait : portée réelle des suppressions S2612

Une occurrence os.chmod(chemin, 0o777) ajoutée temporairement dans openbao_flow.py, voisine des trois sites couverts par # NOSONAR(S2612) mais sans suppression, a été remontée. Les sites 102, 104 et 109 ne l'ont pas été. Cette mesure confirme qu'une suppression au site ne masque pas les occurrences voisines et que NOSONAR(S2612) est réellement pris en compte.

Résultats du scan :

```text
python:S2612 | src/forgeai/deploy/openbao_flow.py : 118
```

### e5, e6 et e7 non réductibles : NOSONAR ignoré par pythonsecurity

# NOSONAR(S8707) a été posé temporairement au site sur registre.py:101 et registre.py:141 après retrait de e7. Le scan a continué de remonter les deux issues. NOSONAR est donc ignoré par les règles pythonsecurity d'analyse de sécurité avancée ; le périmètre fichier est le seul disponible pour e5, e6 et e7.

Résultats du scan :

```text
pythonsecurity:S8707 | src/forgeai/core/registre.py : 101
pythonsecurity:S8707 | src/forgeai/core/registre.py : 141
```

### Rectification sur les NOSONAR nus retirés de registre.py

La conclusion antérieure selon laquelle les deux NOSONAR nus retirés de registre.py ne masquaient rien était fausse : le scan alors observé tournait avec e7 actif, qui masquait S8707 sur tout le fichier. Leur retrait reste correct parce que e7 couvre déjà ces lignes et qu'un NOSONAR au site y serait de toute façon sans effet, comme le démontre la mesure pythonsecurity.

| Règle | Portée | Site | Propriétaire | Risque accepté | Test compensatoire | Révision |
|---|---|---|---|---|---|---|
| S2068 | line | src/forgeai/cli.py:73 | équipe plateforme ForgeAI | La ligne peut masquer uniquement une occurrence S2068 sur cette constante publique. | La suppression porte sur une constante publique documentée, et non sur un comportement exécutable susceptible d'être couvert par un test. | 2027-02-10 |
| S5332 | line | src/forgeai/cli.py:121 | équipe réseau ForgeAI | Un transport HTTP reste autorisé uniquement pour le service local ou LAN documenté. | La suppression porte sur une chaîne de connexion locale documentée, et non sur un comportement exécutable distinct à tester. | 2027-02-10 |
| S2612 | line | src/forgeai/deploy/openbao_flow.py:102 | équipe secrets ForgeAI | La clé d'unseal peut être lisible par le conteneur non-root sur le même hôte de confiance. | Le comportement est prouvé par la preuve e2e S6 documentée. | 2027-02-10 |
| S2612 | line | src/forgeai/deploy/openbao_flow.py:104 | équipe secrets ForgeAI | La clé d'unseal peut être lisible par le conteneur non-root sur le même hôte de confiance. | Le comportement est prouvé par la preuve e2e S6 documentée. | 2027-02-10 |
| S2612 | line | src/forgeai/deploy/openbao_flow.py:109 | équipe secrets ForgeAI | La clé d'unseal peut être lisible par le conteneur non-root sur le même hôte de confiance. | Le comportement est prouvé par la preuve e2e S6 documentée. | 2027-02-10 |
| S2083 | line | src/forgeai/models/vault.py:252 | équipe secrets ForgeAI | L'analyse de traversée de chemin ne reconnaît pas la validation explicite du descripteur ouvert. | La garde O_NOFOLLOW et la validation du descripteur sont documentées directement au site. | 2027-02-10 |
| S2083 | line | src/forgeai/models/_locking.py:53 | équipe modèles ForgeAI | L'analyse ne distingue pas ce répertoire local contrôlé d'un chemin non fiable. | Le commentaire au site documente la cible locale et l'absence d'élévation de privilège. | 2027-02-10 |
| S2083 | line | src/forgeai/models/_locking.py:79 | équipe modèles ForgeAI | L'analyse de traversée de chemin ne reconnaît pas le temporaire créé dans le répertoire cible. | Le commentaire au site documente l'origine contrôlée du temporaire et la finalité du remplacement. | 2027-02-10 |
| S5332 | line | src/forgeai/network/bootstrap.py:69 | équipe réseau ForgeAI | Le faux positif peut masquer uniquement S5332 sur cette validation de bootstrap privée. | La suppression est réduite à la validation Headscale concernée. | 2027-02-10 |
| S5443 | line | src/forgeai/renderers/k3s.py:249 | équipe déploiement ForgeAI | Le faux positif peut masquer uniquement S5443 sur ce littéral de manifeste. | La suppression est réduite au littéral du montage emptyDir concerné. | 2027-02-10 |
| pythonsecurity:S8707 | file | scripts/gate_docs.py | équipe gouvernance ForgeAI | Le faux positif peut masquer une occurrence S8707 dans ce fichier jusqu'à sa révision. | tests/test_doc032_gate_docs.py | 2027-02-10 |
| pythonsecurity:S8705 | file | scripts/gate_docs.py | équipe gouvernance ForgeAI | Le faux positif peut masquer une occurrence S8705 dans ce fichier jusqu'à sa révision. | tests/test_doc032_gate_docs.py | 2027-02-10 |
| pythonsecurity:S8707 | file | src/forgeai/core/registre.py | équipe audit ForgeAI | Le faux positif peut masquer une occurrence S8707 dans ce fichier jusqu'à sa révision. | tests/test_registre.py | 2027-02-10 |
| pythonsecurity:S8707 | file | scripts/governance/evidence_dedup.py | équipe gouvernance ForgeAI | Le faux positif peut masquer une occurrence S8707 dans ce fichier jusqu'à sa révision. | tests/test_rc1011_dedup.py | 2027-02-10 |
| — | glob | **/__pycache__/** | équipe plateforme ForgeAI | Aucun cache Python généré n'est analysé. | Non-réductible : il s'agit de fichiers générés. | 2027-02-10 |
| — | glob | **/*.pyc | équipe plateforme ForgeAI | Aucun bytecode Python généré n'est analysé. | Non-réductible : il s'agit de fichiers générés. | 2027-02-10 |
| — | glob | src/forgeai/data/** | équipe plateforme ForgeAI | Les données statiques ne sont pas analysées comme du code. | Non-réductible : cette arborescence contient des données et non du code. | 2027-02-10 |
| — | glob | scripts/proof/** | équipe preuves ForgeAI | Les outils de preuve e2e ne sont pas inclus dans l'analyse produit. | Non-réductible : ces scripts sont eux-mêmes les preuves e2e exécutées manuellement. | 2027-02-10 |
| — | glob | **/__pycache__/** | équipe plateforme ForgeAI | Aucun cache Python généré n'est considéré comme test. | Non-réductible : il s'agit de fichiers générés. | 2027-02-10 |
| — | glob | **/*.pyc | équipe plateforme ForgeAI | Aucun bytecode Python généré n'est considéré comme test. | Non-réductible : il s'agit de fichiers générés. | 2027-02-10 |
| — | glob | src/forgeai/web/assets/** | équipe web ForgeAI | La couverture Sonar ne mesure pas les assets navigateur. | Non-réductible : la couverture Python ne peut pas mesurer les assets navigateur. | 2027-02-10 |
| — | glob | scripts/proof/** | équipe preuves ForgeAI | La couverture Sonar ne mesure pas les scripts de preuve e2e. | Non-réductible : les scripts constituent les preuves e2e exécutées. | 2027-02-10 |
| — | glob | scripts/check_metering_sites.py | équipe gouvernance ForgeAI | La couverture Sonar ne mesure pas le wrapper CLI sans logique métier. | tests/test_metering_guard.py | 2027-02-10 |
| pythonsecurity:S8705 | file | scripts/mypy_gate.py | équipe gouvernance ForgeAI | Le faux positif peut masquer une occurrence S8705 dans ce fichier jusqu'à sa révision. | tests/test_rc1019_mypy_gate.py | 2027-02-10 |
| pythonsecurity:S8707 | file | scripts/mypy_gate.py | équipe gouvernance ForgeAI | Le faux positif peut masquer une occurrence S8707 dans ce fichier jusqu'à sa révision. | tests/test_rc1019_mypy_gate.py | 2027-02-10 |
| pythonsecurity:S8705 | file | scripts/gate_git_ref.py | équipe gouvernance ForgeAI | Le faux positif peut masquer une occurrence S8705 dans ce fichier jusqu'à sa révision. | tests/test_gate_git_ref.py | 2027-02-10 |
| pythonsecurity:S8705 | file | scripts/branch_coverage_report.py | équipe gouvernance ForgeAI | Le faux positif peut masquer une occurrence S8705 dans ce fichier jusqu'à sa révision. | tests/test_branch_coverage_report.py | 2027-02-10 |
| pythonsecurity:S8707 | file | scripts/branch_coverage_report.py | équipe gouvernance ForgeAI | Le faux positif peut masquer une occurrence S8707 dans ce fichier jusqu'à sa révision. | tests/test_branch_coverage_report.py | 2027-02-10 |
| pythonsecurity:S8707 | file | scripts/verifier_artefact_distribue.py | équipe gouvernance ForgeAI | Le faux positif peut masquer une occurrence S8707 dans ce fichier jusqu'à sa révision. | tests/test_verifier_artefact_distribue.py | 2027-02-14 |
| pythonsecurity:S8707 | file | scripts/rapport_composants.py | équipe gouvernance ForgeAI | Le faux positif peut masquer une occurrence S8707 dans ce fichier jusqu'à sa révision. | tests/test_rapport_composants.py | 2027-02-14 |
