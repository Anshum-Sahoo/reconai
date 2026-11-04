# ReconAI — API Contracts Specification

> **Status:** Corrective revision — v1.2.1 (based on v1.2)
> **Date:** 2026-11-04
> **Base URL:** `https://{backend-host}/api/v1`
> **Authentication:** `Authorization: Bearer {session_token}` on all routes except `/health` and `/auth/session`.
> **Conventions:** All timestamps are UTC ISO-8601. Currency values are decimal strings. `operator_label` is self-declared and is not an authenticated personal identity.

## 0. Authentication and Health

### `POST /auth/session` (public)
Request: `{"password":"..."}`. The backend validates against `DEMO_ACCESS_PASSWORD` with `hmac.compare_digest`, then issues an HMAC-SHA256 token signed by separate `JWT_SECRET` (default 8-hour expiry). Invalid password returns `401`. The token subject is the shared demo principal; it does not identify an individual reviewer.

### `GET /health` (public)
Returns service/database health and application version. Do not expose environment variables, secret values, or internal credentials.

## 1. Clients, Periods, and Sessions

### `GET /clients`
List active clients. Returns `items` with `id`, `name`, masked `gstin`, `is_active`.

### `POST /clients`
Create a client. Required body: `name`, `gstin`; optional contact fields. Validate GSTIN format and uniqueness. Returns `201` with the created client.

### `GET /clients/{client_id}/periods`
List periods for one client.

### `POST /clients/{client_id}/periods`
Create a monthly or quarterly period. Monthly requires `period_year` and `period_month`; quarterly requires `period_year` and `period_quarter`. Do not accept both month and quarter. Returns `201`.

### `GET /periods/{period_id}/sessions`
List sessions for the period.

### `POST /periods/{period_id}/sessions`
Create a reconciliation session. Returns `201` with `status = DRAFT` and `sources_ready` flags (PR and GSTR-2B false; invoices false/optional).

### `GET /sessions/{session_id}`
Returns session status, `sources_ready`, counts of required/optional documents, last reconciliation timestamp, and current summary when available.

## 2. Document Management and Processing

### `POST /sessions/{session_id}/documents`
Upload `multipart/form-data` with `file` and `document_type` (`PURCHASE_REGISTER`, `GSTR2B`, `INVOICE`). CSV/XLSX is allowed for PR/GSTR-2B; PDF only for invoice evidence. Returns `202 Accepted` with `document_id`, `status = PROCESSING`, and a status URL. PR and GSTR-2B each allow one active file per session; multiple invoice PDFs are allowed. Duplicate file hash or an existing active required-source file returns `409`. Direct PNG/JPG uploads return `422` (V2).

### `GET /sessions/{session_id}/documents`
List documents and current processing states for the session.

### `GET /sessions/{session_id}/documents/{document_id}`
Required polling endpoint. Returns:

```json
{
  "document_id": "...",
  "document_type": "PURCHASE_REGISTER",
  "status": "FAILED",
  "error_code": "UNSUPPORTED_CREDIT_NOTE",
  "error_message": "Credit/debit notes are unsupported in MVP.",
  "processed_at": "2026-11-04T12:00:00Z",
  "records_extracted": 0,
  "status_url": "/api/v1/sessions/{session_id}/documents/{document_id}"
}
```

Supported document states: `UPLOADED`, `PROCESSING`, `PROCESSED`, `PROCESSED_WITH_WARNINGS`, `FAILED`, `DUPLICATE`, `DELETED`. A failed required PR or GSTR-2B document keeps its readiness flag false and blocks reconciliation with `409 REQUIRED_SOURCE_NOT_READY` until deleted and replaced. A failed optional invoice PDF does not block baseline reconciliation; it is reported as a warning and counts as an invoice file having been uploaded for missing-invoice classification.

### `DELETE /sessions/{session_id}/documents/{document_id}`
Soft-delete the document, mark its extracted records `EXCLUDED`, and write an audit event. Returns `200`. It does not physically delete historical source records.

### `GET /sessions/{session_id}/records`
List extracted records for the session with filters for `record_type`, `match_status`, and document ID. Include source row/page provenance, raw value references, normalized values, confidence fields, and correction status.

### `GET /sessions/{session_id}/records/{record_id}`
Return one extracted record and its source provenance. Verify that the record belongs to the path session.

### `PATCH /sessions/{session_id}/records/{record_id}`
Correct supported normalized fields. Request body contains `corrected_fields`, `correction_note` (minimum 10 characters), and `operator_label`. Preserve raw source values; write before/after state to `audit_log`; recompute current-value fingerprint; leave historic fuzzy candidate decisions intact but do not apply old fingerprints. Return `reconciliation_required = true`; the operator must rerun reconciliation to rebuild current matches/exceptions.

## 3. Reconciliation Execution

### `POST /sessions/{session_id}/reconcile`
Synchronous. Requires at least one required-source document in `PROCESSED` state with valid extracted records. `PROCESSED_WITH_WARNINGS` is acceptable only for optional invoice PDFs in MVP; a required PR/GSTR file with partial parse failures remains not ready until corrected or replaced. Missing or failed required input returns `409 REQUIRED_SOURCE_NOT_READY`. Optional invoice documents are not a precondition. If uploaded invoice files remain `UPLOADED` or `PROCESSING`, complete the PR-GSTR baseline and set `invoice_evidence_pending = true`; defer both missing-invoice exception types until all invoice files reach terminal states. A failed invoice file is terminal and counts as an uploaded file.

