# FinAccountingApp

Graphical application for personal financial accounting with multicurrency support, import/export, tags, budgets, debts, assets, and goals.

The current `v2.0.1` release continues the stable `v2.0.0` line as a personal-security hardening patch: the normalized `amount_base` / `limit_base` architecture, `base_currency` runtime model, per-tab GUI packages, and Windows installer remain intact, while local secret handling, import/backup trust boundaries, and the packaged Windows security posture are tightened on top of that baseline.

In the current runtime contract:

- `exchange_rate_api_key` should no longer live in plaintext `currency_config.json` and is persisted through OS-backed secure storage by default
- env var `FINACCOUNTING_EXCHANGE_RATE_API_KEY` remains a runtime override over secure storage
- mutable runtime state still lives in user-scoped `AppData`, not beside the installed application
- backup/export files remain plaintext financial data, and that is now reflected explicitly in the UX and docs
- the Windows release workflow is prepared for optional code signing, but without a certificate the installer and bundle remain unsigned

## 🚀 Quick Start

### Requirements

- Python `3.11+`
- `pip`

### Installation

```bash
cd "Проект ФУ/FinAccountingApp-dev"

python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Windows CMD
.venv\Scripts\activate.bat

# Linux/macOS
source .venv/bin/activate

# Base runtime dependencies
pip install -r requirements.txt

# Optional: PDF export
pip install -r requirements-pdf.txt
# or:
# pip install .[pdf]

# Dev dependencies
pip install -r requirements-dev.txt
```

### Launch

```bash
python main.py
```

The app starts a Tkinter GUI on top of SQLite runtime storage. `Infographics` and `Operations` are built eagerly, the remaining tabs are built lazily, and post-startup maintenance plus heavier refresh passes run after the first window paint.

### Windows build (`PyInstaller --onedir`)

- The main Windows bundle is built from the checked-in [FinAccountingApp.spec](C:/Users/swar4/OneDrive/Документы/Финансовый%20учёт/Проект%20ФУ/FinAccountingApp-dev/FinAccountingApp.spec)
- Bundled read-only resources include `gui/assets/icons`, `locales`, and `db/schema.sql`
- In packaged mode, mutable runtime files (`finance.db`, currency config/cache, backups) are created in user-scoped `AppData` instead of the install directory
- Migration utilities [migrate_json_to_sqlite.py](C:/Users/swar4/OneDrive/Документы/Финансовый%20учёт/Проект%20ФУ/FinAccountingApp-dev/migrate_json_to_sqlite.py) and [migration_002_rename_amount_kzt_to_base.py](C:/Users/swar4/OneDrive/Документы/Финансовый%20учёт/Проект%20ФУ/FinAccountingApp-dev/migrations/migration_002_rename_amount_kzt_to_base.py) are included in the bundle as raw Python scripts, not as separate `.exe` tools
- The GitHub Actions release workflow can optionally sign `FinAccountingApp.exe` and the installer when a code-signing certificate is configured in repository secrets; without a certificate, the build remains unsigned

## ✨ Core Features

- Track income, expenses, mandatory payments, and wallet-to-wallet transfers
- Multi-currency records normalized into `base_currency` (default `KZT`)
- Two-layer multicurrency model with persisted `base_currency` and runtime-only `display_currency`
- Operation tags with free-form entry, normalization, suggestions, color coding, and sidecar display in the journal
- Reports with fixed-rate and current-rate totals, grouped view, tag filters, and `CSV` / `XLSX` / `PDF` export
- Statement views in `Reports` and exported statement files now list records newest first
- Financial analytics: `net worth`, cashflow, category breakdown, tag coverage, and monthly summary
- Category and tag budgets with live progress, pace tracking, and forecast status
- Debt and loan tracking with repayment history and write-off flows
- Distribution System for monthly net-income allocation and frozen snapshots
- Wealth layer: `Assets`, `Goals`, and a dedicated wealth `Dashboard`
- Full backup / import / migration for `JSON` ↔ `SQLite`
- Read-only Data Audit Engine for runtime consistency checks, including tag integrity
- External `locales/*.txt` language packs with a shared i18n loader and fallback chain
- Runtime `theme` / `language` preferences persisted in SQLite schema metadata
- Light / dark theme system with live theme-aware shell, status bar, audit views, and dialogs
- Redesigned desktop shell with card-based sections, updated spacing tokens, and cleaner notebook/treeview/status patterns
- Improved theme application for Treeview, Canvas, and Combobox popdown widgets
- Section-aware `JSON` import so records-only restore does not wipe unrelated `debts/assets/goals/budgets`
- Safer persistence behavior: corrupt JSON quarantine, `.error` copies on save failure, atomic backup/export paths
- Patch-level stabilization on top of `v1.15.0`: safer import/runtime flows, GUI coordinator split, and tighter rollback/durability guarantees
- Inline editing now distinguishes operation-currency amounts from persisted base-value equivalents instead of treating everything as implicit `KZT`
- Bulk `JSON` restore preserves top-level `tags` even without current bindings to operations

