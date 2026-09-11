use crate::{
    StorageResult, export_temp_path, normalize_tag_name, replace_export_file, sqlite_err,
    storage_clear_read_connection_cache,
};
use rusqlite::{Connection, OptionalExtension, Transaction, types::Value};
use serde_json::{Map, Number, Value as JsonValue};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::fs;
use std::path::Path;

const BACKUP_FORMAT: &str = "ledgera.full_backup";
const BACKUP_VERSION: i64 = 1;
const MAX_BACKUP_BYTES: u64 = 50 * 1024 * 1024;

const BACKUP_TABLES: &[&str] = &[
    "wallets",
    "transfers",
    "mandatory_expenses",
    "records",
    "tags",
    "record_tags",
    "debts",
    "debt_payments",
    "budgets",
];

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct FullBackupResult {
    pub path: String,
    pub imported_rows: i64,
    pub budget_rows: i64,
    pub checksum: String,
}

fn table_exists(conn: &Connection, table: &str) -> StorageResult<bool> {
    conn.query_row(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        [table],
        |_| Ok(()),
    )
    .optional()
    .map_err(sqlite_err)
    .map(|value| value.is_some())
}

fn table_columns(conn: &Connection, table: &str) -> StorageResult<Vec<String>> {
    let mut stmt = conn
        .prepare(&format!("PRAGMA table_info({table})"))
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| row.get::<_, String>(1))
        .map_err(sqlite_err)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
}

#[derive(Debug, Clone)]
struct TableColumn {
    name: String,
    declared_type: String,
    not_null: bool,
    has_default: bool,
    is_primary_key: bool,
}

fn table_schema(conn: &Connection, table: &str) -> StorageResult<Vec<TableColumn>> {
    let mut stmt = conn
        .prepare(&format!("PRAGMA table_info({table})"))
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| {
            Ok(TableColumn {
                name: row.get(1)?,
                declared_type: row.get::<_, String>(2)?.to_ascii_uppercase(),
                not_null: row.get::<_, i64>(3)? != 0,
                has_default: row.get::<_, Option<String>>(4)?.is_some(),
                is_primary_key: row.get::<_, i64>(5)? != 0,
            })
        })
        .map_err(sqlite_err)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
}

fn sql_value_to_json(value: rusqlite::types::ValueRef<'_>) -> JsonValue {
    match value {
        rusqlite::types::ValueRef::Null => JsonValue::Null,
        rusqlite::types::ValueRef::Integer(value) => JsonValue::Number(value.into()),
        rusqlite::types::ValueRef::Real(value) => Number::from_f64(value)
            .map(JsonValue::Number)
            .unwrap_or(JsonValue::Null),
        rusqlite::types::ValueRef::Text(value) => {
            JsonValue::String(String::from_utf8_lossy(value).into_owned())
        }
        rusqlite::types::ValueRef::Blob(value) => {
            JsonValue::String(format!("base64:{}", base64_like(value)))
        }
    }
}

fn base64_like(value: &[u8]) -> String {
    value.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn read_table(conn: &Connection, table: &str) -> StorageResult<Vec<JsonValue>> {
    if !table_exists(conn, table)? {
        return Ok(Vec::new());
    }
    let columns = table_columns(conn, table)?;
    let mut stmt = conn
        .prepare(&format!("SELECT * FROM {table}"))
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| {
            let mut object = Map::new();
            for (index, column) in columns.iter().enumerate() {
                object.insert(column.clone(), sql_value_to_json(row.get_ref(index)?));
            }
            Ok(JsonValue::Object(object))
        })
        .map_err(sqlite_err)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
}

fn load_json(path: &str) -> StorageResult<JsonValue> {
    let metadata = fs::metadata(path).map_err(|error| error.to_string())?;
    if metadata.len() > MAX_BACKUP_BYTES {
        return Err(format!("Backup file exceeds {MAX_BACKUP_BYTES} bytes"));
    }
    let bytes = fs::read(path).map_err(|error| error.to_string())?;
    serde_json::from_slice(&bytes).map_err(|error| format!("Invalid backup JSON: {error}"))
}

