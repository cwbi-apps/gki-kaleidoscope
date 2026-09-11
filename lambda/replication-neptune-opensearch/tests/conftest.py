"""
Shared fixtures for testing lambda/replication-neptune-opensearch/main.py.

These tests never talk to a real Neptune cluster, DynamoDB table, or
OpenSearch domain - they simulate a deployed environment by faking each
external dependency:

  - DynamoDB (the replication checkpoint table) is faked in-memory with
    `moto`.
  - Neptune (the SPARQL and Streams HTTP endpoints) and OpenSearch (the
    `_bulk` HTTP endpoint) are faked with a small in-test HTTP router
    (see `HttpMock` below) that stands in for `requests.get`/`requests.post`.

`main.py` reads its configuration from environment variables and creates
its boto3 DynamoDB resource/table at *import time*, so tests must control
the environment *before* importing it. `_import_fresh` below reloads the
module from disk under whatever environment the test needs, so nothing
leaks between tests (each test gets its own module object).
"""

import importlib.util
import json
from pathlib import Path

import boto3
import pytest
from moto import mock_aws


MODULE_PATH = Path(__file__).resolve().parent.parent / "main.py"

# A complete, valid "deployed" environment. Individual tests override or
# remove keys from this baseline via the `load_module` fixture.
DEFAULT_ENV = {
    "AWS_DEFAULT_REGION": "us-gov-west-1",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SECURITY_TOKEN": "testing",
    "AWS_SESSION_TOKEN": "testing",
    "NEPTUNE_ENDPOINT": "neptune-test.cluster-abc123.us-gov-west-1.neptune.amazonaws.com",
    "OPENSEARCH_ENDPOINT": "search-test-domain.us-gov-west-1.es.amazonaws.com",
    "TARGET_INDEX": "geo_objects",
    "CHECKPOINT_TABLE": "replication-checkpoints",
}


def _import_fresh():
    """Exec main.py from disk as a brand new, uncached module object."""

    spec = importlib.util.spec_from_file_location(
        "replication_neptune_opensearch_main", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def load_module(monkeypatch):
    """
    Factory fixture: load_module(overrides={...}, remove=[...]) sets the
    default environment (with any overrides applied and any `remove` keys
    deleted), then imports main.py fresh under it.
    """

    def _load(overrides=None, remove=None):
        env = dict(DEFAULT_ENV)
        if overrides:
            env.update(overrides)
        if remove:
            for key in remove:
                env.pop(key, None)
                monkeypatch.delenv(key, raising=False)

        for key, value in env.items():
            monkeypatch.setenv(key, value)

        return _import_fresh()

    return _load


@pytest.fixture
def checkpoint_table():
    """
    A moto-mocked DynamoDB table matching CHECKPOINT_TABLE, standing in
    for the real deployed checkpoint table. Active for the life of the
    test.
    """

    with mock_aws():
        ddb = boto3.resource(
            "dynamodb", region_name=DEFAULT_ENV["AWS_DEFAULT_REGION"]
        )
        table = ddb.create_table(
            TableName=DEFAULT_ENV["CHECKPOINT_TABLE"],
            KeySchema=[{"AttributeName": "streamId", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "streamId", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
        yield table


@pytest.fixture
def neptune(checkpoint_table, load_module):
    """
    The module under test, imported fresh with the default "deployed"
    environment and a working (empty) mocked checkpoint table already in
    place.
    """

    return load_module()


class FakeResponse:
    """Stands in for a `requests.Response` from Neptune or OpenSearch."""

    def __init__(self, status_code=200, json_data=None, text=None):
        self.status_code = status_code
        self._json = {} if json_data is None else json_data
        self.text = text if text is not None else json.dumps(self._json)
        self.ok = 200 <= status_code < 400

    def json(self):
        return self._json

    def raise_for_status(self):
        if not self.ok:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}: {self.text}")


class HttpMock:
    """
    A tiny router standing in for `requests.get`/`requests.post` so tests
    can script Neptune/OpenSearch responses and assert on what was sent,
    without any real network access.

    - `get_queue`: FIFO list of FakeResponse (or callables) returned for
      successive calls to requests.get (used by the Neptune Streams poll).
    - `post_responses`: maps a URL suffix (e.g. "/sparql" or "/_bulk") to
      its own FIFO queue of FakeResponse (or callables).
    """

    def __init__(self):
        self.get_queue = []
        self.post_responses = {}
        self.calls = {"get": [], "post": []}

    def get(self, url, **kwargs):
        self.calls["get"].append((url, kwargs))
        if not self.get_queue:
            raise AssertionError(f"Unexpected GET to {url} (queue empty)")
        item = self.get_queue.pop(0)
        return item(url, kwargs) if callable(item) else item

    def post(self, url, **kwargs):
        self.calls["post"].append((url, kwargs))
        for suffix, queue in self.post_responses.items():
            if url.endswith(suffix):
                if not queue:
                    raise AssertionError(
                        f"Unexpected POST to {url} (queue for {suffix!r} empty)"
                    )
                item = queue.pop(0)
                return item(url, kwargs) if callable(item) else item
        raise AssertionError(f"Unexpected POST to {url} (no route configured)")


@pytest.fixture
def http_mock(neptune, monkeypatch):
    """Patch the module's `requests.get`/`requests.post` with an HttpMock."""

    mock = HttpMock()
    monkeypatch.setattr(neptune.requests, "get", mock.get)
    monkeypatch.setattr(neptune.requests, "post", mock.post)
    return mock


class FakeLambdaContext:
    """Stands in for the Lambda `context` object passed to the handler."""

    def __init__(self, remaining_ms=15 * 60 * 1000):
        self._remaining_ms = remaining_ms

    def get_remaining_time_in_millis(self):
        return self._remaining_ms
