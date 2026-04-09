"""DataCollector — Public Dataset Acquisition Agent.

Responsibilities:
- Discover and download public datasets from government and research sources
- Validate dataset schemas (columns, types, row counts)
- Compute integrity hashes (SHA-256) for all downloaded files
- Maintain a metadata index at data/datasets/index.json
- Respect API rate limits with configurable delays
- Search for datasets by keyword across all sources
- Track freshness and re-download stale datasets

Sources:
    - data.gov (CKAN API)
    - Census Bureau (API)
    - CMS (Centers for Medicare & Medicaid Services)
    - HHS (Health & Human Services)
    - PubMed (NCBI E-utilities)
    - Kaggle (requires API key, graceful skip if missing)
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class DatasetStatus(Enum):
    """Lifecycle status of a tracked dataset."""
    DISCOVERED = "discovered"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    VALIDATED = "validated"
    STALE = "stale"
    ERROR = "error"


class DataSource(Enum):
    """Supported public data sources."""
    DATA_GOV = "data.gov"
    CENSUS = "census"
    CMS = "cms"
    HHS = "hhs"
    PUBMED = "pubmed"
    KAGGLE = "kaggle"


@dataclass
class DatasetSchema:
    """Schema information extracted from a dataset."""
    columns: list[str] = field(default_factory=list)
    column_types: dict[str, str] = field(default_factory=dict)
    row_count: int = 0
    file_format: str = ""
    size_bytes: int = 0


@dataclass
class DatasetRecord:
    """Metadata for a single dataset in the index."""
    dataset_id: str
    title: str
    source: str
    source_url: str
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    local_path: str = ""
    sha256: str = ""
    schema: DatasetSchema = field(default_factory=DatasetSchema)
    status: str = DatasetStatus.DISCOVERED.value
    discovered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    downloaded_at: str = ""
    last_checked: str = ""
    refresh_interval_hours: int = 168  # 7 days default
    download_count: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DatasetRecord:
        schema_data = d.pop("schema", {})
        schema = DatasetSchema(**schema_data) if schema_data else DatasetSchema()
        return cls(schema=schema, **d)


# ---------------------------------------------------------------------------
# Source API configuration
# ---------------------------------------------------------------------------

SOURCE_ENDPOINTS: dict[str, str] = {
    DataSource.DATA_GOV.value: "https://catalog.data.gov/api/3/action/package_search",
    DataSource.CENSUS.value: "https://api.census.gov/data.json",
    DataSource.CMS.value: "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items",
    DataSource.HHS.value: "https://healthdata.gov/api/3/action/package_search",
    DataSource.PUBMED.value: "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
    DataSource.KAGGLE.value: "https://www.kaggle.com/api/v1/datasets/list",
}

DEFAULT_RATE_LIMIT_SECONDS: dict[str, float] = {
    DataSource.DATA_GOV.value: 0.5,
    DataSource.CENSUS.value: 1.0,
    DataSource.CMS.value: 0.5,
    DataSource.HHS.value: 0.5,
    DataSource.PUBMED.value: 0.34,  # NCBI: max 3 req/sec without API key
    DataSource.KAGGLE.value: 1.0,
}


# ---------------------------------------------------------------------------
# HTTP abstraction (injectable for testing)
# ---------------------------------------------------------------------------

class HTTPClient:
    """Thin wrapper around urllib for testability."""

    def get(self, url: str, headers: dict[str, str] | None = None,
            params: dict[str, str] | None = None,
            timeout: int = 30) -> HTTPResponse:
        """Perform an HTTP GET request."""
        import urllib.request
        import urllib.error

        if params:
            url = f"{url}?{urlencode(params)}"
        req = urllib.request.Request(url, headers=headers or {})
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            body = resp.read()
            return HTTPResponse(
                status_code=resp.status,
                body=body,
                headers=dict(resp.headers),
            )
        except urllib.error.HTTPError as exc:
            return HTTPResponse(
                status_code=exc.code,
                body=exc.read() if exc.fp else b"",
                headers=dict(exc.headers) if exc.headers else {},
                error=str(exc),
            )
        except Exception as exc:
            return HTTPResponse(
                status_code=0,
                body=b"",
                headers={},
                error=str(exc),
            )


@dataclass
class HTTPResponse:
    """Simple HTTP response container."""
    status_code: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)
    error: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# DataCollector agent
# ---------------------------------------------------------------------------

class DataCollector(BaseAgent):
    """Public dataset acquisition agent.

    Discovers, downloads, validates, and indexes public datasets from
    government and research data portals.
    """

    def __init__(self, config: AgentConfig, audit: AuditLog) -> None:
        super().__init__(config, audit)
        self._datasets: dict[str, DatasetRecord] = {}
        self._datasets_dir: Path = Path(
            config.custom.get("datasets_dir", "data/datasets")
        )
        self._index_path: Path = self._datasets_dir / "index.json"
        self._http: HTTPClient = HTTPClient()
        self._rate_limits: dict[str, float] = dict(DEFAULT_RATE_LIMIT_SECONDS)
        self._last_request_time: dict[str, float] = {}
        self._enabled_sources: list[str] = [s.value for s in DataSource]
        self._max_datasets_per_search: int = int(
            config.custom.get("max_datasets_per_search", 10)
        )
        self._stale_threshold_hours: int = int(
            config.custom.get("stale_threshold_hours", 168)
        )

    # ------------------------------------------------------------------
    # HTTP client injection (for testing)
    # ------------------------------------------------------------------

    def set_http_client(self, client: HTTPClient) -> None:
        """Replace the HTTP client (used for dependency injection in tests)."""
        self._http = client

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _wait_for_rate_limit(self, source: str) -> None:
        """Sleep if needed to respect API rate limits."""
        delay = self._rate_limits.get(source, 0.5)
        last = self._last_request_time.get(source, 0.0)
        elapsed = time.time() - last
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_time[source] = time.time()

    def set_rate_limit(self, source: str, seconds: float) -> None:
        """Override rate limit for a source."""
        self._rate_limits[source] = seconds

    # ------------------------------------------------------------------
    # Index persistence
    # ------------------------------------------------------------------

    def _ensure_datasets_dir(self) -> None:
        """Create the datasets directory if it doesn't exist."""
        self._datasets_dir.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> None:
        """Load the dataset index from disk."""
        if self._index_path.exists():
            try:
                raw = json.loads(self._index_path.read_text(encoding="utf-8"))
                for entry in raw.get("datasets", []):
                    record = DatasetRecord.from_dict(entry)
                    self._datasets[record.dataset_id] = record
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                self.log(
                    "index_load_error",
                    severity=Severity.WARNING,
                    details={"error": str(exc)},
                )

    def _save_index(self) -> None:
        """Persist the dataset index to disk."""
        self._ensure_datasets_dir()
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "dataset_count": len(self._datasets),
            "datasets": [r.to_dict() for r in self._datasets.values()],
        }
        self._index_path.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Discovery — search across sources
    # ------------------------------------------------------------------

    def search(self, keyword: str, sources: list[str] | None = None) -> list[DatasetRecord]:
        """Search for datasets matching a keyword across configured sources.

        Args:
            keyword: Search term.
            sources: Optional list of source names to search. Defaults to all.

        Returns:
            List of DatasetRecord objects discovered.
        """
        targets = sources or self._enabled_sources
        results: list[DatasetRecord] = []

        for source in targets:
            try:
                found = self._search_source(source, keyword)
                results.extend(found)
            except Exception as exc:
                self.log(
                    "search_error",
                    severity=Severity.WARNING,
                    details={"source": source, "keyword": keyword, "error": str(exc)},
                )

        # Register discovered datasets
        for record in results:
            if record.dataset_id not in self._datasets:
                self._datasets[record.dataset_id] = record

        if results:
            self._save_index()
            self.log("search_complete", details={
                "keyword": keyword,
                "results_count": len(results),
                "sources_searched": targets,
            })

        return results

    def _search_source(self, source: str, keyword: str) -> list[DatasetRecord]:
        """Search a single data source for datasets matching keyword."""
        dispatch = {
            DataSource.DATA_GOV.value: self._search_data_gov,
            DataSource.CENSUS.value: self._search_census,
            DataSource.CMS.value: self._search_cms,
            DataSource.HHS.value: self._search_hhs,
            DataSource.PUBMED.value: self._search_pubmed,
            DataSource.KAGGLE.value: self._search_kaggle,
        }

        handler = dispatch.get(source)
        if handler is None:
            return []

        self._wait_for_rate_limit(source)
        return handler(keyword)

    # -- data.gov (CKAN) --

    def _search_data_gov(self, keyword: str) -> list[DatasetRecord]:
        endpoint = SOURCE_ENDPOINTS[DataSource.DATA_GOV.value]
        params = {"q": keyword, "rows": str(self._max_datasets_per_search)}
        resp = self._http.get(endpoint, params=params)
        if not resp.ok:
            return []

        data = resp.json()
        results_list = data.get("result", {}).get("results", [])
        records: list[DatasetRecord] = []
        for item in results_list[:self._max_datasets_per_search]:
            resources = item.get("resources", [])
            download_url = ""
            if resources:
                download_url = resources[0].get("url", "")

            records.append(DatasetRecord(
                dataset_id=f"datagov_{item.get('id', '')}",
                title=item.get("title", "Untitled"),
                source=DataSource.DATA_GOV.value,
                source_url=download_url,
                description=item.get("notes", "")[:500],
                keywords=[keyword] + item.get("tags", []),
            ))
        return records

    # -- Census Bureau --

    def _search_census(self, keyword: str) -> list[DatasetRecord]:
        endpoint = SOURCE_ENDPOINTS[DataSource.CENSUS.value]
        resp = self._http.get(endpoint)
        if not resp.ok:
            return []

        data = resp.json()
        datasets = data.get("dataset", [])
        records: list[DatasetRecord] = []
        kw_lower = keyword.lower()

        for item in datasets:
            title = item.get("title", "")
            desc = item.get("description", "")
            if kw_lower not in title.lower() and kw_lower not in desc.lower():
                continue

            dist = item.get("distribution", [])
            download_url = dist[0].get("accessURL", "") if dist else ""

            records.append(DatasetRecord(
                dataset_id=f"census_{item.get('identifier', title[:30])}",
                title=title,
                source=DataSource.CENSUS.value,
                source_url=download_url,
                description=desc[:500],
                keywords=[keyword],
            ))
            if len(records) >= self._max_datasets_per_search:
                break

        return records

    # -- CMS --

    def _search_cms(self, keyword: str) -> list[DatasetRecord]:
        endpoint = SOURCE_ENDPOINTS[DataSource.CMS.value]
        params = {"keyword": keyword}
        resp = self._http.get(endpoint, params=params)
        if not resp.ok:
            return []

        items = resp.json() if isinstance(resp.json(), list) else []
        records: list[DatasetRecord] = []
        for item in items[:self._max_datasets_per_search]:
            title = item.get("title", "Untitled")
            download_url = item.get("downloadURL", "")
            records.append(DatasetRecord(
                dataset_id=f"cms_{item.get('identifier', title[:30])}",
                title=title,
                source=DataSource.CMS.value,
                source_url=download_url,
                description=item.get("description", "")[:500],
                keywords=[keyword],
            ))
        return records

    # -- HHS --

    def _search_hhs(self, keyword: str) -> list[DatasetRecord]:
        endpoint = SOURCE_ENDPOINTS[DataSource.HHS.value]
        params = {"q": keyword, "rows": str(self._max_datasets_per_search)}
        resp = self._http.get(endpoint, params=params)
        if not resp.ok:
            return []

        data = resp.json()
        results_list = data.get("result", {}).get("results", [])
        records: list[DatasetRecord] = []
        for item in results_list[:self._max_datasets_per_search]:
            resources = item.get("resources", [])
            download_url = resources[0].get("url", "") if resources else ""
            records.append(DatasetRecord(
                dataset_id=f"hhs_{item.get('id', '')}",
                title=item.get("title", "Untitled"),
                source=DataSource.HHS.value,
                source_url=download_url,
                description=item.get("notes", "")[:500],
                keywords=[keyword],
            ))
        return records

    # -- PubMed (NCBI E-utilities) --

    def _search_pubmed(self, keyword: str) -> list[DatasetRecord]:
        endpoint = SOURCE_ENDPOINTS[DataSource.PUBMED.value]
        params = {
            "db": "pubmed",
            "term": keyword,
            "retmode": "json",
            "retmax": str(self._max_datasets_per_search),
        }
        resp = self._http.get(endpoint, params=params)
        if not resp.ok:
            return []

        data = resp.json()
        id_list = data.get("esearchresult", {}).get("idlist", [])
        records: list[DatasetRecord] = []
        for pmid in id_list[:self._max_datasets_per_search]:
            records.append(DatasetRecord(
                dataset_id=f"pubmed_{pmid}",
                title=f"PubMed Article {pmid}",
                source=DataSource.PUBMED.value,
                source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                keywords=[keyword],
            ))
        return records

    # -- Kaggle --

    def _search_kaggle(self, keyword: str) -> list[DatasetRecord]:
        api_key = os.environ.get("KAGGLE_KEY", "")
        api_user = os.environ.get("KAGGLE_USERNAME", "")
        if not api_key or not api_user:
            self.log(
                "kaggle_skip",
                severity=Severity.INFO,
                details={"reason": "KAGGLE_KEY or KAGGLE_USERNAME not set"},
            )
            return []

        endpoint = SOURCE_ENDPOINTS[DataSource.KAGGLE.value]
        params = {"search": keyword}
        import base64
        creds = base64.b64encode(f"{api_user}:{api_key}".encode()).decode()
        headers = {"Authorization": f"Basic {creds}"}

        resp = self._http.get(endpoint, headers=headers, params=params)
        if not resp.ok:
            return []

        items = resp.json() if isinstance(resp.json(), list) else []
        records: list[DatasetRecord] = []
        for item in items[:self._max_datasets_per_search]:
            ref = item.get("ref", "")
            records.append(DatasetRecord(
                dataset_id=f"kaggle_{ref}",
                title=item.get("title", ref),
                source=DataSource.KAGGLE.value,
                source_url=f"https://www.kaggle.com/datasets/{ref}",
                description=item.get("subtitle", "")[:500],
                keywords=[keyword],
            ))
        return records

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download(self, dataset_id: str) -> DatasetRecord | None:
        """Download a dataset by its ID.

        Returns the updated DatasetRecord, or None if not found.
        """
        record = self._datasets.get(dataset_id)
        if record is None:
            self.log(
                "download_not_found",
                severity=Severity.WARNING,
                details={"dataset_id": dataset_id},
            )
            return None

        if not record.source_url:
            record.status = DatasetStatus.ERROR.value
            record.errors.append("No source URL available")
            self._save_index()
            return record

        record.status = DatasetStatus.DOWNLOADING.value
        self._wait_for_rate_limit(record.source)

        resp = self._http.get(record.source_url)
        if not resp.ok:
            record.status = DatasetStatus.ERROR.value
            record.errors.append(f"Download failed: HTTP {resp.status_code}")
            self._save_index()
            self.log(
                "download_failed",
                severity=Severity.ERROR,
                details={
                    "dataset_id": dataset_id,
                    "status_code": resp.status_code,
                    "error": resp.error,
                },
            )
            return record

        # Determine filename
        safe_id = dataset_id.replace("/", "_").replace("\\", "_")
        ext = self._guess_extension(resp)
        filename = f"{safe_id}{ext}"
        filepath = self._datasets_dir / filename

        self._ensure_datasets_dir()
        filepath.write_bytes(resp.body)

        # Compute integrity hash
        sha256 = hashlib.sha256(resp.body).hexdigest()

        record.local_path = str(filepath)
        record.sha256 = sha256
        record.status = DatasetStatus.DOWNLOADED.value
        record.downloaded_at = datetime.now(timezone.utc).isoformat()
        record.last_checked = record.downloaded_at
        record.download_count += 1
        record.schema.size_bytes = len(resp.body)

        self._save_index()
        self.log("download_complete", details={
            "dataset_id": dataset_id,
            "path": str(filepath),
            "size_bytes": len(resp.body),
            "sha256": sha256[:16] + "...",
        })
        return record

    def _guess_extension(self, resp: HTTPResponse) -> str:
        """Guess a file extension from response headers or content."""
        content_type = resp.headers.get("Content-Type", "").lower()
        if "csv" in content_type:
            return ".csv"
        if "json" in content_type:
            return ".json"
        if "xml" in content_type:
            return ".xml"
        if "zip" in content_type or "octet-stream" in content_type:
            return ".zip"
        if "excel" in content_type or "spreadsheet" in content_type:
            return ".xlsx"

        # Sniff content
        try:
            text = resp.body[:200].decode("utf-8", errors="ignore")
            if text.strip().startswith("{") or text.strip().startswith("["):
                return ".json"
            if "," in text and "\n" in text:
                return ".csv"
            if text.strip().startswith("<"):
                return ".xml"
        except Exception:
            pass

        return ".dat"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, dataset_id: str) -> DatasetSchema | None:
        """Validate a downloaded dataset — check schema, row count, types.

        Returns the DatasetSchema, or None if the dataset isn't found/downloaded.
        """
        record = self._datasets.get(dataset_id)
        if record is None:
            return None
        if not record.local_path:
            return None

        filepath = Path(record.local_path)
        if not filepath.exists():
            record.status = DatasetStatus.ERROR.value
            record.errors.append("Local file missing")
            self._save_index()
            return None

        file_bytes = filepath.read_bytes()

        # Verify integrity
        computed_hash = hashlib.sha256(file_bytes).hexdigest()
        if record.sha256 and computed_hash != record.sha256:
            record.status = DatasetStatus.ERROR.value
            record.errors.append(
                f"Integrity check failed: expected {record.sha256[:16]}..., "
                f"got {computed_hash[:16]}..."
            )
            self._save_index()
            self.log("validation_integrity_fail", severity=Severity.ERROR, details={
                "dataset_id": dataset_id,
            })
            return None

        schema = self._extract_schema(filepath, file_bytes)
        record.schema = schema
        record.status = DatasetStatus.VALIDATED.value
        record.last_checked = datetime.now(timezone.utc).isoformat()
        self._save_index()

        self.log("validation_complete", details={
            "dataset_id": dataset_id,
            "columns": len(schema.columns),
            "rows": schema.row_count,
            "format": schema.file_format,
        })
        return schema

    def _extract_schema(self, filepath: Path, file_bytes: bytes) -> DatasetSchema:
        """Extract schema information from a file."""
        ext = filepath.suffix.lower()
        schema = DatasetSchema(
            size_bytes=len(file_bytes),
            file_format=ext.lstrip(".") or "unknown",
        )

        if ext == ".csv":
            schema = self._extract_csv_schema(file_bytes, schema)
        elif ext == ".json":
            schema = self._extract_json_schema(file_bytes, schema)
        elif ext == ".xml":
            schema.file_format = "xml"
            # Basic: just count lines as a proxy
            schema.row_count = file_bytes.count(b"\n")

        return schema

    def _extract_csv_schema(self, file_bytes: bytes, schema: DatasetSchema) -> DatasetSchema:
        """Parse CSV to extract columns, types, row count."""
        text = file_bytes.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)

        if not rows:
            return schema

        schema.columns = rows[0]
        data_rows = rows[1:]
        schema.row_count = len(data_rows)
        schema.file_format = "csv"

        # Infer column types from first data row
        if data_rows:
            for i, col in enumerate(schema.columns):
                if i < len(data_rows[0]):
                    schema.column_types[col] = self._infer_type(data_rows[0][i])

        return schema

    def _extract_json_schema(self, file_bytes: bytes, schema: DatasetSchema) -> DatasetSchema:
        """Parse JSON to extract schema info."""
        try:
            data = json.loads(file_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            schema.file_format = "json"
            return schema

        schema.file_format = "json"

        if isinstance(data, list):
            schema.row_count = len(data)
            if data and isinstance(data[0], dict):
                schema.columns = list(data[0].keys())
                for key, val in data[0].items():
                    schema.column_types[key] = type(val).__name__
        elif isinstance(data, dict):
            schema.columns = list(data.keys())
            schema.row_count = 1

        return schema

    @staticmethod
    def _infer_type(value: str) -> str:
        """Infer the data type of a string value."""
        if not value or value.strip() == "":
            return "empty"
        try:
            int(value)
            return "integer"
        except ValueError:
            pass
        try:
            float(value)
            return "float"
        except ValueError:
            pass
        low = value.lower()
        if low in ("true", "false"):
            return "boolean"
        return "string"

    # ------------------------------------------------------------------
    # Refresh / staleness
    # ------------------------------------------------------------------

    def stale_datasets(self) -> list[DatasetRecord]:
        """Find datasets that are past their refresh interval."""
        now = datetime.now(timezone.utc)
        stale: list[DatasetRecord] = []

        for record in self._datasets.values():
            if record.status == DatasetStatus.ERROR.value:
                continue
            if not record.downloaded_at:
                continue

            try:
                downloaded_dt = datetime.fromisoformat(record.downloaded_at)
            except (ValueError, TypeError):
                continue

            if downloaded_dt.tzinfo is None:
                downloaded_dt = downloaded_dt.replace(tzinfo=timezone.utc)

            hours_since = (now - downloaded_dt).total_seconds() / 3600
            threshold = record.refresh_interval_hours or self._stale_threshold_hours
            if hours_since > threshold:
                record.status = DatasetStatus.STALE.value
                stale.append(record)

        return stale

    def refresh(self, dataset_id: str) -> DatasetRecord | None:
        """Re-download and re-validate a dataset.

        Returns the updated record, or None if not found.
        """
        record = self._datasets.get(dataset_id)
        if record is None:
            return None

        downloaded = self.download(dataset_id)
        if downloaded and downloaded.status == DatasetStatus.DOWNLOADED.value:
            self.validate(dataset_id)

        self.log("refresh_complete", details={"dataset_id": dataset_id})
        return self._datasets.get(dataset_id)

    def refresh_stale(self) -> list[DatasetRecord]:
        """Refresh all stale datasets. Returns list of refreshed records."""
        stale = self.stale_datasets()
        refreshed: list[DatasetRecord] = []
        for record in stale:
            result = self.refresh(record.dataset_id)
            if result:
                refreshed.append(result)
        return refreshed

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_dataset(self, dataset_id: str) -> DatasetRecord | None:
        """Retrieve a dataset record by ID."""
        return self._datasets.get(dataset_id)

    def list_datasets(self, source: str | None = None,
                      status: str | None = None) -> list[DatasetRecord]:
        """List all known datasets, optionally filtered by source or status."""
        results = list(self._datasets.values())
        if source:
            results = [r for r in results if r.source == source]
        if status:
            results = [r for r in results if r.status == status]
        return results

    def dataset_count(self) -> int:
        """Return the total number of tracked datasets."""
        return len(self._datasets)

    def datasets_by_source(self) -> dict[str, int]:
        """Count datasets grouped by source."""
        counts: dict[str, int] = {}
        for record in self._datasets.values():
            counts[record.source] = counts.get(record.source, 0) + 1
        return counts

    def remove_dataset(self, dataset_id: str, delete_file: bool = False) -> bool:
        """Remove a dataset from the index (and optionally from disk).

        Returns True if the dataset was found and removed.
        """
        record = self._datasets.pop(dataset_id, None)
        if record is None:
            return False

        if delete_file and record.local_path:
            filepath = Path(record.local_path)
            if filepath.exists():
                filepath.unlink()

        self._save_index()
        self.log("dataset_removed", details={"dataset_id": dataset_id})
        return True

    # ------------------------------------------------------------------
    # BaseAgent lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Set up the data collector: create directories, load index."""
        self._set_status(AgentStatus.IDLE)
        self._ensure_datasets_dir()
        self._load_index()
        self.log("initialized", details={
            "datasets_dir": str(self._datasets_dir),
            "indexed_datasets": len(self._datasets),
            "enabled_sources": self._enabled_sources,
        })

    def run(self) -> AgentReport:
        """Execute a collection cycle: check staleness, report status."""
        self._set_status(AgentStatus.RUNNING)
        actions: list[str] = []
        alerts: list[str] = []
        recommendations: list[str] = []

        # Check for stale datasets
        stale = self.stale_datasets()
        if stale:
            alerts.append(f"{len(stale)} dataset(s) are stale and need refresh.")
            for s in stale[:5]:
                recommendations.append(
                    f"Refresh '{s.title}' (last downloaded: {s.downloaded_at or 'never'})"
                )
        actions.append(f"Checked staleness for {len(self._datasets)} dataset(s).")

        # Check for error datasets
        errored = [d for d in self._datasets.values()
                    if d.status == DatasetStatus.ERROR.value]
        if errored:
            alerts.append(f"{len(errored)} dataset(s) in error state.")

        # Dataset stats
        by_source = self.datasets_by_source()
        validated_count = len([
            d for d in self._datasets.values()
            if d.status == DatasetStatus.VALIDATED.value
        ])

        self._set_status(AgentStatus.IDLE)
        return AgentReport(
            agent_name=self.name,
            status=AgentStatus.IDLE.value,
            summary=(
                f"Tracking {len(self._datasets)} dataset(s) across "
                f"{len(by_source)} source(s). "
                f"{validated_count} validated, {len(stale)} stale, "
                f"{len(errored)} errored."
            ),
            actions_taken=actions,
            recommendations=recommendations,
            alerts=alerts,
            data={
                "total_datasets": len(self._datasets),
                "by_source": by_source,
                "validated": validated_count,
                "stale": len(stale),
                "errored": len(errored),
                "datasets_dir": str(self._datasets_dir),
            },
        )

    def report(self) -> AgentReport:
        """Return a status report without side effects."""
        by_source = self.datasets_by_source()
        validated = len([
            d for d in self._datasets.values()
            if d.status == DatasetStatus.VALIDATED.value
        ])
        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary=(
                f"DataCollector: {len(self._datasets)} dataset(s), "
                f"{validated} validated, across {len(by_source)} source(s)."
            ),
            data={
                "total_datasets": len(self._datasets),
                "by_source": by_source,
                "validated": validated,
                "sources": self._enabled_sources,
                "datasets_dir": str(self._datasets_dir),
            },
        )
