"""Logique pure d'ancrage des registres ForgeAI.

Une ancre ne peut pas vivre dans l'arbre d'une PR : un attaquant qui soumet
une PR controle tout cet arbre et peut modifier, dans le meme commit, une
ancre versionnee avec la fraude. La reference faisant autorite est donc
l'etat deja merge, par exemple ``origin/main``. Ce module ne fait que la
logique de comparaison ; la resolution de cette reference est confiee a
l'appelant.
"""

from __future__ import annotations

import hmac

BASE_VERSION = 1


def prefixe_conserve(reference: list[dict], courant: list[dict]) -> str | None:
    """Verifie que le registre courant conserve integralement une reference.

    Args:
        reference: Entrees du registre de reference deja approuve.
        courant: Entrees actuellement observees pour le registre.

    Returns:
        ``None`` si ``courant`` prolonge exactement ``reference`` ; sinon un
        message francais decrivant la premiere divergence ou une troncature.
    """
    if len(courant) < len(reference):
        return (
            "troncature detectee : registre courant de longueur "
            f"{len(courant)}, reference de longueur {len(reference)}"
        )

    for rang, entree_reference in enumerate(reference):
        entree_courante = courant[rang]
        seq_attendu = (
            entree_reference.get("seq", "inconnu")
            if isinstance(entree_reference, dict)
            else "inconnu"
        )

        hash_reference = (
            entree_reference.get("hash")
            if isinstance(entree_reference, dict)
            else None
        )
        hash_courant = (
            entree_courante.get("hash")
            if isinstance(entree_courante, dict)
            else None
        )

        if not isinstance(hash_reference, str) or not isinstance(hash_courant, str):
            return (
                f"divergence au rang {rang}, seq attendu {seq_attendu} : "
                "hash absent ou invalide"
            )

        if not hmac.compare_digest(hash_courant, hash_reference):
            return (
                f"divergence au rang {rang}, seq attendu {seq_attendu} : "
                f"hash courant {hash_courant} different du hash de reference "
                f"{hash_reference}"
            )

    return None


def anomalies_seq(entrees: list[dict]) -> list[str]:
    """Controle la continuite, l'unicite et l'ordre strict des ``seq``.

    Ce controle attrape l'edition manuelle et la divergence d'un second
    ecrivain qui ne respecte pas le format. Il n'apporte pas d'anti-rollback :
    tronquer un registre puis y re-ajouter des entrees laisse des ``seq``
    contigus.

    Args:
        entrees: Entrees deja chargees du registre, dans leur ordre JSONL.

    Returns:
        Liste des messages d'anomalie ; une liste vide si les ``seq`` vont de
        1 a ``len(entrees)`` avec une progression de un.
    """
    resultat: list[str] = []

    for rang, entree in enumerate(entrees, start=1):
        if not isinstance(entree, dict) or "seq" not in entree:
            resultat.append(f"seq absente a l'entree de rang {rang}")
            continue

        seq = entree["seq"]
        if not isinstance(seq, int) or isinstance(seq, bool):
            resultat.append(
                f"seq non entier a l'entree de rang {rang} : valeur {seq!r}"
            )
            continue

        if seq != rang:
            details: list[str] = []
            if seq < rang:
                details.append("doublon ou ordre non strictement croissant")
            elif seq > rang:
                details.append("progression superieure a +1")
            detail = f" ({', '.join(details)})" if details else ""
            resultat.append(
                f"seq incoherente a l'entree de rang {rang} : "
                f"attendue {rang}, obtenue {seq}{detail}"
            )

    return resultat


def checkpoint_de(entrees: list[dict], registre: str) -> dict:
    """Construit le payload d'ancrage du dernier etat d'un registre.

    Args:
        entrees: Entrees deja chargees du registre a ancrer.
        registre: Nom stable du registre ancre.

    Returns:
        Le payload contenant le registre, le ``seq`` et le hash final, ainsi
        que le nombre total d'entrees.

    Raises:
        ValueError: Si aucune entree ne peut etre ancree.
    """
    if not entrees:
        raise ValueError(
            "impossible de creer un checkpoint sur un registre vide : "
            "un ancrage-de-rien est interdit"
        )

    derniere = entrees[-1]
    return {
        "registre": registre,
        "seq": derniere["seq"],
        "hash_ancre": derniere["hash"],
        "entrees": len(entrees),
    }


