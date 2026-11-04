# ReconAI — Build Instructions for Coding Agents

> **Status:** Corrective revision — v1.2.1 (based on v1.2)
> **Date:** 2026-11-04
> **Audience:** Coding Agents & Implementation Engineers
> **Authority:** Governing build rules for ReconAI implementation.
> **Corrective revision:** 2026-11-04 — closes implementation-contract gaps found during independent review.
> **Changes from v1.1:**
> - Enforced 13 database entities in SQLAlchemy models and Alembic migrations.
> - Specified `DEMO_ACCESS_PASSWORD` and `JWT_SECRET` backend environment variable usage.
> - Mandated strict use of `Decimal` for financial calculations and `AMOUNT_TOLERANCE = Decimal("1.00")`.

---

## 1. Non-Negotiable Coding Rules

1. **Financial Calculations:** NEVER use Python `float` or SQL `FLOAT`/`REAL` for currency amounts. Always use `decimal.Decimal` in Python and `NUMERIC(15,2)` in PostgreSQL.
2. **Environment Variables:** `DEMO_ACCESS_PASSWORD` and `JWT_SECRET` must NEVER be exposed to the frontend or sent in API responses.
3. **Database Entities:** Ensure all 13 tables defined in `DATABASE_SCHEMA.md` are correctly mapped in `backend/db/models.py`.
4. **Fuzzy Decisions vs Exceptions:** Do not mix fuzzy match decisions with exception reviews. Use `fuzzy_match_decisions` as a persistent multi-candidate registry and `POST /sessions/{id}/fuzzy-matches/{candidate_id}/decision`; never store unconfirmed proposals in `match_results`.
5. **Report Generation:** Reports must run synchronously and include the legal disclaimer footer.

---

## 2. Environment Configuration Reference

```bash
# backend/.env
DATABASE_URL=postgresql://user:password@localhost:5432/reconai
DEMO_ACCESS_PASSWORD=your_demo_password_here
JWT_SECRET=your_jwt_signing_secret_32_chars_min
GEMINI_API_KEY=your_gemini_api_key_here
UPLOAD_DIR=/tmp/reconai_uploads
CORS_ORIGINS=http://localhost:3000
```

```bash
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## 3. Reconciliation and Data Integrity Implementation Rules

1. `match_results` contains confirmed `EXACT` or `CONFIRMED_FUZZY` PR-GSTR-2B pairs only. It must not contain proposed candidates, one-sided missing records, or undefined partial rows.
2. `fuzzy_match_decisions` is the persistent candidate registry. Multiple candidate rows may reference one PR or GSTR-2B record. Candidate status is `PROPOSED`, `CONFIRMED`, `REJECTED`, or `SUPERSEDED`. Each decision transition writes an append-only `audit_log` event.
3. Generate stable `source_record_key` values from file SHA-256 + record type + row/page/item position. Candidate hashes also include the current normalized-value fingerprint; manual corrections invalidate old decisions without erasing their history.
4. Apply confirmed fuzzy decisions before invoice linking. Confirming a candidate must lock and validate both records and supersede competing proposals. Rejecting a candidate must preserve the row and leave records available for other proposals.
5. Exact matching requires complete non-null GSTIN and invoice-normalization keys. Do not match `NULL` keys or select arbitrary duplicates.
6. Missing counterpart exceptions are created for unmatched PR/GSTR records only after exact and confirmed decisions; duplicate-excluded records are not double-counted.
7. Compare money only when both sides are non-null. One missing side creates `MISSING_FINANCIAL_VALUE`; both missing sides are non-comparable; never substitute zero.
8. Invoice PDFs provide invoice-header evidence only. Line-item extraction and line-item reconciliation are V2.
9. Every document upload must expose a status URL and implement `GET /sessions/{id}/documents/{document_id}`. Required-source failures block reconciliation; optional invoice failures do not.
10. Use composite database constraints and service-level ownership checks so cross-client/session references cannot be created.
11. `operator_label` is self-declared under the shared demo password; never present it as verified identity.
12. Treat FastAPI `BackgroundTasks` as best-effort for the hackathon. Persist processing state and recover stale `PROCESSING` documents as explicit failures, not successes.

## 4. Required Test Gate

Do not mark a roadmap task complete or call the MVP ready until all acceptance tests in `DEVELOPMENT_ROADMAP.md` pass. Use deterministic synthetic fixtures, pytest, and API integration tests. Include regression tests for multiple fuzzy candidates sharing one record, unmatched classification, `None` financial values, reruns, and document-status polling.
