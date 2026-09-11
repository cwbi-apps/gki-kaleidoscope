"""
Neptune SPARQL Streams -> OpenSearch replication poller.

Optimized behavior:

  1. Read the last committed Neptune stream checkpoint from DynamoDB.
  2. Fetch up to BATCH_SIZE stream records (default 5000).
  3. Parse changed subjects + predicates.
  4. Ignore geometry-only changes immediately.
  5. Re-query ALL affected subjects in ONE SPARQL request.
     - Search across all named graphs.
     - Exclude geometry predicates in SPARQL so geometry is never fetched.
  6. Reconstruct existing geo_objects documents:
       uri
       label
       code
       type
  7. Apply all updates/deletes in ONE OpenSearch _bulk request.
  8. Persist the checkpoint after EACH successfully processed stream page.
  9. Continue processing additional pages until:
       - Neptune has no more records, OR
       - the Lambda has been running for MAX_RUNTIME_SECONDS
         (default 720 / 12 min).
 10. Exit gracefully so the next scheduled invocation resumes from the
     last persisted checkpoint.

The replicator intentionally does NOT know:
  - graph names
  - LPG namespace
  - lpgs prefix
  - concrete GeoObject types

It infers:
  - label from rdfs:label
  - type from rdf:type
  - code from a predicate whose local name is "GeoObject-code"

Required environment variables:
  NEPTUNE_ENDPOINT
  OPENSEARCH_ENDPOINT
  TARGET_INDEX
  CHECKPOINT_TABLE

Optional environment variables:
  NEPTUNE_PORT=8182
  BATCH_SIZE=5000
  MAX_RUNTIME_SECONDS=720
  IGNORED_PREDICATE_PREFIXES=http://www.opengis.net/ont/geosparql#
"""

import json
import logging
import os
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

import boto3
import requests
from requests_aws4auth import AWS4Auth


LOG = logging.getLogger()
LOG.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REGION = os.environ.get(
    "AWS_REGION",
    "us-gov-west-1",
)

NEPTUNE_ENDPOINT = os.environ["NEPTUNE_ENDPOINT"]

NEPTUNE_PORT = os.environ.get(
    "NEPTUNE_PORT",
    "8182",
)

OPENSEARCH_ENDPOINT = os.environ[
    "OPENSEARCH_ENDPOINT"
]

TARGET_INDEX = os.environ[
    "TARGET_INDEX"
]

CHECKPOINT_TABLE = os.environ[
    "CHECKPOINT_TABLE"
]

BATCH_SIZE = int(
    os.environ.get(
        "BATCH_SIZE",
        "5000",
    )
)

MAX_RUNTIME_SECONDS = int(
    os.environ.get(
        "MAX_RUNTIME_SECONDS",
        "720",
    )
)

STREAM_ID = "default"


IGNORED_PREDICATE_PREFIXES = [
    value.strip()
    for value in os.environ.get(
        "IGNORED_PREDICATE_PREFIXES",
        "http://www.opengis.net/ont/geosparql#",
    ).split(",")
    if value.strip()
]


RDF_TYPE = (
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
)

RDFS_LABEL = (
    "http://www.w3.org/2000/01/rdf-schema#label"
)


_ddb = boto3.resource("dynamodb")
_table = _ddb.Table(CHECKPOINT_TABLE)


STATEMENT_RE = re.compile(
    r"^<([^>]+)>\s+<([^>]+)>\s+"
)


# ---------------------------------------------------------------------------
# AWS authentication
# ---------------------------------------------------------------------------

def _auth(
    service: str,
) -> AWS4Auth:

    creds = (
        boto3.Session()
        .get_credentials()
        .get_frozen_credentials()
    )

    return AWS4Auth(
        creds.access_key,
        creds.secret_key,
        REGION,
        service,
        session_token=creds.token,
    )


# ---------------------------------------------------------------------------
# Endpoint helpers
# ---------------------------------------------------------------------------

