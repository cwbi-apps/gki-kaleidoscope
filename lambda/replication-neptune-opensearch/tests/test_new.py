"""
Basic functional tests for lambda/replication-neptune-opensearch/main.py.

Run with (from this `tests/` directory or anywhere above it):

    pip install -r requirements-test.txt
    pytest lambda/replication-neptune-opensearch/tests -v

No AWS account, real Neptune cluster, DynamoDB table, or OpenSearch
domain is required or contacted - everything is mocked (see conftest.py).
"""

import json

import pytest
import requests

from conftest import DEFAULT_ENV, FakeLambdaContext, FakeResponse


# ---------------------------------------------------------------------------
# Configuration / import-time behavior
# ---------------------------------------------------------------------------

class TestConfiguration:

    def test_missing_required_env_var_raises(self, load_module):
        with pytest.raises(KeyError):
            load_module(remove=["NEPTUNE_ENDPOINT"])

        with pytest.raises(KeyError):
            load_module(remove=["OPENSEARCH_ENDPOINT"])

        with pytest.raises(KeyError):
            load_module(remove=["TARGET_INDEX"])

        with pytest.raises(KeyError):
            load_module(remove=["CHECKPOINT_TABLE"])

    def test_optional_env_vars_have_documented_defaults(self, load_module):
        module = load_module()

        assert module.NEPTUNE_PORT == "8182"
        assert module.BATCH_SIZE == 5000
        assert module.MAX_RUNTIME_SECONDS == 720
        assert module.IGNORED_PREDICATE_PREFIXES == [
            "http://www.opengis.net/ont/geosparql#"
        ]

    def test_optional_env_vars_can_be_overridden(self, load_module):
        module = load_module(
            overrides={
                "NEPTUNE_PORT": "9999",
                "BATCH_SIZE": "10",
                "MAX_RUNTIME_SECONDS": "5",
                "IGNORED_PREDICATE_PREFIXES": (
                    "http://example.org/geom#, http://example.org/other#"
                ),
            }
        )

        assert module.NEPTUNE_PORT == "9999"
        assert module.BATCH_SIZE == 10
        assert module.MAX_RUNTIME_SECONDS == 5
        assert module.IGNORED_PREDICATE_PREFIXES == [
            "http://example.org/geom#",
            "http://example.org/other#",
        ]

    def test_neptune_base_url_adds_scheme_and_port_when_bare_host(
        self, load_module
    ):
        module = load_module(
            overrides={"NEPTUNE_ENDPOINT": "myhost.example.com"}
        )

        assert module._neptune_base_url() == "https://myhost.example.com:8182"
        assert module._sparql_url() == "https://myhost.example.com:8182/sparql"
        assert (
            module._stream_url()
            == "https://myhost.example.com:8182/sparql/stream"
        )

    def test_neptune_base_url_respects_full_url(self, load_module):
        module = load_module(
            overrides={"NEPTUNE_ENDPOINT": "https://myhost.example.com:9999/"}
        )

        assert module._neptune_base_url() == "https://myhost.example.com:9999"

    def test_opensearch_base_url_adds_scheme_when_bare_host(self, load_module):
        module = load_module(
            overrides={"OPENSEARCH_ENDPOINT": "search-domain.example.com/"}
        )

        assert module._opensearch_base_url() == "https://search-domain.example.com"

    def test_opensearch_base_url_respects_full_url(self, load_module):
        module = load_module(
            overrides={"OPENSEARCH_ENDPOINT": "http://localhost:9200"}
        )

        assert module._opensearch_base_url() == "http://localhost:9200"


# ---------------------------------------------------------------------------
# Predicate helpers
# ---------------------------------------------------------------------------

