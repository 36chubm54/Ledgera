# Architecture Guide

This document keeps the technical map of the project outside the compact release-oriented `README.md` / `README_EN.md`.

It is intended for contributors who need to understand where logic lives, how the runtime is composed, and which modules usually change together.

## 1. System Overview

The application is a Tkinter desktop app backed by SQLite at runtime.

At a high level:

1. `main.py` starts the GUI
2. `bootstrap.py` validates and prepares runtime storage
3. `gui/tkinter_gui.py` builds the application shell and delegates runtime/startup/status/tab lifecycle work
4. `gui/controllers.py` exposes app-level operations to the UI
5. `app/use_cases.py`, `app/use_cases_*`, and `services/*` implement business flows
6. `infrastructure/sqlite_repository.py` and `storage/sqlite_storage.py` persist runtime data

Supported business areas include:

- records, transfers, wallets
- tags and record-tag assignments
- budgets
- debts and loans
- monthly distribution
- strategic assets and goals
- runtime UI preferences, theming, and localization
- desktop shell layout and themed widget composition
- analytics, reports, and audit
- import / export / backup / migration

## 2. Layer Map

| Layer            | Purpose                                                  | Main modules                                                                                                                                                                                                                                                                                                                                                                                                  |
| ---------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `domain`         | Immutable entities, enums, validation rules, report DTOs | `records.py`, `tags.py`, `wallets.py`, `budget.py`, `debt.py`, `asset.py`, `goal.py`, `reports.py`, `audit.py`, `validation.py`                                                                                                                                                                                                                                                                               |
| `app`            | Use cases, application contracts, and orchestration      | `use_cases.py`, `use_cases_records.py`, `use_cases_assets.py`, `use_cases_mandatory.py`, `use_cases_analytics.py`, `use_cases_planning.py`, `repository.py`, `import_support.py`, `preferences_service.py`, `audit_runner.py`, `use_case_support.py`, `finance_service.py`, `record_service.py`, `services.py`                                                                                                |
| `services`       | Focused business subsystems and read-only engines        | `import_service.py`, `import_models.py`, `import_payload_support.py`, `import_replace_support.py`, `import_execution_support.py`, `import_mandatory_support.py`, `audit_service.py`, `balance_service.py`, `metrics_service.py`, `timeline_service.py`, `budget_service.py`, `debt_service.py`, `distribution_service.py`, `asset_service.py`, `goal_service.py`, `dashboard_service.py`, `report_service.py` |
| `infrastructure` | Runtime repository implementation                        | `sqlite_repository.py`, `repositories.py`                                                                                                                                                                                                                                                                                                                                                                     |
| `storage`        | Low-level persistence adapters and schema bootstrap      | `sqlite_storage.py`, `json_storage.py`, `base.py`                                                                                                                                                                                                                                                                                                                                                             |
| `gui`            | Tkinter presentation layer                               | `tkinter_gui.py`, `controllers.py`, `runtime_coordinator.py`, `startup_coordinator.py`, `status_bar_coordinator.py`, `tab_lifecycle.py`, `tabs/*`, `exporters.py`, `importers.py`, `tooltip.py`, `logging_utils.py`, `ui_theme.py`, `i18n.py`, `ui_dialogs.py`                                                                                                                                                |
| `utils`          | Format-specific helpers and shared technical helpers     | `backup_utils.py`, `import_core.py`, `csv_utils.py`, `excel_utils.py`, `pdf_utils.py`, `money.py`, `charting.py`, `debt_report_utils.py`, `tabular_utils.py`                                                                                                                                                                                                                                                  |
| `tests`          | Regression, contract, and integration-like coverage      | `test_*` modules across all subsystems                                                                                                                                                                                                                                                                                                                                                                        |

Current implementation note:

- the table above describes the intended ownership boundaries
- application-side repository capabilities are now expressed through `app/repository_protocols.py`
- the desktop runtime still depends primarily on `infrastructure/sqlite_repository.py` as the only fully featured backend for preferences, audit, analytics, planning, and shell-facing workflows
- treat JSON storage and other adapters as narrower persistence backends, not as drop-in replacements for the full runtime feature set

