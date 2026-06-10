# API examples

All examples assume the server is running at `http://localhost:8000`
(`uv run uvicorn app.main:app --reload --port 8000`).

The `GET` examples below were captured against a database that already contains
the full ingested corpus (10,555 documents from all five
`input_docs/documents_*.jsonl` files — see
[`execution_log_sample.md`](./execution_log_sample.md) and
[`stats_examples.md`](./stats_examples.md)). The `POST /ingestions` examples
were captured against a freshly-migrated, empty database using the small
`tests/fixtures/sample_input/staged_pipeline.jsonl` fixture (12 lines, 9 valid
records, 3 hard-skips) so the upload/idempotency flow can be shown from a clean
slate.

---

## `POST /ingestions`

Upload a single `.jsonl` file as `multipart/form-data` (field name `file`). The
request returns `201` immediately with `status: "queued"`; all parsing and
processing (stages 0-3) happens in a background task.

```bash
$ curl -s -F "file=@tests/fixtures/sample_input/staged_pipeline.jsonl;type=application/x-ndjson" \
    http://localhost:8000/ingestions
```

```json
{
    "id": 1,
    "status": "queued",
    "source_file": "staged_pipeline.jsonl",
    "file_hash": "818451fc11736196eb93f1a81ce1845a139e70a623280e53ffaa5d4bd1b6e9ab"
}
```

A moment later, `GET /ingestions/1` shows `status: "completed"` (see below).

### Re-posting the same file (idempotency)

Re-posting the exact same bytes without `?force=true` is rejected with `409`,
referencing the existing run:

```bash
$ curl -s -w "\nHTTP %{http_code}\n" \
    -F "file=@tests/fixtures/sample_input/staged_pipeline.jsonl;type=application/x-ndjson" \
    http://localhost:8000/ingestions
```

```json
{"detail":{"message":"file already ingested","existing_run_id":1}}
HTTP 409
```

`?force=true` bypasses the check and creates a new run that re-processes the
same source file from scratch:

```bash
$ curl -s -F "file=@tests/fixtures/sample_input/staged_pipeline.jsonl;type=application/x-ndjson" \
    "http://localhost:8000/ingestions?force=true"
```

```json
{
    "id": 2,
    "status": "queued",
    "source_file": "staged_pipeline.jsonl",
    "file_hash": "818451fc11736196eb93f1a81ce1845a139e70a623280e53ffaa5d4bd1b6e9ab"
}
```

---

## `GET /ingestions?limit=&offset=`

Paginated run history, newest first. `limit`/`offset` default to `20`/`0`.

```bash
$ curl -s "http://localhost:8000/ingestions?limit=2&offset=0" | python3 -m json.tool
```

```json
{
    "items": [
        {
            "id": 5,
            "source_file": "documents_5.jsonl",
            "file_hash": "037256d03cff29e532b1b3c90e81671e0a79a58b7d21b9f59d1f35ff4deb208a",
            "status": "completed",
            "started_at": "2026-06-10T15:48:57",
            "finished_at": "2026-06-10T15:48:59.463822",
            "total_lines": 500,
            "raw_loaded_count": 474,
            "skipped_count": 26,
            "error_message": null
        },
        {
            "id": 4,
            "source_file": "documents_4.jsonl",
            "file_hash": "dbcfeb071ad0b72ad0e1cd2dcbe983541a0bf8caeba1fb0fd8786ec473d22f29",
            "status": "completed",
            "started_at": "2026-06-10T15:48:55",
            "finished_at": "2026-06-10T15:48:57.693003",
            "total_lines": 1500,
            "raw_loaded_count": 1436,
            "skipped_count": 64,
            "error_message": null
        }
    ],
    "total": 5,
    "limit": 2,
    "offset": 0
}
```

---

## `GET /ingestions/{id}`

Run detail: source file/hash, status, line counts, per-stage pending counts
(`normalize_pending`/`dedup_pending`/`scoring_pending` — all `0` once the
pipeline has completed), error count, and up to 20 sample
`ingestion_errors` rows.

```bash
$ curl -s "http://localhost:8000/ingestions/1" | python3 -m json.tool
```

