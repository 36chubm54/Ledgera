use criterion::{Criterion, criterion_group, criterion_main};
use ledgera_engine_storage::{
    metrics_monthly_summary, metrics_savings_rate, metrics_spending_by_category,
};
use rusqlite::Connection;
use std::fs;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

fn create_bench_db(rows: usize) -> String {
    let unique = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let path = std::env::temp_dir().join(format!("ledgera_metrics_bench_{unique}.db"));
    let conn = Connection::open(&path).unwrap();
    conn.execute_batch(
        "
        CREATE TABLE records (
            id INTEGER PRIMARY KEY,
            type TEXT NOT NULL,
            date TEXT NOT NULL,
            wallet_id INTEGER NOT NULL,
            transfer_id INTEGER DEFAULT NULL,
            amount_base REAL NOT NULL,
            amount_base_minor INTEGER DEFAULT NULL,
            category TEXT NOT NULL DEFAULT ''
        );
        ",
    )
    .unwrap();

    let tx = conn.unchecked_transaction().unwrap();
    {
        let mut stmt = tx
            .prepare(
                "INSERT INTO records (
                    type, date, wallet_id, transfer_id, amount_base, amount_base_minor, category
                 ) VALUES (?1, ?2, 1, NULL, ?3, ?4, ?5)",
            )
            .unwrap();
        for index in 0..rows {
            let record_type = if index % 5 == 0 { "income" } else { "expense" };
            let month = index % 12 + 1;
            let day = index % 28 + 1;
            let amount_minor = if record_type == "income" {
                100_000_i64
            } else {
                1_000_i64 + (index % 20_000) as i64
            };
            let category = if record_type == "income" {
                "Salary".to_owned()
            } else {
                format!("Category {}", index % 12)
            };
            stmt.execute((
                record_type,
                format!("2026-{month:02}-{day:02}"),
                amount_minor as f64 / 100.0,
                amount_minor,
                category,
            ))
            .unwrap();
        }
    }
    tx.commit().unwrap();
    path.to_string_lossy().into_owned()
}

fn remove_bench_db(path: &str) {
    let _ = fs::remove_file(PathBuf::from(path));
}

fn bench_metrics_engine(c: &mut Criterion) {
    let db_path = create_bench_db(10_000);

    c.bench_function("metrics_savings_rate_10k", |b| {
        b.iter(|| metrics_savings_rate(&db_path, "2026-01-01", "2026-12-31").unwrap())
    });
    c.bench_function("metrics_spending_by_category_10k", |b| {
        b.iter(|| {
            metrics_spending_by_category(&db_path, "2026-01-01", "2026-12-31", Some(10)).unwrap()
        })
    });
    c.bench_function("metrics_monthly_summary_10k", |b| {
        b.iter(|| metrics_monthly_summary(&db_path, None, None).unwrap())
    });

    remove_bench_db(&db_path);
}

criterion_group!(benches, bench_metrics_engine);
criterion_main!(benches);
