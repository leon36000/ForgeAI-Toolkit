# Revue tour 1 (OPT-001) : objection Gemini-3.1-Pro CONFIRMÉE et corrigée

## Objection (majeure) — JUSTE
« test_backends_et_hardware_sans_interblocage est un faux positif : le mock de run_checks n'appelle pas
full_report() sur le détecteur, donc _hardware_report() n'est jamais appelé depuis _available_backends,
le verrou n'est jamais repris, et le test réussirait à tort même avec un Lock simple. »

## Vérification EXPÉRIMENTALE (pas d'argumentation)
RLock temporairement remplacé par Lock (réintroduction volontaire du bug), puis exécution du test :
  -> le test PASSAIT (exit 0). Objection CONFIRMÉE : faux positif avéré.

## Correction
Le faux `run_checks` appelle désormais `detector.full_report()` — c'est CE chemin qui reprend le verrou.
Preuve BIDIRECTIONNELLE après correction :
  - avec `threading.Lock`  -> le test ÉCHOUE par timeout (le deadlock est bien détecté)
  - avec `threading.RLock` -> le test PASSE
Le test discrimine donc réellement la régression qu'il prétend garder.

Merci au reviewer : sans cette objection, un test rassurant mais inopérant serait entré sur main.
