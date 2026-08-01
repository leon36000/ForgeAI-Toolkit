from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from forgeai.core.registre_completude import anomalies, charger


def entree(
    type_entree: str,
    payload: dict,
    seq: int = 1,
) -> dict:
    return {
        "seq": seq,
        "ts": "2025-01-01T00:00:00Z",
        "type": type_entree,
        "actor": "test",
        "payload": payload,
        "prev_hash": "genesis",
        "hash": f"hash-{seq}",
    }


def test_g1_schema_revue_scellee_sans_prompt_sha256() -> None:
    rapport = anomalies(
        [
            entree(
                "revue_scellee",
                {"story": "X", "vendors": ["vendor-a"]},
            )
        ]
    )

    assert len(rapport) == 1
    assert rapport[0]["type"] == "schema"
    assert rapport[0]["seq"] == 1
    assert rapport[0]["story"] == "X"
    assert "prompt_sha256" in rapport[0]["raison"]


def test_g2_story_complete_sans_attestation() -> None:
    rapport = anomalies([entree("story_complete", {"story": "X"})])

    attestations = [
        anomalie for anomalie in rapport if anomalie["type"] == "attestation"
    ]
    assert len(attestations) == 1
    assert attestations[0]["story"] == "X"
    assert attestations[0]["seq"] == 1


def test_g3_revue_scellee_separee_atteste_la_story() -> None:
    rapport = anomalies(
        [
            entree("story_complete", {"story": "X"}, seq=1),
            entree(
                "revue_scellee",
                {
                    "story": "X",
                    "prompt_sha256": "empreinte-prompt",
                    "vendors": ["vendor-a"],
                },
                seq=2,
            ),
        ]
    )

    assert not [
        anomalie for anomalie in rapport if anomalie["type"] == "attestation"
    ]


def test_g4_revue_en_ligne_atteste_la_story() -> None:
    rapport = anomalies(
        [
            entree(
                "story_complete",
                {"story": "X", "revue": "APPROVE 3/3"},
            )
        ]
    )

    assert not [
        anomalie for anomalie in rapport if anomalie["type"] == "attestation"
    ]


def test_g5_jointure_par_dossier_et_schema_story_exige() -> None:
    rapport = anomalies(
        [
            entree("story_complete", {"story": "X"}, seq=1),
            entree(
                "revue_scellee",
                {
                    "dossier": "reviews/X",
                    "prompt_sha256": "empreinte-prompt",
                    "vendors": ["vendor-a"],
                },
                seq=2,
            ),
        ]
    )

    attestations = [
        anomalie for anomalie in rapport if anomalie["type"] == "attestation"
    ]
    schemas = [anomalie for anomalie in rapport if anomalie["type"] == "schema"]

    assert not attestations
    assert len(schemas) == 1
    assert schemas[0]["seq"] == 2
    assert schemas[0]["story"] == "X"
    assert "story" in schemas[0]["raison"]


def test_g6_registre_reel_ne_depasse_pas_une_anomalie_attestation() -> None:
    racine = Path(__file__).resolve().parents[1]
    entrees = charger(racine / "Registres" / "mission.jsonl")
    rapport = anomalies(entrees)
    attestations = [
        anomalie for anomalie in rapport if anomalie["type"] == "attestation"
    ]

    assert len(attestations) <= 1


def test_g7_integrite_n_implique_pas_completude() -> None:
    registre_chaine = [
        {
            "seq": 1,
            "ts": "2025-01-01T00:00:00Z",
            "type": "story_complete",
            "actor": "test",
            "payload": {"story": "X"},
            "prev_hash": "genesis",
            "hash": "hash-valide-1",
        }
    ]

    rapport = anomalies(registre_chaine)

    assert registre_chaine[0]["prev_hash"] == "genesis"
    assert registre_chaine[0]["hash"] == "hash-valide-1"
    assert len(rapport) == 1
    assert rapport[0]["type"] == "attestation"
    assert rapport[0]["story"] == "X"


def test_g8_anomalies_ne_reecrit_jamais_le_registre() -> None:
    registre = [
        entree("story_complete", {"story": "X"}, seq=1),
        entree(
            "revue_scellee",
            {
                "dossier": "reviews/X",
                "prompt_sha256": "empreinte-prompt",
                "vendors": ["vendor-a"],
            },
            seq=2,
        ),
    ]
    avant = deepcopy(registre)

    rapport = anomalies(registre)

    assert rapport
    assert registre == avant
