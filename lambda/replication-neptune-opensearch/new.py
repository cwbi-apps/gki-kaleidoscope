"""
Neptune SPARQL Streams -> OpenSearch replication poller.

Performance-optimized batch flow:

  1. Read the last committed Neptune stream checkpoint from DynamoDB.
  2. Pull a batch from /sparql/stream.
  3. Parse changed RDF subjects + predicates.
  4. Ignore subjects whose changes are geometry-only.
  5. Re-query ALL affected subjects in one SPARQL request across all named graphs.
  6. Reconstruct existing geo_objects documents:
       uri
       label
       code
       type
  7. Apply all index/delete operations in one OpenSearch _bulk request.
  8. Advance the DynamoDB checkpoint only after the whole batch succeeds.

The replicator intentionally does NOT know:
  - graph names
  - LPG namespace
  - lpgs prefix
  - concrete GeoObject types

It infers:
  - label from rdfs:label
  - type from rdf:type
  - code from any predicate whose local name is "GeoObject-code"

Required environment variables:
  NEPTUNE_ENDPOINT
  OPENSEARCH_ENDPOINT
  TARGET_INDEX
  CHECKPOINT_TABLE

Optional environment variables:
  NEPTUNE_PORT=8182
  BATCH_SIZE=100
  IGNORED_PREDICATE_PREFIXES=http://www.opengis.net/ont/geosparql#
"""

import json
import logging
import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

import boto3
import requests
from requests_aws4auth import AWS4Auth


LOG = logging.getLogger()
LOG.setLevel(logging.INFO)


REGION = os.environ.get(
    "AWS_REGION",
    "us-gov-west-1",
)

NEPTUNE_ENDPOINT = os.environ["NEPTUNE_ENDPOINT"]
NEPTUNE_PORT = os.environ.get(
    "NEPTUNE_PORT",
    "8182",
)

OPENSEARCH_ENDPOINT = os.environ["OPENSEARCH_ENDPOINT"]
TARGET_INDEX = os.environ["TARGET_INDEX"]
CHECKPOINT_TABLE = os.environ["CHECKPOINT_TABLE"]

BATCH_SIZE = int(
    os.environ.get(
        "BATCH_SIZE",
        "100",
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


# ---------------------------------------------------------------------------
# Neptune stream statement parsing
# ---------------------------------------------------------------------------

# Expected beginning of a SPARQL stream statement:
#
#   <subject> <predicate> ...
#
# We only need subject + predicate from the stream record.
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
            f"https://{endpoint}:"
            f"{NEPTUNE_PORT}"
        )

    return endpoint


def _sparql_url() -> str:

    return (
        f"{_neptune_base_url()}/sparql"
    )


def _stream_url() -> str:

    return (
        f"{_neptune_base_url()}"
        "/sparql/stream"
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
        timeout=20,
    )

    LOG.info(
        "Neptune stream returned HTTP %s",
        response.status_code,
    )

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
                "The requested change records are no longer available. "
                "Reset/rebuild the replication state before resuming "
                "this poller."
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
    """
    Extract the local name from an RDF predicate IRI.

    Examples:

      https://example/schema#GeoObject-code
        -> GeoObject-code

      https://example/schema/GeoObject-code
        -> GeoObject-code
    """

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

    match = STATEMENT_RE.match(statement)

    if not match:

        LOG.warning(
            "Unable to parse subject/predicate "
            "from stream statement: %s",
            statement[:500],
        )

        return None

    subject = match.group(1)
    predicate = match.group(2)

    return subject, predicate


def _changed_subjects(
    records: List[Dict[str, Any]],
) -> Set[str]:
    """
    Return subjects requiring OpenSearch refresh.

    If a subject has ONLY geometry-related mutations in this stream
    batch, skip it entirely.

    If at least one non-geometry predicate changed for the subject,
    refresh the subject exactly once.
    """

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
    """
    Validate an IRI before interpolation into VALUES.

    These subject IRIs came from Neptune itself, but reject characters
    that would make the generated SPARQL invalid.
    """

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

    #
    # GRAPH ?graph searches every named graph.
    #
    # No graph or LPG namespace needs to be configured.
    #
    query = f"""
SELECT ?uri ?graph ?predicate ?object
WHERE {{
    VALUES ?uri {{
        {values}
    }}

    GRAPH ?graph {{
        ?uri ?predicate ?object .
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
        timeout=60,
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
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Reconstruct the existing geo_objects OpenSearch document shape:

      {
        "uri": "...",
        "label": "...",
        "code": "...",
        "type": "..."
      }

    We discover the relevant RDF predicates dynamically:

      rdfs:label      -> label
      rdf:type        -> type
      *#GeoObject-code
      */GeoObject-code -> code

    No LPG namespace is hard-coded.
    """

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
        Optional[Dict[str, Any]],
    ] = {}

    for uri in subjects:

        doc = grouped.get(uri)

        #
        # No current triples for this subject means it was deleted.
        #
        if not doc:

            documents[uri] = None
            continue

        #
        # A subject with none of the properties represented by
        # geo_objects does not belong in this index.
        #
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
        Optional[Dict[str, Any]],
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
        "Sending %d subject updates/deletes "
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
        timeout=60,
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

        #
        # Deleting something that no longer exists is fine.
        #
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
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(
    event: Dict[str, Any],
    _context: Any,
) -> Dict[str, Any]:

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

    LOG.info(
        "Polling Neptune SPARQL stream "
        "from commitNum=%s opNum=%s",
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

    if not records:

        LOG.info(
            "No new Neptune stream records"
        )

        return {
            "processedRecords": 0,
            "processedSubjects": 0,
        }

    #
    # Collapse potentially many stream mutations into
    # one refresh per affected GeoObject.
    #
    subjects = _changed_subjects(
        records
    )

    LOG.info(
        "Stream returned %d records; "
        "%d unique subjects require refresh",
        len(records),
        len(subjects),
    )

    if subjects:

        #
        # ONE SPARQL query for the entire batch.
        #
        payload = _query_subjects(
            subjects
        )

        #
        # Reconstruct current geo_objects state.
        #
        documents = _build_documents(
            subjects,
            payload,
        )

        #
        # ONE OpenSearch bulk request.
        #
        _bulk_write(
            documents
        )

    else:

        LOG.info(
            "All stream mutations were ignored "
            "geometry changes; no OpenSearch writes required"
        )

    #
    # Do not advance this until ALL work above has succeeded.
    #
    last = (
        stream.get("lastEventId")
        or {}
    )

    if (
        "commitNum" not in last
        or "opNum" not in last
    ):

        raise RuntimeError(
            "Neptune stream response contained records "
            "but no lastEventId"
        )

    new_commit_num = int(
        last["commitNum"]
    )

    new_op_num = int(
        last["opNum"]
    )

    _write_checkpoint(
        new_commit_num,
        new_op_num,
    )

    LOG.info(
        "Replication complete: "
        "%d stream records, "
        "%d refreshed subjects",
        len(records),
        len(subjects),
    )

    return {
        "processedRecords":
            len(records),
        "processedSubjects":
            len(subjects),
        "commitNum":
            new_commit_num,
        "opNum":
            new_op_num,
    }