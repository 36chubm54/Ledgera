from app_paths import (
    get_json_path,
    get_resource_root,
    get_source_root,
    get_sqlite_path,
    get_user_data_root,
)

PROJECT_ROOT = get_source_root()
RESOURCE_ROOT = get_resource_root()
USER_DATA_ROOT = get_user_data_root()

SQLITE_PATH = str(get_sqlite_path())
JSON_PATH = str(get_json_path())

# How many timestamped JSON backups to keep in `project/backups/`.
# Older backups are pruned on startup after creating a new one.
JSON_BACKUP_KEEP_LAST = 30

# Size threshold (in bytes) for considering the SQLite database "large".
# If the database file size exceeds this value, a background export may be triggered.
LAZY_EXPORT_SIZE_THRESHOLD = 50 * 1024 * 1024  # 50 MiB
