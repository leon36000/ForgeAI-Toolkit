#!/usr/bin/env python3
"""R-ALL en masse — vérifie objectivement les URLs GitHub déjà présentes au catalogue.

Pour chaque entrée non vérifiée dont `source_url` pointe vers github.com : appelle
`gh api repos/<owner>/<repo>` (source objective, pas la mémoire d'un modèle). Si le dépôt
résout : marque `verified`, renseigne licence/popularité/maintenance depuis l'API, flag
PUBLIC-INSTALLABLE, `source_url` canonique (suit les renommages). Sinon : laissé non
vérifié et listé « à revoir » (candidat INTROUVABLE, à trancher sur dossier).

La description bilingue existante (issue du répertoire vérifié) est conservée — l'API ne
fait que CONFIRMER l'existence et compléter les métadonnées factuelles.

Usage : rall_verify_urls.py <catalogue.json> [--limit N]
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

SLUG_RE = re.compile(r"github\.com/([^/\s]+)/([^/\s#?]+)")


def gh_repo(owner: str, repo: str) -> dict | None:
    repo = repo.removesuffix(".git")
    proc = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}",
         "--jq", "{full_name,spdx:.license.spdx_id,stars:.stargazers_count,"
                 "archived,pushed:.pushed_at,desc:.description}"],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def main() -> None:
    path = Path(sys.argv[1])
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    data = json.loads(path.read_text(encoding="utf-8"))
    cibles = [e for e in data["entries"]
              if not e.get("verified") and "github.com/" in (e.get("source_url") or "")]
    if limit:
        cibles = cibles[:limit]

    today = date.today().isoformat()
    ok, arevoir = 0, []
    for e in cibles:
        m = SLUG_RE.search(e["source_url"])
        if not m:
            arevoir.append(e["name"])
            continue
        info = gh_repo(m.group(1), m.group(2))
        if info is None:
            arevoir.append(e["name"])
            continue
        e["verified"] = True
        e["verified_at"] = today
        e["verify_method"] = "gh-api repos/... (source objective)"
        e["source_url"] = f"https://github.com/{info['full_name']}"
        e["flag"] = "PUBLIC-INSTALLABLE"
        e["license"] = info.get("spdx") or "NOASSERTION"
        e["maintenance"] = "archived" if info.get("archived") else "active"
        stars = info.get("stars")
        if stars is not None:
            e["popularity"] = f"★{stars} (gh-api {today})"
        ok += 1

    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1)
    path.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    path.with_suffix(".sha256").write_text(digest + "\n", encoding="utf-8")

    reste = sum(1 for e in data["entries"] if not e.get("verified"))
    print(f"vérifiées gh-api : {ok}/{len(cibles)} | à revoir (404/slug) : {len(arevoir)}")
    if arevoir:
        print("  à revoir :", ", ".join(arevoir[:25]) + (" …" if len(arevoir) > 25 else ""))
    print(f"total non vérifiées restantes : {reste} | sha256 : {digest[:16]}…")


if __name__ == "__main__":
    main()
