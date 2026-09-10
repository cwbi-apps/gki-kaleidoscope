"""Neptune Streams -> OpenSearch poller.

Adapted from AWS's amazon-neptune-fulltext-search reference.

Each invocation:
1. Read the last committed stream offset from DynamoDB
2. Pull a batch of records from the Neptune Streams API (SigV4)
3. Project each record into a geo_objects-shaped document
4. Bulk-index into OpenSearch (SigV4)
5. Advance the checkpoint atomically on success

NOTE:
This is a scaffolded implementation. The full record projection logic
(SPARQL/PG model -> geo_objects mapping fields) is application-specific
and should be filled in alongside the Kaleidoscope + GeoPrism domain model.

The control loop, IAM, error routing, and idempotency are production-shaped.
"""

import json
import logging
import os
from typing import Any, Dict, List, Tuple

import boto3
import requests
from requests_aws4auth import AWS4Auth


LOG = logging.getLogger()
LOG.setLevel(logging.INFO)


REGION = os.environ.get("AWS_REGION", "us-gov-west-1")

NEPTUNE_ENDPOINT = os.environ["NEPTUNE_ENDPOINT"]
NEPTUNE_PORT = os.environ.get("NEPTUNE_PORT", "8182")
NEPTUNE_DB_NAME = os.environ.get("NEPTUNE_DB_NAME", "sparql")

OPENSEARCH_ENDPOINT = os.environ["OPENSEARCH_ENDPOINT"]
TARGET_INDEX = os.environ["TARGET_INDEX"]

CHECKPOINT_TABLE = os.environ["CHECKPOINT_TABLE"]
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "100"))

STREAM_ID = "default"  # one logical stream per cluster


_ddb = boto3.resource("dynamodb")
_table = _ddb.Table(CHECKPOINT_TABLE)


def _auth(service: str) -> AWS4Auth:
    creds = boto3.Session().get_credentials().get_frozen_credentials()

    return AWS4Auth(
        creds.access_key,
        creds.secret_key,
        REGION,
        service,
        session_token=creds.token,
    )


def _read_checkpoint() -> Dict[str, Any]:
    resp = _table.get_item(Key={"streamId": STREAM_ID})

    return resp.get("Item") or {
        "streamId": STREAM_ID,
        "commitNum": 1,
        "opNum": 1,
    }


def _write_checkpoint(commit_num: int, op_num: int) -> None:
    _table.put_item(
        Item={
            "streamId": STREAM_ID,
            "commitNum": commit_num,
            "opNum": op_num,
        }
    )


def _fetch_stream(commit_num: int, op_num: int) -> Dict[str, Any]:
    base = NEPTUNE_ENDPOINT

    if not base.startswith("http"):
        base = f"https://{base}:{NEPTUNE_PORT}"

    url = f"{base}/{NEPTUNE_DB_NAME}/stream"

    params = {
        "iteratorType": (
            "AFTER_SEQUENCE_NUMBER"
            if (commit_num or op_num)
            else "TRIM_HORIZON"
        ),
        "commitNum": commit_num,
        "opNum": op_num,
        "limit": BATCH_SIZE,
    }

    resp = requests.get(
        url,
        params=params,
        auth=_auth("neptune-db"),
        timeout=20,
    )

    print("Status:", resp.status_code)
    print("Body:", resp.text)

    if resp.status_code == 404:
        return {
            "records": [],
            "lastEventId": {
                "commitNum": commit_num,
                "opNum": op_num,
            },
        }

    resp.raise_for_status()
    return resp.json()


def _project_record(
    record: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    """Project a Neptune Streams record into a geo_objects doc.

    TODO: domain-specific projection.

    The scaffold below extracts vertex ID + label as a placeholder.

    The real implementation must populate:
    uri/label/code/type/geometryWkt/hasGeometry
    per the WKT testing notes schema.
    """
    data = record.get("data") or {}

    vertex_id = (
        data.get("id")
        or record.get("eventId", {}).get("opNum", "unknown")
    )

    doc = {
        "uri": str(vertex_id),
        "label": str(data.get("value", {}).get("value", "")),
        "code": "",
        "type": str(data.get("type", "")),
        "geometryWkt": "",
        "hasGeometry": False,
    }

    return str(vertex_id), doc


def _bulk_index(
    docs: List[Tuple[str, Dict[str, Any]]],
) -> None:
    if not docs:
        return

    endpoint = OPENSEARCH_ENDPOINT

    if not endpoint.startswith("http"):
        endpoint = f"https://{endpoint}"

    lines = []

    for doc_id, doc in docs:
        lines.append(
            json.dumps(
                {
                    "index": {
                        "_index": TARGET_INDEX,
                        "_id": doc_id,
                    }
                }
            )
        )
        lines.append(json.dumps(doc))

    body = "\n".join(lines) + "\n"

    resp = requests.post(
        f"{endpoint}/_bulk",
        data=body,
        auth=_auth("es"),
        headers={"Content-Type": "application/x-ndjson"},
        timeout=30,
    )

    resp.raise_for_status()

    payload = resp.json()

    if payload.get("errors"):
        # Let the Lambda fail so the DLQ captures the event.
        # The next poll will replay from the unadvanced checkpoint.
        raise RuntimeError(
            "OpenSearch bulk index had errors: "
            f"{json.dumps(payload)[:1000]}"
        )


def lambda_handler(
    event: Dict[str, Any],
    _context: Any,
) -> Dict[str, Any]:
    checkpoint = _read_checkpoint()

    commit_num = int(checkpoint.get("commitNum") or 1)
    op_num = int(checkpoint.get("opNum") or 1)

    LOG.info(
        "Polling from commitNum=%s opNum=%s",
        commit_num,
        op_num,
    )

    stream = _fetch_stream(commit_num, op_num)
    records = stream.get("records") or []

    if not records:
        LOG.info("No new records")
        return {"processed": 0}

    projected = [_project_record(record) for record in records]

    _bulk_index(projected)

    last = stream.get("lastEventId") or {}

    _write_checkpoint(
        int(last.get("commitNum") or commit_num),
        int(last.get("opNum") or op_num),
    )

    LOG.info(
        "Processed %d records; checkpoint advanced",
        len(records),
    )

    return {"processed": len(records)}