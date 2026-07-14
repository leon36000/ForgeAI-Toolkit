<!-- Livrable Phase A — §1 plan maître
membre: grok (Grok-4.5 via forge-model-bridge, provider_id=Grok-4.5)
date: 2026-07-14 | statut: DONE | claim: UNVERIFIED (revue aveugle à venir au plan-freeze)
-->
# ForgeAI Toolkit — Matrice de couverture de tests (Phase A)

## 1. Matrice par fonctionnalité

### 1.1 Détection hardware multi-vendor

| Type | Contenu |
|------|---------|
| **Unitaires** | `test_cpu_parse_lscpu_flags_avx512`, `test_gpu_nvidia_smi_multi_gpu_uuids`, `test_gpu_amd_rocm_smi_vram_gb`, `test_gpu_intel_lspci_arc_detection`, `test_ram_meminfo_total_available`, `test_disk_lsblk_nvme_capacity_free`, `test_vendor_conflict_nvidia_amd_coexist` |
| **Intégration** | `test_detect_hardware_aggregate_profile_from_fixtures`, `test_hardware_profile_serializes_to_json_schema` |
| **E2E preuve** | `test_e2e_detect_and_match_brick_on_ci_host` → **observable** : stdout contient `vendor=CPU_ONLY\|NVIDIA\|AMD\|INTEL`, `gpus_count=N`, et au moins 1 brique `status=compatible` ou `incompatible` explicite (pas vide). |
| **Mocké** | sorties `lspci`/`nvidia-smi`/`rocm-smi`/`lscpu`/`free`/`lsblk` via fixtures réel-like (hardware absent CI) |
| **Ne PAS mocker** | parsing, agrégation métadonnées, scoring compatibilité, écriture profil |

### 1.2 Catalogue de briques (YAML, compat, FR/EN)

| Type | Contenu |
|------|---------|
| **Unitaires** | `test_parse_brick_yaml_required_fields`, `test_parse_brick_rejects_missing_min_vram`, `test_compat_resolve_vram_below_min_fails`, `test_compat_resolve_cuda_arch_match`, `test_i18n_brick_description_fr_en_keys_present`, `test_i18n_fallback_en_when_fr_missing`, `test_catalog_index_unique_brick_id` |
| **Intégration** | `test_load_catalog_dir_all_valid_yaml`, `test_resolve_catalog_against_hardware_profile_fixture` |
| **E2E preuve** | `test_e2e_install_compatible_brick_manifest_written` → **observable** : fichier manifeste généré contenant `brick_id=…` et `compat_status=ok` ; pour brick RAG : requête → réponse non vide avec source citée. |
| **Mocké** | aucun pour parsing YAML ; hardware via profil fixture |
| **Ne PAS mocker** | chargeur catalogue, moteur de résolution, fichiers YAML réels du repo |

### 1.3 Moteur de rendu double backend (Compose + K3s)

| Type | Contenu |
|------|---------|
| **Unitaires** | `test_render_compose_service_image_ports`, `test_render_compose_gpu_reservations_nvidia`, `test_render_k3s_deployment_resources`, `test_render_k3s_service_clusterip`, `test_same_manifest_compose_and_k3s_service_names_parity`, `test_render_rejects_unknown_backend` |
| **Intégration** | `test_pipeline_manifest_to_compose_yml_and_k3s_yaml`, `test_validate_rendered_compose_with_docker_compose_config` |
| **E2E preuve** | `test_e2e_deploy_compose_stack_healthcheck_ready` → **observable** : `docker compose ps` service `healthy` **ET** HTTP local répond 200 sur endpoint métier (ex. `/health` ou query RAG). |
| **Mocké** | cluster K3s distant si pas de runner ; images registry externe (pull pré-caché CI) |
| **Ne PAS mocker** | templates de rendu, diff Compose vs K3s, validation structure YAML générée |

### 1.4 Wizard TUI (Textual)

| Type | Contenu |
|------|---------|
| **Unitaires** | `test_wizard_step_hardware_displays_detected_gpus`, `test_wizard_step_brick_filter_by_compat`, `test_wizard_step_backend_compose_or_k3s`, `test_wizard_validate_blocks_next_on_incompat`, `test_wizard_locale_switch_fr_en_labels` |
| **Intégration** | `test_wizard_pilot_headless_full_path_writes_manifest` (Textual pilot/async) |
| **E2E preuve** | `test_e2e_wizard_complete_produces_runnable_compose` → **observable** : sortie wizard = chemin manifeste ; `docker compose -f <path> config` exit 0. |
| **Mocké** | input clavier via pilot Textual ; hardware via fixture |
| **Ne PAS mocker** | état machine des steps, validation, sérialisation config finale |

### 1.5 Multi-nœuds (SSH ed25519, Tailscale)

| Type | Contenu |
|------|---------|
| **Unitaires** | `test_generate_ed25519_keypair_permissions_600`, `test_ssh_bootstrap_script_includes_authorized_keys`, `test_tailscale_join_command_uses_authkey_env`, `test_node_registry_rejects_duplicate_node_id`, `test_bootstrap_dry_run_no_remote_exec` |
| **Intégration** | `test_bootstrap_local_sshd_container_adds_key_and_ping`, `test_tailscale_status_json_parses_peer_ip` |
| **E2E preuve** | `test_e2e_second_node_joins_and_answers_agent_ping` → **observable** : registre nœuds montre `status=online` + réponse agent distante `pong` (pas seulement tunnel up). |
| **Mocké** | Tailscale control plane (authkey fake + fixture `tailscale status`) si pas de compte CI ; SSH distant hors job dédié |
| **Ne PAS mocker** | génération clés, format authorized_keys, modèle registre nœuds, protocole ping agent |

### 1.6 Registres JSONL hash-chaînés

