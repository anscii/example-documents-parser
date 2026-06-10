# Sample execution log

This is a real run against a freshly-migrated, empty `data/app.db`, ingesting all five
`input_docs/documents_*.jsonl` files one at a time via `POST /ingestions`, polling
`GET /ingestions/{id}` until each run reaches a terminal status.

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000 &

for f in input_docs/documents_*.jsonl; do
  resp=$(curl -s -F "file=@$f" http://localhost:8000/ingestions)
  run_id=$(echo "$resp" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
  while true; do
    status=$(curl -s "http://localhost:8000/ingestions/$run_id" | python3 -c "import sys,json;print(json.load(sys.stdin)['status'])")
    [ "$status" = "completed" ] || [ "$status" = "failed" ] && break
    sleep 1
  done
  echo "run $run_id ($f): $status"
done
```

## Per-run summary

Each `POST /ingestions` call returns immediately with `status: "queued"`; the pipeline
(stages 0-3) then runs in a `BackgroundTask` and `GET /ingestions/{id}` reaches
`status: "completed"` a few seconds later.

| run | source file          | total_lines | raw_loaded | skipped | final status |
|----:|----------------------|------------:|-----------:|--------:|--------------|
|   1 | documents_1.jsonl     |        4000 |       3766 |     234 | completed    |
|   2 | documents_2.jsonl     |        3000 |       2834 |     166 | completed    |
|   3 | documents_3.jsonl     |        2000 |       1875 |     125 | completed    |
|   4 | documents_4.jsonl     |        1500 |       1396 |     104 | completed    |
|   5 | documents_5.jsonl     |         500 |        462 |      38 | completed    |
| **sum** |                   |   **11000** |  **10333** | **667** |              |

These totals match the data profile in `docs/architecture_plan.md`: 11,000 input lines
total, 10,333 valid records promoted to `raw_documents` (and ultimately to `documents`),
667 hard-skips recorded in `ingestion_errors`. The skip categories are `not_object`
(`[]`), `broken_stub` (`{"broken": true}`), `empty` (`{}` — see `CONTEXT.md`), and
`invalid_json` (malformed JSON).

After all five runs complete, draining each processing stage manually confirms the
global queues are empty:

```bash
$ curl -s -X POST http://localhost:8000/processing/normalize
{"processed":0,"remaining":0}
$ curl -s -X POST http://localhost:8000/processing/duplicates
{"processed":0,"remaining":0}
$ curl -s -X POST http://localhost:8000/processing/scoring
{"processed":0,"remaining":0}
$ curl -s "http://localhost:8000/documents?page_size=1" | python3 -c "import sys,json;print(json.load(sys.stdin)['total'])"
10333
```

## Logging

Each ingestion run gets its own log file at `logs/ingestion_run_{run_id}.log` (in addition
to the same records being emitted to stdout). The first line is always an `INFO`
"pipeline started" marker, and the run ends with an `INFO` "FINAL SUMMARY" line (per-run
totals for normalized/duplicate/scored documents plus elapsed time) followed by "pipeline
completed". In between: `INFO` records mark stage start/end and batch progress, `WARNING`
records mirror per-document `normalization_warnings` (each prefixed with the raw
document's `external_id`, or `None` if it had none), and `ERROR` records mirror rows
written to `ingestion_errors`.

### Full log: run 5 (`documents_5.jsonl`, 500 lines, 462 valid)

This is the smallest run and is reproduced here in full as a representative example —
38 `ERROR` lines (one per skipped line, mirroring `ingestion_errors`, including the
`empty` category for `{}` records), 148 `WARNING` lines (one per document with
`normalization_warnings`), then one `INFO` line per stage plus the `FINAL SUMMARY` and
"pipeline completed":

```
2026-06-10 23:21:08,425 INFO app.services.ingestion_service: run 5: pipeline started (source_file=documents_5.jsonl, status=queued)
2026-06-10 23:21:08,426 ERROR app.processing.raw_load_worker: run 5: line 17 skipped (broken_stub): broken stub record
2026-06-10 23:21:08,426 ERROR app.processing.raw_load_worker: run 5: line 20 skipped (empty): expected a non-empty JSON object
2026-06-10 23:21:08,427 ERROR app.processing.raw_load_worker: run 5: line 31 skipped (empty): expected a non-empty JSON object
2026-06-10 23:21:08,427 ERROR app.processing.raw_load_worker: run 5: line 64 skipped (broken_stub): broken stub record
2026-06-10 23:21:08,428 ERROR app.processing.raw_load_worker: run 5: line 82 skipped (broken_stub): broken stub record
... (33 more ERROR lines, one per skipped line) ...
2026-06-10 23:21:08,459 INFO app.processing.raw_load_worker: run 5: stage 0 complete - total_lines=500 raw_loaded=462 skipped=38
2026-06-10 23:21:08,466 WARNING app.processing.normalize_worker: raw_document 9875 (external_id=doc-000003): published_at: could not parse date: 'invalid-date'
2026-06-10 23:21:08,466 WARNING app.processing.normalize_worker: raw_document 9877 (external_id=None): published_at: could not parse date: '2023-13-45'; tags: tags list contained non-string elements, which were dropped
2026-06-10 23:21:08,466 WARNING app.processing.normalize_worker: raw_document 9880 (external_id=None): word_count: could not parse integer: 'lots'
2026-06-10 23:21:08,466 WARNING app.processing.normalize_worker: raw_document 9881 (external_id=doc-000009): status: unrecognized status: ''
2026-06-10 23:21:08,466 WARNING app.processing.normalize_worker: raw_document 9882 (external_id=doc-000010): status: unrecognized status: ''
... (142 more WARNING lines, one per document with a normalization warning) ...
2026-06-10 23:21:08,515 WARNING app.processing.normalize_worker: raw_document 10330 (external_id=doc-000496): status: unrecognized status: ''
2026-06-10 23:21:08,604 INFO app.processing.normalize_worker: stage 1: normalized 462 raw documents (remaining=0)
2026-06-10 23:21:08,604 INFO app.services.ingestion_service: app.processing.normalize_worker: processed=462 remaining=0
2026-06-10 23:21:09,981 INFO app.processing.duplicates_worker: stage 2: processed 462 documents (remaining=0)
2026-06-10 23:21:09,982 INFO app.services.ingestion_service: app.processing.duplicates_worker: processed=462 remaining=0
2026-06-10 23:21:10,026 INFO app.processing.scoring_worker: stage 3: scored 462 documents (remaining=0)
2026-06-10 23:21:10,026 INFO app.services.ingestion_service: app.processing.scoring_worker: processed=462 remaining=0
2026-06-10 23:21:10,036 INFO app.services.ingestion_service: run 5: FINAL SUMMARY - total_lines=500 raw_loaded=462 skipped=38 normalized=462 duplicates=374 scored=462 elapsed=2.03s
2026-06-10 23:21:10,036 INFO app.services.ingestion_service: run 5: pipeline completed
```

### Excerpt: run 1 (`documents_1.jsonl`, 4000 lines, 3766 valid) — batching across stages

Run 1 is the largest (3766 valid documents) and shows the `default_batch_size=500` batching
behaviour across all three normalization/dedup/scoring stages (234 `ERROR` lines and 1275
`WARNING` lines omitted for brevity):

```
2026-06-10 23:20:59,880 INFO app.services.ingestion_service: run 1: pipeline started (source_file=documents_1.jsonl, status=queued)
2026-06-10 23:20:59,880 ERROR app.processing.raw_load_worker: run 1: line 7 skipped (empty): expected a non-empty JSON object
2026-06-10 23:20:59,882 ERROR app.processing.raw_load_worker: run 1: line 68 skipped (empty): expected a non-empty JSON object
... (232 more ERROR lines) ...
2026-06-10 23:21:00,090 INFO app.processing.raw_load_worker: run 1: stage 0 complete - total_lines=4000 raw_loaded=3766 skipped=234
... (1275 WARNING lines, one per document with a normalization warning, e.g.
"raw_document 2 (external_id=doc-000001): status: unrecognized status: ''") ...
2026-06-10 23:21:00,263 INFO app.processing.normalize_worker: stage 1: normalized 500 raw documents (remaining=3266)
2026-06-10 23:21:00,375 INFO app.processing.normalize_worker: stage 1: normalized 500 raw documents (remaining=2766)
2026-06-10 23:21:00,487 INFO app.processing.normalize_worker: stage 1: normalized 500 raw documents (remaining=2266)
2026-06-10 23:21:00,591 INFO app.processing.normalize_worker: stage 1: normalized 500 raw documents (remaining=1766)
2026-06-10 23:21:00,711 INFO app.processing.normalize_worker: stage 1: normalized 500 raw documents (remaining=1266)
2026-06-10 23:21:00,816 INFO app.processing.normalize_worker: stage 1: normalized 500 raw documents (remaining=766)
2026-06-10 23:21:00,946 INFO app.processing.normalize_worker: stage 1: normalized 500 raw documents (remaining=266)
2026-06-10 23:21:01,017 INFO app.processing.normalize_worker: stage 1: normalized 266 raw documents (remaining=0)
2026-06-10 23:21:01,324 INFO app.processing.duplicates_worker: stage 2: processed 500 documents (remaining=643)
2026-06-10 23:21:01,355 INFO app.processing.duplicates_worker: stage 2: processed 500 documents (remaining=143)
2026-06-10 23:21:01,386 INFO app.processing.duplicates_worker: stage 2: processed 143 documents (remaining=0)
2026-06-10 23:21:01,427 INFO app.processing.scoring_worker: stage 3: scored 500 documents (remaining=3266)
2026-06-10 23:21:01,470 INFO app.processing.scoring_worker: stage 3: scored 500 documents (remaining=2766)
2026-06-10 23:21:01,511 INFO app.processing.scoring_worker: stage 3: scored 500 documents (remaining=2266)
2026-06-10 23:21:01,569 INFO app.processing.scoring_worker: stage 3: scored 500 documents (remaining=1766)
2026-06-10 23:21:01,610 INFO app.processing.scoring_worker: stage 3: scored 500 documents (remaining=1266)
2026-06-10 23:21:01,668 INFO app.processing.scoring_worker: stage 3: scored 500 documents (remaining=766)
2026-06-10 23:21:01,709 INFO app.processing.scoring_worker: stage 3: scored 500 documents (remaining=266)
2026-06-10 23:21:01,738 INFO app.processing.scoring_worker: stage 3: scored 266 documents (remaining=0)
2026-06-10 23:21:01,755 INFO app.services.ingestion_service: run 1: FINAL SUMMARY - total_lines=4000 raw_loaded=3766 skipped=234 normalized=3766 duplicates=2772 scored=3766 elapsed=2.74s
2026-06-10 23:21:01,755 INFO app.services.ingestion_service: run 1: pipeline completed
```

Note that stage 2 (duplicates) reaches `remaining=0` after only 1143 of the 3766 documents
appear in `processed` counts — `process_batch()` recomputes `duplicate_group_id`/
`is_canonical`/`duplicate_confidence` for the *entire title cohort* of every document in its
batch (per `docs/adr/0002-duplicate-detection-grouping.md`), so a single batch can resolve
many more documents than its own size.

## Idempotency / `force` flow

Re-posting an already-completed file without `force` is rejected with `409`; with
`force=true` it is accepted as a new run (re-processing the same source file from
scratch). Continuing from the state above (5 completed runs, ids 1-5):

```bash
$ curl -s -o /dev/null -w "%{http_code}\n" -F "file=@input_docs/documents_1.jsonl" http://localhost:8000/ingestions
409
$ curl -s -F "file=@input_docs/documents_1.jsonl" "http://localhost:8000/ingestions?force=true"
{"id":6,"status":"queued","source_file":"documents_1.jsonl","file_hash":"ed6d18c4737c711f89db71f26fd3a1a34c44db8c619283b6d78accfd743cd8ab"}
```

This run 6 is not part of the 5-run sequence above — it would re-process
`documents_1.jsonl` from scratch, adding another 3766 `documents` rows (and shifting the
`/stats` totals in `docs/stats_examples.md`), so it is omitted from the figures here.
