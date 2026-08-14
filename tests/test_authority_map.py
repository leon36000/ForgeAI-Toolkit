from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "governance" / "validate_authority.py"
_spec = importlib.util.spec_from_file_location(
    "validate_authority", REPO / "scripts" / "governance" / "validate_authority.py"
)
_validate_authority = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_validate_authority)
check = _validate_authority.check
cycles = _validate_authority.cycles
digest_of = _validate_authority.digest_of
render = _validate_authority.render


def _source(
    source_id: str,
    *,
    status: str = "active",
    scope: str = "governance_method",
    owner: str = "nathan",
    superseded_by: str | None = None,
    prevails_over: list[str] | None = None,
    positions: list[dict] | None = None,
    digest: dict | None = None,
    version: str = "1.0",
    retention: str = "in_force",
    cleanup_issue: int | None = None,
    resolution_issue: int | None = None,
    vision_log_seq: int | None = None,
    mission_seq: int | None = None,
    notes: str = "Source de test valide.",
) -> dict:
    return {
        "id": source_id,
        "title": f"Source {source_id}",
        "path": None,
        "anchor": None,
        "kind": "doctrine",
        "scope": scope,
        "version": version,
        "version_source": "declared_in_file",
        "status": status,
        "owner": owner,
        "superseded_by": superseded_by,
        "prevails_over": prevails_over or [],
        "positions": positions or [],
        "digest": digest
        or {
            "policy": "delegated",
            "value": None,
            "checked_at": "2026-08-14",
            "delegated_to": "test",
        },
        "retention": retention,
        "cleanup_issue": cleanup_issue,
        "resolution_issue": resolution_issue,
        "decision": {
            "vision_log_seq": vision_log_seq,
            "mission_seq": mission_seq,
            "ref": None,
        },
        "retention": retention,
        "cleanup_issue": cleanup_issue,
        "resolution_issue": resolution_issue,
        "notes": notes,
    }


def _authority(sources: list[dict]) -> dict:
    return {
        "_schema": "authority-v1",
        "vision_log": "vision-log.jsonl",
        "owners": {"nathan": {"role": "Responsable"}},
        "scopes": {
            "governance_method": {"singleton": False},
            "singleton_scope": {"singleton": True},
        },
        "topics": {
            "seat": {
                "question": "Qui décide ?",
                "vocabulaire": ["lead_a", "lead_b"],
            }
        },
        "sources": sources,
    }


def _check(authority: dict, tmp_path: Path, baseline: dict | None = None) -> tuple[bool, list[str]]:
    (tmp_path / "vision-log.jsonl").write_text(
        '{"seq": 1}\n{"seq": 2}\n',
        encoding="utf-8",
    )
    registres = tmp_path / "Registres"
    registres.mkdir(exist_ok=True)
    (registres / "mission.jsonl").write_text('{"seq": 1}\n', encoding="utf-8")
    return check(
        authority,
        baseline or {"conflits": []},
        tmp_path,
        render(authority),
    )


def test_id_duplique_rejete(tmp_path: Path) -> None:
    authority = _authority([_source("source-a"), _source("source-a")])

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("id dupliqué: source-a" in error for error in errors)


def test_cycle_de_succession_rejete(tmp_path: Path) -> None:
    authority = _authority(
        [
            _source("source-a", superseded_by="source-b"),
            _source("source-b", superseded_by="source-a"),
        ]
    )

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("cycle de succession" in error for error in errors)
    assert cycles({"source-a": ["source-b"], "source-b": ["source-a"]}) == [
        ["source-a", "source-b", "source-a"]
    ]


def test_cycle_de_precedence_rejete(tmp_path: Path) -> None:
    authority = _authority(
        [
            _source("source-a", prevails_over=["source-b"]),
            _source("source-b", prevails_over=["source-a"]),
        ]
    )

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("cycle de précédence" in error for error in errors)


def test_arete_croisee_succession_precedence_rejetee(tmp_path: Path) -> None:
    authority = _authority(
        [
            _source(
                "source-a",
                superseded_by="source-b",
                prevails_over=["source-b"],
            ),
            _source("source-b"),
        ]
    )

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("arête croisée succession/précédence" in error for error in errors)


def test_successeur_absent_pour_un_superseded_rejete(tmp_path: Path) -> None:
    authority = _authority(
        [
            _source(
                "source-a",
                status="superseded",
                superseded_by="source-absente",
                retention="pending_cleanup",
                cleanup_issue=12,
                vision_log_seq=1,
            )
        ]
    )

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("successeur inconnu: 'source-absente'" in error for error in errors)


