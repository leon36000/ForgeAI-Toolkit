"""Story E3c — preuve e2e RÉELLE : immudb branché comme ledger d'audit immuable.

Opt-in : ne s'exécute QUE si `FORGEAI_E2E=1` (skip par défaut, y compris CI — déploie un conteneur
immudb réel). Reproductible :

    FORGEAI_E2E=1 python3 -m pytest tests/test_immudb_e2e.py -s

Prouve, via le CODE RÉEL `forgeai.audit.immudb` (le chemin exact du wizard --rag-durci) :
  1. INSCRIPTION au ledger : un événement d'audit écrit renvoie transactionId + documentId ;
  2. IMMUABLE & HORODATÉ : la piste d'audit du document (révisions) porte transactionId/revision/ts
     côté serveur — inscription inviolable, relisible à l'identique ;
  3. APPEND-ONLY : une 2e écriture avance le transactionId ; l'audit du 1er document reste inchangé ;
  4. LOAD-BEARING : immudb arrêté → LedgerError (aucun repli), sans fuite des identifiants.

Preuve d'exécution RÉELLE journalisée au registre Registres/mission.jsonl (événement tdad_green E3c).
"""
from __future__ import annotations

import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from forgeai.audit.immudb import LedgerError, ensure_collection, history, open_session, record

pytestmark = pytest.mark.skipif(
    os.environ.get("FORGEAI_E2E") != "1",
    reason=(
        "preuve e2e Docker (immudb réel) — skip par défaut ; preuve d'exécution RÉELLE journalisée "
        "au registre Registres/mission.jsonl (tdad_green E3c) ; rejouable avec FORGEAI_E2E=1"
    ),
)

_USER, _PASSWORD = "immudb", "immudb"  # proof:allow — défaut PUBLIC immudb (dev), pas un secret


def _ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def test_immudb_ledger_audit_e2e(tmp_path: Path):
    subprocess.run(["docker", "rm", "-f", "e3c-immudb-test"], capture_output=True, text=True)
    try:
        subprocess.run([
            "docker", "run", "-d", "--name", "e3c-immudb-test", "-p", "18082:8080",
            "codenotary/immudb:1.11.1",
        ], check=True, capture_output=True, text=True, timeout=120)

        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and not _ok("http://127.0.0.1:18082/"):
            time.sleep(2)
        assert _ok("http://127.0.0.1:18082/"), "immudb (REST 8080) doit être en santé"

        base = "http://127.0.0.1:18082"
        token = open_session(base, _USER, _PASSWORD)
        ensure_collection(base, token, "forgeai_audit", [
            {"name": "event", "type": "STRING"}, {"name": "fact", "type": "STRING"}])

        # 1) inscription
        rec = record(base, token, "forgeai_audit",
                     {"event": "rag_durci_verified", "fact": "Vornak-9"})
        assert rec["transactionId"] and rec["documentId"]

        # 2) immuable & horodaté : la piste d'audit relit le document + porte tx/revision
        revs = history(base, token, "forgeai_audit", rec["documentId"])
        assert revs and revs[0]["document"]["fact"] == "Vornak-9"
        assert revs[0]["transactionId"] == rec["transactionId"]
        assert revs[0].get("revision") == "1"

        # 3) append-only : une 2e écriture avance le tx ; l'audit du 1er document est inchangé
        rec2 = record(base, token, "forgeai_audit",
                      {"event": "second", "fact": "autre"})
        assert int(rec2["transactionId"]) > int(rec["transactionId"])
        revs_again = history(base, token, "forgeai_audit", rec["documentId"])
        assert revs_again[0]["transactionId"] == rec["transactionId"], "audit du 1er doc immuable"

        # 4) load-bearing : immudb arrêté -> LedgerError, sans fuite d'identifiants
        subprocess.run(["docker", "stop", "e3c-immudb-test"], capture_output=True, text=True)
        with pytest.raises(LedgerError) as exc:
            record(base, token, "forgeai_audit", {"event": "x", "fact": "y"})
        # le token de session (identifiant distinct) ne doit pas fuiter ; l'invariant mot-de-passe
        # est couvert déterministiquement par test_immudb.py (le défaut immudb == nom du produit,
        # ambigu ici car il apparaît légitimement en préfixe « immudb POST … » du message).
        assert token not in str(exc.value)
    finally:
        subprocess.run(["docker", "rm", "-f", "e3c-immudb-test"], capture_output=True, text=True)
