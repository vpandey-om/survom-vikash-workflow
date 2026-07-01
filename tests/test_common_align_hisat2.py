import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "bin/common__align__hisat2.py"
META = ROOT / "modules/local/common/align/hisat2/meta.yml"
MODULE = ROOT / "modules/local/common/align/hisat2/main.nf"
FIXTURE_DIR = ROOT / "tests/fixtures/hisat2"


class Hisat2AlignTests(unittest.TestCase):
    def run_command(self, args, cwd=ROOT):
        return subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_implementation_stub_declares_paired_only_contract(self):
        result = self.run_command([sys.executable, str(HELPER), "--help"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Contract stub only", result.stdout)
        self.assertIn("--paired", result.stdout)

    def test_metadata_declares_hisat2_align_contract(self):
        metadata = json.loads(META.read_text(encoding="utf-8"))
        self.assertEqual(metadata["id"], "common.align.hisat2")
        self.assertEqual(metadata["version"], "0.1.0")
        self.assertEqual(metadata["status"], "experimental")
        self.assertEqual(metadata["implementation_path"], "bin/common__align__hisat2.py")
        self.assertEqual(metadata["process_name"], "SURVOM_COMMON_ALIGN_HISAT2")
        self.assertEqual([input_["name"] for input_ in metadata["inputs"]], ["sample_id", "paired_fastq_files", "hisat2_index"])
        self.assertEqual([output["name"] for output in metadata["outputs"]], ["sorted_bam", "sorted_bam_bai", "hisat2_alignment_summary"])

    def test_module_uses_restricted_hisat2_samtools_pipeline(self):
        text = MODULE.read_text(encoding="utf-8")
        self.assertIn("hisat2 \\", text)
        self.assertIn('-x "${hisat2_index}/reference"', text)
        self.assertIn("-1", text)
        self.assertIn("-2", text)
        self.assertIn("--dta", text)
        self.assertIn('-p "${task.cpus}"', text)
        self.assertIn("--summary-file hisat2_alignment_summary.txt", text)
        self.assertIn("samtools sort", text)
        self.assertIn("samtools index", text)
        for unsupported in ["--rna-strandness", " FR", " RF", "--pen-noncansplice", "--pen-cansplice", "--max-intronlen", "StringTie"]:
            self.assertNotIn(unsupported, text)

    def test_fastq_fixtures_are_paired_and_reviewable(self):
        for name in ["sample_R1.fastq", "sample_R2.fastq"]:
            text = (FIXTURE_DIR / name).read_text(encoding="utf-8")
            self.assertIn("@synthetic_pair", text)
            self.assertLess(len(text), 256)

    def test_metadata_validation_passes(self):
        result = self.run_command(
            [sys.executable, "tools/validate_atomic_metadata.py", "--project-root", ".", "--metadata-root", "modules/local"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_registry_generation_includes_hisat2_align_record(self):
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
            self.assertIn("common.align.hisat2", ids)


if __name__ == "__main__":
    unittest.main()
