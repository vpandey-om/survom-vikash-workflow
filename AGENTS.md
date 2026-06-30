# SurvOm Agent Governance

This repository is governed by the owner. The owner is the sole approval authority for all work, scope changes, validation status, releases, and promotions.

## Operating Rules

- Work on exactly one owner-approved task at a time.
- A task marked `DRAFT` is plan-only. Read-only inspection is allowed, including repository listing, `git status`, `git diff`, and document reading. DRAFT prohibits edits, generated artifacts, code execution, validation execution, status changes, and validation-tier promotion.
- Do not commit, push, merge, reset, rebase, delete branches, or create tags.
- Do not run AWS Batch, create AWS resources, use customer data, or promote validation status.
- Existing production code is read-only unless the approved task explicitly lists the path as editable.
- Do not create pipeline code, atomic-step code, containers, dependencies, CI, workflows, tests, or customer-data tooling unless a future approved task explicitly permits those paths and artifacts.

## Atomic Step Policy

Every atomic step must be scaffolded, tested, versioned, and reviewed separately. One approval covers one step only unless the owner explicitly states otherwise.

Step identity uses stable lowercase, domain-qualified IDs in the form `domain.category.step_name`, such as `transcriptomics.de.simple_de_test`. IDs are immutable after the first owner-approved release.

Each atomic step owns a machine-readable `meta.yml`. Until a pinned YAML parser is approved, `meta.yml` content must be JSON-compatible and the JSON Schema contract is authoritative. The filesystem is the source of truth. Generated registries and indexes are derived from step metadata and must never be hand-edited.

Registry records must support immutable version and checksum provenance. Each atomic step uses SemVer in `meta.yml`. Implementation checksum drift without a corresponding version change is prohibited.

Allowed status values are `experimental`, `active`, and `deprecated`. Status is distinct from validation tier. Only the owner may approve a status change.

Allowed validation tiers are `unit_tested`, `golden_dataset`, and `published_concordance`. An agent may collect evidence, but must not change or promote a validation tier. Customer-facing execution requires owner-approved eligibility and may use only steps meeting the future customer-use policy.

Containers must be pinned when containers are introduced. Never use `latest`.

Dynamic workflow assembly may select only owner-approved registry steps and must generate a reviewable manifest. A manifest must eventually capture selected step IDs, versions, checksums, inputs, outputs, validation tier, registry source, and approval or review evidence. Execution may use only a fixed, reviewable, owner-approved manifest. An LLM may propose a manifest, but must never modify an executable customer pipeline at runtime.

Before scaffolding, an agent must verify approved task status, allowed paths, duplicate and naming-collision checks, taxonomy fit, and registry consistency. Uncertainty about scientific correctness, taxonomy, duplicate intent, validation evidence, or customer eligibility blocks edits and must be reported for owner review. Structural checks may be automated; scientific correctness and validation promotion require owner approval.

## Required Final Report

Every final report must state:

- Changed files.
- Tests or checks run.
- Version impact.
- Validation evidence.
- Risks and limitations.
- Git diff summary.