Response `200` includes:

```json
{
  "session_id": "...",
  "status": "REVIEW",
  "reconciled_at": "2026-11-04T12:10:00Z",
  "summary": {
    "total_pr_records": 138,
    "total_gstr2b_records": 145,
    "total_invoice_records": 121,
    "exact_matches": 130,
    "confirmed_fuzzy_matches": 3,
    "proposed_fuzzy_candidates": 7,
    "rejected_fuzzy_candidates": 2,
    "unmatched_pr": 5,
    "unmatched_gstr2b": 12,
    "missing_invoice_pairs": 12,
    "invoice_evidence_pending": false,
    "total_exceptions": 26,
    "total_value_difference": "45230.00"
  }
}
```

The `partial_matches` metric is intentionally omitted because MVP has no partial `match_results`; one-sided records are represented by exceptions. `total_value_difference` sums absolute values for financial mismatch exceptions only; missing-value and non-financial exceptions are excluded. The sample counts are illustrative and must be calculated from the persisted run, not copied as constants.

## 4. Fuzzy Candidate Workflow

### `GET /sessions/{session_id}/fuzzy-matches`
List candidate-registry entries with candidate ID, PR/GSTR-2B record IDs, score, status (`PROPOSED`, `CONFIRMED`, `REJECTED`, `SUPERSEDED`), close-competition flag, source fingerprints, and self-declared decision label if any. Multiple proposals may reference the same record.

### `POST /sessions/{session_id}/fuzzy-matches/{candidate_id}/decision`
Request:

```json
{
  "decision": "CONFIRM_MATCH",
  "comment": "Verified against the source invoice and date.",
  "operator_label": "CA staff - A. Sharma"
}
```

Valid decisions: `CONFIRM_MATCH`, `REJECT_MATCH`. A comment of at least 10 characters is required. On confirmation, the server transactionally locks both records, verifies neither is already assigned, changes the candidate to `CONFIRMED`, and invokes the deterministic session rebuild so the confirmed pair becomes a `CONFIRMED_FUZZY` `match_results` row; the rebuild also reattaches invoice evidence and refreshes exceptions/summary. Competing proposals sharing either record become `SUPERSEDED`. On rejection, it records `REJECTED`, creates no match row, and preserves the candidate; the rebuild refreshes pending/missing classification. Both transitions append to `audit_log`. Repeating the same terminal decision is idempotent and returns the current result; attempting the opposite decision or confirming a candidate whose records are already assigned returns `409`.

Response includes `candidate_id`, `candidate_status`, `match_result_id` (null for rejection), `decision`, `operator_label`, and `decided_at`.

## 5. Exception Review Workflow

### `GET /sessions/{session_id}/exceptions`
List current-run exceptions with pagination and optional filters (`exception_type`, `severity`, `status`).

### `GET /sessions/{session_id}/exceptions/{exception_id}`
Return exception details, associated records from `exception_records` (required for every exception, including those with a `match_result_id`), `discrepancy_key`, `details`, AI explanation (if available), and all historical reviews for that session/discrepancy key. Historical reviews remain visible even when `exception_id` is NULL after a rerun.

### `POST /sessions/{session_id}/exceptions/{exception_id}/review`
Status mapping: `ACCEPT` → `ACCEPTED`; `DISPUTE` → `DISPUTED`; `DEFER` → `DEFERRED`; `REOPEN` → `OPEN`. There is no `RESOLVED` state/action in MVP. Exception severity is a fixed display category defined in `RECONCILIATION_RULES.md`, not a tax-risk determination.

Request: `{"action":"ACCEPT|DISPUTE|DEFER|REOPEN", "comment":"At least 10 characters", "operator_label":"CA staff - A. Sharma"}`. The comment must be at least 10 characters. The endpoint only changes exception workflow status; it never confirms or rejects a fuzzy match. It stores an immutable `exception_snapshot`, `discrepancy_key`, self-declared operator label, timestamp, and audit event.

## 6. Reports

### `POST /sessions/{session_id}/reports`
Generate `EXCEPTION_XLSX`, `SUMMARY_PDF`, or `AUDIT_XLSX` synchronously. Request includes `report_type`, optional filters, and `operator_label`. Response `200` contains report ID, status, file size, and download URL.

### `GET /sessions/{session_id}/reports/{report_id}/download`
Authenticated download. The report must belong to the same session. Returns the binary file with a safe content-disposition filename; unknown/mismatched report returns `404`.

## 7. Common Error Contract

Use a consistent JSON error body with `type`, `title`, `status`, `error_code`, and safe `detail`. Minimum relevant codes: `UNAUTHORIZED`, `REQUIRED_SOURCE_NOT_READY`, `DOCUMENT_PROCESSING_FAILED`, `UNSUPPORTED_CREDIT_NOTE`, `DUPLICATE_DOCUMENT`, `RECORD_ALREADY_MATCHED`, `CANDIDATE_ALREADY_DECIDED`, `INVALID_STATE_TRANSITION`, `RESOURCE_NOT_FOUND`, `VALIDATION_ERROR`.

## 8. Attribution and Security Boundary

The shared demo token identifies only the shared demo principal. `operator_label` is self-reported, must be displayed as such, and must never be described as verified identity. The server must never trust `client_id`, `session_id`, or record ownership from body fields when a resource path already determines ownership; validate ownership from database relationships. All routes except `/health` and `/auth/session` require a valid bearer token.
