# ReconAI — Shared Agent Instructions

> **Version:** 1.2.1  
> **Date:** 2026-11-04  
> **Applies to:** Gemini CLI, Antigravity, OpenCode, Claude Code, and any other AI coding agent working in this repository.  
> **Project root:** `reconai/`  
> **Specification authority:** The current documents in `docs/` are the source of truth. These instructions summarize their non-negotiable implementation rules; they do not replace them.

---

## 0. Before You Do Anything

ReconAI is a hackathon MVP: a GST reconciliation and evidence-intelligence platform for CA firms, GST practitioners, and SME finance teams.

**Before planning or changing code:**

1. Inspect the existing repository structure. Do not assume that an example folder tree is already present.
2. Run `git status --short` and inspect the current branch and recent changes. Preserve all existing user and teammate work.
3. Read the specification documents in this order:
   1. `docs/SPEC_DECISIONS.md`
   2. `docs/PRODUCT_REQUIREMENTS.md`
   3. `docs/ARCHITECTURE.md`
   4. `docs/DATABASE_SCHEMA.md`
   5. `docs/API_CONTRACTS.md`
   6. `docs/RECONCILIATION_RULES.md`
   7. `docs/AI_GUARDRAILS.md`
   8. `docs/DEVELOPMENT_ROADMAP.md`
   9. `docs/GEMINI_BUILD_INSTRUCTIONS.md`
   10. `docs/IMPLEMENTATION_BLOCKERS.md`
   11. `docs/SPEC_CONSISTENCY_CHECKLIST.md`
   12. `docs/SPEC_REVIEW_REPORT.md`
   13. `README.md`
4. If one of the supporting documents is absent in the repository, report that fact; do not invent its contents.
5. If two specifications conflict, stop and report the exact conflicting sections. Do not silently choose one or make a new business rule.
6. Before a broad change, provide a short plan and list the files to be changed. Work in small, reviewable batches.
7. After each batch, summarize changed files and run the most relevant tests. Do not claim a task is complete merely because code was generated.

**Do not restart or rewrite the whole project just because you have been handed off from another coding agent.** Inspect the existing code, `git diff`, and uncommitted changes first.

---

## 1. Product and MVP Boundaries

ReconAI compares three possible sources:

- **Purchase Register (PR): required.**
- **GSTR-2B statement: required.**
- **Supplier invoice PDFs: optional supporting evidence.**

The core reconciliation is deterministic **PR ↔ GSTR-2B** reconciliation. Supplier invoice PDFs provide invoice-header evidence only in the MVP. Invoice line-item extraction and line-item reconciliation are V2.

The product must not:

- Claim live GSTN/GST portal API integration.
- File GST returns or amendments.
- Determine ITC eligibility or provide tax/legal advice.
- Treat AI explanations as accounting decisions.
- Use AI to calculate financial values, select matches, change match states, or override deterministic rules.

Use clearly labelled synthetic data for demonstrations. Do not present synthetic records as real taxpayer or GSTN data.

---

## 2. Technical Architecture and Scope Discipline

The target is a **modular monolith**, not microservices.

| Layer | Technology / responsibility |
|---|---|
| Frontend | Next.js App Router, TypeScript, Tailwind CSS, shadcn/ui |
| Backend | Python 3.11+, FastAPI, Pydantic |
| Persistence | PostgreSQL 15+, SQLAlchemy 2.0, Alembic |
| Tabular ingestion | pandas and openpyxl |
| PDF extraction | PyMuPDF; Gemini Vision fallback for image-based or low-confidence PDF content |
| Fuzzy similarity | RapidFuzz |
| Reports | openpyxl for XLSX; ReportLab for PDF |
| Tests | pytest and API/integration tests; frontend tests as defined by the repository |
| AI | Gemini adapter plus NullAdapter fallback |

Do not introduce Celery, Redis, a vector database, RAG, microservices, or a multi-agent runtime unless a documented requirement and an approved design change justify it.

Preserve the repository's existing layout. The current project archive has root-level `backend/`, `frontend/`, `docs/`, `sample_data/`, and `test/` directories. Do not rename `test/` to `tests/`, relocate modules, or generate a second nested `reconai/reconai/` tree without first checking the actual repository and explaining why a change is needed.