fn sections(payload: &JsonValue) -> StorageResult<&Map<String, JsonValue>> {
    let object = payload
        .as_object()
        .ok_or_else(|| "Backup root must be a JSON object".to_owned())?;
    if object.get("format").and_then(JsonValue::as_str) != Some(BACKUP_FORMAT) {
        return Err("Unsupported backup format".to_owned());
    }
    if object.get("version").and_then(JsonValue::as_i64) != Some(BACKUP_VERSION) {
        return Err("Unsupported backup version".to_owned());
    }
    Ok(object)
}

fn payload_checksum(payload: &JsonValue) -> StorageResult<String> {
    let mut object = payload
        .as_object()
        .cloned()
        .ok_or_else(|| "Backup root must be a JSON object".to_owned())?;
    object.remove("checksum");
    let canonical = serde_json::to_vec(&JsonValue::Object(object))
        .map_err(|error| format!("Cannot canonicalize backup: {error}"))?;
    let digest = Sha256::digest(canonical);
    Ok(digest.iter().map(|byte| format!("{byte:02x}")).collect())
}

fn verify_checksum(payload: &JsonValue) -> StorageResult<String> {
    let object = sections(payload)?;
    let Some(value) = object.get("checksum").and_then(JsonValue::as_str) else {
        return Err("Backup checksum is required".to_owned());
    };
    let actual = payload_checksum(payload)?;
    let expected = value.strip_prefix("sha256:").unwrap_or(value);
    if expected.len() != 64
        || !expected
            .chars()
            .all(|character| character.is_ascii_hexdigit())
    {
        return Err("Invalid backup checksum format".to_owned());
    }
    if !expected.eq_ignore_ascii_case(&actual) {
        return Err("Backup checksum mismatch".to_owned());
    }
    Ok(format!("sha256:{actual}"))
}

fn validate_scalar_type(
    table: &str,
    row_index: usize,
    column: &TableColumn,
    value: &JsonValue,
) -> StorageResult<()> {
    if value.is_null() {
        if column.not_null || column.is_primary_key {
            return Err(format!(
                "{table} row {row_index} column '{}' cannot be null",
                column.name
            ));
        }
        return Ok(());
    }
    let valid = if column.declared_type.contains("INT") {
        value.as_i64().is_some()
    } else if column.declared_type.contains("REAL")
        || column.declared_type.contains("FLOA")
        || column.declared_type.contains("DOUB")
    {
        value.as_f64().is_some_and(f64::is_finite)
    } else if column.declared_type.contains("TEXT")
        || column.declared_type.contains("CHAR")
        || column.declared_type.contains("CLOB")
    {
        value.is_string()
    } else {
        matches!(
            value,
            JsonValue::Null | JsonValue::Bool(_) | JsonValue::Number(_) | JsonValue::String(_)
        )
    };
    if !valid {
        return Err(format!(
            "{table} row {row_index} column '{}' has an invalid JSON type",
            column.name
        ));
    }
    if column.name == "id" || column.name.ends_with("_id") {
        if value.as_i64().map(|id| id <= 0).unwrap_or(true) {
            return Err(format!(
                "{table} row {row_index} column '{}' must be a positive integer",
                column.name
            ));
        }
    }
    if [
        "system",
        "allow_negative",
        "is_active",
        "auto_pay",
        "include_mandatory",
        "is_write_off",
    ]
    .contains(&column.name.as_str())
        && !matches!(value.as_i64(), Some(0 | 1))
    {
        return Err(format!(
            "{table} row {row_index} column '{}' must be 0 or 1",
            column.name
        ));
    }
    if ["date", "start_date", "end_date", "payment_date"].contains(&column.name.as_str())
        && !value.is_null()
    {
        validate_backup_date(
            value.as_str().ok_or_else(|| {
                format!(
                    "{table} row {row_index} column '{}' must be text",
                    column.name
                )
            })?,
            &column.name,
        )?;
    }
    Ok(())
}

fn row_id_set(table: &str, rows: &[JsonValue]) -> StorageResult<HashSet<i64>> {
    rows.iter()
        .enumerate()
        .map(|(index, row)| {
            row.as_object()
                .and_then(|object| object.get("id"))
                .and_then(JsonValue::as_i64)
                .ok_or_else(|| format!("{table} row {} must have an integer id", index + 1))
        })
        .collect()
}

fn validate_reference(
    table: &str,
    row_index: usize,
    column: &str,
    value: Option<&JsonValue>,
    target: &HashSet<i64>,
) -> StorageResult<()> {
    let Some(value) = value else {
        return Ok(());
    };
    if value.is_null() {
        return Ok(());
    }
    let Some(id) = value.as_i64() else {
        return Err(format!(
            "{table} row {row_index} column '{column}' must be an integer"
        ));
    };
    if !target.contains(&id) {
        return Err(format!(
            "{table} row {row_index} column '{column}' references missing id {id}"
        ));
    }
    Ok(())
}

