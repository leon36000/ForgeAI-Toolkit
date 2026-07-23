"""FAI-0014 (#120) — le serveur web re-lit et re-parse des fichiers de données STATIQUES
du paquet à CHAQUE requête (catalogue.json 1.15 MiB sur /api/bricks + /api/spheres,
moteurs/modèles/locales ailleurs). Baseline : ~18-20 ms/req pour re-parser le catalogue.

Spécification : ces loaders de données immuables du paquet doivent être MÉMOÏSÉS (une lecture par
process, pas par requête). Preuve par identité : deux appels renvoient le MÊME objet caché.
RED avant correctif : chaque appel re-parse → objets distincts.
"""
import forgeai.web.server as server


def test_catalogue_entries_memoise():
    # le PARSE est mémoïsé (le tuple caché est identique d'un appel à l'autre)
    assert server._catalogue_entries_cached() is server._catalogue_entries_cached(), \
        "catalogue re-parsé à chaque appel (aucun cache) — coût O(1.15 MiB)/requête"
    # mais chaque appelant reçoit une COPIE : muter la liste rendue ne corrompt PAS le cache partagé
    a = server._catalogue_entries()
    b = server._catalogue_entries()
    assert a == b and a is not b
    n = len(a)
    a.append({"id": "MUTATION-TEST"})
    assert len(server._catalogue_entries()) == n, "mutation d'un appelant a corrompu le cache"


def test_read_data_text_memoise():
    a = server._read_data_text("moteurs-inference.json")
    b = server._read_data_text("moteurs-inference.json")
    assert a is b, "fichier de données re-lu à chaque appel (aucun cache)"


def test_read_data_text_distingue_les_fichiers():
    """Le cache reste correct par NOM de fichier (pas de collision entre ressources)."""
    a = server._read_data_text("moteurs-inference.json")
    b = server._read_data_text("modeles-locaux.json")
    assert a != b
