import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Dialect-adaptive types for cross-environment testing and strict PostgreSQL DDL
UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")
JSONB_TYPE = PG_JSONB().with_variant(sa.JSON(), "sqlite")


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# 1. clients
class Client(Base, TimestampMixin):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    gstin: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    gstin_state: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    periods: Mapped[List["Period"]] = relationship(
        "Period", back_populates="client", cascade="all, delete-orphan"
    )
    sessions: Mapped[List["ReconSession"]] = relationship(
        "ReconSession", back_populates="client"
    )


# 2. periods
class Period(Base, TimestampMixin):
    __tablename__ = "periods"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    period_type: Mapped[str] = mapped_column(Text, nullable=False)
    period_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    period_month: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    period_quarter: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="OPEN", nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    client: Mapped["Client"] = relationship("Client", back_populates="periods")
    sessions: Mapped[List["ReconSession"]] = relationship(
        "ReconSession",
        back_populates="period",
        foreign_keys="[ReconSession.period_id, ReconSession.client_id]",
        overlaps="sessions",
    )

    __table_args__ = (
        UniqueConstraint("id", "client_id", name="periods_identity_unique"),
        CheckConstraint(
            "period_type IN ('MONTHLY', 'QUARTERLY')",
            name="check_period_type",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'CLOSED', 'ARCHIVED')",
            name="check_period_status",
        ),
        CheckConstraint(
            "(period_type = 'MONTHLY' AND period_month BETWEEN 1 AND 12 AND period_quarter IS NULL) OR "
            "(period_type = 'QUARTERLY' AND period_month IS NULL AND period_quarter BETWEEN 1 AND 4)",
            name="periods_type_fields_check",
        ),
        Index(
            "idx_period_month_unique",
            "client_id",
            "period_year",
            "period_month",
            unique=True,
            sqlite_where=sa.text("period_type = 'MONTHLY'"),
            postgresql_where=sa.text("period_type = 'MONTHLY'"),
        ),
        Index(
            "idx_period_quarter_unique",
            "client_id",
            "period_year",
            "period_quarter",
            unique=True,
            sqlite_where=sa.text("period_type = 'QUARTERLY'"),
            postgresql_where=sa.text("period_type = 'QUARTERLY'"),
        ),
    )


# 3. recon_sessions
class ReconSession(Base, TimestampMixin):
    __tablename__ = "recon_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("periods.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="DRAFT", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sources_ready: Mapped[Dict[str, Any]] = mapped_column(
        JSONB_TYPE,
        nullable=False,
        default=lambda: {
            "invoices": False,
            "purchase_register": False,
            "gstr2b": False,
        },
    )
    reconciled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    client: Mapped["Client"] = relationship(
        "Client", back_populates="sessions", overlaps="sessions"
    )
    period: Mapped["Period"] = relationship(
        "Period",
        back_populates="sessions",
        foreign_keys=[period_id, client_id],
        overlaps="client,sessions",
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        back_populates="session",
        foreign_keys="[Document.session_id, Document.client_id]",
        cascade="all, delete-orphan",
    )
    extracted_records: Mapped[List["ExtractedRecord"]] = relationship(
        "ExtractedRecord",
        back_populates="session",
        foreign_keys="[ExtractedRecord.session_id, ExtractedRecord.client_id]",
        cascade="all, delete-orphan",
    )
    match_results: Mapped[List["MatchResult"]] = relationship(
        "MatchResult",
        back_populates="session",
        foreign_keys="[MatchResult.session_id, MatchResult.client_id]",
        cascade="all, delete-orphan",
    )
    exceptions: Mapped[List["ReconException"]] = relationship(
        "ReconException",
        back_populates="session",
        foreign_keys="[ReconException.session_id, ReconException.client_id]",
        cascade="all, delete-orphan",
    )
    summary: Mapped[Optional["ReconSummary"]] = relationship(
        "ReconSummary",
        back_populates="session",
        foreign_keys="[ReconSummary.session_id, ReconSummary.client_id]",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("id", "client_id", name="sessions_identity_unique"),
        ForeignKeyConstraint(
            ["period_id", "client_id"],
            ["periods.id", "periods.client_id"],
            name="sessions_period_client_fk",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'PROCESSING', 'READY', 'RECONCILING', 'REVIEW', 'CLOSED', 'FAILED')",
            name="check_session_status",
        ),
    )


