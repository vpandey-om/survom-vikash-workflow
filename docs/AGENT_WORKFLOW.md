# SurvOm Agent Workflow

This workflow defines how agents operate in this repository. The owner is the sole approval authority.

## Before Work Starts

1. Confirm the active task and its status.
2. Confirm that only one approved task is active.
3. Confirm the editable paths listed by the approved task.
4. Treat all existing production code as read-only unless its path is explicitly listed.

If the task status is `DRAFT`, stop after planning. Read-only inspection is allowed, including repository listing, `git status`, `git diff`, and document reading. DRAFT prohibits edits, generated artifacts, code execution, validation execution, status changes, and validation-tier promotion.

## Forbidden Operations

Agents must never:

- Commit, push, merge, reset, rebase, delete branches, or tag.
- Run AWS Batch or create AWS resources.
- Use customer data.
- Promote validation status.
- Modify executable customer pipelines at runtime.
- Hand-edit a generated registry or index.
- Use container tag `latest` when containers are introduced.

## Atomic Step Workflow

Every atomic step must be scaffolded, tested, versioned, and reviewed separately.

An approval for one atomic step does not authorize work on another step. Start the next step only after the owner approves a new task.

Step IDs use stable lowercase, domain-qualified IDs in the form `domain.category.step_name`, such as `transcriptomics.de.simple_de_test`. IDs are immutable after the first owner-approved release.

Each atomic step owns a machine-readable `meta.yml`. Until a pinned YAML parser is approved, `meta.yml` content must be JSON-compatible and the JSON Schema contract is authoritative. The filesystem is the source of truth. Generated registries and indexes are derived from step metadata and must never be hand-edited.

Each step uses SemVer in `meta.yml`. Registry records must support immutable version and checksum provenance. Implementation checksum drift without a corresponding version change is prohibited.

Allowed status values are `experimental`, `active`, and `deprecated`. Status is distinct from validation tier. Only the owner may approve a status change.

Allowed validation tiers are `unit_tested`, `golden_dataset`, and `published_concordance`. An agent may collect evidence, but must not change or promote a validation tier. Customer-facing execution requires owner-approved eligibility and may use only steps meeting the future customer-use policy.

Before scaffolding, an agent must verify approved task status, allowed paths, duplicate and naming-collision checks, taxonomy fit, and registry consistency. Uncertainty about scientific correctness, taxonomy, duplicate intent, validation evidence, or customer eligibility blocks edits and must be reported for owner review.

Structural checks may be automated. Scientific correctness and validation promotion require owner approval.

## Dynamic Workflow Assembly

Dynamic workflow assembly may select only owner-approved registry steps. It must generate a reviewable manifest showing the selected steps, versions, inputs, outputs, and validation status claimed by the registry.

An LLM may propose a manifest using approved registry steps only. Execution may use only a fixed, reviewable, owner-approved manifest. Manifests must eventually capture selected step IDs, versions, checksums, inputs, outputs, validation tier, registry source, and approval or review evidence.

An LLM may help plan, review, or draft manifests, but it must never alter an executable customer pipeline at runtime.

## SeqKit FASTQ Stats Testing

Normal unit tests for `common.qc.seqkit_fastq_stats` use only fully synthetic FASTQ fixtures committed under `tests/fixtures/seqkit_fastq_stats`.

The optional SeqKit smoke test uses external public/local FASTQ files supplied by path, writes outputs only to the requested output directory, and must never copy smoke-test inputs into Git. Customer data must never be used for unit tests or smoke tests. Smoke-test results are evidence only; they do not promote validation tier, status, or production/customer-use eligibility.

## Final Report

Every final report must include:

- Changed files.
- Tests or checks run.
- Version impact.
- Validation evidence.
- Risks and limitations.
- Git diff summary.
