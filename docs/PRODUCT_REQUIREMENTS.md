# ReconAI — Product Requirements Document

> **Status:** Corrective revision — v1.2.1 (based on v1.2)
> **Date:** 2026-11-04
> **Authority:** Governing Product Requirements for ReconAI MVP.
> **Corrective revision:** 2026-11-04 — closes implementation-contract gaps found during independent review.
> **Changes from v1.1:**
> - Clarified baseline reconciliation scope: Core reconciliation operates deterministically between Purchase Register and GSTR-2B; supplier invoice PDFs serve as optional supporting evidence.
> - Split missing invoice exceptions into `MISSING_IN_INVOICE_NO_DOCS` (no invoice files uploaded) and `MISSING_IN_INVOICE_UNMATCHED` (invoices uploaded but no match found).
> - Updated credit note policy: Async document processing explicitly fails (`status = FAILED`) if an invoice contains negative total financial amounts or explicit credit-note indicators. Negative amounts are never converted to positive values.
> - Decoupled exception review actions (`ACCEPT`, `DISPUTE`, `DEFER`, `REOPEN`) from fuzzy match decisions (`CONFIRM_MATCH`, `REJECT_MATCH`).
> - Mandated support for extracting multiple invoices per PDF while preserving individual page provenance.

---

## 1. Product Objectives

ReconAI provides Chartered Accountant (CA) firms, GST practitioners, and SME finance teams with a structured, auditable workflow for comparing up to three financial data sources:

1. **Purchase Register (PR):** Buyer's internal accounting record of received invoices. (Required)
2. **GSTR-2B Statement:** Government-generated auto-drafted Input Tax Credit (ITC) statement. (Required)
3. **Supplier Invoices:** Physical or digital invoice documents (PDF) providing invoice-header supporting evidence. (Optional; line-item extraction is V2)

The platform normalizes data, executes deterministic Purchase Register (PR) to GSTR-2B reconciliation, links optional supplier-invoice header evidence, flags tax and financial discrepancies, presents grounded AI explanations, and maintains an append-only audit log of reviewer actions. MVP invoice evidence is invoice-header-level only; line-item extraction and line-item reconciliation are deferred to V2.

ReconAI does **not** replace professional accounting judgment or calculate tax eligibility. It surfaces discrepancies and evidence so accountants can resolve exceptions efficiently.

---

## 2. Target Users

| Persona | Primary Need |
|---|---|
| **CA Firm Partner** | Client portfolio oversight, high-level discrepancy summaries, and audit trail compliance |
| **CA Staff Accountant** | Daily operational workflow: upload files, correct low-confidence fields, review exceptions, confirm/reject fuzzy candidates |
| **GST Practitioner** | Single-client focus, quick upload-to-report reconciliation loops |
| **SME Finance Manager** | Internal pre-filing checks and evidence package preparation for external auditors |

---

## 3. Core User Journeys

### 3.1 Monthly Reconciliation Journey

```
Accountant authenticates via demo access password
       ↓
Selects or creates Client & Financial Period (e.g., Acme Ltd, Oct 2026)
       ↓
Creates Reconciliation Session
       ↓
Uploads Source Documents:
  · Purchase Register (CSV/XLSX)            [REQUIRED]
  · GSTR-2B Statement (CSV/XLSX)            [REQUIRED]
  · Supplier Invoices (PDF batch)           [OPTIONAL]
       ↓
System extracts and normalizes records (Async Background Job):
  · Tabular parsing for PR and GSTR-2B
  · Text parsing / AI Vision for PDF invoices (supports multiple invoices per PDF)
  · Credit notes / negative totals flagged as FAILED documents
       ↓
Accountant triggers deterministic Reconciliation Engine (Synchronous):
  · Core PR ↔ GSTR-2B baseline match executes independently of invoices
  · Invoices linked to confirmed PR-GSTR-2B pairs or included as supporting evidence on one-sided missing-counterpart exceptions
  · Persistent fuzzy decisions applied; rejected fuzzy candidates skipped
       ↓
Accountant reviews output in Workspace:
  · Confirms/Rejects fuzzy match candidates (`CONFIRM_MATCH` / `REJECT_MATCH`)
  · Evaluates financial exceptions (`ACCEPT`, `DISPUTE`, `DEFER`, `REOPEN`)
       ↓
Accountant generates synchronous audit & summary reports (XLSX, PDF)
```

### 3.2 Field Correction Journey

```
Accountant views extracted record with low confidence indicator (< 0.70)
       ↓
Inspects original source value and source page/row reference
       ↓
Edits field value manually (supplies mandatory reviewer notes)
       ↓
System persists corrected value, preserving original raw source string
       ↓
Accountant re-runs reconciliation session; prior exception review snapshots remain intact
```

