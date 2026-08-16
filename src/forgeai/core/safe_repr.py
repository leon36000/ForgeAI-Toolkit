"""Représentation textuelle d'exception qui ne lève JAMAIS (source unique).

Round 27 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : rien n'empêche une exception
(personnalisée, ou standard encapsulant des données arbitraires) de définir un `__str__` qui lève
lui-même — vérifié empiriquement (cas légal en Python). Une simple f-string `f"...: {exc}"` dans
un handler censé être best-effort ferait alors échouer CE handler avant d'atteindre la logique de
récupération qui le suit (ex. persister l'état, marquer un déploiement terminé, tenter un
nettoyage). Source unique pour éviter que ce garde-fou dérive entre les modules qui en ont besoin
(web/server.py, hardware/detect.py) — même motif que core/redaction.py pour la rédaction.
"""
from __future__ import annotations


def str_exc_sur(exc: BaseException) -> str:
    """Représentation textuelle de `exc` qui NE LÈVE JAMAIS, même si `exc.__str__()` lui-même
    lève une exception.

    Round 28 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : `except Exception` (round 27)
    ne couvre pas un `__str__` qui lève un `BaseException` non-`Exception` (ex. `SystemExit`,
    `KeyboardInterrupt` — légal en Python, vérifié empiriquement), contredisant la garantie
    documentée « ne lève jamais ». `except BaseException` ici est délibéré et sûr : on ne capture
    pas l'exception d'ORIGINE (`exc` reste inchangée, toujours accessible à l'appelant si besoin),
    seulement un échec du FORMATAGE de son message — la capacité normale de Ctrl-C/SystemExit à
    interrompre le programme via l'exception ORIGINALE n'est pas affectée.
    """
    try:
        return str(exc)
    except BaseException:  # noqa: BLE001 — délibéré, voir docstring
        return f"{type(exc).__name__} (str() a levé lors du formatage du message d'erreur)"
