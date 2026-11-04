# ReconAI — AI Guardrails Specification

> **Status:** Corrective revision — v1.2.1 (based on v1.2)
> **Date:** 2026-11-04
> **Authority:** Non-negotiable AI Guardrails for ReconAI.
> **Corrective revision:** 2026-11-04 — closes implementation-contract gaps found during independent review.
> **Changes from v1.1:**
> - Structured Invoice Extraction Schema updated to return an array of invoice objects (`invoices: list[InvoiceSchema]`) to support multi-invoice PDFs.
> - Explicit extraction rule added: Flag explicit credit notes or negative invoice totals (`invoice_total < 0` or `taxable_value < 0`) as extraction failures.
> - Reinforce AI Provider Abstraction (`GeminiAdapter` / `NullAdapter` fallback).

---

## 1. Permitted vs. Prohibited AI Operations

| Category | Permitted | Prohibited |
|---|---|---|
| **Extraction** | Extract structured fields from PDF text/images into JSON schema | Fabricate missing values; guess unreadable amounts; process credit notes |
| **Reconciliation** | Read deterministic reconciliation summaries | Calculate financial matches; set match statuses; override rules |
| **Explanations** | Explain detected exceptions using provided source values | Recommend tax advice; claim live GSTN connection; determine ITC eligibility |

---

## 2. Multi-Invoice Structured Extraction Schema

When calling Gemini Vision for PDF extraction, the following structured output schema is enforced:

```python
INVOICE_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "is_credit_note": {
            "type": "boolean",
            "description": "True if document explicitly states Credit Note or contains negative invoice total."
        },
        "invoices": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_page_number": {"type": "integer"},
                    "source_item_index": {"type": "integer"},
                    "is_credit_note": {"type": "boolean"},
                    "supplier_gstin": {"type": ["string", "null"]},
                    "invoice_number": {"type": ["string", "null"]},
                    "invoice_date": {"type": ["string", "null"]},
                    "taxable_value": {"type": ["string", "null"]},
                    "cgst": {"type": ["string", "null"]},
                    "sgst": {"type": ["string", "null"]},
                    "igst": {"type": ["string", "null"]},
                    "invoice_total": {"type": ["string", "null"]},
                    "supplier_name": {"type": ["string", "null"]},
                    "confidence": {
                        "type": "object",
                        "properties": {
                            "supplier_gstin": {"type": "number"},
                            "invoice_number": {"type": "number"},
                            "invoice_date": {"type": "number"},
                            "taxable_value": {"type": "number"},
                            "invoice_total": {"type": "number"}
                        }
                    }
                },
                "required": ["source_page_number", "source_item_index", "is_credit_note", "supplier_gstin", "invoice_number", "invoice_total", "confidence"]
            }
        }
    },
    "required": ["is_credit_note", "invoices"]
}
```

---

## 3. Extraction Processing Rules

1. **Credit Note Detection:** Detect explicit credit/debit-note language and document-level negative `invoice_total` or `taxable_value`. A negative line item alone is not a supported MVP field because line-item extraction is deferred. For MVP, source files are processed atomically: if any invoice in a PDF is an explicit credit note or has a negative document-level total/taxable value, fail the entire PDF with `status = FAILED`, `error_code = UNSUPPORTED_CREDIT_NOTE`, and persist no extracted records from that file. For PR/GSTR-2B CSV/XLSX, the same atomic failure applies if any row is explicitly a credit/debit note or has a negative document-level invoice total/taxable value. Never convert negative amounts to positive.
2. **Multi-Invoice Support:** Each invoice object in the `invoices` array must preserve its `source_page_number` and `source_item_index`. Do not silently drop additional invoices on the same page. This schema is invoice-level only; line-item extraction is V2.
3. **Partial Extraction Failure:** If parsing is incomplete for a non-credit-note reason, retain successfully extracted invoices and mark the document `PROCESSED_WITH_WARNINGS`; log the failed page/item and error in `audit_log`. Credit-note detection is a file-level hard failure and overrides partial-success handling.
4. **Grounding:** The AI must return `null` for unreadable fields, must not invent amounts or GSTINs, and must not set reconciliation/match statuses. Deterministic validators decide whether a value is parseable and whether the document is unsupported.

## 4. Source Data Scope

- MVP extracts invoice-header fields only: GSTIN, invoice number/date, taxable value, CGST, SGST, IGST, invoice total, supplier name, confidence, page number and within-page item index.
- Line-item extraction, line-item matching, tax eligibility and filing decisions are explicitly outside MVP.
- AI `is_credit_note` is a detection signal, not the sole decision-maker. Backend deterministic text/value checks must also run. Ambiguous classification must fail safely for manual correction; it must not normalize a suspected credit note into a positive invoice.