### Runtime currency configuration

`CurrencyService` treats runtime currency/provider settings as persisted application policy layered on top of the repository-owned accounting base currency.

Current contract:

- `base_currency` remains a repository-owned concern after bootstrap
- runtime updates to `display_currency`, provider mode, provider selection, API key, auto-update, and refresh interval are persisted before the in-memory runtime is reconfigured
- failed config persistence must not leave partially applied runtime currency state in memory
- `exchange_rate_api_key` should be persisted through OS-backed secure storage rather than plaintext `currency_config.json`
- env var `FINACCOUNTING_EXCHANGE_RATE_API_KEY` remains a runtime override, but not the preferred default persistence path

## 3. Key Runtime Flows

### 3.0 Resource and runtime path ownership

The desktop runtime now distinguishes packaged read-only resources from mutable user data through a shared path contract in `app_paths.py`.

Current rules:

- packaged resources such as `gui/assets/icons`, `locales`, and `db/schema.sql` resolve from the bundle resource root
- mutable runtime files such as `finance.db`, currency config/cache, and backup output resolve from a user-scoped data directory
- in Windows packaged mode, that mutable runtime state is expected to live under `AppData`, not inside the install tree
- in Linux packaged mode, mutable runtime state is expected to live under `XDG_DATA_HOME` or `~/.local/share/FinAccountingApp`, not inside the AppImage mount, extracted bundle, or `/opt/FinAccountingApp` install tree
- dev checkouts still resolve runtime files from the source tree unless an explicit override is provided
- updater downloads are treated separately from the general source-tree dev contract and resolve to a dedicated Windows `AppData\updates` cache even in source mode

Packaging note:

- the checked-in `FinAccountingApp.spec` builds the main `PyInstaller --onedir` app bundle
- `FinAccountingApp.linux.spec` builds the Linux `PyInstaller --onedir` bundle that is then wrapped into `Ledgera-linux.AppImage` and Linux `.deb` / `.rpm` system packages
- the current Linux GUI contract distinguishes `system-package`, `AppImage`, and source runtime: `deb` / `rpm` packaged Linux stays on native `ttk.Combobox` popdowns by default with guard logic, while `AppImage` and source-mode Linux can fall back to the app-managed compatibility popup path for problematic selector flows
- Linux tag autocomplete follows the same split: `AppImage` and source-mode Linux can use the custom popup path, while `deb` / `rpm` packaged Linux, Windows, and other non-Linux runtimes stay on native `ttk.Combobox` behavior
- `migrate_json_to_sqlite.py` and `migrations/migration_002_rename_amount_kzt_to_base.py` are shipped inside that bundle as raw Python utility scripts rather than separate executable tools
- the Windows release workflow can optionally sign `FinAccountingApp.exe` and the installer if certificate secrets are configured; otherwise the release remains unsigned
- the Windows installer-facing brand is now `Ledgera`: setup artifacts are emitted as `Ledgera-<version>-setup.exe`, while the internal bundled executable remains `FinAccountingApp.exe`
- the Linux release workflow smoke-builds the AppImage and system-package paths on PRs and publishes `Ledgera-linux.AppImage`, `.deb`, and `.rpm` artifacts on tagged releases
- Linux system packages install the read-only bundle into `/opt/FinAccountingApp`, expose `/usr/bin/ledgera`, and register a desktop entry plus icon through standard system paths
- Linux package metadata is now owned by `packaging/linux/appstream_metadata.json` and validated in CI through `appstreamcli --pedantic` rather than being generated directly from release prose
- Linux package/AppStream display identity is `Ledgera`, while internal bundle/data paths remain `FinAccountingApp` for compatibility
- `GNOME Software` may still omit license details or release notes for locally installed third-party packages even when the package ships valid AppStream metadata; this has been observed to differ between Ubuntu GNOME and Fedora GNOME

### 3.0.1 Application update flow

The desktop app now has a packaged-runtime updater surface in `Settings`.

