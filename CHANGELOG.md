# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog.
This project adheres to Semantic Versioning.

---

## [2.0.0-beta.2] - 2026-05-12

### Changed

- Continued the `2.0.0` beta stabilization line on top of the completed `amount_base` / `limit_base` storage migration
- Kept the two-layer currency model stable: `base_currency` remains the persisted accounting layer while `display_currency` stays UI-only
- Carried forward the repository capability protocol cleanup and shell/runtime extraction as the baseline architecture for the next beta update

### Fixed

- Preserved compatibility with pre-precision SQLite schemas by backfilling missing legacy `*_minor` columns before startup rename migration
- Preserved imports from pre-rename CSV/XLSX full-backup files by falling back from `amount_base` to legacy `amount_kzt`
- Preserved legacy JSON repository records and transfers that still store normalized amounts under `amount_kzt`
- Restored transfer reconstruction during CSV full import so valid linked transfer pairs no longer fail integrity checks
- Localized exported report headers and section labels while making base-currency columns explicit with the actual code (for example `KZT`) instead of generic `base currency` wording
- Switched report statement order to `newest first` in both the `Reports` tab and exported statement files
- Taught the generic import parser to accept localized report `CSV` / `XLSX` exports without treating title/balance/subtotal rows as ordinary operations
- Tightened budget/distribution repository capability guards with explicit capability markers instead of empty protocol checks
- Narrowed the `RecordService` base-currency fallback so unexpected repository/runtime failures are no longer silently converted into `KZT`

### Testing

- Full release gate is green: `pyright` passes and the full `pytest` suite passes before beta cut

---

## [2.0.0-alpha.2] - 2026-05-10

### Breaking Changes

- DB schema: `amount_kzt` / `amount_kzt_minor` renamed to `amount_base` / `amount_base_minor` in `records`, `transfers`, and `mandatory_expenses`
- DB schema: `limit_kzt` / `limit_kzt_minor` renamed to `limit_base` / `limit_base_minor` in `budgets`
- Python naming aligned with base-currency storage, including `Record.amount_base`, `Record.signed_amount_base()`, `convert_money_to_base()`, and `wallet_balance_base()`

### Migration

- Added `migrations/migration_002_rename_amount_kzt_to_base.py`; migration runs automatically on startup and is idempotent
- `schema_meta` now stores `base_currency = KZT` for migrated and newly initialized databases

### Added

- Added `CurrencyService.display_currency`, `set_display_currency()`, `to_display()`, and `display_symbol` for runtime-only display conversion
- Added a status-bar display currency switcher that refreshes visible amounts without changing stored base values
- Added `app/repository_protocols.py` to express upper-layer repository capabilities without direct `SQLiteRecordRepository` typing
- Added `gui/shell/*` helpers and `gui/tabs/infographics_support.py` to move shell/runtime and infographics orchestration out of the main Tkinter shell module

### Changed

- Renamed the commercial fallback provider from `open_exchange` / `OpenExchangeProvider` to `exchange_rate` / `ExchangeRateProvider`
- Aligned report/export/status-bar documentation and runtime messaging with the new `base_currency` / `display_currency` contract
- Moved shell/runtime orchestration out of `gui/tkinter_gui.py` into dedicated status, refresh, lifecycle, notebook, preferences, startup, records, and setup helpers
- Switched upper `app`, `services`, and `gui.controllers` layers from direct concrete SQLite typing to narrower repository capability protocols

### Removed

- Removed deprecated `*_kzt` Python aliases and helper methods that had been kept only for the transition period

### Tests

- Added architecture-boundary and protocol-regression coverage for the contract cleanup
- Restored Tk-based local test execution as an optional local gate by validating the Tcl/Tk runtime path separately from product code

---

## [2.0.0-alpha.1] - 2026-05-10

### Added

- `infrastructure/currency_providers.py` with `BaseRateProvider`, `NBKProvider`, `CBRProvider`, `OpenExchangeProvider`, and `StaticProvider`
- `infrastructure/currency_aggregator.py` with `CurrencyAggregator` for ordered provider fallback
- `currency_config.json` for runtime currency-provider selection and OpenExchange configuration
- `CurrencyService.__init__(..., aggregator=...)` dependency injection support for online-rate tests

### Changed

- Replaced the monolithic online rate fetch path in `app/services.py` with provider-backed aggregation while preserving the public `CurrencyService` API
- Switched `CBRProvider` to parse the publicly reachable Rambler mirror of the Central Bank of Russia rates table instead of calling `cbr.ru` directly in blocked regions

### Internal

- Kept `CurrencyService` behavior backward compatible with `v1.15.2`, including cache fallback and default offline rates

---

## [v1.15.2] - 2026-05-10

### Changed

- Clarified inline amount-edit semantics so `KZT` operations and transfers now edit the primary amount directly, while non-`KZT` flows keep editing the `KZT` equivalent

### Fixed

- Fixed SQLite bulk replace so top-level `tags` from backup/import survive restore even when they currently have no `record_tags`
- Fixed `KZT` transfer and inline-record editing so the stored primary amount stays consistent with what the editor shows
- Fixed `sqlite_sequence` maintenance for `distribution`, `assets`, `goals`, and JSON->SQLite migration flows by routing updates through a shared helper

### Tests

- Added regression coverage for `KZT` amount editing, orphan-tag restore, tag-sequence reset, migration reruns, and duplicate-free `sqlite_sequence` updates

### Docs

- Updated `README.md`, `README_EN.md`, and `CHANGELOG.md` for `v1.15.2`

No breaking changes.

---

## [v1.15.1] - 2026-05-09

### Added

- Added shell-level runtime helpers for background work, deferred startup, status refresh, and lazy tab lifecycle (`gui/runtime_coordinator.py`, `gui/startup_coordinator.py`, `gui/status_bar_coordinator.py`, `gui/tab_lifecycle.py`)
- Added application-level import/runtime helpers (`app/import_support.py`, `app/preferences_service.py`, `app/audit_runner.py`, `app/repository.py`) to formalize boundaries that were previously implicit
- Added small UX polish on top of `v1.15.0`, including `Ctrl+T` tag-mode switching in analytics, inline transfer editing, and reusable popup tooltip support

### Changed