---

## 3. Absolute Engineering Rules

### 3.1 Financial precision

- Use Python `decimal.Decimal` for all monetary calculations.
- Use PostgreSQL `NUMERIC(15,2)` for stored monetary values.
- Never use Python `float`, SQL `FLOAT`, or SQL `REAL` for currency calculations or persisted currency values.
- Serialize monetary values in API responses as decimal strings, for example `"84745.76"`.
- `AMOUNT_TOLERANCE = Decimal("1.00")` is an explicit **MVP business-rule choice**, not a universal GST rule.
- Apply the tolerance independently to `taxable_value`, `cgst`, `sgst`, `igst`, and `invoice_total`, but only when both compared values are present.
- Never convert `None` to zero. If exactly one side is missing, create `MISSING_FINANCIAL_VALUE` with field and side details. If both sides are `None`, mark that field non-comparable and do not create a mismatch for it.

### 3.2 Source provenance and corrections

- Raw `source_*` values are immutable after extraction. Never overwrite original source strings or source JSON.
- A manual correction updates only the normalized/corrected value fields through the specified correction API.
- Every correction requires the mandatory reviewer/operator note and an append-only `audit_log` event.
- Reconciliation must be rerun after a relevant normalized-field correction.
- Corrections change the current normalized-value fingerprint and invalidate prior fuzzy candidate decisions for current matching. Preserve the old candidate and decision history; do not delete it.

### 3.3 Authentication and secrets

- Use backend-only `DEMO_ACCESS_PASSWORD` to authenticate the shared hackathon demo login.
- Validate passwords using `hmac.compare_digest`.
- Use a separate backend-only `JWT_SECRET` for HMAC-SHA256 session-token signing.
- Never expose either secret to the frontend, browser storage, API responses, logs, source control, or public configuration.
- Frontend receives only the short-lived session token and stores it according to the API/build specifications (session storage for the MVP).
- All protected API requests use `Authorization: Bearer {session_token}`.
- The shared demo password identifies a demo principal only. A submitted `operator_label`/reviewer label is self-declared, not independently verified identity. Never describe it as verified user authentication.
- Do not use the old `API_KEY` authentication design or put secrets in `NEXT_PUBLIC_*` variables.

### 3.4 Determinism and transactionality

- Same source inputs, normalized values, and persistent decision state must produce the same reconciliation result.
- Use stable ordering and explicit tie-breakers; never rely on database return order.
- Reconciliation is synchronous and must run transactionally: commit a complete run or roll back the run's changes. Never expose partially persisted match/exception output as a completed run.
- Do not let an LLM choose candidates, match records, classify financial mismatches, assign severity, or change statuses.

---

## 4. Document Ingestion and Processing Rules

1. PR and GSTR-2B CSV/XLSX files are required. Supplier invoice PDFs are optional.
2. Upload requests return `202 Accepted` and a `document_id` plus a status URL.
3. Implement the documented status endpoint: `GET /sessions/{session_id}/documents/{document_id}`. The frontend polls until a terminal state and displays `status`, `error_code`, `error_message`, `processed_at`, and `records_extracted` as defined in `API_CONTRACTS.md`.
4. A failed required PR or GSTR-2B document blocks reconciliation. A failed optional invoice PDF does not block the PR-GSTR baseline.
5. FastAPI `BackgroundTasks` is best-effort for this hackathon MVP, not a durable queue. Persist state transitions. Detect stale `PROCESSING` documents and explicitly mark them failed/recovery-required; never treat an interrupted task as successful.
6. File processing is atomic. If a source file contains an explicit credit/debit-note indicator or unsupported negative document-level invoice total/taxable value, mark the entire file `FAILED` with `UNSUPPORTED_CREDIT_NOTE` and persist no extracted records from that file.
7. Do not fail a file solely because of a negative individual line item. Line-item extraction is outside the MVP.
8. Preserve invoice-level provenance, including source document, page number, and item index for multiple invoices on one PDF page.
9. Duplicate file hashes within a session return `409`. PR and GSTR-2B allow one active file per type per session; replacement requires explicit deletion as specified by the API.
10. PNG/JPG direct upload without a PDF wrapper is V2 and returns `422` in the MVP.

