# ReconAI — Architecture Document

> **Status:** Corrective revision — v1.2.1 (based on v1.2)
> **Date:** 2026-11-04
> **Authority:** Technical Architecture Specification for ReconAI MVP.
> **Corrective revision:** 2026-11-04 — closes implementation-contract gaps found during independent review.
> **Changes from v1.1:**
> - Updated Authentication architecture: `DEMO_ACCESS_PASSWORD` evaluated via constant-time string comparison (`hmac.compare_digest`), generating short-lived session tokens signed with `JWT_SECRET`.
> - Updated Entity Count to 13 distinct PostgreSQL tables (added `exception_records` and `fuzzy_match_decisions`).
> - Restructured Reconciliation Engine flow: Baseline execution matches PR ↔ GSTR-2B; invoice documents are linked asynchronously as optional invoice-level supporting evidence; line-item extraction is V2.
> - Added persistent fuzzy decision lookups (`fuzzy_match_decisions`) during Phase 4 matching.
> - Defined immutable exception snapshots and deterministic `discrepancy_key` generation for audit preservation.

---

## 1. System Architecture Decision Summary

| Decision | Specification | Rationale |
|---|---|---|
| Topology | **Modular Monolith (FastAPI + Next.js)** | Optimal for hackathon delivery; single-repo architecture eliminates distributed system overhead. |
| Persistence | **PostgreSQL 15+ (Supabase / Render)** | Native `NUMERIC(15,2)`, `JSONB`, relational integrity, and constraint enforcement required for financial data. |
| Authentication | **`DEMO_ACCESS_PASSWORD` + JWT Session Tokens** | Session tokens minted via `/auth/session` using constant-time password comparison. Signed via `JWT_SECRET`. Server secrets never sent to client. |
| File Storage | **Local Filesystem / Object Storage Abstracted** | Local path `/uploads/` wrapped in `StorageService` interface; ready for Cloudflare R2 / S3 in V2. |
| AI Integration | **Provider Adapter Pattern** | `AIProvider` protocol with `GeminiAdapter` and `NullAdapter` fallback. AI is strictly advisory. |
| Processing Execution | **Async Upload / Sync Engine & Reports** | Document parsing runs via FastAPI `BackgroundTasks`. Reconciliation engine and report generation execute synchronously (< 30s target). |

---

## 2. System Architecture Topology

```
┌────────────────────────────────────────────────────────────────────────┐
│                          CLIENT BROWSER                                │
│                     Next.js Frontend (Vercel)                          │
│                                                                        │
│   /dashboard   /sessions   /exceptions   /fuzzy-matches   /reports     │
│                                                                        │
│   Auth Header: Authorization: Bearer {session_token}                   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTPS REST
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend (Render)                           │
│                                                                        │
│  ┌────────────────┐  ┌──────────────────┐  ┌────────────────────────┐  │
│  │   API Layer    │  │  Service Layer   │  │   Background Tasks     │  │
│  │   (Routers)    │  │                  │  │  (FastAPI Background)  │  │
│  │                │  │  · Session       │  │  · Document Parsing    │  │
│  │  · Auth        │  │  · Client        │  │  · Multi-Invoice PDF   │  │
│  │  · Documents   │  │  · Reconciliation│  │    Extraction          │  │
│  │  · Exceptions  │  │  · Reporting     │  │  · Credit Note Check   │  │
│  │  · Fuzzy Match │  │                  │  │                        │  │
│  └───────┬────────┘  └────────┬─────────┘  └────────────────────────┘  │
│          │                    │                                        │
│          ▼                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                      Domain Services                             │  │
│  │                                                                  │  │
│  │  ┌───────────────────┐  ┌──────────────────┐  ┌───────────────┐  │  │
│  │  │ DocumentProcessor │  │ Reconciliation   │  │ AIService     │  │  │
│  │  │                   │  │ Engine           │  │ (Adapter)     │  │  │
│  │  │ · PyMuPDF         │  │ · Normalizer     │  │ · Gemini      │  │  │
│  │  │ · Gemini Vision   │  │ · Matcher        │  │   Adapter     │  │  │
│  │  │ · Tabular Parsers │  │ · Comparator     │  │ · Null        │  │  │
│  │  │                   │  │ · Classifier     │  │   Adapter     │  │  │
│  │  └───────────────────┘  └──────────────────┘  └───────────────┘  │  │
│  └────────────────────────────────┬─────────────────────────────────┘  │
│                                   │                                    │
│                                   ▼                                    │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                  Data Access Layer (SQLAlchemy 2.0)               │  │
│  └────────────────────────────────┬─────────────────────────────────┘  │
└───────────────────────────────────┼────────────────────────────────────┘
                                    │
             ┌──────────────────────┼──────────────────────┐
             ▼                      ▼                      ▼
  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
  │ PostgreSQL        │  │ Local Filesystem  │  │ Gemini API        │
  │ (Supabase)        │  │ Storage           │  │ (External)        │
  │                   │  │ /uploads/         │  │                   │
  │ · 13 Entities     │  │                   │  │ · Vision Extractor│
  │ · Audit Logs      │  │                   │  │ · Explanations    │
  │ · Persistent      │  │                   │  │                   │
  │   Fuzzy Decisions │  │                   │  │                   │
  └───────────────────┘  └───────────────────┘  └───────────────────┘
```

