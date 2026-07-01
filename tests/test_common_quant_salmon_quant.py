import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "bin/common__quant__salmon_quant.py"
META = ROOT / "modules/local/common/quant/salmon_quant/meta.yml"
MODULE = ROOT / "modules/local/common/quant/salmon_quant/main.nf"
FIXTURE_DIR = ROOT / "tests/fixtures/salmon"


class SalmonQuantTests(unittest.TestCase):
    def run_command(self, args, cwd=ROOT):
        return subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_implementation_stub_declares_only_supported_layouts(self):
        help_result = self.run_command([sys.executable, str(HELPER), "--help"])
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("Contract stub only", help_result.stdout)
        self.assertIn("single", help_result.stdout)
        self.assertIn("paired", help_result.stdout)

        invalid = self.run_command([sys.executable, str(HELPER), "--read-layout", "umi"])
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("invalid choice", invalid.stderr)

    def test_metadata_declares_salmon_quant_contract(self):
        metadata = json.loads(META.read_text(encoding="utf-8"))
        self.assertEqual(metadata["id"], "common.quant.salmon_quant")
        self.assertEqual(metadata["version"], "0.1.0")
        self.assertEqual(metadata["implementation_path"], "bin/common__quant__salmon_quant.py")
        self.assertEqual(metadata["process_name"], "SURVOM_COMMON_QUANT_SALMON_QUANT")
        self.assertEqual([input_["name"] for input_ in metadata["inputs"]], ["salmon_index", "fastq_files"])
        self.assertEqual(
            [output["name"] for output in metadata["outputs"]],
            ["quant_sf", "cmd_info_json", "aux_info", "libParams"],
        )
        self.assertIsNone(metadata["container"])
        metadata_text = json.dumps(metadata).lower()
        for unsupported in ["alevin", "umi", "raw salmon flags", "library-type override", "tximport"]:
            self.assertNotIn(unsupported, metadata_text)

    def test_module_supports_single_and_paired_without_extra_features(self):
        module_text = MODULE.read_text(encoding="utf-8")
        self.assertIn("salmon quant", module_text)
        self.assertIn('--index "${salmon_index}"', module_text)
        self.assertIn("--libType A", module_text)
        self.assertIn("--mates1", module_text)
        self.assertIn("--mates2", module_text)
        self.assertIn("--unmated", module_text)
        self.assertIn("--validateMappings", module_text)
        self.assertIn("--output salmon_quant", module_text)
        self.assertIn('path("salmon_quant/quant.sf")', module_text)
        self.assertIn('path("salmon_quant/cmd_info.json")', module_text)
        self.assertIn('path("salmon_quant/aux_info")', module_text)
        self.assertIn('path("salmon_quant/libParams")', module_text)
        for unsupported in [
            "alevin",
            "--umi",
            "--libType ${",
            "library_type",
            "raw_flags",
            "--dumpEq",
            "--writeUnmappedNames",
            "--geneMap",
        ]:
            self.assertNotIn(unsupported, module_text)

    def test_fastq_fixtures_are_tiny_and_reviewable(self):
        for name in ["sample_single.fastq", "sample_R1.fastq", "sample_R2.fastq"]:
            text = (FIXTURE_DIR / name).read_text(encoding="utf-8")
            self.assertIn("@", text)
            self.assertIn("+", text)
            self.assertLess(len(text), 2048)

    def test_metadata_validation_passes(self):
        result = self.run_command(
            [sys.executable, "tools/validate_atomic_metadata.py", "--project-root", ".", "--metadata-root", "modules/local"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_registry_generation_includes_salmon_quant_record(self):
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
            self.assertIn("common.quant.salmon_quant", ids)


if __name__ == "__main__":
    unittest.main()