---

## 5. Reconciliation Engine Invariants

The order and behaviour below are mandatory. See `docs/RECONCILIATION_RULES.md` for the full algorithm.

1. Normalize records and calculate stable `source_record_key` values from file SHA-256, record type, and source row/page/item position.
2. Calculate a value-sensitive normalized fingerprint from the stable source key and current matching/financial fields.
3. Detect duplicates within each source **before exact matching**. Only group records with complete non-null duplicate keys. Missing GSTIN or invoice key is not itself a duplicate group.
4. Duplicate-excluded records receive `match_status = EXCLUDED`, are linked to one `DUPLICATE_CANDIDATE` exception through `exception_records`, and are not also classified as missing counterparts.
5. Exact matching is PR ↔ GSTR-2B on the complete key `(supplier_gstin, invoice_norm_key)`. Both values must be non-null. Never match null keys or select an arbitrary duplicate.
6. `match_results` stores confirmed PR-GSTR-2B pairs only: `EXACT` or `CONFIRMED_FUZZY`. It must not store unconfirmed proposals, one-sided missing rows, or undefined partial rows.
7. Fuzzy proposals are stored in the persistent `fuzzy_match_decisions` candidate registry. Multiple proposals may reference the same record; this is not a confirmed one-to-one assignment.
8. Fuzzy eligibility:
   - Both GSTINs present and equal: `token_sort_ratio >= 85`.
   - Exactly one GSTIN missing: score `>= 95`, invoice dates within 3 calendar days, and at least one shared comparable amount field within ₹1.00.
   - Both GSTINs missing: do not propose.
   - Different non-null GSTINs: never propose.
   - Every proposal requires a human decision.
9. Candidate lifecycle is `PROPOSED`, `CONFIRMED`, `REJECTED`, or `SUPERSEDED`. Candidate keys use stable source-position keys plus current normalized-value fingerprints, not database UUIDs alone.
10. Confirming a candidate must execute transactionally: revalidate current fingerprints and that both records are still eligible/unassigned; create one `CONFIRMED_FUZZY` `match_results` row; mark both source records `MATCHED`; and supersede competing proposals for either record. If validation fails, return a conflict and do not partially apply the decision.
11. Rejecting a candidate preserves it as `REJECTED`, appends an audit event, and leaves records available for other proposals. Do not delete rejected candidates.
12. Apply valid confirmed fuzzy decisions **before invoice evidence linking**. Do not reapply decisions if fingerprints changed or their records are no longer eligible.
13. Link optional invoice-header evidence after exact and confirmed fuzzy baseline pairs exist. Invoice files must never determine whether PR ↔ GSTR-2B reconciliation runs.
14. After exact matches and valid confirmed fuzzy decisions, classify eligible unmatched PR records as `MISSING_IN_GSTR2B` and eligible unmatched GSTR-2B records as `MISSING_IN_PR`. A record with an active `PROPOSED` candidate remains `PENDING_MATCH_REVIEW` and is not simultaneously classified as missing. After all its proposals become rejected/superseded, create the applicable missing exception if it remains unmatched.
15. Missing invoice exceptions apply only to confirmed PR-GSTR-2B pairs and only after all uploaded invoice PDFs are terminal. Use `MISSING_IN_INVOICE_NO_DOCS` if no invoice PDFs were uploaded; otherwise use `MISSING_IN_INVOICE_UNMATCHED` when no unique invoice record can be linked. While an invoice PDF is still processing, defer these exceptions; baseline reconciliation may still complete.
16. A uniquely matching invoice may support a one-sided missing-counterpart exception. Unlinked invoice records remain in source inventory; there is no separate orphan-invoice exception in MVP.
17. Reruns reset transient `match_status` values for all records from active documents before recomputation. Reapply duplicate exclusions, exact matches, valid confirmed decisions and current proposals in the defined order. Records belonging to soft-deleted documents remain excluded.
18. Generate `discrepancy_key` from canonical JSON containing the exception type and sorted stable `source_record_key` values. Generate candidate keys from canonical stable source keys plus current normalized-value fingerprints.

