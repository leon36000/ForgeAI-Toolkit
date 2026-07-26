# Revue tour 1 (OPT-002) : objection Qwen3.6-40B CONFIRMÉE et corrigée
Objection (mineure) : « la 3e sonde modifiée (_summary_payload / cluster_status) n'a pas de test dédié
vérifiant l'utilisation du runner borné, contrairement aux deux autres ».
=> JUSTE : 2 des 3 sondes étaient testées. Un correctif partiellement testé.
Correction : ajout de `test_cluster_status_utilise_un_runner_borne`.
Preuve BIDIRECTIONNELLE : sans la borne -> le test ÉCHOUE ; avec la borne -> il PASSE.
(Au passage, ma 1re version du test utilisait un stack_id inexistant « dev-agentique » et échouait des
DEUX côtés — donc ne discriminait rien ; corrigé en « agentique », un id réel.)
