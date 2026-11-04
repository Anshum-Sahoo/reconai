# ReconAI — Implementation Blockers and Release Gates

> **Status:** Specification blockers addressed in v1.2.1; implementation gates remain open.
> **Date:** 2026-11-04

## A. Specification-Level P0 Blockers

No unresolved specification-level P0 blocker is intentionally left in this corrective package. The following contracts were added: document polling/readiness; multi-candidate fuzzy registry; complete unmatched-record classification; exact distinction between proposed candidates and confirmed matches.

## B. Mandatory Implementation Gates (Open Until Proven by Tests)

1. Implement all 13 tables and composite client/session ownership constraints in SQLAlchemy and Alembic.
2. Implement document status polling and persisted state transitions, including stale `PROCESSING` recovery.
3. Implement atomic file-level credit-note failure and verify no extracted records from a failed file are committed.
4. Implement PR-GSTR exact matching without invoice files.
5. Implement `fuzzy_match_decisions` as the persistent candidate registry; confirm/reject/supersede operations must be transactional and append audit events.
6. Verify candidate hashes change after manual normalized-field corrections, while historic candidate rows and audit events remain.
7. Implement one-sided missing exceptions and duplicate-exclusion rules exactly once.
8. Implement financial comparison with `None` semantics; no zero coercion and no float arithmetic.
9. Implement invoice linking after exact/confirmed-fuzzy baseline creation.
10. Implement all API paths, including client/period/session CRUD-lite, document status, candidate/exception lists, and report download.
11. Enforce shared-demo identity limits; `operator_label` is unverified.
12. Execute all acceptance tests listed in `SPEC_CONSISTENCY_CHECKLIST.md`.

## C. Known MVP Deployment Limitation

FastAPI `BackgroundTasks` is best-effort, not a durable job queue. For the hackathon MVP, persist all state transitions and detect stale `PROCESSING` rows on startup. Do not claim durable at-least-once processing. A durable worker/queue may be introduced in a later version if deployment reliability requires it.

## D. Release Decision

Do not label ReconAI implementation-ready, production-ready, or tax-validated based on documents alone. The release gate is the passing automated test suite, migration review, and successful end-to-end synthetic-data demo.
