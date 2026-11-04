# ReconAI — Specification Consistency Checklist

> **Status:** Corrected specification set — v1.2.1
> **Date:** 2026-11-04
> **Verification scope:** Document-level consistency only; implementation not yet verified.

## Cross-Document Consistency Audit

| Check | Required target | Result | Evidence / rule |
|---|---|---|---|
| Database entity count | 13 tables | PASS | Same 13-table model; no new table introduced. |
| Authentication | `DEMO_ACCESS_PASSWORD` + `JWT_SECRET` | PASS | API, architecture, build guide and decisions agree. |
| Attribution | Self-declared `operator_label` | PASS | No claim of individual identity under shared demo login. |
| Money | Python `Decimal`, PostgreSQL `NUMERIC(15,2)` | PASS | Financial computations prohibit float. |
| Amount tolerance | `Decimal("1.00")` | PASS | Defined per-field and as MVP choice, not universal GST rule. |
| Baseline matching | PR ↔ GSTR-2B, invoice optional | PASS | Reconciliation rules and architecture sequence agree. |
| Exact match key | Complete non-null GSTIN + invoice key | PASS | Null keys do not exact-match. |
| Fuzzy candidates | Multi-candidate registry; all human-confirmed | PASS | Proposals are separate from confirmed `match_results`. |
| One-to-one confirmed matches | Unique confirmed source assignment | PASS | Enforced in match table and transactional decision workflow. |
| Candidate persistence | `PROPOSED/CONFIRMED/REJECTED/SUPERSEDED` | PASS | Candidate key includes stable source identity and current value fingerprint. |
| Unmatched PR/GSTR | `MISSING_IN_GSTR2B` / `MISSING_IN_PR` | PASS | Rules define timing, status resets and exclusions. |
| Financial NULLs | One missing -> `MISSING_FINANCIAL_VALUE`; both missing -> non-comparable | PASS | No `None` to zero conversion. |
| Duplicate evidence | Nullable match reference + `exception_records` | PASS | Duplicate exceptions associate all involved records. |
| Missing invoice | Only confirmed PR-GSTR pairs after invoice processing is terminal | PASS | In-progress optional PDFs defer invoice exceptions but never block baseline. |
| Credit note policy | Atomic file failure; no sign conversion | PASS | AI guardrails, PRD, API and architecture aligned. |
| Audit history | Snapshot + stable key + append-only candidate events | PASS | Rerun semantics preserve reviews/decisions/audit. |
| Async document status | Upload 202 + polling GET endpoint | PASS | Required/optional failure behaviour and persisted error codes defined. |
| Report download | Authenticated endpoint | PASS | API contract defines ownership check and binary response. |
| Record correction | GET list/detail + PATCH | PASS | Raw values retained; correction note and audit event required; rerun required. |
| Roadmap status | Tasks unchecked until completed | PASS | No planned work is represented as completed. |

## Required Implementation Acceptance Tests

- [ ] Upload PR and GSTR-2B without invoices; exact baseline run succeeds.
- [ ] Poll a document from `PROCESSING` to `PROCESSED` and to `FAILED` in separate tests.
- [ ] Failed required PR/GSTR blocks reconcile; failed optional invoice does not.
- [ ] Multiple proposals may point to one source record without violating `match_results` uniqueness.
- [ ] Confirming one proposal creates one match and supersedes overlapping proposals.
- [ ] Rejecting a proposal persists across reruns and does not create a match.
- [ ] Manual correction changes candidate fingerprint; old decision remains audit history and is not applied.
- [ ] Unmatched PR/GSTR records generate the corresponding missing exception exactly once.
- [ ] Duplicate-excluded rows are not additionally classified as missing.
- [ ] `None` vs zero, one missing side, and both missing sides follow the defined financial rules.
- [ ] Invoice absence exceptions occur only on confirmed PR-GSTR pairs.
- [ ] Cross-client/session foreign-key and service validation tests reject mismatches.
- [ ] Exception snapshots and fuzzy decision audit events survive reruns.
- [ ] Every exception type populates `exception_records` with all involved source evidence.
- [ ] Rerun resets transient match statuses before recomputation.
- [ ] Exception status transitions and severity mappings match the API and rules.
- [ ] Credit-note file failure is atomic and never converts negative amounts to positive.

## Verification Statement

The v1.2.1 documents are aligned at the specification level against the checks above. This is **not** a claim that the application is implemented or tested. Implementation readiness must be declared only after all acceptance tests pass and the code/database migrations are reviewed.
