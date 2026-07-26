# K8S-023 — journal de la revue scellée

**APPROVE 3/3, zéro objection** à tous les niveaux. Vendors distincts `google / kimi-k2.6 / xai`,
sceau commun `prompt_sha256 = 23dafab553ba…`.

## SWAP CIV — appliqué DOUBLEMENT
Deux vendors ont codé ce package : **MiniMax-M3** (fonction `_network_policies`) puis
**DeepSeek-V4-Flash** (4e famille de politiques, après plusieurs sorties vides de MiniMax et Kimi).
Les DEUX sortent donc du trio de revue — DeepSeek-V4-Pro, reviewer habituel, est exclu parce que
son vendor a codé. Trio retenu : Gemini-3.1-Pro, Grok-4.5, et un troisième à réassigner.

## Route instable journalisée
`Qwen3.8-Max`, pressenti comme troisième, a rendu **HTTP 408 Request Timeout**. Réassigné via le
pool vers **Kimi-K2.6** (Moonshot n'ayant pas codé ce package). Le sceau est resté identique : le
pack n'a pas changé entre les deux appels, les trois verdicts portent bien `23dafab553ba`.

## Ce que le pack contenait
Diff intégral, preuve rouge reproduite sur `origin/main`, et surtout le **test réseau de
laboratoire** sur cluster k3s réel : manifeste appliqué tel quel, cinq flux mesurés depuis les pods,
et le journal de la **première exécution qui a invalidé l'implémentation** (allowlist
unidirectionnelle → flux permis bloqué), plus la distinction explicite entre ce vrai défaut et le
faux positif de sonde sur le DNS. C'est cette preuve d'exécution qui donne son poids au verdict.