## 💱 Multicurrency Model

- `base_currency` defines the persisted normalized values in SQLite (`amount_base`, `limit_base`) and is stored in `schema_meta`
- `display_currency` affects only UI presentation and can be switched at runtime from the status bar
- Business calculations continue to operate on base amounts; UI conversion is done on demand through `CurrencyService.to_display(...)`
- `base_currency` is chosen only during first-run setup, then SQLite `schema_meta` remains the source of truth
- By default, the display selector is limited to the whitelist `KZT` / `USD` / `EUR` / `RUB`, even if cached rates contain more currency codes
- `Settings -> Currency and rates` can update `display_currency`, provider mode, primary/fallback provider, `exchange_rate_api_key`, `auto_update`, and `update_interval_minutes`, but not post-startup `base_currency`
- `exchange_rate_api_key` is no longer expected to live in `currency_config.json`: in the Windows packaged/runtime flow it is migrated into secure OS storage, env var `FINACCOUNTING_EXCHANGE_RATE_API_KEY` remains an override path, and a plaintext fallback is only tolerated when secure storage is unavailable
- `auto_update` is now active behavior instead of passive metadata: when online mode is enabled, rates refresh automatically according to `update_interval_minutes`
- Exported reports are localized to the current UI language, and base-amount columns explicitly show the real base code, for example `Amount (KZT)`
- Localized report `CSV` / `XLSX` exports remain import-safe for the app's generic import pipeline

## 🖥️ Application Tabs

- `Infographics` — quick visual view of expenses and cashflow by day/month
- `Operations` — add, edit, delete, import, and export operations, tags, and inline editing
- `Reports` — build reports, grouped summaries, wallet/category/tag filters, export
- `Analytics` — period metrics: `net worth`, savings rate, burn rate, category breakdown, and tag coverage
- `Dashboard` — wealth overview: `Assets`, `Goals`, allocation, compact net-worth trend
- `Budget` — category limits and live budget tracking
- `Debts` — debts and loans: create, repay, write off, close, view history, track progress
- `Distribution` — monthly net-income distribution and frozen snapshots
- `Mandatory` — mandatory payment templates, edit/delete flows, and add-to-records actions
- `Settings` — wallets, currency and rates, backup/import, audit

## 🏗️ Architecture Overview

| Layer | Responsibility |
| --- | --- |
| `domain` | Immutable models and business rules: records, tags, wallets, budgets, debts, assets, goals, reports |
| `app` | Use cases, application contracts, and orchestration between GUI, services, and repository |
| `services` | Specialized flows: import, audit, analytics, budget/debt/distribution/wealth logic |
| `infrastructure` + `storage` | SQLite/JSON persistence, schema bootstrap, repository/storage adapters |
| `gui` | Tkinter UI, controller layer, shell coordinators, exporters/import preview dialogs, tab composition |

Also important:

- `utils` — import/export formats, PDF/XLSX helpers, money helpers, charting
- `tests` — regression and contract coverage for domain/app/services/gui/import-export flows
- `.gitattributes` — normalized source/text line endings (`LF`) to reduce cross-platform diff noise

## 🔌 Key Extension Points

### Main entry points

