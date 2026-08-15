<!-- Généré par scripts/governance/validate_sonar_suppressions.py --render ; ne pas éditer à la main. -->
# Suppressions Sonar et risques acceptés

Ce rapport inventorie les suppressions actives. Les échéances sont révisées tous les 180 jours.

La réduction de S2612 dans `openbao_flow.py` est désormais au site : une nouvelle occurrence ailleurs dans ce fichier n'est plus masquée.

| Règle | Portée | Site | Propriétaire | Risque accepté | Test compensatoire | Révision |
|---|---|---|---|---|---|---|
| S5332 | line | src/forgeai/cli.py:121 | équipe réseau ForgeAI | Un transport HTTP reste autorisé uniquement pour le service local ou LAN documenté. | La suppression concerne une décision de déploiement explicitement documentée à la ligne concernée. | 2027-02-11 |
| S2612 | line | src/forgeai/deploy/openbao_flow.py:102 | équipe secrets ForgeAI | La clé d'unseal peut être lisible par le conteneur non-root sur le même hôte de confiance. | Le comportement est prouvé par la preuve e2e S6 documentée ; aucune occurrence de test unitaire précise n'est déclarée ici. | 2027-02-11 |
| S2612 | line | src/forgeai/deploy/openbao_flow.py:104 | équipe secrets ForgeAI | La clé d'unseal peut être lisible par le conteneur non-root sur le même hôte de confiance. | Le comportement est prouvé par la preuve e2e S6 documentée ; aucune occurrence de test unitaire précise n'est déclarée ici. | 2027-02-11 |
| S2612 | line | src/forgeai/deploy/openbao_flow.py:109 | équipe secrets ForgeAI | La clé d'unseal peut être lisible par le conteneur non-root sur le même hôte de confiance. | Le comportement est prouvé par la preuve e2e S6 documentée ; aucune occurrence de test unitaire précise n'est déclarée ici. | 2027-02-11 |
| S2083 | line | src/forgeai/models/vault.py:252 | équipe secrets ForgeAI | L'analyse de traversée de chemin ne reconnaît pas la validation explicite du descripteur ouvert. | La garde O_NOFOLLOW et la validation du descripteur sont documentées directement au site. | 2027-02-11 |
| S2083 | line | src/forgeai/models/_locking.py:53 | équipe modèles ForgeAI | L'analyse ne distingue pas ce répertoire local contrôlé d'un chemin non fiable. | Le commentaire au site documente la cible locale et l'absence d'élévation de privilège. | 2027-02-11 |
| S2083 | line | src/forgeai/models/_locking.py:79 | équipe modèles ForgeAI | L'analyse de traversée de chemin ne reconnaît pas le temporaire créé dans le répertoire cible. | Le commentaire au site documente l'origine contrôlée du temporaire et la finalité du remplacement. | 2027-02-11 |
| python:S5443 | file | src/forgeai/renderers/k3s.py | équipe déploiement ForgeAI | Le faux positif peut masquer une occurrence S5443 dans ce fichier jusqu'à sa révision. | Non-réductible : Sonar vise le fichier car son analyse ne distingue pas ce littéral de contenu de manifeste d'un chemin temporaire local. | 2027-02-11 |
| python:S2068 | file | src/forgeai/cli.py | équipe plateforme ForgeAI | Le faux positif peut masquer une occurrence S2068 dans ce fichier jusqu'à sa révision. | Non-réductible : SonarCloud ne comprend pas la justification noqa déjà présente dans le code. | 2027-02-11 |
| python:S5332 | file | src/forgeai/network/bootstrap.py | équipe réseau ForgeAI | Le faux positif peut masquer une occurrence S5332 dans ce fichier jusqu'à sa révision. | Non-réductible : l'exception correspond à une compatibilité de bootstrap réseau privée documentée. | 2027-02-11 |
| pythonsecurity:S8707 | file | scripts/gate_docs.py | équipe gouvernance ForgeAI | Le faux positif peut masquer une occurrence S8707 dans ce fichier jusqu'à sa révision. | tests/test_doc032_gate_docs.py | 2027-02-11 |
| pythonsecurity:S8705 | file | scripts/gate_docs.py | équipe gouvernance ForgeAI | Le faux positif peut masquer une occurrence S8705 dans ce fichier jusqu'à sa révision. | tests/test_doc032_gate_docs.py | 2027-02-11 |
| pythonsecurity:S8707 | file | src/forgeai/core/registre.py | équipe audit ForgeAI | Le faux positif peut masquer une occurrence S8707 dans ce fichier jusqu'à sa révision. | tests/test_registre.py | 2027-02-11 |
| — | glob | **/__pycache__/** | équipe plateforme ForgeAI | Aucun cache Python généré n'est analysé. | Non-réductible : il s'agit de fichiers générés. | 2027-02-11 |
| — | glob | **/*.pyc | équipe plateforme ForgeAI | Aucun bytecode Python généré n'est analysé. | Non-réductible : il s'agit de fichiers générés. | 2027-02-11 |
| — | glob | src/forgeai/data/** | équipe plateforme ForgeAI | Les données statiques ne sont pas analysées comme du code. | Non-réductible : cette arborescence contient des données et non du code. | 2027-02-11 |
| — | glob | scripts/proof/** | équipe preuves ForgeAI | Les outils de preuve e2e ne sont pas inclus dans l'analyse produit. | Non-réductible : ces scripts sont eux-mêmes les preuves e2e exécutées manuellement. | 2027-02-11 |
| — | glob | **/__pycache__/** | équipe plateforme ForgeAI | Aucun cache Python généré n'est considéré comme test. | Non-réductible : il s'agit de fichiers générés. | 2027-02-11 |
| — | glob | **/*.pyc | équipe plateforme ForgeAI | Aucun bytecode Python généré n'est considéré comme test. | Non-réductible : il s'agit de fichiers générés. | 2027-02-11 |
| — | glob | src/forgeai/web/assets/** | équipe web ForgeAI | La couverture Sonar ne mesure pas les assets navigateur. | Non-réductible : la couverture Python ne peut pas mesurer les assets navigateur. | 2027-02-11 |
| — | glob | scripts/proof/** | équipe preuves ForgeAI | La couverture Sonar ne mesure pas les scripts de preuve e2e. | Non-réductible : les scripts constituent les preuves e2e exécutées. | 2027-02-11 |
| — | glob | scripts/check_metering_sites.py | équipe gouvernance ForgeAI | La couverture Sonar ne mesure pas le wrapper CLI sans logique métier. | tests/test_metering_guard.py | 2027-02-11 |