---

## 4. Functional Requirements

### 4.1 Document Intelligence

| ID | Requirement | Priority |
|---|---|---|
| DI-01 | Accept CSV and XLSX uploads for Purchase Register and GSTR-2B. | MVP |
| DI-02 | Accept multi-page PDF uploads for supplier invoices (text-layer and image-based PDFs). | MVP |
| DI-03 | Extract multi-invoice PDFs into distinct invoice-level records, preserving `source_page_number` and `source_item_index` per invoice. If any invoice in the PDF is identified as an unsupported credit note, fail the entire PDF atomically; do not persist a partial subset from that file. | MVP |
| DI-04 | Use PyMuPDF for text PDF parsing; fall back to Gemini Vision for image PDFs or confidence < 0.70. | MVP |
| DI-05 | Store per-field confidence scores (0.000–1.000) for all extracted invoice-header fields. | MVP |
| DI-06 | Treat each uploaded source file atomically: if a supplier-invoice PDF contains an explicit credit-note indicator or any extracted invoice has a negative document-level `invoice_total` or `taxable_value`, fail the entire PDF (`FAILED`, `UNSUPPORTED_CREDIT_NOTE`). For PR/GSTR-2B tabular files, fail the entire file if a row is explicitly identified as a credit/debit note or has a negative document-level invoice total/taxable value. Do not reject a negative individual line item solely on that basis; line-item extraction is out of MVP. | MVP |
| DI-07 | Preserve raw source values verbatim alongside normalized, typed values. | MVP |
| DI-08 | Prevent duplicate file uploads within a session using SHA-256 file hashing (returns 409 Conflict). | MVP |
| DI-09 | Restrict Purchase Register and GSTR-2B uploads to one active file per type per session. Allow explicit document deletion (`DELETE`) to enable replacement. | MVP |
| DI-10 | Direct PNG/JPG image uploads without PDF wrappers are deferred to V2 (returns 422 Unprocessable Entity). | V2 |

### 4.2 Reconciliation Engine

| ID | Requirement | Priority |
|---|---|---|
| RE-01 | Baseline reconciliation executes deterministically between PR and GSTR-2B records regardless of invoice presence. | MVP |
| RE-02 | Normalize GSTINs (uppercase, strip spaces, validate 15-char format), dates (ISO 8601), invoice numbers (`invoice_norm_key` stripping separators), and amounts (Python `Decimal` quantized to 2 decimal places). | MVP |
| RE-03 | Execute exact primary key matching on `(normalized_supplier_gstin, invoice_norm_key)`. | MVP |
| RE-04 | Generate PR-GSTR-2B fuzzy candidate proposals using `token_sort_ratio`. If both GSTINs are present they must be identical and score ≥ 85. If exactly one GSTIN is missing, require score ≥ 95 plus corroborating evidence: invoice dates within 3 calendar days and at least one comparable amount field within ₹1.00. If both GSTINs are missing or both non-null GSTINs differ, do not generate a candidate. Every proposal requires human confirmation. | MVP |
| RE-05 | Enforce one-to-one assignment only for confirmed PR-GSTR-2B pairs and linked invoice evidence. Multiple fuzzy proposals may reference the same record in the candidate registry; no proposal is a match until a reviewer confirms it. | MVP |
| RE-06 | Evaluate financial discrepancies against fixed `AMOUNT_TOLERANCE = Decimal("1.00")`. | MVP |
| RE-07 | Flag duplicate records within a source in Phase 2 duplicate detection, exclude them from matching, and generate `DUPLICATE_CANDIDATE` exceptions associated with all involved records. | MVP |
| RE-08 | For successfully matched PR-GSTR-2B pairs only, generate `MISSING_IN_INVOICE_NO_DOCS` when no invoice PDF was uploaded, or `MISSING_IN_INVOICE_UNMATCHED` when one or more invoice PDFs were uploaded but no unique invoice record could be linked to that pair. Defer these exceptions while any uploaded invoice PDF is still processing; this does not block the PR-GSTR baseline. | MVP |
| RE-09 | Persist fuzzy candidate states (`PROPOSED`, `CONFIRMED`, `REJECTED`, `SUPERSEDED`) across reruns. Reapply confirmed candidates only when their source-record fingerprints and current normalized values are unchanged; never regenerate an unchanged rejected candidate. A changed source/corrected value creates a new candidate key while retaining prior decisions for audit. | MVP |
| RE-10 | Create `MISSING_IN_GSTR2B` for each eligible unmatched PR record and `MISSING_IN_PR` for each eligible unmatched GSTR-2B record after exact matching and confirmed fuzzy decisions. Duplicate-excluded records are not also classified as missing. | MVP |
| RE-11 | Compare a financial field only when both source values are present. If one is present and the other is `NULL`, create `MISSING_FINANCIAL_VALUE`; if both are `NULL`, mark the field non-comparable and do not substitute zero. | MVP |