- Split former orchestration hotspots into narrower modules: `app/use_cases_*`, `services/import_*_support.py`, and dedicated GUI coordinators/helpers
- Moved import transaction ownership out of the GUI layer into app/service support modules and decomposed `ImportService` into payload/replacement/execution/mandatory helpers
- Introduced the application-level `RecordRepository` contract and aligned use cases with it instead of depending on infrastructure-owned ports
- Tightened GUI/runtime typing boundaries so shell helpers now use protocol-shaped contracts and the codebase passes `pyright`
- Refined analytics/infographics presentation for large category sets and chart redraw behavior

### Fixed

- Fixed background GUI callbacks so `on_success(...)` failures no longer surface as raw Tk tracebacks
- Fixed chart refresh suspension so failed redraw/update steps do not leave chart updates permanently blocked
- Fixed legacy JSON auto-migration so failed persistence is surfaced explicitly instead of silently continuing with unsaved state
- Fixed import/create and backup/migration edge cases around runtime durability, rollback, and repository save behavior

### Tests

- Added regression coverage for architecture boundaries, GUI runtime coordinators, startup/status shell helpers, repository durability, and typed test helpers around the new app-level contracts

### Docs

- Reframed `README.md`, `README_EN.md`, and `docs/architecture.md` around the `v1.15.1` stabilization pass and the post-`v1.15.0` architectural cleanup

No breaking changes.

---

## [v1.15.0] - 2026-05-09

### Added

- Added first-class operation tags with dedicated domain/storage support (`tags`, `record_tags`), repository APIs, color metadata, usage counters, and JSON backup/migration coverage
- Added tag-aware UI in `Operations`: free-form tag entry, suggestions, validation, color picking, and tag sidecar display
- Added single-tag and multi-tag report filtering plus tag export surfaces in `XLSX` / `PDF`
- Added tag budgets and tag-based forecast/pace tracking in the budget subsystem
- Added tag analytics coverage mode with dedicated table + bar chart and explicit non-additive semantics
- Added `tag_integrity` checks to the audit engine

### Changed

- Extended import/export/backup pipelines so tags participate in `JSON`, `CSV`, `XLSX`, SQLite bulk replace, and JSON→SQLite migration flows
- Generalized budgets from category-only scope to `scope_type` / `scope_value` (`category` or `tag`)
- Localized budget forecast statuses through UI-facing localization keys instead of hardcoded service text
- Report exports now include a `By Tag` sheet in `XLSX` and `Group report on tag` in `PDF`

### Fixed

- Fixed import create-paths so imported records no longer lose tags after operation reset/recreate flows
- Fixed analytics tag coverage so each tag reflects the full amount of matching records instead of splitting one record across multiple tags
- Fixed several UI and typing edge cases around tag dropdowns, color pickers, analytics layout, and repository/storage type hints

### Tests

- Added/updated regression coverage for tag persistence, tag import/export, tag analytics, tag budgets, tag audit checks, and new export layouts

### Docs

- Updated `README.md`, `README_EN.md`, and `docs/architecture.md` for the tag system, tag budgets, tag analytics, tag export, and backup/migration changes

No breaking changes.

---

## [1.14.0] - 2026-05-04

### Added

- Added reusable UI shell helpers in `gui/ui_theme.py`, including card-section builders, spacing tokens, Treeview zebra helpers, and deeper palette application for shell widgets
- Added stronger theme propagation for Canvas, Treeview, and Combobox popdown widgets across the desktop shell

### Changed

- Redesigned the desktop interface shell with more consistent card-based layouts, refreshed spacing, and cleaner visual hierarchy across major tabs
- Refreshed `Operations`, `Debts`, `Budget`, `Reports`, `Analytics`, and `Settings` layouts to better fit the updated theme system
- Updated `gui/tkinter_gui.py` so shell initialization, DPI bootstrap wiring, and theme application live closer to the GUI layer
- Tightened dark/light theme styling for notebook tabs, headings, status bar controls, inline panels, and tables

### Fixed

- Improved desktop-shell consistency so tab content, auxiliary canvases, and list-heavy views follow the active palette more reliably
- Stabilized migration/runtime tests around the current SQLite migration paths and audit/runtime expectations

### Tests

- Updated regression coverage for redesigned shell behavior, runtime storage paths, audit expectations, and JSON→SQLite migration flows

### Docs

- Updated `README.md`, `README_EN.md`, and `docs/architecture.md` for `v1.14.0` and the redesigned desktop shell

No breaking changes.

---

## [1.13.0] - 2026-04-29

### Added

- Added global hotkey system with comprehensive keyboard shortcuts for all major tabs (`gui/hotkeys.py`)
- Added hotkey help dialog accessible via `F1` or `?` with detailed table of shortcuts
- Added support for tab switching via `Alt+1`…`Alt+8`
- Added shortcut guards that ignore keypresses when focus is inside input fields (`Entry`, `Combobox`, `Text`)
- Added focus‑aware blocking for destructive shortcuts (`Del`, `Ctrl+Del`, `Ctrl+W`) to prevent accidental data loss
- Added proper `Enter` key handling that allows normal text input in `Combobox` and `Text` widgets
- Added hotkey deactivation when the operations inline editor is open
- Added dedicated tests for hotkey registration and behavior (`tests/test_hotkeys.py`)

### Changed

- Updated `gui/tkinter_gui.py` to register hotkeys at startup and manage tab‑specific bindings
- Enhanced `gui/tabs/operations_tab.py`, `budget_tab.py`, `debts_tab.py`, `reports_tab.py`, `analytics_tab.py` to expose action methods for hotkey handlers
- Improved focus detection logic to avoid conflicts with inline editors and modal dialogs
- Updated Russian and English locale files with new hotkey‑related UI strings

### Tests

- Added regression coverage for hotkey registration, focus guards, tab‑specific shortcuts, and the help dialog
- Extended GUI tests to verify hotkeys do not interfere with text input

### Docs

- Updated `README.md` and `README_EN.md` with complete hotkey table and detailed behavior description
- Synchronized version references across `pyproject.toml`, `README.md`, `README_EN.md`, and `version.py`

No breaking changes.

---

## [1.12.0] - 2026-04-25

### Added

- Added persisted runtime `theme` / `language` preferences through SQLite schema metadata
- Added live light/dark theme support through `gui/ui_theme.py` with runtime palette switching
- Added `ImportCapabilities` in `app/finance_service.py` so import flows can detect supported bulk-replace/load operations through one explicit capability contract
- Added `gui/logging_utils.py` with shared structured UI error logging used by deferred startup and audit-related GUI flows
- Added warning surfaces for degraded grouped report export: `XLSX` exporters now create a `Warnings` sheet and `PDF` exporters embed a visible warning block when grouped sections cannot be built
- Added thread-safe SQLite connection wrappers in `storage/sqlite_storage.py` to coordinate concurrent reads, backups, and background GUI work

