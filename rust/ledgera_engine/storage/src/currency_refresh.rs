use quick_xml::Reader;
use quick_xml::events::Event;
use rusqlite::{Connection, OptionalExtension, params};
use serde_json::Value;
use std::collections::HashSet;
use std::sync::{Mutex, OnceLock};
use std::process::Command;

use crate::{StorageResult, sqlite_err, validate_currency_code, validate_ymd_date};

#[derive(Debug, Clone, PartialEq)]
pub struct CurrencyRateSnapshotPayload {
    pub refresh_id: String,
    pub provider: String,
    pub base_currency: String,
    pub currency: String,
    pub rate_text: String,
    pub effective_date: String,
    pub fetched_at: String,
    pub status: String,
    pub diagnostic: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CurrencyRateSnapshotRow {
    pub id: i64,
    pub refresh_id: String,
    pub provider: String,
    pub base_currency: String,
    pub currency: String,
    pub rate: f64,
    pub rate_text: String,
    pub effective_date: String,
    pub fetched_at: String,
    pub status: String,
    pub diagnostic: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CurrencyRefreshRunPayload {
    pub refresh_id: String,
    pub backend: String,
    pub requested_provider: String,
    pub selected_provider: String,
    pub status: String,
    pub effective_date: String,
    pub fetched_at: String,
    pub fallback_chain: String,
    pub diagnostic: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CurrencyRefreshStatusRow {
    pub refresh_id: String,
    pub backend: String,
    pub requested_provider: String,
    pub selected_provider: String,
    pub status: String,
    pub effective_date: String,
    pub fetched_at: String,
    pub fallback_chain: String,
    pub diagnostic: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CurrencyRefreshRequestPayload {
    pub refresh_id: String,
    pub backend: String,
    pub base_currency: String,
    pub primary_provider: String,
    pub fallback_provider: String,
    pub effective_date: String,
    pub fetched_at: String,
    pub provider_payload: String,
    pub payload_format: String,
    pub api_key: String,
    pub timeout_seconds: i64,
    pub dry_run: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CurrencyRefreshResultRow {
    pub refresh_id: String,
    pub status: String,
    pub selected_provider: String,
    pub rates_count: i64,
    pub effective_date: String,
    pub fetched_at: String,
    pub fallback_chain: String,
    pub diagnostic: String,
    pub stale: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ProviderRate {
    pub currency: String,
    pub rate_text: String,
}

static ACTIVE_REFRESHES: OnceLock<Mutex<HashSet<String>>> = OnceLock::new();

struct RefreshGuard {
    refresh_id: String,
}

impl Drop for RefreshGuard {
    fn drop(&mut self) {
        if let Some(active) = ACTIVE_REFRESHES.get() {
            if let Ok(mut active) = active.lock() {
                active.remove(&self.refresh_id);
            }
        }
    }
}

fn acquire_refresh_guard(refresh_id: &str) -> StorageResult<RefreshGuard> {
    let active = ACTIVE_REFRESHES.get_or_init(|| Mutex::new(HashSet::new()));
    let mut active = active.lock().map_err(|_| "Currency refresh lock is poisoned".to_owned())?;
    if !active.insert(refresh_id.to_owned()) {
        return Err("Currency refresh is already running".to_owned());
    }
    Ok(RefreshGuard { refresh_id: refresh_id.to_owned() })
}

pub fn normalize_rate_text(value: &str) -> StorageResult<String> {
    let trimmed = value.trim().replace(',', ".");
    if trimmed.is_empty() || trimmed.starts_with('-') || trimmed.starts_with('+') {
        return Err("Currency rate must be a positive decimal".to_owned());
    }
    let mut parts = trimmed.split('.');
    let whole = parts.next().unwrap_or_default();
    let fraction = parts.next().unwrap_or_default();
    if parts.next().is_some()
        || whole.is_empty()
        || !whole.chars().all(|value| value.is_ascii_digit())
        || !fraction.chars().all(|value| value.is_ascii_digit())
    {
        return Err("Currency rate must be a positive decimal".to_owned());
    }
    let whole = whole.trim_start_matches('0');
    let fraction = fraction.trim_end_matches('0');
    let normalized = if fraction.is_empty() {
        if whole.is_empty() { "0".to_owned() } else { whole.to_owned() }
    } else {
        format!("{}.{}", if whole.is_empty() { "0" } else { whole }, fraction)
    };
    let number = normalized.parse::<f64>().map_err(|_| "Currency rate must be a positive decimal".to_owned())?;
    if !number.is_finite() || number <= 0.0 {
        return Err("Currency rate must be positive".to_owned());
    }
    Ok(normalized)
}

pub fn provider_order(primary: &str, fallback: &str, enable_cbr: bool) -> Vec<String> {
    let mut result = Vec::new();
    for provider in [primary, fallback, if enable_cbr { "cbr" } else { "" }, "static", "cache"] {
        let normalized = provider.trim().to_lowercase();
        if !normalized.is_empty() && !result.contains(&normalized) {
            result.push(normalized);
        }
    }
    result
}

pub fn parse_nbk_xml(xml: &str) -> StorageResult<Vec<ProviderRate>> {
    let mut reader = Reader::from_str(xml);
    reader.config_mut().trim_text(true);
    let mut current_tag = String::new();
    let mut title = String::new();
    let mut description = String::new();
    let mut rates = Vec::new();
    loop {
        match reader.read_event() {
            Ok(Event::Start(event)) => current_tag = String::from_utf8_lossy(event.name().as_ref()).to_lowercase(),
            Ok(Event::Text(text)) => {
                let value = text.decode().map_err(|_| "NBK XML contains invalid text".to_owned())?.trim().to_owned();
                if current_tag == "title" { title = value.clone(); }
                if current_tag == "description" { description = value; }
            }
            Ok(Event::End(event)) => {
                let tag = String::from_utf8_lossy(event.name().as_ref()).to_lowercase();
                if tag == "item" {
                    if title.len() == 3 {
                        if let Ok(rate_text) = normalize_rate_text(&description) {
                            rates.push(ProviderRate { currency: title.to_uppercase(), rate_text });
                        }
                    }
                    title.clear();
                    description.clear();
                }
                current_tag.clear();
            }
            Ok(Event::Eof) => break,
            Err(error) => return Err(format!("NBK XML parsing failed: {error}")),
            _ => {}
        }
    }
    if rates.is_empty() { return Err("NBK response contained no valid rates".to_owned()); }
    Ok(rates)
}

pub fn parse_cbr_xml(xml: &str) -> StorageResult<Vec<ProviderRate>> {
    let mut reader = Reader::from_str(xml);
    reader.config_mut().trim_text(true);
    let mut current_tag = String::new();
    let mut code = String::new();
    let mut nominal = String::new();
    let mut value = String::new();
    let mut rates = Vec::new();
    loop {
        match reader.read_event() {
            Ok(Event::Start(event)) => current_tag = String::from_utf8_lossy(event.name().as_ref()).to_lowercase(),
            Ok(Event::Text(text)) => {
                let text = text.decode().map_err(|_| "CBR XML contains invalid text".to_owned())?.trim().to_owned();
                match current_tag.as_str() {
                    "charcode" => code = text,
                    "nominal" => nominal = text,
                    "value" => value = text,
                    _ => {}
                }
            }
            Ok(Event::End(event)) => {
                let tag = String::from_utf8_lossy(event.name().as_ref()).to_lowercase();
                if tag == "valute" {
                    if code.len() == 3 {
                        if let Ok(rate) = divide_decimal_text(&value, &nominal) {
                            rates.push(ProviderRate { currency: code.to_uppercase(), rate_text: rate });
                        }
                    }
                    code.clear();
                    nominal.clear();
                    value.clear();
                }
                current_tag.clear();
            }
            Ok(Event::Eof) => break,
            Err(error) => return Err(format!("CBR XML parsing failed: {error}")),
            _ => {}
        }
    }
    if rates.is_empty() { return Err("CBR response contained no valid rates".to_owned()); }
    Ok(rates)
}

pub fn parse_exchange_rate_json(json: &str, target_base: &str) -> StorageResult<Vec<ProviderRate>> {
    let payload: Value = serde_json::from_str(json).map_err(|error| format!("ExchangeRate JSON parsing failed: {error}"))?;
    if payload.get("result").and_then(Value::as_str) != Some("success") {
        return Err(format!("ExchangeRate API error: {}", payload.get("error-type").and_then(Value::as_str).unwrap_or("unknown-error")));
    }
    let quotes = payload.get("conversion_rates").and_then(Value::as_object).ok_or_else(|| "ExchangeRate response contained no conversion rates".to_owned())?;
    let target = target_base.trim().to_uppercase();
    let target_quote_text = if target == "USD" {
        "1".to_owned()
    } else {
        let value = quotes.get(&target).ok_or_else(|| format!("Missing target base in ExchangeRate rates: {target}"))?;
        value_text(value)?
    };
    let mut rates = Vec::new();
    for (currency, value) in quotes {
        let quote_text = value_text(value).map_err(|_| format!("Invalid ExchangeRate value for {currency}"))?;
        if quote_text == "0" { continue; }
        let normalized = divide_decimal_text(&target_quote_text, &quote_text)?;
        rates.push(ProviderRate { currency: currency.to_uppercase(), rate_text: normalized });
    }
    rates.push(ProviderRate { currency: "USD".to_owned(), rate_text: normalize_rate_text(&target_quote_text)? });
    Ok(rates)
}

fn value_text(value: &Value) -> StorageResult<String> {
    let text = value.as_str().map(str::to_owned).unwrap_or_else(|| value.to_string());
    let zero = text
        .trim()
        .replace(',', ".")
        .chars()
        .filter(|character| *character != '.')
        .all(|character| character == '0');
    if zero {
        return Ok("0".to_owned());
    }
    normalize_rate_text(&text)
}

fn decimal_parts(value: &str) -> StorageResult<(u128, u32)> {
    let normalized = normalize_rate_text(value)?;
    let mut parts = normalized.split('.');
    let whole = parts.next().unwrap_or_default();
    let fraction = parts.next().unwrap_or_default();
    let scale = fraction.len() as u32;
    let digits = format!("{whole}{fraction}").parse::<u128>().map_err(|_| "Currency rate is too large".to_owned())?;
    Ok((digits, scale))
}

fn divide_decimal_text(numerator: &str, denominator: &str) -> StorageResult<String> {
    let (numerator, numerator_scale) = decimal_parts(numerator)?;
    let (denominator, denominator_scale) = decimal_parts(denominator)?;
    if denominator == 0 { return Err("Currency rate denominator must be positive".to_owned()); }
    let scale = 12u32;
    let numerator_scaled = numerator
        .checked_mul(10u128.pow(denominator_scale))
        .and_then(|value| value.checked_mul(10u128.pow(scale)))
        .ok_or_else(|| "Currency rate is too large".to_owned())?;
    let denominator_scaled = denominator
        .checked_mul(10u128.pow(numerator_scale))
        .ok_or_else(|| "Currency rate is too large".to_owned())?;
    let quotient = numerator_scaled / denominator_scaled;
    let remainder = numerator_scaled % denominator_scaled;
    let rounded = if remainder.saturating_mul(2) >= denominator_scaled { quotient + 1 } else { quotient };
    let whole = rounded / 10u128.pow(scale);
    let fraction = format!("{:012}", rounded % 10u128.pow(scale)).trim_end_matches('0').to_owned();
    normalize_rate_text(if fraction.is_empty() { whole.to_string() } else { format!("{whole}.{fraction}") }.as_str())
}

pub fn static_provider_rates() -> Vec<ProviderRate> {
    [("USD", "500"), ("EUR", "590"), ("RUB", "6.5")]
        .into_iter()
        .map(|(currency, rate_text)| ProviderRate { currency: currency.to_owned(), rate_text: rate_text.to_owned() })
        .collect()
}

fn static_provider_rates_for_base(base: &str) -> StorageResult<Vec<ProviderRate>> {
    let base = base.trim().to_uppercase();
    if base == "KZT" { return Ok(static_provider_rates()); }
    let kzt_rates = static_provider_rates();
    let base_rate = if base == "USD" {
        "500".to_owned()
    } else if base == "EUR" {
        "590".to_owned()
    } else if base == "RUB" {
        "6.5".to_owned()
    } else {
        return Err(format!("Static provider does not support base currency {base}"));
    };
    let mut result = Vec::new();
    for rate in kzt_rates {
        if rate.currency == base { continue; }
        result.push(ProviderRate { currency: rate.currency, rate_text: divide_decimal_text(&rate.rate_text, &base_rate)? });
    }
    Ok(result)
}

fn parse_provider_payload(provider: &str, payload: &str, format: &str, base: &str) -> StorageResult<Vec<ProviderRate>> {
    match provider {
        "nbk" => {
            if !base.eq_ignore_ascii_case("KZT") {
                return Err("NBK provider currently supports KZT base only".to_owned());
            }
            parse_nbk_xml(payload)
        }
        "exchange_rate" => parse_exchange_rate_json(payload, base),
        "static" => static_provider_rates_for_base(base),
        "cbr" => {
            if !base.eq_ignore_ascii_case("RUB") {
                return Err("CBR target base requires an explicit RUB cross-rate".to_owned());
            }
            if format.eq_ignore_ascii_case("json") {
                parse_exchange_rate_json(payload, base)
            } else {
                parse_cbr_xml(payload)
            }
        }
        "cache" => Err("Cached provider payload is not supplied".to_owned()),
        other => Err(format!("Unsupported currency provider: {other}")),
    }
}

fn provider_endpoint(provider: &str, base: &str, api_key: &str) -> StorageResult<String> {
    let endpoint = match provider {
        "nbk" => "https://www.nationalbank.kz/rss/rates_all.xml".to_owned(),
        "cbr" => "https://www.cbr.ru/scripts/XML_daily.asp".to_owned(),
        "exchange_rate" => {
            if api_key.trim().is_empty() { return Err("ExchangeRate API key is required".to_owned()); }
            format!("https://v6.exchangerate-api.com/v6/{}/latest/USD", api_key.trim())
        }
        other => return Err(format!("Provider {other} does not have an HTTP endpoint")),
    };
    let _ = base;
    Ok(endpoint)
}

fn fetch_provider_payload(provider: &str, base: &str, api_key: &str, timeout_seconds: i64) -> StorageResult<(String, String)> {
    let endpoint = provider_endpoint(provider, base, api_key)?;
    let timeout = timeout_seconds.clamp(1, 120).to_string();
    let output = Command::new("curl")
        .args(["--fail", "--silent", "--show-error", "--location", "--max-time", &timeout, "--user-agent", "Ledgera currency refresh", &endpoint])
        .output()
        .map_err(|error| format!("{provider} transport is unavailable: {error}"))?;
    if !output.status.success() {
        let diagnostic = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        return Err(format!("{provider} request failed{}", if diagnostic.is_empty() { String::new() } else { format!(": {diagnostic}") }));
    }
    let body = String::from_utf8(output.stdout).map_err(|_| format!("{provider} response is not valid UTF-8"))?;
    let format = if provider == "exchange_rate" { "json" } else { "xml" };
    Ok((body, format.to_owned()))
}

fn cached_provider_rates(db_path: &str, base: &str, date: &str) -> StorageResult<Vec<ProviderRate>> {
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    ensure_currency_refresh_schema(&conn)?;
    let mut stmt = conn.prepare(
        "SELECT currency, rate_text
         FROM currency_rate_snapshots
         WHERE base_currency = ?1 AND effective_date <= ?2 AND status = 'success'
         ORDER BY effective_date DESC, fetched_at DESC, id DESC",
    ).map_err(sqlite_err)?;
    let rows = stmt.query_map(params![base, date], |row| Ok(ProviderRate { currency: row.get(0)?, rate_text: row.get(1)? })).map_err(sqlite_err)?;
    let mut rates = Vec::new();
    let mut seen = HashSet::new();
    for row in rows {
        let rate = row.map_err(sqlite_err)?;
        if seen.insert(rate.currency.clone()) { rates.push(rate); }
    }
    if rates.is_empty() { return Err("No cached provider rates are available".to_owned()); }
    Ok(rates)
}

pub fn ensure_currency_refresh_schema(conn: &Connection) -> StorageResult<()> {
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS currency_refresh_runs (
            refresh_id TEXT PRIMARY KEY,
            backend TEXT NOT NULL,
            requested_provider TEXT NOT NULL,
            selected_provider TEXT NOT NULL,
            status TEXT NOT NULL,
            effective_date TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            fallback_chain TEXT NOT NULL DEFAULT '',
            diagnostic TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS currency_rate_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            refresh_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            base_currency TEXT NOT NULL,
            currency TEXT NOT NULL,
            rate REAL NOT NULL,
            rate_text TEXT NOT NULL,
            effective_date TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'success',
            diagnostic TEXT NOT NULL DEFAULT '',
            UNIQUE(refresh_id, provider, base_currency, currency, effective_date)
        );
        CREATE INDEX IF NOT EXISTS idx_currency_snapshots_lookup
            ON currency_rate_snapshots(base_currency, currency, effective_date DESC, fetched_at DESC, id DESC);",
    ).map_err(sqlite_err)
}

pub fn currency_rate_snapshot_rows(db_path: &str) -> StorageResult<Vec<CurrencyRateSnapshotRow>> {
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    ensure_currency_refresh_schema(&conn)?;
    let mut stmt = conn.prepare(
        "SELECT id, refresh_id, provider, base_currency, currency, rate, rate_text,
                effective_date, fetched_at, status, diagnostic
         FROM currency_rate_snapshots
         ORDER BY effective_date DESC, currency COLLATE NOCASE, id DESC",
    ).map_err(sqlite_err)?;
    let rows = stmt.query_map([], |row| Ok(CurrencyRateSnapshotRow {
        id: row.get(0)?, refresh_id: row.get(1)?, provider: row.get(2)?,
        base_currency: row.get(3)?, currency: row.get(4)?, rate: row.get(5)?,
        rate_text: row.get(6)?, effective_date: row.get(7)?, fetched_at: row.get(8)?,
        status: row.get(9)?, diagnostic: row.get(10)?,
    })).map_err(sqlite_err)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
}

pub fn upsert_currency_rate_snapshot(db_path: &str, payload: &CurrencyRateSnapshotPayload) -> StorageResult<CurrencyRateSnapshotRow> {
    let base = payload.base_currency.trim().to_uppercase();
    let currency = payload.currency.trim().to_uppercase();
    validate_currency_code(&base)?;
    validate_currency_code(&currency)?;
    validate_ymd_date(payload.effective_date.trim())?;
    let rate_text = normalize_rate_text(&payload.rate_text)?;
    let rate = rate_text.parse::<f64>().map_err(|_| "Invalid snapshot rate".to_owned())?;
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    ensure_currency_refresh_schema(&conn)?;
    conn.execute(
        "INSERT INTO currency_rate_snapshots
            (refresh_id, provider, base_currency, currency, rate, rate_text, effective_date, fetched_at, status, diagnostic)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)
         ON CONFLICT(refresh_id, provider, base_currency, currency, effective_date) DO UPDATE SET
            rate = excluded.rate, rate_text = excluded.rate_text, fetched_at = excluded.fetched_at,
            status = excluded.status, diagnostic = excluded.diagnostic",
        params![payload.refresh_id, payload.provider, base, currency, rate, rate_text, payload.effective_date.trim(), payload.fetched_at, payload.status, payload.diagnostic],
    ).map_err(sqlite_err)?;
    currency_rate_snapshot_rows(db_path)?.into_iter().find(|row|
        row.refresh_id == payload.refresh_id && row.provider == payload.provider &&
        row.base_currency == base && row.currency == currency && row.effective_date == payload.effective_date.trim()
    ).ok_or_else(|| "Currency rate snapshot was not saved".to_owned())
}

pub fn record_currency_refresh(db_path: &str, payload: &CurrencyRefreshRunPayload) -> StorageResult<CurrencyRefreshStatusRow> {
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    ensure_currency_refresh_schema(&conn)?;
    conn.execute(
        "INSERT INTO currency_refresh_runs
            (refresh_id, backend, requested_provider, selected_provider, status, effective_date, fetched_at, fallback_chain, diagnostic)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)
         ON CONFLICT(refresh_id) DO UPDATE SET
            backend = excluded.backend, requested_provider = excluded.requested_provider,
            selected_provider = excluded.selected_provider, status = excluded.status,
            effective_date = excluded.effective_date, fetched_at = excluded.fetched_at,
            fallback_chain = excluded.fallback_chain, diagnostic = excluded.diagnostic",
        params![payload.refresh_id, payload.backend, payload.requested_provider, payload.selected_provider, payload.status, payload.effective_date, payload.fetched_at, payload.fallback_chain, payload.diagnostic],
    ).map_err(sqlite_err)?;
    latest_currency_refresh_status(db_path)
}

pub fn latest_currency_refresh_status(db_path: &str) -> StorageResult<CurrencyRefreshStatusRow> {
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    ensure_currency_refresh_schema(&conn)?;
    conn.query_row(
        "SELECT refresh_id, backend, requested_provider, selected_provider, status, effective_date, fetched_at, fallback_chain, diagnostic
         FROM currency_refresh_runs ORDER BY fetched_at DESC, refresh_id DESC LIMIT 1",
        [],
        |row| Ok(CurrencyRefreshStatusRow {
            refresh_id: row.get(0)?, backend: row.get(1)?, requested_provider: row.get(2)?,
            selected_provider: row.get(3)?, status: row.get(4)?, effective_date: row.get(5)?,
            fetched_at: row.get(6)?, fallback_chain: row.get(7)?, diagnostic: row.get(8)?,
        }),
    ).optional().map_err(sqlite_err)?.ok_or_else(|| "Currency refresh has not run yet".to_owned())
}

pub fn refresh_currency_rates(db_path: &str, request: &CurrencyRefreshRequestPayload) -> StorageResult<CurrencyRefreshResultRow> {
    let base = request.base_currency.trim().to_uppercase();
    validate_currency_code(&base)?;
    validate_ymd_date(request.effective_date.trim())?;
    if request.refresh_id.trim().is_empty() { return Err("Refresh id is required".to_owned()); }
    let _refresh_guard = acquire_refresh_guard(request.refresh_id.trim())?;
    let order = provider_order(&request.primary_provider, &request.fallback_provider, false);
    let mut errors = Vec::new();
    let mut selected = None;
    for provider in &order {
        let parsed = if request.provider_payload.trim().is_empty() && (provider == "cache" || provider == "static") {
            if provider == "static" {
                cached_provider_rates(db_path, &base, request.effective_date.trim()).or_else(|_| Ok(static_provider_rates_for_base(&base)?))
            } else {
                cached_provider_rates(db_path, &base, request.effective_date.trim())
            }
        } else {
            let fetched = if request.provider_payload.trim().is_empty() {
            if provider == "static" {
                Ok((String::new(), "static".to_owned()))
            } else {
                fetch_provider_payload(provider, &base, &request.api_key, request.timeout_seconds)
            }
        } else {
            Ok((request.provider_payload.clone(), request.payload_format.clone()))
        };
            fetched.and_then(|(payload, format)| parse_provider_payload(provider, &payload, &format, &base))
        };
        match parsed {
            Ok(rates) if !rates.is_empty() => { selected = Some((provider.clone(), rates)); break; }
            Ok(_) => errors.push(format!("{provider}: empty rates")),
            Err(error) => errors.push(format!("{provider}: {error}")),
        }
    }
    let Some((selected_provider, rates)) = selected else {
        let diagnostic = errors.join("; ");
        let result = CurrencyRefreshResultRow {
            refresh_id: request.refresh_id.clone(), status: "error".to_owned(), selected_provider: String::new(),
            rates_count: 0, effective_date: request.effective_date.clone(), fetched_at: request.fetched_at.clone(),
            fallback_chain: order.join(","), diagnostic: diagnostic.clone(), stale: true,
        };
        if !request.dry_run {
            record_currency_refresh(db_path, &CurrencyRefreshRunPayload {
                refresh_id: request.refresh_id.clone(), backend: request.backend.clone(), requested_provider: request.primary_provider.clone(),
                selected_provider: String::new(), status: "error".to_owned(), effective_date: request.effective_date.clone(),
                fetched_at: request.fetched_at.clone(), fallback_chain: order.join(","), diagnostic,
            })?;
        }
        return Ok(result);
    };
    if !request.dry_run {
        let conn = Connection::open(db_path).map_err(sqlite_err)?;
        ensure_currency_refresh_schema(&conn)?;
        let tx = conn.unchecked_transaction().map_err(sqlite_err)?;
        tx.execute(
            "INSERT INTO currency_refresh_runs
                (refresh_id, backend, requested_provider, selected_provider, status, effective_date, fetched_at, fallback_chain, diagnostic)
             VALUES (?1, ?2, ?3, ?4, 'success', ?5, ?6, ?7, '')
             ON CONFLICT(refresh_id) DO UPDATE SET selected_provider = excluded.selected_provider,
                status = excluded.status, effective_date = excluded.effective_date, fetched_at = excluded.fetched_at,
                fallback_chain = excluded.fallback_chain, diagnostic = excluded.diagnostic",
            params![request.refresh_id, request.backend, request.primary_provider, selected_provider, request.effective_date, request.fetched_at, order.join(",")],
        ).map_err(sqlite_err)?;
        for rate in &rates {
            let currency = rate.currency.trim().to_uppercase();
            if currency == base { continue; }
            validate_currency_code(&currency)?;
            let rate_text = normalize_rate_text(&rate.rate_text)?;
            let rate_value = rate_text.parse::<f64>().map_err(|_| "Invalid provider rate".to_owned())?;
            tx.execute(
                "INSERT INTO currency_rate_snapshots
                    (refresh_id, provider, base_currency, currency, rate, rate_text, effective_date, fetched_at, status, diagnostic)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, 'success', '')
                 ON CONFLICT(refresh_id, provider, base_currency, currency, effective_date) DO UPDATE SET
                    rate = excluded.rate, rate_text = excluded.rate_text, fetched_at = excluded.fetched_at,
                    status = excluded.status, diagnostic = excluded.diagnostic",
                params![request.refresh_id, selected_provider, base, currency, rate_value, rate_text, request.effective_date, request.fetched_at],
            ).map_err(sqlite_err)?;
        }
        tx.commit().map_err(sqlite_err)?;
    }
    Ok(CurrencyRefreshResultRow {
        refresh_id: request.refresh_id.clone(), status: if request.dry_run { "preview" } else { "success" }.to_owned(),
        selected_provider, rates_count: rates.len() as i64, effective_date: request.effective_date.clone(),
        fetched_at: request.fetched_at.clone(), fallback_chain: order.join(","), diagnostic: String::new(), stale: false,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalizes_rates_without_losing_decimal_text() {
        assert_eq!(normalize_rate_text("000457.4300").unwrap(), "457.43");
        assert_eq!(normalize_rate_text("6,500").unwrap(), "6.5");
        assert!(normalize_rate_text("0").is_err());
    }

    #[test]
    fn parses_nbk_fixture() {
        let xml = r#"<rss><channel><item><title>USD</title><description>457.43</description></item><item><title>EUR</title><description>512.41</description></item></channel></rss>"#;
        let rates = parse_nbk_xml(xml).unwrap();
        assert_eq!(rates[0].currency, "USD");
        assert_eq!(rates[1].rate_text, "512.41");
    }

    #[test]
    fn parses_cbr_fixture_with_nominal() {
        let xml = r#"<ValCurs><Valute><CharCode>USD</CharCode><Nominal>1</Nominal><Value>92,50</Value></Valute><Valute><CharCode>JPY</CharCode><Nominal>100</Nominal><Value>61,20</Value></Valute></ValCurs>"#;
        let rates = parse_cbr_xml(xml).unwrap();
        assert_eq!(rates[0].rate_text, "92.5");
        assert_eq!(rates[1].rate_text, "0.612");
    }

    #[test]
    fn parses_exchange_rate_fixture_relative_to_target_base() {
        let json = r#"{"result":"success","conversion_rates":{"USD":1,"KZT":500,"EUR":0.9}}"#;
        let rates = parse_exchange_rate_json(json, "KZT").unwrap();
        let usd = rates.iter().find(|rate| rate.currency == "USD").unwrap();
        let eur = rates.iter().find(|rate| rate.currency == "EUR").unwrap();
        assert_eq!(usd.rate_text, "500");
        assert_eq!(eur.rate_text, "555.555555555556");
    }

    #[test]
    fn provider_order_is_deduplicated_and_ends_with_static_cache() {
        assert_eq!(provider_order("nbk", "nbk", true), vec!["nbk", "cbr", "static", "cache"]);
    }

    #[test]
    fn refresh_writes_snapshots_without_overwriting_manual_rates() {
        let path = std::env::temp_dir().join(format!("ledgera-currency-{}.db", std::process::id()));
        let path_text = path.to_string_lossy().to_string();
        let _ = std::fs::remove_file(&path);
        crate::initialize_database(&path_text).unwrap();
        let result = refresh_currency_rates(&path_text, &CurrencyRefreshRequestPayload {
            refresh_id: "fixture-1".to_owned(),
            backend: "rust".to_owned(),
            base_currency: "KZT".to_owned(),
            primary_provider: "exchange_rate".to_owned(),
            fallback_provider: "static".to_owned(),
            effective_date: "2026-10-12".to_owned(),
            fetched_at: "2026-10-12T10:00:00Z".to_owned(),
            provider_payload: r#"{"result":"success","conversion_rates":{"USD":1,"KZT":500}}"#.to_owned(),
            payload_format: "json".to_owned(),
            api_key: String::new(),
            timeout_seconds: 10,
            dry_run: false,
        }).unwrap();
        assert_eq!(result.status, "success");
        assert_eq!(crate::current_currency_rates(&path_text).unwrap().get("USD"), Some(&500.0));
        crate::upsert_currency_rate(&path_text, &crate::CurrencyRatePayload {
            base_currency: "KZT".to_owned(), currency: "USD".to_owned(), rate: "510".to_owned(),
            effective_date: "2026-10-12".to_owned(), source: "manual".to_owned(),
        }).unwrap();
        assert_eq!(crate::current_currency_rates(&path_text).unwrap().get("USD"), Some(&510.0));
        let _ = std::fs::remove_file(path);
    }
}
