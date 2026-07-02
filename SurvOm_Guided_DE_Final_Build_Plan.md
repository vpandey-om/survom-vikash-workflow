# SurvOm Guided Differential Analysis — Final Build Plan (Nextflow DSL2)

This wraps the already-designed `stats.*` core (`SurvOm_DE_Final_Build_Plan.md`) with a
beginner-facing layer. It does **not** replace that plan — it adds a UI-friendly front door
(`data.inspect_inputs` → `analysis.plan_differential`) and a human-readable back door
(`results.report_differential`) around the same six `stats.*` steps you already scoped.

Same operating discipline as the other two plans: one branch per atomic step, nothing merges
without explicit review, no hidden thresholds anywhere — including at the wizard/UX layer.

---

## 0. Corrections locked in from critical review of the Codex draft

| # | Draft said | **Final (locked)** |
|---|---|---|
| 1 | `stats.deseq2` interface.yaml has `default:` on `test_type`, `apply_shrinkage`, `shrinkage_method`, `p_adjust_method`, `save_rds` | **No defaults, anywhere** — same rule as the core DE plan. All five REQUIRED. The wizard supplies an explicit value; the step never falls back on its own. |
| 2 | `test_type` enum lists `[wald, lrt]`, `shrinkage_method` lists `[apeglm, normal, ashr]` | v1 enums list **only what's actually implemented**: `test_type: [wald]`, `shrinkage_method: [apeglm]`. Widen the enum in the same sprint you implement the new option — never before. |
| 3 | This doc's `stats.filter_features` uses `min_samples_fraction`; the core DE plan used `min_samples` (absolute count) | Reconciled: filter spec takes **exactly one** of `min_samples_count` / `min_samples_fraction` (mirrors the "exactly one selection mode" pattern already used in the pathway plan) — hard fail if both or neither are set. |
| 4 | Sprint 3 bundles 3 atomic steps (planner + validate_design + build_contrasts); Sprint 6 bundles 3 more | Restructured into **13 parts, one atomic step per branch** — see §3. |
| 5 | Nothing cross-checks declared `assay_type` against what `data.inspect_inputs` actually detected | New required check in `analysis.plan_differential`: if `assay_type` implies raw counts but `value_profile.integer_fraction < 1.0`, hard-fail with a beginner-readable message — before DESeq2 ever sees the data. |
| 6 | Covariate reference levels (`batch_1`, `female`) appear in `design_spec.json` with no stated selection rule | `analysis.plan_differential` must apply one documented deterministic rule (alphabetically-first level, absent explicit user input) and record it in a new `assumptions_applied` array in `analysis_plan.json` — visible to the wizard, not buried. |
| 7 | Example wizard thresholds (`min_count: 10`, `adjusted_p < 0.05`, `\|log2FC\| ≥ 1`) risk becoming silent UX-layer defaults even though atomic steps enforce "required" | The wizard may **suggest** starting values, but must display them and require confirmation before the run starts. Every value actually used gets written into `analysis_manifest.json` as user-confirmed, not implied. |
| 8 | interface.yaml example omits `container:` | Added `container: null`, matching both prior plans. |

Everything else in the draft (four-layer architecture, MVP scope, the nine-step catalogue, the
`data.*`/`results.*` restraint against over-atomizing) carries forward unchanged.

---

## 1. What's new here vs. what already exists

| Step | Status | Action needed |
|---|---|---|
| `data.inspect_inputs` | **New** | Build from scratch — §3, Part 2 |
| `analysis.plan_differential` | **New** | Build from scratch — §3, Part 3 |
| `stats.validate_design` | Already scoped in the DE plan (Sprint 2) | Verify compatibility only — §3, Part 4 |
| `stats.build_contrasts` | Already scoped (Sprint 3) | Verify compatibility only — §3, Part 5 |
| `stats.filter_features` | Already scoped (Sprint 4) | **Amend** — reconcile fraction/count params — §3, Part 6 |
| `stats.deseq2` | Already scoped (Sprint 5) | **Amend** — remove all defaults, narrow enums — §3, Part 7 |
| `stats.combine_results` | Already scoped (Sprint 6) | Verify compatibility only — §3, Part 8 |
| `stats.qc_diagnostics` | Already scoped (Sprint 7) | Verify compatibility only — §3, Part 9 |
| `results.report_differential` | **New** | Build from scratch — §3, Part 10 |

Check the actual repo state in Part 0 before assuming any of the "already scoped" steps exist as
code — "already scoped" means *designed*, not necessarily *built yet*.

---

