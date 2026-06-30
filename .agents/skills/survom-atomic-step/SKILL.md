---
name: survom-atomic-step
description: Governance rules for SurvOm atomic pipeline step work. Use before planning, scaffolding, editing, testing, reviewing, or reporting any atomic step or dynamic workflow assembly task in this repository.
---

# SurvOm Atomic Step Governance

The owner is the sole approval authority. Work only on the single currently approved task.

## Task Status

- `DRAFT` means plan-only. Read-only inspection is allowed, including repository listing, `git status`, `git diff`, and document reading. DRAFT prohibits edits, generated artifacts, code execution, validation execution, status changes, and validation-tier promotion.
- Work may begin only after the owner approves the task and the task lists the editable paths.
- Existing production code is read-only unless the approved task explicitly lists its path.

## Prohibited Actions

Never commit, push, merge, reset, rebase, delete branches, or tag.

Never run AWS Batch, create AWS resources, use customer data, or promote validation status.

Never create pipeline code, atomic-step code, containers, dependencies, CI, scientific Python or R scripts, or customer-data tooling unless a future approved task explicitly authorizes those artifacts.

Never hand-edit a generated registry or index. Generated registries and indexes are derived from step-owned `meta.yml` files.

Never use container tag `latest` when containers are introduced.

## Step Identity, Metadata, and Provenance

Step IDs must be stable lowercase, domain-qualified IDs in the form `domain.category.step_name`, such as `transcriptomics.de.simple_de_test`.

Step IDs are immutable after the first owner-approved release.

Each atomic step owns a machine-readable `meta.yml`. Until a pinned YAML parser is approved, `meta.yml` content must be JSON-compatible and the JSON Schema contract is authoritative. The filesystem is the source of truth.

Each atomic step uses SemVer in `meta.yml`. Registry records must support immutable version and checksum provenance. Implementation checksum drift without a corresponding version change is prohibited.

Allowed status values are:

- `experimental`
- `active`
- `deprecated`

Status is not validation tier. Only the owner may approve a status change.

Allowed validation tiers are:

- `unit_tested`
- `golden_dataset`
- `published_concordance`

An agent may collect validation evidence, but must not change or promote a validation tier. Customer-facing execution requires owner-approved eligibility and may use only steps meeting the future customer-use policy.

## Required Pre-Scaffold Workflow

Before scaffolding, an agent must verify:

1. The task is owner-approved and not `DRAFT`.
2. Editable paths are listed and match the requested step.
3. The proposed ID follows `domain.category.step_name`.
4. The proposed ID, aliases, step intent, input signature, output signature, and taxonomy do not duplicate or collide with existing registry metadata.
5. The taxonomy fits the approved domain, category, assay or data modality, lifecycle stage, inputs, and outputs.
6. Registry consistency checks pass for status, validation tier, SemVer, and checksum provenance expectations.

Uncertainty about scientific correctness, taxonomy, duplicate intent, validation evidence, or customer eligibility blocks edits and must be reported for owner review.

Structural checks may be automated. Scientific correctness and validation promotion require owner approval.

## Atomic Step Lifecycle

Each atomic step must be handled separately:

1. Scaffold only the approved step and approved paths.
2. Add focused tests for that step.
3. Assign or update the step version as approved.
4. Produce validation evidence without promoting validation status.
5. Submit for owner review before any further step work begins.

## Dynamic Workflow Assembly

Dynamic workflow assembly may select only owner-approved registry steps and must generate a reviewable manifest.

An LLM may propose a manifest using approved registry steps only. Execution may use only a fixed, reviewable, owner-approved manifest.

Manifests must eventually capture selected step IDs, versions, checksums, inputs, outputs, validation tier, registry source, and approval or review evidence.

An LLM must never modify an executable customer pipeline at runtime.

## Final Report Requirements

Final reports must include changed files, tests run, version impact, validation evidence, risks, and a Git diff summary.
