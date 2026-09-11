# Neptune → OpenSearch Replication Lambda

## 1. What this function does

This Lambda is a poller that keeps an OpenSearch index in sync with a
Neptune graph. On each invocation it:

1. Reads the last committed Neptune Streams checkpoint (`commitNum` /
   `opNum`) from a DynamoDB table.
2. Fetches up to `BATCH_SIZE` records from the Neptune Streams endpoint,
   starting after that checkpoint.
3. Parses each stream record to find the changed subject + predicate, and
   throws away subjects whose *only* changes were to geometry predicates
   (e.g. `geo:asWKT`) — geometry churn is extremely common and shouldn't
   trigger a re-index.
4. For every subject that *does* need a refresh, re-queries Neptune for its
   current state in a **single** batched SPARQL request (across all named
   graphs, explicitly excluding geometry predicates so geometry is never
   fetched or indexed).
5. Reconstructs the OpenSearch `geo_objects` document for each subject —
   `uri`, `label` (from `rdfs:label`), `type` (from `rdf:type`), and `code`
   (from whichever predicate's local name is `GeoObject-code`). A subject
   that no longer resolves to anything in Neptune is treated as deleted.
6. Applies all of that page's updates/deletes to OpenSearch in a **single**
   `_bulk` request.
7. Persists the new checkpoint immediately after each page succeeds, so a
   crash mid-run only replays the in-flight page, not everything before it.
8. Keeps pulling additional pages until Neptune has nothing left, or until
   `MAX_RUNTIME_SECONDS` has elapsed (default 720s / 12 min), at which point
   it exits gracefully — the next scheduled invocation picks up right where
   this one left off.

Deliberately, the replicator has no knowledge of graph names, the LPG
namespace, the `lpgs` prefix, or concrete `GeoObject` types — it infers
everything generically from RDF vocabulary (`rdfs:label`, `rdf:type`, and
the `GeoObject-code` predicate's local name), so it doesn't need to change
as the ontology grows.

Both Neptune and OpenSearch are called over HTTPS using SigV4-signed
requests (`requests_aws4auth`), i.e. IAM auth rather than a username and
password.

## 2. Running the tests

The tests live in `tests/` (`test_new.py` + `conftest.py` — the filename
predates the `main.py` rename, but its content targets `main.py`). They
simulate a
deployed environment without touching any real AWS resources:

```bash
pip install -r tests/requirements-test.txt
pytest tests -v
```

How the mocking works, at a high level:

- **DynamoDB (the checkpoint table)** is faked in-memory with
  [`moto`](https://github.com/getmoto/moto). A real DynamoDB table is
  created inside `moto`'s mock AWS account before each test, so
  `_read_checkpoint` / `_write_checkpoint` exercise the actual DynamoDB API
  shape (`get_item`/`put_item`, `Decimal` values, etc.) rather than a
  hand-rolled stub.
- **Neptune (SPARQL + Streams) and OpenSearch (`_bulk`)** are faked with a
  small in-test HTTP router (`HttpMock` in `conftest.py`) that stands in for
  `requests.get`/`requests.post`. Each test scripts the HTTP responses it
  wants back (a stream page, a SPARQL result set, a bulk response) and can
  assert on exactly what was sent — the query text, which subjects were
  batched together, the bulk NDJSON body, etc.
- Because `main.py` reads its config from environment variables and builds
  its boto3 DynamoDB resource **at import time**, tests can't just `import
  main` once — different tests need different environments (e.g. a test
  that a missing env var raises). `conftest.py`'s `load_module` fixture
  handles this by `exec`-ing `main.py` fresh from disk under whatever
  environment a given test needs, so each test gets an isolated module
  object and nothing leaks between tests.

Test coverage spans both unit-level pieces (URL building, predicate/geometry
filtering, stream statement parsing, SPARQL query construction, document
building, bulk-write error handling, the runtime/time-budget guard) and
full `lambda_handler` end-to-end scenarios (happy path, geometry-only pages,
multi-page pagination until caught up, an expired stream checkpoint, a
stalled checkpoint, and confirming the checkpoint does *not* advance when
the OpenSearch write fails).

## 3. Building `function.zip` for deployment

`build.sh` packages `main.py` and its pinned dependencies (from
`requirements.txt`) into a deployable `function.zip`, the same way the
other lambdas in this repo do it (see `lambda/name-resolution-opensearch/`):

```bash
./build.sh
```

That:

1. Wipes any previous `package/` and `function.zip`.
2. `pip install`s `requirements.txt` into `package/`.
3. Copies `main.py` into `package/`.
4. Zips the contents of `package/` into `function.zip` at the repo root of
   this lambda.

Upload `function.zip` as the function code, with the handler set to:

```
main.lambda_handler
```

`package/` and `function.zip` are build output and are gitignored — don't
commit them.

## 4. Deployment configuration

### Required environment variables

| Variable | Description |
| --- | --- |
| `NEPTUNE_ENDPOINT` | Neptune cluster endpoint (hostname, or a full `https://host:port` URL). |
| `OPENSEARCH_ENDPOINT` | OpenSearch domain endpoint (hostname, or a full URL). |
| `TARGET_INDEX` | OpenSearch index that receives the replicated `geo_objects` documents. |
| `CHECKPOINT_TABLE` | DynamoDB table name used to persist the Neptune Streams checkpoint. Must already contain (or be seeded with) an item with a `streamId` key of `"default"` before the first run — the function raises on a cold table rather than silently starting from the beginning of the stream. |

### Optional environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `NEPTUNE_PORT` | `8182` | Used only if `NEPTUNE_ENDPOINT` is a bare hostname. |
| `BATCH_SIZE` | `5000` | Max Neptune stream records fetched per page. |
| `MAX_RUNTIME_SECONDS` | `720` (12 min) | Soft cutoff — the function stops pulling new pages once this elapses, and exits cleanly for the next invocation to resume. |
| `IGNORED_PREDICATE_PREFIXES` | `http://www.opengis.net/ont/geosparql#` | Comma-separated predicate URI prefixes to treat as geometry (excluded from SPARQL re-queries and from triggering a re-index). |

`AWS_REGION` isn't in the table above because Lambda sets it automatically
at runtime — but note the code falls back to `us-gov-west-1` if it's ever
unset (used for SigV4-signing the Neptune/OpenSearch requests), which
implies this is meant to run in GovCloud. Double check that's still correct
for wherever this gets deployed.

### Other knobs worth setting

- **Timeout — 15 minutes.** `MAX_RUNTIME_SECONDS` defaults to 720s (12 min)
  specifically so the function always exits *before* a hard Lambda timeout
  — but that only helps if the Lambda's own configured timeout is at least
  a few minutes longer. Set the function timeout to Lambda's maximum of 15
  minutes (900s) so the in-flight SPARQL query + OpenSearch bulk write for
  the last page always has room to finish.
- **Memory.** This function is I/O-bound (HTTP calls to Neptune/OpenSearch)
  rather than compute- or memory-heavy — the amount of data held in memory
  at once is bounded by `BATCH_SIZE`. 1024 MB is a reasonable starting
  point; note that Lambda also scales CPU with memory, so bumping it can
  speed up JSON parsing/serialization for large batches if pages are slow.
  Watch max memory used in CloudWatch after a few real runs and tune from
  there — there's no hard requirement here.
- **Reserved concurrency — 1.** Checkpoint advancement isn't
  compare-and-swap; two overlapping invocations reading the same checkpoint
  could both process the same page and race on the final `put_item`. If
  this is triggered on a fixed schedule (e.g. EventBridge), set reserved
  concurrency to 1 so a slow invocation can't overlap with the next
  scheduled one.
- **Trigger.** This is designed to be invoked on a schedule (e.g. an
  EventBridge rate/cron rule), not synchronously — it always returns once
  it's caught up or hits `MAX_RUNTIME_SECONDS`, and expects to be called
  again later to keep polling.
- **Networking.** If Neptune and/or the OpenSearch domain are VPC-only
  (typical), the function needs to run in that VPC (subnets + a security
  group that can reach both endpoints on 8182/443), and will need a NAT
  gateway or VPC interface endpoints if it also needs to reach DynamoDB.
- **IAM execution role.** At minimum: `dynamodb:GetItem` and
  `dynamodb:PutItem` on `CHECKPOINT_TABLE`; `neptune-db:connect` (or your
  org's equivalent read-query permission) on the Neptune cluster; and
  `es:ESHttpGet`/`es:ESHttpPost` on the OpenSearch domain's `_bulk` and
  index paths. All three are IAM-authenticated (SigV4), not
  username/password.