### Changed

- The application shell, status bar, dialogs, audit report views, and major tabs are now theme-aware at runtime
- Theme and language can now be switched through runtime UI preferences instead of only startup defaults
- `ImportService` is now section-aware for partial `JSON` payloads and uses `json_sections_present` when available, falling back to payload inspection only when older payloads omit section metadata
- `JSON` records-only imports now preserve unrelated runtime entities such as `debts`, `assets`, `goals`, `budgets`, and distribution data instead of treating missing sections as an implicit wipe
- Import normalization now preserves `related_debt_id` links more carefully: when the payload does not supply debt data, existing links are retained when possible; when it does, links are constrained to allowed debt IDs
- `CreateIncome` / `CreateExpense`, `FinanceService`, and `FinancialController` now propagate `related_debt_id` through create-path imports, including `CSV` / `XLSX`
- Bootstrap now distinguishes `BackupExportError`, runs `PRAGMA quick_check`, and applies more conservative export behavior for large SQLite databases stored under OneDrive-managed paths
- JSON repository save/load error handling is more explicit, with corruption quarantine and dedicated save/corruption error types

### Fixed

- Fixed import rollback/remap edge cases so `debt_payments.record_id` and `records.related_debt_id` survive normalization and repository-level record replacement more reliably
- Fixed runtime persistence so explicit `wallet.id` and `record.id` values are preserved when `SQLiteStorage` inserts imported entities
- Fixed grouped report export degradation so `XLSX` / `PDF` output still succeeds with a user-visible warning instead of silently dropping grouped content or failing hard
- Fixed GUI scheduling and tooltip geometry edge cases by tightening `after` job management and safer `TclError` handling around delayed UI work
- Fixed JSON repository failure modes on damaged or locked files by quarantining unreadable payloads and preserving unsaved data in `.error` snapshots

### Tests

- Added/updated regression coverage for runtime theme/language preferences, theme palettes, section-aware import behavior, debt-link preservation, repository corruption/save-failure handling, thread-safe SQLite backup/select flows, explicit-ID SQLite inserts, grouped-export warning paths, and GUI compatibility around ttk-based debt forms

### Docs

- Updated `README.md`, `README_EN.md`, and `docs/architecture.md` for `v1.12.0`, runtime theme/language preferences, import capability negotiation, partial-JSON semantics, repository durability, grouped-export warnings, and OneDrive-aware bootstrap behavior

No breaking changes.

---

## [1.11.0] - 2026-04-08

### Added

- Added external localization packs in `locales/ru.txt` and `locales/en.txt` with unified `tr(...)` lookups for shell/tabs/dialogs
- Added `gui/i18n.py` language loader with safe fallback behavior (`selected language -> ru -> default`)
- Added shared GUI theming/util modules: `gui/ui_theme.py`, `gui/ui_helpers.py`, `gui/ui_text.py`
- Added `.gitattributes` to normalize text/source line endings and reduce cross-platform CRLF/LF noise
- Added Windows DPI-awareness bootstrap in app startup to keep Tk + native file dialogs sharp on HiDPI displays

### Changed

- Refreshed Tkinter UI to a soft-blue minimal style: calmer contrast, unified controls, updated status bar, notebook/treeview/scrollbar/checkbutton states
- Reworked Settings inline panels to use consistent two-column layout with equal-width action rows (`Create/Edit/Add to records`)
- Improved Distribution tables so columns stretch to the right edge in both empty and populated states
- Improved dashboard/infographics chart layout behavior for compact window sizes and better axis/legend visibility
- Localized Distribution action buttons and messagebox flows to eliminate hardcoded UI strings
- Replaced raw enum values in Debts/Budget tables with localized labels for kind/status/pace values
- Added application icon hooks (`.ico` + `iconphoto` fallback) for the top-left window icon and future EXE packaging

### Fixed

- Fixed multiple mixed-language GUI tails by routing remaining tab/shell strings through i18n keys
- Fixed Dashboard tab render issues caused by geometry conflicts and tightened chart area allocation
- Fixed stale default hover colors from `clam` (brown accents) by enforcing blue palette mappings in ttk style maps
- Fixed fragile GUI test behavior in incomplete Tcl/Tk environments by introducing deterministic Tk availability guards in tests
- Hardened DPI bootstrap exception handling on unsupported/non-Windows environments so startup never fails because of DPI API calls

### Tests

- Added/updated localization coverage for language-pack parsing and fallback behavior
- Extended GUI regression checks for dashboard/debts/analytics flows under the refreshed UI layer
- GUI Tk tests now skip cleanly when Tcl/Tk runtime files are unavailable, preventing environment-only red builds

### Docs

- Updated `README.md` and `README_EN.md` for `v1.11.0`, external language packs, UI polish, and test-environment guardrails

No breaking changes.

---

## [1.10.1] - 2026-04-07

### Fixed

- Fixed import rollback for SQLite so failed restore flows no longer leave partially updated `assets`, `goals`, or other newer entities behind
- Extended non-SQLite import rollback so JSON/file-based repositories now restore `debts` and `debt_payments` too, instead of only records/transfers
- Fixed operation-id normalization after import so `debt_payments.record_id` links are preserved instead of being nulled during record reindexing
- Fixed bulk asset snapshot upsert so late validation failures no longer leave partial writes in the database
- Fixed non-strict JSON import so orphan `asset_snapshots` are skipped early instead of failing later during asset replacement
- Fixed non-strict JSON import so orphan `debt_payments` are skipped early and orphan `records.related_debt_id` links are cleared before bulk replace
- Fixed bulk JSON import so `assets` and `goals` are no longer applied twice after `replace_all_for_import(...)`
- Hardened import payload validation to reject duplicate `wallet.id`, multiple `system` wallets, and duplicate/invalid `distribution_snapshots` earlier in the pipeline
- Hardened backup creation so JSON backup files are written atomically via temp file + `fsync` + `os.replace`
- Hardened the currency-rate cache and JSON repository writes so temp files are flushed and synced before replace
- Hardened JSON -> SQLite migration validation so reruns now compare payload signatures for wallets, transfers, records, and mandatory templates instead of relying only on counts/balances

### Tests

