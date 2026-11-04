use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::io::{BufRead, BufReader, Write};
use std::net::{IpAddr, TcpListener, TcpStream, UdpSocket};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

pub type SyncResult<T> = Result<T, String>;

const PROTOCOL_VERSION: &str = "ledgera-sync/alpha.3.4";
const DISCOVERY_REQUEST: &[u8] = b"LEDGERA_SYNC_DISCOVER";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SyncConfig {
    pub db_path: String,
    pub device_id: String,
    pub device_name: String,
    pub bind_host: String,
    pub bind_port: u16,
    pub discovery_enabled: bool,
    pub discovery_port: u16,
    pub poll_interval_ms: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SyncStatus {
    pub enabled: bool,
    pub running: bool,
    pub bind_host: String,
    pub bind_port: u16,
    pub device_id: String,
    pub device_name: String,
    pub last_error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SyncPeer {
    pub host: String,
    pub port: u16,
    pub device_id: String,
    pub device_name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SyncApplyResult {
    pub inserted: usize,
    pub skipped: usize,
    pub errors: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SyncRecord {
    pub record_type: String,
    pub date: String,
    pub wallet_id: i64,
    pub amount_original: f64,
    pub amount_original_minor: i64,
    pub currency: String,
    pub rate_at_operation: f64,
    pub rate_at_operation_text: String,
    pub amount_base: f64,
    pub amount_base_minor: i64,
    pub category: String,
    pub note: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
enum WireMessage {
    Hello {
        protocol: String,
        device_id: String,
        device_name: String,
    },
    RecordsDeltaResponse {
        records: Vec<SyncRecord>,
    },
    RecordsApplyResult {
        inserted: usize,
        skipped: usize,
        errors: usize,
    },
    Error {
        message: String,
    },
}

struct DaemonState {
    stop: Arc<AtomicBool>,
    handle: Option<JoinHandle<()>>,
    discovery_handle: Option<JoinHandle<()>>,
    status: SyncStatus,
}

static DAEMON: OnceLock<Mutex<Option<DaemonState>>> = OnceLock::new();

fn daemon_slot() -> &'static Mutex<Option<DaemonState>> {
    DAEMON.get_or_init(|| Mutex::new(None))
}

fn sqlite_err(err: rusqlite::Error) -> String {
    format!("sqlite error: {err}")
}

pub fn sync_status() -> SyncStatus {
    let guard = daemon_slot().lock().expect("sync daemon lock");
    guard
        .as_ref()
        .map(|state| state.status.clone())
        .unwrap_or_else(disabled_status)
}

pub fn sync_start_daemon(config: SyncConfig) -> SyncResult<SyncStatus> {
    let mut guard = daemon_slot().lock().map_err(|error| error.to_string())?;
    if let Some(state) = guard.as_ref() {
        return Ok(state.status.clone());
    }

    let listener = TcpListener::bind((config.bind_host.as_str(), config.bind_port))
        .map_err(|error| error.to_string())?;
    listener
        .set_nonblocking(true)
        .map_err(|error| error.to_string())?;
    let actual_addr = listener.local_addr().map_err(|error| error.to_string())?;
    let discovery_socket = if config.discovery_enabled {
        let socket = UdpSocket::bind((config.bind_host.as_str(), config.discovery_port))
            .map_err(|error| format!("sync discovery bind failed: {error}"))?;
        socket
            .set_read_timeout(Some(Duration::from_millis(100)))
            .map_err(|error| format!("sync discovery timeout setup failed: {error}"))?;
        Some(socket)
    } else {
        None
    };

    let stop = Arc::new(AtomicBool::new(false));
    let daemon_stop = Arc::clone(&stop);
    let daemon_config = config.clone();
    let handle = thread::spawn(move || run_tcp_daemon(listener, daemon_config, daemon_stop));

    let discovery_handle = discovery_socket.map(|socket| {
        let discovery_stop = Arc::clone(&stop);
        let discovery_config = config.clone();
        thread::spawn(move || {
            run_discovery_responder(socket, discovery_config, actual_addr.port(), discovery_stop);
        })
    });

    let status = SyncStatus {
        enabled: true,
        running: true,
        bind_host: actual_addr.ip().to_string(),
        bind_port: actual_addr.port(),
        device_id: config.device_id,
        device_name: config.device_name,
        last_error: None,
    };
    *guard = Some(DaemonState {
        stop,
        handle: Some(handle),
        discovery_handle,
        status: status.clone(),
    });
    Ok(status)
}

pub fn sync_stop_daemon() -> SyncResult<SyncStatus> {
    let mut state = {
        let mut guard = daemon_slot().lock().map_err(|error| error.to_string())?;
        guard.take()
    };
    if let Some(ref mut daemon) = state {
        daemon.stop.store(true, Ordering::SeqCst);
        if let Some(handle) = daemon.handle.take() {
            handle.join().ok();
        }
        if let Some(handle) = daemon.discovery_handle.take() {
            handle.join().ok();
        }
        let mut status = daemon.status.clone();
        status.running = false;
        return Ok(status);
    }
    Ok(disabled_status())
}

pub fn sync_discover_peers(timeout_ms: u64, discovery_port: u16) -> SyncResult<Vec<SyncPeer>> {
    let socket = UdpSocket::bind(("0.0.0.0", 0)).map_err(|error| error.to_string())?;
    socket
        .set_broadcast(true)
        .map_err(|error| error.to_string())?;
    socket
        .set_read_timeout(Some(Duration::from_millis(100)))
        .map_err(|error| error.to_string())?;
    socket
        .send_to(DISCOVERY_REQUEST, ("255.255.255.255", discovery_port))
        .map_err(|error| error.to_string())?;

    let deadline = Instant::now() + Duration::from_millis(timeout_ms);
    let mut peers = Vec::new();
    let mut seen = HashSet::new();
    while Instant::now() < deadline {
        let mut buf = [0_u8; 2048];
        match socket.recv_from(&mut buf) {
            Ok((len, addr)) => {
                if let Ok(peer) = serde_json::from_slice::<SyncPeer>(&buf[..len]) {
                    let host = resolved_discovery_host(&peer.host, addr.ip());
                    let key = (peer.device_id.clone(), host.clone(), peer.port);
                    if seen.insert(key) {
                        peers.push(SyncPeer { host, ..peer });
                    }
                }
            }
            Err(error)
                if error.kind() == std::io::ErrorKind::WouldBlock
                    || error.kind() == std::io::ErrorKind::TimedOut => {}
            Err(error) => return Err(error.to_string()),
        }
    }
    Ok(peers)
}

pub fn sync_push_once(
    config: SyncConfig,
    peer_host: &str,
    peer_port: u16,
) -> SyncResult<SyncApplyResult> {
    let records = standalone_records(&config.db_path)?;
    let mut stream =
        TcpStream::connect((peer_host, peer_port)).map_err(|error| error.to_string())?;
    stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .map_err(|error| error.to_string())?;
    send_message(
        &mut stream,
        &WireMessage::Hello {
            protocol: PROTOCOL_VERSION.to_owned(),
            device_id: config.device_id,
            device_name: config.device_name,
        },
    )?;
    send_message(&mut stream, &WireMessage::RecordsDeltaResponse { records })?;

    let mut reader = BufReader::new(stream);
    let message = read_message(&mut reader)?;
    match message {
        WireMessage::RecordsApplyResult {
            inserted,
            skipped,
            errors,
        } => Ok(SyncApplyResult {
            inserted,
            skipped,
            errors,
        }),
        WireMessage::Error { message } => Err(message),
        _ => Err("unexpected sync response".to_owned()),
    }
}

pub fn record_fingerprint(record: &SyncRecord) -> String {
    [
        record.record_type.as_str(),
        record.date.as_str(),
        &record.wallet_id.to_string(),
        &record.amount_original_minor.to_string(),
        record.currency.as_str(),
        record.rate_at_operation_text.as_str(),
        &record.amount_base_minor.to_string(),
        record.category.as_str(),
        record.note.as_str(),
    ]
    .join("|")
}

fn run_tcp_daemon(listener: TcpListener, config: SyncConfig, stop: Arc<AtomicBool>) {
    while !stop.load(Ordering::SeqCst) {
        match listener.accept() {
            Ok((stream, _addr)) => {
                let config = config.clone();
                thread::spawn(move || {
                    handle_connection(stream, &config).ok();
                });
            }
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(50));
            }
            Err(_) => break,
        }
    }
}

fn run_discovery_responder(
    socket: UdpSocket,
    config: SyncConfig,
    actual_port: u16,
    stop: Arc<AtomicBool>,
) {
    while !stop.load(Ordering::SeqCst) {
        let mut buf = [0_u8; 1024];
        match socket.recv_from(&mut buf) {
            Ok((len, addr)) if &buf[..len] == DISCOVERY_REQUEST => {
                let peer = SyncPeer {
                    host: advertised_discovery_host(&config.bind_host),
                    port: actual_port,
                    device_id: config.device_id.clone(),
                    device_name: config.device_name.clone(),
                };
                if let Ok(payload) = serde_json::to_vec(&peer) {
                    socket.send_to(&payload, addr).ok();
                }
            }
            Ok(_) => {}
            Err(error)
                if error.kind() == std::io::ErrorKind::WouldBlock
                    || error.kind() == std::io::ErrorKind::TimedOut => {}
            Err(_) => break,
        }
    }
}

fn advertised_discovery_host(bind_host: &str) -> String {
    if is_wildcard_host(bind_host) {
        String::new()
    } else {
        bind_host.to_owned()
    }
}

fn resolved_discovery_host(peer_host: &str, sender_ip: IpAddr) -> String {
    if is_wildcard_host(peer_host) {
        sender_ip.to_string()
    } else {
        peer_host.to_owned()
    }
}

fn is_wildcard_host(host: &str) -> bool {
    matches!(host.trim(), "" | "0.0.0.0" | "::")
}

fn handle_connection(mut stream: TcpStream, config: &SyncConfig) -> SyncResult<()> {
    let mut reader = BufReader::new(stream.try_clone().map_err(|error| error.to_string())?);
    match read_message(&mut reader)? {
        WireMessage::Hello {
            protocol,
            device_id,
            ..
        } if protocol == PROTOCOL_VERSION && device_id != config.device_id => {}
        WireMessage::Hello { device_id, .. } if device_id == config.device_id => {
            send_message(
                &mut stream,
                &WireMessage::Error {
                    message: "same device sync is not allowed".to_owned(),
                },
            )?;
            return Ok(());
        }
        _ => {
            send_message(
                &mut stream,
                &WireMessage::Error {
                    message: "unsupported sync protocol".to_owned(),
                },
            )?;
            return Ok(());
        }
    }

    match read_message(&mut reader)? {
        WireMessage::RecordsDeltaResponse { records } => {
            let result = apply_inbound_records(&config.db_path, &records)?;
            send_message(
                &mut stream,
                &WireMessage::RecordsApplyResult {
                    inserted: result.inserted,
                    skipped: result.skipped,
                    errors: result.errors,
                },
            )
        }
        _ => send_message(
            &mut stream,
            &WireMessage::Error {
                message: "expected records payload".to_owned(),
            },
        ),
    }
}

fn standalone_records(db_path: &str) -> SyncResult<Vec<SyncRecord>> {
    let conn = Connection::open(db_path).map_err(sqlite_err)?;
    let mut stmt = conn
        .prepare(
            "SELECT type, date, wallet_id, amount_original, amount_original_minor,
                    currency, rate_at_operation, rate_at_operation_text,
                    amount_base, amount_base_minor, category, note
             FROM records
             WHERE transfer_id IS NULL
               AND related_debt_id IS NULL
               AND type IN ('income', 'expense')
             ORDER BY id",
        )
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| {
            Ok(SyncRecord {
                record_type: row.get(0)?,
                date: row.get(1)?,
                wallet_id: row.get(2)?,
                amount_original: row.get(3)?,
                amount_original_minor: row.get(4)?,
                currency: row.get(5)?,
                rate_at_operation: row.get(6)?,
                rate_at_operation_text: row.get(7)?,
                amount_base: row.get(8)?,
                amount_base_minor: row.get(9)?,
                category: row.get(10)?,
                note: row.get(11)?,
            })
        })
        .map_err(sqlite_err)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
}

fn apply_inbound_records(db_path: &str, records: &[SyncRecord]) -> SyncResult<SyncApplyResult> {
    let mut conn = Connection::open(db_path).map_err(sqlite_err)?;
    let existing = existing_fingerprint_counts(&conn)?;
    let mut seen_fingerprints = HashMap::new();
    let mut inserted = 0;
    let mut skipped = 0;
    let mut to_insert = Vec::new();

    let tx = conn.transaction().map_err(sqlite_err)?;
    for record in records {
        let fingerprint = record_fingerprint(record);
        let seen_count = seen_fingerprints.entry(fingerprint.clone()).or_insert(0);
        let existing_count = existing.get(&fingerprint).copied().unwrap_or(0);
        if *seen_count < existing_count {
            *seen_count += 1;
            skipped += 1;
            continue;
        }
        *seen_count += 1;
        let wallet_exists = tx
            .query_row(
                "SELECT 1 FROM wallets WHERE id = ?",
                [record.wallet_id],
                |_| Ok(()),
            )
            .optional()
            .map_err(sqlite_err)?
            .is_some();
        if !wallet_exists {
            return Ok(SyncApplyResult {
                inserted: 0,
                skipped,
                errors: 1,
            });
        }
        to_insert.push(record);
    }
    for record in to_insert {
        tx.execute(
            "INSERT INTO records (
                type, date, wallet_id, transfer_id, related_debt_id,
                amount_original, amount_original_minor, currency,
                rate_at_operation, rate_at_operation_text,
                amount_base, amount_base_minor, category, note, period
             )
             VALUES (?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            params![
                record.record_type,
                record.date,
                record.wallet_id,
                record.amount_original,
                record.amount_original_minor,
                record.currency,
                record.rate_at_operation,
                record.rate_at_operation_text,
                record.amount_base,
                record.amount_base_minor,
                record.category,
                record.note,
            ],
        )
        .map_err(sqlite_err)?;
        inserted += 1;
    }
    tx.commit().map_err(sqlite_err)?;
    if inserted > 0 {
        ledgera_engine_storage::storage_clear_read_connection_cache();
    }
    Ok(SyncApplyResult {
        inserted,
        skipped,
        errors: 0,
    })
}

pub fn apply_records_for_test(
    db_path: &str,
    records: &[SyncRecord],
) -> SyncResult<SyncApplyResult> {
    apply_inbound_records(db_path, records)
}

pub fn standalone_records_for_test(db_path: &str) -> SyncResult<Vec<SyncRecord>> {
    standalone_records(db_path)
}

fn existing_fingerprint_counts(conn: &Connection) -> SyncResult<HashMap<String, usize>> {
    let mut counts = HashMap::new();
    for record in standalone_records_from_conn(conn)? {
        *counts.entry(record_fingerprint(&record)).or_insert(0) += 1;
    }
    Ok(counts)
}

fn standalone_records_from_conn(conn: &Connection) -> SyncResult<Vec<SyncRecord>> {
    let mut stmt = conn
        .prepare(
            "SELECT type, date, wallet_id, amount_original, amount_original_minor,
                    currency, rate_at_operation, rate_at_operation_text,
                    amount_base, amount_base_minor, category, note
             FROM records
             WHERE transfer_id IS NULL
               AND related_debt_id IS NULL
               AND type IN ('income', 'expense')
             ORDER BY id",
        )
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| {
            Ok(SyncRecord {
                record_type: row.get(0)?,
                date: row.get(1)?,
                wallet_id: row.get(2)?,
                amount_original: row.get(3)?,
                amount_original_minor: row.get(4)?,
                currency: row.get(5)?,
                rate_at_operation: row.get(6)?,
                rate_at_operation_text: row.get(7)?,
                amount_base: row.get(8)?,
                amount_base_minor: row.get(9)?,
                category: row.get(10)?,
                note: row.get(11)?,
            })
        })
        .map_err(sqlite_err)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
}

