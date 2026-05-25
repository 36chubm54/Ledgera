from __future__ import annotations

from app.data.protocols import (
    BudgetRepositoryProtocol,
    DistributionRepositoryProtocol,
)


class _SqlOnlyRepository:
    def query_all(self, sql: str, params: tuple = ()) -> list[object]:
        del sql, params
        return []

    def query_one(self, sql: str, params: tuple = ()) -> object | None:
        del sql, params
        return None

    def query_iter(
        self,
        sql: str,
        params: tuple = (),
        *,
        chunk_size: int = 1000,
    ):
        del sql, params, chunk_size
        yield from ()

    def execute(self, sql: str, params: tuple = ()) -> None:
        del sql, params

    def commit(self) -> None:
        return None

    def transaction(self):
        class _Tx:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> bool:
                del exc_type, exc, tb
                return False

        return _Tx()

    def set_sqlite_sequence(self, table: str, seq: int | None = None) -> None:
        del table, seq


class _BudgetCapableRepository(_SqlOnlyRepository):
    def supports_budget_repository(self) -> bool:
        return True


class _DistributionCapableRepository(_SqlOnlyRepository):
    def supports_distribution_repository(self) -> bool:
        return True


def test_budget_repository_protocol_requires_explicit_budget_capability_marker() -> None:
    assert not isinstance(_SqlOnlyRepository(), BudgetRepositoryProtocol)
    assert isinstance(_BudgetCapableRepository(), BudgetRepositoryProtocol)


def test_distribution_repository_protocol_requires_explicit_distribution_marker() -> None:
    assert not isinstance(_SqlOnlyRepository(), DistributionRepositoryProtocol)
    assert isinstance(_DistributionCapableRepository(), DistributionRepositoryProtocol)
