<!-- NE PAS ÉDITER À LA MAIN — généré par scripts/governance/validate_authority.py --render -->

# Hiérarchie d'autorité

Cette carte est le rendu de `governance/authority.json`.

## Propriétaires

| Identifiant | Rôle |
|---|---|
| `copilot` | cockpit multi-IDE ORCH-001 (historique) |
| `nathan` | T3 — gardien (paiements, secrets prod, suppressions, CANON) |
| `orchestrateur` | session lead Claude Code — méthode et pipeline |

## Portées

| Portée | Singleton |
|---|---|
| `architecture` | non |
| `catalogue_data` | oui |
| `coordination_ops` | oui |
| `evidence_ledger` | oui |
| `governance_method` | non |
| `ide_contract` | non |
| `orchestration` | non |
| `plan_of_record` | non |
| `product_requirements` | oui |
| `security` | non |
| `system_state` | oui |

## Sources

| Id | Source | Statut | Portée | Propriétaire | Successeur |
|---|---|---|---|---|---|
| `adr.rag-004a` | `CANON/adr/ADR-RAG-004A-grounding-contract.md` | active | `architecture` | `nathan` | `—` |
| `adr.secret-020a` | `CANON/adr/ADR-SECRET-020A-openbao-unseal-permissions.md` | active | `architecture` | `nathan` | `—` |
| `adr.trust-019a` | `CANON/adr/ADR-TRUST-019A-registres-modele-de-menace-racine-confiance.md` | active | `architecture` | `nathan` | `—` |
| `agents-md` | `AGENTS.md` | conflicted | `governance_method` | `nathan` | `—` |
| `agents-md.orch-001` | décision sans fichier | superseded | `orchestration` | `copilot` | `gov.decision-mission-lead` |
| `canon.directives-perimetre` | `CANON/directives-perimetre.md` | conflicted | `security` | `nathan` | `—` |
| `canon.etat-systeme` | `CANON/ETAT-SYSTEME.md` | active | `system_state` | `nathan` | `—` |
| `canon.plan-integral` | `CANON/plan-integral.md` | conflicted | `plan_of_record` | `nathan` | `—` |
| `canon.plan-maitre-bmad` | `CANON/PLAN-MAITRE-EXECUTION-BMAD-v1.0.md` | conflicted | `plan_of_record` | `nathan` | `—` |
| `canon.spec-stacks` | `CANON/spec-stacks.md` | active | `architecture` | `nathan` | `—` |
| `canon.spec-web-ui` | `CANON/spec-web-ui.md` | active | `architecture` | `nathan` | `—` |
| `claude-md` | `CLAUDE.md` | conflicted | `governance_method` | `nathan` | `—` |
| `coord.active-claims` | `archive/coordination/active-claims.json` | superseded | `coordination_ops` | `copilot` | `gov.decision-mission-lead` |
| `coord.work-packages` | `archive/coordination/work-packages.json` | superseded | `coordination_ops` | `copilot` | `gov.decision-mission-lead` |
| `cursor.orchestration-rules` | `archive/cursor/rules/forgeai-orchestration.mdc` | superseded | `ide_contract` | `copilot` | `gov.decision-mission-lead` |
| `gov.decision-arborescence-evidence-work-archive` | `governance/decisions/D-2026-08-15-arborescence-evidence-work-archive.md` | active | `governance_method` | `orchestrateur` | `—` |
| `gov.decision-mission-lead` | `governance/decisions/D-2026-08-14-mission-lead.md` | conflicted | `orchestration` | `nathan` | `—` |
| `gov.decision-racines-documentaires` | `governance/decisions/D-2026-08-15-racines-documentaires.md` | active | `governance_method` | `orchestrateur` | `—` |
| `manifests.roles` | `manifests/roles.yaml` | active | `ide_contract` | `orchestrateur` | `—` |
| `master-plan` | `MASTER-PLAN.md` | conflicted | `plan_of_record` | `nathan` | `—` |
| `readme` | `README.md` | active | `governance_method` | `nathan` | `—` |
| `registres.mission` | `evidence/registres/mission.jsonl` | active | `evidence_ledger` | `orchestrateur` | `—` |
| `stories.orch-001` | `stories/ORCH-001.md` | archived | `orchestration` | `copilot` | `—` |

## Précédences déclarées

- `canon.plan-integral` prévaut sur `master-plan`, `canon.plan-maitre-bmad`

## Positions déclarées

- `agents-md` : `orchestration_seat` = `claude_code_opus_mission_lead` (AGENTS.md:9)
- `agents-md` : `workspace_confinement` = `repo_plus_external_governance_tooling` (AGENTS.md:73-76)
- `canon.directives-perimetre` : `workspace_confinement` = `repo_only_strict` (CANON/directives-perimetre.md:7)
- `canon.plan-integral` : `plan_of_record` = `canon_plan_integral` (CANON/plan-integral.md:4)
- `canon.plan-integral` : `orchestration_seat` = `claude_code_session_lead` (CANON/plan-integral.md:27)
- `canon.plan-maitre-bmad` : `plan_of_record` = `canon_plan_maitre_bmad_v1` (CANON/PLAN-MAITRE-EXECUTION-BMAD-v1.0.md:1-2)
- `claude-md` : `workspace_confinement` = `repo_plus_external_governance_tooling` (CLAUDE.md:39)
- `gov.decision-mission-lead` : `orchestration_seat` = `claude_code_opus_mission_lead` (governance/decisions/D-2026-08-14-mission-lead.md:9)
- `master-plan` : `plan_of_record` = `master_plan_v1` (MASTER-PLAN.md:7)
