import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "bin/common__reference__hisat2_index.py"
META = ROOT / "modules/local/common/reference/hisat2_index/meta.yml"
MODULE = ROOT / "modules/local/common/reference/hisat2_index/main.nf"
FIXTURE_DIR = ROOT / "tests/fixtures/hisat2"


class Hisat2IndexTests(unittest.TestCase):
    def run_command(self, args, cwd=ROOT):
        return subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_implementation_stub_is_help_only(self):
        result = self.run_command([sys.executable, str(HELPER), "--help"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Contract stub only", result.stdout)
        self.assertIn("--genome-fasta", result.stdout)
        self.assertIn("--annotation-gtf", result.stdout)

    def test_metadata_declares_hisat2_index_contract(self):
        metadata = json.loads(META.read_text(encoding="utf-8"))
        self.assertEqual(metadata["id"], "common.reference.hisat2_index")
        self.assertEqual(metadata["version"], "0.1.0")
        self.assertEqual(metadata["status"], "experimental")
        self.assertEqual(metadata["implementation_path"], "bin/common__reference__hisat2_index.py")
        self.assertEqual(metadata["process_name"], "SURVOM_COMMON_REFERENCE_HISAT2_INDEX")
        self.assertEqual([input_["name"] for input_ in metadata["inputs"]], ["genome_fasta", "annotation_gtf"])
        self.assertEqual([output["name"] for output in metadata["outputs"]], ["hisat2_index", "annotation_ss", "annotation_exon"])

    def test_module_uses_fixed_hisat2_index_commands(self):
        text = MODULE.read_text(encoding="utf-8")
        self.assertIn("hisat2_extract_splice_sites.py", text)
        self.assertIn("hisat2_extract_exons.py", text)
        self.assertIn("hisat2-build", text)
        self.assertIn("--ss annotation.ss", text)
        self.assertIn("--exon annotation.exon", text)
        self.assertIn("hisat2_index/reference", text)
        for unsupported in ["samtools", "StringTie", "--dta", "--rna-strandness", "--pen-noncansplice"]:
            self.assertNotIn(unsupported, text)

    def test_synthetic_fixtures_exist(self):
        self.assertIn(">chrSynthetic", (FIXTURE_DIR / "genome.fa").read_text(encoding="utf-8"))
        self.assertIn("gene_id", (FIXTURE_DIR / "annotation.gtf").read_text(encoding="utf-8"))

    def test_metadata_validation_passes(self):
        result = self.run_command(
            [sys.executable, "tools/validate_atomic_metadata.py", "--project-root", ".", "--metadata-root", "modules/local"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_registry_generation_includes_hisat2_index_record(self):
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
            self.assertIn("common.reference.hisat2_index", ids)


if __name__ == "__main__":
    unittest.main()
