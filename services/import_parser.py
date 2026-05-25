from services.importing import parser as _parser

MAX_CSV_FIELD_SIZE = _parser.MAX_CSV_FIELD_SIZE
MAX_IMPORT_FILE_SIZE = _parser.MAX_IMPORT_FILE_SIZE
MAX_IMPORT_ROWS = _parser.MAX_IMPORT_ROWS
ParsedImportData = _parser.ParsedImportData


def _sync_limits() -> None:
    _parser.MAX_CSV_FIELD_SIZE = MAX_CSV_FIELD_SIZE
    _parser.MAX_IMPORT_FILE_SIZE = MAX_IMPORT_FILE_SIZE
    _parser.MAX_IMPORT_ROWS = MAX_IMPORT_ROWS


def parse_import_file(path: str, *, force: bool = False) -> ParsedImportData:
    _sync_limits()
    return _parser.parse_import_file(path, force=force)


def parse_transfer_row(*args, **kwargs):
    return _parser.parse_transfer_row(*args, **kwargs)


__all__ = [
    "MAX_CSV_FIELD_SIZE",
    "MAX_IMPORT_FILE_SIZE",
    "MAX_IMPORT_ROWS",
    "ParsedImportData",
    "parse_import_file",
    "parse_transfer_row",
]
