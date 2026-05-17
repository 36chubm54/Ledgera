# FinAccountingApp

[![Release](https://img.shields.io/github/v/release/36chubm54/FinAccountingApp?display_name=tag)](https://github.com/36chubm54/FinAccountingApp/releases)
[![Windows Build](https://img.shields.io/github/actions/workflow/status/36chubm54/FinAccountingApp/windows-build.yml?branch=main&label=windows%20build)](https://github.com/36chubm54/FinAccountingApp/actions/workflows/windows-build.yml)
[![License](https://img.shields.io/github/license/36chubm54/FinAccountingApp)](https://github.com/36chubm54/FinAccountingApp/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![README EN](https://img.shields.io/badge/README-English-blue)](README_EN.md)

Графическое приложение для персонального финансового учёта с мультивалютностью, импортом/экспортом, тегами, бюджетами, долгами, активами и целями.

Текущий релиз `v2.1.0` развивает стабильную Windows desktop-линию вокруг встроенного updater flow. Поверх уже закреплённой архитектуры с `amount_base` / `limit_base`, `base_currency`, per-tab GUI packages и Windows installer приложение теперь умеет проверять GitHub Releases из `Settings`, скачивать новый installer в user-scoped cache и передавать обновление штатному установщику без ручного поиска release asset'ов.

В актуальном runtime-контракте:

- `exchange_rate_api_key` больше не должен жить в plaintext `currency_config.json` и по умолчанию уходит в OS-backed secure storage
- env var `FINACCOUNTING_EXCHANGE_RATE_API_KEY` остаётся runtime override поверх secure storage
- mutable runtime state по-прежнему живёт в user-scoped `AppData`, а не рядом с установленным приложением
- Windows updater скачивает installer в отдельный `updates` cache внутри `AppData` и не пишет payload в install tree
- backup/export файлы остаются plaintext financial data, и это теперь явно отражено в UX и документации
- Windows release workflow подготовлен к optional code signing, но без сертификата installer и bundle остаются unsigned

## 🚀 Быстрый старт

### Требования

- Python `3.11+`
- `pip`

### Установка

```bash
cd "Проект ФУ/project"

python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Windows CMD
.venv\Scripts\activate.bat

# Linux/macOS
source .venv/bin/activate

# Базовые runtime-зависимости
pip install -r requirements.txt

# Опционально: PDF-экспорт
pip install -r requirements-pdf.txt
# или:
# pip install .[pdf]

# Dev-зависимости
pip install -r requirements-dev.txt
```

### Запуск приложения

```bash
python main.py
```

Приложение запускает Tkinter GUI поверх SQLite runtime-storage. Вкладки `Infographics` и `Operations` строятся сразу, остальные вкладки достраиваются лениво, а post-startup maintenance и тяжёлые refresh-проходы выполняются после первого показа окна.

### Windows build (`PyInstaller --onedir`)

- Основной Windows bundle собирается через checked-in `FinAccountingApp.spec`
- Bundled read-only resources включают `gui/assets/icons`, `locales`, `db/schema.sql`
- В packaged режиме mutable runtime files (`finance.db`, currency config/cache, backups, updater downloads) создаются в user-scoped `AppData`, а не внутри install directory
- Migration utilities `migrate_json_to_sqlite.py` и `migration_002_rename_amount_kzt_to_base.py` входят в bundle как raw Python scripts, а не как отдельные `.exe`
- GitHub Actions release workflow может опционально подписывать `FinAccountingApp.exe` и installer, если в repository secrets настроен code-signing certificate; без сертификата build остаётся unsigned

## ✨ Основные возможности

- Учёт доходов, расходов, обязательных платежей и переводов между кошельками
- Мультивалютные записи с нормализацией в `base_currency` (по умолчанию `KZT`)
- Двухуровневая валютная модель: `base_currency` для хранения и `display_currency` для отображения
- Теги операций: свободный ввод, нормализация, автоподсказки, цветовая индикация и sidecar-отображение в журнале
- Отчёты с fixed-rate и current-rate итогами, grouped view, tag filters и экспортом в `CSV` / `XLSX` / `PDF`
- Выписка в `Reports` и экспортируемые statement-файлы показывают записи от новых к старым (`newest first`)
- Финансовая аналитика: `net worth`, cashflow, category breakdown, tag coverage, monthly summary
- Бюджеты по категориям и тегам с live progress, pace tracking и forecast-status
- Учёт долгов и ссуд с историей погашений и write-off сценариями
- Distribution System для monthly net-income allocation и frozen snapshots
- Wealth layer: `Assets`, `Goals`, wealth `Dashboard`
- Full backup / import / migration для `JSON` ↔ `SQLite`
- Manual Windows app updater в `Settings`: проверка GitHub Release, скачивание installer'а с progress dialog и handoff в штатный setup flow
- Read-only Data Audit Engine для проверки консистентности данных, включая tag integrity
- Внешние языковые пакеты `locales/*.txt` и единый i18n-loader с fallback-цепочкой
- Runtime `theme` / `language` preferences с сохранением в SQLite schema metadata
- Light / dark theme system и live theme-aware shell, status bar, audit views и диалоги
- Redesign desktop shell: card-based sections, обновлённые spacing tokens, более чистые notebook/treeview/status patterns
- Улучшенное theme application для Treeview, Canvas и Combobox popdown widgets
- Section-aware `JSON` import: records-only restore не затирает несвязанные `debts/assets/goals/budgets`
- Более безопасная persistence-слой логика: quarantine для битых JSON-файлов, `.error` copies при save-failure, atomic backup/export paths
- Patch-level stabilization поверх `v1.15.0`: safer import/runtime flows, GUI coordinator split, tighter rollback/durability guarantees
- Inline editing различает сумму записи в валюте операции и базовый эквивалент, чтобы не смешивать `display_currency` с persisted base-values
- Bulk `JSON` restore сохраняет top-level `tags` даже без текущих привязок к операциям

## 💱 Multicurrency Model

- `base_currency` определяет, как нормализованные значения хранятся в SQLite (`amount_base`, `limit_base`), и записывается в `schema_meta`
- `display_currency` меняет только представление сумм в работающем приложении и переключается из status bar
- Бизнес-расчёты продолжают работать в базовой валюте; UI-конвертация выполняется через `CurrencyService.to_display(...)`
- `base_currency` выбирается только при первом запуске через setup wizard, затем источником истины остаётся SQLite `schema_meta`
- По умолчанию селектор отображения ограничен whitelist-ом `KZT` / `USD` / `EUR` / `RUB`, даже если кэш курсов содержит больше кодов
- `Settings -> Валюта и курсы` позволяет менять `display_currency`, provider mode, primary/fallback provider, `exchange_rate_api_key`, `auto_update` и `update_interval_minutes`, но не post-startup `base_currency`
- `Settings -> Обновление приложения` в Windows умеет проверять последний GitHub Release, скачивать `setup.exe` в `AppData\updates` и предлагать install handoff через штатный installer
- `exchange_rate_api_key` больше не должен жить в `currency_config.json`: в Windows packaged/runtime flow он переносится в secure OS storage, env var `FINACCOUNTING_EXCHANGE_RATE_API_KEY` остаётся override-путём, а аварийный plaintext fallback допустим только когда secure storage недоступен
- `auto_update` больше не является декоративным флагом: при включённом online mode курсы обновляются автоматически по `update_interval_minutes`
- Экспортируемые отчёты локализуются по текущему языку UI, а колонки базовых сумм явно показывают код базы, например `Сумма (KZT)`
- Локализованные report `CSV` / `XLSX` exports остаются import-safe для generic import pipeline приложения

## 🖥️ Вкладки приложения

- `Infographics` — быстрый визуальный обзор расходов и cashflow по дням/месяцам
- `Operations` — добавление, редактирование, удаление, импорт и экспорт операций, теги и inline-edit
- `Reports` — генерация отчётов, grouped summary, wallet/category/tag filters, export
- `Analytics` — метрики за период: `net worth`, savings rate, burn rate, category breakdown и tag coverage
- `Dashboard` — wealth overview: `Assets`, `Goals`, allocation, compact net-worth trend
- `Budget` — лимиты по категориям и live tracking исполнения
- `Debts` — долги и ссуды: создание, погашение, write off, close, history, progress
- `Distribution` — monthly net-income distribution и frozen snapshots
- `Mandatory` — обязательные платежи: шаблоны, редактирование, удаление и добавление в операции
- `Settings` — кошельки, валюта и курсы, обновление приложения, backup/import, audit

## 🏗️ Архитектурный обзор

| Слой | Ответственность |
| --- | --- |
| `domain` | Immutable-модели и бизнес-правила: records, tags, wallets, budgets, debts, assets, goals, reports |
| `app` | Use case-ы, application contracts и orchestration между GUI, сервисами и репозиторием |
| `services` | Специализированные сценарии: import, audit, analytics, budget/debt/distribution/wealth logic |
| `infrastructure` + `storage` | SQLite/JSON persistence, schema bootstrap, repository/storage adapters |
| `gui` | Tkinter UI, controller layer, shell coordinators, exporters/import preview dialogs, tab composition |

Что ещё важно:

- `utils` — форматы импорта/экспорта, PDF/XLSX helpers, money helpers, charting
- `tests` — regression и contract coverage для domain/app/services/gui/import-export flows
- `.gitattributes` — нормализация line endings (`LF`) для снижения шума в кроссплатформенных диффах

## 🔌 Ключевые точки расширения

### Основные entry points

| Точка | Когда использовать |
| --- | --- |
| `gui.controllers.FinancialController` | Главная точка входа для GUI и интеграций верхнего уровня |
| `app.repository.RecordRepository` | Application-level repository contract для use case-ов |
| `app.repository_protocols` | Узкие capability-contracts для runtime repository вместо direct concrete typing |
| `app.import_support.run_import_transaction(...)` | Rollback-safe orchestration между controller/import service и runtime repository |
| `app.preferences_service` | Сохранение runtime UI preferences: `theme`, `language`, online-mode |
| `app.audit_runner` | App-level запуск audit-flow из GUI/controller |
| `services.import_service.ImportService` | Основной import coordinator, который делегирует payload/replacement/execution/mandatory flows support-модулям |
| `services.audit_service.AuditService` | Read-only проверка целостности SQLite-данных |
| `services.balance_service.BalanceService` | Балансы кошельков, total balance, cashflow |
| `services.metrics_service.MetricsService` | Savings rate, burn rate, monthly/category/tag analytics |
| `services.budget_service.BudgetService` | Budget CRUD, category/tag budgets и live tracking |
| `services.debt_service.DebtService` | Debt/loan lifecycle |
| `services.distribution_service.DistributionService` | Monthly distribution и frozen rows |
| `services.app_update_service.AppUpdateService` | Проверка GitHub Release, выбор Windows installer asset и stream-download updater payload |
| `infrastructure.sqlite_repository.SQLiteRecordRepository` | Основной runtime repository |
| `storage.sqlite_storage.SQLiteStorage` | Низкоуровневый SQLite adapter / schema bootstrap |
| `infrastructure.currency_providers.CurrencyProviderRegistry` | Реестр и extension point для rate providers |

Практические акценты текущего рабочего дерева:

- `FinancialController.save_theme_preference(...)` / `save_language_preference(...)` — runtime UI preferences, сохраняемые в SQLite
- `gui.ui_theme` — централизованная light/dark palette system, card helpers, spacing tokens и Treeview theming helpers
- `gui.runtime_coordinator.UiRuntimeCoordinator` — безопасное `after(...)`, polling background tasks и shutdown-aware scheduling
- `gui.startup_coordinator.DeferredStartupCoordinator` — deferred startup, auto-application mandatory payments и post-startup maintenance
- `gui.status_bar_coordinator.StatusBarCoordinator` — online-mode toggle и периодический status refresh
- `gui.tab_lifecycle` — lazy tab build и lifecycle dispatch вне основного shell-класса
- `gui.shell.*` — shell-specific lifecycle/refresh/preferences/status helpers, вынесенные из `gui.tkinter_gui`
- `gui.tabs.*` — реальные tab packages, где `*_tab.py` оставлены как тонкие compatibility shims
- `gui.tabs.settings.update_section` — Windows-only updater card, modal download progress dialog и installer handoff prompts
- `CurrencyService.get_available_display_currencies()` — whitelist-aware набор кодов для status-bar switcher вместо полного набора из кэша
- `FinanceService.get_import_capabilities()` — единая capability-модель для import pipeline вместо ad-hoc проверок по атрибутам
- `services.import_payload_support`, `services.import_replace_support`, `services.import_execution_support`, `services.import_mandatory_support` — разрезанный import stack вместо одного разросшегося service body
- `FinancialController.list_tags()` / `search_tags()` / `set_tag_color()` — app-level entry points для tag-aware UI и аналитики
- `SQLiteRecordRepository.replace_records_and_transfers(...)` — безопасная bulk-замена операций с ремапом связанных debt-payment ссылок
- `gui.logging_utils.log_ui_error(...)` — общий structured logging helper для GUI ошибок и деградаций

### Import / backup entry points

| Точка | Назначение |
| --- | --- |
| `FinancialController.import_records(...)` | Основной app-level импорт из GUI/controller |
| `app.import_support.run_import_transaction(...)` | Transaction/snapshot orchestration с rollback semantics |
| `ImportService.import_file(...)` | Основной pipeline импорта операций |
| `utils.backup_utils.export_full_backup_to_json(...)` | Low-level full backup export |
| `utils.backup_utils.import_full_backup_from_json(...)` | Low-level backup parser, возвращает `ImportedBackupData` |
| `migrate_json_to_sqlite.py` | Полная миграция JSON payload в SQLite |
| `backup.py` | Экспорт текущего SQLite state в backup / `data.json` |

### Важные developer-сценарии

- Добавление новой сущности обычно затрагивает `domain` → `repository/storage` → `app/use_cases_*` → `gui/controllers` → нужную вкладку
- Новые read-only метрики лучше добавлять в `services/*_service.py`, а не в GUI
- Новые форматы/варианты импорта лучше подключать через `ImportService`, `app.import_support` и `utils/import_core.py`
- Если меняется schema, нужно синхронно обновлять `db/schema.sql`, bootstrap/migration flow и regression tests

## ⌨️ Горячие клавиши

Глобальные сочетания регистрируются через `gui.hotkeys.register_hotkeys(app)` один раз на экземпляр `FinancialApp`. Обработчики читают активную вкладку и текущий фокус в момент нажатия, поэтому остаются корректными даже при lazy-build и пересборке вкладок.

| Клавиша | Область | Действие |
| --- | --- | --- |
| `Alt+1..9` | Глобально | Переключить вкладку (1–Infographics, 2–Operations, 3–Reports, 4–Analytics, 5–Dashboard, 6–Budget, 7–Debts, 8–Distribution, 9–Mandatory) |
| `F5` | Глобально | Обновить данные (вызывает refresh всех вкладок) |
| `F1` / `?` | Глобально | Открыть справку по горячим клавишам |
| `Ctrl+I` | Операции | Установить тип операции «Доход» |
| `Ctrl+E` | Операции | Установить тип операции «Расход» |
| `Home` | Операции | Перейти к первой записи в списке |
| `End` | Операции | Перейти к последней записи в списке |
| `Del` | Операции | Удалить выбранную запись |
| `Ctrl+Del` | Операции | Удалить все записи (требует подтверждения) |
| `F2` | Операции | Редактировать выбранную запись |
| `Enter` | Операции | Сохранить операцию (в форме редактирования) |
| `Ctrl+G` | Отчеты | Сформировать отчет |
| `Ctrl+Shift+C` | Отчеты | Экспортировать отчет в CSV |
| `Ctrl+Shift+X` | Отчеты | Экспортировать отчет в XLSX |
| `Ctrl+Shift+P` | Отчеты | Экспортировать отчет в PDF |
| `Ctrl+R` | Аналитика | Обновить аналитику (пересчитать метрики) |
| `Ctrl+T` | Аналитика | Переключить режим тегов |
| `Enter` | Бюджет | Добавить новый бюджет |
| `Del` | Бюджет | Удалить выбранный бюджет |
| `F2` | Бюджет | Редактировать выбранный бюджет |
| `Enter` | Долги | Добавить новый долг |
| `Ctrl+P` | Долги | Погасить выбранный долг |
| `Ctrl+W` | Долги | Списать выбранный долг (write off) |
| `Del` | Долги | Удалить выбранный долг |
| `Enter` | Mandatory | Добавить обязательный платёж |
| `F2` | Mandatory | Редактировать выбранный обязательный платёж |
| `Del` | Mandatory | Удалить выбранный обязательный платёж |
| `Ctrl+Enter` | Mandatory | Добавить выбранный обязательный платёж в операции |

Горячие клавиши работают только когда фокус находится в основном окне приложения (не в диалогах) и активна соответствующая вкладка. Для предотвращения конфликтов с вводом текста реализованы следующие защиты:

- Клавиши `Del`, `F2`, `Home`, `End`, `Ctrl+Del`, `Ctrl+R`, `Ctrl+P`, `Ctrl+W` игнорируются, если фокус находится в любом поле ввода (`Entry`, `ttk.Entry`, `ttk.Combobox`, `tk.Text`).
- Клавиша `Enter` не обрабатывается, когда фокус в `ttk.Combobox` или `tk.Text`, а также если активен inline-редактор операции.
- Все горячие клавиши блокируются, когда открыт inline-редактор операции (режим редактирования записи в списке операций).
- `Settings` остаётся доступной вкладкой shell, но не имеет отдельного `Alt+номер` shortcut, потому что глобальное быстрое переключение ограничено первыми девятью tab slots.
- Сочетания, привязанные к конкретным вкладкам (`Ctrl+I`, `Ctrl+E`, `Ctrl+G` и др.), срабатывают только когда эта вкладка активна.

## 🧪 Тесты

### Запуск

```bash
pytest
```

```bash
pytest --cov=. --cov-report=term-missing
```

### Что покрыто

- domain-модели и validation rules
- use case-ы и controller flows
- import/export contracts (`CSV`, `XLSX`, `JSON`, backup)
- SQLite runtime storage, bootstrap и migration
- GUI-level regression tests для критичных вкладок, coordinators и exporters
- architecture boundary и typing-regression checks для ключевых shell/runtime слоёв

## 💾 Импорт / backup / migration

### Import

- Pipeline: `parse -> dry-run validation -> user confirmation -> rollback-safe runtime transaction`
- Поддерживаются `CSV`, `XLSX`, `JSON`
- Для `JSON` full backup восстанавливаются runtime-сущности, включая `budgets`, `debts`, `debt_payments`, distribution/wealth payloads, если подсистемы поддерживаются репозиторием
- `JSON` backup/import теперь включает `tags` и `record_tags`
- Для readonly snapshot требуется `force=True`
- Для `JSON` под `ImportPolicy.CURRENT_RATE` fast bulk-replace path тоже разрешён, если репозиторий его поддерживает
- `ImportCapabilities` определяет, какие bulk-replace и load-* операции реально доступны конкретному runtime-service
- Partial `JSON` import стал section-aware: если payload содержит только `records`, текущие `debts/assets/goals/budgets/distribution` не стираются
- Legacy `JSON` без `tags` / `record_tags` по-прежнему поддерживается и трактуется как payload без тегов
- Если секция `debts` явно отсутствует, pipeline старается сохранить существующие `related_debt_id` связи; если секция есть, ссылки нормализуются только по допустимым debt IDs
- `CSV` / `XLSX` import по-прежнему идёт через create-path и не использует bulk replace; `related_debt_id` и `tags` теперь корректно прокидываются и там
- Generic import parser понимает и локализованные report `CSV` / `XLSX` exports: title rows, opening balance и subtotal/final rows не принимаются за обычные операции
- Import orchestration вынесен в `app.import_support`, а service-слой разделён на focused `services/import_*_support.py` helpers
- `v1.10.1` усиливает раннюю валидацию import payload: битые ссылочные связи, дубликаты `wallet.id`, несколько `system` wallets и невалидные/дублированные `distribution_snapshots` теперь отсекаются раньше

### Backup

- Full backup хранится в `JSON`
- Базовый low-level parser: `import_full_backup_from_json(...)`
- `import_backup(...)` оставлен только как deprecated compatibility wrapper
- Snapshot backup и startup-export paths включают теги и их связи с операциями
- Для JSON backend standalone tag metadata во время rollback/import считается compatibility-слоем; полноценный runtime-контракт для tag metadata остаётся у SQLite backend
- JSON export и backup-copy paths записываются atomically через temporary file + `fsync` + `os.replace`
- `backup.export_to_json(...)` теперь поднимает `BackupExportError`, чтобы bootstrap/UI различали export-failure и другие startup-проблемы
- При ошибке сохранения JSON repository пишет `.error` snapshot с несохранённым payload и поднимает `RepositorySaveError`
- Битый или пустой JSON runtime-файл карантинится как `.corrupt_*` и поднимает `RepositoryDataCorruptionError`
- Legacy JSON auto-migration больше не продолжает работу молча после провала persist-шагa: ошибка сохранения поднимается явно
- `requirements-pdf.txt` нужен только для PDF-экспорта, не для базового runtime

### Migration

```bash
python migrate_json_to_sqlite.py --dry-run
python migrate_json_to_sqlite.py --json-path data.json --sqlite-path finance.db
```

- Скрипт переносит JSON payload в SQLite в одной явной транзакции
- При наличии `tags` / `record_tags` миграция переносит и их; при отсутствии этих секций завершается без ошибки
- Pre-schema compatibility поддерживает старые SQLite БД, где таблица `records` ещё без `related_debt_id`
- Migration и bootstrap должны идти в паре с актуальным `db/schema.sql`
- На OneDrive-путях bootstrap дополнительно учитывает sync/coherence риски, выполняет `PRAGMA quick_check` и для больших БД может форсировать synchronous export вместо фонового

## 🧭 Ссылка на подробную архитектуру

Сейчас README оставлен компактным и ориентированным на релиз/use cases.  
Подробная техническая карта слоёв, runtime-flows и модулей вынесена в `docs/architecture.md`.

## 💱 Поддерживаемые валюты

- По умолчанию UI-селектор отображения использует `KZT`, `USD`, `EUR`, `RUB`
- Базовая валюта в текущем runtime-конфиге по умолчанию — `KZT`
- Provider chain может загружать более широкий набор курсов, если это разрешено конфигом и текущим online-provider

Курсы обновляются через `CurrencyService` и ordered provider chain:

- `NBKProvider` — основной online-источник для `KZT`
- `ExchangeRateProvider` — fallback provider с API key
- `CBRProvider` — опциональный provider для `RUB`-base сценариев через Rambler mirror
- `StaticProvider` — safe fallback без сети

Полезные config points:

- `currency_config.json` — `provider_mode`, `fallback_provider`, `commercial_fallback_provider`, `display_currency_whitelist`, `auto_update`, `update_interval_minutes`
- env var `FINACCOUNTING_EXCHANGE_RATE_API_KEY` — runtime override для `exchange_rate_api_key`

## 🔐 Security Notes

- Runtime data (`finance.db`, `currency_config.json`, `currency_rates.json`, backups, exports) хранится в user-scoped `AppData`, а не рядом с `.exe`
- Downloads встроенного updater'а тоже живут в отдельном `AppData\updates` cache, а не рядом с исходниками или установленным bundle
- `exchange_rate_api_key` должен храниться в secure OS-backed storage; `currency_config.json` больше не рассматривается как место для plaintext secrets
- SQLite база, JSON backups и exported reports по-прежнему не шифруются at rest: это читаемые файлы с финансовыми данными
- Uninstall удаляет установленные файлы и ярлыки, но не удаляет пользовательские данные в `AppData`
- Для personal Windows use рекомендуется:
  - `BitLocker`
  - пароль на Windows-учётной записи
  - использование приложения только на доверенной машине
  - импорт только из доверенных backup/export файлов

## 📄 Лицензия

Проект распространяется под лицензией `MIT`. См. `LICENSE`.
