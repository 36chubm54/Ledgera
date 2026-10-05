use crate::{
    StorageResult, sqlite_err, storage_clear_read_connection_cache, with_cached_read_connection,
};
use ledgera_engine_core::{minor_to_money_value, to_minor_units};
use rusqlite::{Connection, OptionalExtension, params};
use std::{collections::HashMap, fs, path::Path};

#[derive(Debug, Clone, PartialEq)]
pub struct AssetPayload {
    pub id: i64,
    pub name: String,
    pub category: String,
    pub currency: String,
    pub is_active: bool,
    pub created_at: String,
    pub description: String,
    pub current_value_minor: i64,
    pub current_value_base: f64,
    pub current_snapshot_date: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct AssetBreakdownPayload {
    pub label: String,
    pub amount_base: f64,
    pub asset_count: i64,
    pub color: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CapitalPointPayload {
    pub month: String,
    pub balance_base: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct GoalPayload {
    pub id: i64,
    pub title: String,
    pub target_amount_minor: i64,
    pub currency: String,
    pub target_date: Option<String>,
    pub is_completed: bool,
    pub created_at: String,
    pub description: String,
    pub current_amount_minor: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DashboardPayload {
    pub base_currency: String,
    pub net_worth_base: f64,
    pub total_assets_base: f64,
    pub active_asset_count: i64,
    pub total_asset_count: i64,
    pub completed_goal_count: i64,
    pub total_goal_count: i64,
    pub capital: Vec<CapitalPointPayload>,
    pub asset_breakdown: Vec<AssetBreakdownPayload>,
    pub assets: Vec<AssetPayload>,
    pub goals: Vec<GoalPayload>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct AssetSnapshotUpdatePayload {
    pub asset_id: i64,
    pub value: String,
    pub note: String,
}

const CATEGORY_COLORS: &[(&str, &str)] = &[
    ("bank", "#4F8EF7"),
    ("crypto", "#F5C542"),
    ("cash", "#2E8B70"),
    ("other", "#858585"),
];

fn category_color(category: &str) -> String {
    CATEGORY_COLORS
        .iter()
        .find(|(key, _)| *key == category)
        .map(|(_, color)| (*color).to_owned())
        .unwrap_or_else(|| "#858585".to_owned())
}

fn validate_asset_fields(name: &str, category: &str, currency: &str) -> StorageResult<()> {
    if name.trim().is_empty() {
        return Err("Asset name is required".to_owned());
    }
    if !matches!(category, "bank" | "crypto" | "cash" | "other") {
        return Err("Invalid asset category".to_owned());
    }
    let normalized = currency.trim().to_uppercase();
    if normalized.len() != 3 || !normalized.chars().all(|value| value.is_ascii_uppercase()) {
        return Err("Invalid asset currency".to_owned());
    }
    Ok(())
}

fn asset_from_conn(conn: &Connection, asset_id: i64) -> StorageResult<AssetPayload> {
    conn.query_row(
        "SELECT a.id, a.name, a.category, a.currency, a.is_active, a.created_at, a.description,
                COALESCE(s.value_minor, 0), s.snapshot_date
         FROM assets a
         LEFT JOIN asset_snapshots s ON s.id = (
             SELECT latest.id FROM asset_snapshots latest
             WHERE latest.asset_id = a.id
             ORDER BY latest.snapshot_date DESC, latest.id DESC LIMIT 1
         )
         WHERE a.id = ?",
        [asset_id],
        |row| {
            let currency: String = row.get(3)?;
            let value_minor: i64 = row.get(7)?;
            Ok(AssetPayload {
                id: row.get(0)?,
                name: row.get(1)?,
                category: row.get(2)?,
                current_value_base: minor_to_money_value(value_minor),
                currency,
                is_active: row.get(4)?,
                created_at: row.get(5)?,
                description: row.get(6)?,
                current_value_minor: value_minor,
                current_snapshot_date: row.get(8)?,
            })
        },
    )
    .optional()
    .map_err(sqlite_err)?
    .ok_or_else(|| format!("Asset not found: {asset_id}"))
}

pub fn asset_rows(db_path: &str, active_only: bool) -> StorageResult<Vec<AssetPayload>> {
    with_cached_read_connection(db_path, |conn| {
        let filter = if active_only {
            "WHERE a.is_active = 1"
        } else {
            ""
        };
        let mut stmt = conn
            .prepare(&format!(
                "SELECT a.id FROM assets a {filter} ORDER BY a.id ASC"
            ))
            .map_err(sqlite_err)?;
        let ids = stmt
            .query_map([], |row| row.get::<_, i64>(0))
            .map_err(sqlite_err)?;
        ids.map(|id| {
            id.map_err(sqlite_err)
                .and_then(|id| asset_from_conn(conn, id))
        })
        .collect()
    })
}

pub fn asset_create(
    db_path: &str,
    name: &str,
    category: &str,
    currency: &str,
    value: &str,
    snapshot_date: &str,
    description: &str,
) -> StorageResult<AssetPayload> {
    validate_asset_fields(name, category, currency)?;
    let value_minor = to_minor_units(value)?;
    if value_minor < 0 {
        return Err("Asset value must be zero or positive".to_owned());
    }
    let mut conn = Connection::open(db_path).map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute(
        "INSERT INTO assets (name, category, currency, created_at, description) VALUES (?, ?, ?, ?, ?)",
        params![name.trim(), category, currency.trim().to_uppercase(), snapshot_date, description.trim()],
    )
    .map_err(sqlite_err)?;
    let id = tx.last_insert_rowid();
    tx.execute(
        "INSERT INTO asset_snapshots (asset_id, snapshot_date, value_minor, currency, note) VALUES (?, ?, ?, ?, '')",
        params![id, snapshot_date, value_minor, currency.trim().to_uppercase()],
    )
    .map_err(sqlite_err)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    asset_from_conn(&conn, id)
}

pub fn asset_update(
    db_path: &str,
    asset_id: i64,
    name: &str,
    category: &str,
    currency: &str,
    value: &str,
    snapshot_date: &str,
    description: &str,
) -> StorageResult<AssetPayload> {
    validate_asset_fields(name, category, currency)?;
    let value_minor = to_minor_units(value)?;
    if value_minor < 0 {
        return Err("Asset value must be zero or positive".to_owned());
    }
    let mut conn = Connection::open(db_path).map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    let changed = tx
        .execute(
            "UPDATE assets SET name = ?, category = ?, currency = ?, description = ? WHERE id = ?",
            params![
                name.trim(),
                category,
                currency.trim().to_uppercase(),
                description.trim(),
                asset_id
            ],
        )
        .map_err(sqlite_err)?;
    if changed == 0 {
        return Err(format!("Asset not found: {asset_id}"));
    }
    tx.execute(
        "INSERT INTO asset_snapshots (asset_id, snapshot_date, value_minor, currency, note)
         VALUES (?, ?, ?, ?, 'Updated from asset form')
         ON CONFLICT(asset_id, snapshot_date) DO UPDATE SET value_minor = excluded.value_minor, currency = excluded.currency",
        params![asset_id, snapshot_date, value_minor, currency.trim().to_uppercase()],
    )
    .map_err(sqlite_err)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    asset_from_conn(&conn, asset_id)
}

pub fn asset_add_snapshot(
    db_path: &str,
    asset_id: i64,
    value: &str,
    snapshot_date: &str,
    note: &str,
) -> StorageResult<AssetPayload> {
    asset_add_snapshots_bulk(
        db_path,
        &[AssetSnapshotUpdatePayload {
            asset_id,
            value: value.to_owned(),
            note: note.to_owned(),
        }],
        snapshot_date,
    )?
    .into_iter()
    .next()
    .ok_or_else(|| "Asset snapshot was not saved".to_owned())
}

pub fn asset_add_snapshots_bulk(
    db_path: &str,
    updates: &[AssetSnapshotUpdatePayload],
    snapshot_date: &str,
) -> StorageResult<Vec<AssetPayload>> {
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    let tx = conn.unchecked_transaction().map_err(sqlite_err)?;
    for update in updates {
        let value_minor = to_minor_units(&update.value)?;
        if value_minor < 0 {
            return Err("Asset value must be zero or positive".to_owned());
        }
        let currency: String = tx
            .query_row(
                "SELECT currency FROM assets WHERE id = ? AND is_active = 1",
                [update.asset_id],
                |row| row.get(0),
            )
            .optional()
            .map_err(sqlite_err)?
            .ok_or_else(|| format!("Active asset not found: {}", update.asset_id))?;
        tx.execute(
            "INSERT INTO asset_snapshots (asset_id, snapshot_date, value_minor, currency, note)
             VALUES (?, ?, ?, ?, ?)
             ON CONFLICT(asset_id, snapshot_date) DO UPDATE SET value_minor = excluded.value_minor, note = excluded.note",
            params![update.asset_id, snapshot_date, value_minor, currency, update.note.trim()],
        ).map_err(sqlite_err)?;
    }
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    updates
        .iter()
        .map(|update| asset_from_conn(&conn, update.asset_id))
        .collect()
}

pub fn asset_set_active(db_path: &str, asset_id: i64, active: bool) -> StorageResult<AssetPayload> {
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    let changed = conn
        .execute(
            "UPDATE assets SET is_active = ? WHERE id = ?",
            params![active, asset_id],
        )
        .map_err(sqlite_err)?;
    if changed == 0 {
        return Err(format!("Asset not found: {asset_id}"));
    }
    storage_clear_read_connection_cache();
    asset_from_conn(&conn, asset_id)
}

pub fn goal_rows(db_path: &str) -> StorageResult<Vec<GoalPayload>> {
    with_cached_read_connection(db_path, |conn| {
        let mut stmt = conn.prepare(
            "SELECT id, title, target_amount_minor, currency, target_date, is_completed, created_at, description
             FROM goals ORDER BY is_completed ASC, target_date IS NULL ASC, target_date ASC, id ASC"
        ).map_err(sqlite_err)?;
        let rows = stmt
            .query_map([], |row| {
                Ok(GoalPayload {
                    id: row.get(0)?,
                    title: row.get(1)?,
                    target_amount_minor: row.get(2)?,
                    currency: row.get(3)?,
                    target_date: row.get(4)?,
                    is_completed: row.get(5)?,
                    created_at: row.get(6)?,
                    description: row.get(7)?,
                    current_amount_minor: 0,
                })
            })
            .map_err(sqlite_err)?;
        rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
    })
}

pub fn goal_create(
    db_path: &str,
    title: &str,
    target_amount: &str,
    currency: &str,
    target_date: Option<&str>,
    description: &str,
    created_at: &str,
) -> StorageResult<GoalPayload> {
    let target_minor = to_minor_units(target_amount)?;
    if title.trim().is_empty() || target_minor <= 0 {
        return Err("Goal title and positive target amount are required".to_owned());
    }
    let normalized = currency.trim().to_uppercase();
    if normalized.len() != 3 || !normalized.chars().all(|value| value.is_ascii_uppercase()) {
        return Err("Invalid goal currency".to_owned());
    }
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    conn.execute("INSERT INTO goals (title, target_amount_minor, currency, target_date, created_at, description) VALUES (?, ?, ?, ?, ?, ?)", params![title.trim(), target_minor, normalized, target_date, created_at, description.trim()]).map_err(sqlite_err)?;
    let id = conn.last_insert_rowid();
    storage_clear_read_connection_cache();
    let rows = goal_rows(db_path)?;
    rows.into_iter()
        .find(|row| row.id == id)
        .ok_or_else(|| format!("Goal not found: {id}"))
}

pub fn goal_set_completed(db_path: &str, goal_id: i64, completed: bool) -> StorageResult<()> {
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    if conn
        .execute(
            "UPDATE goals SET is_completed = ? WHERE id = ?",
            params![completed, goal_id],
        )
        .map_err(sqlite_err)?
        == 0
    {
        return Err(format!("Goal not found: {goal_id}"));
    }
    storage_clear_read_connection_cache();
    Ok(())
}

pub fn goal_delete(db_path: &str, goal_id: i64) -> StorageResult<()> {
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    if conn
        .execute("DELETE FROM goals WHERE id = ?", [goal_id])
        .map_err(sqlite_err)?
        == 0
    {
        return Err(format!("Goal not found: {goal_id}"));
    }
    storage_clear_read_connection_cache();
    Ok(())
}

fn current_currency_rates(db_path: &str) -> StorageResult<HashMap<String, f64>> {
    let mut rates = HashMap::new();
    let path = Path::new(db_path)
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join("currency_rates.json");
    if path.is_file() {
        let text = fs::read_to_string(&path)
            .map_err(|err| format!("Failed to read current currency rates: {err}"))?;
        let configured: HashMap<String, f64> = serde_json::from_str(&text)
            .map_err(|err| format!("Invalid current currency rates: {err}"))?;
        for (currency, rate) in configured {
            if rate.is_finite() && rate > 0.0 {
                rates.insert(currency.trim().to_uppercase(), rate);
            }
        }
    }
    let base = crate::base_currency_code(db_path)?;
    rates.insert(base.to_uppercase(), 1.0);
    Ok(rates)
}

fn convert_minor(
    value_minor: i64,
    currency: &str,
    rates: &HashMap<String, f64>,
) -> StorageResult<f64> {
    let rate = rates
        .get(&currency.trim().to_uppercase())
        .copied()
        .ok_or_else(|| {
            format!(
                "Dashboard has no usable rate for currency {}",
                currency.trim().to_uppercase()
            )
        })?;
    Ok(minor_to_money_value(value_minor) * rate)
}

fn wallet_total_base(
    db_path: &str,
    rates: &HashMap<String, f64>,
    up_to_date: Option<&str>,
) -> StorageResult<f64> {
    Ok(crate::wallet_balance_rows(db_path, up_to_date)?
        .iter()
        .map(|row| convert_minor(((row.3 + row.4) * 100.0).round() as i64, &row.2, rates))
        .collect::<StorageResult<Vec<_>>>()?
        .into_iter()
        .sum())
}

fn asset_total_base_at(
    db_path: &str,
    rates: &HashMap<String, f64>,
    up_to_date: &str,
) -> StorageResult<f64> {
    with_cached_read_connection(db_path, |conn| {
        let mut stmt = conn
            .prepare(
                "SELECT snapshot.value_minor, snapshot.currency
             FROM assets AS asset JOIN asset_snapshots AS snapshot ON snapshot.asset_id = asset.id
             WHERE asset.is_active = 1 AND snapshot.snapshot_date = (
                 SELECT MAX(previous.snapshot_date) FROM asset_snapshots AS previous
                 WHERE previous.asset_id = snapshot.asset_id AND previous.snapshot_date <= ?1
             )",
            )
            .map_err(sqlite_err)?;
        let rows = stmt
            .query_map([up_to_date], |row| {
                Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
            })
            .map_err(sqlite_err)?;
        rows.map(|row| {
            row.map_err(sqlite_err)
                .and_then(|(minor, currency)| convert_minor(minor, &currency, rates))
        })
        .collect::<StorageResult<Vec<_>>>()
        .map(|values| values.into_iter().sum())
    })
}

fn capital_points(
    db_path: &str,
    rates: &HashMap<String, f64>,
) -> StorageResult<Vec<CapitalPointPayload>> {
    let months = with_cached_read_connection(db_path, |conn| {
        let mut stmt = conn
            .prepare(
                "SELECT DISTINCT month FROM (
                    SELECT substr(snapshot_date, 1, 7) AS month FROM asset_snapshots
                    UNION
                    SELECT substr(date, 1, 7) AS month FROM records
                ) WHERE month IS NOT NULL ORDER BY month",
            )
            .map_err(sqlite_err)?;
        let rows = stmt
            .query_map([], |row| row.get::<_, String>(0))
            .map_err(sqlite_err)?;
        rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
    })?;

    let current_date = crate::current_local_date();
    let current_month = format!("{:04}-{:02}", current_date.0, current_date.1);
    let months = if months.is_empty() {
        vec![current_month]
    } else if months.iter().any(|month| month == &current_month) {
        months
    } else {
        months
            .into_iter()
            .chain(std::iter::once(current_month))
            .collect()
    };

    months
        .into_iter()
        .map(|month| {
            let month_end = format!("{month}-31");
            let wallet = wallet_total_base(db_path, rates, Some(&month_end))?;
            let assets = asset_total_base_at(db_path, rates, &month_end)?;
            Ok(CapitalPointPayload {
                month,
                balance_base: wallet + assets,
            })
        })
        .collect()
}

pub fn dashboard_payload(db_path: &str) -> StorageResult<DashboardPayload> {
    let base_currency = crate::base_currency_code(db_path)?;
    let rates = current_currency_rates(db_path)?;
    let assets = asset_rows(db_path, false)?;
    let active_assets: Vec<_> = assets.iter().filter(|asset| asset.is_active).collect();
    let total_assets_base: f64 = active_assets
        .iter()
        .map(|asset| convert_minor(asset.current_value_minor, &asset.currency, &rates))
        .collect::<StorageResult<Vec<_>>>()?
        .into_iter()
        .sum();
    let mut breakdown = Vec::new();
    for category in ["bank", "crypto", "cash", "other"] {
        let rows: Vec<_> = active_assets
            .iter()
            .filter(|asset| asset.category == category)
            .collect();
        let amount = rows
            .iter()
            .map(|asset| convert_minor(asset.current_value_minor, &asset.currency, &rates))
            .collect::<StorageResult<Vec<_>>>()?
            .into_iter()
            .sum();
        if !rows.is_empty() {
            breakdown.push(AssetBreakdownPayload {
                label: category.to_owned(),
                amount_base: amount,
                asset_count: rows.len() as i64,
                color: category_color(category),
            });
        }
    }
    let wallet_rows = crate::wallet_balance_rows(db_path, None)?;
    let mut goals = goal_rows(db_path)?;
    for goal in &mut goals {
        let asset_minor = active_assets
            .iter()
            .filter(|asset| asset.currency == goal.currency)
            .map(|asset| asset.current_value_minor)
            .sum::<i64>();
        let wallet_minor = wallet_rows
            .iter()
            .filter(|row| row.2 == goal.currency)
            .map(|row| ((row.3 + row.4) * 100.0).round() as i64)
            .sum::<i64>();
        goal.current_amount_minor = asset_minor + wallet_minor;
    }
    let completed_goal_count = goals.iter().filter(|goal| goal.is_completed).count() as i64;
    let wallet_total = wallet_total_base(db_path, &rates, None)?;
    let capital = capital_points(db_path, &rates)?;
    Ok(DashboardPayload {
        base_currency,
        net_worth_base: wallet_total + total_assets_base,
        total_assets_base,
        active_asset_count: active_assets.len() as i64,
        total_asset_count: assets.len() as i64,
        completed_goal_count,
        total_goal_count: goals.len() as i64,
        capital,
        asset_breakdown: breakdown,
        assets,
        goals,
    })
}

#[cfg(test)]
mod tests {
    use crate::{
        AssetSnapshotUpdatePayload, asset_add_snapshot, asset_add_snapshots_bulk, asset_create,
        dashboard_payload, goal_create, goal_delete, goal_set_completed, initialize_database,
    };
    use std::time::{SystemTime, UNIX_EPOCH};

    fn test_db_path() -> String {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock")
            .as_nanos();
        std::env::temp_dir()
            .join(format!("ledgera_dashboard_{unique}.db"))
            .to_string_lossy()
            .into_owned()
    }

    #[test]
    fn dashboard_uses_latest_asset_snapshot_and_builds_capital_history() {
        let db_path = test_db_path();
        initialize_database(&db_path).expect("database initialization");
        let asset = asset_create(&db_path, "Reserve", "bank", "KZT", "1000", "2026-01-01", "")
            .expect("asset creation");
        asset_add_snapshot(&db_path, asset.id, "1250", "2026-02-01", "").expect("asset snapshot");

        let snapshot = dashboard_payload(&db_path).expect("dashboard snapshot");

        assert_eq!(snapshot.total_assets_base, 1250.0);
        assert_eq!(snapshot.assets[0].current_value_minor, 125000);
        assert!(snapshot.capital.len() >= 2);
        assert_eq!(snapshot.capital[0].month, "2026-01");
        assert_eq!(snapshot.capital[0].balance_base, 1000.0);
        assert_eq!(snapshot.capital[1].month, "2026-02");
        assert_eq!(snapshot.capital[1].balance_base, 1250.0);

        let goal = goal_create(
            &db_path,
            "Emergency fund",
            "5000",
            "KZT",
            None,
            "",
            "2026-01-01",
        )
        .expect("goal creation");
        assert_eq!(
            dashboard_payload(&db_path).unwrap().goals[0].current_amount_minor,
            125000
        );
        goal_set_completed(&db_path, goal.id, true).expect("goal completion");
        assert_eq!(dashboard_payload(&db_path).unwrap().completed_goal_count, 1);
        goal_delete(&db_path, goal.id).expect("goal deletion");
        assert_eq!(dashboard_payload(&db_path).unwrap().total_goal_count, 0);

        let _ = std::fs::remove_file(db_path);
    }

    #[test]
    fn bulk_asset_snapshots_are_atomic() {
        let db_path = test_db_path();
        initialize_database(&db_path).expect("database initialization");
        let asset = asset_create(&db_path, "Reserve", "bank", "KZT", "1000", "2026-01-01", "")
            .expect("asset creation");
        let result = asset_add_snapshots_bulk(
            &db_path,
            &[
                AssetSnapshotUpdatePayload {
                    asset_id: asset.id,
                    value: "2000".to_owned(),
                    note: "".to_owned(),
                },
                AssetSnapshotUpdatePayload {
                    asset_id: -1,
                    value: "3000".to_owned(),
                    note: "".to_owned(),
                },
            ],
            "2026-02-01",
        );
        assert!(result.is_err());
        let snapshot = dashboard_payload(&db_path).expect("dashboard snapshot");
        assert_eq!(snapshot.assets[0].current_value_minor, 100000);
        let _ = std::fs::remove_file(db_path);
    }
}
