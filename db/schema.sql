PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    currency TEXT NOT NULL CHECK(length(trim(currency)) = 3 AND upper(trim(currency)) = trim(currency)),
    initial_balance REAL NOT NULL DEFAULT 0 CHECK(initial_balance >= 0),
    initial_balance_minor INTEGER DEFAULT NULL CHECK(initial_balance_minor >= 0 OR initial_balance_minor IS NULL),
    system INTEGER NOT NULL DEFAULT 0 CHECK(system IN (0, 1)),
    allow_negative INTEGER NOT NULL DEFAULT 0 CHECK(allow_negative IN (0, 1)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_wallet_id INTEGER NOT NULL,
    to_wallet_id INTEGER NOT NULL,
    date TEXT NOT NULL CHECK(date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    amount_original REAL NOT NULL CHECK(amount_original > 0),
    amount_original_minor INTEGER DEFAULT NULL CHECK(amount_original_minor > 0 OR amount_original_minor IS NULL),
    currency TEXT NOT NULL CHECK(length(trim(currency)) = 3 AND upper(trim(currency)) = trim(currency)),
    rate_at_operation REAL NOT NULL CHECK(rate_at_operation > 0),
    rate_at_operation_text TEXT DEFAULT NULL,
    amount_base REAL NOT NULL CHECK(amount_base > 0),
    amount_base_minor INTEGER DEFAULT NULL CHECK(amount_base_minor > 0 OR amount_base_minor IS NULL),
    description TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(from_wallet_id) REFERENCES wallets(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY(to_wallet_id) REFERENCES wallets(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    CHECK(from_wallet_id <> to_wallet_id)
);

CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK(type IN ('income', 'expense', 'mandatory_expense')),
    date TEXT NOT NULL CHECK(date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    wallet_id INTEGER NOT NULL,
    transfer_id INTEGER,
    related_debt_id INTEGER DEFAULT NULL,
    amount_original REAL NOT NULL CHECK(amount_original >= 0),
    amount_original_minor INTEGER DEFAULT NULL CHECK(amount_original_minor >= 0 OR amount_original_minor IS NULL),
    currency TEXT NOT NULL CHECK(length(trim(currency)) = 3 AND upper(trim(currency)) = trim(currency)),
    rate_at_operation REAL NOT NULL CHECK(rate_at_operation > 0),
    rate_at_operation_text TEXT DEFAULT NULL,
    amount_base REAL NOT NULL CHECK(amount_base >= 0),
    amount_base_minor INTEGER DEFAULT NULL CHECK(amount_base_minor >= 0 OR amount_base_minor IS NULL),
    category TEXT NOT NULL CHECK(length(trim(category)) > 0),
    description TEXT NOT NULL DEFAULT '',
    period TEXT CHECK(period IN ('daily', 'weekly', 'monthly', 'yearly') OR period IS NULL),
    FOREIGN KEY(wallet_id) REFERENCES wallets(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY(transfer_id) REFERENCES transfers(id) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY(related_debt_id) REFERENCES debts(id) ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE CHECK(length(trim(name)) > 0),
    color TEXT NOT NULL DEFAULT '',
    usage_count INTEGER NOT NULL DEFAULT 0,
    last_used_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS record_tags (
    record_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY(record_id, tag_id),
    FOREIGN KEY(record_id) REFERENCES records(id) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES tags(id) ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_name TEXT NOT NULL CHECK(length(trim(contact_name)) > 0),
    kind TEXT NOT NULL CHECK(kind IN ('debt', 'loan')),
    total_amount_minor INTEGER NOT NULL CHECK(total_amount_minor > 0),
    remaining_amount_minor INTEGER NOT NULL CHECK(
        remaining_amount_minor >= 0 AND remaining_amount_minor <= total_amount_minor
    ),
    currency TEXT NOT NULL CHECK(length(trim(currency)) = 3 AND upper(trim(currency)) = trim(currency)),
    interest_rate REAL NOT NULL DEFAULT 0 CHECK(interest_rate >= 0),
    status TEXT NOT NULL CHECK(status IN ('open', 'closed')),
    created_at TEXT NOT NULL CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    closed_at TEXT DEFAULT NULL CHECK(
        closed_at IS NULL OR closed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
    ),
    CHECK(status = 'open' OR remaining_amount_minor = 0)
);

CREATE TABLE IF NOT EXISTS debt_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    debt_id INTEGER NOT NULL,
    record_id INTEGER DEFAULT NULL,
    operation_type TEXT NOT NULL CHECK(
        operation_type IN (
            'debt_take',
            'debt_repay',
            'loan_give',
            'loan_collect',
            'debt_forgive'
        )
    ),
    principal_paid_minor INTEGER NOT NULL CHECK(principal_paid_minor > 0),
    is_write_off INTEGER NOT NULL DEFAULT 0 CHECK(is_write_off IN (0, 1)),
    payment_date TEXT NOT NULL CHECK(payment_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    FOREIGN KEY(debt_id) REFERENCES debts(id) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY(record_id) REFERENCES records(id) ON UPDATE CASCADE ON DELETE SET NULL,
    CHECK(
        (is_write_off = 1 AND operation_type = 'debt_forgive')
        OR (is_write_off = 0 AND operation_type <> 'debt_forgive')
    )
);

CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    category TEXT NOT NULL CHECK(category IN ('bank', 'crypto', 'cash', 'other')),
    currency TEXT NOT NULL CHECK(length(trim(currency)) = 3 AND upper(trim(currency)) = trim(currency)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TEXT NOT NULL CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS asset_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    snapshot_date TEXT NOT NULL CHECK(
        snapshot_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
    ),
    value_minor INTEGER NOT NULL CHECK(value_minor >= 0),
    currency TEXT NOT NULL CHECK(length(trim(currency)) = 3 AND upper(trim(currency)) = trim(currency)),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(asset_id) REFERENCES assets(id) ON UPDATE CASCADE ON DELETE CASCADE,
    UNIQUE(asset_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL CHECK(length(trim(title)) > 0),
    target_amount_minor INTEGER NOT NULL CHECK(target_amount_minor > 0),
    currency TEXT NOT NULL CHECK(length(trim(currency)) = 3 AND upper(trim(currency)) = trim(currency)),
    target_date TEXT DEFAULT NULL CHECK(
        target_date IS NULL OR target_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
    ),
    is_completed INTEGER NOT NULL DEFAULT 0 CHECK(is_completed IN (0, 1)),
    created_at TEXT NOT NULL CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS mandatory_expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_id INTEGER NOT NULL,
    amount_original REAL NOT NULL CHECK(amount_original >= 0),
    amount_original_minor INTEGER DEFAULT NULL CHECK(amount_original_minor >= 0 OR amount_original_minor IS NULL),
    currency TEXT NOT NULL CHECK(length(trim(currency)) = 3 AND upper(trim(currency)) = trim(currency)),
    rate_at_operation REAL NOT NULL CHECK(rate_at_operation > 0),
    rate_at_operation_text TEXT DEFAULT NULL,
    amount_base REAL NOT NULL CHECK(amount_base >= 0),
    amount_base_minor INTEGER DEFAULT NULL CHECK(amount_base_minor >= 0 OR amount_base_minor IS NULL),
    category TEXT NOT NULL CHECK(length(trim(category)) > 0),
    description TEXT NOT NULL CHECK(length(trim(description)) > 0),
    period TEXT NOT NULL CHECK(period IN ('daily', 'weekly', 'monthly', 'yearly')),
    date TEXT DEFAULT NULL,
    auto_pay INTEGER NOT NULL DEFAULT 0 CHECK(auto_pay IN (0, 1)),
    FOREIGN KEY(wallet_id) REFERENCES wallets(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL CHECK(length(trim(category)) > 0),
    scope_type TEXT NOT NULL DEFAULT 'category' CHECK(scope_type IN ('category', 'tag')),
    scope_value TEXT NOT NULL DEFAULT '',
    start_date TEXT NOT NULL CHECK(length(start_date) = 10),
    end_date TEXT NOT NULL CHECK(length(end_date) = 10),
    limit_base REAL NOT NULL CHECK(limit_base > 0),
    limit_base_minor INTEGER NOT NULL DEFAULT 0,
    include_mandatory INTEGER NOT NULL DEFAULT 0 CHECK(include_mandatory IN (0, 1)),
    CHECK(start_date <= end_date)
);

CREATE TABLE IF NOT EXISTS distribution_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    group_name TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    pct REAL NOT NULL DEFAULT 0.0 CHECK(pct >= 0 AND pct <= 100),
    pct_minor INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    UNIQUE(name)
);

CREATE TABLE IF NOT EXISTS distribution_subitems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    sort_order INTEGER NOT NULL DEFAULT 0,
    pct REAL NOT NULL DEFAULT 0.0 CHECK(pct >= 0 AND pct <= 100),
    pct_minor INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    FOREIGN KEY(item_id) REFERENCES distribution_items(id) ON DELETE CASCADE,
    UNIQUE(item_id, name)
);

CREATE TABLE IF NOT EXISTS distribution_snapshots (
    month TEXT PRIMARY KEY CHECK(month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'),
    is_negative INTEGER NOT NULL DEFAULT 0 CHECK(is_negative IN (0, 1)),
    auto_fixed INTEGER NOT NULL DEFAULT 0 CHECK(auto_fixed IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS distribution_snapshot_values (
    snapshot_month TEXT NOT NULL,
    column_key TEXT NOT NULL,
    column_label TEXT NOT NULL,
    column_order INTEGER NOT NULL,
    value_text TEXT NOT NULL,
    PRIMARY KEY(snapshot_month, column_key),
    FOREIGN KEY(snapshot_month) REFERENCES distribution_snapshots(month) ON DELETE CASCADE
);

-- Migration for existing databases:
-- ALTER TABLE wallets ADD COLUMN initial_balance_minor INTEGER DEFAULT NULL;
-- ALTER TABLE transfers ADD COLUMN amount_original_minor INTEGER DEFAULT NULL;
-- ALTER TABLE transfers ADD COLUMN rate_at_operation_text TEXT DEFAULT NULL;
-- ALTER TABLE transfers ADD COLUMN amount_base_minor INTEGER DEFAULT NULL;
-- ALTER TABLE records ADD COLUMN amount_original_minor INTEGER DEFAULT NULL;
-- ALTER TABLE records ADD COLUMN rate_at_operation_text TEXT DEFAULT NULL;
-- ALTER TABLE records ADD COLUMN amount_base_minor INTEGER DEFAULT NULL;
-- ALTER TABLE records ADD COLUMN related_debt_id INTEGER DEFAULT NULL;
-- ALTER TABLE mandatory_expenses ADD COLUMN amount_original_minor INTEGER DEFAULT NULL;
-- ALTER TABLE mandatory_expenses ADD COLUMN rate_at_operation_text TEXT DEFAULT NULL;
-- ALTER TABLE mandatory_expenses ADD COLUMN amount_base_minor INTEGER DEFAULT NULL;
-- ALTER TABLE mandatory_expenses ADD COLUMN date TEXT DEFAULT NULL;
-- ALTER TABLE mandatory_expenses ADD COLUMN auto_pay INTEGER NOT NULL DEFAULT 0;
-- ALTER TABLE distribution_snapshots ADD COLUMN auto_fixed INTEGER NOT NULL DEFAULT 0;
-- ALTER TABLE budgets ADD COLUMN scope_type TEXT NOT NULL DEFAULT 'category';
-- ALTER TABLE budgets ADD COLUMN scope_value TEXT NOT NULL DEFAULT '';
-- Migration 002:
-- ALTER TABLE records RENAME COLUMN amount_kzt TO amount_base;
-- ALTER TABLE records RENAME COLUMN amount_kzt_minor TO amount_base_minor;
-- ALTER TABLE transfers RENAME COLUMN amount_kzt TO amount_base;
-- ALTER TABLE transfers RENAME COLUMN amount_kzt_minor TO amount_base_minor;
-- ALTER TABLE mandatory_expenses RENAME COLUMN amount_kzt TO amount_base;
-- ALTER TABLE mandatory_expenses RENAME COLUMN amount_kzt_minor TO amount_base_minor;
-- ALTER TABLE budgets RENAME COLUMN limit_kzt TO limit_base;
-- ALTER TABLE budgets RENAME COLUMN limit_kzt_minor TO limit_base_minor;

CREATE INDEX IF NOT EXISTS idx_records_date ON records(date);
CREATE INDEX IF NOT EXISTS idx_records_wallet_id ON records(wallet_id);
CREATE INDEX IF NOT EXISTS idx_records_wallet_date ON records(wallet_id, date);
CREATE INDEX IF NOT EXISTS idx_records_related_debt_id ON records(related_debt_id);
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
CREATE INDEX IF NOT EXISTS idx_record_tags_record_id ON record_tags(record_id);
CREATE INDEX IF NOT EXISTS idx_record_tags_tag_id ON record_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_transfers_date ON transfers(date);
CREATE INDEX IF NOT EXISTS idx_transfers_wallet_from ON transfers(from_wallet_id);
CREATE INDEX IF NOT EXISTS idx_transfers_wallet_to ON transfers(to_wallet_id);
CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category);
CREATE INDEX IF NOT EXISTS idx_assets_is_active ON assets(is_active);
CREATE INDEX IF NOT EXISTS idx_asset_snapshots_asset_date ON asset_snapshots(asset_id, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_mandatory_expenses_wallet_id ON mandatory_expenses(wallet_id);
CREATE INDEX IF NOT EXISTS idx_budgets_category ON budgets(category);
CREATE INDEX IF NOT EXISTS idx_budgets_scope ON budgets(scope_type, scope_value);
CREATE INDEX IF NOT EXISTS idx_budgets_dates ON budgets(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_goals_completed ON goals(is_completed);
CREATE INDEX IF NOT EXISTS idx_goals_target_date ON goals(target_date);
CREATE INDEX IF NOT EXISTS idx_debts_contact_name ON debts(contact_name);
CREATE INDEX IF NOT EXISTS idx_debts_status ON debts(status);
CREATE INDEX IF NOT EXISTS idx_debt_payments_debt_id ON debt_payments(debt_id);
CREATE INDEX IF NOT EXISTS idx_debt_payments_record_id ON debt_payments(record_id);
CREATE INDEX IF NOT EXISTS idx_dist_items_order ON distribution_items(sort_order);
CREATE INDEX IF NOT EXISTS idx_dist_subitems_item ON distribution_subitems(item_id);
CREATE INDEX IF NOT EXISTS idx_dist_snapshot_values_month_order
ON distribution_snapshot_values(snapshot_month, column_order);