def test_successeur_inconnu_rejete(tmp_path: Path) -> None:
    authority = _authority([_source("source-a", superseded_by="source-inconnue")])

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("successeur inconnu: 'source-inconnue'" in error for error in errors)


def test_empreinte_perimee_rejetee(tmp_path: Path) -> None:
    document = tmp_path / "document.md"
    document.write_text("version initiale\n", encoding="utf-8")
    digest = digest_of(document, "content_sha256", None)
    document.write_text("version modifiée\n", encoding="utf-8")
    source = _source(
        "source-a",
        digest={
            "policy": "content_sha256",
            "value": digest,
            "checked_at": "2026-08-14",
            "delegated_to": None,
        },
    )
    source["path"] = "document.md"
    authority = _authority([source])

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("empreinte périmée: document.md" in error for error in errors)


def test_empreinte_absente_sur_source_active_rejetee(tmp_path: Path) -> None:
    document = tmp_path / "document.md"
    document.write_text("contenu\n", encoding="utf-8")
    source = _source(
        "source-a",
        digest={
            "policy": "content_sha256",
            "value": None,
            "checked_at": "2026-08-14",
            "delegated_to": None,
        },
    )
    source["path"] = "document.md"
    authority = _authority([source])

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("valeur d'empreinte absente ou invalide" in error for error in errors)


def test_proprietaire_hors_owners_rejete(tmp_path: Path) -> None:
    authority = _authority([_source("source-a", owner="inconnu")])

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("propriétaire hors owners: 'inconnu'" in error for error in errors)


def test_version_absente_sur_source_active_rejetee(tmp_path: Path) -> None:
    authority = _authority([_source("source-a", version="")])

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("version absente sur source active ou conflictuelle" in error for error in errors)


def test_position_hors_vocabulaire_rejetee(tmp_path: Path) -> None:
    authority = _authority(
        [
            _source(
                "source-a",
                positions=[
                    {
                        "topic": "seat",
                        "position": "valeur_inconnue",
                        "locator": "source.md:1",
                    }
                ],
            )
        ]
    )

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("position hors vocabulaire" in error for error in errors)


def test_conflit_non_baseline_rejete(tmp_path: Path) -> None:
    authority = _authority(
        [
            _source(
                "source-a",
                positions=[{"topic": "seat", "position": "lead_a", "locator": "a.md:1"}],
            ),
            _source(
                "source-b",
                positions=[{"topic": "seat", "position": "lead_b", "locator": "b.md:1"}],
            ),
        ]
    )

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("conflit nouveau non baseliné" in error for error in errors)


def test_conflit_baseline_accepte(tmp_path: Path) -> None:
    authority = _authority(
        [
            _source(
                "source-a",
                positions=[{"topic": "seat", "position": "lead_a", "locator": "a.md:1"}],
            ),
            _source(
                "source-b",
                positions=[{"topic": "seat", "position": "lead_b", "locator": "b.md:1"}],
            ),
        ]
    )
    baseline = {
        "conflits": [
            {
                "kind": "topic_position",
                "sujet": "seat",
                "sources": ["source-a", "source-b"],
                "positions": ["lead_a", "lead_b"],
            }
        ]
    }

    ok, errors = _check(authority, tmp_path, baseline)

    assert ok
    assert errors == []


def test_conflit_baseline_perime_rejete(tmp_path: Path) -> None:
    authority = _authority([_source("source-a")])
    baseline = {
        "conflits": [
            {
                "kind": "topic_position",
                "sujet": "seat",
                "sources": ["source-a", "source-b"],
                "positions": ["lead_a", "lead_b"],
            }
        ]
    }

    ok, errors = _check(authority, tmp_path, baseline)

    assert not ok
    assert any("conflit baseliné périmé" in error for error in errors)


def test_singleton_de_portee_viole_rejete(tmp_path: Path) -> None:
    authority = _authority(
        [
            _source("source-a", scope="singleton_scope"),
            _source("source-b", scope="singleton_scope"),
        ]
    )

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("portée singleton violée: singleton_scope" in error for error in errors)


def test_section_ancree_absente_du_fichier_rejetee(tmp_path: Path) -> None:
    document = tmp_path / "document.md"
    document.write_text("# Section présente\n\nContenu\n", encoding="utf-8")
    source = _source(
        "source-a",
        digest={
            "policy": "section_sha256",
            "value": "a" * 64,
            "checked_at": "2026-08-14",
            "delegated_to": None,
        },
    )
    source["path"] = "document.md"
    source["anchor"] = "Section absente"
    authority = _authority([source])

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("section ancrée absente: 'Section absente'" in error for error in errors)


