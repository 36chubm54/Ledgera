"""AssetService - manual asset registry, snapshots, and aggregation."""

from __future__ import annotations

from dataclasses import replace

from app.repository_protocols import AssetRepositoryProtocol
from app.services import CurrencyService
from domain.asset import Asset, AssetCategory, AssetSnapshot
from domain.validation import ensure_not_future, parse_ymd
from utils.money import minor_to_money, to_minor_units, to_money_float


class AssetService:
    def __init__(self, repository: AssetRepositoryProtocol, currency: CurrencyService) -> None:
        self._repo = repository
        self._currency = currency

    def create_asset(
        self,
        *,
        name: str,
        category: str,
        currency: str,
        created_at: str,
        description: str = "",
        is_active: bool = True,
    ) -> Asset:
        name_value = str(name or "").strip()
        if not name_value:
            raise ValueError("Asset name is required")
        created_at_text = self._normalize_date(created_at)
        asset = Asset(
            id=self._next_asset_id(),
            name=name_value,
            category=AssetCategory(str(category or "").strip().lower()),
            currency=str(currency or "").strip().upper(),
            is_active=bool(is_active),
            created_at=created_at_text,
            description=str(description or "").strip(),
        )
        self._repo.save_asset(asset)
        return self._repo.get_asset_by_id(asset.id)

    def update_asset(
        self,
        asset_id: int,
        *,
        name: str | None = None,
        category: str | None = None,
        currency: str | None = None,
        created_at: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
    ) -> Asset:
        current = self._repo.get_asset_by_id(int(asset_id))
        updated = replace(
            current,
            name=str(name).strip() if name is not None else current.name,
            category=(
                AssetCategory(str(category or "").strip().lower())
                if category is not None
                else current.category
            ),
            currency=str(currency or current.currency).strip().upper(),
            created_at=self._normalize_date(created_at)
            if created_at is not None
            else current.created_at,
            description=str(description).strip()
            if description is not None
            else current.description,
            is_active=bool(is_active) if is_active is not None else current.is_active,
        )
        self._repo.save_asset(updated)
        return self._repo.get_asset_by_id(int(asset_id))

    def deactivate_asset(self, asset_id: int) -> None:
        if not self._repo.deactivate_asset(int(asset_id)):
            raise ValueError(f"Asset not found: {asset_id}")

    def add_snapshot(
        self,
        *,
        asset_id: int,
        snapshot_date: str,
        value: float,
        currency: str | None = None,
        note: str = "",
    ) -> AssetSnapshot:
        snapshot = self._build_snapshot(
            asset_id=asset_id,
            snapshot_date=snapshot_date,
            value=value,
            currency=currency,
            note=note,
        )
        self._repo.save_asset_snapshot(snapshot)
        return self._load_snapshot_by_asset_date(
            int(snapshot.asset_id), str(snapshot.snapshot_date)
        )

    def bulk_upsert_snapshots(self, entries: list[dict]) -> list[AssetSnapshot]:
        next_snapshot_id = self._next_asset_snapshot_id()
        prepared: list[AssetSnapshot] = []
        for entry in entries:
            prepared.append(
                self._build_snapshot(
                    asset_id=int(entry["asset_id"]),
                    snapshot_date=str(entry["snapshot_date"]),
                    value=float(entry["value"]),
                    currency=entry.get("currency"),
                    note=str(entry.get("note", "") or ""),
                    snapshot_id=next_snapshot_id,
                )
            )
            next_snapshot_id += 1

        with self._repo.transaction():
            for snapshot in prepared:
                self._repo.save_asset_snapshot(snapshot, commit=False)
        return [
            self._load_snapshot_by_asset_date(int(snapshot.asset_id), str(snapshot.snapshot_date))
            for snapshot in prepared
        ]

    def get_assets(self, *, active_only: bool = False) -> list[Asset]:
        return self._repo.load_assets(active_only=active_only)

    def get_asset_history(self, asset_id: int) -> list[AssetSnapshot]:
        self._repo.get_asset_by_id(int(asset_id))
        return self._repo.load_asset_snapshots(int(asset_id))

    def get_latest_snapshots(self, *, active_only: bool = True) -> list[AssetSnapshot]:
        return self._repo.get_latest_asset_snapshots(active_only=active_only)

    def get_total_assets_base(self, *, active_only: bool = True) -> float:
        total = 0.0
        for snapshot in self.get_latest_snapshots(active_only=active_only):
            total += self._currency.convert(
                minor_to_money(int(snapshot.value_minor)),
                str(snapshot.currency),
            )
        return to_money_float(total)

    def get_allocation_by_category(
        self, *, active_only: bool = True
    ) -> list[tuple[str, float, float]]:
        latest_by_asset = self.get_latest_snapshots(active_only=active_only)
        if not latest_by_asset:
            return []
        asset_map = {asset.id: asset for asset in self.get_assets(active_only=active_only)}
        totals: dict[str, float] = {}
        for snapshot in latest_by_asset:
            asset = asset_map.get(int(snapshot.asset_id))
            if asset is None:
                continue
            converted = self._currency.convert(
                minor_to_money(int(snapshot.value_minor)),
                str(snapshot.currency),
            )
            key = str(asset.category.value)
            totals[key] = to_money_float(totals.get(key, 0.0) + converted)
        grand_total = sum(totals.values())
        if grand_total <= 0:
            return [(key, value, 0.0) for key, value in sorted(totals.items())]
        return [
            (key, to_money_float(value), round(value / grand_total * 100.0, 1))
            for key, value in sorted(totals.items())
        ]

    def replace_assets(self, assets: list[Asset], snapshots: list[AssetSnapshot]) -> None:
        asset_ids = {int(asset.id) for asset in assets}
        for snapshot in snapshots:
            if int(snapshot.asset_id) not in asset_ids:
                raise ValueError(
                    f"Asset snapshot #{snapshot.id} references missing asset #{snapshot.asset_id}"
                )
        with self._repo.transaction():
            self._repo.execute("DELETE FROM asset_snapshots")
            self._repo.execute("DELETE FROM assets")
            self._repo.execute("DELETE FROM sqlite_sequence WHERE name = ?", ("asset_snapshots",))
            self._repo.execute("DELETE FROM sqlite_sequence WHERE name = ?", ("assets",))
            for asset in sorted(assets, key=lambda item: int(item.id)):
                self._repo.execute(
                    """
                    INSERT INTO assets (
                        id, name, category, currency, is_active, created_at, description
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(asset.id),
                        str(asset.name),
                        str(asset.category.value),
                        str(asset.currency).upper(),
                        int(bool(asset.is_active)),
                        str(asset.created_at),
                        str(asset.description or ""),
                    ),
                )
            for snapshot in sorted(snapshots, key=lambda item: int(item.id)):
                self._repo.execute(
                    """
                    INSERT INTO asset_snapshots (
                        id, asset_id, snapshot_date, value_minor, currency, note
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(snapshot.id),
                        int(snapshot.asset_id),
                        str(snapshot.snapshot_date),
                        int(snapshot.value_minor),
                        str(snapshot.currency).upper(),
                        str(snapshot.note or ""),
                    ),
                )
            if assets:
                self._repo.set_sqlite_sequence(
                    "assets",
                    max(int(asset.id) for asset in assets),
                )
            if snapshots:
                self._repo.set_sqlite_sequence(
                    "asset_snapshots",
                    max(int(snapshot.id) for snapshot in snapshots),
                )

    def _normalize_date(self, value: str) -> str:
        parsed = parse_ymd(value)
        ensure_not_future(parsed)
        return parsed.isoformat()

    def _next_asset_id(self) -> int:
        return max((int(asset.id) for asset in self._repo.load_assets()), default=0) + 1

    def _next_asset_snapshot_id(self) -> int:
        return (
            max((int(snapshot.id) for snapshot in self._repo.load_asset_snapshots()), default=0) + 1
        )

    def _build_snapshot(
        self,
        *,
        asset_id: int,
        snapshot_date: str,
        value: float,
        currency: str | None = None,
        note: str = "",
        snapshot_id: int | None = None,
    ) -> AssetSnapshot:
        asset = self._repo.get_asset_by_id(int(asset_id))
        snapshot_date_text = self._normalize_date(snapshot_date)
        amount_minor = to_minor_units(value)
        if amount_minor < 0:
            raise ValueError("Asset snapshot value cannot be negative")
        return AssetSnapshot(
            id=self._next_asset_snapshot_id() if snapshot_id is None else int(snapshot_id),
            asset_id=int(asset.id),
            snapshot_date=snapshot_date_text,
            value_minor=amount_minor,
            currency=str(currency or asset.currency).strip().upper(),
            note=str(note or "").strip(),
        )

    def _load_snapshot_by_asset_date(self, asset_id: int, snapshot_date: str) -> AssetSnapshot:
        snapshots = [
            snapshot
            for snapshot in self._repo.load_asset_snapshots(int(asset_id))
            if str(snapshot.snapshot_date) == str(snapshot_date)
        ]
        if not snapshots:
            raise RuntimeError("Failed to load saved asset snapshot")
        return max(snapshots, key=lambda item: int(item.id))
