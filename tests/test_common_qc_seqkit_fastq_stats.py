import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/seqkit_fastq_stats"
NORMALIZER = ROOT / "bin/common__qc__seqkit_fastq_stats.py"
SMOKE_SCRIPT = ROOT / "tools/run_seqkit_fastq_stats_smoke_test.sh"


class SeqkitFastqStatsTests(unittest.TestCase):
    def run_command(self, args, cwd=ROOT):
        return subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def normalize(self, seqkit_tsv, json_out, tsv_out):
        return self.run_command(
            [
                sys.executable,
                str(NORMALIZER),
                "--seqkit-tsv",
                str(seqkit_tsv),
                "--json-out",
                str(json_out),
                "--tsv-out",
                str(tsv_out),
            ]
        )

    def test_valid_seqkit_tsv_matches_expected_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_out = Path(tmp) / "summary.json"
            tsv_out = Path(tmp) / "summary.tsv"
            result = self.normalize(FIXTURES / "expected_seqkit_stats.tsv", json_out, tsv_out)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json_out.read_text(), (FIXTURES / "expected_summary.json").read_text())

    def test_numeric_fields_parse_as_expected_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_out = Path(tmp) / "summary.json"
            tsv_out = Path(tmp) / "summary.tsv"
            result = self.normalize(FIXTURES / "expected_seqkit_stats.tsv", json_out, tsv_out)
            self.assertEqual(result.returncode, 0, result.stderr)
            first = json.loads(json_out.read_text())["files"][0]
            self.assertIsInstance(first["num_seqs"], int)
            self.assertIsInstance(first["sum_len"], int)
            self.assertIsInstance(first["avg_len"], int)
            self.assertIsInstance(first["avg_qual"], float)
            self.assertEqual(first["num_seqs"], 2)
            self.assertEqual(first["sum_len"], 24)

    def test_fastq_fixtures_are_synthetic(self):
        expected_names = {
            "tiny_R1.fastq.gz": ["@SYNTH_R1_0001", "@SYNTH_R1_0002"],
            "tiny_R2.fastq.gz": ["@SYNTH_R2_0001", "@SYNTH_R2_0002"],
        }
        for filename, names in expected_names.items():
            result = self.run_command(["gzip", "-dc", str(FIXTURES / filename)])
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = result.stdout.splitlines()
            self.assertEqual(lines[0], names[0])
            self.assertEqual(lines[4], names[1])
            self.assertNotIn("HBR_Rep1", result.stdout)
            self.assertNotIn("ErccTranscripts", result.stdout)

    def test_json_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            first_json = Path(tmp) / "first.json"
            second_json = Path(tmp) / "second.json"
            first_tsv = Path(tmp) / "first.tsv"
            second_tsv = Path(tmp) / "second.tsv"
            first = self.normalize(FIXTURES / "expected_seqkit_stats.tsv", first_json, first_tsv)
            second = self.normalize(FIXTURES / "expected_seqkit_stats.tsv", second_json, second_tsv)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(first_json.read_bytes(), second_json.read_bytes())

    def test_tsv_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            first_json = Path(tmp) / "first.json"
            second_json = Path(tmp) / "second.json"
            first_tsv = Path(tmp) / "first.tsv"
            second_tsv = Path(tmp) / "second.tsv"
            first = self.normalize(FIXTURES / "expected_seqkit_stats.tsv", first_json, first_tsv)
            second = self.normalize(FIXTURES / "expected_seqkit_stats.tsv", second_json, second_tsv)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(first_tsv.read_bytes(), second_tsv.read_bytes())

    def test_missing_required_column_fails_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.normalize(
                FIXTURES / "malformed_missing_column.tsv",
                Path(tmp) / "summary.json",
                Path(tmp) / "summary.tsv",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing required column", result.stderr)
            self.assertIn("avg_len", result.stderr)

    def test_invalid_numeric_data_fails_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.tsv"
            lines = (FIXTURES / "expected_seqkit_stats.tsv").read_text().splitlines()
            header = lines[0].split("\t")
            first_row = lines[1].split("\t")
            first_row[header.index("sum_len")] = "not_a_number"
            bad.write_text("\n".join([lines[0], "\t".join(first_row), *lines[2:]]) + "\n", encoding="utf-8")
            result = self.normalize(bad, Path(tmp) / "summary.json", Path(tmp) / "summary.tsv")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not numeric", result.stderr)

    def test_empty_seqkit_tsv_header_only_returns_empty_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.tsv"
            header = (FIXTURES / "expected_seqkit_stats.tsv").read_text().splitlines()[0]
            empty.write_text(header + "\n", encoding="utf-8")
            json_out = Path(tmp) / "summary.json"
            result = self.normalize(empty, json_out, Path(tmp) / "summary.tsv")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(json_out.read_text())["files"], [])

    def test_metadata_validator_accepts_step_meta(self):
        result = self.run_command(
            [
                sys.executable,
                "tools/validate_atomic_metadata.py",
                "--project-root",
                ".",
                "--metadata-root",
                "modules/local",
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Validated ", result.stdout)
        self.assertIn("metadata file", result.stdout)

    def test_registry_generator_includes_seqkit_step(self):
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
            registry = json.loads(output.read_text())
            self.assertEqual(registry["step_count"], len(registry["steps"]))
            self.assertIn("common.qc.seqkit_fastq_stats", [step["id"] for step in registry["steps"]])

    def test_drift_tooling_detects_checksum_mismatch_without_version_bump(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            command = [
                sys.executable,
                "tools/sync_registry.py",
                "--project-root",
                ".",
                "--metadata-root",
                "modules/local",
                "--output",
                "registry.json",
            ]
            first = self.run_command(command, cwd=project)
            self.assertEqual(first.returncode, 0, first.stderr)
            impl = project / "bin/common__qc__seqkit_fastq_stats.py"
            impl.write_text(impl.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
            second = self.run_command(command, cwd=project)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("checksum drift detected without version bump", second.stderr)

    def test_smoke_script_rejects_missing_inputs_before_docker(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_command(
                [
                    str(SMOKE_SCRIPT),
                    "--r1",
                    str(Path(tmp) / "missing_R1.fastq.gz"),
                    "--r2",
                    str(Path(tmp) / "missing_R2.fastq.gz"),
                    "--out-dir",
                    str(Path(tmp) / "out"),
                ]
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("R1 FASTQ is missing or unreadable", result.stderr)

    def test_smoke_script_rejects_fixture_output_directory_before_docker(self):
        with tempfile.TemporaryDirectory() as tmp:
            r1 = Path(tmp) / "r1.fastq.gz"
            r2 = Path(tmp) / "r2.fastq.gz"
            r1.write_text("placeholder", encoding="utf-8")
            r2.write_text("placeholder", encoding="utf-8")
            result = self.run_command(
                [
                    str(SMOKE_SCRIPT),
                    "--r1",
                    str(r1),
                    "--r2",
                    str(r2),
                    "--out-dir",
                    str(FIXTURES),
                ]
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("outside tracked repository fixtures", result.stderr)


if __name__ == "__main__":
    unittest.main()