| Entry point | Use it for |
| --- | --- |
| `gui.controllers.FinancialController` | Main integration surface for GUI and high-level app flows |
| `app.repository.RecordRepository` | Application-level repository contract consumed by use cases |
| `app.repository_protocols` | Narrow capability contracts for the runtime repository instead of direct concrete typing |
| `app.import_support.run_import_transaction(...)` | Rollback-safe orchestration between controller/import service and the runtime repository |
| `app.preferences_service` | Runtime persistence helpers for `theme`, `language`, and online-mode UI preferences |
| `app.audit_runner` | App-level audit launch helper for GUI/controller flows |
| `services.import_service.ImportService` | Main import coordinator delegating payload/replacement/execution/mandatory flows to support modules |
| `services.audit_service.AuditService` | Read-only SQLite integrity checks |
| `services.balance_service.BalanceService` | Wallet balances, total balance, cashflow |
| `services.metrics_service.MetricsService` | Savings rate, burn rate, monthly/category/tag analytics |
| `services.budget_service.BudgetService` | Budget CRUD, category/tag budgets, and live tracking |
| `services.debt_service.DebtService` | Debt/loan lifecycle |
| `services.distribution_service.DistributionService` | Monthly distribution and frozen rows |
| `infrastructure.sqlite_repository.SQLiteRecordRepository` | Primary runtime repository |
| `storage.sqlite_storage.SQLiteStorage` | Low-level SQLite adapter / schema bootstrap |
| `infrastructure.currency_providers.CurrencyProviderRegistry` | Registry and extension point for rate providers |

Practical highlights in the current working tree:

- `FinancialController.save_theme_preference(...)` / `save_language_preference(...)` — runtime UI preferences persisted in SQLite
- `gui.ui_theme` — centralized light/dark palette system, card helpers, spacing tokens, and Treeview theming helpers
- `gui.runtime_coordinator.UiRuntimeCoordinator` — safe `after(...)`, background task polling, and shutdown-aware scheduling
- `gui.startup_coordinator.DeferredStartupCoordinator` — deferred startup flow, mandatory auto-payments, and post-startup maintenance
- `gui.status_bar_coordinator.StatusBarCoordinator` — online-mode toggles and recurring status refresh logic
- `gui.tab_lifecycle` — lazy tab build and lifecycle dispatch outside the main shell class
- `gui.shell.*` — shell-specific lifecycle/refresh/preferences/status helpers extracted from `gui.tkinter_gui`
- `gui.tabs.*` — real tab packages, with `*_tab.py` kept as thin compatibility shims
- `CurrencyService.get_available_display_currencies()` — whitelist-aware display switcher values instead of the full cached-rate set
- `FinanceService.get_import_capabilities()` — a single capability model for the import pipeline instead of ad-hoc attribute probing
- `services.import_payload_support`, `services.import_replace_support`, `services.import_execution_support`, `services.import_mandatory_support` — a split import stack instead of one oversized service body
- `FinancialController.list_tags()` / `search_tags()` / `set_tag_color()` — app-level entry points for tag-aware UI and analytics
- `SQLiteRecordRepository.replace_records_and_transfers(...)` — safe bulk operation replacement with debt-payment link remapping
- `gui.logging_utils.log_ui_error(...)` — shared structured logging helper for GUI errors and degraded flows

### Import / backup entry points

| Entry point | Purpose |
| --- | --- |
| `FinancialController.import_records(...)` | Primary app-level import entry from GUI/controller flows |
| `app.import_support.run_import_transaction(...)` | Transaction/snapshot orchestration with rollback semantics |
| `ImportService.import_file(...)` | Main operation import pipeline |
| `utils.backup_utils.export_full_backup_to_json(...)` | Low-level full-backup export |
| `utils.backup_utils.import_full_backup_from_json(...)` | Low-level backup parser, returns `ImportedBackupData` |
| `migrate_json_to_sqlite.py` | Full migration of a JSON payload into SQLite |
| `backup.py` | Export current SQLite state into backup / `data.json` |

### Important developer scenarios

- Adding a new entity usually touches `domain` → `repository/storage` → `app/use_cases_*` → `gui/controllers` → target tab
- New read-only metrics belong in `services/*_service.py`, not in GUI code
- New import formats/variants should go through `ImportService`, `app.import_support`, and `utils/import_core.py`
- Schema changes should be updated together in `db/schema.sql`, bootstrap/migration flow, and regression tests

## ⌨️ Hotkeys

Global shortcuts are registered through `gui.hotkeys.register_hotkeys(app)` once per `FinancialApp` instance. Handlers inspect the active tab and current focus at keypress time, so they remain valid across lazy-built and rebuilt tabs.

