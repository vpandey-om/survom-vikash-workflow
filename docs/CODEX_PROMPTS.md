# SurvOm Codex Prompts

Use these prompts to keep Codex work inside owner-controlled governance.

## Plan-Only Draft Task

```text
This task is DRAFT. Plan only. Read-only inspection is allowed, including repository listing, git status, git diff, and document reading. Do not edit files, generate files, run commands that execute project code, run validation, create resources, change status, or promote validation tier.

Report the proposed scope, editable paths, tests to run after approval, version impact, validation evidence to collect, risks, and open owner decisions.
```

## Approved Single Task

```text
Work on this one approved task only. The owner is the sole approval authority.

Editable paths:
- <list exact paths>

All existing production code outside those paths is read-only.

Do not commit, push, merge, reset, rebase, delete branches, tag, run AWS Batch, use customer data, create AWS resources, create containers or dependencies, or promote validation status.

Do not hand-edit generated registries or indexes. Do not use container tag latest when containers are introduced.

At completion, report changed files, tests run, version impact, validation evidence, risks, and Git diff summary.
```

## Atomic Step Task

```text
Create or update only the approved atomic step named below. Every atomic step must be scaffolded, tested, versioned, and reviewed separately.

Step name:
Registry ID in domain.category.step_name format:
Version, using SemVer per atomic step:
Editable paths:

Each atomic step owns meta.yml. Until a pinned YAML parser is approved, meta.yml content must be JSON-compatible and the JSON Schema contract is authoritative. The filesystem is the source of truth. Generated registries and indexes are derived from step metadata and are never hand-edited.

Before scaffolding, verify approved task status, allowed paths, duplicate and naming collision checks, taxonomy fit, and registry consistency.

Allowed status values are experimental, active, and deprecated. Status is not validation tier. Allowed validation tiers are unit_tested, golden_dataset, and published_concordance.

Implementation checksum drift without a corresponding version change is prohibited. Containers must be pinned when introduced; never use latest.

Uncertainty about scientific correctness, taxonomy, duplicate intent, validation evidence, or customer eligibility blocks edits and must be reported for owner review. Structural checks may be automated; scientific correctness and validation promotion require owner approval.

Do not work on any other step. Do not promote status or validation tier. Do not create dynamic runtime behavior that lets an LLM modify an executable customer pipeline.
```

## Dynamic Workflow Assembly Review

```text
Review dynamic workflow assembly only as a manifest-producing process.

An LLM may propose a manifest using approved registry steps only. Execution may use only a fixed, reviewable, owner-approved manifest.

It may select only owner-approved registry steps. It must generate a reviewable manifest containing selected step IDs, versions, checksums, inputs, outputs, validation tier, registry source, and approval or review evidence.

An LLM must never modify an executable customer pipeline at runtime.
```