---

## 6. Database Rules

- The specification defines **13 PostgreSQL tables**. Use `docs/DATABASE_SCHEMA.md` as the exact schema authority:
  `clients`, `periods`, `recon_sessions`, `documents`, `extracted_records`, `match_results`, `recon_exceptions`, `exception_records`, `exception_reviews`, `fuzzy_match_decisions`, `recon_summary`, `reports`, `audit_log`.
- Use SQLAlchemy 2.0 declarative models and Alembic migrations.
- Enforce client/session/record ownership with composite foreign keys where specified and service-level ownership validation on every API operation. Never accept a record ID from another session or client.
- Keep `recon_exceptions.match_result_id` nullable. Use `exception_records` to associate one exception with all involved extracted records.
- `exception_reviews` preserves immutable `exception_snapshot` and stable `discrepancy_key`; do not erase reviews on reruns.
- Fuzzy candidate rows and audit events survive reruns. The current candidate row stores current state; `audit_log` retains every transition.
- Do not add or remove a table, field, status, enum value, or relationship without updating all affected specifications and obtaining approval.

---

## 7. Exception Review, Severity, and Audit Rules

- Fuzzy candidate decisions and exception status reviews are separate workflows and separate APIs.
- Fuzzy candidate actions: `CONFIRM_MATCH`, `REJECT_MATCH`.
- Exception review actions: `ACCEPT`, `DISPUTE`, `DEFER`, `REOPEN`.
- Exception status mapping: `ACCEPT` → `ACCEPTED`; `DISPUTE` → `DISPUTED`; `DEFER` → `DEFERRED`; `REOPEN` → `OPEN`.
- MVP has no `RESOLVED` exception state/action. Do not create one.
- Use the severity mapping in `docs/RECONCILIATION_RULES.md` exactly. Severity is a display category, not a tax-risk or ITC eligibility judgment.
- All review comments must satisfy the minimum length and validation in the API/schema specifications.
- Persist exception review snapshots and append-only audit events for corrections, document deletion, candidate transitions, review actions, report generation, and reconciliation reruns as specified.

---

## 8. AI Guardrails

AI may:

- Extract invoice-header fields from PDF text/images into the specified structured schema.
- Return multiple invoice objects per PDF with page and item provenance.
- Draft explanations grounded only in deterministic source values supplied by the backend.
- Draft a session-level narrative summary.

AI must never:

- Calculate or alter financial values.
- Perform exact/fuzzy matching or decide which candidate is correct.
- Set match, exception, severity, or review statuses.
- Determine ITC eligibility or give tax/legal advice.
- Fabricate missing fields, silently infer unreadable values, or claim a live GSTN connection.

All core reconciliation, review, and report workflows must function when Gemini is unavailable through `NullAdapter`. Treat all document text and AI output as untrusted data; validate against schemas and business rules before persistence.

---

## 9. API Conventions

- Base path: `/api/v1`.
- Public endpoints: `GET /health` and `POST /auth/session` only.
- All other endpoints require `Authorization: Bearer {session_token}`.
- Follow `docs/API_CONTRACTS.md` exactly for request fields, response schemas, status codes, pagination, and error bodies.
- Monetary values are JSON strings; IDs are UUID strings; timestamps are ISO 8601 UTC.
- Use the documented RFC 7807-style error format.
- Upload is asynchronous (`202`); reconciliation and report generation are synchronous (`200`) in the MVP.
- Document status polling, records list/detail/correction, candidate list/decision, exception list/detail/review, and report download routes are required. Do not implement only the upload/create endpoint while omitting the corresponding read/status route.
- Validate session ownership on every route, including downloads and nested resources.

---

## 10. Frontend Rules

- Keep the frontend a thin workflow client. Business rules and financial calculations belong in the backend.
- Keep the fuzzy-match workspace separate from the exception-review workspace.
- Show candidate status and explain that proposals are not matches until confirmed.
- Show source values, raw provenance, normalized values, confidence, and correction state where the API provides them.
- Poll document status using the specified status URL; show explicit processing failures and block reconciliation only for failed required sources.
- Do not display a self-declared operator label as a verified account identity.
- Do not put secrets in `NEXT_PUBLIC_*` variables or frontend source.

