# ReconAI — Development Roadmap Specification

> **Status:** Corrective revision — v1.2.1 (based on v1.2)
> **Date:** 2026-11-04
> **Timeline:** 18 Working Days (Hackathon Build Target)
> **Corrective revision:** 2026-11-04 — closes implementation-contract gaps found during independent review.
> **Changes from v1.1:**
> - Synchronized entity count to 13 database tables.
> - Added implementation tasks for `exception_records` association table and `fuzzy_match_decisions` table.
> - Updated Authentication tasks to reflect `DEMO_ACCESS_PASSWORD` constant-time verification and `JWT_SECRET`.
> - Updated Reconciliation Engine tasks for baseline PR ↔ GSTR-2B execution and persistent fuzzy decisions.

---

## Milestones & Critical Path

```
Days 1–3:   Foundation (FastAPI, 13 SQLAlchemy Models, Auth, DB Migrations)
Days 4–6:   Document Ingestion (CSV/XLSX, Multi-Invoice PDF, status polling, async recovery)
Days 7–9:   Reconciliation Engine (PR↔GSTR-2B baseline, candidate registry, unmatched classification, exceptions)
Days 10–12: AI Integration (Gemini Vision, Multi-Invoice Schema, Explanations)
Days 13–15: Frontend (Dashboard, Sessions, Separate Fuzzy & Exception Workspaces)
Days 16–17: Synchronous Reports (XLSX, PDF, Audit Trail) & End-to-End Validation
Day 18:     Deployment (Render + Vercel + Supabase) & Demo Script
```

---

## Milestone Breakdown

### Milestone 1: Foundation & Security (Days 1–3)
- [x] Initialize FastAPI backend project structure.
- [x] Define **13 SQLAlchemy models** in `backend/db/models.py`.
- [x] Create Alembic initial migration `0001_initial_schema.py` creating all 13 tables.
- [x] Implement constant-time password authentication in `POST /api/v1/auth/session` using `DEMO_ACCESS_PASSWORD` and HMAC-SHA256 JWT signing with `JWT_SECRET`.
- [x] Implement `verify_session_token` FastAPI security dependency.

### Milestone 2: Document Ingestion & Async Processing (Days 4–6)
- [ ] Implement file storage service (`StorageService`) with hash uniqueness checks.
- [ ] Create async background processing for tabular (CSV/XLSX) and PDF parsing; persist each state transition and handle stale PROCESSING records.
- [ ] Implement multi-invoice PDF parsing with `source_page_number` and `source_item_index` tracking; line items are V2.
- [ ] Implement atomic file-level credit-note/negative document-total rejection with `FAILED` + `UNSUPPORTED_CREDIT_NOTE`; never apply absolute value.
- [ ] Implement document deletion (`DELETE /sessions/{id}/documents/{doc_id}`) marking records `EXCLUDED`.

### Milestone 3: Deterministic Reconciliation Engine (Days 7–9)
- [ ] Implement Normalizer (GSTIN, `invoice_norm_key`, dates, Decimal amounts).
- [ ] Implement Phase 2 duplicate detection with `DUPLICATE_CANDIDATE` exceptions and `exception_records` association rows.
- [ ] Implement Phase 3 baseline exact matching (PR ↔ GSTR-2B) and invoice evidence linking.
- [ ] Implement a multi-candidate registry that permits multiple proposals per PR/GSTR record; apply strict GSTIN/amount/date guards; require confirmation; persist rejected/confirmed/superseded states and audit events.
- [ ] Implement unmatched PR/GSTR exception generation, missing-financial-value handling, confirmed-pair-only missing-invoice exceptions, and `AMOUNT_TOLERANCE = Decimal("1.00")`.

### Milestone 4: AI Guidance & Adapter (Days 10–12)
- [ ] Implement `AIProvider` protocol, `GeminiAdapter`, and `NullAdapter` fallback.
- [ ] Implement `INVOICE_EXTRACTION_SCHEMA` with multi-invoice array support.
- [ ] Implement exception explanation generator grounded in source values.

### Milestone 5: Frontend Workspace (Days 13–15)
- [ ] Scaffold Next.js 14 App Router project with Tailwind CSS & shadcn/ui.
- [ ] Implement auth flow storing session token in `sessionStorage`.
- [ ] Build Session Upload panel using `GET /sessions/{id}/documents/{document_id}` polling; surface required-source failures separately from optional invoice failures.
- [ ] Build separate **Fuzzy Match Candidates UI** (`CONFIRM_MATCH` / `REJECT_MATCH`).
- [ ] Build **Exception Review Workspace UI** (`ACCEPT`, `DISPUTE`, `DEFER`, `REOPEN`).

### Milestone 6: Reporting & Deployment (Days 16–18)
- [ ] Implement synchronous XLSX Exception Report, PDF Summary, and XLSX Audit Trail generators.
- [ ] Embed legal disclaimers on all exported reports.
- [ ] Deploy database to Supabase, backend to Render, frontend to Vercel.
- [ ] Execute complete end-to-end reconciliation verification using synthetic test data.

## 7. Required Acceptance Tests (Must Pass Before Demo)

- [ ] Exact PR-GSTR-2B matching succeeds with zero invoice PDFs uploaded.
- [ ] Multiple fuzzy proposals can reference one PR record without violating a database unique constraint; confirming one supersedes overlapping proposals.
- [ ] A proposed fuzzy candidate does not create a `match_results` row until confirmed.
- [ ] Rejected candidates survive reruns; a changed normalized value creates a new candidate fingerprint while retaining the old decision history.
- [ ] A confirmed fuzzy candidate is reapplied only when both source fingerprints remain unchanged and both records remain eligible.
- [ ] An unmatched PR generates `MISSING_IN_GSTR2B`; an unmatched GSTR-2B record generates `MISSING_IN_PR`; duplicates are not double-classified.
- [ ] Missing invoice exceptions occur only for confirmed PR-GSTR-2B pairs.
- [ ] `None` versus zero is tested; one missing side creates `MISSING_FINANCIAL_VALUE`, both missing sides are non-comparable, and neither is converted to zero.
- [ ] Every asynchronous document can be polled to a terminal state; failed required inputs block reconciliation, failed optional invoices do not.
- [ ] Credit note detection fails the whole relevant source file atomically and never creates a partial extracted subset.
- [ ] Cross-session/client foreign-key violations are rejected by the database or service validation tests.
- [ ] Exception and fuzzy decision history is retained after reruns.

All checkboxes above represent planned work. Mark them complete only after the corresponding implementation and test has actually passed.
