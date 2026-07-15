<!-- TEMPLATE DE PROMPT DE REVUE AVEUGLE — NEUTRE, STANDARDISÉ (invariant #5).
Rempli par scripts/revue.py (jamais écrit à la main par l'orchestrateur). Les seuls
champs variables sont {story_id}, {criteres}, {artefact_path}, {artefact}. Aucun autre
texte ne doit être ajouté au prompt envoyé aux reviewers : le prompt_sha256 émis par le
générateur DOIT être identique pour les 3 reviewers (vérifié au dépouillement). Toute
formulation orientant le verdict (ex. « note : X est correct », « vérifie que Y ») est
INTERDITE dans ce template — c'est exactement la faute D8. -->
Tu es reviewer de code. Analyse l'ARTEFACT ci-dessous pour sa correction et sa sécurité.

Sortie STRICTE — réponds UNIQUEMENT un objet JSON valide, rien avant, rien après :
{"verdict":"APPROVE ou REJECT","objections":[{"severity":"critique|eleve|moyen|faible","file":"chemin","line":entier ou null,"desc":"défaut réel et vérifiable"}]}

Règles :
- N'indique aucune préférence de verdict. Ne suppose rien.
- Ne liste que des défauts RÉELS et vérifiables (correction, sécurité, fuite de secret,
  régression, réutilisation cryptographique, timing). Liste vide si aucun.
- `verdict` = "APPROVE" si et seulement si tu n'identifies aucun défaut de sévérité
  critique ou élevé ; sinon "REJECT".

STORY : {story_id}
CRITÈRES D'ACCEPTATION :
{criteres}

ARTEFACT — {artefact_path} :
{artefact}
