import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "bin/common__preprocess__fastp.py"
META = ROOT / "modules/local/common/preprocess/fastp/meta.yml"
MODULE = ROOT / "modules/local/common/preprocess/fastp/main.nf"


class FastpTests(unittest.TestCase):
    def run_command(self, args, cwd=ROOT):
        return subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_implementation_stub_declares_only_approved_profiles(self):
        help_result = self.run_command([sys.executable, str(HELPER), "--help"])
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("Contract stub only", help_result.stdout)
        self.assertIn("default", help_result.stdout)
        self.assertIn("illumina_pe_q20", help_result.stdout)

        invalid = self.run_command([sys.executable, str(HELPER), "--trimming-profile", "raw_flags"])
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("invalid choice", invalid.stderr)

    def test_metadata_declares_fastp_v010_contract(self):
        metadata = json.loads(META.read_text(encoding="utf-8"))
        self.assertEqual(metadata["id"], "common.preprocess.fastp")
        self.assertEqual(metadata["version"], "0.1.0")
        self.assertEqual(metadata["implementation_path"], "bin/common__preprocess__fastp.py")
        self.assertEqual(metadata["process_name"], "SURVOM_COMMON_PREPROCESS_FASTP")
        self.assertEqual(
            [input_["name"] for input_ in metadata["inputs"]],
            ["fastq_files", "trimming_profile"],
        )
        self.assertIn("Allowed values: default, illumina_pe_q20", json.dumps(metadata))
        metadata_text = json.dumps(metadata).lower()
        for unsupported in [
            "raw fastp flags",
            "cut_front",
            "trim_poly_x",
            "merging",
            "deduplication",
            "unpaired",
            "failed-read",
            "custom adapters",
        ]:
            self.assertNotIn(unsupported, metadata_text)

    def test_module_supports_exactly_two_profiles_without_raw_flags(self):
        module_text = MODULE.read_text(encoding="utf-8")
        self.assertIn('trimming_profile in ["default", "illumina_pe_q20"]', module_text)
        self.assertIn("Unsupported fastp trimming_profile", module_text)
        self.assertIn("requires paired-end input", module_text)
        self.assertIn("--detect_adapter_for_pe", module_text)
        self.assertIn("--cut_tail", module_text)
        self.assertIn("--cut_window_size 4", module_text)
        self.assertIn("--cut_mean_quality 20", module_text)
        self.assertIn("--length_required 30", module_text)

        for unsupported in [
            "--cut_front",
            "--trim_poly_x",
            "--umi",
            "--merge",
            "--dedup",
            "--unpaired",
            "--failed_out",
            "--adapter_sequence",
            "--adapter_fasta",
        ]:
            self.assertNotIn(unsupported, module_text)

    def test_metadata_validation_passes(self):
        result = self.run_command(
            [sys.executable, "tools/validate_atomic_metadata.py", "--project-root", ".", "--metadata-root", "modules/local"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_registry_generation_includes_fastp_record(self):
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
            self.assertIn("common.preprocess.fastp", ids)


if __name__ == "__main__":
    unittest.main()