def _neptune_base_url() -> str:

    endpoint = NEPTUNE_ENDPOINT.rstrip("/")

    if not endpoint.startswith("http"):
        endpoint = (
            f"https://{endpoint}:{NEPTUNE_PORT}"
        )

    return endpoint


def _sparql_url() -> str:

    return (
        f"{_neptune_base_url()}/sparql"
    )


def _stream_url() -> str:

    return (
        f"{_neptune_base_url()}/sparql/stream"
    )


def _opensearch_base_url() -> str:

    endpoint = (
        OPENSEARCH_ENDPOINT.rstrip("/")
    )

    if not endpoint.startswith("http"):
        endpoint = f"https://{endpoint}"

    return endpoint


# ---------------------------------------------------------------------------
# Checkpoint persistence
# ---------------------------------------------------------------------------

def _read_checkpoint(
) -> Optional[Dict[str, Any]]:

    response = _table.get_item(
        Key={
            "streamId": STREAM_ID,
        }
    )

    return response.get("Item")


def _write_checkpoint(
    commit_num: int,
    op_num: int,
) -> None:

    _table.put_item(
        Item={
            "streamId": STREAM_ID,
            "commitNum": commit_num,
            "opNum": op_num,
        }
    )

    LOG.info(
        "Checkpoint advanced to "
        "commitNum=%s opNum=%s",
        commit_num,
        op_num,
    )


# ---------------------------------------------------------------------------
# Neptune Streams
# ---------------------------------------------------------------------------

def _fetch_stream(
    commit_num: int,
    op_num: int,
) -> Dict[str, Any]:

    params = {
        "iteratorType":
            "AFTER_SEQUENCE_NUMBER",
        "commitNum": commit_num,
        "opNum": op_num,
        "limit": BATCH_SIZE,
    }

    response = requests.get(
        _stream_url(),
        params=params,
        auth=_auth("neptune-db"),
        timeout=30,
    )

    LOG.info(
        "Neptune stream returned HTTP %s",
        response.status_code,
    )

    if response.status_code == 404:

        return {
            "records": [],
            "lastEventId": {
                "commitNum": commit_num,
                "opNum": op_num,
            },
        }

    if response.status_code == 400:

        try:
            body = response.json()

        except ValueError:
            body = {}

        if (
            body.get("code")
            == "ExpiredStreamException"
        ):

            raise RuntimeError(
                "Neptune stream checkpoint has expired. "
                "The requested stream records are no longer available. "
                "Reinitialize replication state before resuming this poller."
            )

    if not response.ok:

        LOG.error(
            "Neptune stream request failed: "
            "HTTP %s %s",
            response.status_code,
            response.text[:2000],
        )

    response.raise_for_status()

    return response.json()


# ---------------------------------------------------------------------------
# Predicate helpers
# ---------------------------------------------------------------------------

def _ignored_predicate(
    predicate: str,
) -> bool:

    return any(
        predicate.startswith(prefix)
        for prefix
        in IGNORED_PREDICATE_PREFIXES
    )


def _predicate_local_name(
    predicate: str,
) -> str:

    value = predicate.rstrip("/")

    if "#" in value:
        return value.rsplit("#", 1)[1]

    return value.rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------
# Stream parsing
# ---------------------------------------------------------------------------

def _parse_stream_statement(
    record: Dict[str, Any],
) -> Optional[Tuple[str, str]]:

    statement = str(
        (record.get("data") or {})
        .get("stmt")
        or ""
    ).strip()

    if not statement:

        LOG.warning(
            "Stream record had no data.stmt: %s",
            json.dumps(record)[:1000],
        )

        return None

    match = STATEMENT_RE.match(
        statement
    )

    if not match:

        LOG.warning(
            "Unable to parse subject/predicate "
            "from stream statement: %s",
            statement[:500],
        )

        return None

    return (
        match.group(1),
        match.group(2),
    )


