import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "bin/common__aggregate__salmon_quantmerge.py"
META = ROOT / "modules/local/common/aggregate/salmon_quantmerge/meta.yml"
MODULE = ROOT / "modules/local/common/aggregate/salmon_quantmerge/main.nf"
FIXTURE_DIR = ROOT / "tests/fixtures/salmon"


class SalmonQuantmergeTests(unittest.TestCase):
    def run_command(self, args, cwd=ROOT):
        return subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_implementation_stub_declares_only_numreads_column(self):
        help_result = self.run_command([sys.executable, str(HELPER), "--help"])
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("Contract stub only", help_result.stdout)
        self.assertIn("NumReads", help_result.stdout)

        invalid = self.run_command([sys.executable, str(HELPER), "--column", "TPM"])
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("invalid choice", invalid.stderr)

    def test_metadata_declares_salmon_quantmerge_contract(self):
        metadata = json.loads(META.read_text(encoding="utf-8"))
        self.assertEqual(metadata["id"], "common.aggregate.salmon_quantmerge")
        self.assertEqual(metadata["version"], "0.1.0")
        self.assertEqual(metadata["implementation_path"], "bin/common__aggregate__salmon_quantmerge.py")
        self.assertEqual(metadata["process_name"], "SURVOM_COMMON_AGGREGATE_SALMON_QUANTMERGE")
        self.assertEqual([input_["name"] for input_ in metadata["inputs"]], ["quant_files"])
        self.assertEqual([output["name"] for output in metadata["outputs"]], ["salmon_counts_tsv"])
        self.assertIsNone(metadata["container"])

    def test_module_uses_fixed_salmon_quantmerge_command(self):
        module_text = MODULE.read_text(encoding="utf-8")
        self.assertIn("salmon quantmerge", module_text)
        self.assertIn("--quants", module_text)
        self.assertIn("--column NumReads", module_text)
        self.assertIn("--output salmon_counts.tsv", module_text)
        self.assertIn("requires two or more quant.sf files", module_text)
        self.assertIn("quantmerge_inputs", module_text)
        self.assertIn("/quant.sf", module_text)
        for unsupported in ["--column TPM", "tximport", "deseq2", "edger", "raw_flags", "alevin"]:
            self.assertNotIn(unsupported, module_text.lower())

    def test_quant_sf_fixtures_are_tiny_and_reviewable(self):
        for name in ["sample1_quant.sf", "sample2_quant.sf"]:
            text = (FIXTURE_DIR / name).read_text(encoding="utf-8")
            self.assertIn("Name\tLength\tEffectiveLength\tTPM\tNumReads", text)
            self.assertIn("tx1", text)
            self.assertLess(len(text), 512)

    def test_metadata_validation_passes(self):
        result = self.run_command(
            [sys.executable, "tools/validate_atomic_metadata.py", "--project-root", ".", "--metadata-root", "modules/local"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_registry_generation_includes_salmon_quantmerge_record(self):
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
            self.assertIn("common.aggregate.salmon_quantmerge", ids)


if __name__ == "__main__":
    unittest.main()