## 2. Architecture (unchanged shape, cleaned)

```
gene_counts.tsv + sample_metadata.tsv + analysis_request.json
                    |
                    v
          data.inspect_inputs
                    |
                    v
        analysis.plan_differential
                    |
        +-----------+-----------+
        |                       |
        v                       v
  stats.validate_design   (feature_matrix.meta.json,
        |                  design_spec.json,
        v                  contrast_spec.json all
  stats.build_contrasts    flow from the planner into
        |                  every step below)
        v
  stats.filter_features
        |
        v
     stats.deseq2
        |
        v
  stats.combine_results
        |
        v
  stats.qc_diagnostics
        |
        v
 results.report_differential
```

---

## 3. Build order — 13 parts, one atomic step per branch

### Part 0 — Discovery (branch: none — no code)

**Do this before anything else, and tell Codex to do it before anything else.** This repo already
has an atomic-step organization skill/convention set — read it first, don't reinvent shape.

```bash
cd /data/shared/vikash/survom-vikash-workflow
# 1. Read the repo's own atomic-step skill/convention docs first
find . -iname "SKILL.md" -o -iname "*atomic*step*" | grep -v node_modules | sort
cat AGENTS.md | sed -n '1,240p'

# 2. Check whether the stats.* steps from the DE plan already exist as code, not just design
find bin -name "stats_*" -o -name "*validate_design*" -o -name "*deseq2*" | sort
git log --oneline --all | grep -i "stats\." | head -50
find atomic_steps -maxdepth 1 -type d 2>/dev/null | sort

# 3. Confirm existing interface.yaml / CLI / fixture conventions
cat atomic_steps/stats.deseq2/interface.yaml 2>/dev/null
```

**Codex prompt for Part 0:**
> Before writing any code, read this repository's atomic-step organization skill/convention
> documentation (search for SKILL.md or equivalent) and AGENTS.md. Report: (a) the exact
> interface.yaml conventions this repo uses, (b) whether stats.validate_design, stats.build_contrasts,
> stats.filter_features, stats.deseq2, stats.combine_results, and stats.qc_diagnostics already
> exist as code in this repo (not just as a design doc), and if so their current interface.yaml
> contents, (c) the fixture/test layout convention, (d) the registry generation and Docker-version
> validation commands. Do not write or edit any files.

**Definition of done:** you know exactly which of Parts 4–9 below are "verify" work vs. "amend"
work vs. "actually build from scratch because the DE plan was never implemented." Don't guess —
this changes the whole shape of the next 9 branches.

---

### Part 1 — Shared utilities and contracts (branch: `step/guided-de-shared-utils`)

**Deliverables:**
```
shared_models.py        # pydantic models: DesignSpec, ContrastSpec, FeatureMatrixMeta,
                         # AnalysisPlan (now including assumptions_applied), FilterSpec
                         # (now with exactly-one-of min_samples_count/min_samples_fraction)
shared_io.py             # TSV reader/writer utilities
shared_errors.py         # standard error JSON format, exit-code convention
result_table_schema.py   # ResultTable v1 validator (reuse from stats core if it already exists)
```

