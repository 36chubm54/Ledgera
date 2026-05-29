from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infrastructure.sqlite_repository import SQLiteRecordRepository  # noqa: E402

SCHEMA_PATH = ROOT / "db" / "schema.sql"
TMP_ROOT = ROOT / "tests" / "_tmp"
RUST_ENGINE_ROOT = ROOT / "rust" / "ledgera_engine"


def _remove_if_unlocked(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        print(f"warning: benchmark database is still locked and was not removed: {path}")


def _seed_db(db_path: Path, rows: int) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO wallets (id, name, currency, initial_balance, is_active) "
            "VALUES (1, 'Bench', 'KZT', 0, 1)"
        )
        for index in range(rows):
            record_type = "income" if index % 5 == 0 else "expense"
            category = "Salary" if record_type == "income" else f"Category {index % 12}"
            amount = 1000.0 if record_type == "income" else float(10 + index % 200)
            month = (index % 12) + 1
            day = (index % 28) + 1
            conn.execute(
                "INSERT INTO records "
                "(type, date, wallet_id, amount_original, currency, rate_at_operation, amount_base, category) "  # noqa: E501
                "VALUES (?, ?, 1, ?, 'KZT', 1.0, ?, ?)",
                (record_type, f"2026-{month:02d}-{day:02d}", amount, amount, category),
            )
        conn.commit()
    finally:
        conn.close()


def _time_call(label: str, iterations: int, callback) -> float:
    started = time.perf_counter()
    for _ in range(iterations):
        callback()
    elapsed = time.perf_counter() - started
    print(f"{label}: {elapsed:.4f}s total, {elapsed / iterations:.6f}s/op")
    return elapsed


def _load_analytics_modules():
    from bridge import ledgera_bridge
    from services.analytics import metrics as metrics_module
    from services.analytics import period_snapshot as period_snapshot_module
    from services.analytics import timeline as timeline_module
    from services.analytics.metrics import MetricsService
    from services.analytics.period_snapshot import PeriodAnalyticsSnapshotService
    from services.analytics.timeline import TimelineService

    return (
        ledgera_bridge,
        metrics_module,
        period_snapshot_module,
        timeline_module,
        MetricsService,
        PeriodAnalyticsSnapshotService,
        TimelineService,
    )


def _backend_label(metrics_module, timeline_module) -> str:
    metrics_backend = "rust" if metrics_module._RUST_METRICS_CORE is not None else "python"
    timeline_backend = "rust" if timeline_module._RUST_TIMELINE_CORE is not None else "python"
    return f"metrics={metrics_backend}, timeline={timeline_backend}"


def _clear_rust_storage_cache(ledgera_bridge) -> None:
    storage_control = ledgera_bridge.get_storage_control_core()
    if storage_control is not None:
        storage_control.storage_clear_read_cache()


def _latest_rust_source_mtime() -> float | None:
    source_roots = [
        RUST_ENGINE_ROOT / "core" / "src",
        RUST_ENGINE_ROOT / "storage" / "src",
        RUST_ENGINE_ROOT / "ffi" / "src",
    ]
    mtimes = [
        path.stat().st_mtime
        for root in source_roots
        if root.exists()
        for path in root.rglob("*.rs")
    ]
    return max(mtimes) if mtimes else None


def _warn_if_extension_looks_stale(extension_path: object) -> None:
    if not extension_path:
        return
    extension_file = Path(str(extension_path))
    if not extension_file.exists():
        return
    latest_source_mtime = _latest_rust_source_mtime()
    if latest_source_mtime is None:
        return
    extension_mtime = extension_file.stat().st_mtime
    print(f"extension_mtime: {time.ctime(extension_mtime)}")
    print(f"latest_rust_source_mtime: {time.ctime(latest_source_mtime)}")
    if extension_mtime < latest_source_mtime:
        print(
            "warning: installed ledgera_core extension looks older than Rust sources; "
            "run maturin build and reinstall the wheel before trusting benchmark results."
        )


