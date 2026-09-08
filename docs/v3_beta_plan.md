# Ledgera v3 Beta Plan

## Status

The `v3.0.0-alpha` cycle is complete. Alpha delivered the Rust engine
workspace, Python bridge, analytics/currency hot paths, planning write paths,
local Desktop sync MVP, AuditEngine v2 parity, and the first Kotlin Operations
screen over Rust UniFFI.

The beta cycle turns those foundations into a feature-complete cross-platform
client track. Tkinter remains the primary production UI until Kotlin Desktop
feature parity is demonstrated. The roadmap target is still a Rust-centered
architecture with Kotlin Compose Multiplatform UI for Desktop, Android, and
iOS, while Python remains available for migrations, tests, tooling, bridge
compatibility, and controlled fallback during the beta cycle.

## Beta.1 - Kotlin Desktop Feature Parity

Goal: make Kotlin Compose Desktop feature-complete with the current Tkinter
desktop app while preserving Rust/Python fallback boundaries.

Current status:

- Foundation shell is started: Kotlin Desktop has beta.1 runtime framing,
  navigation entries for all 9 roadmap sections, shared engine status/error
  state, and Operations is the active functional workflow.
- Operations standalone record CRUD is wired for income/expense rows, including
  create/list/update/delete, tag replacement, and Rust-side rejection for
  transfer/debt-linked edits.
- Operations transfer creation is wired for base-currency source/target wallet
  transfers with optional base-currency commission marker records; transfer
  editing/deletion is wired for base-currency transfers.
- Operations safe bulk deletion is wired for delete-all and selective-delete
  flows over Operations-owned standalone records, generated mandatory rows,
  transfers, and debt-linked cashflow rows; matching debt history rows are removed
  synchronously when present, while unsupported linked records are preserved and
  reported as skipped. Rust storage normalizes `records.id` after Operations
  write/delete flows and keeps record tags plus debt payment record links
  remapped.
- Operations CSV/XLSX import/export is wired for standalone records, generated
  mandatory rows, aggregate transfer rows, and debt-linked operation rows while
  preserving debt payment record links during same-database replace-import.
  Debt-linked import is strict: rows whose existing debt card, source record,
  or matching payment history cannot be verified are rejected instead of
  detached or recreated.
  Transfer list parity,
  `.xls`/JSON/current-rate import, and commission editing remain later
  Operations slices.
- Operations create/edit dialogs now use the fixed 32-color tag palette plus
  `no color`; tag colors are persisted in SQLite and manual reassignment is
  validated by Rust/Kotlin UniFFI without changing migration headers.
- Settings wallet listing and active base-currency wallet creation are wired,
  which unlocks manual transfer-creator smoke testing on copied ledger DBs.
- Debts wiring is moving in phased slices: Kotlin Desktop can list debts/loans,
  show selected debt payment history, create base-currency debts/loans, register
  payments, register write-offs, close debts/loans, delete debt cards, and
  delete payments through Rust/Kotlin UniFFI while debt-card editing and
  import/export stay pending follow-up slices. Rust storage normalizes
  `debts.id` after debt create/delete flows and remaps debt-linked operation
  rows plus payment history links in the same transaction.
- Mandatory wiring has started: Kotlin Desktop can list/create/update/delete
  mandatory templates, add a template to Operations records, apply due
  auto-payments, and run CSV/XLSX previewed replace-import/export through
  Rust/Kotlin UniFFI. `.xls`, JSON backup/export, current-rate import, and
  wallet creation from import stay pending follow-up slices.
- Reports foundation is wired through Rust/Kotlin UniFFI: Kotlin Desktop can
  generate read-only period reports with Python-compatible wallet/category/tag,
  fixed/current, monthly, category, tag, and debt summaries, and export the
  generated view as CSV, XLSX, or PDF. Reports import is deliberately not part
  of beta.1.
- Remaining beta.1 work is capability wiring and screen parity for the other
  Operations flows and the other sections through Rust/Kotlin UniFFI, not a
  Kotlin-to-Python runtime bridge.

Scope:

- Kotlin Desktop implements all 9 main tabs: Operations, Reports, Analytics,
  Dashboard, Budget, Debts, Distribution, Mandatory, and Settings.
- Operations uses `RecordEngine`, `TransferEngine`, and `TagEngine` surfaces.
- Reports uses `ReportEngine` and `ExportEngine` surfaces for CSV/XLSX/PDF
  workflows.
- Analytics uses `MetricsEngine` and `TimelineEngine` surfaces.
- Dashboard uses `AssetEngine`, `GoalEngine`, and `NetWorthEngine` surfaces.
- Budget, Debts, Distribution, and Mandatory screens use their Rust-backed
  planning service surfaces.
- Settings exposes `SettingsEngine`, `UpdaterEngine`, `AuditEngine`,
  persistence, and runtime configuration controls without moving business rules
  into Kotlin.
- Kotlin navigation supports back-stack behavior and deep links where workflows
  cross screens.
- Kotlin Desktop uses native file dialogs, system tray behavior, and keyboard
  handling appropriate for repeated desktop use.
- Windows and Linux Kotlin Desktop artifacts build reproducibly in CI,
  including the beta.1 installer/package formats chosen for the branch.

Exit criteria:

- All 9 Kotlin Desktop tabs pass smoke testing on Windows and Linux.
- Kotlin Desktop build runs in CI without manual local dependencies.
- Windows `.msi` and Linux package outputs, initially `.deb` where supported by
  the chosen packager, are produced or explicitly deferred with an owner.
- Tkinter still launches as the production UI and rollback path without
  regressions.
- Any `--legacy-ui` flag or equivalent launcher behavior is documented before
  Tkinter is presented as legacy.

Out of scope:

- Android and iOS clients.
- CRDT v2 conflict handling.
- Tkinter removal or hard deprecation before Kotlin parity is proven.

## Beta.2 - Android Client

Goal: bring the shared Kotlin UI and Rust engine to Android.

Scope:

- Rust engine builds for Android ABIs through `cargo-ndk` or an equivalent
  mobile build pipeline.
- Android loads the Rust engine and calls the shared Kotlin/Rust interface.
- Android supports the required Android targets, including
  `aarch64-linux-android`, `x86_64-linux-android`, and any additional ABI kept
  in the release matrix.
- Android UI adapts the beta.1 flows to phone/tablet navigation patterns.
- Android storage and secure preferences integrate with platform facilities
  while preserving Rust-owned persistence contracts.
- Desktop and Android can sync standalone records over the local network.
- Android packaging produces APK/AAB artifacts suitable for test distribution.

Exit criteria:

- APK starts on Android API 26+ on an emulator and at least one real-device
  class.
- A new standalone record created on Desktop or Android appears on the other
  device over LAN within 3 seconds.
- LWW conflict behavior is deterministic for the fields still covered by the
  beta.2 sync contract.
- APK/AAB build is reproducible in CI.

Out of scope:

- iOS client.
- Full operation-aware CRDT v2.
- Cloud relay, external sync service, or account server.

## Beta.3 - iOS and CRDT v2

Goal: add the iOS target and mature sync conflict handling.

Scope:

- Rust engine builds into the iOS distribution format needed by the Kotlin/iOS
  client, with an `xcframework` or equivalent artifact for device and simulator
  targets.
- Kotlin/iOS integrates with native platform storage/preferences where needed,
  including secure storage.
- Compose/iOS or native interop covers the platform-specific dialogs and
  navigation that cannot be shared cleanly.
- Sync conflict handling moves beyond the alpha additive-only MVP and beta.2
  LWW behavior toward operation-aware CRDT behavior.
- CRDT v2 covers tag set operations and record-level vector-clock or equivalent
  operation metadata.
- Kotlin provides a merge UI for critical conflicts that should not be resolved
  silently, especially amount-like financial fields.
- Python becomes a narrower bridge/tooling layer for migrations, scripts,
  documentation, parity tests, optional development APIs, and beta fallback
  where it is still explicitly retained.

Exit criteria:

- iOS build artifacts are produced for device and simulator targets required by
  the chosen test distribution path.
- Desktop, Android, and iOS can participate in the local sync contract covered
  by beta.3 tests.
- CRDT v2 convergence tests cover deterministic merge behavior and manual merge
  handoff for critical conflicts.
- Python-owned fallback paths are either retained intentionally with tests or
  marked for later removal with a documented owner and target milestone.

Out of scope:

- General cloud sync.
- Removing Python as a migration, testing, scripting, or compatibility layer.
- Releasing v3.0.0 without the beta.4 stabilization gates.

## Beta.4 / Release Candidate

Goal: stabilize the v3 release across supported platforms.

Scope:

- Full regression suite covers v2.6.1 behavior plus Rust/Python and
  Kotlin/Rust parity.
- Tkinter is explicitly treated as legacy UI while remaining available for
  rollback.
- Security, performance, packaging, and migration checks are release gates.
- Release artifacts are produced for the Desktop and mobile targets planned for
  v3.0.0.
- Migration guide and final release documentation are ready before RC.

Exit criteria:

- v2.6.1 regression suite and v3 parity suites are green.
- FFI boundaries catch and map Rust panics/errors without crashing Python or JVM
  callers.
- Performance gates are measured against the roadmap targets: startup under
  300ms where applicable and local sync delta under 100ms on LAN.
- Security audit covers Rust dependencies, Kotlin/Gradle dependencies, and the
  release packaging surface, including `cargo audit`, `cargo deny`, and Kotlin
  SAST coverage where the branch enables it.
- Release artifacts are reproducible for all supported v3.0.0 targets: Windows,
  Linux, Android, and any macOS/iOS outputs retained for the release candidate.
- Migration notes, API changes, and breaking-change documentation are complete.

Out of scope:

- New feature work unrelated to release stabilization.
- Tkinter deletion.
- Expanding sync beyond the local-first contract without a separate roadmap.

## Carry-Forward Constraints

- No external cloud service is part of the planned local sync contract.
- Local sync duplicate detection must preserve record multiplicity; two
  distinct identical-looking records are not the same operation unless a later
  CRDT/source-identity layer proves that relationship explicitly.
- Kotlin UI must not own business rules that belong in Rust or Python service
  contracts.
- Rust FFI boundaries must keep panic/error handling explicit and test-covered.
- Rust modules that replace Python behavior need parity tests before they become
  the default path.
- Python fallback remains available during beta unless a path has an explicit
  deprecation decision, tests, and rollback plan.
- Tkinter deprecation must not happen before Kotlin Desktop feature parity is
  demonstrated.
- Historical alpha acceptance docs live in `docs/archive/v3-alpha/`.
