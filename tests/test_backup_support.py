import logging
from pathlib import Path

import pytest

from utils.backup.support import write_json_atomically


def test_write_json_atomically_logs_temp_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    target = tmp_path / "backup.json"

    def _broken_replace(_src: str, _dst: str) -> None:
        raise OSError("disk busy")

    def _broken_unlink(path: str) -> None:
        raise OSError(f"cleanup denied: {path}")

    monkeypatch.setattr("utils.backup.support.os.replace", _broken_replace)
    monkeypatch.setattr("utils.backup.support.os.unlink", _broken_unlink)
    caplog.set_level(logging.WARNING)

    with pytest.raises(OSError, match="disk busy"):
        write_json_atomically(str(target), {"records": []})

    assert "Backup temp file cleanup failed" in caplog.text
    assert "cleanup denied" in caplog.text
