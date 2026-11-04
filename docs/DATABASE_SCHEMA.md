# ReconAI — Database Schema Specification

> **Status:** Corrective revision — v1.2.1 (based on v1.2)
> **Date:** 2026-11-04
> **Database Engine:** PostgreSQL 15+
> **ORM:** SQLAlchemy 2.0 (Declarative Mapping)
> **Corrective revision:** 2026-11-04 — closes implementation-contract gaps found during independent review.
> **Corrective changes in v1.2.1:** Persistent fuzzy candidate registry supports many proposals per source record; current-run `match_results` contain confirmed pairs only; source fingerprints and ownership constraints are explicit.
> **Changes from v1.1:**
> - Entity Count increased to 13 distinct PostgreSQL tables.
> - Added `exception_records` association table (many-to-many between `recon_exceptions` and `extracted_records`).
> - Made `recon_exceptions.match_result_id` nullable to support non-match exceptions (e.g. `DUPLICATE_CANDIDATE`).
> - Added `fuzzy_match_decisions` table for persistent fuzzy candidate decisions surviving reruns.
> - Updated `exception_reviews`: Added `discrepancy_key` (CHAR(64)) and `exception_snapshot` (JSONB) for immutable audit preservation across reruns.
> - Removed `extracted_records.has_negative_amounts` flag (credit note invoices fail processing entirely).

---

## Entity Relationship Overview

```
clients (1)
  └── periods (2)
        └── recon_sessions (3)
              ├── documents (4)
              │     └── extracted_records (5) ──┐
              ├── match_results (6)             │
              │     └── recon_exceptions (7) ───┼──► exception_records (8) [Association]
              │           └── exception_reviews (9)
              ├── fuzzy_match_decisions (10)
              ├── recon_summary (11)
              └── reports (12)

audit_log (13) — global append-only log
```

**Total Entities:** 13

---

## Table Schemas

### 1. `clients`
```sql
CREATE TABLE clients (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    gstin           CHAR(15) NOT NULL,
    gstin_state     CHAR(2) GENERATED ALWAYS AS (SUBSTRING(gstin FROM 1 FOR 2)) STORED,
    contact_email   TEXT,
    contact_phone   TEXT,
    address         TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT clients_gstin_unique UNIQUE (gstin)
);
```

### 2. `periods`
```sql
CREATE TABLE periods (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id       UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    period_type     TEXT NOT NULL CHECK (period_type IN ('MONTHLY', 'QUARTERLY')),
    period_year     SMALLINT NOT NULL,
    period_month    SMALLINT CHECK (period_month BETWEEN 1 AND 12),
    period_quarter  SMALLINT CHECK (period_quarter BETWEEN 1 AND 4),
    label           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED', 'ARCHIVED')),
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT periods_identity_unique UNIQUE (id, client_id),
    CONSTRAINT periods_type_fields_check CHECK (
        (period_type = 'MONTHLY' AND period_month BETWEEN 1 AND 12 AND period_quarter IS NULL) OR
        (period_type = 'QUARTERLY' AND period_month IS NULL AND period_quarter BETWEEN 1 AND 4)
    )
);

CREATE UNIQUE INDEX idx_period_month_unique ON periods(client_id, period_year, period_month) WHERE period_type = 'MONTHLY';
CREATE UNIQUE INDEX idx_period_quarter_unique ON periods(client_id, period_year, period_quarter) WHERE period_type = 'QUARTERLY';
```

### 3. `recon_sessions`
```sql
CREATE TABLE recon_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id       UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    period_id       UUID NOT NULL REFERENCES periods(id) ON DELETE RESTRICT,
    name            TEXT,
    status          TEXT NOT NULL DEFAULT 'DRAFT'
                    CHECK (status IN ('DRAFT', 'PROCESSING', 'READY', 'RECONCILING', 'REVIEW', 'CLOSED', 'FAILED')),
    error_message   TEXT,
    sources_ready   JSONB NOT NULL DEFAULT '{"invoices": false, "purchase_register": false, "gstr2b": false}',
    reconciled_at   TIMESTAMPTZ,
    closed_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT sessions_identity_unique UNIQUE (id, client_id),
    CONSTRAINT sessions_period_client_fk FOREIGN KEY (period_id, client_id) REFERENCES periods(id, client_id) ON DELETE RESTRICT
);
```

