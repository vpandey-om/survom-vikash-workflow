#!/usr/bin/env python3
"""Validate SurvOm atomic step meta.yml files with standard library only.

Authoritative format: meta.yml files must contain JSON-compatible metadata.
Until a pinned YAML parser is approved, this tool reads meta.yml with
json.loads and validates the subset of JSON Schema used by
docs/schemas/atomic-step-meta.schema.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA_PATH = ROOT / "docs/schemas/atomic-step-meta.schema.json"


class MetadataError(Exception):
    """Raised when metadata cannot be parsed or validated."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MetadataError(
            f"{path}: meta.yml must contain JSON-compatible metadata until a pinned YAML parser is approved "
            f"(line {exc.lineno}, column {exc.colno}: {exc.msg})"
        ) from exc
    if not isinstance(parsed, dict):
        raise MetadataError(f"{path}: metadata root must be a JSON object")
    return parsed


def load_schema(schema_path: Path = DEFAULT_SCHEMA_PATH) -> dict[str, Any]:
    return load_json(schema_path)


def find_metadata_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root]
    return sorted(path for path in root.rglob("meta.yml") if ".git" not in path.parts)


def schema_type_matches(value: Any, expected: str | list[str]) -> bool:
    expected_types = expected if isinstance(expected, list) else [expected]
    for expected_type in expected_types:
        if expected_type == "null" and value is None:
            return True
        if expected_type == "object" and isinstance(value, dict):
            return True
        if expected_type == "array" and isinstance(value, list):
            return True
        if expected_type == "string" and isinstance(value, str):
            return True
        if expected_type == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if expected_type == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if expected_type == "boolean" and isinstance(value, bool):
            return True
    return False


def type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__


def validate_schema_subset(value: Any, schema: dict[str, Any], location: str) -> list[str]:
    """Validate the JSON Schema subset used by SurvOm metadata contracts."""

    errors: list[str] = []
    if "const" in schema and value != schema["const"]:
        errors.append(f"{location}: must equal {schema['const']!r}")
    if "type" in schema and not schema_type_matches(value, schema["type"]):
        errors.append(f"{location}: expected type {schema['type']}, got {type_name(value)}")
        return errors
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{location}: must be one of {schema['enum']}")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{location}: must not be empty")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            errors.append(f"{location}: must match pattern {schema['pattern']}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{location}: must contain at least {schema['minItems']} item(s)")
        if schema.get("uniqueItems") and len(value) != len({json.dumps(item, sort_keys=True) for item in value}):
            errors.append(f"{location}: items must be unique")
        if "items" in schema:
            for index, item in enumerate(value):
                errors.extend(validate_schema_subset(item, schema["items"], f"{location}[{index}]"))

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{location}: missing required field '{key}'")
        if schema.get("additionalProperties") is False:
            allowed = set(schema.get("properties", {}))
            for key in sorted(set(value) - allowed):
                errors.append(f"{location}: unexpected field '{key}'")
        for key, subschema in schema.get("properties", {}).items():
            if key in value:
                errors.extend(validate_schema_subset(value[key], subschema, f"{location}.{key}"))

    return errors


def expected_parts(step_id: str) -> tuple[str, str, str]:
    pieces = step_id.split(".")
    if len(pieces) != 3:
        raise MetadataError(f"id '{step_id}' must use domain.category.step_name")
    return pieces[0], pieces[1], pieces[2]


def expected_paths(meta: dict[str, Any]) -> tuple[str, str, str]:
    domain, category, step_name = expected_parts(str(meta["id"]))
    module_path = f"modules/local/{domain}/{category}/{step_name}"
    impl_ext = "py" if meta.get("language") == "python" else "R"
    implementation_path = f"bin/{domain}__{category}__{step_name}.{impl_ext}"
    process_name = f"SURVOM_{domain}_{category}_{step_name}".upper()
    return module_path, implementation_path, process_name


def relative_to_or_none(path: Path, parent: Path) -> Path | None:
    try:
        return path.relative_to(parent)
    except ValueError:
        return None


