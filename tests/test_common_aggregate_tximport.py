import csv
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "bin/common__aggregate__tximport.R"
META = ROOT / "modules/local/common/aggregate/tximport/meta.yml"
MODULE = ROOT / "modules/local/common/aggregate/tximport/main.nf"
FIXTURE_DIR = ROOT / "tests/fixtures/tximport"
IMAGE = "survom/tximport:3.21-dev"


class TximportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            ["docker", "image", "inspect", IMAGE],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise unittest.SkipTest(f"Docker image is unavailable: {IMAGE}")

    def run_command(self, args, cwd=ROOT):
        return subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def run_tximport(self, fixture_dir, samples="samples.tsv", tx2gene="tx2gene.tsv"):
        out_dir = fixture_dir / "out"
        return self.run_command(
            [
                "docker",
                "run",
                "--rm",
                "-u",
                f"{ROOT.stat().st_uid}:{ROOT.stat().st_gid}",
                "-v",
                f"{ROOT}:/repo",
                "-w",
                "/repo",
                IMAGE,
                "Rscript",
                "bin/common__aggregate__tximport.R",
                "--samples",
                f"/repo/{fixture_dir.relative_to(ROOT) / samples}",
                "--tx2gene",
                f"/repo/{fixture_dir.relative_to(ROOT) / tx2gene}",
                "--outdir",
                f"/repo/{out_dir.relative_to(ROOT)}",
            ]
        )

    def copy_fixture(self):
        tmp = tempfile.TemporaryDirectory(dir=ROOT / "tests/fixtures/tximport")
        path = Path(tmp.name)
        for item in FIXTURE_DIR.iterdir():
            if item.name.startswith("tmp"):
                continue
            if item.is_dir():
                shutil.copytree(item, path / item.name)
            else:
                shutil.copy2(item, path / item.name)
        self.addCleanup(tmp.cleanup)
        return path

    def read_tsv(self, path):
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))

    def test_metadata_declares_tximport_contract(self):
        metadata = json.loads(META.read_text(encoding="utf-8"))
        self.assertEqual(metadata["id"], "common.aggregate.tximport")
        self.assertEqual(metadata["version"], "0.1.0")
        self.assertEqual(metadata["status"], "experimental")
        self.assertEqual(metadata["process_name"], "SURVOM_COMMON_AGGREGATE_TXIMPORT")
        self.assertEqual(metadata["implementation_path"], "bin/common__aggregate__tximport.R")
        self.assertEqual(metadata["omics"], ["genomics", "transcriptomics"])
        self.assertEqual([input_["name"] for input_ in metadata["inputs"]], ["samples_tsv", "tx2gene_tsv"])
        self.assertEqual(
            [output["name"] for output in metadata["outputs"]],
            ["gene_counts_tsv", "gene_abundance_tsv", "gene_lengths_tsv"],
        )
        metadata_text = json.dumps(metadata).lower()
        for unsupported in ["deseq2", "edger", "normalization", "filtering", "differential expression"]:
            self.assertNotIn(unsupported, metadata_text)

    def test_module_uses_r_helper_and_declared_outputs(self):
        text = MODULE.read_text(encoding="utf-8")
        self.assertIn("SURVOM_COMMON_AGGREGATE_TXIMPORT", text)
        self.assertIn("common__aggregate__tximport.R", text)
        self.assertIn("--samples", text)
        self.assertIn("--tx2gene", text)
        self.assertIn('path("tximport/gene_counts.tsv")', text)
        self.assertIn('path("tximport/gene_abundance.tsv")', text)
        self.assertIn('path("tximport/gene_lengths.tsv")', text)
        for unsupported in ["DESeq2", "edgeR", "filter", "countsFromAbundance", "txOut"]:
            self.assertNotIn(unsupported, text)

    def test_deterministic_gene_outputs(self):
        fixture = self.copy_fixture()
        result = self.run_tximport(fixture)
        self.assertEqual(result.returncode, 0, result.stderr)

        counts = self.read_tsv(fixture / "out/gene_counts.tsv")
        abundance = self.read_tsv(fixture / "out/gene_abundance.tsv")
        lengths = self.read_tsv(fixture / "out/gene_lengths.tsv")

        self.assertEqual([row["gene_id"] for row in counts], ["gene_alpha", "gene_beta"])
        self.assertEqual(counts[0]["sample_A"], "10.00000000")
        self.assertEqual(counts[0]["sample_B"], "10.00000000")
        self.assertEqual(counts[1]["sample_A"], "10.00000000")
        self.assertEqual(counts[1]["sample_B"], "10.00000000")
        self.assertEqual(abundance[0]["sample_A"], "50.00000000")
        self.assertEqual(abundance[0]["sample_B"], "50.00000000")
        self.assertEqual(abundance[1]["sample_A"], "50.00000000")
        self.assertEqual(abundance[1]["sample_B"], "50.00000000")
        self.assertEqual(lengths[0]["sample_A"], "80.00000000")
        self.assertEqual(lengths[0]["sample_B"], "80.00000000")
        self.assertEqual(lengths[1]["sample_A"], "100.0000000")
        self.assertEqual(lengths[1]["sample_B"], "100.0000000")

    def assert_failure_contains(self, fixture, expected):
        result = self.run_tximport(fixture)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(expected, result.stderr)

    def test_rejects_bad_sample_sheet_header(self):
        fixture = self.copy_fixture()
        (fixture / "samples.tsv").write_text("sample\tquant_sf\nsample_A\tsample1/quant.sf\n", encoding="utf-8")
        self.assert_failure_contains(fixture, "samples.tsv must have header")

    def test_rejects_duplicate_sample_ids(self):
        fixture = self.copy_fixture()
        (fixture / "samples.tsv").write_text(
            "sample_id\tquant_sf\nsample_A\tsample1/quant.sf\nsample_A\tsample2/quant.sf\n",
            encoding="utf-8",
        )
        self.assert_failure_contains(fixture, "duplicate sample_id")

    def test_rejects_missing_quant_sf(self):
        fixture = self.copy_fixture()
        (fixture / "samples.tsv").write_text(
            "sample_id\tquant_sf\nsample_A\tsample1/quant.sf\nsample_B\tmissing/quant.sf\n",
            encoding="utf-8",
        )
        self.assert_failure_contains(fixture, "quant_sf file does not exist")

    def test_rejects_malformed_tx2gene_header(self):
        fixture = self.copy_fixture()
        (fixture / "tx2gene.tsv").write_text("tx\tgene\nx\ty\n", encoding="utf-8")
        self.assert_failure_contains(fixture, "tx2gene.tsv must have header")

    def test_rejects_duplicate_transcript_ids(self):
        fixture = self.copy_fixture()
        (fixture / "tx2gene.tsv").write_text(
            "transcript_id\tgene_id\ntx1\tgene_alpha\ntx1\tgene_beta\n",
            encoding="utf-8",
        )
        self.assert_failure_contains(fixture, "duplicate transcript_id")

    def test_rejects_zero_shared_transcripts(self):
        fixture = self.copy_fixture()
        (fixture / "tx2gene.tsv").write_text(
            "transcript_id\tgene_id\nmissing_tx\tgene_alpha\nother_tx\tgene_beta\n",
            encoding="utf-8",
        )
        self.assert_failure_contains(fixture, "zero shared transcript IDs")

    def test_metadata_validation_passes(self):
        result = self.run_command(
            [sys.executable, "tools/validate_atomic_metadata.py", "--project-root", ".", "--metadata-root", "modules/local"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_registry_generation_includes_tximport_record(self):
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
            self.assertIn("common.aggregate.tximport", ids)


if __name__ == "__main__":
    unittest.main()
