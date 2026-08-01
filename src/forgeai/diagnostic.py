"""OPS-031C — bundle de diagnostic reproductible et rédigé.

`portability.py` exporte le SETUP du stack-modèles pour migrer de machine ; ce module-ci répond à
une autre question : rassembler l'état d'exécution pour un DIAGNOSTIC. On en reprend les deux bonnes
idées — sérialisation canonique et empreinte couvrant tout le bundle — sans importer un module au
rôle différent.

Un bundle de support est destiné à QUITTER la machine : l'absence de secret n'est donc pas un
ornement mais la propriété centrale. La rédaction a lieu à la CONSTRUCTION, jamais à l'écriture —
rédiger « au moment d'écrire le fichier » laisserait fuir toute autre sortie (affichage, envoi).
"""

from __future__ import annotations

import hashlib
import json

from forgeai import __version__ as _forgeai_version
from forgeai.core.redaction import redact_mapping, redact_text

DIAGNOSTIC_VERSION = 1


def _canonique(charge: dict) -> str:
    """Sérialisation DÉTERMINISTE : même entrée → mêmes octets (clés triées, séparateurs compacts)."""
    return json.dumps(charge, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def empreinte(contenu: dict) -> str:
    """SHA256 du contenu canonique — couvre TOUT le bundle, donc toute altération est détectable."""
    return hashlib.sha256(_canonique(contenu).encode("utf-8")).hexdigest()


def collect_diagnostic(*, horodatage: str, etat, logs, version: str = _forgeai_version) -> dict:
    """Construit le bundle à partir de FOURNISSEURS injectés (testable sans sonde réelle).

    `horodatage` est INJECTÉ et jamais lu de l'horloge ici : sinon deux appels sur le même état
    produiraient des octets différents et « reproductible » ne voudrait rien dire — c'est aussi ce
    qui rend la propriété testable.
    """
    contenu = {
        "version": DIAGNOSTIC_VERSION,
        "forgeai_version": version,
        "horodatage": horodatage,
        "etat": redact_mapping(etat()),
        "logs": [redact_text(str(ligne)) for ligne in logs()],
    }
    return {"contenu": contenu, "empreinte": empreinte(contenu)}


def rendre(bundle: dict) -> str:
    """Rend le bundle en JSON canonique (octets reproductibles)."""
    return _canonique(bundle)