class TestPredicateHelpers:

    def test_ignored_predicate_matches_configured_prefix(self, neptune):
        assert neptune._ignored_predicate(
            "http://www.opengis.net/ont/geosparql#asWKT"
        )
        assert not neptune._ignored_predicate(
            "http://www.w3.org/2000/01/rdf-schema#label"
        )

    def test_predicate_local_name_hash_form(self, neptune):
        assert (
            neptune._predicate_local_name(
                "http://example.org/schema#GeoObject-code"
            )
            == "GeoObject-code"
        )

    def test_predicate_local_name_slash_form(self, neptune):
        assert (
            neptune._predicate_local_name("http://example.org/schema/code")
            == "code"
        )

    def test_predicate_local_name_trailing_slash_is_stripped(self, neptune):
        assert (
            neptune._predicate_local_name("http://example.org/schema/code/")
            == "code"
        )


# ---------------------------------------------------------------------------
# Stream statement parsing + subject filtering
# ---------------------------------------------------------------------------

class TestStreamParsing:

    def test_parse_stream_statement_valid(self, neptune):
        record = {
            "data": {
                "stmt": '<http://example.org/s1> <http://example.org/p1> "v" .'
            }
        }

        assert neptune._parse_stream_statement(record) == (
            "http://example.org/s1",
            "http://example.org/p1",
        )

    def test_parse_stream_statement_missing_data(self, neptune):
        assert neptune._parse_stream_statement({}) is None

    def test_parse_stream_statement_malformed(self, neptune):
        record = {"data": {"stmt": "not a valid n-triple statement"}}
        assert neptune._parse_stream_statement(record) is None

    def test_changed_subjects_excludes_geometry_only_changes(self, neptune):
        records = [
            {
                "data": {
                    "stmt": (
                        "<http://example.org/geomOnly> "
                        "<http://www.opengis.net/ont/geosparql#asWKT> "
                        '"POINT(0 0)" .'
                    )
                }
            }
        ]

        assert neptune._changed_subjects(records) == set()

    def test_changed_subjects_includes_non_geometry_changes(self, neptune):
        records = [
            {
                "data": {
                    "stmt": (
                        "<http://example.org/labelChanged> "
                        "<http://www.w3.org/2000/01/rdf-schema#label> "
                        '"New Label" .'
                    )
                }
            }
        ]

        assert neptune._changed_subjects(records) == {
            "http://example.org/labelChanged"
        }

    def test_changed_subjects_requires_refresh_if_any_predicate_qualifies(
        self, neptune
    ):
        # Same subject touched by both a geometry predicate and a
        # non-geometry predicate in the same page -> still requires refresh.
        records = [
            {
                "data": {
                    "stmt": (
                        "<http://example.org/mixed> "
                        "<http://www.opengis.net/ont/geosparql#asWKT> "
                        '"POINT(0 0)" .'
                    )
                }
            },
            {
                "data": {
                    "stmt": (
                        "<http://example.org/mixed> "
                        "<http://www.w3.org/2000/01/rdf-schema#label> "
                        '"Mixed" .'
                    )
                }
            },
        ]

        assert neptune._changed_subjects(records) == {"http://example.org/mixed"}

    def test_changed_subjects_skips_unparseable_records(self, neptune):
        records = [
            {"data": {"stmt": "garbage"}},
            {
                "data": {
                    "stmt": (
                        "<http://example.org/ok> "
                        "<http://www.w3.org/2000/01/rdf-schema#label> "
                        '"OK" .'
                    )
                }
            },
        ]

        assert neptune._changed_subjects(records) == {"http://example.org/ok"}


# ---------------------------------------------------------------------------
# SPARQL query construction
# ---------------------------------------------------------------------------

