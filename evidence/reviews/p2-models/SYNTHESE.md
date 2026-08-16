# Revue aveugle 3 vendors — sous-système `models/` P2 (B-08/B-09/B-10/B-11)

Rattrapage de gouvernance (PARTIE 7 §5) : les 4 stories modèles avaient été livrées avec
preuve tests+CI mais SANS la revue aveugle 3 vendors requise avant de quitter l'état
`UNVERIFIED`. Revue conduite le 2026-07-15 via `forge-model-bridge`, 3 vendors distincts
non-Anthropic, sur le code seul (aveugle).

## Périmètre revu (le plus à risque)
- `vault.py` — chiffrement de secrets écrit main (stdlib pur) — **priorité**
- `gateway.py` — enforcement de l'invariant « aucune brique ne pointe un fournisseur »
- `local.py` — téléchargement vérifié par empreinte (chaîne d'appro)

## Verdicts bruts
| Vendor | Modèle | Verdict |
|---|---|---|
| DeepSeek | DeepSeek-V4-Pro | REJECT (7 objections) |
| xAI | Grok-4.5 | REJECT (3 objections) — **confirme la construction crypto correcte** |
| Google | Gemini-3.1-Pro | REJECT (3 objections) |

## Tally déterministe (convergence ≥2 vendors, après vérification)
Chaque objection a été **vérifiée** (règle : aucun claim de modèle accepté sans preuve).

### RETENUS et corrigés (2)
1. **scrypt N=2^14 bas** (DeepSeek + Grok + Gemini, 3/3) → relevé à **2^16** (`vault.py`, ~67 Mo, <1 s, portable).
2. **TOCTOU / download non-atomique** (DeepSeek + Grok + Gemini, 3/3) → **`.part` + vérif + renommage atomique** (`local.py`). Le fichier à destination est toujours l'artefact vérifié.

### ASSUMÉ et documenté (1)
3. **Préférer un AEAD standard (AES-GCM/ChaCha20-Poly1305)** (Grok + Gemini, faible). L'invariant portabilité `dependencies=[]` interdit une lib AEAD (absente de la stdlib). La construction EtM(HMAC-CTR) est saine pour la menace « au repos » (salt+nonce aléatoires par scellement, tag constant-time vérifié AVANT déchiffrement) — **confirmé par Grok**. Compromis noté au docstring de `vault.py`; migration `cryptography` si la portabilité est relâchée. Débordement de compteur (Gemini) : compteur 8 octets → 2^69 octets, irréaliste pour une clé d'API.

### RÉFUTÉS (5, tous de DeepSeek — mauvaise lecture)
- « bit-flip non détecté » → FAUX : le tag EtM couvre `ct`, tout bit-flip échoue à la vérif.
- « déchiffrement avant vérif (oracle) » → FAUX : `unseal` lève sur `compare_digest` AVANT le XOR.
- « réutilisation de nonce/keystream » → FAUX : le salt aléatoire par scellement rend `enc_key` unique.
- « nonce modifiable sans détection » → FAUX : le tag couvre le nonce; pas recalculable sans `mac_key`.
- « fuite de clé dans les violations » (gateway) → FAUX : le message n'affiche pas la valeur de la clé.

## Disposition finale — **APPROUVÉ APRÈS CORRECTIFS** (signature Fable, orchestrateur/juge)
Les 3 REJECT convergeaient sur 2 durcissements légitimes (scrypt N, TOCTOU), **tous deux
appliqués**; le reste des objections est soit un compromis assumé et documenté, soit un
faux positif réfuté avec preuve. Suite complète verte après correctifs, no-stub OK.

Mapping stories : B-09 (`vault`/`routes`/`probe`), B-11 (`gateway`), B-08 (`local`),
B-10 (`strategy`, non contesté). **État : UNVERIFIED → VÉRIFIÉ (avec correctifs).**