def verifier_ancres(ancres: list[dict], registres: dict[str, list[dict]]) -> list[str]:
    """Verifie que chaque ancre est encore presente dans son registre.

    Args:
        ancres: Payloads d'ancrage produits par :func:`checkpoint_de`.
        registres: Mapping des noms de registres vers leurs entrees actuelles.

    Returns:
        Liste des anomalies detectees, notamment pour tout registre ancre mais
        absent du mapping. Une liste vide signifie que toutes les ancres sont
        conservees.
    """
    resultat: list[str] = []

    for rang_ancre, ancre in enumerate(ancres, start=1):
        if not isinstance(ancre, dict):
            resultat.append(
                f"ancre malformee au rang {rang_ancre} : payload non dictionnaire"
            )
            continue

        champs_manquants = [
            champ
            for champ in ("registre", "seq", "hash_ancre", "entrees")
            if champ not in ancre
        ]
        if champs_manquants:
            resultat.append(
                f"ancre malformee au rang {rang_ancre} : champs manquants "
                f"{', '.join(champs_manquants)}"
            )
            continue

        registre = ancre["registre"]
        seq = ancre["seq"]
        hash_ancre = ancre["hash_ancre"]
        nombre_entrees = ancre["entrees"]

        erreurs_type: list[str] = []
        if not isinstance(registre, str) or not registre:
            erreurs_type.append("registre doit etre une chaine non vide")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
            erreurs_type.append("seq doit etre un entier strictement positif")
        if not isinstance(hash_ancre, str):
            erreurs_type.append("hash_ancre doit etre une chaine")
        if (
            not isinstance(nombre_entrees, int)
            or isinstance(nombre_entrees, bool)
            or nombre_entrees < 1
        ):
            erreurs_type.append("entrees doit etre un entier strictement positif")

        if erreurs_type:
            resultat.append(
                f"ancre malformee au rang {rang_ancre} : "
                + "; ".join(erreurs_type)
            )
            continue

        if registre not in registres:
            resultat.append(f"registre ancre absent : {registre!r}")
            continue

        entrees = registres[registre]
        if not isinstance(entrees, list):
            resultat.append(
                f"registre ancre invalide : {registre!r} ne contient pas une liste d'entrees"
            )
            continue

        if len(entrees) < nombre_entrees:
            resultat.append(
                f"registre ancre incomplet : {registre!r} contient {len(entrees)} "
                f"entrees, ancre exige {nombre_entrees}"
            )

        if seq > len(entrees):
            resultat.append(
                f"registre ancre incomplet : {registre!r} ne contient pas "
                f"le rang seq {seq} (longueur {len(entrees)})"
            )
            continue

        entree = entrees[seq - 1]
        hash_courant = entree.get("hash") if isinstance(entree, dict) else None
        if not isinstance(hash_courant, str):
            resultat.append(
                f"registre ancre invalide : {registre!r}, rang seq {seq}, "
                "hash absent ou invalide"
            )
            continue

        if not hmac.compare_digest(hash_courant, hash_ancre):
            resultat.append(
                f"ancre invalide pour {registre!r}, seq {seq} : "
                f"hash attendu {hash_ancre}, hash observe {hash_courant}"
            )

    return resultat


def _identite_de(valeur: object) -> tuple[str, int, str, str] | None:
    """Retourne la cle immuable d'une identite de baseline valide."""
    if not isinstance(valeur, dict):
        return None

    fichier = valeur.get("fichier")
    seq = valeur.get("seq")
    type_entree = valeur.get("type")
    champ = valeur.get("champ")

    if (
        not isinstance(fichier, str)
        or not isinstance(seq, int)
        or isinstance(seq, bool)
        or not isinstance(type_entree, str)
        or not isinstance(champ, str)
    ):
        return None

    return (fichier, seq, type_entree, champ)