Current flow:

- `gui.tabs.settings.update_section` initiates the check and download UX
- `gui.controllers.FinancialController` exposes the thin updater facade to the UI
- `services.app_update_service.AppUpdateService` queries GitHub Releases, applies prerelease-aware release filtering, selects the runtime-matching asset, and streams the download to the updater cache
- `gui.shell.shell_window.launch_installer_and_exit(...)` performs the final installer/package handoff after user confirmation

Design rules:

- updater logic is separate from currency `auto_update`
- the running app only checks and downloads; it does not patch binaries in place
- packaged updater runtimes persist a downloaded-update state in `schema_meta` so the primary CTA can survive restart as `Install update`
- cleanup of downloaded installer/package artifacts is deferred until the next successful launch of the target-or-newer version
- Windows still delegates the real update to the installer, while packaged Linux delegates it to a terminal-launched package-manager command
- packaged Linux `.deb` / `.rpm` runtime is the only Linux environment with in-app update download/handoff support in this wave
- packaged Linux updater selects artifacts via the install-root `.linux-package-kind` marker and never guesses `.deb` vs `.rpm` heuristically
- Linux package handoff runs through a supported terminal executable and a terminal-kept-open `sudo apt install ...` / `sudo dnf install ...` command, not through `xdg-open` or direct package-manager execution in the app process
- terminal handoff now also preflights the required package manager (`apt` / `dnf`) before spawning the terminal UX
- source-mode Windows/Linux and `AppImage` remain explicit manual-release-page paths rather than pretending to support in-app installation
- stable builds ignore GitHub prerelease releases, while prerelease builds can see newer prereleases and then transition to the final stable release

### 3.1 Startup

- `main.py` launches the app
- `bootstrap.py` prepares runtime SQLite state
- `storage/sqlite_storage.py` initializes schema and compatibility migrations
- `gui/tkinter_gui.py` creates the main window shell
- `gui.startup_coordinator.DeferredStartupCoordinator` may run post-startup maintenance after the first window paint

Important startup concerns:

- SQLite integrity and schema readiness
- JSON export/backup synchronization
- OneDrive-aware export timing and WAL/SHM coherence
- applying saved runtime theme/language preferences before shell build
- applying shell-wide theme styling to cards, tables, canvases, and popdown controls
- optional currency refresh
- auto-application of mandatory payments
- early reconciliation of persisted updater install/cleanup state before the full shell build
- deferred GUI work and safe `after(...)` scheduling through `gui.runtime_coordinator.UiRuntimeCoordinator`
- eager build of `Infographics` and `Operations`, with the remaining tabs composed lazily on first activation
- online-mode status refresh through `gui.status_bar_coordinator.StatusBarCoordinator`
- lazy tab build and rebuild routing through `gui.tab_lifecycle`

### 3.2 Creating or Editing Financial Data

Typical path:

`GUI tab -> FinancialController -> use case / service -> SQLiteRecordRepository -> SQLiteStorage`

This remains the practical runtime path even after the recent contract cleanup:

- upper layers use narrower repository protocols where possible
- the main app runtime is still composed around the SQLite repository as the concrete provider of those capabilities
- contributors should read `app/repository_protocols.py` as the application-facing contract surface and `infrastructure/sqlite_repository.py` as the concrete runtime implementation behind it

Examples:

- operations and transfers are initiated through the public shim `gui/tabs/operations_tab.py`, with the real implementation living under `gui/tabs/operations/`
- debts/loans are initiated through `gui/tabs/debts_tab.py`, backed by `gui/tabs/debts/`
- assets/goals are initiated through `gui/tabs/dashboard_tab.py`, backed by `gui/tabs/dashboard/`
- theme/language preference changes are initiated from the app shell and persisted via `app.preferences_service`

### 3.3 Reports and Analytics

There are three main read-only analytics layers:

- `BalanceService` — balances and net worth
- `MetricsService` — rates, category summaries, tag coverage, month summaries
- `TimelineService` — month-by-month historical aggregates

