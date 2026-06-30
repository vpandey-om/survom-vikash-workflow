#!/usr/bin/env python3
"""Generate deterministic SurvOm registry.json from atomic step metadata.

Local drift detection compares against the existing registry output. Future CI
must also compare metadata and implementation checksums against the merge base,
otherwise a simultaneous implementation edit and registry regeneration could
bypass local drift detection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from validate_atomic_metadata import find_metadata_files, load_schema, validate_collection


REGISTRY_SCHEMA_VERSION = 1


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_record(project_root: Path, meta_path: Path, meta: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    errors = []
    implementation_path = project_root / str(meta["implementation_path"])
    if not implementation_path.exists():
        errors.append(f"{meta_path}: declared implementation_path does not exist: {meta['implementation_path']}")
        return None, errors

    record = {
        "id": meta["id"],
        "version": meta["version"],
        "display_name": meta["display_name"],
        "description": meta["description"],
        "domain": meta["domain"],
        "category": meta["category"],
        "omics": sorted(meta["omics"]),
        "status": meta["status"],
        "validation_tier": meta["validation"]["tier"],
        "language": meta["language"],
        "implementation_path": meta["implementation_path"],
        "module_path": meta["module_path"],
        "process_name": meta["process_name"],
        "container": meta["container"],
        "inputs": meta["inputs"],
        "outputs": meta["outputs"],
        "aliases": sorted(meta["aliases"]),
        "deprecation": meta["deprecation"],
        "checksums": {
            "metadata_sha256": sha256_file(meta_path),
            "implementation_sha256": sha256_file(implementation_path),
        },
        "metadata_path": str(meta_path.relative_to(project_root)),
    }
    return record, errors


def load_existing_registry(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def drift_errors(existing: dict[str, Any] | None, new_records: list[dict[str, Any]]) -> list[str]:
    if not existing:
        return []
    previous = {record["id"]: record for record in existing.get("steps", [])}
    errors = []
    for record in new_records:
        old = previous.get(record["id"])
        if not old:
            continue
        checksum_changed = old.get("checksums") != record.get("checksums")
        version_same = old.get("version") == record.get("version")
        if checksum_changed and version_same:
            errors.append(
                f"{record['id']}: checksum drift detected without version bump "
                f"(version {record['version']})"
            )
    return errors


def build_registry(project_root: Path, metadata_root: Path) -> tuple[dict[str, Any], list[str]]:
    metadata_files = find_metadata_files(metadata_root)
    records, errors = validate_collection(
        metadata_files,
        metadata_root,
        project_root,
        schema=load_schema(),
    )
    if errors:
        return {}, errors

    registry_records = []
    for record in records:
        registry_record, record_errors = build_record(project_root, record["path"], record["meta"])
        errors.extend(record_errors)
        if registry_record:
            registry_records.append(registry_record)

    registry_records.sort(key=lambda item: (item["id"], item["version"]))
    registry = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "generated_by": "tools/sync_registry.py",
        "source": {
            "metadata_root": str(metadata_root.relative_to(project_root))
            if metadata_root.is_relative_to(project_root)
            else str(metadata_root),
        },
        "step_count": len(registry_records),
        "steps": registry_records,
    }
    return registry, errors


def write_registry(path: Path, registry: dict[str, Any]) -> None:
    path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic SurvOm registry.json.",
        epilog=(
            "Note: local checksum drift detection compares against the existing registry output. "
            "Future CI must add merge-base comparison to prevent implementation edits and registry "
            "regeneration from bypassing drift detection."
        ),
    )
    parser.add_argument("--project-root", default=".", help="Project root used to resolve declared paths.")
    parser.add_argument(
        "--metadata-root",
        default="modules/local",
        help="Directory containing future atomic step meta.yml files. Defaults to modules/local.",
    )
    parser.add_argument("--output", default="registry.json", help="Registry JSON output path.")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    metadata_root = (project_root / args.metadata_root).resolve()
    output_path = (project_root / args.output).resolve()

    registry, errors = build_registry(project_root, metadata_root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    existing = load_existing_registry(output_path)
    errors = drift_errors(existing, registry["steps"])
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    write_registry(output_path, registry)
    print(f"Wrote {output_path} with {registry['step_count']} step(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