def _changed_subjects(
    records: List[Dict[str, Any]],
) -> Set[str]:

    changed: Dict[str, bool] = {}

    for record in records:

        parsed = _parse_stream_statement(
            record
        )

        if parsed is None:
            continue

        subject, predicate = parsed

        if subject not in changed:
            changed[subject] = False

        if not _ignored_predicate(
            predicate
        ):
            changed[subject] = True

    return {
        subject
        for subject, requires_refresh
        in changed.items()
        if requires_refresh
    }


# ---------------------------------------------------------------------------
# SPARQL helpers
# ---------------------------------------------------------------------------

def _sparql_iri(
    value: str,
) -> str:

    if (
        "<" in value
        or ">" in value
        or "\n" in value
        or "\r" in value
    ):

        raise ValueError(
            f"Invalid RDF subject IRI: {value!r}"
        )

    return f"<{value}>"


def _geometry_filter_sparql() -> str:

    if not IGNORED_PREDICATE_PREFIXES:
        return ""

    conditions = []

    for prefix in IGNORED_PREDICATE_PREFIXES:

        escaped = (
            prefix
            .replace("\\", "\\\\")
            .replace('"', '\\"')
        )

        conditions.append(
            "!"
            "STRSTARTS("
            "STR(?predicate), "
            f'"{escaped}"'
            ")"
        )

    return (
        "FILTER("
        + " && ".join(conditions)
        + ")"
    )


def _query_subjects(
    subjects: Set[str],
) -> Dict[str, Any]:

    if not subjects:

        return {
            "results": {
                "bindings": []
            }
        }

    values = "\n".join(
        _sparql_iri(uri)
        for uri in sorted(subjects)
    )

    geometry_filter = (
        _geometry_filter_sparql()
    )

    query = f"""
SELECT ?uri ?predicate ?object
WHERE {{
    VALUES ?uri {{
        {values}
    }}

    GRAPH ?graph {{
        ?uri ?predicate ?object .

        {geometry_filter}
    }}
}}
"""

    LOG.info(
        "Querying current RDF state for "
        "%d subjects in one SPARQL request",
        len(subjects),
    )

    response = requests.post(
        _sparql_url(),
        data={
            "query": query,
        },
        headers={
            "Accept":
                "application/sparql-results+json",
        },
        auth=_auth("neptune-db"),
        timeout=90,
    )

    if not response.ok:

        LOG.error(
            "Batched SPARQL lookup failed: "
            "HTTP %s %s",
            response.status_code,
            response.text[:2000],
        )

    response.raise_for_status()

    return response.json()


# ---------------------------------------------------------------------------
# SPARQL result handling
# ---------------------------------------------------------------------------

def _binding_value(
    binding: Dict[str, Any],
    key: str,
) -> str:

    value = binding.get(key)

    if not value:
        return ""

    return str(
        value.get(
            "value",
            "",
        )
    )


def _build_documents(
    subjects: Set[str],
    payload: Dict[str, Any],
) -> Dict[str, Optional[Dict[str, str]]]:

    grouped: Dict[
        str,
        Dict[str, str],
    ] = defaultdict(
        lambda: {
            "uri": "",
            "label": "",
            "code": "",
            "type": "",
        }
    )

    bindings = (
        payload
        .get("results", {})
        .get("bindings", [])
    )

    for binding in bindings:

        uri = _binding_value(
            binding,
            "uri",
        )

        predicate = _binding_value(
            binding,
            "predicate",
        )

        value = _binding_value(
            binding,
            "object",
        )

        if not uri or not predicate:
            continue

        if _ignored_predicate(
            predicate
        ):
            continue

        doc = grouped[uri]

        doc["uri"] = uri

        if predicate == RDFS_LABEL:

            doc["label"] = value

        elif predicate == RDF_TYPE:

            doc["type"] = value

        elif (
            _predicate_local_name(
                predicate
            )
            == "GeoObject-code"
        ):

            doc["code"] = value

    documents: Dict[
        str,
        Optional[Dict[str, str]],
    ] = {}

    for uri in subjects:

        doc = grouped.get(uri)

        if not doc:

            documents[uri] = None
            continue

        if not (
            doc.get("label")
            or doc.get("code")
            or doc.get("type")
        ):

            documents[uri] = None
            continue

        documents[uri] = {
            "uri": uri,
            "label": doc.get(
                "label",
                "",
            ),
            "code": doc.get(
                "code",
                "",
            ),
            "type": doc.get(
                "type",
                "",
            ),
        }

    return documents


