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
|   1 | documents_1.jsonl     |        4000 |       3844 |     156 | completed    |
|   2 | documents_2.jsonl     |        3000 |       2884 |     116 | completed    |
|   3 | documents_3.jsonl     |        2000 |       1917 |      83 | completed    |
|   4 | documents_4.jsonl     |        1500 |       1436 |      64 | completed    |
|   5 | documents_5.jsonl     |         500 |        474 |      26 | completed    |
| **sum** |                   |   **11000** |  **10555** | **445** |              |

These totals match the data profile in `docs/architecture_plan.md`: 11,000 input lines
total, 10,555 valid records promoted to `raw_documents` (and ultimately to `documents`),
445 hard-skips recorded in `ingestion_errors` (`not_object` / `broken_stub` / invalid JSON).

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
10555
```

## Logging

Each ingestion run gets its own log file at `logs/ingestion_run_{run_id}.log` (in addition
to the same records being emitted to stdout). INFO records mark stage start/end and batch
progress, WARNING records mirror per-document `normalization_warnings`, and ERROR records
mirror rows written to `ingestion_errors`.

### Full log: run 5 (`documents_5.jsonl`, 500 lines, 474 valid)

This is the smallest run and is reproduced here in full as a representative example —
26 `ERROR` lines (one per skipped line, mirroring `ingestion_errors`), ~149 `WARNING`
lines (one per document with `normalization_warnings`), then one `INFO` line per stage
plus the final "pipeline completed":

```
2026-06-10 17:48:57,910 ERROR app.processing.raw_load_worker: run 5: line 17 skipped (broken_stub): broken stub record
2026-06-10 17:48:57,911 ERROR app.processing.raw_load_worker: run 5: line 64 skipped (broken_stub): broken stub record
2026-06-10 17:48:57,911 ERROR app.processing.raw_load_worker: run 5: line 82 skipped (broken_stub): broken stub record
2026-06-10 17:48:57,911 ERROR app.processing.raw_load_worker: run 5: line 83 skipped (not_object): expected a JSON object, got list
2026-06-10 17:48:57,912 ERROR app.processing.raw_load_worker: run 5: line 102 skipped (broken_stub): broken stub record
... (21 more ERROR lines, one per skipped line) ...
2026-06-10 17:48:57,942 INFO app.processing.raw_load_worker: run 5: stage 0 complete - total_lines=500 raw_loaded=474 skipped=26
2026-06-10 17:48:57,948 WARNING app.processing.normalize_worker: raw_document 10085: published_at: could not parse date: 'invalid-date'
2026-06-10 17:48:57,948 WARNING app.processing.normalize_worker: raw_document 10087: published_at: could not parse date: '2023-13-45'; tags: tags list contained non-string elements, which were dropped
2026-06-10 17:48:57,948 WARNING app.processing.normalize_worker: raw_document 10090: word_count: could not parse integer: 'lots'
2026-06-10 17:48:57,948 WARNING app.processing.normalize_worker: raw_document 10091: status: unrecognized status: ''
2026-06-10 17:48:57,949 WARNING app.processing.normalize_worker: raw_document 10092: status: unrecognized status: ''
... (143 more WARNING lines, one per document with a normalization warning) ...
2026-06-10 17:48:57,995 WARNING app.processing.normalize_worker: raw_document 10552: status: unrecognized status: ''
2026-06-10 17:48:58,055 INFO app.processing.normalize_worker: stage 1: normalized 474 raw documents (remaining=0)
2026-06-10 17:48:58,055 INFO app.services.ingestion_service: app.processing.normalize_worker: processed=474 remaining=0
2026-06-10 17:48:59,400 INFO app.processing.duplicates_worker: stage 2: processed 474 documents (remaining=0)
2026-06-10 17:48:59,400 INFO app.services.ingestion_service: app.processing.duplicates_worker: processed=474 remaining=0
2026-06-10 17:48:59,463 INFO app.processing.scoring_worker: stage 3: scored 474 documents (remaining=0)
2026-06-10 17:48:59,463 INFO app.services.ingestion_service: app.processing.scoring_worker: processed=474 remaining=0
2026-06-10 17:48:59,474 INFO app.services.ingestion_service: run 5: pipeline completed
```

### Excerpt: run 1 (`documents_1.jsonl`, 4000 lines, 3844 valid) — batching across stages

Run 1 is the largest (3844 valid documents) and shows the `default_batch_size=500` batching
behaviour across all three normalization/dedup/scoring stages (156 `ERROR` lines and 1275
`WARNING` lines omitted for brevity):

```
2026-06-10 17:48:49,414 ERROR app.processing.raw_load_worker: run 1: line 87 skipped (not_object): expected a JSON object, got list
2026-06-10 17:48:49,414 ERROR app.processing.raw_load_worker: run 1: line 88 skipped (broken_stub): broken stub record
... (154 more ERROR lines) ...
2026-06-10 17:48:49,620 INFO app.processing.raw_load_worker: run 1: stage 0 complete - total_lines=4000 raw_loaded=3844 skipped=156
... (1275 WARNING lines, one per document with a normalization warning) ...
2026-06-10 17:48:49,790 INFO app.processing.normalize_worker: stage 1: normalized 500 raw documents (remaining=3344)
2026-06-10 17:48:49,898 INFO app.processing.normalize_worker: stage 1: normalized 500 raw documents (remaining=2844)
2026-06-10 17:48:50,002 INFO app.processing.normalize_worker: stage 1: normalized 500 raw documents (remaining=2344)
2026-06-10 17:48:50,105 INFO app.processing.normalize_worker: stage 1: normalized 500 raw documents (remaining=1844)
2026-06-10 17:48:50,223 INFO app.processing.normalize_worker: stage 1: normalized 500 raw documents (remaining=1344)
2026-06-10 17:48:50,325 INFO app.processing.normalize_worker: stage 1: normalized 500 raw documents (remaining=844)
2026-06-10 17:48:50,446 INFO app.processing.normalize_worker: stage 1: normalized 500 raw documents (remaining=344)
2026-06-10 17:48:50,527 INFO app.processing.normalize_worker: stage 1: normalized 344 raw documents (remaining=0)
2026-06-10 17:48:50,830 INFO app.processing.duplicates_worker: stage 2: processed 500 documents (remaining=713)
2026-06-10 17:48:50,870 INFO app.processing.duplicates_worker: stage 2: processed 500 documents (remaining=213)
2026-06-10 17:48:50,887 INFO app.processing.duplicates_worker: stage 2: processed 213 documents (remaining=0)
2026-06-10 17:48:51,099 INFO app.processing.scoring_worker: stage 3: scored 500 documents (remaining=1844)
... (more scoring batches) ...
2026-06-10 17:48:51,227 INFO app.processing.scoring_worker: stage 3: scored 344 documents (remaining=0)
2026-06-10 17:48:51,236 INFO app.services.ingestion_service: run 1: pipeline completed
```

Note that stage 2 (duplicates) reaches `remaining=0` after only 1213 of the 3844 documents
appear in `processed` counts — `process_batch()` recomputes `duplicate_group_id`/
`is_canonical`/`duplicate_confidence` for the *entire title cohort* of every document in its
batch (per `docs/adr/0002-duplicate-detection-grouping.md`), so a single batch can resolve
many more documents than its own size.

## Idempotency / `force` flow

Re-posting an already-completed file without `force` is rejected with `409`; with
`force=true` it is accepted as a new run (re-processing the same source file from scratch):

```bash
$ curl -s -o /dev/null -w "%{http_code}\n" -F "file=@input_docs/documents_1.jsonl" http://localhost:8000/ingestions
409
$ curl -s -F "file=@input_docs/documents_1.jsonl" "http://localhost:8000/ingestions?force=true"
{"id":6,"status":"queued","source_file":"documents_1.jsonl","file_hash":"ed6d18c4737c711f89db71f26fd3a1a34c44db8c619283b6d78accfd743cd8ab"}
```

(Run 6 from this example was discarded — the database was reset to a clean state before
capturing the final `/stats` numbers in `docs/stats_examples.md`.)
