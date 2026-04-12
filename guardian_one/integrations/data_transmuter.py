"""Data Transmuter — McGonagall-level data transformation engine.

Turns CSV into JSON. JSON into YAML. YAML into Parquet-ready dicts.
Markdown into structured data. Unstructured text into tagged records.
Any format in, any format out — like Transfiguration class, but for bytes.

The Archivist uses this to normalise data from every source into a
unified format before indexing, syncing, or archiving.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import yaml


class DataFormat(Enum):
    JSON = "json"
    YAML = "yaml"
    CSV = "csv"
    TSV = "tsv"
    MARKDOWN_TABLE = "markdown_table"
    KEY_VALUE = "key_value"
    RAW_TEXT = "raw_text"


@dataclass
class TransmutationResult:
    """Result of a data transformation."""
    success: bool
    source_format: DataFormat
    target_format: DataFormat
    data: Any = None
    error: str = ""
    record_count: int = 0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class DataTransmuter:
    """McGonagall-level data format transformer.

    Feed it data in any supported format, tell it what you want,
    and it transfigures. No wand required.
    """

    # ------------------------------------------------------------------
    # Detection — figure out what we're looking at
    # ------------------------------------------------------------------

    @staticmethod
    def detect_format(data: str) -> DataFormat:
        """Auto-detect the format of a string payload."""
        stripped = data.strip()

        # JSON — starts with { or [
        if stripped and stripped[0] in ('{', '['):
            try:
                json.loads(stripped)
                return DataFormat.JSON
            except (json.JSONDecodeError, ValueError):
                pass

        # YAML — has key: value patterns, not CSV
        if re.search(r'^[\w_]+\s*:', stripped, re.MULTILINE):
            try:
                parsed = yaml.safe_load(stripped)
                if isinstance(parsed, (dict, list)):
                    return DataFormat.YAML
            except yaml.YAMLError:
                pass

        # Markdown table — has | delimiters and --- separator
        if '|' in stripped and re.search(r'\|[\s\-]+\|', stripped):
            return DataFormat.MARKDOWN_TABLE

        # CSV — comma-separated with consistent column count
        lines = stripped.split('\n')
        if len(lines) >= 2 and ',' in lines[0]:
            cols = len(lines[0].split(','))
            if all(len(line.split(',')) == cols for line in lines[:5] if line.strip()):
                return DataFormat.CSV

        # TSV
        if len(lines) >= 2 and '\t' in lines[0]:
            return DataFormat.TSV

        # Key-value pairs
        if re.search(r'^[\w_]+\s*[=:]\s*.+$', stripped, re.MULTILINE):
            kv_lines = [l for l in lines if re.match(r'[\w_]+\s*[=:]\s*.+', l)]
            if len(kv_lines) >= 2:
                return DataFormat.KEY_VALUE

        return DataFormat.RAW_TEXT

    # ------------------------------------------------------------------
    # Parsing — turn raw strings into Python structures
    # ------------------------------------------------------------------

    @staticmethod
    def parse(data: str, fmt: DataFormat | None = None) -> Any:
        """Parse a string into a Python data structure."""
        if fmt is None:
            fmt = DataTransmuter.detect_format(data)

        if fmt == DataFormat.JSON:
            return json.loads(data)

        if fmt == DataFormat.YAML:
            return yaml.safe_load(data)

        if fmt == DataFormat.CSV:
            reader = csv.DictReader(io.StringIO(data))
            return list(reader)

        if fmt == DataFormat.TSV:
            reader = csv.DictReader(io.StringIO(data), delimiter='\t')
            return list(reader)

        if fmt == DataFormat.MARKDOWN_TABLE:
            return DataTransmuter._parse_markdown_table(data)

        if fmt == DataFormat.KEY_VALUE:
            return DataTransmuter._parse_key_value(data)

        # RAW_TEXT — return as-is
        return data

    @staticmethod
    def _parse_markdown_table(data: str) -> list[dict[str, str]]:
        """Parse a markdown table into a list of dicts."""
        lines = [l.strip() for l in data.strip().split('\n') if l.strip()]
        if len(lines) < 3:
            return []

        # Extract headers
        headers = [h.strip() for h in lines[0].split('|') if h.strip()]
        # Skip separator line (index 1)
        rows: list[dict[str, str]] = []
        for line in lines[2:]:
            cells = [c.strip() for c in line.split('|') if c.strip()]
            if len(cells) == len(headers):
                rows.append(dict(zip(headers, cells)))
        return rows

    @staticmethod
    def _parse_key_value(data: str) -> dict[str, str]:
        """Parse key=value or key: value pairs."""
        result: dict[str, str] = {}
        for line in data.strip().split('\n'):
            line = line.strip()
            match = re.match(r'([\w_]+)\s*[=:]\s*(.+)', line)
            if match:
                result[match.group(1)] = match.group(2).strip()
        return result

    # ------------------------------------------------------------------
    # Serialisation — turn Python structures into strings
    # ------------------------------------------------------------------

    @staticmethod
    def serialize(data: Any, fmt: DataFormat) -> str:
        """Serialize a Python data structure into a string format."""
        if fmt == DataFormat.JSON:
            return json.dumps(data, indent=2, default=str)

        if fmt == DataFormat.YAML:
            return yaml.dump(data, default_flow_style=False, sort_keys=False)

        if fmt == DataFormat.CSV:
            return DataTransmuter._to_csv(data)

        if fmt == DataFormat.TSV:
            return DataTransmuter._to_csv(data, delimiter='\t')

        if fmt == DataFormat.MARKDOWN_TABLE:
            return DataTransmuter._to_markdown_table(data)

        if fmt == DataFormat.KEY_VALUE:
            if isinstance(data, dict):
                return '\n'.join(f"{k} = {v}" for k, v in data.items())
            return str(data)

        return str(data)

    @staticmethod
    def _to_csv(data: Any, delimiter: str = ',') -> str:
        """Convert list of dicts to CSV string."""
        if not isinstance(data, list) or not data:
            return ""
        if not isinstance(data[0], dict):
            return ""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys(), delimiter=delimiter)
        writer.writeheader()
        writer.writerows(data)
        return output.getvalue()

    @staticmethod
    def _to_markdown_table(data: Any) -> str:
        """Convert list of dicts to a markdown table."""
        if not isinstance(data, list) or not data:
            return ""
        if not isinstance(data[0], dict):
            return ""
        headers = list(data[0].keys())
        lines = ['| ' + ' | '.join(headers) + ' |']
        lines.append('| ' + ' | '.join('---' for _ in headers) + ' |')
        for row in data:
            lines.append('| ' + ' | '.join(str(row.get(h, '')) for h in headers) + ' |')
        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # Transmute — the main act
    # ------------------------------------------------------------------

    @classmethod
    def transmute(
        cls,
        data: str,
        target: DataFormat,
        source: DataFormat | None = None,
    ) -> TransmutationResult:
        """Transform data from one format to another.

        Like McGonagall turning a desk into a pig — except it's
        CSV into JSON, and nobody gets detention.
        """
        detected = source or cls.detect_format(data)

        try:
            parsed = cls.parse(data, detected)
            output = cls.serialize(parsed, target)
            count = len(parsed) if isinstance(parsed, (list, dict)) else 1

            return TransmutationResult(
                success=True,
                source_format=detected,
                target_format=target,
                data=output,
                record_count=count,
            )
        except Exception as exc:
            return TransmutationResult(
                success=False,
                source_format=detected,
                target_format=target,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Convenience — common transformations
    # ------------------------------------------------------------------

    @classmethod
    def to_json(cls, data: str) -> TransmutationResult:
        return cls.transmute(data, DataFormat.JSON)

    @classmethod
    def to_yaml(cls, data: str) -> TransmutationResult:
        return cls.transmute(data, DataFormat.YAML)

    @classmethod
    def to_csv(cls, data: str) -> TransmutationResult:
        return cls.transmute(data, DataFormat.CSV)

    @classmethod
    def to_markdown(cls, data: str) -> TransmutationResult:
        return cls.transmute(data, DataFormat.MARKDOWN_TABLE)

    # ------------------------------------------------------------------
    # Schema extraction
    # ------------------------------------------------------------------

    @classmethod
    def extract_schema(cls, data: str) -> dict[str, Any]:
        """Extract the schema/structure of a data payload.

        Returns field names, types, and sample values.
        Useful for mapping data between systems.
        """
        fmt = cls.detect_format(data)
        parsed = cls.parse(data, fmt)

        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            sample = parsed[0]
            return {
                "format": fmt.value,
                "record_count": len(parsed),
                "fields": {
                    k: {"type": type(v).__name__, "sample": str(v)[:100]}
                    for k, v in sample.items()
                },
            }

        if isinstance(parsed, dict):
            return {
                "format": fmt.value,
                "record_count": 1,
                "fields": {
                    k: {"type": type(v).__name__, "sample": str(v)[:100]}
                    for k, v in parsed.items()
                },
            }

        return {"format": fmt.value, "record_count": 1, "fields": {}}