class TestSparqlHelpers:

    def test_sparql_iri_wraps_value(self, neptune):
        assert (
            neptune._sparql_iri("http://example.org/s1")
            == "<http://example.org/s1>"
        )

    @pytest.mark.parametrize(
        "bad_value",
        [
            "http://example.org/<injected>",
            "http://example.org/>injected",
            "http://example.org/\nsecond-line",
        ],
    )
    def test_sparql_iri_rejects_unsafe_values(self, neptune, bad_value):
        with pytest.raises(ValueError):
            neptune._sparql_iri(bad_value)

    def test_geometry_filter_sparql_default_prefix(self, neptune):
        filter_clause = neptune._geometry_filter_sparql()

        assert "FILTER(" in filter_clause
        assert "STRSTARTS(STR(?predicate)" in filter_clause
        assert "http://www.opengis.net/ont/geosparql#" in filter_clause

    def test_geometry_filter_sparql_empty_when_no_prefixes(self, neptune):
        neptune.IGNORED_PREDICATE_PREFIXES = []
        assert neptune._geometry_filter_sparql() == ""

    def test_geometry_filter_sparql_escapes_quotes(self, load_module):
        module = load_module(
            overrides={"IGNORED_PREDICATE_PREFIXES": 'http://example.org/"weird'}
        )

        filter_clause = module._geometry_filter_sparql()
        assert '\\"weird' in filter_clause

    def test_query_subjects_short_circuits_with_no_subjects(
        self, neptune, http_mock
    ):
        result = neptune._query_subjects(set())

        assert result == {"results": {"bindings": []}}
        assert http_mock.calls["post"] == []

    def test_query_subjects_sends_one_batched_request(self, neptune, http_mock):
        http_mock.post_responses["/sparql"] = [
            FakeResponse(
                json_data={
                    "results": {
                        "bindings": [
                            {
                                "uri": {"value": "http://example.org/s1"},
                                "predicate": {
                                    "value": "http://www.w3.org/2000/01/rdf-schema#label"
                                },
                                "object": {"value": "Bridge 12"},
                            }
                        ]
                    }
                }
            )
        ]

        subjects = {"http://example.org/s1", "http://example.org/s2"}
        result = neptune._query_subjects(subjects)

        assert len(http_mock.calls["post"]) == 1
        url, kwargs = http_mock.calls["post"][0]
        assert url.endswith("/sparql")

        query = kwargs["data"]["query"]
        assert "<http://example.org/s1>" in query
        assert "<http://example.org/s2>" in query
        assert "GRAPH ?graph" in query
        assert "FILTER(" in query  # geometry predicates excluded server-side

        assert result["results"]["bindings"][0]["object"]["value"] == "Bridge 12"

    def test_query_subjects_raises_on_http_error(self, neptune, http_mock):
        http_mock.post_responses["/sparql"] = [
            FakeResponse(status_code=500, text="internal error")
        ]

        with pytest.raises(requests.HTTPError):
            neptune._query_subjects({"http://example.org/s1"})


# ---------------------------------------------------------------------------
# Document construction
# ---------------------------------------------------------------------------

class TestBuildDocuments:

    def _bindings(self, *triples):
        return {
            "results": {
                "bindings": [
                    {
                        "uri": {"value": s},
                        "predicate": {"value": p},
                        "object": {"value": o},
                    }
                    for s, p, o in triples
                ]
            }
        }

    def test_builds_full_document(self, neptune):
        payload = self._bindings(
            (
                "http://example.org/s1",
                "http://www.w3.org/2000/01/rdf-schema#label",
                "Bridge 12",
            ),
            (
                "http://example.org/s1",
                "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
                "http://example.org/schema#Bridge",
            ),
            (
                "http://example.org/s1",
                "http://example.org/schema#GeoObject-code",
                "BR-12",
            ),
        )

        documents = neptune._build_documents({"http://example.org/s1"}, payload)

        assert documents["http://example.org/s1"] == {
            "uri": "http://example.org/s1",
            "label": "Bridge 12",
            "code": "BR-12",
            "type": "http://example.org/schema#Bridge",
        }

    def test_ignores_geometry_predicates(self, neptune):
        payload = self._bindings(
            (
                "http://example.org/s1",
                "http://www.w3.org/2000/01/rdf-schema#label",
                "Bridge 12",
            ),
            (
                "http://example.org/s1",
                "http://www.opengis.net/ont/geosparql#asWKT",
                "POINT(0 0)",
            ),
        )

        documents = neptune._build_documents({"http://example.org/s1"}, payload)

        assert documents["http://example.org/s1"]["label"] == "Bridge 12"
        # Geometry must never leak into the OpenSearch document.
        assert "asWKT" not in json.dumps(documents)
        assert "POINT" not in json.dumps(documents)

    def test_subject_missing_from_results_is_marked_for_delete(self, neptune):
        payload = self._bindings()  # subject no longer exists in Neptune

        documents = neptune._build_documents({"http://example.org/gone"}, payload)

        assert documents["http://example.org/gone"] is None

    def test_subject_with_no_meaningful_fields_is_marked_for_delete(self, neptune):
        # A subject that comes back with only an ignorable/unknown predicate
        # (no label/type/code) should be treated as deleted, not indexed
        # with an empty document.
        payload = self._bindings(
            (
                "http://example.org/s1",
                "http://example.org/schema#someUnmappedPredicate",
                "irrelevant",
            ),
        )

        documents = neptune._build_documents({"http://example.org/s1"}, payload)

        assert documents["http://example.org/s1"] is None