# 4. documents
class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("recon_sessions.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    row_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="UPLOADED", nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    session: Mapped["ReconSession"] = relationship(
        "ReconSession",
        back_populates="documents",
        foreign_keys=[session_id, client_id],
    )
    extracted_records: Mapped[List["ExtractedRecord"]] = relationship(
        "ExtractedRecord",
        back_populates="document",
        foreign_keys="[ExtractedRecord.document_id, ExtractedRecord.session_id, ExtractedRecord.client_id]",
        overlaps="extracted_records",
    )

    __table_args__ = (
        UniqueConstraint("id", "session_id", "client_id", name="documents_identity_unique"),
        ForeignKeyConstraint(
            ["session_id", "client_id"],
            ["recon_sessions.id", "recon_sessions.client_id"],
            name="documents_session_client_fk",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "document_type IN ('INVOICE', 'PURCHASE_REGISTER', 'GSTR2B')",
            name="check_document_type",
        ),
        CheckConstraint(
            "status IN ('UPLOADED', 'PROCESSING', 'PROCESSED', 'PROCESSED_WITH_WARNINGS', 'FAILED', 'DUPLICATE', 'DELETED')",
            name="check_document_status",
        ),
        Index("idx_documents_session", "session_id"),
        Index("idx_documents_hash_session", "session_id", "file_hash"),
        Index(
            "idx_documents_active_required_type",
            "session_id",
            "document_type",
            unique=True,
            sqlite_where=sa.text("document_type IN ('PURCHASE_REGISTER', 'GSTR2B') AND deleted_at IS NULL AND status <> 'DELETED'"),
            postgresql_where=sa.text("document_type IN ('PURCHASE_REGISTER', 'GSTR2B') AND deleted_at IS NULL AND status <> 'DELETED'"),
        ),
        Index(
            "idx_documents_active_hash",
            "session_id",
            "file_hash",
            unique=True,
            sqlite_where=sa.text("deleted_at IS NULL"),
            postgresql_where=sa.text("deleted_at IS NULL"),
        ),
    )


# 5. extracted_records
class ExtractedRecord(Base, TimestampMixin):
    __tablename__ = "extracted_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("recon_sessions.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    record_type: Mapped[str] = mapped_column(Text, nullable=False)

    # Raw provenance values
    source_row_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_item_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_record_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_supplier_gstin: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_invoice_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_invoice_date: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_taxable_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_cgst: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_sgst: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_igst: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_invoice_total: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_supplier_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_raw_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB_TYPE, nullable=True)

    # Normalized typed values
    supplier_gstin: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    invoice_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    invoice_norm_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    invoice_date: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)
    taxable_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    cgst: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    sgst: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    igst: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    invoice_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    supplier_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Quality & corrections
    extraction_method: Mapped[str] = mapped_column(Text, nullable=False)
    overall_confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3), nullable=True)
    field_confidence: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB_TYPE, nullable=True)
    is_manually_corrected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    corrected_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    corrected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    correction_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Matching state
    match_status: Mapped[str] = mapped_column(Text, default="UNMATCHED", nullable=False)

    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="extracted_records",
        foreign_keys=[document_id, session_id, client_id],
        overlaps="extracted_records",
    )
    session: Mapped["ReconSession"] = relationship(
        "ReconSession",
        back_populates="extracted_records",
        foreign_keys=[session_id, client_id],
        overlaps="document,extracted_records",
    )

    __table_args__ = (
        UniqueConstraint("document_id", "source_record_key", name="extracted_records_source_key_unique"),
        UniqueConstraint("id", "session_id", "client_id", name="extracted_records_identity_unique"),
        ForeignKeyConstraint(
            ["document_id", "session_id", "client_id"],
            ["documents.id", "documents.session_id", "documents.client_id"],
            name="extracted_records_document_owner_fk",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["session_id", "client_id"],
            ["recon_sessions.id", "recon_sessions.client_id"],
            name="extracted_records_session_client_fk",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "record_type IN ('INVOICE', 'PURCHASE_REGISTER', 'GSTR2B')",
            name="check_record_type",
        ),
        CheckConstraint(
            "extraction_method IN ('CSV_PARSE', 'XLSX_PARSE', 'PDF_TEXT', 'AI_VISION')",
            name="check_extraction_method",
        ),
        CheckConstraint(
            "match_status IN ('UNMATCHED', 'MATCHED', 'PENDING_MATCH_REVIEW', 'EXCLUDED')",
            name="check_match_status",
        ),
        Index("idx_extracted_session", "session_id"),
        Index("idx_extracted_gstin", "supplier_gstin"),
        Index("idx_extracted_norm_key", "invoice_norm_key"),
    )


