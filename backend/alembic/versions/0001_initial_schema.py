"""Initial 13-table schema for ReconAI v1.2.1

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-04 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. clients
    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("gstin", sa.String(length=15), nullable=False),
        sa.Column("gstin_state", sa.String(length=2), nullable=True),
        sa.Column("contact_email", sa.Text(), nullable=True),
        sa.Column("contact_phone", sa.Text(), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gstin", name="clients_gstin_unique"),
    )

    # 2. periods
    op.create_table(
        "periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_type", sa.Text(), nullable=False),
        sa.Column("period_year", sa.SmallInteger(), nullable=False),
        sa.Column("period_month", sa.SmallInteger(), nullable=True),
        sa.Column("period_quarter", sa.SmallInteger(), nullable=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="OPEN", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "client_id", name="periods_identity_unique"),
        sa.CheckConstraint("period_type IN ('MONTHLY', 'QUARTERLY')", name="check_period_type"),
        sa.CheckConstraint("status IN ('OPEN', 'CLOSED', 'ARCHIVED')", name="check_period_status"),
        sa.CheckConstraint(
            "(period_type = 'MONTHLY' AND period_month BETWEEN 1 AND 12 AND period_quarter IS NULL) OR "
            "(period_type = 'QUARTERLY' AND period_month IS NULL AND period_quarter BETWEEN 1 AND 4)",
            name="periods_type_fields_check",
        ),
    )
    op.create_index(
        "idx_period_month_unique",
        "periods",
        ["client_id", "period_year", "period_month"],
        unique=True,
        postgresql_where=sa.text("period_type = 'MONTHLY'"),
    )
    op.create_index(
        "idx_period_quarter_unique",
        "periods",
        ["client_id", "period_year", "period_quarter"],
        unique=True,
        postgresql_where=sa.text("period_type = 'QUARTERLY'"),
    )

    # 3. recon_sessions
    op.create_table(
        "recon_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="DRAFT", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "sources_ready",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text('\'{"invoices": false, "purchase_register": false, "gstr2b": false}\''),
            nullable=False,
        ),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["period_id", "client_id"], ["periods.id", "periods.client_id"], name="sessions_period_client_fk", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "client_id", name="sessions_identity_unique"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PROCESSING', 'READY', 'RECONCILING', 'REVIEW', 'CLOSED', 'FAILED')",
            name="check_session_status",
        ),
    )

    # 4. documents
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_type", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), server_default="UPLOADED", nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id", "client_id"], ["recon_sessions.id", "recon_sessions.client_id"], name="documents_session_client_fk", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "session_id", "client_id", name="documents_identity_unique"),
        sa.CheckConstraint("document_type IN ('INVOICE', 'PURCHASE_REGISTER', 'GSTR2B')", name="check_document_type"),
        sa.CheckConstraint("status IN ('UPLOADED', 'PROCESSING', 'PROCESSED', 'PROCESSED_WITH_WARNINGS', 'FAILED', 'DUPLICATE', 'DELETED')", name="check_document_status"),
    )
    op.create_index("idx_documents_session", "documents", ["session_id"])
    op.create_index("idx_documents_hash_session", "documents", ["session_id", "file_hash"])
    op.create_index(
        "idx_documents_active_required_type",
        "documents",
        ["session_id", "document_type"],
        unique=True,
        postgresql_where=sa.text("document_type IN ('PURCHASE_REGISTER', 'GSTR2B') AND deleted_at IS NULL AND status <> 'DELETED'"),
    )
    op.create_index(
        "idx_documents_active_hash",
        "documents",
        ["session_id", "file_hash"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # 5. extracted_records
    op.create_table(
        "extracted_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_type", sa.Text(), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=True),
        sa.Column("source_page_number", sa.Integer(), nullable=True),
        sa.Column("source_item_index", sa.Integer(), nullable=True),
        sa.Column("source_record_key", sa.String(length=64), nullable=False),
        sa.Column("source_supplier_gstin", sa.Text(), nullable=True),
        sa.Column("source_invoice_number", sa.Text(), nullable=True),
        sa.Column("source_invoice_date", sa.Text(), nullable=True),
        sa.Column("source_taxable_value", sa.Text(), nullable=True),
        sa.Column("source_cgst", sa.Text(), nullable=True),
        sa.Column("source_sgst", sa.Text(), nullable=True),
        sa.Column("source_igst", sa.Text(), nullable=True),
        sa.Column("source_invoice_total", sa.Text(), nullable=True),
        sa.Column("source_supplier_name", sa.Text(), nullable=True),
        sa.Column("source_raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("supplier_gstin", sa.String(length=15), nullable=True),
        sa.Column("invoice_number", sa.Text(), nullable=True),
        sa.Column("invoice_norm_key", sa.Text(), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("taxable_value", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("cgst", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("sgst", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("igst", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("invoice_total", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("supplier_name", sa.Text(), nullable=True),
        sa.Column("extraction_method", sa.Text(), nullable=False),
        sa.Column("overall_confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("field_confidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_manually_corrected", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("corrected_by", sa.Text(), nullable=True),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correction_notes", sa.Text(), nullable=True),
        sa.Column("match_status", sa.Text(), server_default="UNMATCHED", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id", "session_id", "client_id"],
            ["documents.id", "documents.session_id", "documents.client_id"],
            name="extracted_records_document_owner_fk",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "client_id"],
            ["recon_sessions.id", "recon_sessions.client_id"],
            name="extracted_records_session_client_fk",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "source_record_key", name="extracted_records_source_key_unique"),
        sa.UniqueConstraint("id", "session_id", "client_id", name="extracted_records_identity_unique"),
        sa.CheckConstraint("record_type IN ('INVOICE', 'PURCHASE_REGISTER', 'GSTR2B')", name="check_record_type"),
        sa.CheckConstraint("extraction_method IN ('CSV_PARSE', 'XLSX_PARSE', 'PDF_TEXT', 'AI_VISION')", name="check_extraction_method"),
        sa.CheckConstraint("match_status IN ('UNMATCHED', 'MATCHED', 'PENDING_MATCH_REVIEW', 'EXCLUDED')", name="check_match_status"),
    )
    op.create_index("idx_extracted_session", "extracted_records", ["session_id"])
    op.create_index("idx_extracted_gstin", "extracted_records", ["supplier_gstin"])
    op.create_index("idx_extracted_norm_key", "extracted_records", ["invoice_norm_key"])

    # 6. match_results
    op.create_table(
        "match_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pr_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gstr2b_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_type", sa.Text(), nullable=False),
        sa.Column("match_confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("match_key", sa.Text(), nullable=True),
        sa.Column("fuzzy_score_pr_gstr2b", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["pr_record_id", "session_id", "client_id"],
            ["extracted_records.id", "extracted_records.session_id", "extracted_records.client_id"],
            name="match_results_pr_record_fk",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["gstr2b_record_id", "session_id", "client_id"],
            ["extracted_records.id", "extracted_records.session_id", "extracted_records.client_id"],
            name="match_results_gstr2b_record_fk",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invoice_record_id", "session_id", "client_id"],
            ["extracted_records.id", "extracted_records.session_id", "extracted_records.client_id"],
            name="match_results_invoice_record_fk",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "session_id", "client_id", name="match_results_identity_unique"),
        sa.CheckConstraint("match_type IN ('EXACT', 'CONFIRMED_FUZZY')", name="check_match_type"),
    )
    op.create_index("idx_match_pr_record", "match_results", ["pr_record_id"], unique=True)
    op.create_index("idx_match_gstr2b_record", "match_results", ["gstr2b_record_id"], unique=True)
    op.create_index(
        "idx_match_invoice_record",
        "match_results",
        ["invoice_record_id"],
        unique=True,
        postgresql_where=sa.text("invoice_record_id IS NOT NULL"),
    )
    op.create_index("idx_match_session", "match_results", ["session_id"])

    # 7. recon_exceptions
    op.create_table(
        "recon_exceptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_result_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("discrepancy_key", sa.String(length=64), nullable=False),
        sa.Column("exception_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("value_difference", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("ai_explanation", sa.Text(), nullable=True),
        sa.Column("ai_explanation_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), server_default="OPEN", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["match_result_id", "session_id", "client_id"],
            ["match_results.id", "match_results.session_id", "match_results.client_id"],
            name="recon_exceptions_match_result_fk",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "session_id", "client_id", name="recon_exceptions_identity_unique"),
        sa.CheckConstraint(
            "exception_type IN ("
            "'MISSING_IN_PR', 'MISSING_IN_GSTR2B', 'MISSING_IN_INVOICE_NO_DOCS', 'MISSING_IN_INVOICE_UNMATCHED', "
            "'TAXABLE_VALUE_MISMATCH', 'CGST_MISMATCH', 'SGST_MISMATCH', 'IGST_MISMATCH', 'INVOICE_TOTAL_MISMATCH', "
            "'DUPLICATE_CANDIDATE', 'MISSING_FINANCIAL_VALUE', 'DATE_MISMATCH', 'SUPPLIER_NAME_MISMATCH')",
            name="check_exception_type",
        ),
        sa.CheckConstraint("severity IN ('HIGH', 'MEDIUM', 'LOW')", name="check_exception_severity"),
        sa.CheckConstraint("status IN ('OPEN', 'ACCEPTED', 'DISPUTED', 'DEFERRED')", name="check_exception_status"),
    )
    op.create_index("idx_exceptions_session", "recon_exceptions", ["session_id"])
    op.create_index("idx_exceptions_discrepancy_key", "recon_exceptions", ["discrepancy_key"])

    # 8. exception_records
    op.create_table(
        "exception_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("exception_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("extracted_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_role", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["exception_id", "session_id", "client_id"],
            ["recon_exceptions.id", "recon_exceptions.session_id", "recon_exceptions.client_id"],
            name="exception_records_exception_fk",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["extracted_record_id", "session_id", "client_id"],
            ["extracted_records.id", "extracted_records.session_id", "extracted_records.client_id"],
            name="exception_records_record_fk",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exception_id", "extracted_record_id", name="exception_records_unique"),
        sa.CheckConstraint("record_role IN ('PRIMARY', 'DUPLICATE_CANDIDATE', 'COUNTERPART', 'SUPPORTING_INVOICE')", name="check_record_role"),
    )
    op.create_index("idx_exception_records_exception", "exception_records", ["exception_id"])
    op.create_index("idx_exception_records_record", "exception_records", ["extracted_record_id"])

    # 9. exception_reviews
    op.create_table(
        "exception_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("exception_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("discrepancy_key", sa.String(length=64), nullable=False),
        sa.Column("exception_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("reviewer", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id", "client_id"],
            ["recon_sessions.id", "recon_sessions.client_id"],
            name="reviews_session_client_fk",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["exception_id", "session_id", "client_id"],
            ["recon_exceptions.id", "recon_exceptions.session_id", "recon_exceptions.client_id"],
            name="reviews_exception_owner_fk",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("action IN ('ACCEPT', 'DISPUTE', 'DEFER', 'REOPEN')", name="check_review_action"),
        sa.CheckConstraint("length(comment) >= 10", name="check_review_comment_length"),
    )
    op.create_index("idx_reviews_exception", "exception_reviews", ["exception_id"])
    op.create_index("idx_reviews_discrepancy_key", "exception_reviews", ["discrepancy_key"])

    # 10. fuzzy_match_decisions
    op.create_table(
        "fuzzy_match_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pr_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gstr2b_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pr_value_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("gstr2b_value_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("candidate_key_hash", sa.String(length=64), nullable=False),
        sa.Column("similarity_score", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("candidate_status", sa.Text(), server_default="PROPOSED", nullable=False),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["pr_record_id", "session_id", "client_id"],
            ["extracted_records.id", "extracted_records.session_id", "extracted_records.client_id"],
            name="fuzzy_candidate_pr_fk",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["gstr2b_record_id", "session_id", "client_id"],
            ["extracted_records.id", "extracted_records.session_id", "extracted_records.client_id"],
            name="fuzzy_candidate_gstr2b_fk",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "candidate_key_hash", name="fuzzy_decisions_candidate_unique"),
        sa.CheckConstraint("similarity_score BETWEEN 0 AND 100", name="check_fuzzy_similarity_score"),
        sa.CheckConstraint("candidate_status IN ('PROPOSED', 'CONFIRMED', 'REJECTED', 'SUPERSEDED')", name="check_candidate_status"),
    )
    op.create_index("idx_fuzzy_decisions_session", "fuzzy_match_decisions", ["session_id"])
    op.create_index("idx_fuzzy_decisions_pr", "fuzzy_match_decisions", ["pr_record_id"])
    op.create_index("idx_fuzzy_decisions_gstr2b", "fuzzy_match_decisions", ["gstr2b_record_id"])
    op.create_index("idx_fuzzy_decisions_status", "fuzzy_match_decisions", ["session_id", "candidate_status"])

    # 11. recon_summary
    op.create_table(
        "recon_summary",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("total_invoice_records", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_pr_records", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_gstr2b_records", sa.Integer(), server_default="0", nullable=False),
        sa.Column("exact_matches", sa.Integer(), server_default="0", nullable=False),
        sa.Column("confirmed_fuzzy_matches", sa.Integer(), server_default="0", nullable=False),
        sa.Column("proposed_fuzzy_candidates", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejected_fuzzy_candidates", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unmatched_pr", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unmatched_gstr2b", sa.Integer(), server_default="0", nullable=False),
        sa.Column("missing_invoice_pairs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_exceptions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("exceptions_by_type", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("total_value_difference", sa.Numeric(precision=15, scale=2), server_default="0.00", nullable=False),
        sa.Column("highest_value_exception", sa.Numeric(precision=15, scale=2), server_default="0.00", nullable=False),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("ai_summary_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id", "client_id"],
            ["recon_sessions.id", "recon_sessions.client_id"],
            name="summary_session_client_fk",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="recon_summary_session_unique"),
    )
    op.create_index("idx_summary_session", "recon_summary", ["session_id"], unique=True)

    # 12. reports
    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_type", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("filters_applied", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.Text(), server_default="READY", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("generated_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id", "client_id"],
            ["recon_sessions.id", "recon_sessions.client_id"],
            name="reports_session_client_fk",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("report_type IN ('EXCEPTION_XLSX', 'SUMMARY_PDF', 'AUDIT_XLSX')", name="check_report_type"),
        sa.CheckConstraint("status IN ('READY', 'FAILED')", name="check_report_status"),
    )
    op.create_index("idx_reports_session", "reports", ["session_id"])

    # 13. audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("before_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id", "client_id"],
            ["recon_sessions.id", "recon_sessions.client_id"],
            name="audit_session_client_fk",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(session_id IS NULL AND client_id IS NULL) OR (session_id IS NOT NULL AND client_id IS NOT NULL)",
            name="audit_session_client_pair_check",
        ),
    )
    op.create_index("idx_audit_entity", "audit_log", ["entity_type", "entity_id"])
    op.create_index("idx_audit_session", "audit_log", ["session_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("reports")
    op.drop_table("recon_summary")
    op.drop_table("fuzzy_match_decisions")
    op.drop_table("exception_reviews")
    op.drop_table("exception_records")
    op.drop_table("recon_exceptions")
    op.drop_table("match_results")
    op.drop_table("extracted_records")
    op.drop_table("documents")
    op.drop_table("recon_sessions")
    op.drop_table("periods")
    op.drop_table("clients")