fn validate_relationships(object: &Map<String, JsonValue>) -> StorageResult<()> {
    let rows = |table: &str| object[table].as_array().unwrap();
    let wallets = row_id_set("wallets", rows("wallets"))?;
    let transfers = row_id_set("transfers", rows("transfers"))?;
    let tags = row_id_set("tags", rows("tags"))?;
    let records = row_id_set("records", rows("records"))?;
    let debts = row_id_set("debts", rows("debts"))?;
    for (index, row) in rows("transfers").iter().enumerate() {
        let row = row.as_object().unwrap();
        validate_reference(
            "transfers",
            index + 1,
            "from_wallet_id",
            row.get("from_wallet_id"),
            &wallets,
        )?;
        validate_reference(
            "transfers",
            index + 1,
            "to_wallet_id",
            row.get("to_wallet_id"),
            &wallets,
        )?;
    }
    for (index, row) in rows("mandatory_expenses").iter().enumerate() {
        validate_reference(
            "mandatory_expenses",
            index + 1,
            "wallet_id",
            row.as_object().unwrap().get("wallet_id"),
            &wallets,
        )?;
    }
    for (index, row) in rows("records").iter().enumerate() {
        let row = row.as_object().unwrap();
        validate_reference(
            "records",
            index + 1,
            "wallet_id",
            row.get("wallet_id"),
            &wallets,
        )?;
        validate_reference(
            "records",
            index + 1,
            "transfer_id",
            row.get("transfer_id"),
            &transfers,
        )?;
        validate_reference(
            "records",
            index + 1,
            "related_debt_id",
            row.get("related_debt_id"),
            &debts,
        )?;
    }
    let mut record_tags = HashSet::new();
    for (index, row) in rows("record_tags").iter().enumerate() {
        let row = row.as_object().unwrap();
        let record_id = row["record_id"].as_i64().unwrap();
        let tag_id = row["tag_id"].as_i64().unwrap();
        validate_reference(
            "record_tags",
            index + 1,
            "record_id",
            row.get("record_id"),
            &records,
        )?;
        validate_reference("record_tags", index + 1, "tag_id", row.get("tag_id"), &tags)?;
        if !record_tags.insert((record_id, tag_id)) {
            return Err(format!(
                "record_tags row {} duplicates a record/tag link",
                index + 1
            ));
        }
    }
    for (index, row) in rows("debt_payments").iter().enumerate() {
        let row = row.as_object().unwrap();
        validate_reference(
            "debt_payments",
            index + 1,
            "debt_id",
            row.get("debt_id"),
            &debts,
        )?;
        validate_reference(
            "debt_payments",
            index + 1,
            "record_id",
            row.get("record_id"),
            &records,
        )?;
    }
    Ok(())
}

fn validate_table_rows(conn: &Connection, table: &str, rows: &[JsonValue]) -> StorageResult<()> {
    let schema = table_schema(conn, table)?;
    let known: HashSet<_> = schema.iter().map(|column| column.name.as_str()).collect();
    for (index, value) in rows.iter().enumerate() {
        let row_index = index + 1;
        let object = value
            .as_object()
            .ok_or_else(|| format!("{table} row {row_index} must be an object"))?;
        for name in object.keys() {
            if !known.contains(name.as_str()) {
                return Err(format!(
                    "{table} row {row_index} contains unknown column '{name}'"
                ));
            }
        }
        for column in &schema {
            if column.is_primary_key || (column.not_null && !column.has_default) {
                if !object.contains_key(&column.name) {
                    return Err(format!(
                        "{table} row {row_index} is missing required column '{}'",
                        column.name
                    ));
                }
            }
            if let Some(value) = object.get(&column.name) {
                validate_scalar_type(table, row_index, column, value)?;
            }
        }
    }
    Ok(())
}

