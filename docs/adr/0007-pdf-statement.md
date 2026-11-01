# ADR 0007: Rust-owned landscape PDF statement

## Status

Accepted

## Context

Reports already calculate fixed operation-time values, current-rate values, and
logical transfer rows in the Rust storage engine. The previous PDF renderer was
portrait A4 and reused a single five-column table for every section, which made
transfers difficult to audit and caused wide report data to wrap unpredictably.

## Decision

Keep report arithmetic and filtering in Rust and make the PDF renderer a pure
presentation layer over `ReportResult`. Render an A4 landscape document with a
12 mm margin, typed sections, repeated headers, intact rows, a bundled Unicode
font, explicit fixed/current mode, and document metadata. Transfers are rendered
once in a dedicated section with both endpoints, amounts, currencies, rate,
commission, base equivalents, and integrity status.

The existing UniFFI export method and `ReportResultDto` remain unchanged. CSV,
XLSX, and PDF continue to consume the same report snapshot, so an export cannot
silently recalculate or mutate ledger data.

## Consequences

PDFs are wider and more suitable for a statement-style audit, while long cells
may use at most two measured lines followed by an explicit ellipsis. Pagination
and section headers are deterministic. The Python exporter remains available as
a compatibility path and must keep the same transfer-neutral and fixed/current
semantics.