---

## 3. Data Processing Flows

### 3.1 Document Ingestion Flow (Async)

```
POST /sessions/{id}/documents (multipart/form-data)
  │
  ├── 1. Validate file extension & MIME type (PDF, CSV, XLSX only; PNG/JPG → 422).
  ├── 2. Compute SHA-256 file hash; check session uniqueness (duplicate hash → 409).
  ├── 3. Enforce single-active-file constraint for PR / GSTR2B (existing file → 409).
  ├── 4. Save file to storage: /uploads/{client_id}/{session_id}/{doc_id}_{filename}.
  ├── 5. Create `documents` row (status: UPLOADED).
  ├── 6. Queue BackgroundTask: process_document(document_id).
  └── 7. Return 202 Accepted + document_id.

Async Background Worker:
  ├── Update document.status = PROCESSING.
  ├── Parse Content:
  │     ├── CSV/XLSX: Read rows via pandas, map headers.
  │     └── PDF: Parse text layer via PyMuPDF. If text missing/unclear, call Gemini Vision.
  ├── Check Credit Note / Negative Amounts:
  │     └── If any invoice/row is an explicit credit/debit note or has a negative
  │           document-level invoice_total/taxable_value:
  │           Set status = FAILED, error_code = UNSUPPORTED_CREDIT_NOTE;
  │           persist no extracted rows from the entire file.
  ├── Save Extracted Records:
  │     └── Create `extracted_records` rows with source provenance and confidence scores.
  ├── Update Document Status: PROCESSED, or PROCESSED_WITH_WARNINGS for non-credit extraction gaps.
  ├── Persist error_code/error_message and processed_at on failure/warning.
  └── Update session.sources_ready flags.
```

### 3.2 Reconciliation Execution Flow (Synchronous)

```text
POST /sessions/{id}/reconcile
  1. Verify one successfully PROCESSED PR file and one successfully PROCESSED GSTR-2B file.
     Optional invoice PDFs do not gate reconciliation.
  2. In one database transaction, rebuild current-run outputs; preserve exception_reviews,
     fuzzy_match_decisions, source records and audit_log. Reset records from active/non-deleted documents to UNMATCHED; retain deleted-document records as EXCLUDED.
  3. Normalize values and compute stable source keys/value fingerprints.
  4. Detect within-source duplicates; create duplicate exceptions and exception_records.
  5. Exact-match PR ↔ GSTR-2B on complete (GSTIN, invoice_norm_key) keys.
  6. Reapply unchanged CONFIRMED fuzzy decisions only when both records remain eligible.
  7. Generate/persist eligible fuzzy proposals in fuzzy_match_decisions. Multiple candidates
     may reference one record; proposals are not match_results and require explicit review.
  8. Link invoice records to confirmed pairs (and one-sided exception evidence) by exact key.
  9. Classify unmatched PR/GSTR-2B records, missing invoice evidence, missing financial
     values and field mismatches.
 10. Enforce one-to-one invariants, compute defined summary metrics, and commit.
 11. Set session.status = REVIEW and return the summary.
```

