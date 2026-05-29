# Ledgera v3.0.0 Alpha.2 Readiness

## Status

`v3.0.0-alpha.2` is closed as a Rust-backed Analytics + Currency hot-path MVP with Python-first runtime contracts.

The app continues to expose the existing Python services and Tkinter-facing controller API. Rust is loaded only through `bridge.ledgera_bridge` when `LEDGERA_ENABLE_RUST_CORE=1` is set, and `LEDGERA_FORCE_PYTHON_FALLBACK=1` keeps the Python path fully available for validation and rollback.

## Completed

- `bridge.ledgera_bridge` exposes typed metrics, timeline, currency, and storage-control accessors.
- `MetricsService` can delegate savings rate, burn rate, category aggregates, income aggregates, tag aggregates, tag coverage, monthly summaries, and period snapshots to Rust.
- `TimelineService` can delegate monthly cashflow, cumulative income/expense, and net-worth monthly deltas to Rust.
- `CurrencyService` can delegate deterministic currency helper behavior to Rust, including provider-order resolution, rate selection, default-rate derivation, and code normalization.
- The analytics tab can use a compact `AnalyticsRefreshSnapshot` for the GUI refresh path without changing the visible GUI contract.
- Rust analytics refresh uses compact tuple payloads, one-pass period aggregation, deterministic category ordering, and a no-tags fast path.
- Metrics snapshot caching requires exact category/tag limit matches, so limited Rust snapshots cannot satisfy later unbounded queries.
- Alpha.2 CI includes Rust checks, wheel build validation, targeted Rust-backed pytest slices, forced Python fallback pytest, pyright, and benchmark compile coverage.
- Benchmark tooling reports backend availability, extension path, extension/source mtimes, and stale-extension warnings before timing begins.

## Runtime Flags

- `LEDGERA_ENABLE_RUST_CORE=1` enables Rust-backed bridge loading.
- `LEDGERA_FORCE_PYTHON_FALLBACK=1` forces Python fallback and skips importing the Rust extension.
- If both variables are set, forced Python fallback wins.

## Compatibility Boundaries

- Python remains the owner of public dataclasses, service contracts, GUI-facing controller methods, and dataclass reconstruction.
- Python remains the owner of currency HTTP providers, API keys, runtime config persistence, cache files, and secrets.
- Rust analytics paths are read-only; SQLite writes, schema migrations, WAL/bootstrap policy, and transaction-local mutation semantics remain Python-owned.
- The GUI refresh snapshot is an optimization seam. Callers that do not expose it still use the existing per-method analytics calls.
- Benchmarks must run against a freshly built and installed `ledgera_core` wheel. A modified Rust checkout alone is not enough evidence.

## Validation Evidence

- `cargo test` in `rust/ledgera_engine`
- `cargo clippy --all-targets -- -D warnings` in `rust/ledgera_engine`
- `maturin build --release --out dist/wheels`
- Fresh `ledgera_core` wheel installation before benchmark validation
- Rust-enabled targeted pytest for `ledgera_core`, bridge, metrics, timeline, currency, and analytics-tab slices
- Forced Python fallback pytest for the Rust-backed analytics/currency wrapper slices
- `npx -y pyright`: `0 errors, 0 warnings`
- GUI-like analytics refresh benchmark reached the alpha.2 speed target after fresh wheel installation; local observed result: `5.22x`

## Deferred

- Rust-owned currency HTTP parsing, provider secrets, and SQLite-backed currency cache persistence.
- Rust-owned SQLite write paths, schema migrations, WAL bootstrap, and transaction-local mutation handling.
- Strict TimelineEngine-specific `>=5x` criterion reporting through a published benchmark result.
- Distribution, Budget, Debt, sync, Kotlin/Native FFI, and Android/Desktop Kotlin UI work.

## Acceptance

Alpha.2 is ready to merge into `v3.0.0-alpha` when the Rust Alpha workflow is green, review feedback is addressed, and the PR documents the known scope boundaries around Python-owned currency I/O and benchmark interpretation.