### 4.3 AI Intelligence & Guidance

| ID | Requirement | Priority |
|---|---|---|
| AI-01 | Generate advisory discrepancy explanations grounded strictly in source values provided by the reconciliation engine. | MVP |
| AI-02 | Generate high-level narrative summaries for reconciliation sessions. | MVP |
| AI-03 | Ensure all engine operations, reviews, matching, and report generation function fully when AI services are unavailable (`NullAdapter` fallback). | MVP |
| AI-04 | Prohibit AI models from calculating financial totals, determining tax eligibility, or setting reconciliation match statuses. | MVP |

### 4.4 Accountant Workspace & Review Workflow

| ID | Requirement | Priority |
|---|---|---|
| AW-01 | Manage Clients, Financial Periods, and Reconciliation Sessions. | MVP |
| AW-02 | Provide dedicated workflow APIs for fuzzy candidate decisions (`CONFIRM_MATCH`, `REJECT_MATCH`). | MVP |
| AW-03 | Provide dedicated workflow APIs for exception status reviews (`ACCEPT`, `DISPUTE`, `DEFER`, `REOPEN`) requiring a comment (minimum 10 characters). | MVP |
| AW-04 | Maintain immutable review records capturing complete exception snapshots (`exception_snapshot`) and deterministic SHA-256 `discrepancy_key` links across reruns. | MVP |
| AW-05 | Display reviewer/operator labels as self-declared attribution under shared demo authentication; do not represent them as independently authenticated identities. | MVP |
| AW-06 | Expose document processing status and session readiness so the frontend can poll asynchronous work and distinguish required-source failures from optional invoice failures. | MVP |
| AW-07 | Provide extracted-record listing, detail, and manual field-correction APIs; corrections preserve raw values, require notes, change current-value fingerprints, and require reconciliation rerun. | MVP |

### 4.5 Reporting

| ID | Requirement | Priority |
|---|---|---|
| RP-01 | Generate synchronous XLSX Exception Reports containing source evidence, normalized values, and review state. | MVP |
| RP-02 | Generate synchronous PDF Reconciliation Summaries containing statistical breakdown and AI summary narrative (if available). | MVP |
| RP-03 | Generate synchronous XLSX Audit Trail Reports capturing all reviewer actions, manual corrections, fuzzy decisions, and historical review snapshots. | MVP |

---

## 5. Non-Functional & Boundary Requirements

1. **Financial Precision:** All monetary amounts must be handled as Python `Decimal` and PostgreSQL `NUMERIC(15,2)`. Floating-point arithmetic is strictly forbidden in financial calculations.
2. **Determinism:** Reconciliation matching rules must produce identical output given identical input records and persistent decision states.
3. **Auditability & Immutability:** Review decisions, fuzzy-candidate state transitions, manual field corrections, document processing outcomes, and document deletions write append-only records to `audit_log`; exception reviews also retain immutable exception snapshots.
4. **Identity Boundary:** The MVP shared password identifies a demo session, not an individual person. `operator_label` values are self-reported labels for audit readability only.
5. **Legal Disclaimer:** Every generated report must display the explicit legal disclaimer: *"ReconAI is a reconciliation aid, not a GST filing, amendment, or legal tax advice."*

## 6. MVP Classification Rules (Normative)

- A baseline match is a confirmed PR-GSTR-2B pair. Supplier invoices never gate the baseline.
- `MISSING_IN_GSTR2B` and `MISSING_IN_PR` are generated only after exact matching and application of unchanged, previously confirmed fuzzy decisions. Records excluded as within-source duplicates are not also marked missing.
- Fuzzy proposals are not `match_results`. A proposal enters `match_results` only after `CONFIRM_MATCH`; rejected proposals remain in the persistent candidate registry.
- Invoice evidence is linked by exact, complete `(supplier_gstin, invoice_norm_key)` key to a confirmed PR-GSTR-2B pair. A uniquely matching invoice may also be attached as supporting evidence to a one-sided missing-counterpart exception. Unlinked invoice records remain visible in source inventory; they do not create a new exception type in MVP.
- `MISSING_IN_INVOICE_NO_DOCS` and `MISSING_IN_INVOICE_UNMATCHED` apply only to confirmed PR-GSTR-2B pairs.
- MVP compares financial values between PR and GSTR-2B. Supplier invoice totals are displayed as supporting evidence but do not independently determine match status or tax eligibility.
- Invoice line items and line-item matching are V2.