# ---------------------------------------------------------------------------
# OpenSearch bulk operations
# ---------------------------------------------------------------------------

def _bulk_write(
    documents: Dict[
        str,
        Optional[Dict[str, str]],
    ],
) -> None:

    if not documents:
        return

    lines: List[str] = []

    for uri, document in documents.items():

        if document is None:

            lines.append(
                json.dumps({
                    "delete": {
                        "_index":
                            TARGET_INDEX,
                        "_id":
                            uri,
                    }
                })
            )

            continue

        lines.append(
            json.dumps({
                "index": {
                    "_index":
                        TARGET_INDEX,
                    "_id":
                        uri,
                }
            })
        )

        lines.append(
            json.dumps(
                document
            )
        )

    body = "\n".join(lines) + "\n"

    LOG.info(
        "Sending %d updates/deletes "
        "to OpenSearch in one bulk request",
        len(documents),
    )

    response = requests.post(
        (
            f"{_opensearch_base_url()}"
            "/_bulk"
        ),
        data=body,
        auth=_auth("es"),
        headers={
            "Content-Type":
                "application/x-ndjson",
        },
        timeout=90,
    )

    if not response.ok:

        LOG.error(
            "OpenSearch bulk request failed: "
            "HTTP %s %s",
            response.status_code,
            response.text[:2000],
        )

    response.raise_for_status()

    payload = response.json()

    if not payload.get("errors"):
        return

    failures = []

    for item in payload.get(
        "items",
        [],
    ):

        operation = (
            item.get("index")
            or item.get("delete")
            or {}
        )

        status = operation.get(
            "status"
        )

        error = operation.get(
            "error"
        )

        if (
            status == 404
            and item.get("delete")
        ):

            continue

        if error:

            failures.append(
                operation
            )

    if failures:

        raise RuntimeError(
            "OpenSearch bulk replication "
            "contained errors: "
            + json.dumps(
                failures[:10]
            )
        )


# ---------------------------------------------------------------------------
# Runtime guard
# ---------------------------------------------------------------------------