# ---------------------------------------------------------------------------
# OpenSearch bulk writes
# ---------------------------------------------------------------------------

class TestBulkWrite:

    def test_empty_documents_short_circuits(self, neptune, http_mock):
        neptune._bulk_write({})
        assert http_mock.calls["post"] == []

    def test_sends_index_and_delete_lines(self, neptune, http_mock):
        http_mock.post_responses["/_bulk"] = [
            FakeResponse(json_data={"errors": False, "items": []})
        ]

        documents = {
            "http://example.org/keep": {
                "uri": "http://example.org/keep",
                "label": "Kept",
                "code": "K-1",
                "type": "http://example.org/schema#Thing",
            },
            "http://example.org/gone": None,
        }

        neptune._bulk_write(documents)

        assert len(http_mock.calls["post"]) == 1
        url, kwargs = http_mock.calls["post"][0]
        assert url.endswith("/_bulk")
        assert kwargs["headers"]["Content-Type"] == "application/x-ndjson"

        lines = [json.loads(line) for line in kwargs["data"].strip().split("\n")]
        assert {"index": {"_index": neptune.TARGET_INDEX, "_id": "http://example.org/keep"}} in lines
        assert {"delete": {"_index": neptune.TARGET_INDEX, "_id": "http://example.org/gone"}} in lines
        assert {
            "uri": "http://example.org/keep",
            "label": "Kept",
            "code": "K-1",
            "type": "http://example.org/schema#Thing",
        } in lines

    def test_raises_on_http_error(self, neptune, http_mock):
        http_mock.post_responses["/_bulk"] = [
            FakeResponse(status_code=503, text="unavailable")
        ]

        with pytest.raises(requests.HTTPError):
            neptune._bulk_write(
                {"http://example.org/s1": {"uri": "http://example.org/s1"}}
            )

    def test_ignores_404_on_delete(self, neptune, http_mock):
        http_mock.post_responses["/_bulk"] = [
            FakeResponse(
                json_data={
                    "errors": True,
                    "items": [
                        {"delete": {"status": 404, "error": {"type": "not_found"}}}
                    ],
                }
            )
        ]

        # Should not raise - deleting something already absent is fine.
        neptune._bulk_write({"http://example.org/gone": None})

    def test_raises_runtime_error_on_real_failures(self, neptune, http_mock):
        http_mock.post_responses["/_bulk"] = [
            FakeResponse(
                json_data={
                    "errors": True,
                    "items": [
                        {
                            "index": {
                                "status": 400,
                                "error": {"type": "mapper_parsing_exception"},
                            }
                        }
                    ],
                }
            )
        ]

        with pytest.raises(RuntimeError, match="OpenSearch bulk replication"):
            neptune._bulk_write(
                {"http://example.org/s1": {"uri": "http://example.org/s1"}}
            )


# ---------------------------------------------------------------------------
# Checkpoint persistence (real DynamoDB API shape, via moto)
# ---------------------------------------------------------------------------

class TestCheckpoint:

    def test_read_checkpoint_returns_none_when_absent(self, neptune):
        assert neptune._read_checkpoint() is None

    def test_write_then_read_round_trips(self, neptune):
        neptune._write_checkpoint(commit_num=42, op_num=7)

        checkpoint = neptune._read_checkpoint()
        assert int(checkpoint["commitNum"]) == 42
        assert int(checkpoint["opNum"]) == 7

    def test_write_checkpoint_overwrites_previous_value(self, neptune):
        neptune._write_checkpoint(commit_num=1, op_num=1)
        neptune._write_checkpoint(commit_num=2, op_num=99)

        checkpoint = neptune._read_checkpoint()
        assert int(checkpoint["commitNum"]) == 2
        assert int(checkpoint["opNum"]) == 99