fn budget_legacy_row(row: &Map<String, JsonValue>) -> StorageResult<Map<String, JsonValue>> {
    let category = row
        .get("category")
        .and_then(JsonValue::as_str)
        .unwrap_or("")
        .trim()
        .to_owned();
    let scope_type = row
        .get("scope_type")
        .and_then(JsonValue::as_str)
        .unwrap_or("category")
        .trim()
        .to_ascii_lowercase();
    let raw_scope_value = row
        .get("scope_value")
        .and_then(JsonValue::as_str)
        .unwrap_or(&category)
        .trim()
        .to_owned();
    let scope_value = if scope_type == "tag" {
        normalize_tag_name(&raw_scope_value)
    } else {
        raw_scope_value
    };
    let limit_base = row
        .get("limit_base")
        .or_else(|| row.get("limit_kzt"))
        .cloned()
        .ok_or_else(|| "Budget limit_base is required".to_owned())?;
    let limit_base_minor = row
        .get("limit_base_minor")
        .or_else(|| row.get("limit_kzt_minor"))
        .cloned()
        .ok_or_else(|| "Budget limit_base_minor is required".to_owned())?;
    let start_date = row
        .get("start_date")
        .and_then(JsonValue::as_str)
        .ok_or_else(|| "Budget start_date is required".to_owned())?;
    let end_date = row
        .get("end_date")
        .and_then(JsonValue::as_str)
        .ok_or_else(|| "Budget end_date is required".to_owned())?;
    if category.is_empty() || scope_value.is_empty() {
        return Err("Budget scope_value is required".to_owned());
    }
    if scope_type != "category" && scope_type != "tag" {
        return Err("Budget scope_type must be category or tag".to_owned());
    }
    if start_date > end_date {
        return Err("Budget start_date must be <= end_date".to_owned());
    }
    let limit_minor = limit_base_minor
        .as_i64()
        .ok_or_else(|| "Budget limit_base_minor must be an integer".to_owned())?;
    if limit_minor <= 0 {
        return Err("Budget limit must be positive".to_owned());
    }
    let limit_value = limit_base
        .as_f64()
        .ok_or_else(|| "Budget limit_base must be a number".to_owned())?;
    if !limit_value.is_finite() {
        return Err("Budget limit_base must be finite".to_owned());
    }
    let expected_minor = (limit_value * 100.0).round();
    if expected_minor != limit_minor as f64 {
        return Err("Budget limit_base and limit_base_minor mismatch".to_owned());
    }
    validate_backup_date(start_date, "start_date")?;
    validate_backup_date(end_date, "end_date")?;
    if start_date > end_date {
        return Err("Budget start_date must be <= end_date".to_owned());
    }
    let mut normalized = Map::new();
    for key in ["id", "start_date", "end_date", "include_mandatory"] {
        if let Some(value) = row.get(key) {
            normalized.insert(key.to_owned(), value.clone());
        }
    }
    normalized.insert("category".to_owned(), JsonValue::String(category));
    normalized.insert("scope_type".to_owned(), JsonValue::String(scope_type));
    normalized.insert("scope_value".to_owned(), JsonValue::String(scope_value));
    normalized.insert("limit_base".to_owned(), limit_base);
    normalized.insert(
        "limit_base_minor".to_owned(),
        JsonValue::Number(limit_minor.into()),
    );
    normalized
        .entry("include_mandatory".to_owned())
        .or_insert(JsonValue::Bool(false));
    Ok(normalized)
}

fn validate_backup_date(value: &str, field: &str) -> StorageResult<()> {
    let parts: Vec<_> = value.split('-').collect();
    if parts.len() != 3 || parts[0].len() != 4 || parts[1].len() != 2 || parts[2].len() != 2 {
        return Err(format!("Budget {field} must use YYYY-MM-DD"));
    }
    let year = parts[0]
        .parse::<i32>()
        .map_err(|_| format!("Budget {field} must use YYYY-MM-DD"))?;
    let month = parts[1]
        .parse::<usize>()
        .map_err(|_| format!("Budget {field} must use YYYY-MM-DD"))?;
    let day = parts[2]
        .parse::<usize>()
        .map_err(|_| format!("Budget {field} must use YYYY-MM-DD"))?;
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let days = [
        31,
        if leap { 29 } else { 28 },
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ];
    if !(1..=12).contains(&month) || day == 0 || day > days[month - 1] {
        return Err(format!("Budget {field} must use a valid date"));
    }
    Ok(())
}