# 6. match_results
class MatchResult(Base):
    __tablename__ = "match_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("recon_sessions.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_record_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID_TYPE, nullable=True)
    pr_record_id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, nullable=False)
    gstr2b_record_id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, nullable=False)
    match_type: Mapped[str] = mapped_column(Text, nullable=False)
    match_confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3), nullable=True)
    match_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fuzzy_score_pr_gstr2b: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 1), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    session: Mapped["ReconSession"] = relationship(
        "ReconSession",
        back_populates="match_results",
        foreign_keys=[session_id, client_id],
    )
    exceptions: Mapped[List["ReconException"]] = relationship(
        "ReconException",
        back_populates="match_result",
        foreign_keys="[ReconException.match_result_id, ReconException.session_id, ReconException.client_id]",
        cascade="all, delete-orphan",
        overlaps="exceptions",
    )

    __table_args__ = (
        UniqueConstraint("id", "session_id", "client_id", name="match_results_identity_unique"),
        ForeignKeyConstraint(
            ["pr_record_id", "session_id", "client_id"],
            ["extracted_records.id", "extracted_records.session_id", "extracted_records.client_id"],
            name="match_results_pr_record_fk",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["gstr2b_record_id", "session_id", "client_id"],
            ["extracted_records.id", "extracted_records.session_id", "extracted_records.client_id"],
            name="match_results_gstr2b_record_fk",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["invoice_record_id", "session_id", "client_id"],
            ["extracted_records.id", "extracted_records.session_id", "extracted_records.client_id"],
            name="match_results_invoice_record_fk",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "match_type IN ('EXACT', 'CONFIRMED_FUZZY')",
            name="check_match_type",
        ),
        Index("idx_match_pr_record", "pr_record_id", unique=True),
        Index("idx_match_gstr2b_record", "gstr2b_record_id", unique=True),
        Index(
            "idx_match_invoice_record",
            "invoice_record_id",
            unique=True,
            sqlite_where=sa.text("invoice_record_id IS NOT NULL"),
            postgresql_where=sa.text("invoice_record_id IS NOT NULL"),
        ),
        Index("idx_match_session", "session_id"),
    )


