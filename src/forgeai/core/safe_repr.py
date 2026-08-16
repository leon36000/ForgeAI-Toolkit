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
    """Représentation textuelle de `exc`, robuste si `exc.__str__()` lève une `Exception`.

    Historique délibéré (#452) — deux rounds de revue scellée en tension directe, résolus en
    faveur de la sécurité signal plutôt que d'une couverture totale :

    - Round 27 : `except Exception` (ci-dessous) ne couvrait pas un `__str__` qui lève un
      `BaseException` non-`Exception` (`SystemExit`, `KeyboardInterrupt` — légal en Python,
      vérifié empiriquement). Corrigé round 28 en `except BaseException`.
    - Round 30 : `except BaseException` capture aussi un `KeyboardInterrupt`/`SystemExit`
      *asynchrone* qui arrive PENDANT l'appel à `str(exc)` sans rapport avec `exc.__str__()`
      elle-même (livraison de signal non déterministe — Python ne peut PAS distinguer "levée
      par le code de `__str__`" de "arrivée de l'extérieur pendant que ce code tournait"). Une
      interruption Ctrl-C légitime au mauvais moment serait donc avalée silencieusement.

    Revenu à `except Exception` : c'est le compromis retenu délibérément, aligné sur la
    convention de la stdlib (`traceback.format_exception_only` et consorts ne capturent pas non
    plus `BaseException`) — CPython exclut spécifiquement `KeyboardInterrupt`/`SystemExit` de la
    hiérarchie `Exception` pour que ce genre de garde-fou reste signal-safe. Risque résiduel
    accepté, étroit et documenté : un `__str__` personnalisé qui lève explicitement
    `SystemExit`/`KeyboardInterrupt` (plutôt qu'une `Exception` normale) fera encore échouer
    cette fonction — un cas pathologique bien plus rare et bien moins dommageable qu'avaler un
    Ctrl-C réel.
    """
    try:
        return str(exc)
    except Exception:
        return f"{type(exc).__name__} (str() a levé lors du formatage du message d'erreur)"
