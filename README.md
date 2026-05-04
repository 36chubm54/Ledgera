# FinAccountingApp

Графическое приложение для персонального финансового учёта с мультивалютностью, импортом/экспортом, бюджетами, долгами, активами и целями.

Текущий релиз `v1.14.0` посвящён редизайну desktop shell: обновлены визуальная система темы, layout основных вкладок и shell-level поведение Tkinter-приложения. Интерфейс стал более карточным и консистентным, Treeview-таблицы получили zebra/highlight styling, а light/dark palette system теперь глубже применяется к shell, canvas-виджетам, combobox popdown и рабочим вкладкам.

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

Приложение запускает Tkinter GUI поверх SQLite runtime-storage. Основные вкладки могут достраиваться лениво, а post-startup maintenance выполняется после первого показа окна.

## ✨ Основные возможности

- Учёт доходов, расходов, обязательных платежей и переводов между кошельками
- Мультивалютные записи с пересчётом в базовую валюту `KZT`
- Отчёты с fixed-rate и current-rate итогами, grouped view и экспортом в `CSV` / `XLSX` / `PDF`
- Финансовая аналитика: `net worth`, cashflow, category breakdown, monthly summary
- Бюджеты по категориям с live progress и pace tracking
- Учёт долгов и ссуд с историей погашений и write-off сценариями
- Distribution System для monthly net-income allocation
- Wealth layer: `Assets`, `Goals`, wealth `Dashboard`
- Full backup / import / migration для `JSON` ↔ `SQLite`
- Read-only Data Audit Engine для проверки консистентности данных
- Внешние языковые пакеты `locales/*.txt` и единый i18n-loader с fallback-цепочкой
- Runtime `theme` / `language` preferences с сохранением в SQLite schema metadata
- Light / dark theme system и live theme-aware shell, status bar, audit views и диалоги
- Redesign desktop shell: card-based sections, обновлённые spacing tokens, более чистые notebook/treeview/status patterns
- Улучшенное theme application для Treeview, Canvas и Combobox popdown widgets
- Поддержка пользовательской иконки окна (`.ico` + `iconphoto` fallback) и подготовка к иконке будущего `exe`
- Section-aware `JSON` import: records-only restore не затирает несвязанные `debts/assets/goals/budgets`
- Более безопасная persistence-слой логика: quarantine для битых JSON-файлов, `.error` copies при save-failure, atomic backup/export paths
- Экспорт отчётов в `XLSX` / `PDF` теперь явно сигнализирует о деградации grouped-section вместо silent failure

## 🖥️ Вкладки приложения

- `Infographics` — быстрый визуальный обзор расходов и cashflow по дням/месяцам
- `Operations` — добавление, редактирование, удаление, импорт и экспорт операций
- `Reports` — генерация отчётов, grouped summary, wallet/category filters, export
- `Analytics` — метрики за период: `net worth`, savings rate, burn rate, monthly summary
- `Dashboard` — wealth overview: `Assets`, `Goals`, allocation, compact net-worth trend
- `Budget` — лимиты по категориям и live tracking исполнения
- `Debts` — долги и ссуды: создание, погашение, write off, close, history, progress
- `Distribution` — monthly net-income distribution и frozen snapshots
- `Settings` — кошельки, mandatory expenses, backup/import, audit

## 🏗️ Архитектура в 5 слоях

| Слой | Ответственность |
| --- | --- |
| `domain` | Immutable-модели и бизнес-правила: records, wallets, budgets, debts, assets, goals, reports |
| `app` | Use cases и orchestration между GUI, сервисами и репозиторием |
| `services` | Специализированные сценарии: import, audit, analytics, budget/debt/distribution/wealth logic |
| `infrastructure` + `storage` | SQLite/JSON persistence, schema bootstrap, repository/storage adapters |
| `gui` | Tkinter UI, controller layer, exporters/import preview dialogs, tab composition |

Что ещё важно:

- `utils` — форматы импорта/экспорта, PDF/XLSX helpers, money helpers, charting
- `tests` — regression и contract coverage для domain/app/services/gui/import-export flows
- `.gitattributes` — нормализация line endings (`LF`) для снижения шума в кроссплатформенных диффах

## 🔌 Ключевые точки расширения

