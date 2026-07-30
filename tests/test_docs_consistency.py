"""Tests de cohérence documentation <-> code pour les claims GPU (CAP-033A).

CAP-033A vérifie que `CANON/ETAT-SYSTEME.md` — le seul document qui se définit lui-même comme
l'« état canonique des capacités réellement livrées et prouvées » — décrit fidèlement ce que
`forgeai gpu drivers` fait vraiment, et rien de plus. Ces tests échouent (ROUGE) tant que la
doc affirme un module ou une capacité d'exécution qui n'existe pas dans le code, et passent
(VERT) une fois la doc corrigée. Aucun changement de code n'est attendu : l'écart trouvé est
documentaire, le comportement réel est déjà correct et couvert par `tests/test_drivers.py`.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    path = ROOT / relative
    assert path.exists(), f"{relative} introuvable"
    return path.read_text(encoding="utf-8")


def test_etat_systeme_ne_reference_pas_de_module_gpu_inexistant():
    """CAP-033A — le cycle de vie des drivers GPU vit dans hardware/drivers.py, PAS dans un
    package gpu/ (qui n'existe pas dans src/forgeai/). ETAT-SYSTEME.md doit référencer le
    chemin réel, jamais un chemin fantôme."""
    assert not (ROOT / "src" / "forgeai" / "gpu").exists(), (
        "ce test suppose qu'aucun package src/forgeai/gpu/ n'existe — s'il est créé un jour, "
        "ce test et CANON/ETAT-SYSTEME.md doivent être révisés ensemble"
    )
    doc = _read("CANON/ETAT-SYSTEME.md")
    assert "**gpu/**" not in doc, (
        "CANON/ETAT-SYSTEME.md référence un sous-système 'gpu/' inexistant dans src/forgeai/ "
        "— le code des drivers GPU vit dans src/forgeai/hardware/drivers.py"
    )
    assert "hardware/drivers.py" in doc, (
        "CANON/ETAT-SYSTEME.md doit référencer le chemin réel du code des drivers GPU : "
        "src/forgeai/hardware/drivers.py"
    )


def test_gpu_drivers_install_ne_sexecute_jamais_sur_lhote():
    """CAP-033A (garde-fou anti-régression) — preuve directe, par lecture de la source, que
    `_gpu_drivers` (src/forgeai/cli.py, chemin réel de `forgeai gpu drivers --action
    install|update`) ne fait qu'imprimer et journaliser le plan (`install_argv` /
    `rollback_argv`) calculé par `plan_driver_op` : aucun appel runner/subprocess ne
    l'exécute. Ce test épingle un comportement déjà correct aujourd'hui (cf.
    test_cli_gpu_drivers_amd dans tests/test_drivers.py, qui ne vérifie que la sortie
    imprimée) — il doit rester vert avant et après le correctif documentaire."""
    cli_src = _read("src/forgeai/cli.py")
    start = cli_src.index("def _gpu_drivers")
    end = cli_src.index("\ndef _doctor")
    assert start < end
    body = cli_src[start:end]

    assert "plan_driver_op" in body, "_gpu_drivers doit calculer un plan via plan_driver_op"
    assert "plan.install_argv" in body, "le plan calculé doit être exposé (impression/payload)"
    assert "subprocess" not in body, (
        "_gpu_drivers ne doit JAMAIS invoquer subprocess directement pour exécuter le plan "
        "d'installation — seule l'impression/journalisation est attendue"
    )
    assert ".run(plan" not in body, (
        "_gpu_drivers ne doit JAMAIS exécuter plan.install_argv/rollback_argv via un runner "
        "— seule l'impression/journalisation est attendue (exécution réelle hors périmètre, "
        "en attente de CLI-036)"
    )


def test_etat_systeme_documente_labsence_dexecution_reelle():
    """CAP-033A — CANON/ETAT-SYSTEME.md classe « drivers GPU » COUVERTE dans Extensions et
    décrit `gpu` comme gérant « le cycle de vie » complet, sans jamais préciser que
    l'installation n'est PAS exécutée sur l'hôte : elle est seulement planifiée et affichée
    (exécution réelle en attente de CLI-036, cf. stories/HW-037.md « Écart résiduel »). Ce
    test échoue tant que la doc ne porte pas cette réserve explicite."""
    doc = _read("CANON/ETAT-SYSTEME.md")
    assert "CLI-036" in doc, (
        "CANON/ETAT-SYSTEME.md doit documenter explicitement que "
        "`forgeai gpu drivers --action install|update` ne fait qu'imprimer et journaliser un "
        "plan (install_argv/rollback_argv) : l'exécution réelle reste dépendante de CLI-036 "
        "(runner borné et annulable), cf. stories/HW-037.md"
    )