def _runtime_exceeded(
    started_at: float,
    context: Any,
) -> bool:

    elapsed = (
        time.monotonic()
        - started_at
    )

    if elapsed >= MAX_RUNTIME_SECONDS:

        LOG.warning(
            "Replication worker reached configured "
            "runtime limit: elapsed=%.1fs limit=%ds. "
            "Exiting gracefully.",
            elapsed,
            MAX_RUNTIME_SECONDS,
        )

        return True

    if context is not None:

        remaining_ms = (
            context
            .get_remaining_time_in_millis()
        )

        if remaining_ms <= 60_000:

            LOG.warning(
                "Lambda has only %d ms remaining. "
                "Exiting gracefully.",
                remaining_ms,
            )

            return True

    return False


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(
    event: Dict[str, Any],
    context: Any,
) -> Dict[str, Any]:

    started_at = time.monotonic()

    checkpoint = _read_checkpoint()

    if checkpoint is None:

        raise RuntimeError(
            "No Neptune stream checkpoint exists in DynamoDB. "
            "Initialize the replication checkpoint before "
            "running this poller."
        )

    commit_num = int(
        checkpoint["commitNum"]
    )

    op_num = int(
        checkpoint["opNum"]
    )

    total_records = 0
    total_subjects = 0
    pages_processed = 0


    LOG.info(
        "Starting Neptune -> OpenSearch replication "
        "from commitNum=%s opNum=%s "
        "batchSize=%d maxRuntimeSeconds=%d",
        commit_num,
        op_num,
        BATCH_SIZE,
        MAX_RUNTIME_SECONDS,
    )


    while True:

        #
        # Don't begin another page if we've reached our
        # intentional runtime cutoff.
        #
        if _runtime_exceeded(
            started_at,
            context,
        ):

            break


        page_started_at = time.monotonic()


        LOG.info(
            "Fetching stream page from "
            "commitNum=%s opNum=%s",
            commit_num,
            op_num,
        )


        stream = _fetch_stream(
            commit_num,
            op_num,
        )

        records = (
            stream.get("records")
            or []
        )


        # -------------------------------------------------------------------
        # We're caught up.
        # -------------------------------------------------------------------

        if not records:

            LOG.info(
                "No additional Neptune stream records. "
                "Replication is caught up."
            )

            break


        subjects = _changed_subjects(
            records
        )


        LOG.info(
            "Fetched %d stream records; "
            "%d unique non-geometry subjects require refresh",
            len(records),
            len(subjects),
        )


        # -------------------------------------------------------------------
        # One SPARQL query + one OpenSearch bulk write for this stream page.
        # -------------------------------------------------------------------

        if subjects:

            sparql_started_at = (
                time.monotonic()
            )

            payload = _query_subjects(
                subjects
            )

            sparql_elapsed = (
                time.monotonic()
                - sparql_started_at
            )


            documents = _build_documents(
                subjects,
                payload,
            )


            opensearch_started_at = (
                time.monotonic()
            )

            _bulk_write(
                documents
            )

            opensearch_elapsed = (
                time.monotonic()
                - opensearch_started_at
            )

        else:

            sparql_elapsed = 0.0
            opensearch_elapsed = 0.0

            LOG.info(
                "Page contained only ignored geometry "
                "mutations; no OpenSearch work required."
            )


        # -------------------------------------------------------------------
        # Page succeeded. Advance checkpoint NOW.
        # -------------------------------------------------------------------

        last = (
            stream.get("lastEventId")
            or {}
        )

        if (
            "commitNum" not in last
            or "opNum" not in last
        ):

            raise RuntimeError(
                "Neptune stream returned records "
                "but did not provide lastEventId"
            )


        new_commit_num = int(
            last["commitNum"]
        )

        new_op_num = int(
            last["opNum"]
        )


        if (
            new_commit_num == commit_num
            and new_op_num == op_num
        ):

            raise RuntimeError(
                "Neptune returned stream records but "
                "lastEventId did not advance. "
                "Aborting to prevent an infinite loop."
            )


        _write_checkpoint(
            new_commit_num,
            new_op_num,
        )


        commit_num = new_commit_num
        op_num = new_op_num

        total_records += len(
            records
        )

        total_subjects += len(
            subjects
        )

        pages_processed += 1


        page_elapsed = (
            time.monotonic()
            - page_started_at
        )

        total_elapsed = (
            time.monotonic()
            - started_at
        )


        LOG.info(
            "Page %d complete: "
            "streamRecords=%d uniqueSubjects=%d "
            "sparqlSeconds=%.3f "
            "openSearchSeconds=%.3f "
            "pageSeconds=%.3f "
            "totalRecords=%d "
            "totalElapsedSeconds=%.1f",
            pages_processed,
            len(records),
            len(subjects),
            sparql_elapsed,
            opensearch_elapsed,
            page_elapsed,
            total_records,
            total_elapsed,
        )


    elapsed = (
        time.monotonic()
        - started_at
    )


    LOG.info(
        "Replication invocation finished: "
        "pages=%d records=%d subjects=%d "
        "elapsed=%.1fs checkpoint=(%s,%s)",
        pages_processed,
        total_records,
        total_subjects,
        elapsed,
        commit_num,
        op_num,
    )


    return {
        "pagesProcessed":
            pages_processed,

        "processedRecords":
            total_records,

        "processedSubjects":
            total_subjects,

        "elapsedSeconds":
            round(elapsed, 2),

        "commitNum":
            commit_num,

        "opNum":
            op_num,
    }