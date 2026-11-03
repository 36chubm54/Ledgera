# PDF renderer POC

This isolated Typst template tests the visual primitives needed to match the
HTML reference: KPI cards, Material-like color tokens, chips, signed amounts,
tables, and a fixed A4 landscape page.

The template also reads `data.json`. Debt progress bars are calculated from
`settled / total`, so the component is data-driven rather than a static image.

Rust now prepares the matching internal `PdfPresentationData` model in the
storage reporting path. It carries Fixed/Current mode, KPI values, operations,
logical transfers, monthly/category/tag summaries, and debt progress values.
The same model is consumed by the production Typst renderer when the
`typst-pdf` feature is enabled; the current `printpdf` renderer remains the
default fallback.

Build it with:

```text
typst compile --root . docs/pdf-poc/statement.typ C:/Temp/ledgera-typst-poc.pdf
```

Production feature build:

```text
cargo check -p ledgera_engine_storage --features typst-pdf
cargo test -p ledgera_engine_storage --features typst-pdf report_exports_keep_operation_and_transfer_sections
cargo check -p ledgera_engine_kotlin_ffi --features typst-pdf
cargo check -p ledgera_core --features typst-pdf
```

The Desktop Gradle task enables the same feature automatically. A normal
`compileKotlinDesktop` build therefore uses Typst; the legacy `printpdf` path
is available only when the native Rust library is built without the feature.

The checked-in template is kept here as a visual reference. The production
renderer uses the embedded copy in
`rust/ledgera_engine/storage/src/typst_statement.typ` and supplies data from
Rust instead of reading this sample `data.json`.
