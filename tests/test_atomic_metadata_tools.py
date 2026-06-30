import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def base_meta():
    return {
        "aliases": ["simple-de-test"],
        "category": "de",
        "container": None,
        "deprecation": {"deprecated_by": None, "reason": None},
        "description": "Fixture-only transcriptomics differential expression step.",
        "display_name": "Simple DE test",
        "domain": "transcriptomics",
        "id": "transcriptomics.de.simple_de_test",
        "implementation_path": "bin/transcriptomics__de__simple_de_test.py",
        "inputs": [],
        "language": "python",
        "module_path": "modules/local/transcriptomics/de/simple_de_test",
        "omics": ["transcriptomics"],
        "outputs": [],
        "owners": [],
        "process_name": "SURVOM_TRANSCRIPTOMICS_DE_SIMPLE_DE_TEST",
        "reviewers": [],
        "schema_version": 1,
        "status": "experimental",
        "validation": {"evidence": [], "tier": "unit_tested"},
        "version": "0.1.0",
    }


def write_fixture_project(project: Path, meta=None, meta_rel=None, create_impl=True):
    meta = meta or base_meta()
    meta_rel = meta_rel or Path("modules/local/transcriptomics/de/simple_de_test/meta.yml")
    meta_path = project / meta_rel
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if create_impl:
        impl_path = project / "bin/transcriptomics__de__simple_de_test.py"
        impl_path.parent.mkdir(parents=True, exist_ok=True)
        impl_path.write_text("print('fixture')\n", encoding="utf-8")
    return meta_path


class AtomicMetadataToolTests(unittest.TestCase):
    def run_tool(self, *args, cwd=ROOT):
        return subprocess.run(
            [sys.executable, *args],
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def validate_project(self, project: Path, *extra):
        return self.run_tool(
            str(ROOT / "tools/validate_atomic_metadata.py"),
            "--project-root",
            str(project),
            "--metadata-root",
            "modules/local",
            *extra,
            cwd=project,
        )

    def test_validate_accepts_valid_fixture_project(self):
        result = self.run_tool(
            "tools/validate_atomic_metadata.py",
            "--project-root",
            "tests/fixtures/valid_step",
            "--metadata-root",
            "modules/local",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Validated 1 metadata file", result.stdout)

    def test_meta_yml_must_be_json_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            meta_path = project / "modules/local/transcriptomics/de/simple_de_test/meta.yml"
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_path.write_text("schema_version: 1\n", encoding="utf-8")
            result = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("meta.yml must contain JSON-compatible metadata", result.stderr)

    def test_validate_rejects_common_omics(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            meta = base_meta()
            meta["omics"] = ["common"]
            write_fixture_project(project, meta=meta)
            result = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("$.omics[0]: must be one of", result.stderr)

    def test_validate_rejects_wrong_metadata_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            write_fixture_project(
                project,
                meta_rel=Path("modules/local/transcriptomics/wrong/simple_de_test/meta.yml"),
            )
            result = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("metadata file must be located", result.stderr)

    def test_validate_rejects_wrong_module_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            meta = base_meta()
            meta["module_path"] = "modules/local/transcriptomics/wrong/simple_de_test"
            write_fixture_project(project, meta=meta)
            result = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("module_path must be modules/local/transcriptomics/de/simple_de_test", result.stderr)

    def test_validate_rejects_wrong_implementation_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            meta = base_meta()
            meta["implementation_path"] = "bin/transcriptomics__de__wrong.py"
            write_fixture_project(project, meta=meta)
            result = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("implementation_path must be bin/transcriptomics__de__simple_de_test.py", result.stderr)

    def test_validate_rejects_wrong_process_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            meta = base_meta()
            meta["process_name"] = "SURVOM_TRANSCRIPTOMICS_DE_WRONG"
            write_fixture_project(project, meta=meta)
            result = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("process_name must be SURVOM_TRANSCRIPTOMICS_DE_SIMPLE_DE_TEST", result.stderr)

    def test_validate_rejects_missing_referenced_files_for_production(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            write_fixture_project(project, create_impl=False)
            result = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("declared implementation_path does not exist", result.stderr)

    def test_validate_allows_isolated_fixture_paths_when_explicit(self):
        result = self.run_tool(
            "tools/validate_atomic_metadata.py",
            "--project-root",
            ".",
            "--metadata-root",
            "tests/fixtures/valid_step/modules/local",
            "--allow-fixture-paths",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_validate_rejects_duplicate_ids_and_process_names(self):
        result = self.run_tool(
            "tools/validate_atomic_metadata.py",
            "--project-root",
            ".",
            "--metadata-root",
            "tests/fixtures/duplicate_steps",
            "--allow-fixture-paths",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate id", result.stderr)
        self.assertIn("duplicate process_name", result.stderr)

    def test_sync_registry_writes_deterministic_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            shutil.copytree(ROOT / "tests/fixtures/valid_step", project)
            result = self.run_tool(
                str(ROOT / "tools/sync_registry.py"),
                "--project-root",
                str(project),
                "--metadata-root",
                "modules/local",
                "--output",
                "registry.json",
                cwd=project,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            registry = json.loads((project / "registry.json").read_text(encoding="utf-8"))
            self.assertEqual(registry["step_count"], 1)
            self.assertEqual(registry["steps"][0]["id"], "transcriptomics.de.simple_de_test")
            self.assertRegex(registry["steps"][0]["checksums"]["metadata_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(registry["steps"][0]["checksums"]["implementation_sha256"], r"^[0-9a-f]{64}$")

    def test_sync_registry_blocks_checksum_drift_without_version_bump(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            shutil.copytree(ROOT / "tests/fixtures/drift_step", project)
            command = [
                str(ROOT / "tools/sync_registry.py"),
                "--project-root",
                str(project),
                "--metadata-root",
                "modules/local",
                "--output",
                "registry.json",
            ]
            first = self.run_tool(*command, cwd=project)
            self.assertEqual(first.returncode, 0, first.stderr)
            impl = project / "bin/transcriptomics__de__drift_check.py"
            impl.write_text(impl.read_text(encoding="utf-8") + "\nprint('after')\n", encoding="utf-8")
            second = self.run_tool(*command, cwd=project)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("checksum drift detected without version bump", second.stderr)

    def test_root_sync_registry_includes_approved_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "registry.json"
            result = self.run_tool(
                "tools/sync_registry.py",
                "--project-root",
                str(ROOT),
                "--metadata-root",
                "modules/local",
                "--output",
                str(output),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            registry = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(registry["step_count"], 1)
            self.assertEqual(registry["steps"][0]["id"], "common.qc.seqkit_fastq_stats")


if __name__ == "__main__":
    unittest.main()