- Added regression coverage for SQLite/file import rollback, debt-payment link preservation during normalization, atomic asset snapshot batch updates, orphan asset/debt snapshot handling in non-strict JSON import, duplicate wallet/system-wallet payload rejection, distribution snapshot validation, atomic backup/cache writes, JSON repository fsync behavior, and stronger JSON -> SQLite equivalence checks

No breaking changes.

---

## [1.10.0] - 2026-04-06

### Added

- Added strategic wealth-management domains: `assets`, `asset_snapshots`, and `goals`
- Added services, use cases, controller flows, and SQLite persistence for manual asset registry, snapshot history, and strategic goals
- Added a dedicated `Dashboard` tab with net worth trend, asset allocation, goals overview, quick actions, and bulk asset snapshot update
- Added Dashboard goal-management UI flows: create, complete, reopen, and delete
- Added Dashboard asset-management UI flows: create, edit, deactivate, and bulk snapshot save
- Full backup/import/JSON->SQLite migration now support `assets`, `asset_snapshots`, and `goals`
- Audit engine now includes integrity checks for assets, asset snapshots, and goals

### Changed

- Net worth now includes the latest active asset snapshots in addition to wallets, debts, and loans
- Goal progress is now derived dynamically from current asset aggregates through the asset service
- Dashboard forms now use inline validation and clearer warnings for asset currency changes and invalid goal timelines

### Fixed

- Fixed asset edit flow so `created_at` is handled correctly end-to-end in controller/use-case/service paths
- Fixed bulk asset snapshot UX issues around cramped layout and unclear validation feedback
- Hardened asset/goal UI validation for invalid dates, currencies, amounts, and edge-case form states

### Tests

- Added regression coverage for asset/goal domain models, asset service/controller flows, dashboard service/tab behavior, backup/import/migration, runtime SQLite storage, and the expanded audit engine

### Docs

- Updated `README.md` and `README_EN.md` for `v1.10.0`, the new `Dashboard` tab, strategic asset/goal flows, asset-aware net worth, and expanded audit coverage
- Compacted README structure and moved detailed technical mapping into `docs/architecture.md`

No breaking changes.

---

## [1.9.1] - 2026-04-03

### Changed

- `ImportService.import_file(...)` now allows bulk replace for `JSON` imports even under `ImportPolicy.CURRENT_RATE`, preserving debt-linked restore flows through the fast SQLite replace path
- `import_full_backup_from_json(...)` remains the primary low-level backup parser and now returns the structured `ImportedBackupData` object explicitly in tests/docs
- `import_backup(...)` remains available only as a deprecated compatibility wrapper over `import_full_backup_from_json(...)`

### Fixed

- `SQLiteStorage.initialize_schema()` now pre-adds `records.related_debt_id` for pre-`1.9.0` databases before applying the full schema, preventing startup/migration failures when debt indexes are created
- Backup JSON debt-payment parsing now handles empty `record_id` values more cleanly during import validation

### Tests

- Added regression coverage for pre-`1.9.0` SQLite schema bootstrap compatibility, deprecated backup-wrapper behavior, structured backup import results, and `CURRENT_RATE` JSON bulk replace with debts/debt payments

### Docs

- Updated `README.md` and `README_EN.md` for `v1.9.1`, the legacy/deprecated backup helper split, `ImportedBackupData`, and pre-schema compatibility for `related_debt_id`
- Documented that PDF export dependencies are now optional: base install uses `requirements.txt`, while PDF support can be added via `requirements-pdf.txt` or `pip install .[pdf]`

No breaking changes.

---

## [1.9.0] - 2026-04-02

### Added

- Added the `Debts` tab with debt/loan creation, payment registration, write-off, close, delete, history, and progress visualization
- Added debt domain models, SQLite tables, repository/service/use-case/controller flows, and dedicated GUI/runtime test coverage
- Full backup/import/migration pipelines now support `debts` and `debt_payments`
- Audit engine now includes `debt_balance_integrity`
- XLSX/PDF report export now includes debt summary sections when debts overlap the report period

### Changed

- Net worth calculations now account for open debts and loans
- Reports monthly summary now correctly extends from `Period` start to the current month when `Period end` is empty
- Debt report export is wallet-aware for wallet-filtered reports
- Legacy backup JSON import helpers remain available, but `ImportService.import_file(...)` is now the documented primary app-level import path
- Debt deletion in the GUI now explicitly warns that linked cashflow records and wallet balances are preserved

### Fixed

- Fixed several debt-flow data integrity issues around ID renormalization and linked record deletion
- Fixed GUI full-backup export so user-triggered backups include `debts` and `debt_payments`
- Fixed startup JSON/technical backup sync to account for SQLite WAL/SHM activity and avoid stale empty exports
- Fixed Settings tab initialization crash caused by invalid `Treeview` anchor configuration
- Fixed debt progress bar rendering for small or evenly split paid/write-off states

### Tests

- Added/updated regression coverage for debt domain, debt service, debt controller, debts tab, report controller, backup/import/export, audit, and runtime storage paths

### Docs

- Updated `README.md` and `README_EN.md` for the `Debts` tab, debt-aware reports/net worth, backup/import semantics, and import API roles
- Clarified import API roles: `ImportService.import_file(...)` is the primary app-level import path, while `gui.importers` / `import_full_backup_from_json(...)` remain legacy-compatible helpers

No breaking changes.

---

## [1.8.2] - 2026-03-29

### Added

- JSON full backup now includes `budgets` alongside records, mandatory expenses, distribution structure, and frozen snapshots
- `FinanceService` / `BudgetService` / `FinancialController` now expose `replace_budgets(...)` for full-backup restore flows

### Changed

- Full-backup import and JSON -> SQLite migration now restore budgets in addition to distribution data
- Startup maintenance was split from repository bootstrap so the GUI can defer heavy post-startup work until after the main window appears
- `FinancialApp` now builds tabs lazily and runs deferred startup sync after the first UI paint, reducing startup blocking
- Operations and Settings refresh paths now also trigger full cross-tab refresh where needed
- Analytics Dashboard net worth now respects the selected period end date (`To`) instead of always using the current balance
- `backup.py` loads budget/distribution services lazily to reduce import-time coupling

### Tests

- Added coverage for budget export/import in full backup, budget restore in JSON -> SQLite migration, runtime JSON restore, and deferred startup maintenance paths

### Docs

- Updated `README.md` and `README_EN.md` for budgets in full backup, deferred startup maintenance, Analytics Dashboard date semantics, and the expanded import/export API

