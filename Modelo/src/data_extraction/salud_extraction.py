"""
Health Data Extraction Script for MINSAL Chile (DEIS / Urgencias)
================================================================

Processes raw DEIS/MINSAL health data CSV files containing anonymized
emergency-room attendance counts by establishment, cause, date, age group,
and region.

Produces cleaned, region-normalized, date-unified CSVs suitable for the
predictive model pipeline.

Author: Ignacio Fernandez (Nafery) - ML Lead
Project: MINSAL Early Warning System - Predictive Model of Respiratory Demand

Data Source:
  DEIS (Direccion de Estadisticas e Informacion en Salud) — Atenciones de Urgencia
  File format: semicolon-delimited CSV, Latin-1 / ISO-8859-1 encoded

Features:
  - Automatic encoding detection (latin-1 fallback, UTF-8 primary)
  - Semicolon-delimited CSV parsing
  - Region name normalization to DEIS/MINSAL canonical format
  - Date unification to YYYY-MM-DD from DD/MM/YYYY input
  - Respiratory cause flagging (CIE-10 J00-J99 + TEMA RESPIRATORIO)
  - Optional regional filtering
  - Consolidated output CSV
  - Structured logging for full traceability

Usage:
    python salud_extraction.py --input /path/to/AtencionesUrgencia2024.csv \\
        --output ./data/salud/processed.csv

    python salud_extraction.py --input-dir ./raw_health/ \\
        --output ./data/salud/ \\
        --filter-region "Biobio"
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("salud_extraction.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("salud_extraction")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Canonical region names matching the DEIS/MINSAL convention.
CANONICAL_REGIONS: List[str] = [
    "Arica y Parinacota",
    "Tarapaca",
    "Antofagasta",
    "Atacama",
    "Coquimbo",
    "Valparaiso",
    "Metropolitana",
    "OHiggins",
    "Maule",
    "Nuble",
    "Biobio",
    "Araucania",
    "Los Rios",
    "Los Lagos",
    "Aysen",
    "Magallanes",
]

# Mapping: lower-cased alias → canonical name.
REGION_ALIAS_MAP: Dict[str, str] = {
    "arica y parinacota": "Arica y Parinacota",
    "arica y parinacota de chile": "Arica y Parinacota",
    "tarapacá": "Tarapaca",
    "tarapaca": "Tarapaca",
    "antofagasta": "Antofagasta",
    "atacama": "Atacama",
    "coquimbo": "Coquimbo",
    "valparaíso": "Valparaiso",
    "valparaiso": "Valparaiso",
    "metropolitana": "Metropolitana",
    "metropolitana de santiago": "Metropolitana",
    "o'higgins": "OHiggins",
    "ohiggins": "OHiggins",
    "maule": "Maule",
    "ñuble": "Nuble",
    "nuble": "Nuble",
    "biobío": "Biobio",
    "biobio": "Biobio",
    "la araucanía": "Araucania",
    "araucania": "Araucania",
    "los ríos": "Los Rios",
    "los rios": "Los Rios",
    "los lagos": "Los Lagos",
    "aysén": "Aysen",
    "aysen": "Aysen",
    "magallanes": "Magallanes",
    "magallanes y la antartica chilena": "Magallanes",
}

# CIE-10 chapter codes for respiratory diseases (J00–J99).
RESPIRATORY_CIE_PREFIXES = [
    "J0", "J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8", "J9",
]

# All acceptable column-name variants (case-insensitive matching).
COLUMN_ALIASES: Dict[str, List[str]] = {
    "fecha": ["fecha", "Fecha", "FECHA", "fecharegistro", "Fecha Registro"],
    "nombre_region": [
        "nombreregion",
        "NombreRegion",
        "NOMBREREGION",
        "nombre region",
        "region",
        "Region",
        "NOMBRE区域",
    ],
    "codigo_region": [
        "codigoregion",
        "CodigoRegion",
        "CODIGOREGION",
        "codigo region",
        "cod_reg",
    ],
    "total": ["total", "Total", "TOTAL", "cant_total", "CANT_TOTAL"],
    "menores_1": ["menores_1", "Menores_1", "MENORES_1", "menores1", "<1"],
    "de_1_a_4": ["de_1_a_4", "De_1_a_4", "DE_1_A_4", "1-4", "de1a4"],
    "de_5_a_14": ["de_5_a_14", "De_5_a_14", "DE_5_A_14", "5-14", "de5a14"],
    "de_15_a_64": [
        "de_15_a_64",
        "De_15_a_64",
        "DE_15_A_64",
        "15-64",
        "de15a64",
        "adultos",
    ],
    "de_65_y_mas": [
        "de_65_y_mas",
        "De_65_y_mas",
        "DE_65_Y_MAS",
        "65+",
        "adultos_mayores",
        "de65ymas",
    ],
    "glosa_causa": [
        "glosacausa",
        "GlosaCausa",
        "GLOSACAUSA",
        "glosa causa",
        "causa",
        "Causa",
        "CAUSA",
    ],
    "codigo_causa": [
        "idcausa",
        "IdCausa",
        "IDCAUSA",
        "codigo_causa",
        "cod_causa",
    ],
    "codigo_comuna": ["codigocomuna", "CodigoComuna", "CODIGOCOMUNA", "comuna"],
    "nombre_comuna": ["nombracomuna", "NombreComuna", "NOMBRECOMUNA", "comuna"],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalize_region_name(raw: str) -> str:
    """Return the canonical region name for a raw DEIS region string.

    Args:
        raw: Raw region name as read from the source CSV.

    Returns:
        Canonical region name. Unknown names pass through as-is.
    """
    cleaned = raw.strip()
    # Direct match
    if cleaned in REGION_ALIAS_MAP:
        return REGION_ALIAS_MAP[cleaned]
    # Case-insensitive match
    lookup = cleaned.lower().strip()
    for alias, canonical in REGION_ALIAS_MAP.items():
        if alias.lower().strip() == lookup:
            return canonical
    return cleaned


def normalize_date(date_str: str) -> Optional[str]:
    """Parse various date formats and return YYYY-MM-DD.

    Handles: DD/MM/YYYY, DD-MM-YYYY, YYYYMMDD, and ISO 8601 variants.

    Args:
        date_str: Raw date string from the source CSV.

    Returns:
        Normalized date string (YYYY-MM-DD) or None on failure.
    """
    if not date_str or not date_str.strip():
        return None
    date_str = date_str.strip()

    # Already ISO?
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str

    # Try common patterns
    patterns = [
        ("%d/%m/%Y", None),
        ("%d-%m-%Y", None),
        ("%Y%m%d", None),
        ("%d/%m/%y", None),
    ]
    for fmt, _ in patterns:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    logger.warning("Could not parse date: %s", date_str)
    return None


def detect_encoding(file_path: str) -> str:
    """Detect the text encoding of a CSV file.

    Tries UTF-8 first; falls back to latin-1 if decoding fails.

    Args:
        file_path: Absolute or relative path to the CSV file.

    Returns:
        Encoding name string ('utf-8' or 'latin-1').
    """
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            fh.read(8192)
        return "utf-8"
    except UnicodeDecodeError:
        logger.info("UTF-8 decode failed, falling back to latin-1 for %s", file_path)
        return "latin-1"


def resolve_column(headers: List[str], key: str) -> Optional[str]:
    """Find the actual header name that matches the given logical key.

    Args:
        headers: Raw header list from the CSV.
        key: Logical column name (e.g. 'fecha', 'nombre_region').

    Returns:
        The matching header string, or None if no match found.
    """
    key_lower = key.lower()
    aliases = COLUMN_ALIASES.get(key_lower, [key_lower])
    for header in headers:
        h_clean = header.strip().lower().replace(" ", "").replace("_", "")
        for alias in aliases:
            a_clean = alias.lower().replace(" ", "").replace("_", "")
            if h_clean == a_clean:
                return header
    return None


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------


def read_health_csv(
    file_path: str,
    encoding: Optional[str] = None,
    delimiter: str = ";",
) -> Tuple[List[str], List[Dict]]:
    """Read a DEIS health data CSV and return headers + parsed rows.

    Args:
        file_path: Path to the CSV file.
        encoding: Explicit encoding (None → auto-detect).
        delimiter: CSV field separator (default ';').

    Returns:
        Tuple of (headers, list-of-row-dicts).

    Raises:
        FileNotFoundError: If the file does not exist.
        csv.Error: If the file cannot be parsed.
    """
    file_path = Path(file_path).expanduser().resolve()
    if encoding is None:
        encoding = detect_encoding(str(file_path))

    logger.info("Reading %s (encoding=%s, delimiter='%s')", file_path, encoding, delimiter)

    headers: List[str] = []
    rows: List[Dict] = []

    with open(file_path, "r", encoding=encoding, newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        headers = list(reader.fieldnames) if reader.fieldnames else []
        for i, raw_row in enumerate(reader):
            # Normalize keys to stripped lower-case for uniform access
            clean_row = {k.strip(): v.strip() if v else "" for k, v in raw_row.items()}
            rows.append(clean_row)
            if (i + 1) % 500_000 == 0:
                logger.info("Progress: %d rows read …", i + 1)

    logger.info("Finished reading. Total rows: %d, Headers: %s", len(rows), headers)
    return headers, rows


def filter_respiratory(row: Dict) -> bool:
    """Check whether a row corresponds to a respiratory condition.

    Uses the GlosaCausa column; matches CIE-10 codes J00–J99 or any
    occurrence of 'respiratorio' / 'respirator' in the cause description.

    Args:
        row: Parsed row dictionary.

    Returns:
        True if the cause is respiratory.
    """
    cause = row.get("glosa_causa", "").upper()
    code = row.get("codigo_causa", "").strip()

    # Direct CIE-10 prefix check on cause text
    for prefix in RESPIRATORY_CIE_PREFIXES:
        if cause.startswith(prefix) or code.startswith(prefix):
            return True

    # Keyword heuristic
    keywords = ["RESPIRATORIO", "NEUMONIA", "BRONQUITIS", "ASMA", "EPOC", "GRIPE", " influenza"]
    return any(kw in cause for kw in keywords)


def process_row(row: Dict) -> Optional[Dict]:
    """Normalize a single row into the canonical output schema.

    Output schema:
        Fecha, Region, CodigoRegion, Total, Menores_1, De_1_a_4,
        De_5_a_14, De_15_a_64, De_65_y_mas, GlosaCausa, CodigoCausa,
        NombreComuna, es_respiratoria

    Args:
        row: Raw row dict from the source CSV.

    Returns:
        Normalized row dict, or None if the row could not be processed.
    """
    fecha_raw = row.get("fecha", "")
    fecha_norm = normalize_date(fecha_raw)
    if fecha_norm is None:
        logger.warning("Skipping row with unparseable date: %s", fecha_raw)
        return None

    region_raw = row.get("nombre_region", "")
    region_norm = normalize_region_name(region_raw)
    codigo_region = row.get("codigo_region", "").strip()

    try:
        total = int(float(row.get("total", 0)))
    except (ValueError, TypeError):
        total = 0

    def safe_int(key: str) -> int:
        try:
            return int(float(row.get(key, 0) or 0))
        except (ValueError, TypeError):
            return 0

    is_respiratory = filter_respiratory(row)

    return {
        "Fecha": fecha_norm,
        "Region": region_norm,
        "CodigoRegion": codigo_region,
        "Total": total,
        "Menores_1": safe_int("menores_1"),
        "De_1_a_4": safe_int("de_1_a_4"),
        "De_5_a_14": safe_int("de_5_a_14"),
        "De_15_a_64": safe_int("de_15_a_64"),
        "De_65_y_mas": safe_int("de_65_y_mas"),
        "GlosaCausa": row.get("glosa_causa", ""),
        "CodigoCausa": row.get("codigo_causa", ""),
        "NombreComuna": row.get("nombre_comuna", ""),
        "es_respiratoria": 1 if is_respiratory else 0,
    }


def write_output_csv(
    rows: Iterator[Dict],
    output_path: str,
    include_all: bool = True,
) -> Tuple[int, int]:
    """Write processed rows to a consolidated CSV file.

    Args:
        rows: Iterator yielding normalized row dicts.
        output_path: Destination CSV path.
        include_all: If False, emit only respiratory rows.

    Returns:
        Tuple of (written_count, skipped_count).
    """
    output_path = Path(output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "Fecha", "Region", "CodigoRegion", "Total",
        "Menores_1", "De_1_a_4", "De_5_a_14",
        "De_15_a_64", "De_65_y_mas", "GlosaCausa",
        "CodigoCausa", "NombreComuna", "es_respiratoria",
    ]

    written = 0
    skipped = 0

    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            if not include_all and not row.get("es_respiratoria"):
                skipped += 1
                continue
            try:
                writer.writerow(row)
                written += 1
            except Exception as exc:
                logger.warning("Skipped row during write: %s", exc)
                skipped += 1

    logger.info("CSV written: %s  (%d rows, %d skipped)", output_path, written, skipped)
    return written, skipped


# ---------------------------------------------------------------------------
# Public orchestration
# ---------------------------------------------------------------------------


def process_health_file(
    input_path: str,
    output_path: str,
    filter_region: Optional[str] = None,
    respiratory_only: bool = False,
) -> str:
    """Process a single DEIS health CSV into a cleaned, normalized output.

    Args:
        input_path: Path to the raw source CSV.
        output_path: Path for the cleaned output CSV.
        filter_region: If set, keep only rows for this region (canonical or alias).
        respiratory_only: If True, keep only rows flagged as respiratory.

    Returns:
        Absolute path to the output CSV.

    Raises:
        FileNotFoundError: If input_path does not exist.
    """
    input_path = Path(input_path).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    headers, rows = read_health_csv(str(input_path))

    # Validate required columns exist (after alias resolution)
    required_keys = ["fecha", "nombre_region", "total"]
    resolved = {k: resolve_column(headers, k) for k in required_keys}
    missing = [k for k, hdr in resolved.items() if hdr is None]
    if missing:
        logger.warning("Optional columns not found: %s — continuing with best-effort", missing)

    total_before = len(rows)
    logger.info("Processing %d rows (filter_region=%s, respiratory_only=%s)",
                total_before, filter_region, respiratory_only)

    filtered_rows = []
    for row in rows:
        # Region filter
        if filter_region:
            canon = normalize_region_name(filter_region)
            row_region = normalize_region_name(row.get("nombre_region", ""))
            if row_region != canon:
                continue

        processed = process_row(row)
        if processed is None:
            continue
        filtered_rows.append(processed)

    logger.info("Rows after processing: %d (filtered from %d)", len(filtered_rows), total_before)

    written, skipped = write_output_csv(
        iter(filtered_rows),
        output_path,
        include_all=not respiratory_only,
    )

    logger.info(
        "Done. Wrote %d rows, skipped %d. Output: %s",
        written,
        skipped,
        output_path,
    )
    return str(output_path)


def process_health_directory(
    input_dir: str,
    output_dir: str,
    pattern: str = "*.csv",
    filter_region: Optional[str] = None,
    respiratory_only: bool = False,
) -> List[str]:
    """Process every matching CSV in a directory, one output per input file.

    Args:
        input_dir: Directory containing raw source CSVs.
        output_dir: Directory for output CSVs.
        pattern: Glob pattern for source files (default '*.csv').
        filter_region: Optional region filter applied to every file.
        respiratory_only: If True, keep only respiratory rows.

    Returns:
        List of absolute output paths (one per input file processed).
    """
    input_path = Path(input_dir).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    csv_files = sorted(input_path.glob(pattern))
    if not csv_files:
        logger.warning("No files matching %s in %s", pattern, input_path)
        return []

    logger.info("Found %d CSV file(s) in %s", len(csv_files), input_path)
    outputs = []

    for csv_file in csv_files:
        stem = csv_file.stem
        out_file = output_path / f"{stem}_processed.csv"
        logger.info("Processing: %s → %s", csv_file.name, out_file.name)
        try:
            result = process_health_file(
                input_path=str(csv_file),
                output_path=str(out_file),
                filter_region=filter_region,
                respiratory_only=respiratory_only,
            )
            outputs.append(result)
        except Exception as exc:
            logger.error("Failed to process %s: %s", csv_file.name, exc, exc_info=True)

    return outputs


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="MINSAL DEIS Health Data Processor (Atenciones de Urgencia)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a single file
  %(prog)s --input AtencionesUrgencia2024.csv --output ./data/salud/out.csv

  # Process all files in a directory, respiratory only
  %(prog)s --input-dir ./raw/ --output ./data/salud/ --respiratory-only

  # Filter to a single region
  %(prog)s --input AtencionesUrgencia2024.csv \\
           --output ./data/salud/biobio.csv \\
           --filter-region Biobio
        """,
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Path to a single input CSV file.",
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        help="Path to directory containing input CSV files.",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.csv",
        help="Glob pattern for --input-dir (default: *.csv).",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Path for the output CSV file (--input mode).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Directory for output CSVs (--input-dir mode).",
    )
    parser.add_argument(
        "--filter-region",
        type=str,
        default=None,
        help="Keep only rows for the given region (canonical or alias name).",
    )
    parser.add_argument(
        "--respiratory-only",
        action="store_true",
        help="Emit only rows classified as respiratory conditions.",
    )
    parser.add_argument(
        "--encoding",
        type=str,
        default=None,
        help="Override auto-detected encoding (e.g. latin-1, utf-8).",
    )

    args = parser.parse_args()

    if not args.input and not args.input_dir:
        parser.error("Either --input or --input-dir is required.")
    if args.input and not args.output:
        parser.error("--output is required when using --input.")
    if args.input_dir and not args.output_dir:
        parser.error("--output-dir is required when using --input-dir.")

    try:
        if args.input:
            output = process_health_file(
                input_path=args.input,
                output_path=args.output,
                filter_region=args.filter_region,
                respiratory_only=args.respiratory_only,
            )
            logger.info("Processed file: %s", output)
        else:
            outputs = process_health_directory(
                input_dir=args.input_dir,
                output_dir=args.output_dir,
                pattern=args.pattern,
                filter_region=args.filter_region,
                respiratory_only=args.respiratory_only,
            )
            logger.info("Batch complete. %d file(s) processed.", len(outputs))
            for p in outputs:
                logger.info("  → %s", p)
    except Exception as exc:
        logger.error("Fatal error: %s", exc, exc_info=True)
        raise
