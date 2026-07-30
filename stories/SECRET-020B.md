# SECRET-020B — Appliquer le modèle de permission OpenBao approuvé

## Contexte

Story SECRET-020B (issue #264, package SECRET-020B, lane CLAUDE_CODE).

La story applique l’ADR SECRET-020A §7, approuvé et mergé. Les dépendances SECRET-020A et DATA-003 sont complétées.

Le §7.2 de l’ADR était déjà livré avant cette story et n’est pas re-corrigé : l’écriture atomique des secrets et la maîtrise de la fenêtre TOCTOU passent déjà par `_write_file`, qui délègue à `atomic_write_secret_text` (mkstemp + fchmod + replace). Mesure conservée : 300 écritures sous umask permissif n’exposent jamais un mode plus large que la cible.

La présente story applique le reste du modèle de permission approuvé : durcissement des modes POSIX, groupe dédié quand il est disponible, cohérence structurelle entre les permissions fichier et les capacités runtime des conteneurs, et repli conservateur quand l’environnement ne permet pas le durcissement.

## Décision

1. `unseal_key` passe de 0644 à **0640 + groupe dédié `forgeai-openbao`** quand le groupe existe.
   - Repli strict en **0644** si le groupe est absent, si la plateforme n’est pas POSIX, ou si le chown échoue.
   - Objectif : ne jamais laisser un 0640 orphelin de groupe, ce qui casserait le re-unseal et reproduirait la régression e2e S6 « re-unseal muet après restart ».

2. `keys_dir` passe de 0711 à **0750 + groupe dédié `forgeai-openbao`** quand le groupe existe.
   - Même règle de repli conservateur : 0711 si le groupe est absent, si la plateforme n’est pas POSIX, ou si le chown échoue.

3. Dans le rendu Compose, le service `openbao-unsealer` reçoit **`group_add: ["<gid>"]`** avec le GID quoté lorsque le groupe existe.
   - Aucun GID codé en dur.
   - Conformité à l’ADR §8 : un GID fixe avait été rejeté.

4. Dans le rendu K3s, le volume Secret `openbao-keys` reçoit **`defaultMode: 288`**, soit **0o440**.

5. La source unique de décision est **`resolve_openbao_gid()`**.
   - La résolution du groupe est dynamique via `grp`.
   - L’appel pilote à la fois le mode fichier et le `group_add` Compose.
   - Un 0640 sans `group_add` correspondant est donc structurellement impossible.

## Critères d'acceptation

- [x] `test_unseal_key_0640_with_group` : la clé de descellement est écrite en 0640 avec le groupe `forgeai-openbao` lorsque le groupe existe.
- [x] `test_unseal_key_fallback_group_absent` : en l’absence de groupe, la clé reste lisible selon le comportement historique sûr, sans 0640 orphelin.
- [x] `test_unseal_key_fallback_chown_failed` : si le chown échoue, le repli conservateur est appliqué et le re-unseal n’est pas cassé.
- [x] `test_keys_dir_modes_0750_and_0711` : le répertoire de clés est en 0750 + groupe quand le groupe existe, avec repli 0711 sinon.
- [x] `test_portability_without_grp` : le module reste importable et fonctionnel sans `grp`, avec `resolve_openbao_gid()` qui renvoie `None`.
- [x] `test_compose_group_add_presence_and_fallback` : `group_add` est émis avec GID quoté quand le groupe existe, et absent en repli.
- [x] `test_k3s_secret_default_mode_288` : le manifeste K3s expose `defaultMode: 288` sur le volume Secret des clés.

Preuves associées :

- [x] 7 tests neufs couvrent : 0640 + groupe, repli groupe absent, repli chown échoué, répertoire 0750/0711, portabilité sans `grp`, `group_add` présent+quoté et absent en repli, `defaultMode: 288`.
- [x] 88→ suites openbao intactes.
- [x] 4 mutations tuées, chacune par son test dédié :
  - [x] mutation `0640 → 0644` tuée par `test_unseal_key_0640_with_group` ;
  - [x] mutation `group_add jamais émis` tuée par `test_compose_group_add_presence_and_fallback` ;
  - [x] mutation `defaultMode retiré` tuée par `test_k3s_secret_default_mode_288` ;
  - [x] mutation `repli chown supprimé` tuée par `test_unseal_key_fallback_chown_failed`.
- [x] Suite complète du repo verte.

## Portabilité (héritée de PORT-286)

`grp` est POSIX-only.

L’import de `grp` est conditionnel afin de préserver la portabilité sur les 3 OS de la matrice CI `guard-fs-multi-os`. Le module reste importable partout.

Sur Windows, `resolve_openbao_gid()` renvoie `None`. Le repli conservateur s’applique alors partout : modes historiques, pas de `group_add`, pas de dépendance à un groupe POSIX absent.

## Frontière T3

La décision de sécurité — le modèle de permission OpenBao — relève de l’ADR SECRET-020A, acte T3 déjà revu et mergé.

Cette story est l’application codée de cette décision, pas une nouvelle décision de sécurité.

Le repli vers le comportement historique prouvé est volontairement conservateur : il intervient uniquement quand l’environnement ne permet pas le durcissement approuvé.

Aucun secret réel n’est manipulé : les tests travaillent sur `tmp_path` et utilisent le GID de l’opérateur courant.
