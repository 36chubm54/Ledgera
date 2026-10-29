use quick_xml::events::Event;
use quick_xml::Reader;
use rusqlite::{params, Connection, OptionalExtension};
use serde_json::Value;
use std::collections::HashSet;
use std::net::{IpAddr, ToSocketAddrs};
use std::process::Command;
use std::str::FromStr;
use std::sync::{Mutex, OnceLock};

use crate::{sqlite_err, validate_currency_code, validate_ymd_date, StorageResult};

pub const SUPPORTED_CURRENCY_PROVIDER_NAMES: &[&str] =
    &["nbk", "exchange_rate", "cbr", "static", "cache"];

pub const CUSTOM_PROVIDER_PREFIX: &str = "custom:";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CurrencyProviderDefinitionPayload {
    pub provider_id: String,
    pub display_name: String,
    pub endpoint: String,
    pub http_method: String,
    pub response_format: String,
    pub currency_path: String,
    pub rate_path: String,
    pub effective_date_path: String,
    pub aliases_json: String,
    pub response_base_currency: String,
    pub rate_semantics: String,
    pub auth_mode: String,
    pub credential_ref: String,
    pub request_body: String,
    pub timeout_seconds: i64,
    pub retry_count: i64,
    pub redirect_limit: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CurrencyProviderDefinitionRow {
    pub provider_id: String,
    pub display_name: String,
    pub endpoint: String,
    pub http_method: String,
    pub response_format: String,
    pub currency_path: String,
    pub rate_path: String,
    pub effective_date_path: String,
    pub aliases_json: String,
    pub response_base_currency: String,
    pub rate_semantics: String,
    pub auth_mode: String,
    pub credential_ref: String,
    pub request_body: String,
    pub timeout_seconds: i64,
    pub retry_count: i64,
    pub redirect_limit: i64,
    pub schema_version: i64,
    pub active: bool,
    pub tested_at: String,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CurrencyProviderSettingRow {
    pub provider_id: String,
    pub mode: String,
    pub primary_enabled: bool,
    pub fallback_enabled: bool,
    pub credential_status: String,
    pub last_status: String,
    pub last_diagnostic: String,
    pub last_checked_at: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CurrencyProviderSettingPayload {
    pub provider_id: String,
    pub mode: String,
    pub primary_enabled: bool,
    pub fallback_enabled: bool,
    pub credential_status: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CurrencyProviderTestResultRow {
    pub provider_id: String,
    pub status: String,
    pub rates_count: i64,
    pub effective_date: String,
    pub diagnostic: String,
    pub activated: bool,
}

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
    pub credential_ref: String,
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
    let mut active = active
        .lock()
        .map_err(|_| "Currency refresh lock is poisoned".to_owned())?;
    if !active.insert(refresh_id.to_owned()) {
        return Err("Currency refresh is already running".to_owned());
    }
    Ok(RefreshGuard {
        refresh_id: refresh_id.to_owned(),
    })
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
        if whole.is_empty() {
            "0".to_owned()
        } else {
            whole.to_owned()
        }
    } else {
        format!(
            "{}.{}",
            if whole.is_empty() { "0" } else { whole },
            fraction
        )
    };
    let is_zero = normalized
        .chars()
        .filter(|character| *character != '.')
        .all(|character| character == '0');
    if is_zero {
        return Err("Currency rate must be positive".to_owned());
    }
    Ok(normalized)
}

pub fn provider_order(primary: &str, fallback: &str, enable_cbr: bool) -> Vec<String> {
    let mut result = Vec::new();
    for provider in [
        primary,
        fallback,
        if enable_cbr { "cbr" } else { "" },
        "static",
        "cache",
    ] {
        let normalized = provider.trim().to_lowercase();
        if !normalized.is_empty() && !result.contains(&normalized) {
            result.push(normalized);
        }
    }
    result
}

fn validate_requested_provider(value: &str, field: &str) -> StorageResult<()> {
    let normalized = value.trim().to_lowercase();
    if normalized.is_empty()
        || SUPPORTED_CURRENCY_PROVIDER_NAMES.contains(&normalized.as_str())
        || is_custom_provider_id(&normalized)
    {
        return Ok(());
    }
    Err(format!(
        "Unsupported {field} provider '{normalized}'. Supported providers: {}",
        SUPPORTED_CURRENCY_PROVIDER_NAMES.join(", ")
    ))
}

fn is_custom_provider_id(value: &str) -> bool {
    let slug = value
        .strip_prefix(CUSTOM_PROVIDER_PREFIX)
        .unwrap_or_default();
    !slug.is_empty()
        && slug.len() <= 64
        && slug.chars().all(|character| {
            character.is_ascii_lowercase()
                || character.is_ascii_digit()
                || character == '-'
                || character == '_'
        })
        && slug
            .chars()
            .next()
            .is_some_and(|character| character.is_ascii_lowercase() || character.is_ascii_digit())
}

fn validate_public_https_endpoint(endpoint: &str) -> StorageResult<()> {
    let trimmed = endpoint.trim();
    if !trimmed.to_ascii_lowercase().starts_with("https://") {
        return Err("Provider endpoint must use HTTPS".to_owned());
    }
    let authority = trimmed[8..]
        .split(['/', '?', '#'])
        .next()
        .unwrap_or_default();
    let host = authority
        .rsplit('@')
        .next()
        .unwrap_or_default()
        .split(':')
        .next()
        .unwrap_or_default();
    if host.is_empty() || host.eq_ignore_ascii_case("localhost") || host.ends_with(".local") {
        return Err("Provider endpoint must use a public HTTPS host".to_owned());
    }
    if let Ok(address) = IpAddr::from_str(host) {
        let private = match address {
            IpAddr::V4(value) => {
                value.is_private()
                    || value.is_loopback()
                    || value.is_link_local()
                    || value.is_unspecified()
            }
            IpAddr::V6(value) => {
                value.is_loopback()
                    || value.is_unspecified()
                    || value.is_unique_local()
                    || value.is_unicast_link_local()
            }
        };
        if private {
            return Err("Provider endpoint cannot target a private or loopback address".to_owned());
        }
    }
    Ok(())
}

fn validate_provider_definition(
    payload: &CurrencyProviderDefinitionPayload,
) -> StorageResult<(String, String, String, String)> {
    let provider_id = payload.provider_id.trim().to_lowercase();
    if !is_custom_provider_id(&provider_id) {
        return Err("Custom provider id must match custom:<lowercase-slug>".to_owned());
    }
    let display_name = payload.display_name.trim();
    if display_name.is_empty() || display_name.len() > 128 {
        return Err(
            "Provider display name is required and must be at most 128 characters".to_owned(),
        );
    }
    validate_public_https_endpoint(&payload.endpoint)?;
    let endpoint_lower = payload.endpoint.to_ascii_lowercase();
    let body_lower = payload.request_body.to_ascii_lowercase();
    if endpoint_lower.contains("api_key=")
        || endpoint_lower.contains("access_token=")
        || body_lower.contains("api_key")
        || body_lower.contains("access_token")
        || body_lower.contains("authorization")
    {
        return Err(
            "Provider definition must not contain API keys or authorization values".to_owned(),
        );
    }
    let method = payload.http_method.trim().to_uppercase();
    if method != "GET" && method != "POST" {
        return Err("Provider HTTP method must be GET or POST".to_owned());
    }
    let format = payload.response_format.trim().to_lowercase();
    if format != "json" && format != "xml" {
        return Err("Provider response format must be json or xml".to_owned());
    }
    if payload.currency_path.trim().is_empty() || payload.rate_path.trim().is_empty() {
        return Err("Provider currency and rate paths are required".to_owned());
    }
    let base = payload.response_base_currency.trim().to_uppercase();
    validate_currency_code(&base)?;
    let semantics = payload.rate_semantics.trim().to_lowercase();
    if semantics != "quote_per_base" && semantics != "base_per_quote" {
        return Err("Provider rate semantics must be quote_per_base or base_per_quote".to_owned());
    }
    let auth_mode = payload.auth_mode.trim().to_lowercase();
    if !["none", "api_key_header", "api_key_query", "bearer"].contains(&auth_mode.as_str()) {
        return Err(
            "Provider auth mode must be none, api_key_header, api_key_query, or bearer".to_owned(),
        );
    }
    if auth_mode != "none" && payload.credential_ref.trim().is_empty() {
        return Err("Credential reference is required for an authenticated provider".to_owned());
    }
    if payload.aliases_json.trim().is_empty() {
        return Err("Provider aliases must be a JSON object".to_owned());
    }
    let aliases: Value = serde_json::from_str(&payload.aliases_json)
        .map_err(|_| "Provider aliases must be a JSON object".to_owned())?;
    if !aliases.is_object() {
        return Err("Provider aliases must be a JSON object".to_owned());
    }
    Ok((provider_id, method, format, base))
}

pub fn currency_provider_definition_rows(
    db_path: &str,
) -> StorageResult<Vec<CurrencyProviderDefinitionRow>> {
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    ensure_currency_refresh_schema(&conn)?;
    let mut stmt = conn
        .prepare(
            "SELECT provider_id, display_name, endpoint, http_method, response_format,
                currency_path, rate_path, effective_date_path, aliases_json,
                response_base_currency, rate_semantics, auth_mode, credential_ref,
                request_body, timeout_seconds, retry_count, redirect_limit,
                schema_version, active, tested_at, created_at, updated_at
         FROM currency_provider_definitions ORDER BY display_name COLLATE NOCASE, provider_id",
        )
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| {
            Ok(CurrencyProviderDefinitionRow {
                provider_id: row.get(0)?,
                display_name: row.get(1)?,
                endpoint: row.get(2)?,
                http_method: row.get(3)?,
                response_format: row.get(4)?,
                currency_path: row.get(5)?,
                rate_path: row.get(6)?,
                effective_date_path: row.get(7)?,
                aliases_json: row.get(8)?,
                response_base_currency: row.get(9)?,
                rate_semantics: row.get(10)?,
                auth_mode: row.get(11)?,
                credential_ref: row.get(12)?,
                request_body: row.get(13)?,
                timeout_seconds: row.get(14)?,
                retry_count: row.get(15)?,
                redirect_limit: row.get(16)?,
                schema_version: row.get(17)?,
                active: row.get::<_, i64>(18)? != 0,
                tested_at: row.get(19)?,
                created_at: row.get(20)?,
                updated_at: row.get(21)?,
            })
        })
        .map_err(sqlite_err)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
}

pub fn currency_provider_setting_rows(
    db_path: &str,
) -> StorageResult<Vec<CurrencyProviderSettingRow>> {
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    ensure_currency_refresh_schema(&conn)?;
    let mut stmt = conn
        .prepare(
            "SELECT provider_id, mode, primary_enabled, fallback_enabled, credential_status,
                last_status, last_diagnostic, last_checked_at
         FROM currency_provider_settings ORDER BY provider_id",
        )
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| {
            Ok(CurrencyProviderSettingRow {
                provider_id: row.get(0)?,
                mode: row.get(1)?,
                primary_enabled: row.get::<_, i64>(2)? != 0,
                fallback_enabled: row.get::<_, i64>(3)? != 0,
                credential_status: row.get(4)?,
                last_status: row.get(5)?,
                last_diagnostic: row.get(6)?,
                last_checked_at: row.get(7)?,
            })
        })
        .map_err(sqlite_err)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
}

