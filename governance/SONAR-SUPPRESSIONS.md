<!-- Généré par scripts/governance/validate_sonar_suppressions.py --render ; ne pas éditer à la main. -->
# Suppressions Sonar et risques acceptés

Ce rapport inventorie les suppressions actives. Les échéances sont révisées tous les 180 jours.

Les suppressions inline ciblées utilisent obligatoirement la syntaxe Sonar `# NOSONAR(Sxxxx)`. La forme `# NOSONAR Sxxxx` est une suppression nue : le texte après `NOSONAR` n'est pas une clé de règle. Source : https://community.sonarsource.com/t/python-issue-suppression-improvements-nosonar-and-new-rules/145017

La réduction de S2612 dans `openbao_flow.py` est désormais au site : une nouvelle occurrence ailleurs dans ce fichier n'est plus masquée.

La portée réelle des suppressions ciblées est vérifiée par le scan SonarCloud de la PR qui introduit une occurrence voisine : toute occurrence non couverte par un `NOSONAR(<règle>)` ciblé apparaît dans ce scan. La vérification ne relève donc pas du gate local ; sur la PR 499, `api/issues/search?pullRequest=499` a renvoyé deux issues et aucune sur `registre.py`, ce qui a confirmé que les deux `NOSONAR` nus retirés ne masquaient aucune issue.

| Règle | Portée | Site | Propriétaire | Risque accepté | Test compensatoire | Révision |
|---|---|---|---|---|---|---|
| S2068 | line | src/forgeai/cli.py:73 | équipe plateforme ForgeAI | La ligne peut masquer uniquement une occurrence S2068 sur cette constante publique. | La suppression est réduite à la constante concernée. | 2027-02-10 |
| S5332 | line | src/forgeai/cli.py:121 | équipe réseau ForgeAI | Un transport HTTP reste autorisé uniquement pour le service local ou LAN documenté. | La suppression concerne une décision de déploiement explicitement documentée à la ligne concernée. | 2027-02-10 |
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
| — | glob | **/__pycache__/** | équipe plateforme ForgeAI | Aucun cache Python généré n'est analysé. | Non-réductible : il s'agit de fichiers générés. | 2027-02-10 |
| — | glob | **/*.pyc | équipe plateforme ForgeAI | Aucun bytecode Python généré n'est analysé. | Non-réductible : il s'agit de fichiers générés. | 2027-02-10 |
| — | glob | src/forgeai/data/** | équipe plateforme ForgeAI | Les données statiques ne sont pas analysées comme du code. | Non-réductible : cette arborescence contient des données et non du code. | 2027-02-10 |
| — | glob | scripts/proof/** | équipe preuves ForgeAI | Les outils de preuve e2e ne sont pas inclus dans l'analyse produit. | Non-réductible : ces scripts sont eux-mêmes les preuves e2e exécutées manuellement. | 2027-02-10 |
| — | glob | **/__pycache__/** | équipe plateforme ForgeAI | Aucun cache Python généré n'est considéré comme test. | Non-réductible : il s'agit de fichiers générés. | 2027-02-10 |
| — | glob | **/*.pyc | équipe plateforme ForgeAI | Aucun bytecode Python généré n'est considéré comme test. | Non-réductible : il s'agit de fichiers générés. | 2027-02-10 |
| — | glob | src/forgeai/web/assets/** | équipe web ForgeAI | La couverture Sonar ne mesure pas les assets navigateur. | Non-réductible : la couverture Python ne peut pas mesurer les assets navigateur. | 2027-02-10 |
| — | glob | scripts/proof/** | équipe preuves ForgeAI | La couverture Sonar ne mesure pas les scripts de preuve e2e. | Non-réductible : les scripts constituent les preuves e2e exécutées. | 2027-02-10 |
| — | glob | scripts/check_metering_sites.py | équipe gouvernance ForgeAI | La couverture Sonar ne mesure pas le wrapper CLI sans logique métier. | tests/test_metering_guard.py | 2027-02-10 |
