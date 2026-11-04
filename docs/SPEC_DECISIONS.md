# ReconAI — Final Business & Architectural Decisions

> **Status:** Corrective revision — v1.2.1 (based on v1.2)
> **Date:** 2026-11-04
> **Scope:** Architecture, Data Integrity, Security, Business Rules

## 1. Authentication and Attribution

1. Use backend-only `DEMO_ACCESS_PASSWORD` for shared demo login and a separate `JWT_SECRET` for token signing.
2. Validate the password with `hmac.compare_digest`.
3. Shared authentication identifies a demo principal, not an individual. Reviewer/operator labels are self-declared and must not be represented as verified identity.

## 2. Source and Reconciliation Scope

1. PR ↔ GSTR-2B is the independent reconciliation baseline. Invoice PDFs are optional invoice-level evidence only.
2. MVP does not extract or reconcile invoice line items.
3. Exact matching requires complete non-null GSTIN and `invoice_norm_key` values.
4. Duplicate groups are created only from complete matching keys; missing keys are not treated as duplicate groups.
5. Confirmed `match_results` are one-to-one PR-GSTR-2B pairs. One-sided records are represented by missing-counterpart exceptions, not partial/missing match rows.
6. Unmatched PR creates `MISSING_IN_GSTR2B`; unmatched GSTR-2B creates `MISSING_IN_PR`, after all exact and confirmed fuzzy decisions. Duplicate-excluded records are not double-classified.

## 3. Fuzzy Candidate Lifecycle

1. `fuzzy_match_decisions` is the persistent candidate registry, not merely a single decision per source record. Multiple proposed rows may reference one record.
2. Candidate states: `PROPOSED`, `CONFIRMED`, `REJECTED`, `SUPERSEDED`.
3. Proposed candidates are not `match_results`. All candidates require explicit human confirmation.
4. With two non-null GSTINs, they must match and token-sort score must be ≥85. With exactly one missing GSTIN, score must be ≥95, invoice dates must be within 3 days, and at least one shared amount field must be within ₹1.00. Both missing GSTINs or different non-null GSTINs are prohibited.
5. Confirming locks both records, creates a `CONFIRMED_FUZZY` match, and supersedes competing proposals. Rejecting preserves the candidate and does not create a match.
6. Candidate keys include stable source-position identity and current normalized-value fingerprints. Corrections invalidate old decisions for matching but never delete their audit history.
7. Every rerun resets current non-excluded record match states before rebuilding; exact/confirmed matches and active proposals then set the current state deterministically.
8. Exception status mapping is fixed (`ACCEPTED`, `DISPUTED`, `DEFERRED`, `OPEN`); severity is an MVP display mapping only. No `RESOLVED` action/state exists in MVP.

## 4. Financial and Missing-Value Rules

1. `AMOUNT_TOLERANCE = Decimal("1.00")` is an MVP business-rule choice, not a universal GST rule.
2. Apply independently to taxable value, CGST, SGST, IGST, and invoice total when both sides are present.
3. Exactly one missing value creates `MISSING_FINANCIAL_VALUE`; both missing values are non-comparable; `None` is never converted to zero.

## 5. Credit Notes and Ingestion

1. Any explicit credit/debit-note indicator or negative document-level invoice total/taxable value causes atomic failure of the entire source file (`FAILED`, `UNSUPPORTED_CREDIT_NOTE`). No records from that file are persisted.
2. A negative line item alone is not an MVP signal because line-item extraction is V2.
3. Negative amounts are never made positive.
4. Asynchronous document status is polled using `GET /sessions/{session_id}/documents/{document_id}`. Failed required PR/GSTR inputs block reconciliation; failed optional invoice PDFs do not.

## 6. Invoice Evidence

1. Invoice evidence links by exact complete GSTIN + normalized invoice number.
2. Missing invoice exceptions are emitted only for confirmed PR-GSTR-2B pairs. If any uploaded invoice PDF is still processing, defer both types and set `invoice_evidence_pending = true`; the baseline may still complete. Once all invoice files are terminal, use `NO_DOCS` if none were uploaded, otherwise `UNMATCHED` when no unique invoice record links.
3. A uniquely matching invoice may support a one-sided missing-counterpart exception. Unlinked invoices remain in source inventory; there is no separate orphan invoice exception in MVP.

## 7. Audit, Ownership, and API Contracts

1. `exception_reviews` keeps immutable snapshots and stable `discrepancy_key` values based on exception type and sorted stable source-record keys.
2. Fuzzy state transitions are appended to `audit_log`; current candidate state is retained in `fuzzy_match_decisions`.
3. Current-run matches/exceptions may be rebuilt on rerun; source records, reviews, fuzzy candidate history and audit events are not physically deleted.
4. Composite database constraints and service validation enforce client/session ownership across all related entities.
5. API routes must cover client, period, session, document polling, fuzzy candidate listing/decision, exception listing/detail/review, and report download.

## 8. Product Boundaries

1. No live GSTN connection, GST filing, ITC eligibility determination, or tax/legal advice.
2. AI may extract and explain only. Matching, arithmetic, classification and state transitions are deterministic backend operations.
3. BackgroundTasks is a hackathon-scale best-effort mechanism; stale processing records are explicitly failed and surfaced for operator action.