# 7. recon_exceptions
class ReconException(Base, TimestampMixin):
    __tablename__ = "recon_exceptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("recon_sessions.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    match_result_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID_TYPE, nullable=True)
    discrepancy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    exception_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    value_difference: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    details: Mapped[Dict[str, Any]] = mapped_column(JSONB_TYPE, nullable=False, default=dict)
    ai_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_explanation_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, default="OPEN", nullable=False)

    session: Mapped["ReconSession"] = relationship(
        "ReconSession",
        back_populates="exceptions",
        foreign_keys=[session_id, client_id],
        overlaps="exceptions",
    )
    match_result: Mapped[Optional["MatchResult"]] = relationship(
        "MatchResult",
        back_populates="exceptions",
        foreign_keys=[match_result_id, session_id, client_id],
        overlaps="exceptions,session",
    )
    exception_records: Mapped[List["ExceptionRecord"]] = relationship(
        "ExceptionRecord",
        back_populates="exception",
        foreign_keys="[ExceptionRecord.exception_id, ExceptionRecord.session_id, ExceptionRecord.client_id]",
        cascade="all, delete-orphan",
    )
    reviews: Mapped[List["ExceptionReview"]] = relationship(
        "ExceptionReview",
        back_populates="exception",
        foreign_keys="[ExceptionReview.exception_id, ExceptionReview.session_id, ExceptionReview.client_id]",
    )

    __table_args__ = (
        UniqueConstraint("id", "session_id", "client_id", name="recon_exceptions_identity_unique"),
        ForeignKeyConstraint(
            ["match_result_id", "session_id", "client_id"],
            ["match_results.id", "match_results.session_id", "match_results.client_id"],
            name="recon_exceptions_match_result_fk",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "exception_type IN ("
            "'MISSING_IN_PR', "
            "'MISSING_IN_GSTR2B', "
            "'MISSING_IN_INVOICE_NO_DOCS', "
            "'MISSING_IN_INVOICE_UNMATCHED', "
            "'TAXABLE_VALUE_MISMATCH', "
            "'CGST_MISMATCH', "
            "'SGST_MISMATCH', "
            "'IGST_MISMATCH', "
            "'INVOICE_TOTAL_MISMATCH', "
            "'DUPLICATE_CANDIDATE', "
            "'MISSING_FINANCIAL_VALUE', "
            "'DATE_MISMATCH', "
            "'SUPPLIER_NAME_MISMATCH')",
            name="check_exception_type",
        ),
        CheckConstraint(
            "severity IN ('HIGH', 'MEDIUM', 'LOW')",
            name="check_exception_severity",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'ACCEPTED', 'DISPUTED', 'DEFERRED')",
            name="check_exception_status",
        ),
        Index("idx_exceptions_session", "session_id"),
        Index("idx_exceptions_discrepancy_key", "discrepancy_key"),
    )


# 8. exception_records (Association Table)
class ExceptionRecord(Base):
    __tablename__ = "exception_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, primary_key=True, default=uuid.uuid4
    )
    exception_id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, nullable=False)
    extracted_record_id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("recon_sessions.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    record_role: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    exception: Mapped["ReconException"] = relationship(
        "ReconException",
        back_populates="exception_records",
        foreign_keys=[exception_id, session_id, client_id],
    )
    extracted_record: Mapped["ExtractedRecord"] = relationship(
        "ExtractedRecord",
        foreign_keys=[extracted_record_id, session_id, client_id],
        overlaps="exception,exception_records",
    )

    __table_args__ = (
        UniqueConstraint("exception_id", "extracted_record_id", name="exception_records_unique"),
        ForeignKeyConstraint(
            ["exception_id", "session_id", "client_id"],
            ["recon_exceptions.id", "recon_exceptions.session_id", "recon_exceptions.client_id"],
            name="exception_records_exception_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["extracted_record_id", "session_id", "client_id"],
            ["extracted_records.id", "extracted_records.session_id", "extracted_records.client_id"],
            name="exception_records_record_fk",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "record_role IN ('PRIMARY', 'DUPLICATE_CANDIDATE', 'COUNTERPART', 'SUPPORTING_INVOICE')",
            name="check_record_role",
        ),
        Index("idx_exception_records_exception", "exception_id"),
        Index("idx_exception_records_record", "extracted_record_id"),
    )


# 9. exception_reviews
class ExceptionReview(Base):
    __tablename__ = "exception_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, primary_key=True, default=uuid.uuid4
    )
    exception_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID_TYPE, nullable=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, nullable=False)
    discrepancy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    exception_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSONB_TYPE, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    exception: Mapped[Optional["ReconException"]] = relationship(
        "ReconException",
        back_populates="reviews",
        foreign_keys=[exception_id, session_id, client_id],
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "client_id"],
            ["recon_sessions.id", "recon_sessions.client_id"],
            name="reviews_session_client_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["exception_id", "session_id", "client_id"],
            ["recon_exceptions.id", "recon_exceptions.session_id", "recon_exceptions.client_id"],
            name="reviews_exception_owner_fk",
            ondelete="SET NULL",
        ),
        CheckConstraint(
            "action IN ('ACCEPT', 'DISPUTE', 'DEFER', 'REOPEN')",
            name="check_review_action",
        ),
        CheckConstraint(
            "length(comment) >= 10",
            name="check_review_comment_length",
        ),
        Index("idx_reviews_exception", "exception_id"),
        Index("idx_reviews_discrepancy_key", "discrepancy_key"),
    )


