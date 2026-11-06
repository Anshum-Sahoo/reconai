import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
import pytest
from sqlalchemy.orm import Session

from backend.db.models import (
    AuditLog,
    Base,
    Client,
    Document,
    ExceptionRecord,
    ExceptionReview,
    ExtractedRecord,
    FuzzyMatchDecision,
    MatchResult,
    Period,
    ReconException,
    ReconSession,
    ReconSummary,
    Report,
)


def test_all_13_tables_registered():
    """Verify all 13 distinct PostgreSQL tables specified in DATABASE_SCHEMA.md exist."""
    expected_tables = {
        "clients",
        "periods",
        "recon_sessions",
        "documents",
        "extracted_records",
        "match_results",
        "recon_exceptions",
        "exception_records",
        "exception_reviews",
        "fuzzy_match_decisions",
        "recon_summary",
        "reports",
        "audit_log",
    }
    registered_tables = set(Base.metadata.tables.keys())
    assert registered_tables == expected_tables, f"Missing or extra tables: {expected_tables ^ registered_tables}"


def test_create_full_entity_hierarchy(db_session: Session):
    """
    Test creating records across all 13 tables, verifying composite keys,
    strict Decimal usage, and relationships.
    """
    # 1. Client
    client_id = uuid.uuid4()
    client = Client(
        id=client_id,
        name="Acme Components Ltd",
        gstin="27AABCA1234L1ZX",
        gstin_state="27",
        contact_email="finance@acme.example",
    )
    db_session.add(client)
    db_session.flush()

    # 2. Period
    period_id = uuid.uuid4()
    period = Period(
        id=period_id,
        client_id=client.id,
        period_type="MONTHLY",
        period_year=2026,
        period_month=10,
        label="Oct 2026",
        status="OPEN",
    )
    db_session.add(period)
    db_session.flush()

    # 3. ReconSession
    session_id = uuid.uuid4()
    session = ReconSession(
        id=session_id,
        client_id=client.id,
        period_id=period.id,
        name="October 2026 Baseline Run",
        status="DRAFT",
        sources_ready={"invoices": False, "purchase_register": True, "gstr2b": True},
    )
    db_session.add(session)
    db_session.flush()

    # 4. Document
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        session_id=session.id,
        client_id=client.id,
        document_type="PURCHASE_REGISTER",
        original_filename="pr_oct_2026.xlsx",
        storage_path="uploads/pr_oct_2026.xlsx",
        file_hash="a" * 64,
        status="PROCESSED",
    )
    db_session.add(doc)
    db_session.flush()

    # 5. ExtractedRecord (PR and GSTR-2B)
    pr_record_id = uuid.uuid4()
    pr_record = ExtractedRecord(
        id=pr_record_id,
        document_id=doc.id,
        session_id=session.id,
        client_id=client.id,
        record_type="PURCHASE_REGISTER",
        source_row_number=12,
        source_record_key="b" * 64,
        source_supplier_gstin="27AABCT1332L1ZX",
        source_invoice_number="INV/2026/001",
        supplier_gstin="27AABCT1332L1ZX",
        invoice_number="INV/2026/001",
        invoice_norm_key="INV2026001",
        invoice_date=date(2026, 10, 5),
        taxable_value=Decimal("84745.76"),
        cgst=Decimal("7627.12"),
        sgst=Decimal("7627.12"),
        igst=Decimal("0.00"),
        invoice_total=Decimal("100000.00"),
        extraction_method="XLSX_PARSE",
        overall_confidence=Decimal("1.000"),
        match_status="MATCHED",
    )
    gstr_record_id = uuid.uuid4()
    gstr_record = ExtractedRecord(
        id=gstr_record_id,
        document_id=doc.id,
        session_id=session.id,
        client_id=client.id,
        record_type="GSTR2B",
        source_row_number=18,
        source_record_key="c" * 64,
        source_supplier_gstin="27AABCT1332L1ZX",
        source_invoice_number="INV-2026-001",
        supplier_gstin="27AABCT1332L1ZX",
        invoice_number="INV-2026-001",
        invoice_norm_key="INV2026001",
        invoice_date=date(2026, 10, 5),
        taxable_value=Decimal("84745.76"),
        cgst=Decimal("7627.12"),
        sgst=Decimal("7627.12"),
        igst=Decimal("0.00"),
        invoice_total=Decimal("100000.00"),
        extraction_method="CSV_PARSE",
        overall_confidence=Decimal("1.000"),
        match_status="MATCHED",
    )
    db_session.add_all([pr_record, gstr_record])
    db_session.flush()

    # Verify Decimal financial values (never float)
    assert isinstance(pr_record.taxable_value, Decimal)
    assert pr_record.taxable_value == Decimal("84745.76")
    assert not isinstance(pr_record.taxable_value, float)

    # 6. MatchResult
    match_id = uuid.uuid4()
    match = MatchResult(
        id=match_id,
        session_id=session.id,
        client_id=client.id,
        pr_record_id=pr_record.id,
        gstr2b_record_id=gstr_record.id,
        match_type="EXACT",
        match_confidence=Decimal("1.000"),
        match_key="27AABCT1332L1ZX_INV2026001",
    )
    db_session.add(match)
    db_session.flush()

    # 7. ReconException
    exception_id = uuid.uuid4()
    disc_key = "d" * 64
    exc = ReconException(
        id=exception_id,
        session_id=session.id,
        client_id=client.id,
        match_result_id=match.id,
        discrepancy_key=disc_key,
        exception_type="MISSING_IN_INVOICE_NO_DOCS",
        severity="MEDIUM",
        value_difference=None,
        status="OPEN",
    )
    db_session.add(exc)
    db_session.flush()

    # 8. ExceptionRecord (Association Table)
    exc_rec = ExceptionRecord(
        id=uuid.uuid4(),
        exception_id=exc.id,
        extracted_record_id=pr_record.id,
        session_id=session.id,
        client_id=client.id,
        record_role="PRIMARY",
    )
    db_session.add(exc_rec)
    db_session.flush()

    # 9. ExceptionReview
    review = ExceptionReview(
        id=uuid.uuid4(),
        exception_id=exc.id,
        session_id=session.id,
        client_id=client.id,
        discrepancy_key=disc_key,
        exception_snapshot={"status": "OPEN", "type": "MISSING_IN_INVOICE_NO_DOCS"},
        action="DEFER",
        comment="Awaiting supplier invoice copy via email",
        reviewer="CA Staff - Test User",
    )
    db_session.add(review)
    db_session.flush()

    # 10. FuzzyMatchDecision
    fuzzy_dec = FuzzyMatchDecision(
        id=uuid.uuid4(),
        session_id=session.id,
        client_id=client.id,
        pr_record_id=pr_record.id,
        gstr2b_record_id=gstr_record.id,
        pr_value_fingerprint="e" * 64,
        gstr2b_value_fingerprint="f" * 64,
        candidate_key_hash="1" * 64,
        similarity_score=Decimal("92.5"),
        candidate_status="PROPOSED",
    )
    db_session.add(fuzzy_dec)
    db_session.flush()

    # 11. ReconSummary
    summary = ReconSummary(
        id=uuid.uuid4(),
        session_id=session.id,
        client_id=client.id,
        total_pr_records=1,
        total_gstr2b_records=1,
        exact_matches=1,
        total_exceptions=1,
        total_value_difference=Decimal("0.00"),
    )
    db_session.add(summary)
    db_session.flush()

    # 12. Report
    report = Report(
        id=uuid.uuid4(),
        session_id=session.id,
        client_id=client.id,
        report_type="EXCEPTION_XLSX",
        storage_path="reports/exc_1.xlsx",
        status="READY",
        generated_by="CA Staff - Test User",
    )
    db_session.add(report)
    db_session.flush()

    # 13. AuditLog
    audit = AuditLog(
        event_type="SESSION_CREATED",
        entity_type="recon_session",
        entity_id=session.id,
        session_id=session.id,
        client_id=client.id,
        actor="CA Partner - Test User",
        before_state=None,
        after_state={"status": "DRAFT"},
    )
    db_session.add(audit)
    db_session.commit()

    # Verify retrieval
    retrieved_client = db_session.get(Client, client.id)
    assert retrieved_client is not None
    assert len(retrieved_client.periods) == 1
    assert len(retrieved_client.sessions) == 1
    assert db_session.get(AuditLog, audit.id) is not None
    assert db_session.get(FuzzyMatchDecision, fuzzy_dec.id) is not None
    assert db_session.get(ExceptionRecord, exc_rec.id) is not None