### 4. `documents`
```sql
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES recon_sessions(id) ON DELETE CASCADE,
    client_id       UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    document_type   TEXT NOT NULL CHECK (document_type IN ('INVOICE', 'PURCHASE_REGISTER', 'GSTR2B')),
    original_filename TEXT NOT NULL,
    storage_path    TEXT NOT NULL,
    file_size_bytes BIGINT,
    mime_type       TEXT,
    file_hash       CHAR(64) NOT NULL,
    page_count      INTEGER,
    row_count       INTEGER,
    status          TEXT NOT NULL DEFAULT 'UPLOADED'
                    CHECK (status IN ('UPLOADED', 'PROCESSING', 'PROCESSED', 'PROCESSED_WITH_WARNINGS', 'FAILED', 'DUPLICATE', 'DELETED')),
    error_code      TEXT,
    error_message   TEXT,
    processed_at    TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT documents_identity_unique UNIQUE (id, session_id, client_id),
    CONSTRAINT documents_session_client_fk FOREIGN KEY (session_id, client_id) REFERENCES recon_sessions(id, client_id) ON DELETE CASCADE
);

CREATE INDEX idx_documents_session ON documents(session_id);
CREATE INDEX idx_documents_hash_session ON documents(session_id, file_hash);
CREATE UNIQUE INDEX idx_documents_active_required_type ON documents(session_id, document_type)
    WHERE document_type IN ('PURCHASE_REGISTER', 'GSTR2B') AND deleted_at IS NULL AND status <> 'DELETED';
CREATE UNIQUE INDEX idx_documents_active_hash ON documents(session_id, file_hash) WHERE deleted_at IS NULL;
```

### 5. `extracted_records`
```sql
CREATE TABLE extracted_records (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id             UUID NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    session_id              UUID NOT NULL REFERENCES recon_sessions(id) ON DELETE CASCADE,
    client_id               UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    record_type             TEXT NOT NULL CHECK (record_type IN ('INVOICE', 'PURCHASE_REGISTER', 'GSTR2B')),

    -- Raw provenance values
    source_row_number       INTEGER,
    source_page_number      INTEGER,
    source_item_index       INTEGER, -- 1-based invoice ordinal within a PDF page
    source_record_key       CHAR(64) NOT NULL, -- stable SHA-256 of file hash + source position + record type
    source_supplier_gstin   TEXT,
    source_invoice_number   TEXT,
    source_invoice_date     TEXT,
    source_taxable_value    TEXT,
    source_cgst             TEXT,
    source_sgst             TEXT,
    source_igst             TEXT,
    source_invoice_total    TEXT,
    source_supplier_name    TEXT,
    source_raw_json         JSONB,

    -- Normalized typed values
    supplier_gstin          CHAR(15),
    invoice_number          TEXT,
    invoice_norm_key        TEXT,
    invoice_date            DATE,
    taxable_value           NUMERIC(15,2),
    cgst                    NUMERIC(15,2),
    sgst                    NUMERIC(15,2),
    igst                    NUMERIC(15,2),
    invoice_total           NUMERIC(15,2),
    supplier_name           TEXT,

    -- Quality & corrections
    extraction_method       TEXT NOT NULL CHECK (extraction_method IN ('CSV_PARSE', 'XLSX_PARSE', 'PDF_TEXT', 'AI_VISION')),
    overall_confidence      NUMERIC(4,3),
    field_confidence        JSONB,
    is_manually_corrected   BOOLEAN NOT NULL DEFAULT FALSE,
    corrected_by            TEXT,
    corrected_at            TIMESTAMPTZ,
    correction_notes        TEXT,

    -- Matching state
    match_status            TEXT NOT NULL DEFAULT 'UNMATCHED'
                            CHECK (match_status IN ('UNMATCHED', 'MATCHED', 'PENDING_MATCH_REVIEW', 'EXCLUDED')),

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT extracted_records_source_key_unique UNIQUE (document_id, source_record_key),
    CONSTRAINT extracted_records_identity_unique UNIQUE (id, session_id, client_id),
    CONSTRAINT extracted_records_document_owner_fk FOREIGN KEY (document_id, session_id, client_id)
        REFERENCES documents(id, session_id, client_id) ON DELETE RESTRICT,
    CONSTRAINT extracted_records_session_client_fk FOREIGN KEY (session_id, client_id)
        REFERENCES recon_sessions(id, client_id) ON DELETE CASCADE
);

CREATE INDEX idx_extracted_session ON extracted_records(session_id);
CREATE INDEX idx_extracted_gstin ON extracted_records(supplier_gstin);
CREATE INDEX idx_extracted_norm_key ON extracted_records(invoice_norm_key);
```

