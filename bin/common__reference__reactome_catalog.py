#!/usr/bin/env python3
"""Build a filtered Reactome mapping catalog as compressed Parquet."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any


CATALOG_VERSION = "0.1.0"
OUTPUT_COLUMNS = [
    "source_identifier",
    "direct_pathway_id",
    "identifier_label",
    "pathway_id",
    "pathway_url",
    "pathway_name",
    "evidence_code",
    "species",
]


class CatalogError(Exception):
    """Raised for expected catalog build failures."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def yaml_quote(value: Any) -> str:
    text = str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    columns = payload["derived"]["columns"]
    content = [
        "database_id: reactome",
        f"release_version: {yaml_quote(payload['release_version'])}",
        f"organism: {payload['organism']}",
        f"catalog_version: {yaml_quote(payload['catalog_version'])}",
        "",
        "source:",
        f"  mapping_file: {payload['source']['mapping_file']}",
        f"  mapping_sha256: {yaml_quote(payload['source']['mapping_sha256'])}",
        f"  mapping_kind: {payload['source']['mapping_kind']}",
        f"  source_identifier_namespace: {payload['source']['source_identifier_namespace']}",
        "",
        "derived:",
        f"  mapping_file: {payload['derived']['mapping_file']}",
        f"  mapping_sha256: {yaml_quote(payload['derived']['mapping_sha256'])}",
        f"  format: {payload['derived']['format']}",
        f"  compression: {payload['derived']['compression']}",
        f"  rows: {payload['derived']['rows']}",
        "  columns:",
    ]
    content.extend(f"    - {column}" for column in columns)
    content.extend(
        [
            "",
            "filter:",
            f"  species: {payload['filter']['species']}",
            f"  hierarchy_level: {payload['filter']['hierarchy_level']}",
            "",
        ]
    )
    path.write_text("\n".join(content), encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_required_text(value: str, label: str) -> str:
    if value is None or not str(value).strip():
        raise CatalogError(f"Missing required parameter: {label}")
    return str(value).strip()


def read_reactome_mapping(path: Path, organism: str) -> tuple[list[dict[str, str]], dict[str, int], list[str]]:
    if not path.exists():
        raise CatalogError(f"Reactome mapping file does not exist: {path}")
    if not path.is_file():
        raise CatalogError(f"Reactome mapping path is not a file: {path}")
    if path.stat().st_size == 0:
        raise CatalogError(f"Reactome mapping file is empty: {path}")

    retained: list[dict[str, str]] = []
    seen_rows: set[tuple[str, ...]] = set()
    malformed_row_count = 0
    duplicate_row_count = 0
    input_row_count = 0
    warnings: list[str] = []

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for line_number, row in enumerate(reader, start=1):
            if not row or all(not cell.strip() for cell in row):
                continue
            input_row_count += 1
            if len(row) != 8:
                malformed_row_count += 1
                continue
            if not row[7].strip():
                malformed_row_count += 1
                continue
            normalized = tuple(cell.strip() for cell in row)
            if normalized in seen_rows:
                duplicate_row_count += 1
            seen_rows.add(normalized)
            if row[7].strip() == organism:
                retained.append(dict(zip(OUTPUT_COLUMNS, normalized, strict=True)))

    if input_row_count == 0:
        raise CatalogError(f"Reactome mapping file contains no non-empty rows: {path}")
    if malformed_row_count:
        raise CatalogError(
            "Reactome mapping file has incompatible column structure: "
            f"{malformed_row_count} non-empty row(s) did not contain exactly eight columns "
            "or had a missing species column."
        )
    if not retained:
        raise CatalogError(f"No Reactome mapping rows matched requested organism: {organism}")
    if duplicate_row_count:
        warnings.append(f"Detected {duplicate_row_count} duplicate source row(s); retained duplicates are preserved.")

    diagnostics = {
        "input_row_count": input_row_count,
        "retained_organism_row_count": len(retained),
        "malformed_row_count": malformed_row_count,
        "duplicate_row_count": duplicate_row_count,
    }
    return retained, diagnostics, warnings


def ensure_duckdb():
    try:
        import duckdb  # type: ignore
    except ImportError as exc:
        raise CatalogError(
            "DuckDB Python package is required to write and read Parquet for this step. "
            "Install duckdb in the runtime environment or run the step in a container that provides it."
        ) from exc
    return duckdb


def write_parquet(rows: list[dict[str, str]], out_parquet: Path) -> int:
    duckdb = ensure_duckdb()
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(database=":memory:")
    try:
        connection.execute(
            "CREATE TABLE reactome_catalog ("
            "source_identifier VARCHAR, "
            "direct_pathway_id VARCHAR, "
            "identifier_label VARCHAR, "
            "pathway_id VARCHAR, "
            "pathway_url VARCHAR, "
            "pathway_name VARCHAR, "
            "evidence_code VARCHAR, "
            "species VARCHAR)"
        )
        values = [[row[column] for column in OUTPUT_COLUMNS] for row in rows]
        connection.executemany(
            "INSERT INTO reactome_catalog VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            values,
        )
        connection.execute(
            "COPY reactome_catalog TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(out_parquet)],
        )
        read_back = connection.execute(
            "SELECT COUNT(*) FROM read_parquet(?)",
            [str(out_parquet)],
        ).fetchone()
        if read_back is None:
            raise CatalogError("Parquet read-back validation returned no result.")
        output_rows = int(read_back[0])
    except CatalogError:
        raise
    except Exception as exc:
        raise CatalogError(f"Parquet writing or read-back validation failed: {exc}") from exc
    finally:
        connection.close()
    if output_rows != len(rows):
        raise CatalogError(
            f"Parquet read-back row count mismatch: expected {len(rows)}, observed {output_rows}."
        )
    return output_rows


def validate_parquet_species(out_parquet: Path, organism: str) -> None:
    duckdb = ensure_duckdb()
    connection = duckdb.connect(database=":memory:")
    try:
        species_rows = connection.execute(
            "SELECT DISTINCT species FROM read_parquet(?) ORDER BY species",
            [str(out_parquet)],
        ).fetchall()
    finally:
        connection.close()
    observed = [row[0] for row in species_rows]
    if observed != [organism]:
        raise CatalogError(
            f"Parquet read-back organism validation failed: expected only {organism!r}, observed {observed!r}."
        )


def build_catalog(args: argparse.Namespace) -> int:
    release_version = validate_required_text(args.release_version, "release_version")
    organism = validate_required_text(args.organism, "organism")
    mapping_kind = validate_required_text(args.mapping_kind, "mapping_kind")
    source_identifier_namespace = validate_required_text(
        args.source_identifier_namespace, "source_identifier_namespace"
    )
    mapping_file = Path(args.mapping_file).expanduser()
    out_parquet = Path(args.out_parquet)
    out_manifest = Path(args.out_manifest)
    out_diagnostics = Path(args.out_diagnostics)

    rows, partial_diagnostics, warnings = read_reactome_mapping(mapping_file, organism)
    source_digest = sha256(mapping_file)
    output_rows = write_parquet(rows, out_parquet)
    validate_parquet_species(out_parquet, organism)
    output_digest = sha256(out_parquet)

    manifest = {
        "database_id": "reactome",
        "release_version": release_version,
        "organism": organism,
        "catalog_version": CATALOG_VERSION,
        "source": {
            "mapping_file": str(mapping_file.resolve()),
            "mapping_sha256": source_digest,
            "mapping_kind": mapping_kind,
            "source_identifier_namespace": source_identifier_namespace,
        },
        "derived": {
            "mapping_file": str(out_parquet.resolve()),
            "mapping_sha256": output_digest,
            "format": "parquet",
            "compression": "zstd",
            "rows": output_rows,
            "columns": OUTPUT_COLUMNS,
        },
        "filter": {
            "species": organism,
            "hierarchy_level": "all_pathways",
        },
    }
    diagnostics = {
        **partial_diagnostics,
        "output_row_count": output_rows,
        "source_sha256": source_digest,
        "output_sha256": output_digest,
        "warnings": warnings,
    }

    out_manifest.parent.mkdir(parents=True, exist_ok=True)
    out_diagnostics.parent.mkdir(parents=True, exist_ok=True)
    write_manifest(out_manifest, manifest)
    write_json(out_diagnostics, diagnostics)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a compressed Parquet Reactome mapping catalog from a local All Levels mapping file."
    )
    parser.add_argument("--mapping-file", required=True, help="Local Reactome All Levels mapping text file.")
    parser.add_argument("--release-version", required=True, help="Explicit Reactome release version.")
    parser.add_argument("--organism", required=True, help="Organism name to retain, for example 'Homo sapiens'.")
    parser.add_argument("--mapping-kind", required=True, help="Explicit mapping kind metadata.")
    parser.add_argument(
        "--source-identifier-namespace",
        required=True,
        help="Explicit source identifier namespace metadata.",
    )
    parser.add_argument("--out-parquet", required=True, help="Output compressed Parquet catalog path.")
    parser.add_argument("--out-manifest", required=True, help="Output YAML provenance manifest path.")
    parser.add_argument("--out-diagnostics", required=True, help="Output JSON build diagnostics path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        return build_catalog(parse_args(argv))
    except CatalogError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