| Type | Contenu |
|------|---------|
| **Unitaires** | `test_jsonl_append_computes_sha256_chain`, `test_jsonl_verify_detects_tampered_line`, `test_jsonl_verify_detects_broken_prev_hash`, `test_jsonl_reject_append_without_prev_link`, `test_jsonl_load_heads_and_tip_hash` |
| **Intégration** | `test_deploy_event_appended_and_chain_valid_on_disk` |
| **E2E preuve** | `test_e2e_full_deploy_writes_hash_chain_verifiable` → **observable** : `forgeai registry verify` exit 0 et tip hash == dernier SHA256 fichier. |
| **Mocké** | rien (I/O fichier local) |
| **Ne PAS mocker** | hash, append atomique, verify |

### 1.7 Gates no-stub

| Type | Contenu |
|------|---------|
| **Unitaires** | `test_gate_scan_rejects_not_implemented_error`, `test_gate_scan_rejects_pass_only_test_body`, `test_gate_scan_rejects_todo_stub_function`, `test_gate_allows_explicit_mock_in_tests_dir_only`, `test_gate_fails_on_mock_in_src_package` |
| **Intégration** | `test_pre_commit_gate_runs_on_sample_repo_tree` |
| **E2E preuve** | `test_e2e_ci_gate_blocks_pr_with_stub` → **observable** : job CI exit ≠ 0 + message `STUB_DETECTED:path:line`. |
| **Mocké** | rien |
| **Ne PAS mocker** | scanner AST/source, chemins `src/` vs `tests/` |

---

## 2. Stratégie hardware en CI

**Approche** : détecteur lit **command runners injectables** ; en prod = subprocess système ; en tests = mémoire fixture (`HardwareCommandFixture`). CI **sans GPU** : toujours fixtures. Runner GPU optionnel nightly pour non-régression binaire réel.

**Règle** : chaque fixture = capture réelle anonymisée (`# captured: host=… date=…`), jamais inventée à la main au-delà du format outil.

### Exemple fixture 1 — `nvidia-smi` (multi-GPU)

```text
# tests/fixtures/hardware/nvidia_smi_L_query.txt
# captured: host=lab-box-07 date=2025-11-12
0, NVIDIA GeForce RTX 3090, 24576, 24000, 8.6, 525.60.13
1, NVIDIA GeForce RTX 3090, 24576, 23800, 8.6, 525.60.13
```

Format consommé : `index,name,memory.total[MiB],memory.free[MiB],compute_cap,driver`

### Exemple fixture 2 — `lspci -nn` (AMD + Intel)

```text
# tests/fixtures/hardware/lspci_nn_amd_intel.txt
# captured: host=workstation-a2 date=2025-10-03
03:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Navi 21 [Radeon RX 6800/6800 XT] [1002:73bf]
00:02.0 VGA compatible controller [0300]: Intel Corporation Device [8086:56a0] (rev 08)
00:1f.4 SMBus [0c05]: Intel Corporation Device [8086:7aa3]
```

Compléter avec `lscpu_avx512.txt`, `proc_meminfo_64g.txt`, `lsblk_nvme.txt` sous le même pattern.

`test_gpu_nvidia_smi_multi_gpu_uuids` et `test_gpu_amd_rocm_smi_vram_gb` **doivent** consommer ces fichiers ; un test d'intégrité refuse fixture tronquée/mal formée.

---

## 3. Seuils

| Module | Couverture min. lignes | Branches |
|--------|------------------------|----------|
| `forgeai.hardware` | 90 % | 85 % |
| `forgeai.catalog` | 90 % | 85 % |
| `forgeai.render` | 90 % | 85 % |
| `forgeai.wizard` | 80 % | 75 % |
| `forgeai.nodes` | 85 % | 80 % |
| `forgeai.registry` | 95 % | 90 % |
| `forgeai.gates` | 95 % | 90 % |
| **Global `src/`** | **85 %** | **80 %** |

| Critère | Valeur |
|---------|--------|
| Budget CI PR (unit + intégration) | ≤ 12 min wall-clock |
| Budget CI nightly (+ e2e compose + SSH container) | ≤ 45 min |
| Flakiness | > 1 fail intermittent / 50 runs → quarantine + issue ; retest 3× interdit en merge gate |
| Retry autorisé | uniquement infra réseau Tailscale/SSH e2e, max 1, loggé |

Fail CI si couverture baisse de > 1 pt vs `main` sans justification `cov-ignore` datée.

---

## 4. Anti-faux-vert — 5 règles

1. **Assertion métier observable** : tout e2e assert un **effet utilisateur** (réponse RAG non vide, `registry verify` OK, nœud `pong`, HTTP 200 métier). Interdit : seul `returncode == 0` ou « container running ».
2. **Interdiction `pass` / assert True** : gate AST échoue sur corps de test sans `assert`/`pytest.raises`/`expect` Textual réel ; `test_*` vide = fail build.
3. **Mocks localisés et listés** : `@pytest.mark.mocked_external("nvidia-smi"|"tailscale"|"ssh")` obligatoire ; mock hors `tests/` = fail `test_gate_fails_on_mock_in_src_package`.
4. **Preuve double backend** : chaque fixture manifeste de non-régression génère Compose **et** K3s ; test `…_parity` compare noms services/ports/limites GPU — un backend seul = incomplet.
5. **Chaîne de confiance registre** : tout chemin « deploy réussi » lit le tip hash JSONL et vérifie la chaîne ; un test qui mocke `append`/`verify` en e2e est rejeté par revue + gate.

---

**Rappel équipe** : *une fonctionnalité sans ligne dans cette matrice + tests nommés n'existe pas.* TDD : RED (test échoue sur comportement absent) → GREEN (impl minimal) → REFACTOR.
