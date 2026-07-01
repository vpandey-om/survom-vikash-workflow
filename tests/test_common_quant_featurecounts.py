import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "bin/common__quant__featurecounts.py"
META = ROOT / "modules/local/common/quant/featurecounts/meta.yml"
MODULE = ROOT / "modules/local/common/quant/featurecounts/main.nf"
FIXTURE_DIR = ROOT / "tests/fixtures/featurecounts"


class FeatureCountsTests(unittest.TestCase):
    def run_command(self, args, cwd=ROOT):
        return subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_implementation_stub_declares_paired_contract(self):
        result = self.run_command([sys.executable, str(HELPER), "--help"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Contract stub only", result.stdout)
        self.assertIn("--paired", result.stdout)

    def test_metadata_declares_featurecounts_contract(self):
        metadata = json.loads(META.read_text(encoding="utf-8"))
        self.assertEqual(metadata["id"], "common.quant.featurecounts")
        self.assertEqual(metadata["domain"], "common")
        self.assertEqual(metadata["category"], "quant")
        self.assertEqual(metadata["version"], "0.1.0")
        self.assertEqual(metadata["status"], "experimental")
        self.assertEqual(metadata["process_name"], "SURVOM_COMMON_QUANT_FEATURECOUNTS")
        self.assertEqual(metadata["implementation_path"], "bin/common__quant__featurecounts.py")
        self.assertEqual(metadata["validation"]["tier"], "unit_tested")
        self.assertIsNone(metadata["container"])
        self.assertEqual(metadata["omics"], ["genomics", "transcriptomics"])
        self.assertEqual(
            [input_["name"] for input_ in metadata["inputs"]],
            ["sample_id", "sorted_bam", "bam_index", "annotation_gtf"],
        )
        self.assertEqual([output["name"] for output in metadata["outputs"]], ["gene_counts_tsv", "gene_counts_summary"])

    def test_module_uses_only_default_featurecounts_command(self):
        text = MODULE.read_text(encoding="utf-8")
        self.assertIn("featureCounts \\", text)
        self.assertIn('-a "${annotation_gtf}"', text)
        self.assertIn("-o gene_counts.tsv", text)
        self.assertIn('-T "${task.cpus}"', text)
        self.assertIn("-p \\", text)
        self.assertIn("-t exon", text)
        self.assertIn("-g gene_id", text)
        self.assertIn('"${sorted_bam}"', text)
        self.assertIn('path("gene_counts.tsv")', text)
        self.assertIn('path("gene_counts.tsv.summary")', text)
        for unsupported in [
            "-B",
            "-C",
            "-s",
            "-M",
            "-O",
            "--fraction",
            "raw_options",
            "profile",
            "DESeq2",
            "edgeR",
            "strand",
        ]:
            self.assertNotIn(unsupported, text)

    def test_container_catalog_declares_pinned_subread_image(self):
        catalog = (ROOT / "containers/catalog/subread.yaml").read_text(encoding="utf-8")
        self.assertIn("tool: subread", catalog)
        self.assertIn('version: "2.1.1"', catalog)
        self.assertIn("survom/subread:2.1.1-dev", catalog)
        self.assertIn("quay.io/biocontainers/subread:2.1.1--h577a1d6_0", catalog)
        self.assertNotIn(":latest", catalog)

    def test_fixtures_are_reviewable(self):
        self.assertIn("gene_id", (FIXTURE_DIR / "annotation.gtf").read_text(encoding="utf-8"))
        self.assertIn("Geneid", (FIXTURE_DIR / "expected_gene_counts_header.txt").read_text(encoding="utf-8"))

    def test_metadata_validation_passes(self):
        result = self.run_command(
            [sys.executable, "tools/validate_atomic_metadata.py", "--project-root", ".", "--metadata-root", "modules/local"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_registry_generation_includes_featurecounts_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "registry.json"
            result = self.run_command(
                [
                    sys.executable,
                    "tools/sync_registry.py",
                    "--project-root",
                    ".",
                    "--metadata-root",
                    "modules/local",
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            registry = json.loads(output.read_text(encoding="utf-8"))
            ids = [record["id"] for record in registry["steps"]]
            self.assertIn("common.quant.featurecounts", ids)


if __name__ == "__main__":
    unittest.main()
