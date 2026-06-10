---
status: accepted
---

# Duplicate detection groups by title + (shared author OR shared source)

This is a synthetic dataset: ~41 titles each repeat 176-386 times, with author/organization/source/doi/url independently randomized within each title cohort — simulating different sites republishing the same underlying document (e.g. an EU climate report mirrored by multiple national government sites).

Two Documents are duplicates iff they share a `normalized_title` AND (the same non-Unknown author OR the same non-empty `source_name`). Connected components within each title cohort form Duplicate Groups; the Canonical Document is chosen by earliest `published_at`, then completeness, then lowest id. Organization, language, and region agreement only contribute to a `duplicate_confidence` score (0.5-1.0) — they don't create grouping edges on their own.

## Considered options

- **Title alone**: rejected — over-groups, since ~376 unrelated-looking records share each title.
- **Title + organization**: rejected — under-groups the "EU report mirrored by different national sites" scenario, where organization legitimately differs.
- **Content similarity (body/doi)**: rejected — profiling found 0 shared DOIs and no near-identical body text across the corpus, so there's no usable content-based signal.

## Consequences

Two records sharing a title but with completely disjoint author, source, organization, language, and region are treated as coincidentally-same-titled distinct Documents, not duplicates. This is a deliberate false-negative tradeoff, documented in the README as an assumption.
