"""Tests du registre append-only hash-chaîné."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import registre


def test_append_cree_une_chaine_valide(tmp_path):
    reg = tmp_path / "r.jsonl"
    first = registre.append(reg, "test", "pytest", {"n": 1})
    second = registre.append(reg, "test", "pytest", {"n": 2})

    assert first["seq"] == 1
    assert first["prev_hash"] == registre.GENESIS
    assert second["seq"] == 2
    assert second["prev_hash"] == first["hash"]
    assert registre.verify(reg) is None


def test_verify_detecte_une_alteration(tmp_path):
    reg = tmp_path / "r.jsonl"
    registre.append(reg, "test", "pytest", {"n": 1})
    registre.append(reg, "test", "pytest", {"n": 2})

    lines = reg.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["payload"] = {"n": 999}  # falsification sans recalcul du hash
    lines[0] = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    reg.write_text("\n".join(lines) + "\n", encoding="utf-8")

    erreur = registre.verify(reg)
    assert erreur is not None
    assert "seq 1" in erreur


def test_verify_detecte_une_entree_supprimee(tmp_path):
    reg = tmp_path / "r.jsonl"
    registre.append(reg, "test", "pytest", {"n": 1})
    registre.append(reg, "test", "pytest", {"n": 2})

    lines = reg.read_text(encoding="utf-8").splitlines()
    reg.write_text(lines[1] + "\n", encoding="utf-8")  # suppression de la genèse

    assert registre.verify(reg) is not None


def test_registre_vide_est_valide(tmp_path):
    assert registre.verify(tmp_path / "absent.jsonl") is None


def test_append_cree_le_repertoire_parent(tmp_path):
    # ex. ~/.forgeai/Registres/ inexistant au premier lancement (portabilité P3)
    reg = tmp_path / "nouveau" / "Registres" / "mission.jsonl"
    entry = registre.append(reg, "t", "a", {"n": 1})
    assert reg.exists()
    assert entry["seq"] == 1


def test_cli_append_puis_verify(tmp_path, monkeypatch, capsys):
    reg = tmp_path / "r.jsonl"
    monkeypatch.setattr(sys, "argv",
                        ["registre.py", "append", str(reg), "--type", "t",
                         "--actor", "a", "--payload-json", '{"k": 1}'])
    registre.main()
    assert json.loads(capsys.readouterr().out)["seq"] == 1

    monkeypatch.setattr(sys, "argv", ["registre.py", "verify", str(reg)])
    with pytest.raises(SystemExit) as exc:
        registre.main()
    assert exc.value.code == 0
    assert "chaîne intègre" in capsys.readouterr().out


def test_cli_verify_detecte_la_falsification(tmp_path, monkeypatch, capsys):
    reg = tmp_path / "r.jsonl"
    registre.append(reg, "t", "a", {"n": 1})
    lines = reg.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["actor"] = "usurpé"
    reg.write_text(json.dumps(entry, sort_keys=True, ensure_ascii=False,
                              separators=(",", ":")) + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["registre.py", "verify", str(reg)])
    with pytest.raises(SystemExit) as exc:
        registre.main()
    assert exc.value.code == 1
    assert "ECHEC" in capsys.readouterr().out


def test_ligne_json_invalide_rejetee(tmp_path):
    reg = tmp_path / "r.jsonl"
    reg.write_text("{pas du json\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="JSON invalide"):
        registre.verify(reg)


# ── TRUST-019B (FAI-U-019) — Tier 1 : HMAC-SHA256 à clé locale ────────────────
# ADR TRUST-019A §9 : key_id optionnel par entrée ; verify rétro-compatible avec les
# entrées Tier 0 (sans key_id -> SHA-256 nu) ; clé générée par commande EXPLICITE en 0600 ;
# sans racine disponible -> statut UNVERIFIED/échec explicite, jamais silencieusement OK.
import os
import stat as _stat

from forgeai.core import registre as core_registre


def test_init_key_cree_une_cle_locale_en_0600(tmp_path):
    """`init_key` (commande explicite, jamais implicite) crée la clé HMAC en 0600."""
    key_path = tmp_path / "hmac.key"
    key_id = core_registre.init_key(key_path)
    assert key_id and isinstance(key_id, str)
    assert key_path.exists()
    assert _stat.S_IMODE(os.stat(key_path).st_mode) == 0o600
    # idempotence : ne régénère pas silencieusement une clé existante
    assert core_registre.init_key(key_path) == key_id


def test_reecriture_integrale_detectee_avec_hmac(tmp_path):
    """Défaut FAI-U-019 : une réécriture TOTALE cohérente passait verify(). Avec une clé
    HMAC (Tier 1), l'attaquant sans la clé ne peut pas reforger la chaîne -> DÉTECTÉE."""
    key_path = tmp_path / "hmac.key"
    core_registre.init_key(key_path)
    reg = tmp_path / "r.jsonl"
    for i in range(3):
        core_registre.append(reg, "t", "auteur", {"i": i}, key_path=key_path)
    assert core_registre.verify(reg, key_path=key_path) is None  # chaîne saine

    # l'attaquant réécrit TOUT de façon cohérente, SANS la clé (Tier 0 seulement)
    entries = [json.loads(l) for l in reg.read_text(encoding="utf-8").splitlines()]
    reg.unlink()
    for e in entries:
        core_registre.append(reg, "t", "attaquant", {**e["payload"], "HOSTILE": True})
    erreur = core_registre.verify(reg, key_path=key_path)
    assert erreur, "réécriture intégrale NON détectée (régression FAI-U-019)"


def test_sans_cle_les_entrees_hmac_sont_unverified(tmp_path):
    """Racine indisponible : statut UNVERIFIED explicite, jamais un OK silencieux."""
    key_path = tmp_path / "hmac.key"
    core_registre.init_key(key_path)
    reg = tmp_path / "r.jsonl"
    core_registre.append(reg, "t", "auteur", {"i": 1}, key_path=key_path)
    statut = core_registre.verify_status(reg, key_path=None)
    assert statut == "UNVERIFIED", statut


def test_retrocompat_entrees_tier0_sans_key_id(tmp_path):
    """Entrées historiques (sans key_id) : vérification SHA-256 nue, aucune migration destructive."""
    reg = tmp_path / "r.jsonl"
    core_registre.append(reg, "t", "auteur", {"i": 1})          # Tier 0, pas de clé
    core_registre.append(reg, "t", "auteur", {"i": 2})
    assert core_registre.verify(reg) is None
    entries = [json.loads(l) for l in reg.read_text(encoding="utf-8").splitlines()]
    assert all("key_id" not in e for e in entries)