### 6. `match_results` — confirmed current-run assignments only
```sql
CREATE TABLE match_results (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id              UUID NOT NULL REFERENCES recon_sessions(id) ON DELETE CASCADE,
    client_id               UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    invoice_record_id       UUID,
    pr_record_id            UUID NOT NULL,
    gstr2b_record_id        UUID NOT NULL,
    match_type              TEXT NOT NULL CHECK (match_type IN ('EXACT', 'CONFIRMED_FUZZY')),
    match_confidence        NUMERIC(4,3),
    match_key               TEXT,
    fuzzy_score_pr_gstr2b   NUMERIC(4,1),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT match_results_pr_record_fk FOREIGN KEY (pr_record_id, session_id, client_id)
        REFERENCES extracted_records(id, session_id, client_id) ON DELETE RESTRICT,
    CONSTRAINT match_results_gstr2b_record_fk FOREIGN KEY (gstr2b_record_id, session_id, client_id)
        REFERENCES extracted_records(id, session_id, client_id) ON DELETE RESTRICT,
    CONSTRAINT match_results_invoice_record_fk FOREIGN KEY (invoice_record_id, session_id, client_id)
        REFERENCES extracted_records(id, session_id, client_id) ON DELETE RESTRICT,
    CONSTRAINT match_results_identity_unique UNIQUE (id, session_id, client_id)
);

CREATE UNIQUE INDEX idx_match_invoice_record ON match_results(invoice_record_id) WHERE invoice_record_id IS NOT NULL;
CREATE UNIQUE INDEX idx_match_pr_record ON match_results(pr_record_id);
CREATE UNIQUE INDEX idx_match_gstr2b_record ON match_results(gstr2b_record_id);
CREATE INDEX idx_match_session ON match_results(session_id);
```

Only confirmed PR-GSTR-2B pairs are stored here. Proposed fuzzy candidates belong in `fuzzy_match_decisions`; a proposal does not consume a one-to-one match slot. Partial/missing one-sided records are represented by exceptions and `exception_records`, not fabricated match rows.

### 7. `recon_exceptions`
```sql
CREATE TABLE recon_exceptions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID NOT NULL REFERENCES recon_sessions(id) ON DELETE CASCADE,
    client_id           UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    match_result_id     UUID, -- NULLABLE for duplicate and one-sided exceptions; composite FK below
    discrepancy_key     CHAR(64) NOT NULL, -- SHA-256 hash of canonical fingerprints + type
    exception_type      TEXT NOT NULL CHECK (exception_type IN (
                            'MISSING_IN_PR',
                            'MISSING_IN_GSTR2B',
                            'MISSING_IN_INVOICE_NO_DOCS',
                            'MISSING_IN_INVOICE_UNMATCHED',
                            'TAXABLE_VALUE_MISMATCH',
                            'CGST_MISMATCH',
                            'SGST_MISMATCH',
                            'IGST_MISMATCH',
                            'INVOICE_TOTAL_MISMATCH',
                            'DUPLICATE_CANDIDATE',
                            'MISSING_FINANCIAL_VALUE',
                            'DATE_MISMATCH',
                            'SUPPLIER_NAME_MISMATCH'
                        )),
    severity            TEXT NOT NULL CHECK (severity IN ('HIGH', 'MEDIUM', 'LOW')),
    value_difference    NUMERIC(15,2),
    details             JSONB NOT NULL DEFAULT '{}', -- field names, missing-side markers, candidate/source context
    ai_explanation      TEXT,
    ai_explanation_at   TIMESTAMPTZ,
    status              TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'ACCEPTED', 'DISPUTED', 'DEFERRED')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE recon_exceptions ADD CONSTRAINT recon_exceptions_identity_unique UNIQUE (id, session_id, client_id);
ALTER TABLE recon_exceptions ADD CONSTRAINT recon_exceptions_match_result_fk
    FOREIGN KEY (match_result_id, session_id, client_id)
    REFERENCES match_results(id, session_id, client_id) ON DELETE CASCADE;

CREATE INDEX idx_exceptions_session ON recon_exceptions(session_id);
CREATE INDEX idx_exceptions_discrepancy_key ON recon_exceptions(discrepancy_key);
```

