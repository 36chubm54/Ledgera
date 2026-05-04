# Architecture Guide

This document keeps the technical map of the project outside the compact release-oriented `README.md` / `README_EN.md`.

It is intended for contributors who need to understand where logic lives, how the runtime is composed, and which modules usually change together.

## 1. System Overview

The application is a Tkinter desktop app backed by SQLite at runtime.

At a high level:

1. `main.py` starts the GUI
2. `bootstrap.py` validates and prepares runtime storage
3. `gui/tkinter_gui.py` builds the application shell and tabs
4. `gui/controllers.py` exposes app-level operations to the UI
5. `app/use_cases.py` and `services/*` implement business flows
6. `infrastructure/sqlite_repository.py` and `storage/sqlite_storage.py` persist runtime data

Supported business areas include:

- records, transfers, wallets
- budgets
- debts and loans
- monthly distribution
- strategic assets and goals
- runtime UI preferences, theming, and localization
- desktop shell layout and themed widget composition
- analytics, reports, and audit
- import / export / backup / migration

## 2. Layer Map

| Layer | Purpose | Main modules |
| --- | --- | --- |
| `domain` | Immutable entities, enums, validation rules, report DTOs | `records.py`, `wallets.py`, `budget.py`, `debt.py`, `asset.py`, `goal.py`, `reports.py`, `audit.py`, `validation.py` |
| `app` | Use cases, application contracts, and orchestration | `use_cases.py`, `use_case_support.py`, `finance_service.py`, `record_service.py`, `services.py` |
| `services` | Focused business subsystems and read-only engines | `import_service.py`, `audit_service.py`, `balance_service.py`, `metrics_service.py`, `timeline_service.py`, `budget_service.py`, `debt_service.py`, `distribution_service.py`, `asset_service.py`, `goal_service.py`, `dashboard_service.py` |
| `infrastructure` | Runtime repository implementation | `sqlite_repository.py`, `repositories.py` |
| `storage` | Low-level persistence adapters and schema bootstrap | `sqlite_storage.py`, `json_storage.py`, `base.py` |
| `gui` | Tkinter presentation layer | `tkinter_gui.py`, `controllers.py`, `tabs/*`, `exporters.py`, `importers.py`, `tooltip.py`, `logging_utils.py`, `ui_theme.py`, `i18n.py`, `ui_dialogs.py` |
| `utils` | Format-specific helpers and shared technical helpers | `backup_utils.py`, `import_core.py`, `csv_utils.py`, `excel_utils.py`, `pdf_utils.py`, `money.py`, `charting.py`, `debt_report_utils.py`, `tabular_utils.py` |
| `tests` | Regression, contract, and integration-like coverage | `test_*` modules across all subsystems |

## 3. Key Runtime Flows

### 3.1 Startup

- `main.py` launches the app
- `bootstrap.py` prepares runtime SQLite state
- `storage/sqlite_storage.py` initializes schema and compatibility migrations
- `gui/tkinter_gui.py` creates the main window and tabs
- post-startup maintenance may run after the first window paint

Important startup concerns:

- SQLite integrity and schema readiness
- JSON export/backup synchronization
- OneDrive-aware export timing and WAL/SHM coherence
- applying saved runtime theme/language preferences before shell build
- applying shell-wide theme styling to cards, tables, canvases, and popdown controls
- optional currency refresh
- auto-application of mandatory payments
- deferred GUI work and safe `after(...)` scheduling

### 3.2 Creating or Editing Financial Data

Typical path:

`GUI tab -> FinancialController -> use case / service -> SQLiteRecordRepository -> SQLiteStorage`

Examples:

- operations and transfers are initiated from `gui/tabs/operations_tab.py`
- debts/loans are initiated from `gui/tabs/debts_tab.py`
- assets/goals are initiated from `gui/tabs/dashboard_tab.py`
- theme/language preference changes are initiated from the app shell and persisted via `gui/controllers.py`

### 3.3 Reports and Analytics

There are three main read-only analytics layers:

- `BalanceService` — balances and net worth
- `MetricsService` — rates, category summaries, month summaries
- `TimelineService` — month-by-month historical aggregates

Report UI uses:

- `gui/tabs/reports_tab.py`
- `gui/tabs/reports_controller.py`
- `services/report_service.py`

