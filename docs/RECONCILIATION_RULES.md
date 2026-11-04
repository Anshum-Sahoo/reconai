# ReconAI — Reconciliation Rules Specification

> **Status:** Corrective revision — v1.2.1 (based on v1.2)
> **Date:** 2026-11-04
> **Authority:** Deterministic reconciliation rules. These rules take precedence over AI output.
> **Core principle:** PR ↔ GSTR-2B is the independent baseline. Invoice PDFs are optional, invoice-level supporting evidence only.

## Constants

```python
from decimal import Decimal

AMOUNT_TOLERANCE = Decimal("1.00")  # MVP business-rule choice; not a claim about a universal GST standard
FUZZY_THRESHOLD_SAME_GSTIN = 85.0
FUZZY_THRESHOLD_ONE_GSTIN_MISSING = 95.0
FUZZY_AMBIGUITY_MARGIN = 5.0
```

## Phase 1: Normalization and Stable Source Identity

1. Normalize GSTIN by stripping whitespace and uppercasing; validate 15-character format. Invalid or blank GSTIN becomes `None` and must be reported as missing/invalid source data, not guessed.
2. Normalize invoice number by trimming, uppercasing and removing `-`, `/`, `\`, spaces and `_` for `invoice_norm_key`. Preserve the display value and raw source value.
3. Parse dates to ISO `DATE` values. Invalid or absent dates remain `None`.
4. Parse money using `Decimal`; strip currency symbols and grouping commas; quantize to 2 decimal places with `ROUND_HALF_UP`. Never use float and never take `abs()` of negative values.
5. Create `source_record_key = SHA256(document.file_hash + record_type + source_row_number OR source_page_number + source_item_index)`. For PDF pages with multiple invoices, `source_item_index` differentiates invoices on the same page. This key identifies source position and remains stable for the same file/row.
6. At matching time compute a value-sensitive record fingerprint from `source_record_key` plus canonical current normalized matching fields (GSTIN, invoice key, date, taxable value, tax components, invoice total). A manual correction changes this fingerprint and invalidates decisions tied to the old candidate key.

## Phase 2: Within-Source Duplicate Detection

Group records within each source by the complete key `(supplier_gstin, invoice_norm_key)` only when both fields are non-null/non-empty. If a key occurs more than once in the same source:

1. Mark every record in that duplicate group `EXCLUDED` for matching.
2. Create one `DUPLICATE_CANDIDATE` exception with `match_result_id = NULL`.
3. Add one `exception_records` row for every involved extracted record, using `record_role = 'DUPLICATE_CANDIDATE'`.
4. Do not also generate missing-counterpart exceptions for those excluded records.
5. Records lacking either key component are not grouped as duplicates merely because both values are NULL; they remain eligible for one-sided missing classification and carry a missing-match-key detail.

## Phase 3: Exact PR ↔ GSTR-2B Baseline Matching

Exact matching is independent of invoice documents:

1. Consider only non-duplicate PR and GSTR-2B records with complete, non-null `(supplier_gstin, invoice_norm_key)` keys.
2. Group both sources by that exact key. Phase 2 should have removed within-source duplicate keys; if a key is still non-unique, raise an invariant error and stop the run rather than arbitrarily selecting a row.
3. Create one `match_results` row for each unique PR-GSTR-2B pair with `match_type = 'EXACT'`, and set both source records to `MATCHED`.
4. Do not create `match_results` for one-sided unmatched records. Those are represented by exceptions in Phase 6.
5. No invoice record is required or consulted in this phase.

## Phase 4: Persistent Confirmed Decisions and Fuzzy Candidate Generation

`fuzzy_match_decisions` is the persistent candidate registry. It may hold multiple candidate rows referencing the same PR or GSTR-2B record. Such proposals are not `match_results` and do not consume the one-to-one match indexes.

### 4.1 Reapply previously confirmed decisions

1. Load `CONFIRMED` candidates for the session whose candidate key still matches the current value-sensitive fingerprints.
2. Apply a confirmed pair only if both records are still eligible and unmatched after Phase 3.
3. Create `match_results(match_type='CONFIRMED_FUZZY')` and set both records `MATCHED`.
4. If either record is already matched, excluded, missing, or its fingerprint changed, do not force the old decision. Mark the old candidate `SUPERSEDED` where appropriate and write an audit event.
5. Apply these decisions before invoice evidence linking.

### 4.2 Generate new proposals

For remaining unmatched PR and GSTR-2B records:

1. Compare `invoice_norm_key` with `rapidfuzz.fuzz.token_sort_ratio`; both keys must be non-empty.
2. GSTIN eligibility:
   - If both GSTINs are non-null, they must be identical; score must be at least 85.
   - If exactly one GSTIN is `None`, score must be at least 95, invoice dates must both be present and within 3 calendar days, and at least one amount field present on both sides must differ by no more than ₹1.00.
   - If both GSTINs are `None`, do not generate a fuzzy candidate.
   - Two different non-null GSTINs must never be fuzzy-linked.
3. Persist every eligible candidate at or above the applicable threshold in `fuzzy_match_decisions` with status `PROPOSED`. Multiple candidates may refer to one record.
4. Rank candidates by score descending; use stable `source_record_key` values as deterministic tie-breakers. Flag a candidate set as close/ambiguous when the top two scores for a record are within 5.0 points. This flag informs the UI; it never authorizes automatic confirmation.
5. All fuzzy proposals require explicit human confirmation, including a single high-scoring proposal. No fuzzy proposal is stored in `match_results` before confirmation.
6. Skip a proposal only when the same current `candidate_key_hash` is already `REJECTED`, `CONFIRMED`, or `SUPERSEDED`. A material correction changes the current-value fingerprint and therefore produces a new candidate key; historical decisions remain stored.

### 4.3 Fuzzy decision transaction

- `CONFIRM_MATCH`: lock both source records; verify neither is assigned to another confirmed match; set candidate status `CONFIRMED`; create exactly one `CONFIRMED_FUZZY` match result; supersede other still-proposed candidates that overlap either record; write an append-only audit event.
- `REJECT_MATCH`: set candidate status `REJECTED`; create no match result; preserve the candidate row; write an append-only audit event. Records remain pending only if another `PROPOSED` candidate references them; otherwise return them to `UNMATCHED`.
- Repeating the same decision is idempotent. Conflicting decisions on a terminal candidate return HTTP 409; no fuzzy-candidate reopen action exists in MVP.

Exception review state mapping is separate: `ACCEPT` → `ACCEPTED`, `DISPUTE` → `DISPUTED`, `DEFER` → `DEFERRED`, `REOPEN` → `OPEN`. MVP does not use a `RESOLVED` exception status because there is no corresponding review action.

## Phase 5: Invoice Evidence Linking

Run after exact pairs and previously confirmed fuzzy pairs have been established.

1. Invoice records are supplementary evidence and do not create or alter a PR-GSTR-2B match.
2. Link an invoice to a confirmed pair only when its complete `(supplier_gstin, invoice_norm_key)` key exactly equals the pair key and the invoice is not duplicate-excluded.
3. Enforce one invoice record per confirmed pair and one pair per invoice record. If more than one eligible invoice remains for the same key, raise an invariant/data-quality error; do not choose arbitrarily.
4. For a one-sided unmatched PR or GSTR-2B record, an exact-key invoice may be attached to the resulting missing-counterpart exception as `SUPPORTING_INVOICE` through `exception_records`.
5. Invoice records that cannot be uniquely linked remain visible in the invoice source inventory. MVP does not create a separate orphan-invoice exception type.
6. Missing-invoice exceptions are created only for confirmed PR-GSTR-2B pairs and only when invoice evidence processing is final: `MISSING_IN_INVOICE_NO_DOCS` if no invoice files were uploaded; `MISSING_IN_INVOICE_UNMATCHED` if at least one invoice file was uploaded but no invoice record was uniquely linked to the pair. If any uploaded invoice file is still `UPLOADED` or `PROCESSING`, defer missing-invoice classification for all pairs and set `invoice_evidence_pending = true`; the PR-GSTR baseline and other exception classifications may still complete. Failed invoice files are terminal and count as uploaded files.

## Phase 6: Unmatched Records and Exception Classification

After Phase 3 and Phase 4.1 confirmed-decision application:

1. A non-excluded PR record with no confirmed match and no active `PROPOSED` fuzzy candidate creates exactly one `MISSING_IN_GSTR2B` exception with `match_result_id = NULL` and an `exception_records` row with role `PRIMARY`.
2. A non-excluded GSTR-2B record with no confirmed match and no active `PROPOSED` fuzzy candidate creates exactly one `MISSING_IN_PR` exception with `match_result_id = NULL` and an `exception_records` row with role `PRIMARY`.
3. If a unique invoice evidence record exactly matches the one-sided record key, add it to that exception with role `SUPPORTING_INVOICE`.
4. Records with one or more `PROPOSED` fuzzy candidates remain `PENDING_MATCH_REVIEW` and are not simultaneously classified as missing. When all proposals for that record are `REJECTED` or `SUPERSEDED` and no confirmed match exists, create the appropriate missing exception.
5. Duplicate-excluded records are not classified again as missing. A rerun replaces current missing exceptions, so at most one current missing exception exists per underlying unmatched source record.
6. Every exception must populate `exception_records` with all source records that support it. Pair-based financial/date/name/missing-invoice exceptions link both PR (`PRIMARY`) and GSTR-2B (`COUNTERPART`) records; one-sided missing exceptions link the present source record (`PRIMARY`) and any uniquely linked invoice (`SUPPORTING_INVOICE`); duplicate exceptions link every duplicate member (`DUPLICATE_CANDIDATE`). `match_result_id` is supplementary navigation, not a substitute for these evidence associations.

### Financial comparison and missing values

Compare PR and GSTR-2B for `taxable_value`, `cgst`, `sgst`, `igst`, and `invoice_total` independently:

- If both values are present, compute `abs(pr_value - gstr2b_value)` using `Decimal`; create the corresponding mismatch exception only when the difference is greater than `AMOUNT_TOLERANCE`.
- If exactly one side is `None`, create `MISSING_FINANCIAL_VALUE`, storing the field name and the present/missing side in `details`; do not calculate a numeric difference.
- If both sides are `None`, mark the field `NOT_COMPARABLE` in comparison details and do not create a mismatch or substitute zero.
- An explicit `Decimal("0.00")` is a real value and is not equivalent to `None`.
- Tolerance applies independently to each of the five listed fields. It does not apply to counts, dates, GSTINs, invoice numbers, or supplier names.

For dates, create `DATE_MISMATCH` only when both dates are present and differ. If one is absent, store a data-completeness note; do not invent a date. Supplier-name mismatches are advisory and must not override GSTIN eligibility.

### MVP severity mapping

Use this fixed display mapping (not a tax-risk or ITC-eligibility judgment):
- `HIGH`: `MISSING_IN_PR`, `MISSING_IN_GSTR2B`, `DUPLICATE_CANDIDATE`, `INVOICE_TOTAL_MISMATCH`.
- `MEDIUM`: `TAXABLE_VALUE_MISMATCH`, `CGST_MISMATCH`, `SGST_MISMATCH`, `IGST_MISMATCH`, `MISSING_FINANCIAL_VALUE`, `DATE_MISMATCH`.
- `LOW`: `SUPPLIER_NAME_MISMATCH`, `MISSING_IN_INVOICE_NO_DOCS`, `MISSING_IN_INVOICE_UNMATCHED`.

## Phase 7: One-to-One Invariants and Summary

1. A record may occur in at most one confirmed `match_results` row per session.
2. Proposed fuzzy candidates are stored separately and may share records; they do not count as matches.
3. An invoice can be linked to at most one confirmed pair or one one-sided exception.
4. Before commit, assert no source record is assigned to multiple confirmed matches and no excluded duplicate is matched.
5. Summary metrics:
   - `exact_matches`: count of `EXACT` rows.
   - `confirmed_fuzzy_matches`: count of `CONFIRMED_FUZZY` rows.
   - `proposed_fuzzy_candidates`: count of `PROPOSED` candidate-registry rows.
   - `rejected_fuzzy_candidates`: count of `REJECTED` candidate-registry rows.
   - `unmatched_pr`: eligible PR records with no confirmed match and no pending proposal.
   - `unmatched_gstr2b`: eligible GSTR-2B records with no confirmed match and no pending proposal.
   - `missing_invoice_pairs`: confirmed pairs without a uniquely linked invoice after all uploaded invoice files reach terminal status.
   - `invoice_evidence_pending`: true when one or more uploaded invoice files remain `UPLOADED` or `PROCESSING`.
   - `total_exceptions`: current-run exception count.
6. Do not expose an undefined `partial_matches` count. It is removed from MVP summary contracts.
7. `total_pr_records`, `total_gstr2b_records`, and `total_invoice_records` count all extracted records from non-deleted documents of the respective type, including duplicate-excluded records. Excluded duplicates remain separately visible through `DUPLICATE_CANDIDATE` exceptions.
8. `total_value_difference` is the sum of `value_difference` across current financial mismatch exceptions (`TAXABLE_VALUE_MISMATCH`, `CGST_MISMATCH`, `SGST_MISMATCH`, `IGST_MISMATCH`, `INVOICE_TOTAL_MISMATCH`), each calculated as an absolute difference. Do not include missing-value, date, supplier-name, duplicate, missing-counterpart, or missing-invoice exceptions.
9. `highest_value_exception` is the maximum absolute `value_difference` among those same financial mismatch exceptions; use `Decimal("0.00")` when none exist.
10. `total_exceptions` counts current `recon_exceptions` rows only. Fuzzy candidate registry rows are counted in their dedicated candidate metrics, not as exceptions.

## Discrepancy and Candidate Key Calculation

- `discrepancy_key`: SHA-256 of canonical JSON containing exception type and sorted stable `source_record_key` values (not database UUIDs).
- `candidate_key_hash`: SHA-256 of canonical JSON containing the PR and GSTR-2B stable source keys plus their current normalized-value fingerprints.
- Validate source record types at the service boundary: PR candidates must reference `PURCHASE_REGISTER` records, GSTR candidates `GSTR2B` records, and invoice links `INVOICE` records. Composite FKs enforce client/session ownership; service validation enforces semantic record types.
- Serialize canonical JSON with sorted keys, UTF-8, no insignificant whitespace, and fixed decimal strings.
- Exception reviews store an immutable snapshot of exception type, values, source keys, linked evidence, and relevant explanation at review time.

## Rerun Semantics

1. Execute a rerun in one database transaction.
2. Reset every extracted record from non-deleted documents to `UNMATCHED` before rebuilding. Duplicate detection then marks currently duplicated rows `EXCLUDED`; exact/confirmed assignments set rows to `MATCHED`; active proposals set rows to `PENDING_MATCH_REVIEW`. Records belonging to soft-deleted documents remain `EXCLUDED`.
3. Before removing current exceptions, ensure each review has a complete immutable snapshot and discrepancy key.
4. Delete/rebuild current-run `match_results`, `recon_exceptions`, `exception_records`, and `recon_summary`; do not delete `exception_reviews`, `fuzzy_match_decisions`, or `audit_log`.
5. Rebuild exact matches; reapply unchanged confirmed decisions; regenerate proposals while skipping unchanged rejected/terminal candidates; then link invoice evidence and classify exceptions.
6. If a source record is manually corrected, retain the original raw values, update corrected normalized values, write an audit event, and compute a new current-value fingerprint. Old fuzzy decisions remain historical and are not applied to the changed fingerprint.
7. If an identical file is re-uploaded after soft deletion, and its file hash, source position key, and current-value fingerprint are identical, rebind the candidate-registry row to the new extracted-record UUIDs within the same session and append a `CANDIDATE_REBOUND` audit event. This preserves confirmed/rejected decisions across identical re-uploads without relying on old record UUIDs. If the file content or normalized values differ, do not rebind; a new source/candidate key is required.
8. All operations must be deterministic for identical source rows, corrections, and persistent candidate states.