def anomalies_base(
    base: dict,
    reference_base: dict | None,
    anomalies_reelles: list[dict],
) -> list[str]:
    """Valide une baseline de completude contre ses bornes et les mesures reelles.

    Args:
        base: Baseline candidate contenant ``identites`` et ``bornes``.
        reference_base: Baseline deja mergee, ou ``None`` pour une nouvelle base.
        anomalies_reelles: Anomalies actuellement mesurees dans les registres.

    Returns:
        Liste des refus : identites hors borne, ajouts non autorises par rapport
        a la reference, et identites devenues perimees.
    """
    resultat: list[str] = []

    identites_brutes = base.get("identites")
    bornes = base.get("bornes")
    if not isinstance(identites_brutes, list):
        resultat.append("base invalide : identites doit etre une liste")
        identites_brutes = []
    if not isinstance(bornes, dict):
        resultat.append("base invalide : bornes doit etre un dictionnaire")
        bornes = {}

    identites: list[tuple[str, int, str, str]] = []
    for rang, identite_brute in enumerate(identites_brutes, start=1):
        identite = _identite_de(identite_brute)
        if identite is None:
            resultat.append(
                f"base invalide : identite au rang {rang} sans fichier, seq, type et champ valides"
            )
        else:
            identites.append(identite)

    identites_reference: set[tuple[str, int, str, str]] = set()
    if reference_base is not None:
        if not isinstance(reference_base, dict):
            resultat.append("reference_base invalide : dictionnaire attendu")
        else:
            reference_identites = reference_base.get("identites")
            if not isinstance(reference_identites, list):
                resultat.append(
                    "reference_base invalide : identites doit etre une liste"
                )
            else:
                for rang, identite_brute in enumerate(reference_identites, start=1):
                    identite = _identite_de(identite_brute)
                    if identite is None:
                        resultat.append(
                            "reference_base invalide : identite au rang "
                            f"{rang} sans fichier, seq, type et champ valides"
                        )
                    else:
                        identites_reference.add(identite)

    identites_reelles: set[tuple[str, int, str, str]] = set()
    for anomalie in anomalies_reelles:
        identite = _identite_de(anomalie)
        if identite is not None:
            identites_reelles.add(identite)

    for fichier, seq, type_entree, champ in identites:
        borne = bornes.get(fichier)
        seq_max: int | None = None
        if not isinstance(borne, dict):
            resultat.append(
                f"borne absente ou invalide pour {fichier!r} : "
                "ne peut pas valider l'identite baselined"
            )
        else:
            valeur_seq_max = borne.get("seq_max")
            hash_borne = borne.get("hash")
            if (
                not isinstance(valeur_seq_max, int)
                or isinstance(valeur_seq_max, bool)
                or not isinstance(hash_borne, str)
            ):
                resultat.append(
                    f"borne invalide pour {fichier!r} : seq_max entier et hash chaine requis"
                )
            else:
                seq_max = valeur_seq_max

        if seq_max is not None and seq > seq_max:
            resultat.append(
                f"hors borne : ne peut pas etre baselinee : "
                f"fichier {fichier!r}, seq {seq}, seq_max {seq_max}, "
                f"type {type_entree!r}, champ {champ!r}"
            )

        if reference_base is not None and (fichier, seq, type_entree, champ) not in identites_reference:
            resultat.append(
                f"base non croissante : identite ajoutee sans autorisation : "
                f"fichier {fichier!r}, seq {seq}, type {type_entree!r}, "
                f"champ {champ!r}"
            )

        if (fichier, seq, type_entree, champ) not in identites_reelles:
            resultat.append(
                f"identite perimee : fichier {fichier!r}, seq {seq}, "
                f"type {type_entree!r}, champ {champ!r} ne correspond a "
                "aucune anomalie reelle"
            )

    return resultat


def anomalies_ancrage(
    reference: dict[str, list[dict]], courant: dict[str, list[dict]]
) -> list[str]:
    """Detecte les suppressions et divergences des registres ancrés.

    Args:
        reference: Mapping des registres tels qu'ils existent dans l'etat deja
            merge.
        courant: Mapping des registres observes dans l'arbre controle.

    Returns:
        Liste des anomalies detectees ; une liste vide signifie que tous les
        registres de reference sont conserves et que les nouveaux registres
        sont acceptes.

    Cette fonction itere sur l'union des cles des deux mappings, jamais sur un
    seul des deux. Iterer seulement sur ``courant`` rendrait une suppression de
    registre invisible : le fichier absent ne serait simplement plus enumere.
    Iterer seulement sur les preuves d'ancrage laisserait un registre neuf non
    protege, et un ensemble de preuves vide produirait zero iteration donc un
    succes silencieux. Un registre nouveau est legitimement accepte ; sans
    cette regle, toute PR creant son propre registre echouerait a son propre
    gate.
    """
    resultat: list[str] = []

    for registre in sorted(set(reference) | set(courant)):
        present_reference = registre in reference
        present_courant = registre in courant

        entrees_reference = reference.get(registre)
        entrees_courant = courant.get(registre)

        if present_reference and not isinstance(entrees_reference, list):
            resultat.append(
                f"{registre} : valeur de reference invalide : "
                "une liste d'entrees est requise"
            )

        if present_courant and not isinstance(entrees_courant, list):
            resultat.append(
                f"{registre} : valeur courante invalide : "
                "une liste d'entrees est requise"
            )

        if present_reference and present_courant:
            if isinstance(entrees_reference, list) and isinstance(
                entrees_courant, list
            ):
                anomalie = prefixe_conserve(entrees_reference, entrees_courant)
                if anomalie is not None:
                    resultat.append(f"{registre} : {anomalie}")
            continue

        if present_reference and not present_courant:
            if isinstance(entrees_reference, list):
                resultat.append(
                    f"{registre} : registre supprime, "
                    f"{len(entrees_reference)} entrees perdues"
                )
            else:
                resultat.append(
                    f"{registre} : registre supprime, "
                    "nombre d'entrees perdues inconnu"
                )

    return resultat
