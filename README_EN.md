# FinAccountingApp

Graphical application for personal financial accounting with multicurrency support, import/export, budgets, debts, assets, and goals.

The current `v1.14.0` release focuses on a redesigned desktop shell: the visual theme system, major tab layouts, and shell-level Tkinter behavior were refreshed together. The UI is now more card-based and consistent, Treeview tables use stronger zebra/highlight styling, and the light/dark palette system is applied more deeply across the shell, canvas widgets, combobox popdowns, and working tabs.

## 🚀 Quick Start

### Requirements

- Python `3.11+`
- `pip`

### Installation

```bash
cd "Проект ФУ/project"

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

The app starts a Tkinter GUI on top of SQLite runtime storage. Core tabs can be built lazily, and post-startup maintenance runs after the first window paint.

## ✨ Core Features

- Track income, expenses, mandatory payments, and wallet-to-wallet transfers
- Multi-currency records normalized into base currency `KZT`
- Reports with fixed-rate and current-rate totals, grouped view, and `CSV` / `XLSX` / `PDF` export
- Financial analytics: `net worth`, cashflow, category breakdown, monthly summary
- Category budgets with live progress and pace tracking
- Debt and loan tracking with repayment history and write-off flows
- Distribution System for monthly net-income allocation
- Wealth layer: `Assets`, `Goals`, and a dedicated wealth `Dashboard`
- Full backup / import / migration for `JSON` ↔ `SQLite`
- Read-only Data Audit Engine for runtime consistency checks
- External `locales/*.txt` language packs with a shared i18n loader and fallback chain
- Runtime `theme` / `language` preferences persisted in SQLite schema metadata
- Light / dark theme system with live theme-aware shell, status bar, audit views, and dialogs
- Redesigned desktop shell with card-based sections, updated spacing tokens, and cleaner notebook/treeview/status patterns
- Improved theme application for Treeview, Canvas, and Combobox popdown widgets
- Custom window icon support (`.ico` + `iconphoto` fallback) with forward compatibility for packaged `exe` icon usage
- Section-aware `JSON` import so records-only restore does not wipe unrelated `debts/assets/goals/budgets`
- Safer persistence behavior: corrupt JSON quarantine, `.error` copies on save failure, atomic backup/export paths
- `XLSX` / `PDF` report export now shows explicit degradation warnings instead of silently dropping grouped sections

## 🖥️ Application Tabs

- `Infographics` — quick visual view of expenses and cashflow by day/month
- `Operations` — add, edit, delete, import, and export operations
- `Reports` — build reports, grouped summaries, wallet/category filters, export
- `Analytics` — period metrics: `net worth`, savings rate, burn rate, monthly summary
- `Dashboard` — wealth overview: `Assets`, `Goals`, allocation, compact net-worth trend
- `Budget` — category limits and live budget tracking
- `Debts` — debts and loans: create, repay, write off, close, view history, track progress
- `Distribution` — monthly net-income distribution and frozen snapshots
- `Settings` — wallets, mandatory expenses, backup/import, audit

## 🏗️ Architecture in 5 Layers

| Layer | Responsibility |
| --- | --- |
| `domain` | Immutable models and business rules: records, wallets, budgets, debts, assets, goals, reports |
| `app` | Use cases and orchestration between GUI, services, and repository |
| `services` | Specialized flows: import, audit, analytics, budget/debt/distribution/wealth logic |
| `infrastructure` + `storage` | SQLite/JSON persistence, schema bootstrap, repository/storage adapters |
| `gui` | Tkinter UI, controller layer, exporters/import preview dialogs, tab composition |

Also important:

- `utils` — import/export formats, PDF/XLSX helpers, money helpers, charting
- `tests` — regression and contract coverage for domain/app/services/gui/import-export flows
- `.gitattributes` — normalized source/text line endings (`LF`) to reduce cross-platform diff noise

## 🔌 Key Extension Points

### Main entry points

| Entry point | Use it for |
| --- | --- |
| `gui.controllers.FinancialController` | Main integration surface for GUI and high-level app flows |
| `services.import_service.ImportService` | Real import pipeline: dry-run, validation, commit |
| `services.audit_service.AuditService` | Read-only SQLite integrity checks |
| `services.balance_service.BalanceService` | Wallet balances, total balance, cashflow |
| `services.metrics_service.MetricsService` | Savings rate, burn rate, monthly/category analytics |
| `services.budget_service.BudgetService` | Budget CRUD and live tracking |
| `services.debt_service.DebtService` | Debt/loan lifecycle |
| `services.distribution_service.DistributionService` | Monthly distribution and frozen rows |
| `infrastructure.sqlite_repository.SQLiteRecordRepository` | Primary runtime repository |
| `storage.sqlite_storage.SQLiteStorage` | Low-level SQLite adapter / schema bootstrap |

Practical `v1.14.0` highlights:

- `FinancialController.save_theme_preference(...)` / `save_language_preference(...)` — runtime UI preferences persisted in SQLite
- `gui.ui_theme` — centralized light/dark palette system, card helpers, spacing tokens, and Treeview theming helpers
- `gui.tkinter_gui` — the main shell orchestration layer applying theme, status bar, and tab rebuild/runtime hooks
- `FinanceService.get_import_capabilities()` — a single capability model for the import pipeline instead of ad-hoc attribute probing
- `FinancialController.load_debts()` and `related_debt_id` in `create_income(...)` / `create_expense(...)` — important hooks for debt-aware import/restore flows
- `SQLiteRecordRepository.replace_records_and_transfers(...)` — safe bulk operation replacement with debt-payment link remapping
- `gui.logging_utils.log_ui_error(...)` — shared structured logging helper for GUI errors and degraded flows

### Import / backup entry points

| Entry point | Purpose |
| --- | --- |
| `FinancialController.import_records(...)` | Primary app-level import entry from GUI/controller flows |
| `ImportService.import_file(...)` | Main operation import pipeline |
| `utils.backup_utils.export_full_backup_to_json(...)` | Low-level full-backup export |
| `utils.backup_utils.import_full_backup_from_json(...)` | Low-level backup parser, returns `ImportedBackupData` |
| `migrate_json_to_sqlite.py` | Full migration of a JSON payload into SQLite |
| `backup.py` | Export current SQLite state into backup / `data.json` |

### Important developer scenarios

- Adding a new entity usually touches `domain` → `repository/storage` → `app/use_cases` → `gui/controllers` → target tab
- New read-only metrics belong in `services/*_service.py`, not in GUI code
- New import formats/variants should go through `ImportService` and `utils/import_core.py`
- Schema changes should be updated together in `db/schema.sql`, bootstrap/migration flow, and regression tests

## ⌨️ Hotkeys

Global shortcuts are registered through `gui.hotkeys.register_hotkeys(app)` once per `FinancialApp` instance. Handlers inspect the active tab and current focus at keypress time, so they remain valid across lazy-built and rebuilt tabs.

| Key | Scope | Action |
| --- | --- | --- |
| `Alt+1..8` | Global | Switch tab (1–Infographics, 2–Operations, 3–Reports, 4–Analytics, 5–Dashboard, 6–Budget, 7–Debts, 8–Distribution) |
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
| `Enter` | Budget | Add a new budget |
| `Del` | Budget | Delete the selected budget |
| `F2` | Budget | Edit the selected budget |
| `Enter` | Debts | Add a new debt |
| `Ctrl+P` | Debts | Pay the selected debt |
| `Ctrl+W` | Debts | Write off the selected debt |
| `Del` | Debts | Delete the selected debt |

Hotkeys work only when focus is inside the main application window (not in dialogs) and the corresponding tab is active. To prevent conflicts with text input, the following safeguards are implemented:

- Keys `Del`, `F2`, `Home`, `End`, `Ctrl+Del`, `Ctrl+R`, `Ctrl+P`, `Ctrl+W` are ignored if focus is inside any input field (`Entry`, `ttk.Entry`, `ttk.Combobox`, `tk.Text`).
- The `Enter` key is not processed when focus is in a `ttk.Combobox` or `tk.Text`, or when the operations inline editor is active.
- All hotkeys are blocked while the operations inline editor is open (record editing mode in the operations list).
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
- GUI-level regression tests for critical tabs and exporters

## 💾 Import / Backup / Migration

### Import

- Pipeline: `parse -> dry-run validation -> user confirmation -> SQLite transaction`
- Supports `CSV`, `XLSX`, `JSON`
- `JSON` full backup restores runtime entities including `budgets`, `debts`, `debt_payments`, and distribution/wealth payloads when supported by the repository
- Readonly snapshots require `force=True`
- For `JSON` under `ImportPolicy.CURRENT_RATE`, the fast bulk-replace path is still allowed when the repository supports it
- `ImportCapabilities` defines which bulk-replace and load-* operations are actually available for the current runtime service
- Partial `JSON` import is now section-aware: when a payload only contains `records`, current `debts/assets/goals/budgets/distribution` data is preserved
- If the `debts` section is explicitly absent, the pipeline tries to preserve existing `related_debt_id` links; if the section is present, links are normalized only against allowed debt IDs
- `CSV` / `XLSX` imports still use the create-path instead of bulk replace, and `related_debt_id` is now propagated there as well
- `v1.10.1` adds stricter early payload validation: broken references, duplicate `wallet.id`, multiple `system` wallets, and invalid/duplicate `distribution_snapshots` are rejected earlier in the import pipeline

### Backup

- Full backup is stored as `JSON`
- Main low-level parser: `import_full_backup_from_json(...)`
- `import_backup(...)` remains only as a deprecated compatibility wrapper
- JSON export and backup-copy paths are written atomically through a temporary file plus `fsync` and `os.replace`
- `backup.export_to_json(...)` now raises `BackupExportError` so bootstrap and the GUI can distinguish export failures from other startup issues
- On JSON repository save failure, an `.error` snapshot of the unsaved payload is written and `RepositorySaveError` is raised
- Corrupt or empty JSON runtime files are quarantined as `.corrupt_*` and raise `RepositoryDataCorruptionError`
- `requirements-pdf.txt` is only needed for PDF export, not for the default runtime install

### Migration

```bash
python migrate_json_to_sqlite.py --dry-run
python migrate_json_to_sqlite.py --json-path data.json --sqlite-path finance.db
```

- The script migrates a JSON payload into SQLite in one explicit transaction
- Pre-schema compatibility supports legacy SQLite databases where `records` still lacks `related_debt_id`
- Migration and bootstrap should stay aligned with the current `db/schema.sql`
- On OneDrive-managed paths, bootstrap also accounts for sync/coherence risks, runs `PRAGMA quick_check`, and may force synchronous export for large databases instead of background export

## 🧭 Link to Detailed Architecture

This README is intentionally compact and release-oriented.  
The detailed layer map, runtime flows, and module guide now live in `docs/architecture.md`.

## 💱 Supported Currencies

- `KZT` — base currency
- `RUB`
- `USD`
- `EUR`

Rates are provided through `CurrencyService`; offline mode keeps the last known state.

## 📄 License

The project is distributed under the `MIT` license. See `LICENSE`.
