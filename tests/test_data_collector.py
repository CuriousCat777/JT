"""Tests for DataCollector — public dataset acquisition agent."""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from guardian_one.core.audit import AuditLog
from guardian_one.core.base_agent import AgentStatus
from guardian_one.core.config import AgentConfig
from guardian_one.agents.data_collector import (
    DataCollector,
    DatasetRecord,
    DatasetSchema,
    DatasetStatus,
    DataSource,
    HTTPClient,
    HTTPResponse,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


def _make_collector(tmpdir: str | None = None) -> DataCollector:
    d = tmpdir or tempfile.mkdtemp()
    config = AgentConfig(
        name="data_collector",
        custom={"datasets_dir": d, "max_datasets_per_search": 5},
    )
    dc = DataCollector(config, _make_audit())
    dc.set_rate_limit("data.gov", 0)
    dc.set_rate_limit("census", 0)
    dc.set_rate_limit("cms", 0)
    dc.set_rate_limit("hhs", 0)
    dc.set_rate_limit("pubmed", 0)
    dc.set_rate_limit("kaggle", 0)
    return dc


class MockHTTP(HTTPClient):
    """HTTP client that returns canned responses."""

    def __init__(self):
        self.responses: dict[str, HTTPResponse] = {}
        self.calls: list[str] = []
        self._default = HTTPResponse(status_code=200, body=b'{}')

    def add(self, url_fragment: str, body: bytes | dict | list,
            status_code: int = 200, headers: dict | None = None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        self.responses[url_fragment] = HTTPResponse(
            status_code=status_code, body=body, headers=headers or {},
        )

    def get(self, url, headers=None, params=None, timeout=30):
        self.calls.append(url)
        for frag, resp in self.responses.items():
            if frag in url:
                return resp
        return self._default


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def test_initialize():
    dc = _make_collector()
    dc.initialize()
    assert dc.status == AgentStatus.IDLE


def test_run_empty():
    dc = _make_collector()
    dc.initialize()
    report = dc.run()
    assert report.agent_name == "data_collector"
    assert "0 dataset" in report.summary


def test_report_empty():
    dc = _make_collector()
    dc.initialize()
    report = dc.report()
    assert report.data["total_datasets"] == 0


# ---------------------------------------------------------------------------
# Search — data.gov
# ---------------------------------------------------------------------------

def test_search_data_gov():
    dc = _make_collector()
    dc.initialize()
    mock = MockHTTP()
    mock.add("catalog.data.gov", {
        "result": {"results": [
            {"id": "abc123", "title": "Hospital Data", "notes": "Test",
             "tags": [], "resources": [{"url": "http://example.com/data.csv"}]},
            {"id": "def456", "title": "Physician Payments", "notes": "Test2",
             "tags": [], "resources": [{"url": "http://example.com/pay.csv"}]},
        ]}
    })
    dc.set_http_client(mock)
    results = dc.search("hospital", sources=["data.gov"])
    assert len(results) == 2
    assert results[0].title == "Hospital Data"
    assert results[0].source == "data.gov"
    assert dc.dataset_count() == 2


# ---------------------------------------------------------------------------
# Search — Census
# ---------------------------------------------------------------------------

def test_search_census():
    dc = _make_collector()
    dc.initialize()
    mock = MockHTTP()
    mock.add("api.census.gov", {
        "dataset": [
            {"title": "Population Estimates", "description": "Annual pop",
             "identifier": "pop2024", "distribution": [{"accessURL": "http://census.gov/pop.csv"}]},
            {"title": "Housing Data", "description": "Housing stats",
             "identifier": "house2024", "distribution": []},
            {"title": "Unrelated Data", "description": "No match", "identifier": "x"},
        ]
    })
    dc.set_http_client(mock)
    results = dc.search("population", sources=["census"])
    assert len(results) == 1
    assert "Population" in results[0].title


# ---------------------------------------------------------------------------
# Search — CMS
# ---------------------------------------------------------------------------

def test_search_cms():
    dc = _make_collector()
    dc.initialize()
    mock = MockHTTP()
    mock.add("data.cms.gov", [
        {"identifier": "cms001", "title": "Medicare Payments",
         "description": "Payment data", "downloadURL": "http://cms.gov/pay.csv"},
    ])
    dc.set_http_client(mock)
    results = dc.search("medicare", sources=["cms"])
    assert len(results) == 1
    assert results[0].source == "cms"


# ---------------------------------------------------------------------------
# Search — HHS
# ---------------------------------------------------------------------------

def test_search_hhs():
    dc = _make_collector()
    dc.initialize()
    mock = MockHTTP()
    mock.add("healthdata.gov", {
        "result": {"results": [
            {"id": "hhs001", "title": "Quality Metrics", "notes": "Hospital quality",
             "resources": [{"url": "http://hhs.gov/quality.csv"}]},
        ]}
    })
    dc.set_http_client(mock)
    results = dc.search("quality", sources=["hhs"])
    assert len(results) == 1
    assert results[0].source == "hhs"


# ---------------------------------------------------------------------------
# Search — PubMed
# ---------------------------------------------------------------------------

def test_search_pubmed():
    dc = _make_collector()
    dc.initialize()
    mock = MockHTTP()
    mock.add("eutils.ncbi.nlm.nih.gov", {
        "esearchresult": {"idlist": ["12345678", "87654321"]}
    })
    dc.set_http_client(mock)
    results = dc.search("hospitalist", sources=["pubmed"])
    assert len(results) == 2
    assert results[0].dataset_id == "pubmed_12345678"


# ---------------------------------------------------------------------------
# Search — Kaggle (skips without API key)
# ---------------------------------------------------------------------------

def test_search_kaggle_no_key():
    dc = _make_collector()
    dc.initialize()
    mock = MockHTTP()
    dc.set_http_client(mock)
    with patch.dict("os.environ", {}, clear=True):
        results = dc.search("health", sources=["kaggle"])
    assert len(results) == 0


def test_search_kaggle_with_key():
    dc = _make_collector()
    dc.initialize()
    mock = MockHTTP()
    mock.add("kaggle.com", [
        {"ref": "user/health-data", "title": "Health Dataset", "subtitle": "Public"},
    ])
    dc.set_http_client(mock)
    with patch.dict("os.environ", {"KAGGLE_KEY": "fake", "KAGGLE_USERNAME": "testuser"}):
        results = dc.search("health", sources=["kaggle"])
    assert len(results) == 1
    assert "kaggle" in results[0].dataset_id


# ---------------------------------------------------------------------------
# Search — multi-source
# ---------------------------------------------------------------------------

def test_search_all_sources():
    dc = _make_collector()
    dc.initialize()
    mock = MockHTTP()
    mock.add("catalog.data.gov", {"result": {"results": [
        {"id": "dg1", "title": "DG Result", "notes": "", "tags": [], "resources": []}
    ]}})
    mock.add("healthdata.gov", {"result": {"results": [
        {"id": "hhs1", "title": "HHS Result", "notes": "", "resources": []}
    ]}})
    mock.add("data.cms.gov", [])
    mock.add("api.census.gov", {"dataset": []})
    mock.add("eutils.ncbi.nlm.nih.gov", {"esearchresult": {"idlist": ["99999"]}})
    dc.set_http_client(mock)
    with patch.dict("os.environ", {}, clear=True):
        results = dc.search("test")
    assert len(results) >= 3


def test_search_error_handling():
    dc = _make_collector()
    dc.initialize()
    mock = MockHTTP()
    mock.add("catalog.data.gov", b'invalid json', status_code=500)
    dc.set_http_client(mock)
    results = dc.search("test", sources=["data.gov"])
    assert len(results) == 0


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def test_download_csv():
    dc = _make_collector()
    dc.initialize()
    dc._datasets["test1"] = DatasetRecord(
        dataset_id="test1", title="Test CSV",
        source="data.gov", source_url="http://example.com/test.csv",
    )
    mock = MockHTTP()
    csv_data = b"name,age,city\nAlice,30,NYC\nBob,25,LA\n"
    mock.add("example.com", csv_data, headers={"Content-Type": "text/csv"})
    dc.set_http_client(mock)

    result = dc.download("test1")
    assert result is not None
    assert result.status == DatasetStatus.DOWNLOADED.value
    assert result.sha256 != ""
    assert result.download_count == 1
    assert Path(result.local_path).exists()


def test_download_json():
    dc = _make_collector()
    dc.initialize()
    dc._datasets["test2"] = DatasetRecord(
        dataset_id="test2", title="Test JSON",
        source="cms", source_url="http://example.com/data.json",
    )
    mock = MockHTTP()
    json_data = json.dumps([{"id": 1, "value": "a"}, {"id": 2, "value": "b"}]).encode()
    mock.add("example.com", json_data, headers={"Content-Type": "application/json"})
    dc.set_http_client(mock)

    result = dc.download("test2")
    assert result is not None
    assert result.status == DatasetStatus.DOWNLOADED.value


def test_download_not_found():
    dc = _make_collector()
    dc.initialize()
    result = dc.download("nonexistent")
    assert result is None


def test_download_no_url():
    dc = _make_collector()
    dc.initialize()
    dc._datasets["no_url"] = DatasetRecord(
        dataset_id="no_url", title="No URL", source="test", source_url="",
    )
    result = dc.download("no_url")
    assert result is not None
    assert result.status == DatasetStatus.ERROR.value


def test_download_http_failure():
    dc = _make_collector()
    dc.initialize()
    dc._datasets["fail1"] = DatasetRecord(
        dataset_id="fail1", title="Fail", source="test",
        source_url="http://example.com/fail",
    )
    mock = MockHTTP()
    mock.add("example.com", b"error", status_code=500)
    dc.set_http_client(mock)

    result = dc.download("fail1")
    assert result is not None
    assert result.status == DatasetStatus.ERROR.value
    assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_validate_csv():
    dc = _make_collector()
    dc.initialize()

    # Write a CSV file
    csv_data = b"name,age,score\nAlice,30,95.5\nBob,25,87.0\nCharlie,35,91.2\n"
    import hashlib
    sha = hashlib.sha256(csv_data).hexdigest()

    filepath = Path(dc._datasets_dir) / "test_validate.csv"
    filepath.write_bytes(csv_data)

    dc._datasets["val1"] = DatasetRecord(
        dataset_id="val1", title="Validate CSV",
        source="test", source_url="http://test.com",
        local_path=str(filepath), sha256=sha,
    )

    schema = dc.validate("val1")
    assert schema is not None
    assert schema.columns == ["name", "age", "score"]
    assert schema.row_count == 3
    assert schema.file_format == "csv"
    assert schema.column_types.get("age") == "integer"
    assert schema.column_types.get("score") == "float"
    assert schema.column_types.get("name") == "string"


def test_validate_json():
    dc = _make_collector()
    dc.initialize()

    json_data = json.dumps([
        {"id": 1, "name": "Hospital A", "beds": 200},
        {"id": 2, "name": "Hospital B", "beds": 150},
    ]).encode()
    import hashlib
    sha = hashlib.sha256(json_data).hexdigest()

    filepath = Path(dc._datasets_dir) / "test_validate.json"
    filepath.write_bytes(json_data)

    dc._datasets["val2"] = DatasetRecord(
        dataset_id="val2", title="Validate JSON",
        source="test", source_url="http://test.com",
        local_path=str(filepath), sha256=sha,
    )

    schema = dc.validate("val2")
    assert schema is not None
    assert schema.row_count == 2
    assert "id" in schema.columns
    assert schema.file_format == "json"


def test_validate_integrity_fail():
    dc = _make_collector()
    dc.initialize()

    filepath = Path(dc._datasets_dir) / "tampered.csv"
    filepath.write_bytes(b"name,age\nAlice,30\n")

    dc._datasets["tamper1"] = DatasetRecord(
        dataset_id="tamper1", title="Tampered",
        source="test", source_url="http://test.com",
        local_path=str(filepath), sha256="wrong_hash_value",
    )

    schema = dc.validate("tamper1")
    assert schema is None
    assert dc._datasets["tamper1"].status == DatasetStatus.ERROR.value


def test_validate_missing_file():
    dc = _make_collector()
    dc.initialize()
    dc._datasets["missing1"] = DatasetRecord(
        dataset_id="missing1", title="Missing",
        source="test", source_url="http://test.com",
        local_path="/nonexistent/path/file.csv",
    )
    schema = dc.validate("missing1")
    assert schema is None


def test_validate_not_found():
    dc = _make_collector()
    dc.initialize()
    assert dc.validate("nope") is None


def test_validate_no_local_path():
    dc = _make_collector()
    dc.initialize()
    dc._datasets["nolp"] = DatasetRecord(
        dataset_id="nolp", title="No Path",
        source="test", source_url="http://test.com",
    )
    assert dc.validate("nolp") is None


# ---------------------------------------------------------------------------
# Index persistence
# ---------------------------------------------------------------------------

def test_save_and_load_index():
    tmpdir = tempfile.mkdtemp()
    dc = _make_collector(tmpdir)
    dc.initialize()

    dc._datasets["idx1"] = DatasetRecord(
        dataset_id="idx1", title="Index Test",
        source="data.gov", source_url="http://test.com",
    )
    dc._save_index()

    # Create a new collector pointing to same dir
    dc2 = _make_collector(tmpdir)
    dc2.initialize()
    assert dc2.dataset_count() == 1
    assert dc2.get_dataset("idx1").title == "Index Test"


def test_load_corrupt_index():
    tmpdir = tempfile.mkdtemp()
    index_path = Path(tmpdir) / "index.json"
    index_path.write_text("not valid json", encoding="utf-8")

    dc = _make_collector(tmpdir)
    dc.initialize()
    assert dc.dataset_count() == 0  # gracefully handles corruption


# ---------------------------------------------------------------------------
# Staleness & refresh
# ---------------------------------------------------------------------------

def test_stale_datasets():
    dc = _make_collector()
    dc.initialize()

    old_time = (datetime.now(timezone.utc) - timedelta(hours=200)).isoformat()
    dc._datasets["stale1"] = DatasetRecord(
        dataset_id="stale1", title="Old Data",
        source="test", source_url="http://test.com",
        status=DatasetStatus.VALIDATED.value,
        downloaded_at=old_time,
        refresh_interval_hours=168,
    )

    recent_time = datetime.now(timezone.utc).isoformat()
    dc._datasets["fresh1"] = DatasetRecord(
        dataset_id="fresh1", title="Fresh Data",
        source="test", source_url="http://test.com",
        status=DatasetStatus.VALIDATED.value,
        downloaded_at=recent_time,
        refresh_interval_hours=168,
    )

    stale = dc.stale_datasets()
    assert len(stale) == 1
    assert stale[0].dataset_id == "stale1"


def test_stale_skips_errors():
    dc = _make_collector()
    dc.initialize()
    old_time = (datetime.now(timezone.utc) - timedelta(hours=200)).isoformat()
    dc._datasets["err1"] = DatasetRecord(
        dataset_id="err1", title="Errored",
        source="test", source_url="http://test.com",
        status=DatasetStatus.ERROR.value,
        downloaded_at=old_time,
    )
    assert len(dc.stale_datasets()) == 0


def test_refresh():
    dc = _make_collector()
    dc.initialize()
    dc._datasets["ref1"] = DatasetRecord(
        dataset_id="ref1", title="Refresh Me",
        source="test", source_url="http://example.com/data.csv",
        status=DatasetStatus.STALE.value,
    )
    mock = MockHTTP()
    csv_data = b"a,b\n1,2\n"
    mock.add("example.com", csv_data, headers={"Content-Type": "text/csv"})
    dc.set_http_client(mock)

    result = dc.refresh("ref1")
    assert result is not None
    assert result.status == DatasetStatus.VALIDATED.value


def test_refresh_not_found():
    dc = _make_collector()
    dc.initialize()
    assert dc.refresh("nonexistent") is None


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def test_list_datasets_filter_source():
    dc = _make_collector()
    dc.initialize()
    dc._datasets["a"] = DatasetRecord(dataset_id="a", title="A", source="cms", source_url="")
    dc._datasets["b"] = DatasetRecord(dataset_id="b", title="B", source="hhs", source_url="")
    dc._datasets["c"] = DatasetRecord(dataset_id="c", title="C", source="cms", source_url="")

    cms_only = dc.list_datasets(source="cms")
    assert len(cms_only) == 2


def test_list_datasets_filter_status():
    dc = _make_collector()
    dc.initialize()
    dc._datasets["d"] = DatasetRecord(
        dataset_id="d", title="D", source="test", source_url="",
        status=DatasetStatus.VALIDATED.value,
    )
    dc._datasets["e"] = DatasetRecord(
        dataset_id="e", title="E", source="test", source_url="",
        status=DatasetStatus.ERROR.value,
    )
    validated = dc.list_datasets(status=DatasetStatus.VALIDATED.value)
    assert len(validated) == 1


def test_datasets_by_source():
    dc = _make_collector()
    dc.initialize()
    dc._datasets["x1"] = DatasetRecord(dataset_id="x1", title="X1", source="cms", source_url="")
    dc._datasets["x2"] = DatasetRecord(dataset_id="x2", title="X2", source="cms", source_url="")
    dc._datasets["x3"] = DatasetRecord(dataset_id="x3", title="X3", source="pubmed", source_url="")

    by_source = dc.datasets_by_source()
    assert by_source["cms"] == 2
    assert by_source["pubmed"] == 1


def test_remove_dataset():
    dc = _make_collector()
    dc.initialize()
    dc._datasets["rm1"] = DatasetRecord(
        dataset_id="rm1", title="Remove", source="test", source_url="",
    )
    assert dc.remove_dataset("rm1")
    assert dc.dataset_count() == 0
    assert not dc.remove_dataset("rm1")  # already removed


def test_remove_dataset_with_file():
    dc = _make_collector()
    dc.initialize()
    filepath = Path(dc._datasets_dir) / "removeme.csv"
    filepath.write_bytes(b"data")

    dc._datasets["rm2"] = DatasetRecord(
        dataset_id="rm2", title="Remove File", source="test",
        source_url="", local_path=str(filepath),
    )
    dc.remove_dataset("rm2", delete_file=True)
    assert not filepath.exists()


# ---------------------------------------------------------------------------
# DatasetRecord serialization
# ---------------------------------------------------------------------------

def test_record_roundtrip():
    record = DatasetRecord(
        dataset_id="rt1", title="Roundtrip", source="cms",
        source_url="http://test.com",
        schema=DatasetSchema(columns=["a", "b"], row_count=10, file_format="csv"),
    )
    d = record.to_dict()
    restored = DatasetRecord.from_dict(d)
    assert restored.dataset_id == "rt1"
    assert restored.schema.columns == ["a", "b"]
    assert restored.schema.row_count == 10


# ---------------------------------------------------------------------------
# Type inference
# ---------------------------------------------------------------------------

def test_infer_type_integer():
    assert DataCollector._infer_type("42") == "integer"


def test_infer_type_float():
    assert DataCollector._infer_type("3.14") == "float"


def test_infer_type_boolean():
    assert DataCollector._infer_type("true") == "boolean"
    assert DataCollector._infer_type("False") == "boolean"


def test_infer_type_string():
    assert DataCollector._infer_type("hello") == "string"


def test_infer_type_empty():
    assert DataCollector._infer_type("") == "empty"


# ---------------------------------------------------------------------------
# File extension guessing
# ---------------------------------------------------------------------------

def test_guess_extension_csv():
    dc = _make_collector()
    resp = HTTPResponse(200, b"a,b\n1,2\n", {"Content-Type": "text/csv"})
    assert dc._guess_extension(resp) == ".csv"


def test_guess_extension_json():
    dc = _make_collector()
    resp = HTTPResponse(200, b'{"key": "val"}', {"Content-Type": "application/json"})
    assert dc._guess_extension(resp) == ".json"


def test_guess_extension_sniff_json():
    dc = _make_collector()
    resp = HTTPResponse(200, b'[{"a":1}]', {})
    assert dc._guess_extension(resp) == ".json"


def test_guess_extension_sniff_csv():
    dc = _make_collector()
    resp = HTTPResponse(200, b"name,age\nAlice,30\n", {})
    assert dc._guess_extension(resp) == ".csv"


def test_guess_extension_unknown():
    dc = _make_collector()
    resp = HTTPResponse(200, b'\x00\x01\x02', {})
    assert dc._guess_extension(resp) == ".dat"


# ---------------------------------------------------------------------------
# HTTPResponse
# ---------------------------------------------------------------------------

def test_http_response_ok():
    r = HTTPResponse(200, b"ok")
    assert r.ok
    r2 = HTTPResponse(404, b"not found")
    assert not r2.ok


def test_http_response_json():
    r = HTTPResponse(200, json.dumps({"a": 1}).encode())
    assert r.json() == {"a": 1}


def test_http_response_text():
    r = HTTPResponse(200, b"hello world")
    assert r.text() == "hello world"


# ---------------------------------------------------------------------------
# Run with populated data
# ---------------------------------------------------------------------------

def test_run_with_datasets():
    dc = _make_collector()
    dc.initialize()

    old = (datetime.now(timezone.utc) - timedelta(hours=200)).isoformat()
    dc._datasets["run1"] = DatasetRecord(
        dataset_id="run1", title="R1", source="cms", source_url="",
        status=DatasetStatus.VALIDATED.value, downloaded_at=old,
    )
    dc._datasets["run2"] = DatasetRecord(
        dataset_id="run2", title="R2", source="hhs", source_url="",
        status=DatasetStatus.ERROR.value,
    )
    dc._datasets["run3"] = DatasetRecord(
        dataset_id="run3", title="R3", source="cms", source_url="",
        status=DatasetStatus.VALIDATED.value,
        downloaded_at=datetime.now(timezone.utc).isoformat(),
    )

    report = dc.run()
    assert "3 dataset" in report.summary
    assert len(report.alerts) >= 1  # stale + errored alerts
    assert report.data["total_datasets"] == 3
