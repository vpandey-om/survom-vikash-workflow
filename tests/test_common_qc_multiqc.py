import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "bin/common__qc__multiqc.py"
META = ROOT / "modules/local/common/qc/multiqc/meta.yml"
MODULE = ROOT / "modules/local/common/qc/multiqc/main.nf"
FIXTURES = ROOT / "tests/fixtures/multiqc"
IMAGE = "survom/multiqc:1.35-dev"


class MultiQCTests(unittest.TestCase):
    def run_command(self, args, cwd=ROOT):
        return subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def docker_available(self):
        if not shutil.which("docker"):
            return False
        result = self.run_command(["docker", "image", "inspect", IMAGE])
        return result.returncode == 0

    def test_implementation_stub_is_help_only(self):
        result = self.run_command([sys.executable, str(HELPER), "--help"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Contract stub only", result.stdout)

    def test_metadata_declares_multiqc_identity_and_outputs(self):
        metadata = json.loads(META.read_text(encoding="utf-8"))
        self.assertEqual(metadata["id"], "common.qc.multiqc")
        self.assertEqual(metadata["version"], "0.1.0")
        self.assertEqual(metadata["process_name"], "SURVOM_COMMON_QC_MULTIQC")
        self.assertEqual(metadata["container"], None)
        self.assertEqual(metadata["implementation_path"], "bin/common__qc__multiqc.py")
        self.assertEqual(
            [output["name"] for output in metadata["outputs"]],
            ["multiqc_report", "multiqc_data"],
        )

    def test_module_uses_declared_fastqc_directory_and_native_outputs(self):
        module_text = MODULE.read_text(encoding="utf-8")
        self.assertIn("tuple val(sample_id), path(fastqc_reports_dir)", module_text)
        self.assertIn('find -L "${fastqc_reports_dir}"', module_text)
        self.assertIn('path "multiqc/multiqc_report.html", emit: report', module_text)
        self.assertIn('path "multiqc/multiqc_data", emit: data', module_text)
        self.assertIn("--data-dir", module_text)
        self.assertIn("mv multiqc/multiqc_report_data multiqc/multiqc_data", module_text)
        self.assertIn("no FastQC HTML or ZIP reports found", module_text)
        self.assertNotIn("multiqc_config", module_text)

    def test_metadata_validation_passes(self):
        result = self.run_command(
            [sys.executable, "tools/validate_atomic_metadata.py", "--project-root", ".", "--metadata-root", "modules/local"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_registry_generation_includes_multiqc_record(self):
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
            self.assertIn("common.qc.multiqc", ids)

    def test_multiqc_runs_on_synthetic_fastqc_report_fixtures(self):
        if not self.docker_available():
            self.skipTest(f"Docker image is unavailable: {IMAGE}")
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "multiqc"
            result = self.run_command(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-u",
                    f"{self.run_command(['id', '-u']).stdout.strip()}:{self.run_command(['id', '-g']).stdout.strip()}",
                    "-v",
                    f"{FIXTURES / 'fastqc_reports'}:/input:ro",
                    "-v",
                    f"{tmp}:/work",
                    "-w",
                    "/work",
                    IMAGE,
                    "sh",
                    "-lc",
                    (
                        "multiqc --outdir multiqc --filename multiqc_report.html --data-dir /input "
                        "&& mv multiqc/multiqc_report_data multiqc/multiqc_data"
                    ),
                ]
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((out_dir / "multiqc_report.html").is_file())
            self.assertTrue((out_dir / "multiqc_data").is_dir())

    def test_multiqc_fails_clearly_on_empty_input_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports = Path(tmp) / "empty_reports"
            reports.mkdir()
            result = self.run_command(
                [
                    "bash",
                    "-lc",
                    (
                        f"if ! find {reports} -maxdepth 1 -type f "
                        "\\( -name '*_fastqc.html' -o -name '*_fastqc.zip' \\) | grep -q .; then "
                        f"echo 'ERROR: no FastQC HTML or ZIP reports found in declared input directory: {reports}' >&2; exit 1; fi"
                    ),
                ]
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no FastQC HTML or ZIP reports found", result.stderr)


if __name__ == "__main__":
    unittest.main()