pub fn upsert_currency_provider_setting(
    db_path: &str,
    payload: &CurrencyProviderSettingPayload,
) -> StorageResult<CurrencyProviderSettingRow> {
    let provider_id = payload.provider_id.trim().to_lowercase();
    if !is_custom_provider_id(&provider_id) {
        return Err("Only custom providers have editable settings".to_owned());
    }
    let mode = payload.mode.trim().to_lowercase();
    if !["primary", "fallback", "manual-only"].contains(&mode.as_str()) {
        return Err("Provider mode must be primary, fallback, or manual-only".to_owned());
    }
    let credential_status = payload.credential_status.trim().to_lowercase();
    if !["missing", "configured", "environment", "invalid"].contains(&credential_status.as_str()) {
        return Err("Unsupported provider credential status".to_owned());
    }
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    ensure_currency_refresh_schema(&conn)?;
    let changed = conn
        .execute(
            "UPDATE currency_provider_settings
         SET mode = ?2, primary_enabled = ?3, fallback_enabled = ?4, credential_status = ?5
         WHERE provider_id = ?1",
            params![
                provider_id,
                mode,
                payload.primary_enabled as i64,
                payload.fallback_enabled as i64,
                credential_status
            ],
        )
        .map_err(sqlite_err)?;
    if changed == 0 {
        return Err("Currency provider definition was not found".to_owned());
    }
    currency_provider_setting_rows(db_path)?
        .into_iter()
        .find(|row| row.provider_id == provider_id)
        .ok_or_else(|| "Currency provider settings were not saved".to_owned())
}

pub fn upsert_currency_provider_definition(
    db_path: &str,
    payload: &CurrencyProviderDefinitionPayload,
    now: &str,
) -> StorageResult<CurrencyProviderDefinitionRow> {
    let (provider_id, method, format, base) = validate_provider_definition(payload)?;
    let timeout = payload.timeout_seconds.clamp(1, 120);
    let retry_count = payload.retry_count.clamp(0, 3);
    let redirect_limit = payload.redirect_limit.clamp(0, 5);
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    ensure_currency_refresh_schema(&conn)?;
    conn.execute(
        "INSERT INTO currency_provider_definitions
            (provider_id, display_name, endpoint, http_method, response_format,
             currency_path, rate_path, effective_date_path, aliases_json,
             response_base_currency, rate_semantics, auth_mode, credential_ref,
             request_body, timeout_seconds, retry_count, redirect_limit, schema_version,
             active, tested_at, created_at, updated_at)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14,
                 ?15, ?16, ?17, 1, 0, '', COALESCE((SELECT created_at FROM currency_provider_definitions WHERE provider_id = ?1), ?18), ?18)
         ON CONFLICT(provider_id) DO UPDATE SET
            display_name = excluded.display_name, endpoint = excluded.endpoint,
            http_method = excluded.http_method, response_format = excluded.response_format,
            currency_path = excluded.currency_path, rate_path = excluded.rate_path,
            effective_date_path = excluded.effective_date_path, aliases_json = excluded.aliases_json,
            response_base_currency = excluded.response_base_currency, rate_semantics = excluded.rate_semantics,
            auth_mode = excluded.auth_mode, credential_ref = excluded.credential_ref,
            request_body = excluded.request_body, timeout_seconds = excluded.timeout_seconds,
            retry_count = excluded.retry_count, redirect_limit = excluded.redirect_limit,
            active = 0,
            tested_at = '',
            updated_at = excluded.updated_at",
        params![provider_id, payload.display_name.trim(), payload.endpoint.trim(), method, format,
            payload.currency_path.trim(), payload.rate_path.trim(), payload.effective_date_path.trim(),
            payload.aliases_json.trim(), base, payload.rate_semantics.trim().to_lowercase(),
            payload.auth_mode.trim().to_lowercase(), payload.credential_ref.trim(), payload.request_body,
            timeout, retry_count, redirect_limit, now],
    ).map_err(sqlite_err)?;
    conn.execute(
        "INSERT INTO currency_provider_settings (provider_id) VALUES (?1)
         ON CONFLICT(provider_id) DO NOTHING",
        [provider_id.as_str()],
    )
    .map_err(sqlite_err)?;
    currency_provider_definition_rows(db_path)?
        .into_iter()
        .find(|row| row.provider_id == provider_id)
        .ok_or_else(|| "Currency provider definition was not saved".to_owned())
}

