import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "bin/common__qc__fastqc.py"
META = ROOT / "modules/local/common/qc/fastqc/meta.yml"
MODULE = ROOT / "modules/local/common/qc/fastqc/main.nf"


class FastQCTests(unittest.TestCase):
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

    def test_metadata_declares_only_native_fastqc_outputs(self):
        metadata = json.loads(META.read_text(encoding="utf-8"))
        self.assertEqual(metadata["version"], "0.1.0")
        self.assertEqual(metadata["implementation_path"], "bin/common__qc__fastqc.py")
        self.assertEqual(
            [output["name"] for output in metadata["outputs"]],
            ["fastqc_html", "fastqc_zip"],
        )
        self.assertNotIn("manifest", json.dumps(metadata).lower())

    def test_module_emits_only_native_fastqc_outputs(self):
        module_text = MODULE.read_text(encoding="utf-8")
        self.assertIn('path "fastqc/*_fastqc.html", emit: html', module_text)
        self.assertIn('path "fastqc/*_fastqc.zip", emit: zip', module_text)
        self.assertNotIn("fastqc_manifest", module_text)
        self.assertNotIn("common__qc__fastqc.py", module_text)

    def test_metadata_validation_passes(self):
        result = self.run_command(
            [sys.executable, "tools/validate_atomic_metadata.py", "--project-root", ".", "--metadata-root", "modules/local"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_registry_generation_includes_fastqc_record(self):
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
            self.assertIn("common.qc.fastqc", ids)


if __name__ == "__main__":
    unittest.main()