# ---------------------------------------------------------------------------
# Runtime guard
# ---------------------------------------------------------------------------

class TestRuntimeGuard:

    def test_not_exceeded_with_plenty_of_time(self, neptune):
        started_at = neptune.time.monotonic()
        context = FakeLambdaContext(remaining_ms=10 * 60 * 1000)

        assert neptune._runtime_exceeded(started_at, context) is False

    def test_exceeded_once_max_runtime_elapses(self, neptune):
        neptune.MAX_RUNTIME_SECONDS = 1
        started_at = neptune.time.monotonic() - 2  # 2s "ago"

        assert neptune._runtime_exceeded(started_at, context=None) is True

    def test_exceeded_when_lambda_context_almost_out_of_time(self, neptune):
        started_at = neptune.time.monotonic()
        context = FakeLambdaContext(remaining_ms=30_000)  # under the 60s guard

        assert neptune._runtime_exceeded(started_at, context) is True

    def test_no_context_and_time_remaining_is_fine(self, neptune):
        started_at = neptune.time.monotonic()
        assert neptune._runtime_exceeded(started_at, context=None) is False


# ---------------------------------------------------------------------------
# lambda_handler end-to-end (the "deployed environment" simulation)
# ---------------------------------------------------------------------------

def _label_binding(uri, label):
    return {
        "uri": {"value": uri},
        "predicate": {"value": "http://www.w3.org/2000/01/rdf-schema#label"},
        "object": {"value": label},
    }


