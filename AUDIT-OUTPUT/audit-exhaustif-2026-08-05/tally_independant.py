"""Contre-implémentation INDÉPENDANTE du dépouillement (L0b).

Écrite à partir de la SPÉCIFICATION (invariants §2/§3 de la méthode), pas par copie
de scripts/revue.py. Sert uniquement à détecter une divergence : deux implémentations
qui concordent, ou c'est un constat. Anti-circularité — l'outil qui scelle l'audit ne
peut pas être son propre juge.
"""
import re

# table vendor reconstruite depuis la spécification, pas importée du dépôt audité
_V = [(r'^glm', 'zhipu'), (r'^deepseek', 'deepseek'), (r'^kimi', 'moonshot'),
      (r'^composer', 'xai'), (r'^grok', 'xai'), (r'^gemini', 'google'),
      (r'^qwen', 'alibaba'), (r'^gpt-', 'openai'), (r'^longcat', 'meituan'),
      (r'^mimo', 'xiaomi'), (r'^minimax', 'minimax'), (r'^nemotron', 'nvidia'),
      (r'^tencent|^hy3', 'tencent'), (r'^fable|^claude', 'anthropic')]
CONNUS = {v for _, v in _V}
BLOQUANTES = {'critique', 'eleve', 'elevee'}


def vendor(nom: str) -> str:
    n = (nom or '').lower()
    for pat, v in _V:
        if re.match(pat, n):
            return v
    return 'INCONNU'


def tally_ind(verdicts: list[dict]) -> dict:
    if len(verdicts) < 3:
        return {"result": "INVALIDE", "motif": "moins de 3 verdicts"}
    shas = {v.get("prompt_sha256") for v in verdicts}
    if len(shas) != 1 or None in shas:
        return {"result": "INVALIDE", "motif": "sceau prompt_sha256 non identique ou absent"}
    vends = [vendor(v.get("vendor") or v.get("reviewer_model", "")) for v in verdicts]
    if any(x == 'INCONNU' or x not in CONNUS for x in vends):
        return {"result": "INVALIDE", "motif": "vendor non reconnu (anti-Sybil)"}
    if len(set(vends)) < 3:
        return {"result": "INVALIDE", "motif": "moins de 3 vendors distincts"}
    bruts = [str(v.get("verdict", "")).upper() for v in verdicts]
    if any(b not in ("APPROVE", "REJECT") for b in bruts):
        return {"result": "INVALIDE", "motif": "verdict hors APPROVE/REJECT"}
    res = "APPROVE" if all(b == "APPROVE" for b in bruts) else "REJECT"
    objs = [o for v in verdicts for o in v.get("objections", [])]
    return {"result": res,
            "ratio": f"{bruts.count('APPROVE')}/{len(bruts)}",
            "vendors": sorted(set(vends)),
            "bloquantes": [o for o in objs
                           if str(o.get("severity", "")).lower() in BLOQUANTES]}