### Основные entry points

| Точка | Когда использовать |
| --- | --- |
| `gui.controllers.FinancialController` | Главная точка входа для GUI и интеграций верхнего уровня |
| `services.import_service.ImportService` | Реальный import pipeline: dry-run, validation, commit |
| `services.audit_service.AuditService` | Read-only проверка целостности SQLite-данных |
| `services.balance_service.BalanceService` | Балансы кошельков, total balance, cashflow |
| `services.metrics_service.MetricsService` | Savings rate, burn rate, monthly/category analytics |
| `services.budget_service.BudgetService` | Budget CRUD и live tracking |
| `services.debt_service.DebtService` | Debt/loan lifecycle |
| `services.distribution_service.DistributionService` | Monthly distribution и frozen rows |
| `infrastructure.sqlite_repository.SQLiteRecordRepository` | Основной runtime repository |
| `storage.sqlite_storage.SQLiteStorage` | Низкоуровневый SQLite adapter / schema bootstrap |

Практические акценты для `v1.14.0`:

- `FinancialController.save_theme_preference(...)` / `save_language_preference(...)` — runtime UI preferences, сохраняемые в SQLite
- `gui.ui_theme` — централизованная light/dark palette system, card helpers, spacing tokens и Treeview theming helpers
- `gui.tkinter_gui` — главный shell orchestration layer, применяющий theme, status bar и tab rebuild/runtime hooks
- `FinanceService.get_import_capabilities()` — единая capability-модель для import pipeline вместо ad-hoc проверок по атрибутам
- `FinancialController.load_debts()` и `related_debt_id` в `create_income(...)` / `create_expense(...)` — важные точки для debt-aware import/restore flows
- `SQLiteRecordRepository.replace_records_and_transfers(...)` — безопасная bulk-замена операций с ремапом связанных debt-payment ссылок
- `gui.logging_utils.log_ui_error(...)` — общий structured logging helper для GUI ошибок и деградаций

### Import / backup entry points

| Точка | Назначение |
| --- | --- |
| `FinancialController.import_records(...)` | Основной app-level импорт из GUI/controller |
| `ImportService.import_file(...)` | Основной pipeline импорта операций |
| `utils.backup_utils.export_full_backup_to_json(...)` | Low-level full backup export |
| `utils.backup_utils.import_full_backup_from_json(...)` | Low-level backup parser, возвращает `ImportedBackupData` |
| `migrate_json_to_sqlite.py` | Полная миграция JSON payload в SQLite |
| `backup.py` | Экспорт текущего SQLite state в backup / `data.json` |

### Важные developer-сценарии

- Добавление новой сущности обычно затрагивает `domain` → `repository/storage` → `app/use_cases` → `gui/controllers` → нужную вкладку
- Новые read-only метрики лучше добавлять в `services/*_service.py`, а не в GUI
- Новые форматы/варианты импорта лучше подключать через `ImportService` и `utils/import_core.py`
- Если меняется schema, нужно синхронно обновлять `db/schema.sql`, bootstrap/migration flow и regression tests

## ⌨️ Горячие клавиши

Глобальные сочетания регистрируются через `gui.hotkeys.register_hotkeys(app)` один раз на экземпляр `FinancialApp`. Обработчики читают активную вкладку и текущий фокус в момент нажатия, поэтому остаются корректными даже при lazy-build и пересборке вкладок.

| Клавиша | Область | Действие |
| --- | --- | --- |
| `Alt+1..8` | Глобально | Переключить вкладку (1–Infographics, 2–Operations, 3–Reports, 4–Analytics, 5–Dashboard, 6–Budget, 7–Debts, 8–Distribution) |
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
| `Enter` | Бюджет | Добавить новый бюджет |
| `Del` | Бюджет | Удалить выбранный бюджет |
| `F2` | Бюджет | Редактировать выбранный бюджет |
| `Enter` | Долги | Добавить новый долг |
| `Ctrl+P` | Долги | Погасить выбранный долг |
| `Ctrl+W` | Долги | Списать выбранный долг (write off) |
| `Del` | Долги | Удалить выбранный долг |

Горячие клавиши работают только когда фокус находится в основном окне приложения (не в диалогах) и активна соответствующая вкладка. Для предотвращения конфликтов с вводом текста реализованы следующие защиты:

- Клавиши `Del`, `F2`, `Home`, `End`, `Ctrl+Del`, `Ctrl+R`, `Ctrl+P`, `Ctrl+W` игнорируются, если фокус находится в любом поле ввода (`Entry`, `ttk.Entry`, `ttk.Combobox`, `tk.Text`).
- Клавиша `Enter` не обрабатывается, когда фокус в `ttk.Combobox` или `tk.Text`, а также если активен inline‑редактор операции.
- Все горячие клавиши блокируются, когда открыт inline‑редактор операции (режим редактирования записи в списке операций).
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
- use cases и controller flows
- import/export contracts (`CSV`, `XLSX`, `JSON`, backup)
- SQLite runtime storage, bootstrap и migration
- GUI-level regression tests для критичных вкладок и exporters

## 💾 Импорт / backup / migration

### Import

- Pipeline: `parse -> dry-run validation -> user confirmation -> SQLite transaction`
- Поддерживаются `CSV`, `XLSX`, `JSON`
- Для `JSON` full backup восстанавливаются runtime-сущности, включая `budgets`, `debts`, `debt_payments`, distribution/wealth payloads, если подсистемы поддерживаются репозиторием
- Для readonly snapshot требуется `force=True`
- Для `JSON` под `ImportPolicy.CURRENT_RATE` fast bulk-replace path тоже разрешён, если репозиторий его поддерживает
- `ImportCapabilities` определяет, какие bulk-replace и load-* операции реально доступны конкретному runtime-service
- Partial `JSON` import стал section-aware: если payload содержит только `records`, текущие `debts/assets/goals/budgets/distribution` не стираются
- Если секция `debts` явно отсутствует, pipeline старается сохранить существующие `related_debt_id` связи; если секция есть — ссылки нормализуются только по допустимым debt IDs
- `CSV` / `XLSX` import по-прежнему идёт через create-path и не использует bulk replace; `related_debt_id` теперь корректно прокидывается и там
- `v1.10.1` усиливает раннюю валидацию import payload: битые ссылочные связи, дубликаты `wallet.id`, несколько `system` wallets и невалидные/дублированные `distribution_snapshots` теперь отсекаются раньше

### Backup

- Full backup хранится в `JSON`
- Базовый low-level parser: `import_full_backup_from_json(...)`
- `import_backup(...)` оставлен только как deprecated compatibility wrapper
- JSON export и backup-copy paths записываются atomically через temporary file + `fsync` + `os.replace`
- `backup.export_to_json(...)` теперь поднимает `BackupExportError`, чтобы bootstrap/UI различали export-failure и другие startup-проблемы
- При ошибке сохранения JSON repository пишет `.error` snapshot с несохранённым payload и поднимает `RepositorySaveError`
- Битый или пустой JSON runtime-файл карантинится как `.corrupt_*` и поднимает `RepositoryDataCorruptionError`
- `requirements-pdf.txt` нужен только для PDF-экспорта, не для базового runtime

### Migration

```bash
python migrate_json_to_sqlite.py --dry-run
python migrate_json_to_sqlite.py --json-path data.json --sqlite-path finance.db
```

- Скрипт переносит JSON payload в SQLite в одной явной транзакции
- Pre-schema compatibility поддерживает старые SQLite БД, где таблица `records` ещё без `related_debt_id`
- Migration и bootstrap должны идти в паре с актуальным `db/schema.sql`
- На OneDrive-путях bootstrap дополнительно учитывает sync/coherence риски, выполняет `PRAGMA quick_check` и для больших БД может форсировать synchronous export вместо фонового

## 🧭 Ссылка на подробную архитектуру

Сейчас README оставлен компактным и ориентированным на релиз/use cases.  
Подробная техническая карта слоёв, runtime-flows и модулей вынесена в `docs/architecture.md`.

## 💱 Поддерживаемые валюты

- `KZT` — базовая валюта
- `RUB`
- `USD`
- `EUR`

Курсы обновляются через `CurrencyService`; offline-mode сохраняет последнее доступное состояние.

## 📄 Лицензия

Проект распространяется под лицензией `MIT`. См. `LICENSE`.