```json
{
    "id": 1,
    "source_file": "documents_1.jsonl",
    "file_hash": "ed6d18c4737c711f89db71f26fd3a1a34c44db8c619283b6d78accfd743cd8ab",
    "status": "completed",
    "started_at": "2026-06-10T15:48:49",
    "finished_at": "2026-06-10T15:48:51.227808",
    "total_lines": 4000,
    "raw_loaded_count": 3844,
    "skipped_count": 156,
    "error_message": null,
    "normalize_pending": 0,
    "dedup_pending": 0,
    "scoring_pending": 0,
    "error_count": 156,
    "sample_errors": [
        {"line_number": 87, "error_category": "not_object", "error_detail": "expected a JSON object, got list"},
        {"line_number": 88, "error_category": "broken_stub", "error_detail": "broken stub record"},
        {"line_number": 132, "error_category": "broken_stub", "error_detail": "broken stub record"},
        {"line_number": 177, "error_category": "broken_stub", "error_detail": "broken stub record"},
        {"line_number": 189, "error_category": "broken_stub", "error_detail": "broken stub record"}
        // ... 15 more (sample_errors is capped at 20; error_count=156 is the true total)
    ]
}
```

A run for the small fixture (`staged_pipeline.jsonl`, all 3 error categories in
one file) looks like this:

```bash
$ curl -s "http://localhost:8000/ingestions/1" | python3 -m json.tool
```

```json
{
    "id": 1,
    "source_file": "staged_pipeline.jsonl",
    "file_hash": "818451fc11736196eb93f1a81ce1845a139e70a623280e53ffaa5d4bd1b6e9ab",
    "status": "completed",
    "started_at": "2026-06-10T16:15:17",
    "finished_at": "2026-06-10T16:15:17.813301",
    "total_lines": 12,
    "raw_loaded_count": 9,
    "skipped_count": 3,
    "error_message": null,
    "normalize_pending": 0,
    "dedup_pending": 0,
    "scoring_pending": 0,
    "error_count": 3,
    "sample_errors": [
        {"line_number": 2, "error_category": "not_object", "error_detail": "expected a JSON object, got list"},
        {"line_number": 3, "error_category": "broken_stub", "error_detail": "broken stub record"},
        {"line_number": 4, "error_category": "invalid_json", "error_detail": "Expecting ',' delimiter: line 1 column 24 (char 23)"}
    ]
}
```

A nonexistent run id returns `404`:

```bash
$ curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000/ingestions/999"
404
```

---

## `POST /processing/{normalize,duplicates,scoring}?batch_size=`

Manually drive one batch of a stage against the **global** queue (not scoped to
one run). `batch_size` defaults to `500` (`app.config.settings.default_batch_size`).
Useful for resuming/inspecting the pipeline outside of `POST /ingestions`'
automatic background drain. Once every queue is empty (the normal state after
a run completes), each call is a no-op:

```bash
$ curl -s -X POST "http://localhost:8000/processing/normalize?batch_size=100"
{"processed":0,"remaining":0}

$ curl -s -X POST http://localhost:8000/processing/duplicates
{"processed":0,"remaining":0}

$ curl -s -X POST http://localhost:8000/processing/scoring
{"processed":0,"remaining":0}
```

`processed` is the number of rows handled in this single batch; `remaining` is
the total queue size still pending after this batch (`0` means fully drained).
If `processed < remaining` after a call, the queue still has work — call the
same endpoint again (or rely on `POST /ingestions`'s automatic drain, which
loops until `remaining == 0`).

---

## `GET /documents`

Paginated, filterable document list. `page` defaults to `1`, `page_size`
defaults to `20` (max `100`). `canonical_only` defaults to `false` (shows the
full corpus, including known duplicates and documents still pending stage
2/3). Each item is a `DocumentSummary` (a trimmed view — see `GET
/documents/{id}` for the full record).

### No filters (full corpus)

```bash
$ curl -s "http://localhost:8000/documents?page_size=1" | python3 -m json.tool
```

```json
{
    "items": [
        {
            "id": 1,
            "title": "Energy Market Trends 2023",
            "author": {"id": 2, "name": "J Smith"},
            "organization": {"id": 2, "name": "International Renewable Energy Agency"},
            "source_name": "Feed A",
            "published_at": "2018-12-23",
            "language": "sv",
            "status": "draft",
            "document_type": "report",
            "region": "South Asia",
            "tags": [{"id": 1, "name": "resources"}, {"id": 2, "name": "water"}],
            "citation_count": 445,
            "relevance_score": null,
            "quality_score": 36.34,
            "is_canonical": false,
            "duplicate_group_id": 1
        }
    ],
    "total": 10555,
    "page": 1,
    "page_size": 1
}
```