class TestLambdaHandlerEndToEnd:

    def test_raises_when_no_checkpoint_initialized(self, neptune, http_mock):
        with pytest.raises(RuntimeError, match="No Neptune stream checkpoint"):
            neptune.lambda_handler({}, FakeLambdaContext())

    def test_happy_path_single_page(self, neptune, http_mock):
        neptune._write_checkpoint(commit_num=1, op_num=1)

        stream_page = {
            "records": [
                {
                    "data": {
                        "stmt": (
                            "<http://example.org/bridge1> "
                            "<http://www.w3.org/2000/01/rdf-schema#label> "
                            '"Bridge 12" .'
                        )
                    }
                },
                {
                    # Geometry-only change: must never reach Neptune/OpenSearch.
                    "data": {
                        "stmt": (
                            "<http://example.org/geomOnly> "
                            "<http://www.opengis.net/ont/geosparql#asWKT> "
                            '"POINT(0 0)" .'
                        )
                    }
                },
            ],
            "lastEventId": {"commitNum": 5, "opNum": 10},
        }
        caught_up_page = {"records": [], "lastEventId": {"commitNum": 5, "opNum": 10}}

        http_mock.get_queue = [
            FakeResponse(json_data=stream_page),
            FakeResponse(json_data=caught_up_page),
        ]
        http_mock.post_responses["/sparql"] = [
            FakeResponse(
                json_data={
                    "results": {
                        "bindings": [
                            _label_binding("http://example.org/bridge1", "Bridge 12")
                        ]
                    }
                }
            )
        ]
        http_mock.post_responses["/_bulk"] = [
            FakeResponse(json_data={"errors": False, "items": []})
        ]

        result = neptune.lambda_handler({}, FakeLambdaContext())

        assert result == {
            "pagesProcessed": 1,
            "processedRecords": 2,
            "processedSubjects": 1,
            "elapsedSeconds": result["elapsedSeconds"],
            "commitNum": 5,
            "opNum": 10,
        }

        # Only the non-geometry subject was ever queried.
        sparql_query = http_mock.calls["post"][0][1]["data"]["query"]
        assert "<http://example.org/bridge1>" in sparql_query
        assert "<http://example.org/geomOnly>" not in sparql_query

        checkpoint = neptune._read_checkpoint()
        assert int(checkpoint["commitNum"]) == 5
        assert int(checkpoint["opNum"]) == 10

    def test_page_with_only_geometry_changes_skips_neptune_and_opensearch(
        self, neptune, http_mock
    ):
        neptune._write_checkpoint(commit_num=1, op_num=1)

        stream_page = {
            "records": [
                {
                    "data": {
                        "stmt": (
                            "<http://example.org/geomOnly> "
                            "<http://www.opengis.net/ont/geosparql#asWKT> "
                            '"POINT(0 0)" .'
                        )
                    }
                }
            ],
            "lastEventId": {"commitNum": 2, "opNum": 1},
        }
        caught_up_page = {"records": [], "lastEventId": {"commitNum": 2, "opNum": 1}}

        http_mock.get_queue = [
            FakeResponse(json_data=stream_page),
            FakeResponse(json_data=caught_up_page),
        ]

        result = neptune.lambda_handler({}, FakeLambdaContext())

        assert result["processedSubjects"] == 0
        assert http_mock.calls["post"] == []  # neither SPARQL nor OpenSearch hit

        checkpoint = neptune._read_checkpoint()
        assert int(checkpoint["commitNum"]) == 2

    def test_deletes_subject_no_longer_present_in_neptune(self, neptune, http_mock):
        neptune._write_checkpoint(commit_num=1, op_num=1)

        stream_page = {
            "records": [
                {
                    "data": {
                        "stmt": (
                            "<http://example.org/deletedThing> "
                            "<http://www.w3.org/2000/01/rdf-schema#label> "
                            '"whatever" .'
                        )
                    }
                }
            ],
            "lastEventId": {"commitNum": 2, "opNum": 1},
        }
        caught_up_page = {"records": [], "lastEventId": {"commitNum": 2, "opNum": 1}}

        http_mock.get_queue = [
            FakeResponse(json_data=stream_page),
            FakeResponse(json_data=caught_up_page),
        ]
        # Requerying Neptune finds nothing - the subject was deleted.
        http_mock.post_responses["/sparql"] = [
            FakeResponse(json_data={"results": {"bindings": []}})
        ]
        http_mock.post_responses["/_bulk"] = [
            FakeResponse(json_data={"errors": False, "items": []})
        ]

        neptune.lambda_handler({}, FakeLambdaContext())

        bulk_body = http_mock.calls["post"][1][1]["data"]
        lines = [json.loads(line) for line in bulk_body.strip().split("\n")]
        assert {
            "delete": {
                "_index": neptune.TARGET_INDEX,
                "_id": "http://example.org/deletedThing",
            }
        } in lines

    def test_multi_page_stops_when_caught_up(self, neptune, http_mock):
        neptune._write_checkpoint(commit_num=1, op_num=1)

        page_one = {
            "records": [
                {
                    "data": {
                        "stmt": (
                            "<http://example.org/s1> "
                            "<http://www.w3.org/2000/01/rdf-schema#label> "
                            '"S1" .'
                        )
                    }
                }
            ],
            "lastEventId": {"commitNum": 2, "opNum": 1},
        }
        page_two_empty = {"records": [], "lastEventId": {"commitNum": 2, "opNum": 1}}

        http_mock.get_queue = [
            FakeResponse(json_data=page_one),
            FakeResponse(json_data=page_two_empty),
        ]
        http_mock.post_responses["/sparql"] = [
            FakeResponse(
                json_data={
                    "results": {
                        "bindings": [_label_binding("http://example.org/s1", "S1")]
                    }
                }
            )
        ]
        http_mock.post_responses["/_bulk"] = [
            FakeResponse(json_data={"errors": False, "items": []})
        ]

        result = neptune.lambda_handler({}, FakeLambdaContext())

        assert result["pagesProcessed"] == 1
        assert len(http_mock.calls["get"]) == 2  # fetched again, found nothing new

    def test_stops_immediately_when_runtime_budget_already_spent(
        self, neptune, http_mock
    ):
        neptune._write_checkpoint(commit_num=1, op_num=1)
        neptune.MAX_RUNTIME_SECONDS = 0  # simulate the cutoff already reached

        result = neptune.lambda_handler({}, FakeLambdaContext())

        assert result["pagesProcessed"] == 0
        assert http_mock.calls["get"] == []  # never even fetched a page

        # Checkpoint must be untouched.
        checkpoint = neptune._read_checkpoint()
        assert int(checkpoint["commitNum"]) == 1
        assert int(checkpoint["opNum"]) == 1

    def test_expired_stream_checkpoint_raises_clear_error(self, neptune, http_mock):
        neptune._write_checkpoint(commit_num=1, op_num=1)

        http_mock.get_queue = [
            FakeResponse(
                status_code=400,
                json_data={"code": "ExpiredStreamException"},
            )
        ]

        with pytest.raises(RuntimeError, match="checkpoint has expired"):
            neptune.lambda_handler({}, FakeLambdaContext())

    def test_stalled_checkpoint_raises_to_avoid_infinite_loop(
        self, neptune, http_mock
    ):
        neptune._write_checkpoint(commit_num=1, op_num=1)

        stream_page = {
            "records": [
                {
                    "data": {
                        "stmt": (
                            "<http://example.org/s1> "
                            "<http://www.w3.org/2000/01/rdf-schema#label> "
                            '"S1" .'
                        )
                    }
                }
            ],
            # Does not advance from the current checkpoint.
            "lastEventId": {"commitNum": 1, "opNum": 1},
        }

        http_mock.get_queue = [FakeResponse(json_data=stream_page)]
        http_mock.post_responses["/sparql"] = [
            FakeResponse(json_data={"results": {"bindings": []}})
        ]
        http_mock.post_responses["/_bulk"] = [
            FakeResponse(json_data={"errors": False, "items": []})
        ]

        with pytest.raises(RuntimeError, match="did not advance"):
            neptune.lambda_handler({}, FakeLambdaContext())

    def test_missing_last_event_id_raises(self, neptune, http_mock):
        neptune._write_checkpoint(commit_num=1, op_num=1)

        stream_page = {
            "records": [
                {
                    "data": {
                        "stmt": (
                            "<http://example.org/s1> "
                            "<http://www.w3.org/2000/01/rdf-schema#label> "
                            '"S1" .'
                        )
                    }
                }
            ]
            # No lastEventId at all.
        }

        http_mock.get_queue = [FakeResponse(json_data=stream_page)]
        http_mock.post_responses["/sparql"] = [
            FakeResponse(json_data={"results": {"bindings": []}})
        ]
        http_mock.post_responses["/_bulk"] = [
            FakeResponse(json_data={"errors": False, "items": []})
        ]

        with pytest.raises(RuntimeError, match="did not provide lastEventId"):
            neptune.lambda_handler({}, FakeLambdaContext())

    def test_opensearch_failure_propagates_out_of_handler(self, neptune, http_mock):
        neptune._write_checkpoint(commit_num=1, op_num=1)

        stream_page = {
            "records": [
                {
                    "data": {
                        "stmt": (
                            "<http://example.org/s1> "
                            "<http://www.w3.org/2000/01/rdf-schema#label> "
                            '"S1" .'
                        )
                    }
                }
            ],
            "lastEventId": {"commitNum": 2, "opNum": 1},
        }

        http_mock.get_queue = [FakeResponse(json_data=stream_page)]
        http_mock.post_responses["/sparql"] = [
            FakeResponse(
                json_data={
                    "results": {
                        "bindings": [_label_binding("http://example.org/s1", "S1")]
                    }
                }
            )
        ]
        http_mock.post_responses["/_bulk"] = [
            FakeResponse(
                json_data={
                    "errors": True,
                    "items": [
                        {"index": {"status": 400, "error": {"type": "boom"}}}
                    ],
                }
            )
        ]

        with pytest.raises(RuntimeError, match="OpenSearch bulk replication"):
            neptune.lambda_handler({}, FakeLambdaContext())

        # And because the OpenSearch write failed, the checkpoint must NOT
        # have advanced - the next invocation should retry this page.
        checkpoint = neptune._read_checkpoint()
        assert int(checkpoint["commitNum"]) == 1