def validate_semantics(
    meta: dict[str, Any],
    meta_path: Path,
    metadata_root: Path,
    project_root: Path,
    allow_fixture_paths: bool = False,
) -> list[str]:
    errors: list[str] = []
    try:
        domain, category, step_name = expected_parts(str(meta["id"]))
        expected_module, expected_impl, expected_process = expected_paths(meta)
    except MetadataError as exc:
        return [f"{meta_path}: {exc}"]

    if meta.get("domain") != domain:
        errors.append(f"{meta_path}: domain must match id domain '{domain}'")
    if meta.get("category") != category:
        errors.append(f"{meta_path}: category must match id category '{category}'")

    expected_meta_rel = Path(domain) / category / step_name / "meta.yml"
    root_relative_meta = relative_to_or_none(meta_path, metadata_root)
    if root_relative_meta != expected_meta_rel:
        errors.append(
            f"{meta_path}: metadata file must be located at "
            f"{metadata_root / expected_meta_rel}"
        )

    if meta.get("module_path") != expected_module:
        errors.append(f"{meta_path}: module_path must be {expected_module}")
    if meta.get("implementation_path") != expected_impl:
        errors.append(f"{meta_path}: implementation_path must be {expected_impl}")
    if meta.get("process_name") != expected_process:
        errors.append(f"{meta_path}: process_name must be {expected_process}")

    if not allow_fixture_paths:
        module_abs = project_root / expected_module
        impl_abs = project_root / expected_impl
        if not module_abs.is_dir():
            errors.append(f"{meta_path}: declared module_path does not exist: {expected_module}")
        if not impl_abs.is_file():
            errors.append(f"{meta_path}: declared implementation_path does not exist: {expected_impl}")

    return errors


def validate_collection(
    metadata_files: list[Path],
    metadata_root: Path,
    project_root: Path,
    schema: dict[str, Any] | None = None,
    allow_fixture_paths: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    schema = schema or load_schema()
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    ids: dict[str, Path] = {}
    aliases: dict[str, Path] = {}
    process_names: dict[str, Path] = {}

    for path in metadata_files:
        try:
            meta = load_json(path)
        except MetadataError as exc:
            errors.append(str(exc))
            continue
        errors.extend(f"{path}: {error}" for error in validate_schema_subset(meta, schema, "$"))
        errors.extend(validate_semantics(meta, path, metadata_root, project_root, allow_fixture_paths))
        records.append({"path": path, "meta": meta})

    for record in records:
        path = record["path"]
        meta = record["meta"]
        step_id = str(meta.get("id", ""))
        if step_id:
            if step_id in ids:
                errors.append(f"{path}: duplicate id '{step_id}' also used by {ids[step_id]}")
            ids[step_id] = path
        process_name = str(meta.get("process_name", ""))
        if process_name:
            if process_name in process_names:
                errors.append(f"{path}: duplicate process_name '{process_name}' also used by {process_names[process_name]}")
            process_names[process_name] = path
        for alias in meta.get("aliases", []) if isinstance(meta.get("aliases"), list) else []:
            if alias in aliases:
                errors.append(f"{path}: duplicate alias '{alias}' also used by {aliases[alias]}")
            aliases[alias] = path

    for alias, alias_path in aliases.items():
        if alias in ids:
            errors.append(f"{alias_path}: alias '{alias}' collides with step id in {ids[alias]}")

    return records, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate SurvOm atomic step meta.yml files.")
    parser.add_argument("--project-root", default=".", help="Project root used to resolve declared paths.")
    parser.add_argument(
        "--metadata-root",
        default="modules/local",
        help="Directory or meta.yml file to validate. Defaults to future production root modules/local.",
    )
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA_PATH),
        help="JSON Schema contract to use. Defaults to docs/schemas/atomic-step-meta.schema.json.",
    )
    parser.add_argument(
        "--allow-fixture-paths",
        action="store_true",
        help="Allow isolated test fixtures to skip production module/implementation existence checks.",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    metadata_root = (project_root / args.metadata_root).resolve()
    schema = load_schema(Path(args.schema))
    metadata_files = find_metadata_files(metadata_root)
    records, errors = validate_collection(
        metadata_files,
        metadata_root,
        project_root,
        schema=schema,
        allow_fixture_paths=args.allow_fixture_paths,
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Validated {len(records)} metadata file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