### 8. `exception_records` (Association Table)
```sql
CREATE TABLE exception_records (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exception_id        UUID NOT NULL,
    extracted_record_id UUID NOT NULL,
    session_id          UUID NOT NULL REFERENCES recon_sessions(id) ON DELETE CASCADE,
    client_id           UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    record_role         TEXT NOT NULL CHECK (record_role IN ('PRIMARY', 'DUPLICATE_CANDIDATE', 'COUNTERPART', 'SUPPORTING_INVOICE')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT exception_records_exception_fk FOREIGN KEY (exception_id, session_id, client_id)
        REFERENCES recon_exceptions(id, session_id, client_id) ON DELETE CASCADE,
    CONSTRAINT exception_records_record_fk FOREIGN KEY (extracted_record_id, session_id, client_id)
        REFERENCES extracted_records(id, session_id, client_id) ON DELETE RESTRICT,
    CONSTRAINT exception_records_unique UNIQUE (exception_id, extracted_record_id)
);

CREATE INDEX idx_exception_records_exception ON exception_records(exception_id);
CREATE INDEX idx_exception_records_record ON exception_records(extracted_record_id);
```

### 9. `exception_reviews`
```sql
CREATE TABLE exception_reviews (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exception_id        UUID,
    session_id          UUID NOT NULL,
    client_id           UUID NOT NULL,
    discrepancy_key     CHAR(64) NOT NULL,
    exception_snapshot  JSONB NOT NULL, -- Full immutable snapshot of exception & source values
    action              TEXT NOT NULL CHECK (action IN ('ACCEPT', 'DISPUTE', 'DEFER', 'REOPEN')),
    comment             TEXT NOT NULL CHECK (length(comment) >= 10),
    reviewer            TEXT NOT NULL, -- self-declared operator label under shared demo auth
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT reviews_session_client_fk FOREIGN KEY (session_id, client_id)
        REFERENCES recon_sessions(id, client_id) ON DELETE CASCADE,
    CONSTRAINT reviews_exception_owner_fk FOREIGN KEY (exception_id, session_id, client_id)
        REFERENCES recon_exceptions(id, session_id, client_id) ON DELETE SET NULL (exception_id)
);

CREATE INDEX idx_reviews_exception ON exception_reviews(exception_id);
CREATE INDEX idx_reviews_discrepancy_key ON exception_reviews(discrepancy_key);
```

### 10. `fuzzy_match_decisions` — persistent candidate registry and decision state

This table stores candidate proposals as well as their current decision state. Multiple rows may reference the same PR or GSTR-2B record. It is intentionally separate from `match_results`.

```sql
CREATE TABLE fuzzy_match_decisions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id              UUID NOT NULL REFERENCES recon_sessions(id) ON DELETE CASCADE,
    client_id               UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    pr_record_id            UUID NOT NULL,
    gstr2b_record_id        UUID NOT NULL,
    pr_value_fingerprint    CHAR(64) NOT NULL,
    gstr2b_value_fingerprint CHAR(64) NOT NULL,
    candidate_key_hash      CHAR(64) NOT NULL,
    similarity_score       NUMERIC(4,1) NOT NULL CHECK (similarity_score BETWEEN 0 AND 100),
    candidate_status       TEXT NOT NULL DEFAULT 'PROPOSED'
                            CHECK (candidate_status IN ('PROPOSED', 'CONFIRMED', 'REJECTED', 'SUPERSEDED')),
    decision_comment       TEXT,
    decided_by             TEXT, -- self-declared operator label under shared demo auth
    decided_at             TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fuzzy_candidate_pr_fk FOREIGN KEY (pr_record_id, session_id, client_id)
        REFERENCES extracted_records(id, session_id, client_id) ON DELETE RESTRICT,
    CONSTRAINT fuzzy_candidate_gstr2b_fk FOREIGN KEY (gstr2b_record_id, session_id, client_id)
        REFERENCES extracted_records(id, session_id, client_id) ON DELETE RESTRICT,
    CONSTRAINT fuzzy_decisions_candidate_unique UNIQUE (session_id, candidate_key_hash)
);

CREATE INDEX idx_fuzzy_decisions_session ON fuzzy_match_decisions(session_id);
CREATE INDEX idx_fuzzy_decisions_pr ON fuzzy_match_decisions(pr_record_id);
CREATE INDEX idx_fuzzy_decisions_gstr2b ON fuzzy_match_decisions(gstr2b_record_id);
CREATE INDEX idx_fuzzy_decisions_status ON fuzzy_match_decisions(session_id, candidate_status);
```