fn validate_payload(conn: &Connection, payload: &JsonValue) -> StorageResult<Vec<JsonValue>> {
    let object = sections(payload)?;
    for table in BACKUP_TABLES {
        if *table == "budgets" && !object.contains_key(*table) {
            continue;
        }
        if !object.get(*table).map(JsonValue::is_array).unwrap_or(false) {
            return Err(format!("Backup section '{table}' must be an array"));
        }
    }
    for table in BACKUP_TABLES {
        let rows = object
            .get(*table)
            .and_then(JsonValue::as_array)
            .map_or(&[][..], Vec::as_slice);
        validate_table_rows(conn, table, rows)?;
    }
    validate_relationships(object)?;
    let mut budgets = Vec::new();
    let budget_rows = object
        .get("budgets")
        .and_then(JsonValue::as_array)
        .map_or(&[][..], Vec::as_slice);
    for (index, row) in budget_rows.iter().enumerate() {
        let row = row
            .as_object()
            .ok_or_else(|| format!("budgets row {} must be an object", index + 1))?;
        budgets.push(JsonValue::Object(budget_legacy_row(row)?));
    }
    for table in BACKUP_TABLES {
        if *table == "budgets" {
            continue;
        }
        for (index, row) in object[*table].as_array().unwrap().iter().enumerate() {
            if !row.is_object() {
                return Err(format!("{table} row {} must be an object", index + 1));
            }
        }
    }
    if table_exists(conn, "budgets")? {
        let mut scopes = HashSet::new();
        for (index, value) in budgets.iter().enumerate() {
            let row = value.as_object().unwrap();
            let scope_type = row["scope_type"].as_str().unwrap();
            let scope_value = row["scope_value"].as_str().unwrap();
            let start_date = row["start_date"].as_str().unwrap();
            let end_date = row["end_date"].as_str().unwrap();
            let key = format!("{scope_type}|{scope_value}|{start_date}|{end_date}");
            if !scopes.insert(key) {
                return Err(format!(
                    "Backup contains duplicate budget at row {}",
                    index + 1
                ));
            }
            for previous in budgets.iter().take(index) {
                let previous = previous.as_object().unwrap();
                let previous_start = previous["start_date"].as_str().unwrap();
                let previous_end = previous["end_date"].as_str().unwrap();
                if previous["scope_type"] == row["scope_type"]
                    && previous["scope_value"] == row["scope_value"]
                    && previous_start <= end_date
                    && previous_end >= start_date
                {
                    return Err(format!(
                        "Backup contains overlapping budgets for '{}'",
                        scope_value
                    ));
                }
            }
        }
    }
    Ok(budgets)
}

pub fn export_full_backup_json(db_path: &str, path: &str) -> StorageResult<FullBackupResult> {
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    let mut object = Map::new();
    object.insert(
        "format".to_owned(),
        JsonValue::String(BACKUP_FORMAT.to_owned()),
    );
    object.insert(
        "version".to_owned(),
        JsonValue::Number(BACKUP_VERSION.into()),
    );
    let mut total = 0_i64;
    let mut budgets = 0_i64;
    for table in BACKUP_TABLES {
        let rows = read_table(&conn, table)?;
        total += rows.len() as i64;
        if *table == "budgets" {
            budgets = rows.len() as i64;
        }
        object.insert((*table).to_owned(), JsonValue::Array(rows));
    }
    let checksum = payload_checksum(&JsonValue::Object(object.clone()))?;
    object.insert(
        "checksum".to_owned(),
        JsonValue::String(format!("sha256:{checksum}")),
    );
    let temp_path = export_temp_path(path)?;
    let bytes =
        serde_json::to_vec_pretty(&JsonValue::Object(object)).map_err(|error| error.to_string())?;
    if let Err(error) = fs::write(&temp_path, bytes) {
        let _ = fs::remove_file(&temp_path);
        return Err(error.to_string());
    }
    if let Err(error) = replace_export_file(&temp_path, Path::new(path)) {
        let _ = fs::remove_file(&temp_path);
        return Err(error);
    }
    Ok(FullBackupResult {
        path: path.to_owned(),
        imported_rows: total,
        budget_rows: budgets,
        checksum: format!("sha256:{checksum}"),
    })
}

