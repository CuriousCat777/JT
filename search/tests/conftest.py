"""Conftest for search tests — registers --live option."""
import pytest


def pytest_addoption(parser):
    """Add --live flag to run live integration tests against running engines."""
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run live integration tests against running Typesense/Meilisearch",
    )


def pytest_collection_modifyitems(config, items):
    """Skip live tests unless --live is specified."""
    if not config.getoption("--live", default=False):
        skip_live = pytest.mark.skip(reason="Pass --live to run live integration tests")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)