`candidate_key_hash` uses stable source-record keys plus current normalized-value fingerprints, not database UUIDs alone. Candidate rows survive reruns. On identical file re-upload after soft deletion, the row may be rebound to new extracted-record UUIDs only when stable source keys and value fingerprints match exactly; the rebind must be appended to `audit_log`. Every transition to `CONFIRMED`, `REJECTED`, or `SUPERSEDED` must also append an event to `audit_log`; the current row stores current state, while `audit_log` preserves the transition history. A manual correction changes the value fingerprint and causes a new candidate hash; prior rows remain historical and are not applied to the corrected values.

### 11. `recon_summary`
```sql
CREATE TABLE recon_summary (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                  UUID NOT NULL REFERENCES recon_sessions(id) ON DELETE CASCADE,
    client_id                   UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    total_invoice_records       INTEGER NOT NULL DEFAULT 0,
    total_pr_records            INTEGER NOT NULL DEFAULT 0,
    total_gstr2b_records        INTEGER NOT NULL DEFAULT 0,
    exact_matches               INTEGER NOT NULL DEFAULT 0,
    confirmed_fuzzy_matches     INTEGER NOT NULL DEFAULT 0,
    proposed_fuzzy_candidates   INTEGER NOT NULL DEFAULT 0,
    rejected_fuzzy_candidates   INTEGER NOT NULL DEFAULT 0,
    unmatched_pr                INTEGER NOT NULL DEFAULT 0,
    unmatched_gstr2b            INTEGER NOT NULL DEFAULT 0,
    missing_invoice_pairs       INTEGER NOT NULL DEFAULT 0,
    total_exceptions            INTEGER NOT NULL DEFAULT 0,
    exceptions_by_type          JSONB NOT NULL DEFAULT '{}',
    total_value_difference      NUMERIC(15,2) NOT NULL DEFAULT 0.00,
    highest_value_exception     NUMERIC(15,2) NOT NULL DEFAULT 0.00,
    ai_summary                  TEXT,
    ai_summary_at               TIMESTAMPTZ,
    computed_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT summary_session_client_fk FOREIGN KEY (session_id, client_id)
        REFERENCES recon_sessions(id, client_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX idx_summary_session ON recon_summary(session_id);
```

### 12. `reports`
```sql
CREATE TABLE reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES recon_sessions(id) ON DELETE CASCADE,
    client_id       UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    report_type     TEXT NOT NULL CHECK (report_type IN ('EXCEPTION_XLSX', 'SUMMARY_PDF', 'AUDIT_XLSX')),
    storage_path    TEXT NOT NULL,
    file_size_bytes BIGINT,
    filters_applied JSONB,
    status          TEXT NOT NULL DEFAULT 'READY' CHECK (status IN ('READY', 'FAILED')),
    error_message   TEXT,
    generated_by    TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT reports_session_client_fk FOREIGN KEY (session_id, client_id)
        REFERENCES recon_sessions(id, client_id) ON DELETE CASCADE
);

CREATE INDEX idx_reports_session ON reports(session_id);
```


### Cross-table ownership and lifecycle constraints

The composite foreign keys defined above are normative: `periods`, `recon_sessions`, `documents`, `extracted_records`, `match_results`, `recon_exceptions`, `exception_records`, and `fuzzy_match_decisions` must never connect rows from different clients or sessions. Add matching composite unique keys to parent tables where referenced. Apply equivalent `(session_id, client_id)` ownership validation to `reports`, `recon_summary`, and `exception_reviews`. `exception_reviews` must reference exceptions only within the same session and client; because the live exception may be deleted during a rerun, the review's `session_id`, `discrepancy_key`, and immutable `exception_snapshot` remain authoritative after `exception_id` becomes NULL. Service-layer checks are required in addition to database constraints for nullable review references and audit events.

`recon_sessions.period_id` must belong to the same `client_id` as the session. `documents.session_id` and `extracted_records.document_id` must belong to the same session and client as their rows. The application must soft-delete source documents and mark their extracted records `EXCLUDED`; it must not physically cascade-delete source records referenced by audit history or fuzzy decisions. The application database role must not be granted UPDATE/DELETE permission on `audit_log`; append-only behaviour must be enforced by database permissions, not convention alone.

### 13. `audit_log`
```sql
CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    event_type      TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    entity_id       UUID,
    session_id      UUID,
    client_id       UUID,
    actor           TEXT NOT NULL,
    before_state    JSONB,
    after_state     JSONB,
    metadata        JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT audit_session_client_pair_check CHECK ((session_id IS NULL) = (client_id IS NULL)),
    CONSTRAINT audit_session_client_fk FOREIGN KEY (session_id, client_id)
        REFERENCES recon_sessions(id, client_id) ON DELETE RESTRICT
);

CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_session ON audit_log(session_id);
```
