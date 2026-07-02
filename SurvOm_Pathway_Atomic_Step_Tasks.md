# SurvOm Pathway Enrichment — Atomic Step Task Blocks (v1)

Six tasks, one atomic step each, in build order. Paste each block to Codex individually — do not
combine two. `registry.json` is only ever touched via `tools/sync_registry.py`, never edited by
hand, in every block below.

Naming derivation used throughout (inferred from your `common.differential.report` example —
confirm against `registry.json` before running Task 1):
- Registry ID: `common.pathway.<step>` (3-segment dot path)
- Process name: `SURVOM_` + registry ID, upper-cased, dots → underscores
- Module path: `modules/local/common/pathway/<step>/{meta.yml,main.nf}`
- bin script: `bin/common__pathway__<step>.py` (dots → double underscore; `.R` instead of `.py`
  for any future R-based step, e.g. `gsea`)
- Smoke test: `scripts/smoke_test_common_pathway_<step>.sh`
- Fixtures: `tests/fixtures/common_pathway_<step>/`

---

## Task 1 — validate_input

```
# Owner Approval — Atomic Step Task

Implement only: common.pathway.validate_input

Registry ID: common.pathway.validate_input
Version: 0.1.0
Status: experimental
Process name: SURVOM_COMMON_PATHWAY_VALIDATE_INPUT
Validation intent: validate ORA or GSEA enrichment input structure, selection or ranking policy,
and background-universe consistency (selected features must be a subset of the background
universe) before any identifier mapping or enrichment runs

## Approved editable paths
```text
modules/local/common/pathway/validate_input/meta.yml
modules/local/common/pathway/validate_input/main.nf
bin/common__pathway__validate_input.py
scripts/smoke_test_common_pathway_validate_input.sh
tests/fixtures/common_pathway_validate_input/
registry.json
```

registry.json may change only through:
```bash
python tools/sync_registry.py --project-root . --metadata-root modules/local --output registry.json
```
```

**Required behavior to hold Codex to:** `selection_column` and any threshold field
(`adjusted_p_value_max`, `effect_abs_min`) are mutually exclusive — hard fail if both or neither
are set. If `direction != both` is requested downstream, this step must fail now if no `direction`
column exists in the input, not later inside `overrepresentation`.

---

## Task 2 — resolve_identifiers

```
# Owner Approval — Atomic Step Task

Implement only: common.pathway.resolve_identifiers

Registry ID: common.pathway.resolve_identifiers
Version: 0.1.0
Status: experimental
Process name: SURVOM_COMMON_PATHWAY_RESOLVE_IDENTIFIERS
Validation intent: resolve selected/ranked feature identifiers AND the background universe into
the gene-set database's identifier namespace, with explicit ambiguous/unmapped/duplicate
handling policies and no default values for any policy

## Approved editable paths
```text
modules/local/common/pathway/resolve_identifiers/meta.yml
modules/local/common/pathway/resolve_identifiers/main.nf
bin/common__pathway__resolve_identifiers.py
scripts/smoke_test_common_pathway_resolve_identifiers.sh
tests/fixtures/common_pathway_resolve_identifiers/
registry.json
```

registry.json may change only through:
```bash
python tools/sync_registry.py --project-root . --metadata-root modules/local --output registry.json
```
```

**Required behavior:** `ambiguous_mapping_policy`, `unmapped_identifier_policy`,
`duplicate_resolved_identifier_policy` are all REQUIRED params, no defaults. This step emits
**two** resolved outputs — `resolved_identifiers.tsv` and `resolved_background_universe.tsv` —
not just one; the background universe must land in the same namespace as the gene sets or ORA
overlap math downstream is wrong.

---

## Task 3 — validate_gene_sets

```
# Owner Approval — Atomic Step Task

Implement only: common.pathway.validate_gene_sets

Registry ID: common.pathway.validate_gene_sets
Version: 0.1.0
Status: experimental
Process name: SURVOM_COMMON_PATHWAY_VALIDATE_GENE_SETS
Validation intent: validate a gene-set database manifest and GMT file (required metadata fields,
checksum match against the file on disk, gene-set ID uniqueness, size limits) before use in
enrichment testing

## Approved editable paths
```text
modules/local/common/pathway/validate_gene_sets/meta.yml
modules/local/common/pathway/validate_gene_sets/main.nf
bin/common__pathway__validate_gene_sets.py
scripts/smoke_test_common_pathway_validate_gene_sets.sh
tests/fixtures/common_pathway_validate_gene_sets/
registry.json
```

registry.json may change only through:
```bash
python tools/sync_registry.py --project-root . --metadata-root modules/local --output registry.json
```
```