### `tag`

```bash
$ curl -s -G "http://localhost:8000/documents" --data-urlencode "tag=energy" --data-urlencode "page_size=2" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print('total:',d['total']);print([i['title'] for i in d['items']])"
```

```
total: 1621
['climate policy in southern europe', 'Urban Heat Island Mitigation']
```

### `status` + `document_type`

```bash
$ curl -s -G "http://localhost:8000/documents" \
    --data-urlencode "status=published" --data-urlencode "document_type=report" --data-urlencode "page_size=2" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print('total:',d['total']);print([(i['id'],i['status'],i['document_type']) for i in d['items']])"
```

```
total: 404
[(9, 'published', 'report'), (28, 'published', 'report')]
```

### `published_after` / `published_before`

```bash
$ curl -s -G "http://localhost:8000/documents" \
    --data-urlencode "published_after=2023-01-01" --data-urlencode "published_before=2023-12-31" --data-urlencode "page_size=2" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print('total:',d['total']);print([(i['id'],i['published_at']) for i in d['items']])"
```

```
total: 1239
[(4, '2023-12-13'), (16, '2023-06-21')]
```

### `q` (substring search over title/abstract/body)

```bash
$ curl -s -G "http://localhost:8000/documents" --data-urlencode "q=hydrogen" --data-urlencode "page_size=2" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print('total:',d['total']);print([i['title'] for i in d['items']])"
```

```
total: 356
['Green Hydrogen: Cost Trajectories', 'Hydrogen Economy: Prospects and Challenges']
```

### `canonical_only=true`

Excludes only documents *known* to be non-canonical (`is_canonical IS NOT
FALSE`) — singletons (`duplicate_group_id IS NULL`, `is_canonical=true`) and
documents still pending stage 2 (`is_canonical IS NULL`) both pass:

```bash
$ curl -s -G "http://localhost:8000/documents" --data-urlencode "canonical_only=true" --data-urlencode "page_size=2" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print('total:',d['total']);print([(i['id'],i['is_canonical'],i['duplicate_group_id']) for i in d['items']])"
```

```
total: 2537
[(5, True, None), (6, True, None)]
```

### `min_quality_score` + `sort_by` + `sort_dir`

```bash
$ curl -s -G "http://localhost:8000/documents" \
    --data-urlencode "min_quality_score=90" --data-urlencode "sort_by=quality_score" \
    --data-urlencode "sort_dir=desc" --data-urlencode "page_size=3" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print('total:',d['total']);print([(i['id'],i['quality_score']) for i in d['items']])"
```

```
total: 456
[(3, 100.0), (43, 100.0), (117, 100.0)]
```

### `organization`

```bash
$ curl -s -G "http://localhost:8000/documents" \
    --data-urlencode "organization=International Renewable Energy Agency" --data-urlencode "page_size=2" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print('total:',d['total']);print([(i['id'],i['organization']['name']) for i in d['items']])"
```

```
total: 315
[(1, 'International Renewable Energy Agency'), (5, 'International Renewable Energy Agency')]
```

### `language` + `region` (combined filters)

```bash
$ curl -s -G "http://localhost:8000/documents" \
    --data-urlencode "language=en" --data-urlencode "region=Europe" --data-urlencode "page_size=2" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print('total:',d['total']);print([(i['id'],i['language'],i['region']) for i in d['items']])"
```

```
total: 98
[(6, 'en', 'Europe'), (33, 'en', 'Europe')]
```

---

## `GET /documents/{id}`

`DocumentDetail` includes everything in `DocumentSummary` plus the full set of
normalized fields, `*_raw` companions, `url_valid`/`doi_valid`,
`normalization_warnings`, and `duplicate_group` (`null` if the document is a
pending-stage-2 singleton candidate with no group, i.e.
`duplicate_group_id IS NULL`).

### A singleton (no duplicate group)

```bash
$ curl -s "http://localhost:8000/documents/5" | python3 -m json.tool
```

