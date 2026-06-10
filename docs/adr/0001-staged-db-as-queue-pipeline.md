---
status: accepted
---

# Use SQLite tables as a "DB-as-queue" instead of a real message queue

The task asks for a multi-stage processing pipeline (raw-load -> normalize -> dedup -> score) driven by "workers" pulling from queues, but adding Celery/Redis/RQ is heavy infrastructure for a 1-day SQLite-based take-home.

We use SQLite tables/columns as the queue. `raw_documents.status` (`pending`/`normalized`) and nullable result columns on `documents` (`duplicate_group_id`/`is_canonical`/`quality_score`) act as queue markers. Each "worker" is a `process_batch()` function that pulls rows `WHERE <marker> IS NULL` (or `status='pending'`). `POST /ingestions` schedules `run_pipeline()` via FastAPI `BackgroundTasks`, and a startup hook resumes incomplete runs and drains all queues.

## Consequences

This demonstrates the queue/worker separation the task asks for with zero extra infrastructure, but it only works correctly for a single process — there's no row-locking across concurrent workers and no at-least-once delivery guarantee. A production version would swap in Celery/RQ + Postgres with `SELECT ... FOR UPDATE SKIP LOCKED`.