Report UI uses:

- `gui/tabs/reports_tab.py` as the public compatibility shim
- `gui/tabs/reports/` as the real package owner for report UI/layout/render/build logic
- `gui/tabs/reports_controller.py`
- `services/report_service.py`

Export uses:

- `gui/exporters.py`
- `utils/csv_utils.py`
- `utils/excel_utils.py`
- `utils/pdf_utils.py`

Current report/export contract:

- statement-style report views and exported statement rows are ordered newest first, with `record.id` used as the same-day tie-breaker so the effective ordering contract is `date + record.id`
- export headers are localized through shared report-export i18n helpers
- base-amount columns explicitly include the actual base code, for example `Amount (KZT)` / `Сумма (KZT)`
- localized statement exports must stay compatible with the generic import parser, not only with direct `report_from_*` helpers
- Linux export popup helpers must treat app-level focus loss as a real close condition so custom popup surfaces do not survive after app switching

### Money and transfer semantics

Services that calculate income, expense, or cashflow totals must identify transfers structurally through `transfer_id`, not by checking whether the category label equals `Transfer`.

Current tag-specific behavior:

- `services/report_service.py` builds tag-aware grouped export payloads
- `services/metrics_service.py` provides tag coverage aggregates for analytics
- export helpers treat tag grouping as overlapping coverage, not as an additive partition of expenses

### 3.4 Import / Backup / Migration

Main application import entry:

- `FinancialController.import_records(...)`
- `app.import_support.run_import_transaction(...)`
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
- imported JSON/CSV/XLSX payloads should be treated as untrusted input, with file-size guardrails and explicit validation before persistence
- JSON full backups can contain extended runtime entities such as budgets, debts, assets, goals, and distribution payloads
- partial `JSON` imports are section-aware and should not treat omitted sections as implicit deletion
- debt-aware imports must preserve `records.related_debt_id` and `debt_payments.record_id` links across normalization and bulk replace paths
- JSON repositories are compatibility backends: they preserve record-tag assignments during full restore, but standalone tag metadata rollback is not a first-class runtime contract there the way it is in SQLite
- generic CSV/XLSX import is expected to accept localized report exports as statement files and strip presentation rows such as report titles, opening balance, subtotals, and final balance
- compatibility logic in `storage/sqlite_storage.py` protects older SQLite databases during schema initialization
- rollback-safe import orchestration lives in `app.import_support.py`
- payload parsing, replacement, execution, and mandatory-template paths are split across `services/import_*_support.py`

### 3.5 Security posture

Current practical security model:

- runtime data lives in a user-scoped platform data directory, separate from the installed binaries
- SQLite data, JSON backups, and exported reports remain plaintext files at rest
- uninstall removes installed files or bundles, but not user data in the platform data directory
- recommended host protections are OS-level (full-disk encryption, account password, trusted-machine-only use), not custom application crypto

### Repository compatibility notes

The SQLite repository remains the authoritative runtime backend for `schema_meta`, including `base_currency`.

The JSON compatibility repository supports full dataset replacement for backup and restore scenarios. In that path it now preserves top-level tag metadata, including:

- tag color
- usage count
- last-used date

## 4. Subsystem Map

### 4.1 Records / Wallets / Transfers

Core modules:

- `domain/records.py`
- `domain/wallets.py`
- `domain/transfers.py`
- `infrastructure/sqlite_repository.py`
- `storage/sqlite_storage.py`

These form the base event history used by reports and analytics.

### 4.1.1 Tags

Core modules:

- `domain/tags.py`
- `utils/tag_utils.py`
- `infrastructure/sqlite_repository.py`
- `storage/sqlite_storage.py`

This subsystem is responsible for:

- normalizing tag names and validating invalid inputs such as numeric-only tags
- storing tag metadata (`color`, `usage_count`, `last_used_at`)
- maintaining `record_tags` assignments for operation records
- exposing tag search/list/rename/delete/color APIs to controllers and UI

### Application facade boundaries

