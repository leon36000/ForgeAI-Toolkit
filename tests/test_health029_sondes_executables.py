"""HEALTH-029 — les sondes émises doivent être EXÉCUTABLES dans les images réellement livrées.

Défaut trouvé en DÉPLOYANT, pas en lisant : `docker inspect` rapportait `unhealthy` avec
`exec: "curl": executable file not found in $PATH`, alors que le service répondait parfaitement
depuis l'hôte. Deux causes indépendantes — la sonde visait le port HÔTE depuis l'INTÉRIEUR du
conteneur, et le binaire n'existait pas dans l'image.

Mesures qui fondent ces tests (exécutées sur les images épinglées du dépôt) :
  qdrant/qdrant  : ni curl, ni wget, ni nc — mais bash présent
  ollama/ollama  : ni curl — mais bash et la CLI `ollama` présents
"""

from __future__ import annotations

import json
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
DONNEES = RACINE / "src" / "forgeai" / "data"

# Binaires MESURÉS absents des images livrées par défaut. Une sonde qui les invoque ne peut
# jamais réussir : le conteneur reste `unhealthy` à vie.
BINAIRES_ABSENTS = ("curl", "wget", "nc")


def _services_livres():
    for nom in ("deploy-minimal.json", "deploy-hardened.json"):
        charge = json.loads((DONNEES / nom).read_text(encoding="utf-8"))
        for service in charge.get("services", []):
            yield nom, service


def test_g1_chaque_service_livre_declare_une_sonde():
    """CA1 — sans sonde déclarée, le service retombe sur le repli hérité, qui construit sa cible
    à partir du port HÔTE alors qu'elle s'exécute DANS le conteneur."""
    for fichier, service in _services_livres():
        assert service.get("probe_type"), (
            f"{fichier}: le service {service['name']!r} n'a pas de sonde déclarée — il retombera "
            "sur le repli hérité, dont la cible porte le port hôte"
        )


def test_g2_aucune_sonde_n_invoque_un_binaire_absent_des_images():
    """CA3 — LE détecteur du défaut mesuré. Une sonde `curl` sur qdrant/ollama est inexécutable."""
    for fichier, service in _services_livres():
        cible = service.get("probe_target") or []
        argv = " ".join(str(a) for a in cible)
        for binaire in BINAIRES_ABSENTS:
            assert not argv.split(" ")[0].endswith(binaire), (
                f"{fichier}: la sonde de {service['name']!r} invoque {binaire!r}, "
                f"MESURÉ absent de l'image {service.get('image','')[:40]}"
            )


def test_g3_la_sonde_vise_le_port_INTERNE_jamais_le_port_hote():
    """CA1/CA2 — la sonde s'exécute DANS le conteneur : elle doit viser `container_port`.

    Le port hôte est dérivé par décalage (+10000) dans le planificateur ; le trouver dans une
    sonde interne est la signature exacte du défaut d'origine.
    """
    for fichier, service in _services_livres():
        interne = int(service["container_port"])
        argv = " ".join(str(a) for a in (service.get("probe_target") or []))
        if not argv:
            continue
        hote_probable = interne + 10000
        assert str(hote_probable) not in argv, (
            f"{fichier}: la sonde de {service['name']!r} contient le port HÔTE {hote_probable} "
            f"alors qu'elle s'exécute dans le conteneur (port interne {interne})"
        )
        if "/dev/tcp" in argv:
            assert f"/{interne}" in argv, (
                f"{fichier}: sonde TCP de {service['name']!r} sans le port interne {interne}"
            )


def test_g4_les_variables_shell_sont_echappees_pour_compose():
    """CA3 — Docker Compose interpole `$VAR` AVANT que le conteneur ne voie la commande.

    Une sonde bash qui lit une variable doit doubler le `$`, sinon compose la remplace par du vide
    et la sonde compare une chaîne inexistante — elle échouerait silencieusement, ou pire,
    réussirait pour la mauvaise raison.
    """
    for fichier, service in _services_livres():
        argv = " ".join(str(a) for a in (service.get("probe_target") or []))
        if "$" not in argv:
            continue
        # Tout `$` doit faire partie d'un `$$` : on vérifie qu'aucun `$` n'est isolé.
        sans_doubles = argv.replace("$$", "")
        assert "$" not in sans_doubles, (
            f"{fichier}: la sonde de {service['name']!r} contient un `$` non doublé — compose "
            f"l'interpolerait avant le conteneur : {argv!r}"
        )


def test_g5_la_sonde_prouve_une_reponse_applicative_quand_c_est_possible():
    """CA1 — portée honnête de chaque sonde.

    Une sonde purement TCP prouve seulement qu'un port ACCEPTE les connexions : un processus figé
    qui n'répond plus la passerait. Quand un chemin de santé est déclaré, la sonde doit donc
    vérifier la RÉPONSE, pas seulement l'écoute.
    """
    for fichier, service in _services_livres():
        chemin = service.get("healthcheck_path")
        argv = " ".join(str(a) for a in (service.get("probe_target") or []))
        if not chemin or not argv or "/dev/tcp" not in argv:
            continue
        assert chemin in argv, (
            f"{fichier}: {service['name']!r} déclare le chemin de santé {chemin!r} mais sa sonde "
            "ne le vérifie pas — elle ne prouverait que l'ouverture du port"
        )


def test_g6_le_plan_serialise_une_sonde_declaree():
    """CA1 — détecteur d'un défaut réel : `probe_type` est une enum, et le champ n'avait jamais
    été peuplé de bout en bout. Le plan échouait donc à la sérialisation dès qu'une sonde était
    réellement déclarée — un mécanisme défini mais jamais exercé."""
    from forgeai.core.models import DeploymentPlan, ProbeType, RenderTarget, ServiceSpec

    plan = DeploymentPlan(
        plan_id="p-test", profile="minimal", target=RenderTarget.COMPOSE,
        services=[ServiceSpec(
            name="svc", image="img:1", host_port=18080, container_port=8080,
            probe_type=ProbeType.EXEC, probe_target=("bash", "-c", "true"),
        )],
        model="m", embed_model="e",
    )
    charge = json.loads(plan.to_json())
    assert charge["services"][0]["probe_type"] == ProbeType.EXEC.value, (
        "la sonde doit être sérialisée en chaîne, sinon `plan.json` n'est pas écrit du tout"
    )