pub fn delete_currency_provider_definition(
    db_path: &str,
    provider_id: &str,
) -> StorageResult<bool> {
    let normalized = provider_id.trim().to_lowercase();
    if !is_custom_provider_id(&normalized) {
        return Err("Only custom providers can be deleted".to_owned());
    }
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    ensure_currency_refresh_schema(&conn)?;
    let changed = conn
        .execute(
            "DELETE FROM currency_provider_definitions WHERE provider_id = ?1",
            [normalized.as_str()],
        )
        .map_err(sqlite_err)?;
    Ok(changed > 0)
}

pub fn activate_currency_provider_definition(
    db_path: &str,
    provider_id: &str,
    tested_at: &str,
) -> StorageResult<()> {
    let normalized = provider_id.trim().to_lowercase();
    if !is_custom_provider_id(&normalized) {
        return Err("Only custom providers can be activated".to_owned());
    }
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    ensure_currency_refresh_schema(&conn)?;
    let changed = conn.execute(
        "UPDATE currency_provider_definitions SET active = 1, tested_at = ?2, updated_at = ?2 WHERE provider_id = ?1",
        params![normalized, tested_at],
    ).map_err(sqlite_err)?;
    if changed == 0 {
        return Err("Currency provider definition was not found".to_owned());
    }
    conn.execute(
        "UPDATE currency_provider_settings SET last_status = 'success', last_diagnostic = '', last_checked_at = ?2 WHERE provider_id = ?1",
        params![normalized, tested_at],
    ).map_err(sqlite_err)?;
    Ok(())
}

