# FinAccountingApp

[![Release](https://img.shields.io/github/v/release/36chubm54/FinAccountingApp?display_name=tag)](https://github.com/36chubm54/FinAccountingApp/releases)
[![Windows Build](https://img.shields.io/github/actions/workflow/status/36chubm54/FinAccountingApp/windows-build.yml?branch=main&label=windows%20build)](https://github.com/36chubm54/FinAccountingApp/actions/workflows/windows-build.yml)
[![Linux Build](https://img.shields.io/github/actions/workflow/status/36chubm54/FinAccountingApp/linux-build.yml?branch=main&label=linux%20build)](https://github.com/36chubm54/FinAccountingApp/actions/workflows/linux-build.yml)
[![License](https://img.shields.io/github/license/36chubm54/FinAccountingApp)](https://github.com/36chubm54/FinAccountingApp/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![README RU](https://img.shields.io/badge/README-Русский-blue)](README.md)

Graphical application for personal financial accounting with multicurrency support, import/export, tags, budgets, debts, assets, and goals.

The current `v2.5.1` release hardens the updater and startup UX after `v2.5.0`: packaged Windows and packaged Linux now persist already-downloaded update state across restarts, the primary CTA in `Settings -> Application updates` switches from `Check for updates` to `Install update`, and downloaded installer/package artifacts are removed only after the next successful launch of the target-or-newer version. In parallel, the polished startup surfaces make deferred startup and the first-run setup feel more intentional while the prerelease-aware updater logic and terminal/package-manager preflight keep install handoff honest.

In the current runtime contract:

- `exchange_rate_api_key` should no longer live in plaintext `currency_config.json` and is persisted through OS-backed secure storage by default
- env var `FINACCOUNTING_EXCHANGE_RATE_API_KEY` remains a runtime override over secure storage
- packaged mutable runtime state lives in a user-scoped platform data directory: `AppData` on Windows and `XDG_DATA_HOME` / `~/.local/share/FinAccountingApp` on Linux
- the Windows updater downloads installers into a dedicated `updates` cache under `AppData`, and the packaged Linux updater does the same for `.deb` / `.rpm` artifacts in a user-scoped Linux updates cache
- when an installer/package has already been downloaded, the updater now restores that state after restart and offers `Install update` without re-downloading it
- downloaded updater artifacts are removed only after the next successful launch of the upgraded target-or-newer version, not immediately after handoff
- stable builds ignore GitHub prerelease releases, while prerelease builds can see newer prereleases and then transition to the final stable release
- backup/export files remain plaintext financial data, and that is now reflected explicitly in the UX and docs
- the Windows release workflow is prepared for optional code signing, but without a certificate the installer and bundle remain unsigned

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

The app starts a Tkinter GUI on top of SQLite runtime storage. `Infographics` and `Operations` are built eagerly, the remaining tabs are built lazily, and post-startup maintenance plus heavier refresh passes run after the first window paint.

### Windows build (`PyInstaller --onedir`)

- The main Windows bundle is built from the checked-in `FinAccountingApp.spec`
- Bundled read-only resources include `gui/assets/icons`, `locales`, and `db/schema.sql`
- In packaged mode, mutable runtime files (`finance.db`, currency config/cache, backups, updater downloads) are created in user-scoped `AppData` instead of the install directory
- Migration utilities `migrate_json_to_sqlite.py` and `migration_002_rename_amount_kzt_to_base.py` are included in the bundle as raw Python scripts, not as separate `.exe` tools
- Windows installer-facing branding now uses `Ledgera`: the setup artifact is built as `Ledgera-<version>-setup.exe`, and the default install directory becomes `Program Files\\Ledgera`
- The bundled executable and internal runtime paths remain compatibility-oriented: the installer still ships `FinAccountingApp.exe`, and user data still resolves under `AppData`
- The GitHub Actions release workflow can optionally sign `FinAccountingApp.exe` and the installer when a code-signing certificate is configured in repository secrets; without a certificate, the build remains unsigned
- Windows CI now exercises the installer build path on regular workflow runs as well, so installer regressions are caught on PRs and manual runs instead of only on tagged releases

### Linux build (`PyInstaller --onedir` + `AppImage` / `deb` / `rpm`)

- The Linux bundle is still built through `FinAccountingApp.linux.spec`
- The release workflow now emits three Linux artifact formats from that bundle:
  - `Ledgera-linux.AppImage`
  - `Ledgera-<version>-x86_64.deb`
  - `Ledgera-<version>-x86_64.rpm`
- `deb` / `rpm` packaged Linux runtime on `Wayland` / `XWayland` now stays on the native `ttk.Combobox` path by default with guard logic, while `AppImage` and source-mode Linux use a compatibility fallback for problematic selector surfaces
- Packaged Linux runtime keeps the same read-only resources vs mutable user-data split as Windows builds: the database, currency config, backups, exports, and updates are no longer expected to live beside either the AppImage or the installed system bundle
- User data for packaged Linux builds resolve to `XDG_DATA_HOME/FinAccountingApp` or `~/.local/share/FinAccountingApp`
- For `.deb` / `.rpm` system packages, the bundle is installed under `/opt/FinAccountingApp`, the launcher is exposed as `/usr/bin/ledgera`, and the desktop entry plus icon are registered system-wide
- Linux package metadata is now owned by the packaging layer: AppStream summary, description, and release notes are no longer generated directly from `README` / `CHANGELOG`, and the generated metadata is validated through `appstreamcli --pedantic`
- Packaged Linux `deb` / `rpm` builds now support a persisted in-app updater flow: the app detects the current package kind through an install-root marker, downloads the matching Linux package into a user-scoped `updates` cache, survives restarts with a ready-to-install CTA, and after confirmation opens a terminal-based `sudo apt install ...` / `sudo dnf install ...` handoff
- If the packaged Linux runtime cannot determine the package kind confidently, cannot resolve a supported terminal executable, or cannot find the required package manager (`apt` / `dnf`), the updater degrades to the manual GitHub Releases path instead of guessing an install command
- `AppImage` and source-mode Linux still do not update in-app: for those runtimes the supported path remains manually downloading a newer Linux package or AppImage from GitHub Releases
- In this release wave, Wayland compatibility now splits `system-package`, `AppImage`, and source runtime behavior: `deb` / `rpm` packaged Linux keeps native `ttk.Combobox` behavior by default, while `AppImage`, source-mode Linux, and Linux tag autocomplete can still use the app-managed fallback path when needed; the corresponding selectors stay on native `ttk.Combobox` on Windows
- `GNOME Software` may display license data and release notes inconsistently for locally installed third-party packages even when AppStream metadata is present; in practice this can differ between Ubuntu GNOME and Fedora GNOME

### Linux package build

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install .[pdf,build]
npm install -g @goreleaser/nfpm
pyinstaller --noconfirm FinAccountingApp.linux.spec
chmod +x packaging/linux/build_appimage.sh packaging/linux/build_system_packages.sh
bash packaging/linux/build_system_packages.sh dist/FinAccountingApp artifacts
```

## ✨ Core Features

- Track income, expenses, mandatory payments, and wallet-to-wallet transfers
- Multi-currency records normalized into `base_currency` (default `KZT`)
- Two-layer multicurrency model with persisted `base_currency` and runtime-only `display_currency`
- Operation tags with free-form entry, normalization, suggestions, color coding, and sidecar display in the journal
- Reports with fixed-rate and current-rate totals, grouped view, tag filters, and `CSV` / `XLSX` / `PDF` export
- Statement views in `Reports` and exported statement files now list records newest first, with deterministic same-day ordering by `date + record.id`
- Financial analytics: `net worth`, cashflow, category breakdown, tag coverage, and monthly summary
- Category and tag budgets with live progress, pace tracking, and forecast status
- Debt and loan tracking with repayment history and write-off flows
- Distribution System for monthly net-income allocation and frozen snapshots
- Wealth layer: `Assets`, `Goals`, and a dedicated wealth `Dashboard`
- Full backup / import / migration for `JSON` ↔ `SQLite`
- In-app updater in `Settings`: Windows downloads `Ledgera-*-setup.exe`, packaged Linux `deb` / `rpm` builds download the matching package, and both packaged runtime paths now persist downloaded-update state across restarts before the final install handoff
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
- `Settings -> Application updates` on Windows can check the latest GitHub Release, download `Ledgera-*-setup.exe` into `AppData\\updates`, survive restart with a ready-to-install CTA, and then hand off to the normal installer; packaged Linux `deb` / `rpm` builds do the same for the matching package in a user-scoped updates cache and a terminal-based install handoff, while `AppImage` and source-mode Linux stay on the manual GitHub Releases path
- `exchange_rate_api_key` is no longer expected to live in `currency_config.json`: in packaged/runtime flows it is migrated into secure OS storage where the platform supports it, env var `FINACCOUNTING_EXCHANGE_RATE_API_KEY` remains an override path, and a plaintext fallback is only tolerated when secure storage is unavailable
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
- `Settings` — wallets, currency and rates, application updates, backup/import, audit

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
| `services.app_update_service.AppUpdateService` | GitHub Releases lookup, prerelease-aware asset selection, and streamed updater downloads for the Windows installer and packaged Linux packages |
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
- `gui.tabs.settings.update_section` — updater-section UI with a Windows installer flow, packaged Linux package download + terminal handoff, and manual fallback for `AppImage` / source-mode
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
- In the current runtime config, the default base currency is `KZT`
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

- Runtime data (`finance.db`, `currency_config.json`, `currency_rates.json`, backups, exports) lives in a user-scoped platform data directory: `AppData` on Windows and `XDG_DATA_HOME` / `~/.local/share/FinAccountingApp` on Linux
- In-app updater downloads on Windows and packaged Linux also live in a user-scoped `updates` cache instead of the source checkout or installed bundle; `AppImage` and source-mode runtimes still do not use in-app install handoff
- `exchange_rate_api_key` is expected to live in secure OS-backed storage; `currency_config.json` is no longer treated as a plaintext secret store
- The SQLite database, JSON backups, and exported reports are still not encrypted at rest: they remain readable financial-data files
- Uninstalling or removing the bundle does not remove user data from the platform data directory
- For personal use, the recommended host protections are:
  - full-disk encryption (`BitLocker`, `LUKS`, `FileVault`, or equivalent)
  - a password-protected system account
  - trusted-machine-only usage
  - importing only trusted backup/export files

## 📄 License

The project is distributed under the `MIT` license. See `LICENSE`.