# 10. fuzzy_match_decisions
class FuzzyMatchDecision(Base, TimestampMixin):
    __tablename__ = "fuzzy_match_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("recon_sessions.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    pr_record_id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, nullable=False)
    gstr2b_record_id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, nullable=False)
    pr_value_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    gstr2b_value_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    similarity_score: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    candidate_status: Mapped[str] = mapped_column(Text, default="PROPOSED", nullable=False)
    decision_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("session_id", "candidate_key_hash", name="fuzzy_decisions_candidate_unique"),
        ForeignKeyConstraint(
            ["pr_record_id", "session_id", "client_id"],
            ["extracted_records.id", "extracted_records.session_id", "extracted_records.client_id"],
            name="fuzzy_candidate_pr_fk",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["gstr2b_record_id", "session_id", "client_id"],
            ["extracted_records.id", "extracted_records.session_id", "extracted_records.client_id"],
            name="fuzzy_candidate_gstr2b_fk",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "similarity_score BETWEEN 0 AND 100",
            name="check_fuzzy_similarity_score",
        ),
        CheckConstraint(
            "candidate_status IN ('PROPOSED', 'CONFIRMED', 'REJECTED', 'SUPERSEDED')",
            name="check_candidate_status",
        ),
        Index("idx_fuzzy_decisions_session", "session_id"),
        Index("idx_fuzzy_decisions_pr", "pr_record_id"),
        Index("idx_fuzzy_decisions_gstr2b", "gstr2b_record_id"),
        Index("idx_fuzzy_decisions_status", "session_id", "candidate_status"),
    )


# 11. recon_summary
class ReconSummary(Base):
    __tablename__ = "recon_summary"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("recon_sessions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    total_invoice_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_pr_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_gstr2b_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exact_matches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confirmed_fuzzy_matches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    proposed_fuzzy_candidates: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_fuzzy_candidates: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unmatched_pr: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unmatched_gstr2b: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    missing_invoice_pairs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_exceptions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exceptions_by_type: Mapped[Dict[str, Any]] = mapped_column(JSONB_TYPE, default=dict, nullable=False)
    total_value_difference: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0.00"), nullable=False
    )
    highest_value_exception: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0.00"), nullable=False
    )
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_summary_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    session: Mapped["ReconSession"] = relationship(
        "ReconSession",
        back_populates="summary",
        foreign_keys=[session_id, client_id],
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "client_id"],
            ["recon_sessions.id", "recon_sessions.client_id"],
            name="summary_session_client_fk",
            ondelete="CASCADE",
        ),
        Index("idx_summary_session", "session_id", unique=True),
    )


# 12. reports
class Report(Base, TimestampMixin):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("recon_sessions.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    report_type: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    filters_applied: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB_TYPE, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="READY", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_by: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "client_id"],
            ["recon_sessions.id", "recon_sessions.client_id"],
            name="reports_session_client_fk",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "report_type IN ('EXCEPTION_XLSX', 'SUMMARY_PDF', 'AUDIT_XLSX')",
            name="check_report_type",
        ),
        CheckConstraint(
            "status IN ('READY', 'FAILED')",
            name="check_report_status",
        ),
        Index("idx_reports_session", "session_id"),
    )


# 13. audit_log
class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID_TYPE, nullable=True)
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID_TYPE, nullable=True)
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID_TYPE, nullable=True)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    before_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB_TYPE, nullable=True)
    after_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB_TYPE, nullable=True)
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB_TYPE, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "(session_id IS NULL AND client_id IS NULL) OR (session_id IS NOT NULL AND client_id IS NOT NULL)",
            name="audit_session_client_pair_check",
        ),
        ForeignKeyConstraint(
            ["session_id", "client_id"],
            ["recon_sessions.id", "recon_sessions.client_id"],
            name="audit_session_client_fk",
            ondelete="RESTRICT",
        ),
        Index("idx_audit_entity", "entity_type", "entity_id"),
        Index("idx_audit_session", "session_id"),
    )