def _analytics_load(
    snapshot_service,
    *,
    category_limit: int | None,
    tag_limit: int | None,
) -> tuple[object, ...]:
    snapshot = snapshot_service.get_refresh_snapshot(
        "2026-01-01",
        "2026-12-31",
        category_limit=category_limit,
        tag_limit=tag_limit,
    )
    return (
        snapshot.spending_by_category,
        snapshot.income_by_category,
        snapshot.spending_by_tag,
        snapshot.savings_rate,
        snapshot.burn_rate,
        snapshot.monthly_summary,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Alpha.2 analytics bridge benchmark")
    parser.add_argument("--rows", type=int, default=50_000)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--backend", choices=("rust", "python", "both"), default="both")
    parser.add_argument(
        "--limit-mode",
        choices=("gui", "top10"),
        default="gui",
        help="Use gui for the real analytics refresh path, or top10 for bounded-list diagnostics.",
    )
    args = parser.parse_args()
    category_limit = 10 if args.limit_mode == "top10" else None
    tag_limit = 10 if args.limit_mode == "top10" else None

    if args.backend == "python":
        os.environ["LEDGERA_FORCE_PYTHON_FALLBACK"] = "1"
    else:
        os.environ.setdefault("LEDGERA_ENABLE_RUST_CORE", "1")
        os.environ.pop("LEDGERA_FORCE_PYTHON_FALLBACK", None)
    (
        ledgera_bridge,
        metrics_module,
        period_snapshot_module,
        timeline_module,
        MetricsService,
        PeriodAnalyticsSnapshotService,
        TimelineService,
    ) = _load_analytics_modules()
    del MetricsService, TimelineService
    TMP_ROOT.mkdir(exist_ok=True)
    db_path = TMP_ROOT / f"alpha2_bench_{os.getpid()}.db"
    try:
        _remove_if_unlocked(db_path)
        _seed_db(db_path, args.rows)
        repo = SQLiteRecordRepository(str(db_path), schema_path=str(SCHEMA_PATH))
        try:
            extension = ledgera_bridge.load_extension_module()
            extension_path = getattr(extension, "__file__", None) if extension is not None else None
            if args.backend in {"rust", "both"} and metrics_module._RUST_METRICS_CORE is None:
                raise RuntimeError(
                    "Rust metrics core is unavailable; build/install ledgera_core before benchmarking"  # noqa: E501
                )
            print(f"backend: {_backend_label(metrics_module, timeline_module)}")
            print(f"extension: {extension_path or 'unavailable'}")
            _warn_if_extension_looks_stale(extension_path)
            print(
                "fixture: "
                f"rows={args.rows}, iterations={args.iterations}, limit_mode={args.limit_mode}"
            )
            current_elapsed = _time_call(
                "current analytics path (cold services)",
                args.iterations,
                lambda: _analytics_load(
                    PeriodAnalyticsSnapshotService(repo),
                    category_limit=category_limit,
                    tag_limit=tag_limit,
                ),
            )
            warm_snapshot = PeriodAnalyticsSnapshotService(repo)
            _time_call(
                "current analytics path (same service instance)",
                args.iterations,
                lambda: _analytics_load(
                    warm_snapshot,
                    category_limit=category_limit,
                    tag_limit=tag_limit,
                ),
            )

            if args.backend != "both":
                return
            rust_core = metrics_module._RUST_METRICS_CORE
            rust_snapshot_core = period_snapshot_module._RUST_METRICS_CORE
            rust_timeline_core = timeline_module._RUST_TIMELINE_CORE
            setattr(metrics_module, "_RUST_METRICS_CORE", None)  # noqa: B010
            setattr(period_snapshot_module, "_RUST_METRICS_CORE", None)  # noqa: B010
            setattr(timeline_module, "_RUST_TIMELINE_CORE", None)  # noqa: B010
            try:
                print(f"fallback backend: {_backend_label(metrics_module, timeline_module)}")
                fallback_elapsed = _time_call(
                    "python-fallback analytics path (cold services)",
                    args.iterations,
                    lambda: _analytics_load(
                        PeriodAnalyticsSnapshotService(repo),
                        category_limit=category_limit,
                        tag_limit=tag_limit,
                    ),
                )
            finally:
                setattr(metrics_module, "_RUST_METRICS_CORE", rust_core)  # noqa: B010
                setattr(period_snapshot_module, "_RUST_METRICS_CORE", rust_snapshot_core)  # noqa: B010
                setattr(timeline_module, "_RUST_TIMELINE_CORE", rust_timeline_core)  # noqa: B010
            if current_elapsed > 0:
                print(f"speedup_vs_python: {fallback_elapsed / current_elapsed:.2f}x")
        finally:
            _clear_rust_storage_cache(ledgera_bridge)
            repo.close()
    finally:
        _remove_if_unlocked(db_path)


if __name__ == "__main__":
    main()