fn send_message(stream: &mut TcpStream, message: &WireMessage) -> SyncResult<()> {
    let payload = serde_json::to_string(message).map_err(|error| error.to_string())?;
    stream
        .write_all(payload.as_bytes())
        .map_err(|error| error.to_string())?;
    stream.write_all(b"\n").map_err(|error| error.to_string())
}

fn read_message(reader: &mut BufReader<TcpStream>) -> SyncResult<WireMessage> {
    let mut line = String::new();
    let bytes = reader
        .read_line(&mut line)
        .map_err(|error| error.to_string())?;
    if bytes == 0 {
        return Err("empty sync response".to_owned());
    }
    serde_json::from_str(line.trim()).map_err(|error| error.to_string())
}

fn disabled_status() -> SyncStatus {
    SyncStatus {
        enabled: false,
        running: false,
        bind_host: String::new(),
        bind_port: 0,
        device_id: String::new(),
        device_name: String::new(),
        last_error: None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn test_db_path(name: &str) -> String {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        std::env::temp_dir()
            .join(format!("ledgera_sync_{name}_{nanos}.db"))
            .to_string_lossy()
            .into_owned()
    }

    fn test_daemon_lock() -> std::sync::MutexGuard<'static, ()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
            .lock()
            .expect("daemon test lock")
    }

    fn init_schema(db_path: &str) {
        let conn = Connection::open(db_path).expect("open");
        conn.execute_batch(
            "
            CREATE TABLE wallets (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                currency TEXT NOT NULL,
                initial_balance REAL NOT NULL DEFAULT 0,
                initial_balance_minor INTEGER NOT NULL DEFAULT 0,
                system INTEGER NOT NULL DEFAULT 0,
                allow_negative INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                date TEXT NOT NULL,
                wallet_id INTEGER NOT NULL,
                transfer_id INTEGER,
                related_debt_id INTEGER,
                amount_original REAL NOT NULL,
                amount_original_minor INTEGER,
                currency TEXT NOT NULL,
                rate_at_operation REAL NOT NULL,
                rate_at_operation_text TEXT NOT NULL,
                amount_base REAL NOT NULL,
                amount_base_minor INTEGER,
                category TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                period TEXT
            );
            INSERT INTO wallets (id, name, currency) VALUES (1, 'Main', 'KZT');
            ",
        )
        .expect("schema");
    }

    fn insert_record(
        db_path: &str,
        record_type: &str,
        transfer_id: Option<i64>,
        debt_id: Option<i64>,
    ) {
        let conn = Connection::open(db_path).expect("open");
        conn.execute(
            "INSERT INTO records (
                type, date, wallet_id, transfer_id, related_debt_id,
                amount_original, amount_original_minor, currency,
                rate_at_operation, rate_at_operation_text,
                amount_base, amount_base_minor, category, note, period
             )
             VALUES (?, '2026-03-01', 1, ?, ?, 100.0, 10000, 'KZT', 1.0, '1.000000',
                     100.0, 10000, 'General', '', NULL)",
            params![record_type, transfer_id, debt_id],
        )
        .expect("insert");
    }

    fn sync_record(wallet_id: i64) -> SyncRecord {
        SyncRecord {
            record_type: "income".to_owned(),
            date: "2026-03-01".to_owned(),
            wallet_id,
            amount_original: 100.0,
            amount_original_minor: 10000,
            currency: "KZT".to_owned(),
            rate_at_operation: 1.0,
            rate_at_operation_text: "1.000000".to_owned(),
            amount_base: 100.0,
            amount_base_minor: 10000,
            category: "General".to_owned(),
            note: "".to_owned(),
        }
    }

    #[test]
    fn fingerprint_ignores_local_id() {
        let record = sync_record(1);
        assert_eq!(record_fingerprint(&record), record_fingerprint(&record));
    }

    #[test]
    fn discovery_host_normalizes_wildcard_addresses() {
        let sender: IpAddr = "192.168.1.25".parse().expect("ip");
        assert_eq!(advertised_discovery_host("0.0.0.0"), "");
        assert_eq!(advertised_discovery_host("::"), "");
        assert_eq!(advertised_discovery_host("127.0.0.1"), "127.0.0.1");
        assert_eq!(resolved_discovery_host("", sender), "192.168.1.25");
        assert_eq!(resolved_discovery_host("0.0.0.0", sender), "192.168.1.25");
        assert_eq!(resolved_discovery_host("::", sender), "192.168.1.25");
        assert_eq!(resolved_discovery_host("10.0.0.2", sender), "10.0.0.2");
    }

    #[test]
    fn standalone_delta_excludes_linked_records() {
        let db_path = test_db_path("delta");
        init_schema(&db_path);
        insert_record(&db_path, "income", None, None);
        insert_record(&db_path, "expense", Some(1), None);
        insert_record(&db_path, "income", None, Some(1));
        let records = standalone_records(&db_path).expect("records");
        assert_eq!(records.len(), 1);
        assert_eq!(records[0].record_type, "income");
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn inbound_apply_inserts_and_skips_duplicates() {
        let db_path = test_db_path("apply");
        init_schema(&db_path);
        let record = sync_record(1);
        let first = apply_inbound_records(&db_path, std::slice::from_ref(&record)).expect("first");
        assert_eq!(first.inserted, 1);
        let second = apply_inbound_records(&db_path, &[record]).expect("second");
        assert_eq!(second.skipped, 1);
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn inbound_apply_preserves_identical_records_in_same_batch() {
        let db_path = test_db_path("apply_identical_batch");
        init_schema(&db_path);
        let record = sync_record(1);
        let first =
            apply_inbound_records(&db_path, &[record.clone(), record.clone()]).expect("first");
        assert_eq!(first.inserted, 2);
        assert_eq!(first.skipped, 0);
        assert_eq!(standalone_records(&db_path).expect("records").len(), 2);

        let second = apply_inbound_records(&db_path, &[record.clone(), record]).expect("second");
        assert_eq!(second.inserted, 0);
        assert_eq!(second.skipped, 2);
        assert_eq!(standalone_records(&db_path).expect("records").len(), 2);
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn inbound_apply_rejects_missing_wallet_without_partial_insert() {
        let db_path = test_db_path("missing_wallet");
        init_schema(&db_path);
        let valid = sync_record(1);
        let invalid = sync_record(404);
        let result = apply_inbound_records(&db_path, &[valid, invalid]).expect("apply");
        assert_eq!(result.inserted, 0);
        assert_eq!(result.errors, 1);
        assert!(standalone_records(&db_path).expect("records").is_empty());
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn daemon_lifecycle_is_idempotent() {
        let _guard = test_daemon_lock();
        sync_stop_daemon().expect("cleanup");
        let config = SyncConfig {
            db_path: test_db_path("daemon"),
            device_id: "device-a".to_owned(),
            device_name: "Device A".to_owned(),
            bind_host: "127.0.0.1".to_owned(),
            bind_port: 0,
            discovery_enabled: false,
            discovery_port: 0,
            poll_interval_ms: 1000,
        };
        let first = sync_start_daemon(config).expect("start");
        let second = sync_start_daemon(SyncConfig {
            db_path: String::new(),
            device_id: "device-b".to_owned(),
            device_name: "Device B".to_owned(),
            bind_host: "127.0.0.1".to_owned(),
            bind_port: 0,
            discovery_enabled: false,
            discovery_port: 0,
            poll_interval_ms: 1000,
        })
        .expect("start twice");
        assert_eq!(first.bind_port, second.bind_port);
        assert!(second.running);
        assert!(!sync_stop_daemon().expect("stop").running);
        assert!(!sync_stop_daemon().expect("stop twice").running);
    }

    #[test]
    fn start_reports_discovery_bind_failure() {
        let _guard = test_daemon_lock();
        sync_stop_daemon().expect("cleanup");
        let occupied = UdpSocket::bind(("127.0.0.1", 0)).expect("bind occupied discovery port");
        let occupied_port = occupied.local_addr().expect("addr").port();
        let config = SyncConfig {
            db_path: test_db_path("discovery_bind"),
            device_id: "device-a".to_owned(),
            device_name: "Device A".to_owned(),
            bind_host: "127.0.0.1".to_owned(),
            bind_port: 0,
            discovery_enabled: true,
            discovery_port: occupied_port,
            poll_interval_ms: 1000,
        };

        let error = sync_start_daemon(config).expect_err("discovery bind must fail");

        assert!(error.contains("sync discovery bind failed"));
        assert!(!sync_status().running);
        drop(occupied);
    }

    #[test]
    fn push_rejects_same_device_loopback() {
        let _guard = test_daemon_lock();
        sync_stop_daemon().expect("cleanup");
        let db_path = test_db_path("same_device");
        init_schema(&db_path);
        insert_record(&db_path, "income", None, None);
        let config = SyncConfig {
            db_path: db_path.clone(),
            device_id: "device-a".to_owned(),
            device_name: "Device A".to_owned(),
            bind_host: "127.0.0.1".to_owned(),
            bind_port: 0,
            discovery_enabled: false,
            discovery_port: 0,
            poll_interval_ms: 1000,
        };
        let status = sync_start_daemon(config.clone()).expect("start");
        let error = sync_push_once(config, "127.0.0.1", status.bind_port)
            .expect_err("same device must fail");
        assert!(error.contains("same device"));
        sync_stop_daemon().expect("stop");
        fs::remove_file(db_path).ok();
    }
}