**Required behavior:** `min_gene_set_size`/`max_gene_set_size` are REQUIRED, no defaults. A
manifest missing `release_version`, `retrieval_date`, `source_url`, `license_note`, or
`checksum_sha256` fails validation. A checksum mismatch between the manifest and the actual GMT
file on disk fails validation.

**This is the step your Reactome/GO BP input feeds — see the bootstrap section below before
writing this task's fixtures.**

---

## Task 4 — overrepresentation

```
# Owner Approval — Atomic Step Task

Implement only: common.pathway.overrepresentation

Registry ID: common.pathway.overrepresentation
Version: 0.1.0
Status: experimental
Process name: SURVOM_COMMON_PATHWAY_OVERREPRESENTATION
Validation intent: run Fisher exact or hypergeometric over-representation analysis of a resolved
selected feature set against a resolved background universe and validated gene sets, emitting the
standardized enrichment result table with unique-resolved-id overlap counting

## Approved editable paths
```text
modules/local/common/pathway/overrepresentation/meta.yml
modules/local/common/pathway/overrepresentation/main.nf
bin/common__pathway__overrepresentation.py
scripts/smoke_test_common_pathway_overrepresentation.sh
tests/fixtures/common_pathway_overrepresentation/
registry.json
```

registry.json may change only through:
```bash
python tools/sync_registry.py --project-root . --metadata-root modules/local --output registry.json
```
```

**Required behavior:** `test_method`, `p_adjust_method`, `direction` are REQUIRED, no defaults.
`overlap_count` must count unique resolved IDs, never raw input rows — a one-to-many mapping
under `retain_all` must not inflate the count.

---

## Task 5 — combine_results

```
# Owner Approval — Atomic Step Task

Implement only: common.pathway.combine_results

Registry ID: common.pathway.combine_results
Version: 0.1.0
Status: experimental
Process name: SURVOM_COMMON_PATHWAY_COMBINE_RESULTS
Validation intent: validate and concatenate enrichment result tables across databases and
contrasts into one schema-checked combined table, with no cross-method or cross-database-version
consensus scoring of any kind

## Approved editable paths
```text
modules/local/common/pathway/combine_results/meta.yml
modules/local/common/pathway/combine_results/main.nf
bin/common__pathway__combine_results.py
scripts/smoke_test_common_pathway_combine_results.sh
tests/fixtures/common_pathway_combine_results/
registry.json
```

registry.json may change only through:
```bash
python tools/sync_registry.py --project-root . --metadata-root modules/local --output registry.json
```
```

**Required behavior:** if two inputs share `database_id` but differ in `database_version`, fail
unless `allow_mixed_database_versions=true` (REQUIRED param, no default) — and even then, keep
versions as separately labeled rows.

---

## Task 6 — qc_diagnostics

```
# Owner Approval — Atomic Step Task

Implement only: common.pathway.qc_diagnostics

Registry ID: common.pathway.qc_diagnostics
Version: 0.1.0
Status: experimental
Process name: SURVOM_COMMON_PATHWAY_QC_DIAGNOSTICS
Validation intent: generate transparent enrichment diagnostics (mapping counts, background
universe size pre/post mapping, gene-set size distribution, database version and checksum) and
optional parameter-controlled plots from combined pathway results

## Approved editable paths
```text
modules/local/common/pathway/qc_diagnostics/meta.yml
modules/local/common/pathway/qc_diagnostics/main.nf
bin/common__pathway__qc_diagnostics.py
scripts/smoke_test_common_pathway_qc_diagnostics.sh
tests/fixtures/common_pathway_qc_diagnostics/
registry.json
```

registry.json may change only through:
```bash
python tools/sync_registry.py --project-root . --metadata-root modules/local --output registry.json
```
```

**Required behavior:** significant-pathway count in the diagnostics is based on user-supplied
criteria only — never a hard-coded 0.05.

---

# Input preparation — what you actually need to gather