No breaking changes.

---

## [1.8.1] - 2026-03-24

### Fixed

- Restored legacy transfer-row parsing in `services/import_parser.py` for `ImportPolicy.LEGACY`
- Restored export of orphan/unlinked transfer aggregates in tabular CSV/XLSX data export
- Preserved source record order during post-import ID normalization while keeping deterministic transfer ID remapping
- GUI full-backup export now writes correct snapshot metadata with `meta.storage="sqlite"`

### Changed

- Full-backup import and JSON -> SQLite migration now reject malformed `distribution_items` / `distribution_subitems` instead of silently skipping broken structure payloads
- Tooltip positioning logic was extracted and hardened for multi-monitor layouts with negative window origins
- Backup/export/import docs were updated to reflect distribution structure restore, strict backup validation, and GUI backup metadata

### Tests

- Added regression coverage for legacy transfer parsing, orphan transfer export, tooltip geometry, strict distribution-structure validation, GUI backup metadata, and deterministic import ID normalization

No breaking changes.

---

## [1.8.0] - 2026-03-24

### Added

- Added the Distribution System with persisted `distribution_items` and `distribution_subitems`
- Added `domain/distribution.py` models and `services/distribution_service.py` for CRUD, validation, and monthly cashflow allocation
- Added a new `Distribution` tab between `Budget` and `Settings` for structure editing and period-based distribution review
- Added frozen `distribution_snapshots` with `auto_fixed` support for fixed month rows in JSON backup/import
- Added `tests/test_distribution_service.py` and schema/runtime coverage for the new tables and snapshot flows

### Changed

- Main notebook order is now `Infographics | Operations | Reports | Analytics | Budget | Distribution | Settings`
- Distribution calculations reuse existing minor-unit SQL helpers so the new major feature stays compatible with `v1.7.2`-`v1.7.4` money precision fixes
- Startup now auto-freezes closed distribution months before export, while background JSON export skips repeated auto-freeze
- Full JSON backup export now writes atomically via temp file + replace and can restore distribution snapshots on import

### Tests

- Added service-level coverage for distribution CRUD, validation, monthly net-income calculation, history ranges, snapshot restore, and auto-fixed month protection

### Docs

- Updated `README.md` and `README_EN.md` for the Distribution tab, snapshot-aware backup/import, and atomic JSON export behavior

No breaking changes.

---

## [1.7.4] - 2026-03-23

### Added

- Added shared GUI support modules for import flow, Operations refresh logic, and Settings audit dialogs
- Added grouped report export for summary-by-category view in `CSV`, `XLSX`, and `PDF`
- Added `services/currency_support.py` to normalize wallet balances and timeline initial balances to KZT

### Changed

- Reports summary now shows wallet-specific balances when a wallet filter is selected
- `BalanceService`, `TimelineService`, `GenerateReport`, `CalculateWalletBalance`, and `SoftDeleteWallet` now support multi-currency wallet initial balances via `CurrencyService`
- Budget tab now exposes `Include mandatory` directly in the table and refreshes after related operations/settings changes
- SQLite repository now resolves records and mandatory expenses directly by row/id and supports indexed transfer lookup
- JSON backup pruning now honors `keep_last=0` by skipping backup creation and removing matching retained files
- Batch budget result calculation now uses a single SQL aggregation query for current spend
- `PDF`/`XLSX` grouped category sections are skipped when they would only duplicate a single-category filtered report

### Tests

- Added coverage for multi-currency wallet initial balances in balance, timeline, report, and wallet use cases
- Added coverage for batch budget calculations, mandatory-expense budget inclusion, grouped export behavior, and backup pruning with `keep_last=0`

### Docs

- Updated `README.md` and `README_EN.md` for grouped report export, budget refresh behavior, multi-currency balance analytics, and the new helper modules

No breaking changes.

---

## [1.7.3] - 2026-03-23

### Added

- Excel exports now apply readability styling: colored headers, highlighted totals, `freeze_panes`, `auto_filter`, auto-width columns, and numeric amount cells
- Analytics Dashboard now includes an `ⓘ` tooltip explaining the displayed metrics

### Changed

- `Analytics` replaces annualized expenses with `Year expense` in the Dashboard
- `Cost per day/hour/minute` is now derived from year-to-date expenses instead of annualized burn rate
- `FinancialController` adds `get_year_expense(...)` and removes `get_average_annual_expenses(...)`
- Wallets refresh after editing a selected record in `gui/tabs/operations_tab.py`

### Tests

- Updated `tests/test_analytics_tab.py` for year-to-date expense and time-cost calculations
- Extended `tests/test_excel.py` to cover styled XLSX exports and numeric cell values

### Docs

- Updated `README.md` and `README_EN.md` to document the Analytics metric changes and improved XLSX export formatting

No breaking changes.

---

## [1.7.2] - 2026-03-22

### Added

- Expanded support for date validation in `validation.py` (dates are now rejected if they are earlier than UNIX time)
- After deleting an entry, wallets are updated

### Changed

- `gui/tabs/settings_tab.py` restores the `Refresh` button in the wallet frame

### Tests

- 2 scenarios in `tests/test_validation.py` covering date validation before UNIX time

### Docs

- Updated `README.md` and `README_EN.md` to describe the new date validation rules

---

## [1.7.1] - 2026-03-21

### Added

- Global status bar at the bottom of the main window with an `Online` toggle and runtime currency status
- `CurrencyService.set_online(bool)`, `CurrencyService.is_online`, `CurrencyService.last_fetched_at`, and `CurrencyService.refresh_rates()`
- `FinancialController` online-mode helpers with persistent `schema_meta["online_mode"]`
- `tests/test_online_mode.py` covering runtime online/offline switching scenarios

### Changed

- Saved online mode is restored on application startup without requiring a restart
- Currency status text refreshes periodically so the last update timestamp stays current
- Online-mode switching no longer blocks the GUI while exchange rates are being fetched in the background

### Docs

- Updated `README.md` and `README_EN.md` to describe the new status bar and online toggle

No breaking changes.

---

## [1.7.0] - 2026-03-21

### Added

- Budget System with persistent `budgets` table, overlap-safe date ranges, `limit_base_minor`, and `include_mandatory`
- `domain/budget.py` with `Budget`, `BudgetResult`, `BudgetStatus`, `PaceStatus`, and pace computation helpers
- `services/budget_service.py` for budget CRUD, spend aggregation, overlap checks, and category suggestions
- New Budget tab between Analytics and Settings with creation form, Treeview summary, and pace-aware progress canvas
- Budget use cases and controller delegation methods for create/list/delete/update/result flows
- Distinct income / expense / mandatory-expense category helpers in `services/metrics_service.py`
- `tests/test_budget_service.py` plus schema contract coverage for the new table/indexes

