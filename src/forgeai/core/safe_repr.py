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
    lève une exception."""
    try:
        return str(exc)
    except Exception:
        return f"{type(exc).__name__} (str() a levé lors du formatage du message d'erreur)"