def test_digest_delegue_exige_delegated_to(tmp_path: Path) -> None:
    source = _source(
        "source-a",
        digest={
            "policy": "delegated",
            "value": None,
            "checked_at": "2026-08-14",
            "delegated_to": None,
        },
    )
    authority = _authority([source])

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("digest délégué exige delegated_to" in error for error in errors)


def test_carte_desynchronisee_rejetee(tmp_path: Path) -> None:
    authority = _authority([_source("source-a")])
    (tmp_path / "vision-log.jsonl").write_text('{"seq": 1}\n', encoding="utf-8")
    registres = tmp_path / "Registres"
    registres.mkdir()
    (registres / "mission.jsonl").write_text("", encoding="utf-8")

    ok, errors = check(authority, {"conflits": []}, tmp_path, "# Carte obsolète\n")

    assert not ok
    assert errors == ["• carte d'autorité désynchronisée"]


def test_rendu_est_idempotent(tmp_path: Path) -> None:
    authority = _authority([_source("source-a"), _source("source-b")])
    first = render(authority)
    copied = copy.deepcopy(authority)

    second = render(copied)
    ok, errors = _check(copied, tmp_path)

    assert first == second
    assert ok
    assert errors == []


def test_journal_de_vision_requis_pour_statut_non_actif(tmp_path: Path) -> None:
    authority = _authority(
        [
            _source(
                "source-a",
                status="archived",
                retention="historical_record",
            )
        ]
    )

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("journal de vision requis pour statut non actif" in error for error in errors)


def test_mission_seq_inexistant_rejete(tmp_path: Path) -> None:
    authority = _authority([_source("source-a", mission_seq=99)])

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("mission_seq inexistant: 99" in error for error in errors)


def test_marqueur_8bis_dans_les_notes_rejete(tmp_path: Path) -> None:
    marqueur_interdit = "TO" + "DO"
    authority = _authority([_source("source-a", notes=f"Annotation {marqueur_interdit} interdite.")])

    ok, errors = _check(authority, tmp_path)

    assert not ok
    assert any("marqueur interdit dans notes" in error for error in errors)


def test_inventaire_reel_du_depot_passe_le_gate() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    authority = json.loads(
        (repo_root / "governance" / "authority.json").read_text(encoding="utf-8")
    )
    baseline = json.loads(
        (repo_root / "governance" / "conflicts-baseline.json").read_text(encoding="utf-8")
    )
    map_text = (repo_root / "governance" / "AUTHORITY-MAP.md").read_text(encoding="utf-8")

    ok, errors = check(authority, baseline, repo_root, map_text)

    assert ok
    assert errors == []


def test_main_render_puis_check_sur_vrai_depot_reussit(monkeypatch, capsys) -> None:
    # Appel EN PROCESS (pas subprocess.run) : un subprocess séparé est invisible à
    # coverage.py, ce qui viderait ces tests de leur utilité pour le seuil de couverture
    # SonarCloud sur le code nouveau (constaté : 0 gain de couverture avec subprocess).
    monkeypatch.chdir(REPO)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--render"])
    rc = _validate_authority.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "PASS" in out

    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])
    rc2 = _validate_authority.main()
    out2 = capsys.readouterr().out
    assert rc2 == 0
    assert "PASS" in out2


def test_main_rejette_un_chemin_hors_du_depot(monkeypatch, capsys) -> None:
    monkeypatch.chdir(REPO)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--map", "../../../../etc/passwd"])
    rc = _validate_authority.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "hors du dépôt" in out


def test_main_erreur_json_invalide(tmp_path: Path, monkeypatch, capsys) -> None:
    (tmp_path / "authority.json").write_text("{invalide", encoding="utf-8")
    (tmp_path / "conflicts-baseline.json").write_text(
        '{"conflits": []}',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--repo-root",
            str(tmp_path),
            "--authority",
            "authority.json",
            "--baseline",
            "conflicts-baseline.json",
        ],
    )
    rc = _validate_authority.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "Expecting property name enclosed in double quotes" in out


def test_main_erreur_authority_json_pas_un_objet(tmp_path: Path, monkeypatch, capsys) -> None:
    (tmp_path / "authority.json").write_text("[]", encoding="utf-8")
    (tmp_path / "conflicts-baseline.json").write_text(
        '{"conflits": []}',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--repo-root",
            str(tmp_path),
            "--authority",
            "authority.json",
            "--baseline",
            "conflicts-baseline.json",
        ],
    )
    rc = _validate_authority.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "objet JSON attendu" in out