### 3.3 Asynchronous Document Status and Recovery

- `POST /sessions/{id}/documents` returns `202` and a document status URL.
- The frontend polls `GET /sessions/{id}/documents/{document_id}` until a terminal state (`PROCESSED`, `PROCESSED_WITH_WARNINGS`, `FAILED`, or `DELETED`).
- A failed PR or GSTR-2B source keeps that required source unready; reconciliation returns `409 REQUIRED_SOURCE_NOT_READY`. A failed optional invoice PDF does not block PR-GSTR-2B reconciliation.
- MVP uses FastAPI `BackgroundTasks`; this is a hackathon-scale, best-effort execution mechanism, not a durable job queue. Persist each state transition. At startup, detect documents left in `PROCESSING` beyond the configured stale threshold, mark them `FAILED` with `PROCESSING_INTERRUPTED`, and require re-upload/retry by explicit operator action. Do not silently report them as processed.

## 4. Security & Authentication Architecture

### 4.1 Authentication Workflow

1. **Authentication Endpoint:** `POST /api/v1/auth/session` receives JSON payload `{"password": "<value>"}`.
2. **Constant-Time Verification:** Backend compares the provided password against `DEMO_ACCESS_PASSWORD` using Python's `hmac.compare_digest` to prevent timing attacks.
3. **Token Minting:** Upon successful verification, backend generates an HMAC-SHA256 JWT token signed with `JWT_SECRET`. The token payload contains `iat` (issued at) and `exp` (expiration timestamp, default 8 hours).
4. **Client-Side Authorization:** Frontend receives the token and stores it in `sessionStorage`. On all subsequent requests, frontend sends the header: `Authorization: Bearer {session_token}`.
5. **Request Interception:** FastAPI dependency `verify_session_token` decodes and verifies the token signature and expiration.
6. **Secret Isolation:** `DEMO_ACCESS_PASSWORD` and `JWT_SECRET` reside strictly in backend environment variables and are never exposed to the frontend or included in public configuration endpoints.

---

## 5. Technology Stack & Deployment Model

```
Backend:      Python 3.11+, FastAPI, SQLAlchemy 2.0 (Declarative), Alembic, PyMuPDF, RapidFuzz, ReportLab, openpyxl, pandas
Frontend:     Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui
Database:     PostgreSQL 15+ (Hosted on Supabase or Render)
Deployment:   Render Web Service (Backend) + Vercel (Frontend)
```

## 6. Data Ownership and Match Lifecycle

- Database composite foreign keys and service-level ownership checks must ensure that client, period, session, document, extracted record, match, exception, association, candidate and report references all belong to the same client/session.
- `match_results` stores confirmed exact or confirmed fuzzy PR-GSTR-2B pairs only. Each PR and GSTR-2B record can occur in at most one current confirmed pair.
- `fuzzy_match_decisions` is the persistent candidate registry. It supports multiple proposed edges per record and stores states `PROPOSED`, `CONFIRMED`, `REJECTED`, `SUPERSEDED`. Each state transition is appended to `audit_log`.
- Candidate identity is based on stable file/source-position keys plus current normalized-value fingerprints. A manual correction changes the current-value fingerprint; historical decisions remain auditable but do not apply to corrected values.
- `exception_reviews` stores an immutable exception snapshot and stable discrepancy key. A rerun may detach the live exception UUID, but must not delete historical snapshots.
