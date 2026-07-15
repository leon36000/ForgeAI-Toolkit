#!/usr/bin/env python3
"""Pipeline de revue aveugle — génération de prompt NEUTRE + dépouillement DÉTERMINISTE.

Deux fonctions, toutes deux pures/déterministes (invariants #5 et #10 : « aucun LLM n'écrit
un score », « prompts sans verdict attendu ») :

  build_prompt(...)  → remplit CANON/revue-template.md avec l'artefact/critères et rend le
                       texte EXACT à envoyer aux reviewers + son sha256. Le prompt n'est
                       JAMAIS écrit à la main : identique pour les 3 reviewers (le sha256
                       partagé le prouve au dépouillement).

  tally(verdicts)    → dépouillement PAR SCRIPT. Exige ≥3 verdicts de ≥3 vendors DISTINCTS,
                       tous liés au MÊME prompt_sha256 ; APPROVE ssi tous APPROVE ; sinon
                       REJECT avec l'union des objections triées par sévérité. Aucun jugement
                       de modèle : fonction pure de règles binaires.

Usage :
  revue.py prompt --artefact <path> --story <id> [--criteres <fichier>] [--out <fichier>]
  revue.py tally <dossier_verdicts>          # lit *.verdict.json ; code retour 0 si APPROVE
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

_PLACEHOLDER = re.compile(r"\{(story_id|criteres|artefact_path|artefact)\}")

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "CANON" / "revue-template.md"

# model/alias → vendor. Deux reviewers du même vendor ne comptent QUE pour un (invariant #5 :
# Composer + Grok = xAI, jamais appariés).
_VENDOR = {
    "glm": "zhipu", "glm52": "zhipu", "glm-5.2": "zhipu",
    "deepseek": "deepseek", "deepseek-v4-pro": "deepseek",
    "kimi": "moonshot", "kimi-2.7": "moonshot",
    "composer": "xai", "composer-2.5": "xai", "grok": "xai", "grok-4.5": "xai",
    "gemini": "google", "gemini-3.1-pro": "google",
    "qwen": "alibaba", "qwen37max": "alibaba", "qwen3.7-max": "alibaba",
    "longcat": "meituan", "longcat-2.0": "meituan",
    "mimo": "xiaomi", "mimo-pro-v2": "xiaomi",
    "nemotron": "nvidia",
}
_SEVERITY_RANK = {"critique": 0, "eleve": 1, "moyen": 2, "faible": 3}
_BLOCKING = {"critique", "eleve"}
_KNOWN_VENDORS = set(_VENDOR.values())  # vendors reconnus (identité vérifiable)


def vendor_of(model_or_vendor: str) -> str:
    key = model_or_vendor.strip().lower()
    return _VENDOR.get(key, key)  # inconnu → tel quel (rejeté au dépouillement, cf. tally)


def build_prompt(story_id: str, criteres: str, artefact_path: str, artefact: str,
                 template_path: Path = TEMPLATE) -> tuple[str, str]:
    """Rend (prompt_exact, sha256). Le template est lu au canon ; aucun texte n'est ajouté."""
    tpl = template_path.read_text(encoding="utf-8")
    # On ne garde que le corps (après le commentaire HTML d'en-tête) pour le prompt envoyé.
    # Le marqueur est OBLIGATOIRE : sans lui, l'en-tête (instructions internes) fuiterait dans
    # le prompt envoyé aux reviewers → non-neutralité (revue aveugle Nemotron). On échoue fort.
    if "-->" not in tpl:
        raise ValueError(f"template {template_path} sans marqueur '-->' : en-tête non séparable")
    tpl = tpl.split("-->", 1)[1].lstrip("\n")
    values = {"story_id": story_id, "criteres": criteres.strip(),
              "artefact_path": artefact_path, "artefact": artefact}
    # Substitution EN UN SEUL PASSAGE (re.sub) : le texte substitué n'est JAMAIS re-scanné,
    # donc un champ contenant « {artefact} » ne peut pas injecter un autre champ. Corrige le
    # défaut d'injection croisée des .replace() chaînés (revue aveugle Qwen, criterion #4).
    prompt = _PLACEHOLDER.sub(lambda m: values[m.group(1)], tpl)
    return prompt, hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def tally(verdicts: list[dict]) -> dict:
    """Dépouillement déterministe. Retourne {result, reason, vendors, objections, prompt_sha256}."""
    if len(verdicts) < 3:
        return {"result": "INVALIDE", "reason": f"{len(verdicts)} verdict(s) < 3 requis"}
    shas = {v.get("prompt_sha256") for v in verdicts}
    if len(shas) != 1 or None in shas:
        return {"result": "INVALIDE",
                "reason": f"prompts non identiques (sha distincts : {sorted(s or 'MANQUANT' for s in shas)})"}
    vendors = [vendor_of(v.get("vendor") or v.get("reviewer_model", "")) for v in verdicts]
    # Anti-Sybil (revue aveugle Nemotron) : un vendor NON reconnu ne peut pas compter comme
    # « distinct » — sinon des chaînes bidon simuleraient la diversité de vendors exigée.
    inconnus = sorted(set(vendors) - _KNOWN_VENDORS)
    if inconnus:
        return {"result": "INVALIDE",
                "reason": f"vendor(s) inconnu(s), identité non vérifiable : {inconnus}"}
    distinct = set(vendors)
    if len(distinct) < 3:
        return {"result": "INVALIDE",
                "reason": f"{len(distinct)} vendor(s) distinct(s) < 3 (vus : {sorted(distinct)})"}
    raw = [str(v.get("verdict", "")).upper() for v in verdicts]
    if any(r not in ("APPROVE", "REJECT") for r in raw):
        return {"result": "INVALIDE", "reason": f"verdict hors APPROVE/REJECT : {raw}"}
    objections = [o for v in verdicts for o in v.get("objections", [])]
    objections.sort(key=lambda o: _SEVERITY_RANK.get(str(o.get("severity", "faible")).lower(), 9))
    result = "APPROVE" if all(r == "APPROVE" for r in raw) else "REJECT"
    return {"result": result, "reason": f"{raw.count('APPROVE')}/{len(raw)} APPROVE",
            "vendors": sorted(distinct), "prompt_sha256": shas.pop(),
            "objections": objections,
            "bloquantes": [o for o in objections
                           if str(o.get("severity", "")).lower() in _BLOCKING]}


def _cmd_prompt(args) -> int:
    artefact = Path(args.artefact).read_text(encoding="utf-8")
    criteres = Path(args.criteres).read_text(encoding="utf-8") if args.criteres else "(voir story)"
    prompt, sha = build_prompt(args.story, criteres, args.artefact, artefact)
    if args.out:
        Path(args.out).write_text(prompt, encoding="utf-8")
    else:
        print(prompt)
    print(f"\n# prompt_sha256={sha}", file=sys.stderr)
    return 0


def _cmd_tally(args) -> int:
    verdicts = [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(Path(args.dossier).glob("*.verdict.json"))]
    res = tally(verdicts)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res.get("result") == "APPROVE" else 1


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(prog="revue.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("prompt", help="génère le prompt de revue neutre + sha256")
    pp.add_argument("--artefact", required=True)
    pp.add_argument("--story", required=True)
    pp.add_argument("--criteres", default=None)
    pp.add_argument("--out", default=None)
    pp.set_defaults(func=_cmd_prompt)
    pt = sub.add_parser("tally", help="dépouille les *.verdict.json d'un dossier (déterministe)")
    pt.add_argument("dossier")
    pt.set_defaults(func=_cmd_tally)
    args = p.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