`app/use_cases.py` is maintained as an explicit compatibility facade with named re-exports rather than wildcard imports. This keeps the public application surface inspectable and reduces accidental symbol drift between use-case modules.

Current scope:

- tags are attached to `records` only
- transfers, budgets, assets, goals, and debts are not tagged as standalone entities
- tag analytics and tag budgets build on top of record-tag assignments

This area also owns the most sensitive import/relink logic:

- repository-level bulk replacement through `replace_records_and_transfers(...)`
- preservation of explicit imported IDs where required
- remapping of debt-linked records during import normalization

### 4.2 Budgets

Core modules:

- `domain/budget.py`
- `services/budget_service.py`
- `gui/tabs/budget_tab.py`
- `gui/tabs/budget/`

Budgets are date-ranged limits with live execution tracking.

As of the current working tree, the subsystem supports:

- `scope_type="category"`
- `scope_type="tag"`

Tag budgets reuse the same pace/forecast pipeline, but their spend queries are resolved through `record_tags` rather than direct category predicates.

### 4.3 Debts and Loans

Core modules:

- `domain/debt.py`
- `services/debt_service.py`
- `gui/tabs/debts_tab.py`
- `gui/tabs/debts/`
- `utils/debt_report_utils.py`

This subsystem links debt payments to cashflow records and affects net worth and report exports.

### 4.4 Mandatory Expenses

Core modules:

- `domain/records.py`
- `app/use_cases_mandatory.py`
- `services/import_mandatory_support.py`
- `gui/tabs/mandatory_tab.py`
- `gui/tabs/mandatory/`

This subsystem owns reusable mandatory-payment templates, add-to-records flows, startup auto-application, and the dedicated `Mandatory` desktop tab introduced during the final `2.0.0` GUI cleanup wave.

### 4.5 Distribution

Core modules:

- `domain/distribution.py`
- `services/distribution_service.py`
- `gui/tabs/distribution_tab.py`
- `gui/tabs/distribution/`

This subsystem calculates monthly net-income allocation and supports frozen snapshot rows.

### 4.6 Assets / Goals / Dashboard

Core modules:

- `domain/asset.py`
- `domain/goal.py`
- `domain/dashboard.py`
- `services/asset_service.py`
- `services/goal_service.py`
- `services/dashboard_service.py`
- `gui/tabs/dashboard_tab.py`
- `gui/tabs/dashboard/`

This subsystem adds a strategic wealth-management layer above the transactional ledger.

### 4.7 Audit

Core modules:

- `domain/audit.py`
- `services/audit_service.py`
- `app/audit_runner.py`

Audit is intentionally read-only and validates runtime integrity without mutating data.

### 4.8 Import / Backup Reliability

Core modules:

- `app/import_support.py`
- `services/import_service.py`
- `services/import_models.py`
- `services/import_payload_support.py`
- `services/import_replace_support.py`
- `services/import_execution_support.py`
- `services/import_mandatory_support.py`
- `utils/backup_utils.py`
- `backup.py`
- `bootstrap.py`
- `infrastructure/repositories.py`

This subsystem is responsible for:

- payload parsing and `json_sections_present` awareness
- tag-aware import/export of `tags` and `record_tags`
- capability negotiation via `ImportCapabilities`
- rollback-safe import transactions
- strict separation between app-level transaction orchestration and service-level import handlers
- corruption quarantine and save-failure handling for JSON repositories
- startup export discipline for SQLite, especially on OneDrive-managed paths

### 4.9 Runtime UI Preferences

Core modules:

- `gui/ui_theme.py`
- `gui/i18n.py`
- `gui/tkinter_gui.py`
- `gui/ui_dialogs.py`
- `gui/controllers.py`
- `app/preferences_service.py`

This subsystem is responsible for:

- light/dark theme palettes and runtime palette switching
- persisted language/theme preferences stored in SQLite schema metadata
- live rebuilding of shell strings and theme-aware widgets/dialogs
- keeping Tk styling, localized strings, and shell state synchronized during runtime preference changes

Current implementation note:

- persisted runtime preferences require schema-meta support, which is currently provided by the SQLite runtime repository

It also owns the shared desktop-shell design primitives:

- spacing tokens and card-style section composition
- Treeview zebra-striping and palette-aware list/table styling
- shell-level theme application for `Canvas` and Combobox dropdown widgets

Tag-heavy UI also lives close to this layer:

- operations tag entry with suggestions and color selection
- analytics tag coverage mode
- tag-aware report filters

### 4.10 Desktop Shell Layout

Core modules:

- `gui/tkinter_gui.py`
- `gui/shell/*`
- `gui/ui_theme.py`
- `gui/runtime_coordinator.py`
- `gui/startup_coordinator.py`
- `gui/status_bar_coordinator.py`
- `gui/tab_lifecycle.py`
- `gui/tabs/operations/`
- `gui/tabs/debts/`
- `gui/tabs/mandatory/`
- `gui/tabs/settings/`

This subsystem is responsible for:

- composing the main shell, status area, notebook, and tab containers
- keeping tab layouts visually consistent through shared card helpers and spacing tokens
- coordinating shell rebuilds when runtime theme/language state changes
- surfacing shell-owned updater handoff actions without embedding updater network logic into the shell itself
- applying redesign conventions across form-heavy and table-heavy tabs
- isolating background polling, deferred startup, status refresh, and lazy tab lifecycle outside the main shell class
- keeping first paint responsive by deferring charts/budget/distribution refresh work until after the shell becomes interactive
- ensuring Tk-heavy popup managers and widget helpers cancel pending `after(...)` callbacks on teardown so shutdown and test flows do not leak orphaned callbacks

Current implementation note:

- `gui/tkinter_gui.py` is now treated as a composition shell, while `gui/shell/*` owns most shell-specific lifecycle, status, notebook, refresh, preferences, records, and startup orchestration
- major tab implementations now live under dedicated `gui/tabs/<tab_name>/` packages, while top-level `gui/tabs/*_tab.py` files remain thin compatibility shims for tab lifecycle imports and tests
- the `Settings` tab now uses a multi-panel layout where wallets stay full-width, while currency settings, updater, backup, and audit are composed as separate card sections
- keep new feature details out of `gui/tkinter_gui.py`: tab-specific and shell-policy behavior should continue to land in `gui/tabs/*` or `gui/shell/*`

### 4.11 Hotkeys

Core modules:

- `gui/hotkeys.py`
- `gui/tkinter_gui.py`
- `gui/tabs/operations/`
- `gui/tabs/reports/`
- `gui/tabs/analytics/`
- `gui/tabs/budget/`
- `gui/tabs/debts/`
- `gui/tabs/mandatory/`

`gui.hotkeys` is the single registration point for application-wide shortcuts. `register_hotkeys(app)` binds the global sequences once per `FinancialApp` instance, while handlers resolve the active tab and the latest tab binding objects at event time.

Important design rules:

- hotkeys are bound at the shell level, not inside individual tabs
- actions are executed only when the matching tab is active
- destructive or input-conflicting shortcuts also check current focus and skip when focus is inside `Entry`, `Combobox`, or `Text`
- the design is compatible with lazy tab build and `_reset_tab_bindings()` because handlers read current `app._*_bindings` references on each keypress

### 4.12 Currency Provider System

Core modules:

- `app/services.py`
- `domain/currency.py`
- `infrastructure/currency_providers.py`
- `infrastructure/currency_aggregator.py`
- `currency_config.json` + OS-backed secret storage for API credentials

This subsystem is responsible for:

- preserving the public `CurrencyService` adapter interface used by application services and UI
- fetching exchange rates through ordered providers instead of a single hardcoded RSS implementation
- building provider chains through `CurrencyProviderRegistry` and `ProviderBuildContext`
- routing `KZT`-base online refresh through `NBKProvider`, then `ExchangeRateProvider`, then `StaticProvider`
- optionally enabling `CBRProvider` for `RUB`-base or explicit provider-order configurations
- keeping offline defaults and cached rates available when online providers fail
- exposing a whitelist-aware `display_currency` selector instead of blindly surfacing every cached currency code

