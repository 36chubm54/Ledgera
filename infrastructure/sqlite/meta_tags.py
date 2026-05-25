from __future__ import annotations

from typing import Any

from domain.tags import Tag
from utils.records.tags import normalize_tag_name


class SQLiteMetaTagsMixin:
    _conn: Any

    def ensure_schema_meta(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def get_schema_meta(self, key: str) -> str | None:
        self.ensure_schema_meta()
        row = self._conn.execute(
            "SELECT value FROM schema_meta WHERE key = ?",
            (str(key),),
        ).fetchone()
        if row is None:
            return None
        return str(row[0])

    def set_schema_meta(self, key: str, value: str) -> None:
        self.ensure_schema_meta()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO schema_meta (key, value)
            VALUES (?, ?)
            """,
            (str(key), str(value)),
        )
        self._conn.commit()

    def list_tags(self) -> list[Tag]:
        rows = self._conn.execute(
            """
            SELECT id, name, color, usage_count, last_used_at
            FROM tags
            ORDER BY last_used_at DESC, usage_count DESC, name COLLATE NOCASE, name
            """
        ).fetchall()
        return [
            Tag(
                id=int(row["id"]),
                name=str(row["name"]),
                color=str(row["color"] or ""),
                usage_count=int(row["usage_count"] or 0),
                last_used_at=str(row["last_used_at"] or ""),
            )
            for row in rows
        ]

    def search_tags(self, prefix: str) -> list[Tag]:
        needle = normalize_tag_name(prefix)
        if not needle:
            return self.list_tags()
        rows = self._conn.execute(
            """
            SELECT id, name, color, usage_count, last_used_at
            FROM tags
            WHERE lower(name) LIKE lower(?)
            ORDER BY last_used_at DESC, usage_count DESC, name COLLATE NOCASE, name
            """,
            (f"{needle}%",),
        ).fetchall()
        return [
            Tag(
                id=int(row["id"]),
                name=str(row["name"]),
                color=str(row["color"] or ""),
                usage_count=int(row["usage_count"] or 0),
                last_used_at=str(row["last_used_at"] or ""),
            )
            for row in rows
        ]
