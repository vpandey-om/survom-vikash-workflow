import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "bin/common__reference__salmon_index.py"
META = ROOT / "modules/local/common/reference/salmon_index/meta.yml"
MODULE = ROOT / "modules/local/common/reference/salmon_index/main.nf"
FIXTURE = ROOT / "tests/fixtures/salmon/transcripts.fa"


class SalmonIndexTests(unittest.TestCase):
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
        self.assertIn("--transcript-fasta", result.stdout)

    def test_metadata_declares_salmon_index_contract(self):
        metadata = json.loads(META.read_text(encoding="utf-8"))
        self.assertEqual(metadata["id"], "common.reference.salmon_index")
        self.assertEqual(metadata["version"], "0.1.0")
        self.assertEqual(metadata["implementation_path"], "bin/common__reference__salmon_index.py")
        self.assertEqual(metadata["process_name"], "SURVOM_COMMON_REFERENCE_SALMON_INDEX")
        self.assertEqual([input_["name"] for input_ in metadata["inputs"]], ["transcript_fasta"])
        self.assertEqual([output["name"] for output in metadata["outputs"]], ["salmon_index"])
        self.assertIsNone(metadata["container"])

    def test_module_uses_fixed_salmon_index_command(self):
        module_text = MODULE.read_text(encoding="utf-8")
        self.assertIn("salmon index", module_text)
        self.assertIn('--transcripts "${transcript_fasta}"', module_text)
        self.assertIn("--index salmon_index", module_text)
        self.assertIn('--threads "${task.cpus}"', module_text)
        self.assertIn("path(\"salmon_index\")", module_text)
        for unsupported in ["quant ", "quantmerge", "alevin", "--libType", "--decoys"]:
            self.assertNotIn(unsupported, module_text)

    def test_fixture_is_tiny_transcript_fasta(self):
        text = FIXTURE.read_text(encoding="utf-8")
        self.assertIn(">tx1", text)
        self.assertIn(">tx2", text)

    def test_metadata_validation_passes(self):
        result = self.run_command(
            [sys.executable, "tools/validate_atomic_metadata.py", "--project-root", ".", "--metadata-root", "modules/local"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_registry_generation_includes_salmon_index_record(self):
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
            self.assertIn("common.reference.salmon_index", ids)


if __name__ == "__main__":
    unittest.main()