### Changed

- `gui/tabs/operations_tab.py` category inputs now use editable `ttk.Combobox` widgets with suggestions that switch by operation type
- Inline category editing in `Operations` now uses category-specific `Combobox` suggestions for income / expense / mandatory records
- `gui/tabs/settings_tab.py` restores the `Refresh` button in the mandatory expenses action bar
- `Add to Records` now validates empty selection early and shows a clearer error dialog instead of proceeding without a selected template
- SQLite schema initialization now creates the `budgets` table automatically for existing and new databases

### Tests

- 19 scenarios in `tests/test_budget_service.py` covering CRUD, overlap detection, pace states, include_mandatory flag, transfer exclusion, category queries, and precision with minor units.

### Docs

- Updated `README.md` and `README_EN.md` to document the budget system and its features

No breaking changes.

---

## [1.6.0] - 2026-03-19

### Added

- Precise money helpers in `utils/money.py` for quantization, minor units, and canonical FX-rate formatting
- SQL helper expressions in `services/sqlite_money_sql.py` for minor-unit based sums and signed money calculations
- Precision columns in SQLite schema: `*_minor` for money and `rate_at_operation_text` for exchange rates

### Changed

- SQLite storage/repository now persist and read money values through dual representation: `REAL` + exact minor units
- Existing SQLite databases are auto-migrated/backfilled with precision columns on startup
- Migration, import, backup, and analytics flows now use quantized money/rate helpers instead of raw float arithmetic
- Balance, metrics, and timeline analytics now aggregate through minor-unit SQL expressions to reduce rounding drift

### Tests

- Extended `tests/test_migrate_json_to_sqlite.py` to verify `*_minor` and `rate_at_operation_text` migration payload
- Added Excel import coverage for quantized `existing_initial_balance` in `tests/test_excel.py`

### Docs

- Updated `README.md` and `README_EN.md` to document the precision model and new helper modules

No breaking changes.

---

## [1.5.1] - 2026-03-18

### Added

- Reports UI refactor: a dedicated `ReportsController` + `services/report_service.py` DTO helpers
- Tooltips and shared record kind colors for Treeviews (`gui/tooltip.py`, `gui/record_colors.py`)
- Lazy SQLite → JSON export on startup (skips when `data.json` is up-to-date; may run in background for large DB)

### Changed

- Reports tab now supports grouped drill-down via double-click and a `Back` button
- Summary totals can be switched between fixed-rate and current-rate mode (`Totals mode`)
- Operations list migrated from Listbox to Treeview with sortable columns and kind-based coloring
- Remove `prettytable` dependency and deprecated Report table helpers (`as_table`, `monthly_income_expense_table`)

### Tests

- Add/extend export contract coverage for CSV/XLSX reports and mandatory templates (`tests/test_csv.py`, `tests/test_excel.py`)
- Add bootstrap/backup coverage for SQLite → JSON export and backup pruning (`tests/test_bootstrap_backup.py`)

### Docs

- Update `README.md` and `README_EN.md` to match the new Reports/Operations UI and lazy export behavior

No breaking changes.

---

## [1.5.0] - 2026-03-15

### Added

- `Analytics` tab in the main Notebook (between Reports and Settings)
- Dashboard section: net worth (KZT), savings rate (%), burn rate (KZT/day)
- Net worth timeline chart (line chart on `tk.Canvas`, monthly granularity)
- Category Breakdown: spending and income Treeviews + expenses pie chart on `tk.Canvas`
- Monthly Report: Treeview with income, expenses, cashflow, savings rate per month
- Period filter (`From` / `To`, `YYYY-MM-DD`) with `Refresh` button
- Positive/negative cashflow rows colored green/red in Monthly Report

### Fixed

- Wallet lists/menus now refresh after operations that change wallets/data (GUI)

### Tests

- Added `tests/test_analytics_tab.py` with 8 headless scenarios (service-level)

### Docs

- Updated `README.md` and `README_EN.md` to document the Analytics tab

No breaking changes.

---

## [1.4.3] - 2026-03-15

- `MetricsService` in `services/metrics_service.py` — read-only financial metrics service (live SQL aggregates; no intermediate storage)
- `CategorySpend` and `MonthlySummary` frozen dataclasses as result types
- Metrics methods:
  `get_savings_rate`, `get_burn_rate`, `get_spending_by_category`, `get_income_by_category`,
  `get_top_expense_categories`, `get_monthly_summary`
- `RunMetrics` use case in `app/use_cases.py`
- Metrics delegation methods in `FinancialController`:
  `get_savings_rate`, `get_burn_rate`, `get_spending_by_category`, `get_income_by_category`,
  `get_top_expense_categories`, `get_monthly_summary`

### Tests

- Added `tests/test_metrics_service.py` with scenarios covering empty DB, transfer exclusion,
  limits, division-by-zero safety, and read-only guarantee.

### Docs

- Updated `README.md` and `README_EN.md` to mention Metrics Engine and the enhanced startup notification.

No breaking changes.

---

## [1.4.2] - 2026-03-14

### Added

- Mandatory auto‑pay now displays a detailed informational GUI message on startup when payments are applied.
- The message includes a list of created mandatory expenses with category, amount (KZT) and date for improved transparency.

### Changed

- `ApplyMandatoryAutoPayments` use case now returns a list of created `MandatoryExpenseRecord` objects instead of a simple count.
- `FinancialController.apply_mandatory_auto_payments()` adapted to return the list.
- GUI startup logic in `tkinter_gui.py` builds a user‑friendly summary from the returned records.

### Tests

- Existing auto‑pay scenarios in `tests/test_mandatory_ux.py` updated.
- All modified modules (`use_cases.py`, `controllers.py`, `tkinter_gui.py`) compile without syntax errors.
- No regression introduced; test suite passes.

### Docs

- Updated `README.md` and `README_EN.md` to mention the enhanced startup notification.

No breaking changes.

---

## [1.4.1] - 2026-03-14

### Added

- Mandatory auto-pay now supports all periods: `daily`, `weekly`, `monthly`, `yearly` (anchored by template `date`)
- Mandatory templates: wallet dropdown on create, plus inline editing of `wallet` and `period` after creation
- Operations tab inline edit: update `date` and `wallet` in addition to `amount_base`, `category`, and optional `description`

