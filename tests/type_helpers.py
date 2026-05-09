from __future__ import annotations

from typing import cast

from app.repository import RecordRepository


def typed_repo(repo: object) -> RecordRepository:
    return cast(RecordRepository, repo)