---

## 11. Testing and Definition of Done

Never mark a roadmap checkbox complete unless the implementation exists and its tests pass.

At minimum, add automated tests for:

- PR ↔ GSTR-2B exact baseline with no invoice PDFs.
- Exact matching with null keys (must not match) and duplicate groups (must be excluded).
- Multiple fuzzy proposals referencing one record without violating confirmed-match uniqueness.
- Confirming one proposal transactionally creates one match and supersedes overlapping proposals.
- Rejecting a proposal persists across reruns and does not block other candidates.
- Manual correction changes candidate fingerprint; old decisions remain historical and are not reapplied.
- A record with a proposed candidate is pending review, not missing; rejected/superseded-only unmatched records become missing exceptions.
- Unmatched PR and GSTR-2B produce the correct one-sided exception types exactly once.
- Duplicate-excluded records are not also marked missing.
- `None` vs zero, one missing amount, and both missing amounts follow the financial rules.
- Missing invoice exceptions are generated only for confirmed pairs after invoice processing is terminal.
- Atomic credit-note failure persists no records from the failed file.
- Required-source failure blocks reconciliation; optional invoice failure does not.
- Document polling transitions, stale processing recovery, session readiness, and status response shape.
- Cross-client/session ownership violations are rejected.
- Review snapshots, fuzzy decision history, and audit entries survive reruns.
- Exception statuses and severity mappings match the specification.
- Every API endpoint has success, validation, authorization, not-found, and conflict tests where applicable.

Run the commands already documented in the repository. At minimum, run the backend test suite (for example `pytest -q`) and relevant frontend checks if configured. Do not claim tests passed unless you actually ran them and saw a passing exit code. If tests cannot be run, state why and list the remaining verification work.

---

## 12. Git, File Safety, and Agent Handoffs

- Never delete, overwrite, or mass-format user files without first checking `git status` and reviewing the diff.
- Do not rewrite specification documents while implementing code unless explicitly asked.
- Keep changes focused and commit-sized. Do not have two coding agents edit the same files concurrently.
- Before handing work to another agent, report: current branch, changed files, tests run, test results, unresolved issues, and the next exact task.
- Do not add credentials, uploaded taxpayer files, private PDFs, or real GST data to Git.
- Keep synthetic fixtures clearly labelled as synthetic.
- Avoid destructive commands (`git reset --hard`, broad deletes, force pushes, database drops) unless the user explicitly requests them and the impact is confirmed.

---

## 13. Out of Scope for MVP

| Not in MVP | Required behaviour |
|---|---|
| Live GSTN integration / filing | Do not implement or claim it. |
| ITC eligibility or tax/legal advice | Do not calculate, recommend, or claim eligibility. |
| PNG/JPG direct uploads | Return documented `422`; PDF-wrapped images may use Gemini Vision. |
| Credit note reconciliation | Fail the entire affected source file atomically with `UNSUPPORTED_CREDIT_NOTE`. |
| Invoice line-item extraction/reconciliation | V2; MVP is invoice-header evidence only. |
| Durable task queue | FastAPI BackgroundTasks is best-effort for MVP; surface stale jobs. |
| Microservices, RAG, vector DB, multi-agent runtime | Do not add without approved scope change. |
| Automated fuzzy-match acceptance | Never; human confirmation is mandatory. |

---

## 14. Conflict Resolution

If a task request, existing code, an older README/AGENTS file, or an agent suggestion conflicts with the v1.2.1 specifications:

1. Do not silently implement the conflicting behaviour.
2. Identify the exact files/sections and explain the impact.
3. Prefer the current v1.2.1 specifications over stale v1.1/v1.2 notes and obsolete code comments, unless the user explicitly approves a specification change.
4. If the v1.2.1 documents themselves conflict, treat it as a blocker and request a decision rather than inventing one.

**The most important rule:** deterministic PR-to-GSTR-2B reconciliation and an auditable human-review workflow are the core of ReconAI. Protect those invariants above convenience or speed.