### Changed

- Transfers are protected from inline edits when the selected record has category `"Transfer"` (in addition to `transfer_id` linkage)

### Tests

- Extended `tests/test_mandatory_ux.py` with auto-pay scenarios for all periods
- Added record inline edit coverage for wallet/date updates

### Docs

- Updated `README.md` and `README_EN.md`

No breaking changes.

---

## [1.4.0] - 2026-03-13

### Added

- Timeline Engine: read-only analytical service for historical net worth and cashflow
- `TimelineService` in `services/timeline_service.py` with 3 methods:
  `get_net_worth_timeline` — net worth per month via SQL window function
  `get_monthly_cashflow` — income/expenses/cashflow per month with optional date range
  `get_cumulative_income_expense` — running totals for income and expenses
- `MonthlyNetWorth`, `MonthlyCashflow`, `MonthlyCumulative` frozen dataclasses as result types
- `RunTimeline` use case in `app/use_cases.py`
- Timeline delegation methods in `FinancialController`:
  `get_net_worth_timeline`, `get_monthly_cashflow`, `get_cumulative_income_expense`

### Changed

- "Transfer" category excluded from charts (expenses by category, daily/monthly cashflow)

### Removed

- Remove obsolete log messages about the selected repository

### Tests

- Added `tests/test_timeline_service.py` with 12 scenarios covering empty DB behavior,
  initial balance baseline, transfer neutrality for net worth, transfer exclusion in cashflow,
  date filters, and read-only guarantee
- Extended `tests/test_charting.py` with scenarios for covering aggregated data with the excluded "Transfer" category

### Docs

- Updated `README.md` and `README_EN.md` with Timeline Engine description

No breaking changes.

---

## [1.3.3] - 2026-03-11

### Added

- `date` field (optional, YYYY-MM-DD) and `auto_pay` flag in mandatory expense templates
- Inline editing of `amount_base` and `date` templates directly in the settings list
- `Description` field in the `Add operation` form (Operations tab)
- `Description` field in the `Transfer` form (Operations tab)
- `date` support for `mandatory_expenses` in CSV/XLSX import-export and JSON backup/export flows
- Coloring of text in the list of operations by type income/expense/mandatory/transfer

### Changed

- The `Edit Amount KZT` button has been renamed to `Edit` (Operations tab)
- `auto_pay` is calculated automatically from `date`: non-empty date → `auto_pay=True`
- The form for adding a mandatory expense has been expanded with the `Date (optional)` field
- `data.json` startup export now keeps `mandatory_expenses.date` instead of dropping it
- Startup JSON backups are now pruned via `JSON_BACKUP_KEEP_LAST`

### Removed

- `mandatory_expense_no_date` check removed from Data Audit Engine (date field is now valid)

### Tests

- Added `tests/test_mandatory_ux.py` covering template dates, inline edits, and auto-pay behavior
- Added `tests/test_schema_contracts.py` to enforce schema/domain period constraints
- Updated `tests/test_audit_engine.py`: removed outdated assertions, check count = 10
- Added round-trip coverage for `mandatory_expenses.date` in CSV/XLSX, backup JSON, startup export, and JSON -> SQLite migration

### Docs

- Updated `README.md` and `README_EN.md`

No breaking changes.

---

## [1.3.2] - 2026-03-09

### Added

- Balance Engine: read-only analytical service for derived financial state
- `BalanceService` in `services/balance_service.py` with 6 methods:
  `get_wallet_balance`, `get_wallet_balances`, `get_total_balance`,
  `get_cashflow`, `get_income`, `get_expenses`
- `WalletBalance` and `CashflowResult` frozen dataclasses as result types
- Balance delegation methods in `FinancialController`:
  `get_wallet_balance`, `get_wallet_balances`, `get_total_balance`,
  `get_cashflow`, `get_income`, `get_expenses`
- Index `idx_records_wallet_date` on `records(wallet_id, date)` in `db/schema.sql`

### Tests

- Add `tests/test_balance_service.py` with 13 scenarios covering wallet balance,
  historical balance, transfer neutrality, cashflow, and read-only guarantee

### Docs

- Update `README.md` and `README_EN.md` with Balance Engine description

No breaking changes.

---

## [1.3.1] - 2026-03-09

### Changed

- Removed pure schema-level duplicate checks from the Data Audit Engine
- Narrowed audit scope from 9 checks to 8 business-level checks
- Kept the audit strictly read-only

### Added

- Transfer amount alignment check between `transfers` rows and linked `expense` / `income` records
- Amount positivity check for records, transfers, and mandatory expense templates

### Tests

- Updated `tests/test_audit_engine.py`
- Audit coverage now includes 16 scenarios
- Kept commission exclusion logic and read-only guarantee coverage

### Docs

- Updated `README.md` and `README_EN.md` to reflect the refined audit scope
- Updated `CHANGELOG.md` for `v1.3.1`

No breaking changes.

---

## [1.3.0] - 2026-03-09

### Added

- Data Audit Engine: on-demand, read-only diagnostic of the SQLite database
- `AuditReport`, `AuditFinding`, `AuditSeverity` dataclasses in `domain/audit.py`
- `AuditService` in `services/audit_service.py` with 9 integrity and consistency checks:
  transfer pair integrity, orphan records, amount consistency, rate positivity,
  date validity, wallet references, currency codes, record types,
  mandatory expense date absence
- `RunAudit` use case in `app/use_cases.py`
- `run_audit()` method in `FinancialController`
- `Finance Audit` block in `Settings` tab with `Run Audit` button
- Modal audit report dialog with color-coded Errors, Warnings, and Passed sections

### Tests

- Add `tests/test_audit_engine.py` with 17 scenarios covering all checks,
  commission exclusion logic, and read-only guarantee

### Docs

- Update `README.md` and `README_EN.md` with Data Audit Engine description
  under the Settings tab section

No breaking changes.

---

## [1.2.3] - 2026-03-08

### Added

- Import Dry-run Mode: full parse and validation cycle without writing to SQLite
- `ImportResult` dataclass (`domain/import_result.py`) with fields `imported`, `skipped`, `errors`, `dry_run`; replaces bare tuple returns from `ImportService`
- Import preview dialog in `Operations` tab: displays record count, skipped rows,
  and errors before the user confirms the operation