fn json_to_sql(value: &JsonValue) -> StorageResult<Value> {
    match value {
        JsonValue::Null => Ok(Value::Null),
        JsonValue::Bool(value) => Ok(Value::Integer(i64::from(*value))),
        JsonValue::Number(value) if value.is_i64() => Ok(Value::Integer(value.as_i64().unwrap())),
        JsonValue::Number(value) => Ok(Value::Real(
            value
                .as_f64()
                .ok_or_else(|| "Invalid JSON number".to_owned())?,
        )),
        JsonValue::String(value) => Ok(Value::Text(value.clone())),
        JsonValue::Array(_) | JsonValue::Object(_) => {
            Err("Backup table values must be scalar JSON values".to_owned())
        }
    }
}

fn insert_table_rows(tx: &Transaction<'_>, table: &str, rows: &[JsonValue]) -> StorageResult<i64> {
    let columns = table_columns(tx, table)?;
    let mut count = 0_i64;
    for (index, value) in rows.iter().enumerate() {
        let object = value
            .as_object()
            .ok_or_else(|| format!("{table} row {} must be an object", index + 1))?;
        let names: Vec<_> = columns
            .iter()
            .filter(|column| object.contains_key(*column))
            .cloned()
            .collect();
        if names.is_empty() {
            return Err(format!(
                "{table} row {} has no recognized columns",
                index + 1
            ));
        }
        let placeholders = std::iter::repeat_n("?", names.len())
            .collect::<Vec<_>>()
            .join(", ");
        let sql = format!(
            "INSERT INTO {table} ({}) VALUES ({placeholders})",
            names.join(", ")
        );
        let values = names
            .iter()
            .map(|name| json_to_sql(object.get(name).unwrap()))
            .collect::<StorageResult<Vec<_>>>()?;
        tx.execute(&sql, rusqlite::params_from_iter(values))
            .map_err(sqlite_err)?;
        count += 1;
    }
    Ok(count)
}

pub fn preview_full_backup_json(db_path: &str, path: &str) -> StorageResult<FullBackupResult> {
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    let payload = load_json(path)?;
    let checksum = verify_checksum(&payload)?;
    let budgets = validate_payload(&conn, &payload)?;
    let object = sections(&payload)?;
    let imported_rows = BACKUP_TABLES
        .iter()
        .map(|table| {
            object
                .get(*table)
                .and_then(JsonValue::as_array)
                .map_or(0, |rows| rows.len() as i64)
        })
        .sum();
    Ok(FullBackupResult {
        path: path.to_owned(),
        imported_rows,
        budget_rows: budgets.len() as i64,
        checksum,
    })
}

pub fn import_full_backup_json(db_path: &str, path: &str) -> StorageResult<FullBackupResult> {
    let payload = load_json(path)?;
    let mut conn = Connection::open(db_path).map_err(sqlite_err)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let checksum = verify_checksum(&payload)?;
    let budgets = validate_payload(&conn, &payload)?;
    let object = sections(&payload)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute_batch(
        "DELETE FROM record_tags;
         DELETE FROM debt_payments;
         DELETE FROM records;
         DELETE FROM transfers;
         DELETE FROM mandatory_expenses;
         DELETE FROM budgets;
         DELETE FROM tags;
         DELETE FROM debts;
         DELETE FROM wallets;",
    )
    .map_err(sqlite_err)?;
    let mut imported_rows = 0_i64;
    for table in [
        "wallets",
        "debts",
        "transfers",
        "mandatory_expenses",
        "records",
        "tags",
    ] {
        imported_rows += insert_table_rows(&tx, table, object[table].as_array().unwrap())?;
    }
    imported_rows += insert_table_rows(&tx, "budgets", &budgets)?;
    for table in ["debt_payments", "record_tags"] {
        imported_rows += insert_table_rows(&tx, table, object[table].as_array().unwrap())?;
    }
    for table in BACKUP_TABLES {
        if !table_columns(&tx, table)?
            .iter()
            .any(|column| column == "id")
        {
            continue;
        }
        tx.execute("DELETE FROM sqlite_sequence WHERE name = ?", [*table])
            .map_err(sqlite_err)?;
        let max_id: Option<i64> = tx
            .query_row(&format!("SELECT MAX(id) FROM {table}"), [], |row| {
                row.get(0)
            })
            .optional()
            .map_err(sqlite_err)?
            .flatten();
        if let Some(max_id) = max_id {
            tx.execute(
                "INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)",
                (*table, max_id),
            )
            .map_err(sqlite_err)?;
        }
    }
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(FullBackupResult {
        path: path.to_owned(),
        imported_rows,
        budget_rows: budgets.len() as i64,
        checksum,
    })
}