| Key | Scope | Action |
| --- | --- | --- |
| `Alt+1..9` | Global | Switch tab (1–Infographics, 2–Operations, 3–Reports, 4–Analytics, 5–Dashboard, 6–Budget, 7–Debts, 8–Distribution, 9–Mandatory) |
| `F5` | Global | Refresh data (calls refresh across all tabs) |
| `F1` / `?` | Global | Open the hotkey help |
| `Ctrl+I` | Operations | Set operation type to “Income” |
| `Ctrl+E` | Operations | Set operation type to “Expense” |
| `Home` | Operations | Jump to the first record in the list |
| `End` | Operations | Jump to the last record in the list |
| `Del` | Operations | Delete the selected record |
| `Ctrl+Del` | Operations | Delete all records (requires confirmation) |
| `F2` | Operations | Edit the selected record |
| `Enter` | Operations | Save the operation (while in edit form) |
| `Ctrl+G` | Reports | Generate a report |
| `Ctrl+Shift+C` | Reports | Export report to CSV |
| `Ctrl+Shift+X` | Reports | Export report to XLSX |
| `Ctrl+Shift+P` | Reports | Export report to PDF |
| `Ctrl+R` | Analytics | Refresh analytics (recalculate metrics) |
| `Ctrl+T` | Analytics | Toggle tag mode |
| `Enter` | Budget | Add a new budget |
| `Del` | Budget | Delete the selected budget |
| `F2` | Budget | Edit the selected budget |
| `Enter` | Debts | Add a new debt |
| `Ctrl+P` | Debts | Pay the selected debt |
| `Ctrl+W` | Debts | Write off the selected debt |
| `Del` | Debts | Delete the selected debt |
| `Enter` | Mandatory | Add a new mandatory payment |
| `F2` | Mandatory | Edit the selected mandatory payment |
| `Del` | Mandatory | Delete the selected mandatory payment |
| `Ctrl+Enter` | Mandatory | Add the selected mandatory payment to operations |

Hotkeys work only when focus is inside the main application window (not in dialogs) and the corresponding tab is active. To prevent conflicts with text input, the following safeguards are implemented:

- Keys `Del`, `F2`, `Home`, `End`, `Ctrl+Del`, `Ctrl+R`, `Ctrl+P`, `Ctrl+W` are ignored if focus is inside any input field (`Entry`, `ttk.Entry`, `ttk.Combobox`, `tk.Text`).
- The `Enter` key is not processed when focus is in a `ttk.Combobox` or `tk.Text`, or when the operations inline editor is active.
- All hotkeys are blocked while the operations inline editor is open (record editing mode in the operations list).
- `Settings` remains a shell tab but does not have its own `Alt+number` shortcut because global fast switching is limited to the first nine tab slots.
- Shortcuts tied to specific tabs (`Ctrl+I`, `Ctrl+E`, `Ctrl+G`, etc.) fire only when that tab is active.

## 🧪 Tests

### Run

```bash
pytest
```

```bash
pytest --cov=. --cov-report=term-missing
```

### What is covered

- domain models and validation rules
- use cases and controller flows
- import/export contracts (`CSV`, `XLSX`, `JSON`, backup)
- SQLite runtime storage, bootstrap, and migration
- GUI-level regression tests for critical tabs, coordinators, and exporters
- architecture-boundary and typing-regression checks for key shell/runtime layers

## 💾 Import / Backup / Migration

### Import

- Pipeline: `parse -> dry-run validation -> user confirmation -> rollback-safe runtime transaction`
- Supports `CSV`, `XLSX`, `JSON`
- `JSON` full backup restores runtime entities including `budgets`, `debts`, `debt_payments`, and distribution/wealth payloads when supported by the repository
- `JSON` backup/import now also includes `tags` and `record_tags`
- Readonly snapshots require `force=True`
- For `JSON` under `ImportPolicy.CURRENT_RATE`, the fast bulk-replace path is still allowed when the repository supports it
- `ImportCapabilities` defines which bulk-replace and load-* operations are actually available for the current runtime service
- Partial `JSON` import is now section-aware: when a payload only contains `records`, current `debts/assets/goals/budgets/distribution` data is preserved
- Legacy `JSON` payloads without `tags` / `record_tags` are still accepted and treated as tag-less data
- If the `debts` section is explicitly absent, the pipeline tries to preserve existing `related_debt_id` links; if the section is present, links are normalized only against allowed debt IDs
- `CSV` / `XLSX` imports still use the create-path instead of bulk replace, and both `related_debt_id` and `tags` are now propagated there
- The generic import parser also understands localized report `CSV` / `XLSX` exports, so title rows, opening balance, and subtotal/final rows are not misread as normal operations
- Import orchestration now lives in `app.import_support`, while the service layer is split into focused `services/import_*_support.py` helpers
- `v1.10.1` adds stricter early payload validation: broken references, duplicate `wallet.id`, multiple `system` wallets, and invalid/duplicate `distribution_snapshots` are rejected earlier in the import pipeline