```json
{
    "id": 5,
    "title": null,
    "author": {"id": 1, "name": "Unknown"},
    "organization": {"id": 2, "name": "International Renewable Energy Agency"},
    "source_name": null,
    "published_at": "2018-10-18",
    "language": "de",
    "status": "draft",
    "document_type": "report",
    "region": "Middle East",
    "tags": [{"id": 5, "name": "livestock"}, {"id": 6, "name": "methane"}],
    "citation_count": 181,
    "relevance_score": 0.467,
    "quality_score": 53.0,
    "is_canonical": true,
    "duplicate_group_id": null,
    "raw_external_id": "doc-000004",
    "abstract": null,
    "body": "Longer body text. Longer body text. Longer body text.",
    "published_at_raw": "2018-10-18",
    "updated_at": "2021-02-14",
    "updated_at_raw": "2021-02-14",
    "language_raw": "de",
    "status_raw": "False",
    "document_type_raw": "REPORT",
    "url": "https://climate-inst.eu/doc/8749",
    "url_valid": true,
    "doi": null,
    "doi_valid": null,
    "word_count": null,
    "page_count": 168,
    "version": "1",
    "open_access": true,
    "peer_reviewed": true,
    "normalization_warnings": null,
    "created_at": "2026-06-10T15:48:49",
    "duplicate_group": null
}
```

Note `status_raw: "False"` (the source had `"status": false`, normalized to
`"draft"`) and `document_type_raw: "REPORT"` (case-insensitively matched to
`"report"`).

### A 2-member duplicate group (canonical + duplicate)

`/documents/774` (canonical) and `/documents/10411` (duplicate) share
`normalized_title="transport decarbonisation pathways"` and the same
`author_id`, giving `duplicate_confidence=0.75` (`0.5` title match + `0.25`
shared author):

```bash
$ curl -s "http://localhost:8000/documents/774" | python3 -c "import sys,json;d=json.load(sys.stdin);print(json.dumps({k:d[k] for k in ('id','title','author','is_canonical','duplicate_group_id','duplicate_group')}, indent=2))"
```

```json
{
    "id": 774,
    "title": "Transport Decarbonisation Pathways",
    "author": {"id": 25, "name": "Kenji Yamamoto"},
    "is_canonical": true,
    "duplicate_group_id": 774,
    "duplicate_group": {
        "group_id": 774,
        "group_size": 2,
        "is_canonical": true,
        "confidence": 0.75
    }
}
```

```bash
$ curl -s "http://localhost:8000/documents/10411" | python3 -c "import sys,json;d=json.load(sys.stdin);print(json.dumps({k:d[k] for k in ('id','title','author','is_canonical','duplicate_group_id','duplicate_group')}, indent=2))"
```

```json
{
    "id": 10411,
    "title": "Transport Decarbonisation Pathways",
    "author": {"id": 25, "name": "Kenji Yamamoto"},
    "is_canonical": false,
    "duplicate_group_id": 774,
    "duplicate_group": {
        "group_id": 774,
        "group_size": 2,
        "is_canonical": false,
        "confidence": 0.75
    }
}
```

### A large duplicate group (confidence capped at 1.0)

`/documents/12` belongs to a 169-member group where it agrees with at least
one other member on author/source plus organization/language/region, hitting
the `1.0` cap:

```bash
$ curl -s "http://localhost:8000/documents/12" | python3 -c "import sys,json;d=json.load(sys.stdin);print(json.dumps({k:d[k] for k in ('id','title','duplicate_group','normalization_warnings')}, indent=2))"
```

```json
{
    "id": 12,
    "title": "Green Hydrogen: Cost Trajectories",
    "duplicate_group": {
        "group_id": 12,
        "group_size": 169,
        "is_canonical": false,
        "confidence": 1.0
    },
    "normalization_warnings": [
        "tags: tags list contained non-string elements, which were dropped"
    ]
}
```

### Not found

```bash
$ curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000/documents/999999"
404
```

---

## `GET /stats`

Corpus-wide aggregate statistics (`total_documents`, `by_status`,
`by_document_type`, `by_region`, `by_language`, `top_tags`, `duplicate_stats`,
`quality_score_distribution`).

```bash
$ curl -s http://localhost:8000/stats | python3 -m json.tool
```

A full real response (10,555 documents) is in
[`stats_examples.md`](./stats_examples.md), including notes on bucket
semantics (`unknown` buckets for `region`/`language`/`document_type`,
histogram bucketing, etc.).