Export uses:

- `gui/exporters.py`
- `utils/csv_utils.py`
- `utils/excel_utils.py`
- `utils/pdf_utils.py`

### 3.4 Import / Backup / Migration

Main application import entry:

- `FinancialController.import_records(...)`
- `services.import_service.ImportService.import_file(...)`
- `FinanceService.get_import_capabilities()`

Low-level backup helpers:

- `utils.backup_utils.export_full_backup_to_json(...)`
- `utils.backup_utils.import_full_backup_from_json(...)`

Migration entry:

- `migrate_json_to_sqlite.py`

Important details:

- dry-run and real import share the same validation pipeline
- readonly snapshots require `force=True`
- JSON full backups can contain extended runtime entities such as budgets, debts, assets, goals, and distribution payloads
- partial `JSON` imports are section-aware and should not treat omitted sections as implicit deletion
- debt-aware imports must preserve `records.related_debt_id` and `debt_payments.record_id` links across normalization and bulk replace paths
- compatibility logic in `storage/sqlite_storage.py` protects older SQLite databases during schema initialization
- import rollback logic lives close to GUI transaction orchestration in `gui/controller_import_support.py`

## 4. Subsystem Map

### 4.1 Records / Wallets / Transfers

Core modules:

- `domain/records.py`
- `domain/wallets.py`
- `domain/transfers.py`
- `infrastructure/sqlite_repository.py`
- `storage/sqlite_storage.py`

These form the base event history used by reports and analytics.

As of `v1.12.0`, this area also owns the most sensitive import/relink logic:

- repository-level bulk replacement through `replace_records_and_transfers(...)`
- preservation of explicit imported IDs where required
- remapping of debt-linked records during import normalization

### 4.2 Budgets

Core modules:

- `domain/budget.py`
- `services/budget_service.py`
- `gui/tabs/budget_tab.py`

Budgets are date-ranged category limits with live execution tracking.

### 4.3 Debts and Loans

Core modules:

- `domain/debt.py`
- `services/debt_service.py`
- `gui/tabs/debts_tab.py`
- `utils/debt_report_utils.py`

This subsystem links debt payments to cashflow records and affects net worth and report exports.

### 4.4 Distribution

Core modules:

- `domain/distribution.py`
- `services/distribution_service.py`
- `gui/tabs/distribution_tab.py`

This subsystem calculates monthly net-income allocation and supports frozen snapshot rows.

### 4.5 Assets / Goals / Dashboard

Core modules:

- `domain/asset.py`
- `domain/goal.py`
- `domain/dashboard.py`
- `services/asset_service.py`
- `services/goal_service.py`
- `services/dashboard_service.py`
- `gui/tabs/dashboard_tab.py`

This subsystem adds a strategic wealth-management layer above the transactional ledger.

### 4.6 Audit

Core modules:

- `domain/audit.py`
- `services/audit_service.py`

Audit is intentionally read-only and validates runtime integrity without mutating data.

### 4.7 Import / Backup Reliability

Core modules:

- `services/import_parser.py`
- `services/import_service.py`
- `gui/controller_import_support.py`
- `utils/backup_utils.py`
- `backup.py`
- `bootstrap.py`
- `infrastructure/repositories.py`

This subsystem is responsible for:

- payload parsing and `json_sections_present` awareness
- capability negotiation via `ImportCapabilities`
- rollback-safe import transactions
- corruption quarantine and save-failure handling for JSON repositories
- startup export discipline for SQLite, especially on OneDrive-managed paths

### 4.8 Runtime UI Preferences

Core modules:

- `gui/ui_theme.py`
- `gui/i18n.py`
- `gui/tkinter_gui.py`
- `gui/ui_dialogs.py`
- `gui/controllers.py`

This subsystem is responsible for:

- light/dark theme palettes and runtime palette switching
- persisted language/theme preferences stored in SQLite schema metadata
- live rebuilding of shell strings and theme-aware widgets/dialogs
- keeping Tk styling, localized strings, and shell state synchronized during runtime preference changes

As of `v1.14.0`, it also owns the shared desktop-shell design primitives:

- spacing tokens and card-style section composition
- Treeview zebra-striping and palette-aware list/table styling
- shell-level theme application for `Canvas` and Combobox dropdown widgets

### 4.9 Desktop Shell Layout

Core modules:

- `gui/tkinter_gui.py`
- `gui/ui_theme.py`
- `gui/tabs/operations_tab.py`
- `gui/tabs/debts_tab.py`
- `gui/tabs/settings_tab.py`

This subsystem is responsible for:

- composing the main shell, status area, notebook, and tab containers
- keeping tab layouts visually consistent through shared card helpers and spacing tokens
- coordinating shell rebuilds when runtime theme/language state changes
- applying redesign conventions across form-heavy and table-heavy tabs

### 4.10 Hotkeys

Core modules:

- `gui/hotkeys.py`
- `gui/tkinter_gui.py`
- `gui/tabs/operations_tab.py`
- `gui/tabs/reports_tab.py`
- `gui/tabs/analytics_tab.py`
- `gui/tabs/budget_tab.py`
- `gui/tabs/debts_tab.py`

`gui.hotkeys` is the single registration point for application-wide shortcuts. `register_hotkeys(app)` binds the global sequences once per `FinancialApp` instance, while handlers resolve the active tab and the latest tab binding objects at event time.

Important design rules:

- hotkeys are bound at the shell level, not inside individual tabs
- actions are executed only when the matching tab is active
- destructive or input-conflicting shortcuts also check current focus and skip when focus is inside `Entry`, `Combobox`, or `Text`
- the design is compatible with lazy tab build and `_reset_tab_bindings()` because handlers read current `app._*_bindings` references on each keypress

## 5. Data Model Overview

Main SQLite tables:

- `wallets`
- `records`
- `transfers`
- `mandatory_expenses`
- `budgets`
- `debts`
- `debt_payments`
- `distribution_items`
- `distribution_subitems`
- `distribution_snapshots`
- `assets`
- `asset_snapshots`
- `goals`

Important data-model notes:

- money values often use dual storage: human-readable values plus exact `*_minor`
- records may reference `transfer_id` and `related_debt_id`
- debt, asset, and goal data affect read-only wealth calculations
- schema/bootstrap compatibility must be preserved for older SQLite databases
- full-backup payloads may omit sections intentionally, so import code must distinguish "section absent" from "section present but empty"

## 6. Change Patterns

When adding a new domain concept, the usual sequence is:

1. Add immutable domain models and validation
2. Extend SQLite schema and storage/repository mapping
3. Add service and/or use case logic
4. Expose it through `FinancialController`
5. Wire it into a tab or export flow
6. Add tests across domain, service, controller, and integration paths
7. Update `README.md`, `README_EN.md`, and `CHANGELOG.md`

When changing import/export behavior, review together:

- `services/import_service.py`
- `services/import_parser.py`
- `gui/controller_import_support.py`
- `utils/backup_utils.py`
- `gui/exporters.py`
- `migrate_json_to_sqlite.py`
- `infrastructure/repositories.py`
- `storage/sqlite_storage.py`
- the related contract tests

When changing GUI startup/deferred work, review together:

- `gui/tkinter_gui.py`
- `gui/ui_theme.py`
- `gui/i18n.py`
- `gui/logging_utils.py`
- `gui/ui_helpers.py`
- `bootstrap.py`
- Tk-related regression tests

## 7. Packaging Notes

Base runtime dependencies live in `requirements.txt`.

Optional PDF support is separated into:

- `requirements-pdf.txt`
- `pyproject.toml` optional dependency group `pdf`

This keeps the default install lighter while preserving PDF export as an add-on.

## 8. Where to Start

If you are new to the codebase:

- start with `README.md`
- open `gui/controllers.py`
- inspect `app/use_cases.py`
- then move into the service or tab that matches your feature area

For data-format issues:

- start with `services/import_service.py`
- then inspect `gui/controller_import_support.py`, `utils/backup_utils.py`, and `migrate_json_to_sqlite.py`

For net-worth/report issues:

- start with `services/balance_service.py`
- then `services/timeline_service.py`, `services/report_service.py`, and report exporters

For runtime durability issues:

- inspect `infrastructure/repositories.py`
- then `storage/sqlite_storage.py`, `backup.py`, and `bootstrap.py`