If `stats.*` contracts already exist from the DE plan (per Part 0's findings), **import and
extend them here rather than redefining them** — `AnalysisPlan` and `FilterSpec` are the only
genuinely new/changed shapes in this layer.

**Acceptance gate:** `FilterSpec` rejects a payload with both `min_samples_count` and
`min_samples_fraction` set, and rejects one with neither set. `AnalysisPlan` requires
`assumptions_applied` as a (possibly empty) list, never absent.

---

### Part 2 — `data.inspect_inputs` (branch: `step/data-inspect-inputs`)

**Nextflow process skeleton:**
```groovy
process DATA_INSPECT_INPUTS {
    tag "${meta.id}"
    container null

    input:
    tuple val(meta), path(feature_matrix)
    path sample_metadata
    val feature_id_column
    val sample_id_column

    output:
    tuple val(meta), path("input_inspection.json"), emit: inspection

    script:
    """
    data__inspect_inputs.py \\
        --feature-matrix ${feature_matrix} \\
        --sample-metadata ${sample_metadata} \\
        --feature-id-column ${feature_id_column} \\
        --sample-id-column ${sample_id_column} \\
        --out-inspection input_inspection.json
    """
}
```

**Important rule (unchanged from draft, worth restating):** this step never mutates user data —
it only inspects and reports. It is **advisory**, feeding the UI human-readable warnings — it is
not the authoritative gate. `stats.validate_design` (Part 4) is the hard gate. The two checks
overlapping on sample-ID matching is intentional layering, not redundancy: this step explains
mismatches in plain language for the wizard before the user even picks a design; validate_design
enforces it as a hard stop regardless of what the UI showed.

**Fixtures:** valid matrix+metadata · duplicate feature IDs · duplicate metadata sample IDs ·
matrix-only sample · metadata-only sample · non-numeric count value · non-integer values present
(needed by Part 3's assay-type cross-check, fixture reused there).

**Acceptance gate:** `value_profile.integer_fraction` and `suggested_value_scale` are correctly
computed on the non-integer fixture — this output is what Part 3's new safety check depends on.

---

### Part 3 — `analysis.plan_differential` (branch: `step/analysis-plan-differential`)

**Nextflow process skeleton:**
```groovy
process ANALYSIS_PLAN_DIFFERENTIAL {
    tag "${meta.id}"
    container null

    input:
    tuple val(meta), path(analysis_request)
    path input_inspection

    output:
    tuple val(meta), path("feature_matrix.meta.json"), emit: feature_matrix_meta
    tuple val(meta), path("design_spec.json"), emit: design_spec
    tuple val(meta), path("contrast_spec.json"), emit: contrast_spec
    tuple val(meta), path("analysis_plan.json"), emit: analysis_plan

    script:
    """
    analysis__plan_differential.py \\
        --analysis-request ${analysis_request} \\
        --input-inspection ${input_inspection} \\
        --out-feature-matrix-meta feature_matrix.meta.json \\
        --out-design-spec design_spec.json \\
        --out-contrast-spec contrast_spec.json \\
        --out-analysis-plan analysis_plan.json
    """
}
```

**New required check (fix #5):** if `analysis_request.assay_type` implies raw counts
(`bulk_rnaseq_counts`) but `input_inspection.feature_matrix.value_profile.integer_fraction < 1.0`
or `suggested_value_scale != "raw_count"`, **hard-fail** with a message a non-statistician can
act on, e.g.: *"Your data appears to already be normalized (non-integer values detected), but you
selected 'raw RNA-seq counts.' DESeq2 requires raw integer counts — check your export settings or
choose a different assay type."*

**New required behavior (fix #6):** any reference level not explicitly supplied by the user
(covariates only — the primary factor's numerator/denominator is always user-specified) is chosen
by one documented rule: **alphabetically first level**. Every such auto-choice is appended to
`analysis_plan.json`'s new `assumptions_applied` array, e.g.:
```json
"assumptions_applied": [
  "Reference level for 'batch' set to 'batch_1' (alphabetically first — not explicitly chosen)."
]
```
This array must be shown to the user before the run executes, not just logged after the fact.

**Auto-engine-selection rule, made explicit:** `recommended_engine = deseq2` when
`assay_type = bulk_rnaseq_counts` is fine **only because it's currently the sole implemented
option** for that assay type — it is not a "pick the best method" judgment call. Once a second
engine exists for the same assay type (e.g., `edgeR`), this auto-selection logic must stop and
require an explicit user or wizard choice instead of silently picking one. Flag this in code
comments now so it isn't missed later.

**Fixtures:** valid two-group request · `paired: true` (must refuse MVP path, recommend future
repeated-measures workflow, not silently run unpaired) · assay_type/value_profile mismatch (new,
per fix #5) · covariate with no explicit reference level (new, per fix #6) · requested engine
incompatible with assay type.

**Acceptance gate:** the assay-type mismatch fixture fails here, before `stats.validate_design`
ever runs; `assumptions_applied` is non-empty and correctly worded on the covariate-reference
fixture.

---

### Part 4 — `stats.validate_design` — verify only (branch: `step/stats-validate-design` if not already built, else skip)

If Part 0 found this already built from the DE plan: confirm it accepts `design_spec.json` exactly
as produced by Part 3, with no changes needed. If it doesn't exist yet, build it per the DE Final
Build Plan's Sprint 2 spec unchanged — nothing in this guided layer alters that step's contract.

**Acceptance gate:** feeding Part 3's `design_spec.json` output straight into this step (using the
happy-path fixture) produces `validated: passed` with zero adaptation needed.

---

### Part 5 — `stats.build_contrasts` — verify only (branch: `step/stats-build-contrasts` if not already built, else skip)

Same posture as Part 4 — per the DE plan's Sprint 3 spec, unchanged. Confirm Part 3's
`contrast_spec.json` output is accepted as-is.

---

### Part 6 — `stats.filter_features` — amend (branch: `step/stats-filter-features-amend`)

**Fix #3, applied here:** filter spec becomes:
```json
{
  "mode": "count_prevalence",
  "min_count": 10,
  "min_samples_count": null,
  "min_samples_fraction": 0.5
}
```
Exactly one of `min_samples_count` / `min_samples_fraction` must be non-null — hard fail on both
or neither, mirroring the pathway plan's mutual-exclusivity pattern. When `min_samples_fraction`
is supplied, resolve to an absolute count via `ceil(n_samples × fraction)` and **record the
resolved absolute count in `filter_report.json`**, not just the fraction — so the report is
self-explanatory without cross-referencing sample count elsewhere.

**Fixtures:** everything already listed in the DE plan's Sprint 4, plus: fraction-based spec ·
count-based spec · both-set (hard fail) · neither-set (hard fail).

**Acceptance gate:** the two 6-sample example fixtures (fraction=0.5 and count=3) produce
identical `filtered_feature_matrix.tsv` output — proving the reconciliation is actually
equivalent, not just schema-legal.

---

### Part 7 — `stats.deseq2` — amend (branch: `step/stats-deseq2-amend`)

**Fixes #1 and #2, applied here.** Corrected interface.yaml:

```yaml
step_id: stats.deseq2
version: 0.2.0
language: R
entrypoint: bin/stats__deseq2.R
inputs:
  - {name: feature_matrix, type: file, format: tsv}
  - {name: sample_metadata, type: file, format: tsv}
  - {name: validated_design, type: file, format: json}
  - {name: resolved_contrasts, type: file, format: json}
outputs:
  - {name: results, type: file, format: tsv, schema: result_table_v1}
  - {name: diagnostics, type: file, format: json, schema: diagnostics_bundle_v1}
params:
  - {name: test_type, type: enum, values: [wald]}                    # lrt added when built, not before
  - {name: apply_shrinkage, type: bool}                               # no default
  - {name: shrinkage_method, type: enum, values: [apeglm]}            # normal/ashr added when built
  - {name: p_adjust_method, type: enum, values: [BH, BY, bonferroni, holm, none]}
  - {name: save_rds, type: bool}                                      # no default
container: null
```

**Why shrinkage stays in scope here even though the core DE plan deferred it:** raw unshrunken
log2 fold changes for low-count genes are genuinely misleading in a beginner-facing plain-language
report — this is a deliberate, reasoned extension of the core `stats.deseq2` v1 scope for this
specific guided product, not silent creep. It must still be a required, wizard-supplied value —
never a step-level default.

**Fixtures:** everything in the DE plan's Sprint 5, plus: `apply_shrinkage: true` with `apeglm` ·
`apply_shrinkage: false` (raw LFC, still schema-valid) · missing `apply_shrinkage` value entirely
(hard fail — proves there's no fallback).

**Acceptance gate:** omitting any one of the five params fails the step; the happy-path fixture
with shrinkage on produces a smaller-magnitude `effect_estimate` than the same fixture with
shrinkage off, on the same low-count synthetic gene (proves shrinkage is actually being applied,
not just accepted as a flag).

---

### Part 8 — `stats.combine_results` — verify only (branch: `step/stats-combine-results` if not already built, else skip)

Per the DE plan's Sprint 6, unchanged. With only one engine (DESeq2) in this MVP, this step still
matters — its schema-validation-before-concatenation behavior is what lets edgeR/limma plug in
later without touching `results.report_differential`.

---

### Part 9 — `stats.qc_diagnostics` — verify only (branch: `step/stats-qc-diagnostics` if not already built, else skip)

Per the DE plan's Sprint 7. One addition worth confirming during verification: the PCA transform
rule (VST if `save_rds` was true upstream, else `log2(normalized_count + 1)`) needs the resolved
`apply_shrinkage`/`save_rds` values from Part 7 threaded through correctly — check this wiring
explicitly since Part 7's amendment changed how those values are supplied.

---

### Part 10 — `results.report_differential` (branch: `step/results-report-differential`)

**Nextflow process skeleton:**
```groovy
process RESULTS_REPORT_DIFFERENTIAL {
    tag "${meta.id}"
    container null

    input:
    tuple val(meta), path(analysis_plan)
    path design_validation_report
    path filter_report
    path combined_results
    path combined_diagnostics
    path qc_report
    val adjusted_p_value_max        // REQUIRED, wizard-confirmed, no default
    val absolute_log2_fold_change_min  // REQUIRED, wizard-confirmed, no default

    output:
    tuple val(meta), path("differential_analysis_report.html"), emit: report
    tuple val(meta), path("significant_features.tsv"), emit: significant
    tuple val(meta), path("upregulated_features.tsv"), emit: upregulated
    tuple val(meta), path("downregulated_features.tsv"), emit: downregulated
    tuple val(meta), path("analysis_manifest.json"), emit: manifest

    script:
    """
    results__report_differential.py \\
        --analysis-plan ${analysis_plan} \\
        --design-validation-report ${design_validation_report} \\
        --filter-report ${filter_report} \\
        --combined-results ${combined_results} \\
        --combined-diagnostics ${combined_diagnostics} \\
        --qc-report ${qc_report} \\
        --adjusted-p-value-max ${adjusted_p_value_max} \\
        --absolute-log2-fold-change-min ${absolute_log2_fold_change_min} \\
        --out-report differential_analysis_report.html \\
        --out-significant significant_features.tsv \\
        --out-upregulated upregulated_features.tsv \\
        --out-downregulated downregulated_features.tsv \\
        --out-manifest analysis_manifest.json
    """
}
```

**`analysis_manifest.json` is the reproducibility record (fix #7 + the original master design
doc's reproducibility-metadata requirement) — must include, not just "parameters used":**
```
workflow/step versions (all nine atomic steps, not just deseq2)
tool/package versions (DESeq2, apeglm, R, python, pandas...)
input file checksums (feature matrix, sample metadata)
every resolved parameter from every step (filtering, shrinkage, p_adjust_method, thresholds)
assumptions_applied (carried through unchanged from analysis_plan.json)
run timestamp
```

**Significance filtering stays exactly as scoped in the draft — this part was correct:**
`adjusted_p_value_max`/`absolute_log2_fold_change_min` only ever filter the derived
`significant_features.tsv`; they never touch `combined_results.tsv`, which retains every tested
feature regardless of significance. Keep this.

**Fixtures:** happy path · zero significant features (valid, not an error) · all features
significant · missing threshold params (hard fail — no fallback to 0.05/1.0).

**Acceptance gate:** `analysis_manifest.json` alone (without any other output file) is sufficient
to describe exactly how to reproduce the run — every REQUIRED param from every upstream step
appears somewhere in it.

---

### Part 11 — Nextflow workflow integration (branch: `step/differential-rnaseq-mvp-workflow`)

Only wire steps that individually passed their own acceptance gate. `workflows/differential_rnaseq_mvp.nf`
chains Parts 2–10 exactly as drawn in §2. Each module exposes only declared files through `emit:` —
no untracked working-directory files pass between processes (draft's rule, unchanged, correct).

**Checks before this gate closes:** a hard failure at any step (especially Part 3's new
assay-type/reference-level checks) stops the whole chain with a message that reaches the UI
layer intact, not just a Nextflow stack trace.

---

### Part 12 — End-to-end fixture test + Definition of Done

Run `fixtures/rnaseq_two_group_happy_path/` through the full chain. Confirm every item in the
draft's §10 Definition of Done, plus:

```
assumptions_applied is populated and shown to the user before run confirmation
assay_type / value_profile mismatch is caught before DESeq2 runs
shrinkage on/off produces measurably different effect_estimate values
analysis_manifest.json alone documents every resolved parameter
```

---

## 4. Standing discipline (identical to the other two plans — reuse it)

1. Branch off latest `master`, one atomic step per branch — Parts 4/5/8/9 are "verify," not "skip
   the branch entirely," if any adaptation turns out to be needed.
2. Read the repo's atomic-step organization skill(s) + `AGENTS.md` + nearest `interface.yaml`
   before writing code — this is Part 0, and it applies again at the start of every subsequent part
   if you're unsure a convention still holds.
3. Implement only what this one part needs.
4. Run: unit tests, smoke test, metadata validation, registry generation, Docker-version
   validation, `git diff --check`.
5. Show `git status` + diff. **Do not stage or commit.**
6. Merge only after explicit go-ahead.

**Never ask Codex to:** build multiple atomic steps in one branch · give a step a default value
"so the wizard has something to fall back on" (the wizard supplies the value, the step never
does) · expose an enum option that isn't implemented yet · auto-select between two *equally valid*
engines for the same assay type once a second one exists.

---

## 5. Start today

```bash
cd /data/shared/vikash/survom-vikash-workflow
git switch master
git pull --ff-only
```

Run Part 0 (discovery, no branch, no code) first — its findings determine whether Parts 4, 5, 8,
and 9 are "verify a few hours' work" or "build from scratch," which changes your real timeline.
Only after Part 0's findings are in hand, branch for Part 1.