Provider hierarchy:

- `NBKProvider` parses the National Bank of Kazakhstan RSS feed and remains the primary source for `KZT`
- `CBRProvider` parses the Rambler mirror of the Central Bank of Russia rates table and exposes `RUB`-base rates for environments where direct `cbr.ru` access is blocked
- `ExchangeRateProvider` normalizes `USD`-base JSON quotes from [ExchangeRate-API](https://www.exchangerate-api.com/) into the app's target base currency
- `StaticProvider` returns hardcoded defaults and never performs network I/O

Configuration model:

- `provider_order` overrides the whole chain explicitly when present
- otherwise `provider_mode` chooses between `fallback_provider` and `commercial_fallback_provider`
- `exchange_rate_api_key` should resolve from OS-backed secure storage first, with env var `FINACCOUNTING_EXCHANGE_RATE_API_KEY` as an override path
- `display_currency_whitelist` constrains which codes appear in the status-bar switcher
- `auto_update` and `update_interval_minutes` control recurring rate refresh while online mode is enabled
- first-run setup may seed the initial provider/display config through a dedicated GUI wizard, but `base_currency` remains a bootstrap-only choice that is persisted into SQLite `schema_meta`

Aggregation rules:

- `CurrencyAggregator` tries providers in configured order and logs fallback when a provider raises `ProviderFetchError`
- successful non-static provider results are cached to `currency_rates.json`
- static fallback still yields a safe result, but cached rates take precedence when available

## 5. Data Model Overview

Main SQLite tables:

- `wallets`
- `records`
- `tags`
- `record_tags`
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
- multicurrency storage is now two-layered: `base_currency` lives in `schema_meta` and defines persisted `amount_base` / `limit_base` values, while `display_currency` is a runtime-only presentation choice in `CurrencyService`
- records may reference `transfer_id` and `related_debt_id`
- debt, asset, and goal data affect read-only wealth calculations
- tag groups are overlapping coverage views, not mutually exclusive accounting partitions
- schema/bootstrap compatibility must be preserved for older SQLite databases
- full-backup payloads may omit sections intentionally, so import code must distinguish "section absent" from "section present but empty"

## 6. Change Patterns

When adding a new domain concept, the usual sequence is:

1. Add immutable domain models and validation
2. Extend SQLite schema and storage/repository mapping
3. Add service and/or `app/use_cases_*` logic
4. Expose it through `FinancialController`
5. Wire it into a tab or export flow
6. Add tests across domain, service, controller, and integration paths
7. Update `README.md`, `README_EN.md`, and `CHANGELOG.md`

When changing import/export behavior, review together:

- `app/import_support.py`
- `services/import_service.py`
- `services/import_models.py`
- `services/import_payload_support.py`
- `services/import_replace_support.py`
- `services/import_execution_support.py`
- `services/import_mandatory_support.py`
- `utils/backup_utils.py`
- `gui/exporters.py`
- `migrate_json_to_sqlite.py`
- `infrastructure/repositories.py`
- `storage/sqlite_storage.py`
- the related contract tests

When changing GUI startup/deferred work, review together:

- `gui/tkinter_gui.py`
- `gui/runtime_coordinator.py`
- `gui/startup_coordinator.py`
- `gui/status_bar_coordinator.py`
- `gui/tab_lifecycle.py`
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
- inspect `app/use_cases.py` and then the concrete `app/use_cases_*` modules behind it
- then move into the service or tab that matches your feature area

For data-format issues:

- start with `app/import_support.py`
- then inspect `services/import_service.py`, `services/import_*_support.py`, `utils/backup_utils.py`, and `migrate_json_to_sqlite.py`

For net-worth/report issues:

- start with `services/balance_service.py`
- then `services/timeline_service.py`, `services/report_service.py`, and report exporters

For runtime durability issues:

- inspect `infrastructure/repositories.py`
- then `storage/sqlite_storage.py`, `backup.py`, and `bootstrap.py`