### Backup

- Full backup is stored as `JSON`
- Main low-level parser: `import_full_backup_from_json(...)`
- `import_backup(...)` remains only as a deprecated compatibility wrapper
- Snapshot backups and startup-export paths now include tags and record-tag links
- For the JSON backend, standalone tag metadata during rollback/import is treated as a compatibility layer; the full runtime contract for tag metadata remains SQLite-backed
- JSON export and backup-copy paths are written atomically through a temporary file plus `fsync` and `os.replace`
- `backup.export_to_json(...)` now raises `BackupExportError` so bootstrap and the GUI can distinguish export failures from other startup issues
- On JSON repository save failure, an `.error` snapshot of the unsaved payload is written and `RepositorySaveError` is raised
- Corrupt or empty JSON runtime files are quarantined as `.corrupt_*` and raise `RepositoryDataCorruptionError`
- Legacy JSON auto-migration no longer continues silently after persist failure: a failed migration save is surfaced explicitly
- `requirements-pdf.txt` is only needed for PDF export, not for the default runtime install

### Migration

```bash
python migrate_json_to_sqlite.py --dry-run
python migrate_json_to_sqlite.py --json-path data.json --sqlite-path finance.db
```

- The script migrates a JSON payload into SQLite in one explicit transaction
- When `tags` / `record_tags` exist in the payload, they are migrated too; when they are absent, migration still succeeds cleanly
- Pre-schema compatibility supports legacy SQLite databases where `records` still lacks `related_debt_id`
- Migration and bootstrap should stay aligned with the current `db/schema.sql`
- On OneDrive-managed paths, bootstrap also accounts for sync/coherence risks, runs `PRAGMA quick_check`, and may force synchronous export for large databases instead of background export

## 🧭 Link to Detailed Architecture

This README is intentionally compact and release-oriented.  
The detailed layer map, runtime flows, and module guide now live in `docs/architecture.md`.

## 💱 Supported Currencies

- By default, the UI display selector uses `KZT`, `USD`, `EUR`, and `RUB`
- In the current beta config, the default base currency is `KZT`
- The provider chain can load a wider set of rates when allowed by config and the active online provider

Rates are provided through `CurrencyService` and an ordered provider chain:

- `NBKProvider` — primary online source for `KZT`
- `ExchangeRateProvider` — API-key-based fallback provider
- `CBRProvider` — optional `RUB`-base provider via the Rambler mirror
- `StaticProvider` — safe offline fallback with no network I/O

Useful configuration points:

- `currency_config.json` — `provider_mode`, `fallback_provider`, `commercial_fallback_provider`, `display_currency_whitelist`, `auto_update`, `update_interval_minutes` without a plaintext `exchange_rate_api_key`
- env var `FINACCOUNTING_EXCHANGE_RATE_API_KEY` — runtime override for `exchange_rate_api_key`

## 🔐 Security Notes

- Runtime data (`finance.db`, `currency_config.json`, `currency_rates.json`, backups, exports) lives in user-scoped `AppData`, not beside the executable
- `exchange_rate_api_key` is expected to live in secure OS-backed storage; `currency_config.json` is no longer treated as a plaintext secret store
- The SQLite database, JSON backups, and exported reports are still not encrypted at rest: they remain readable financial-data files
- Uninstall removes installed files and shortcuts, but does not remove user data from `AppData`
- For personal Windows use, the recommended host protections are:
  - `BitLocker`
  - a password-protected Windows account
  - trusted-machine-only usage
  - importing only trusted backup/export files

## 📄 License

The project is distributed under the `MIT` license. See `LICENSE`.
