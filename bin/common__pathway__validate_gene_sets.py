#!/usr/bin/env python3
"""Validate pathway gene-set database manifests and GMT files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REQUIRED_MANIFEST_FIELDS = (
    "database_id",
    "name",
    "organism",
    "identifier_namespace",
    "gene_set_format",
    "release_version",
    "retrieval_date",
    "source_url",
    "license_note",
    "checksum_sha256",
)
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CHECKSUM_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class GeneSetValidationError(Exception):
    """Raised for expected user-facing gene-set validation failures."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise GeneSetValidationError(f"Missing {label}: {path}")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GeneSetValidationError(f"{label} is not valid JSON: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise GeneSetValidationError(f"{label} must contain a JSON object.")
    return parsed


def parse_scalar(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value


def read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise GeneSetValidationError(f"Missing gene-set manifest: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    if parsed is not None:
        raise GeneSetValidationError("gene-set manifest must contain a JSON object or flat YAML-style mapping.")

    manifest: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise GeneSetValidationError(f"gene-set manifest line {line_number} is not a key/value entry.")
        key, value = line.split(":", 1)
        key = key.strip()
        if not key:
            raise GeneSetValidationError(f"gene-set manifest line {line_number} has an empty key.")
        if key in manifest:
            raise GeneSetValidationError(f"gene-set manifest contains duplicate key: {key}.")
        manifest[key] = parse_scalar(value)
    if not manifest:
        raise GeneSetValidationError("gene-set manifest is empty.")
    return manifest


def require_int(params: dict[str, Any], key: str) -> int:
    value = params.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise GeneSetValidationError(f"validation_params.{key} must be an explicit integer.")
    if value < 1:
        raise GeneSetValidationError(f"validation_params.{key} must be at least 1.")
    return value


def normalize_manifest(manifest: dict[str, Any]) -> dict[str, str]:
    missing = [
        field
        for field in REQUIRED_MANIFEST_FIELDS
        if field not in manifest or not isinstance(manifest[field], str) or not manifest[field].strip()
    ]
    if missing:
        raise GeneSetValidationError(f"gene-set manifest is missing required field(s): {', '.join(missing)}.")

    normalized = {field: manifest[field].strip() for field in REQUIRED_MANIFEST_FIELDS}
    if normalized["gene_set_format"].lower() != "gmt":
        raise GeneSetValidationError("gene-set manifest field gene_set_format must be 'gmt'.")
    normalized["gene_set_format"] = "gmt"
    if not DATE_PATTERN.fullmatch(normalized["retrieval_date"]):
        raise GeneSetValidationError("gene-set manifest field retrieval_date must use YYYY-MM-DD format.")
    if not CHECKSUM_PATTERN.fullmatch(normalized["checksum_sha256"]):
        raise GeneSetValidationError("gene-set manifest field checksum_sha256 must be a lowercase SHA-256 digest.")

    for key, value in manifest.items():
        if key not in normalized and isinstance(value, str):
            normalized[key] = value.strip()
    return normalized


def read_gmt(path: Path, min_size: int, max_size: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        raise GeneSetValidationError(f"Missing GMT file: {path}")

    rows: list[dict[str, Any]] = []
    malformed_lines: list[int] = []
    size_failures: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for line_number, row in enumerate(reader, start=1):
            if not row:
                continue
            if len(row) < 3:
                malformed_lines.append(line_number)
                continue
            gene_set_id = row[0].strip()
            description = row[1].strip()
            members = [member.strip() for member in row[2:] if member.strip()]
            if not gene_set_id:
                malformed_lines.append(line_number)
                continue
            unique_members = sorted(set(members))
            size = len(unique_members)
            if size < min_size or size > max_size:
                size_failures.append(f"{gene_set_id}={size}")
            rows.append(
                {
                    "gene_set_id": gene_set_id,
                    "description": description,
                    "members": members,
                    "unique_member_count": size,
                }
            )

    if malformed_lines:
        raise GeneSetValidationError(f"GMT file contains malformed line(s): {', '.join(map(str, malformed_lines))}.")
    if not rows:
        raise GeneSetValidationError("GMT file must contain at least one gene set.")

    duplicate_ids = sorted(gene_set_id for gene_set_id, count in Counter(row["gene_set_id"] for row in rows).items() if count > 1)
    if duplicate_ids:
        raise GeneSetValidationError(f"GMT gene-set IDs must be unique. Duplicates: {', '.join(duplicate_ids)}.")
    if size_failures:
        raise GeneSetValidationError(
            "GMT gene-set sizes must be within validation_params.min_gene_set_size and "
            f"validation_params.max_gene_set_size. Offending sets: {', '.join(size_failures)}."
        )

    unique_members = sorted({member for row in rows for member in row["members"]})
    diagnostics = {
        "n_gene_sets": len(rows),
        "n_unique_identifiers": len(unique_members),
        "min_observed_gene_set_size": min(row["unique_member_count"] for row in rows),
        "max_observed_gene_set_size": max(row["unique_member_count"] for row in rows),
        "gene_set_ids": [row["gene_set_id"] for row in rows],
    }
    return rows, diagnostics


def write_gmt(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        for row in rows:
            writer.writerow([row["gene_set_id"], row["description"], *row["members"]])


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def base_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "step_id": "common.pathway.validate_gene_sets",
        "version": "0.1.0",
        "status": "failed",
        "manifest": {},
        "gene_sets": {},
        "validation_params": {},
        "warnings": [],
        "errors": [],
    }


def validate_gene_sets(
    gene_set_manifest: Path,
    gene_set_file: Path,
    params: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any]]:
    min_size = require_int(params, "min_gene_set_size")
    max_size = require_int(params, "max_gene_set_size")
    if min_size > max_size:
        raise GeneSetValidationError("validation_params.min_gene_set_size must be <= max_gene_set_size.")

    manifest = normalize_manifest(read_manifest(gene_set_manifest))
    actual_checksum = sha256_file(gene_set_file)
    if manifest["checksum_sha256"] != actual_checksum:
        raise GeneSetValidationError(
            "gene-set manifest checksum_sha256 does not match the GMT file on disk. "
            f"Expected {manifest['checksum_sha256']}, observed {actual_checksum}."
        )

    rows, gene_set_diagnostics = read_gmt(gene_set_file, min_size, max_size)
    report = base_report()
    report.update(
        {
            "status": "passed",
            "manifest": {
                "database_id": manifest["database_id"],
                "name": manifest["name"],
                "organism": manifest["organism"],
                "identifier_namespace": manifest["identifier_namespace"],
                "gene_set_format": manifest["gene_set_format"],
                "release_version": manifest["release_version"],
                "retrieval_date": manifest["retrieval_date"],
                "source_url": manifest["source_url"],
                "license_note": manifest["license_note"],
                "checksum_sha256": manifest["checksum_sha256"],
            },
            "gene_sets": gene_set_diagnostics,
            "validation_params": {
                "min_gene_set_size": min_size,
                "max_gene_set_size": max_size,
            },
            "warnings": [],
            "errors": [],
        }
    )
    return rows, manifest, report


def write_failure(args: argparse.Namespace, message: str) -> None:
    report = base_report()
    report["errors"] = [message]
    write_json(args.out_validation_report, report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a pathway gene-set database manifest and GMT file.")
    parser.add_argument("--gene-set-manifest", required=True, type=Path)
    parser.add_argument("--gene-set-file", required=True, type=Path)
    parser.add_argument("--validation-params", required=True, type=Path)
    parser.add_argument("--out-validated-gene-sets", required=True, type=Path)
    parser.add_argument("--out-validated-manifest", required=True, type=Path)
    parser.add_argument("--out-validation-report", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        params = read_json(args.validation_params, "validation params")
        rows, manifest, report = validate_gene_sets(args.gene_set_manifest, args.gene_set_file, params)
    except GeneSetValidationError as exc:
        write_failure(args, str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    write_gmt(args.out_validated_gene_sets, rows)
    write_json(args.out_validated_manifest, manifest)
    write_json(args.out_validation_report, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