`common.pathway.download_gene_sets` (the automated downloader) is Phase 2, deliberately deferred.
To get a *real* first ORA result out of Task 4 rather than just a synthetic fixture, you need to
manually stage two things: a Reactome gene-set file, and one more database (GO BP is the natural
second one, per the pathway plan's v1 scope). Neither of these is an atomic step — this is prep
work you do by hand, once, outside Nextflow.

## Reactome (recommended first database — easiest, no account needed)

Reactome publishes its own ready-made GMT directly, no login required:

- File: **Reactome Pathways Gene Set** — `https://download.reactome.org/version/ReactomePathways.gmt.zip`
- For a *fixed, reproducible* version rather than "whatever is current today," use Reactome's
  Zenodo archive instead — they've published a versioned snapshot every quarter since release 89
  (June 2024): `https://zenodo.org/records/15126939` (check for the latest record matching the
  release you want). This gives you a stable DOI and a file that won't change under you, which is
  exactly what `release_version` + `checksum_sha256` in the manifest are supposed to protect.
- License: Creative Commons (see `https://reactome.org/license` for the exact terms) — fill this
  into `license_note`.
- **Before writing the manifest, inspect the file yourself** to confirm the identifier namespace —
  don't assume:
  ```bash
  unzip -p ReactomePathways.gmt.zip | head -3 | cut -f1-4
  ```
  Reactome's own GMT has historically used UniProt accessions in some releases and gene symbols in
  others — check the actual gene tokens (do they look like `P04637` (UniProt), `ENSG00000141510`
  (Ensembl), or `TP53` (symbol)?) and set `identifier_namespace` accordingly. This determines what
  `target_namespace` you pass to `resolve_identifiers` later.
- Alternative if you specifically want Ensembl gene IDs without any symbol/UniProt conversion step:
  Reactome also publishes a direct Ensembl-to-pathway mapping file —
  `https://download.reactome.org/version/Ensembl2Reactome_All_Levels.txt` — a flat two-column
  mapping rather than GMT format, but trivially convertible to GMT (group by pathway ID) and
  guarantees `ensembl_gene_id` as the namespace with no ambiguity.

**Manifest fields to fill in by hand** (per `GeneSetDatabaseManifest v1` from the pathway plan):
```yaml
database_id: reactome_hs
name: Reactome Human Pathways
organism: Homo sapiens
identifier_namespace: <confirmed by inspecting the file — see above>
gene_set_format: gmt
release_version: <e.g. "Reactome 92" — check https://reactome.org/about/release-calendar for the exact number>
retrieval_date: <date you actually downloaded it>
source_url: https://download.reactome.org/version/ReactomePathways.gmt.zip
license_note: "Creative Commons — see https://reactome.org/license"
checksum_sha256: <run: sha256sum ReactomePathways.gmt>
local_path: /data/shared/vikash/survom-storage/pathway-databases/reactome/
```

## GO Biological Process (second database)

Two real options, genuinely different tradeoffs:

1. **MSigDB's `C5:GO:BP` collection** — single ready-made GMT, gene symbols or Entrez IDs, but
   requires free registration at `gsea-msigdb.org` and is licensed **CC BY 4.0** (Broad Institute) —
   easiest path, one file, no assembly required.
2. **Gene Ontology's own OBO + GAF files** — `go-basic.obo` + `goa_human.gaf` from
   `geneontology.org` — no registration, but you have to build the GMT yourself (propagate GO term
   hierarchy, filter to biological_process namespace, exclude/include evidence codes like IEA per
   your own policy). More faithful to the primary source, more work.

For a first real run, I'd start with MSigDB's `C5:GO:BP` — it's a single file, well-documented
identifier handling, and the license terms are unambiguous. Switch to building it from OBO+GAF
directly later if you need control over evidence-code filtering that MSigDB's pre-built file
doesn't expose.

**Manifest fields — same shape as Reactome above**, with `database_id: go_bp_hs`,
`gene_set_format: gmt`, `license_note: "CC BY 4.0 — Broad Institute, see https://www.gsea-msigdb.org/gsea/msigdb/license_terms.jsp"`.

## Identifier mapping source (needed by Task 2, separate from the gene-set databases)

`resolve_identifiers` also needs a `mapping_source_manifest` — this is not the same thing as the
gene-set database manifests above. Two reasonable choices:

1. **Bioconductor `org.Hs.eg.db`** — versioned with each Bioconductor release, handles
   Ensembl ↔ Entrez ↔ HGNC symbol mapping, easiest to keep reproducible since the Bioconductor
   release number *is* the version to record.
2. **Ensembl BioMart export** — a flat TSV you generate yourself (Ensembl Gene ID, Entrez Gene ID,
   HGNC Symbol columns), gives you a concrete file to checksum, but you own re-generating it when
   Ensembl updates.

I'd default to `org.Hs.eg.db` for v1 — it's what most of the R-based enrichment ecosystem already
assumes, and "record the Bioconductor release version" is a cleaner reproducibility story than
"record the date I ran a BioMart query."

---

# Suggested order of operations

1. Confirm the `common.pathway.*` naming guess against `registry.json` (see the grep command above).
2. Download and checksum the Reactome GMT, write its manifest by hand.
3. Run Task 1 through Task 6, one at a time, each with your explicit go-ahead before merge.
4. Once Task 3 is merged, validate the real Reactome file through it (not just the synthetic
   fixture) before moving to Task 4.
5. Add the GO BP manifest once Reactome's path is proven end-to-end — don't stage both databases
   before Task 3 exists; you won't know if your manifest format is even right yet.