- `dry_run: bool = False` parameter in `ImportService.import_file(...)` and `FinanceService` protocol

### Changed

- `ImportService.import_file(...)` now returns `ImportResult` instead of a plain tuple
- `Operations` tab import now executes a two-step flow: dry-run preview, user confirmation, then real import
- All callers of `import_file` updated to use `ImportResult` field access

### Tests

- Add dry-run coverage to import service and SQLite import pipeline tests
- Update import controller and runtime storage tests to use `ImportResult` field access

### Docs

- Update `README.md` and `README_EN.md` with dry-run mode description under the import section

No breaking changes.

---

## [1.2.2] - 2026-03-07

### Fixed

- Enforce strict integer validation for `wallet_id` and `transfer_id` across JSON/CSV/XLSX import paths
- Stop silent coercion of malformed IDs in import, repository loading, and legacy JSON migration flows
- Fix SQLite schema path resolution during bootstrap
- Remove direct internal storage access from bootstrap, backup, and migration code
- Preserve report metadata in `grouped_by_category()` subreports while keeping zero initial balance

### Refactor

- Add public admin/query APIs for SQLite storage and repository bootstrap operations
- Extract shared helpers from `use_cases.py` and `controllers.py` to reduce responsibility overlap
- Refactor `migrate_json_to_sqlite.py` to use public storage APIs and explicit transactions
- Extract shared CSV/XLSX tabular export helpers
- Remove redundant `sys.path` bootstrapping from entry and GUI modules

### Changed

- Strengthen SQLite constraints for currency codes and date-shaped fields
- Make snapshot metadata use `version.py` and caller-provided storage mode
- Treat `MandatoryExpenseRecord.type` consistently as `mandatory_expense`
- Align CSV/XLSX export labeling and row-building through shared helpers

### Tests

- Stabilize pytest temp-path handling for the current Windows/OneDrive workspace
- Add regression coverage for strict import ID contracts and malformed payload handling
- Add coverage for bootstrap/runtime SQLite integrity flows
- Add regression coverage for grouped report metadata preservation
- Add contract coverage for snapshot metadata and mandatory record type

### Docs

- Update `README.md` and `README_EN.md` for import validation, launch mode, report grouping, and snapshot metadata

No breaking changes.

---

## [1.2.1] - 2026-03-07

### Refactor

- Finalize SQLite as the only runtime storage backend
- Remove `USE_SQLITE` feature flag and runtime branching
- Simplify bootstrap to always initialize and validate `finance.db`
- Remove JSON runtime bootstrap and startup export flow
- Keep JSON only for import, export, backup, and migration workflows

### Changed

- Repositories now use SQLite runtime storage by default
- Import pipeline now commits application data through SQLite transactions only
- Transfer-linked records now cascade on SQLite transfer deletion

### Tests

- Add SQLite runtime coverage for bootstrap initialization
- Add integration coverage for JSON/CSV/XLSX import into SQLite
- Add rollback regression coverage to ensure failed imports do not mutate the database
- Add cascade-delete verification for transfers and linked records

### Docs

- Update `README.md` and `README_EN.md` to describe SQLite as primary runtime storage
- Add release draft for tag `Finalize SQLite storage backend`

This release removes the legacy dual-backend runtime model.

---

## [1.2.0] - 2026-03-05

### Added

- Immutable snapshot backup format
- SHA256 integrity validation
- Readonly import protection
- Force override mode

### Security

- Prevent import of modified backups
- Guarantee transactional rollback on integrity failure

### Docs

- Update `README.md` and `README_EN.md` with new backup format details
- Document the force override mode and integrity validation process

---

## [1.1.3] - 2026-03-04

### Fixed

- Reject duplicate `initial_balance` rows during import (transaction aborts)
- Enforce strict positive integer `wallet_id` parsing for import rows
- Normalize imported `mandatory_expenses` template IDs to `1..N` in bulk replace path
- Reject non-finite numeric payloads (`NaN`, `inf`) in import amounts and IDs
- Remove `date` from `mandatory_expenses` schema/export payloads (CSV/XLSX/backup)
- Align JSON/SQLite repositories and migration flow to persist mandatory templates without `date`
- Restore compatibility wrappers `report_from_csv` / `report_from_xlsx` for report adapters

### Tests

- Add regression coverage for duplicate `initial_balance` handling
- Add contract test for strict `wallet_id` validation (no fractional values)
- Add coverage for mandatory template ID normalization in bulk import
- Add regression tests for overflow/non-finite numeric values in import rows

### Docs

- Update `README.md` and `README_EN.md` with new import validation rules
- Document that `mandatory_expenses` templates no longer store/export `date`

No breaking changes.

---

## [1.1.2] - 2026-03-04

### Performance

- Implement bulk import replace flow via `replace_all_for_import`
- Build records/transfers in memory and persist once for faster JSON imports
- Decouple SQLite startup cost when `USE_SQLITE=False`
- Lazy-load SQLite modules in bootstrap
- Optimize Windows file lock retry logic (`WinError 5/32`)

### Refactor

- Remove `report_from_csv` wrapper
- Simplify import pipeline integration

No breaking changes.

---

## [1.1.1] - 2026-03-02

### Removed

- Remove deprecated web frontend directory

---

## [1.1.0] - 2026-03-02

### Fixed

- Harden SQLite bootstrap integrity checks
- Restore deterministic ID normalization
- Fix transfer append ordering issues

### Stability

- Strengthen SQLite data consistency guarantees

---

## [1.0.1] - 2026-03-01

### Refactor

- Overhaul SQLite import pipeline with service architecture
- Add safety guardrails for migration consistency

---

## [1.0.0] - 2026-03-01

### Added

- SQLite as primary storage
- Storage abstraction layer
- Robust bootstrap process
- JSON-to-SQLite migration support

### Changed

- Application storage backend migrated from JSON to SQLite

This marks the beginning of the SQL era.

---

## [0.6.0] - 2026-02-28

### Added

- Storage abstraction layer
- JSON-to-SQLite migration foundation

### Stability

- Final stable JSON-based release

This is the last stable release before SQLite migration.

---

## [0.5.0] - 2026-02-19

### Added

- Wallet transfers with commissions
- Net worth calculation
- Wallet domain model

---

## [0.2.0] - 2026-01-20

### Changed

- Replace CLI with multi-window Tkinter GUI

---

## [0.1.0] - 2026-01-20

### Added

- Initial CLI-based financial accounting prototype
- Layered backend structure (domain, application, infrastructure)
