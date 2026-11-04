# ReconAI — Corrective Specification Review Report (v1.2 → v1.2.1)

> **Date:** 2026-11-04
> **Scope:** Targeted specification corrections after independent review. No application code was written.

## Executive Summary

The v1.2 package resolved the original authentication, optional-invoice baseline, duplicate-evidence, fuzzy-review separation and audit-snapshot concerns. Independent review found additional implementation-contract gaps. This corrective revision updates all eight governing specifications, the decision register, and the consistency checklist.

## Corrections Applied

1. **Document status polling:** Added `GET /sessions/{session_id}/documents/{document_id}`, document listing, explicit processing states, readiness rules, and required-versus-optional source failure behaviour, including deferred invoice-evidence classification while optional PDFs are processing.
2. **Fuzzy candidate cardinality:** Recast `fuzzy_match_decisions` as a persistent multi-candidate registry. Multiple proposals may reference one PR/GSTR record; proposed candidates do not occupy one-to-one `match_results` slots.
3. **Fuzzy candidate lifecycle:** Defined `PROPOSED`, `CONFIRMED`, `REJECTED`, and `SUPERSEDED`; confirmation, rejection, supersession, idempotency, manual correction fingerprinting, and audit events.
4. **Unmatched records:** Defined `MISSING_IN_GSTR2B` and `MISSING_IN_PR` conditions after exact and confirmed fuzzy matching; duplicate-excluded records are not double-classified. Defined summary count and value formulas.
5. **Financial NULL handling:** Defined both-present comparison, one-sided missing-value exceptions, both-missing non-comparability, and explicit distinction between zero and `None`.
6. **Invoice-link sequence:** Confirmed decisions are applied before invoice evidence linking. Invoices remain optional invoice-header-level evidence; line-item extraction is V2.
7. **Data ownership:** Added composite ownership constraints and service-level validation requirements across client/session/document/record/match/exception/association/candidate/report relationships. Every exception now requires evidence-association rows; identical re-uploads have explicit candidate rebind semantics.
8. **Credit note scope:** Defined atomic source-file failure for explicit credit/debit-note indicators or negative document-level totals; no absolute-value conversion and no partial persistence from a failed file.
9. **API completeness:** Added client/period/session management, document listing/status polling, extracted-record listing/detail/correction, fuzzy candidate listing, exception listing, and authenticated report download contracts.
10. **Attribution:** Clarified that shared demo auth plus `operator_label` is not verified individual identity.
11. **Schema alignment:** Added source item indexes/keys, `PROCESSED_WITH_WARNINGS`, precise match and candidate states, `MISSING_FINANCIAL_VALUE`, and PR-GSTR-2B fuzzy score naming.
12. **Roadmap truthfulness:** Changed all task checkboxes to unchecked and added acceptance-test gates.

## Governing Artefacts

Eight revised specifications plus `SPEC_DECISIONS.md`, `SPEC_REVIEW_REPORT.md`, `SPEC_CONSISTENCY_CHECKLIST.md`, and `IMPLEMENTATION_BLOCKERS.md`.

## Verification Boundary

This review verifies specification consistency and internal contract design only. It does not verify implemented code, migrations, deployment, penetration resistance, GST correctness, or real-world data performance. Those require implementation and test evidence.