pub fn test_currency_provider_definition(
    db_path: &str,
    provider_id: &str,
    base_currency: &str,
    effective_date: &str,
    tested_at: &str,
    provider_payload: &str,
    api_key: &str,
) -> StorageResult<CurrencyProviderTestResultRow> {
    let normalized = provider_id.trim().to_lowercase();
    let definition = currency_provider_definition(db_path, &normalized)?;
    let base = base_currency.trim().to_uppercase();
    validate_currency_code(&base)?;
    validate_ymd_date(effective_date.trim())?;
    let fetched = if provider_payload.trim().is_empty() {
        fetch_custom_provider_payload(&definition, api_key)
    } else {
        Ok((
            provider_payload.to_owned(),
            definition.response_format.clone(),
        ))
    };
    let result = fetched.and_then(|(payload, _)| {
        let resolved_date =
            resolve_custom_effective_date(&payload, &definition, effective_date.trim())?;
        parse_custom_provider_payload(&payload, &definition, &base)
            .map(|rates| (rates, resolved_date))
    });
    match result {
        Ok((rates, resolved_date)) if !rates.is_empty() => {
            activate_currency_provider_definition(db_path, &normalized, tested_at)?;
            Ok(CurrencyProviderTestResultRow {
                provider_id: normalized,
                status: "success".to_owned(),
                rates_count: rates.len() as i64,
                effective_date: resolved_date,
                diagnostic: String::new(),
                activated: true,
            })
        }
        Ok((_, resolved_date)) => Ok(CurrencyProviderTestResultRow {
            provider_id: normalized,
            status: "error".to_owned(),
            rates_count: 0,
            effective_date: resolved_date,
            diagnostic: "Provider returned no usable rates".to_owned(),
            activated: false,
        }),
        Err(error) => Ok(CurrencyProviderTestResultRow {
            provider_id: normalized,
            status: "error".to_owned(),
            rates_count: 0,
            effective_date: effective_date.to_owned(),
            diagnostic: sanitize_provider_diagnostic(&error, api_key),
            activated: false,
        }),
    }
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
            Ok(Event::Start(event)) => {
                current_tag = String::from_utf8_lossy(event.name().as_ref()).to_lowercase()
            }
            Ok(Event::Text(text)) => {
                let value = text
                    .decode()
                    .map_err(|_| "NBK XML contains invalid text".to_owned())?
                    .trim()
                    .to_owned();
                if current_tag == "title" {
                    title = value.clone();
                }
                if current_tag == "description" {
                    description = value;
                }
            }
            Ok(Event::End(event)) => {
                let tag = String::from_utf8_lossy(event.name().as_ref()).to_lowercase();
                if tag == "item" {
                    if title.len() == 3 {
                        if let Ok(rate_text) = normalize_rate_text(&description) {
                            rates.push(ProviderRate {
                                currency: title.to_uppercase(),
                                rate_text,
                            });
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
    if rates.is_empty() {
        return Err("NBK response contained no valid rates".to_owned());
    }
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
            Ok(Event::Start(event)) => {
                current_tag = String::from_utf8_lossy(event.name().as_ref()).to_lowercase()
            }
            Ok(Event::Text(text)) => {
                let text = text
                    .decode()
                    .map_err(|_| "CBR XML contains invalid text".to_owned())?
                    .trim()
                    .to_owned();
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
                            rates.push(ProviderRate {
                                currency: code.to_uppercase(),
                                rate_text: rate,
                            });
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
    if rates.is_empty() {
        return Err("CBR response contained no valid rates".to_owned());
    }
    Ok(rates)
}

pub fn parse_exchange_rate_json(json: &str, target_base: &str) -> StorageResult<Vec<ProviderRate>> {
    let payload: Value = serde_json::from_str(json)
        .map_err(|error| format!("ExchangeRate JSON parsing failed: {error}"))?;
    if payload.get("result").and_then(Value::as_str) != Some("success") {
        return Err(format!(
            "ExchangeRate API error: {}",
            payload
                .get("error-type")
                .and_then(Value::as_str)
                .unwrap_or("unknown-error")
        ));
    }
    let quotes = payload
        .get("conversion_rates")
        .and_then(Value::as_object)
        .ok_or_else(|| "ExchangeRate response contained no conversion rates".to_owned())?;
    let target = target_base.trim().to_uppercase();
    let target_quote_text = if target == "USD" {
        "1".to_owned()
    } else {
        let value = quotes
            .get(&target)
            .ok_or_else(|| format!("Missing target base in ExchangeRate rates: {target}"))?;
        value_text(value)?
    };
    let mut rates = Vec::new();
    for (currency, value) in quotes {
        let quote_text =
            value_text(value).map_err(|_| format!("Invalid ExchangeRate value for {currency}"))?;
        if quote_text == "0" {
            continue;
        }
        let normalized = divide_decimal_text(&target_quote_text, &quote_text)?;
        rates.push(ProviderRate {
            currency: currency.to_uppercase(),
            rate_text: normalized,
        });
    }
    rates.push(ProviderRate {
        currency: "USD".to_owned(),
        rate_text: normalize_rate_text(&target_quote_text)?,
    });
    Ok(rates)
}

fn value_text(value: &Value) -> StorageResult<String> {
    let text = value
        .as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| value.to_string());
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
    let digits = format!("{whole}{fraction}")
        .parse::<u128>()
        .map_err(|_| "Currency rate is too large".to_owned())?;
    Ok((digits, scale))
}

fn divide_decimal_text(numerator: &str, denominator: &str) -> StorageResult<String> {
    let (numerator, numerator_scale) = decimal_parts(numerator)?;
    let (denominator, denominator_scale) = decimal_parts(denominator)?;
    if denominator == 0 {
        return Err("Currency rate denominator must be positive".to_owned());
    }
    let scale = 12u32;
    let denominator_power = decimal_power(denominator_scale)?;
    let scale_power = decimal_power(scale)?;
    let numerator_power = decimal_power(numerator_scale)?;
    let numerator_scaled = numerator
        .checked_mul(denominator_power)
        .and_then(|value| value.checked_mul(scale_power))
        .ok_or_else(|| "Currency rate is too large".to_owned())?;
    let denominator_scaled = denominator
        .checked_mul(numerator_power)
        .ok_or_else(|| "Currency rate is too large".to_owned())?;
    let quotient = numerator_scaled / denominator_scaled;
    let remainder = numerator_scaled % denominator_scaled;
    let rounded = if remainder.saturating_mul(2) >= denominator_scaled {
        quotient + 1
    } else {
        quotient
    };
    let whole = rounded / scale_power;
    let fraction = format!("{:012}", rounded % scale_power)
        .trim_end_matches('0')
        .to_owned();
    normalize_rate_text(
        if fraction.is_empty() {
            whole.to_string()
        } else {
            format!("{whole}.{fraction}")
        }
        .as_str(),
    )
}

fn decimal_power(scale: u32) -> StorageResult<u128> {
    10u128
        .checked_pow(scale)
        .ok_or_else(|| "Currency rate is too large".to_owned())
}

pub fn static_provider_rates() -> Vec<ProviderRate> {
    [("USD", "500"), ("EUR", "590"), ("RUB", "6.5")]
        .into_iter()
        .map(|(currency, rate_text)| ProviderRate {
            currency: currency.to_owned(),
            rate_text: rate_text.to_owned(),
        })
        .collect()
}

fn static_provider_rates_for_base(base: &str) -> StorageResult<Vec<ProviderRate>> {
    let base = base.trim().to_uppercase();
    if base == "KZT" {
        return Ok(static_provider_rates());
    }
    let kzt_rates = static_provider_rates();
    let base_rate = if base == "USD" {
        "500".to_owned()
    } else if base == "EUR" {
        "590".to_owned()
    } else if base == "RUB" {
        "6.5".to_owned()
    } else {
        return Err(format!(
            "Static provider does not support base currency {base}"
        ));
    };
    let mut result = Vec::new();
    for rate in kzt_rates {
        if rate.currency == base {
            continue;
        }
        result.push(ProviderRate {
            currency: rate.currency,
            rate_text: divide_decimal_text(&rate.rate_text, &base_rate)?,
        });
    }
    Ok(result)
}

fn parse_provider_payload(
    provider: &str,
    payload: &str,
    format: &str,
    base: &str,
) -> StorageResult<Vec<ProviderRate>> {
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

fn json_path_values<'a>(root: &'a Value, path: &str) -> StorageResult<Vec<&'a Value>> {
    let normalized = path.trim().trim_start_matches("$.").trim_start_matches('$');
    if normalized.is_empty() {
        return Ok(vec![root]);
    }
    let mut current = vec![root];
    for segment in normalized.split('.').filter(|part| !part.is_empty()) {
        let mut next = Vec::new();
        for value in current {
            if segment == "*" {
                match value {
                    Value::Array(items) => next.extend(items.iter()),
                    Value::Object(items) => next.extend(items.values()),
                    _ => {}
                }
            } else if let Some(index) = segment.strip_suffix("[*]") {
                let child = value
                    .get(index)
                    .ok_or_else(|| format!("JSON path segment is missing: {segment}"))?;
                match child {
                    Value::Array(items) => next.extend(items.iter()),
                    Value::Object(items) => next.extend(items.values()),
                    _ => return Err(format!("JSON path segment is not a collection: {segment}")),
                }
            } else {
                next.push(
                    value
                        .get(segment)
                        .ok_or_else(|| format!("JSON path segment is missing: {segment}"))?,
                );
            }
        }
        current = next;
    }
    Ok(current)
}

fn parse_custom_json(
    payload: &str,
    definition: &CurrencyProviderDefinitionRow,
    requested_base: &str,
) -> StorageResult<Vec<ProviderRate>> {
    let root: Value = serde_json::from_str(payload)
        .map_err(|error| format!("Custom provider JSON parsing failed: {error}"))?;
    let aliases: serde_json::Map<String, Value> = serde_json::from_str(&definition.aliases_json)
        .map_err(|_| "Custom provider aliases are invalid".to_owned())?;
    let currencies = json_path_values(&root, &definition.currency_path)?;
    let rates = json_path_values(&root, &definition.rate_path)?;
    let mut parsed = Vec::new();
    if currencies.len() == 1 && currencies[0].is_object() && rates.len() == 1 && rates[0].is_null()
    {
        if let Some(values) = currencies[0].as_object() {
            for (code, value) in values {
                if let Ok(rate_text) = value_text(value) {
                    parsed.push(ProviderRate {
                        currency: code.to_uppercase(),
                        rate_text,
                    });
                }
            }
        }
    } else if currencies.len() == 1
        && currencies[0].is_object()
        && rates.len() == 1
        && rates[0].is_object()
    {
        if let (Some(rate_map), Some(currency_map)) =
            (rates[0].as_object(), currencies[0].as_object())
        {
            for (code, value) in currency_map {
                let candidate = rate_map.get(code).unwrap_or(value);
                if let Ok(rate_text) = value_text(candidate) {
                    parsed.push(ProviderRate {
                        currency: code.to_uppercase(),
                        rate_text,
                    });
                }
            }
        }
    } else {
        if currencies.len() != rates.len() || currencies.is_empty() {
            return Err(
                "Custom provider currency/rate paths returned different item counts".to_owned(),
            );
        }
        for (currency, rate) in currencies.iter().zip(rates.iter()) {
            let raw_code = currency
                .as_str()
                .ok_or_else(|| "Custom provider currency value is not text".to_owned())?;
            let canonical = aliases
                .get(&raw_code.to_uppercase())
                .and_then(Value::as_str)
                .unwrap_or(raw_code);
            let code = canonical.trim().to_uppercase();
            validate_currency_code(&code)?;
            parsed.push(ProviderRate {
                currency: code,
                rate_text: value_text(rate)?,
            });
        }
    }
    normalize_custom_rates(parsed, definition, requested_base)
}

fn parse_custom_xml(
    payload: &str,
    definition: &CurrencyProviderDefinitionRow,
    requested_base: &str,
) -> StorageResult<Vec<ProviderRate>> {
    let currency_tag = definition
        .currency_path
        .rsplit('/')
        .next()
        .unwrap_or(&definition.currency_path)
        .trim_matches(|character| character == '$' || character == '.')
        .to_lowercase();
    let rate_tag = definition
        .rate_path
        .rsplit('/')
        .next()
        .unwrap_or(&definition.rate_path)
        .trim_matches(|character| character == '$' || character == '.')
        .to_lowercase();
    let aliases: serde_json::Map<String, Value> = serde_json::from_str(&definition.aliases_json)
        .map_err(|_| "Custom provider aliases are invalid".to_owned())?;
    let mut reader = Reader::from_str(payload);
    reader.config_mut().trim_text(true);
    let mut current_tag = String::new();
    let mut currency = String::new();
    let mut rate = String::new();
    let mut parsed = Vec::new();
    loop {
        match reader.read_event() {
            Ok(Event::Start(event)) => {
                current_tag = String::from_utf8_lossy(event.name().as_ref()).to_lowercase()
            }
            Ok(Event::Text(text)) => {
                let value = text
                    .decode()
                    .map_err(|_| "Custom provider XML contains invalid text".to_owned())?
                    .trim()
                    .to_owned();
                if current_tag == currency_tag {
                    currency = value.clone();
                }
                if current_tag == rate_tag {
                    rate = value;
                }
            }
            Ok(Event::End(event)) => {
                let tag = String::from_utf8_lossy(event.name().as_ref()).to_lowercase();
                if !currency.is_empty()
                    && !rate.is_empty()
                    && tag != currency_tag
                    && tag != rate_tag
                {
                    let canonical = aliases
                        .get(&currency.to_uppercase())
                        .and_then(Value::as_str)
                        .unwrap_or(&currency);
                    let code = canonical.trim().to_uppercase();
                    validate_currency_code(&code)?;
                    parsed.push(ProviderRate {
                        currency: code,
                        rate_text: normalize_rate_text(&rate)?,
                    });
                    currency.clear();
                    rate.clear();
                }
                current_tag.clear();
            }
            Ok(Event::Eof) => break,
            Err(error) => return Err(format!("Custom provider XML parsing failed: {error}")),
            _ => {}
        }
    }
    if !currency.is_empty() && !rate.is_empty() {
        let canonical = aliases
            .get(&currency.to_uppercase())
            .and_then(Value::as_str)
            .unwrap_or(&currency);
        parsed.push(ProviderRate {
            currency: canonical.trim().to_uppercase(),
            rate_text: normalize_rate_text(&rate)?,
        });
    }
    normalize_custom_rates(parsed, definition, requested_base)
}

fn normalize_custom_rates(
    mut rates: Vec<ProviderRate>,
    definition: &CurrencyProviderDefinitionRow,
    requested_base: &str,
) -> StorageResult<Vec<ProviderRate>> {
    let response_base = definition.response_base_currency.trim().to_uppercase();
    let requested_base = requested_base.trim().to_uppercase();
    validate_currency_code(&response_base)?;
    validate_currency_code(&requested_base)?;
    let mut quote_per_response = std::collections::HashMap::new();
    for rate in rates.drain(..) {
        let normalized = if definition.rate_semantics == "base_per_quote" {
            divide_decimal_text("1", &rate.rate_text)?
        } else {
            normalize_rate_text(&rate.rate_text)?
        };
        quote_per_response.insert(rate.currency.clone(), normalized);
    }
    quote_per_response
        .entry(response_base.clone())
        .or_insert_with(|| "1".to_owned());
    let base_rate = quote_per_response
        .get(&requested_base)
        .ok_or_else(|| format!("Custom provider has no rate for requested base {requested_base}"))?
        .clone();
    let mut result = Vec::new();
    for (currency, rate) in quote_per_response {
        if currency == requested_base {
            continue;
        }
        result.push(ProviderRate {
            currency,
            rate_text: divide_decimal_text(&rate, &base_rate)?,
        });
    }
    if result.is_empty() {
        return Err("Custom provider returned no usable rates".to_owned());
    }
    Ok(result)
}

fn parse_custom_provider_payload(
    payload: &str,
    definition: &CurrencyProviderDefinitionRow,
    base: &str,
) -> StorageResult<Vec<ProviderRate>> {
    match definition.response_format.as_str() {
        "json" => parse_custom_json(payload, definition, base),
        "xml" => parse_custom_xml(payload, definition, base),
        _ => Err("Unsupported custom provider response format".to_owned()),
    }
}

fn resolve_custom_effective_date(
    payload: &str,
    definition: &CurrencyProviderDefinitionRow,
    fallback_date: &str,
) -> StorageResult<String> {
    let path = definition.effective_date_path.trim();
    if path.is_empty() {
        return Ok(fallback_date.to_owned());
    }
    let raw = match definition.response_format.as_str() {
        "json" => {
            let root: Value = serde_json::from_str(payload)
                .map_err(|error| format!("Custom provider JSON parsing failed: {error}"))?;
            let values = json_path_values(&root, path)?;
            let value = values.first().ok_or_else(|| {
                "Custom provider effective date path returned no values".to_owned()
            })?;
            value
                .as_str()
                .map(str::to_owned)
                .or_else(|| value.as_number().map(ToString::to_string))
                .ok_or_else(|| "Custom provider effective date is not text".to_owned())?
        }
        "xml" => {
            let tag = path
                .rsplit('/')
                .next()
                .unwrap_or(path)
                .trim_matches(|character| character == '$' || character == '.')
                .to_lowercase();
            let mut reader = Reader::from_str(payload);
            reader.config_mut().trim_text(true);
            let mut current_tag = String::new();
            let mut date = None;
            loop {
                match reader.read_event() {
                    Ok(Event::Start(event)) => {
                        current_tag = String::from_utf8_lossy(event.name().as_ref()).to_lowercase();
                    }
                    Ok(Event::Text(text)) if current_tag == tag => {
                        date = Some(
                            text.decode()
                                .map_err(|_| {
                                    "Custom provider XML contains invalid text".to_owned()
                                })?
                                .trim()
                                .to_owned(),
                        );
                    }
                    Ok(Event::Eof) => break,
                    Err(error) => {
                        return Err(format!("Custom provider XML parsing failed: {error}"))
                    }
                    _ => {}
                }
                if date.is_some() {
                    break;
                }
            }
            date.ok_or_else(|| "Custom provider effective date path returned no values".to_owned())?
        }
        _ => return Err("Unsupported custom provider response format".to_owned()),
    };
    let date = raw.trim().get(..10).unwrap_or(raw.trim()).to_owned();
    validate_ymd_date(&date)?;
    Ok(date)
}

fn provider_endpoint(provider: &str, base: &str, api_key: &str) -> StorageResult<String> {
    let endpoint = match provider {
        "nbk" => "https://www.nationalbank.kz/rss/rates_all.xml".to_owned(),
        "cbr" => "https://www.cbr.ru/scripts/XML_daily.asp".to_owned(),
        "exchange_rate" => {
            if api_key.trim().is_empty() {
                return Err("ExchangeRate API key is required".to_owned());
            }
            format!(
                "https://v6.exchangerate-api.com/v6/{}/latest/USD",
                api_key.trim()
            )
        }
        other => return Err(format!("Provider {other} does not have an HTTP endpoint")),
    };
    let _ = base;
    Ok(endpoint)
}

fn fetch_provider_payload(
    provider: &str,
    base: &str,
    api_key: &str,
    timeout_seconds: i64,
) -> StorageResult<(String, String)> {
    const MAX_PROVIDER_RESPONSE_BYTES: usize = 5 * 1024 * 1024;
    let endpoint = provider_endpoint(provider, base, api_key)?;
    let timeout = timeout_seconds.clamp(1, 120).to_string();
    let output = Command::new("curl")
        .args([
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--max-redirs",
            "3",
            "--max-time",
            &timeout,
            "--max-filesize",
            &MAX_PROVIDER_RESPONSE_BYTES.to_string(),
            "--user-agent",
            "Ledgera currency refresh",
            &endpoint,
        ])
        .output()
        .map_err(|error| format!("{provider} transport is unavailable: {error}"))?;
    if !output.status.success() {
        let raw_diagnostic = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        let diagnostic = sanitize_provider_diagnostic(&raw_diagnostic, api_key.trim());
        return Err(format!(
            "{provider} request failed{}",
            if diagnostic.is_empty() {
                String::new()
            } else {
                format!(": {diagnostic}")
            }
        ));
    }
    let body = String::from_utf8(output.stdout)
        .map_err(|_| format!("{provider} response is not valid UTF-8"))?;
    if body.len() > MAX_PROVIDER_RESPONSE_BYTES {
        return Err(format!("{provider} response exceeds the 5 MB limit"));
    }
    let format = if provider == "exchange_rate" {
        "json"
    } else {
        "xml"
    };
    Ok((body, format.to_owned()))
}

fn currency_provider_definition(
    db_path: &str,
    provider: &str,
) -> StorageResult<CurrencyProviderDefinitionRow> {
    currency_provider_definition_rows(db_path)?
        .into_iter()
        .find(|definition| definition.provider_id == provider)
        .ok_or_else(|| format!("Custom provider definition '{provider}' was not found"))
}

fn fetch_custom_provider_payload(
    definition: &CurrencyProviderDefinitionRow,
    api_key: &str,
) -> StorageResult<(String, String)> {
    validate_public_https_endpoint(&definition.endpoint)?;
    let host = definition.endpoint[8..]
        .split(['/', '?', '#'])
        .next()
        .unwrap_or_default()
        .rsplit('@')
        .next()
        .unwrap_or_default()
        .split(':')
        .next()
        .unwrap_or_default();
    let resolved = (host, 443)
        .to_socket_addrs()
        .map_err(|_| "Provider endpoint host could not be resolved".to_owned())?;
    for address in resolved {
        let private = match address.ip() {
            IpAddr::V4(value) => {
                value.is_private()
                    || value.is_loopback()
                    || value.is_link_local()
                    || value.is_unspecified()
            }
            IpAddr::V6(value) => {
                value.is_loopback()
                    || value.is_unspecified()
                    || value.is_unique_local()
                    || value.is_unicast_link_local()
            }
        };
        if private {
            return Err("Provider endpoint resolved to a private or loopback address".to_owned());
        }
    }
    let timeout = definition.timeout_seconds.clamp(1, 120).to_string();
    let mut endpoint = definition.endpoint.clone();
    let mut arguments = vec![
        "--fail".to_owned(),
        "--silent".to_owned(),
        "--show-error".to_owned(),
        "--location".to_owned(),
        "--max-redirs".to_owned(),
        definition.redirect_limit.clamp(0, 5).to_string(),
        "--max-time".to_owned(),
        timeout,
        "--user-agent".to_owned(),
        "Ledgera currency refresh".to_owned(),
    ];
    let secret = api_key.trim();
    match definition.auth_mode.as_str() {
        "api_key_query" if !secret.is_empty() => {
            endpoint.push(if endpoint.contains('?') { '&' } else { '?' });
            endpoint.push_str("api_key=");
            endpoint.push_str(secret);
        }
        "api_key_header" if !secret.is_empty() => {
            arguments.push("--header".to_owned());
            arguments.push(format!("X-API-Key: {secret}"));
        }
        "bearer" if !secret.is_empty() => {
            arguments.push("--header".to_owned());
            arguments.push(format!("Authorization: Bearer {secret}"));
        }
        mode if mode != "none" => return Err("Provider credentials are missing".to_owned()),
        _ => {}
    }
    if definition.http_method == "POST" {
        arguments.push("--request".to_owned());
        arguments.push("POST".to_owned());
        if !definition.request_body.trim().is_empty() {
            arguments.push("--data".to_owned());
            arguments.push(definition.request_body.clone());
        }
    }
    arguments.push(endpoint);
    let mut last_error = String::new();
    for attempt in 0..=definition.retry_count.clamp(0, 3) {
        let output = Command::new("curl")
            .args(&arguments)
            .output()
            .map_err(|error| {
                format!(
                    "{} transport is unavailable: {error}",
                    definition.provider_id
                )
            })?;
        if output.status.success() {
            let body = String::from_utf8(output.stdout)
                .map_err(|_| "Provider response is not valid UTF-8".to_owned())?;
            if body.len() > 5 * 1024 * 1024 {
                return Err("Provider response exceeds the 5 MB limit".to_owned());
            }
            return Ok((body, definition.response_format.clone()));
        }
        let diagnostic = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        last_error = if diagnostic.is_empty() {
            "request failed".to_owned()
        } else {
            sanitize_provider_diagnostic(&diagnostic, secret)
        };
        if attempt < definition.retry_count.clamp(0, 3)
            && is_retryable_curl_failure(output.status.code())
        {
            continue;
        }
    }
    Err(format!(
        "{} request failed: {last_error}",
        definition.provider_id
    ))
}

fn is_retryable_curl_failure(code: Option<i32>) -> bool {
    matches!(code, Some(6 | 7 | 28 | 52 | 55 | 56))
}

fn sanitize_provider_diagnostic(value: &str, secret: &str) -> String {
    if secret.is_empty() {
        return value.to_owned();
    }
    value.replace(secret, "<redacted>")
}

fn cached_provider_rates(
    db_path: &str,
    base: &str,
    date: &str,
) -> StorageResult<Vec<ProviderRate>> {
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    ensure_currency_refresh_schema(&conn)?;
    let mut stmt = conn
        .prepare(
            "SELECT currency, rate_text
         FROM currency_rate_snapshots
         WHERE base_currency = ?1 AND effective_date <= ?2 AND status = 'success'
         ORDER BY effective_date DESC, fetched_at DESC, id DESC",
        )
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map(params![base, date], |row| {
            Ok(ProviderRate {
                currency: row.get(0)?,
                rate_text: row.get(1)?,
            })
        })
        .map_err(sqlite_err)?;
    let mut rates = Vec::new();
    let mut seen = HashSet::new();
    for row in rows {
        let rate = row.map_err(sqlite_err)?;
        if seen.insert(rate.currency.clone()) {
            rates.push(rate);
        }
    }
    if rates.is_empty() {
        return Err("No cached provider rates are available".to_owned());
    }
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
            ON currency_rate_snapshots(base_currency, currency, effective_date DESC, fetched_at DESC, id DESC);
        CREATE TABLE IF NOT EXISTS currency_provider_definitions (
            provider_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            http_method TEXT NOT NULL DEFAULT 'GET',
            response_format TEXT NOT NULL,
            currency_path TEXT NOT NULL,
            rate_path TEXT NOT NULL,
            effective_date_path TEXT NOT NULL DEFAULT '',
            aliases_json TEXT NOT NULL DEFAULT '{}',
            response_base_currency TEXT NOT NULL,
            rate_semantics TEXT NOT NULL,
            auth_mode TEXT NOT NULL DEFAULT 'none',
            credential_ref TEXT NOT NULL DEFAULT '',
            request_body TEXT NOT NULL DEFAULT '',
            timeout_seconds INTEGER NOT NULL DEFAULT 10,
            retry_count INTEGER NOT NULL DEFAULT 0,
            redirect_limit INTEGER NOT NULL DEFAULT 3,
            schema_version INTEGER NOT NULL DEFAULT 1,
            active INTEGER NOT NULL DEFAULT 0,
            tested_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS currency_provider_settings (
            provider_id TEXT PRIMARY KEY REFERENCES currency_provider_definitions(provider_id) ON DELETE CASCADE,
            mode TEXT NOT NULL DEFAULT 'manual-only',
            primary_enabled INTEGER NOT NULL DEFAULT 0,
            fallback_enabled INTEGER NOT NULL DEFAULT 0,
            credential_status TEXT NOT NULL DEFAULT 'missing',
            last_status TEXT NOT NULL DEFAULT 'never',
            last_diagnostic TEXT NOT NULL DEFAULT '',
            last_checked_at TEXT NOT NULL DEFAULT ''
        );",
    ).map_err(sqlite_err)
}

pub fn currency_rate_snapshot_rows(db_path: &str) -> StorageResult<Vec<CurrencyRateSnapshotRow>> {
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    ensure_currency_refresh_schema(&conn)?;
    let mut stmt = conn
        .prepare(
            "SELECT id, refresh_id, provider, base_currency, currency, rate, rate_text,
                effective_date, fetched_at, status, diagnostic
         FROM currency_rate_snapshots
         ORDER BY effective_date DESC, currency COLLATE NOCASE, id DESC",
        )
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| {
            Ok(CurrencyRateSnapshotRow {
                id: row.get(0)?,
                refresh_id: row.get(1)?,
                provider: row.get(2)?,
                base_currency: row.get(3)?,
                currency: row.get(4)?,
                rate: row.get(5)?,
                rate_text: row.get(6)?,
                effective_date: row.get(7)?,
                fetched_at: row.get(8)?,
                status: row.get(9)?,
                diagnostic: row.get(10)?,
            })
        })
        .map_err(sqlite_err)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
}

pub fn upsert_currency_rate_snapshot(
    db_path: &str,
    payload: &CurrencyRateSnapshotPayload,
) -> StorageResult<CurrencyRateSnapshotRow> {
    let base = payload.base_currency.trim().to_uppercase();
    let currency = payload.currency.trim().to_uppercase();
    validate_currency_code(&base)?;
    validate_currency_code(&currency)?;
    validate_ymd_date(payload.effective_date.trim())?;
    let rate_text = normalize_rate_text(&payload.rate_text)?;
    let rate = rate_text
        .parse::<f64>()
        .map_err(|_| "Invalid snapshot rate".to_owned())?;
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
    currency_rate_snapshot_rows(db_path)?
        .into_iter()
        .find(|row| {
            row.refresh_id == payload.refresh_id
                && row.provider == payload.provider
                && row.base_currency == base
                && row.currency == currency
                && row.effective_date == payload.effective_date.trim()
        })
        .ok_or_else(|| "Currency rate snapshot was not saved".to_owned())
}

pub fn record_currency_refresh(
    db_path: &str,
    payload: &CurrencyRefreshRunPayload,
) -> StorageResult<CurrencyRefreshStatusRow> {
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

pub fn refresh_currency_rates(
    db_path: &str,
    request: &CurrencyRefreshRequestPayload,
) -> StorageResult<CurrencyRefreshResultRow> {
    let base = request.base_currency.trim().to_uppercase();
    validate_currency_code(&base)?;
    validate_ymd_date(request.effective_date.trim())?;
    validate_requested_provider(&request.primary_provider, "primary")?;
    validate_requested_provider(&request.fallback_provider, "fallback")?;
    if request.refresh_id.trim().is_empty() {
        return Err("Refresh id is required".to_owned());
    }
    let _refresh_guard = acquire_refresh_guard(request.refresh_id.trim())?;
    let order = provider_order(&request.primary_provider, &request.fallback_provider, false);
    let mut errors = Vec::new();
    let mut selected = None;
    for provider in &order {
        let custom_definition = if is_custom_provider_id(provider) {
            match currency_provider_definition(db_path, provider) {
                Ok(definition) if definition.active => Some(definition),
                Ok(_) => {
                    errors.push(format!(
                        "{provider}: provider is not activated after a successful test"
                    ));
                    continue;
                }
                Err(error) => {
                    errors.push(format!("{provider}: {error}"));
                    continue;
                }
            }
        } else {
            None
        };
        let parsed: StorageResult<(Vec<ProviderRate>, String)> =
            if request.provider_payload.trim().is_empty()
                && (provider == "cache" || provider == "static")
            {
                if provider == "static" {
                    cached_provider_rates(db_path, &base, request.effective_date.trim())
                        .or_else(|_| Ok(static_provider_rates_for_base(&base)?))
                } else {
                    cached_provider_rates(db_path, &base, request.effective_date.trim())
                }
                .map(|rates| (rates, request.effective_date.trim().to_owned()))
            } else if let Some(definition) = custom_definition.as_ref() {
                let fetched = if request.provider_payload.trim().is_empty() {
                    fetch_custom_provider_payload(definition, &request.api_key)
                } else {
                    Ok((
                        request.provider_payload.clone(),
                        request.payload_format.clone(),
                    ))
                };
                fetched.and_then(|(payload, _format)| {
                    let effective_date = resolve_custom_effective_date(
                        &payload,
                        definition,
                        request.effective_date.trim(),
                    )?;
                    parse_custom_provider_payload(&payload, definition, &base)
                        .map(|rates| (rates, effective_date))
                })
            } else {
                let fetched = if request.provider_payload.trim().is_empty() {
                    if provider == "static" {
                        Ok((String::new(), "static".to_owned()))
                    } else {
                        fetch_provider_payload(
                            provider,
                            &base,
                            &request.api_key,
                            request.timeout_seconds,
                        )
                    }
                } else {
                    Ok((
                        request.provider_payload.clone(),
                        request.payload_format.clone(),
                    ))
                };
                fetched.and_then(|(payload, format)| {
                    parse_provider_payload(provider, &payload, &format, &base)
                        .map(|rates| (rates, request.effective_date.trim().to_owned()))
                })
            };
        match parsed {
            Ok((rates, effective_date)) if !rates.is_empty() => {
                selected = Some((provider.clone(), rates, effective_date));
                break;
            }
            Ok((_, _)) => errors.push(format!("{provider}: empty rates")),
            Err(error) => errors.push(format!("{provider}: {error}")),
        }
    }
    let Some((selected_provider, rates, selected_effective_date)) = selected else {
        let diagnostic = errors.join("; ");
        let result = CurrencyRefreshResultRow {
            refresh_id: request.refresh_id.clone(),
            status: "error".to_owned(),
            selected_provider: String::new(),
            rates_count: 0,
            effective_date: request.effective_date.clone(),
            fetched_at: request.fetched_at.clone(),
            fallback_chain: order.join(","),
            diagnostic: diagnostic.clone(),
            stale: true,
        };
        if !request.dry_run {
            record_currency_refresh(
                db_path,
                &CurrencyRefreshRunPayload {
                    refresh_id: request.refresh_id.clone(),
                    backend: request.backend.clone(),
                    requested_provider: request.primary_provider.clone(),
                    selected_provider: String::new(),
                    status: "error".to_owned(),
                    effective_date: request.effective_date.clone(),
                    fetched_at: request.fetched_at.clone(),
                    fallback_chain: order.join(","),
                    diagnostic,
                },
            )?;
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
            params![request.refresh_id, request.backend, request.primary_provider, selected_provider, selected_effective_date, request.fetched_at, order.join(",")],
        ).map_err(sqlite_err)?;
        for rate in &rates {
            let currency = rate.currency.trim().to_uppercase();
            if currency == base {
                continue;
            }
            validate_currency_code(&currency)?;
            let rate_text = normalize_rate_text(&rate.rate_text)?;
            let rate_value = rate_text
                .parse::<f64>()
                .map_err(|_| "Invalid provider rate".to_owned())?;
            tx.execute(
                "INSERT INTO currency_rate_snapshots
                    (refresh_id, provider, base_currency, currency, rate, rate_text, effective_date, fetched_at, status, diagnostic)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, 'success', '')
                 ON CONFLICT(refresh_id, provider, base_currency, currency, effective_date) DO UPDATE SET
                    rate = excluded.rate, rate_text = excluded.rate_text, fetched_at = excluded.fetched_at,
                    status = excluded.status, diagnostic = excluded.diagnostic",
                params![request.refresh_id, selected_provider, base, currency, rate_value, rate_text, selected_effective_date, request.fetched_at],
            ).map_err(sqlite_err)?;
        }
        tx.commit().map_err(sqlite_err)?;
    }
    Ok(CurrencyRefreshResultRow {
        refresh_id: request.refresh_id.clone(),
        status: if request.dry_run {
            "preview"
        } else {
            "success"
        }
        .to_owned(),
        selected_provider,
        rates_count: rates.len() as i64,
        effective_date: selected_effective_date,
        fetched_at: request.fetched_at.clone(),
        fallback_chain: order.join(","),
        diagnostic: String::new(),
        stale: false,
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
        assert_eq!(
            normalize_rate_text("999999999999999999999999999999999999999999").unwrap(),
            "999999999999999999999999999999999999999999"
        );
    }

    #[test]
    fn retries_only_network_failures() {
        assert!(is_retryable_curl_failure(Some(28)));
        assert!(is_retryable_curl_failure(Some(56)));
        assert!(!is_retryable_curl_failure(Some(22)));
        assert!(!is_retryable_curl_failure(None));
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
        assert_eq!(
            provider_order("nbk", "nbk", true),
            vec!["nbk", "cbr", "static", "cache"]
        );
    }

    #[test]
    fn rejects_unknown_refresh_provider_instead_of_silently_falling_back() {
        let path = std::env::temp_dir().join(format!(
            "ledgera-currency-provider-{}.db",
            std::process::id()
        ));
        let path_text = path.to_string_lossy().to_string();
        let _ = std::fs::remove_file(&path);
        crate::initialize_database(&path_text).unwrap();
        let error = refresh_currency_rates(
            &path_text,
            &CurrencyRefreshRequestPayload {
                refresh_id: "provider-validation".to_owned(),
                backend: "rust".to_owned(),
                base_currency: "KZT".to_owned(),
                primary_provider: "typo_provider".to_owned(),
                fallback_provider: "static".to_owned(),
                effective_date: "2026-10-12".to_owned(),
                fetched_at: "2026-10-12T10:00:00Z".to_owned(),
                provider_payload: String::new(),
                payload_format: String::new(),
                api_key: String::new(),
                credential_ref: String::new(),
                timeout_seconds: 10,
                dry_run: true,
            },
        )
        .unwrap_err();
        assert!(
            error.contains("Unsupported primary provider"),
            "unexpected error: {error}"
        );
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn refresh_writes_snapshots_without_overwriting_manual_rates() {
        let path = std::env::temp_dir().join(format!("ledgera-currency-{}.db", std::process::id()));
        let path_text = path.to_string_lossy().to_string();
        let _ = std::fs::remove_file(&path);
        crate::initialize_database(&path_text).unwrap();
        let result = refresh_currency_rates(
            &path_text,
            &CurrencyRefreshRequestPayload {
                refresh_id: "fixture-1".to_owned(),
                backend: "rust".to_owned(),
                base_currency: "KZT".to_owned(),
                primary_provider: "exchange_rate".to_owned(),
                fallback_provider: "static".to_owned(),
                effective_date: "2026-10-12".to_owned(),
                fetched_at: "2026-10-12T10:00:00Z".to_owned(),
                provider_payload: r#"{"result":"success","conversion_rates":{"USD":1,"KZT":500}}"#
                    .to_owned(),
                payload_format: "json".to_owned(),
                api_key: String::new(),
                credential_ref: String::new(),
                timeout_seconds: 10,
                dry_run: false,
            },
        )
        .unwrap();
        assert_eq!(result.status, "success");
        assert_eq!(
            crate::current_currency_rates(&path_text)
                .unwrap()
                .get("USD"),
            Some(&500.0)
        );
        crate::upsert_currency_rate(
            &path_text,
            &crate::CurrencyRatePayload {
                base_currency: "KZT".to_owned(),
                currency: "USD".to_owned(),
                rate: "510".to_owned(),
                effective_date: "2026-10-12".to_owned(),
                source: "manual".to_owned(),
            },
        )
        .unwrap();
        assert_eq!(
            crate::current_currency_rates(&path_text)
                .unwrap()
                .get("USD"),
            Some(&510.0)
        );
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn custom_json_provider_normalizes_cross_rate_without_floating_point_storage() {
        let definition = CurrencyProviderDefinitionRow {
            provider_id: "custom:fixture".to_owned(),
            display_name: "Fixture".to_owned(),
            endpoint: "https://example.com/rates".to_owned(),
            http_method: "GET".to_owned(),
            response_format: "json".to_owned(),
            currency_path: "$.rates".to_owned(),
            rate_path: "$.rates".to_owned(),
            effective_date_path: String::new(),
            aliases_json: "{}".to_owned(),
            response_base_currency: "USD".to_owned(),
            rate_semantics: "quote_per_base".to_owned(),
            auth_mode: "none".to_owned(),
            credential_ref: String::new(),
            request_body: String::new(),
            timeout_seconds: 10,
            retry_count: 0,
            redirect_limit: 3,
            schema_version: 1,
            active: true,
            tested_at: "2026-10-19".to_owned(),
            created_at: "2026-10-19".to_owned(),
            updated_at: "2026-10-19".to_owned(),
        };
        let rates = parse_custom_provider_payload(
            r#"{"rates":{"USD":"1","KZT":"500","EUR":"0.9"}}"#,
            &definition,
            "KZT",
        )
        .unwrap();
        assert_eq!(
            rates
                .iter()
                .find(|rate| rate.currency == "USD")
                .unwrap()
                .rate_text,
            "0.002"
        );
        assert_eq!(
            rates
                .iter()
                .find(|rate| rate.currency == "EUR")
                .unwrap()
                .rate_text,
            "0.0018"
        );
    }

    #[test]
    fn custom_provider_uses_effective_date_from_response() {
        let definition = CurrencyProviderDefinitionRow {
            provider_id: "custom:dated".to_owned(),
            display_name: "Dated fixture".to_owned(),
            endpoint: "https://example.com/rates".to_owned(),
            http_method: "GET".to_owned(),
            response_format: "json".to_owned(),
            currency_path: "$.rates".to_owned(),
            rate_path: "$.rates".to_owned(),
            effective_date_path: "$.date".to_owned(),
            aliases_json: "{}".to_owned(),
            response_base_currency: "USD".to_owned(),
            rate_semantics: "quote_per_base".to_owned(),
            auth_mode: "none".to_owned(),
            credential_ref: String::new(),
            request_body: String::new(),
            timeout_seconds: 10,
            retry_count: 0,
            redirect_limit: 3,
            schema_version: 1,
            active: true,
            tested_at: "2026-10-19".to_owned(),
            created_at: "2026-10-19".to_owned(),
            updated_at: "2026-10-19".to_owned(),
        };
        assert_eq!(
            resolve_custom_effective_date(
                r#"{"date":"2026-10-18T12:00:00Z","rates":{"USD":"1","KZT":"500"}}"#,
                &definition,
                "2026-10-19",
            )
            .unwrap(),
            "2026-10-18"
        );
    }

    #[test]
    fn custom_provider_definition_requires_public_https_and_starts_inactive() {
        let path =
            std::env::temp_dir().join(format!("ledgera-custom-provider-{}.db", std::process::id()));
        let path_text = path.to_string_lossy().to_string();
        let _ = std::fs::remove_file(&path);
        crate::initialize_database(&path_text).unwrap();
        let row = upsert_currency_provider_definition(
            &path_text,
            &CurrencyProviderDefinitionPayload {
                provider_id: "custom:fixture".to_owned(),
                display_name: "Fixture".to_owned(),
                endpoint: "https://example.com/rates".to_owned(),
                http_method: "GET".to_owned(),
                response_format: "json".to_owned(),
                currency_path: "$.rates".to_owned(),
                rate_path: "$.rates".to_owned(),
                effective_date_path: String::new(),
                aliases_json: "{}".to_owned(),
                response_base_currency: "USD".to_owned(),
                rate_semantics: "quote_per_base".to_owned(),
                auth_mode: "none".to_owned(),
                credential_ref: String::new(),
                request_body: String::new(),
                timeout_seconds: 10,
                retry_count: 0,
                redirect_limit: 3,
            },
            "2026-10-19",
        )
        .unwrap();
        assert!(!row.active);
        assert!(upsert_currency_provider_definition(
            &path_text,
            &CurrencyProviderDefinitionPayload {
                provider_id: "custom:bad".to_owned(),
                display_name: "Bad".to_owned(),
                endpoint: "http://localhost/rates".to_owned(),
                http_method: "GET".to_owned(),
                response_format: "json".to_owned(),
                currency_path: "$.rates".to_owned(),
                rate_path: "$.rates".to_owned(),
                effective_date_path: String::new(),
                aliases_json: "{}".to_owned(),
                response_base_currency: "USD".to_owned(),
                rate_semantics: "quote_per_base".to_owned(),
                auth_mode: "none".to_owned(),
                credential_ref: String::new(),
                request_body: String::new(),
                timeout_seconds: 10,
                retry_count: 0,
                redirect_limit: 3,
            },
            "2026-10-19"
        )
        .is_err());
        activate_currency_provider_definition(&path_text, "custom:fixture", "2026-10-19").unwrap();
        assert!(currency_provider_definition_rows(&path_text).unwrap()[0].active);
        let refresh = refresh_currency_rates(
            &path_text,
            &CurrencyRefreshRequestPayload {
                refresh_id: "custom-fixture-refresh".to_owned(),
                backend: "rust".to_owned(),
                base_currency: "KZT".to_owned(),
                primary_provider: "custom:fixture".to_owned(),
                fallback_provider: "static".to_owned(),
                effective_date: "2026-10-19".to_owned(),
                fetched_at: "2026-10-19T10:00:00Z".to_owned(),
                provider_payload: r#"{"rates":{"USD":"1","KZT":"500"}}"#.to_owned(),
                payload_format: "json".to_owned(),
                api_key: String::new(),
                credential_ref: String::new(),
                timeout_seconds: 10,
                dry_run: false,
            },
        )
        .unwrap();
        assert_eq!(refresh.selected_provider, "custom:fixture");
        let _ = std::fs::remove_file(path);
    }
}
